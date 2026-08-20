"""רגרסיה ל-race condition אמיתי בין שתי טרנזקציות נפרדות שגורם ל-
StaleDataError על UPDATE של audit_logs (שוחזר ותועד בייצור, 2026-08-20).

התרחיש: משתמש A ("target") שיתף פעולה על אירוע בבעלות משתמש B ("owner") —
למשל ערך את פרטי האירוע כ-co-manager. זה יוצר שורת ``audit_logs`` עם
``event_id`` = האירוע של B ו-``user_id`` = A. אם, **בו-זמנית**:
  - אדמין מוחק את A (מצב "משתמש + כל האירועים") — לולאת הניקוי ב-
    ``_delete_user_impl`` טוענת את השורה (לפי ``user_id``) ומנסה לאפס
    ``user_id = None``.
  - B מוחק את האירוע שלו (``delete_event_cascade``, בטרנזקציה נפרדת
    לגמרי, בלתי-קשורה למחיקת A) — זה מוחק את אותה שורה בדיוק (לפי
    ``event_id``).
אם B מצליח לעשות commit בין הרגע שהאדמין טען את השורה לרגע שהוא מנסה
לעדכן אותה — ה-UPDATE רץ נגד שורה שכבר לא קיימת. SQLAlchemy דורש התאמת
rowcount ל-UPDATE/DELETE-לפי-מפתח, ולכן זורק ``StaleDataError`` (הופך
ל-``PendingRollbackError`` בשימוש הבא ב-session) — בלתי-מטופל, מפיל את
כל בקשת המחיקה.

התיקון: ``.with_for_update()`` על שאילתת ה-AuditLog לפני העדכון (גם
ב-``_delete_user_impl`` ב-admin.py וגם ב-``delete_my_account`` ב-auth.py).
זו נעילת שורה אמיתית ברמת ה-DB — לא ניתנת לבדיקה נאמנה על SQLite (שאין לו
נעילות ברמת שורה; ``with_for_update()`` שם no-op שקט). הבדיקות כאן משתמשות
ב-Postgres אמיתי (embedded, דרך חבילת ``pgserver`` — לא Docker, לא שירות
חיצוני) עם שני threads אמיתיים ו-synchronization מדויק, כדי לשחזר את
המרוץ בפועל ולוודא שהנעילה באמת סוגרת אותו.

דורש: ``pip install pgserver`` (כלי בדיקה בלבד — לא נוסף ל-requirements.txt
הראשי כדי לא להכביד על פריסת הייצור). אם לא מותקן, כל הבדיקות כאן מדולגות
אוטומטית (לא נכשלות) כדי לא לשבור סביבות שלא התקינו את זה.
"""
import threading
import time

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

pgserver = pytest.importorskip("pgserver", reason="pip install pgserver כדי להריץ בדיקות race אמיתיות מול Postgres")

from app import models  # noqa: E402
from app.account import delete_event_cascade  # noqa: E402
from app.database import Base  # noqa: E402
from app.ratelimit import client_ip  # noqa: E402
from app.routers.admin import _delete_user_impl  # noqa: E402
from app.routers.auth import delete_my_account  # noqa: E402


class _FakeClient:
    host = "127.0.0.1"


class _FakeRequest:
    """מחליף מינימלי ל-``fastapi.Request`` — כל מה ש-``delete_my_account``
    בפועל צריך ממנו הוא ``request.client.host`` (דרך ``client_ip``)."""

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


def _make_race_scenario(engine):
    """יוצר: owner + אירוע בבעלותו, target + שורת audit_logs עם event_id של
    אירוע owner ו-user_id של target (בדיוק תבנית "target שיתף פעולה על
    אירוע של מישהו אחר" מהתקרית האמיתית). מחזיר dict של מזהים."""
    setup = Session(engine, autoflush=False, expire_on_commit=False)
    admin = models.User(email=f"admin{time.time_ns()}@veya.test", password_hash="x", is_admin=True)
    owner = models.User(email=f"owner{time.time_ns()}@veya.test", password_hash="x")
    target = models.User(email=f"target{time.time_ns()}@veya.test", password_hash="x")
    setup.add_all([admin, owner, target])
    setup.commit()
    ev = models.Event(owner_id=owner.id, groom_name="a", bride_name="b", event_type="wedding")
    setup.add(ev)
    setup.commit()
    al = models.AuditLog(
        event_id=ev.id, user_id=target.id, action="update_event",
        detail="target ערך אירוע בבעלות owner",
    )
    setup.add(al)
    setup.commit()
    ids = {"admin": admin.id, "owner": owner.id, "target": target.id, "event": ev.id}
    setup.close()
    return ids


