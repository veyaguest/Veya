"""סטטוסים של פרטי קבלת המתנות, והמעברים המותרים ביניהם.

חמישה סטטוסים, לפי מסלול החיים של חשבון בנק שממתין לאימות:

    missing       אין פרטים, או שהם נערכו ועדיין לא הוגשו. **סטטוס הפתיחה.**
    submitted     בעלי האירוע הגישו את הפרטים ואת אישור ניהול החשבון.
    under_review  VEYA (או ספק בעתיד) התחילה לבדוק אותם.
    verified      הפרטים אומתו — מכאן אפשר להעביר אליהם כסף.
    rejected      הבדיקה נכשלה (אישור לא קריא, שם לא תואם וכו').

**הכלל שמגן על הכסף:** ``verified`` לעולם אינו נקבע מבקשה של בעלי האירוע.
המעבר אליו עובר דרך ``payout_service.set_status``, שמיועד לצד הבודק —
אדם ב-VEYA היום, adapter של ספק מחר. מי שמזין את פרטי החשבון אינו מי
שמאשר אותם.

**עריכה מבטלת אימות.** שינוי של קוד הבנק, הסניף או מספר החשבון מחזיר את
הסטטוס ל-``missing`` (ראו ``payout_service.save_details``). חשבון שאומת
ואז הוחלף אינו חשבון מאומת — אחרת אפשר היה לעבור אימות עם חשבון אחד
ולהחליף אותו אחרי כן בחשבון אחר.
"""
from __future__ import annotations

MISSING = "missing"
SUBMITTED = "submitted"
UNDER_REVIEW = "under_review"
VERIFIED = "verified"
REJECTED = "rejected"

ALL = (MISSING, SUBMITTED, UNDER_REVIEW, VERIFIED, REJECTED)

#: סטטוסים שבהם הפרטים אצל VEYA וממתינים להכרעה — אין מה לעשות מלבד לחכות.
PENDING_REVIEW = (SUBMITTED, UNDER_REVIEW)

# המעברים המותרים. כל מה שלא כאן — אסור.
#
# שים לב למה שחסר בכוונה:
#   missing → verified        אי אפשר לאמת מה שלא הוגש.
#   submitted → verified      אימות עובר תמיד דרך בדיקה מפורשת
#                             (under_review), כדי שתמיד יהיה תיעוד של מי
#                             בדק ומתי — ולא "קפיצה" ישירה.
#   rejected → verified       דחייה נסגרת רק בהגשה מחודשת של הפרטים.
#   verified → under_review   בדיקה חוזרת מתחילה מהגשה, לא מאמצע.
#
# אין כאן סטטוס סופי אחד: גם ``verified`` וגם ``rejected`` יכולים לחזור
# ל-``missing`` כשבעלי האירוע עורכים את הפרטים.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    MISSING: (SUBMITTED,),
    SUBMITTED: (UNDER_REVIEW, REJECTED, MISSING),
    UNDER_REVIEW: (VERIFIED, REJECTED, MISSING),
    VERIFIED: (MISSING,),
    REJECTED: (SUBMITTED, MISSING),
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
