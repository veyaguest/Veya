"""מרכז שליטה בטלפנים — API.

- ``/admin/call-ops/*``     אדמין (Support ומעלה): יום, משימות, ציר זמן, חריגות,
                           הקצאה, שינוי תאריך, ביטול, שליטה בסבבים, ניהול טלפנים.
- ``/admin/call-ops/my/*`` טלפן (או אדמין): רק מה שמותר לו לראות.

כל חישוב "מי צריך שיחה" עובר ב-``app/call_ops.py``; כאן רק תצוגה, הרשאות ויומן.
"""
from __future__ import annotations

import secrets
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import (
    admin_audit, admin_rbac, auth, call_center, call_ops, event_cycle, event_terms,
    local_time, models, roles,
)
from app.auth import get_current_caller
from app.database import get_db

router = APIRouter(prefix="/admin/call-ops", tags=["call-ops"])

MAX_LIMIT = 200


# ── עזרים ─────────────────────────────────────────────────────────────────

def _today() -> date:
    return local_time.israel_date()


def _day(value: Optional[str]) -> date:
    try:
        return call_ops.parse_day(value, _today())
    except ValueError:
        raise HTTPException(status_code=400, detail="תאריך לא תקין")


def _relation(day: date, today: date) -> str:
    if day < today:
        return "past"
    if day == today:
        return "today"
    if day == today + timedelta(days=1):
        return "tomorrow"
    return "future"


def _mode(day: date, today: date) -> str:
    return "tasks" if day <= today + timedelta(days=1) else "preview"


def _hosts(event: models.Event) -> str:
    return event_terms.hosts_names(event.event_type, event.groom_name, event.bride_name) or f"אירוע #{event.id}"


def _ddmm(iso: str) -> str:
    if not iso or len(iso) < 10:
        return ""
    y, m, d = iso[:10].split("-")
    return f"{d}.{m}.{y}"


