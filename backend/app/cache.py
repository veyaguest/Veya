"""מטמון פשוט בזיכרון-תהליך (in-process), עם TTL, לנתונים ציבוריים שמשתנים לעיתים
רחוקות — שלב 1 בתוכנית ה-caching: venues, veya_templates, veya_workflow_steps,
מטא-דאטה/בייטים של media.

**לא שכבת לוגיקה עסקית** — רק "read-through cache" מעל שאילתות קיימות, עם
invalidation מפורש בכל endpoint שכותב לטבלאות האלה. שום query/endpoint לא
משתנה בהתנהגותו — רק נחסך round-trip ל-DB כשהמידע כבר במטמון ותקף.

**מודל התהליך:** האפליקציה רצה כ-worker יחיד של uvicorn (ראה render.yaml —
אין ``--workers``), אז dict בזיכרון משותף לכל הבקשות ובטוח לשימוש. אם בעתיד
יעברו למספר workers/instances, המטמון הזה יהפוך to per-process — כל instance
יראה נתונים מעודכנים תוך כדי ה-TTL שלו, לא מיידית. מקובל לנתונים שמשתנים
לעיתים רחוקות (venues/templates/workflow), **לא מתאים** לנתוני אורחים/RSVP
דינמיים (שלבים הבאים בתוכנית).

**Fallback:** כל תקלה במטמון עצמו (לא בשאילתה!) גורמת לדילוג על המטמון
ופנייה ישירה ל-loader — מסך לעולם לא נשבר בגלל המטמון.
"""
from __future__ import annotations

import time
from threading import Lock
from types import SimpleNamespace
from typing import Any, Callable, Iterable

_store: dict[str, tuple[float, Any]] = {}
_lock = Lock()


def snapshot(row: Any) -> SimpleNamespace:
    """מעתיק עמודות טעונות של אובייקט ORM לעותק שטוח (בלי קשר ל-session).

    בטוח לשמור במטמון ולהחזיר בבקשות עתידיות: אין lazy-load, אין תלות
    בסשן שכבר נסגר. משמש רק לקריאה (attribute access) — לא ל-``db.add``/merge.
    """
    data = {k: v for k, v in vars(row).items() if not k.startswith("_sa_")}
    return SimpleNamespace(**data)


def snapshot_all(rows: Iterable[Any]) -> list[SimpleNamespace]:
    return [snapshot(r) for r in rows]


def get_or_set(key: str, ttl_seconds: float, loader: Callable[[], Any]) -> Any:
    """מחזיר את הערך במטמון עבור ``key`` אם עדיין בתוקף; אחרת קורא ל-loader,
    שומר את התוצאה עם תפוגה בעוד ``ttl_seconds`` שניות, ומחזיר אותה.

    אם קריאת/כתיבת המטמון עצמה נכשלת מסיבה כלשהי (לא אמורה, אבל ליתר ביטחון),
    פשוט מדלגים על המטמון וקוראים ל-loader ישירות — פעם אחת בלבד, כדי לא
    להכפיל שאילתות במקרה של תקלה.
    """
    now = time.monotonic()
    try:
        with _lock:
            entry = _store.get(key)
        if entry is not None and entry[0] > now:
            return entry[1]
    except Exception:
        return loader()

    value = loader()

    try:
        with _lock:
            _store[key] = (now + ttl_seconds, value)
    except Exception:
        pass
    return value


def get(key: str) -> Any:
    """מחזיר את הערך במטמון אם קיים ותקף, אחרת ``None`` — בלי לקרוא ל-loader.
    שימושי כשהקורא צריך להחליט בעצמו אם/איך לשמור את התוצאה (למשל: לדלג על
    מטמון לפי גודל התוכן, כמו ב-media_serve.py)."""
    now = time.monotonic()
    try:
        with _lock:
            entry = _store.get(key)
        if entry is not None and entry[0] > now:
            return entry[1]
    except Exception:
        pass
    return None


def set(key: str, value: Any, ttl_seconds: float) -> None:
    """שומר ערך במטמון עם תפוגה בעוד ``ttl_seconds`` שניות."""
    try:
        with _lock:
            _store[key] = (time.monotonic() + ttl_seconds, value)
    except Exception:
        pass


def invalidate_prefix(prefix: str) -> None:
    """מוחק מהמטמון כל מפתח שמתחיל ב-``prefix``. קוראים לזה מיד אחרי כתיבה
    לטבלה הרלוונטית, כדי שהאדמין יראה שינוי מיידית ולא יחכה ל-TTL."""
    with _lock:
        for k in [k for k in _store if k.startswith(prefix)]:
            del _store[k]


def invalidate_key(key: str) -> None:
    with _lock:
        _store.pop(key, None)


def clear_all() -> None:
    """מנקה את כל המטמון. שימושי לבדיקות."""
    with _lock:
        _store.clear()
