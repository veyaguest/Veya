"""בדיקות למחיקת אירוע בודד ע"י אדמין (app/routers/admin.py::delete_single_event).

הפיצ'ר: כפתור "מחיקת אירוע" בכרטיס המשתמש בפאנל האדמין — מוחק אירוע ספציפי
בלי למחוק את המשתמש/החשבון שלו. הראוט עצמו לא מיישם שום לוגיקת מחיקה חדשה —
הוא רק עוטף את ``delete_event_cascade`` הקיים (כבר מכוסה ב-14 תרחישים ב-
tests/test_account_delete.py) בבדיקת admin + 404 + audit.record. הבדיקות כאן
מתמקדות בדיוק במה שחדש: 404 לאירוע לא קיים, שהמשתמש/הבעלים לא נפגע, ש-audit
log נכתב נכון, ושמחיקת אירוע אחד לא נוגעת באירוע אחר של אותו בעלים — הכול
דרך פונקציית ה-router עצמה (לא רק דרך delete_event_cascade ישירות), כדי
לתפוס רגרסיה אם מישהו יוסיף לוגיקה לראוט ולא רק יקרא לפונקציה הקיימת.

הרצה: ``venv/bin/python tests/test_admin_delete_event.py`` (עצמאי, בלי pytest).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, event, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402
from app.database import Base  # noqa: E402
from app.routers.admin import delete_single_event  # noqa: E402
from fastapi import HTTPException  # noqa: E402


class _FakeClient:
    host = "127.0.0.1"


class _FakeRequest:
    """מחליף מינימלי ל-``fastapi.Request`` — כל מה שהראוט בפועל צריך ממנו
    הוא ``request.client.host`` (ל-audit.record)."""

    client = _FakeClient()


def _fresh_session() -> Session:
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _make_user(db: Session, email: str, is_admin: bool = False) -> models.User:
    u = models.User(email=email, password_hash="x", display_name="בדיקה", is_admin=is_admin)
    db.add(u)
    db.commit()
    return u


def _make_event(db: Session, owner_id: int) -> models.Event:
    ev = models.Event(owner_id=owner_id, groom_name="יואב", bride_name="דנה", event_type="wedding")
    db.add(ev)
    db.commit()
    return ev


def _make_guest(db: Session, event_id: int, phone: str = "0501234567") -> models.Guest:
    g = models.Guest(event_id=event_id, full_name="מוזמן", phone=phone, side="groom")
    db.add(g)
    db.commit()
    return g


def test_1_admin_deletes_event_owner_account_untouched() -> None:
    """אדמין מוחק אירוע של מישהו אחר — האירוע והמוזמנים נעלמים, אבל חשבון
    הבעלים עצמו נשאר לגמרי בשלמותו (בניגוד למחיקת משתמש)."""
    db = _fresh_session()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    owner = _make_user(db, "couple@veya.test")
    ev = _make_event(db, owner.id)
    g = _make_guest(db, ev.id)
    ev_id = ev.id

    delete_single_event(ev_id, _FakeRequest(), db=db, admin=admin)

    assert db.get(models.Event, ev_id) is None
    assert db.get(models.Guest, g.id) is None
    kept_owner = db.get(models.User, owner.id)
    assert kept_owner is not None
    assert kept_owner.disabled is False
    print("✓ 1: אדמין מחק אירוע של משתמש אחר — האירוע נעלם, חשבון הבעלים נשאר שלם")


def test_2_missing_event_returns_404_not_crash() -> None:
    db = _fresh_session()
    admin = _make_user(db, "admin@veya.test", is_admin=True)

    try:
        delete_single_event(999999, _FakeRequest(), db=db, admin=admin)
        assert False, "היה אמור לזרוק 404"
    except HTTPException as exc:
        assert exc.status_code == 404
    print("✓ 2: מחיקת אירוע שלא קיים מחזירה 404 מסודר, לא קורסת")


def test_3_deleting_one_event_does_not_touch_sibling_event() -> None:
    db = _fresh_session()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    owner = _make_user(db, "couple@veya.test")
    ev1 = _make_event(db, owner.id)
    ev2 = _make_event(db, owner.id)
    g1 = _make_guest(db, ev1.id, phone="0540000001")
    g2 = _make_guest(db, ev2.id, phone="0540000002")

    delete_single_event(ev1.id, _FakeRequest(), db=db, admin=admin)

    assert db.get(models.Event, ev1.id) is None
    assert db.get(models.Guest, g1.id) is None
    assert db.get(models.Event, ev2.id) is not None
    assert db.get(models.Guest, g2.id) is not None
    print("✓ 3: מחיקת אירוע אחד לא נוגעת באירוע אחר של אותו בעלים")


def test_4_audit_log_recorded_with_correct_action() -> None:
    db = _fresh_session()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    owner = _make_user(db, "couple@veya.test")
    ev = _make_event(db, owner.id)
    ev_id = ev.id

    delete_single_event(ev_id, _FakeRequest(), db=db, admin=admin)

    logs = db.scalars(
        select(models.AuditLog).where(models.AuditLog.action == "admin_delete_event")
    ).all()
    assert len(logs) == 1
    assert logs[0].user_id == admin.id
    assert f"#{ev_id}" in logs[0].detail
    print("✓ 4: נרשמה שורת audit_logs אחת עם הפעולה הנכונה ומזהה האירוע")


def test_5_dependent_call_center_rows_are_cleaned_up() -> None:
    """delete_event_cascade כבר מנקה call_logs/call_assignments (לא מכוסה
    ב-test_account_delete.py::_assert_event_fully_gone) — מוודאים שזה קורה
    גם דרך הראוט של האדמין, לא רק כשקוראים לפונקציה ישירות."""
    db = _fresh_session()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    owner = _make_user(db, "couple@veya.test")
    ev = _make_event(db, owner.id)
    g = _make_guest(db, ev.id)
    db.add(models.CallLog(event_id=ev.id, guest_id=g.id, outcome="confirmed", created_by_id=admin.id))
    db.add(models.CallAssignment(event_id=ev.id, user_id=admin.id, assigned_by_id=admin.id))
    db.commit()
    ev_id = ev.id

    delete_single_event(ev_id, _FakeRequest(), db=db, admin=admin)

    assert db.query(models.CallLog).count() == 0
    assert db.query(models.CallAssignment).count() == 0
    print("✓ 5: call_logs/call_assignments נמחקים גם דרך ראוט האדמין")


if __name__ == "__main__":
    test_1_admin_deletes_event_owner_account_untouched()
    test_2_missing_event_returns_404_not_crash()
    test_3_deleting_one_event_does_not_touch_sibling_event()
    test_4_audit_log_recorded_with_correct_action()
    test_5_dependent_call_center_rows_are_cleaned_up()
    print()
    print("=== כל 5 תרחישי מחיקת אירוע (אדמין) עברו ===")
