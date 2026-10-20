"""מה הזוג יכול לבחור לכל הודעה, ומה יישלח ב-WhatsApp (החלטות הבעלים 2026-10-20).

- **הזמנה, בקשת אישור, תזכורות ותודה** — בוחרים נוסח מספריית הנוסחים, בלי עריכה
  חופשית. כל נוסח בספרייה = תבנית WhatsApp זהה (``whatsapp_library``), ולכן מה
  שהזוג רואה הוא בדיוק מה שהמוזמן מקבל. נוסח שנערך בעבר (לפני ההחלטה) מסומן
  "נערך" — הוא לא יישלח ב-WhatsApp עד שבוחרים נוסח מהרשימה.
- **יום האירוע ושינוי מועד** — נוסח קבוע, זהה לתבניות השירות ב-Meta
  (``whatsapp_templates.FIXED_TEMPLATES``). הזוג רואה אותו ולא בוחר.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models

#: הנוסח הקבוע של ההודעות שאין להן בחירה — אותו טקסט כמו בתבניות ב-Meta
#: (``docs/whatsapp-templates.md``). שורה שכל המשתנים בה ריקים נמחקת בשליחה
#: (``communication.render_message``), ולכן שורת השולחן יוצאת רק כשיש שולחן —
#: בדיוק כמו ``veya_event_day_table`` / ``veya_event_day``.
FIXED_CONTENT: dict[str, str] = {
    "event_day": (
        "היי {{guest_name}},\n"
        "היום מתראים ב{{event_type}} של {{host_names}}.\n"
        "השולחן שלכם: {{table_number}}\n"
        "הניווט וכל הפרטים בקישור האישי.\n"
        "{{rsvp_link}}"
    ),
    # הגרסה בלי תאריך — בטוחה בכל שלב. אחרי שנקבע תאריך חדש נשלחת ב-WhatsApp
    # התבנית עם התאריך והקישור (``veya_postponement``).
    "postponement": (
        "היי {{guest_name}},\n"
        "רצינו לעדכן שיש שינוי במועד {{event_type_definite}} של {{host_names}}.\n"
        "נעדכן אתכם על המועד החדש בהקדם."
    ),
}
FIXED_VARIABLES: dict[str, list[str]] = {
    "event_day": ["guest_name", "event_type", "host_names", "table_number", "rsvp_link"],
    "postponement": ["guest_name", "event_type_definite", "host_names"],
}

LIBRARY = "library"
EDITED = "edited"
FIXED = "fixed"
EMPTY = "empty"

CHOOSE_FROM_LIST = "אפשר לבחור רק נוסח מהרשימה — כך ההודעה ב-WhatsApp זהה בדיוק למה שאתם רואים"
FIXED_WORDING = "הנוסח של ההודעה הזו קבוע, כדי שיישלח ב-WhatsApp"


def options(db: Session, event_type: str, message_type: str) -> list[models.MessageDefaultOption]:
    return list(db.scalars(
        select(models.MessageDefaultOption)
        .where(models.MessageDefaultOption.event_type == event_type)
        .where(models.MessageDefaultOption.message_type == message_type)
        .where(models.MessageDefaultOption.is_active == True)  # noqa: E712
        .where(models.MessageDefaultOption.content != "")
        .order_by(models.MessageDefaultOption.option_number)
    ).all())


def first_option_content(db: Session, event_type: str, message_type: str) -> Optional[str]:
    rows = options(db, event_type, message_type)
    return rows[0].content if rows else None


def validate_content(db: Session, event: models.Event, message_type: str, content: str) -> Optional[str]:
    """``None`` אם מותר לשמור את הנוסח הזה; אחרת ההסבר לזוג."""
    from app import whatsapp_library as wl

    if message_type in FIXED_CONTENT:
        return None if content == FIXED_CONTENT[message_type] else FIXED_WORDING
    if message_type in wl.LIBRARY_TYPES:
        if any(o.content == content for o in options(db, event.event_type, message_type)):
            return None
        return CHOOSE_FROM_LIST
    return None


def info(db: Session, event: models.Event, em: models.EventMessage) -> dict:
    """מאיפה הנוסח, איזו תבנית תישלח ב-WhatsApp, ומה הסטטוס שלה ב-Meta."""
    from app import whatsapp_library as wl
    from app import whatsapp_template_status, whatsapp_templates

    mt = em.message_type
    names: list[str] = []
    if mt in FIXED_CONTENT:
        source = FIXED
        names = ([whatsapp_templates.EVENT_DAY.name, whatsapp_templates.EVENT_DAY_TABLE.name]
                 if mt == "event_day" else
                 [whatsapp_templates.POSTPONEMENT_NO_DATE.name, whatsapp_templates.POSTPONEMENT.name])
    elif not (em.content or "").strip():
        source = EMPTY
    elif mt in wl.LIBRARY_TYPES:
        match = next((o for o in options(db, event.event_type, mt) if o.content == em.content), None)
        if match is None:
            source = EDITED
        else:
            source = LIBRARY
            spec = whatsapp_templates.library_spec(event.event_type, mt, match.option_number, match.content)
            if spec is not None:
                names = [spec.name] + ([spec.with_image.name] if spec.with_image else [])
    else:
        source = EDITED
    statuses = [whatsapp_template_status.status_of(n) for n in names]
    if not names:
        status = None
    elif any(s is None for s in statuses):
        status = None  # לא ידוע (אין חיבור ל-Meta)
    elif all(s == whatsapp_template_status.APPROVED for s in statuses):
        status = whatsapp_template_status.APPROVED
    else:
        status = next(s for s in statuses if s != whatsapp_template_status.APPROVED)
    return {"wording_source": source, "template_name": names[0] if names else None,
            "template_status": status}


def apply_fixed_wordings(db: Session) -> int:
    """מעדכן את נוסח יום האירוע ושינוי המועד בכל האירועים לנוסח הקבוע. idempotent."""
    changed = 0
    for row in db.scalars(
        select(models.EventMessage).where(models.EventMessage.message_type.in_(list(FIXED_CONTENT)))
    ):
        if row.content != FIXED_CONTENT[row.message_type]:
            row.content = FIXED_CONTENT[row.message_type]
            row.variables_supported = list(FIXED_VARIABLES[row.message_type])
            changed += 1
    return changed
