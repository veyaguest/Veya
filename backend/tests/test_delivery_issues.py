"""בדיקות להודעות WhatsApp שלא הגיעו (``app/delivery_issues.py``).

נועל את ההחלטות (2026-10-19):
- 131049 (הגבלת שיווק): ההזמנה נשלחת שוב אחרי 24 שעות, ועוד פעם לכל היותר
  אחרי עוד 24 — רק בימי חול, 10:00–19:00, לפני יום האירוע, למי שעוד לא ענה.
- אף פעם לא פעמיים: ``pending`` לא נשלח שוב; הזמנה שיצאה בינתיים או ריצה
  כפולה — לא שולחים.
- 131050 / 131026 / כשל אחר — לעולם לא נשלחים שוב אוטומטית.

לוח הזמנים: אירוע רביעי 30/9/2026, סגירה יומיים לפני; סבב ה-WhatsApp הראשון
ב-14/9 — כל הבדיקות כאן לפניו, כדי שתזכורות המסלול לא ייכנסו לתמונה.
שעון ישראל בספטמבר = UTC+3.

הרצה: ``venv/bin/python -m pytest tests/test_delivery_issues.py``.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import (  # noqa: E402
    communication, delivery_issues as di, message_status as ms, messaging, models,
    postponement_service, rsvp_scheduler,
)
from app.database import Base  # noqa: E402

# שלישי 8/9 12:00 בישראל — ההזמנה המקורית נעצרה.
FAILED_AT = datetime(2026, 9, 8, 9, 0)


def _db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _event(db: Session, **kw) -> models.Event:
    fields = dict(
        groom_name="יואב", bride_name="דנה", event_type="wedding",
        event_date="2026-09-30", rsvp_send_time="12:00", thank_you_send_time="12:00",
        venue_commit_days_before=2,
    )
    fields.update(kw)
    ev = models.Event(**fields)
    db.add(ev)
    db.flush()
    for mt in communication.MESSAGE_TYPES:
        db.add(models.EventMessage(
            event_id=ev.id, message_type=mt, title=mt,
            content=f"{mt} ל-{{{{guest_name}}}}", is_active=True,
            trigger_offset_days=communication.DEFAULT_TRIGGER_OFFSET_DAYS[mt],
            target_audience=communication.DEFAULT_TARGET_AUDIENCE[mt],
        ))
    db.commit()
    return ev


def _guest(db: Session, ev: models.Event, name: str = "רוני לוי", phone: str = "0501234567",
           status: str = "pending") -> models.Guest:
    g = models.Guest(event_id=ev.id, full_name=name, phone=phone, side="groom",
                     rsvp_status=status, created_at=datetime(2026, 1, 1), guest_token=f"tok{name}x")
    db.add(g)
    db.commit()
    return g


def _msg(db: Session, ev: models.Event, g: models.Guest, *, status: str = ms.FAILED,
         code: int | None = di.CODE_MARKETING_CAP, kind: str = "invitation",
         at: datetime = FAILED_AT) -> models.Message:
    m = models.Message(
        event_id=ev.id, guest_id=g.id, direction="outbound", kind=kind, channel="whatsapp",
        status=status, provider="meta", failure_code=code if status == ms.FAILED else None,
        created_at=at, cycle_number=1,
    )
    if status == ms.BLOCKED:
        m.failure_code = 131050
    db.add(m)
    db.commit()
    return m


def _invitations(db: Session, g: models.Guest) -> list[models.Message]:
    return list(db.scalars(
        select(models.Message).where(models.Message.guest_id == g.id,
                                     models.Message.kind == "invitation")
        .order_by(models.Message.id)
    ).all())


def _tick(db: Session, now: datetime):
    return rsvp_scheduler.run(db, now=now)


# ---- סיווג ----

def test_classify_each_code() -> None:
    db = _db()
    ev = _event(db)
    cases = {
        "a": (ms.FAILED, di.CODE_MARKETING_CAP, di.MARKETING_CAP),
        "b": (ms.BLOCKED, None, di.MARKETING_OPT_OUT),
        "c": (ms.FAILED, di.CODE_UNDELIVERABLE, di.UNDELIVERABLE),
        "d": (ms.FAILED, 131000, di.FAILED_OTHER),
        "e": (ms.FAILED, None, di.FAILED_OTHER),
        "f": (ms.PENDING, None, None),
        "g": (ms.SENT, None, None),
        "h": (ms.DELIVERED, None, None),
    }
    guests = {}
    for key, (status, code, _) in cases.items():
        guests[key] = _guest(db, ev, name=f"מוזמן {key}")
        _msg(db, ev, guests[key], status=status, code=code)
    found = {i.guest.id: i.reason for i in di.issues_for_event(db, ev)}
    for key, (_, _, expected) in cases.items():
        assert found.get(guests[key].id) == expected, (key, found.get(guests[key].id))


def test_later_delivered_message_clears_the_issue() -> None:
    db = _db()
    ev = _event(db)
    g = _guest(db, ev)
    _msg(db, ev, g, code=di.CODE_UNDELIVERABLE)
    assert [i.reason for i in di.issues_for_event(db, ev)] == [di.UNDELIVERABLE]
    _msg(db, ev, g, status=ms.DELIVERED, kind="rsvp_request", at=datetime(2026, 9, 14, 9, 0))
    assert di.issues_for_event(db, ev) == []


# ---- שליחה חוזרת אחרי הגבלת שיווק ----

def test_resend_only_after_24_hours_and_once_per_tick() -> None:
    db = _db()
    ev = _event(db)
    g = _guest(db, ev)
    _msg(db, ev, g)

    _tick(db, datetime(2026, 9, 9, 8, 59))           # 23:59 שעות — מוקדם מדי
    assert len(_invitations(db, g)) == 1
    _tick(db, datetime(2026, 9, 9, 9, 0))            # 24 שעות בדיוק
    rows = _invitations(db, g)
    assert len(rows) == 2 and rows[-1].status == ms.SENT
    _tick(db, datetime(2026, 9, 9, 9, 15))           # ריצה נוספת — לא שוב
    _tick(db, datetime(2026, 9, 10, 9, 30))          # גם למחרת — היא נשלחה
    assert len(_invitations(db, g)) == 2


def test_second_resend_skips_weekend_and_no_third() -> None:
    db = _db()
    ev = _event(db)
    g = _guest(db, ev)
    # רביעי 9/9 12:00 — נעצרה; ניסיון 1 בחמישי 10/9.
    _msg(db, ev, g, at=datetime(2026, 9, 9, 9, 0))
    _tick(db, datetime(2026, 9, 10, 9, 0))
    first = _invitations(db, g)[-1]
    assert first.status == ms.SENT
    # Meta עצרה גם את הניסיון הזה (חמישי 12:00).
    first.status, first.failure_code, first.created_at = ms.FAILED, di.CODE_MARKETING_CAP, datetime(2026, 9, 10, 9, 0)
    db.commit()
    issue = di.issues_for_event(db, ev)[0]
    # 24 שעות אחר כך = שישי → ראשון 13/9 10:00 בישראל (07:00 UTC).
    assert issue.cap_failures == 2 and issue.resend_at == datetime(2026, 9, 13, 7, 0)
    _tick(db, datetime(2026, 9, 11, 9, 30))          # שישי — לא שולחים
    _tick(db, datetime(2026, 9, 12, 9, 30))          # שבת — לא שולחים
    assert len(_invitations(db, g)) == 2
    _tick(db, datetime(2026, 9, 13, 7, 0))
    second = _invitations(db, g)[-1]
    assert len(_invitations(db, g)) == 3 and second.status == ms.SENT
    # גם השני נעצר — אין שלישי.
    second.status, second.failure_code, second.created_at = ms.FAILED, di.CODE_MARKETING_CAP, datetime(2026, 9, 13, 7, 0)
    db.commit()
    assert di.issues_for_event(db, ev)[0].resend_at is None
    _tick(db, datetime(2026, 9, 14, 7, 30))
    _tick(db, datetime(2026, 9, 15, 7, 30))
    assert len(_invitations(db, g)) == 3


def test_resend_only_within_send_hours() -> None:
    db = _db()
    ev = _event(db)
    g = _guest(db, ev)
    _msg(db, ev, g, at=datetime(2026, 9, 8, 15, 30))   # 18:30 בישראל
    _tick(db, datetime(2026, 9, 9, 16, 0))             # 19:00 — כבר לא
    assert len(_invitations(db, g)) == 1
    # הרגע המוקדם (רביעי 18:30) עבר בלי ריצה — הניסיון זז לחמישי 10:00.
    assert di.issues_for_event(db, ev, now=datetime(2026, 9, 9, 16, 0))[0].resend_at == datetime(2026, 9, 10, 7, 0)
    _tick(db, datetime(2026, 9, 10, 6, 59))            # 09:59 — עוד לא
    assert len(_invitations(db, g)) == 1
    _tick(db, datetime(2026, 9, 10, 7, 0))
    assert len(_invitations(db, g)) == 2


def test_never_twice() -> None:
    """``pending``, הזמנה שיצאה בינתיים, או הזמנה שכבר נמסרה — אין שליחה חוזרת."""
    db = _db()
    ev = _event(db)
    later = datetime(2026, 9, 10, 9, 0)

    pending = _guest(db, ev, name="ממתין א")
    _msg(db, ev, pending, status=ms.PENDING, code=None)

    resent_by_hand = _guest(db, ev, name="ידני ב")
    _msg(db, ev, resent_by_hand)
    _msg(db, ev, resent_by_hand, status=ms.SENT, code=None, at=datetime(2026, 9, 8, 12, 0))

    # הזמנה שנמסרה קודם, ושליחה חוזרת ידנית (אדמין) שנעצרה — הוא כבר קיבל.
    had_one = _guest(db, ev, name="קיבל ד")
    _msg(db, ev, had_one, status=ms.DELIVERED, code=None, at=datetime(2026, 9, 7, 9, 0))
    _msg(db, ev, had_one)
    db.commit()

    _tick(db, later)
    assert len(_invitations(db, pending)) == 1
    assert len(_invitations(db, resent_by_hand)) == 2
    assert len(_invitations(db, had_one)) == 2


def test_no_auto_resend_after_hand_off() -> None:
    """הצוות העביר לבעלי האירוע לשלוח בעצמם — VEYA לא שולחת שוב בעצמה."""
    db = _db()
    ev = _event(db)
    g = _guest(db, ev)
    _msg(db, ev, g)
    g.whatsapp_handoff_at = datetime(2026, 9, 8, 12, 0)
    db.commit()
    assert di.issues_for_event(db, ev)[0].resend_at is None
    _tick(db, datetime(2026, 9, 9, 9, 0))
    assert len(_invitations(db, g)) == 1


def test_rules_block_resend() -> None:
    db = _db()
    ev = _event(db)
    answered = _guest(db, ev, name="ענה", status="confirmed")
    _msg(db, ev, answered)
    bad_phone = _guest(db, ev, name="מספר", phone="123")
    _msg(db, ev, bad_phone)
    reminder = _guest(db, ev, name="תזכורת")
    _msg(db, ev, reminder, kind="reminder_1")         # לא תבנית שיווק
    for code_status in ((ms.BLOCKED, None), (ms.FAILED, di.CODE_UNDELIVERABLE), (ms.FAILED, 131000)):
        g = _guest(db, ev, name=f"קוד {code_status}")
        _msg(db, ev, g, status=code_status[0], code=code_status[1])
    before = db.query(models.Message).count()
    _tick(db, datetime(2026, 9, 10, 9, 0))
    assert db.query(models.Message).count() == before


def test_emergency_stop_postponement_and_event_day() -> None:
    db = _db()
    ev = _event(db)
    g = _guest(db, ev)
    _msg(db, ev, g)
    now = datetime(2026, 9, 9, 9, 0)

    original = messaging.emergency_stop_active
    messaging.emergency_stop_active = lambda: True
    try:
        _tick(db, now)
    finally:
        messaging.emergency_stop_active = original
    original_open = postponement_service.open_request_of
    postponement_service.open_request_of = lambda _db, _eid: object()
    try:
        _tick(db, now)
    finally:
        postponement_service.open_request_of = original_open
    assert len(_invitations(db, g)) == 1

    # נעצרה יום לפני האירוע — 24 שעות אחר כך זה כבר יום האירוע.
    ev2 = _event(db, event_date="2026-09-10")
    g2 = _guest(db, ev2, name="אחרון")
    _msg(db, ev2, g2, at=datetime(2026, 9, 9, 9, 0))
    assert di.issues_for_event(db, ev2)[0].resend_at is None
    assert di.resend_due(db, ev2, datetime(2026, 9, 10, 9, 0)) == (0, 0)
    assert len(_invitations(db, g2)) == 1


# ---- תור השיחות של האדמין ----

def _sync(db: Session, now: datetime):
    from app import call_ops

    stats = call_ops.sync(db, now=now, force=True)
    db.commit()
    return stats


def _tasks(db: Session, g: models.Guest) -> list[models.CallTask]:
    return list(db.scalars(
        select(models.CallTask).where(models.CallTask.guest_id == g.id).order_by(models.CallTask.id)
    ).all())


def test_undeliverable_goes_to_call_queue_today_once() -> None:
    from app import call_ops

    db = _db()
    ev = _event(db)
    g = _guest(db, ev)
    _msg(db, ev, g, code=di.CODE_UNDELIVERABLE)
    opted_out = _guest(db, ev, name="פרסום")
    _msg(db, ev, opted_out, status=ms.BLOCKED, code=None)
    capped = _guest(db, ev, name="הגבלה")
    _msg(db, ev, capped)

    now = datetime(2026, 9, 10, 9, 0)              # חמישי — אין עדיין סבב שיחות
    _sync(db, now)
    tasks = _tasks(db, g)
    assert len(tasks) == 1
    t = tasks[0]
    assert (t.round_number, t.reason, t.status, t.due_date) == (
        call_ops.MANUAL_ROUND, call_ops.DELIVERY_REASON, call_ops.OPEN, "2026-09-10")
    assert _tasks(db, opted_out) == [] and _tasks(db, capped) == []
    _sync(db, now)
    _sync(db, datetime(2026, 9, 13, 9, 0))
    assert len(_tasks(db, g)) == 1

    delivery = call_ops.delivery_states(db, [g, opted_out, capped])
    assert call_ops.reason_label(t.reason, g, None, delivery.get(g.id)) == "WhatsApp לא מגיע למספר הזה"
    assert "פרסום" in call_ops.reason_label("no_response", opted_out, None, delivery.get(opted_out.id))


def test_call_task_closes_when_answered_or_whatsapp_works() -> None:
    from app import call_ops

    db = _db()
    ev = _event(db)
    answered = _guest(db, ev, name="ענה")
    _msg(db, ev, answered, code=di.CODE_UNDELIVERABLE)
    fixed = _guest(db, ev, name="הגיע")
    _msg(db, ev, fixed, code=di.CODE_UNDELIVERABLE)
    called = _guest(db, ev, name="התקשרו")
    _msg(db, ev, called, code=di.CODE_UNDELIVERABLE)
    now = datetime(2026, 9, 10, 9, 0)
    _sync(db, now)

    answered.rsvp_status = "confirmed"
    _msg(db, ev, fixed, status=ms.DELIVERED, code=None, kind="rsvp_request", at=datetime(2026, 9, 10, 9, 30))
    done = _tasks(db, called)[0]
    done.status, done.last_outcome = call_ops.DONE, "no_answer"   # כבר ניסו — לא נפתחת שוב
    db.commit()
    _sync(db, datetime(2026, 9, 10, 10, 0))
    assert _tasks(db, answered)[0].status == call_ops.CLOSED_BY_RSVP
    t = _tasks(db, fixed)[0]
    assert (t.status, t.closed_reason) == (call_ops.SKIPPED, "whatsapp_ok")
    assert [x.status for x in _tasks(db, called)] == [call_ops.DONE]


def test_regular_call_round_replaces_the_whatsapp_task() -> None:
    from app import call_ops

    db = _db()
    # המסלול התחיל ב-14/9 — לוח הזמנים קפוא (סבב שיחות ראשון בחמישי 17/9).
    ev = _event(db, rsvp_track_active=True, rsvp_track_started_at=datetime(2026, 9, 14, 6, 0))
    g = _guest(db, ev)
    _msg(db, ev, g, code=di.CODE_UNDELIVERABLE)
    _sync(db, datetime(2026, 9, 15, 9, 0))
    assert [t.round_number for t in _tasks(db, g)] == [0]
    _sync(db, datetime(2026, 9, 17, 9, 0))
    tasks = _tasks(db, g)
    open_ = [t for t in tasks if t.status == call_ops.OPEN]
    assert len(open_) == 1 and open_[0].round_number != call_ops.MANUAL_ROUND, [
        (t.round_number, t.status, t.closed_reason) for t in tasks]
    manual = next(t for t in tasks if t.round_number == call_ops.MANUAL_ROUND)
    assert (manual.status, manual.closed_reason) == (call_ops.SKIPPED, "next_round")
    delivery = call_ops.delivery_states(db, [g])
    assert call_ops.reason_label(open_[0].reason, g, (1, 0), delivery.get(g.id)) == "WhatsApp לא מגיע למספר הזה"