def _names(db: Session, ids) -> dict[int, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {
        u.id: (u.display_name or u.email)
        for u in db.scalars(select(models.User).where(models.User.id.in_(ids))).all()
    }


def _sync_for(db: Session, user: models.User) -> None:
    allowed = None if user.is_admin else call_center.visible_event_ids(db, user)
    if allowed is None:
        call_ops.sync(db)
    else:
        call_ops.sync(db, event_ids=allowed)
    db.commit()


# ── סכמות ─────────────────────────────────────────────────────────────────

class TaskRow(BaseModel):
    task_id: Optional[int]
    guest_id: int
    guest_name: str
    phone: str
    rsvp_status: str
    event_id: int
    event_label: str
    event_type: str
    event_date: str
    round_number: int
    total_rounds: int
    round_label: str
    reason: str
    reason_label: str
    planned_date: str
    due_date: str
    assignee_id: Optional[int]
    assignee_name: str
    status: str
    status_label: str
    status_tone: str
    attempts: int
    last_attempt_at: Optional[datetime]
    last_outcome: str
    handled_by_name: str
    closed_reason_label: str
    needs_attention: bool
    round_state: str = ""


class TaskPage(BaseModel):
    date: str
    mode: str
    group: str
    total: int
    limit: int
    offset: int
    items: list[TaskRow]


_OUTCOME_LABEL = {
    "confirmed": ("אישר/ה הגעה", "ok"),
    "declined": ("לא מגיע/ה", "neutral"),
    "no_answer": ("לא ענה/תה", "warn"),
    "busy": ("לא ניתן להשיג", "warn"),
    "wrong_number": ("מספר לא תקין", "bad"),
    "callback": ("ביקש/ה שיחה חוזרת", "info"),
}


def _status(task: Optional[models.CallTask], today_iso: str) -> tuple[str, str]:
    if task is None:
        return "מתוכנן", "neutral"
    if task.status == call_ops.OPEN:
        if task.reason == "callback":
            return "ביקש/ה שיחה חוזרת", "info"
        if task.due_date < today_iso:
            return "באיחור", "bad"
        return ("הוקצה לטלפן", "neutral") if task.assignee_id else ("ממתין לשיחה", "warn")
    if task.status == call_ops.DONE:
        return _OUTCOME_LABEL.get(task.last_outcome, ("טופל", "ok"))
    if task.status == call_ops.CLOSED_BY_RSVP:
        return call_ops.CLOSED_REASON_LABELS.get(task.closed_reason, "נסגר"), "ok"
    if task.status == call_ops.CANCELLED:
        return "בוטלה", "neutral"
    return call_ops.CLOSED_REASON_LABELS.get(task.closed_reason, "דולגה"), "neutral"


class _RoundCache:
    def __init__(self, db: Session):
        self.db = db
        self.cache: dict[int, dict[int, call_ops.RoundPlan]] = {}

    def plans(self, event: models.Event) -> dict[int, call_ops.RoundPlan]:
        if event.id not in self.cache:
            controls = call_ops._controls(self.db, [event.id])
            self.cache[event.id] = {
                p.round_number: p for p in call_ops.round_plans(event, datetime.utcnow(), controls)
            }
        return self.cache[event.id]


def _round_label(round_number: int, total: int) -> str:
    if round_number == call_ops.MANUAL_ROUND:
        return "שיחה ידנית"
    return f"טלפון {round_number} מתוך {total}" if total else f"טלפון {round_number}"


def _task_rows(db: Session, pairs: list[tuple[models.CallTask, models.Guest, models.Event]]) -> list[TaskRow]:
    today_iso = _today().isoformat()
    rounds = _RoundCache(db)
    names = _names(db, {t.assignee_id for t, _, _ in pairs} | {t.handled_by_id for t, _, _ in pairs})
    wa = call_ops.last_whatsapp(db, [g.id for _, g, _ in pairs])
    rows = []
    for t, g, e in pairs:
        plans = rounds.plans(e)
        total = len(plans)
        label, tone = _status(t, today_iso)
        rows.append(TaskRow(
            task_id=t.id, guest_id=g.id, guest_name=g.full_name, phone=g.phone or "",
            rsvp_status=g.rsvp_status, event_id=e.id, event_label=_hosts(e), event_type=e.event_type,
            event_date=e.event_date or "", round_number=t.round_number, total_rounds=total,
            round_label=_round_label(t.round_number, total), reason=t.reason,
            reason_label=call_ops.reason_label(t.reason, g, wa.get(g.id)),
            planned_date=t.planned_date, due_date=t.due_date, assignee_id=t.assignee_id,
            assignee_name=names.get(t.assignee_id, "") if t.assignee_id else "",
            status=t.status, status_label=label, status_tone=tone, attempts=t.attempts or 0,
            last_attempt_at=t.last_attempt_at, last_outcome=t.last_outcome or "",
            handled_by_name=names.get(t.handled_by_id, "") if t.handled_by_id else "",
            closed_reason_label=call_ops.CLOSED_REASON_LABELS.get(t.closed_reason, "") if t.closed_reason else "",
            needs_attention=(
                (t.attempts or 0) >= call_ops.many_attempts()
                or t.last_outcome == call_center.WRONG_NUMBER
                or (t.status == call_ops.OPEN and t.due_date < today_iso)
            ),
            round_state=plans.get(t.round_number).state if plans.get(t.round_number) else "",
        ))
    return rows


def _task_query(
    db: Session, user: models.User, *, day: date, group: str, event_id: Optional[int],
    assignee: Optional[str], round_number: Optional[int], event_type: str, q: str,
):
    T, G, E = models.CallTask, models.Guest, models.Event
    today_iso = _today().isoformat()
    stmt = (
        select(T, G, E).join(G, T.guest_id == G.id).join(E, T.event_id == E.id)
        .where(call_ops.group_filter(group, day.isoformat(), today_iso))
    )
    visible = call_ops._visible_filter(user, db)
    if visible is not None:
        stmt = stmt.where(visible)
    if event_id:
        stmt = stmt.where(T.event_id == event_id)
    if assignee == "none":
        stmt = stmt.where(T.assignee_id.is_(None))
    elif assignee:
        try:
            stmt = stmt.where(T.assignee_id == int(assignee))
        except ValueError:
            raise HTTPException(status_code=400, detail="טלפן לא תקין")
    if round_number is not None:
        stmt = stmt.where(T.round_number == round_number)
    if event_type:
        stmt = stmt.where(E.event_type == event_type)
    if q.strip():
        like = f"%{q.strip()}%"
        digits = "".join(ch for ch in q if ch.isdigit())
        conds = [G.full_name.ilike(like), E.groom_name.ilike(like), E.bride_name.ilike(like)]
        if len(digits) >= 3:
            conds.append(G.phone.ilike(f"%{digits}%"))
        stmt = stmt.where(or_(*conds))
    return stmt


def _preview_rows(db: Session, day: date, user: models.User, event_id: Optional[int], q: str) -> list[TaskRow]:
    allowed = None if user.is_admin else call_center.visible_event_ids(db, user)
    rows = call_ops.preview(db, day, event_id=event_id, allowed_event_ids=allowed)
    if q.strip():
        needle = q.strip()
        rows = [r for r in rows if needle in (r.guest.full_name or "") or needle in (r.guest.phone or "") or needle in _hosts(r.event)]
    names = _names(db, {r.default_assignee for r in rows})
    day_iso = day.isoformat()
    return [
        TaskRow(
            task_id=None, guest_id=r.guest.id, guest_name=r.guest.full_name, phone=r.guest.phone or "",
            rsvp_status=r.guest.rsvp_status, event_id=r.event.id, event_label=_hosts(r.event),
            event_type=r.event.event_type, event_date=r.event.event_date or "",
            round_number=r.round.round_number, total_rounds=r.round.total_rounds,
            round_label=_round_label(r.round.round_number, r.round.total_rounds),
            reason="maybe" if r.guest.rsvp_status == "maybe" else "no_response",
            reason_label=call_ops.REASON_LABELS["maybe" if r.guest.rsvp_status == "maybe" else "no_response"],
            planned_date=day_iso, due_date=day_iso, assignee_id=r.default_assignee,
            assignee_name=names.get(r.default_assignee, "") if r.default_assignee else "",
            status="planned", status_label="מתוכנן", status_tone="neutral", attempts=0,
            last_attempt_at=None, last_outcome="", handled_by_name="", closed_reason_label="",
            needs_attention=False,
        )
        for r in rows
    ]


# ── יום ───────────────────────────────────────────────────────────────────

class RoundSummary(BaseModel):
    event_id: int
    event_label: str
    event_date: str
    round_number: int
    total_rounds: int
    round_label: str
    state: str
    total: int
    handled: int
    pending: int
    no_answer: int
    callback: int
    complete: bool


class CallerLoad(BaseModel):
    id: int
    name: str
    availability: str
    available: bool
    tasks: int
    handled: int
    pending: int
    next_day: int
    capacity: Optional[int]
    overloaded: bool


class ExceptionItem(BaseModel):
    key: str
    severity: str
    title: str
    detail: str
    count: int
    group: str = ""
    assignee: str = ""
    event_ids: list[int] = Field(default_factory=list)


class DaySummary(BaseModel):
    date: str
    today: str
    relation: str
    mode: str
    counts: dict[str, int]
    rounds: list[RoundSummary]
    callers: list[CallerLoad]
    exceptions: list[ExceptionItem]


def _caller_loads(db: Session, day: date, visible=None) -> list[CallerLoad]:
    T = models.CallTask
    day_iso, next_iso = day.isoformat(), (day + timedelta(days=1)).isoformat()
    callers = db.scalars(
        select(models.User).where(models.User.account_type == roles.PHONE_AGENT)
        .order_by(models.User.display_name, models.User.id)
    ).all()
    if not callers:
        return []
    ids = [c.id for c in callers]
    profs = call_ops.profiles(db, ids)
    stats: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for uid, status, due, planned, n in db.execute(
        select(T.assignee_id, T.status, T.due_date, T.planned_date, func.count(T.id))
        .where(T.assignee_id.in_(ids), or_(T.planned_date.in_((day_iso, next_iso)), T.due_date.in_((day_iso, next_iso))))
        .group_by(T.assignee_id, T.status, T.due_date, T.planned_date)
    ).all():
        s = stats[uid]
        if planned == day_iso or (status == call_ops.OPEN and due == day_iso):
            s["tasks"] += n
            if status in call_ops.HANDLED and planned == day_iso:
                s["handled"] += n
            if status == call_ops.OPEN and due == day_iso:
                s["pending"] += n
        if (status == call_ops.OPEN and due == next_iso) or planned == next_iso:
            s["next"] += n
    active_loads = [stats[c.id]["tasks"] for c in callers if not c.disabled]
    avg = (sum(active_loads) / len(active_loads)) if active_loads else 0
    rows = []
    for c in callers:
        p = profs.get(c.id)
        s = stats[c.id]
        cap = p.daily_capacity if p else None
        overloaded = (cap is not None and s["pending"] > cap) or (
            len(active_loads) >= 2 and avg > 0 and s["tasks"] > max(10, 2 * avg)
        )
        rows.append(CallerLoad(
            id=c.id, name=c.display_name or c.email,
            availability=call_ops.availability_label(c, p, day),
            available=call_ops.is_available(c, p, day),
            tasks=s["tasks"], handled=s["handled"], pending=s["pending"], next_day=s["next"],
            capacity=cap, overloaded=overloaded,
        ))
    return rows


def _round_summaries(db: Session, day: date) -> list[RoundSummary]:
    T = models.CallTask
    day_iso = day.isoformat()
    agg: dict[tuple[int, int], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for eid, rnd, status, outcome, reason, n in db.execute(
        select(T.event_id, T.round_number, T.status, T.last_outcome, T.reason, func.count(T.id))
        .where(T.planned_date == day_iso, T.status.not_in((call_ops.CANCELLED,)))
        .group_by(T.event_id, T.round_number, T.status, T.last_outcome, T.reason)
    ).all():
        a = agg[(eid, rnd)]
        a["total"] += n
        if status in call_ops.HANDLED:
            a["handled"] += n
        if status == call_ops.OPEN:
            a["pending"] += n
            if reason == "callback":
                a["callback"] += n
        if status == call_ops.DONE and outcome in call_ops.UNREACHABLE_OUTCOMES:
            a["no_answer"] += n
    if not agg:
        return []
    events = {e.id: e for e in db.scalars(select(models.Event).where(models.Event.id.in_({k[0] for k in agg}))).all()}
    rounds = _RoundCache(db)
    out = []
    for (eid, rnd), a in agg.items():
        e = events.get(eid)
        if e is None:
            continue
        plans = rounds.plans(e)
        plan = plans.get(rnd)
        out.append(RoundSummary(
            event_id=eid, event_label=_hosts(e), event_date=e.event_date or "", round_number=rnd,
            total_rounds=len(plans), round_label=_round_label(rnd, len(plans)),
            state=plan.state if plan else "", total=a["total"], handled=a["handled"],
            pending=a["pending"], no_answer=a["no_answer"], callback=a["callback"],
            complete=a["pending"] == 0,
        ))
    out.sort(key=lambda r: (r.complete, -r.pending, r.event_label))
    return out


def _exceptions(db: Session, today: date) -> list[ExceptionItem]:
    T = models.CallTask
    t_iso = today.isoformat()
    items: list[ExceptionItem] = []

    overdue = db.execute(
        select(T.event_id, func.count(T.id)).where(T.status == call_ops.OPEN, T.due_date < t_iso).group_by(T.event_id)
    ).all()
    if overdue:
        items.append(ExceptionItem(
            key="overdue", severity="critical", title="שיחות שהיו צריכות להתבצע ולא טופלו",
            detail=f"ב-{len(overdue)} אירועים", count=sum(n for _, n in overdue), group="overdue",
            event_ids=[e for e, _ in overdue],
        ))

    unassigned = db.scalar(select(func.count(T.id)).where(
        T.status == call_ops.OPEN, T.due_date == t_iso, T.assignee_id.is_(None),
    )) or 0
    if unassigned:
        items.append(ExceptionItem(
            key="unassigned", severity="warning", title="משימות להיום בלי טלפן",
            detail="אפשר לחלק אוטומטית או להקצות ידנית", count=unassigned, group="pending", assignee="none",
        ))

    no_caller_events = db.execute(
        select(T.event_id).where(T.status == call_ops.OPEN, T.due_date <= t_iso)
        .group_by(T.event_id).having(func.count(T.assignee_id) == 0)
    ).scalars().all()
    if no_caller_events:
        with_default = set(db.scalars(select(models.CallAssignment.event_id).where(
            models.CallAssignment.event_id.in_(no_caller_events)
        )).all())
        orphan = [e for e in no_caller_events if e not in with_default]
        if orphan:
            items.append(ExceptionItem(
                key="events_without_caller", severity="warning", title="אירועים עם שיחות פתוחות ובלי אף טלפן",
                detail="אין טלפן קבוע לאירוע ואף משימה לא הוקצתה", count=len(orphan), group="pending",
                assignee="none", event_ids=orphan,
            ))

    threshold = call_ops.many_attempts()
    many = db.scalar(select(func.count(T.id)).where(T.status == call_ops.OPEN, T.attempts >= threshold)) or 0
    if many:
        items.append(ExceptionItem(
            key="many_attempts", severity="info", title=f"אורחים עם {threshold} ניסיונות ומעלה",
            detail="שווה לבדוק מול בעלי האירוע אם יש דרך אחרת להשיג", count=many, group="followup",
        ))

    callers = db.scalars(select(models.User).where(models.User.account_type == roles.PHONE_AGENT)).all()
    profs = call_ops.profiles(db, [c.id for c in callers])
    unavailable = [c.id for c in callers if not call_ops.is_available(c, profs.get(c.id), today)]
    if unavailable:
        stuck = db.execute(
            select(T.assignee_id, func.count(T.id)).where(
                T.status == call_ops.OPEN, T.due_date <= t_iso, T.assignee_id.in_(unavailable),
            ).group_by(T.assignee_id)
        ).all()
        if stuck:
            items.append(ExceptionItem(
                key="unavailable_caller", severity="critical", title="משימות אצל טלפן לא זמין",
                detail="הטלפן לא פעיל או בחופשה — צריך להעביר", count=sum(n for _, n in stuck), group="pending",
                assignee=str(stuck[0][0]) if len(stuck) == 1 else "",
            ))

    overloaded = [c for c in _caller_loads(db, today) if c.overloaded]
    if overloaded:
        items.append(ExceptionItem(
            key="overloaded", severity="warning", title="טלפנים עם עומס חריג",
            detail=", ".join(c.name for c in overloaded[:4]), count=len(overloaded),
        ))

    incomplete = db.execute(
        select(T.event_id, T.round_number).where(T.status == call_ops.OPEN, T.planned_date < t_iso)
        .group_by(T.event_id, T.round_number)
    ).all()
    if incomplete:
        items.append(ExceptionItem(
            key="incomplete_rounds", severity="warning", title="סבבים שעברו ולא הושלמו",
            detail="נשארו בהם שיחות פתוחות", count=len(incomplete), group="overdue",
            event_ids=sorted({e for e, _ in incomplete}),
        ))

    paused = db.scalar(select(func.count(models.CallRoundControl.id)).where(
        models.CallRoundControl.state.in_(("paused", "stopped"))
    )) or 0
    if paused:
        items.append(ExceptionItem(
            key="paused_rounds", severity="info", title="סבבים מושהים או עצורים",
            detail="לא נוצרות בהם משימות חדשות", count=paused,
        ))

    # נתונים חסרים: מוזמנים פתוחים בלי טלפון באירועים שיש בהם שיחות פתוחות היום
    active_events = db.scalars(
        select(T.event_id).where(T.status == call_ops.OPEN, T.due_date <= t_iso).distinct()
    ).all()
    if active_events:
        missing = db.scalar(select(func.count(models.Guest.id)).where(
            models.Guest.event_id.in_(active_events),
            models.Guest.rsvp_status.in_(call_center.OPEN_STATUSES),
            models.Guest.phone == "",
        )) or 0
        if missing:
            items.append(ExceptionItem(
                key="missing_phone", severity="info", title="אורחים בלי מספר טלפון",
                detail="לא נכנסים לתור השיחות עד שבעלי האירוע יוסיפו מספר", count=missing,
                event_ids=list(active_events)[:50],
            ))

    dupes = db.scalar(select(func.count()).select_from(
        select(T.guest_id).where(
            T.status == call_ops.OPEN, T.round_number != call_ops.MANUAL_ROUND, T.planned_date <= t_iso,
        )
        .group_by(T.guest_id).having(func.count(T.id) > 1).subquery()
    )) or 0
    if dupes:
        items.append(ExceptionItem(
            key="duplicates", severity="warning", title="אורחים עם יותר ממשימה פתוחה אחת",
            detail="לא אמור לקרות — שווה לבדוק את האורחים האלה", count=dupes,
        ))
    return items


@router.get("/day", response_model=DaySummary)
def day_summary(
    date_: Optional[str] = Query(None, alias="date"),
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("calls.operate")),
):
    _sync_for(db, admin)
    today = _today()
    day = _day(date_)
    mode = _mode(day, today)
    if mode == "tasks":
        counts = call_ops.day_counts(db, day, today)
        rounds = _round_summaries(db, day)
    else:
        rows = call_ops.preview(db, day)
        assigned = sum(1 for r in rows if r.default_assignee)
        counts = {
            "planned": len(rows), "handled": 0, "pending": len(rows), "not_handled": 0, "overdue": 0,
            "unreachable": 0, "followup": 0, "cancelled": 0,
            "assigned": assigned, "unassigned": len(rows) - assigned,
        }
        grouped: dict[int, list[call_ops.PreviewRow]] = defaultdict(list)
        for r in rows:
            grouped[r.event.id].append(r)
        rounds = [
            RoundSummary(
                event_id=eid, event_label=_hosts(items[0].event), event_date=items[0].event.event_date or "",
                round_number=items[0].round.round_number, total_rounds=items[0].round.total_rounds,
                round_label=_round_label(items[0].round.round_number, items[0].round.total_rounds),
                state=items[0].round.state, total=len(items), handled=0, pending=len(items),
                no_answer=0, callback=0, complete=False,
            )
            for eid, items in grouped.items()
        ]
    return DaySummary(
        date=day.isoformat(), today=today.isoformat(), relation=_relation(day, today), mode=mode,
        counts=counts, rounds=rounds, callers=_caller_loads(db, day),
        exceptions=_exceptions(db, today) if day == today else [],
    )


@router.get("/tasks", response_model=TaskPage)
def list_tasks(
    date_: Optional[str] = Query(None, alias="date"),
    group: str = "all",
    event_id: Optional[int] = None,
    assignee: Optional[str] = None,
    round_number: Optional[int] = Query(None, alias="round"),
    event_type: str = "",
    q: str = Query("", max_length=100),
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("calls.operate")),
):
    return _list_tasks_impl(db, admin, date_, group, event_id, assignee, round_number, event_type, q, limit, offset)


