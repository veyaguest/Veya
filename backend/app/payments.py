"""שכבת הפשטה לספק סליקה — כדי שאפשר יהיה לחבר ספק אמיתי בלי לגעת במתנות.

**מה זה פותר:** מערכת המתנות לא יודעת ולא צריכה לדעת מי מסלק. היא מדברת
עם ``PaymentProvider`` בלבד. חיבור ספק ישראלי אמיתי בעתיד הוא מימוש נוסף
של אותו ממשק ורישום ב-``_PROVIDERS`` — בלי שינוי במודל הנתונים, בסטטוסים
או בנתיבי ה-API.

**מה במפורש אין כאן:** פרטי אשראי. הממשק לא מקבל מספר כרטיס, CVV או תוקף
ולעולם לא יקבל — ספק אמיתי יעבוד ב-Hosted Fields/Tokenization, כך שהפרטים
עוברים ישירות אליו והדפדפן של המוזמן לעולם לא שולח אותם ל-VEYA.
"""
from __future__ import annotations

import os
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from app import gift_status

# סטטוסים שספק יכול לדווח עליהם. המיפוי לסטטוס העסקה שלנו נמצא למטה.
PROVIDER_PENDING = "pending"
PROVIDER_PAID = "paid"
PROVIDER_FAILED = "failed"
PROVIDER_REFUNDED = "refunded"

# מיפוי מתשובת ספק לסטטוס העסקה שלנו. מרוכז כאן כדי שספק חדש יצטרך
# להתאים את עצמו למילון אחד, ולא לפזר תרגומים בקוד.
PROVIDER_TO_GIFT_STATUS = {
    PROVIDER_PENDING: gift_status.PENDING,
    PROVIDER_PAID: gift_status.PAID,
    PROVIDER_FAILED: gift_status.FAILED,
    PROVIDER_REFUNDED: gift_status.REFUNDED,
}


@dataclass(frozen=True)
class PaymentIntent:
    """תשובת הספק על עסקה אחת — הצורה שכל ספק מחזיר, יהיה אשר יהיה."""

    provider_transaction_id: str
    status: str                       # אחד מ-PROVIDER_* למעלה
    amount_agorot: int
    currency: str = "ILS"
    # לאן ספק אמיתי היה שולח את המוזמן כדי להזין פרטי אשראי אצלו.
    redirect_url: str = ""
    # שדות גולמיים מהספק, לצורכי תמיכה ובירור. אין בהם פרטי אשראי.
    raw: dict = field(default_factory=dict)


class PaymentProvider(ABC):
    """הממשק שכל ספק סליקה חייב לממש."""

    name: str = "abstract"

    @abstractmethod
    def create_payment(
        self,
        *,
        amount_agorot: int,
        currency: str,
        reference: str,
        description: str = "",
        metadata: Optional[dict] = None,
    ) -> PaymentIntent:
        """פותח עסקה אצל הספק ומחזיר את מזהה העסקה שלו.

        ``reference`` הוא המפתח שלנו (idempotency_key), כדי שגם אצל הספק
        אפשר יהיה למצוא את העסקה ולמנוע כפילות בצד שלו.
        """

    @abstractmethod
    def get_payment_status(self, provider_transaction_id: str) -> PaymentIntent:
        """שואל את הספק מה קרה בפועל.

        **זו הפונקציה שקובעת אם עסקה שולמה** — לא בקשת ה-Frontend. כשיהיה
        ספק אמיתי, ה-webhook שלו יזרים לכאן את אותו מידע.
        """

    @abstractmethod
    def refund_payment(
        self, provider_transaction_id: str, *, amount_agorot: Optional[int] = None
    ) -> PaymentIntent:
        """מבקש החזר. ``amount_agorot=None`` = החזר מלא."""


class MockProvider(PaymentProvider):
    """ספק מדומה לבדיקות — **אין כאן כסף אמיתי ואין קריאת רשת**.

    שומר את העסקאות בזיכרון התהליך. התוצאה (הצלחה/כישלון) נקבעת מראש דרך
    ``metadata["simulate"]`` — כלומר הלקוח מגדיר איך ה*עולם* יתנהג בהדמיה,
    ולא קובע ישירות את סטטוס העסקה. ההבחנה הזו היא בדיוק מה ששומר על
    הארכיטקטורה נכונה: גם בהדמיה, הסטטוס מגיע מ"הספק".
    """

    name = "mock"

    def __init__(self) -> None:
        self._intents: dict[str, PaymentIntent] = {}

    def create_payment(
        self,
        *,
        amount_agorot: int,
        currency: str,
        reference: str,
        description: str = "",
        metadata: Optional[dict] = None,
    ) -> PaymentIntent:
        meta = metadata or {}
        outcome = meta.get("simulate", "success")
        txn_id = f"MOCK-{secrets.token_hex(6).upper()}"
        intent = PaymentIntent(
            provider_transaction_id=txn_id,
            # הספק המדומה "מעבד" מיד; ספק אמיתי היה מחזיר pending ואז שולח webhook.
            status=PROVIDER_PAID if outcome == "success" else PROVIDER_FAILED,
            amount_agorot=amount_agorot,
            currency=currency,
            redirect_url="",
            raw={"mock": True, "reference": reference, "description": description},
        )
        self._intents[txn_id] = intent
        return intent

    def get_payment_status(self, provider_transaction_id: str) -> PaymentIntent:
        intent = self._intents.get(provider_transaction_id)
        if intent is None:
            raise KeyError(f"עסקה לא נמצאה אצל הספק: {provider_transaction_id}")
        return intent

    def refund_payment(
        self, provider_transaction_id: str, *, amount_agorot: Optional[int] = None
    ) -> PaymentIntent:
        intent = self.get_payment_status(provider_transaction_id)
        refunded = PaymentIntent(
            provider_transaction_id=intent.provider_transaction_id,
            status=PROVIDER_REFUNDED,
            amount_agorot=amount_agorot or intent.amount_agorot,
            currency=intent.currency,
            raw={**intent.raw, "refunded": True},
        )
        self._intents[intent.provider_transaction_id] = refunded
        return refunded


# ── רישום הספקים ────────────────────────────────────────────────────────
# נקודת החיבור היחידה. ספק ישראלי אמיתי ייכנס כאן, וייבחר דרך
# ``VEYA_PAYMENT_PROVIDER``. שום קוד אחר לא צריך להשתנות.
_PROVIDERS: dict[str, PaymentProvider] = {"mock": MockProvider()}


def get_provider(name: Optional[str] = None) -> PaymentProvider:
    """הספק הפעיל. ברירת מחדל ``mock`` — אין עדיין ספק אמיתי."""
    key = (name or os.getenv("VEYA_PAYMENT_PROVIDER", "mock")).strip().lower()
    provider = _PROVIDERS.get(key)
    if provider is None:
        raise ValueError(f"ספק סליקה לא מוכר: {key}")
    return provider
