"""חיבור למסד הנתונים (SQLAlchemy).

כברירת מחדל עובדים עם SQLite (קובץ בודד, בלי שרת). מעבר ל-PostgreSQL
בהמשך = שינוי משתנה DATABASE_URL בלבד, בלי לגעת בקוד.
"""
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./veya.db")

# check_same_thread נדרש רק ל-SQLite כדי לאפשר גישה מכמה בקשות.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
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