def _list_tasks_impl(db, user, date_, group, event_id, assignee, round_number, event_type, q, limit, offset) -> TaskPage:
    if group not in call_ops.GROUPS:
        raise HTTPException(status_code=400, detail="קבוצה לא מוכרת")
    _sync_for(db, user)
    today = _today()
    day = _day(date_)
    if _mode(day, today) == "preview":
        rows = _preview_rows(db, day, user, event_id, q)
        if assignee == "none":
            rows = [r for r in rows if r.assignee_id is None]
        elif assignee:
            rows = [r for r in rows if str(r.assignee_id) == assignee]
        return TaskPage(date=day.isoformat(), mode="preview", group=group, total=len(rows), limit=limit,
                        offset=offset, items=rows[offset:offset + limit])
    stmt = _task_query(db, user, day=day, group=group, event_id=event_id, assignee=assignee,
                       round_number=round_number, event_type=event_type, q=q)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    T, G, E = models.CallTask, models.Guest, models.Event
    pairs = db.execute(
        stmt.order_by(T.due_date, E.event_date, E.id, G.full_name, T.id).limit(limit).offset(offset)
    ).all()
    return TaskPage(date=day.isoformat(), mode="tasks", group=group, total=total, limit=limit,
                    offset=offset, items=_task_rows(db, [tuple(p) for p in pairs]))


