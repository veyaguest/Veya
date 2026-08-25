"""סטטוסים של עסקת מתנה, והמעברים המותרים ביניהם.

חמישה סטטוסים בלבד — לא הומצאו נוספים:

    pending    נוצרה, ממתינה לתשובת ספק הסליקה. **סטטוס הפתיחה תמיד.**
    paid       הספק אישר שהכסף התקבל.
    failed     הספק דחה את התשלום.
    cancelled  ננטשה לפני שהסתיימה (המוזמן סגר, פג תוקף).
    refunded   הוחזרה אחרי שכבר שולמה.

**הכלל שמגן על הכסף:** ``paid`` נקבע אך ורק מתשובת ספק הסליקה — לא מבקשת
ה-Frontend. לקוח יכול לומר "שילמתי" כמה שירצה; הוא לא מקור אמת על תנועת
כסף. לכן המעבר ל-``paid`` עובר תמיד דרך ``gift_service`` שמצטט את הספק
(היום ``MockProvider``, מחר webhook אמיתי).
"""
from __future__ import annotations

PENDING = "pending"
PAID = "paid"
FAILED = "failed"
CANCELLED = "cancelled"
REFUNDED = "refunded"

ALL = (PENDING, PAID, FAILED, CANCELLED, REFUNDED)

# סטטוסים סופיים — מהם אין יציאה.
TERMINAL = (FAILED, CANCELLED, REFUNDED)

# המעברים המותרים. כל מה שלא כאן — אסור.
#
# שים לב למה שחסר בכוונה:
#   failed → pending    ניסיון חוזר הוא **עסקה חדשה**, לא החייאה של ישנה.
#                       כך לא נאבד את העקבות של הניסיון שנכשל.
#   paid → failed       ספק שמדווח כישלון אחרי הצלחה = מחלוקת/ביטול,
#                       והביטוי הנכון לזה הוא refunded.
#   pending → refunded  אי אפשר להחזיר כסף שלא התקבל.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    PENDING: (PAID, FAILED, CANCELLED),
    PAID: (REFUNDED,),
    FAILED: (),
    CANCELLED: (),
    REFUNDED: (),
}


class InvalidStatusTransition(ValueError):
    """ניסיון לעבור בין סטטוסים בדרך שאינה מותרת."""


def can_transition(current: str, target: str) -> bool:
    """האם המעבר מותר. מעבר לאותו סטטוס נחשב מותר (idempotent)."""
    if current == target:
        return True
    return target in TRANSITIONS.get(current, ())


def assert_transition(current: str, target: str) -> None:
    if target not in ALL:
        raise InvalidStatusTransition(f"סטטוס לא מוכר: {target}")
    if not can_transition(current, target):
        raise InvalidStatusTransition(f"מעבר אסור: {current} → {target}")
