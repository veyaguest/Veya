"""בדיקות לשעת השליחה של מסלול אישורי-ההגעה (app/communication.py).

התכונה: הזוג בוחר שעה אחת (HH:MM, שעון ישראל, ללא תאריך/אזור-זמן) לכל
הודעות מסלול אישורי-ההגעה (rsvp_request/reminder_1/reminder_2/final_reminder/
event_day), ושעה נפרדת להודעת התודה — שתיהן בטווח 10:00–19:00 בלבד. מסלול
הימים הקיים (``trigger_offset_days``) לא השתנה; רק נוסף לו רכיב שעה. שישי/שבת ממשיכים
לדחות שליחה ליום הפעיל הבא, באמצעות המנגנון הקיים ב-``rsvp_timeline``
(``is_weekend``/``next_active_day``) — לא לוגיקה חדשה.

מכסה בדיוק את מה שהתבקש:
1. טווח השעות המותר (10:00–19:00) — כולל גבולות ופורמטים לא תקינים.
2. הודעת תודה עם שעה נפרדת מהמסלול.
3. שישי/שבת — דחיית שליחה ליום הפעיל הבא, גם כשעוגן ה-offset עצמו נופל
   על סוף השבוע (מ-invited_at) וגם כשתאריך האירוע גורם לכך.
4. שעון קיץ/חורף (DST) — 10:00/19:00 בישראל הם שעות UTC שונות בכל עונה.
5. שליחה כפולה — dedup לפי (event_message_id, guest_id) לא נשבר.

הרצה: ``venv/bin/python tests/test_communication_send_time.py`` (עצמאי, בלי pytest).
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


# ---- עזרי בדיקה קלים (לא-DB) — תואמים ל-_due_now בלי לפתוח session -------

class FakeEvent:
    def __init__(self, **kw):
        self.rsvp_send_time = "12:00"
        self.thank_you_send_time = "12:00"
        self.__dict__.update(kw)


class FakeEventMessage:
    def __init__(self, offset: int):
        self.trigger_offset_days = offset


class FakeGuest:
    def __init__(self, guest_id: int = 1):
        self.id = guest_id


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
# 2. הודעת תודה — שעה נפרדת מהמסלול
# ============================================================================

def test_thank_you_uses_its_own_send_time_not_rsvp_track() -> None:
    ev = FakeEvent(rsvp_send_time="10:00", thank_you_send_time="18:00")
    guest = FakeGuest()
    event_date = date(2026, 9, 8)  # Tuesday — יום אחרי (9/9) גם הוא שלישי-רביעי, לא סופ"ש
    em_thanks = FakeEventMessage(1)  # thank_you: יום אחרי האירוע = 9/9 (רביעי)

    # 09/9 ב-10:00 שעון ישראל (=07:00 UTC בקיץ) — עדיין לפני 18:00 של התודה.
    still_pending = datetime(2026, 9, 9, 7, 0)
    assert c._due_now("thank_you", em_thanks, guest, still_pending, event_date, {}, ev) is False, (
        "תודה לא אמורה להישלח ב-10:00 כשהוגדרה ל-18:00"
    )
    # 09/9 ב-18:00 שעון ישראל (=15:00 UTC בקיץ) — הגיע הזמן.
    due_now = datetime(2026, 9, 9, 15, 0)
    assert c._due_now("thank_you", em_thanks, guest, due_now, event_date, {}, ev) is True

    # לעומת event_day, שממשיך להשתמש בשעת המסלול (10:00) ולא בשעת התודה.
    em_eday = FakeEventMessage(0)
    at_ten = datetime(2026, 9, 8, 7, 0)  # 09/9 עצמו — יום האירוע, 10:00 IL
    assert c._due_now("event_day", em_eday, guest, at_ten, event_date, {}, ev) is True, (
        "event_day משתמש ב-rsvp_send_time (10:00), לא בשעת התודה"
    )
    print("✓ 5: הודעת תודה משתמשת בשעה הנפרדת שלה, שאר המסלול בשעה המשותפת")


def test_changing_rsvp_send_time_does_not_affect_thank_you() -> None:
    """שינוי שעת המסלול לא זולג לשעת התודה — שני שדות עצמאיים לגמרי."""
    ev = FakeEvent(rsvp_send_time="10:00", thank_you_send_time="15:00")
    guest = FakeGuest()
    event_date = date(2026, 9, 8)
    em_thanks = FakeEventMessage(1)

    at_track_hour = datetime(2026, 9, 9, 7, 0)  # 10:00 IL — שעת המסלול, לא שעת התודה
    assert c._due_now("thank_you", em_thanks, guest, at_track_hour, event_date, {}, ev) is False
    at_thanks_hour = datetime(2026, 9, 9, 12, 0)  # 15:00 IL
    assert c._due_now("thank_you", em_thanks, guest, at_thanks_hour, event_date, {}, ev) is True
    print("✓ 6: rsvp_send_time ו-thank_you_send_time עצמאיים זה מזה")


# ============================================================================
# 3. שישי/שבת — דחיית שליחה ליום הפעיל הבא
# ============================================================================

def test_weekend_postpones_event_date_anchored_message() -> None:
    """final_reminder/event_day/thank_you מחושבים מתאריך האירוע — אם התאריך
    שיוצא נופל על שישי/שבת, השליחה נדחית לראשון, לא נשלחת בסופ"ש עצמו."""
    ev = FakeEvent()
    guest = FakeGuest()
    event_date = date(2026, 9, 10)  # חמישי
    em = FakeEventMessage(1)  # event_date + 1 = 11/9 (שישי!)

    friday_noon = datetime(2026, 9, 11, 9, 0)     # 12:00 IL, יום שישי עצמו
    saturday_noon = datetime(2026, 9, 12, 9, 0)   # 12:00 IL, שבת
    sunday_before = datetime(2026, 9, 13, 8, 59)  # 11:59 IL, יום ראשון — עדיין לפני הדחייה
    sunday_after = datetime(2026, 9, 13, 9, 1)    # 12:01 IL, יום ראשון — אחרי הדחייה

    assert c._due_now("final_reminder", em, guest, friday_noon, event_date, {}, ev) is False, (
        "אסור לשלוח בשישי, גם אם הגיע ה-offset"
    )
    assert c._due_now("final_reminder", em, guest, saturday_noon, event_date, {}, ev) is False, (
        "אסור לשלוח בשבת"
    )
    assert c._due_now("final_reminder", em, guest, sunday_before, event_date, {}, ev) is False
    assert c._due_now("final_reminder", em, guest, sunday_after, event_date, {}, ev) is True, (
        "אחרי הדחייה ליום ראשון, בשעה שנבחרה — ההודעה כן יוצאת"
    )
    print("✓ 7: הודעה שמחושבת מתאריך האירוע ונופלת על שישי/שבת נדחית לראשון")


