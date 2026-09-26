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


def _called_on(db: Session, day: date) -> set[str]:
    """מי ברשימת השיחות של סבב השיחות שביום ``day`` (אחרי יציאת הסבב)."""
    from app import call_center

    queues = call_center.build_queues(db, now=_at(day, 10))
    return {g.full_name for q in queues for g in q.guests}


def test_new_guest_waits_for_the_next_reminder_before_calls() -> None:
    """(2026-09-25) מוזמן חדש לא נכנס ישר לשיחות: קודם התזכורת הקרובה, ומשם
    במסלול. גם כשסבב שיחות כבר רץ — הוא מחכה לתזכורת הבאה.

    לוח: W 15/9 · P 17/9 · W 20/9 (12:00) · P 23/9 · W 24/9 · P 28/9.
    """
    db = _db()
    ev = _event(db)
    _guest(db, ev, "ותיק")
    before_call = _guest(db, ev, "לפני השיחות", "0501010101", created=_at(date(2026, 9, 16), 7))
    during_call = _guest(db, ev, "בזמן השיחות", "0502020202", created=_at(date(2026, 9, 17), 7))
    # 20/9 בשעה 10:00 בישראל — לפני יציאת תזכורת 2 (12:00): מקבל אותה.
    before_send = _guest(db, ev, "לפני השליחה", "0503030303", created=_at(date(2026, 9, 20), 7))
    # 20/9 בשעה 15:00 בישראל — אחרי שתזכורת 2 יצאה: מחכה לתזכורת 3.
    after_send = _guest(db, ev, "אחרי השליחה", "0504040404", created=_at(date(2026, 9, 20), 12))

    # המשימה המתוזמנת רצה כרגיל (היא זו שמקבעת את יום תחילת המסלול).
    _run_every_day(db, date(2026, 9, 14), date(2026, 9, 17))
    assert _called_on(db, date(2026, 9, 17)) == {"ותיק"}, _called_on(db, date(2026, 9, 17))
    _run_every_day(db, date(2026, 9, 18), date(2026, 9, 23))
    assert _called_on(db, date(2026, 9, 23)) == {"ותיק", "לפני השיחות", "בזמן השיחות", "לפני השליחה"}
    _run_every_day(db, date(2026, 9, 24), date(2026, 9, 28))
    assert "אחרי השליחה" in _called_on(db, date(2026, 9, 28))
    _run_every_day(db, date(2026, 9, 29), date(2026, 9, 29))
    assert _kinds_for(db, before_call) == ["reminder_2", "final_reminder"]
    assert _kinds_for(db, during_call) == ["reminder_2", "final_reminder"]
    assert _kinds_for(db, before_send) == ["reminder_2", "final_reminder"]
    assert _kinds_for(db, after_send) == ["final_reminder"]
    print("✓ מוזמן חדש: קודם התזכורת הקרובה, ורק אחריה שיחות")


def test_maybe_goes_to_calls_and_answered_leave() -> None:
    """אישר / לא מגיע — יוצאים גם מהשיחות. לא החליט — ממשיך לשיחות. לא ענה — ממשיך."""
    db = _db()
    ev = _event(db)
    for name, status in (("אישר", "confirmed"), ("לא מגיע", "declined"),
                         ("לא החליט", "maybe"), ("לא ענה", "pending")):
        _guest(db, ev, name, status=status)
    _run_every_day(db, date(2026, 9, 14), date(2026, 9, 17))
    assert _called_on(db, date(2026, 9, 17)) == {"לא החליט", "לא ענה"}
    print("✓ לא החליט / לא ענה — לשיחות; אישר / לא מגיע — לא")


def test_track_rounds_are_never_sent_on_friday_or_saturday() -> None:
    """תזכורת 3 בחמישי 24/9, השלב הבא בשני 28/9. אם הריצה של חמישי פוספסה —
    שישי ושבת לא שולחים; ראשון (עדיין בתוך החלון) כן."""
    db = _db()
    ev = _event(db)
    g = _guest(db, ev, "אורח")
    _run_every_day(db, date(2026, 9, 14), date(2026, 9, 23))
    _tick(db, _at(date(2026, 9, 25)))  # שישי
    _tick(db, _at(date(2026, 9, 26)))  # שבת
    assert "final_reminder" not in _kinds_for(db, g), "נשלח בסוף שבוע"
    _tick(db, _at(date(2026, 9, 27)))  # ראשון
    assert _kinds_for(db, g)[-1] == "final_reminder"
    print("✓ שישי/שבת: אין שליחה, גם כשחלון הסבב עובר דרכם")


