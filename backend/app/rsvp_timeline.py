"""לוח הזמנים של אישורי-ההגעה — חישוב *לאחור* מיום ההתחייבות לאולם.

עיקרון מנחה (כמו שאר מנועי ה-RSVP): מודול טהור ודטרמיניסטי. הוא רק *מחשב*
מתי כל שלב במסלול אישורי-ההגעה אמור לקרות, ומחזיר תצוגת "יומן משימות" לזוג.
אין כאן תופעות לוואי, אין כתיבה ל-DB, אין קריאות LLM, ואין תלות ב-``seating.py``.

הרעיון:
- הזוג בוחר כמה ימים לפני האירוע הוא חייב למסור לאולם מספר סופי
  (``Event.venue_commit_days_before``, 1–10). מכאן נגזר **יום ההתחייבות**
  = תאריך האירוע פחות אותם ימים.
- כל סבב אישורי-ההגעה מחושב *לאחור* מיום ההתחייבות, כך שהסבב האחרון מסתיים
  ממש לפניו — ואז הרשימה סופית ומדויקת.
- שישי/שבת: לא מתזמנים בהם פעולות. פעולה שנופלת על סוף שבוע מוזזת ליום
  הפעיל הקרוב (ראשון), עם דגל ``moved_from_weekend``.
- זמן קצר: אם אין מספיק ימים לסבב המלא, המסלול מתכווץ בצורה חכמה
  (``compressed=true``) כדי להספיק כמה שיותר אישורים לפני יום ההתחייבות.

שלב Phase 1: **הגדרה + תצוגה בלבד** — המודול לא שולח כלום. חיבור השליחה
בפועל לשלבים המתוזמנים יתווסף בשלב הבא.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from app import models
from app.automation import parse_event_date

# ---- הסבב הקבוע של אישורי-ההגעה ----
# כל שלב עם היסט יחסי (בימים) בתוך סבב *אידיאלי* מלא, שנפרס לאחור מיום
# ההתחייבות. audience: all = כל המוזמנים ; pending = מי שעדיין לא אישר.
# (השלבים כאן לתצוגה בלבד ב-Phase 1; בעתיד ניתן לגזור אותם מ-VeyaWorkflowStep.)
CYCLE: list[dict] = [
    {"type": "whatsapp_first", "offset": 0,  "icon": "✅", "label": "בקשת אישור ראשונה ב-WhatsApp", "audience": "all"},
    {"type": "reminder",       "offset": 3,  "icon": "📩", "label": "תזכורת ראשונה",              "audience": "pending"},
    {"type": "call_round",     "offset": 6,  "icon": "📞", "label": "סבב שיחות ראשון",            "audience": "pending"},
    {"type": "reminder",       "offset": 8,  "icon": "📩", "label": "תזכורת נוספת",               "audience": "pending"},
    {"type": "call_round",     "offset": 10, "icon": "📞", "label": "סבב שיחות שני",              "audience": "pending"},
    {"type": "reminder",       "offset": 11, "icon": "📩", "label": "תזכורת אחרונה",             "audience": "pending"},
    {"type": "call_round",     "offset": 12, "icon": "📞", "label": "סבב שיחות אחרון",           "audience": "pending"},
]
FULL_SPAN = 12  # ההיסט הגדול ביותר בסבב — אורך הסבב האידיאלי בימים.

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


def _empty_view(event: models.Event) -> dict:
    """מצב 'עדיין לא הוגדר' — אין תאריך אירוע או שלא נבחר יום התחייבות."""
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

    # בלי תאריך אירוע או בלי בחירת יום התחייבות — אין מה לחשב.
    if event_date is None or commit_days is None:
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

    commitment_date = event_date - timedelta(days=commit_days)
    # עוגן הסיום: היום הפעיל האחרון *לפני* יום ההתחייבות (יום מרווח לסגירה).
    anchor_end = _prev_active_day(commitment_date - timedelta(days=1))
    ideal_start = anchor_end - timedelta(days=FULL_SPAN)
    # לא מתחילים בעבר — VEYA ממתינה ומתחילה את הסבב בזמן.
    effective_start = max(ideal_start, today)
    available = (anchor_end - effective_start).days
    compressed = available < FULL_SPAN
    if available < 0:
        available = 0
    scale = 1.0 if not compressed else (available / FULL_SPAN if FULL_SPAN else 1.0)

    # ---- פריסת שלבי הסבב לתאריכים ----
    # מפה iso -> {"date":.., "actions":[...]}. יום אחד יכול לשאת כמה פעולות
    # (במיוחד במצב מכווץ).
    by_iso: dict[str, dict] = {}

    def ensure_day(d: date) -> dict:
        iso = d.isoformat()
        if iso not in by_iso:
            by_iso[iso] = {"date": d, "actions": []}
        return by_iso[iso]

    for step in CYCLE:
        off = round(step["offset"] * scale)
        natural = effective_start + timedelta(days=off)
        placed = _next_active_day(natural)
        if placed > anchor_end:
            placed = _prev_active_day(anchor_end)
        moved = _is_weekend(natural) and placed != natural
        cnt = count_for(step["audience"])
        ensure_day(placed)["actions"].append({
            "type": step["type"],
            "icon": step["icon"],
            "label": step["label"],
            "audience": _audience_label(step["audience"]),
            "audience_count": cnt,
            "moved_from_weekend": moved,
        })

    rsvp_start_date = min((v["date"] for v in by_iso.values()), default=effective_start)

    # ---- ציוני דרך אחרי הסבב ----
    # יום ההתחייבות עצמו.
    ensure_day(commitment_date)["actions"].append({
        "type": "commitment",
        "icon": "🏢",
        "label": "יום ההתחייבות לאולם — הרשימה הסופית מוכנה",
        "audience": _audience_label("confirmed"),
        "audience_count": confirmed,
        "moved_from_weekend": False,
    })
    # יום לפני האירוע — תזכורת חמה למי שאישר.
    day_before = event_date - timedelta(days=1)
    if day_before > commitment_date:
        ensure_day(day_before)["actions"].append({
            "type": "day_before",
            "icon": "🎉",
            "label": "תזכורת 'מחר מתראים' למי שאישר",
            "audience": _audience_label("confirmed"),
            "audience_count": confirmed,
            "moved_from_weekend": False,
        })
    # יום האירוע — הודעה אישית עם מספר השולחן.
    ensure_day(event_date)["actions"].append({
        "type": "day_of",
        "icon": "❤️",
        "label": "הודעת 'היום מתראים' עם מספר השולחן",
        "audience": _audience_label("confirmed"),
        "audience_count": confirmed,
        "moved_from_weekend": False,
    })

    # ---- עוגני 'היום' ו'מחר' (מופיעים תמיד, גם בלי פעולה) ----
    tomorrow = today + timedelta(days=1)
    for anchor in (today, tomorrow):
        # לא מציגים 'מחר' אם הוא כבר אחרי יום האירוע (הסתיים).
        if anchor <= event_date:
            ensure_day(anchor)

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
            "is_tomorrow": d == tomorrow,
            "is_past": d < today,
            "is_commitment": d == commitment_date,
            "actions": entry["actions"],
        })

    # ---- סיכומי 'מה קורה היום / מחר' ----
    def summary_for(d: date) -> str:
        e = by_iso.get(d.isoformat())
        if not e or not e["actions"]:
            return "אין פעילות מתוכננת"
        return " · ".join(a["label"] for a in e["actions"])

    today_summary = summary_for(today)
    tomorrow_summary = summary_for(tomorrow)

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