def test_weekend_postpones_rsvp_request_anchored_reminder() -> None:
    """reminder_1/reminder_2 מחושבים מיום **בקשת האישור הראשונה** — אותה
    דחיית סופ"ש חלה גם עליהם, לא רק על השלבים שמחושבים מתאריך האירוע."""
    ev = FakeEvent()
    guest = FakeGuest()
    # בקשת האישור הראשונה נשלחה ביום שלישי 1/9 ב-08:00 UTC = 11:00 IL (קיץ).
    requested_at = {1: datetime(2026, 9, 1, 8, 0)}
    em = FakeEventMessage(3)  # 1/9 + 3 = 4/9, יום שישי!

    friday = datetime(2026, 9, 4, 9, 0)      # שישי עצמו — אסור
    sunday_after = datetime(2026, 9, 6, 9, 1)  # אחרי הדחייה לראשון 6/9, 12:00 IL

    assert c._due_now("reminder_1", em, guest, friday, None, requested_at, ev) is False
    assert c._due_now("reminder_1", em, guest, sunday_after, None, requested_at, ev) is True
    print("✓ 8: תזכורת שמחושבת מבקשת האישור הראשונה ונופלת על שישי נדחית לראשון גם היא")


def test_reminder_not_due_before_rsvp_request_sent() -> None:
    """אין עוגן (בקשת האישור הראשונה עדיין לא נשלחה למוזמן) → התזכורת לא due,
    בלי קשר לכמה זמן עבר. חשוב: ההזמנה יכולה לצאת חודש מראש — היא לא מפעילה
    את שעון התזכורות."""
    ev = FakeEvent()
    guest = FakeGuest()
    em = FakeEventMessage(3)
    way_later = datetime(2027, 1, 1, 12, 0)
    assert c._due_now("reminder_1", em, guest, way_later, None, {}, ev) is False
    print("✓ 8b: תזכורת לא נשלחת לפני שיצאה בקשת אישור ראשונה לאותו מוזמן")


