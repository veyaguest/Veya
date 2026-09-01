"""נקודת הכניסה ל-Backend של VEYA (FastAPI)."""
import os
import traceback
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from sqlalchemy import inspect, text

from app import models  # noqa: F401  — נדרש כדי לרשום את הטבלאות
from app.database import (
    Base, IS_POSTGRES, MigrationSessionLocal, migrations_engine,
)
from app.routers import (
    admin,
    auth,
    automation,
    call_center,
    communication,
    confirm,
    constraints,
    event,
    event_members,
    events,
    finance,
    gifts,
    guests,
    hall,
    import_guests,
    media_serve,
    messaging,
    partner,
    payout,
    payout_admin,
    postpone,
    postpone_admin,
    seating,
    stats,
    venues,)

app = FastAPI(title="VEYA API", version="0.1.0")


class _UnhandledErrorMiddleware(BaseHTTPMiddleware):
    """תופס כל חריגה לא-מטופלת (לא HTTPException — למשל IntegrityError
    מ-Postgres) ומחזירה תשובת 500 נקייה, **לפני** ש-CORSMiddleware עוטף
    אותה (ראו סדר app.add_middleware למטה — הרשמה ראשונה = הכי פנימי).

    בלי זה: Starlette מטפל בחריגה לא-מטופלת ב-ServerErrorMiddleware, שעוטף
    את כל שאר ה-middleware מבחוץ — כולל CORSMiddleware. משמעות הדבר:
    תגובת ה-500 יוצאת **בלי** כותרות CORS, הדפדפן חוסם אותה מסיבות אבטחה,
    וה-JS רואה TypeError גולמי (לא תגובת HTTP בכלל) — בדיוק מה שה-frontend
    (api.ts::apiFetch) מתרגם ל"החיבור לשרת נכשל", למרות שהשרת בכלל *ענה*
    עם 500 אמיתי. זה בדיוק מה שקרה במחיקת "משתמש + כל האירועים": חריגה
    לא-מטופלת באמצע ה-cascade הוצגה כתקלת רשת סתומה במקום שגיאת שרת אמיתית.
    """

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except HTTPException:
            raise
        except Exception as exc:
            print(
                f"[veya:unhandled] {request.method} {request.url.path} → {exc!r}",
                flush=True,
            )
            traceback.print_exc()
            return JSONResponse({"detail": "שגיאת שרת פנימית, נסו שוב"}, status_code=500)


