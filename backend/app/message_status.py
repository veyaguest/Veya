"""שכבת "שירות WhatsApp" — סטטוס הודעות יוצאות, בלי תלות בספק ספציפי.

שרשרת האחריות (ראו architecture.md): ספק ההודעות (``messaging.py``:
``SendResult``/``MockProvider``/``MetaProvider``) → השכבה הזו (ממפה תוצאת
שליחה או webhook לסטטוס אחיד, ומעדכנת/מסכמת את ``Message``) → routers
(חושפים סיכום ל-frontend). כשמחליפים ספק WhatsApp — רק ``messaging.py``
משתנה; השכבה הזו והלאה נשארות זהות.

מקור אמת יחיד לאוצר-המילים של ``Message.status``.
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
PENDING = "pending"                # נוצרה במערכת, טרם הועברה לספק (עתידי — תור אסינכרוני)
QUEUED = "queued"                  # טלפון תקין, עדיין לא בוצע ניסיון שליחה
SENT = "sent"                      # התקבלה ע"י הספק
DELIVERED = "delivered"            # אושרה כנמסרה למכשיר (webhook)
READ = "read"                      # אושרה כנקראה (webhook — לא תמיד זמין)
FAILED = "failed"                  # ניסיון השליחה נכשל (ספק/רשת)
INVALID_NUMBER = "invalid_number"  # אין מספר טלפון תקין לשליחה
BLOCKED = "blocked"                # המוזמן חסם את מספר העסק (webhook)

OUTBOUND_STATUSES = frozenset(
    {PENDING, QUEUED, SENT, DELIVERED, READ, FAILED, INVALID_NUMBER, BLOCKED}
)

_TIMESTAMP_FIELD = {DELIVERED: "delivered_at", READ: "read_at"}


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
    return fields


def guest_effective_status(guest, latest_by_guest: dict[int, "models.Message"]) -> str:
    """הסטטוס האפקטיבי של מוזמן: ההודעה היוצאת האחרונה שנשלחה אליו — או,
    אם עוד לא נשלחה אליו הודעה, נגזר מתקינות מספר הטלפון (בלי לחכות
    ל-webhook כדי לדעת שמספר חסר/לא תקין לא יגיע לשום מקום).
    """
    msg = latest_by_guest.get(guest.id)
    if msg is not None:
        return msg.status if msg.status in OUTBOUND_STATUSES else SENT
    return QUEUED if classify_phone(guest.phone) == "valid" else INVALID_NUMBER


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

    counts = {s: 0 for s in (SENT, DELIVERED, READ, FAILED, INVALID_NUMBER, BLOCKED, QUEUED)}
    for g in guests:
        status = guest_effective_status(g, latest_by_guest)
        if status == PENDING:
            status = QUEUED  # pending/queued מוצגים כקבוצה אחת ("ממתינים לשליחה")
        counts[status] = counts.get(status, 0) + 1
    return counts


def apply_status_update(
    db: Session,
    *,
    provider_message_id: str,
    status: str,
    timestamp: Optional[datetime] = None,
    reason: str = "",
) -> bool:
    """מעדכן הודעה יוצאת קיימת לפי מזהה הספק — נקרא מ-webhook. לא עושה
    commit (כמו ``_record_reply``) — הקריאה אחראית לזה, כדי שכמה עדכונים
    מאותה בקשת webhook ייכנסו כטרנזקציה אחת.

    מחזיר ``True`` אם נמצאה ועודכנה הודעה תואמת, אחרת ``False`` (webhook
    שהגיע למזהה לא מוכר — למשל לפני שההודעה נשמרה, או ניסיון זיוף).
    """
    if not provider_message_id or status not in OUTBOUND_STATUSES:
        return False
    ts = timestamp or datetime.utcnow()

    if IS_POSTGRES:
        from sqlalchemy import text as _text

        row = db.execute(
            _text("SELECT * FROM app_update_message_status(:pmid, :status, :ts, :reason)"),
            {"pmid": provider_message_id, "status": status, "ts": ts, "reason": reason},
        ).mappings().first()
        return bool(row and row.get("id") is not None)

    msg = db.scalar(
        select(models.Message).where(models.Message.provider_message_id == provider_message_id)
    )
    if msg is None:
        return False
    msg.status = status
    ts_field = _TIMESTAMP_FIELD.get(status)
    if ts_field:
        setattr(msg, ts_field, ts)
    if status in (FAILED, INVALID_NUMBER, BLOCKED) and reason:
        msg.failure_reason = reason
    return True


# ---- מיפוי סטטוסים של Meta (webhook, מצב live) ----
# Meta שולחת אך ורק את ארבעת הערכים האלה בשדה statuses[].status (מתועד
# ב-Cloud API). זיהוי עדין יותר (invalid_number/blocked לפי errors[].code)
# דורש קודי שגיאה אמיתיים ממערכת חיה — לא ממציאים אותם כאן; עד אז כל כשל
# שמדווח ה-webhook ממופה ל-FAILED הגנרי.
_META_STATUS_MAP = {"sent": SENT, "delivered": DELIVERED, "read": READ, "failed": FAILED}


def map_meta_status(raw_status: str) -> Optional[str]:
    return _META_STATUS_MAP.get(raw_status)
