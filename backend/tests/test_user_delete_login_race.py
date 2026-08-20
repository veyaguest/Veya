"""רגרסיה ל-race condition שני, אמיתי, שהתגלה בפרודקשן אחרי תיקון ה-race
של audit_logs (test_audit_log_race.py): DELETE FROM users נכשל עם
``psycopg2.errors.ForeignKeyViolation`` על ``login_events_user_id_fkey``.

התרחיש: ``_delete_user_impl`` מוחק את שורות ה-``login_events`` הקיימות של
המשתמש *ברגע מסוים* בתוך הטרנזקציה (SELECT ואז DELETE לכל שורה שנמצאה).
אם, **בטרנזקציה נפרדת לגמרי**, מישהו מתחבר לאותו חשבון (``POST /auth/login``,
שעושה ``commit()`` משלו) בדיוק אחרי אותו SELECT אבל לפני שהמחיקה של
``users`` עצמה הושלמה — נוצרת שורת login_events חדשה שהסשן של המחיקה
מעולם לא ראה. כשה-DELETE FROM users רץ, Postgres חוסם אותו כדין (FK) —
אבל זו חריגה לא-מטופלת שמפילה את כל בקשת המחיקה.

זו בדיוק אותה *מחלקת* בעיה כמו ה-race של audit_logs, אבל הפתרון שם
(``with_for_update()`` על שאילתת audit_logs עצמה) לא רלוונטי כאן: השורה
הבעייתית *לא קיימת עדיין* ברגע שהסשן שלנו סורק את login_events, ולכן אין
מה לנעול. הפתרון כאן שונה במהותו: נועלים (FOR UPDATE) את שורת ה-**הורה**
(users.id) עצמה בתחילת המחיקה. Postgres נועל אוטומטית (FOR KEY SHARE) כל
שורת הורה שמתווספת אליה שורת-בת עם FK — ולכן כל INSERT מקביל שמצביע על
user_id הזה (login_events, וגם כל טבלה אחרת עם FK ל-users.id) חוסם עד
שהטרנזקציה שלנו מסתיימת, במקום להיווצר "מתחת לרגליים".

דורש Postgres אמיתי (embedded, ``pip install pgserver``) מאותה סיבה כמו
test_audit_log_race.py — SQLite מתעלם בשקט מ-``with_for_update()`` ומ-FK
locking בכלל, כך שלא ניתן לבדוק נאמנה על SQLite. מדולג אוטומטית אם
``pgserver`` לא מותקן.
"""
import threading
import time

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

pgserver = pytest.importorskip("pgserver", reason="pip install pgserver כדי להריץ בדיקות race אמיתיות מול Postgres")

from app import models  # noqa: E402
from app.database import Base  # noqa: E402
from app.routers.admin import _delete_user_impl  # noqa: E402
from app.routers.auth import delete_my_account  # noqa: E402


class _FakeClient:
    host = "127.0.0.1"


class _FakeRequest:
    client = _FakeClient()


@pytest.fixture(scope="module")
def pg_engine():
    import tempfile

    pgdata = tempfile.mkdtemp()
    srv = pgserver.get_server(pgdata, cleanup_mode="delete")
    uri = srv.get_uri().replace("postgresql://", "postgresql+psycopg2://", 1)
    engine = create_engine(uri)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()
    srv.cleanup()


def _make_users(engine):
    setup = Session(engine, autoflush=False, expire_on_commit=False)
    admin = models.User(email=f"admin{time.time_ns()}@veya.test", password_hash="x", is_admin=True)
    target = models.User(email=f"target{time.time_ns()}@veya.test", password_hash="x")
    setup.add_all([admin, target])
    setup.commit()
    ids = {"admin": admin.id, "target": target.id}
    setup.close()
    return ids


