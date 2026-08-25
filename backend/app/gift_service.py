"""שכבת העסקאות של המתנות — יצירה, מניעת כפילות, ועדכון סטטוס מהספק.

שלושה כללים שהמודול הזה אוכף, וששום נתיב API לא אמור לעקוף:

1. **השרת מחשב את הכסף.** ``gift_amount`` מגיע מהמוזמן; ``fee`` ו-``total``
   מחושבים כאן מחדש (``gift.quote``) ולעולם לא מתקבלים מהלקוח.
2. **הזהות מגיעה מהטוקן.** ``event_id`` ו-``guest_id`` נגזרים משורת המוזמן
   שהטוקן פתח — הם אינם פרמטרים שהלקוח יכול לשלוח.
3. **``paid`` מגיע רק מהספק.** בקשת הלקוח לא קובעת סטטוס. גם בהדמיה,
   הסטטוס נקרא מ-``provider.get_payment_status``.
"""
from __future__ import annotations

import hashlib
import secrets
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import gift as gift_money
from app import gift_status, models, payments
from app.database import IS_POSTGRES


class GiftConflict(ValueError):
    """אותו ``idempotency_key`` הגיע עם פרטים אחרים — לא ניסיון חוזר אמיתי."""


def build_idempotency_key(guest_id: int, client_key: Optional[str]) -> str:
    """ממרחב-שם את מפתח הלקוח לפי המוזמן.

    **למה זה קריטי:** המפתח מגיע מדפדפן של מוזמן אנונימי. בלי מרחב-שם,
    מוזמן אחד שישלח ``"1"`` היה מתנגש במוזמן אחר ששלח ``"1"`` — והשני היה
    מקבל בתשובה את העסקה של הראשון. ה-hash מבטיח אורך קבוע ומונע הזרקה
    של תווים לא צפויים למפתח ייחודי ב-DB.

    בלי מפתח מהלקוח נוצר מפתח אקראי — כלומר בקשה בלי מפתח אף פעם לא
    "מתאחדת" עם קודמת, וזו התנהגות נכונה: אין דרך לדעת שזו אותה כוונה.
    """
    raw = (client_key or "").strip()
    if not raw:
        return f"g{guest_id}:auto:{secrets.token_urlsafe(16)}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return f"g{guest_id}:{digest}"


def _insert_gift(db: Session, gift_row: models.Gift) -> models.Gift:
    """הוספה שעובדת גם למוזמן אנונימי תחת RLS.

    אותה בעיה בדיוק כמו ב-``app_record_confirm_message``: למוזמן יש רק
    ``guest_token`` ולא זהות משתמש, ולכן INSERT רגיל (עם RETURNING
    שברירת המחדל של SQLAlchemy) נדחה ע"י מדיניות ה-SELECT. ב-Postgres
    עוברים דרך ``app_record_gift`` (SECURITY DEFINER), ראו rls/13_gifts_rls.sql.
    """
    if IS_POSTGRES:
        from sqlalchemy import text

        row_id = db.execute(
            text(
                "SELECT app_record_gift(:event_id, :guest_id, :gift, :fee, :total, "
                ":currency, :status, :provider, :idem, :sender, :message)"
            ),
            {
                "event_id": gift_row.event_id,
                "guest_id": gift_row.guest_id,
                "gift": gift_row.gift_amount_agorot,
                "fee": gift_row.fee_agorot,
                "total": gift_row.total_agorot,
                "currency": gift_row.currency,
                "status": gift_row.status,
                "provider": gift_row.provider,
                "idem": gift_row.idempotency_key,
                "sender": gift_row.sender_name,
                "message": gift_row.message,
            },
        ).scalar_one()
        db.flush()
        return db.get(models.Gift, row_id)

    db.add(gift_row)
    db.flush()
    return gift_row


def find_by_key(db: Session, idempotency_key: str) -> Optional[models.Gift]:
    return db.scalar(
        select(models.Gift).where(models.Gift.idempotency_key == idempotency_key)
    )


