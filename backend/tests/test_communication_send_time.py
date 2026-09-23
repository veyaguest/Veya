"""בדיקות לשעת השליחה ולחלון השליחה של מסלול אישורי-ההגעה (app/communication.py).

מ-2026-09-23: לכל סבב שעה משלו (``EventMessage.send_time``), ובלי שעה —
שעת ברירת המחדל של האירוע (המסלול/יום האירוע: ``rsvp_send_time``; התודה:
``thank_you_send_time``). התאריך נקבע תמיד ע"י לוח הזמנים. כל הודעה נשלחת
רק בחלון שלה (``send_window``) — אין שליחה בדיעבד.

מכסה:
1. טווח השעות המותר (10:00–19:00) — כולל גבולות ופורמטים לא תקינים.
2. הודעת תודה עם שעה נפרדת; שעה לכל סבב גוברת על ברירת המחדל.
3. שישי/שבת — הודעות יום האירוע/תודה נדחות ליום הפעיל הבא.
4. שעון קיץ/חורף (DST).
5. חלון השליחה: לא לפני השעה, ולא אחרי שהשלב הבא התחיל.
6. שליחה כפולה — dedup לפי (event_message_id, guest_id) לא נשבר.

הרצה: ``venv/bin/python tests/test_communication_send_time.py`` (עצמאי, או pytest).
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import communication as c  # noqa: E402
from app import models  # noqa: E402
from app.database import Base  # noqa: E402


# ---- עזרי בדיקה קלים (בלי DB) ----------------------------------------------

def _event(**kw) -> models.Event:
    base = dict(
        event_type="wedding", event_date="2026-09-08", rsvp_send_time="12:00",
        thank_you_send_time="12:00", venue_commit_days_before=None,
        rsvp_track_active=False, rsvp_track_started_at=None,
    )
    base.update(kw)
    return models.Event(**base)


def _em(message_type: str, offset: int = 0, send_time=None) -> models.EventMessage:
    return models.EventMessage(
        message_type=message_type, trigger_offset_days=offset, send_time=send_time,
    )


def _due(message_type: str, em: models.EventMessage, now: datetime, ev) -> bool:
    """האם ההודעה בחלון השליחה שלה ברגע ``now`` (UTC נאיבי)."""
    window = c.send_window(message_type, em, ev, now)
    if window is None:
        return False
    return window[0] <= c.now_in_israel(now) < window[1]


# ============================================================================
# 1. טווח השעות המותר (10:00–19:00)
# ============================================================================

def test_send_time_boundaries_are_inclusive() -> None:
    assert c.validate_send_time("10:00") == "10:00", "10:00 הוא הגבול התחתון — חייב להתקבל"
    assert c.validate_send_time("19:00") == "19:00", "19:00 הוא הגבול העליון — חייב להתקבל"
    assert c.validate_send_time("14:37") == "14:37", "שעה אמצעית תקינה"
    print("✓ 1: גבולות הטווח (10:00 ו-19:00) מתקבלים בדיוק")


def test_send_time_outside_range_rejected() -> None:
    for bad in ("09:59", "00:00", "19:01", "23:59", "06:30"):
        try:
            c.validate_send_time(bad)
            raise AssertionError(f"{bad} היה אמור להידחות (מחוץ ל-10:00–19:00)")
        except ValueError:
            pass
    print("✓ 2: שעות מחוץ לטווח 10:00–19:00 נדחות")


def test_send_time_bad_format_rejected() -> None:
    for bad in ("", "10", "10:0", "25:00", "10:60", "בוקר", "10:00:00", "10-00"):
        try:
            c.validate_send_time(bad)
            raise AssertionError(f"'{bad}' היה אמור להידחות (פורמט לא תקין)")
        except ValueError:
            pass
    print("✓ 3: פורמטים לא תקינים (ריק/חסר אפסים/שעה>23/דקה>59/מילה) נדחים")


def test_default_send_time_is_within_allowed_range() -> None:
    """ברירת המחדל למשתמשים קיימים/חדשים חייבת להיות שעה בטוחה בתוך הטווח."""
    assert c.validate_send_time(c.DEFAULT_SEND_TIME) == c.DEFAULT_SEND_TIME
    print(f"✓ 4: ברירת המחדל ({c.DEFAULT_SEND_TIME}) בטוחה בתוך 10:00–19:00")


# ============================================================================
# 2. הודעת תודה — שעה נפרדת; שעה לכל סבב
# ============================================================================

def test_thank_you_uses_its_own_send_time_not_rsvp_track() -> None:
    ev = _event(event_date="2026-09-08", rsvp_send_time="10:00", thank_you_send_time="18:00")
    em_thanks = _em("thank_you", 1)  # יום אחרי האירוע = 9/9 (רביעי)

    still_pending = datetime(2026, 9, 9, 7, 0)  # 10:00 IL
    assert _due("thank_you", em_thanks, still_pending, ev) is False, (
        "תודה לא אמורה להישלח ב-10:00 כשהוגדרה ל-18:00"
    )
    assert _due("thank_you", em_thanks, datetime(2026, 9, 9, 15, 0), ev) is True  # 18:00 IL

    em_eday = _em("event_day", 0)
    assert _due("event_day", em_eday, datetime(2026, 9, 8, 7, 0), ev) is True, (
        "event_day משתמש בשעת המסלול (10:00), לא בשעת התודה"
    )
    print("✓ 5: הודעת תודה משתמשת בשעה הנפרדת שלה, שאר המסלול בשעה המשותפת")


def test_changing_rsvp_send_time_does_not_affect_thank_you() -> None:
    ev = _event(event_date="2026-09-08", rsvp_send_time="10:00", thank_you_send_time="15:00")
    em_thanks = _em("thank_you", 1)
    assert _due("thank_you", em_thanks, datetime(2026, 9, 9, 7, 0), ev) is False
    assert _due("thank_you", em_thanks, datetime(2026, 9, 9, 12, 0), ev) is True
    print("✓ 6: rsvp_send_time ו-thank_you_send_time עצמאיים זה מזה")


def test_round_send_time_overrides_event_default() -> None:
    """(14) שינוי שעת שליחה: שעה של סבב גוברת על ברירת המחדל של האירוע —
    והתאריך לא זז. ``None`` = חזרה לברירת המחדל."""
    ev = _event(event_date="2026-09-08", rsvp_send_time="10:00")
    em = _em("event_day", 0, send_time="17:30")
    assert c.effective_send_time(ev, em) == "17:30"
    assert _due("event_day", em, datetime(2026, 9, 8, 7, 30), ev) is False  # 10:30 IL
    assert _due("event_day", em, datetime(2026, 9, 8, 14, 31), ev) is True  # 17:31 IL
    em.send_time = None
    assert c.effective_send_time(ev, em) == "10:00"
    assert _due("event_day", em, datetime(2026, 9, 8, 7, 30), ev) is True

    # סבב WhatsApp: אותו יום בלוח, שעה אחרת.
    full = _event(event_date="2026-10-14", venue_commit_days_before=5,
                  rsvp_track_started_at=datetime(2026, 9, 1), rsvp_send_time="12:00")
    req_early = _em("rsvp_request")
    req_late = _em("rsvp_request", send_time="18:00")
    a = c.send_window("rsvp_request", req_early, full)
    b = c.send_window("rsvp_request", req_late, full)
    assert a[0].date() == b[0].date(), "שינוי שעה הזיז את התאריך"
    assert (a[0].hour, b[0].hour) == (12, 18)
    print("✓ 6b: שעה לכל סבב גוברת על ברירת המחדל, בלי להזיז את התאריך")


# ============================================================================
# 3. שישי/שבת
# ============================================================================

def test_weekend_postpones_event_date_anchored_message() -> None:
    """תודה שנופלת בשישי נדחית לראשון — ונשלחת רק באותו יום (לא בדיעבד)."""
    ev = _event(event_date="2026-09-10")  # חמישי → תודה בשישי 11/9
    em = _em("thank_you", 1)
    assert _due("thank_you", em, datetime(2026, 9, 11, 9, 0), ev) is False, "אסור לשלוח בשישי"
    assert _due("thank_you", em, datetime(2026, 9, 12, 9, 0), ev) is False, "אסור לשלוח בשבת"
    assert _due("thank_you", em, datetime(2026, 9, 13, 8, 59), ev) is False
    assert _due("thank_you", em, datetime(2026, 9, 13, 9, 1), ev) is True
    assert _due("thank_you", em, datetime(2026, 9, 14, 9, 1), ev) is False, (
        "יום אחרי החלון — לא שולחים בדיעבד"
    )
    print("✓ 7: תודה שנופלת בסופ\"ש נדחית לראשון, ורק לאותו יום")


def test_whatsapp_rounds_follow_the_schedule_and_window() -> None:
    """(5) כל סבב WhatsApp בתאריך שלו בלוח, בשעה שנבחרה, ורק עד שמתחיל השלב
    הבא — אף פעם לא בסופ\"ש ולא אחרי יום הסגירה."""
    from app import rsvp_timeline

    ev = _event(event_date="2026-10-14", venue_commit_days_before=5,
                rsvp_track_started_at=datetime(2026, 9, 1), rsvp_send_time="12:00")
    schedule = rsvp_timeline.compute_schedule(ev)
    rounds = rsvp_timeline.whatsapp_rounds(ev)
    assert [r.message_type for r in rounds] == ["rsvp_request", "reminder_1", "reminder_2", "final_reminder"]
    for r in rounds:
        assert not rsvp_timeline.is_weekend(r.day) and r.day <= schedule.commitment_date
        em = _em(r.message_type)
        day_before = datetime.combine(r.day, datetime.min.time()).replace(hour=8, minute=59)  # 11:59 IL
        at_time = datetime.combine(r.day, datetime.min.time()).replace(hour=9, minute=1)      # 12:01 IL
        after_window = datetime.combine(r.until, datetime.min.time()).replace(hour=9, minute=1)
        assert _due(r.message_type, em, day_before, ev) is False
        assert _due(r.message_type, em, at_time, ev) is True
        assert _due(r.message_type, em, after_window, ev) is False, f"{r.message_type}: נשלח בדיעבד"
    print("✓ 8: סבבי WhatsApp בתאריכי הלוח, בשעה שנבחרה, ורק בחלון שלהם")


