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
from datetime import datetime, timedelta
from typing import Optional

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import automation, event_terms, messaging, models

# ---- סדר קבוע וכינויים ----

MESSAGE_TYPES: list[str] = [
    "invitation", "reminder_1", "reminder_2",
    "final_reminder", "event_day", "thank_you",
]

# אלה שמות השלבים עצמם (ניתנו במפורש ע"י הבעלים) — לא "תוכן הודעה".
MESSAGE_TYPE_LABELS: dict[str, str] = {
    "invitation": "הזמנה",
    "reminder_1": "תזכורת ראשונה",
    "reminder_2": "תזכורת שנייה",
    "final_reminder": "תזכורת אחרונה",
    "event_day": "יום האירוע",
    "thank_you": "תודה",
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

# המשתנים הדינמיים הנתמכים (הרשימה שנקבעה במפורש). "gift_link" תמיד ריק
# היום — אין פיצ'ר מתנות באשראי בנוי (roadmap.md).
VARIABLE_KEYS: list[str] = [
    "guest_name", "guest_names", "host_names", "event_type",
    "event_date", "event_time", "venue_name", "address",
    "navigation_link", "rsvp_link", "table_number", "gift_link",
]

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


def _matches_audience(guest: models.Guest, audience: str) -> bool:
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
) -> bool:
    """האם ההודעה הגיע זמנה עבור המוזמן הזה — עוגן קבוע לפי סוג ההודעה."""
    offset = timedelta(days=em.trigger_offset_days)
    if message_type in ("reminder_1", "reminder_2"):
        anchor = invited_at.get(guest.id)
        return anchor is not None and now >= anchor + offset
    if message_type in ("final_reminder", "event_day", "thank_you"):
        if event_date is None:
            return False
        trigger_day = event_date + timedelta(days=em.trigger_offset_days)
        return now.date() >= trigger_day
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
        messages = list(db.scalars(
            select(models.Message).where(models.Message.event_id == event.id)
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
            if not _matches_audience(guest, em.target_audience):
                continue
            if not _due_now(message_type, em, guest, now, event_date, invited_at):
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
            status=res.status,
            provider=res.provider,
            channel="whatsapp",
            event_message_id=a.event_message.id,
        ))
        if res.ok:
            sent += 1
        else:
            failed += 1
            last_detail = res.detail
    return {"sent": sent, "failed": failed, "detail": last_detail}