def test_rsvp_request_due_on_schedule_date_not_before() -> None:
    """בקשת האישור הראשונה (rsvp_request) מעוגנת ללוח הזמנים (מועד סגירת
    הרשימה) — לא להיסט ולא לשליחת ההזמנה. due בדיוק ביום/שעה של שלב
    ``whatsapp_first`` בלוח."""
    from app import rsvp_timeline

    ev = FakeEvent(
        event_date="2026-09-30",
        venue_commit_days_before=5,
        # ההזמנה יצאה חודשיים מראש — לא רלוונטי, הלוח עוגן במועד סגירת הרשימה.
        rsvp_track_started_at=datetime(2026, 7, 1),
        rsvp_send_time="12:00",
    )
    guest = FakeGuest()
    em = FakeEventMessage(0)

    request_day = rsvp_timeline.rsvp_request_date(ev)
    assert request_day is not None

    day_before = datetime.combine(request_day, datetime.min.time()) - timedelta(days=1)
    # יום לפני, בכל שעה — עדיין לא.
    assert c._due_now("rsvp_request", em, guest, day_before, None, {}, ev) is False
    # יום השליחה עצמו, 09:00 IL (=06:00/07:00 UTC) — לפני 12:00, עדיין לא.
    early = datetime.combine(request_day, datetime.min.time()).replace(hour=5)
    assert c._due_now("rsvp_request", em, guest, early, None, {}, ev) is False
    # יום השליחה, 12:01 IL — due.
    at_hour = datetime.combine(request_day, datetime.min.time()).replace(hour=10)
    assert c._due_now("rsvp_request", em, guest, at_hour, None, {}, ev) is True
    print("✓ 8c: בקשת אישור ראשונה נשלחת בדיוק ביום/שעה של הלוח, לא לפני")


def test_rsvp_request_not_due_without_commitment_date() -> None:
    """בלי מועד סגירת רשימה אין לוח זמנים — הבקשה הראשונה לא due."""
    ev = FakeEvent(event_date="2026-09-30", venue_commit_days_before=None)
    guest = FakeGuest()
    em = FakeEventMessage(0)
    assert c._due_now("rsvp_request", em, guest, datetime(2026, 9, 20, 12, 0), None, {}, ev) is False
    print("✓ 8d: בלי מועד סגירת רשימה — בקשת אישור ראשונה לא נכנסת לתור")


def test_weekday_message_not_affected_by_weekend_logic() -> None:
    """יום חול רגיל — אין דחייה, ההודעה יוצאת בדיוק בשעה שנבחרה."""
    ev = FakeEvent(rsvp_send_time="12:00")
    guest = FakeGuest()
    event_date = date(2026, 9, 8)  # שלישי
    em = FakeEventMessage(0)  # יום האירוע עצמו — שלישי, לא סופ"ש

    before = datetime(2026, 9, 8, 8, 59)  # 11:59 IL
    after = datetime(2026, 9, 8, 9, 1)    # 12:01 IL
    assert c._due_now("event_day", em, guest, before, event_date, {}, ev) is False
    assert c._due_now("event_day", em, guest, after, event_date, {}, ev) is True
    print("✓ 9: יום חול רגיל לא מושפע מלוגיקת סוף השבוע")


# ============================================================================
# 4. שעון קיץ/חורף (DST)
# ============================================================================

