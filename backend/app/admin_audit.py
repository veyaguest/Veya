"""כתיבה ליומן פעולות האדמין (``AdminAuditLog``).

כלל: כל פעולת אדמין שמשנה מידע קוראת ל-``record`` **באותה טרנזקציה** של
השינוי עצמו — כך אין שינוי בלי שורת יומן, ואין שורת יומן לשינוי שנכשל.

בניגוד ל-``audit.record`` (שבולע שגיאות כי הוא משני לפעולה), כאן כשל בכתיבה
**כן** מפיל את הפעולה: פעולת אדמין בלי תיעוד היא בדיוק מה שהיומן נועד למנוע.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app import admin_rbac, models

DOMAIN_LABELS = {
    "users": "משתמשים",
    "events": "אירועים",
    "admins": "הרשאות אדמין",
    "calls": "טלפנים",
    "venues": "אולמות",
    "messages": "הודעות",
    "settings": "כללי המערכת",
    "features": "פיצ'רים",
    "overrides": "Overrides",
    "commerce": "מסחר",
    "payouts": "קבלת מתנות",
    "postponements": "בקשות דחייה",
}


def change(field: str, label: str, before: Any, after: Any) -> dict:
    return {"field": field, "label": label, "before": _show(before), "after": _show(after)}


def _show(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if value is True:
        return "כן"
    if value is False:
        return "לא"
    return str(value)[:300]


def client_ip(request: Optional[Request]) -> Optional[str]:
    if request is None or request.client is None:
        return None
    return request.client.host


def record(
    db: Session,
    actor: models.User,
    *,
    domain: str,
    action: str,
    summary: str,
    target_type: str = "",
    target_id: Any = "",
    target_label: str = "",
    changes: Optional[Iterable[dict]] = None,
    reason: str = "",
    event_id: Optional[int] = None,
    request: Optional[Request] = None,
) -> models.AdminAuditLog:
    """מוסיף שורת יומן אדמין. לא מבצע commit — הקורא עושה זאת יחד עם השינוי."""
    row = models.AdminAuditLog(
        actor_id=actor.id,
        actor_label=(actor.display_name or actor.email or "")[:200],
        actor_role=admin_rbac.role_of(actor) or "",
        domain=domain,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id not in (None, "") else "",
        target_label=(target_label or "")[:300],
        summary=summary[:1000],
        changes=[c for c in (changes or []) if c.get("before") != c.get("after")] or None,
        reason=(reason or "").strip()[:1000],
        event_id=event_id,
        ip=client_ip(request),
    )
    db.add(row)
    return row