class TimelineDay(BaseModel):
    date: str
    mode: str
    planned: int
    handled: int
    pending: int
    unassigned: int


@router.get("/timeline", response_model=list[TimelineDay])
def timeline(
    start: Optional[str] = None,
    days: int = Query(14, ge=1, le=45),
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("calls.operate")),
):
    _sync_for(db, admin)
    today = _today()
    first = _day(start) if start else today - timedelta(days=2)
    T = models.CallTask
    out = []
    horizon = today + timedelta(days=1)
    task_days = [first + timedelta(days=i) for i in range(days) if first + timedelta(days=i) <= horizon]
    preview_days = [first + timedelta(days=i) for i in range(days) if first + timedelta(days=i) > horizon]
    agg: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    if task_days:
        isos = [d.isoformat() for d in task_days]
        for planned, status, assignee_null, n in db.execute(
            select(T.planned_date, T.status, T.assignee_id.is_(None), func.count(T.id))
            .where(T.planned_date.in_(isos)).group_by(T.planned_date, T.status, T.assignee_id.is_(None))
        ).all():
            a = agg[planned]
            if status == call_ops.CANCELLED:
                continue
            a["planned"] += n
            if status in call_ops.HANDLED:
                a["handled"] += n
        for due, assignee_null, n in db.execute(
            select(T.due_date, T.assignee_id.is_(None), func.count(T.id))
            .where(T.due_date.in_(isos), T.status == call_ops.OPEN).group_by(T.due_date, T.assignee_id.is_(None))
        ).all():
            agg[due]["pending"] += n
            if assignee_null:
                agg[due]["unassigned"] += n
    for d in task_days:
        a = agg[d.isoformat()]
        out.append(TimelineDay(date=d.isoformat(), mode="tasks", planned=a["planned"], handled=a["handled"],
                               pending=a["pending"], unassigned=a["unassigned"]))
    previews = call_ops.preview_counts(db, preview_days)
    for d in preview_days:
        planned, unassigned = previews.get(d.isoformat(), (0, 0))
        out.append(TimelineDay(date=d.isoformat(), mode="preview", planned=planned, handled=0,
                               pending=planned, unassigned=unassigned))
    return out


# ── כרטיס אורח ────────────────────────────────────────────────────────────

class HistoryItem(BaseModel):
    at: Optional[datetime]
    channel: str          # whatsapp / phone / task
    title: str
    detail: str
    actor: str = ""
    tone: str = "neutral"


class GuestCard(BaseModel):
    guest_id: int
    guest_name: str
    phone: str
    rsvp_status: str
    party_size: int
    confirmed_count: Optional[int]
    event_id: int
    event_label: str
    event_date: str
    event_type: str
    current: Optional[TaskRow]
    tasks: list[TaskRow]
    history: list[HistoryItem]
    next_action: str


_KIND_LABELS = {
    "invitation": "הזמנה", "rsvp_request": "בקשת אישור", "reminder_1": "תזכורת ראשונה",
    "reminder_2": "תזכורת שנייה", "final_reminder": "תזכורת שלישית", "event_day": "הודעת יום האירוע",
    "thank_you": "תודה", "rsvp_reply": "תשובת המוזמן",
}
_MSG_STATUS = {
    "sent": "נשלחה", "delivered": "נמסרה", "read": "נקראה", "failed": "נכשלה",
    "queued": "ממתינה", "pending": "ממתינה", "no_valid_number": "אין מספר תקין", "blocked": "חסום",
}


def _guest_card(db: Session, user: models.User, guest_id: int) -> GuestCard:
    guest = db.get(models.Guest, guest_id)
    if guest is None:
        raise HTTPException(status_code=404, detail="האורח לא נמצא")
    event = db.get(models.Event, guest.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="האורח לא נמצא")
    T = models.CallTask
    tasks = db.scalars(select(T).where(T.guest_id == guest_id).order_by(T.event_cycle, T.round_number)).all()
    if not user.is_admin:
        visible = call_center.can_access_event(db, user, event.id) or any(t.assignee_id == user.id for t in tasks)
        if not visible:
            raise HTTPException(status_code=404, detail="האורח לא נמצא")
    rows = _task_rows(db, [(t, guest, event) for t in tasks])
    current = next((r for r in rows if r.status == call_ops.OPEN), None)

    history: list[HistoryItem] = []
    for m in db.scalars(select(models.Message).where(models.Message.guest_id == guest_id)).all():
        inbound = m.direction == "inbound"
        history.append(HistoryItem(
            at=m.created_at, channel="whatsapp",
            title=("WhatsApp — הגיב/ה" if inbound else f"WhatsApp — {_KIND_LABELS.get(m.kind, m.kind)}"),
            detail=(m.body or "")[:200] if inbound else _MSG_STATUS.get(m.status or "", m.status or ""),
            tone="bad" if m.status == "failed" else "neutral",
        ))
    logs = call_center.guest_call_history(db, guest_id)
    names = _names(db, {lg.created_by_id for lg in logs})
    for lg in logs:
        label, tone = _OUTCOME_LABEL.get(lg.outcome, (lg.outcome, "neutral"))
        detail = lg.note or ""
        if lg.outcome == "callback" and lg.callback_at:
            detail = (f"לחזור ב-{local_time.to_israel(lg.callback_at).strftime('%d.%m %H:%M')}. " + detail).strip()
        history.append(HistoryItem(
            at=lg.created_at, channel="phone", title=f"שיחה — {label}", detail=detail,
            actor=names.get(lg.created_by_id, ""), tone=tone,
        ))
    history.sort(key=lambda h: h.at or datetime.min, reverse=True)

    if guest.rsvp_status == "confirmed":
        next_action = "אישר/ה הגעה — אין צורך בשיחה נוספת"
    elif guest.rsvp_status == "declined":
        next_action = "לא מגיע/ה — אין צורך בשיחה נוספת"
    elif current is not None:
        who = f" אצל {current.assignee_name}" if current.assignee_name else " (עדיין בלי טלפן)"
        next_action = f"{current.round_label} ב-{_ddmm(current.due_date)}{who}"
    else:
        plans = call_ops.round_plans(event, datetime.utcnow(), call_ops._controls(db, [event.id]))
        upcoming = [p for p in plans if p.date > _today()]
        next_action = (
            f"הסבב הבא: טלפון {upcoming[0].round_number} ב-{upcoming[0].date.strftime('%d.%m.%Y')}"
            if upcoming else "אין סבב שיחות נוסף מתוכנן"
        )
    return GuestCard(
        guest_id=guest.id, guest_name=guest.full_name, phone=guest.phone or "", rsvp_status=guest.rsvp_status,
        party_size=guest.party_size or 1, confirmed_count=guest.confirmed_count, event_id=event.id,
        event_label=_hosts(event), event_date=event.event_date or "", event_type=event.event_type,
        current=current, tasks=rows, history=history, next_action=next_action,
    )


