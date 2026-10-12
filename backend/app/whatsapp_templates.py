"""מיפוי שלבי מסלול אישורי ההגעה ל-Templates מאושרים ב-Meta.

למה זה קיים: Meta שולחת ביוזמתנו רק Template שאושר מראש — טקסט קבוע עם
משתנים. הנוסח שבעלי האירוע עורכים במערכת (``EventMessage.content``) **לא**
נשלח כמו שהוא במצבי Meta. כאן נקבע, לכל שלב, איזה Template נשלח ואילו
ערכים ממלאים אותו — כך שהנוסח לא כתוב בתוך קריאת ה-API, ואפשר להחליף
תבנית בלי לגעת בלוגיקת ה-RSVP.

**היום הרשימה ריקה — בכוונה.** אף Template של VEYA עוד לא נוצר ולא אושר
(נוסחים — רק באישור המייסד). עד אז, במצבי Meta, שלב בלי Template לא נשלח,
לא נרשם ולא נחשב כאילו הסבב הושלם (``outbound.send_batch``): כשהתבנית תאושר
ותתווסף כאן, הסבב יצא אם החלון שלו עדיין פתוח.

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


# שלב במסלול (``Message.kind`` / ``EventMessage.message_type``) → Template מאושר.
TEMPLATES: dict[str, TemplateSpec] = {}

# סיבות שבגללן הודעה לא יוצאת במצב Meta (ולא נרשמת).
NO_TEMPLATE = "no_template"
MISSING_VALUE = "missing_value"


def template_for(kind: Optional[str]) -> Optional[TemplateSpec]:
    return TEMPLATES.get(kind or "")


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
