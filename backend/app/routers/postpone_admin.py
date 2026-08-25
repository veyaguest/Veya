"""נוהל דחייה — נתיבי האדמין (הצד שמאשר).

## למה קובץ נפרד מ-``routers/postpone.py``

הקובץ ההוא הוא הצד של **בעלי האירוע**: הם מבקשים, מעדכנים וסוגרים. הקובץ
הזה הוא הצד של **המאשר**: הוא מאשר או דוחה. ההפרדה אינה קוסמטית — היא
הביטוי בקוד לכלל שהמנגנון כולו קיים בשבילו:

    מי שמבקש לדחות את האירוע אינו מי שמאשר את הדחייה.

כל נתיב כאן תלוי ב-``get_current_admin``. אין כאן ``EventAccess``, ולכן אין
שום מסלול שבו בעלים, בן/בת זוג, מפיק או אולם מגיעים לפעולת אישור — גם לא
באירוע שלהם עצמם.

## מה האישור עושה בפועל

הוא **לא קובע תאריך**. הוא פותח לבעלי האירוע את פרטי האירוע לעריכה מלאה,
ומקצה להם את קטגוריית ההודעות "אירוע נדחה". מכאן הם עובדים לבד: מעדכנים
תאריך, קובעים מועד סגירת רשימה חדש, ובסופו של דבר פותחים מחזור אישורי-הגעה
חדש — פעולה שנשארת שלהם ואינה של האדמין.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import event_terms, models, postponement_service, schemas
from app.auth import get_current_admin
from app.database import get_db

router = APIRouter(prefix="/admin/postpone", tags=["admin", "postpone"])


def _row(db: Session, req: models.PostponementRequest) -> schemas.PostponementReviewRow:
    """בונה שורת תור לבדיקה.

    המיפוי מפורש שדה-שדה, מאותה סיבה כמו במודול המקביל של המתנות: עמודה
    חדשה בטבלה לא תזלוג לתשובה רק מפני שנוספה.
    """
    event = db.get(models.Event, req.event_id)
    owner = db.get(models.User, event.owner_id) if event and event.owner_id else None
    requester = (
        db.get(models.User, req.requested_by_user_id)
        if req.requested_by_user_id
        else None
    )
    reviewer = (
        db.get(models.User, req.reviewed_by_user_id)
        if req.reviewed_by_user_id
        else None
    )

    total = confirmed = 0
    if event is not None:
        total = db.scalar(
            select(func.count()).select_from(models.Guest)
            .where(models.Guest.event_id == event.id)
        ) or 0
        confirmed = db.scalar(
            select(func.count()).select_from(models.Guest)
            .where(models.Guest.event_id == event.id)
            .where(models.Guest.rsvp_status == "confirmed")
        ) or 0

    return schemas.PostponementReviewRow(
        request_id=req.id,
        event_id=req.event_id,
        event_title=(
            event_terms.hosts_names(event.event_type, event.groom_name, event.bride_name)
            if event else ""
        ),
        event_type=(event.event_type if event else "wedding") or "wedding",
        cycle_number=req.cycle_number or 1,
        owner_name=(owner.display_name if owner else "") or "",
        owner_email=(owner.email if owner else "") or "",
        requested_by_name=(
            (requester.display_name or requester.email) if requester else ""
        ),
        event_date=(event.event_date if event else "") or "",
        event_time=(event.event_time if event else "") or "",
        venue_name=(event.venue_name if event else "") or "",
        guests_total=total,
        guests_confirmed=confirmed,
        status=req.status,
        requested_at=req.requested_at,
        reviewed_by=(reviewer.display_name or reviewer.email) if reviewer else None,
        reviewed_at=req.reviewed_at,
        rejection_reason=req.rejection_reason,
    )


@router.get("", response_model=list[schemas.PostponementReviewRow])
def list_requests(
    scope: str = Query("pending", pattern="^(pending|approved)$"),
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """שתי רשימות, לפי ``scope``:

    - ``pending`` (ברירת מחדל) — תור הבדיקה. הוותיקה ביותר ראשונה.
    - ``approved`` — נהלים שאושרו והזוג עדיין עובד עליהם. קיימת כדי שיהיה
      אפשר לראות מה פתוח כרגע: בקשה שאושרה יוצאת מתור הבדיקה, ובלי הרשימה
      הזו לא הייתה שום דרך לדעת עליה.
    """
    rows = (
        postponement_service.approved_requests(db)
        if scope == "approved"
        else postponement_service.pending_requests(db)
    )
    return [_row(db, r) for r in rows]


@router.get("/{event_id}", response_model=schemas.PostponementReviewRow)
def get_one(
    event_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """הבקשה האחרונה של אירוע — גם אחרי שהוכרעה, כדי לראות מי אישר ומתי."""
    req = postponement_service.latest(db, event_id)
    if req is None:
        raise HTTPException(status_code=404, detail="אין בקשת דחייה לאירוע הזה")
    return _row(db, req)


@router.post("/{event_id}/approve", response_model=schemas.PostponementReviewRow)
def approve(
    event_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """מאשר את נוהל הדחייה.

    מרגע זה פרטי האירוע פתוחים לעריכה מלאה, וקטגוריית "אירוע נדחה" נפתחת
    בניהול ההודעות. **אין כאן קביעת תאריך** — התאריך החדש הוא של הזוג.
    """
    try:
        req = postponement_service.approve(
            db, event_id,
            reviewer_user_id=admin.id,
            ip=request.client.host if request.client else None,
        )
    except postponement_service.PostponementError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(req)
    return _row(db, req)


@router.post("/{event_id}/reject", response_model=schemas.PostponementReviewRow)
def reject(
    event_id: int,
    payload: schemas.PostponementRejectWrite,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """דוחה את הבקשה. הסיבה חובה ומוצגת לבעלי האירוע.

    קיים כדי שבקשה שנפתחה בטעות לא תישאר תלויה: כל עוד היא ממתינה, בעלי
    האירוע חסומים מלפתוח בקשה חדשה.
    """
    try:
        req = postponement_service.reject(
            db, event_id,
            reason=payload.reason,
            reviewer_user_id=admin.id,
            ip=request.client.host if request.client else None,
        )
    except postponement_service.PostponementError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(req)
    return _row(db, req)