@router.get("/guests/{guest_id}", response_model=GuestCard)
def guest_card(
    guest_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("calls.operate")),
):
    return _guest_card(db, admin, guest_id)


class GuestHit(BaseModel):
    guest_id: int
    guest_name: str
    phone: str
    event_id: int
    event_label: str
    rsvp_status: str
    round_label: str
    status_label: str
    status_tone: str
    assignee_name: str
    last_attempt_at: Optional[datetime]


@router.get("/search", response_model=list[GuestHit])
def search_guests(
    q: str = Query(..., min_length=2, max_length=100),
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("calls.operate")),
):
    """חיפוש אורח מהיר — שם / טלפון / שם אירוע, עם מצב המשימה האחרונה שלו."""
    G, E, T = models.Guest, models.Event, models.CallTask
    like = f"%{q.strip()}%"
    digits = "".join(ch for ch in q if ch.isdigit())
    conds = [G.full_name.ilike(like), E.groom_name.ilike(like), E.bride_name.ilike(like)]
    if len(digits) >= 3:
        conds.append(G.phone.ilike(f"%{digits}%"))
    found = db.execute(
        select(G, E).join(E, G.event_id == E.id).where(or_(*conds)).order_by(G.full_name).limit(20)
    ).all()
    if not found:
        return []
    latest: dict[int, models.CallTask] = {}
    for t in db.scalars(
        select(T).where(T.guest_id.in_([g.id for g, _ in found])).order_by(T.event_cycle, T.round_number, T.id)
    ).all():
        latest[t.guest_id] = t
    rows = {r.guest_id: r for r in _task_rows(db, [(latest[g.id], g, e) for g, e in found if g.id in latest])}
    out = []
    for g, e in found:
        r = rows.get(g.id)
        out.append(GuestHit(
            guest_id=g.id, guest_name=g.full_name, phone=g.phone or "", event_id=e.id, event_label=_hosts(e),
            rsvp_status=g.rsvp_status, round_label=r.round_label if r else "",
            status_label=r.status_label if r else "אין משימות שיחה",
            status_tone=r.status_tone if r else "neutral", assignee_name=r.assignee_name if r else "",
            last_attempt_at=r.last_attempt_at if r else None,
        ))
    return out


# ── פעולות על משימות ──────────────────────────────────────────────────────

class TaskIds(BaseModel):
    task_ids: list[int] = Field(min_length=1, max_length=2000)
    reason: str = Field(default="", max_length=500)


class AssignWrite(TaskIds):
    assignee_id: Optional[int] = None


class RescheduleWrite(TaskIds):
    due_date: str


class BulkResult(BaseModel):
    updated: int
    skipped: int
    message: str


def _load_tasks(db: Session, ids: list[int]) -> list[models.CallTask]:
    tasks = db.scalars(select(models.CallTask).where(models.CallTask.id.in_(set(ids)))).all()
    if not tasks:
        raise HTTPException(status_code=404, detail="המשימות לא נמצאו")
    return list(tasks)


def _validate_assignee(db: Session, assignee_id: int, day: date) -> models.User:
    user = db.get(models.User, assignee_id)
    if user is None or not roles.is_phone_agent(user):
        raise HTTPException(status_code=400, detail="הטלפן לא נמצא")
    if not call_ops.is_available(user, call_ops.profiles(db, [user.id]).get(user.id), day):
        raise HTTPException(status_code=400, detail="הטלפן לא זמין ליום הזה — אי אפשר להקצות לו משימות")
    return user


@router.post("/tasks/assign", response_model=BulkResult)
def assign_tasks(
    payload: AssignWrite,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("calls.operate")),
):
    tasks = [t for t in _load_tasks(db, payload.task_ids)]
    open_tasks = [t for t in tasks if t.status == call_ops.OPEN]
    skipped = len(tasks) - len(open_tasks)
    if not open_tasks:
        raise HTTPException(status_code=400, detail="אפשר להקצות רק משימות פתוחות")
    target = None
    if payload.assignee_id is not None:
        latest_due = max(call_ops.parse_day(t.due_date, _today()) for t in open_tasks)
        earliest_due = min(max(call_ops.parse_day(t.due_date, _today()), _today()) for t in open_tasks)
        target = _validate_assignee(db, payload.assignee_id, earliest_due)
        if latest_due != earliest_due:
            _validate_assignee(db, payload.assignee_id, latest_due)
    before = defaultdict(int)
    for t in open_tasks:
        before[t.assignee_id] += 1
    names = _names(db, set(before) | ({payload.assignee_id} if payload.assignee_id else set()))
    now = datetime.utcnow()
    changed = 0
    for t in open_tasks:
        if t.assignee_id != payload.assignee_id:
            t.assignee_id = payload.assignee_id
            t.updated_at = now
            changed += 1
    if changed:
        from_label = ", ".join(
            f"{names.get(uid, 'ללא טלפן') if uid else 'ללא טלפן'} ({n})" for uid, n in before.items()
        )
        to_label = names.get(payload.assignee_id, "") if payload.assignee_id else "ללא טלפן"
        single = open_tasks[0] if len(open_tasks) == 1 else None
        guest = db.get(models.Guest, single.guest_id) if single else None
        admin_audit.record(
            db, admin, domain="calls", action="call_task.assign",
            summary=(
                f"העביר/ה משימת שיחה של {guest.full_name} ל{to_label}" if guest
                else f"העביר/ה {changed} משימות שיחה ל{to_label}"
            ),
            target_type="call_task", target_id=single.id if single else "",
            target_label=guest.full_name if guest else f"{changed} משימות",
            event_id=single.event_id if single else None,
            changes=[admin_audit.change("assignee", "טלפן", from_label, to_label)],
            reason=payload.reason, request=request,
        )
    db.commit()
    return BulkResult(updated=changed, skipped=skipped,
                      message=f"{changed} משימות הוקצו" if target else f"{changed} משימות שוחררו מהקצאה")


class AutoAssignPreviewWrite(BaseModel):
    date: Optional[str] = None
    task_ids: Optional[list[int]] = None
    caller_ids: Optional[list[int]] = None


class ProposalRow(BaseModel):
    task_id: int
    guest_name: str
    event_label: str
    assignee_id: int
    assignee_name: str
    why: str


class AutoAssignPreview(BaseModel):
    date: str
    proposals: list[ProposalRow]
    by_caller: list[dict]
    unassignable: int
    note: str


@router.post("/tasks/auto-assign/preview", response_model=AutoAssignPreview)
def auto_assign_preview(
    payload: AutoAssignPreviewWrite,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("calls.operate")),
):
    """הצעת חלוקה — לא משנה כלום. האדמין רואה, מאשר, ורק אז ``apply``."""
    day = _day(payload.date)
    T = models.CallTask
    stmt = select(T).where(T.status == call_ops.OPEN, T.assignee_id.is_(None))
    if payload.task_ids:
        stmt = stmt.where(T.id.in_(payload.task_ids))
    else:
        stmt = stmt.where(T.due_date == day.isoformat())
    tasks = list(db.scalars(stmt).all())
    proposals, leftover, note = call_ops.propose_assignments(db, tasks, day, payload.caller_ids)
    by_task = {t.id: t for t in tasks}
    guests = {g.id: g for g in db.scalars(select(models.Guest).where(models.Guest.id.in_({t.guest_id for t in tasks} or {0}))).all()}
    events = {e.id: e for e in db.scalars(select(models.Event).where(models.Event.id.in_({t.event_id for t in tasks} or {0}))).all()}
    names = _names(db, {p.assignee_id for p in proposals})
    counts: dict[int, int] = defaultdict(int)
    for p in proposals:
        counts[p.assignee_id] += 1
    return AutoAssignPreview(
        date=day.isoformat(),
        proposals=[
            ProposalRow(
                task_id=p.task_id, guest_name=guests[by_task[p.task_id].guest_id].full_name,
                event_label=_hosts(events[by_task[p.task_id].event_id]), assignee_id=p.assignee_id,
                assignee_name=names.get(p.assignee_id, ""), why=p.why,
            )
            for p in proposals
        ],
        by_caller=[{"id": uid, "name": names.get(uid, ""), "count": n} for uid, n in sorted(counts.items(), key=lambda x: -x[1])],
        unassignable=len(leftover), note=note,
    )


