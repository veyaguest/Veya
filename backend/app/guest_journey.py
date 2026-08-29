"""מנוע מסע האורח — איזו פעולה פתוחה למוזמן, ומתי.

הקישור של המוזמן (``/confirm/{token}``) קבוע לכל אורך חיי האירוע ולעולם לא
מתחלף. מה שמשתנה לאורך הדרך זה **אילו פעולות פתוחות בו**, והמודול הזה הוא
מקור-האמת היחיד לכך.

שני כללי ברזל:

1. **השרת מחליט, לא הדפדפן.** ה-Frontend רק מצייר את מה שהוא מקבל. אין
   שום חישוב זמינות בצד לקוח — שעון המכשיר של המוזמן אינו מקור אמת.
2. **``?action=`` הוא ניתוב, לא הרשאה.** הפרמטר אומר "לאן לגלול/מה לפתוח",
   והוא נבדק *מול* הזמינות ולא במקומה. מוזמן שינחש ``?action=gift`` שבוע
   לפני האירוע לא יקבל כלום, כי ``gift`` יחזור ``False`` מכאן.

מי שיבנה בעתיד נקודת קצה אמיתית למתנה חייב לקרוא ל-``assert_action_allowed``
לפני כל פעולה — זו נקודת האכיפה, לא ה-UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from fastapi import HTTPException

from app import gift_eligibility, models, rsvp_timeline
from app.automation import parse_event_date
from app.call_center import LOCAL_TIMEZONE

# ── חלון המתנה ───────────────────────────────────────────────────────────
# החלטת בעלים (2026-08-24): החלון הוא **טווח זמן רציף**, לא טווח תאריכים.
#
#     נפתח:  3 ימים לפני האירוע, בשעה 00:00 שעון ישראל
#     נסגר:  היום שאחרי האירוע,  בשעה 10:00 שעון ישראל
#
#     המתנה פתוחה  ⟺  opens_at <= now(Asia/Jerusalem) < closes_at
#
# הטווח **חצי-פתוח** בכוונה: 10:00:00 בדיוק כבר סגור, כדי שלא יהיה רגע
# דו-משמעי אחד. לאירוע ב-12/11:
#
#   08/11 (כל היום)   → סגור
#   09/11 00:00       → נפתח
#   10/11, 11/11      → פתוח
#   12/11 (יום האירוע)→ פתוח
#   13/11 09:59       → פתוח   ← "בוקר אחרי" — מי שלא הספיק בערב
#   13/11 10:00       → סגור
#
# למה הסגירה היא לפי *שעה* ולא לפי תאריך: אורחים שולחים מתנה גם בדרך הביתה
# מהאירוע ובבוקר שאחריו. סגירה בחצות הייתה חותכת בדיוק את החלון הזה.
# הפתיחה נשארה לפי תאריך (00:00) כי "שלושה ימים לפני" היא איך שאנשים
# חושבים, ולא רוצים שהמתנה תיפתח בשעה אקראית שתלויה בשעת החופה.
GIFT_WINDOW_DAYS = 3

# השעה שבה החלון נסגר, ביום שאחרי האירוע (שעון ישראל).
GIFT_CLOSE_HOUR = 10




def _israel_tz():
    """אזור הזמן של ישראל, או ``None`` אם אין מסד אזורי זמן בסביבה."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(LOCAL_TIMEZONE)
    except Exception:  # pragma: no cover - תלוי סביבה
        return None


def israel_timezone():
    """גרסה ציבורית של ``_israel_tz`` — לשימוש חוצה-מודולים (למשל תזמון שעת
    שליחה ב-``communication.py``) שצריך לבנות רגע-יעד בשעון ישראל, לא רק
    להמיר רגע קיים אליו כמו ``now_in_israel``."""
    return _israel_tz()


def now_in_israel(now: datetime | None = None) -> datetime:
    """הרגע הנוכחי בשעון ישראל.

    לא ``datetime.utcnow()``: ישראל מקדימה את UTC בשעתיים (חורף) או שלוש
    (קיץ). כל חישוב שנוגע בשעה — ובראשו סגירת המתנה ב-10:00 — חייב לרוץ
    על השעון המקומי, אחרת הוא נופל בשעה הלא נכונה חצי שנה בשנה.

    ``now`` (ב-UTC) קיים כדי שאפשר יהיה לבדוק גבולות בלי לחכות לשעה אמיתית
    — בדיוק כמו ``now`` ב-``compute_due_messages`` וב-``build_queues``.
    """
    moment = now or datetime.utcnow()
    tz = _israel_tz()
    if tz is None:
        # בלי מסד אזורי זמן נשארים ב-UTC (פער של עד 3 שעות). מוסר במפורש
        # את ה-tzinfo כדי שההשוואות למטה יישארו בין שני ערכים נאיביים.
        return moment.replace(tzinfo=None)
    aware = moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment
    return aware.astimezone(tz)