def test_round_cut_by_short_window_has_no_window() -> None:
    """חלון קצר → פחות סבבים. סבב שלא נכנס ללוח — אין לו חלון, והוא לא נשלח."""
    ev = _event(event_date="2026-09-20", venue_commit_days_before=2,  # סגירה חמישי 17/9
                rsvp_track_started_at=datetime(2026, 9, 14, 7, 0))    # שני
    from app import rsvp_timeline

    types = [r.message_type for r in rsvp_timeline.whatsapp_rounds(ev)]
    assert types == ["rsvp_request"], types
    assert c.send_window("reminder_1", _em("reminder_1"), ev) is None
    assert c.send_window("final_reminder", _em("final_reminder"), ev) is None
    print("✓ 8c: סבב שלא נכנס ללוח הקצר לא נשלח")


def test_rsvp_request_window_needs_a_schedule() -> None:
    """אירוע רחוק בלי מועד סגירה — אין לוח ואין חלון לבקשה הראשונה."""
    far = _event(event_date="2026-10-30")
    assert c.send_window("rsvp_request", _em("rsvp_request"), far, datetime(2026, 9, 20, 12)) is None
    print("✓ 8d: אין מועד סגירה (אירוע רחוק) — אין חלון לבקשה הראשונה")


def test_weekday_message_not_affected_by_weekend_logic() -> None:
    ev = _event(event_date="2026-09-08", rsvp_send_time="12:00")  # שלישי
    em = _em("event_day", 0)
    assert _due("event_day", em, datetime(2026, 9, 8, 8, 59), ev) is False
    assert _due("event_day", em, datetime(2026, 9, 8, 9, 1), ev) is True
    print("✓ 9: יום חול רגיל לא מושפע מלוגיקת סוף השבוע")


