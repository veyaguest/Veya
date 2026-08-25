"""בדיקת פרטי קבלת מתנות בצד VEYA — נתיבי האדמין.

## למה קובץ נפרד מ-``routers/payout.py``

הקובץ ההוא הוא הצד של **בעלי האירוע**: הם ממלאים, שומרים ומגישים. הקובץ
הזה הוא הצד של **הבודק**: הוא מאשר או דוחה. ההפרדה אינה קוסמטית — היא
הביטוי בקוד לכלל שהמנגנון כולו קיים בשבילו:

    מי שמזין את פרטי החשבון אינו מי שמאשר אותם.

כל נתיב כאן תלוי ב-``get_current_admin``. אין כאן ``EventAccess``, ולכן
אין שום מסלול שבו בעלים, בן/בת זוג, מפיק או אולם מגיעים לפעולת אישור —
גם לא באירוע שלהם עצמם. חבר-אירוע יקבל 403 עוד לפני שהבקשה נוגעת בנתונים.

## שתי הבדיקות

``approve``/``reject`` הן **בדיקת VEYA בלבד**. הן אינן נוגעות ב-
``provider_status``, ולכן אישור כאן אינו הופך את החשבון לכשיר — הוא רק
מקדם אחת משתי הבדיקות. ראו ``payout_status.is_fully_verified``.

``provider`` **אינו חלק מהתהליך הרגיל.** הוא כלי בדיקה בלבד: הוא לא פונה
לאף ספק, לא מדמה אישור של ספק אמיתי, ואינו אמור לשמש בעבודה שוטפת. הוא
קיים כדי שאפשר יהיה לבדוק את המסלול מקצה לקצה עד שיחובר ספק אמיתי —
וברגע שיחובר, ה-adapter שלו יקרא לאותה פונקציית שירות והנתיב הזה ייסגר.

``reopen`` הוא הדרך היחידה לבטל נעילה של חשבון מאושר.

**מה אין כאן:** העברת כספים, KYC, Webhooks, חשבוניות והחזרים.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, undefer

from app import banks, event_terms, models, payout_service, schemas
from app.auth import get_current_admin
from app.database import get_db
from app.routers.payout import _certificate_filename, _mask, _quote

router = APIRouter(prefix="/admin/payout", tags=["admin", "payout"])


def _row(db: Session, account: models.PayoutAccount) -> schemas.PayoutReviewRow:
    """בונה שורת תור לבדיקה. **מספר החשבון המלא אינו נכתב לכאן** — גם לא
    לאדמין: מי שבודק משווה מול המסמך עצמו, לא מול JSON.

    המיפוי מפורש שדה-שדה, מאותה סיבה כמו בשאר הקובץ המקביל: עמודה חדשה
    בטבלה לא תזלוג לתשובה רק מפני שנוספה.
    """
    event = db.get(models.Event, account.event_id)
    owner = db.get(models.User, event.owner_id) if event and event.owner_id else None
    reviewer = (
        db.get(models.User, account.veya_reviewed_by_user_id)
        if account.veya_reviewed_by_user_id
        else None
    )
    bank = banks.BY_CODE.get(account.bank_code)
    cert = None
    if account.certificate_filename or account.certificate_size:
        cert = schemas.PayoutCertificateRead(
            filename=account.certificate_filename,
            content_type=account.certificate_content_type,
            size=account.certificate_size,
            uploaded_at=account.certificate_uploaded_at,
        )
    return schemas.PayoutReviewRow(
        event_id=account.event_id,
        event_title=(
            event_terms.hosts_names(event.event_type, event.groom_name, event.bride_name)
            if event
            else ""
        ),
        owner_name=(owner.display_name if owner else "") or "",
        owner_email=(owner.email if owner else "") or "",
        bank_code=account.bank_code,
        bank_name=bank.name if bank else f"קוד בנק {account.bank_code}",
        branch_number=account.branch_number,
        account_number_masked=_mask(account.account_number),
        certificate=cert,
        status=payout_service.current_status(account),
        veya_status=payout_service.veya_status(account),
        provider_status=payout_service.provider_status(account),
        fully_verified=payout_service.is_fully_verified(account),
        rejection_reason=account.rejection_reason,
        provider_rejection_reason=account.provider_rejection_reason,
        submitted_at=account.submitted_at,
        reviewed_by=(reviewer.display_name or reviewer.email) if reviewer else None,
        reviewed_at=account.veya_reviewed_at,
    )


@router.get("", response_model=list[schemas.PayoutReviewRow])
def list_accounts(
    scope: str = Query("pending", pattern="^(pending|approved)$"),
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """שתי רשימות, לפי ``scope``:

    - ``pending`` (ברירת מחדל) — תור הבדיקה. הוותיק ביותר ראשון.
    - ``approved`` — חשבונות שכבר אושרו ולכן נעולים לבעלי האירוע. קיימת
      כדי ש"פתיחה מחדש" תהיה נגישה: חשבון מאושר יוצא מתור הבדיקה, ובלי
      הרשימה הזו לא הייתה שום דרך להגיע אליו מהמסך.
    """
    rows = (
        payout_service.approved_accounts(db)
        if scope == "approved"
        else payout_service.awaiting_veya_review(db)
    )
    return [_row(db, a) for a in rows]


@router.get("/{event_id}", response_model=schemas.PayoutReviewRow)
def get_one(
    event_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """חשבון בודד — גם אחרי שהוכרע, כדי לראות מי בדק ומתי."""
    account = payout_service.get(db, event_id)
    if account is None:
        raise HTTPException(status_code=404, detail="אין פרטי חשבון לאירוע הזה")
    return _row(db, account)


@router.get("/{event_id}/certificate")
def get_certificate(
    event_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """אישור ניהול החשבון, לצורך הבדיקה עצמה.

    אותם כללי הגשה כמו בנתיב של בעלי האירוע: ללא מטמון, ובלי URL ציבורי.
    זו הדרך היחידה שבה אדמין רואה את המסמך.
    """
    account = db.scalars(
        select(models.PayoutAccount)
        .where(models.PayoutAccount.event_id == event_id)
        .options(undefer(models.PayoutAccount.certificate_data))
    ).first()
    if account is None or not account.certificate_data:
        raise HTTPException(status_code=404, detail="לא נמצא אישור ניהול חשבון")
    filename = account.certificate_filename or _certificate_filename(
        account.certificate_content_type or "application/pdf"
    )
    return Response(
        content=account.certificate_data,
        media_type=account.certificate_content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{_quote(filename)}",
            "Cache-Control": "private, no-store",
        },
    )


@router.post("/{event_id}/approve", response_model=schemas.PayoutReviewRow)
def approve(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """VEYA מאשרת את פרטי החשבון.

    **זו אחת משתי בדיקות.** ``provider_status`` נשאר ``pending``, ולכן
    החשבון עדיין אינו ``fully_verified`` ובעלי האירוע עדיין לא רואים
    סכומים. זה מכוון, ולא באג.
    """
    try:
        account = payout_service.veya_approve(
            db, event_id,
            reviewer_user_id=admin.id,
            ip=request.client.host if request.client else None,
        )
    except payout_service.PayoutError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(account)
    return _row(db, account)


@router.post("/{event_id}/reject", response_model=schemas.PayoutReviewRow)
def reject(
    event_id: int,
    payload: schemas.PayoutRejectWrite,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """VEYA דוחה את פרטי החשבון. סיבת הדחייה חובה, ומוצגת לבעלי האירוע."""
    try:
        account = payout_service.veya_reject(
            db, event_id,
            reason=payload.reason,
            reviewer_user_id=admin.id,
            ip=request.client.host if request.client else None,
        )
    except payout_service.PayoutError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(account)
    return _row(db, account)


@router.post("/{event_id}/reopen", response_model=schemas.PayoutReviewRow)
def reopen(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """פותח מחדש חשבון מאושר, כדי שבעלי האירוע יוכלו לתקן ולהגיש שוב.

    **זו הדרך היחידה לבטל את נעילת החשבון.** מרגע שאושר, אין לבעלי
    האירוע שום מסלול לשנות בנק, סניף, מספר חשבון או אישור ניהול חשבון —
    לא ב-UI ולא ב-API. אם נדרש שינוי, הוא עובר דרך כאן.

    הפרטים עצמם נשמרים; מה שמתאפס הוא האישור.
    """
    try:
        account = payout_service.veya_reopen(
            db, event_id,
            reviewer_user_id=admin.id,
            ip=request.client.host if request.client else None,
        )
    except payout_service.PayoutError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(account)
    return _row(db, account)


@router.post("/{event_id}/provider", response_model=schemas.PayoutReviewRow)
def set_provider(
    event_id: int,
    payload: schemas.PayoutProviderStatusWrite,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """רושם את תשובת ספק הסליקה — pending / approved / rejected.

    **הנתיב הזה לא מדבר עם אף ספק.** הוא רושם תשובה, לא מבקש אותה. היום
    אין ספק מחובר, ולכן זו הדרך היחידה שבה ``provider_status`` משתנה בכלל.

    אישור כאן גם הוא אינו מספיק לבדו: בלי אישור VEYA החשבון נשאר לא כשיר.
    """
    try:
        account = payout_service.set_provider_status(
            db, event_id, payload.status,
            reason=payload.reason,
            actor_user_id=admin.id,
            ip=request.client.host if request.client else None,
        )
    except payout_service.PayoutError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(account)
    return _row(db, account)