class AutoAssignApplyWrite(BaseModel):
    date: Optional[str] = None
    assignments: list[dict] = Field(min_length=1, max_length=5000)


@router.post("/tasks/auto-assign/apply", response_model=BulkResult)
def auto_assign_apply(
    payload: AutoAssignApplyWrite,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("calls.operate")),
):
    """מבצע הצעה שאושרה. כל הקצאה נבדקת מחדש: משימה שכבר הוקצתה בינתיים
    (או טלפן שהפך ללא זמין) — מדולגת, לא נדרסת."""
    day = _day(payload.date)
    wanted: dict[int, int] = {}
    for a in payload.assignments:
        try:
            wanted[int(a["task_id"])] = int(a["assignee_id"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=400, detail="הקצאה לא תקינה")
    tasks = _load_tasks(db, list(wanted))
    users = {u.id: u for u in db.scalars(select(models.User).where(models.User.id.in_(set(wanted.values())))).all()}
    profs = call_ops.profiles(db, users.keys())
    now = datetime.utcnow()
    applied = skipped = 0
    per_caller: dict[int, int] = defaultdict(int)
    for t in tasks:
        uid = wanted[t.id]
        user = users.get(uid)
        if t.status != call_ops.OPEN or t.assignee_id is not None or user is None or not call_ops.is_available(user, profs.get(uid), day):
            skipped += 1
            continue
        t.assignee_id = uid
        t.updated_at = now
        applied += 1
        per_caller[uid] += 1
    if applied:
        names = _names(db, per_caller.keys())
        admin_audit.record(
            db, admin, domain="calls", action="call_task.auto_assign",
            summary=f"חילק/ה אוטומטית {applied} משימות שיחה ל-{len(per_caller)} טלפנים",
            target_type="call_task", target_label=f"{applied} משימות",
            changes=[admin_audit.change("distribution", "חלוקה", "ללא טלפן",
                                        ", ".join(f"{names.get(u, u)}: {n}" for u, n in per_caller.items()))],
            request=request,
        )
    db.commit()
    return BulkResult(updated=applied, skipped=skipped, message=f"{applied} משימות חולקו"
                      + (f", {skipped} דולגו (כבר הוקצו או שהטלפן לא זמין)" if skipped else ""))


@router.post("/tasks/reschedule", response_model=BulkResult)
def reschedule_tasks(
    payload: RescheduleWrite,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("calls.operate")),
):
    new_day = _day(payload.due_date)
    if new_day < _today():
        raise HTTPException(status_code=400, detail="אי אפשר לקבוע שיחה לתאריך שעבר")
    tasks = _load_tasks(db, payload.task_ids)
    open_tasks = [t for t in tasks if t.status == call_ops.OPEN]
    if not open_tasks:
        raise HTTPException(status_code=400, detail="אפשר לשנות תאריך רק למשימות פתוחות")
    now = datetime.utcnow()
    before = sorted({t.due_date for t in open_tasks})
    for t in open_tasks:
        t.due_date = new_day.isoformat()
        t.pinned = True
        t.updated_at = now
    admin_audit.record(
        db, admin, domain="calls", action="call_task.reschedule",
        summary=f"שינה/תה תאריך ל-{len(open_tasks)} משימות שיחה",
        target_type="call_task", target_id=open_tasks[0].id if len(open_tasks) == 1 else "",
        target_label=f"{len(open_tasks)} משימות", event_id=open_tasks[0].event_id if len(open_tasks) == 1 else None,
        changes=[admin_audit.change("due_date", "מועד שיחה", ", ".join(_ddmm(d) for d in before), _ddmm(new_day.isoformat()))],
        reason=payload.reason, request=request,
    )
    db.commit()
    return BulkResult(updated=len(open_tasks), skipped=len(tasks) - len(open_tasks),
                      message=f"{len(open_tasks)} משימות הועברו ל-{new_day.strftime('%d.%m.%Y')}")


@router.post("/tasks/cancel", response_model=BulkResult)
def cancel_tasks(
    payload: TaskIds,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("calls.operate")),
):
    if len(payload.reason.strip()) < 3:
        raise HTTPException(status_code=400, detail="צריך לכתוב סיבה לביטול")
    tasks = _load_tasks(db, payload.task_ids)
    open_tasks = [t for t in tasks if t.status == call_ops.OPEN]
    now = datetime.utcnow()
    for t in open_tasks:
        t.status, t.closed_reason, t.closed_at, t.pinned, t.updated_at = call_ops.CANCELLED, "manual", now, True, now
        t.handled_by_id = admin.id
    if open_tasks:
        admin_audit.record(
            db, admin, domain="calls", action="call_task.cancel",
            summary=f"ביטל/ה {len(open_tasks)} משימות שיחה", target_type="call_task",
            target_id=open_tasks[0].id if len(open_tasks) == 1 else "", target_label=f"{len(open_tasks)} משימות",
            changes=[admin_audit.change("status", "סטטוס", "פתוחה", "בוטלה")],
            reason=payload.reason, request=request,
        )
    db.commit()
    return BulkResult(updated=len(open_tasks), skipped=len(tasks) - len(open_tasks),
                      message=f"{len(open_tasks)} משימות בוטלו")


@router.post("/tasks/reopen", response_model=BulkResult)
def reopen_tasks(
    payload: TaskIds,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("calls.operate")),
):
    tasks = _load_tasks(db, payload.task_ids)
    guests = {g.id: g for g in db.scalars(select(models.Guest).where(models.Guest.id.in_({t.guest_id for t in tasks}))).all()}
    today_iso = _today().isoformat()
    now = datetime.utcnow()
    reopened = []
    for t in tasks:
        g = guests.get(t.guest_id)
        if t.status in (call_ops.CANCELLED, call_ops.SKIPPED, call_ops.DONE) and g is not None and g.rsvp_status in call_center.OPEN_STATUSES:
            t.status, t.closed_reason, t.closed_at, t.pinned, t.updated_at = call_ops.OPEN, "", None, True, now
            t.due_date = max(t.due_date, today_iso)
            reopened.append(t)
    if reopened:
        admin_audit.record(
            db, admin, domain="calls", action="call_task.reopen",
            summary=f"פתח/ה מחדש {len(reopened)} משימות שיחה", target_type="call_task",
            target_label=f"{len(reopened)} משימות", reason=payload.reason, request=request,
        )
    db.commit()
    return BulkResult(updated=len(reopened), skipped=len(tasks) - len(reopened),
                      message=f"{len(reopened)} משימות נפתחו מחדש"
                      + ("" if len(reopened) == len(tasks) else " (אורח שכבר אישר או ביטל לא נפתח)"))


class ManualTaskWrite(BaseModel):
    guest_id: int
    due_date: Optional[str] = None
    assignee_id: Optional[int] = None
    note: str = Field(default="", max_length=500)