def test_1_race_reproduces_without_lock(pg_engine):
    """מוכיח שהבאג המקורי (בלי with_for_update) קורה בפועל מול Postgres
    אמיתי, עם שני threads אמיתיים — לא רק state-mismatch תיאורטי."""
    ids = _make_race_scenario(pg_engine)
    b_selected = threading.Event()
    a_committed = threading.Event()
    results = {}

    def owner_deletes_their_event():
        db = Session(pg_engine, autoflush=False, expire_on_commit=False)
        delete_event_cascade(db, db.get(models.Event, ids["event"]))
        b_selected.wait(timeout=5)
        db.commit()
        a_committed.set()

    def admin_nulls_audit_user_id_no_lock():
        db = Session(pg_engine, autoflush=False, expire_on_commit=False)
        stmt = select(models.AuditLog).where(models.AuditLog.user_id == ids["target"])
        for al in db.scalars(stmt).all():
            al.user_id = None
        b_selected.set()
        a_committed.wait(timeout=5)
        try:
            db.commit()
            results["error"] = None
        except Exception as e:
            results["error"] = type(e).__name__
            db.rollback()

    t1 = threading.Thread(target=owner_deletes_their_event)
    t2 = threading.Thread(target=admin_nulls_audit_user_id_no_lock)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert results["error"] == "StaleDataError", (
        f"הבאג לא שוחזר (קיבלנו {results['error']!r}) — אי אפשר לסמוך על "
        "הבדיקות הבאות בלי לוודא קודם שהתרחיש באמת קורה"
    )
    print("✓ 1: הבאג המקורי שוחזר מול Postgres אמיתי (StaleDataError)")


def test_2_for_update_closes_the_race(pg_engine):
    """מוכיח את המנגנון עצמו: עם with_for_update(), הצד שמעדכן נועל את
    השורה; הצד שמוחק (מקביל, בלתי-קשור) חייב לחכות לו — לא מתנגש."""
    ids = _make_race_scenario(pg_engine)
    b_locked = threading.Event()
    results = {}

    def owner_deletes_their_event():
        db = Session(pg_engine, autoflush=False, expire_on_commit=False)
        delete_event_cascade(db, db.get(models.Event, ids["event"]))
        b_locked.wait(timeout=5)
        start = time.time()
        db.commit()
        results["wait_seconds"] = time.time() - start

    def admin_nulls_audit_user_id_with_lock():
        db = Session(pg_engine, autoflush=False, expire_on_commit=False)
        stmt = (
            select(models.AuditLog)
            .where(models.AuditLog.user_id == ids["target"])
            .with_for_update()
        )
        for al in db.scalars(stmt).all():
            al.user_id = None
        b_locked.set()
        time.sleep(0.5)  # מחזיקים את הנעילה כדי לוודא ש-A באמת חוסם, לא רק "מזדמן"
        try:
            db.commit()
            results["error"] = None
        except Exception as e:
            results["error"] = type(e).__name__
            db.rollback()

    t1 = threading.Thread(target=owner_deletes_their_event)
    t2 = threading.Thread(target=admin_nulls_audit_user_id_with_lock)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert results["wait_seconds"] >= 0.4, "A לא חיכתה בכלל — FOR UPDATE כנראה לא נעל שורה"
    assert results["error"] is None, f"עדיין נכשל למרות FOR UPDATE: {results['error']}"
    print(f"✓ 2: FOR UPDATE נועל בפועל (A חיכתה {results['wait_seconds']:.2f}s), אין StaleDataError")