def test_dst_summer_offset() -> None:
    """קיץ בישראל = UTC+3. 10:00 IL = 07:00 UTC."""
    ev = FakeEvent(rsvp_send_time="10:00")
    guest = FakeGuest()
    event_date = date(2026, 7, 1)  # רביעי — לא סופ"ש
    em = FakeEventMessage(0)

    before = datetime(2026, 7, 1, 6, 59)  # 09:59 IL
    after = datetime(2026, 7, 1, 7, 1)    # 10:01 IL
    assert c._due_now("event_day", em, guest, before, event_date, {}, ev) is False
    assert c._due_now("event_day", em, guest, after, event_date, {}, ev) is True
    print("✓ 10: קיץ (UTC+3) — 10:00 שעון ישראל = 07:00 UTC בדיוק")


def test_dst_winter_offset() -> None:
    """חורף בישראל = UTC+2. 10:00 IL = 08:00 UTC — שעה שונה מקיץ לאותה שעת קיר."""
    ev = FakeEvent(rsvp_send_time="10:00")
    guest = FakeGuest()
    event_date = date(2026, 1, 6)  # שלישי — לא סופ"ש
    em = FakeEventMessage(0)

    before = datetime(2026, 1, 6, 7, 59)  # 09:59 IL
    after = datetime(2026, 1, 6, 8, 1)    # 10:01 IL
    assert c._due_now("event_day", em, guest, before, event_date, {}, ev) is False
    assert c._due_now("event_day", em, guest, after, event_date, {}, ev) is True
    print("✓ 11: חורף (UTC+2) — 10:00 שעון ישראל = 08:00 UTC (שעה אחרת מקיץ לאותו 10:00)")


def test_scheduled_moment_matches_israel_wall_clock_both_seasons() -> None:
    """אותה שעת קיר (12:00) חייבת להיות תלויה בעונה כשמשווים ל-UTC."""
    winter = c._scheduled_moment(date(2026, 1, 6), "12:00")  # לא סופ"ש
    summer = c._scheduled_moment(date(2026, 7, 1), "12:00")  # לא סופ"ש
    assert winter.utcoffset().total_seconds() / 3600 == 2, "חורף חייב להיות UTC+2"
    assert summer.utcoffset().total_seconds() / 3600 == 3, "קיץ חייב להיות UTC+3"
    assert winter.hour == 12 and summer.hour == 12, "שעון הקיר נשאר 12:00 בשתי העונות"
    print("✓ 12: שעון הקיר (12:00) זהה בשתי העונות, אבל היסט ה-UTC משתנה כמצופה")


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
        **kw,
    )
    db.add(ev)
    db.commit()
    return ev


def _make_guest(db: Session, event_id: int, phone: str = "0501234567") -> models.Guest:
    g = models.Guest(event_id=event_id, full_name="מוזמן בדיקה", phone=phone, side="groom")
    db.add(g)
    db.commit()
    return g


def test_due_message_not_sent_twice() -> None:
    """קריאה כפולה ל-compute_due_messages/send_due_messages לאותו מוזמן לא
    יוצרת הודעה כפולה — בדיוק כמו advance_track שנקרא בכל טעינת מסך."""
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
    הראשונה נספרת ``+3`` ימים **ממנה** — לא משליחת ההזמנה (שיצאה חודשיים
    מראש)."""
    from app import rsvp_timeline

    db = _fresh_session()
    ev = _make_event(db, venue_commit_days_before=5, rsvp_track_active=True)
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

    # 3 ימי-עבודה אחרי הבקשה (עם דחיית סופ"ש) — התזכורת הראשונה due.
    trigger_day = rsvp_timeline.next_active_day(request_day + timedelta(days=3))
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
    test_weekend_postpones_event_date_anchored_message()
    test_weekend_postpones_rsvp_request_anchored_reminder()
    test_reminder_not_due_before_rsvp_request_sent()
    test_rsvp_request_due_on_schedule_date_not_before()
    test_rsvp_request_not_due_without_commitment_date()
    test_weekday_message_not_affected_by_weekend_logic()
    test_dst_summer_offset()
    test_dst_winter_offset()
    test_scheduled_moment_matches_israel_wall_clock_both_seasons()
    test_due_message_not_sent_twice()
    test_message_not_due_before_scheduled_hour_even_on_repeated_calls()
    test_rsvp_request_then_reminders_chain_end_to_end()
    print("\nכל בדיקות שעת השליחה עברו ✓")
