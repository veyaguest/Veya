"""בדיקות למחיקת אירוע/חשבון (app/account.py: delete_event_cascade).

הבאג שנמצא: אירוע שהופעל בו מסלול אישורי הגעה יוצר שורות ``event_messages``
(רצף "תקשורת עם אורחים", ראו communication.py: provision_event_messages).
הטבלה הזו לא הייתה ברשימת הניקוי של delete_event_cascade, אז DELETE FROM
events נכשל עם IntegrityError ברגע שהיו לאירוע שורות event_messages —
בדיוק המצב שכל אירוע מגיע אליו אחרי לחיצה על "שליחת הזמנות".

מכסה את 13 התרחישים שהתבקשו: אירוע בלי הודעות / עם הודעה אחת / עם כמה
הודעות / עם סטטוסים שונים (sent/delivered/read/failed) / עם
provider_message_id / עם אוטומציות (automation_rules ישן + event_messages
נוכחי) / עם guests, מחיקת חשבון עם כמה אירועים, ווידוא שלא נשאר מידע יתום
ושלא נפגע אירוע אחר.

הרצה: ``venv/bin/python tests/test_account_delete.py`` (עצמאי, בלי pytest).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, event, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402
from app.account import delete_event_cascade  # noqa: E402
from app.database import Base  # noqa: E402


def _fresh_session() -> Session:
    engine = create_engine("sqlite://")

    # קריטי כאן: בדיוק כמו app/database.py — בלי PRAGMA foreign_keys=ON
    # SQLite לא אוכף FK בכלל, וה-DELETE-ים היו "מצליחים" גם אם סדר המחיקה
    # שגוי (בדיוק הבאג האמיתי: DELETE FROM event_messages רץ לפני שה-
    # messages שמצביעות אליו נמחקו). בלי השורה הזו הבדיקות האלה לא היו
    # מזהות את הבאג בכלל — היו "עוברות" גם על קוד שבור.
    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _make_user(db: Session, email: str = "user@example.com") -> models.User:
    u = models.User(email=email, password_hash="x", display_name="בדיקה")
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


def _add_event_message(db: Session, event_id: int, message_type: str = "invitation") -> models.EventMessage:
    em = models.EventMessage(event_id=event_id, message_type=message_type, title="הזמנה", content="שלום")
    db.add(em)
    db.commit()
    return em


def _add_message(
    db: Session, event_id: int, guest_id: int, *, status: str = "sent",
    provider_message_id: str = "", event_message_id=None,
) -> models.Message:
    m = models.Message(
        event_id=event_id, guest_id=guest_id, direction="outbound", kind="invitation",
        body="שלום", status=status, provider="mock",
        provider_message_id=provider_message_id or None,
        event_message_id=event_message_id,
    )
    db.add(m)
    db.commit()
    return m


def _assert_event_fully_gone(db: Session, event_id: int) -> None:
    assert db.get(models.Event, event_id) is None
    assert db.scalars(select(models.Guest).where(models.Guest.event_id == event_id)).first() is None
    assert db.scalars(select(models.Message).where(models.Message.event_id == event_id)).first() is None
    assert db.scalars(select(models.EventMessage).where(models.EventMessage.event_id == event_id)).first() is None
    assert db.scalars(select(models.Clarification).where(models.Clarification.event_id == event_id)).first() is None
    assert db.scalars(select(models.AuditLog).where(models.AuditLog.event_id == event_id)).first() is None
    assert db.scalars(select(models.AutomationRule).where(models.AutomationRule.event_id == event_id)).first() is None
    assert db.scalars(select(models.MessageTemplate).where(models.MessageTemplate.event_id == event_id)).first() is None
    assert db.scalars(select(models.EventMember).where(models.EventMember.event_id == event_id)).first() is None
    assert db.scalars(
        select(models.EventInvitation).where(models.EventInvitation.event_id == event_id)
    ).first() is None


def test_1_event_without_messages() -> None:
    db = _fresh_session()
    u = _make_user(db)
    ev = _make_event(db, u.id)
    delete_event_cascade(db, ev)
    db.commit()
    _assert_event_fully_gone(db, ev.id)
    print("✓ 1: אירוע בלי שום הודעה נמחק בהצלחה")


def test_2_event_with_one_message() -> None:
    db = _fresh_session()
    u = _make_user(db)
    ev = _make_event(db, u.id)
    g = _make_guest(db, ev.id)
    em = _add_event_message(db, ev.id)
    _add_message(db, ev.id, g.id, event_message_id=em.id)
    delete_event_cascade(db, ev)
    db.commit()
    _assert_event_fully_gone(db, ev.id)
    print("✓ 2: אירוע עם הודעה אחת (וה-event_message שיצר אותה) נמחק בהצלחה — זה הבאג המקורי")


def test_3_event_with_many_messages() -> None:
    db = _fresh_session()
    u = _make_user(db)
    ev = _make_event(db, u.id)
    em = _add_event_message(db, ev.id)
    for i in range(5):
        g = _make_guest(db, ev.id, phone=f"050000000{i}")
        _add_message(db, ev.id, g.id, event_message_id=em.id, provider_message_id=f"wamid-{i}")
    delete_event_cascade(db, ev)
    db.commit()
    _assert_event_fully_gone(db, ev.id)
    print("✓ 3: אירוע עם כמה הודעות ומוזמנים נמחק בהצלחה")


def test_4_to_7_every_message_status() -> None:
    db = _fresh_session()
    u = _make_user(db)
    ev = _make_event(db, u.id)
    em = _add_event_message(db, ev.id)
    for i, status in enumerate(["sent", "delivered", "read", "failed"]):
        g = _make_guest(db, ev.id, phone=f"052000000{i}")
        _add_message(db, ev.id, g.id, status=status, event_message_id=em.id, provider_message_id=f"st-{status}")
    delete_event_cascade(db, ev)
    db.commit()
    _assert_event_fully_gone(db, ev.id)
    print("✓ 4-7: אירוע עם הודעות sent/delivered/read/failed נמחק בהצלחה")


def test_8_event_with_provider_message_id() -> None:
    db = _fresh_session()
    u = _make_user(db)
    ev = _make_event(db, u.id)
    g = _make_guest(db, ev.id)
    em = _add_event_message(db, ev.id)
    _add_message(db, ev.id, g.id, event_message_id=em.id, provider_message_id="wamid-real-123")
    delete_event_cascade(db, ev)
    db.commit()
    _assert_event_fully_gone(db, ev.id)
    print("✓ 8: אירוע עם provider_message_id אמיתי נמחק בהצלחה (בלי לנסות לגעת ב-WhatsApp)")


def test_9_event_with_automations() -> None:
    db = _fresh_session()
    u = _make_user(db)
    ev = _make_event(db, u.id)
    # שני מסלולי אוטומציה: הישן (automation_rules, DEPRECATED אך עדיין ב-DB
    # מאירועים קיימים) והנוכחי (event_messages, ראו communication.py).
    db.add(models.AutomationRule(event_id=ev.id, rule_name="תזכורת", trigger_type="no_response"))
    db.commit()
    _add_event_message(db, ev.id, "reminder_1")
    delete_event_cascade(db, ev)
    db.commit()
    _assert_event_fully_gone(db, ev.id)
    print("✓ 9: אירוע עם אוטומציות (ישנות וחדשות) נמחק בהצלחה")


def test_10_event_with_guests() -> None:
    db = _fresh_session()
    u = _make_user(db)
    ev = _make_event(db, u.id)
    for i in range(3):
        _make_guest(db, ev.id, phone=f"053000000{i}")
    delete_event_cascade(db, ev)
    db.commit()
    _assert_event_fully_gone(db, ev.id)
    print("✓ 10: guests נמחקים (relationship cascade), אין orphaned guests")


def test_11_account_deletion_with_events_and_messages() -> None:
    """משכפל את routers/auth.py::delete_my_account — לולאת delete_event_cascade
    על כל האירועים בבעלות המשתמש, ואז מחיקת המשתמש עצמו."""
    db = _fresh_session()
    u = _make_user(db)
    ev1 = _make_event(db, u.id)
    ev2 = _make_event(db, u.id)
    em1 = _add_event_message(db, ev1.id)
    g1 = _make_guest(db, ev1.id)
    _add_message(db, ev1.id, g1.id, status="read", event_message_id=em1.id, provider_message_id="wamid-acc-1")
    _add_event_message(db, ev2.id)  # אירוע שני בלי אף הודעה שנשלחה בפועל

    owned = db.scalars(select(models.Event).where(models.Event.owner_id == u.id)).all()
    assert len(owned) == 2
    for ev in owned:
        delete_event_cascade(db, ev)
    db.delete(u)
    db.commit()

    assert db.get(models.User, u.id) is None
    _assert_event_fully_gone(db, ev1.id)
    _assert_event_fully_gone(db, ev2.id)
    print("✓ 11: מחיקת חשבון עם כמה אירועים (אחד עם הודעות, אחד בלעדיהן) מצליחה")


def test_12_no_orphaned_data_left() -> None:
    """אחרי מחיקה — אפס שורות בכל טבלת-ילד, לא רק שאי-אפשר לשלוף דרך event_id."""
    db = _fresh_session()
    u = _make_user(db)
    ev = _make_event(db, u.id)
    em = _add_event_message(db, ev.id)
    g = _make_guest(db, ev.id)
    _add_message(db, ev.id, g.id, event_message_id=em.id)
    db.add(models.Clarification(
        event_id=ev.id, source_guest_id=g.id, relation_type="avoid", target_text="מישהו",
    ))
    db.commit()

    delete_event_cascade(db, ev)
    db.commit()

    assert db.query(models.Message).count() == 0
    assert db.query(models.EventMessage).count() == 0
    assert db.query(models.Guest).count() == 0
    assert db.query(models.Clarification).count() == 0
    assert db.query(models.Event).count() == 0
    print("✓ 12: אחרי המחיקה אין אף שורה יתומה בשום טבלת-ילד")


def test_13_deleting_one_event_does_not_touch_another() -> None:
    db = _fresh_session()
    u = _make_user(db)
    ev1 = _make_event(db, u.id)
    ev2 = _make_event(db, u.id)
    em1 = _add_event_message(db, ev1.id)
    em2 = _add_event_message(db, ev2.id)
    g1 = _make_guest(db, ev1.id, phone="0540000001")
    g2 = _make_guest(db, ev2.id, phone="0540000002")
    _add_message(db, ev1.id, g1.id, event_message_id=em1.id, provider_message_id="wamid-ev1")
    _add_message(db, ev2.id, g2.id, event_message_id=em2.id, provider_message_id="wamid-ev2")

    delete_event_cascade(db, ev1)
    db.commit()

    _assert_event_fully_gone(db, ev1.id)
    # אירוע 2 נשאר שלם לגמרי — ה-event/guest/event_message/message שלו כולם עדיין קיימים.
    assert db.get(models.Event, ev2.id) is not None
    assert db.get(models.Guest, g2.id) is not None
    assert db.get(models.EventMessage, em2.id) is not None
    remaining = db.scalars(select(models.Message).where(models.Message.event_id == ev2.id)).all()
    assert len(remaining) == 1 and remaining[0].provider_message_id == "wamid-ev2"
    print("✓ 13: מחיקת אירוע אחד לא נוגעת בנתונים של אירוע אחר")


def test_14_event_with_open_invitation() -> None:
    """event_invitations (הזמנת שיתוף-אירוע, ראו models.EventInvitation) הוא FK
    רגיל בלי cascade — בדיוק כמו event_messages בזמנו. בלי הניקוי הזה, מחיקת
    אירוע עם הזמנת שיתוף פתוחה הייתה נכשלת עם IntegrityError."""
    db = _fresh_session()
    u = _make_user(db)
    ev = _make_event(db, u.id)
    db.add(models.EventInvitation(
        event_id=ev.id, invited_email="partner@example.com",
        invited_by=u.id, token_hash="hash123",
    ))
    db.commit()
    delete_event_cascade(db, ev)
    db.commit()
    _assert_event_fully_gone(db, ev.id)
    assert db.query(models.EventInvitation).count() == 0
    print("✓ 14: אירוע עם הזמנת שיתוף פתוחה נמחק בהצלחה, בלי הזמנה יתומה")


if __name__ == "__main__":
    test_1_event_without_messages()
    test_2_event_with_one_message()
    test_3_event_with_many_messages()
    test_4_to_7_every_message_status()
    test_8_event_with_provider_message_id()
    test_9_event_with_automations()
    test_10_event_with_guests()
    test_11_account_deletion_with_events_and_messages()
    test_12_no_orphaned_data_left()
    test_13_deleting_one_event_does_not_touch_another()
    test_14_event_with_open_invitation()
    print()
    print("=== כל 14 תרחישי מחיקת אירוע/חשבון עברו ===")
