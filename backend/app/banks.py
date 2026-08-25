"""בנקים ישראליים — ולידציה של פרטי חשבון לקבלת מתנות.

הרשימה עצמה נמצאת ב-``banks_data.py`` ונוצרת אוטומטית מנתוני **בנק ישראל**
(ראו ``tools/fetch_israeli_banks.py``). הקובץ הזה מוסיף מעליה את הכללים.

**עיקרון:** קוד הבנק הוא נתון נפרד ובדיד — הוא נבחר מרשימה סגורה ונבדק מולה
בשרת. הוא לעולם לא נגזר מהטקסט שהמשתמש הקליד, כי שם בנק שהוקלד ידנית
("פועלים", "בנק הפועלים בעמ") אינו מזהה חד-משמעי, וכסף שנשלח לפי פרשנות של
טקסט חופשי הוא כסף שהולך לאיבוד.
"""
from __future__ import annotations

import re

from app.banks_data import BANKS, BY_CODE, SOURCE, SOURCE_UPDATED, Bank

__all__ = [
    "BANKS", "BY_CODE", "SOURCE", "SOURCE_UPDATED", "Bank",
    "BranchError", "normalize_bank_code", "normalize_branch", "normalize_account",
    "BRANCH_MAX_DIGITS", "ACCOUNT_MIN_DIGITS", "ACCOUNT_MAX_DIGITS",
]

# אורכים אמיתיים: במאגר "סניפים לסליקה" של בנק ישראל קודי הסניפים הפתוחים
# נעים בין 1 ל-999 — כלומר עד שלוש ספרות. מוצג תמיד מרופד לשלוש ("045"),
# כי כך הוא מופיע באישור ניהול החשבון.
BRANCH_MAX_DIGITS = 3

# מספר חשבון: האורך משתנה מבנק לבנק (6 ספרות בהפועלים, 8 בלאומי, 9
# בדיסקונט ועוד), ואין מקור רשמי שמפרסם טווח מחייב לכל בנק. לכן הטווח כאן
# רחב בכוונה — הוא חוסם שגיאות הקלדה גסות (ספרה אחת, או מספר כרטיס אשראי
# שהודבק בטעות) בלי לפסול חשבון אמיתי של אף בנק.
ACCOUNT_MIN_DIGITS = 4
ACCOUNT_MAX_DIGITS = 13


# ספרות, עם מקף או רווח בודד כמפריד בין קבוצות בלבד. ASCII במפורש: ספרות
# עבריות/ערביות-הודיות אינן קלט תקין למספר חשבון, ו-``str.isdigit`` היה
# מקבל אותן.
_SEPARATED_DIGITS = re.compile(r"[0-9]+(?:[-\s][0-9]+)*")
_SEPARATORS = re.compile(r"[-\s]")


class BranchError(ValueError):
    """שגיאת ולידציה עם נוסח עברי מוכן להצגה למשתמש."""


def _digits_only(raw: object, field: str) -> str:
    """מחזיר את הערך כספרות בלבד, או זורק שגיאה בעברית.

    מקבל גם מקפים ורווחים (אנשים מעתיקים "12-345" מהאישור) ומנקה אותם, אבל
    כל תו אחר — אות, סימן — נפסל במפורש ולא "נשתק" בשקט.
    """
    if isinstance(raw, bool) or raw is None:
        raise BranchError(f"חסר {field}")
    text = str(raw).strip()
    if not text:
        raise BranchError(f"חסר {field}")
    # מקף/רווח מותרים רק **בין** קבוצות ספרות ("12-345 67"), כי כך אנשים
    # מעתיקים מאישור הבנק. מקף בהתחלה הוא סימן מינוס, לא מפריד — ולכן
    # "-12" נדחה ולא הופך בשקט ל-12.
    if not _SEPARATED_DIGITS.fullmatch(text):
        raise BranchError(f"{field} יכול להכיל ספרות בלבד")
    return _SEPARATORS.sub("", text)


def normalize_bank_code(raw: object) -> int:
    """מאמת שקוד הבנק קיים ברשימת בנק ישראל, ומחזיר אותו כמספר שלם."""
    if isinstance(raw, bool) or raw is None or (isinstance(raw, str) and not raw.strip()):
        raise BranchError("צריך לבחור בנק מהרשימה")
    try:
        code = int(str(raw).strip())
    except (TypeError, ValueError):
        raise BranchError("צריך לבחור בנק מהרשימה") from None
    if code not in BY_CODE:
        # לא מגלים מה כן קיים — פשוט מחזירים לבחירה מהרשימה.
        raise BranchError("הבנק שנבחר אינו ברשימת הבנקים בישראל")
    return code


def normalize_branch(raw: object) -> str:
    """מספר סניף → שלוש ספרות מרופדות ("45" → "045")."""
    digits = _digits_only(raw, "מספר סניף")
    if len(digits) > BRANCH_MAX_DIGITS:
        raise BranchError(f"מספר סניף הוא עד {BRANCH_MAX_DIGITS} ספרות")
    if int(digits) == 0:
        raise BranchError("מספר סניף אינו תקין")
    return digits.zfill(BRANCH_MAX_DIGITS)


def normalize_account(raw: object) -> str:
    """מספר חשבון → ספרות בלבד, באורך סביר. אפסים מובילים נשמרים."""
    digits = _digits_only(raw, "מספר חשבון")
    if len(digits) < ACCOUNT_MIN_DIGITS:
        raise BranchError(f"מספר חשבון קצר מדי — לפחות {ACCOUNT_MIN_DIGITS} ספרות")
    if len(digits) > ACCOUNT_MAX_DIGITS:
        raise BranchError(f"מספר חשבון ארוך מדי — עד {ACCOUNT_MAX_DIGITS} ספרות")
    if int(digits) == 0:
        raise BranchError("מספר חשבון אינו תקין")
    return digits
