"""לוח הזמנים של אישורי-ההגעה — חישוב *לאחור* ממועד סגירת הרשימה.

עיקרון מנחה (כמו שאר מנועי ה-RSVP): מודול טהור ודטרמיניסטי. הוא רק *מחשב*
מתי כל שלב במסלול אישורי-ההגעה אמור לקרות, ומחזיר תצוגת "יומן משימות" לזוג.
אין כאן תופעות לוואי, אין כתיבה ל-DB, אין קריאות LLM, ואין תלות ב-``seating.py``.

הרעיון:
- הזוג בוחר כמה ימים לפני האירוע הוא חייב למסור לאולם מספר סופי
  (``Event.venue_commit_days_before``, 1–10). מכאן נגזר **מועד סגירת
  הרשימה** = תאריך האירוע פחות אותם ימים (מוזז אחורה אם נופל על סוף שבוע).
- **מועד סגירת הרשימה הוא גם יום סבב השיחות האחרון** — תאריך אחד ויחיד
  (``Schedule.commitment_date``, וגם תאריך ה-``call_round`` האחרון
  ב-``placements``). ביום הזה הטלפנים מבצעים את הסבב האחרון מול מי שעדיין
  לא אישר, ואז סוגרים את הרשימה. אין מועד נפרד ל"סבב טלפונים אחרון".
- כל סבב אישורי-ההגעה מחושב *לאחור* ממועד סגירת הרשימה, כך שהסבב האחרון
  נופל בדיוק עליו — ואז הרשימה סופית ומדויקת.
- שישי/שבת: לא מתזמנים בהם פעולות. פעולה שנופלת על סוף שבוע מוזזת ליום
  הפעיל הקרוב (ראשון), עם דגל ``moved_from_weekend``.
- **אין באותו יום גם שלב WhatsApp וגם סבב טלפונים.** בין כל שני שלבים
  סמוכים ב-``CYCLE`` יש פער מינימלי בימים פעילים (``GAP_WA_CALL`` /
  ``GAP_WA_WA``); בלוח לא דחוס יש יום מפריד מלא, ובלוח דחוס הפער מצטמצם
  אבל שני שלבים לעולם לא נופלים על אותו יום.
- זמן קצר: אם אין מספיק ימים לסבב המלא, המסלול מתכווץ בצורה חכמה
  (``compressed=true``) כדי להספיק כמה שיותר אישורים לפני מועד סגירת הרשימה.

המודול עצמו טהור — רק *מחשב* תאריכים. אבל התאריכים האלה הם מקור האמת לשליחה
בפועל: שלבי ה-WhatsApp (``whatsapp_first`` + ``reminder``) מחוברים למנגנון
השליחה דרך ``rsvp_request_date`` ו-``communication.py`` (סוג ההודעה
``rsvp_request`` והתזכורות). סבבי השיחות (``call_round``) נשארים פעולת מוקד
ידנית (Call Center של האדמין).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from app import models
from app.automation import parse_event_date

# ---- הסבב הקבוע של אישורי-ההגעה ----
# כל שלב עם היסט יחסי (בימים) בתוך סבב *אידיאלי* מלא, שנפרס לאחור ממועד
# סגירת הרשימה. audience: all = כל המוזמנים ; pending = מי שעדיין לא אישר.
# שלבי WhatsApp (whatsapp_first + reminder) נשלחים אוטומטית; call_round הוא
# פעולת מוקד ידנית. הסדר והתאריכים כאן הם מקור האמת גם ל-Call Center של האדמין.
CYCLE: list[dict] = [
    {"type": "whatsapp_first", "offset": 0,  "icon": "✅", "label": "בקשת אישור ראשונה ב-WhatsApp", "audience": "pending"},
    {"type": "reminder",       "offset": 2,  "icon": "📩", "label": "תזכורת ראשונה",              "audience": "pending"},
    {"type": "call_round",     "offset": 4,  "icon": "📞", "label": "סבב שיחות ראשון",            "audience": "pending"},
    {"type": "reminder",       "offset": 6,  "icon": "📩", "label": "תזכורת שנייה",               "audience": "pending"},
    {"type": "call_round",     "offset": 8,  "icon": "📞", "label": "סבב שיחות שני",              "audience": "pending"},
    {"type": "reminder",       "offset": 10, "icon": "📩", "label": "תזכורת שלישית",             "audience": "pending"},
    {"type": "call_round",     "offset": 12, "icon": "📞", "label": "סבב שיחות אחרון",           "audience": "pending"},
]
FULL_SPAN = 12  # ההיסט הגדול ביותר בסבב — אורך הסבב האידיאלי בימים.

# חוק קשיח: אין באותו יום גם שלב WhatsApp (whatsapp_first / reminder) וגם
# סבב טלפונים. הפער בין שלבים סמוכים ב-``CYCLE`` נמדד בימים *פעילים*:
#   · WhatsApp <-> סבב טלפונים  → ``GAP_WA_CALL`` (2 = לפחות יום מפריד ביניהם)
#   · WhatsApp <-> WhatsApp     → ``GAP_WA_WA``  (1 — מותר סמוך)
# בלוח דחוס הפער מצטמצם עד למינימום, אבל שני שלבים לעולם לא נופלים על אותו
# יום (ראו ``compute_schedule`` — כל שלב נדחף לפחות יום פעיל אחד מקודמו).
GAP_WA_CALL = 2
GAP_WA_WA = 1

# האינדקס של סבב השיחות האחרון ב-``CYCLE``. הוא תמיד מוצמד למועד סגירת
# הרשימה (ראו ``compute_schedule``): יום סגירת הרשימה = יום סבב השיחות
# האחרון, תאריך אחד ויחיד.
_LAST_CALL_ROUND_IDX = max(
    i for i, s in enumerate(CYCLE) if s["type"] == "call_round"
)

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


def _advance_active(d: date, n: int) -> date:
    """``n`` ימים פעילים קדימה מ-``d`` (מדלג על שישי/שבת)."""
    for _ in range(n):
        d = _next_active_day(d + timedelta(days=1))
    return d


def _retreat_active(d: date, n: int) -> date:
    """``n`` ימים פעילים אחורה מ-``d`` (מדלג על שישי/שבת)."""
    for _ in range(n):
        d = _prev_active_day(d - timedelta(days=1))
    return d


# ---- גרסאות ציבוריות — לשימוש חוצה-מודולים (למשל תזמון שעת שליחה
# ב-``communication.py``) בלי לגעת בלוגיקה הפנימית הקיימת כאן. ----

def is_weekend(d: date) -> bool:
    """גרסה ציבורית של ``_is_weekend``."""
    return _is_weekend(d)


def next_active_day(d: date) -> date:
    """גרסה ציבורית של ``_next_active_day``."""
    return _next_active_day(d)


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


@dataclass(frozen=True)
class Schedule:
    """פריסת הסבב המלאה לאירוע אחד."""

    commitment_date: date
    anchor_end: date
    start_date: date
    compressed: bool
    placements: list[Placement]


def compute_schedule(event: models.Event, now: Optional[datetime] = None) -> Optional[Schedule]:
    """פורס את שלבי ``CYCLE`` לתאריכים עבור אירוע. ``None`` = אין מה לחשב
    (חסר תאריך אירוע או שלא נבחר מועד סגירת רשימה).

    עוגן ההתחלה: היום שבו מסלול אישורי-ההגעה הופעל בפועל
    (``rsvp_track_started_at`` — כלומר היום שבו נשלחו ההזמנות, שהוא בדיוק
    המשמעות של השלב הראשון בסבב). כך התאריכים יציבים ולא "בורחים" קדימה
    בכל יום שעובר. לפני ההפעלה אין עדיין עוגן אמיתי, ולכן מוצג לוח הזמנים
    הצפוי מהיום — בדיוק כמו קודם.
    """
    now = now or datetime.utcnow()
    today = now.date()
    event_date = parse_event_date(event.event_date)
    commit_days = event.venue_commit_days_before
    if event_date is None or commit_days is None:
        return None

    raw_commitment = event_date - timedelta(days=commit_days)
    # מועד סגירת הרשימה = תאריך האירוע פחות ימי המרווח לאולם, מוזז אחורה אם
    # נפל על שישי/שבת. זהו **תאריך אחד ויחיד**: גם יום סבב השיחות האחרון
    # (ראו ההצמדה למטה) וגם היום שבו הטלפנים סוגרים בפועל את הרשימה.
    commitment_date = _prev_active_day(raw_commitment)
    # עוגן פריסת הסבב — היום הפעיל לפני מועד הסגירה. שאר השלבים נפרסים עד
    # כאן; רק הסבב האחרון מוצמד ל-``commitment_date`` עצמו.
    anchor_end = _prev_active_day(raw_commitment - timedelta(days=1))
    ideal_start = anchor_end - timedelta(days=FULL_SPAN)
    started_on = (
        event.rsvp_track_started_at.date() if event.rsvp_track_started_at else None
    )
    # לא מתחילים מוקדם מהסבב האידיאלי (אין טעם לפרוס 12 יום על פני חודשיים),
    # ולא בעבר כשעוד לא הופעל המסלול.
    effective_start = max(ideal_start, started_on or today)
    available = (anchor_end - effective_start).days
    compressed = available < FULL_SPAN
    if available < 0:
        available = 0
    scale = 1.0 if not compressed else (available / FULL_SPAN if FULL_SPAN else 1.0)

    def natural_of(step: dict) -> date:
        return _next_active_day(
            effective_start + timedelta(days=round(step["offset"] * scale))
        )

    families = ["call" if s["type"] == "call_round" else "wa" for s in CYCLE]

    def gap_after(i: int) -> int:
        """פער מינימלי (בימים פעילים) בין שלב ``i`` לשלב ``i+1``."""
        return GAP_WA_CALL if families[i] != families[i + 1] else GAP_WA_WA

    # ---- פריסה סדרתית ----
    # שלב 1 (קדימה): כל שלב במיקומו הטבעי (מעוגן ל-``effective_start`` ומכווץ
    # לפי ``scale``), ולפחות ``gap_after`` ימים פעילים אחרי השלב הקודם.
    dates: dict[int, date] = {_LAST_CALL_ROUND_IDX: commitment_date}
    floor = natural_of(CYCLE[0])
    for idx in range(_LAST_CALL_ROUND_IDX):
        dates[idx] = max(natural_of(CYCLE[idx]), floor)
        floor = _advance_active(dates[idx], gap_after(idx))

    # שלב 2 (לאחור): מושכים כל שלב שנדחף מעבר למקומו, כך שיישאר לפחות
    # ``gap_after`` ימים פעילים *לפני* השלב הבא. בלוח לא דחוס — תמיד עד יום
    # ההפרדה המלא (יש מקום). בלוח דחוס — לא מוקדם מהמיקום הטבעי (המכווץ לפי
    # ``scale``), כדי לשמור על העיגון לתחילת המסלול.
    for idx in range(_LAST_CALL_ROUND_IDX - 1, -1, -1):
        want = _retreat_active(dates[idx + 1], gap_after(idx))
        if dates[idx] > want:
            dates[idx] = want if not compressed else max(want, natural_of(CYCLE[idx]))

    # שלב 3 (רשת ביטחון): מבטיחים שכל שלב מוקדם ביום פעיל אחד לפחות מהשלב
    # הבא — יורדים לאחור מסבב השיחות האחרון המוצמד. ``_retreat_active``
    # תמיד יורד לפחות יום פעיל אחד, ולכן שני שלבים לעולם לא נופלים על אותו
    # יום (בפרט: אף פעם לא WhatsApp וסבב טלפונים ביחד).
    for idx in range(_LAST_CALL_ROUND_IDX - 1, -1, -1):
        hard = _retreat_active(dates[idx + 1], 1)
        if dates[idx] > hard:
            dates[idx] = hard

    placements: list[Placement] = []
    round_number = 0
    for idx, step in enumerate(CYCLE):
        placed = dates[idx]
        if step["type"] == "call_round":
            round_number += 1
            moved = idx == _LAST_CALL_ROUND_IDX and _is_weekend(raw_commitment)
            rn: Optional[int] = round_number
        else:
            moved = placed != natural_of(step)
            rn = None
        placements.append(Placement(
            step=step, date=placed, moved_from_weekend=moved, round_number=rn,
        ))

    return Schedule(
        commitment_date=commitment_date,
        anchor_end=anchor_end,
        start_date=min((p.date for p in placements), default=effective_start),
        compressed=compressed,
        placements=placements,
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
    today = (now or datetime.utcnow()).date()
    due = [p for p in call_rounds(event, now) if p.date <= today]
    return due[-1] if due else None


def _empty_view(event: models.Event) -> dict:
    """מצב 'עדיין לא הוגדר' — אין תאריך אירוע או שלא נבחר מועד סגירת רשימה."""
    ed = parse_event_date(event.event_date)
    return {
        "configured": False,
        "event_date": _ddmm(ed) if ed else "",
        "commit_days_before": event.venue_commit_days_before,
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
    today = now.date()
    event_date = parse_event_date(event.event_date)
    commit_days = event.venue_commit_days_before

    # בלי תאריך אירוע או בלי בחירת מועד סגירת רשימה — אין מה לחשב.
    schedule = compute_schedule(event, now)
    if schedule is None or event_date is None or commit_days is None:
        return _empty_view(event)

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
