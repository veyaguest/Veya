"""תקשורת עם אורחים — רצף ההודעות הקבוע של אירוע (שלב 1: תשתית).

עיקרון: לכל event_type יש רצף קבוע של 6 סוגי הודעה (``MESSAGE_TYPES``) — לא
עוד ספרייה של קטגוריות/סגנונות לבחירה, לא עוד חוקי אוטומציה חופשיים. כל
אירוע מקבל אוטומטית (idempotent, ראו ``provision_event_messages``) שורת
``EventMessage`` אחת לכל סוג, מועתקת מברירת המחדל הגלובלית שלה
(``MessageDefault``, לפי ``event_type``) — הזוג עורך כאן, לא בוחר מתבניות.

חשוב: ``content`` נשאר ריק (``""``) עד שהבעלים יזין את הטקסטים הסופיים דרך
מסך האדמין (``/admin/message-defaults``). לא ממציאים נוסח כאן.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import (
    automation, event_cycle, event_terms, message_status, messaging, models,
    rsvp_timeline,
)
from app.guest_journey import israel_timezone, now_in_israel

# ---- סדר קבוע וכינויים ----

MESSAGE_TYPES: list[str] = [
    "invitation", "reminder_1", "reminder_2",
    "final_reminder", "event_day", "thank_you",
]

# ---- הודעה מותנית: "אירוע נדחה" ----
#
# ``postponement`` **אינו** ברצף הקבוע למעלה, ובמכוון: אירוע שלא נדחה לא
# אמור לראות כרטיס דחייה בכלל. השורה מוקצית לאירוע רק ברגע שמנהל VEYA מאשר
# נוהל דחייה (``provision_postponement_message``, נקראת מ-
# ``postponement_service.approve``), ומוסתרת שוב מהרצף כשהנוהל נסגר.
#
# היא גם אינה נכנסת לתור ה-due: הודעת דחייה נשלחת **ידנית**, כשהזוג מוכן,
# בדיוק כמו ההזמנה — לא לפי לוח זמנים.
POSTPONEMENT = "postponement"

#: סוגי הודעה שנשלחים **ידנית** דרך ``POST /communication/sequence/{type}/send``.
#: ההזמנה אינה כאן במכוון: היא נשלחת דרך מסלול אישורי-ההגעה, שאוכף
#: "הזמנה אחת בלבד לכל אורח". שני מסלולים לאותה שליחה = הזמנה כפולה.
MANUAL_SEND_TYPES: frozenset[str] = frozenset({POSTPONEMENT})

# אלה שמות השלבים עצמם (ניתנו במפורש ע"י הבעלים) — לא "תוכן הודעה".
MESSAGE_TYPE_LABELS: dict[str, str] = {
    "invitation": "הזמנה",
    "reminder_1": "תזכורת ראשונה",
    "reminder_2": "תזכורת שנייה",
    "final_reminder": "תזכורת אחרונה",
    "event_day": "יום האירוע",
    "thank_you": "תודה",
    POSTPONEMENT: "אירוע נדחה",
}

# עוגן תזמון ברירת מחדל לכל סוג (ימים ביחס לעוגן הקבוע של הסוג — ראו
# _is_due_now). הזמנה נשלחת ידנית (לא דרך תור ה-due), ולכן אין לה עוגן.
DEFAULT_TRIGGER_OFFSET_DAYS: dict[str, int] = {
    "invitation": 0,
    "reminder_1": 3,       # 3 ימים אחרי שליחת ההזמנה
    "reminder_2": 7,       # 7 ימים אחרי שליחת ההזמנה
    "final_reminder": -2,  # יומיים לפני האירוע
    "event_day": 0,        # ביום האירוע עצמו
    "thank_you": 1,        # יום אחרי האירוע
}

# all / pending / confirmed / declined
DEFAULT_TARGET_AUDIENCE: dict[str, str] = {
    "invitation": "all",
    "reminder_1": "pending",
    "reminder_2": "pending",
    "final_reminder": "pending",
    "event_day": "confirmed",
    "thank_you": "confirmed",
}


# ---- שעת שליחה (שעון ישראל, ללא תאריך/אזור-זמן) ----
#
# הזוג בוחר שעה אחת ("HH:MM") שחלה על כל הודעות מסלול אישורי-ההגעה
# (reminder_1/reminder_2/final_reminder/event_day — invitation נשלחת ידנית
# ולא דרך תור ה-due, ולכן אין לה שעה) — ``Event.rsvp_send_time``. הודעת
# התודה מקבלת הגדרת שעה נפרדת משלה — ``Event.thank_you_send_time`` — כי
# היא נשלחת יום אחרי האירוע, בהקשר שונה לגמרי מהתזכורות.
#
# הטווח המותר תואם לשעות סבירות לשליחת הודעות למוזמנים — לא לפנות בוקר
# ולא בלילה.
SEND_TIME_MIN = "10:00"
SEND_TIME_MAX = "19:00"
# ברירת מחדל בטוחה (גם למשתמשים קיימים, ראו _EXTRA_COLUMNS ב-main.py):
# באמצע הטווח, כדי שלא תיפול בטעות על אחד מגבולותיו.
DEFAULT_SEND_TIME = "16:00"

_SEND_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def parse_send_time(value: str) -> time:
    """הופך "HH:MM" ל-``time``. זורק ``ValueError`` אם הפורמט לא תקין."""
    m = _SEND_TIME_RE.match((value or "").strip())
    if not m:
        raise ValueError(f"פורמט שעה לא תקין: '{value}' (נדרש HH:MM)")
    return time(hour=int(m.group(1)), minute=int(m.group(2)))


def validate_send_time(value: str) -> str:
    """בדיקת תקינות שעת שליחה שהזוג בוחר: פורמט "HH:MM" בטווח
    ``SEND_TIME_MIN``–``SEND_TIME_MAX`` בלבד (שעון ישראל; אין כאן תאריך
    ואין אזור-זמן לבחירה — שניהם קבועים). זו נקודת האכיפה היחידה — כל שמירה
    של שעת שליחה (RSVP או תודה) חייבת לעבור דרכה לפני שהיא נכתבת ל-DB.
    """
    t = parse_send_time(value)
    if not (parse_send_time(SEND_TIME_MIN) <= t <= parse_send_time(SEND_TIME_MAX)):
        raise ValueError(f"שעת השליחה חייבת להיות בין {SEND_TIME_MIN} ל-{SEND_TIME_MAX}")
    return f"{t.hour:02d}:{t.minute:02d}"


def _scheduled_moment(day: date, send_time: str) -> datetime:
    """היום שחושב + שעת השליחה שנבחרה, בשעון ישראל — אחרי דחיית סוף שבוע.

    דחיית סוף השבוע *אינה* לוגיקה חדשה: זהו בדיוק המנגנון הקיים שכבר מדלג
    שישי/שבת ליום הפעיל הבא בתצוגת לוח הזמנים (``rsvp_timeline``) — כאן הוא
    מופעל גם על התזמון בפועל של השליחה, כדי שהודעה לעולם לא תתוזמן בזמן
    אסור. ``send_time`` לא תקין (ריק/פגום) נופל בעדינות ל-``DEFAULT_SEND_TIME``
    במקום להפיל את תור ה-due כולו.
    """
    if rsvp_timeline.is_weekend(day):
        day = rsvp_timeline.next_active_day(day)
    try:
        t = parse_send_time(send_time)
    except ValueError:
        t = parse_send_time(DEFAULT_SEND_TIME)
    tz = israel_timezone()
    return datetime.combine(day, t, tzinfo=tz)


# המשתנים הדינמיים הנתמכים (הרשימה שנקבעה במפורש). "gift_link" תמיד ריק
# היום — אין פיצ'ר מתנות באשראי בנוי (roadmap.md).
VARIABLE_KEYS: list[str] = [
    "guest_name", "guest_names", "host_names", "event_type",
    "event_date", "event_time", "venue_name", "address",
    "navigation_link", "rsvp_link", "table_number", "gift_link",
]

# הרחבה ייעודית לחתונה בלבד (הוחלט 2026-08-06): לצד host_names הכללי
# (המשותף לכל סוגי האירוע), נוסחי החתונה מפרידים בפירוש בין שני בעלי
# האירוע. לא מוצעים בעורך לסוגי אירוע אחרים — ראו DEFAULT_VARIABLES_SUPPORTED.
WEDDING_ONLY_VARIABLE_KEYS: list[str] = ["groom_name", "bride_name"]

# אילו משתנים רלוונטיים לכל סוג הודעה — להצעה בעורך (לא חוסם שימוש באחרים).
DEFAULT_VARIABLES_SUPPORTED: dict[str, list[str]] = {
    "invitation": [
        "guest_name", "guest_names", "host_names", "event_type",
        "event_date", "event_time", "venue_name", "address", "rsvp_link",
    ],
    "reminder_1": ["guest_name", "guest_names", "host_names", "event_date", "rsvp_link"],
    "reminder_2": ["guest_name", "guest_names", "host_names", "event_date", "rsvp_link"],
    "final_reminder": ["guest_name", "guest_names", "event_date", "event_time", "rsvp_link"],
    "event_day": [
        "guest_name", "guest_names", "event_time", "venue_name", "address",
        "navigation_link", "table_number",
    ],
    "thank_you": ["guest_name", "guest_names", "host_names", "gift_link"],
    # הודעת דחייה — רשימה מכוונת-מיעוט, משתי סיבות:
    # · בלי ``rsvp_link``: המחזור החדש עוד לא נפתח, וקישור אישור הגעה היה
    #   מוביל את האורח לאשר הגעה למועד שכבר לא קיים. האישור מחדש מגיע
    #   בהזמנה החדשה.
    # · בלי ``event_date``: בשלב הזה התאריך שבאירוע יכול להיות עדיין הישן
    #   *או* כבר החדש, תלוי מתי הזוג שולח. משתנה שמשמעותו משתנה לפי תזמון
    #   הוא בדיוק הדרך לשלוח לאורחים תאריך שגוי.
    POSTPONEMENT: ["guest_name", "guest_names", "host_names", "event_type", "venue_name"],
}


# ---- רינדור: {{var}} -> ערך, שורה עם משתנה ריק נמחקת ----

_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render_message(content: str, values: dict[str, str]) -> str:
    """ממלא משתני ``{{key}}`` בתוכן. שורה שכל המשתנים בה ריקים נמחקת כליל
    (כמו ``messaging.render_automation_template`` — "תוכן חכם"), כדי שלא
    יישאר "מספר השולחן שלכם: " כשעדיין אין שיבוץ."""
    if not content:
        return ""
    out_lines: list[str] = []
    for line in content.split("\n"):
        keys_in_line = _VAR_RE.findall(line)
        if keys_in_line and all(not values.get(k) for k in keys_in_line):
            continue
        out_lines.append(_VAR_RE.sub(lambda m: values.get(m.group(1), ""), line))
    text = "\n".join(out_lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def communication_values(event: models.Event, guest: Optional[models.Guest] = None) -> dict[str, str]:
    """כל 12 המשתנים הנתמכים, עם ערכי אמת של האירוע (ושל מוזמן אם סופק)."""
    terms = event_terms.get_event_terms(event.event_type)
    host_names = event_terms.hosts_names(event.event_type, event.groom_name, event.bride_name)
    values: dict[str, str] = {
        "host_names": host_names,
        "groom_name": event.groom_name or "",
        "bride_name": event.bride_name or "",
        "event_type": terms.celebration,
        "event_date": automation.event_date_display(event),
        "event_time": event.event_time or "",
        "venue_name": event.venue_name or "",
        "address": event.venue_address or "",
        "navigation_link": messaging.maps_link(event.venue_address or ""),
        "gift_link": "",  # אין פיצ'ר מתנות באשראי בנוי עדיין — roadmap.md
    }
    if guest is not None:
        values["guest_name"] = guest.full_name or ""
        values["guest_names"] = guest.full_name or ""
        values["rsvp_link"] = messaging.confirm_link(guest.guest_token)
        values["table_number"] = str(guest.table_number) if guest.table_number else ""
    else:
        values.setdefault("guest_name", "")
        values.setdefault("guest_names", "")
        values.setdefault("rsvp_link", "")
        values.setdefault("table_number", "")
    return values


# ---- הקצאה idempotent מ-MessageDefault לאירוע ----

def provision_event_messages(db: Session, event: models.Event) -> int:
    """יוצר את שורות ה-``EventMessage`` החסרות לאירוע, לפי ``event.event_type``.

    idempotent: לא נוגע בשורה קיימת (גם אם ריקה) — כדי לא לדרוס עריכה של
    הזוג/ברירת מחדל שכבר הוקצתה. מחזיר כמה שורות נוצרו.
    """
    existing_types = set(db.scalars(
        select(models.EventMessage.message_type)
        .where(models.EventMessage.event_id == event.id)
    ).all())
    missing = [mt for mt in MESSAGE_TYPES if mt not in existing_types]
    if not missing:
        return 0

    defaults_by_type = {
        d.message_type: d
        for d in db.scalars(
            select(models.MessageDefault)
            .where(models.MessageDefault.event_type == event.event_type)
        ).all()
    }
    created = 0
    for mt in missing:
        d = defaults_by_type.get(mt)
        db.add(models.EventMessage(
            event_id=event.id,
            message_type=mt,
            title=d.title if d else MESSAGE_TYPE_LABELS[mt],
            content=d.content if d else "",
            variables_supported=(
                list(d.variables_supported) if d and d.variables_supported
                else list(DEFAULT_VARIABLES_SUPPORTED.get(mt, []))
            ),
            is_active=d.is_active if d else True,
            trigger_offset_days=DEFAULT_TRIGGER_OFFSET_DAYS.get(mt, 0),
            target_audience=DEFAULT_TARGET_AUDIENCE.get(mt, "pending"),
        ))
        created += 1
    db.flush()
    return created


def provision_postponement_message(db: Session, event: models.Event) -> bool:
    """מקצה לאירוע את שורת הודעת "אירוע נדחה". מחזיר האם נוצרה שורה חדשה.

    נקראת **רק** מ-``postponement_service.approve`` — לא מיצירת אירוע ולא מ-
    ``provision_event_messages``. אירוע שלא נדחה לעולם לא מקבל את השורה הזו.

    idempotent: דחייה שנייה לאותו אירוע משתמשת בשורה שכבר קיימת, כולל
    הנוסח שהזוג ערך בפעם הקודמת — לא דורסת אותו בברירת המחדל.
    """
    existing = db.scalars(
        select(models.EventMessage)
        .where(models.EventMessage.event_id == event.id)
        .where(models.EventMessage.message_type == POSTPONEMENT)
    ).first()
    if existing is not None:
        return False

    default = db.scalars(
        select(models.MessageDefault)
        .where(models.MessageDefault.event_type == event.event_type)
        .where(models.MessageDefault.message_type == POSTPONEMENT)
    ).first()
    db.add(models.EventMessage(
        event_id=event.id,
        message_type=POSTPONEMENT,
        title=default.title if default else MESSAGE_TYPE_LABELS[POSTPONEMENT],
        # ריק עד שהבעלים יזין נוסחים במסך האדמין — לא ממציאים תוכן כאן.
        content=default.content if default else "",
        variables_supported=(
            list(default.variables_supported) if default and default.variables_supported
            else list(DEFAULT_VARIABLES_SUPPORTED[POSTPONEMENT])
        ),
        is_active=True,
        # אין עוגן תזמון: ההודעה נשלחת ידנית ואינה נכנסת לתור ה-due.
        trigger_offset_days=0,
        # ברירת מחדל "כולם": כשאירוע נדחה, גם מי שסירב וגם מי שטרם השיב
        # צריכים לדעת. הזוג יכול לצמצם לפני השליחה.
        target_audience="all",
    ))
    db.flush()
    return True


def event_messages_by_type(db: Session, event_id: int) -> dict[str, models.EventMessage]:
    rows = db.scalars(
        select(models.EventMessage).where(models.EventMessage.event_id == event_id)
    ).all()
    return {r.message_type: r for r in rows}


# ---- תור ה-due (רק reminder_1/reminder_2/final_reminder/event_day/thank_you —
#      invitation נשלחת ידנית דרך פעולת "שליחת הזמנות" הקיימת) ----

@dataclass
class DueMessageAction:
    """שורה בתור לאישור: הודעה (EventMessage) + מוזמן שהגיע זמנו + תצוגה מקדימה."""

    event_message: models.EventMessage
    guest: models.Guest
    preview: str


def _invited_at(messages: list[models.Message]) -> dict[int, datetime]:
    out: dict[int, datetime] = {}
    for m in messages:
        if m.guest_id is None:
            continue
        if m.direction == "outbound" and m.kind == "invitation" and m.status == "sent":
            prev = out.get(m.guest_id)
            if prev is None or m.created_at < prev:
                out[m.guest_id] = m.created_at
    return out


def _already_sent(messages: list[models.Message]) -> set[tuple[int, int]]:
    """זוגות (event_message_id, guest_id) שכבר נשלחו — dedup."""
    return {
        (m.event_message_id, m.guest_id)
        for m in messages
        if m.event_message_id is not None and m.guest_id is not None
    }


def matches_audience(guest: models.Guest, audience: str) -> bool:
    """האם המוזמן שייך לקהל היעד (``all``/``pending``/``confirmed``/``declined``).

    ציבורית כי גם שליחה ידנית (``routers/communication.py``) בוחרת קהל באותו
    אוצר מילים — ואין סיבה שיהיו שתי הגדרות ל"מי נכלל".
    """
    if audience == "all":
        return True
    return guest.rsvp_status == audience


def _due_now(
    message_type: str,
    em: models.EventMessage,
    guest: models.Guest,
    now: datetime,
    event_date,
    invited_at: dict[int, datetime],
    event: models.Event,
) -> bool:
    """האם ההודעה הגיע זמנה עבור המוזמן הזה — עוגן קבוע לפי סוג ההודעה, עד
    היום; משם ואילך גם שעת השליחה שהזוג בחר (שעון ישראל, ראו
    ``_scheduled_moment``). "תודה" משתמשת בשעה הנפרדת שלה
    (``thank_you_send_time``); שאר סוגי ההודעה במסלול משתמשים באותה שעה
    אחת (``rsvp_send_time``).
    """
    now_il = now_in_israel(now)
    if message_type in ("reminder_1", "reminder_2"):
        anchor = invited_at.get(guest.id)
        if anchor is None:
            return False
        # יום ה"בסיס" נגזר מהיום (שעון ישראל) שבו נשלחה ההזמנה בפועל — לא
        # מהרגע המדויק שלה — כי מה שהזוג בחר הוא שעה ביום, לא מרווח שעות.
        trigger_day = now_in_israel(anchor).date() + timedelta(days=em.trigger_offset_days)
        return now_il >= _scheduled_moment(trigger_day, event.rsvp_send_time)
    if message_type in ("final_reminder", "event_day"):
        if event_date is None:
            return False
        trigger_day = event_date + timedelta(days=em.trigger_offset_days)
        return now_il >= _scheduled_moment(trigger_day, event.rsvp_send_time)
    if message_type == "thank_you":
        if event_date is None:
            return False
        trigger_day = event_date + timedelta(days=em.trigger_offset_days)
        return now_il >= _scheduled_moment(trigger_day, event.thank_you_send_time)
    return False


def compute_due_messages(
    db: Session,
    event: models.Event,
    *,
    guests: Optional[list[models.Guest]] = None,
    messages: Optional[list[models.Message]] = None,
    now: Optional[datetime] = None,
) -> list[DueMessageAction]:
    """מחשב את תור הפעולות שהגיע זמנן, לכל סוגי ההודעה חוץ מ"הזמנה" (שנשלחת
    ידנית). ללא תופעות לוואי — רק חישוב, בדיוק כמו ``automation.compute_due_actions``.
    """
    now = now or datetime.utcnow()
    if guests is None:
        guests = list(db.scalars(
            select(models.Guest).where(models.Guest.event_id == event.id)
        ).all())
    if messages is None:
        # רק שליחות של המחזור הנוכחי: אחרי דחייה, תזכורת שיצאה למועד
        # הישן אינה "כבר נשלחה" — הסבב החדש מתחיל נקי.
        messages = list(db.scalars(
            select(models.Message)
            .where(models.Message.event_id == event.id)
            .where(event_cycle.current_sends(event))
        ).all())

    event_date = automation.parse_event_date(event.event_date)
    invited_at = _invited_at(messages)
    sent = _already_sent(messages)

    by_type = event_messages_by_type(db, event.id)
    actions: list[DueMessageAction] = []
    for message_type in MESSAGE_TYPES:
        if message_type == "invitation":
            continue  # שליחה ידנית — לא דרך התור
        em = by_type.get(message_type)
        if em is None or not em.is_active or not em.content:
            continue
        for guest in guests:
            if (em.id, guest.id) in sent or not guest.phone:
                continue
            if not matches_audience(guest, em.target_audience):
                continue
            if not _due_now(message_type, em, guest, now, event_date, invited_at, event):
                continue
            preview = render_message(em.content, communication_values(event, guest))
            if not preview:
                continue
            actions.append(DueMessageAction(event_message=em, guest=guest, preview=preview))
    return actions


def send_due_messages(
    db: Session, event: models.Event, actions: list[DueMessageAction],
) -> dict:
    """שולח בפועל (mock/live) את הפעולות שאושרו. לא עושה commit."""
    provider = messaging.get_provider()
    sent = failed = 0
    last_detail = ""
    for a in actions:
        res = provider.send_invitation(a.guest.phone, a.preview)
        db.add(models.Message(
            event_id=event.id,
            guest_id=a.guest.id,
            direction="outbound",
            kind=a.event_message.message_type,
            body=a.preview,
            channel="whatsapp",
            event_message_id=a.event_message.id,
            cycle_number=event_cycle.of(event),
            **message_status.outbound_fields(res),
        ))
        if res.ok:
            sent += 1
        else:
            failed += 1
            last_detail = res.detail
    return {"sent": sent, "failed": failed, "detail": last_detail}
