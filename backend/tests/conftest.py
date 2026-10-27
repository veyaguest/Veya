"""הגדרות משותפות לבדיקות, לפני כל טעינה של ``app``:

- שעון קבוע (``tests/fixed_clock.py``).
- WhatsApp במצב ``mock`` ובלי טוקן אמיתי, גם אם ``backend/.env`` מוגדר אחרת
  (``tests/safe_env.py``).
- מסד נתונים זמני לכל ההרצה — **אף פעם לא** ה-DB שב-``backend/.env``.
"""
import atexit
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# מסד זמני לכל ההרצה. בלי זה, אם מודול כלשהו טוען את ``app`` לפני ש-
# ``e2e_seating.make_client`` מציב DB זמני, המנוע נקשר ל-DATABASE_URL שב-.env
# (``backend/veya.db`` — מסד הפיתוח המקומי) וכל הבדיקות כותבות אליו
# (התגלה 2026-10-27: אלפי אולמות בדיקה נשארו במסד הפיתוח). load_dotenv לא דורס
# משתנה שכבר קיים, אז ההצבה כאן מנצחת. תהליכי-משנה שמגדירים DATABASE_URL
# בעצמם (בדיקות Postgres) לא מושפעים.
_TEST_DB = tempfile.NamedTemporaryFile(prefix="veya-tests-", suffix=".db", delete=False)
_TEST_DB.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.name}"
os.environ.pop("MIGRATIONS_DATABASE_URL", None)


def _drop_test_db() -> None:
    try:
        os.unlink(_TEST_DB.name)
    except OSError:
        pass


atexit.register(_drop_test_db)

from tests import safe_env  # noqa: E402

safe_env.apply()

from tests import fixed_clock  # noqa: E402

fixed_clock.install()


def pytest_sessionstart(session) -> None:  # noqa: ARG001
    """המסד הזמני מתחיל עם משתמש-בעלים אחד, כמו כל מסד אמיתי.

    במערכת, המשתמש הראשון שנרשם הופך לאדמין (``routers/auth.py``). בדיקות
    רבות נרשמות כ"זוג רגיל" ומניחות שהוא *לא* אדמין — הנחה שהתקיימה רק כי
    הבדיקות רצו בפועל מול מסד הפיתוח, שכבר היו בו משתמשים. הבעלים הזה שומר על
    אותו מצב, בלי לגעת במסד הפיתוח.
    """
    from app import auth, models
    from app.database import Base, MigrationSessionLocal, migrations_engine

    Base.metadata.create_all(bind=migrations_engine)
    db = MigrationSessionLocal()
    try:
        if not db.query(models.User).first():
            db.add(models.User(email="seed-owner@veya.test", password_hash=auth.hash_password("Seed-Owner-1!"),
                               display_name="בעלים (בדיקות)", is_admin=True, admin_role="super_admin"))
            db.commit()
    finally:
        db.close()
