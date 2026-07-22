"""חיבור למסד הנתונים (SQLAlchemy).

כברירת מחדל עובדים עם SQLite (קובץ בודד, בלי שרת). מעבר ל-PostgreSQL
בהמשך = שינוי משתנה DATABASE_URL בלבד, בלי לגעת בקוד.
"""
import contextvars
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./veya.db")

# האם אנחנו על PostgreSQL (ייצור) — רק שם קיים RLS. ב-SQLite (פיתוח) כל
# מנגנוני ה-RLS הם no-op, כדי שהסביבה המקומית תמשיך לעבוד בדיוק כמו קודם.
IS_POSTGRES = DATABASE_URL.startswith("postgres")

# check_same_thread נדרש רק ל-SQLite כדי לאפשר גישה מכמה בקשות.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

# ── זהות המשתמש לכל בקשה (עבור RLS ב-PostgreSQL) ─────────────────────────
# ContextVar מחזיק את מזהה המשתמש המאומת של הבקשה הנוכחית. הוא מבודד לכל
# בקשה (async task) אוטומטית. מזה נגזר משתנה ה-session ``app.current_user_id``
# שמדיניות ה-RLS ב-Postgres קוראת. ב-SQLite הערך הזה פשוט לא בשימוש.
current_user_id: contextvars.ContextVar = contextvars.ContextVar(
    "veya_current_user_id", default=None
)

# טוקן המוזמן של הבקשה הנוכחית (עבור נתיב ציבורי /confirm/{token}). מדיניות
# ה-RLS על guests/events/messages קוראת את זה דרך app_current_guest_token()
# כדי לזהות מוזמן אנונימי בלי התחברות. ContextVar נפרד מ-current_user_id כי
# שני הזיהויים יכולים להיות רלוונטיים בו-זמנית (אף שבפועל היום לא קורה יחד).
current_guest_token: contextvars.ContextVar = contextvars.ContextVar(
    "veya_current_guest_token", default=None
)


def set_request_identity(user_id) -> None:
    """קובע את זהות המשתמש של הבקשה הנוכחית (נקרא מ-auth אחרי אימות הטוקן)."""
    current_user_id.set(user_id)


def clear_request_identity() -> None:
    """מאפס את הזהות בסיום הבקשה (הגנה נוספת מפני דליפה בין בקשות)."""
    current_user_id.set(None)


def set_guest_token(token: str) -> None:
    """קובע את טוקן המוזמן של הבקשה הנוכחית (נקרא מ-confirm.py לפני כל שאילתה).

    הטוקן כבר מגיע מהמשתמש עצמו בכתובת ה-URL (``/confirm/{token}``) — אין כאן
    חשיפת מידע חדש, רק "מראים" אותו ל-Postgres כדי שמדיניות ה-RLS תוכל לוודא
    שהשורה שמוחזרת אכן שייכת לאותו טוקן בדיוק.
    """
    current_guest_token.set(token)


def clear_guest_token() -> None:
    """מאפס את טוקן המוזמן בסיום הבקשה (הגנה נוספת מפני דליפה בין בקשות)."""
    current_guest_token.set(None)

# SQLite לא אוכף מפתחות זרים (FK) כברירת מחדל — צריך להפעיל זאת לכל חיבור.
# בלי זה אפשר להישאר עם רשומות "יתומות" שמצביעות על אירוע/מוזמן שנמחק.
if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_conn, _connection_record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# expire_on_commit=False: קריטי עבור RLS, לא רק אופטימיזציה. התגלה בבדיקת
# Staging אמיתית מול Postgres: כברירת מחדל (expire_on_commit=True) SQLAlchemy
# "מפקיע" את כל השדות של אובייקט אחרי commit(), כך שגישה לשדה כלשהו (או
# db.refresh() מפורש) אחרי commit מפעילה שאילתת SELECT נוספת בטרנזקציה חדשה.
# גילינו (ריפרודוקציה עם הדפסות אבחון) שבטרנזקציה הנוספת הזו, בתנאים
# מסוימים סביב הריצה בת'רד-פול של FastAPI/anyio, ה-ContextVar של זהות
# המשתמש (current_user_id) יכול להיקרא כ-None למרות שהוגדר נכון קודם באותה
# בקשה ממש — מה שגורם למדיניות ה-SELECT (RLS) לדחות את השאילתה ולזרוק
# שגיאה כאילו השורה "נמחקה". כש-expire_on_commit=False, האובייקט שומר את
# הערכים שכבר קיבל מ-INSERT/UPDATE...RETURNING בזיכרון, ואין צורך בשאילתת
# רענון נוספת אחרי ה-commit בכלל — כל ה-db.refresh() המיותרים הוסרו מהקוד.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, expire_on_commit=False)

