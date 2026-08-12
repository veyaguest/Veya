"""שכבת "שירות WhatsApp" — סטטוס הודעות יוצאות, בלי תלות בספק ספציפי.

שרשרת האחריות (ראו architecture.md): ספק ההודעות (``messaging.py``:
``SendResult``/``MockProvider``/``MetaProvider``) → השכבה הזו (ממפה תוצאת
שליחה או webhook לסטטוס אחיד, ומעדכנת/מסכמת את ``Message``) → routers
(חושפים סיכום ל-frontend). כשמחליפים ספק WhatsApp — רק ``messaging.py``
משתנה; השכבה הזו והלאה נשארות זהות.

מקור אמת יחיד לאוצר-המילים של ``Message.status``.

## כלל ברזל: כל סטטוס = רק מה שהמערכת *באמת* יודעת, ולא יותר
יש כאן שני מקורות ידע נפרדים לגמרי, ואסור לערבב ביניהם:
- **ידע מקומי (לפני כל ניסיון שליחה):** תקינות הפורמט של מספר הטלפון לפי
  הכללים שלנו (``invitations.classify_phone``). זה *לא* אישור מ-WhatsApp —
  ``NO_VALID_NUMBER`` אומר "אין לנו מספר תקין לנסות איתו", לא "WhatsApp
  בדקה ואמרה שאין כזה מספר". חתונה עם מספר שחסר/בפורמט שגוי נגזרת לכאן
  בלי לשלוח כלום — היא לעולם לא מקבלת ``Message`` משלה.
- **ידע מהספק (אחרי ניסיון שליחה בפועל):** ``sent``/``delivered``/``read``/
  ``failed`` מגיעים מ-Meta (תגובת ה-API הסינכרונית או ה-webhook). "המספר
  הזה לא רשום ב-WhatsApp" ("not on WhatsApp") הוא *עובדה שרק הספק יכול
  לאשר* — ורק אחרי שניסינו לשלוח למספר שכן עבר את הבדיקה המקומית. היום
  אין לנו את הקוד המפורש הזה מ-Meta (ראו ``map_meta_status`` למטה), ולכן
  אין סטטוס נפרד עבורו — כשל כזה נספר תחת ``FAILED`` הגנרי, לא תחת
  ``NO_VALID_NUMBER``. **לעולם אין לכתוב ל-``NO_VALID_NUMBER`` מתוך תשובת
  webhook** — זה יערבב בין שתי העובדות השונות האלה.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import IS_POSTGRES
from app.invitations import classify_phone

# ---- אוצר המילים (מקור אמת יחיד ל-Message.status) ----
PENDING = "pending"                    # נוצרה במערכת, טרם הועברה לספק (עתידי — תור אסינכרוני)
QUEUED = "queued"                      # טלפון תקין (מקומית), עדיין לא בוצע ניסיון שליחה
SENT = "sent"                          # התקבלה ע"י הספק (מגיע גם מתגובת ה-API וגם מ-webhook)
DELIVERED = "delivered"                # אושרה כנמסרה למכשיר (webhook בלבד)
READ = "read"                          # אושרה כנקראה (webhook בלבד — לא תמיד זמין, ראו הערה למטה)
FAILED = "failed"                      # ניסיון שליחה שכשל — ספק/רשת/כל סיבה שלא סווגה בנפרד
# "אין מספר תקין" — ידע *מקומי בלבד* (חסר/פורמט לא תקין), נגזר לפני כל
# ניסיון שליחה. שונה מהותית מ"המספר לא רשום ב-WhatsApp" (עובדה שרק הספק
# יכול לאשר) — ראו את כלל הברזל למעלה. שם השדה נבחר בכוונה לא לרמוז על
# אישור מה-WhatsApp.
NO_VALID_NUMBER = "no_valid_number"
BLOCKED = "blocked"                    # המוזמן חסם את מספר העסק — ראו [לאימות] למטה

OUTBOUND_STATUSES = frozenset(
    {PENDING, QUEUED, SENT, DELIVERED, READ, FAILED, NO_VALID_NUMBER, BLOCKED}
)

_TIMESTAMP_FIELD = {DELIVERED: "delivered_at", READ: "read_at"}

# סדר התקדמות טבעי של הודעה שנשלחה בפועל. משמש כדי לחסום "נסיגה" כשעדכוני
# webhook מגיעים לא-לפי-סדר (Meta לא מבטיחה סדר הגעה) — ראו _should_skip_regression.
_PROGRESSION = {SENT: 1, DELIVERED: 2, READ: 3}


def outbound_fields(res) -> dict:
    """בונה את שדות ה-DB להודעה יוצאת מתוך תוצאת השליחה של הספק (``SendResult``).

    כל אתר יצירה של הודעה יוצאת עובר דרך הפונקציה הזו — כדי ש-
    ``provider_message_id``/``sent_at``/``failure_reason`` יתנהגו עקבי בכל
    מקום, ולא רק במקום אחד שנזכרים בו.
    """
    fields: dict = {
        "status": res.status,
        "provider": res.provider,
        "provider_message_id": getattr(res, "provider_message_id", "") or None,
    }
    if res.status == SENT:
        fields["sent_at"] = datetime.utcnow()
    elif res.status == FAILED:
        fields["failure_reason"] = res.detail
        error_code = getattr(res, "error_code", None)
        if error_code is not None:
            fields["failure_code"] = error_code
    return fields


def guest_effective_status(guest, latest_by_guest: dict[int, "models.Message"]) -> str:
    """הסטטוס האפקטיבי של מוזמן: ההודעה היוצאת האחרונה שנשלחה אליו — או,
    אם עוד לא נשלחה אליו אף הודעה, נגזר מתקינות מספר הטלפון *המקומית*
    (בלי לחכות ל-webhook — מספר חסר/בפורמט לא תקין ידוע לנו מיד, לפני
    שמנסים לשלוח, ולכן אין סיבה לחכות). זהו אך ורק ``NO_VALID_NUMBER``,
    לעולם לא נגזר כאן סטטוס שמעיד על אישור מהספק.
    """
    msg = latest_by_guest.get(guest.id)
    if msg is not None:
        return msg.status if msg.status in OUTBOUND_STATUSES else SENT
    return QUEUED if classify_phone(guest.phone) == "valid" else NO_VALID_NUMBER


def summarize(guests: list, messages: list) -> dict[str, int]:
    """סיכום סטטוס ההודעות למסך — כל מוזמן נספר פעם אחת (לא כל ניסיון
    שליחה), לפי ההודעה היוצאת האחרונה שנשלחה אליו בכל שלב (הזמנה/תזכורות/
    יום-אירוע/תודה), או נגזר מתקינות הטלפון אם עוד לא נשלחה אליו הודעה.
    """
    latest_by_guest: dict[int, models.Message] = {}
    for m in messages:
        if m.direction != "outbound" or m.guest_id is None:
            continue
        prev = latest_by_guest.get(m.guest_id)
        if prev is None or m.created_at > prev.created_at:
            latest_by_guest[m.guest_id] = m

    counts = {s: 0 for s in (SENT, DELIVERED, READ, FAILED, NO_VALID_NUMBER, BLOCKED, QUEUED)}
    for g in guests:
        status = guest_effective_status(g, latest_by_guest)
        if status == PENDING:
            status = QUEUED  # pending/queued מוצגים כקבוצה אחת ("ממתינים לשליחה")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _matches_audience(guest, audience: str) -> bool:
    """קהל היעד הנוכחי של הודעה (all/pending/confirmed/declined) — מראה
    ``communication._matches_audience``, כפולה קטנה כאן כדי לא ליצור תלות
    מעגלית (communication.py כבר מייבא את המודול הזה)."""
    if audience == "all":
        return True
    return guest.rsvp_status == audience


def summarize_by_type(
    guests: list, messages: list, message_type: str, target_audience: str,
) -> tuple[dict[str, int], list[tuple]]:
    """כמו ``summarize``, אבל מוגבל לסוג הודעה אחד (``kind == message_type``)
    — לכרטיס "מעקב אחרי המוזמנים" שמציג הודעה נבחרת אחת בכל פעם, לא סיכום
    מצטבר על פני כל הרצף. הסטטוס של ההזמנה של מוזמן לעולם לא משפיע כאן על
    הסטטוס של תזכורת 1 שלו — כל סוג הודעה נספר בנפרד לגמרי.

    מוזמן שלא קיבל הודעה מהסוג הזה *וגם* לא נמצא בקהל היעד הנוכחי שלה
    (``target_audience``) לא נכלל בכלל — הוא פשוט לא רלוונטי היום להודעה הזו
    (למשל כבר אישר הגעה, וההודעה מיועדת רק ל"ממתינים לתשובה").

    מחזיר גם רשימת ``(guest, status, message|None)`` לכל מוזמן רלוונטי —
    הבסיס לרשימת "מי קיבל את ההודעה" בכרטיס (חיפוש/סינון בצד הלקוח).
    """
    latest_by_guest: dict[int, models.Message] = {}
    for m in messages:
        if m.direction != "outbound" or m.guest_id is None or m.kind != message_type:
            continue
        prev = latest_by_guest.get(m.guest_id)
        if prev is None or m.created_at > prev.created_at:
            latest_by_guest[m.guest_id] = m

    counts = {s: 0 for s in (SENT, DELIVERED, READ, FAILED, NO_VALID_NUMBER, BLOCKED, QUEUED)}
    rows: list = []
    for g in guests:
        msg = latest_by_guest.get(g.id)
        if msg is not None:
            status = msg.status if msg.status in OUTBOUND_STATUSES else SENT
        elif _matches_audience(g, target_audience):
            status = QUEUED if classify_phone(g.phone) == "valid" else NO_VALID_NUMBER
        else:
            continue
        if status == PENDING:
            status = QUEUED
        counts[status] = counts.get(status, 0) + 1
        rows.append((g, status, msg))
    return counts, rows


def _should_skip_regression(current_status: str, new_status: str) -> bool:
    """מונע "נסיגה" כשעדכוני webhook מגיעים לא-לפי-סדר — Meta לא מבטיחה
    סדר הגעה בין statuses[] שונים. לדוגמה: אם כבר קיבלנו "נקראה", עדכון
    "נמסרה" מאוחר (למשל retry של Meta) לא אמור להחזיר אותנו אחורה. כשל
    שמגיע אחרי שכבר אישרנו מסירה/קריאה נחשב גם הוא מיושן/כפול — לא דורס.
    """
    cur_rank = _PROGRESSION.get(current_status)
    if cur_rank is None:
        return False  # ההודעה עוד לא בציר ההתקדמות (sent/delivered/read) — אין מה לחסום
    new_rank = _PROGRESSION.get(new_status)
    if new_rank is not None:
        return new_rank < cur_rank
    return current_status in (DELIVERED, READ)


def apply_status_update(
    db: Session,
    *,
    provider_message_id: str,
    status: str,
    timestamp: Optional[datetime] = None,
    reason: str = "",
    failure_code: Optional[int] = None,
    provider_status: Optional[str] = None,
) -> bool:
    """מעדכן הודעה יוצאת קיימת לפי מזהה הספק — נקרא מ-webhook. לא עושה
    commit (כמו ``_record_reply``) — הקריאה אחראית לזה, כדי שכמה עדכונים
    מאותה בקשת webhook ייכנסו כטרנזקציה אחת.

    ההתאמה היא לפי ``provider_message_id`` בלבד — מזהה ייחודי-גלובלית
    (wamid אצל Meta; אקראי-בפועל במצב mock) הנשמר על אינדקס ייחודי ב-DB
    (``ux_messages_provider_message_id``, ראו main.py), כדי שלא יהיה מצב
    שבו עדכון להודעה אחת "דולף" לעדכן הודעה של מוזמן אחר.

    ``failure_code``/``provider_status`` נשמרים גולמיים (ללא פרשנות) גם
    כשהם לא משפיעים על ה-status הפנימי — כדי שלא לאבד מידע שאולי יהיה
    שימושי בעתיד (ראו models.py: Message.failure_code/provider_status).

    מחזיר ``True`` אם נמצאה הודעה תואמת (גם אם העדכון בפועל דולג כי הוא
    מיושן/נסיגה — ראו ``_should_skip_regression``), אחרת ``False`` (webhook
    שהגיע למזהה לא מוכר — למשל לפני שההודעה נשמרה, או ניסיון זיוף).
    """
    if not provider_message_id or status not in OUTBOUND_STATUSES:
        return False
    ts = timestamp or datetime.utcnow()

    if IS_POSTGRES:
        from sqlalchemy import text as _text

        row = db.execute(
            _text(
                "SELECT * FROM app_update_message_status"
                "(:pmid, :status, :ts, :reason, :fcode, :pstatus)"
            ),
            {
                "pmid": provider_message_id, "status": status, "ts": ts, "reason": reason,
                "fcode": failure_code, "pstatus": provider_status,
            },
        ).mappings().first()
        return bool(row and row.get("id") is not None)

    msg = db.scalar(
        select(models.Message).where(models.Message.provider_message_id == provider_message_id)
    )
    if msg is None:
        return False
    if provider_status is not None:
        msg.provider_status = provider_status
    if failure_code is not None:
        msg.failure_code = failure_code
    if _should_skip_regression(msg.status, status):
        return True
    msg.status = status
    ts_field = _TIMESTAMP_FIELD.get(status)
    if ts_field:
        setattr(msg, ts_field, ts)
    if status in (FAILED, NO_VALID_NUMBER, BLOCKED) and reason:
        msg.failure_reason = reason
    return True


# ---- מיפוי סטטוסים של Meta (webhook, מצב live) ----
# Meta שולחת אך ורק את ארבעת הערכים האלה בשדה statuses[].status (מתועד
# ב-Cloud API: sent/delivered/read/failed — אין ערך "blocked" נפרד בשדה
# הזה. מקור: developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes
# ומספר מדריכי ספקים עצמאיים שנבדקו יחד, אוגוסט 2026).
_META_STATUS_MAP = {"sent": SENT, "delivered": DELIVERED, "read": READ, "failed": FAILED}

# מיפוי קודי שגיאה (statuses[].errors[].code) לסטטוס פנימי מדויק יותר
# מ-FAILED הגנרי — **רק** כשיש לנו בסיס סביר לכך שהקוד מציין את אותה עובדה
# ספציפית ולא "קטגוריית-על" שמכסה כמה סיבות שונות. בכוונה קצר: עדיף סטטוס
# גנרי ונכון מאשר סטטוס מדויק-לכאורה ושגוי.
#
# קוד 131026 ("Unable to deliver message") **לא** נכלל כאן בכוונה, למרות
# שהוא הקוד הכי נפוץ למספר-לא-ב-WhatsApp: מתיעוד Meta ומספר מדריכי ספקים
# עצמאיים עולה בעקביות שזו קטגוריית-על מכוונת שמאגדת יחד כמה סיבות שונות
# (אין WhatsApp / לא אישר תנאי שימוש / גרסה ישנה / ואולי גם חסימה) בלי
# לחשוף איזו מהן — Meta לא מבחינה כאן בעצמה, ולכן גם אנחנו לא. הודעה עם
# הקוד הזה נשארת FAILED גנרי; failure_code נשמר גולמי כדי שאפשר יהיה
# לחקור מגמות (אם קוד מסוים חוזר הרבה למוזמן מסוים, יש שם סיפור).
#
# קוד 131050 ("This recipient has chosen to stop receiving marketing
# messages") הוא הקוד הכי ספציפי וחד-משמעי שמצאנו: לא קטגוריית-על, אלא
# ציון מפורש שהמוזמן ביקש לא לקבל הודעות. הכי קרוב ל"המוזמן לא רוצה
# הודעות מאיתנו" שיש לנו הוכחה אמיתית עבורו — ולכן ממופה ל-BLOCKED.
# ‏[רמת ביטחון: בינונית — מבוסס תיעוד ציבורי, לא נבדק עדיין מול production
# אמיתי. לאמת מול payload אמיתי מ-Meta כשיהיה חיבור חי, לפני שסומכים על כך
# להחלטות אוטומטיות (למשל הפסקת שליחה למספר הזה).]
_META_ERROR_CODE_STATUS = {
    131050: BLOCKED,
}


def map_meta_status(raw_status: str, errors: Optional[list] = None) -> Optional[str]:
    """ממפה סטטוס גולמי מ-Meta לסטטוס הפנימי שלנו. אם הסטטוס הגולמי הוא
    'failed' ויש errors[] עם קוד שאנחנו סומכים עליו (ראו _META_ERROR_CODE_STATUS),
    מחזיר את הסטטוס המדויק יותר — אחרת FAILED גנרי.
    """
    base = _META_STATUS_MAP.get(raw_status)
    if base != FAILED or not errors:
        return base
    for err in errors:
        code = err.get("code")
        mapped = _META_ERROR_CODE_STATUS.get(code)
        if mapped:
            return mapped
    return base


def first_error_code(errors: Optional[list]) -> Optional[int]:
    if not errors:
        return None
    code = errors[0].get("code")
    return int(code) if isinstance(code, (int, str)) and str(code).lstrip("-").isdigit() else None
