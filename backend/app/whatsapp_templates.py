"""איזו תבנית WhatsApp מאושרת נשלחת לכל הודעה, ובאילו ערכים.

למה זה קיים: Meta שולחת ביוזמתנו רק Template שאושר מראש — טקסט קבוע עם
משתנים. כאן נקבע, לכל הודעה, איזה Template נשלח ואילו ערכים ממלאים אותו.

## איך נבחרת התבנית (2026-10-20, החלטות הבעלים)
1. **הזמנה, בקשת אישור, תזכורות ותודה** — הזוג בוחר נוסח מספריית הנוסחים
   (``MessageDefaultOption``) ולא עורך אותו. לכל נוסח יש תבנית זהה אחד-לאחד
   (``whatsapp_library``): ``veya_wed_rem1_02`` וכו'. מזהים את הנוסח לפי התוכן
   של ``EventMessage``. נוסח שלא נמצא בספרייה (נערך ידנית בעבר) — אין לו תבנית.
   להזמנה יש גם גרסה עם תמונת ההזמנה כ-Header (``…_img``): לאירוע עם תמונה —
   תמיד היא (לא שולחים הזמנה בלי התמונה).
2. **יום האירוע ושינוי מועד** — תבניות שירות קבועות (``docs/whatsapp-templates.md``):
   ``veya_event_day_table`` כשיש למוזמן שולחן, אחרת ``veya_event_day``;
   ``veya_postponement`` אחרי שנקבע תאריך חדש, אחרת ``veya_postponement_no_date``.
3. ``TEMPLATES`` — רישום מפורש שגובר על (1) ו-(2). ריק בייצור; משמש בדיקות.

במצבי Meta, הודעה בלי תבנית לא נשלחת, לא נרשמת ולא "שורפת" את הסבב
(``outbound.send_batch``). המפתחות ב-``body_params`` הם מפתחות של
``communication.communication_values``.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    language: str = "he"
    # ערכי ``{{1}}``, ``{{2}}``… בגוף התבנית, לפי הסדר — מפתחות של
    # ``communication.communication_values(event, guest)``.
    body_params: tuple[str, ...] = ()
    # כפתור ראשון: קישור אישי שנגמר בטוקן של המוזמן (הכתובת הקבועה עד
    # ``/confirm/`` מוגדרת בתבנית עצמה ב-Meta).
    url_button: bool = False
    # כפתור שני: ניווט ב-Google Maps — הסיומת היא הכתובת (``address``).
    navigation_button: bool = False
    # Header מסוג תמונה — תמונת ההזמנה של האירוע (``messaging.MetaProvider``
    # מעלה אותה ל-Meta פעם אחת למנת שליחה). בלי תמונה — לא נשלח.
    header_image: bool = False
    # גרסה עם תמונה: נבחרת כשלאירוע יש תמונת הזמנה (``template_for``).
    with_image: Optional["TemplateSpec"] = None


# רישום מפורש (גובר על הבחירה האוטומטית). ריק בייצור.
TEMPLATES: dict[str, TemplateSpec] = {}

# תבניות השירות הקבועות (הוגשו ל-Meta 2026-10-19).
EVENT_DAY_TABLE = TemplateSpec(
    name="veya_event_day_table",
    body_params=("guest_name", "event_type", "host_names", "table_number"), url_button=True,
)
EVENT_DAY = TemplateSpec(
    name="veya_event_day", body_params=("guest_name", "event_type", "host_names"), url_button=True,
)
POSTPONEMENT = TemplateSpec(
    name="veya_postponement",
    body_params=("guest_name", "event_type_definite", "host_names", "event_date"), url_button=True,
)
POSTPONEMENT_NO_DATE = TemplateSpec(
    name="veya_postponement_no_date",
    body_params=("guest_name", "event_type_definite", "host_names"),
)
FIXED_TEMPLATES = (EVENT_DAY_TABLE, EVENT_DAY, POSTPONEMENT, POSTPONEMENT_NO_DATE)

# סיבות שבגללן הודעה לא יוצאת במצב Meta (ולא נרשמת).
NO_TEMPLATE = "no_template"
# הנוסח של האירוע אינו נוסח מהספרייה (נערך ידנית) — אין לו תבנית ב-Meta.
NOT_LIBRARY_WORDING = "not_library_wording"
# לתבנית עוד אין אישור של Meta (``whatsapp_template_status``).
NOT_APPROVED = "template_not_approved"
MISSING_VALUE = "missing_value"
# לאירוע יש תמונת הזמנה, אבל אי אפשר להמיר אותה ל-JPEG/PNG — חוסמים (לא שולחים בלעדיה).
IMAGE_UNSUPPORTED = "image_unsupported"
# התמונה לא הועלתה ל-Meta — חוסמים את כל המנה.
IMAGE_UNAVAILABLE = "image_unavailable"
IMAGE_REASONS = frozenset({IMAGE_UNSUPPORTED, IMAGE_UNAVAILABLE})


def _library_option(db, event, kind: str):
    """הנוסח מהספרייה שהאירוע בחר להודעה הזו, או ``None``."""
    from sqlalchemy import select

    from app import models

    em = db.scalar(
        select(models.EventMessage)
        .where(models.EventMessage.event_id == event.id)
        .where(models.EventMessage.message_type == kind)
    )
    content = (em.content if em else "") or ""
    if not content.strip():
        return None
    return db.scalars(
        select(models.MessageDefaultOption)
        .where(models.MessageDefaultOption.event_type == event.event_type)
        .where(models.MessageDefaultOption.message_type == kind)
        .where(models.MessageDefaultOption.content == content)
        .order_by(models.MessageDefaultOption.option_number)
    ).first()


def library_spec(event_type: str, kind: str, option_number: int, content: str) -> Optional[TemplateSpec]:
    """התבנית של נוסח מהספרייה (כולל גרסת התמונה להזמנה), או ``None``."""
    from app import whatsapp_library as wl

    t = wl.library_template(event_type, kind, option_number, content)
    if t is None or not t.exact:
        return None
    spec = TemplateSpec(
        name=t.name, body_params=t.params, url_button=bool(t.link_button),
        navigation_button=t.navigation_button,
    )
    if kind == "invitation":
        spec = replace(spec, with_image=replace(spec, name=wl.image_variant(t.name), header_image=True))
    return spec


def resolve(kind: Optional[str], event=None, guest=None) -> tuple[Optional[TemplateSpec], Optional[str]]:
    """``(תבנית, None)`` או ``(None, סיבה)``. לאירוע עם תמונת הזמנה — גרסת התמונה, תמיד
    (גם אם ההמרה/ההעלאה תיכשל אחר כך — אז חוסמים, לא נופלים לנוסח בלי תמונה)."""
    from app import whatsapp_library as wl

    kind = kind or ""
    spec: Optional[TemplateSpec] = TEMPLATES.get(kind)
    if spec is None and event is not None:
        if kind == "event_day":
            table = getattr(guest, "table_number", None) if guest is not None else None
            spec = EVENT_DAY_TABLE if table else EVENT_DAY
        elif kind == "postponement":
            spec = POSTPONEMENT if _new_date_set(event) else POSTPONEMENT_NO_DATE
        elif kind in wl.LIBRARY_TYPES:
            from sqlalchemy.orm import object_session

            db = object_session(event)
            option = _library_option(db, event, kind) if db is not None else None
            if option is None:
                return None, NOT_LIBRARY_WORDING
            spec = library_spec(event.event_type, kind, option.option_number, option.content)
            if spec is None:
                return None, NOT_LIBRARY_WORDING
    if spec is None:
        return None, NO_TEMPLATE
    if spec.with_image is not None and event is not None and event.invite_image:
        spec = spec.with_image
    return spec, None


def _new_date_set(event) -> bool:
    from sqlalchemy.orm import object_session

    from app import postponement_service

    db = object_session(event)
    if db is None:
        return False
    return postponement_service.event_stage(db, event) == postponement_service.STAGE_NEW_DATE


def template_for(kind: Optional[str], event=None, guest=None) -> Optional[TemplateSpec]:
    """התבנית להודעה, או ``None`` (הסיבה — ``resolve``)."""
    return resolve(kind, event, guest)[0]


def build(spec: TemplateSpec, values: dict[str, str], guest_token: Optional[str]):
    """הערכים לשליחה: ``(body_params, url_suffixes)``, או ``None`` אם חסר ערך.

    ``url_suffixes`` — רשימת ``(index, ערך)`` לכפתורי הקישור הדינמיים: 0 = הקישור
    האישי (הטוקן), 1 = ניווט (הכתובת). Meta דוחה Template עם משתנה ריק
    (132000/131008) — עדיף לא לשלוח בכלל מאשר לשלוח, להיכשל ו"לשרוף" את הסבב.
    """
    from urllib.parse import quote_plus

    params = [(values.get(key) or "").strip() for key in spec.body_params]
    if any(not p for p in params):
        return None
    suffixes: list[tuple[int, str]] = []
    if spec.url_button:
        if not guest_token:
            return None
        suffixes.append((0, guest_token))
    if spec.navigation_button:
        address = (values.get("address") or "").strip()
        if not address:
            return None
        suffixes.append((len(suffixes), quote_plus(address)))
    return params, suffixes
