"""Dependencies משותפים ל-routers."""
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import Depends

from app import models
from app.database import get_db


def get_default_event(db: Session = Depends(get_db)) -> models.Event:
    """מחזיר את אירוע ברירת-המחדל, ויוצר אותו אם עוד לא קיים.

    בשלב הנוכחי אין התחברות משתמשים — כל המוזמנים שייכים לאירוע יחיד.
    """
    event = db.scalars(select(models.Event)).first()
    if event is None:
        event = models.Event()
        db.add(event)
        db.commit()
        db.refresh(event)
    return event
