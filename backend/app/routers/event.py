"""נקודת API לפרטי האירוע (שם החתן/כלה/אולם) — שלב 6.

בשלב הנוכחי יש אירוע יחיד. הפרטים משמשים לכותרת ההזמנה שנשלחת בוואטסאפ
ולכותרת הדשבורד.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_default_event

router = APIRouter(prefix="/event", tags=["event"])


@router.get("", response_model=schemas.EventRead)
def read_event(event: models.Event = Depends(get_default_event)):
    return event


@router.patch("", response_model=schemas.EventRead)
def update_event(
    payload: schemas.EventUpdate,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_default_event),
):
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, key, (value or "").strip())
    db.commit()
    db.refresh(event)
    return event