# ── חיבור נפרד למיגרציות/תחזוקת עלייה (DDL + זריעה) ───────────────────────
# מתי צריך את זה: ברגע ש-DATABASE_URL יוחלף לתפקיד ה-RLS המוגבל (veya_app —
# ראו backend/rls/01_helpers_and_grants.sql), שתי בעיות עולות בבת אחת:
#   1. ``_ensure_columns``/``_ensure_indexes`` ב-main.py מריצים DDL
#      (ALTER TABLE / CREATE INDEX) — מותר רק לבעל הטבלה (postgres), לא
#      ל-veya_app, גם אם יש לו GRANT על SELECT/INSERT/UPDATE/DELETE.
#   2. פעולות תחזוקה בעלייה (``_ensure_admin``, ``_ensure_guest_tokens``,
#      ``_migrate_images``, ``seed_veya_defaults``) רצות *לפני* שיש בקשת
#      HTTP כלשהי — אין "משתמש מחובר" שאפשר להזריק כזהות, אז מדיניות ה-RLS
#      (שתלויה ב-``app_current_user_id()``) הייתה חוסמת אותן.
# הפתרון: MIGRATIONS_DATABASE_URL — חיבור נפרד (ברירת מחדל: אותו ערך כמו
# DATABASE_URL, כך שהיום, לפני שמחליפים תפקיד, אין שום שינוי התנהגות).
# בפרודקשן, כשעוברים בפועל ל-veya_app עבור DATABASE_URL, יש להגדיר את
# MIGRATIONS_DATABASE_URL לחיבור postgres (superuser/בעל הטבלאות) בנפרד —
# ראו checklist ההפעלה. שני החיבורים יכולים להצביע על אותו DB, רק בתפקידים
# שונים.
MIGRATIONS_DATABASE_URL = os.getenv("MIGRATIONS_DATABASE_URL", DATABASE_URL)
if MIGRATIONS_DATABASE_URL == DATABASE_URL:
    migrations_engine = engine
else:
    _migrations_connect_args = (
        {"check_same_thread": False} if MIGRATIONS_DATABASE_URL.startswith("sqlite") else {}
    )
    migrations_engine = create_engine(
        MIGRATIONS_DATABASE_URL, connect_args=_migrations_connect_args
    )

MigrationSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=migrations_engine, expire_on_commit=False
)

# ב-PostgreSQL: בכל תחילת טרנזקציה מזריקים את מזהה המשתמש הנוכחי כמשתנה
# session בשם ``app.current_user_id``. מדיניות ה-RLS משתמשת בו כדי לסנן שורות.
# משתמשים ב-set_config(..., is_local=true) כדי שהערך יהיה מוגבל לטרנזקציה
# ולא ידלוף בין חיבורים ב-pool. כי זה רץ בכל begin, הערך נשמר גם אחרי commit
# (טרנזקציה חדשה → begin חדש → הזרקה מחדש מתוך אותו ContextVar).
if IS_POSTGRES:

    @event.listens_for(SessionLocal, "after_begin")
    def _apply_rls_identity(session, transaction, connection):  # noqa: ANN001
        uid = current_user_id.get()
        connection.exec_driver_sql(
            "SELECT set_config('app.current_user_id', %s, true)",
            (str(uid) if uid is not None else "",),
        )
        token = current_guest_token.get()
        connection.exec_driver_sql(
            "SELECT set_config('app.guest_token', %s, true)",
            (token if token is not None else "",),
        )


class Base(DeclarativeBase):
    """בסיס לכל מודלי הטבלאות (יתווספו בשלב 2)."""


def get_db():
    """מספק חיבור DB לכל בקשה, וסוגר אותו בסיום."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        clear_request_identity()
        clear_guest_token()