# ============================================================================
# 4. שעון קיץ/חורף (DST)
# ============================================================================

def test_dst_summer_offset() -> None:
    ev = _event(event_date="2026-07-01", rsvp_send_time="10:00")  # רביעי
    em = _em("event_day", 0)
    assert _due("event_day", em, datetime(2026, 7, 1, 6, 59), ev) is False
    assert _due("event_day", em, datetime(2026, 7, 1, 7, 1), ev) is True
    print("✓ 10: קיץ (UTC+3) — 10:00 שעון ישראל = 07:00 UTC בדיוק")


def test_dst_winter_offset() -> None:
    ev = _event(event_date="2026-01-06", rsvp_send_time="10:00")  # שלישי
    em = _em("event_day", 0)
    assert _due("event_day", em, datetime(2026, 1, 6, 7, 59), ev) is False
    assert _due("event_day", em, datetime(2026, 1, 6, 8, 1), ev) is True
    print("✓ 11: חורף (UTC+2) — 10:00 שעון ישראל = 08:00 UTC")


def test_scheduled_moment_matches_israel_wall_clock_both_seasons() -> None:
    winter = c._scheduled_moment(date(2026, 1, 6), "12:00")
    summer = c._scheduled_moment(date(2026, 7, 1), "12:00")
    assert winter.utcoffset().total_seconds() / 3600 == 2, "חורף חייב להיות UTC+2"
    assert summer.utcoffset().total_seconds() / 3600 == 3, "קיץ חייב להיות UTC+3"
    assert winter.hour == 12 and summer.hour == 12
    print("✓ 12: שעון הקיר (12:00) זהה בשתי העונות, היסט ה-UTC משתנה כמצופה")


