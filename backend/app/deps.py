"""Dependencies משותפים ל-routers."""
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_user
from app.database import get_db


def get_default_event(db: Session = Depends(get_db)) -> models.Event:
    """מחזיר אירוע ברירת-מחדל (משמש רק באתחול המערכת / תאימות לאחור)."""
    event = db.scalars(select(models.Event)).first()
    if event is None:
        event = models.Event()
        db.add(event)
        db.commit()
        db.refresh(event)
    return event


def get_current_event(
    x_event_id: Optional[int] = Header(default=None, alias="X-Event-Id"),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.Event:
    """מחזיר את האירוע הפעיל של המשתמש המחובר.

    האירוע נבחר לפי כותרת ``X-Event-Id`` שהפרונט שולח. אם לא נשלחה כותרת,
    נבחר האירוע הראשון של המשתמש (נוחות למשתמש עם אירוע יחיד).
    האירוע חייב להיות בבעלות המשתמש — אחרת 404 (לא חושפים אירועים של אחרים).
    """
    if x_event_id is not None:
        event = db.get(models.Event, x_event_id)
        # אדמין (הבעלים) יכול לגשת לכל אירוע; משתמש רגיל — רק לשלו.
        if event is None or (event.owner_id != user.id and not user.is_admin):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="האירוע לא נמצא",
            )
        return event

    event = db.scalars(
        select(models.Event)
        .where(models.Event.owner_id == user.id)
        .order_by(models.Event.id)
    ).first()
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="עדיין לא יצרת אירוע",
        )
    return event
