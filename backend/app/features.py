"""פיצ'רים והרשאות — מה פתוח ב-VEYA ולמי.

ארבעה צירים נפרדים, בכוונה:
- **Feature**  (כאן): האם היכולת פעילה במערכת — פעיל / בטא / כבוי.
- **Permission** (``admin_rbac`` / ``permissions``): מי רשאי לגעת בה.
- **Plan** (שלב המסחר): מה כלול במסלול שנרכש.
- **Event Override** (``FeatureRule`` לאירוע): חריגה לאירוע אחד.

סדר ההכרעה לאירוע: כלל לאירוע → כלל לבעלים → סטטוס הפיצ'ר → ברירת המחדל בקוד.
"בטא" = סגור, חוץ ממי שיש לו כלל פתוח.

``controllable=False`` — פיצ'ר שהקוד עוד לא יודע לכבות. מוצג במסך לידיעה,
בלי מתג שלא עושה כלום.
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

CACHE_SECONDS = 30
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{2,40}$")


@dataclass(frozen=True)
class FeatureDef:
    key: str
    label: str
    description: str
    controllable: bool
    default_enabled: Optional[bool]      # None = ההכרעה נשארת במנגנון הקיים (למשל מתג סביבה)
    rule_scopes: tuple[str, ...] = ()
    reason: str = ""


BUILTIN: dict[str, FeatureDef] = {f.key: f for f in [
    FeatureDef("rsvp", "אישורי הגעה", "מסלול אישורי ההגעה: הזמנה, תזכורות וקישור אישי.", False, True,
               reason="ליבת המוצר — לא ניתן לכבות. אפשר לשלוט בכמות התזכורות ב'כללי המערכת'."),
    FeatureDef("whatsapp", "WhatsApp", "שליחת הודעות WhatsApp למוזמנים.", False, True,
               reason="לעצירה מיידית של כל השליחות — 'עצירת חירום' ב'כללי המערכת'."),
    FeatureDef("calls", "טלפנים", "סבבי שיחות טלפון למי שלא אישר.", True, True, rule_scopes=("event", "user")),
    FeatureDef("seating", "הושבה", "מפת אולם, שולחנות ושיבוץ מוזמנים.", False, True,
               reason="אין עדיין מתג בקוד — פעיל לכל האירועים."),
    FeatureDef("hall_vision", "הושבה חכמה: זיהוי סקיצת אולם", "העלאת סקיצה ויצירת מפה אוטומטית (AI).", True, True,
               reason="מתג כללי בלבד — עדיין לא נבדק לפי אירוע."),
    FeatureDef("gifts", "מתנות באשראי", "אורחים שולחים מתנה בכרטיס אשראי.", True, None,
               rule_scopes=("event", "user")),
    FeatureDef("finance", "כספי האירוע", "תקציב, הוצאות וספירת מעטפות.", False, True,
               reason="אין עדיין מתג בקוד — פעיל לכל האירועים."),
]}


@dataclass
class _Cache:
    loaded_at: float = -1e9
    flags: dict[str, str] = field(default_factory=dict)             # key -> status
    rules: dict[tuple[str, str, int], bool] = field(default_factory=dict)


_cache = _Cache()
_lock = threading.Lock()


def invalidate() -> None:
    with _lock:
        _cache.loaded_at = -1e9


def _ensure_fresh() -> None:
    if time.monotonic() - _cache.loaded_at < CACHE_SECONDS:
        return
    with _lock:
        if time.monotonic() - _cache.loaded_at < CACHE_SECONDS:
            return
        try:
            from sqlalchemy import select

            from app import models
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                _cache.flags = {f.key: f.status for f in db.scalars(select(models.FeatureFlag)).all()}
                _cache.rules = {
                    (r.feature_key, r.scope_type, r.scope_id): bool(r.enabled)
                    for r in db.scalars(select(models.FeatureRule)).all()
                }
            finally:
                db.close()
        except Exception:  # noqa: BLE001 — בלי מסד: ברירות המחדל בקוד
            _cache.flags, _cache.rules = {}, {}
        _cache.loaded_at = time.monotonic()


@dataclass
class Decision:
    enabled: Optional[bool]
    source: str      # event_rule / user_rule / status / default


def decide(key: str, event=None) -> Decision:
    """הכרעה לפיצ'ר (לאירוע, אם ניתן). ``enabled=None`` = אין הכרעה מהאדמין."""
    _ensure_fresh()
    event_id = getattr(event, "id", None)
    owner_id = getattr(event, "owner_id", None)
    if event_id is not None and (key, "event", event_id) in _cache.rules:
        return Decision(_cache.rules[(key, "event", event_id)], "event_rule")
    if owner_id is not None and (key, "user", owner_id) in _cache.rules:
        return Decision(_cache.rules[(key, "user", owner_id)], "user_rule")
    if event_id is not None:
        # מסלול/תוסף שנקבע לאירוע פותח את הפיצ'ר (לא סוגר) — גם כשהוא "בטא".
        try:
            from app import commerce

            if key in commerce.event_features(event_id):
                return Decision(True, "plan")
        except Exception:  # noqa: BLE001
            pass
    status = _cache.flags.get(key)
    if status == "active":
        return Decision(True, "status")
    if status in ("off", "beta"):
        return Decision(False, "status")
    builtin = BUILTIN.get(key)
    return Decision(builtin.default_enabled if builtin else False, "default")


def enabled(key: str, event=None) -> bool:
    d = decide(key, event)
    return bool(d.enabled) if d.enabled is not None else True