def test_3_admin_delete_user_survives_real_race(pg_engine):
    """התרחיש שנכשל בפרודקשן, דרך _delete_user_impl האמיתי (admin.py) —
    לא שחזור מבודד של המנגנון, אלא הפונקציה עצמה מה-repo."""
    ids = _make_race_scenario(pg_engine)
    b_locked = threading.Event()
    results = {}

    def owner_deletes_their_event():
        db = Session(pg_engine, autoflush=False, expire_on_commit=False)
        delete_event_cascade(db, db.get(models.Event, ids["event"]))
        b_locked.wait(timeout=5)
        db.commit()

    def admin_deletes_target():
        db = Session(pg_engine, autoflush=False, expire_on_commit=False)
        admin = db.get(models.User, ids["admin"])
        target = db.get(models.User, ids["target"])
        _delete_user_impl(db, admin, target, "user_and_events")
        b_locked.set()
        time.sleep(0.3)
        try:
            db.commit()
            results["error"] = None
        except Exception as e:
            results["error"] = type(e).__name__
            db.rollback()

    t1 = threading.Thread(target=owner_deletes_their_event)
    t2 = threading.Thread(target=admin_deletes_target)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert results["error"] is None, f"_delete_user_impl עדיין נכשל מול race אמיתי: {results['error']}"
    verify = Session(pg_engine, autoflush=False, expire_on_commit=False)
    assert verify.get(models.User, ids["target"]) is None
    verify.close()
    print("✓ 3: _delete_user_impl (admin.py) עומד במרוץ האמיתי מול Postgres")


def test_4_delete_my_account_survives_real_race(pg_engine):
    """אותו תרחיש בדיוק, דרך delete_my_account האמיתי (auth.py — מחיקה
    עצמית) — אותה תבנית פגיעות בדיוק, אותו תיקון (with_for_update)."""
    ids = _make_race_scenario(pg_engine)
    b_locked = threading.Event()
    results = {}

    def owner_deletes_their_event():
        db = Session(pg_engine, autoflush=False, expire_on_commit=False)
        delete_event_cascade(db, db.get(models.Event, ids["event"]))
        b_locked.wait(timeout=5)
        db.commit()

    def target_deletes_own_account():
        db = Session(pg_engine, autoflush=False, expire_on_commit=False)
        target = db.get(models.User, ids["target"])
        try:
            delete_my_account(_FakeRequest(), db=db, user=target)
            b_locked.set()
            results["error"] = None
        except Exception as e:
            b_locked.set()
            results["error"] = type(e).__name__
            db.rollback()

    t1 = threading.Thread(target=owner_deletes_their_event)
    t2 = threading.Thread(target=target_deletes_own_account)
    t2.start()
    # מוודאים ש-t2 כבר נעל את השורה (with_for_update) לפני ש-t1 מתחילה
    # לנסות למחוק אותה — אחרת אין race אמיתי לבדוק.
    time.sleep(0.1)
    t1.start()
    t1.join(); t2.join()

    assert results["error"] is None, f"delete_my_account עדיין נכשל מול race אמיתי: {results['error']}"
    verify = Session(pg_engine, autoflush=False, expire_on_commit=False)
    assert verify.get(models.User, ids["target"]) is None
    verify.close()
    print("✓ 4: delete_my_account (auth.py) עומד במרוץ האמיתי מול Postgres")


if __name__ == "__main__":
    import tempfile as _tempfile

    _pgdata = _tempfile.mkdtemp()
    _srv = pgserver.get_server(_pgdata, cleanup_mode="delete")
    _uri = _srv.get_uri().replace("postgresql://", "postgresql+psycopg2://", 1)
    _engine = create_engine(_uri)
    Base.metadata.create_all(bind=_engine)

    test_1_race_reproduces_without_lock(_engine)
    test_2_for_update_closes_the_race(_engine)
    test_3_admin_delete_user_survives_real_race(_engine)
    test_4_delete_my_account_survives_real_race(_engine)

    _engine.dispose()
    _srv.cleanup()
    print()
    print("=== כל 4 בדיקות ה-race עברו מול Postgres אמיתי ===")
