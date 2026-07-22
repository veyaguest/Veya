"""מאגר האולמות — לוגיקת עזר (בלי FastAPI): רישום אוטומטי וחיפוש.

המאגר נבנה לבד: בכל פעם שזוג שומר שם+כתובת אולם באירוע, קוראים ל-
``record_venue`` והוא מוסיף/מעדכן רשומה במאגר המשותף. כשזוג אחר מקליד שם
אולם, ``search_venues`` מציע התאמות עם הכתובת — כדי לחסוך הקלדה ולהפעיל
ניווט אוטומטי. אין קריאות רשת/LLM, אין תלות ב-API בתשלום.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import cache, models

# --- caching (שלב 1) ---
# venues הוא מידע ציבורי שמשתנה לעיתים רחוקות (שם/כתובת אולם) — TTL ארוך
# יחסית, אבל עם invalidation מפורש בכל כתיבה כדי שהשינוי ייראה מיד ולא רק
# אחרי שה-TTL פג. כל מפתחות המטמון של venues מתחילים ב-"venues:" כדי
# שאפשר יהיה לנקות את כולם יחד עם invalidate_prefix.
VENUE_CACHE_TTL_SECONDS = 300  # 5 דקות


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
    # המאגר השתנה (שימוש חדש/רשומה חדשה) — מנקים את מטמון החיפוש/הרשימה כדי
    # שהזוג/האדמין הבא יראו את המידע העדכני, לא נתונים ישנים מהמטמון.
    cache.invalidate_prefix("venues:")


def search_venues(db: Session, query: str, limit: int = 8) -> list[models.Venue]:
    """מחזיר אולמות שהשם שלהם מכיל את מחרוזת החיפוש (case-insensitive).

    דירוג: פופולריים (usage_count) קודם, ואז לפי שם. מחרוזת ריקה => ריק.
    תוצאות ממוטמנות לפי (query, limit) ל-``VENUE_CACHE_TTL_SECONDS``.
    """
    q = (query or "").strip()
    if not q:
        return []

    def _load() -> list:
        pattern = f"%{q.lower()}%"
        rows = db.scalars(
            select(models.Venue)
            .where(func.lower(models.Venue.name).like(pattern))
            .order_by(models.Venue.usage_count.desc(), models.Venue.name.asc())
            .limit(limit)
        ).all()
        return cache.snapshot_all(rows)

    key = f"venues:search:{q.lower()}:{limit}"
    return cache.get_or_set(key, VENUE_CACHE_TTL_SECONDS, _load)
