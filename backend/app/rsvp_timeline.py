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
4. **החלון** = מיום הייחוס (היום / יום הפעלת המסלול) עד מועד הסגירה, ולכל
   היותר ``MAX_WINDOW_DAYS`` ימים. 14 = מקסימום, לא חובה.
5. **הסבבים נבנים בתוך החלון האמיתי** (``compute_schedule``):
   - **מועד סגירת הרשימה הוא גם יום סבב השיחות האחרון** — תאריך אחד ויחיד
     (``Schedule.commitment_date``).
   - שישי/שבת: לא מתזמנים בהם פעולות.
   - **כל שלב ביום פעיל משלו** — לכן אף פעם לא WhatsApp וסבב טלפונים באותו
     יום, אף פעם לא תאריך בעבר ואף פעם לא אחרי מועד הסגירה. כשיש מקום נשמר
     יום מפריד בין WhatsApp לשיחות (``GAP_WA_CALL`` / ``GAP_WA_WA``).
   - זמן קצר (``compressed=true``): התהליך נדחס לימים הקיימים. אם אין מספיק
     ימים פעילים לכל השלבים, נבחרים החשובים ביותר לפי ``STEP_PRIORITY`` —
     המסלול מתקצר, לא נשבר.

המודול עצמו טהור — רק *מחשב* תאריכים. אבל התאריכים האלה הם מקור האמת לשליחה
בפועל: שלבי ה-WhatsApp (``whatsapp_first`` + ``reminder``) מחוברים למנגנון
השליחה דרך ``rsvp_request_date`` / ``reminder_date`` ו-``communication.py``
(סוג ההודעה ``rsvp_request`` והתזכורות). סבבי השיחות (``call_round``) נשארים
פעולת מוקד ידנית (Call Center של האדמין).
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

# הפער הרצוי בין שלבים סמוכים, בימים *פעילים*, כשיש מקום בחלון:
#   · WhatsApp <-> סבב טלפונים  → ``GAP_WA_CALL`` (2 = יום מפריד ביניהם)
#   · WhatsApp <-> WhatsApp     → ``GAP_WA_WA``  (1 — מותר סמוך)
# בלוח דחוס הפער מצטמצם, אבל שני שלבים לעולם לא נופלים על אותו יום.
GAP_WA_CALL = 2
GAP_WA_WA = 1

# האינדקס של סבב השיחות האחרון ב-``CYCLE``. הוא תמיד מוצמד למועד סגירת
# הרשימה (ראו ``compute_schedule``): יום סגירת הרשימה = יום סבב השיחות
# האחרון, תאריך אחד ויחיד.
_LAST_CALL_ROUND_IDX = max(
    i for i, s in enumerate(CYCLE) if s["type"] == "call_round"
)

# כשאין מספיק ימים פעילים לכל השלבים — אילו נשמרים קודם (אינדקסים ב-``CYCLE``).
# החלטת המייסד (2026-09-15): בקשת האישור הראשונה (בלעדיה המוזמנים לא יכולים
# לאשר) → סבב השיחות ביום הסגירה → ואז לסירוגין תזכורת/שיחה.
STEP_PRIORITY: tuple[int, ...] = (0, _LAST_CALL_ROUND_IDX, 1, 2, 3, 4, 5)

@dataclass(frozen=True)
class Policy:
    """הפרמטרים של המסלול שאפשר לשלוט בהם מהאדמין (``settings_registry``).

    ברירות המחדל = הקבועים שלמעלה, כך שבלי שום הגדרה במסד התוצאה זהה בדיוק
    להתנהגות הקודמת.
    """

    reminders: int = 3
    calls: int = 3
    max_window_days: int = MAX_WINDOW_DAYS
    near_commit_days: int = DEFAULT_NEAR_COMMIT_DAYS


DEFAULT_POLICY = Policy()


def policy_for(event: models.Event) -> Policy:
    """המדיניות לאירוע: ערכי מערכת + Override לאירוע. תקלה → ברירות המחדל."""
    try:
        from app import settings_registry as sr

        eid = getattr(event, "id", None)
        return Policy(
            reminders=int(sr.value("rsvp.whatsapp_reminders", eid)),
            calls=int(sr.value("calls.rounds", eid)),
            max_window_days=int(sr.value("rsvp.max_window_days", eid)),
            near_commit_days=int(sr.value("rsvp.near_commit_days", eid)),
        )
    except Exception:  # noqa: BLE001 — לוח הזמנים לעולם לא נופל בגלל הגדרה
        return DEFAULT_POLICY