app.add_middleware(_UnhandledErrorMiddleware)

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
app.include_router(call_center.router)
app.include_router(events.router)
app.include_router(event_members.router)
app.include_router(partner.router)
app.include_router(guests.router)
app.include_router(import_guests.router)
app.include_router(seating.router)
app.include_router(constraints.router)
app.include_router(messaging.router)
app.include_router(stats.router)
app.include_router(event.router)
app.include_router(hall.router)
app.include_router(confirm.router)
app.include_router(gifts.router)
app.include_router(finance.router)
app.include_router(automation.router)
app.include_router(communication.router)
app.include_router(venues.router)
app.include_router(media_serve.router)
app.include_router(payout.router)
app.include_router(payout_admin.router)
app.include_router(postpone.router)
app.include_router(postpone_admin.router)

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
        "rsvp_track_active": "BOOLEAN DEFAULT FALSE",
        "rsvp_track_started_at": "TIMESTAMP",
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
        # שעת שליחה (שעון ישראל, "HH:MM") למסלול אישורי-ההגעה ולהודעת התודה
        # בנפרד — ראו models.Event. ברירת מחדל '16:00': בטוחה בתוך הטווח
        # המותר (10:00–19:00) גם למשתמשים קיימים.
        "rsvp_send_time": "TEXT DEFAULT '16:00'",
        "thank_you_send_time": "TEXT DEFAULT '16:00'",
        # מחזור האירוע (נוהל דחייה). ברירת המחדל 1 רשומה במפורש — כל אירוע
        # שכבר קיים בייצור הוא מחזור 1, ו-NULL היה שובר את השוואת המחזור
        # בכל שאילתת הודעות.
        "cycle_number": "INTEGER DEFAULT 1",
    },
    "messages": {
        "channel": "TEXT DEFAULT 'whatsapp'",
        "rule_id": "INTEGER",
        "provider_message_id": "TEXT",
        "sent_at": "TIMESTAMP",
        "delivered_at": "TIMESTAMP",
        "read_at": "TIMESTAMP",
        "failure_reason": "TEXT DEFAULT ''",
        "failure_code": "INTEGER",
        "provider_status": "TEXT",
        # לאיזה מחזור אירוע ההודעה שייכת. ברירת מחדל 1 — כל ההודעות שנשלחו
        # לפני נוהל הדחייה הן של המחזור המקורי.
        "cycle_number": "INTEGER DEFAULT 1",
    },
    "automation_rules": {
        "action_kind": "TEXT DEFAULT 'send'",
    },
    "users": {
        "is_admin": "BOOLEAN DEFAULT FALSE",
        "token_version": "INTEGER DEFAULT 1",
        "account_type": "TEXT DEFAULT 'couple'",
        "phone": "TEXT DEFAULT ''",
        "disabled": "BOOLEAN DEFAULT FALSE",
        "avatar_url": "TEXT DEFAULT ''",
        # אימות כתובת המייל. משתמשים קיימים מסומנים כמאומתים ב-
        # ``_migrate_verify_existing_emails`` כדי שלא ייחסמו רטרואקטיבית.
        "email_verified_at": "TIMESTAMP",
        "email_verification_hash": "TEXT",
        "email_verification_expires_at": "TIMESTAMP",
        # קוד אימות בן 6 ספרות (ערוץ מקביל לקישור) — ראו models.User.
        "email_verification_code_hash": "TEXT",
        "email_verification_code_expires_at": "TIMESTAMP",
        "email_verification_code_attempts": "INTEGER DEFAULT 0",
        # איפוס סיסמה עצמאי ("שכחתי סיסמה") — ראו models.User.
        "password_reset_hash": "TEXT",
        "password_reset_expires_at": "TIMESTAMP",
    },
    "guests": {
        "guest_token": "TEXT",
        "confirmed_count": "INTEGER",
        "guest_note": "TEXT",
        "is_child": "BOOLEAN DEFAULT FALSE",
        # הערות הושבה — נפרד מ-notes_raw (שהפך להערה פנימית בלבד). מתווסף
        # ריק בכוונה: הערות ישנות לא מועתקות אוטומטית, כדי לא להפוך הערה
        # תפעולית לאילוץ ישיבה. במסך המוזמנים יש הצעה להעביר ידנית.
        "seating_notes": "TEXT",
    },
    "venues": {
        "city": "VARCHAR DEFAULT ''",
    },
    "postponement_requests": {
        # צילום מורחב של המחזור הנסגר (אולם/כתובת/מועד סגירה) — נוסף אחרי
        # שהטבלה כבר נפרסה לייצור. כולן nullable: בקשה שאושרה לפני התוספת
        # נשארת בלי צילום, ו-``previous_snapshot_at = NULL`` הוא בדיוק הסמן
        # שאומר לקוד ליפול חזרה לערכי האירוע החיים.
        "previous_venue_name": "TEXT",
        "previous_venue_address": "TEXT",
        "previous_venue_commit_days_before": "INTEGER",
        "previous_snapshot_at": "TIMESTAMP",
    },
    "call_logs": {
        # נוסף אחרי הטבלה עצמה — מאפשר ל"מספר שגוי" להיסגר אוטומטית כשהמספר
        # מתעדכן (ראו models.CallLog.phone_at_call).
        "phone_at_call": "TEXT DEFAULT ''",
    },
    "payout_accounts": {
        # הטבלה נפרסה לייצור לפני שנוסף לה מסלול הסטטוסים. ברירת המחדל
        # 'missing' רשומה כאן במפורש (ולא נסמכת על רשת הביטחון האוטומטית)
        # כדי ששורות שכבר קיימות יקבלו סטטוס תקין ולא NULL — סטטוס NULL
        # לא היה עובר את מכונת המצבים ב-payout_status.
        "status": "TEXT DEFAULT 'missing'",
        "submitted_at": "TIMESTAMP",
        "status_changed_at": "TIMESTAMP",
        "rejection_reason": "TEXT",
        # מי ב-VEYA הכריע בבדיקה האחרונה, ומתי.
        "veya_reviewed_by_user_id": "INTEGER",
        "veya_reviewed_at": "TIMESTAMP",
        # בדיקת ספק הסליקה — עמודה נפרדת מ-status. ברירת המחדל 'pending'
        # רשומה במפורש כדי ששורות שכבר קיימות בייצור יקבלו ערך תקין ולא
        # NULL: חשבון בלי תשובת ספק אינו חשבון שהספק אישר.
        "provider_status": "TEXT DEFAULT 'pending'",
        "provider_status_changed_at": "TIMESTAMP",
        "provider_rejection_reason": "TEXT",
        # שדות לספק עתידי — נוצרים ריקים ואין להם כותב היום.
        "provider": "TEXT",
        "provider_account_id": "TEXT",
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
            # TRUE/FALSE (לא 1/0): Postgres לא מקבל ליטרל שלם כברירת מחדל
            # לעמודת BOOLEAN ("column is of type boolean but default
            # expression is of type integer") — תקין גם ב-SQLite.
            ddl += f" DEFAULT {'TRUE' if value else 'FALSE'}"
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


def _ensure_columns() -> set:
    """מוסיף עמודות חסרות, ומחזיר את קבוצת ``(table, column)`` שנוספו בפועל.

    ערך ההחזרה משמש מיגרציות-נתונים שצריכות לרוץ **בדיוק פעם אחת** — ברגע
    שהעמודה נולדה, ולא בכל עלייה מחדש של השרת (ראו
    ``_migrate_verify_existing_emails``: אם היא הייתה רצה בכל עלייה, היא
    הייתה מאמתת אוטומטית גם משתמשים חדשים שטרם אימתו את המייל).
    """
    # DDL (ALTER TABLE) דורש בעלות על הטבלה — לכן תמיד דרך migrations_engine
    # (בפרודקשן עם RLS זה חיבור postgres נפרד מ-DATABASE_URL הרגיל; היום,
    # לפני שההפרדה מופעלת, שני המשתנים מצביעים על אותו חיבור בדיוק).
    added: set = set()
    inspector = inspect(migrations_engine)
    with migrations_engine.begin() as conn:
        for table, columns in _EXTRA_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    added.add((table, name))

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
                added.add((table_name, column.name))
    return added


def _migrate_verify_existing_emails(added_columns: set) -> None:
    """מסמן משתמשים שכבר היו במערכת כ"מייל מאומת" — פעם אחת, בעת הוספת העמודה.

    בלי זה, כל מי שנרשם לפני שאימות המייל הוצג היה נחסם פתאום ונדרש לאמת
    כתובת — משתמשים קיימים לא נשברים (זו דרישה מפורשת). רץ **רק** ברגע
    שהעמודה ``email_verified_at`` נוצרה; מהרגע הזה והלאה כל משתמש חדש עובר
    את זרימת האימות הרגילה.
    """
    if ("users", "email_verified_at") not in added_columns:
        return
    with migrations_engine.begin() as conn:
        conn.execute(
            text("UPDATE users SET email_verified_at = :now WHERE email_verified_at IS NULL"),
            {"now": datetime.utcnow()},
        )
    print("[migrations] משתמשים קיימים סומנו כבעלי מייל מאומת (חד-פעמי)")


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
    # Call Center — התור נשלף לפי (אירוע, סבב) ולפי מוזמן.
    "ix_call_logs_event_id": ("call_logs", "event_id"),
    "ix_call_logs_guest_id": ("call_logs", "guest_id"),
    "ix_call_logs_event_round": ("call_logs", ("event_id", "round_number")),
    # הקצאת אירועים לטלפנים — נשלפת תמיד לפי המשתמש המחובר.
    "ix_call_assignments_user_id": ("call_assignments", "user_id"),
    "ix_call_assignments_event_id": ("call_assignments", "event_id"),
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
    # מניעת כפילות בעסקאות מתנה. זו ההגנה **האמיתית** מפני לחיצה כפולה:
    # הבדיקה ב-Python (gift_service.create_gift) היא רק קיצור דרך, ואילו
    # שתי בקשות שרצות ממש במקביל נעצרות כאן, ברמת ה-DB.
    "ux_gifts_idempotency_key": ("gifts", "idempotency_key"),
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
    אירוע × כל ``communication.MESSAGE_TYPES``, כולן ``content=""`` (הבעלים
    יזין את הטקסטים הסופיים דרך ``/admin/message-defaults``). רץ רק אם הטבלה
    ריקה, כך שעריכה של האדמין לא נדרסת בהפעלה הבאה. סוגי הודעה שנולדו אחרי
    שהטבלה כבר מלאה בפרודקשן מושלמים בנפרד (ראו ``_ensure_rsvp_request_message_default``)."""
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


# נוסחי "בקשת אישור ראשונה" לפי סוג אירוע — וריאציות שהבעלים שלח (2026-08-29).
# משתמשים ב-{{guest_name}} וב-{{rsvp_link}} בלבד. משמשים גם את הזריעה
# הראשונית (``seed_message_default_options``) וגם את ההשלמה בפרודקשן
# (``_ensure_rsvp_request_message_default``). האפשרות הראשונה של כל סוג
# משמשת גם כברירת המחדל שמוקצית אוטומטית (``MessageDefault.content``), כי
# הבקשה נשלחת אוטומטית ואסור שתישאר ריקה בשקט. סוג אירוע שלא מופיע כאן —
# ``MessageDefault.content`` שלו נשאר ריק עד שהבעלים יזין נוסח.
_RSVP_REQUEST_OPTION_VARS = ["guest_name", "rsvp_link"]
_RSVP_REQUEST_OPTIONS_BY_TYPE: dict[str, list[tuple[str, str]]] = {}
_RSVP_REQUEST_OPTIONS_BY_TYPE["wedding"] = [
    (
        "פשוט וחם",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח שתעדכנו אותנו אם אתם מגיעים לחתונה שלנו.\n\n"
        "אפשר לאשר הגעה כאן:\n{{rsvp_link}}",
    ),
    (
        "אישי ורגוע",
        "היי {{guest_name}} 😊\n\n"
        "נשמח לדעת אם תוכלו להיות איתנו ביום המיוחד שלנו.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "תזכורת עדינה",
        "היי {{guest_name}} ❤️\n\n"
        "קיבלתם את ההזמנה שלנו?\n"
        "נשמח שתעדכנו אותנו אם אתם מגיעים.\n\n"
        "{{rsvp_link}}",
    ),
    (
        "קצר וברור",
        "היי {{guest_name}}!\n\n"
        "נשמח לקבל מכם תשובה לגבי ההגעה לחתונה ❤️\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "מזמין",
        "היי {{guest_name}} ❤️\n\n"
        "אנחנו מזמינים אתכם לחגוג איתנו, ונשמח לדעת אם אתם מגיעים.\n\n"
        "אפשר לעדכן כאן:\n{{rsvp_link}}",
    ),
    (
        "קצר מאוד",
        "היי {{guest_name}} 😊\n\n"
        "נשמח לדעת אם אתם מצטרפים אלינו לחתונה.\n\n"
        "אישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "מצפים לראות אתכם",
        "היי {{guest_name}} ❤️\n\n"
        "אנחנו רוצים לדעת אם נוכל לצפות לראות אתכם איתנו בחתונה.\n\n"
        "נשמח שתעדכנו כאן:\n{{rsvp_link}}",
    ),
    (
        "מנומס וחם",
        "היי {{guest_name}}!\n\n"
        "נשמח אם תוכלו לעדכן אותנו לגבי ההגעה שלכם לחתונה.\n\n"
        "{{rsvp_link}}\n\n"
        "תודה ❤️",
    ),
    (
        "רגוע וקליל",
        "היי {{guest_name}} 🥰\n\n"
        "נשמח לדעת אם אתם איתנו.\n\n"
        "אפשר לאשר הגעה בקלות כאן:\n{{rsvp_link}}",
    ),
    (
        "נערכים לקראת",
        "היי {{guest_name}} ❤️\n\n"
        "אנחנו רוצים להתחיל להיערך לקראת החתונה, ונשמח לדעת אם אתם מגיעים.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "מצפים לתשובה",
        "היי {{guest_name}} 😊\n\n"
        "נשמח לקבל מכם אישור הגעה לחתונה שלנו.\n\n"
        "לעדכון:\n{{rsvp_link}}\n\n"
        "מחכים לתשובה ❤️",
    ),
    (
        "חם ומודה",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח לדעת אם תוכלו להגיע ולחגוג איתנו.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}\n\n"
        "תודה רבה!",
    ),
]

_RSVP_REQUEST_OPTIONS_BY_TYPE["henna"] = [
    (
        "פשוט וחם",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח שתעדכנו אותנו אם אתם מגיעים לחינה שלנו.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "אישי ורגוע",
        "היי {{guest_name}} 😊\n\n"
        "נשמח לדעת אם תוכלו להיות איתנו בחינה.\n\n"
        "אפשר לאשר הגעה כאן:\n{{rsvp_link}}",
    ),
    (
        "תזכורת עדינה",
        "היי {{guest_name}} ❤️\n\n"
        "קיבלתם את ההזמנה שלנו?\n"
        "נשמח שתעדכנו אותנו אם אתם מצטרפים.\n\n"
        "{{rsvp_link}}",
    ),
    (
        "קצר וברור",
        "היי {{guest_name}}!\n\n"
        "נשמח לקבל מכם אישור הגעה לחינה ❤️\n\n"
        "אפשר לעדכן כאן:\n{{rsvp_link}}",
    ),
    (
        "מזמין",
        "היי {{guest_name}} ❤️\n\n"
        "אנחנו מזמינים אתכם להיות איתנו בחינה, ונשמח לדעת אם אתם מגיעים.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "רגוע וקליל",
        "היי {{guest_name}} 🥰\n\n"
        "נשמח לדעת אם אתם מצטרפים אלינו לחינה.\n\n"
        "אישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "מצפים לראות אתכם",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח לדעת אם נוכל לצפות לראות אתכם איתנו בחינה.\n\n"
        "אפשר לעדכן כאן:\n{{rsvp_link}}",
    ),
    (
        "מנומס וחם",
        "היי {{guest_name}} 😊\n\n"
        "נשמח אם תוכלו לעדכן אותנו לגבי ההגעה שלכם לחינה.\n\n"
        "{{rsvp_link}}\n\n"
        "תודה ❤️",
    ),
    (
        "ישיר",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח לדעת אם אתם איתנו בחינה.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "נערכים לקראת",
        "היי {{guest_name}}!\n\n"
        "אנחנו מתחילים להיערך לקראת החינה, ונשמח לדעת אם אתם מגיעים.\n\n"
        "{{rsvp_link}}",
    ),
    (
        "מצפים לתשובה",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח לקבל מכם תשובה לגבי ההגעה לחינה שלנו.\n\n"
        "אפשר לאשר כאן:\n{{rsvp_link}}",
    ),
    (
        "חם ומודה",
        "היי {{guest_name}} 😊\n\n"
        "נשמח שתצטרפו אלינו לחינה.\n\n"
        "רק עדכנו אותנו אם אתם מגיעים:\n{{rsvp_link}}\n\n"
        "תודה ❤️",
    ),
]

_RSVP_REQUEST_OPTIONS_BY_TYPE["brit"] = [
    (
        "פשוט וחם",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח שתעדכנו אותנו אם אתם מגיעים לברית.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "אישי ורגוע",
        "היי {{guest_name}} 😊\n\n"
        "נשמח לדעת אם תוכלו להיות איתנו ולחגוג את הרגע המיוחד.\n\n"
        "אפשר לאשר הגעה כאן:\n{{rsvp_link}}",
    ),
    (
        "תזכורת עדינה",
        "היי {{guest_name}} ❤️\n\n"
        "קיבלתם את ההזמנה שלנו?\n"
        "נשמח שתעדכנו אותנו אם אתם מגיעים.\n\n"
        "{{rsvp_link}}",
    ),
    (
        "קצר וברור",
        "היי {{guest_name}}!\n\n"
        "נשמח לקבל מכם אישור הגעה לברית ❤️\n\n"
        "אפשר לעדכן כאן:\n{{rsvp_link}}",
    ),
    (
        "מזמין",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח שתהיו איתנו באירוע ונשמח לדעת אם אתם מגיעים.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "רגוע וקליל",
        "היי {{guest_name}} 🥰\n\n"
        "נשמח לדעת אם אתם מצטרפים אלינו.\n\n"
        "אישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "מצפים לראות אתכם",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח לראות אתכם איתנו בברית.\n\n"
        "אפשר לעדכן אותנו כאן:\n{{rsvp_link}}",
    ),
    (
        "מנומס וחם",
        "היי {{guest_name}} 😊\n\n"
        "נשמח אם תוכלו לעדכן אותנו לגבי ההגעה שלכם.\n\n"
        "לאישור:\n{{rsvp_link}}\n\n"
        "תודה ❤️",
    ),
    (
        "ישיר",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח לדעת אם אתם איתנו באירוע.\n\n"
        "אישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "נערכים לקראת",
        "היי {{guest_name}}!\n\n"
        "אנחנו מתחילים להיערך לקראת האירוע, ונשמח לדעת אם אתם מגיעים.\n\n"
        "{{rsvp_link}}",
    ),
    (
        "מצפים לתשובה",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח לקבל מכם תשובה לגבי ההגעה לברית.\n\n"
        "אפשר לאשר כאן:\n{{rsvp_link}}",
    ),
    (
        "חם ומודה",
        "היי {{guest_name}} 😊\n\n"
        "נשמח שתצטרפו אלינו לרגע המיוחד הזה.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}\n\n"
        "תודה ❤️",
    ),
]

_RSVP_REQUEST_OPTIONS_BY_TYPE["brita"] = [
    (
        "פשוט וחם",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח שתעדכנו אותנו אם אתם מגיעים לבריתה.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "אישי ורגוע",
        "היי {{guest_name}} 😊\n\n"
        "נשמח לדעת אם תוכלו להיות איתנו בבריתה.\n\n"
        "אפשר לאשר הגעה כאן:\n{{rsvp_link}}",
    ),
    (
        "תזכורת עדינה",
        "היי {{guest_name}} ❤️\n\n"
        "קיבלתם את ההזמנה שלנו?\n"
        "נשמח שתעדכנו אותנו אם אתם מצטרפים.\n\n"
        "{{rsvp_link}}",
    ),
    (
        "קצר וברור",
        "היי {{guest_name}}!\n\n"
        "נשמח לקבל מכם אישור הגעה לבריתה ❤️\n\n"
        "אפשר לעדכן כאן:\n{{rsvp_link}}",
    ),
    (
        "מזמין",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח שתהיו איתנו ונכיר לכם את הקטנה שלנו.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "רגוע וקליל",
        "היי {{guest_name}} 🥰\n\n"
        "נשמח לדעת אם אתם מצטרפים אלינו לבריתה.\n\n"
        "אישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "מצפים לראות אתכם",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח לראות אתכם איתנו בבריתה.\n\n"
        "אפשר לעדכן אותנו כאן:\n{{rsvp_link}}",
    ),
    (
        "מנומס וחם",
        "היי {{guest_name}} 😊\n\n"
        "נשמח אם תוכלו לעדכן אותנו לגבי ההגעה שלכם.\n\n"
        "לאישור:\n{{rsvp_link}}\n\n"
        "תודה ❤️",
    ),
    (
        "ישיר",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח לדעת אם אתם איתנו בבריתה.\n\n"
        "אישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "נערכים לקראת",
        "היי {{guest_name}}!\n\n"
        "נשמח לדעת אם אתם מגיעים לבריתה שלנו.\n\n"
        "אפשר לעדכן כאן:\n{{rsvp_link}}",
    ),
    (
        "מצפים לתשובה",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח לקבל מכם תשובה לגבי ההגעה לבריתה.\n\n"
        "לאישור:\n{{rsvp_link}}",
    ),
    (
        "חם ומודה",
        "היי {{guest_name}} 😊\n\n"
        "נשמח שתצטרפו אלינו לרגע המיוחד הזה.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}\n\n"
        "תודה ❤️",
    ),
]

_RSVP_REQUEST_OPTIONS_BY_TYPE["bar_mitzvah"] = [
    (
        "פשוט וחם",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח שתעדכנו אותנו אם אתם מגיעים לבר המצווה.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "אישי ורגוע",
        "היי {{guest_name}} 😊\n\n"
        "נשמח לדעת אם תוכלו להיות איתנו בבר המצווה.\n\n"
        "אפשר לאשר הגעה כאן:\n{{rsvp_link}}",
    ),
    (
        "תזכורת עדינה",
        "היי {{guest_name}} ❤️\n\n"
        "קיבלתם את ההזמנה שלנו?\n"
        "נשמח שתעדכנו אותנו אם אתם מצטרפים.\n\n"
        "{{rsvp_link}}",
    ),
    (
        "קצר וברור",
        "היי {{guest_name}}!\n\n"
        "נשמח לקבל מכם אישור הגעה לבר המצווה ❤️\n\n"
        "אפשר לעדכן כאן:\n{{rsvp_link}}",
    ),
    (
        "מזמין",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח שתהיו איתנו ונחגוג יחד את בר המצווה.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "רגוע וקליל",
        "היי {{guest_name}} 🥳\n\n"
        "נשמח לדעת אם אתם מצטרפים אלינו לבר המצווה.\n\n"
        "אישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "מצפים לראות אתכם",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח לראות אתכם איתנו ביום המיוחד הזה.\n\n"
        "אפשר לעדכן כאן:\n{{rsvp_link}}",
    ),
    (
        "מנומס וחם",
        "היי {{guest_name}} 😊\n\n"
        "נשמח אם תוכלו לעדכן אותנו לגבי ההגעה שלכם לבר המצווה.\n\n"
        "{{rsvp_link}}\n\n"
        "תודה ❤️",
    ),
    (
        "ישיר",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח לדעת אם אתם איתנו בבר המצווה.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "נערכים לקראת",
        "היי {{guest_name}}!\n\n"
        "נשמח לדעת אם אתם מגיעים לחגוג איתנו.\n\n"
        "אפשר לאשר כאן:\n{{rsvp_link}}",
    ),
    (
        "מצפים לתשובה",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח לקבל מכם תשובה לגבי ההגעה לבר המצווה.\n\n"
        "{{rsvp_link}}",
    ),
    (
        "חם ומודה",
        "היי {{guest_name}} 😊\n\n"
        "נשמח שתצטרפו אלינו לחגוג את בר המצווה.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}\n\n"
        "תודה ❤️",
    ),
]

_RSVP_REQUEST_OPTIONS_BY_TYPE["bat_mitzvah"] = [
    (
        "פשוט וחם",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח שתעדכנו אותנו אם אתם מגיעים לבת המצווה.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "אישי ורגוע",
        "היי {{guest_name}} 😊\n\n"
        "נשמח לדעת אם תוכלו להיות איתנו בבת המצווה.\n\n"
        "אפשר לאשר הגעה כאן:\n{{rsvp_link}}",
    ),
    (
        "תזכורת עדינה",
        "היי {{guest_name}} ❤️\n\n"
        "קיבלתם את ההזמנה שלנו?\n"
        "נשמח שתעדכנו אותנו אם אתם מצטרפים.\n\n"
        "{{rsvp_link}}",
    ),
    (
        "קצר וברור",
        "היי {{guest_name}}!\n\n"
        "נשמח לקבל מכם אישור הגעה לבת המצווה ❤️\n\n"
        "אפשר לעדכן כאן:\n{{rsvp_link}}",
    ),
    (
        "מזמין",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח שתהיו איתנו ונחגוג יחד את בת המצווה.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "רגוע וקליל",
        "היי {{guest_name}} 🥰\n\n"
        "נשמח לדעת אם אתם מצטרפים אלינו לבת המצווה.\n\n"
        "אישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "מצפים לראות אתכם",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח לראות אתכם איתנו ביום המיוחד הזה.\n\n"
        "אפשר לעדכן כאן:\n{{rsvp_link}}",
    ),
    (
        "מנומס וחם",
        "היי {{guest_name}} 😊\n\n"
        "נשמח אם תוכלו לעדכן אותנו לגבי ההגעה שלכם לבת המצווה.\n\n"
        "{{rsvp_link}}\n\n"
        "תודה ❤️",
    ),
    (
        "ישיר",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח לדעת אם אתם איתנו בבת המצווה.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "נערכים לקראת",
        "היי {{guest_name}}!\n\n"
        "נשמח לדעת אם אתם מגיעים לחגוג איתנו.\n\n"
        "אפשר לאשר כאן:\n{{rsvp_link}}",
    ),
    (
        "מצפים לתשובה",
        "היי {{guest_name}} ❤️\n\n"
        "נשמח לקבל מכם תשובה לגבי ההגעה לבת המצווה.\n\n"
        "{{rsvp_link}}",
    ),
    (
        "חם ומודה",
        "היי {{guest_name}} 😊\n\n"
        "נשמח שתצטרפו אלינו לחגוג את בת המצווה.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}\n\n"
        "תודה ❤️",
    ),
]

# אירוע עסקי — טון מנומס ומאופק, בלי אימוג'י (בהתאם ל-veya-copy).
_RSVP_REQUEST_OPTIONS_BY_TYPE["business"] = [
    (
        "רשמי",
        "שלום {{guest_name}},\n\n"
        "נשמח לדעת אם תוכלו להשתתף באירוע שלנו.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "מארחים",
        "היי {{guest_name}},\n\n"
        "נשמח לארח אתכם באירוע ונשמח לקבל את אישור ההגעה שלכם.\n\n"
        "{{rsvp_link}}",
    ),
    (
        "ישיר",
        "שלום {{guest_name}},\n\n"
        "נשמח לדעת אם אתם מתכננים להגיע לאירוע.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "מבקש עדכון",
        "היי {{guest_name}},\n\n"
        "נשמח אם תוכלו לעדכן אותנו לגבי השתתפותכם באירוע.\n\n"
        "אפשר לאשר כאן:\n{{rsvp_link}}",
    ),
    (
        "מזמין",
        "שלום {{guest_name}},\n\n"
        "נשמח לראות אתכם באירוע שלנו.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "קצר",
        "היי {{guest_name}},\n\n"
        "נשמח לדעת אם תוכלו להצטרף אלינו לאירוע.\n\n"
        "אישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "מנומס ומודה",
        "שלום {{guest_name}},\n\n"
        "נשמח לקבל מכם עדכון לגבי ההגעה לאירוע.\n\n"
        "{{rsvp_link}}\n\n"
        "תודה.",
    ),
    (
        "אישי",
        "היי {{guest_name}},\n\n"
        "נשמח אם תוכלו להיות איתנו באירוע.\n\n"
        "אפשר לעדכן כאן:\n{{rsvp_link}}",
    ),
    (
        "רשמי ומצפה",
        "שלום {{guest_name}},\n\n"
        "נשמח לדעת אם נוכל לצפות לראותכם באירוע.\n\n"
        "לאישור הגעה:\n{{rsvp_link}}",
    ),
    (
        "מבקש אישור",
        "היי {{guest_name}},\n\n"
        "נשמח לקבל את אישור ההגעה שלכם לאירוע.\n\n"
        "אפשר לאשר כאן:\n{{rsvp_link}}",
    ),
    (
        "מבקש תשובה",
        "שלום {{guest_name}},\n\n"
        "נשמח לדעת אם אתם מצטרפים אלינו לאירוע.\n\n"
        "לאישור:\n{{rsvp_link}}",
    ),
    (
        "מארחים ומחכים",
        "היי {{guest_name}},\n\n"
        "נשמח לארח אתכם ומחכים לדעת אם תוכלו להגיע.\n\n"
        "אישור הגעה:\n{{rsvp_link}}",
    ),
]


def seed_message_default_options() -> None:
    """זורע פעם אחת את ספריית הנוסחים לבחירה (``MessageDefaultOption``,
    decisions.md 2026-08-06): הזוג בוחר וריאציה מתוך עד 12 לכל
    event_type×message_type, במקום נוסח קבוע יחיד. רץ רק אם הטבלה ריקה.

    נוסחים אמיתיים שהבעלים שלח (הומרו מ-``{טוקן}`` ל-``{{token}}``): 12 נוסחי
    הזמנה לחתונה, ו-12 נוסחי "בקשת אישור ראשונה" לכל סוג אירוע ב-
    ``_RSVP_REQUEST_OPTIONS_BY_TYPE``. שאר השלבים לחתונה מקבלים 12 שורות
    ריקות שמחכות לנוסחים; סוגי אירוע אחרים לא מקבלים שורות לשלבים שאין להם
    נוסח עדיין.
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

        # "בקשת אישור ראשונה" — נוסחים אמיתיים לפי סוג אירוע (כמו הזמנה).
        for et, opts in _RSVP_REQUEST_OPTIONS_BY_TYPE.items():
            rows += [
                models.MessageDefaultOption(
                    event_type=et,
                    message_type="rsvp_request",
                    option_number=i + 1,
                    tone=tone,
                    title=communication.MESSAGE_TYPE_LABELS["rsvp_request"],
                    content=content,
                    variables_supported=list(_RSVP_REQUEST_OPTION_VARS),
                )
                for i, (tone, content) in enumerate(opts)
            ]

        # שורות ריקות לשלבים שעדיין אין להם נוסחים — מבנה זהה, ממתין.
        remaining_types = [
            mt for mt in communication.MESSAGE_TYPES
            if mt not in ("invitation", "rsvp_request")
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


# ---- הפעלת RLS לטבלאות נוהל הדחייה ----
#
# **למה זה כאן ולא בהרצה ידנית כמו שאר קובצי ה-RLS.** קובצי 01–14 מריצים
# ידנית ובכוונה: הם נוגעים בכל טבלאות המערכת, והפעלתם היא אירוע תשתיתי
# (ראו rls/PRODUCTION_ROLLOUT.md). קובץ 15 שונה בשלושה דברים:
#
# 1. הוא נוגע **רק בשלוש טבלאות חדשות** ששייכות לפיצ'ר אחד. אם משהו בו
#    שגוי, מה שנשבר הוא נוהל הדחייה — לא ההתחברות, לא המוזמנים, לא ה-RSVP.
# 2. הטבלאות נולדות מ-``create_all`` בעליית השרת, כלומר **אחרי** שקובצי
#    ה-RLS הידניים כבר רצו. בלי צעד כאן, כל טבלה חדשה במערכת נולדת לנצח
#    בלי מדיניות — וזה בדיוק הפער שהתגלה.
# 3. הוא idempotent לחלוטין (DROP POLICY IF EXISTS + CREATE), ולכן הרצה
#    חוזרת בכל עלייה אינה משנה דבר אחרי הפעם הראשונה.
#
# **מה זה לא עושה:** לא נוגע בנתונים. אין בקובץ INSERT/UPDATE/DELETE/DROP
# TABLE — רק ALTER TABLE ... ENABLE RLS, CREATE POLICY ו-GRANT.
#
# **מתג כיבוי:** ``VEYA_SKIP_RLS_MIGRATIONS=1`` בסביבה. קיים כדי שאפשר
# יהיה לכבות מיד מ-Render, בלי deploy של קוד, אם מתגלה בעיה.
_RLS_MIGRATION_FILES = ("15_postponement_rls.sql",)

#: הפונקציות שקובץ 15 נשען עליהן (קבצים 01 ו-08). בלעדיהן ``CREATE POLICY``
#: ייכשל — ואז עדיף לדלג בקול מאשר להשאיר מדיניות חלקית.
_RLS_REQUIRED_FUNCTIONS = ("app_manages_event", "app_is_admin")


def _ensure_rls_policies() -> None:
    """מחיל את מדיניות ה-RLS של הטבלאות שנוצרות ב-``create_all``.

    שקט לגמרי ב-SQLite (אין שם RLS). לעולם לא מפיל את עליית השרת: כישלון
    נרשם ללוג ותו לא — שרת שעולה בלי מדיניות עדיף על שרת שלא עולה, והפער
    גלוי בלוג.
    """
    if not IS_POSTGRES:
        return
    if os.getenv("VEYA_SKIP_RLS_MIGRATIONS", "").strip() in ("1", "true", "yes"):
        print("[veya:rls] דילוג לפי VEYA_SKIP_RLS_MIGRATIONS", flush=True)
        return

    rls_dir = Path(__file__).resolve().parent.parent / "rls"
    try:
        with migrations_engine.begin() as conn:
            # תנאי מקדים: פונקציות העזר קיימות (כלומר קובצי 01/08 הורצו).
            missing = [
                fn for fn in _RLS_REQUIRED_FUNCTIONS
                if not conn.exec_driver_sql(
                    "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname = 'public' AND p.proname = %s",
                    (fn,),
                ).first()
            ]
            if missing:
                print(
                    "[veya:rls] דילוג — חסרות פונקציות עזר: "
                    f"{', '.join(missing)}. הריצו קודם את rls/01 ו-rls/08.",
                    flush=True,
                )
                return

            for name in _RLS_MIGRATION_FILES:
                path = rls_dir / name
                if not path.exists():
                    print(f"[veya:rls] קובץ חסר: {name}", flush=True)
                    continue
                # הקובץ כולו בטרנזקציה אחת — ALTER TABLE ו-CREATE POLICY
                # טרנזקציוניים ב-Postgres, ולכן זה הכול-או-כלום.
                # cursor גולמי ולא ``exec_driver_sql``: psycopg2 מפרש סימן
                # אחוז בטקסט כ-placeholder ומפיל קובץ SQL שמכיל אותו.
                # ``execute`` בלי פרמטרים כלל אינו עושה אינטרפולציה.
                cur = conn.connection.cursor()
                try:
                    cur.execute(path.read_text(encoding="utf-8"))
                finally:
                    cur.close()
                print(f"[veya:rls] הוחל: {name}", flush=True)

        # אימות עצמי — נרשם ללוג כדי שאפשר יהיה לראות ב-Render מה בפועל
        # קיים, בלי להתחבר ל-DB.
        with migrations_engine.connect() as conn:
            state = conn.exec_driver_sql(
                "SELECT c.relname, c.relrowsecurity, "
                "  (SELECT count(*) FROM pg_policies p "
                "     WHERE p.schemaname = 'public' AND p.tablename = c.relname) "
                "FROM pg_class c "
                "WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r' "
                "  AND c.relname IN "
                "      ('postponement_requests', 'event_cycles', 'guest_cycle_rsvp') "
                "ORDER BY 1"
            ).all()
            summary = " · ".join(
                f"{t}: rls={'on' if on else 'OFF'} policies={n}" for t, on, n in state
            ) or "לא נמצאו טבלאות"
            print(f"[veya:rls] מצב → {summary}", flush=True)
    except Exception as exc:  # noqa: BLE001 — לעולם לא מפיל את העלייה
        print(f"[veya:rls] נכשל (השרת ממשיך לעלות): {exc!r}", flush=True)


def _ensure_rsvp_request_message_default() -> None:
    """משלים את התשתית של ``rsvp_request`` ("בקשת אישור ראשונה") בפרודקשן —
    סוג הודעה שנולד אחרי שהקטלוג כבר נזרע, ולכן ``seed_message_defaults`` /
    ``seed_message_default_options`` (שרצים רק על טבלה ריקה) לא יצרו אותו:

    1. שורת ``MessageDefault`` לכל סוג אירוע. לסוגים שיש להם נוסחים ב-
       ``_RSVP_REQUEST_OPTIONS_BY_TYPE`` — עם נוסח ברירת המחדל (אפשרות 1),
       כי הבקשה נשלחת אוטומטית ואסור שתישאר ריקה בשקט; לשאר ``content=""``
       עד שיוזן נוסח.
    2. שורות ``MessageDefaultOption`` — ספריית הנוסחים לבחירה, לכל סוג
       אירוע שיש לו נוסחים.
    3. יישור כותרת ``final_reminder`` מ"תזכורת אחרונה" ל"תזכורת שלישית"
       (כותרת מערכת, לא של הזוג), כדי שכל המסכים ידברו באותה שפה.

    idempotent: משלים רק חסר, לעולם לא דורס נוסח קיים. רץ דרך
    ``MigrationSessionLocal`` (תפקיד מיוחס, עוקף RLS) כמו שאר תחזוקת העלייה.
    """
    from sqlalchemy import select, update

    from app import communication, event_terms

    db = MigrationSessionLocal()
    try:
        # (3) יישור כותרת "תזכורת אחרונה" -> "תזכורת שלישית" — מדויק: לא נוגע
        # בסוג הודעה אחר ולא בכותרת שכבר עודכנה.
        for model in (models.MessageDefault, models.EventMessage):
            db.execute(
                update(model)
                .where(model.message_type == "final_reminder")
                .where(model.title == "תזכורת אחרונה")
                .values(title="תזכורת שלישית")
            )
            db.commit()

        # (1) שורת MessageDefault לכל סוג אירוע. רשימה קנונית — לא "מה
        # שבמקרה קיים ב-MessageDefault", שיכול להיות חלקי בסביבות ישנות.
        seen = set(db.scalars(
            select(models.MessageDefault.event_type).distinct()
        ).all())
        event_types = sorted(set(event_terms.EVENT_TERMS.keys()) | seen)
        have = set(db.scalars(
            select(models.MessageDefault.event_type)
            .where(models.MessageDefault.message_type == "rsvp_request")
        ).all())
        default_content = {
            et: opts[0][1] for et, opts in _RSVP_REQUEST_OPTIONS_BY_TYPE.items()
        }
        created = 0
        for et in event_types:
            if et in have:
                continue
            db.add(models.MessageDefault(
                event_type=et,
                message_type="rsvp_request",
                title=communication.MESSAGE_TYPE_LABELS["rsvp_request"],
                content=default_content.get(et, ""),
                variables_supported=list(
                    communication.DEFAULT_VARIABLES_SUPPORTED.get("rsvp_request", [])
                ),
            ))
            created += 1

        opts_created = 0
        for et, opts in _RSVP_REQUEST_OPTIONS_BY_TYPE.items():
            content0 = opts[0][1]
            # ריפוי חד-פעמי: סוג אירוע שכבר קיבל שורת rsvp_request ריקה
            # (ברירת מחדל גלובלית או שורת EventMessage שהוקצתה לפני שהיה נוסח)
            # — נותנים לו את נוסח ברירת המחדל. "ריק -> ברירת מחדל" בטוח:
            # לעולם לא דורס נוסח אמיתי שהזוג/הבעלים בחר.
            db.execute(
                update(models.MessageDefault)
                .where(models.MessageDefault.event_type == et)
                .where(models.MessageDefault.message_type == "rsvp_request")
                .where(models.MessageDefault.content == "")
                .values(content=content0)
            )
            et_ids = select(models.Event.id).where(models.Event.event_type == et)
            db.execute(
                update(models.EventMessage)
                .where(models.EventMessage.message_type == "rsvp_request")
                .where(models.EventMessage.content == "")
                .where(models.EventMessage.event_id.in_(et_ids))
                .values(content=content0)
            )

            # שורות MessageDefaultOption — משלים רק מספרים חסרים.
            existing_nums = set(db.scalars(
                select(models.MessageDefaultOption.option_number)
                .where(models.MessageDefaultOption.event_type == et)
                .where(models.MessageDefaultOption.message_type == "rsvp_request")
            ).all())
            for i, (tone, content) in enumerate(opts):
                if (i + 1) in existing_nums:
                    continue
                db.add(models.MessageDefaultOption(
                    event_type=et,
                    message_type="rsvp_request",
                    option_number=i + 1,
                    tone=tone,
                    title=communication.MESSAGE_TYPE_LABELS["rsvp_request"],
                    content=content,
                    variables_supported=list(_RSVP_REQUEST_OPTION_VARS),
                ))
                opts_created += 1

        # תמיד commit — גם אם רק ה-UPDATE של הריפוי (ריק -> ברירת מחדל) שינה
        # שורות, בלי שנוצרו שורות חדשות.
        db.commit()
        if created or opts_created:
            print(
                f"[veya:seed] 'בקשת אישור ראשונה': {created} ברירות מחדל, "
                f"{opts_created} נוסחים לבחירה", flush=True,
            )
    except Exception as exc:  # noqa: BLE001 — לעולם לא מפיל את העלייה
        db.rollback()
        print(f"[veya:seed] השלמת 'בקשת אישור ראשונה' נכשלה: {exc!r}", flush=True)
    finally:
        db.close()


def _seed_postponement_options() -> None:
    """זורע את נוסחי הודעת הדחייה. לעולם לא מפיל את עליית השרת."""
    from app.postponement_messages import seed_postponement_options

    db = MigrationSessionLocal()
    try:
        created = seed_postponement_options(db)
        db.commit()
        if created:
            print(f"[veya:seed] נוצרו {created} נוסחי 'אירוע נדחה'", flush=True)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"[veya:seed] זריעת נוסחי הדחייה נכשלה: {exc!r}", flush=True)
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
    added_columns = _ensure_columns()
    # פעם אחת בלבד, ברגע שעמודת האימות נולדה: משתמשים קיימים מסומנים
    # כמאומתים כדי שלא ייחסמו רטרואקטיבית.
    _migrate_verify_existing_emails(added_columns)
    # מוסיף אינדקסים על מפתחות זרים (לביצועים) אם עדיין אין.
    _ensure_indexes()
    # אינדקסים ייחודיים (מונעים התאמת webhook כפולה/מדליפה) אם עדיין אין.
    _ensure_unique_indexes()
    # מוציא תמונות base64 ישנות מה-DB לקבצים (חד-פעמי, בטוח לחזרה).
    _migrate_images()
    # מחיל מדיניות RLS על טבלאות שנוצרו זה עתה ב-create_all (נוהל דחייה).
    # אחרי create_all ו-_ensure_columns בכוונה: המדיניות מתייחסת לטבלאות
    # שחייבות כבר להתקיים.
    _ensure_rls_policies()
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
    # משלים שורת "בקשת אישור ראשונה" (rsvp_request) לכל סוג אירוע — סוג הודעה
    # שנולד אחרי שהקטלוג נזרע בפרודקשן. משלים חסר בלבד, לא דורס.
    _ensure_rsvp_request_message_default()
    # נוסחי "אירוע נדחה". בנפרד מהזריעה שמעל, כי היא רצה רק על טבלה ריקה —
    # ובייצור הטבלה מלאה מזמן. הזריעה כאן משלימה חסר ולעולם לא דורסת.
    _seed_postponement_options()
    # הוסר (2026-08-24): קריאה ל-get_default_event שיצרה אירוע "ברירת מחדל"
    # בלי owner_id בכל פעם שטבלת האירועים הייתה ריקה. זה בדיוק המנגנון
    # שגרם לבאג 409 בייצור — auth.adopt_orphan_events (רץ בכל הרשמה חדשה)
    # "מאמצת" אוטומטית כל אירוע עם owner_id=NULL למי שנרשם הבא, כך שמשתמש
    # חדש לגמרי קיבל בעלות על אירוע-רפאים הזה בלי לדעת, ואז נחסם ב-409
    # ("כבר יש לך אירוע") בניסיון הראשון שלו ליצור אירוע אמיתי משלו. הפונקציה
    # get_default_event() לא משמשת יותר אף מקום אחר במערכת — ראו גם ההערה
    # המפורשת ב-routers/admin.py::_ORPHANED_EVENTS_HOLDER_EMAIL שמסבירה למה
    # אסור להשאיר אירועים עם owner_id=NULL בסביבה הזו.

    # DEBUG זמני: מדפיס בעליית השרת האם תצורת המייל קיימת (קיום בלבד,
    # לעולם לא ערך המפתח). זו הדרך לענות על "האם RESEND_API_KEY קיים
    # ב-Runtime של Render" בלי לחשוף אותו ובלי endpoint ציבורי.
    from app import emailer as _emailer

    print(f"[veya:startup] email config → {_emailer.config_summary()}", flush=True)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "veya-api"}
