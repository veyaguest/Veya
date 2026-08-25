"""נוהל דחייה — הצד של בעלי האירוע.

**גישה: בעלים / בן-זוג / אדמין בלבד** (``EventAccess(owner_only=True)``), בדיוק
כמו עריכת פרטי האירוע עצמה — הרי זה מה שהנוהל פותח. מפיק או אולם שמנהלים
אירוע אינם פותחים נוהל דחייה ואינם סוגרים אותו.

## שלוש פעולות בלבד

    GET  /postpone           מה מצב הנוהל אצלי
    POST /postpone           בקשה לפתוח נוהל דחייה
    POST /postpone/complete  סיימנו לעדכן — פתחו לנו מחזור אישורי-הגעה חדש

**ואין כאן נתיב שמאשר.** בעלי האירוע יכולים לבקש, ותו לא. האישור נעשה
בנתיבי האדמין (``routers/postpone_admin.py``) — מי שמבקש לדחות אינו מי
שמאשר את הדחייה.

## מה הבקשה לא מכילה

תאריך חדש, ומועד סגירת רשימה חדש. בשלב שבו זוג מבקש לדחות אירוע הוא לרוב
עדיין לא יודע מתי הוא יתקיים — ובקשה שדורשת תאריך הייתה מכריחה אותו להמציא
אחד. שני הפרטים האלה נכנסים אחר כך, דרך ``PATCH /event`` הרגיל, שנפתח
מרגע האישור.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import models, postponement_service, postponement_status, schemas
from app.auth import get_current_owner
from app.database import get_db
from app.deps import EventAccess

_owner_only = EventAccess(owner_only=True)

router = APIRouter(prefix="/postpone", tags=["postpone"])


def _read(db: Session, event: models.Event) -> schemas.PostponementRead:
    """מצב הנוהל + מה מותר לעשות עכשיו.

    ``can_request``/``can_complete`` נגזרים כאן ולא במסך, כדי שהכפתור שמוצג
    למשתמש והכלל שנאכף בשרת יהיו אותו דבר בדיוק.
    """
    row = postponement_service.latest(db, event.id)
    if row is None:
        return schemas.PostponementRead(
            cycle_number=event.cycle_number or 1,
            can_request=True,
        )

    is_open = postponement_status.is_open(row.status)
    unlocked = postponement_status.unlocks_editing(row.status)
    # אפשר לסיים רק כשהתאריך באמת עודכן — אחרת "מחזור חדש" היה מאפס את
    # אישורי ההגעה בלי שום סיבה. אותו תנאי נאכף שוב ב-``service.complete``.
    current_date = (event.event_date or "").strip()
    can_complete = bool(
        unlocked
        and current_date
        and current_date != (row.previous_event_date or "").strip()
    )
    return schemas.PostponementRead(
        status=row.status,
        cycle_number=event.cycle_number or 1,
        requested_at=row.requested_at,
        reviewed_at=row.reviewed_at,
        completed_at=row.completed_at,
        rejection_reason=row.rejection_reason,
        previous_event_date=row.previous_event_date or "",
        previous_event_time=row.previous_event_time or "",
        can_request=not is_open,
        can_complete=can_complete,
    )


@router.get("", response_model=schemas.PostponementRead)
def get_status(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_owner_only),
):
    """מצב נוהל הדחייה של האירוע — כולל בקשה שהוכרעה, כדי שאפשר יהיה להציג
    סיבת דחייה."""
    return _read(db, event)


@router.post("", response_model=schemas.PostponementRead, status_code=201)
def open_request(
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_owner_only),
    user: models.User = Depends(get_current_owner),
):
    """פותח בקשה לנוהל דחייה. **אין גוף בקשה** — אין מה למלא.

    בקשה נוספת בזמן שקיימת בקשה חיה נדחית עם 409 והסבר בעברית.
    """
    try:
        postponement_service.open_request(
            db, event,
            user_id=user.id,
            ip=request.client.host if request.client else None,
        )
    except postponement_service.PostponementError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(event)
    return _read(db, event)


@router.post("/complete", response_model=schemas.PostponementRead)
def complete(
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_owner_only),
    user: models.User = Depends(get_current_owner),
):
    """סוגר את הנוהל ופותח מחזור אישורי-הגעה חדש.

    זו הפעולה שמאפסת את התשובות — ולכן היא **מפורשת ויזומה על ידי הזוג**,
    ולא קורית מאליה כתופעת לוואי של שליחת הזמנה. התשובות הקודמות מועברות
    לארכיון לפני האיפוס (``postponement_service.complete``); שום נתון לא
    נמחק.
    """
    try:
        postponement_service.complete(
            db, event,
            user_id=user.id,
            ip=request.client.host if request.client else None,
        )
    except postponement_service.PostponementError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(event)
    return _read(db, event)
