"""בדיקות למשימה המתוזמנת של מסלול אישורי ההגעה (``app/rsvp_scheduler.py``).

נועל את ה-Product Flow (החלטת המייסד 2026-09-23):
- המסלול רץ בלי שום כניסה למסך, ובלי קשר לשליחת הזמנה.
- מוזמן חדש מצטרף לסבב הבא הרלוונטי — אין replay של סבבים שעברו.
- מי שאישר/לא מגיע יוצא מהמסלול; מספר לא תקין לא מקבל WhatsApp.
- אין שליחה כפולה, גם בריצות חוזרות.
- אירועים קיימים (שכבר באמצע מסלול) ממשיכים בלי לשלוח שוב.

לוח הזמנים של כל הבדיקות (אירוע רביעי 30/9, סגירה יומיים לפני → שני 28/9):
    W 14/9 (בקשה) · W 15/9 (תזכורת 1) · P 17/9 · W 20/9 (תזכורת 2) ·
    P 23/9 · W 24/9 (תזכורת 3) · P 28/9
שעת שליחה 12:00 שעון ישראל = 09:00 UTC (ספטמבר, שעון קיץ).

הרצה: ``venv/bin/python tests/test_rsvp_scheduler.py`` (עצמאי, או pytest).
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import (  # noqa: E402
    communication, message_status, messaging, models, postponement_service,
    rsvp_scheduler, rsvp_timeline,
)
from app.database import Base  # noqa: E402

ROUND_DAYS = {
    "rsvp_request": date(2026, 9, 14),
    "reminder_1": date(2026, 9, 15),
    "reminder_2": date(2026, 9, 20),
    "final_reminder": date(2026, 9, 24),
}
EARLY = datetime(2026, 1, 1)


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


def _guest(db: Session, ev: models.Event, name: str, phone: str = "0501234567",
           created: datetime = EARLY, status: str = "pending") -> models.Guest:
    g = models.Guest(event_id=ev.id, full_name=name, phone=phone, side="groom",
                     rsvp_status=status, created_at=created)
    db.add(g)
    db.commit()
    return g


def _at(day: date, hour_utc: int = 9, minute: int = 30) -> datetime:
    return datetime(day.year, day.month, day.day, hour_utc, minute)


def _tick(db: Session, when: datetime) -> rsvp_scheduler.TickStats:
    return rsvp_scheduler.run(db, when)


def _kinds_for(db: Session, guest: models.Guest) -> list[str]:
    return [
        m.kind for m in db.scalars(
            select(models.Message).where(models.Message.guest_id == guest.id)
            .order_by(models.Message.id)
        ).all()
    ]


def _run_every_day(db: Session, first: date, last: date) -> None:
    d = first
    while d <= last:
        _tick(db, _at(d))
        d += timedelta(days=1)


# ---------------------------------------------------------------------------

def test_schedule_fixture_is_the_full_track() -> None:
    db = _db()
    ev = _event(db)
    rounds = {r.message_type: r.day for r in rsvp_timeline.whatsapp_rounds(ev, _at(date(2026, 9, 13)))}
    assert rounds == ROUND_DAYS, rounds
    print("✓ לוח הבדיקה = המסלול המלא (W W P W P W P)")


def test_track_runs_without_screens_and_without_invitation() -> None:
    """(16) המשימה המתוזמנת שולחת בלי שאף אחד נכנס למסך, ובלי שנשלחה הזמנה."""
    db = _db()
    ev = _event(db)
    dana = _guest(db, ev, "דנה")
    assert not ev.rsvp_track_active

    before = _tick(db, _at(date(2026, 9, 13)))
    assert before.sent == 0 and not db.get(models.Event, ev.id).rsvp_track_active
    too_early = _tick(db, _at(ROUND_DAYS["rsvp_request"], 8, 30))  # 11:30 IL
    assert too_early.sent == 0 and too_early.started == 1, "המסלול מתחיל ביום הסבב הראשון"
    at_time = _tick(db, _at(ROUND_DAYS["rsvp_request"]))
    assert at_time.sent == 1
    assert _kinds_for(db, dana) == ["rsvp_request"]
    assert db.get(models.Event, ev.id).rsvp_track_started_at is not None
    print("✓ (16) הסבב יוצא מהמשימה המתוזמנת — בלי מסך ובלי הזמנה")


def test_full_track_sends_each_round_once() -> None:
    """מסלול מלא, ריצה כל יום (וגם פעמיים ביום) — כל סבב פעם אחת, בתאריך שלו."""
    db = _db()
    ev = _event(db)
    g = _guest(db, ev, "רון")
    d = date(2026, 9, 13)
    while d <= date(2026, 10, 2):
        _tick(db, _at(d))
        _tick(db, _at(d, 14))  # ריצה נוספת באותו יום
        d += timedelta(days=1)
    assert _kinds_for(db, g) == ["rsvp_request", "reminder_1", "reminder_2", "final_reminder"], _kinds_for(db, g)
    sent_days = [
        (m.kind, m.created_at.date()) for m in db.scalars(
            select(models.Message).where(models.Message.guest_id == g.id)
        ).all()
    ]
    assert len(sent_days) == 4
    print("✓ (17) כל סבב נשלח פעם אחת בדיוק, גם בריצות חוזרות")


def test_confirmed_and_declined_leave_the_track() -> None:
    """(11)(12) אישר / לא מגיע באמצע — לא מקבל עוד סבבים. אולי — יוצא מה-WhatsApp."""
    db = _db()
    ev = _event(db)
    yes = _guest(db, ev, "מאשר", "0501111111")
    no = _guest(db, ev, "מסרב", "0502222222")
    maybe = _guest(db, ev, "אולי", "0503333333")
    _run_every_day(db, date(2026, 9, 14), date(2026, 9, 15))
    for g, status in ((yes, "confirmed"), (no, "declined"), (maybe, "maybe")):
        g.rsvp_status = status
    db.commit()
    _run_every_day(db, date(2026, 9, 16), date(2026, 9, 29))
    for g in (yes, no, maybe):
        assert _kinds_for(db, g) == ["rsvp_request", "reminder_1"], (g.full_name, _kinds_for(db, g))
    print("✓ (11)(12) מי שאישר/לא מגיע/אולי לא מקבל עוד סבבי WhatsApp")


def test_new_guest_joins_the_next_round_without_replay() -> None:
    """(8) מוזמן חדש אחרי תזכורת 1 ולפני סבב השיחות הראשון — לא מקבל את
    הבקשה ואת תזכורת 1 בדיעבד; מקבל רק את הסבבים שאחרי שנוסף."""
    db = _db()
    ev = _event(db)
    _guest(db, ev, "ותיק")
    _run_every_day(db, date(2026, 9, 14), date(2026, 9, 15))
    newcomer = _guest(db, ev, "חדש", "0504444444", created=_at(date(2026, 9, 16), 7))
    _run_every_day(db, date(2026, 9, 16), date(2026, 9, 29))
    assert _kinds_for(db, newcomer) == ["reminder_2", "final_reminder"], _kinds_for(db, newcomer)
    print("✓ (8) מוזמן חדש מצטרף לסבב הבא — בלי replay של מה שעבר")


def test_new_guest_after_whatsapp_rounds_gets_no_whatsapp() -> None:
    """(9) נוסף אחרי סבב ה-WhatsApp האחרון — לא חוזר אחורה. (10) נוסף אחרי
    שהמסלול הסתיים — לא נכנס למסלול."""
    db = _db()
    ev = _event(db)
    _run_every_day(db, date(2026, 9, 14), date(2026, 9, 24))
    late = _guest(db, ev, "מאוחר", "0505555555", created=_at(date(2026, 9, 25), 7))
    after_end = _guest(db, ev, "אחרי הסגירה", "0506666666", created=_at(date(2026, 9, 29), 7))
    _run_every_day(db, date(2026, 9, 25), date(2026, 9, 29))
    assert _kinds_for(db, late) == [], _kinds_for(db, late)
    assert _kinds_for(db, after_end) == []
    print("✓ (9)(10) נוסף אחרי סבבי ה-WhatsApp / אחרי הסגירה — לא מקבל WhatsApp בדיעבד")


def test_new_guest_skips_past_call_round() -> None:
    """(8) גם בשיחות: מוזמן שנוסף אחרי יום סבב שיחות לא נכנס אליו בדיעבד."""
    from app import call_ops

    g = models.Guest(full_name="חדש", created_at=_at(date(2026, 9, 18), 7))
    assert call_ops._existed_on(g, date(2026, 9, 17)) is False, "נכנס לסבב שעבר"
    assert call_ops._existed_on(g, date(2026, 9, 23)) is True, "לא נכנס לסבב הבא"
    assert call_ops._existed_on(models.Guest(full_name="ישן"), date(2026, 9, 17)) is True
    print("✓ (8) מוזמן חדש מצטרף לסבב השיחות הבא, לא לזה שעבר")


def test_no_replay_after_a_missed_round() -> None:
    """(18) המשימה לא רצה בזמן תזכורת 1 — כשהיא חוזרת, בחלון של תזכורת 2,
    תזכורת 1 לא נשלחת בדיעבד."""
    db = _db()
    ev = _event(db)
    g = _guest(db, ev, "אורח")
    _tick(db, _at(ROUND_DAYS["rsvp_request"]))
    # השרת "נפל" מ-15/9 עד 20/9.
    _tick(db, _at(ROUND_DAYS["reminder_2"]))
    assert _kinds_for(db, g) == ["rsvp_request", "reminder_2"], _kinds_for(db, g)
    # ובתוך החלון של הסבב (אותו יום, אחרי השעה) — כן משלימים.
    db2 = _db()
    ev2 = _event(db2)
    g2 = _guest(db2, ev2, "אורח")
    _tick(db2, _at(ROUND_DAYS["rsvp_request"], 15))  # 18:00 IL — עדיין בחלון
    assert _kinds_for(db2, g2) == ["rsvp_request"]
    print("✓ (18) סבב שהחלון שלו עבר לא נשלח בדיעבד; באותו חלון — כן")


def test_invalid_phone_is_skipped_and_visible() -> None:
    """(13) מספר לא תקין לא מקבל WhatsApp, מופיע בסטטוס ההודעות, ואחרי תיקון
    מקבל את הסבב הנוכחי (בחלון שלו) — לא את מה שעבר."""
    db = _db()
    ev = _event(db)
    bad = _guest(db, ev, "שגוי", "12345")
    missing = _guest(db, ev, "חסר", "")
    _tick(db, _at(ROUND_DAYS["rsvp_request"]))
    assert _kinds_for(db, bad) == [] and _kinds_for(db, missing) == []
    guests = list(db.scalars(select(models.Guest).where(models.Guest.event_id == ev.id)).all())
    counts = message_status.summarize(guests, list(db.scalars(select(models.Message)).all()))
    assert counts[message_status.NO_VALID_NUMBER] == 2, counts
    bad.phone = "0507777777"
    db.commit()
    _tick(db, _at(ROUND_DAYS["reminder_1"]))
    assert _kinds_for(db, bad) == ["reminder_1"], _kinds_for(db, bad)
    print("✓ (13) מספר לא תקין: לא נשלח, מוצג בסטטוס, ואחרי תיקון — מהסבב הנוכחי")


def test_event_without_chosen_closing_date_sends_nothing() -> None:
    """אירוע קרוב בלי בחירת מועד סגירה: יש לוח לתצוגה, אבל לא נשלח כלום."""
    db = _db()
    ev = _event(db, venue_commit_days_before=None, event_date="2026-09-20")
    g = _guest(db, ev, "אורח")
    assert rsvp_timeline.compute_schedule(ev, _at(date(2026, 9, 14))) is not None
    _run_every_day(db, date(2026, 9, 14), date(2026, 9, 21))
    assert _kinds_for(db, g) == []
    assert not db.get(models.Event, ev.id).rsvp_track_active
    print("✓ אירוע בלי בחירת מועד סגירה — לוח מוצג, שום דבר לא נשלח")


def test_existing_event_mid_track_continues_without_resending() -> None:
    """אירוע ישן: הזמנות נשלחו והמסלול "הופעל" לפני השינוי, הבקשה כבר יצאה
    — ממשיך מהסבב הבא, בלי לשלוח שוב את מה שכבר יצא."""
    db = _db()
    ev = _event(db, venue_commit_days_before=None, rsvp_track_active=True,
                rsvp_track_started_at=datetime(2026, 8, 1), event_date="2026-09-30")
    ev.venue_commit_days_before = 2  # אירוע ישן עם בחירה
    db.commit()
    g = _guest(db, ev, "ותיק")
    em = communication.event_messages_by_type(db, ev.id)
    for kind in ("invitation", "rsvp_request"):
        db.add(models.Message(event_id=ev.id, guest_id=g.id, direction="outbound", kind=kind,
                              body=kind, channel="whatsapp", status="sent",
                              event_message_id=em[kind].id, created_at=datetime(2026, 9, 14, 9)))
    db.commit()
    _run_every_day(db, date(2026, 9, 15), date(2026, 9, 29))
    assert _kinds_for(db, g) == ["invitation", "rsvp_request", "reminder_1", "reminder_2", "final_reminder"]
    print("✓ אירוע קיים באמצע מסלול ממשיך מהסבב הבא, בלי כפילויות")


def test_legacy_active_event_with_default_closing_date_continues() -> None:
    """אירוע שהמסלול שלו כבר התחיל לפני השינוי, בלי בחירת מועד סגירה (ברירת
    המחדל לאירוע קרוב) — ממשיך לפעול."""
    db = _db()
    ev = _event(db, venue_commit_days_before=None, rsvp_track_active=True,
                rsvp_track_started_at=datetime(2026, 9, 14, 6), event_date="2026-09-22")
    g = _guest(db, ev, "אורח")
    _run_every_day(db, date(2026, 9, 14), date(2026, 9, 21))
    assert _kinds_for(db, g)[:1] == ["rsvp_request"], _kinds_for(db, g)
    print("✓ אירוע ישן שהמסלול שלו כבר רץ (ברירת מחדל) ממשיך")


def test_invitation_send_does_not_start_or_feed_the_track() -> None:
    """שליחת הזמנה לא מתחילה מסלול ולא שולחת בקשת אישור לפני הזמן."""
    db = _db()
    ev = _event(db)
    g = _guest(db, ev, "אורח")
    db.add(models.Message(event_id=ev.id, guest_id=g.id, direction="outbound", kind="invitation",
                          body="הזמנה", channel="whatsapp", status="sent",
                          created_at=datetime(2026, 8, 1)))
    db.commit()
    _tick(db, _at(date(2026, 9, 1)))
    assert not db.get(models.Event, ev.id).rsvp_track_active
    assert _kinds_for(db, g) == ["invitation"]
    print("✓ הזמנה שנשלחה חודש מראש לא מתחילה את המסלול")


def test_event_day_and_thank_you_are_sent_by_the_scheduler() -> None:
    """הודעת יום האירוע והתודה יוצאות מהמשימה — ורק ביום שלהן."""
    db = _db()
    ev = _event(db)
    g = _guest(db, ev, "מאשר", status="confirmed")
    _tick(db, _at(date(2026, 9, 29)))
    _tick(db, _at(date(2026, 9, 30)))           # יום האירוע (רביעי)
    _tick(db, _at(date(2026, 10, 1)))           # יום אחרי — תודה (חמישי)
    _tick(db, _at(date(2026, 10, 2)))
    assert _kinds_for(db, g) == ["event_day", "thank_you"], _kinds_for(db, g)
    # לא בדיעבד: אם המשימה לא רצה ביום האירוע, אין "היום מתראים" למחרת.
    db2 = _db()
    ev2 = _event(db2)
    g2 = _guest(db2, ev2, "מאשר", status="confirmed")
    _tick(db2, _at(date(2026, 10, 1)))
    assert _kinds_for(db2, g2) == ["thank_you"], _kinds_for(db2, g2)
    print("✓ יום האירוע + תודה יוצאות מהמשימה, רק ביום שלהן")


def test_emergency_stop_and_open_postponement_send_nothing() -> None:
    """עצירת חירום / נוהל דחייה פתוח — לא שולחים, והסבב לא "נשרף"."""
    db = _db()
    ev = _event(db)
    g = _guest(db, ev, "אורח")
    original = messaging.emergency_stop_active
    messaging.emergency_stop_active = lambda: True
    try:
        stats = _tick(db, _at(ROUND_DAYS["rsvp_request"]))
    finally:
        messaging.emergency_stop_active = original
    assert stats.skipped_emergency and _kinds_for(db, g) == []
    _tick(db, _at(ROUND_DAYS["rsvp_request"], 12))  # העצירה הוסרה, עדיין בחלון
    assert _kinds_for(db, g) == ["rsvp_request"]

    original_open = postponement_service.open_request_of
    postponement_service.open_request_of = lambda _db, _eid: object()
    try:
        _tick(db, _at(ROUND_DAYS["reminder_1"]))
    finally:
        postponement_service.open_request_of = original_open
    assert _kinds_for(db, g) == ["rsvp_request"]
    print("✓ עצירת חירום / נוהל דחייה — לא נשלח כלום, והסבב נשמר לחלון שלו")


if __name__ == "__main__":
    test_schedule_fixture_is_the_full_track()
    test_track_runs_without_screens_and_without_invitation()
    test_full_track_sends_each_round_once()
    test_confirmed_and_declined_leave_the_track()
    test_new_guest_joins_the_next_round_without_replay()
    test_new_guest_after_whatsapp_rounds_gets_no_whatsapp()
    test_new_guest_skips_past_call_round()
    test_no_replay_after_a_missed_round()
    test_invalid_phone_is_skipped_and_visible()
    test_event_without_chosen_closing_date_sends_nothing()
    test_existing_event_mid_track_continues_without_resending()
    test_legacy_active_event_with_default_closing_date_continues()
    test_invitation_send_does_not_start_or_feed_the_track()
    test_event_day_and_thank_you_are_sent_by_the_scheduler()
    test_emergency_stop_and_open_postponement_send_nothing()
    print("\nכל בדיקות המשימה המתוזמנת עברו ✓")
