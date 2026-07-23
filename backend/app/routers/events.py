"""Router לניהול אירועים של המשתמש (שלב 8): רשימה, יצירה, מחיקה.

כל משתמש רואה את האירועים שבבעלותו, ובנוסף (שלב multi-tenant) אירועים
שבהם הוא חבר-אירוע פעיל (מפיק/אולם שהוזמנו). ניהול (יצירה/מחיקה) עדיין
מוגבל לבעלים בלבד.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import models, schemas
from app.account import delete_event_cascade
from app.auth import get_current_user
from app.database import IS_POSTGRES, get_db

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[schemas.EventSummary])
def list_events(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """אירועים בבעלות המשתמש + אירועים ששותפו איתו כחבר-אירוע פעיל, מהחדש לישן."""
    owned = set(
        db.scalars(
            select(models.Event.id).where(models.Event.owner_id == user.id)
        ).all()
    )
    shared = set(
        db.scalars(
            select(models.EventMember.event_id).where(
                models.EventMember.user_id == user.id,
                models.EventMember.status == "active",
            )
        ).all()
    )
    event_ids = owned | shared
    if not event_ids:
        return []
    return db.scalars(
        select(models.Event)
        .where(models.Event.id.in_(event_ids))
        .order_by(models.Event.id.desc())
    ).all()


@router.post("", response_model=schemas.EventSummary, status_code=201)
def create_event(
    payload: schemas.EventCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """יוצר אירוע חדש בבעלות המשתמש.

    ב-Postgres דרך app_create_event (SECURITY DEFINER): INSERT ...RETURNING
    (ברירת המחדל של SQLAlchemy) דורש שהשורה תעבור גם את events_select, לא
    רק את ה-WITH CHECK של events_insert — עוקפים זאת כמו בשאר מקומות ה-
    INSERT הרגישים (ראו app/auth.py::register_user_row להסבר המלא).
    """
    if IS_POSTGRES:
        row = db.execute(
            text("SELECT * FROM app_create_event(:owner_id, :event_type, :groom_name, :bride_name, :venue_name)"),
            {
                "owner_id": user.id, "event_type": payload.event_type,
                "groom_name": payload.groom_name.strip(),
                "bride_name": payload.bride_name.strip(),
                "venue_name": payload.venue_name.strip(),
            },
        ).mappings().first()
        db.commit()
        return models.Event(**dict(row))

    event = models.Event(
        owner_id=user.id,
        event_type=payload.event_type,
        groom_name=payload.groom_name.strip(),
        bride_name=payload.bride_name.strip(),
        venue_name=payload.venue_name.strip(),
    )
    db.add(event)
    db.commit()
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
    delete_event_cascade(db, event)
    db.commit()
