"""מאגר האולמות — לוגיקת עזר (בלי FastAPI): רישום אוטומטי וחיפוש.

המאגר נבנה לבד: בכל פעם שזוג שומר שם+כתובת אולם באירוע, קוראים ל-
``record_venue`` והוא מוסיף/מעדכן רשומה במאגר המשותף. כשזוג אחר מקליד שם
אולם, ``search_venues`` מציע התאמות עם הכתובת — כדי לחסוך הקלדה ולהפעיל
ניווט אוטומטי. אין קריאות רשת/LLM, אין תלות ב-API בתשלום.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models


def _dedup_key(name: str) -> str:
    """שם מנורמל לדדופ: אותיות קטנות + כיווץ רווחים. ריק => אין מפתח."""
    return " ".join((name or "").strip().lower().split())


def record_venue(db: Session, name: str, address: str) -> None:
    """מוסיף/מעדכן אולם במאגר לפי שם. לא מבצע commit — הקורא אחראי לכך.

    - שם ריק => מתעלמים (אין מה לשמור).
    - קיים אולם עם אותו שם מנורמל => מעלים usage_count, ומעדכנים כתובת אם
      התקבלה כתובת חדשה לא-ריקה (הכי עדכני מנצח).
    - אחרת => יוצרים רשומה חדשה.
    """
    name = (name or "").strip()
    address = (address or "").strip()
    key = _dedup_key(name)
    if not key:
        return
    existing = db.scalar(select(models.Venue).where(models.Venue.dedup_key == key))
    if existing:
        existing.usage_count = (existing.usage_count or 1) + 1
        if address:
            existing.address = address
    else:
        db.add(models.Venue(name=name, address=address, dedup_key=key))


def search_venues(db: Session, query: str, limit: int = 8) -> list[models.Venue]:
    """מחזיר אולמות שהשם שלהם מכיל את מחרוזת החיפוש (case-insensitive).

    דירוג: פופולריים (usage_count) קודם, ואז לפי שם. מחרוזת ריקה => ריק.
    """
    q = (query or "").strip()
    if not q:
        return []
    pattern = f"%{q.lower()}%"
    return list(
        db.scalars(
            select(models.Venue)
            .where(func.lower(models.Venue.name).like(pattern))
            .order_by(models.Venue.usage_count.desc(), models.Venue.name.asc())
            .limit(limit)
        ).all()
    )
