"""חיבור למסד הנתונים (SQLAlchemy).

כברירת מחדל עובדים עם SQLite (קובץ בודד, בלי שרת). מעבר ל-PostgreSQL
בהמשך = שינוי משתנה DATABASE_URL בלבד, בלי לגעת בקוד.
"""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./veya.db")

# check_same_thread נדרש רק ל-SQLite כדי לאפשר גישה מכמה בקשות.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

# SQLite לא אוכף מפתחות זרים (FK) כברירת מחדל — צריך להפעיל זאת לכל חיבור.
# בלי זה אפשר להישאר עם רשומות "יתומות" שמצביעות על אירוע/מוזמן שנמחק.
if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_conn, _connection_record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """בסיס לכל מודלי הטבלאות (יתווספו בשלב 2)."""


def get_db():
    """מספק חיבור DB לכל בקשה, וסוגר אותו בסיום."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