def test_1_race_reproduces_without_lock(pg_engine):
    """מוכיח שה-FK violation קורה בפועל: מחיקה (בלי נעילת ה-users row) שרצה
    את לולאת ניקוי login_events, ואז — לפני ה-DELETE FROM users — טרנזקציה
    נפרדת ("התחברות" חדשה) מכניסה login_events טרי לאותו user ומצליחה
    לעשות commit. ה-DELETE FROM users צריך להיכשל עם ForeignKeyViolation."""
    ids = _make_users(pg_engine)
    deletion_scanned_login_events = threading.Event()
    login_committed = threading.Event()
    results = {}

    def deletion_without_lock():
        db = Session(pg_engine, autoflush=False, expire_on_commit=False)
        target = db.get(models.User, ids["target"])
        # משחזרים ידנית רק את השלב הרלוונטי (בלי הנעילה): לולאת ניקוי
        # login_events, ואז DELETE FROM users -- בדיוק כמו הקוד המקורי
        # (הלא-מתוקן) של _delete_user_impl.
        for lg in db.scalars(
            select(models.LoginEvent).where(models.LoginEvent.user_id == target.id)
        ).all():
            db.delete(lg)
        deletion_scanned_login_events.set()
        login_committed.wait(timeout=5)
        db.delete(target)
        try:
            db.commit()
            results["error"] = None
        except Exception as e:
            results["error"] = type(e).__name__
            results["error_text"] = str(e)
            db.rollback()

    def concurrent_login():
        deletion_scanned_login_events.wait(timeout=5)
        db = Session(pg_engine, autoflush=False, expire_on_commit=False)
        db.add(models.LoginEvent(user_id=ids["target"], ip="1.2.3.4", user_agent="test"))
        db.commit()
        login_committed.set()

    t1 = threading.Thread(target=deletion_without_lock)
    t2 = threading.Thread(target=concurrent_login)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert results["error"] == "IntegrityError", (
        f"הבאג לא שוחזר (קיבלנו {results.get('error')!r}) — אי אפשר לסמוך על הבדיקות הבאות"
    )
    assert "login_events" in results["error_text"]
    print("✓ 1: ה-FK violation שוחזר מול Postgres אמיתי (login_events)")


def test_2_locking_target_row_closes_the_race(pg_engine):
    """מוכיח את המנגנון: נעילת שורת ה-users (FOR UPDATE) גורמת ל-INSERT
    המקביל של login_events לחסום (Postgres: FOR KEY SHARE על ההורה) —
    ולכן הוא לא יכול "להתחמק" מלפני ה-DELETE."""
    ids = _make_users(pg_engine)
    row_locked = threading.Event()
    results = {}

    def deletion_with_lock():
        db = Session(pg_engine, autoflush=False, expire_on_commit=False)
        locked = db.execute(
            select(models.User).where(models.User.id == ids["target"]).with_for_update()
        ).scalar_one()
        row_locked.set()
        # מחזיקים את הנעילה קצת כדי לוודא שה-INSERT המקביל באמת חוסם.
        time.sleep(0.5)
        for lg in db.scalars(
            select(models.LoginEvent).where(models.LoginEvent.user_id == locked.id)
        ).all():
            db.delete(lg)
        db.delete(locked)
        try:
            db.commit()
            results["error"] = None
        except Exception as e:
            results["error"] = type(e).__name__
            db.rollback()

    def concurrent_login_attempt():
        row_locked.wait(timeout=5)
        db = Session(pg_engine, autoflush=False, expire_on_commit=False)
        start = time.time()
        db.add(models.LoginEvent(user_id=ids["target"], ip="1.2.3.4", user_agent="test"))
        try:
            db.commit()
            results["login_waited"] = time.time() - start
            results["login_error"] = None
        except Exception as e:
            # מקובל וצפוי: אם ה-login "התעורר" אחרי שהיוזר כבר נמחק, ה-INSERT
            # שלו עצמו נכשל (FK מהצד שלו) -- וזה בסדר גמור, בדיוק כמו שאמור
            # לקרות כשמנסים להתחבר לחשבון שכבר לא קיים.
            results["login_waited"] = time.time() - start
            results["login_error"] = type(e).__name__
            db.rollback()

    t1 = threading.Thread(target=deletion_with_lock)
    t2 = threading.Thread(target=concurrent_login_attempt)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert results["error"] is None, f"המחיקה נכשלה גם עם הנעילה: {results['error']}"
    assert results["login_waited"] >= 0.4, "ה-login המקביל לא חיכה בכלל -- הנעילה כנראה לא תפסה"
    print(
        f"✓ 2: נעילת שורת ה-users חסמה את ה-login המקביל ({results['login_waited']:.2f}s), "
        f"המחיקה הצליחה (login נכשל אח\"כ: {results['login_error']})"
    )