def test_compressed_track_sends_all_reminders_even_on_call_days() -> None:
    """(2026-09-25) חלון קצר: כל 7 השלבים. תזכורת ושיחה באותו יום — התזכורת
    יוצאת (החלון שלה לא נסגר בגלל השיחה), ומוזמן חדש עדיין מתחיל בתזכורת.

    אירוע שני 21/9, סגירה יום לפני → ראשון 20/9 (5 ימים פעילים):
    W 14 · W 15 · P 16 · W+P 17 · W+P 20.
    """
    db = _db()
    ev = _event(db, event_date="2026-09-21", venue_commit_days_before=1)
    old = _guest(db, ev, "ותיק")
    # חמישי 17/9 10:00 בישראל — לפני תזכורת 2 (12:00): מקבל אותה ונכנס לשיחה שאחריה.
    morning = _guest(db, ev, "בוקר", "0507070707", created=_at(date(2026, 9, 17), 7))
    # חמישי 17/9 15:00 — אחרי התזכורת: מחכה לתזכורת 3 ביום ראשון.
    afternoon = _guest(db, ev, "צהריים", "0508080808", created=_at(date(2026, 9, 17), 12))

    _run_every_day(db, date(2026, 9, 14), date(2026, 9, 17))
    kinds = [p.step["type"] for p in rsvp_timeline.compute_schedule(ev, _at(date(2026, 9, 17))).placements]
    assert kinds == ["whatsapp_first", "reminder", "call_round", "reminder", "call_round",
                     "reminder", "call_round"], kinds
    assert _called_on(db, date(2026, 9, 17)) == {"ותיק", "בוקר"}
    _run_every_day(db, date(2026, 9, 18), date(2026, 9, 20))
    assert "צהריים" in _called_on(db, date(2026, 9, 20))

    assert _kinds_for(db, old) == ["rsvp_request", "reminder_1", "reminder_2", "final_reminder"]
    assert _kinds_for(db, morning) == ["reminder_2", "final_reminder"]
    assert _kinds_for(db, afternoon) == ["final_reminder"]
    print("✓ מסלול דחוס: כל התזכורות יוצאות גם ביום של שיחות; מוזמן חדש — קודם תזכורת")


def test_two_working_days_across_a_weekend_send_every_step() -> None:
    """(2026-09-26) חמישי → סגירה ראשון: 2 ימי עבודה. כל 7 השלבים נשמרים
    (W W P ביום חמישי, W P W P ביום ראשון), ושישי/שבת בלי שליחה."""
    db = _db()
    ev = _event(db, event_date="2026-09-21", venue_commit_days_before=1)  # סגירה ראשון 20/9
    g = _guest(db, ev, "אורח")
    placements = rsvp_timeline.compute_schedule(ev, _at(date(2026, 9, 17))).placements
    assert [(p.step["type"], p.date.day) for p in placements] == [
        ("whatsapp_first", 17), ("reminder", 17), ("call_round", 17),
        ("reminder", 20), ("call_round", 20), ("reminder", 20), ("call_round", 20),
    ]
    # שתי הודעות ביום חמישי: 12:00, והשנייה 3 שעות אחריה (15:00).
    _tick(db, _at(date(2026, 9, 17)))          # 12:30
    assert _kinds_for(db, g) == ["rsvp_request"]
    _tick(db, _at(date(2026, 9, 17), 12))      # 15:30
    assert _kinds_for(db, g) == ["rsvp_request", "reminder_1"]
    for day in (18, 19):                        # שישי, שבת — כל היום
        for hour in (7, 9, 12, 15):
            _tick(db, _at(date(2026, 9, day), hour))
    assert _kinds_for(db, g) == ["rsvp_request", "reminder_1"], "נשלח בסוף שבוע"
    _tick(db, _at(date(2026, 9, 20)))
    _tick(db, _at(date(2026, 9, 20), 12))
    assert _kinds_for(db, g) == ["rsvp_request", "reminder_1", "reminder_2", "final_reminder"]
    assert "אורח" in _called_on(db, date(2026, 9, 20))
    print("✓ 2 ימי עבודה סביב סוף שבוע: כל השלבים, בלי שישי/שבת")