def create_gift(
    db: Session,
    guest: models.Guest,
    *,
    gift_amount_agorot: object,
    sender_name: str = "",
    message: Optional[str] = None,
    client_idempotency_key: Optional[str] = None,
    currency: str = "ILS",
) -> tuple[models.Gift, bool]:
    """יוצר עסקת מתנה במצב ``pending``. מחזיר ``(עסקה, נוצרה_עכשיו)``.

    בקשה חוזרת עם אותו מפתח מחזירה את **אותה** עסקה עם ``False`` — לא
    יוצרת שנייה ולא זורקת שגיאה. זו התנהגות ה-idempotency הנכונה: לחיצה
    כפולה או ניסיון חוזר של הרשת לא יוצרים שני חיובים.
    """
    quote = gift_money.quote_from_input(gift_amount_agorot)   # ולידציה + חישוב בשרת
    key = build_idempotency_key(guest.id, client_idempotency_key)

    existing = find_by_key(db, key)
    if existing is not None:
        # אותו מפתח עם סכום אחר = לא ניסיון חוזר, אלא בקשה אחרת שמתחזה.
        if existing.gift_amount_agorot != quote.gift_amount_agorot:
            raise GiftConflict("אותו מפתח כבר שימש לסכום אחר.")
        return existing, False

    row = models.Gift(
        # הזהות מגיעה מהטוקן בלבד — לא מגוף הבקשה.
        event_id=guest.event_id,
        guest_id=guest.id,
        gift_amount_agorot=quote.gift_amount_agorot,
        fee_agorot=quote.fee_agorot,
        total_agorot=quote.total_agorot,
        currency=currency,
        status=gift_status.PENDING,
        provider=payments.get_provider().name,
        idempotency_key=key,
        sender_name=(sender_name or guest.full_name or "").strip(),
        message=(message or None),
    )

    try:
        gift_row = _insert_gift(db, row)
    except IntegrityError:
        # מרוץ בין שתי בקשות במקביל עם אותו מפתח: האינדקס הייחודי ב-DB
        # תפס את השנייה. זו ההגנה האמיתית — לא הבדיקה שלמעלה, שהיא רק
        # קיצור דרך לרוב המקרים.
        db.rollback()
        raced = find_by_key(db, key)
        if raced is None:
            raise
        return raced, False

    return gift_row, True


def set_status(db: Session, gift_row: models.Gift, target: str) -> models.Gift:
    """מעדכן סטטוס אחרי אימות שהמעבר מותר. זורק ``InvalidStatusTransition``."""
    gift_status.assert_transition(gift_row.status, target)
    if gift_row.status != target:
        if IS_POSTGRES:
            from sqlalchemy import text

            db.execute(
                text("SELECT app_update_gift_status(:gid, :status, :txn)"),
                {"gid": gift_row.id, "status": target, "txn": gift_row.provider_transaction_id},
            )
            db.expire(gift_row)
        else:
            gift_row.status = target
        db.flush()
    return gift_row


def start_payment(
    db: Session, gift_row: models.Gift, *, simulate: str = "success"
) -> models.Gift:
    """פותח עסקה אצל הספק ומסנכרן את הסטטוס **מתשובתו**.

    ``simulate`` מוזרם לספק המדומה כדי לקבוע איך "העולם" יתנהג — הוא לא
    קובע את הסטטוס ישירות. זה ההבדל שמאפשר להחליף כאן ספק אמיתי בלי
    לשנות שורה: הסטטוס תמיד נקרא מ-``get_payment_status``.
    """
    provider = payments.get_provider()

    if gift_row.provider_transaction_id is None:
        intent = provider.create_payment(
            amount_agorot=gift_row.total_agorot,     # האורח משלם את הסה"כ
            currency=gift_row.currency,
            reference=gift_row.idempotency_key,
            description=f"מתנה לאירוע {gift_row.event_id}",
            metadata={"simulate": simulate},
        )
        gift_row.provider_transaction_id = intent.provider_transaction_id
        if not IS_POSTGRES:
            db.flush()

    return sync_status_from_provider(db, gift_row)


def sync_status_from_provider(db: Session, gift_row: models.Gift) -> models.Gift:
    """קורא את הסטטוס מהספק ומחיל אותו על העסקה.

    **זו הנקודה שבה עסקה הופכת ל-``paid``** — ורק כאן. כשיחובר ספק אמיתי,
    ה-webhook שלו יקרא לפונקציה הזו (או לתאומה שלה) עם אותה סמנטיקה, ושום
    דבר אחר במערכת לא יצטרך להשתנות.
    """
    if not gift_row.provider_transaction_id:
        return gift_row
    provider = payments.get_provider()
    try:
        intent = provider.get_payment_status(gift_row.provider_transaction_id)
    except KeyError:
        return gift_row      # הספק לא מכיר — משאירים pending, לא ממציאים סטטוס
    target = payments.PROVIDER_TO_GIFT_STATUS.get(intent.status)
    if target is None or not gift_status.can_transition(gift_row.status, target):
        return gift_row
    return set_status(db, gift_row, target)