def _cycle_for(policy: Policy) -> tuple[list[dict], Optional[int], tuple[int, ...]]:
    """הסבב לפי המדיניות: N התזכורות הראשונות, M סבבי השיחות **האחרונים**
    (סבב השיחות האחרון נשאר תמיד ביום סגירת הרשימה)."""
    if policy.reminders == 3 and policy.calls == 3:
        return CYCLE, _LAST_CALL_ROUND_IDX, STEP_PRIORITY
    reminder_idx = [i for i, st in enumerate(CYCLE) if st["type"] == "reminder"][: max(0, policy.reminders)]
    all_calls = [i for i, st in enumerate(CYCLE) if st["type"] == "call_round"]
    call_idx = all_calls[len(all_calls) - max(0, min(policy.calls, len(all_calls))):] if policy.calls > 0 else []
    keep = sorted({0, *reminder_idx, *call_idx})
    cycle = [CYCLE[i] for i in keep]
    calls_new = [j for j, st in enumerate(cycle) if st["type"] == "call_round"]
    last = calls_new[-1] if calls_new else None
    priority = (0,) + ((last,) if last is not None else ()) + tuple(
        j for j in range(1, len(cycle)) if j != last
    )
    return cycle, last, priority


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


def _ddmm(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _weekday(d: date) -> str:
    return _HEB_WEEKDAY.get(d.weekday(), "")


def _audience_label(audience: str) -> str:
    if audience == "all":
        return "כל המוזמנים"
    if audience == "pending":
        return "מי שעדיין לא אישר"
    if audience == "confirmed":
        return "מי שאישר הגעה"
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


def _choose_steps(
    active_days: int, cycle: list[dict] = CYCLE, priority: tuple[int, ...] = STEP_PRIORITY,
) -> list[int]:
    """אילו שלבים מ-``cycle`` נכנסים לחלון (אינדקסים, בסדר הזמן)."""
    return sorted(priority[: min(active_days, len(cycle))])


def _spread(chosen: list[int], cycle: list[dict] = CYCLE) -> list[float]:
    """מיקום יחסי (0..1) לכל שלב נבחר, לפי הפער הרצוי בין שלבים סמוכים."""
    if len(chosen) == 1:
        return [0.0]
    cum = [0]
    for prev, cur in zip(chosen, chosen[1:]):
        same_family = (cycle[prev]["type"] == "call_round") == (cycle[cur]["type"] == "call_round")
        cum.append(cum[-1] + (GAP_WA_WA if same_family else GAP_WA_CALL))
    return [c / cum[-1] for c in cum]


def compute_schedule(event: models.Event, now: Optional[datetime] = None) -> Optional[Schedule]:
    """פורס את שלבי ``CYCLE`` לתאריכים עבור אירוע. ``None`` = אין מה לחשב
    (חסר תאריך אירוע, או אירוע רחוק שעוד לא נבחר לו מועד סגירת רשימה).

    יום הייחוס: היום שבו מסלול אישורי-ההגעה הופעל בפועל
    (``rsvp_track_started_at``), כדי שהתאריכים יהיו יציבים ולא "יברחו" קדימה
    בכל יום שעובר. לפני ההפעלה — היום (לוח הזמנים הצפוי מהיום).
    """
    now = now or datetime.utcnow()
    today = local_time.israel_date(now)
    event_date = parse_event_date(event.event_date)
    commit_days, is_default = resolve_commit_days(event, now)
    if event_date is None or commit_days is None:
        return None

    policy = policy_for(event)
    cycle, last_call_idx, priority = _cycle_for(policy)
    max_window = policy.max_window_days

    started_on = _started_on(event)
    reference = started_on or today
    if is_default and started_on is not None:
        # מסלול שהופעל כשהאירוע עוד היה רחוק, בלי בחירת מועד סגירה: ברירת
        # המחדל "נולדה" ביום שבו האירוע נעשה קרוב — לא מוקדם מזה, כדי שלא
        # יופיעו פתאום סבבים בתאריכים שכבר עברו.
        reference = max(started_on, event_date - timedelta(days=max_window - 1))

    # ---- מועד סגירת הרשימה ----
    # תאריך האירוע פחות הימים, מוזז אחורה אם נפל על שישי/שבת. זהו **תאריך
    # אחד ויחיד**: גם יום סבב השיחות האחרון וגם היום שבו סוגרים את הרשימה.
    # לעולם לא לפני יום הייחוס (אירוע מחר → הרשימה נסגרת היום). אירוע שכבר
    # הגיע לפני יום הייחוס לא "נגרר" קדימה — פשוט לא נשארים בו שלבים.
    raw_commitment = event_date - timedelta(days=commit_days)
    commitment_date = _prev_active_day(raw_commitment)
    if reference < event_date:
        commitment_date = max(commitment_date, reference)

    # ---- החלון: עד MAX_WINDOW_DAYS ימים, לא לפני יום הייחוס ----
    window_start = max(commitment_date - timedelta(days=max_window), reference)
    window_days = (commitment_date - window_start).days
    compressed = window_days < max_window
    active = [
        d for d in (window_start + timedelta(days=i) for i in range(window_days + 1))
        if not _is_weekend(d)
    ]

    # ---- בחירת השלבים ופריסתם ----
    chosen = _choose_steps(len(active), cycle, priority)
    positions = _spread(chosen, cycle) if chosen else []
    slots = len(active) - 1
    idx = [round(p * slots) for p in positions]
    # כל שלב ביום פעיל משלו: קדימה — לפחות אחד אחרי הקודם; אחורה — השלב האחרון
    # על היום האחרון בחלון (מועד הסגירה), וכל שלב לפחות אחד לפני הבא.
    for j in range(1, len(idx)):
        idx[j] = max(idx[j], idx[j - 1] + 1)
    if idx:
        idx[-1] = slots
    for j in range(len(idx) - 2, -1, -1):
        idx[j] = min(idx[j], idx[j + 1] - 1)

    reminders = [i for i in chosen if cycle[i]["type"] == "reminder"]
    calls = [i for i in chosen if cycle[i]["type"] == "call_round"]
    placements: list[Placement] = []
    for j, step_idx in enumerate(chosen):
        step = dict(cycle[step_idx])
        rn: Optional[int] = None
        reminder_n: Optional[int] = None
        if step["type"] == "reminder":
            reminder_n = reminders.index(step_idx) + 1
            step["label"] = _REMINDER_LABELS[reminder_n - 1]
        elif step["type"] == "call_round":
            rn = calls.index(step_idx) + 1
            step["label"] = (
                _LAST_CALL_LABEL if step_idx == last_call_idx else _CALL_LABELS[rn - 1]
            )
        if step_idx == last_call_idx:
            moved = _is_weekend(raw_commitment)
        else:
            natural = window_start + timedelta(days=round(positions[j] * window_days))
            moved = _is_weekend(natural)
        placements.append(Placement(
            step=step, date=active[idx[j]], moved_from_weekend=moved,
            round_number=rn, reminder_number=reminder_n,
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
        "days": [],
    }


def compute_timeline(
    event: models.Event,
    guests: list[models.Guest],
    now: Optional[datetime] = None,
) -> dict:
    """מחשב את לוח הזמנים המלא של אישורי-ההגעה עבור אירוע. טהור, בלי תופעות לוואי.

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
    confirmed = sum(1 for g in guests if g.rsvp_status == "confirmed")

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
    _last_round_number = max(
        (p.round_number for p in schedule.placements if p.round_number is not None),
        default=0,
    )

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
        # סבב השיחות האחרון = גם יום סגירת הרשימה. כרטיס אחד: אחרי הסבב,
        # הרשימה נסגרת. אין שורת "סגירת רשימת המוזמנים" נפרדת.
        is_last_round = (
            step["type"] == "call_round"
            and placement.round_number == _last_round_number
        )
        label = "סבב שיחות אחרון וסגירת הרשימה" if is_last_round else step["label"]
        note = "אחרי הסבב, רשימת המוזמנים נסגרת." if is_last_round else ""
        ensure_day(placement.date)["actions"].append({
            "type": step["type"],
            "icon": step["icon"],
            "label": label,
            "audience": _audience_label(step["audience"]),
            "audience_count": count_for(step["audience"]),
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
        "audience_count": confirmed,
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
        "audience_count": confirmed,
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
        "days": days,
    }
