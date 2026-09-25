"""לוח הזמנים של אישורי-ההגעה — מתאריך האירוע, דרך מועד סגירת הרשימה, אל הסבבים.

עיקרון מנחה (כמו שאר מנועי ה-RSVP): מודול טהור ודטרמיניסטי. הוא רק *מחשב*
מתי כל שלב במסלול אישורי-ההגעה אמור לקרות, ומחזיר תצוגת "יומן משימות" לזוג.
אין כאן תופעות לוואי, אין כתיבה ל-DB, אין קריאות LLM, ואין תלות ב-``seating.py``.

סדר החישוב (לא הופכים אותו — לא מתחילים מ"יש 14 יום"):
1. **תאריך האירוע** — העוגן הראשון.
2. **כמה זמן נשאר עד האירוע.**
3. **מועד סגירת הרשימה** (``resolve_commit_days``):
   - בעל האירוע בחר כמה ימים לפני האירוע למסור מספר סופי
     (``Event.venue_commit_days_before``, 1–10) → משתמשים בבחירה.
   - לא בחר, והאירוע קרוב מכדי לקיים תהליך מלא (פחות מ-``MAX_WINDOW_DAYS``)
     → ברירת מחדל: **יום לפני האירוע**. אירוע מחר → הרשימה נסגרת היום.
   - לא בחר והאירוע רחוק → אין עדיין לוח זמנים; בעל האירוע בוחר.
   אין כאן שום מספר לפי סוג אירוע: ברית, בריתה וחתונה עוברות אותו חישוב,
   וההבדל נובע רק מתאריך האירוע האמיתי.
4. **החלון** = מ-``MAX_WINDOW_DAYS`` (14) ימים לפני מועד הסגירה ועד מועד
   הסגירה — ולא לפני יום הייחוס. יום הייחוס הוא היום, עד שהמסלול מתחיל
   בפועל; מאז הוא קפוא (``rsvp_track_started_at``, נקבע ע"י המשימה המתוזמנת
   ב-``rsvp_scheduler``), כדי שהתאריכים לא "יברחו" קדימה. **שליחת הזמנה אינה
   נקודת האפס** — העוגן הוא מועד הסגירה בלבד.
5. **כמה סבבים** (``rounds_for_window``) — סבב אחד לכל יומיים בחלון, כמו
   במסלול המלא (7 סבבים ב-14 ימים), ולכל היותר ``Policy.max_rounds``. חלון
   קצר מקבל **פחות סבבים**, לא מסלול דחוס.
6. **איזה סבבים** (``SEQUENCES``) — המסלול המלא הוא
   WhatsApp → WhatsApp → שיחות → WhatsApp → שיחות → WhatsApp → שיחות.
   מתחת ל-7 הסבבים מתחלפים (WhatsApp → שיחות → WhatsApp …), בלי שני סבבים
   מאותו סוג רק כדי "למלא" זמן. החלטת המייסד 2026-09-23.
7. **פריסה לתאריכים** (``_place``):
   - הסבב האחרון נופל ביום סגירת הרשימה (``Schedule.commitment_date``).
   - כל סבב ביום משלו — אף פעם שתי פעולות באותו יום, אף פעם לא אחרי מועד
     הסגירה, והסדר לעולם לא מתהפך.
   - שישי/שבת: אין פעולות. סבב שנופל עליהם עובר לחמישי שלפניו, ואם חמישי
     כבר תפוס (או מחוץ לחלון) — לראשון שאחריו.
   - אם אי אפשר לפרוס את כל הסבבים בלי לשבור את הכללים — יורדים לסבב אחד
     פחות ופורסים מחדש.

המודול עצמו טהור — רק *מחשב* תאריכים. אבל התאריכים האלה הם מקור האמת לשליחה
בפועל: שלבי ה-WhatsApp (``whatsapp_first`` + ``reminder``) נשלחים ע"י
``rsvp_scheduler`` דרך ``communication.compute_due_messages``. סבבי השיחות
(``call_round``) הם פעולת מוקד (Call Center של האדמין, ``call_ops``).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from app import local_time, models
from app.automation import parse_event_date

# ---- הסבב המלא של אישורי-ההגעה ----
# הסדר כאן הוא סדר השלבים בזמן. audience: all = כל המוזמנים ; pending = מי
# שעדיין לא אישר. שלבי WhatsApp (whatsapp_first + reminder) נשלחים אוטומטית;
# call_round הוא פעולת מוקד ידנית. הסדר והתאריכים כאן הם מקור האמת גם
# ל-Call Center של האדמין.
CYCLE: list[dict] = [
    {"type": "whatsapp_first", "icon": "✅", "label": "בקשת אישור ראשונה ב-WhatsApp", "audience": "pending"},
    {"type": "reminder",       "icon": "📩", "label": "תזכורת ראשונה",              "audience": "pending"},
    {"type": "call_round",     "icon": "📞", "label": "סבב שיחות ראשון",            "audience": "pending"},
    {"type": "reminder",       "icon": "📩", "label": "תזכורת שנייה",               "audience": "pending"},
    {"type": "call_round",     "icon": "📞", "label": "סבב שיחות שני",              "audience": "pending"},
    {"type": "reminder",       "icon": "📩", "label": "תזכורת שלישית",             "audience": "pending"},
    {"type": "call_round",     "icon": "📞", "label": "סבב שיחות אחרון",           "audience": "pending"},
]

# אורך התהליך המלא, בימים קלנדריים — **מקסימום, לא חובה**. גם הסף לשאלה
# "האם האירוע רחוק מספיק כדי שבעל האירוע יבחר מועד סגירה בעצמו" נגזר ממנו
# (ראו ``resolve_commit_days``) — אין סף נפרד.
MAX_WINDOW_DAYS = 14

# אירוע קרוב שלא נבחר לו מועד סגירה: הרשימה נסגרת יום לפני האירוע.
DEFAULT_NEAR_COMMIT_DAYS = 1

# טווח הבחירה הידנית של "כמה ימים לפני האירוע" (נאכף ב-``routers/event.py``).
MAX_COMMIT_DAYS = 10

# הפער הרצוי בין שלבים סמוכים, ביחידות יחסיות בתוך החלון:
#   · WhatsApp <-> סבב טלפונים  → ``GAP_WA_CALL`` (2 = יום מפריד ביניהם)
#   · WhatsApp <-> WhatsApp     → ``GAP_WA_WA``  (1 — מותר סמוך)
# שני שלבים לעולם לא נופלים על אותו יום.
GAP_WA_CALL = 2
GAP_WA_WA = 1

# ---- כמה סבבים ובאיזה סדר (החלטת המייסד 2026-09-23) ----
# W = WhatsApp (בקשת אישור ראשונה / תזכורת), P = סבב שיחות. 7 = המסלול המלא.
# מתחת ל-7 הסבבים מתחלפים — בלי שני סבבים מאותו סוג רק כדי למלא זמן.
MAX_ROUNDS = 7
SEQUENCES: dict[int, tuple[str, ...]] = {
    7: ("W", "W", "P", "W", "P", "W", "P"),
    6: ("W", "P", "W", "P", "W", "P"),
    5: ("W", "P", "W", "P", "W"),
    4: ("W", "P", "W", "P"),
    3: ("W", "P", "W"),
    2: ("W", "P"),
    1: ("W",),
}

# צפיפות המסלול המלא: סבב אחד לכל ``DAYS_PER_ROUND`` ימים בחלון (7 ב-14).
# חלון קצר לא נעשה צפוף יותר — הוא מקבל פחות סבבים.
DAYS_PER_ROUND = 2


@dataclass(frozen=True)
class Policy:
    """הפרמטרים של המסלול שאפשר לשלוט בהם מהאדמין (``settings_registry``).

    ``max_rounds`` בוחר שורה מ-``SEQUENCES`` — כך שגם הגדרת אדמין לא יכולה
    לייצר מסלול שסותר את האיזון בין WhatsApp לשיחות. ברירות המחדל = המסלול
    המלא, כך שבלי שום הגדרה במסד התוצאה היא המסלול הרגיל.
    """

    max_rounds: int = MAX_ROUNDS
    max_window_days: int = MAX_WINDOW_DAYS
    near_commit_days: int = DEFAULT_NEAR_COMMIT_DAYS


DEFAULT_POLICY = Policy()


def policy_for(event: models.Event) -> Policy:
    """המדיניות לאירוע: ערכי מערכת + Override לאירוע. תקלה → ברירות המחדל."""
    try:
        from app import settings_registry as sr

        eid = getattr(event, "id", None)
        return Policy(
            max_rounds=max(1, min(MAX_ROUNDS, int(sr.value("rsvp.max_rounds", eid)))),
            max_window_days=int(sr.value("rsvp.max_window_days", eid)),
            near_commit_days=int(sr.value("rsvp.near_commit_days", eid)),
        )
    except Exception:  # noqa: BLE001 — לוח הזמנים לעולם לא נופל בגלל הגדרה
        return DEFAULT_POLICY


def rounds_for_window(window_days: int, policy: Policy = DEFAULT_POLICY) -> int:
    """כמה סבבים נכנסים לחלון של ``window_days`` ימים (מיום ההתחלה עד יום
    הסגירה). סבב לכל יומיים, לפחות אחד, לכל היותר ``policy.max_rounds``.
    ``window_days < 0`` (מועד הסגירה כבר עבר) → 0."""
    if window_days < 0:
        return 0
    return max(1, min(policy.max_rounds, -(-window_days // DAYS_PER_ROUND)))


def _steps_for(kinds: tuple[str, ...]) -> list[dict]:
    """ממיר רצף W/P לשלבים עם תוויות: W ראשון = בקשת אישור ראשונה, שאר ה-W
    = תזכורות (ממוספרות), P = סבבי שיחות (האחרון — "סבב שיחות אחרון")."""
    steps: list[dict] = []
    reminders = 0
    calls_total = kinds.count("P")
    calls = 0
    for i, kind in enumerate(kinds):
        if kind == "W" and i == 0:
            steps.append(dict(CYCLE[0]))
        elif kind == "W":
            reminders += 1
            steps.append({**CYCLE[1], "label": _REMINDER_LABELS[reminders - 1]})
        else:
            calls += 1
            label = _LAST_CALL_LABEL if calls == calls_total else _CALL_LABELS[calls - 1]
            steps.append({**CYCLE[2], "label": label})
    return steps


_REMINDER_LABELS = ("תזכורת ראשונה", "תזכורת שנייה", "תזכורת שלישית")
_CALL_LABELS = ("סבב שיחות ראשון", "סבב שיחות שני")
_LAST_CALL_LABEL = "סבב שיחות אחרון"

_HEB_WEEKDAY = {6: "ראשון", 0: "שני", 1: "שלישי", 2: "רביעי", 3: "חמישי", 4: "שישי", 5: "שבת"}


def _is_weekend(d: date) -> bool:
    """שישי (4) או שבת (5) — ימים שבהם לא מתזמנים פעולות."""
    return d.weekday() in (4, 5)


def _next_active_day(d: date) -> date:
    """היום הפעיל הקרוב קדימה (מדלג על שישי/שבת אל ראשון)."""
    while _is_weekend(d):
        d += timedelta(days=1)
    return d


def _prev_active_day(d: date) -> date:
    """היום הפעיל הקרוב אחורה (מדלג על שישי/שבת אל חמישי)."""
    while _is_weekend(d):
        d -= timedelta(days=1)
    return d


# ---- גרסאות ציבוריות — לשימוש חוצה-מודולים (למשל תזמון שעת שליחה
# ב-``communication.py``) בלי לגעת בלוגיקה הפנימית הקיימת כאן. ----

def is_weekend(d: date) -> bool:
    """גרסה ציבורית של ``_is_weekend``."""
    return _is_weekend(d)


def next_active_day(d: date) -> date:
    """גרסה ציבורית של ``_next_active_day``."""
    return _next_active_day(d)


def hebrew_weekday(d: date) -> str:
    """שם היום בעברית ("ראשון".."שבת"). גרסה ציבורית של ``_weekday``,
    לשימוש המחשבון הציבורי (``routers/public_calc.py``) — כדי שהאתר
    השיווקי לא יחזיק מיפוי ימים משלו שיסטה מזה שבמערכת."""
    return _weekday(d)


def rsvp_request_date(event: models.Event, now: Optional[datetime] = None) -> Optional[date]:
    """התאריך שבו נשלחת **בקשת האישור הראשונה** (``whatsapp_first``) לפי לוח
    הזמנים — מקור האמת היחיד גם לתזמון השליחה בפועל (``communication._due_now``)
    וגם לפתיחת אישורי ההגעה למוזמן (``guest_journey.rsvp_open_date``).

    ``None`` = אין לוח זמנים (חסר תאריך אירוע או מועד סגירת רשימה).
    """
    schedule = compute_schedule(event, now)
    if schedule is None:
        return None
    return next(
        (p.date for p in schedule.placements if p.step["type"] == "whatsapp_first"),
        None,
    )


def reminder_date(
    event: models.Event, number: int, now: Optional[datetime] = None
) -> Optional[date]:
    """התאריך של התזכורת ה-``number`` (1/2/3) לפי לוח הזמנים — מקור האמת
    לשליחת התזכורות בפועל (``communication._due_now``).

    ``None`` = אין לוח זמנים, או שהתזכורת הזו לא נכנסה ללוח כי אין מספיק ימים.
    """
    schedule = compute_schedule(event, now)
    if schedule is None:
        return None
    return next(
        (p.date for p in schedule.placements if p.reminder_number == number),
        None,
    )


# סוג ההודעה של כל תזכורת לפי מספרה בלוח (1/2/3). אותו מיפוי כמו
# ``communication.REMINDER_NUMBER`` — כאן בכיוון ההפוך, בלי תלות מעגלית.
REMINDER_MESSAGE_TYPES: dict[int, str] = {1: "reminder_1", 2: "reminder_2", 3: "final_reminder"}


def track_enabled(event: models.Event) -> bool:
    """האם מסלול אישורי ההגעה של האירוע רשאי לפעול (לשלוח, לפתוח אישור
    למוזמנים, ליצור משימות שיחה).

    החלטת המייסד (2026-09-23): **שליחת הזמנה לא קובעת את זה.** המסלול פועל
    כשבעל האירוע בחר מועד סגירת רשימה בעצמו — זו ההסכמה שלו לשליחה בשמו —
    או כשהמסלול כבר התחיל בעבר (``rsvp_track_active``, כולל אירועים שהתחילו
    לפני השינוי). ברירת המחדל האוטומטית לאירוע קרוב מוצגת בלוח, אבל לבדה
    לא מתחילה לשלוח.
    """
    return event.venue_commit_days_before is not None or bool(event.rsvp_track_active)


def track_enabled_clause():
    """אותו תנאי כמו ``track_enabled``, כשאילתת SQL — לסינון אירועים במסד
    (משימה מתוזמנת, Call Center). מקור אמת אחד לשאלה "האם המסלול פועל"."""
    from sqlalchemy import or_

    return or_(
        models.Event.venue_commit_days_before.is_not(None),
        models.Event.rsvp_track_active.is_(True),
    )


@dataclass(frozen=True)
class WhatsAppRound:
    """סבב WhatsApp אחד במסלול, עם החלון שבו מותר לשלוח אותו.

    ``day`` — יום הסבב. ``until`` — היום שבו מתחיל השלב הבא במסלול (כל סוג),
    או היום שאחרי הסגירה לסבב האחרון. אחרי ``until`` הסבב "עבר" — לא שולחים
    אותו בדיעבד (לא למוזמן חדש ולא אחרי תקלה).
    """

    message_type: str
    day: date
    until: date


def whatsapp_rounds(event: models.Event, now: Optional[datetime] = None) -> list[WhatsAppRound]:
    """סבבי ה-WhatsApp של המסלול, לפי הסדר, כל אחד עם סוג ההודעה שלו."""
    schedule = compute_schedule(event, now)
    if schedule is None:
        return []
    placements = schedule.placements
    rounds: list[WhatsAppRound] = []
    for i, p in enumerate(placements):
        if p.step["type"] == "whatsapp_first":
            message_type = "rsvp_request"
        elif p.step["type"] == "reminder" and p.reminder_number in REMINDER_MESSAGE_TYPES:
            message_type = REMINDER_MESSAGE_TYPES[p.reminder_number]
        else:
            continue
        until = (
            placements[i + 1].date if i + 1 < len(placements)
            else schedule.commitment_date + timedelta(days=1)
        )
        rounds.append(WhatsAppRound(message_type, p.date, until))
    return rounds


def track_phase(event: models.Event, now: Optional[datetime] = None) -> str:
    """באיזה שלב המסלול, לתצוגה: ``unscheduled`` (אין לוח זמנים) ·
    ``waiting`` (יש לוח, אבל עוד לא נבחר מועד סגירה — לא יישלח כלום) ·
    ``before`` (הסבב הראשון עוד לא הגיע) · ``running`` · ``ended`` (מועד
    הסגירה עבר)."""
    schedule = compute_schedule(event, now)
    if schedule is None:
        return "unscheduled"
    if not track_enabled(event):
        return "waiting"
    today = local_time.israel_date(now)
    if today > schedule.commitment_date:
        return "ended"
    if not schedule.placements or today < schedule.placements[0].date:
        return "before"
    return "running"


def _ddmm(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _weekday(d: date) -> str:
    return _HEB_WEEKDAY.get(d.weekday(), "")


_CALL_AUDIENCE_LABEL = "מי שעוד לא ענו או לא החליטו"


def _audience_label(audience: str) -> str:
    if audience == "all":
        return "כל המוזמנים"
    if audience == "pending":
        return "מי שעוד לא ענו"
    if audience == "confirmed":
        return "מי שאישרו הגעה"
    return ""


# ---- פריסת הסבב לתאריכים (מקור אמת יחיד) ----
# גם מסך אישורי-ההגעה של בעל האירוע וגם ה-Call Center של האדמין קוראים מכאן,
# כדי ששניהם ידברו על *אותם* תאריכים בדיוק ולא ייווצרו שני לוחות זמנים.


@dataclass(frozen=True)
class Placement:
    """שלב אחד בסבב, אחרי שקיבל תאריך בפועל."""

    step: dict
    date: date
    moved_from_weekend: bool
    # סידורי סבב השיחות (1, 2, 3...) — רק לשלבי ``call_round``, אחרת None.
    round_number: Optional[int]
    # סידורי התזכורת (1, 2, 3) — רק לשלבי ``reminder``, אחרת None. כך השליחה
    # (``communication._due_now``) יודעת איזו תזכורת זו גם כשהלוח נדחס.
    reminder_number: Optional[int] = None


@dataclass(frozen=True)
class Schedule:
    """פריסת הסבב לאירוע אחד."""

    commitment_date: date
    start_date: date
    compressed: bool
    placements: list[Placement]
    # כמה ימים לפני האירוע נסגרת הרשימה בפועל (בחירה ידנית או ברירת מחדל).
    commit_days: int = DEFAULT_NEAR_COMMIT_DAYS
    # True = בעל האירוע לא בחר, והמערכת קבעה "יום לפני האירוע" כי האירוע קרוב.
    commit_is_default: bool = False


def _started_on(event: models.Event) -> Optional[date]:
    # יום ההפעלה בישראל — הפעלה ב-01:00 שעון ישראל היא עדיין "היום", לא אתמול ב-UTC.
    started = event.rsvp_track_started_at
    return local_time.israel_date(started) if started else None


def resolve_commit_days(
    event: models.Event, now: Optional[datetime] = None
) -> tuple[Optional[int], bool]:
    """שלבים 1–4 בסדר החישוב: מתאריך האירוע אל "כמה ימים לפני נסגרת הרשימה".

    מחזיר ``(ימים, האם_ברירת_מחדל)``. ``(None, False)`` = אין עדיין מועד סגירה
    (אין תאריך אירוע, או שהאירוע רחוק ובעל האירוע עוד לא בחר).

    האירוע "קרוב" כשנשארו פחות מ-``MAX_WINDOW_DAYS`` ימים — כלומר אין זמן
    לתהליך מלא, ולכן אין טעם לחכות לבחירה: ברירת המחדל היא יום לפני האירוע.
    """
    event_date = parse_event_date(event.event_date)
    if event_date is None:
        return None, False
    if event.venue_commit_days_before is not None:
        return event.venue_commit_days_before, False
    today = local_time.israel_date(now)
    policy = policy_for(event)
    if 0 < (event_date - today).days < policy.max_window_days:
        return policy.near_commit_days, True
    return None, False


def max_commit_days(event_date: date, today: date) -> int:
    """הבחירה הידנית הגדולה ביותר שעוד לא יוצרת מועד סגירה בעבר (0 = אין)."""
    return max(0, min(MAX_COMMIT_DAYS, (event_date - today).days))


def _spread(kinds: tuple[str, ...]) -> list[float]:
    """מיקום יחסי (0..1) לכל סבב, לפי הפער הרצוי בין סבבים סמוכים."""
    if len(kinds) == 1:
        return [0.0]
    cum = [0]
    for prev, cur in zip(kinds, kinds[1:]):
        cum.append(cum[-1] + (GAP_WA_WA if prev == cur else GAP_WA_CALL))
    return [c / cum[-1] for c in cum]


def _thursday_before(d: date) -> date:
    """חמישי שלפני שישי/שבת (שישי → אתמול, שבת → שלשום)."""
    return d - timedelta(days=d.weekday() - 3)


def _active_days_after(d: date, end: date) -> int:
    """כמה ימים פעילים יש אחרי ``d`` ועד ``end`` (כולל)."""
    count, cur = 0, d + timedelta(days=1)
    while cur <= end:
        if not _is_weekend(cur):
            count += 1
        cur += timedelta(days=1)
    return count


def _place(
    kinds: tuple[str, ...], start: date, end: date,
) -> Optional[list[tuple[date, date]]]:
    """פורס את הסבבים לתאריכים — ``[(תאריך בפועל, תאריך טבעי), ...]`` — או
    ``None`` אם אי אפשר בלי לשבור את הכללים (ואז הקורא יורד לסבב אחד פחות).

    כללים: הסבב האחרון ביום הסגירה (``end``; סבב יחיד — בתחילת החלון); כל סבב ביום פעיל משלו, אחרי
    הקודם ולא אחרי ``end``; שישי/שבת → חמישי שלפני, ואם הוא תפוס/מחוץ לחלון
    → ראשון שאחרי. אם גם הם לא מתאימים (התנגשות עיגול) — היום הפעיל הבא
    שעדיין משאיר מקום לסבבים שאחריו.
    """
    n = len(kinds)
    span = (end - start).days
    positions = _spread(kinds)
    placed: list[tuple[date, date]] = []
    prev: Optional[date] = None
    for k in range(n):
        remaining = n - 1 - k
        if k == n - 1 and n > 1:
            natural = end
            candidates = [end]
        else:
            # סבב יחיד יוצא כמה שיותר מוקדם בחלון — כדי שלמוזמנים יהיה זמן
            # לענות לפני הסגירה (ולא ביום הסגירה עצמו).
            natural = start + timedelta(days=round(positions[k] * span))
            candidates = (
                [_thursday_before(natural), _next_active_day(natural)]
                if _is_weekend(natural) else [natural]
            )
            cur = max(candidates) + timedelta(days=1)
            while cur <= end:
                candidates.append(cur)
                cur += timedelta(days=1)
        chosen: Optional[date] = None
        for c in candidates:
            if _is_weekend(c) or c < start or c > end:
                continue
            if prev is not None and c <= prev:
                continue
            if k < n - 1 and (c >= end or _active_days_after(c, end) < remaining):
                continue
            chosen = c
            break
        if chosen is None:
            return None
        placed.append((chosen, natural))
        prev = chosen
    return placed


def compute_schedule(event: models.Event, now: Optional[datetime] = None) -> Optional[Schedule]:
    """פורס את סבבי המסלול לתאריכים עבור אירוע. ``None`` = אין מה לחשב
    (חסר תאריך אירוע, או אירוע רחוק שעוד לא נבחר לו מועד סגירת רשימה).

    העוגן הוא מועד הסגירה. יום הייחוס (הגבול התחתון של החלון) הוא היום —
    עד שהמסלול מתחיל בפועל; מאז הוא קפוא (``rsvp_track_started_at``, נקבע
    ע"י ``rsvp_scheduler``), כדי שהתאריכים יהיו יציבים ולא "יברחו" קדימה בכל
    יום שעובר. שליחת הזמנה לא משפיעה על לוח הזמנים.
    """
    now = now or datetime.utcnow()
    today = local_time.israel_date(now)
    event_date = parse_event_date(event.event_date)
    commit_days, is_default = resolve_commit_days(event, now)
    if event_date is None or commit_days is None:
        return None

    policy = policy_for(event)
    max_window = policy.max_window_days

    started_on = _started_on(event)
    reference = started_on or today
    if is_default and started_on is not None:
        # מסלול שהתחיל כשהאירוע עוד היה רחוק, בלי בחירת מועד סגירה: ברירת
        # המחדל "נולדה" ביום שבו האירוע נעשה קרוב — לא מוקדם מזה, כדי שלא
        # יופיעו פתאום סבבים בתאריכים שכבר עברו.
        reference = max(started_on, event_date - timedelta(days=max_window - 1))

    # ---- מועד סגירת הרשימה ----
    # תאריך האירוע פחות הימים, מוזז אחורה אם נפל על שישי/שבת. זהו **תאריך
    # אחד ויחיד**: יום הסבב האחרון וגם היום שבו סוגרים את הרשימה.
    # לעולם לא לפני יום הייחוס (אירוע מחר → הרשימה נסגרת היום). אירוע שכבר
    # הגיע לפני יום הייחוס לא "נגרר" קדימה — פשוט לא נשארים בו סבבים.
    raw_commitment = event_date - timedelta(days=commit_days)
    commitment_date = _prev_active_day(raw_commitment)
    if reference < event_date:
        commitment_date = max(commitment_date, reference)

    # ---- החלון: עד max_window ימים לפני הסגירה, לא לפני יום הייחוס ----
    window_start = max(commitment_date - timedelta(days=max_window), reference)
    window_days = (commitment_date - window_start).days
    compressed = window_days < max_window

    # ---- כמה סבבים: לפי החלון; אם אי אפשר לפרוס — סבב אחד פחות ----
    kinds: tuple[str, ...] = ()
    dates: list[tuple[date, date]] = []
    for n in range(rounds_for_window(window_days, policy), 0, -1):
        attempt = _place(SEQUENCES[n], window_start, commitment_date)
        if attempt is not None:
            kinds, dates = SEQUENCES[n], attempt
            break

    placements: list[Placement] = []
    reminder_n = round_n = 0
    for step, (actual, natural) in zip(_steps_for(kinds), dates):
        rn: Optional[int] = None
        rem: Optional[int] = None
        if step["type"] == "reminder":
            reminder_n += 1
            rem = reminder_n
        elif step["type"] == "call_round":
            round_n += 1
            rn = round_n
        moved = _is_weekend(raw_commitment) if actual == commitment_date else _is_weekend(natural)
        placements.append(Placement(
            step=step, date=actual, moved_from_weekend=moved,
            round_number=rn, reminder_number=rem,
        ))

    return Schedule(
        commitment_date=commitment_date,
        start_date=placements[0].date if placements else window_start,
        compressed=compressed,
        placements=placements,
        commit_days=commit_days,
        commit_is_default=is_default,
    )


def call_rounds(event: models.Event, now: Optional[datetime] = None) -> list[Placement]:
    """סבבי השיחות של האירוע בלבד, לפי הסדר (סבב 1, 2, 3...)."""
    schedule = compute_schedule(event, now)
    if schedule is None:
        return []
    return [p for p in schedule.placements if p.round_number is not None]


def due_call_round(
    event: models.Event, now: Optional[datetime] = None
) -> Optional[Placement]:
    """סבב השיחות הפעיל כרגע — האחרון שתאריכו כבר הגיע. ``None`` אם אף סבב
    עדיין לא הגיע (או שאין לוח זמנים לאירוע).

    "האחרון שהגיע" ולא "זה שהיום בדיוק": מוזמן שלא הספיקו להתקשר אליו בסבב
    הקודם עדיין מופיע ברשימה עד שמגיע הסבב הבא — כי הוא עדיין צריך שיחה.
    """
    today = local_time.israel_date(now)
    due = [p for p in call_rounds(event, now) if p.date <= today]
    return due[-1] if due else None


def _empty_view(event: models.Event) -> dict:
    """מצב 'עדיין לא הוגדר' — אין תאריך אירוע או שלא נבחר מועד סגירת רשימה."""
    ed = parse_event_date(event.event_date)
    return {
        "configured": False,
        "event_date": _ddmm(ed) if ed else "",
        "commit_days_before": event.venue_commit_days_before,
        "commit_is_default": False,
        "commitment_date": None,
        "rsvp_start_date": None,
        "days_to_commitment": None,
        "compressed": False,
        "total_guests": 0,
        "pending_count": 0,
        "confirmed_count": 0,
        "today": "",
        "today_summary": "",
        "tomorrow_summary": "",
        "current_stage": None,
        "next_action_date": None,
        "next_action_label": None,
        "track_phase": "unscheduled",
        "track_enabled": track_enabled(event),
        "days": [],
    }


def step_key(placement: "Placement") -> Optional[str]:
    """מפתח ההיסטוריה של שלב: סוג ההודעה (``rsvp_request``/``reminder_1``…)
    לשלבי WhatsApp, ``call_<n>`` לסבב שיחות."""
    step_type = placement.step["type"]
    if step_type == "whatsapp_first":
        return "rsvp_request"
    if step_type == "reminder":
        return REMINDER_MESSAGE_TYPES.get(placement.reminder_number or 0)
    if step_type == "call_round":
        return f"call_{placement.round_number}"
    return None


def compute_timeline(
    event: models.Event,
    guests: list[models.Guest],
    now: Optional[datetime] = None,
    history: Optional[dict[str, int]] = None,
) -> dict:
    """מחשב את לוח הזמנים המלא של אישורי-ההגעה עבור אירוע. טהור, בלי תופעות לוואי.

    ``history`` — לשלבים שכבר עברו: כמה מוזמנים באמת היו בשלב (קיבלו את
    ההודעה / נכנסו לסבב השיחות), לפי ``step_key`` וגם ``event_day``/``thank_you``.
    שלב שעבר מציג את המספר ההיסטורי שלו, לא את הסטטוס של היום. ``None`` =
    אין היסטוריה (מספרים עדכניים לכל השלבים).

    מחזיר dict שמתאים ל-``schemas.RsvpTimelineView`` (ה-router עוטף אותו).
    """
    now = now or datetime.utcnow()
    today = local_time.israel_date(now)
    event_date = parse_event_date(event.event_date)

    # בלי תאריך אירוע, או אירוע רחוק בלי בחירת מועד סגירה — אין מה לחשב.
    schedule = compute_schedule(event, now)
    if schedule is None or event_date is None:
        return _empty_view(event)
    commit_days = schedule.commit_days

    total = len(guests)
    pending = sum(1 for g in guests if g.rsvp_status == "pending")
    maybe = sum(1 for g in guests if g.rsvp_status == "maybe")
    confirmed = sum(1 for g in guests if g.rsvp_status == "confirmed")

    def shown_count(key: Optional[str], day: date, current: int) -> int:
        """שלב שעבר — כמה היו בו בפועל; שלב של היום/עתידי — המצב העדכני."""
        if history is not None and key is not None and day < today:
            return history.get(key, 0)
        return current

    def count_for(audience: str) -> int:
        if audience == "all":
            return total
        if audience == "pending":
            return pending
        if audience == "confirmed":
            return confirmed
        return 0

    commitment_date = schedule.commitment_date
    compressed = schedule.compressed

    # ---- פריסת שלבי הסבב לתאריכים ----
    # מפה iso -> {"date":.., "actions":[...]}. יום אחד יכול לשאת כמה פעולות
    # (במיוחד במצב מכווץ).
    by_iso: dict[str, dict] = {}

    def ensure_day(d: date) -> dict:
        iso = d.isoformat()
        if iso not in by_iso:
            by_iso[iso] = {"date": d, "actions": []}
        return by_iso[iso]

    for placement in schedule.placements:
        step = placement.step
        # הסבב שביום סגירת הרשימה = גם הסגירה עצמה. כרטיס אחד: אחרי הסבב,
        # הרשימה נסגרת. אין שורת "סגירת רשימת המוזמנים" נפרדת. במסלול קצר
        # הסבב הזה יכול להיות גם WhatsApp (למשל 5 סבבים: W P W P W).
        closes = placement.date == commitment_date
        is_last_call = closes and step["type"] == "call_round"
        label = "סבב שיחות אחרון וסגירת הרשימה" if is_last_call else step["label"]
        note = (
            ("אחרי השיחות האחרונות" if is_last_call else "אחרי ההודעה הזו")
            + ", רשימת המוזמנים נסגרת."
        ) if closes else ""
        # סבב שיחות: גם מי שלא החליטו ממשיכים לשיחות (``call_center.OPEN_STATUSES``).
        is_call = step["type"] == "call_round"
        ensure_day(placement.date)["actions"].append({
            "type": step["type"],
            "icon": step["icon"],
            "label": label,
            "audience": _CALL_AUDIENCE_LABEL if is_call else _audience_label(step["audience"]),
            "audience_count": shown_count(
                step_key(placement), placement.date,
                pending + maybe if is_call else count_for(step["audience"]),
            ),
            "moved_from_weekend": placement.moved_from_weekend,
            "note": note,
        })

    rsvp_start_date = schedule.start_date

    # אין הודעת "מחר מתראים" / "יום לפני האירוע" ב-VEYA — רק הודעת יום האירוע.
    # יום האירוע — הודעה אישית עם מספר השולחן.
    ensure_day(event_date)["actions"].append({
        "type": "day_of",
        "icon": "❤️",
        "label": "הודעת 'היום מתראים' עם מספר השולחן",
        "audience": _audience_label("confirmed"),
        "audience_count": shown_count("event_day", event_date, confirmed),
        "moved_from_weekend": False,
    })

    # הודעת התודה — יום אחרי האירוע (``communication.DEFAULT_TRIGGER_OFFSET_DAYS
    # ["thank_you"] == 1``; מוזזת ליום פעיל אם נופלת על סוף שבוע, בדיוק כמו
    # השליחה בפועל ב-``communication._due_now``). מוצגת כשלב אחרון במסלול.
    thank_you_natural = event_date + timedelta(days=1)
    thank_you_date = _next_active_day(thank_you_natural)
    ensure_day(thank_you_date)["actions"].append({
        "type": "thank_you",
        "icon": "🙏",
        "label": "הודעת תודה למוזמנים",
        "audience": _audience_label("confirmed"),
        "audience_count": shown_count("thank_you", thank_you_date, confirmed),
        "moved_from_weekend": thank_you_date != thank_you_natural,
    })

    # ---- עוגן 'היום' (מופיע תמיד, גם בלי פעולה) ----
    # אין עוגן 'מחר': ב-VEYA אין הודעת "מחר מתראים", והלוח לא מדבר על מחר.
    if today <= event_date:
        ensure_day(today)

    # ---- בניית רשימת הימים הממוינת ----
    days: list[dict] = []
    for iso in sorted(by_iso.keys()):
        entry = by_iso[iso]
        d = entry["date"]
        days.append({
            "date": _ddmm(d),
            "iso": iso,
            "weekday": _weekday(d),
            "is_today": d == today,
            "is_tomorrow": False,
            "is_past": d < today,
            "is_commitment": d == commitment_date,
            "actions": entry["actions"],
        })

    # ---- סיכום 'מה קורה היום' ----
    # ריק כשאין פעילות היום — המסך לא מציג בכלל את כרטיס "מה קורה היום" במקרה
    # הזה (הודעת "אין פעילות מתוכננת" היא רעש טכני לבעל האירוע).
    def summary_for(d: date) -> str:
        e = by_iso.get(d.isoformat())
        if not e or not e["actions"]:
            return ""
        return " · ".join(a["label"] for a in e["actions"])

    today_summary = summary_for(today)
    # נשאר ב-JSON לתאימות (schemas.RsvpTimelineView), אבל תמיד ריק —
    # הלוח לא מציג עוד תא 'מחר'.
    tomorrow_summary = ""

    # ---- שלב נוכחי + הפעולה הבאה ----
    action_dates = sorted(
        v["date"] for v in by_iso.values() if v["actions"]
    )
    current_stage: Optional[str] = None
    for d in action_dates:
        if d <= today:
            e = by_iso[d.isoformat()]
            current_stage = e["actions"][-1]["label"]
    next_action_date: Optional[str] = None
    next_action_label: Optional[str] = None
    for d in action_dates:
        if d > today:
            e = by_iso[d.isoformat()]
            next_action_date = _ddmm(d)
            next_action_label = e["actions"][0]["label"]
            break

    return {
        "configured": True,
        "event_date": _ddmm(event_date),
        "commit_days_before": commit_days,
        "commit_is_default": schedule.commit_is_default,
        "commitment_date": _ddmm(commitment_date),
        "rsvp_start_date": _ddmm(rsvp_start_date),
        "days_to_commitment": (commitment_date - today).days,
        "compressed": compressed,
        "total_guests": total,
        "pending_count": pending,
        "confirmed_count": confirmed,
        "today": _ddmm(today),
        "today_summary": today_summary,
        "tomorrow_summary": tomorrow_summary,
        "current_stage": current_stage,
        "next_action_date": next_action_date,
        "next_action_label": next_action_label,
        "track_phase": track_phase(event, now),
        "track_enabled": track_enabled(event),
        "days": days,
    }
