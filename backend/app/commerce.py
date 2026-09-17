"""מסחר — עמלות, מסלולים וזכאויות. לוגיקה בלבד (בלי FastAPI).

עמלת מתנות באשראי:
- ברירת מחדל בקוד: 4% (``gift.GIFT_FEE_PERCENT``), בלי סכום קבוע ובלי מינימום/מקסימום.
- שורת ``FeeRule`` פעילה (system) מחליפה אותה — הכל בנקודות בסיס (350 = 3.5%)
  ובאגורות, חשבון שלמים בלבד.
- הכיוון נעול: העמלה **מתווספת** לסכום שהאורח משלם.

זכאות מסלול: מסלול/תוסף שנקבע לאירוע **פותח** פיצ'רים (לא סוגר) — ראו
``features.decide``. מגבלות (מספר מוזמנים) נשמרות אבל עדיין לא נאכפות במוצר.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

CACHE_SECONDS = 30


@dataclass(frozen=True)
class FeePolicy:
    percent_bp: int = 400
    fixed_agorot: int = 0
    min_agorot: Optional[int] = None
    max_agorot: Optional[int] = None
    source: str = "code"      # code / rule
    rule_id: Optional[int] = None


DEFAULT_FEE = FeePolicy()

_lock = threading.Lock()
_fee_cache: dict = {"at": -1e9, "policy": DEFAULT_FEE}
_ent_cache: dict = {"at": -1e9, "by_event": {}}


def invalidate() -> None:
    with _lock:
        _fee_cache["at"] = -1e9
        _ent_cache["at"] = -1e9


def gift_fee_policy() -> FeePolicy:
    if time.monotonic() - _fee_cache["at"] < CACHE_SECONDS:
        return _fee_cache["policy"]
    with _lock:
        try:
            from sqlalchemy import select

            from app import models
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                rule = db.scalar(
                    select(models.FeeRule).where(
                        models.FeeRule.kind == "gift_card", models.FeeRule.scope_type == "system",
                        models.FeeRule.active.is_(True),
                    ).order_by(models.FeeRule.id.desc())
                )
            finally:
                db.close()
            policy = DEFAULT_FEE if rule is None else FeePolicy(
                rule.percent_bp, rule.fixed_agorot or 0, rule.min_agorot, rule.max_agorot, "rule", rule.id,
            )
        except Exception:  # noqa: BLE001 — עמלה לעולם לא נופלת; ברירת המחדל הנעולה
            policy = DEFAULT_FEE
        _fee_cache.update(at=time.monotonic(), policy=policy)
        return policy


def compute_fee(amount_agorot: int, policy: FeePolicy) -> int:
    """אחוז (עיגול חצי-למעלה) + קבוע, בגבולות מינימום/מקסימום. שלמים בלבד."""
    fee = (amount_agorot * policy.percent_bp + 5000) // 10000 + policy.fixed_agorot
    if policy.min_agorot is not None:
        fee = max(fee, policy.min_agorot)
    if policy.max_agorot is not None:
        fee = min(fee, policy.max_agorot)
    return max(fee, 0)


def percent_display(bp: int):
    return bp // 100 if bp % 100 == 0 else bp / 100


def event_features(event_id: Optional[int]) -> set[str]:
    """פיצ'רים שהמסלול/התוספים של האירוע פותחים (רק זכאות פעילה/ניסיון)."""
    if event_id is None:
        return set()
    if time.monotonic() - _ent_cache["at"] >= CACHE_SECONDS:
        with _lock:
            by_event: dict[int, set[str]] = {}
            try:
                from sqlalchemy import select

                from app import models
                from app.database import SessionLocal

                db = SessionLocal()
                try:
                    addons = {a.key: a.feature_key for a in db.scalars(select(models.Addon)).all()}
                    rows = db.execute(
                        select(models.EventEntitlement, models.PlanVersion)
                        .join(models.PlanVersion, models.EventEntitlement.plan_version_id == models.PlanVersion.id)
                        .where(models.EventEntitlement.status.in_(("active", "trial")))
                    ).all()
                    for ent, ver in rows:
                        keys = set(ver.features or [])
                        for addon_key in list(ver.included_addons or []) + list(ent.addons or []):
                            if addons.get(addon_key):
                                keys.add(addons[addon_key])
                        by_event.setdefault(ent.event_id, set()).update(keys)
                finally:
                    db.close()
            except Exception:  # noqa: BLE001
                by_event = {}
            _ent_cache.update(at=time.monotonic(), by_event=by_event)
    return _ent_cache["by_event"].get(event_id, set())
