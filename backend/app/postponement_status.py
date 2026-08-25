"""סטטוסים של בקשת "נוהל דחייה", והמעברים המותרים ביניהם.

ארבעה סטטוסים, לפי מסלול החיים של אירוע שנדחה:

    pending     בעלי האירוע ביקשו לפתוח נוהל דחייה. **סטטוס הפתיחה.**
    approved    מנהל VEYA אישר — פרטי האירוע פתוחים לעריכה מלאה.
    completed   בעלי האירוע סיימו לעדכן ופתחו מחזור אישורי-הגעה חדש.
    rejected    מנהל VEYA דחה את הבקשה (למשל נפתחה בטעות).

**הכלל שמגן על האירוע:** ``approved`` לעולם אינו נקבע מבקשה של בעלי
האירוע. המעבר אליו עובר דרך ``postponement_service.approve``, שמיועד
לצד המאשר בלבד. מי שמבקש לדחות אינו מי שמאשר את הדחייה — אותו עיקרון
בדיוק שמגן על פרטי קבלת המתנות (``payout_status``).

## למה ``rejected`` קיים

הוא אינו בדרישות המקוריות, שבהן לאדמין יש פעולה אחת בלבד ("אישור נוהל
דחייה"). הוא נוסף כי בלעדיו בקשה שנפתחה בטעות נשארת ``pending`` לנצח:
היא חוסמת את בעלי האירוע מלפתוח בקשה חדשה, ויושבת בתור האדמין בלי שום
דרך להוריד אותה משם. דחייה דורשת סיבה, והסיבה מוצגת לבעלי האירוע.

## מה קובע "האם מותר לערוך את פרטי האירוע"

**תשובה אחת בקוד:** ``unlocks_editing``. אין להעתיק את התנאי לשום מקום
אחר — לא ל-router, לא ל-Frontend. הנעילה עצמה נאכפת ב-
``app/routers/event.py``, והיא שואלת את השאלה הזו ותו לא.
"""
from __future__ import annotations

from typing import Optional

PENDING = "pending"
APPROVED = "approved"
COMPLETED = "completed"
REJECTED = "rejected"

ALL = (PENDING, APPROVED, COMPLETED, REJECTED)

#: סטטוסים שבהם הבקשה "חיה" — כלומר אי אפשר לפתוח בקשה נוספת לאותו אירוע.
#: ``pending`` ממתין להכרעה, ו-``approved`` הוא נוהל שכבר רץ בפועל.
OPEN = (PENDING, APPROVED)

#: הסטטוס היחיד שבו פרטי הליבה של האירוע פתוחים לעריכה.
UNLOCKED = APPROVED

# המעברים המותרים. כל מה שלא כאן — אסור.
#
# שים לב למה שחסר בכוונה:
#   pending → completed     אי אפשר לסיים נוהל שלא אושר.
#   approved → rejected     אחרי שנפתחה עריכה מלאה, "ביטול" אינו דחייה —
#                           הזוג כבר עשוי היה לשנות תאריך ושמות. ביטול
#                           במצב הזה ידרוש החלטה נפרדת של הבעלים.
#   completed → *           מחזור שנסגר נסגר. דחייה נוספת = בקשה חדשה,
#                           שורה חדשה, מחזור חדש.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    PENDING: (APPROVED, REJECTED),
    APPROVED: (COMPLETED,),
    COMPLETED: (),
    REJECTED: (),
}


class InvalidStatusTransition(ValueError):
    """מעבר סטטוס שאינו מותר לפי ``TRANSITIONS``."""


def can_transition(current: str, target: str) -> bool:
    return target in TRANSITIONS.get(current, ())


def assert_transition(current: str, target: str) -> None:
    """זורק ``InvalidStatusTransition`` אם המעבר אסור. שקט אם מותר."""
    if not can_transition(current, target):
        raise InvalidStatusTransition(
            f"מעבר אסור בנוהל הדחייה: {current} → {target}"
        )


def is_open(status: Optional[str]) -> bool:
    """האם הבקשה עדיין חיה (ולכן חוסמת פתיחת בקשה נוספת)."""
    return status in OPEN


def unlocks_editing(status: Optional[str]) -> bool:
    """האם הסטטוס הזה פותח את פרטי האירוע לעריכה מלאה.

    זו התשובה היחידה בקוד לשאלה הזו.
    """
    return status == UNLOCKED
