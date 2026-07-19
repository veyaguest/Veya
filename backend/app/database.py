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


def set_request_identity(user_id) -> None:
    """קובע את זהות המשתמש של הבקשה הנוכחית (נקרא מ-auth אחרי אימות הטוקן)."""
    current_user_id.set(user_id)


def clear_request_identity() -> None:
    """מאפס את הזהות בסיום הבקשה (הגנה נוספת מפני דליפה בין בקשות)."""
    current_user_id.set(None)

# SQLite לא אוכף מפתחות זרים (FK) כברירת מחדל — צריך להפעיל זאת לכל חיבור.
# בלי זה אפשר להישאר עם רשומות "יתומות" שמצביעות על אירוע/מוזמן שנמחק.
if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_conn, _connection_record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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