def _il(day: date, hour: int, minute: int = 30) -> datetime:
    """שעה בישראל (שעון קיץ, UTC+3) → הרגע ב-UTC שהמשימה מקבלת."""
    return datetime(day.year, day.month, day.day, hour - 3, minute)


def test_two_whatsapp_messages_on_one_day_are_three_hours_apart() -> None:
    """(2026-09-26) שתי הודעות באותו יום: הראשונה בשעה שנבחרה, השנייה 3 שעות
    אחריה. שעה שנבחרה מאוחרת מ-16:00 — הראשונה ב-16:00 והשנייה ב-19:00, כדי
    ששום הודעה לא תצא בערב."""
    thursday = date(2026, 9, 17)
    for chosen, first_hour, second_hour in (("12:00", 12, 15), ("18:00", 16, 19)):
        db = _db()
        ev = _event(db, event_date="2026-09-21", venue_commit_days_before=1, rsvp_send_time=chosen)
        g = _guest(db, ev, "אורח")
        _tick(db, _il(thursday, first_hour - 1))
        assert _kinds_for(db, g) == [], (chosen, "לפני השעה")
        _tick(db, _il(thursday, first_hour))
        assert _kinds_for(db, g) == ["rsvp_request"], chosen
        _tick(db, _il(thursday, second_hour - 1))
        assert _kinds_for(db, g) == ["rsvp_request"], (chosen, "השנייה לפני 3 שעות")
        _tick(db, _il(thursday, second_hour))
        assert _kinds_for(db, g) == ["rsvp_request", "reminder_1"], chosen
        _tick(db, _il(thursday, 21))
        assert len(_kinds_for(db, g)) == 2
    print("✓ שתי הודעות ביום: 3 שעות ביניהן, ולא אחרי 19:00")


def test_one_working_day_sends_four_messages_spaced_until_seven() -> None:
    """יום עבודה אחד (אירוע מחר): כל 7 השלבים; 4 הודעות WhatsApp — 10:00,
    13:00, 16:00, 19:00, גם כשהשעה שנבחרה מאוחרת יותר."""
    monday = date(2026, 9, 14)
    db = _db()
    ev = _event(db, event_date="2026-09-15", venue_commit_days_before=1)  # סגירה שני 14/9
    g = _guest(db, ev, "אורח")
    kinds = [p.step["type"] for p in rsvp_timeline.compute_schedule(ev, _il(monday, 9)).placements]
    assert kinds == ["whatsapp_first", "reminder", "call_round", "reminder", "call_round",
                     "reminder", "call_round"], kinds
    expected = {10: 1, 12: 1, 13: 2, 15: 2, 16: 3, 18: 3, 19: 4, 21: 4}
    for hour, count in expected.items():
        _tick(db, _il(monday, hour))
        assert len(_kinds_for(db, g)) == count, (hour, _kinds_for(db, g))
    assert _kinds_for(db, g) == ["rsvp_request", "reminder_1", "reminder_2", "final_reminder"]
    print("✓ יום עבודה אחד: 4 הודעות בריווח של 3 שעות, האחרונה ב-19:00")


