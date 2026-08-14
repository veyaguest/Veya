"""נקודת הכניסה ל-Backend של VEYA (FastAPI)."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from sqlalchemy import inspect, text

from app import models  # noqa: F401  — נדרש כדי לרשום את הטבלאות
from app.database import Base, MigrationSessionLocal, migrations_engine
from app.deps import get_default_event
from app.routers import (
    admin,
    auth,
    automation,
    communication,
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
app.include_router(communication.router)
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
        "event_type": "TEXT DEFAULT 'wedding'",
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
        # שורת ההורים כמזמינים (רגיסטרים דתי/חב"ד/חרדי). נוספו למודל בסבב
        # "3ח" בלי רשומה כאן — ולכן כל DB קיים נשבר בכל שאילתת events
        # ("no such column: events.groom_parents_line"). ראו _ensure_columns:
        # מאז יש גם רשת ביטחון אוטומטית שמונעת הישנות של המקרה הזה.
        "groom_parents_line": "TEXT DEFAULT ''",
        "bride_parents_line": "TEXT DEFAULT ''",
        # תצלום מצב ההושבה שלפני ההרצה האחרונה — ל"החזרת הסידור הקודם".
        "seating_snapshot": "JSON",
        # transform שכבת הסקיצה (בניית אולם אוטומטית מ-AI Vision).
        "hall_sketch_transform": "JSON",
    },
    "messages": {
        "channel": "TEXT DEFAULT 'whatsapp'",
        "rule_id": "INTEGER",
        "provider_message_id": "TEXT",
        "sent_at": "DATETIME",
        "delivered_at": "DATETIME",
        "read_at": "DATETIME",
        "failure_reason": "TEXT DEFAULT ''",
        "failure_code": "INTEGER",
        "provider_status": "TEXT",
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
        "avatar_url": "TEXT DEFAULT ''",
    },
    "guests": {
        "guest_token": "TEXT",
        "confirmed_count": "INTEGER",
        "guest_note": "TEXT",
        "is_child": "BOOLEAN DEFAULT 0",
        # הערות הושבה — נפרד מ-notes_raw (שהפך להערה פנימית בלבד). מתווסף
        # ריק בכוונה: הערות ישנות לא מועתקות אוטומטית, כדי לא להפוך הערה
        # תפעולית לאילוץ ישיבה. במסך המוזמנים יש הצעה להעביר ידנית.
        "seating_notes": "TEXT",
    },
    "venues": {
        "city": "VARCHAR DEFAULT ''",
    },
}


def derive_column_ddl(column) -> str:
    """בונה DDL ל-``ALTER TABLE ... ADD COLUMN`` מתוך הגדרת העמודה במודל.

    רשת ביטחון ל-``_ensure_columns``: אם מישהו הוסיף עמודה למודל ושכח רשומה
    ידנית ב-``_EXTRA_COLUMNS``, העמודה עדיין תתווסף ל-DB במקום לשבור כל
    שאילתה על הטבלה. הטיפוס נגזר דרך מנוע הטיפוסים של SQLAlchemy, ולכן
    נכון גם ל-SQLite וגם ל-Postgres.

    שני כללי בטיחות:
    - **לעולם לא NOT NULL.** ``ADD COLUMN`` עם NOT NULL נכשל על טבלה שכבר יש
      בה שורות, אלא אם יש DEFAULT — ולא בכל מנוע. עמודה חדשה תמיד nullable.
    - **DEFAULT רק לערך סקלרי.** ברירת מחדל שהיא פונקציה (למשל מחולל טוקן)
      מיושמת ע"י SQLAlchemy בזמן INSERT ואין לה ייצוג DDL תקין.
    """
    ddl = column.type.compile(dialect=migrations_engine.dialect)
    default = getattr(column, "default", None)
    if default is not None and not getattr(default, "is_callable", False):
        value = getattr(default, "arg", None)
        if isinstance(value, bool):
            ddl += f" DEFAULT {1 if value else 0}"
        elif isinstance(value, (int, float)):
            ddl += f" DEFAULT {value}"
        elif isinstance(value, str):
            escaped = value.replace("'", "''")
            ddl += f" DEFAULT '{escaped}'"
    return ddl


def missing_migrations() -> dict[str, list[str]]:
    """עמודות שקיימות במודל, חסרות ב-DB, ואין להן רשומה ב-``_EXTRA_COLUMNS``.

    מוחזר גם לשימוש בבדיקת הרגרסיה (``tests/test_schema_migrations.py``),
    כדי שהמקרה הזה ייתפס בבדיקה ולא רק בזמן ריצה בייצור.
    """
    inspector = inspect(migrations_engine)
    gaps: dict[str, list[str]] = {}
    for table_name, table in Base.metadata.tables.items():
        if not inspector.has_table(table_name):
            continue
        existing = {c["name"] for c in inspector.get_columns(table_name)}
        declared = set(_EXTRA_COLUMNS.get(table_name, {}))
        absent = [c.name for c in table.columns if c.name not in existing]
        undeclared = [name for name in absent if name not in declared]
        if undeclared:
            gaps[table_name] = sorted(undeclared)
    return gaps


def _ensure_columns() -> None:
    # DDL (ALTER TABLE) דורש בעלות על הטבלה — לכן תמיד דרך migrations_engine
    # (בפרודקשן עם RLS זה חיבור postgres נפרד מ-DATABASE_URL הרגיל; היום,
    # לפני שההפרדה מופעלת, שני המשתנים מצביעים על אותו חיבור בדיוק).
    inspector = inspect(migrations_engine)
    with migrations_engine.begin() as conn:
        for table, columns in _EXTRA_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))

        # רשת ביטחון: עמודות שבמודל אך לא ב-DB ולא ברשימה הידנית. בלי זה,
        # שכחה של רשומה אחת שוברת כל שאילתה על הטבלה (כפי שקרה עם
        # events.groom_parents_line). מדפיסים אזהרה כדי שזה ייראה בלוג.
        for table_name, table in Base.metadata.tables.items():
            if not inspector.has_table(table_name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table_name)}
            declared = set(_EXTRA_COLUMNS.get(table_name, {}))
            for column in table.columns:
                if column.name in existing or column.name in declared:
                    continue
                ddl = derive_column_ddl(column)
                print(
                    f"[migrations] warning: {table_name}.{column.name} חסרה "
                    f"ב-_EXTRA_COLUMNS — מתווספת אוטומטית כ-{ddl}"
                )
                conn.execute(
                    text(f"ALTER TABLE {table_name} ADD COLUMN {column.name} {ddl}")
                )


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
    # שלב 2 (אופטימיזציית שאילתות, ראה QUERY_OPTIMIZATION.md) — אינדקסים
    # מורכבים (כמה עמודות), לכן הערך הוא tuple של שמות עמודות ולא מחרוזת יחידה.
    "ix_guests_event_rsvp": ("guests", ("event_id", "rsvp_status")),
    "ix_messages_event_direction_kind_status": (
        "messages", ("event_id", "direction", "kind", "status")
    ),
    "ix_audit_logs_user_id": ("audit_logs", "user_id"),
}


def _ensure_indexes() -> None:
    inspector = inspect(migrations_engine)
    with migrations_engine.begin() as conn:
        for name, (table, columns) in _EXTRA_INDEXES.items():
            if not inspector.has_table(table):
                continue
            cols = columns if isinstance(columns, str) else ", ".join(columns)
            conn.execute(
                text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({cols})")
            )


# אינדקסים ייחודיים (בנפרד מ-_EXTRA_INDEXES הרגיל, שאינו UNIQUE). NULL רבים
# מותרים תחת אינדקס ייחודי (SQLite ו-Postgres כאחד — כל NULL נחשב שונה
# מהאחר) — לכן זה לא פוגע בהודעות בלי provider_message_id (תשובות נכנסות,
# שליחות שנכשלו לפני שהוקצה מזהה).
_EXTRA_UNIQUE_INDEXES = {
    # מבטיח שהתאמת webhook לפי provider_message_id (app/message_status.py:
    # apply_status_update) לעולם לא תוכל "לדלוף" ולעדכן הודעה של מוזמן אחר
    # — גם אם באג עתידי ייצור בטעות שני מזהים זהים.
    "ux_messages_provider_message_id": ("messages", "provider_message_id"),
}


def _ensure_unique_indexes() -> None:
    inspector = inspect(migrations_engine)
    with migrations_engine.begin() as conn:
        for name, (table, column) in _EXTRA_UNIQUE_INDEXES.items():
            if not inspector.has_table(table):
                continue
            conn.execute(
                text(f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {table} ({column})")
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

    # תחזוקת עלייה רצה לפני שיש בקשה/משתמש מחובר — דרך MigrationSessionLocal
    # (עוקף RLS), אחרת מדיניות guests/events הייתה חוסמת אותה (אין זהות).
    db = MigrationSessionLocal()
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

    db = MigrationSessionLocal()
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

    db = MigrationSessionLocal()
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


def _migrate_brita_split() -> None:
    """מיגרציה חד-פעמית (2026-08-10): "בריתה" היא סוג אירוע עצמאי משלה —
    ``event_type='brita'`` — לא תת-קטגוריה של "ברית" ולא event_type ישן
    בשם ``brit_bat`` (ראו decisions.md, שני תיקוני כיוון קודמים). מתקנת
    שיירים משני הסבבים הקודמים: (1) שורות שנכתבו ישירות לפרודקשן תחת
    ``event_type='brit_bat'`` לפני שהיה code support — עוברות ל-``brita``.
    (2) יוצרת את 6 שורות ה-``MessageDefault`` (ברירת מחדל ריקה) ל-``brita``,
    שמעולם לא נוצרו כי אין endpoint ליצירת שורה חדשה שם. idempotent — בטוחה
    לרוץ בכל עלייה, לא עושה כלום אחרי הפעם הראשונה.
    """
    from sqlalchemy import select

    from app import communication

    db = MigrationSessionLocal()
    try:
        changed = False
        for model in (models.Event, models.MessageDefault, models.MessageDefaultOption):
            rows = db.scalars(
                select(model).where(model.event_type == "brit_bat")
            ).all()
            for row in rows:
                row.event_type = "brita"
                changed = True

        have_brita_defaults = db.scalar(
            select(models.MessageDefault).where(models.MessageDefault.event_type == "brita")
        )
        if have_brita_defaults is None:
            for message_type in communication.MESSAGE_TYPES:
                db.add(models.MessageDefault(
                    event_type="brita",
                    message_type=message_type,
                    title=communication.MESSAGE_TYPE_LABELS[message_type],
                    content="",
                    variables_supported=list(
                        communication.DEFAULT_VARIABLES_SUPPORTED.get(message_type, [])
                    ),
                ))
            changed = True

        if changed:
            db.commit()
    finally:
        db.close()


def seed_message_defaults() -> None:
    """זורע פעם אחת את קטלוג ברירות המחדל הגלובלי לרצף התקשורת: 7 סוגי
    אירוע × 6 סוגי הודעה = 42 שורות, כולן ``content=""`` (הבעלים יזין את
    הטקסטים הסופיים דרך ``/admin/message-defaults``). רץ רק אם הטבלה ריקה,
    כך שעריכה של האדמין לא נדרסת בהפעלה הבאה."""
    from sqlalchemy import func, select

    from app import communication

    db = MigrationSessionLocal()
    try:
        have = db.scalar(
            select(func.count()).select_from(models.MessageDefault)
        ) or 0
        if have == 0:
            event_types = [
                "wedding", "bar_mitzvah", "bat_mitzvah", "henna",
                "brit", "brita", "business",
            ]
            defaults = [
                models.MessageDefault(
                    event_type=event_type,
                    message_type=message_type,
                    title=communication.MESSAGE_TYPE_LABELS[message_type],
                    content="",
                    variables_supported=list(
                        communication.DEFAULT_VARIABLES_SUPPORTED.get(message_type, [])
                    ),
                )
                for event_type in event_types
                for message_type in communication.MESSAGE_TYPES
            ]
            db.add_all(defaults)
            db.commit()
    finally:
        db.close()


def seed_message_default_options() -> None:
    """זורע פעם אחת את ספריית הנוסחים לבחירה (``MessageDefaultOption``,
    decisions.md 2026-08-06): הזוג בוחר וריאציה מתוך עד 12 לכל
    event_type×message_type, במקום נוסח קבוע יחיד. רץ רק אם הטבלה ריקה.

    בכוונה **חתונה בלבד בשלב הזה** (הוראת הבעלים): 12 נוסחי הזמנה אמיתיים
    שהבעלים שלח (הומרו מ-``{טוקן}`` ל-``{{token}}``), ו-60 שורות ריקות
    (12 לכל אחד מ-5 השלבים הנותרים) שמחכות לנוסחים הבאים. סוגי אירוע
    אחרים לא מקבלים כאן שום שורה — לא עוברים אליהם לפני שחתונה שלמה.
    """
    from sqlalchemy import func, select

    from app import communication

    db = MigrationSessionLocal()
    try:
        have = db.scalar(
            select(func.count()).select_from(models.MessageDefaultOption)
        ) or 0
        if have != 0:
            return

        invitation_vars_full = [
            "guest_name", "groom_name", "bride_name", "event_date",
            "event_time", "venue_name", "address", "rsvp_link",
            "navigation_link",
        ]
        invitation_vars_no_addr_nav = [
            "guest_name", "groom_name", "bride_name", "event_date",
            "event_time", "venue_name", "rsvp_link",
        ]
        invitation_vars_no_nav = [
            "guest_name", "groom_name", "bride_name", "event_date",
            "event_time", "venue_name", "address", "rsvp_link",
        ]

        invitation_options = [
            (
                "חם ומלא פרטים",
                "היי {{guest_name}} ❤️\n\n"
                "אנחנו שמחים ונרגשים להזמין אותך לערב החתונה שלנו.\n\n"
                "{{groom_name}} & {{bride_name}}\n\n"
                "📅 {{event_date}}\n⏰ {{event_time}}\n📍 {{venue_name}}\n📌 {{address}}\n\n"
                "נשמח לראות אותך איתנו ולחגוג יחד.\n\n"
                "לאישור הגעה:\n{{rsvp_link}}\n\n"
                "לניווט:\n{{navigation_link}}",
                invitation_vars_full,
            ),
            (
                "אישי ומשתף",
                "היי {{guest_name}} ❤️\n\n"
                "רצינו לשתף אותך שאנחנו מתחתנים ולהזמין אותך לחגוג איתנו את הערב המיוחד הזה.\n\n"
                "{{groom_name}} ו־{{bride_name}}\n\n"
                "📅 {{event_date}}\n⏰ {{event_time}}\n📍 {{venue_name}}\n\n"
                "נשמח מאוד שתהיה איתנו.\n\n"
                "לאישור הגעה:\n{{rsvp_link}}",
                invitation_vars_no_addr_nav,
            ),
            (
                "נרגש וחגיגי",
                "היי {{guest_name}},\n\n"
                "אנחנו מתרגשים לקראת היום הגדול שלנו ושמחים להזמין אותך לחתונה שלנו ❤️\n\n"
                "{{groom_name}} & {{bride_name}}\n\n"
                "📅 {{event_date}}\n⏰ {{event_time}}\n📍 {{venue_name}}\n📌 {{address}}\n\n"
                "מחכים לראות אותך ולשמוח יחד.\n\n"
                "לאישור הגעה:\n{{rsvp_link}}",
                invitation_vars_no_nav,
            ),
            (
                "מספר את המסע האישי",
                "היי {{guest_name}} ❤️\n\n"
                "אחרי הרבה הכנות והתרגשות הגיע הרגע שלנו.\n\n"
                "נשמח להזמין אותך לערב החתונה שלנו ולחגוג איתנו.\n\n"
                "{{groom_name}} & {{bride_name}}\n\n"
                "📅 {{event_date}}\n⏰ {{event_time}}\n📍 {{venue_name}}\n\n"
                "לאישור הגעה:\n{{rsvp_link}}",
                invitation_vars_no_addr_nav,
            ),
            (
                "פשוט וקצר",
                "היי {{guest_name}},\n\n"
                "אנחנו שמחים להזמין אותך להיות איתנו בערב החתונה שלנו ❤️\n\n"
                "{{groom_name}} ו־{{bride_name}}\n\n"
                "📅 {{event_date}}\n⏰ {{event_time}}\n📍 {{venue_name}}\n\n"
                "נשמח לראות אותך איתנו.\n\n"
                "לאישור:\n{{rsvp_link}}",
                invitation_vars_no_addr_nav,
            ),
            (
                "אישי ובלעדי",
                "היי {{guest_name}} ❤️\n\n"
                "רצינו להזמין אותך באופן אישי לחתונה שלנו.\n\n"
                "אנחנו מתרגשים מאוד ונשמח לחגוג איתך את הערב הזה.\n\n"
                "{{groom_name}} & {{bride_name}}\n\n"
                "📅 {{event_date}}\n⏰ {{event_time}}\n📍 {{venue_name}}\n📌 {{address}}\n\n"
                "לאישור הגעה:\n{{rsvp_link}}",
                invitation_vars_no_nav,
            ),
            (
                "רשמי וחגיגי",
                "שלום {{guest_name}} ❤️\n\n"
                "בשמחה ובהתרגשות אנחנו מזמינים אותך לחתונה שלנו.\n\n"
                "{{groom_name}} & {{bride_name}}\n\n"
                "📅 {{event_date}}\n⏰ {{event_time}}\n📍 {{venue_name}}\n\n"
                "נשמח מאוד שתגיע לחגוג איתנו.\n\n"
                "אישור הגעה:\n{{rsvp_link}}",
                invitation_vars_no_addr_nav,
            ),
            (
                "הכרזה נרגשת",
                "היי {{guest_name}},\n\n"
                "הגיע הזמן לשתף אותך בתאריך החשוב שלנו ❤️\n\n"
                "אנחנו מתחתנים ונשמח שתהיה איתנו בערב החתונה.\n\n"
                "{{groom_name}} & {{bride_name}}\n\n"
                "📅 {{event_date}}\n⏰ {{event_time}}\n📍 {{venue_name}}\n\n"
                "מחכים לראות אותך.\n\n"
                "לאישור הגעה:\n{{rsvp_link}}",
                invitation_vars_no_addr_nav,
            ),
            (
                "נרגש ופשוט",
                "היי {{guest_name}} ❤️\n\n"
                "אנחנו נרגשים לקראת החתונה שלנו ורוצים להזמין אותך לחגוג איתנו.\n\n"
                "{{groom_name}} ו־{{bride_name}}\n\n"
                "📅 {{event_date}}\n⏰ {{event_time}}\n📍 {{venue_name}}\n\n"
                "נשמח מאוד לראות אותך שם.\n\n"
                "לאישור:\n{{rsvp_link}}",
                invitation_vars_no_addr_nav,
            ),
            (
                "רשמי וחם",
                "שלום {{guest_name}},\n\n"
                "אנחנו שמחים ונרגשים לקראת הערב הגדול שלנו.\n\n"
                "נשמח שתהיה איתנו בחתונה שלנו ❤️\n\n"
                "{{groom_name}} & {{bride_name}}\n\n"
                "📅 {{event_date}}\n⏰ {{event_time}}\n📍 {{venue_name}}\n📌 {{address}}\n\n"
                "לאישור הגעה:\n{{rsvp_link}}",
                invitation_vars_no_nav,
            ),
            (
                "ייחודי ומכובד",
                "היי {{guest_name}} ❤️\n\n"
                "רצינו להזמין אותך לחגוג איתנו את אחד הרגעים החשובים שלנו.\n\n"
                "החתונה של:\n{{groom_name}} & {{bride_name}}\n\n"
                "📅 {{event_date}}\n⏰ {{event_time}}\n📍 {{venue_name}}\n\n"
                "נשמח לראות אותך איתנו.\n\n"
                "אישור הגעה:\n{{rsvp_link}}",
                invitation_vars_no_addr_nav,
            ),
            (
                "חם ומרגש",
                "היי {{guest_name}} ❤️\n\n"
                "אנחנו מתרגשים ושמחים להזמין אותך לערב החתונה שלנו.\n\n"
                "נשמח מאוד שתהיה חלק מהשמחה שלנו ותחגוג איתנו.\n\n"
                "{{groom_name}} & {{bride_name}}\n\n"
                "📅 {{event_date}}\n⏰ {{event_time}}\n📍 {{venue_name}}\n📌 {{address}}\n\n"
                "לאישור הגעה:\n{{rsvp_link}}\n\n"
                "לניווט:\n{{navigation_link}}",
                invitation_vars_full,
            ),
        ]

        rows = [
            models.MessageDefaultOption(
                event_type="wedding",
                message_type="invitation",
                option_number=i + 1,
                tone=tone,
                title=communication.MESSAGE_TYPE_LABELS["invitation"],
                content=content,
                variables_supported=variables,
            )
            for i, (tone, content, variables) in enumerate(invitation_options)
        ]

        # 60 שורות ריקות (5 שלבים × 12) — מבנה זהה, ממתין לנוסחים הבאים.
        remaining_types = [
            mt for mt in communication.MESSAGE_TYPES if mt != "invitation"
        ]
        rows += [
            models.MessageDefaultOption(
                event_type="wedding",
                message_type=message_type,
                option_number=option_number,
                tone="",
                title=communication.MESSAGE_TYPE_LABELS[message_type],
                content="",
                variables_supported=[],
            )
            for message_type in remaining_types
            for option_number in range(1, 13)
        ]

        db.add_all(rows)
        db.commit()
    finally:
        db.close()


@app.on_event("startup")
def on_startup() -> None:
    # גיבוי מתוארך של ה-DB לפני כל שינוי (רק אם הקובץ כבר קיים).
    from app import backup

    backup.create_backup()
    # יוצר את קובץ מסד הנתונים ואת הטבלאות (DDL — דרך חיבור המיגרציות).
    Base.metadata.create_all(bind=migrations_engine)
    # מוסיף עמודות חדשות לטבלאות קיימות (מיגרציה קלה).
    _ensure_columns()
    # מוסיף אינדקסים על מפתחות זרים (לביצועים) אם עדיין אין.
    _ensure_indexes()
    # אינדקסים ייחודיים (מונעים התאמת webhook כפולה/מדליפה) אם עדיין אין.
    _ensure_unique_indexes()
    # מוציא תמונות base64 ישנות מה-DB לקבצים (חד-פעמי, בטוח לחזרה).
    _migrate_images()
    # מוודא שיש בעלים (אדמין) אחד לפחות.
    _ensure_admin()
    # מוודא שלכל מוזמן קיים יש טוקן אישי לאישור הגעה.
    _ensure_guest_tokens()
    # "בריתה" כ-event_type עצמאי משלה (2026-08-10) — מתקנת שיירי דאטה
    # משני תיקוני הכיוון הקודמים. חייבת לרוץ לפני הזריעה למטה.
    _migrate_brita_split()
    # זורע את קטלוג ברירות המחדל הגלובלי לרצף התקשורת (7 סוגי אירוע × 6
    # סוגי הודעה, ריק) אם ריק.
    seed_message_defaults()
    # זורע את ספריית הנוסחים לבחירה (עד 12 לכל event_type×message_type),
    # חתונה בלבד בשלב הזה — ראו seed_message_default_options.
    seed_message_default_options()
    # מוודא שקיים אירוע ברירת-מחדל אחד (תחזוקת עלייה — בלי זהות משתמש).
    db = MigrationSessionLocal()
    try:
        get_default_event(db)
    finally:
        db.close()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "veya-api"}
