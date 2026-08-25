"""שכבת הפשטה לספק Payout — כדי שאפשר יהיה לחבר ספק אמיתי בעתיד בלי לגעת
במודל הנתונים, בסטטוסים או בנתיבי ה-API.

**מקבילה מכוונת ל-``app/payments.py``.** שם זה הצד שגובה כסף מהמוזמן; כאן
זה הצד שמעביר כסף לבעלי האירוע. אותו דפוס בדיוק: ממשק מופשט, רישום
ב-``_PROVIDERS``, בחירה לפי משתנה סביבה.

## מה הקובץ הזה **לא** עושה

**הוא לא שולח שום דבר לשום מקום.** ברירת המחדל היא ``ManualProvider``,
שאינו עושה קריאת רשת כלשהי — הוא מייצג את מה שקורה היום בפועל: אדם
ב-VEYA בודק את אישור ניהול החשבון בעיניים. אין כאן אינטגרציה עם ספק,
אין KYC, אין אימות בנק אמיתי, ואין העברת כספים.

השדות ``provider`` ו-``provider_account_id`` בטבלה קיימים ונשמרים, אבל
**אף אחד לא כותב אליהם היום** — הם ממתינים לספק הראשון.

## איך מחברים ספק אמיתי בעתיד

1. לממש את ``PayoutProvider`` (שתי מתודות).
2. לרשום ב-``_PROVIDERS``.
3. להגדיר ``VEYA_PAYOUT_PROVIDER=<name>``.

ואז ``payout_service`` יקרא ל-``register_recipient`` בעת ההגשה, ישמור את
``provider_account_id`` שחזר, וימפה את תשובת הספק לסטטוס שלנו דרך
``PROVIDER_TO_PAYOUT_STATUS``. שום דבר אחר במערכת לא משתנה.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from app import payout_status

# סטטוסים שספק Payout יכול לדווח עליהם.
PROVIDER_PENDING = "pending"
PROVIDER_APPROVED = "approved"
PROVIDER_REJECTED = "rejected"

# מיפוי מתשובת ספק לסטטוס שלנו. מרוכז כאן כדי שספק חדש יתאים את עצמו
# למילון אחד, ולא יפזר תרגומים בקוד.
PROVIDER_TO_PAYOUT_STATUS = {
    PROVIDER_PENDING: payout_status.UNDER_REVIEW,
    PROVIDER_APPROVED: payout_status.VERIFIED,
    PROVIDER_REJECTED: payout_status.REJECTED,
}


@dataclass(frozen=True)
class RecipientRegistration:
    """תשובת הספק על רישום מוטב אחד — הצורה שכל ספק יחזיר."""

    provider_account_id: str
    status: str                        # אחד מ-PROVIDER_* למעלה
    #: הסבר לדחייה, אם הייתה. מוצג לבעלי האירוע.
    reason: str = ""
    #: שדות גולמיים מהספק, לתמיכה ובירור.
    raw: dict = field(default_factory=dict)


class PayoutProvider(ABC):
    """הממשק שכל ספק Payout יצטרך לממש.

    הממשק מקבל את פרטי הבנק **כפרמטרים מפורשים** ולא את שורת ה-ORM, כדי
    שמימוש של ספק לא יקבל גישה לשאר הטבלה (כולל הבייטים של אישור ניהול
    החשבון) רק מפני שהוא צריך מספר חשבון.
    """

    name: str = "abstract"

    @abstractmethod
    def register_recipient(
        self,
        *,
        event_id: int,
        bank_code: int,
        branch_number: str,
        account_number: str,
        holder_name: str,
    ) -> RecipientRegistration:
        """רושם את בעלי האירוע כמוטב אצל הספק."""

    @abstractmethod
    def get_recipient_status(self, provider_account_id: str) -> str:
        """מחזיר את הסטטוס הנוכחי אצל הספק (אחד מ-PROVIDER_*)."""


class ManualProvider(PayoutProvider):
    """ברירת המחדל: אין ספק — הבדיקה ידנית, בתוך VEYA.

    **אינו מבצע שום קריאת רשת ואינו שולח מידע לאף גורם חיצוני.** הוא קיים
    כדי שהקוד שסביבו (שירות, סטטוסים, נתיבים) ייכתב וייבדק מול ממשק אמיתי
    ולא מול ``None`` — וכדי שהחלפתו בספק אמיתי לא תדרוש שינוי מבני.
    """

    name = "manual"

    def register_recipient(self, **kwargs) -> RecipientRegistration:
        # אין מזהה חיצוני, כי אין גורם חיצוני. הסטטוס נשאר "ממתין" —
        # כלומר: מחכה שאדם יסתכל.
        return RecipientRegistration(provider_account_id="", status=PROVIDER_PENDING)

    def get_recipient_status(self, provider_account_id: str) -> str:
        return PROVIDER_PENDING


#: ספקים רשומים. ספק אמיתי בעתיד נרשם כאן ותו לא.
_PROVIDERS: dict[str, PayoutProvider] = {ManualProvider.name: ManualProvider()}

DEFAULT_PROVIDER = ManualProvider.name


def register_provider(provider: PayoutProvider) -> None:
    """מוסיף ספק לרישום. נועד לשימוש עתידי (ולבדיקות)."""
    _PROVIDERS[provider.name] = provider


def available_providers() -> tuple[str, ...]:
    return tuple(sorted(_PROVIDERS))


def get_provider(name: Optional[str] = None) -> PayoutProvider:
    """הספק הפעיל. ברירת המחדל — ``manual``, כלומר אף ספק חיצוני.

    בחירה דרך ``VEYA_PAYOUT_PROVIDER``. שם לא מוכר **נופל בקול** ולא חוזר
    בשקט לברירת המחדל: הגדרה שגויה בייצור שמתגלגלת ל"ידני" בלי שאיש ישים
    לב היא בדיוק הסוג של תקלה שמתגלה מאוחר מדי.
    """
    key = (name or os.getenv("VEYA_PAYOUT_PROVIDER", DEFAULT_PROVIDER)).strip().lower()
    if key not in _PROVIDERS:
        raise ValueError(f"ספק Payout לא מוכר: {key!r}. רשומים: {available_providers()}")
    return _PROVIDERS[key]
