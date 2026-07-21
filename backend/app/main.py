"""נקודת הכניסה ל-Backend של VEYA (FastAPI)."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from sqlalchemy import inspect, text

from app import models  # noqa: F401  — נדרש כדי לרשום את הטבלאות
from app.database import Base, SessionLocal, engine
from app.deps import get_default_event
from app.routers import (
    admin,
    auth,
    automation,
    confirm,
    constraints,
    event,
    event_members,
    events,
    guests,
    hall,
    import_guests,
    media_serve,
    messaging,
    seating,
    stats,
    venues,
)

app = FastAPI(title="VEYA API", version="0.1.0")

# מקורות ה-CORS ניתנים להגדרה ממשתנה סביבה (מופרד בפסיקים), כדי שבייצור
# אפשר יהיה להתיר את הדומיין האמיתי. ברירת מחדל: כתובות הפיתוח המקומיות.
_DEFAULT_CORS = "http://localhost:5173,http://127.0.0.1:5173"
_cors_origins = [
    o.strip() for o in os.getenv("CORS_ORIGINS", _DEFAULT_CORS).split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(events.router)
app.include_router(event_members.router)
app.include_router(guests.router)
app.include_router(import_guests.router)
app.include_router(seating.router)
app.include_router(constraints.router)
app.include_router(messaging.router)
app.include_router(stats.router)
app.include_router(event.router)
app.include_router(hall.router)
app.include_router(confirm.router)
app.include_router(automation.router)
app.include_router(venues.router)
app.include_router(media_serve.router)

# הגשת קבצי תמונות שהועלו (הזמנה/סקיצת אולם) מתוך backend/uploads.
from app.media import UPLOADS_DIR  # noqa: E402

UPLOADS_DIR.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")


# עמודות שנוספו אחרי היצירה הראשונית של הטבלה — הוספה עדינה כדי לא לאבד נתונים.
# (SQLite לא מוסיף עמודות אוטומטית ב-create_all. ב-Postgres בעתיד — Alembic.)
_EXTRA_COLUMNS = {
    "events": {
        "group_notes": "JSON",
        "table_positions": "JSON",
        "hall_elements": "JSON",
        "hall_layout": "JSON",
        "seats_per_table": "INTEGER DEFAULT 12",
        "reserve_seats": "INTEGER DEFAULT 0",
        "message_template": "TEXT",
        "event_date": "TEXT DEFAULT ''",
        "event_time": "TEXT DEFAULT ''",
        "venue_address": "TEXT DEFAULT ''",
        "owner_id": "INTEGER",
        "rsvp_track_active": "BOOLEAN DEFAULT 0",
        "rsvp_track_started_at": "DATETIME",
        "venue_commit_days_before": "INTEGER",
    },
    "messages": {
        "channel": "TEXT DEFAULT 'whatsapp'",
        "rule_id": "INTEGER",
    },
    "automation_rules": {
        "action_kind": "TEXT DEFAULT 'send'",
    },
    "users": {
        "is_admin": "BOOLEAN DEFAULT 0",
        "token_version": "INTEGER DEFAULT 1",
        "account_type": "TEXT DEFAULT 'couple'",
        "phone": "TEXT DEFAULT ''",
        "disabled": "BOOLEAN DEFAULT 0",
    },
    "guests": {
        "guest_token": "TEXT",
        "confirmed_count": "INTEGER",
        "guest_note": "TEXT",
        "is_child": "BOOLEAN DEFAULT 0",
    },
    "venues": {
        "city": "VARCHAR DEFAULT ''",
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


# אינדקסים על מפתחות זרים לביצועים. create_all לא מוסיף אותם לטבלאות שכבר
# קיימות, לכן מוסיפים ידנית (בטוח: IF NOT EXISTS). שמות תואמים לקונבנציית
# SQLAlchemy (ix_<table>_<column>) כדי למנוע כפילות.
_EXTRA_INDEXES = {
    "ix_events_owner_id": ("events", "owner_id"),
    "ix_guests_event_id": ("guests", "event_id"),
    "ix_guests_table_number": ("guests", "table_number"),
    "ix_messages_event_id": ("messages", "event_id"),
    "ix_messages_guest_id": ("messages", "guest_id"),
    "ix_messages_rule_id": ("messages", "rule_id"),
    "ix_clarifications_event_id": ("clarifications", "event_id"),
    "ix_message_templates_event_id": ("message_templates", "event_id"),
    "ix_automation_rules_event_id": ("automation_rules", "event_id"),
}


def _ensure_indexes() -> None:
    inspector = inspect(engine)
    with engine.begin() as conn:
        for name, (table, column) in _EXTRA_INDEXES.items():
            if not inspector.has_table(table):
                continue
            conn.execute(
                text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({column})")
            )


def _migrate_images() -> None:
    """מיגרציה חד-פעמית: מוציא תמונות base64 קיימות מה-DB לאחסון הקבוע.

    ערכים ישנים של ``invite_image``/``hall_sketch`` שנשמרו כ-``data:...``
    נשמרים כרשומת בלוב ב-``media_blobs``, ובשורת האירוע נשמר הנתיב הקצר
    (``/media/<id>``) במקומם. רץ בבטחה שוב ושוב (ערכים שכבר הומרו מתחילים
    ב-``/media`` או ``/uploads`` ולא ייגעו).
    """
    from sqlalchemy import select

    from app import media

    db = SessionLocal()
    try:
        events = db.scalars(select(models.Event)).all()
        changed = False
        for ev in events:
            if ev.invite_image and ev.invite_image.startswith("data:"):
                ev.invite_image = media._write_data_url(db, ev.invite_image, f"invite-{ev.id}")
                changed = True
            if ev.hall_sketch and ev.hall_sketch.startswith("data:"):
                ev.hall_sketch = media._write_data_url(db, ev.hall_sketch, f"sketch-{ev.id}")
                changed = True
        if changed:
            db.commit()
    finally:
        db.close()


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


def _ensure_guest_tokens() -> None:
    """מייצר טוקן אישי למוזמנים קיימים שאין להם עדיין (אחרי מיגרציית העמודה)."""
    from sqlalchemy import select

    db = SessionLocal()
    try:
        missing = db.scalars(
            select(models.Guest).where(models.Guest.guest_token.is_(None))
        ).all()
        for guest in missing:
            guest.guest_token = models.generate_guest_token()
        if missing:
            db.commit()
    finally:
        db.close()


def seed_veya_defaults() -> None:
    """זורע פעם אחת את ברירות המחדל הגלובליות של VEYA: ספריית התבניות
    המומלצות (5) + שלבי המסלול הקבוע (4). רץ רק אם הטבלאות ריקות, כך שאדמין
    שערך את הברירות לא ידרוס אותן בהפעלה הבאה."""
    from sqlalchemy import func, select

    db = SessionLocal()
    try:
        have_templates = db.scalar(
            select(func.count()).select_from(models.VeyaTemplate)
        ) or 0
        if have_templates == 0:
            templates = [
                models.VeyaTemplate(
                    stage="invitation", sort_order=1,
                    name="הזמנה לחתונה",
                    body=(
                        "שלום [שם אורח]! 💍\n"
                        "אנחנו [שמות בני הזוג], ונשמח מאוד לראות אתכם בחתונה שלנו!\n\n"
                        "📅 [תאריך האירוע] בשעה [שעה]\n"
                        "📍 [שם האולם], [כתובת]\n\n"
                        "נשמח לדעת אם תגיעו — לאישור הגעה: [קישור אישור]\n"
                        "מחכים לראותכם! ❤️"
                    ),
                ),
                models.VeyaTemplate(
                    stage="first_reminder", sort_order=2,
                    name="תזכורת ראשונה",
                    body=(
                        "היי [שם אורח] 🙂\n"
                        "רצינו להזכיר — עדיין לא קיבלנו את אישור ההגעה שלכם לחתונה של [שמות בני הזוג].\n\n"
                        "📅 [תאריך האירוע] · [שם האולם]\n\n"
                        "זה לוקח רק רגע: [קישור אישור]\n"
                        "תודה! 🙏"
                    ),
                ),
                models.VeyaTemplate(
                    stage="second_reminder", sort_order=3,
                    name="תזכורת שנייה",
                    body=(
                        "[שם אורח], שלום 🙂\n"
                        "אנחנו כבר קרובים לסגור מספרים לחתונה שלנו ([שמות בני הזוג]), ועדיין מחכים לתשובה שלכם.\n\n"
                        "נשמח אם תאשרו הגעה כאן: [קישור אישור]\n"
                        "תודה רבה! ❤️"
                    ),
                ),
                models.VeyaTemplate(
                    stage="thank_you", sort_order=4,
                    name="תודה על האישור",
                    body=(
                        "תודה [שם אורח]! 🎉\n"
                        "שמחנו לקבל את האישור שלכם. נתראה בחתונה של [שמות בני הזוג]!\n\n"
                        "📅 [תאריך האירוע] בשעה [שעה]\n"
                        "📍 [שם האולם], [כתובת]\n\n"
                        "לניווט: [קישור ניווט]"
                    ),
                ),
                models.VeyaTemplate(
                    stage="before_event", sort_order=5,
                    name="לפני האירוע",
                    body=(
                        "היי [שם אורח]! 🥂\n"
                        "מזכירים שהיום מתחתנים [שמות בני הזוג] ואתם מוזמנים!\n\n"
                        "📅 [תאריך האירוע] בשעה [שעה]\n"
                        "📍 [שם האולם], [כתובת]\n\n"
                        "לניווט נוח: [קישור ניווט]\n"
                        "נתראה! ❤️"
                    ),
                ),
            ]
            db.add_all(templates)
            db.commit()

        have_steps = db.scalar(
            select(func.count()).select_from(models.VeyaWorkflowStep)
        ) or 0
        if have_steps == 0:
            steps = [
                models.VeyaWorkflowStep(
                    step_order=1, name="תזכורת ראשונה", offset_days=3,
                    action_kind="send", template_stage="first_reminder",
                ),
                models.VeyaWorkflowStep(
                    step_order=2, name="תזכורת שנייה", offset_days=6,
                    action_kind="send", template_stage="second_reminder",
                ),
                models.VeyaWorkflowStep(
                    step_order=3, name="מעקב טלפוני", offset_days=9,
                    action_kind="phone_followup", template_stage="",
                ),
                models.VeyaWorkflowStep(
                    step_order=4, name="מעקב טלפוני שני", offset_days=12,
                    action_kind="phone_followup", template_stage="",
                ),
            ]
            db.add_all(steps)
            db.commit()
    finally:
        db.close()


@app.on_event("startup")
def on_startup() -> None:
    # גיבוי מתוארך של ה-DB לפני כל שינוי (רק אם הקובץ כבר קיים).
    from app import backup

    backup.create_backup()
    # יוצר את קובץ מסד הנתונים ואת הטבלאות.
    Base.metadata.create_all(bind=engine)
    # מוסיף עמודות חדשות לטבלאות קיימות (מיגרציה קלה).
    _ensure_columns()
    # מוסיף אינדקסים על מפתחות זרים (לביצועים) אם עדיין אין.
    _ensure_indexes()
    # מוציא תמונות base64 ישנות מה-DB לקבצים (חד-פעמי, בטוח לחזרה).
    _migrate_images()
    # מוודא שיש בעלים (אדמין) אחד לפחות.
    _ensure_admin()
    # מוודא שלכל מוזמן קיים יש טוקן אישי לאישור הגעה.
    _ensure_guest_tokens()
    # זורע את ברירות המחדל הגלובליות של VEYA (תבניות + מסלול קבוע) אם ריק.
    seed_veya_defaults()
    # מוודא שקיים אירוע ברירת-מחדל אחד.
    db = SessionLocal()
    try:
        get_default_event(db)
    finally:
        db.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "veya-api"}