def test_no_calls_or_messages_on_friday_or_saturday_in_any_window() -> None:
    """לכל אורך חלון — מלא, דחוס (5 ימי עבודה) ומאוד דחוס (2 ימים סביב סוף
    שבוע): אין רשימת שיחות ואין הודעה ביום שישי או שבת. תאריכים מפורשים —
    לא תלוי ביום שבו הבדיקה רצה."""
    from app import call_center

    # (תאריך האירוע, ימי סגירה, היום הראשון שבו המשימה רצה)
    windows = (
        ("2026-09-30", 2, date(2026, 9, 14)),  # מלא: 14 ימים
        ("2026-09-21", 1, date(2026, 9, 14)),  # דחוס: 5 ימי עבודה
        ("2026-09-21", 1, date(2026, 9, 17)),  # חמישי + ראשון בלבד
    )
    for event_date, commit, first_day in windows:
        db = _db()
        ev = _event(db, event_date=event_date, venue_commit_days_before=commit)
        g = _guest(db, ev, "אורח")
        d = first_day
        while d <= date(2026, 9, 29):
            before = len(_kinds_for(db, g))
            for hour in (10, 13, 16, 19):
                _tick(db, _il(d, hour))
            queue = call_center.build_queues(db, now=_il(d, 13))
            if d.weekday() in (4, 5):  # שישי, שבת
                assert len(_kinds_for(db, g)) == before, f"הודעה ב-{d}"
                assert not any(q.round_date == d for q in queue), f"סבב שיחות ב-{d}"
            d += timedelta(days=1)
        assert _kinds_for(db, g), "לא נשלח כלום בכלל"
    print("✓ שישי/שבת: אין הודעה ואין סבב שיחות, בכל אורך חלון")


def test_past_steps_show_their_historical_count() -> None:
    """שלב שעבר מציג כמה באמת היו בו — לא את הסטטוס של היום."""
    from app.routers.automation import _step_history

    db = _db()
    ev = _event(db)
    a = _guest(db, ev, "א", "0501111111")
    _guest(db, ev, "ב", "0502222222")
    _run_every_day(db, date(2026, 9, 14), date(2026, 9, 15))
    a.rsvp_status = "confirmed"  # אישר אחרי שקיבל את הבקשה ואת תזכורת 1
    db.commit()
    guests = list(db.scalars(select(models.Guest).where(models.Guest.event_id == ev.id)).all())
    view = rsvp_timeline.compute_timeline(ev, guests, _at(date(2026, 9, 16)), history=_step_history(db, ev))
    counts = {a_["label"]: a_["audience_count"] for d in view["days"] for a_ in d["actions"]}
    assert counts["בקשת אישור ראשונה ב-WhatsApp"] == 2, counts  # היסטורי
    assert counts["תזכורת ראשונה"] == 2, counts                  # היסטורי
    assert counts["תזכורת שנייה"] == 1, counts                   # עתידי — המצב של היום
    print("✓ שלב שעבר — המספר ההיסטורי; שלב עתידי — המצב העדכני")


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


def test_delivered_invitation_still_counts_as_invited() -> None:
    """הזמנה שעודכנה ל"נמסרה"/"נקראה" עדיין נחשבת כנשלחה — אחרת "הזמנה אחת
    לכל מוזמן" נשברת ברגע שוואטסאפ מחובר, ומסך ההודעות חוזר לאשף."""
    from app import invitations

    db = _db()
    ev = _event(db)
    guests = [_guest(db, ev, f"אורח {i}", f"050111111{i}") for i in range(4)]
    for g, status in zip(guests, ("sent", "delivered", "read", "failed")):
        db.add(models.Message(event_id=ev.id, guest_id=g.id, direction="outbound", kind="invitation",
                              body="הזמנה", channel="whatsapp", status=status))
    db.commit()
    assert invitations.invited_guest_ids(db, ev.id, ev) == {g.id for g in guests[:3]}
    print("✓ הזמנה שנמסרה/נקראה נחשבת כנשלחה; שנכשלה — לא")


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
    test_delivered_invitation_still_counts_as_invited()
    test_new_guest_waits_for_the_next_reminder_before_calls()
    test_maybe_goes_to_calls_and_answered_leave()
    test_track_rounds_are_never_sent_on_friday_or_saturday()
    test_past_steps_show_their_historical_count()
    test_compressed_track_sends_all_reminders_even_on_call_days()
    test_two_working_days_across_a_weekend_send_every_step()
    test_two_whatsapp_messages_on_one_day_are_three_hours_apart()
    test_one_working_day_sends_four_messages_spaced_until_seven()
    test_no_calls_or_messages_on_friday_or_saturday_in_any_window()
    print("\nכל בדיקות המשימה המתוזמנת עברו ✓")
