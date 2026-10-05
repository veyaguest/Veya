"""מדידת שימוש בעזרה — אימות, שמירה ותובנות (HELP_CENTER_PLAN.md §12, שלב 8).

- **אימות** (``validate_event``): כל אירוע חייב להתאים בדיוק ל-
  ``help_events_spec.json`` — שם מתוך 11 השמות, רק השדות שמוגדרים לו, וכל ערך
  מתוך רשימה סגורה / מזהה בסיס ידע / bool / int. אין שדה טקסט חופשי בכלל,
  ולכן גם טקסט חיפוש לא יכול לעבור (החלטת המייסד 2026-09-29).
- **שמירה**: בלי זהות (``models.HelpEvent``). 180 יום, ואז נמחק
  (``purge_old`` — רץ לכל היותר פעם בשעה, כשצוות פותח את "תובנות עזרה").
- **תובנות** (``insights``): ספירות פשוטות ל-7/30 יום, למסך האדמין.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models

_SPEC = json.loads((Path(__file__).with_name("help_events_spec.json")).read_text(encoding="utf-8"))
NAMES: dict[str, dict[str, Any]] = _SPEC["names"]
SCREENS: list[str] = _SPEC["screens"]
PLATFORMS: list[str] = _SPEC["platforms"]

KB_ID = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,59}$")
SESSION_ID = re.compile(r"^[0-9a-f]{32}$")
KB_VERSION = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
MAX_INT = 50
RETENTION_DAYS = 180


def session_key(client_session_id: str) -> str:
    """מה שנשמר במקום מזהה הסשן שהדפדפן שלח: טביעה חד-כיוונית עם סוד השרת.
    אירועים מאותה פתיחה של העזרה עדיין מתחברים זה לזה, אבל שום דבר שהגיע
    מהדפדפן לא נשמר כמו שהוא (גם אם מישהו הכניס לשם ספרות "משמעותיות")."""
    from app.auth import JWT_SECRET

    return hashlib.sha256(f"help-session:{JWT_SECRET}:{client_session_id}".encode()).hexdigest()[:32]


def _valid_value(kind: Any, value: Any) -> bool:
    if isinstance(kind, list):
        return isinstance(value, str) and value in kind
    kind = str(kind).rstrip("?")
    if kind == "kb_id":
        return isinstance(value, str) and bool(KB_ID.match(value))
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_INT
    return False


def validate_event(name: str, props: dict) -> Optional[str]:
    """``None`` אם תקין, אחרת תיאור קצר של הבעיה (לשגיאת 422)."""
    spec = NAMES.get(name)
    if spec is None:
        return f"שם לא מוכר: {name[:40]}"
    if not isinstance(props, dict):
        return "props חייב להיות אובייקט"
    extra = set(props) - set(spec)
    if extra:
        return f"{name}: שדות לא מוכרים {sorted(extra)[:5]}"
    for field, kind in spec.items():
        optional = isinstance(kind, str) and kind.endswith("?")
        if field not in props:
            if optional:
                continue
            return f"{name}: חסר {field}"
        if props[field] is None and optional:
            continue
        if not _valid_value(kind, props[field]):
            return f"{name}: ערך לא תקין ב-{field}"
    return None


_last_purge = 0.0


def purge_old(db: Session, *, now: Optional[datetime] = None, force: bool = False) -> None:
    """מוחק אירועים ישנים מ-180 יום. לכל היותר פעם בשעה (אלא אם ``force``)."""
    global _last_purge
    if not force and time.time() - _last_purge < 3600:
        return
    _last_purge = time.time()
    cutoff = (now or datetime.utcnow()) - timedelta(days=RETENTION_DAYS)
    db.execute(delete(models.HelpEvent).where(models.HelpEvent.created_at < cutoff))


def insights(db: Session, days: int, *, now: Optional[datetime] = None) -> dict:
    """ספירות ל-N הימים האחרונים. אין כאן זהות — אין מה לחשוף."""
    since = (now or datetime.utcnow()) - timedelta(days=days)
    rows = db.scalars(select(models.HelpEvent).where(models.HelpEvent.created_at >= since)).all()

    sessions = {r.session_id for r in rows if r.name == "help_opened"}
    opened_by_screen: Counter[str] = Counter(r.screen for r in rows if r.name == "help_opened")
    entries: Counter[str] = Counter((r.props or {}).get("entry", "") for r in rows if r.name == "help_opened")

    topics: dict[str, Counter] = defaultdict(Counter)
    tours: dict[str, Counter] = defaultdict(Counter)
    trees: dict[str, Counter] = defaultdict(Counter)
    no_results: Counter[str] = Counter()
    escalations: Counter[str] = Counter()
    for r in rows:
        p = r.props or {}
        if r.name == "topic_selected":
            topics[p["topic_id"]]["selected"] += 1
        elif r.name == "help_feedback" and p.get("target") == "topic":
            topics[p["id"]][p["value"]] += 1
        elif r.name == "help_feedback" and p.get("target") == "tree":
            trees[p["id"]][p["value"]] += 1
        elif r.name == "guided_help_started":
            tours[p["flow_id"]]["started"] += 1
        elif r.name == "guided_help_completed":
            tours[p["flow_id"]][p["result"]] += 1
        elif r.name == "troubleshooting_started":
            trees[p["tree_id"]]["started"] += 1
        elif r.name == "troubleshooting_completed":
            trees[p["tree_id"]][f"resolution_{p['resolution']}"] += 1
        elif r.name == "search_no_results":
            no_results[r.screen] += 1
        elif r.name in ("escalation_started", "escalation_submitted"):
            escalations[r.name] += 1
            if r.name == "escalation_started" and p.get("tree_id"):
                trees[p["tree_id"]]["escalated"] += 1

    def table(d: dict[str, Counter], key: str, sort_by: str) -> list[dict]:
        out = [{key: k, **dict(c)} for k, c in d.items()]
        return sorted(out, key=lambda x: -x.get(sort_by, 0))

    return {
        "days": days,
        "sessions": len(sessions),
        "events": len(rows),
        "opened_by_screen": [{"screen": s, "count": n} for s, n in opened_by_screen.most_common()],
        "entries": [{"entry": e, "count": n} for e, n in entries.most_common() if e],
        "topics": table(topics, "topic_id", "selected"),
        "tours": table(tours, "flow_id", "started"),
        "trees": table(trees, "tree_id", "started"),
        "no_results": [{"screen": s, "count": n} for s, n in no_results.most_common()],
        "escalations": {
            "started": escalations["escalation_started"],
            "submitted": escalations["escalation_submitted"],
        },
    }