# ============================================================================
# 5. שליחה כפולה (dedup) — עם DB אמיתי
# ============================================================================

def _fresh_session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _make_event(db: Session, **kw) -> models.Event:
    ev = models.Event(
        groom_name="יואב", bride_name="דנה", event_type="wedding",
        event_date="2026-09-08", rsvp_send_time="10:00", thank_you_send_time="10:00",
        **{"venue_commit_days_before": 2, **kw},
    )
    db.add(ev)
    db.commit()
    return ev


def _make_guest(db: Session, event_id: int, phone: str = "0501234567") -> models.Guest:
    g = models.Guest(event_id=event_id, full_name="מוזמן בדיקה", phone=phone, side="groom",
                     created_at=datetime(2026, 1, 1))
    db.add(g)
    db.commit()
    return g


def test_due_message_not_sent_twice() -> None:
    """(17) קריאה כפולה ל-compute_due_messages/send_due_messages לאותו מוזמן
    לא יוצרת הודעה כפולה — כמו שתי ריצות של המשימה המתוזמנת."""
    db = _fresh_session()
    ev = _make_event(db)
    g = _make_guest(db, ev.id)

    em = models.EventMessage(
        event_id=ev.id, message_type="event_day",
        content="שלום {{guest_name}}, מחכים לך היום!",
        is_active=True, trigger_offset_days=0, target_audience="all",
    )
    db.add(em)
    db.commit()

    now = datetime(2026, 9, 8, 8, 0)  # 08/9 11:00 IL — אחרי 10:00, יום חול

    actions = c.compute_due_messages(db, ev, now=now)
    assert len(actions) == 1, f"ציפינו לפעולה אחת בתור, קיבלנו {len(actions)}"
    result = c.send_due_messages(db, ev, actions)
    db.commit()
    assert result["sent"] == 1

    # קריאה שנייה, אותו רגע בדיוק (בדיוק כמו רענון מסך חוזר) — אסור שתיצור עוד הודעה.
    actions_again = c.compute_due_messages(db, ev, now=now)
    assert actions_again == [], "מוזמן שכבר קיבל את ההודעה לא אמור לחזור לתור"

    sent_rows = [
        m for m in db.query(models.Message)
        .filter(models.Message.event_id == ev.id, models.Message.guest_id == g.id)
        .all()
    ]
    assert len(sent_rows) == 1, f"נוצרה יותר מהודעה אחת: {len(sent_rows)}"
    print("✓ 13: קריאה כפולה ל-compute_due_messages לא שולחת את אותה הודעה פעמיים")


def test_message_not_due_before_scheduled_hour_even_on_repeated_calls() -> None:
    """קריאה חוזרת *לפני* שעת השליחה לא מוציאה כלום מהתור, בלי קשר לכמות
    הקריאות — השעה היא שער אמיתי, לא רק בדיקה חד-פעמית."""
    db = _fresh_session()
    ev = _make_event(db)
    _make_guest(db, ev.id)

    em = models.EventMessage(
        event_id=ev.id, message_type="event_day",
        content="שלום {{guest_name}}!",
        is_active=True, trigger_offset_days=0, target_audience="all",
    )
    db.add(em)
    db.commit()

    too_early = datetime(2026, 9, 8, 6, 0)  # 09:00 IL — לפני 10:00
    for _ in range(3):
        assert c.compute_due_messages(db, ev, now=too_early) == []
    print("✓ 14: לפני השעה שנקבעה — התור נשאר ריק גם בקריאות חוזרות")