@router.post("/tasks/manual", response_model=TaskRow)
def add_manual_task(
    payload: ManualTaskWrite,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("calls.operate")),
):
    """שיחה ידנית (Follow-up) לאורח, מחוץ לסבבים. אחת פתוחה לכל אורח."""
    guest = db.get(models.Guest, payload.guest_id)
    if guest is None:
        raise HTTPException(status_code=404, detail="האורח לא נמצא")
    if not (guest.phone or "").strip():
        raise HTTPException(status_code=400, detail="לאורח אין מספר טלפון")
    event = db.get(models.Event, guest.event_id)
    day = _day(payload.due_date)
    if day < _today():
        raise HTTPException(status_code=400, detail="אי אפשר לקבוע שיחה לתאריך שעבר")
    if payload.assignee_id is not None:
        _validate_assignee(db, payload.assignee_id, day)
    cycle = event_cycle.of(event)
    T = models.CallTask
    task = db.scalar(select(T).where(T.guest_id == guest.id, T.event_cycle == cycle, T.round_number == call_ops.MANUAL_ROUND))
    now = datetime.utcnow()
    if task is not None and task.status == call_ops.OPEN:
        raise HTTPException(status_code=409, detail="כבר קיימת שיחה ידנית פתוחה לאורח הזה")
    if task is None:
        task = T(event_id=event.id, guest_id=guest.id, event_cycle=cycle, round_number=call_ops.MANUAL_ROUND, created_at=now)
        db.add(task)
    task.planned_date = task.due_date = day.isoformat()
    task.reason, task.status, task.closed_reason, task.closed_at = "manual", call_ops.OPEN, "", None
    task.assignee_id, task.pinned, task.note, task.updated_at = payload.assignee_id, True, payload.note, now
    admin_audit.record(
        db, admin, domain="calls", action="call_task.manual",
        summary=f"הוסיף/ה שיחה ידנית ל{guest.full_name}", target_type="guest", target_id=guest.id,
        target_label=guest.full_name, event_id=event.id,
        changes=[admin_audit.change("due_date", "מועד", "", _ddmm(day.isoformat()))],
        reason=payload.note, request=request,
    )
    db.commit()
    db.refresh(task)
    return _task_rows(db, [(task, guest, event)])[0]


# ── שליטה בסבב ────────────────────────────────────────────────────────────

class RoundActionWrite(BaseModel):
    reason: str = Field(default="", max_length=500)


_ROUND_ACTIONS = {"pause": "השהה/תה", "resume": "חידש/ה", "stop": "עצר/ה", "start": "הפעיל/ה ידנית"}


@router.post("/rounds/{event_id}/{round_number}/{action}")
def round_action(
    event_id: int,
    round_number: int,
    action: Literal["pause", "resume", "stop", "start"],
    payload: RoundActionWrite,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("calls.manage")),
):
    event = db.get(models.Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="האירוע לא נמצא")
    plans = {p.round_number: p for p in call_ops.round_plans(event, datetime.utcnow(), call_ops._controls(db, [event_id]))}
    if round_number not in plans:
        raise HTTPException(status_code=400, detail="אין סבב כזה בלוח הזמנים של האירוע")
    if action in ("stop", "pause") and len(payload.reason.strip()) < 3:
        raise HTTPException(status_code=400, detail="צריך לכתוב סיבה")
    cycle = event_cycle.of(event)
    C = models.CallRoundControl
    ctrl = db.scalar(select(C).where(C.event_id == event_id, C.event_cycle == cycle, C.round_number == round_number))
    before = ctrl.state if ctrl else ""
    now = datetime.utcnow()
    if action == "resume":
        if ctrl is not None:
            db.delete(ctrl)
        # משימות שבוטלו בגלל עצירה — חוזרות
        for t in db.scalars(select(models.CallTask).where(
            models.CallTask.event_id == event_id, models.CallTask.event_cycle == cycle,
            models.CallTask.round_number == round_number, models.CallTask.closed_reason == "round_stopped",
        )).all():
            t.status, t.closed_reason, t.closed_at, t.updated_at = call_ops.OPEN, "", None, now
    else:
        state = {"pause": "paused", "stop": "stopped", "start": "started"}[action]
        if action == "start" and plans[round_number].date <= _today():
            raise HTTPException(status_code=400, detail="הסבב כבר התחיל לפי לוח הזמנים")
        if ctrl is None:
            ctrl = C(event_id=event_id, event_cycle=cycle, round_number=round_number, state=state, created_at=now)
            db.add(ctrl)
        ctrl.state, ctrl.reason, ctrl.set_by_id = state, payload.reason.strip(), admin.id
        if action == "start":
            ctrl.created_at = now
    db.flush()
    labels = {"": "לפי לוח הזמנים", "paused": "מושהה", "stopped": "עצור", "started": "הופעל ידנית"}
    admin_audit.record(
        db, admin, domain="calls", action=f"call_round.{action}",
        summary=f"{_ROUND_ACTIONS[action]} את סבב טלפון {round_number} — {_hosts(event)}",
        target_type="event", target_id=event_id, target_label=_hosts(event), event_id=event_id,
        changes=[admin_audit.change("state", "מצב הסבב", labels.get(before, before),
                                    labels["" if action == "resume" else {"pause": "paused", "stop": "stopped", "start": "started"}[action]])],
        reason=payload.reason, request=request,
    )
    call_ops.sync(db, event_ids={event_id})
    db.commit()
    return {"ok": True, "state": "" if action == "resume" else ctrl.state}


# ── טלפנים ────────────────────────────────────────────────────────────────

class CallerRow(BaseModel):
    id: int
    email: str
    display_name: str
    phone: str
    disabled: bool
    availability: str
    availability_label: str
    available_today: bool
    unavailable_from: str
    unavailable_until: str
    group_name: str
    daily_capacity: Optional[int]
    note: str
    today: dict[str, int]
    tomorrow_tasks: int
    last_activity_at: Optional[datetime]
    calls_total: int
    event_ids: list[int]


def _caller_rows(db: Session, user_ids: Optional[list[int]] = None) -> list[CallerRow]:
    today = _today()
    stmt = select(models.User).where(models.User.account_type == roles.PHONE_AGENT)
    if user_ids is not None:
        stmt = stmt.where(models.User.id.in_(user_ids))
    users = db.scalars(stmt.order_by(models.User.disabled, models.User.display_name, models.User.id)).all()
    ids = [u.id for u in users]
    profs = call_ops.profiles(db, ids)
    loads = {c.id: c for c in _caller_loads(db, today)}
    last = dict(db.execute(
        select(models.CallLog.created_by_id, func.max(models.CallLog.created_at))
        .where(models.CallLog.created_by_id.in_(ids or [0])).group_by(models.CallLog.created_by_id)
    ).all())
    totals = dict(db.execute(
        select(models.CallLog.created_by_id, func.count(models.CallLog.id))
        .where(models.CallLog.created_by_id.in_(ids or [0])).group_by(models.CallLog.created_by_id)
    ).all())
    events: dict[int, list[int]] = defaultdict(list)
    for uid, eid in db.execute(
        select(models.CallAssignment.user_id, models.CallAssignment.event_id).where(models.CallAssignment.user_id.in_(ids or [0]))
    ).all():
        events[uid].append(eid)
    rows = []
    for u in users:
        p = profs.get(u.id)
        load = loads.get(u.id)
        rows.append(CallerRow(
            id=u.id, email=u.email, display_name=u.display_name or "", phone=u.phone or "",
            disabled=bool(u.disabled), availability=p.availability if p else "active",
            availability_label=call_ops.availability_label(u, p, today),
            available_today=call_ops.is_available(u, p, today),
            unavailable_from=p.unavailable_from if p else "", unavailable_until=p.unavailable_until if p else "",
            group_name=p.group_name if p else "", daily_capacity=p.daily_capacity if p else None,
            note=p.note if p else "",
            today={"tasks": load.tasks if load else 0, "handled": load.handled if load else 0,
                   "pending": load.pending if load else 0},
            tomorrow_tasks=load.next_day if load else 0,
            last_activity_at=last.get(u.id), calls_total=totals.get(u.id, 0), event_ids=sorted(events[u.id]),
        ))
    return rows


