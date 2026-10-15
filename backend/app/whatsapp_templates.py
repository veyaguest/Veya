"""מיפוי שלבי מסלול אישורי ההגעה ל-Templates מאושרים ב-Meta.

למה זה קיים: Meta שולחת ביוזמתנו רק Template שאושר מראש — טקסט קבוע עם
משתנים. הנוסח שבעלי האירוע עורכים במערכת (``EventMessage.content``) **לא**
נשלח כמו שהוא במצבי Meta. כאן נקבע, לכל שלב, איזה Template נשלח ואילו
ערכים ממלאים אותו — כך שהנוסח לא כתוב בתוך קריאת ה-API, ואפשר להחליף
תבנית בלי לגעת בלוגיקת ה-RSVP.

**היום ממופה רק ההזמנה** (2026-10-15, ``docs/whatsapp-templates.md``): תבנית
עם תמונת ההזמנה של האירוע כ-Header, או — לאירוע בלי תמונה — אותו נוסח בלי
תמונה. שאר השלבים ריקים עד שהתבניות שלהם יאושרו. במצבי Meta, שלב בלי
Template לא נשלח, לא נרשם ולא נחשב כאילו הסבב הושלם (``outbound.send_batch``):
כשהתבנית תאושר ותתווסף כאן, הסבב יצא אם החלון שלו עדיין פתוח.

איך מוסיפים Template (אחרי שאושר ב-Meta):
    TEMPLATES["rsvp_request"] = TemplateSpec(
        name="veya_rsvp_request", language="he",
        body_params=("guest_name", "host_names"),   # {{1}}, {{2}} — לפי הסדר
        url_button=True,                            # הסיומת = הטוקן האישי
    )
המפתחות ב-``body_params`` הם מפתחות של ``communication.communication_values``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TemplateSpec:
    name: str
    language: str = "he"
    # ערכי ``{{1}}``, ``{{2}}``… בגוף התבנית, לפי הסדר — מפתחות של
    # ``communication.communication_values(event, guest)``.
    body_params: tuple[str, ...] = ()
    # כפתור "לאישור הגעה" שהקישור שלו נגמר בטוקן האישי של האורח. הכתובת
    # הקבועה (עד ``/confirm/``) מוגדרת ב-Template עצמו ב-Meta.
    url_button: bool = False
    # Header מסוג תמונה — תמונת ההזמנה של האירוע (``messaging.MetaProvider``
    # מעלה אותה ל-Meta פעם אחת למנת שליחה). בלי תמונה — לא נשלח.
    header_image: bool = False
    # גרסה עם תמונה: נבחרת כשלאירוע יש תמונת הזמנה (``template_for``).
    with_image: Optional["TemplateSpec"] = None


_INVITATION_PARAMS = ("guest_name", "event_type", "host_names", "event_date")

# שלב במסלול (``Message.kind`` / ``EventMessage.message_type``) → Template מאושר.
TEMPLATES: dict[str, TemplateSpec] = {
    # הזמנה: כפתור "לצפייה בהזמנה" בלבד — אישור ההגעה נפתח לפי הכללים הקיימים
    # (``guest_journey.rsvp_is_open``), לא מתוך ההזמנה.
    "invitation": TemplateSpec(
        name="veya_invitation", body_params=_INVITATION_PARAMS, url_button=True,
        with_image=TemplateSpec(
            name="veya_invitation_image", body_params=_INVITATION_PARAMS,
            url_button=True, header_image=True,
        ),
    ),
}

# סיבות שבגללן הודעה לא יוצאת במצב Meta (ולא נרשמת).
NO_TEMPLATE = "no_template"
MISSING_VALUE = "missing_value"
# לאירוע יש תמונת הזמנה, אבל אי אפשר להמיר אותה ל-JPEG/PNG — חוסמים (לא שולחים בלעדיה).
IMAGE_UNSUPPORTED = "image_unsupported"
# התמונה לא הועלתה ל-Meta — חוסמים את כל המנה.
IMAGE_UNAVAILABLE = "image_unavailable"
IMAGE_REASONS = frozenset({IMAGE_UNSUPPORTED, IMAGE_UNAVAILABLE})


def template_for(kind: Optional[str], event=None) -> Optional[TemplateSpec]:
    """התבנית לשלב. לשלב עם ``with_image`` ולאירוע עם תמונת הזמנה — הגרסה עם
    התמונה, תמיד (גם אם ההמרה/ההעלאה תיכשל אחר כך — אז חוסמים, לא נופלים לטקסט)."""
    spec = TEMPLATES.get(kind or "")
    if spec is not None and spec.with_image is not None and event is not None and event.invite_image:
        return spec.with_image
    return spec


def build(spec: TemplateSpec, values: dict[str, str], guest_token: Optional[str]):
    """הערכים לשליחה: ``(body_params, url_suffix)``, או ``None`` אם חסר ערך.

    Meta דוחה Template עם משתנה ריק (132000/131008) — עדיף לא לשלוח בכלל
    מאשר לשלוח, להיכשל ו"לשרוף" את הסבב.
    """
    params = [(values.get(key) or "").strip() for key in spec.body_params]
    if any(not p for p in params):
        return None
    suffix = None
    if spec.url_button:
        if not guest_token:
            return None
        suffix = guest_token
    return params, suffix
