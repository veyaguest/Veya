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

## שני אימותים נפרדים

חשבון צריך לעבור **שתי בדיקות בלתי תלויות** לפני שהוא כשיר לקבל כסף:

    בדיקת VEYA        אדם ב-VEYA מסתכל על אישור ניהול החשבון.
    בדיקת ספק הסליקה  הספק שיעביר את הכסף בפועל (טרם נבחר).

חמשת הסטטוסים למעלה הם **מסלול ה-VEYA בלבד** — הם מתארים את מחזור החיים
של ההגשה אצלנו, ולא נוגעים בספק. תשובת הספק נשמרת בעמודה נפרדת משלה
(``payout_accounts.provider_status``), ואף אחת מהשתיים לא כותבת על השנייה.

מעל שתיהן יושבת שאלה אחת — "האם החשבון כשיר?" — ולה **תשובה אחת בקוד**:
``is_fully_verified``. אין להעתיק את התנאי לשום מקום אחר.
"""
from __future__ import annotations

from typing import Optional

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
# ``verified → rejected`` **כן** מותר, ובכוונה: אישור אינו בלתי הפיך. אם
# מתגלה בדיעבד שהחשבון אינו תקין, VEYA חייבת להיות מסוגלת לבטל אישור
# שכבר ניתן — ואיתו נסגרים מיד גם סכומי המתנות (``is_fully_verified``).
# בלי המעבר הזה, טעות בבדיקה הייתה נעולה עד שבעלי האירוע יערכו פרטים.
#
# אין כאן סטטוס סופי אחד: גם ``verified`` וגם ``rejected`` יכולים לחזור
# ל-``missing`` כשבעלי האירוע עורכים את הפרטים.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    MISSING: (SUBMITTED,),
    SUBMITTED: (UNDER_REVIEW, REJECTED, MISSING),
    UNDER_REVIEW: (VERIFIED, REJECTED, MISSING),
    VERIFIED: (REJECTED, MISSING),
    REJECTED: (SUBMITTED, MISSING),
}


# ── אוצר המילים של בדיקה ─────────────────────────────────────────────────
# שתי הבדיקות (VEYA, ספק) מדברות באותן שלוש מילים. הן מוגדרות כאן, במקום
# אחד, כדי ששני המסלולים לא יתפצלו לשתי מוסכמות שונות ("ok" מול "approved").
REVIEW_PENDING = "pending"
REVIEW_APPROVED = "approved"
REVIEW_REJECTED = "rejected"

REVIEW_ALL = (REVIEW_PENDING, REVIEW_APPROVED, REVIEW_REJECTED)


def veya_review(status: Optional[str]) -> str:
    """תרגום מסלול ה-VEYA (חמישה מצבים) לתשובת בדיקה (שלוש מילים).

    זו **נגזרת, לא עמודה שנייה**: מקור האמת נשאר ``payout_accounts.status``.
    עמודת ``veya_status`` נפרדת הייתה יוצרת שני מקורות שיכולים לסתור זה את
    זה (``status='rejected'`` מול ``veya_status='approved'``), וסתירה כזו
    בשדה שמחליט על כסף היא בדיוק מה שאסור שיקרה.

    ``missing`` ו-``submitted``/``under_review`` כולם ``pending``: מבחינת
    "האם VEYA אישרה" — לא, ולא משנה אם עוד לא הוגש או שהוגש ובבדיקה.
    ההבחנה ביניהם נשמרת ב-``status`` עצמו, ומשמשת את הטקסט שמוצג לזוג.
    """
    if status == VERIFIED:
        return REVIEW_APPROVED
    if status == REJECTED:
        return REVIEW_REJECTED
    return REVIEW_PENDING


def normalize_review(value: Optional[str]) -> str:
    """ערך בדיקה תקין. ``None``/ריק (שורה ישנה מלפני העמודה) = ``pending``."""
    if not value:
        return REVIEW_PENDING
    if value not in REVIEW_ALL:
        raise InvalidStatusTransition(f"סטטוס בדיקה לא מוכר: {value}")
    return value


def is_fully_verified(veya: Optional[str], provider: Optional[str]) -> bool:
    """**התנאי היחיד במערכת** ל"החשבון כשיר לקבל כסף".

    שתי הבדיקות, שתיהן ``approved``. אין קיצור דרך: אישור של VEYA לבדו
    אינו מספיק, ואישור של ספק לבדו אינו מספיק.

    כל מקום שצריך לדעת אם החשבון מאומת קורא לכאן (בדרך כלל דרך
    ``payout_service.is_fully_verified``, שמקבל שורה ולא שתי מחרוזות).
    אין להעתיק את ה-``and`` הזה לשום קובץ אחר.
    """
    return veya == REVIEW_APPROVED and provider == REVIEW_APPROVED


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
