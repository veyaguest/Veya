"""נקודת הכניסה ל-Backend של VEYA (FastAPI)."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import inspect, text

from app import models  # noqa: F401  — נדרש כדי לרשום את הטבלאות
from app.database import Base, SessionLocal, engine
from app.deps import get_default_event
from app.routers import (
    admin,
    auth,
    constraints,
    event,
    events,
    guests,
    hall,
    import_guests,
    messaging,
    seating,
    stats,
)

app = FastAPI(title="VEYA API", version="0.1.0")

# מאפשר ל-Frontend (Vite, פורט 5173) לפנות ל-API בזמן פיתוח.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(events.router)
app.include_router(guests.router)
app.include_router(import_guests.router)
app.include_router(seating.router)
app.include_router(constraints.router)
app.include_router(messaging.router)
app.include_router(stats.router)
app.include_router(event.router)
app.include_router(hall.router)


# עמודות שנוספו אחרי היצירה הראשונית של הטבלה — הוספה עדינה כדי לא לאבד נתונים.
# (SQLite לא מוסיף עמודות אוטומטית ב-create_all. ב-Postgres בעתיד — Alembic.)
_EXTRA_COLUMNS = {
    "events": {
        "table_positions": "JSON",
        "hall_elements": "JSON",
        "seats_per_table": "INTEGER DEFAULT 12",
        "owner_id": "INTEGER",
    },
    "users": {
        "is_admin": "BOOLEAN DEFAULT 0",
    },
}


def _ensure_columns() -> None:
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table, columns in _EXTRA_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def _ensure_admin() -> None:
    """מוודא שיש לפחות אדמין אחד — מקדם את המשתמש הראשון (הבעלים) אם אין.

    נדרש כי מיגרציית העמודה ``is_admin`` נותנת 0 למשתמשים קיימים; בלי זה
    אף אחד לא יוכל להיכנס לפאנל האדמין אחרי השדרוג.
    """
    from sqlalchemy import func, select

    db = SessionLocal()
    try:
        admins = db.scalar(
            select(func.count()).select_from(models.User).where(models.User.is_admin.is_(True))
        ) or 0
        if admins == 0:
            first = db.scalars(select(models.User).order_by(models.User.id)).first()
            if first is not None:
                first.is_admin = True
                db.commit()
    finally:
        db.close()


@app.on_event("startup")
def on_startup() -> None:
    # יוצר את קובץ מסד הנתונים ואת הטבלאות.
    Base.metadata.create_all(bind=engine)
    # מוסיף עמודות חדשות לטבלאות קיימות (מיגרציה קלה).
    _ensure_columns()
    # מוודא שיש בעלים (אדמין) אחד לפחות.
    _ensure_admin()
    # מוודא שקיים אירוע ברירת-מחדל אחד.
    db = SessionLocal()
    try:
        get_default_event(db)
    finally:
        db.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "veya-api"}
