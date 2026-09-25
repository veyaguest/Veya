"""כללי המערכת — Registry בקוד + ערכים במסד + Overrides לאירוע.

עקרונות:
- **הקוד מגדיר מה אפשר לשלוט בו.** לכל הגדרה: סוג, גבולות, ברירת מחדל
  (שווה בדיוק להתנהגות לפני שהמסך הזה נולד). אי אפשר להזין ערך שהקוד לא
  יודע להפעיל.
- **המסד שומר רק שינויים.** DB ריק = התנהגות זהה להיום.
- **שרשרת:** ברירת מחדל בקוד → ערך מערכת → (מסלול, בעתיד) → Override לאירוע.
  ``resolve`` מחזיר גם את **המקור**, כדי שהמסך יציג "2 · Override לאירוע ·
  ברירת המערכת: 3".
- **``live``** מסמן הגדרה שהקוד באמת קורא. הגדרה שעדיין לא מחוברת מוצגת
  לקריאה בלבד — לא כפתור שלא עושה כלום.

קריאה מהירה: ערכים נטענים למטמון בזיכרון (רענון כל ``CACHE_SECONDS`` או מיד
אחרי כתיבה באותו תהליך), כדי שחישוב לוח זמנים לאלפי אירועים לא יפנה למסד.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

CACHE_SECONDS = 30


@dataclass(frozen=True)
class Setting:
    key: str
    domain: str                      # rsvp / whatsapp / calls / seating / gifts
    label: str
    help: str
    type: str                        # int / bool / choice / text
    default: Any
    min: Optional[int] = None
    max: Optional[int] = None
    choices: tuple = ()
    event_override: bool = False     # מותר Override ברמת אירוע
    live: bool = True                # הקוד קורא את הערך בפועל
    critical: bool = False           # דורש settings.critical
    unit: str = ""
    readonly_reason: str = ""


DOMAINS = {
    "rsvp": "אישורי הגעה",
    "whatsapp": "WhatsApp",
    "calls": "טלפנים",
    "seating": "הושבה",
    "gifts": "מתנות וכספים",
}

_SETTINGS: list[Setting] = [
    # ── אישורי הגעה ──
    Setting("rsvp.max_rounds", "rsvp", "מספר סבבים מקסימלי",
            "כמה סבבים לכל היותר במסלול אישורי ההגעה (WhatsApp ושיחות יחד). 7 = המסלול המלא. "
            "מתחת ל-7 הסבבים מתחלפים — WhatsApp, שיחות, WhatsApp…. חלון קצר לא מקצר את המסלול — הוא נדחס.",
            "int", 7, 1, 7, event_override=True, unit="סבבים"),
    Setting("rsvp.max_window_days", "rsvp", "אורך תהליך אישורי ההגעה",
            "כמה ימים לכל היותר לפני סגירת הרשימה מתחיל התהליך. אירוע קרוב יותר מקבל תהליך דחוס.",
            "int", 14, 7, 21, event_override=True, unit="ימים"),
    Setting("rsvp.block_weekend", "rsvp", "בלי פעולות בשישי ושבת",
            "שלב שנופל בשישי/שבת עובר ליום פעיל.", "bool", True, live=False,
            readonly_reason="כלל קבוע: גם השליחה בפועל חוסמת שישי ושבת, כדי שהודעה לא תצא בשבת"),
    Setting("rsvp.near_commit_days", "rsvp", "סגירת רשימה לאירוע קרוב (ברירת מחדל)",
            "לאירוע קרוב שבעליו לא בחרו מועד סגירה — כמה ימים לפני האירוע.", "int", 1, 1, 5,
            event_override=True, unit="ימים לפני"),
    # ── WhatsApp ──
    Setting("whatsapp.emergency_stop", "whatsapp", "עצירת חירום לכל השליחות",
            "כל שליחת WhatsApp במערכת נחסמת ונרשמת כנכשלה. לשימוש בתקלה בלבד.", "bool", False,
            critical=True),
    Setting("whatsapp.mode", "whatsapp", "מצב שליחה", "mock = הדגמה, live = שליחה אמיתית דרך Meta.",
            "choice", "mock", choices=("mock", "live"), live=False,
            readonly_reason="נקבע במשתני הסביבה של השרת (WHATSAPP_MODE) — שינוי מכאן עלול להתחיל שליחה אמיתית בלי תבניות מאושרות"),
    Setting("whatsapp.send_time", "whatsapp", "שעת שליחה לאירוע חדש", "שעת השליחה היומית של הודעות האישור.",
            "text", "16:00", live=False, readonly_reason="נקבעת לכל אירוע בנפרד בהגדרות האירוע"),
    # ── טלפנים ──
    Setting("calls.many_attempts", "calls", "ניסיונות עד 'דורש טיפול'",
            "אורח עם מספר ניסיונות כזה ומעלה מסומן לבדיקה.", "int", 3, 2, 10, unit="ניסיונות"),
    Setting("calls.attempts_per_round", "calls", "ניסיונות שיחה בכל סבב",
            "ניסיון אחד בכל סבב; אורח שלא ענה חוזר בסבב הבא.", "int", 1, live=False,
            readonly_reason="חלק מלוגיקת הסבבים — שינוי דורש פיתוח"),
    # ── הושבה ──
    Setting("seating.default_seats", "seating", "מקומות לשולחן באירוע חדש", "", "int", 12, live=False,
            readonly_reason="נקבע לכל אירוע במפת האולם"),
    # ── מתנות ──
    Setting("gifts.fee_mode", "gifts", "מי משלם את העמלה", "העמלה מתווספת לסכום שהאורח משלם.", "choice",
            "added", choices=("added",), live=False,
            readonly_reason="החלטה נעולה: העמלה על נותן המתנה ובעלי האירוע מקבלים את מלוא הסכום"),
]

SETTINGS: dict[str, Setting] = {s.key: s for s in _SETTINGS}

# הגדרות שהוחלפו (2026-09-23): "מספר תזכורות WhatsApp" + "מספר סבבי טלפונים"
# אפשרו מסלול שסותר את האיזון בין WhatsApp לשיחות. הן אוחדו ל-``rsvp.max_rounds``
# — ערכים שנשמרו מומרים פעם אחת בעליית השרת (``main._migrate_rsvp_round_settings``).
RETIRED_ROUND_KEYS = ("rsvp.whatsapp_reminders", "calls.rounds")


def max_rounds_from_retired(reminders: int, calls: int) -> int:
    """המרה מההגדרות הישנות: בקשת אישור + התזכורות + סבבי השיחות, עד 7."""
    return max(1, min(7, 1 + max(0, int(reminders)) + max(0, int(calls))))


def validate(setting: Setting, value: Any) -> Any:
    if setting.type == "int":
        if isinstance(value, bool):
            raise ValueError("ערך לא תקין")
        try:
            v = int(value)
        except (TypeError, ValueError):
            raise ValueError("צריך מספר שלם")
        if setting.min is not None and v < setting.min:
            raise ValueError(f"הערך המינימלי הוא {setting.min}")
        if setting.max is not None and v > setting.max:
            raise ValueError(f"הערך המקסימלי הוא {setting.max}")
        return v
    if setting.type == "bool":
        if not isinstance(value, bool):
            raise ValueError("צריך כן/לא")
        return value
    if setting.type == "choice":
        if value not in setting.choices:
            raise ValueError("ערך לא מוכר")
        return value
    return str(value)[:200]


# ── מטמון ──────────────────────────────────────────────────────────────────

@dataclass
class _Cache:
    loaded_at: float = -1e9
    system: dict[str, Any] = field(default_factory=dict)
    events: dict[int, dict[str, Any]] = field(default_factory=dict)


_cache = _Cache()
_lock = threading.Lock()


def invalidate() -> None:
    with _lock:
        _cache.loaded_at = -1e9


def _load() -> None:
    from sqlalchemy import select

    from app import models
    from app.database import SessionLocal

    system: dict[str, Any] = {}
    events: dict[int, dict[str, Any]] = {}
    db = SessionLocal()
    try:
        for row in db.scalars(select(models.SystemSetting)).all():
            system[row.key] = row.value
        for row in db.scalars(
            select(models.SettingOverride).where(models.SettingOverride.scope_type == "event")
        ).all():
            events.setdefault(row.scope_id, {})[row.key] = row.value
    finally:
        db.close()
    _cache.system, _cache.events = system, events


def _ensure_fresh() -> None:
    if time.monotonic() - _cache.loaded_at < CACHE_SECONDS:
        return
    with _lock:
        if time.monotonic() - _cache.loaded_at < CACHE_SECONDS:
            return
        try:
            _load()
        except Exception:  # noqa: BLE001 — טבלאות חסרות/מסד לא זמין: ברירות המחדל בקוד
            _cache.system, _cache.events = {}, {}
        _cache.loaded_at = time.monotonic()


@dataclass
class Resolved:
    key: str
    value: Any
    source: str          # code / system / event
    system_value: Any    # מה היה בלי Override לאירוע
    default: Any


def resolve(key: str, event_id: Optional[int] = None) -> Resolved:
    setting = SETTINGS[key]
    _ensure_fresh()
    value, source = setting.default, "code"
    if key in _cache.system:
        value, source = _cache.system[key], "system"
    system_value = value
    if event_id is not None and setting.event_override:
        ev = _cache.events.get(event_id, {})
        if key in ev:
            value, source = ev[key], "event"
    return Resolved(key, value, source, system_value, setting.default)


def value(key: str, event_id: Optional[int] = None) -> Any:
    return resolve(key, event_id).value


def event_override_count(event_id: int) -> int:
    _ensure_fresh()
    return len(_cache.events.get(event_id, {}))