def today_in_israel(now: datetime | None = None) -> date:
    """התאריך הנוכחי בישראל (נגזר מ-``now_in_israel``)."""
    return now_in_israel(now).date()


def _israel_moment(day: date, hour: int) -> datetime:
    """חותמת זמן בשעון ישראל ליום ולשעה נתונים (00:00 / 10:00 של החלון)."""
    stamp = datetime.combine(day, time(hour=hour))
    tz = _israel_tz()
    return stamp.replace(tzinfo=tz) if tz is not None else stamp


def gift_window_bounds(event: models.Event) -> tuple[datetime, datetime] | None:
    """גבולות חלון המתנה בשעון ישראל: ``(נפתח, נסגר)``.

    מוחזר גם כשהחלון כבר עבר או עוד לא התחיל — זו פונקציה של תאריך האירוע
    בלבד. ``None`` רק כשאין תאריך תקין לאירוע.
    """
    event_date = parse_event_date(event.event_date)
    if event_date is None:
        return None
    opens = _israel_moment(event_date - timedelta(days=GIFT_WINDOW_DAYS), 0)
    closes = _israel_moment(event_date + timedelta(days=1), GIFT_CLOSE_HOUR)
    return opens, closes


def days_until_event(event: models.Event, *, today: date | None = None) -> int | None:
    """כמה ימי לוח נשארו עד האירוע. שלילי = האירוע כבר עבר. ``None`` = אין תאריך."""
    event_date = parse_event_date(event.event_date)
    if event_date is None:
        return None
    return (event_date - (today or today_in_israel())).days


def gift_is_open(event: models.Event, *, now: datetime | None = None) -> bool:
    """האם אזור המתנה פתוח למוזמן כרגע.

    שני תנאים, וכל אחד מהם עומד בפני עצמו:

    1. **האירוע זכאי לשירות** — ``gift_eligibility.is_eligible``, מקור
       האמת היחיד לשאלה הזו. הבדיקה **אינה** משוכפלת לכאן; כשתחובר
       מערכת חבילות, המסך הזה יתעדכן מאליו.
    2. **חלון המתנה פתוח** — חישוב זמן טהור, שאינו תלוי בזכאות ולכן
       ניתן לבדיקה ולנימוק בנפרד (``gift_window_is_open``).
    """
    if not gift_eligibility.is_eligible(event):
        return False
    return gift_window_is_open(event, now=now)


def gift_window_is_open(event: models.Event, *, now: datetime | None = None) -> bool:
    """חלון המתנה בלבד — בלי מתג הפיצ'ר.

    מופרד מ-``gift_is_open`` כדי שהחלון עצמו יהיה ניתן לבדיקה ולנימוק
    בנפרד מהשאלה "האם הפיצ'ר שוחרר". זו הפונקציה שמגלמת את ההגדרה
    שמתועדת למעלה: ``opens_at <= now < closes_at``.

    שים לב שהסגירה **אינה** נשענת יותר על ``call_center.event_has_ended``
    (שסוגר בחצות): החלטת הבעלים היא שהמתנה נשארת פתוחה עד 10:00 בבוקר
    שאחרי, ולכן יש כאן גבול סגירה מפורש משלה.
    """
    bounds = gift_window_bounds(event)
    if bounds is None:
        return False           # בלי תאריך אי אפשר לדעת — ולכן סגור
    opens, closes = bounds
    return opens <= now_in_israel(now) < closes