def test_rsvp_request_then_reminders_chain_end_to_end() -> None:
    """שרשרת מלאה מול DB: בקשת האישור הראשונה יוצאת בתאריך הלוח, והתזכורת
    הראשונה יוצאת בתאריך שלה בלוח — לא משליחת הזמנה, ובלי שהאירוע "הופעל"."""
    from app import rsvp_timeline

    db = _fresh_session()
    ev = _make_event(db, venue_commit_days_before=5)
    ev.event_date = "2026-09-30"
    ev.rsvp_send_time = "12:00"
    ev.rsvp_track_started_at = datetime(2026, 7, 1)  # ההזמנה יצאה חודשיים מראש
    db.commit()
    _make_guest(db, ev.id)
    db.add_all([
        models.EventMessage(
            event_id=ev.id, message_type="rsvp_request",
            content="היי {{guest_name}}, נשמח לאישור הגעה 🙏",
            is_active=True, trigger_offset_days=0, target_audience="pending",
        ),
        models.EventMessage(
            event_id=ev.id, message_type="reminder_1",
            content="היי {{guest_name}}, תזכורת קטנה 🙂",
            is_active=True, trigger_offset_days=3, target_audience="pending",
        ),
    ])
    db.commit()

    request_day = rsvp_timeline.rsvp_request_date(ev)
    assert request_day is not None

    # לפני תאריך הלוח — שום דבר בתור (גם לא תזכורת, למרות שחודשיים עברו מ"ההזמנה").
    before = datetime.combine(request_day, datetime.min.time()) - timedelta(days=2)
    assert c.compute_due_messages(db, ev, now=before) == []

    # תאריך הלוח, 12:00+ IL — בקשת האישור הראשונה בתור. שולחים.
    at_request = datetime.combine(request_day, datetime.min.time()).replace(hour=10)
    actions = c.compute_due_messages(db, ev, now=at_request)
    assert [a.event_message.message_type for a in actions] == ["rsvp_request"]
    assert c.send_due_messages(db, ev, actions)["sent"] == 1
    # ``send_due_messages`` לא מקבל ``now`` — מקבעים את חותמת השליחה לרגע
    # הבדיקה כדי שעיגון התזכורת יימדד ממנה.
    db.query(models.Message).filter(models.Message.kind == "rsvp_request").update(
        {models.Message.created_at: at_request}
    )
    db.commit()

    # מיד אחרי — התזכורת עדיין לא due (0 ימים מהבקשה).
    assert c.compute_due_messages(db, ev, now=at_request) == []

    # בתאריך התזכורת הראשונה בלוח — התזכורת הראשונה due.
    trigger_day = rsvp_timeline.reminder_date(ev, 1)
    at_reminder = datetime.combine(trigger_day, datetime.min.time()).replace(hour=10)
    later = c.compute_due_messages(db, ev, now=at_reminder)
    assert [a.event_message.message_type for a in later] == ["reminder_1"]
    print("✓ 15: בקשת אישור ראשונה → תזכורת ראשונה, מעוגנות ללוח ולא להזמנה")


if __name__ == "__main__":
    test_send_time_boundaries_are_inclusive()
    test_send_time_outside_range_rejected()
    test_send_time_bad_format_rejected()
    test_default_send_time_is_within_allowed_range()
    test_thank_you_uses_its_own_send_time_not_rsvp_track()
    test_changing_rsvp_send_time_does_not_affect_thank_you()
    test_round_send_time_overrides_event_default()
    test_weekend_postpones_event_date_anchored_message()
    test_whatsapp_rounds_follow_the_schedule_and_window()
    test_round_cut_by_short_window_has_no_window()
    test_rsvp_request_window_needs_a_schedule()
    test_weekday_message_not_affected_by_weekend_logic()
    test_dst_summer_offset()
    test_dst_winter_offset()
    test_scheduled_moment_matches_israel_wall_clock_both_seasons()
    test_due_message_not_sent_twice()
    test_message_not_due_before_scheduled_hour_even_on_repeated_calls()
    test_rsvp_request_then_reminders_chain_end_to_end()
    print("\nכל בדיקות שעת השליחה עברו ✓")
