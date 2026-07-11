"""Router לניהול אירועים של המשתמש (שלב 8): רשימה, יצירה, מחיקה.

כל משתמש רואה ומנהל רק את האירועים שבבעלותו.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[schemas.EventSummary])
def list_events(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """כל האירועים של המשתמש המחובר, מהחדש לישן."""
    return db.scalars(
        select(models.Event)
        .where(models.Event.owner_id == user.id)
        .order_by(models.Event.id.desc())
    ).all()


@router.post("", response_model=schemas.EventSummary, status_code=201)
def create_event(
    payload: schemas.EventCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """יוצר אירוע חדש בבעלות המשתמש."""
    event = models.Event(
        owner_id=user.id,
        groom_name=payload.groom_name.strip(),
        bride_name=payload.bride_name.strip(),
        venue_name=payload.venue_name.strip(),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=204)
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """מוחק אירוע (רק אם הוא בבעלות המשתמש) — כולל כל המוזמנים שלו."""
    event = db.get(models.Event, event_id)
    if event is None or event.owner_id != user.id:
        raise HTTPException(status_code=404, detail="האירוע לא נמצא")
    # ניקוי רשומות תלויות שאין להן cascade אוטומטי (הודעות, הבהרות, יומן אבטחה).
    for msg in db.scalars(
        select(models.Message).where(models.Message.event_id == event_id)
    ).all():
        db.delete(msg)
    for clar in db.scalars(
        select(models.Clarification).where(models.Clarification.event_id == event_id)
    ).all():
        db.delete(clar)
    for log in db.scalars(
        select(models.AuditLog).where(models.AuditLog.event_id == event_id)
    ).all():
        db.delete(log)
    db.delete(event)  # guests נמחקים ב-cascade
    db.commit()