def rsvp_open_date(event: models.Event | None, *, now: datetime | None = None):
    """התאריך שבו אישורי ההגעה נפתחים למוזמן, או ``None`` אם עדיין לא ידוע.

    **מקור האמת: לוח הזמנים של האירוע** (``rsvp_timeline.compute_schedule``,
    שעוגנו מועד סגירת רשימת המוזמנים). אישורי ההגעה נפתחים בדיוק ביום שבו
    יוצאת **בקשת האישור הראשונה** (``whatsapp_first``) לפי אותו לוח — לא לפי
    תאריך שליחת ההזמנה. ההזמנה יכולה לצאת חודש מראש בלי לפתוח כלום; בקשת
    האישור הראשונה היא הרגע שבו האורח מתבקש לראשונה לאשר, ולכן גם הרגע שבו
    כפתור אישור ההגעה נפתח.
    """
    if event is None:
        return None
    # בלי מועד סגירת רשימה (או תאריך אירוע) אין לוח זמנים ואין מה לפתוח.
    return rsvp_timeline.rsvp_request_date(event, now)


def rsvp_is_open(event: models.Event | None, *, now: datetime | None = None) -> bool:
    """האם המוזמן יכול לאשר הגעה כרגע.

    אישורי ההגעה נפתחים ביום שבקשת האישור הראשונה יוצאת לפי לוח הזמנים
    (``rsvp_open_date``). עד אז ה-Guest Hub במצב צפייה בלבד (הזמנה / יומן /
    ניווט), והודעת ההזמנה הראשונה אינה מבקשת אישור. רצפת ביטחון: לא נפתח
    לפני שההזמנות נשלחו בכלל (``rsvp_track_active``).

    ``event is None`` — הקשר תצוגה מקדימה (אין אירוע): מחזיר ``True``, כמו
    ``compute_actions(None)``.
    """
    if event is None:
        return True
    if not event.rsvp_track_active:
        return False
    opens_on = rsvp_open_date(event, now=now)
    if opens_on is None:
        return False
    return today_in_israel(now) >= opens_on


@dataclass(frozen=True)
class ActionAvailability:
    """מה פתוח למוזמן. מתורגם אחד-לאחד ל-``schemas.ConfirmActions``."""

    invitation: bool
    calendar: bool
    navigation: bool
    rsvp: bool
    gift: bool


def compute_actions(
    event: models.Event | None,
    *,
    has_calendar: bool,
    now: datetime | None = None,
) -> ActionAvailability:
    """הזמינות המלאה של פעולות המוזמן, לפי נתוני האירוע בלבד.

    שלוש הפעולות הראשונות תלויות ב*נתונים* (יש תמונת הזמנה? יש תאריך? יש
    כתובת?) — פעולה בלי נתונים לא מוצגת, במקום כפתור שלא עושה כלום.
    ``gift`` ו-``rsvp`` תלויים ב*זמן*: ``rsvp`` נפתח ביום שבקשת האישור
    הראשונה יוצאת לפי לוח הזמנים (``rsvp_is_open``), לא מרגע ההזמנה.
    """
    if event is None:
        return ActionAvailability(False, False, False, True, False)
    return ActionAvailability(
        invitation=bool(event.invite_image),
        calendar=has_calendar,
        navigation=bool((event.venue_address or "").strip()),
        rsvp=rsvp_is_open(event, now=now),
        gift=gift_is_open(event, now=now),
    )


# הפעולות שאפשר לבקש דרך ``?action=`` בקישור. "rsvp" לא ברשימה — אישור
# ההגעה הוא חלק קבוע מהעמוד ולא אזור שנפתח.
ROUTABLE_ACTIONS = ("invitation", "calendar", "navigation", "gift")


def assert_action_allowed(
    event: models.Event | None,
    action: str,
    *,
    has_calendar: bool = False,
    now: datetime | None = None,
) -> None:
    """שער האכיפה: זורק 403 אם הפעולה אינה פתוחה למוזמן הזה כרגע.

    **זו הנקודה שבה "לא מוצג" הופך ל"לא מורשה".** היום אין עדיין נקודת קצה
    למתנה, ולכן אין לה קורא — אבל היא נכתבה ונבדקת עכשיו כדי שמי שיבנה את
    הסליקה לא יסתמך על כך שהכפתור פשוט לא מופיע ב-UI. הסתרה ב-UI היא לא
    אבטחה.
    """
    if action not in ROUTABLE_ACTIONS:
        raise HTTPException(status_code=404, detail="פעולה לא מוכרת.")
    available = compute_actions(event, has_calendar=has_calendar, now=now)
    if not getattr(available, action, False):
        raise HTTPException(
            status_code=403,
            detail="הפעולה הזו עדיין לא זמינה בקישור הזה.",
        )
