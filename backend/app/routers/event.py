"""נקודת API לפרטי האירוע (שם החתן/כלה/אולם) — שלב 6.

בשלב הנוכחי יש אירוע יחיד. הפרטים משמשים לכותרת ההזמנה שנשלחת בוואטסאפ
ולכותרת הדשבורד.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, models, schemas
from app.auth import get_current_user
from app.database import get_db
from app.deps import get_current_event

router = APIRouter(prefix="/event", tags=["event"])


@router.get("", response_model=schemas.EventRead)
def read_event(event: models.Event = Depends(get_current_event)):
    return event


@router.patch("", response_model=schemas.EventRead)
def update_event(
    payload: schemas.EventUpdate,
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
    user: models.User = Depends(get_current_user),
):
    changed = payload.model_dump(exclude_unset=True)
    for key, value in changed.items():
        setattr(event, key, (value or "").strip())
    audit.record(
        db, "update_event",
        event_id=event.id, user_id=user.id,
        detail="עודכנו שדות: " + ", ".join(changed.keys()),
        ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(event)
    return event


@router.get("/audit", response_model=list[schemas.AuditLogRow])
def read_audit(
    limit: int = 30,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """יומן האבטחה של האירוע — הפעולות הרגישות האחרונות (למנהל האירוע בלבד)."""
    stmt = (
        select(models.AuditLog)
        .where(models.AuditLog.event_id == event.id)
        .order_by(models.AuditLog.created_at.desc())
        .limit(max(1, min(limit, 100)))
    )
    return db.scalars(stmt).all()