def test_3_admin_delete_user_survives_real_race(pg_engine):
    """התרחיש שנכשל בפרודקשן, דרך _delete_user_impl האמיתי (admin.py)."""
    ids = _make_users(pg_engine)
    deletion_locked = threading.Event()
    results = {}

    def admin_deletes_target():
        db = Session(pg_engine, autoflush=False, expire_on_commit=False)
        admin = db.get(models.User, ids["admin"])
        target = db.get(models.User, ids["target"])
        try:
            _delete_user_impl(db, admin, target, "user_and_events")
        finally:
            deletion_locked.set()  # השורה כבר ננעלה בתוך _delete_user_impl
        try:
            db.commit()
            results["error"] = None
        except Exception as e:
            results["error"] = type(e).__name__
            db.rollback()

    def concurrent_login_attempt():
        deletion_locked.wait(timeout=5)
        db = Session(pg_engine, autoflush=False, expire_on_commit=False)
        db.add(models.LoginEvent(user_id=ids["target"], ip="1.2.3.4", user_agent="test"))
        try:
            db.commit()
        except Exception:
            db.rollback()

    t1 = threading.Thread(target=admin_deletes_target)
    t2 = threading.Thread(target=concurrent_login_attempt)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert results["error"] is None, f"_delete_user_impl עדיין נכשל: {results['error']}"
    verify = Session(pg_engine, autoflush=False, expire_on_commit=False)
    assert verify.get(models.User, ids["target"]) is None
    verify.close()
    print("✓ 3: _delete_user_impl (admin.py) עומד במרוץ האמיתי מול login_events")


def test_4_delete_my_account_survives_real_race(pg_engine):
    """אותו תרחיש דרך delete_my_account (auth.py — מחיקה עצמית)."""
    ids = _make_users(pg_engine)
    deletion_locked = threading.Event()
    results = {}

    def target_deletes_own_account():
        db = Session(pg_engine, autoflush=False, expire_on_commit=False)
        target = db.get(models.User, ids["target"])
        try:
            delete_my_account(_FakeRequest(), db=db, user=target)
            results["error"] = None
        except Exception as e:
            results["error"] = type(e).__name__
            db.rollback()
        finally:
            deletion_locked.set()

    def concurrent_login_attempt():
        # לא ניתן לתזמן במדויק את רגע הנעילה מבפנים (delete_my_account לא
        # חושף hook) -- ממתינים קצר קבוע לפני הניסיון, מספיק כדי לרוץ לפני
        # שה-commit הסופי נסגר על מכונה מקומית מהירה.
        time.sleep(0.05)
        db = Session(pg_engine, autoflush=False, expire_on_commit=False)
        db.add(models.LoginEvent(user_id=ids["target"], ip="1.2.3.4", user_agent="test"))
        try:
            db.commit()
        except Exception:
            db.rollback()

    t1 = threading.Thread(target=target_deletes_own_account)
    t2 = threading.Thread(target=concurrent_login_attempt)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert results["error"] is None, f"delete_my_account עדיין נכשל: {results['error']}"
    verify = Session(pg_engine, autoflush=False, expire_on_commit=False)
    assert verify.get(models.User, ids["target"]) is None
    verify.close()
    print("✓ 4: delete_my_account (auth.py) עומד במרוץ האמיתי מול login_events")


if __name__ == "__main__":
    import tempfile as _tempfile

    _pgdata = _tempfile.mkdtemp()
    _srv = pgserver.get_server(_pgdata, cleanup_mode="delete")
    _uri = _srv.get_uri().replace("postgresql://", "postgresql+psycopg2://", 1)
    _engine = create_engine(_uri)
    Base.metadata.create_all(bind=_engine)

    test_1_race_reproduces_without_lock(_engine)
    test_2_locking_target_row_closes_the_race(_engine)
    test_3_admin_delete_user_survives_real_race(_engine)
    test_4_delete_my_account_survives_real_race(_engine)

    _engine.dispose()
    _srv.cleanup()
    print()
    print("=== כל 4 בדיקות ה-race (login_events) עברו מול Postgres אמיתי ===")
