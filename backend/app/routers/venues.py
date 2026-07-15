"""חיפוש במאגר האולמות המשותף — השלמה אוטומטית בזמן שהזוג מקליד שם אולם.

המאגר נבנה מעצמו: בכל פעם שזוג שומר שם+כתובת אולם, הרשומה נכנסת למאגר
(ראה ``app/venues.py`` ו-``routers/event.py``). כאן הזוג מקבל את הפירות —
מקליד "אול" ומקבל הצעות אולמות עם הכתובת המוכנה וקישורי ניווט, כדי לחסוך
הקלדה ולהפעיל ניווט אוטומטי. נדרשת התחברות (מידע ציבורי, אך לא חושפים לאנונימי).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import messaging, models, schemas, venues
from app.auth import get_current_user
from app.database import get_db

router = APIRouter(prefix="/venues", tags=["venues"])


@router.get("/search", response_model=list[schemas.VenueSuggestion])
def search(
    q: str = "",
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """מחזיר הצעות אולמות שהשם שלהם מכיל את מחרוזת החיפוש, עם כתובת וקישורי ניווט."""
    results = venues.search_venues(db, q)
    return [
        schemas.VenueSuggestion(
            name=v.name,
            address=v.address or "",
            maps_link=messaging.maps_link(v.address or ""),
            waze_link=messaging.waze_link(v.address or ""),
        )
        for v in results
    ]
