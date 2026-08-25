"""שירות פרטי קבלת המתנות — שמירה, הגשה ושינוי סטטוס.

**זו נקודת הכתיבה היחידה** לטבלת ``payout_accounts``. הנתיבים
(``routers/payout.py``) לא נוגעים בשדות ישירות, כדי ששלושת הכללים
שלמטה ייאכפו בכל מסלול ולא ייתלו בזכירה של מי שיוסיף נתיב חדש:

1. **כל מעבר סטטוס עובר ``payout_status.assert_transition``** — אין השמה
   חופשית ל-``row.status``.
2. **עריכת פרטי בנק מבטלת אימות** — חשבון שאומת והוחלף אינו מאומת.
3. **כל שינוי נרשם ליומן, בלי הנתונים עצמם** — מספר חשבון לא נכתב ליומן.

**מה שאין כאן:** העברת כספים, פנייה לספק סליקה, KYC ואימות בנק אמיתי.
``submit`` רק מסמן שהפרטים מוכנים לבדיקה. הבדיקה עצמה היא היום אדם
ב-VEYA; בעתיד תגיע דרך ``payout_provider`` בלי לשנות את הקובץ הזה.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, banks, models, payout_status

#: השדות שהם "זהות החשבון". שינוי באחד מהם מבטל אימות קיים.
IDENTITY_FIELDS = ("bank_code", "branch_number", "account_number")


class PayoutError(ValueError):
    """שגיאת שימוש עם נוסח עברי מוכן להצגה."""


def get(db: Session, event_id: int) -> Optional[models.PayoutAccount]:
    return db.scalars(
        select(models.PayoutAccount).where(models.PayoutAccount.event_id == event_id)
    ).first()


def current_status(row: Optional[models.PayoutAccount]) -> str:
    """הסטטוס של האירוע. אין שורה = ``missing`` (וכך גם שורה ישנה עם NULL)."""
    if row is None:
        return payout_status.MISSING
    return row.status or payout_status.MISSING


def _set_status(
    db: Session,
    row: models.PayoutAccount,
    target: str,
    *,
    event_id: int,
    user_id: Optional[int],
    reason: str = "",
    detail: str = "",
    ip: Optional[str] = None,
) -> None:
    """מעבר סטטוס יחיד — מאומת, מתוארך ומתועד. הפונקציה הפנימית היחידה
    שמותר לה לגעת ב-``row.status``."""
    before = current_status(row)
    payout_status.assert_transition(before, target)
    if before == target:
        return
    row.status = target
    row.status_changed_at = datetime.utcnow()
    row.rejection_reason = reason or None
    audit.record(
        db,
        "payout_status_changed",
        event_id=event_id,
        user_id=user_id,
        detail=detail or f"סטטוס פרטי קבלת המתנות: {before} → {target}",
        ip=ip,
    )


def save_details(
    db: Session,
    event_id: int,
    *,
    bank_code,
    branch_number,
    account_number,
    user_id: Optional[int] = None,
    ip: Optional[str] = None,
) -> tuple[models.PayoutAccount, bool]:
    """שומר או מעדכן את פרטי הבנק. מחזיר ``(שורה, נוצרה_עכשיו)``.

    הנרמול והוולידציה עוברים דרך ``app/banks.py`` — מקור אמת אחד לכללים
    ולנוסח השגיאות, כך שאותה בדיקה חלה על כל נתיב שכותב פרטי חשבון.
    """
    try:
        code = banks.normalize_bank_code(bank_code)
        branch = banks.normalize_branch(branch_number)
        account = banks.normalize_account(account_number)
    except banks.BranchError as exc:
        raise PayoutError(str(exc)) from exc

    row = get(db, event_id)
    creating = row is None
    if row is None:
        row = models.PayoutAccount(event_id=event_id, status=payout_status.MISSING)
        db.add(row)

    changed = creating or any(
        getattr(row, f) != v
        for f, v in zip(IDENTITY_FIELDS, (code, branch, account))
    )
    row.bank_code, row.branch_number, row.account_number = code, branch, account

    # כלל 2: זהות החשבון השתנתה → כל אימות או בדיקה שבתהליך בטלים.
    if changed and current_status(row) != payout_status.MISSING:
        _set_status(
            db, row, payout_status.MISSING,
            event_id=event_id, user_id=user_id, ip=ip,
            detail="פרטי החשבון שונו — האימות בוטל ונדרשת הגשה מחדש",
        )

    audit.record(
        db,
        "payout_details_saved" if creating else "payout_details_updated",
        event_id=event_id,
        user_id=user_id,
        # בלי קוד בנק, סניף או מספר חשבון — היומן מתעד שינוי, לא נתונים.
        detail="נשמרו פרטי קבלת המתנות" if creating else "עודכנו פרטי קבלת המתנות",
        ip=ip,
    )
    return row, creating


def attach_certificate(
    db: Session,
    row: models.PayoutAccount,
    *,
    data: bytes,
    content_type: str,
    filename: str,
    user_id: Optional[int] = None,
    ip: Optional[str] = None,
) -> None:
    """מצרף אישור ניהול חשבון חדש (דורס קודם).

    החלפת האישור **אינה** מבטלת אימות: זהות החשבון לא השתנתה, ורק המסמך
    שמוכיח אותה הוחלף (למשל סריקה קריאה יותר אחרי דחייה).
    """
    row.certificate_data = data
    row.certificate_content_type = content_type
    row.certificate_filename = filename
    row.certificate_size = len(data)
    row.certificate_uploaded_at = datetime.utcnow()
    audit.record(
        db, "payout_certificate_uploaded",
        event_id=row.event_id, user_id=user_id,
        detail="הועלה אישור ניהול חשבון", ip=ip,
    )


def submit(
    db: Session,
    event_id: int,
    *,
    user_id: Optional[int] = None,
    ip: Optional[str] = None,
) -> models.PayoutAccount:
    """מגיש את הפרטים לבדיקה: ``missing``/``rejected`` → ``submitted``.

    **לא נשלח כאן מידע לאף גורם חיצוני.** ההגשה מסמנת שהפרטים מוכנים;
    הבדיקה עצמה ידנית היום (ראו ``payout_provider.ManualProvider``).
    """
    row = get(db, event_id)
    if row is None:
        raise PayoutError("אין פרטי חשבון להגשה")
    if not row.certificate_data and not row.certificate_size:
        raise PayoutError("צריך לצרף אישור ניהול חשבון לפני ההגשה")

    status = current_status(row)
    if status in payout_status.PENDING_REVIEW:
        raise PayoutError("הפרטים כבר הוגשו וממתינים לבדיקה")
    if status == payout_status.VERIFIED:
        raise PayoutError("הפרטים כבר אומתו")

    try:
        _set_status(
            db, row, payout_status.SUBMITTED,
            event_id=event_id, user_id=user_id, ip=ip,
            detail="פרטי קבלת המתנות הוגשו לבדיקה",
        )
    except payout_status.InvalidStatusTransition as exc:
        raise PayoutError(str(exc)) from exc
    row.submitted_at = datetime.utcnow()
    return row


def set_status(
    db: Session,
    event_id: int,
    target: str,
    *,
    reason: str = "",
    reviewer_user_id: Optional[int] = None,
) -> models.PayoutAccount:
    """מעבר סטטוס מצד הבודק — ``under_review`` / ``verified`` / ``rejected``.

    **בכוונה אין לזה נתיב API של בעלי האירוע.** מי שמזין את פרטי החשבון
    אינו מי שמאשר אותם; הפונקציה הזו מיועדת לצד הבודק — אדם ב-VEYA היום,
    adapter של ספק מחר (``payout_provider.PROVIDER_TO_PAYOUT_STATUS``
    ממפה תשובת ספק אל אותם סטטוסים בדיוק).
    """
    row = get(db, event_id)
    if row is None:
        raise PayoutError("אין פרטי חשבון לאירוע הזה")
    try:
        _set_status(
            db, row, target,
            event_id=event_id, user_id=reviewer_user_id, reason=reason,
        )
    except payout_status.InvalidStatusTransition as exc:
        raise PayoutError(str(exc)) from exc
    return row