@router.get("/callers", response_model=list[CallerRow])
def list_callers(
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("calls.operate")),
):
    _sync_for(db, admin)
    return _caller_rows(db)


class CallerCreate(BaseModel):
    display_name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=200)
    phone: str = Field(default="", max_length=30)
    group_name: str = Field(default="", max_length=60)
    daily_capacity: Optional[int] = Field(default=None, ge=1, le=1000)
    new_password: Optional[str] = Field(default=None, min_length=8, max_length=128)


class CallerCreated(BaseModel):
    caller: CallerRow
    temporary_password: str


@router.post("/callers", response_model=CallerCreated, status_code=201)
def create_caller(
    payload: CallerCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("calls.manage")),
):
    """יוצר משתמש טלפן (``phone_agent``) — לעולם לא אדמין."""
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="כתובת אימייל לא תקינה")
    if db.scalar(select(models.User).where(func.lower(models.User.email) == email)) is not None:
        raise HTTPException(status_code=400, detail="כבר קיים משתמש עם האימייל הזה")
    temp = payload.new_password or secrets.token_urlsafe(9)
    user = models.User(
        email=email, display_name=payload.display_name.strip(), phone=payload.phone.strip(),
        password_hash=auth.hash_password(temp), account_type=roles.PHONE_AGENT, is_admin=False,
        email_verified_at=datetime.utcnow(),
    )
    db.add(user)
    db.flush()
    db.add(models.CallerProfile(
        user_id=user.id, availability="active", group_name=payload.group_name.strip(),
        daily_capacity=payload.daily_capacity, updated_at=datetime.utcnow(),
    ))
    admin_audit.record(
        db, admin, domain="calls", action="caller.create",
        summary=f"הוסיף/ה טלפן: {user.display_name}", target_type="user", target_id=user.id,
        target_label=user.display_name, request=request,
    )
    db.commit()
    return CallerCreated(caller=_caller_rows(db, [user.id])[0], temporary_password=temp)


class CallerUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=30)
    availability: Optional[Literal["active", "inactive", "vacation"]] = None
    unavailable_from: Optional[str] = None
    unavailable_until: Optional[str] = None
    group_name: Optional[str] = Field(default=None, max_length=60)
    daily_capacity: Optional[int] = Field(default=None, ge=0, le=1000)
    note: Optional[str] = Field(default=None, max_length=500)
    event_ids: Optional[list[int]] = None


@router.patch("/callers/{user_id}", response_model=CallerRow)
def update_caller(
    user_id: int,
    payload: CallerUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("calls.manage")),
):
    user = db.get(models.User, user_id)
    if user is None or not roles.is_phone_agent(user):
        raise HTTPException(status_code=404, detail="הטלפן לא נמצא")
    prof = call_ops.profiles(db, [user_id]).get(user_id)
    if prof is None:
        prof = models.CallerProfile(user_id=user_id, availability="active")
        db.add(prof)
    data = payload.model_dump(exclude_unset=True)
    for key in ("unavailable_from", "unavailable_until"):
        if data.get(key):
            _day(data[key])
    if data.get("unavailable_from") and data.get("unavailable_until") and data["unavailable_from"] > data["unavailable_until"]:
        raise HTTPException(status_code=400, detail="תאריך הסיום לפני תאריך ההתחלה")

    changes = []
    labels = {"display_name": "שם", "phone": "טלפון", "availability": "זמינות", "unavailable_from": "לא זמין מ-",
              "unavailable_until": "לא זמין עד", "group_name": "קבוצה", "daily_capacity": "קיבולת יומית", "note": "הערה"}
    for key, value in data.items():
        if key == "event_ids":
            continue
        if key == "daily_capacity" and value == 0:
            value = None
        if key in ("display_name", "phone"):
            old = getattr(user, key)
            setattr(user, key, (value or "").strip())
        else:
            old = getattr(prof, key)
            if isinstance(value, str):
                value = value.strip()
            setattr(prof, key, value if value is not None or key == "daily_capacity" else "")
        new = getattr(user, key) if key in ("display_name", "phone") else getattr(prof, key)
        shown = (lambda v: call_ops.AVAILABILITY_LABELS.get(v, v)) if key == "availability" else (lambda v: v)
        changes.append(admin_audit.change(key, labels.get(key, key), shown(old), shown(new)))
    if prof.availability != "vacation":
        prof.unavailable_from = prof.unavailable_from if data.get("availability") is None else ""
        prof.unavailable_until = prof.unavailable_until if data.get("availability") is None else ""
    prof.updated_at = datetime.utcnow()

    if payload.event_ids is not None:
        wanted = set(payload.event_ids)
        current = {a.event_id: a for a in db.scalars(select(models.CallAssignment).where(models.CallAssignment.user_id == user_id)).all()}
        if wanted - set(current):
            found = set(db.scalars(select(models.Event.id).where(models.Event.id.in_(wanted - set(current)))).all())
            if found != wanted - set(current):
                raise HTTPException(status_code=400, detail="אחד האירועים שנבחרו לא קיים")
        for eid, row in current.items():
            if eid not in wanted:
                db.delete(row)
        for eid in wanted - set(current):
            db.add(models.CallAssignment(event_id=eid, user_id=user_id, assigned_by_id=admin.id))
        if wanted != set(current):
            changes.append(admin_audit.change(
                "event_ids", "אירועים קבועים",
                ", ".join(f"#{e}" for e in sorted(current)) or "—", ", ".join(f"#{e}" for e in sorted(wanted)) or "—",
            ))
    if [c for c in changes if c["before"] != c["after"]]:
        admin_audit.record(
            db, admin, domain="calls", action="caller.update",
            summary=f"עדכן/ה את הטלפן {user.display_name or user.email}", target_type="user",
            target_id=user.id, target_label=user.display_name or user.email, changes=changes, request=request,
        )
    db.commit()
    return _caller_rows(db, [user_id])[0]


# ── הטלפן עצמו ────────────────────────────────────────────────────────────

class MyDay(BaseModel):
    date: str
    today: str
    relation: str
    counts: dict[str, int]


@router.get("/my/day", response_model=MyDay)
def my_day(
    date_: Optional[str] = Query(None, alias="date"),
    db: Session = Depends(get_db),
    agent: models.User = Depends(get_current_caller),
):
    _sync_for(db, agent)
    today = _today()
    day = _day(date_)
    if _mode(day, today) == "preview":
        allowed = None if agent.is_admin else call_center.visible_event_ids(db, agent)
        n = len(call_ops.preview(db, day, allowed_event_ids=allowed))
        counts = {"planned": n, "handled": 0, "pending": n}
    else:
        counts = call_ops.day_counts(db, day, today, call_ops._visible_filter(agent, db))
    return MyDay(date=day.isoformat(), today=today.isoformat(), relation=_relation(day, today), counts=counts)


@router.get("/my/tasks", response_model=TaskPage)
def my_tasks(
    date_: Optional[str] = Query(None, alias="date"),
    group: str = "pending",
    q: str = Query("", max_length=100),
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    agent: models.User = Depends(get_current_caller),
):
    page = _list_tasks_impl(db, agent, date_, group, None, None, None, "", q, limit, offset)
    if not agent.is_admin:
        for row in page.items:  # הטלפן לא צריך לראות מי עוד עובד על מה
            if row.assignee_id not in (None, agent.id):
                row.assignee_name = ""
    return page


@router.get("/my/guests/{guest_id}", response_model=GuestCard)
def my_guest_card(
    guest_id: int,
    db: Session = Depends(get_db),
    agent: models.User = Depends(get_current_caller),
):
    return _guest_card(db, agent, guest_id)
