"""משתמשים ואירועים באדמין — רשימות עם חיפוש/סינון/דפדוף בשרת, ומרכז שליטה לאירוע.

הרשימות הוותיקות (``/admin/users``, ``/admin/events``) מחזירות את כל הטבלה —
זה נשבר כשיש עשרות אלפי שורות. כאן כל סינון וחיתוך נעשים במסד.
מרכז השליטה לאירוע מרכיב תמונת מצב מנתונים קיימים בלבד; מה שלא קיים
(למשל Overrides לפני שנוצרו) מוחזר ריק, לא מומצא.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app import (
    admin_rbac, call_ops, event_terms, gift_status, local_time, messaging, models,
    payout_service, postponement_service, roles, rsvp_timeline,
)
from app.database import get_db

router = APIRouter(prefix="/admin/people", tags=["admin"])

EVENT_TYPE_LABELS = {
    "wedding": "חתונה", "henna": "חינה", "bar_mitzvah": "בר מצווה", "bat_mitzvah": "בת מצווה",
    "brit": "ברית", "brita": "בריתה", "business": "אירוע עסקי",
}


def _hosts(e: models.Event) -> str:
    return event_terms.hosts_names(e.event_type, e.groom_name, e.bride_name) or f"אירוע #{e.id}"


# ── משתמשים ───────────────────────────────────────────────────────────────

class UserRow(BaseModel):
    id: int
    email: str
    display_name: str
    phone: str
    account_type: str
    account_type_label: str
    is_admin: bool
    admin_role_label: str
    disabled: bool
    events_count: int
    last_login_at: Optional[datetime]
    created_at: Optional[datetime]


class UserPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[UserRow]


@router.get("/users", response_model=UserPage)
def list_users(
    q: str = Query("", max_length=100),
    status: str = Query("", pattern="^(|active|disabled|admins|callers|planners|venues)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("users.view")),
):
    U = models.User
    filters = []
    if q.strip():
        like = f"%{q.strip()}%"
        conds = [U.email.ilike(like), U.display_name.ilike(like)]
        digits = "".join(ch for ch in q if ch.isdigit())
        if len(digits) >= 4:
            conds.append(U.phone.ilike(f"%{digits}%"))
        if q.strip().isdigit():
            conds.append(U.id == int(q.strip()))
        filters.append(or_(*conds))
    if status == "active":
        filters.append(U.disabled.is_(False))
    elif status == "disabled":
        filters.append(U.disabled.is_(True))
    elif status == "admins":
        filters.append(U.is_admin.is_(True))
    elif status == "callers":
        filters.append(U.account_type == roles.PHONE_AGENT)
    elif status == "planners":
        filters.append(U.account_type == roles.PLANNER)
    elif status == "venues":
        filters.append(U.account_type == roles.VENUE)

    total = db.scalar(select(func.count(U.id)).where(*filters)) or 0
    users = db.scalars(select(U).where(*filters).order_by(U.id.desc()).limit(limit).offset(offset)).all()
    ids = [u.id for u in users] or [0]
    events = dict(db.execute(
        select(models.Event.owner_id, func.count(models.Event.id)).where(models.Event.owner_id.in_(ids))
        .group_by(models.Event.owner_id)
    ).all())
    logins = dict(db.execute(
        select(models.LoginEvent.user_id, func.max(models.LoginEvent.created_at))
        .where(models.LoginEvent.user_id.in_(ids)).group_by(models.LoginEvent.user_id)
    ).all())
    return UserPage(total=total, limit=limit, offset=offset, items=[
        UserRow(
            id=u.id, email=u.email, display_name=u.display_name or "", phone=u.phone or "",
            account_type=u.account_type or "couple",
            account_type_label=roles.ACCOUNT_TYPE_LABELS.get(u.account_type or "couple", u.account_type or ""),
            is_admin=bool(u.is_admin),
            admin_role_label=admin_rbac.ROLE_LABELS.get(admin_rbac.role_of(u) or "", "") if u.is_admin else "",
            disabled=bool(u.disabled), events_count=events.get(u.id, 0), last_login_at=logins.get(u.id),
            created_at=u.created_at,
        )
        for u in users
    ])


# ── אירועים ───────────────────────────────────────────────────────────────

class EventRow(BaseModel):
    id: int
    label: str
    event_type: str
    event_type_label: str
    event_date: str
    venue_name: str
    owner_id: Optional[int]
    owner_email: str
    guests: int
    confirmed: int
    pending: int
    declined: int
    seated: int
    rsvp_track_active: bool
    open_calls: int
    created_at: Optional[datetime]


class EventPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[EventRow]


@router.get("/events", response_model=EventPage)
def list_events(
    q: str = Query("", max_length=100),
    event_type: str = "",
    when: str = Query("", pattern="^(|upcoming|past|no_date|this_month)$"),
    track: str = Query("", pattern="^(|active|inactive)$"),
    owner_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("events.view")),
):
    E, U = models.Event, models.User
    today = local_time.israel_date().isoformat()
    stmt = select(E, U.email).outerjoin(U, E.owner_id == U.id)
    filters = []
    if q.strip():
        like = f"%{q.strip()}%"
        conds = [E.groom_name.ilike(like), E.bride_name.ilike(like), E.venue_name.ilike(like), U.email.ilike(like)]
        if q.strip().isdigit():
            conds.append(E.id == int(q.strip()))
        filters.append(or_(*conds))
    if event_type:
        filters.append(E.event_type == event_type)
    if when == "upcoming":
        filters += [E.event_date >= today, E.event_date != ""]
    elif when == "past":
        filters += [E.event_date < today, E.event_date != ""]
    elif when == "no_date":
        filters.append(E.event_date == "")
    elif when == "this_month":
        filters += [E.event_date >= today[:8] + "01", E.event_date <= today[:8] + "31"]
    if track == "active":
        filters.append(E.rsvp_track_active.is_(True))
    elif track == "inactive":
        filters.append(E.rsvp_track_active.is_(False))
    if owner_id is not None:
        filters.append(E.owner_id == owner_id)

    total = db.scalar(
        select(func.count(E.id)).select_from(E).outerjoin(U, E.owner_id == U.id).where(*filters)
    ) or 0
    order = (E.event_date.desc(),) if when == "past" else (
        (E.event_date.asc(),) if when in ("upcoming", "this_month") else (E.id.desc(),)
    )
    rows = db.execute(stmt.where(*filters).order_by(*order, E.id.desc()).limit(limit).offset(offset)).all()
    ids = [e.id for e, _ in rows] or [0]
    G = models.Guest
    guest_stats = {
        eid: (n, c, p, d, s)
        for eid, n, c, p, d, s in db.execute(
            select(
                G.event_id, func.count(G.id),
                func.sum(case((G.rsvp_status == "confirmed", 1), else_=0)),
                func.sum(case((G.rsvp_status.in_(("pending", "maybe")), 1), else_=0)),
                func.sum(case((G.rsvp_status == "declined", 1), else_=0)),
                func.sum(case((G.table_number.is_not(None), 1), else_=0)),
            ).where(G.event_id.in_(ids)).group_by(G.event_id)
        ).all()
    }
    calls = dict(db.execute(
        select(models.CallTask.event_id, func.count(models.CallTask.id))
        .where(models.CallTask.event_id.in_(ids), models.CallTask.status == call_ops.OPEN)
        .group_by(models.CallTask.event_id)
    ).all())
    items = []
    for e, email in rows:
        n, c, p, d, s = guest_stats.get(e.id, (0, 0, 0, 0, 0))
        items.append(EventRow(
            id=e.id, label=_hosts(e), event_type=e.event_type,
            event_type_label=EVENT_TYPE_LABELS.get(e.event_type, e.event_type), event_date=e.event_date or "",
            venue_name=e.venue_name or "", owner_id=e.owner_id, owner_email=email or "",
            guests=n or 0, confirmed=c or 0, pending=p or 0, declined=d or 0, seated=s or 0,
            rsvp_track_active=bool(e.rsvp_track_active), open_calls=calls.get(e.id, 0), created_at=e.created_at,
        ))
    return EventPage(total=total, limit=limit, offset=offset, items=items)


# ── מרכז שליטה לאירוע ─────────────────────────────────────────────────────

class Fact(BaseModel):
    label: str
    value: str
    tone: str = "neutral"


class ControlSection(BaseModel):
    key: str
    title: str
    status: str            # ok / warn / bad / neutral / info
    status_label: str
    facts: list[Fact]
    link: str = ""


class EventControl(BaseModel):
    id: int
    label: str
    event_type: str
    event_type_label: str
    event_date: str
    event_time: str
    venue_name: str
    venue_address: str
    cycle_number: int
    created_at: Optional[datetime]
    owner: Optional[dict]
    members: list[dict]
    sections: list[ControlSection]


def _ddmm(iso: str) -> str:
    if not iso or len(iso) < 10:
        return "—"
    y, m, d = iso[:10].split("-")
    return f"{d}.{m}.{y}"


@router.get("/events/{event_id}", response_model=EventControl)
def event_control(
    event_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("events.view")),
):
    e = db.get(models.Event, event_id)
    if e is None:
        raise HTTPException(status_code=404, detail="האירוע לא נמצא")
    today = local_time.israel_date()
    owner = db.get(models.User, e.owner_id) if e.owner_id else None
    members = db.execute(
        select(models.EventMember, models.User).join(models.User, models.EventMember.user_id == models.User.id)
        .where(models.EventMember.event_id == event_id)
    ).all()

    G = models.Guest
    rsvp = dict(db.execute(
        select(G.rsvp_status, func.count(G.id)).where(G.event_id == event_id).group_by(G.rsvp_status)
    ).all())
    total_guests = sum(rsvp.values())
    people_confirmed = db.scalar(
        select(func.coalesce(func.sum(func.coalesce(G.confirmed_count, G.party_size)), 0))
        .where(G.event_id == event_id, G.rsvp_status == "confirmed")
    ) or 0
    no_phone = db.scalar(select(func.count(G.id)).where(G.event_id == event_id, G.phone == "")) or 0
    seated = db.scalar(select(func.count(G.id)).where(
        G.event_id == event_id, G.rsvp_status == "confirmed", G.table_number.is_not(None),
    )) or 0

    sections: list[ControlSection] = []

    # אישורי הגעה + WhatsApp
    schedule = rsvp_timeline.compute_schedule(e)
    M = models.Message
    msg = dict(db.execute(
        select(M.status, func.count(M.id)).where(M.event_id == event_id, M.direction == "outbound").group_by(M.status)
    ).all())
    sent = sum(msg.values())
    failed = msg.get("failed", 0)
    next_step = None
    if schedule:
        upcoming = [p for p in schedule.placements if p.date >= today]
        next_step = upcoming[0] if upcoming else None
    rsvp_status = (
        ("ok", "פעיל") if e.rsvp_track_active else (("warn", "לא הופעל") if total_guests else ("neutral", "אין מוזמנים"))
    )
    sections.append(ControlSection(
        key="rsvp", title="אישורי הגעה ו-WhatsApp", status=rsvp_status[0], status_label=rsvp_status[1],
        facts=[
            Fact(label="מוזמנים", value=str(total_guests)),
            Fact(label="אישרו", value=f"{rsvp.get('confirmed', 0)} ({people_confirmed} אנשים)", tone="ok"),
            Fact(label="ממתינים", value=str(rsvp.get("pending", 0) + rsvp.get("maybe", 0))),
            Fact(label="לא מגיעים", value=str(rsvp.get("declined", 0))),
            Fact(label="סגירת הרשימה", value=schedule.commitment_date.strftime("%d.%m.%Y") if schedule else "לא נקבע"),
            Fact(label="השלב הבא", value=(
                f"{next_step.step['label']} · {next_step.date.strftime('%d.%m')}" if next_step else "—"
            )),
            Fact(label="הודעות שיצאו", value=str(sent)),
            Fact(label="נכשלו", value=str(failed), tone="bad" if failed else "neutral"),
            Fact(label="מצב WhatsApp", value="שליחה אמיתית" if messaging.current_mode() == "live" else "הדגמה",
                 tone="neutral" if messaging.current_mode() == "live" else "warn"),
            Fact(label="מוזמנים בלי טלפון", value=str(no_phone), tone="warn" if no_phone else "neutral"),
        ],
    ))

    # טלפנים
    T = models.CallTask
    task_stats = dict(db.execute(
        select(T.status, func.count(T.id)).where(T.event_id == event_id, T.event_cycle == (e.cycle_number or 1))
        .group_by(T.status)
    ).all())
    open_calls = task_stats.get(call_ops.OPEN, 0)
    overdue = db.scalar(select(func.count(T.id)).where(
        T.event_id == event_id, T.status == call_ops.OPEN, T.due_date < today.isoformat(),
    )) or 0
    callers = db.scalars(
        select(models.User).join(models.CallAssignment, models.CallAssignment.user_id == models.User.id)
        .where(models.CallAssignment.event_id == event_id)
    ).all()
    rounds = call_ops.round_plans(e, datetime.utcnow(), call_ops._controls(db, [event_id]))
    sections.append(ControlSection(
        key="calls", title="טלפנים", link=f"calls?event={event_id}",
        status="bad" if overdue else ("warn" if open_calls and not callers else ("ok" if rounds else "neutral")),
        status_label="באיחור" if overdue else ("בלי טלפן קבוע" if open_calls and not callers else ("פעיל" if rounds else "אין סבבים")),
        facts=[
            Fact(label="סבבי שיחות", value=", ".join(p.date.strftime("%d.%m") for p in rounds) or "—"),
            Fact(label="שיחות פתוחות", value=str(open_calls)),
            Fact(label="באיחור", value=str(overdue), tone="bad" if overdue else "neutral"),
            Fact(label="טופלו", value=str(task_stats.get(call_ops.DONE, 0) + task_stats.get(call_ops.CLOSED_BY_RSVP, 0))),
            Fact(label="טלפנים קבועים", value=", ".join(c.display_name or c.email for c in callers) or "אין"),
        ],
    ))

    # הושבה
    confirmed = rsvp.get("confirmed", 0)
    tables = len(e.table_positions or []) if isinstance(e.table_positions, list) else len((e.table_positions or {}))
    sections.append(ControlSection(
        key="seating", title="הושבה",
        status="ok" if confirmed and seated == confirmed else ("warn" if confirmed else "neutral"),
        status_label="כולם משובצים" if confirmed and seated == confirmed else (f"{confirmed - seated} בלי שולחן" if confirmed else "אין מאשרים"),
        facts=[
            Fact(label="מאשרים משובצים", value=f"{seated} מתוך {confirmed}"),
            Fact(label="שולחנות במפה", value=str(tables)),
            Fact(label="מקומות לשולחן", value=str(e.seats_per_table or "—")),
            Fact(label="סקיצת אולם", value="הועלתה" if e.hall_sketch else "לא הועלתה"),
        ],
    ))

    # מתנות וכספים
    Gf = models.Gift
    paid = db.execute(
        select(func.count(Gf.id), func.coalesce(func.sum(Gf.gift_amount_agorot), 0), func.coalesce(func.sum(Gf.fee_agorot), 0))
        .where(Gf.event_id == event_id, Gf.status == gift_status.PAID)
    ).one()
    payout = db.scalar(select(models.PayoutAccount).where(models.PayoutAccount.event_id == event_id))
    expenses = db.scalar(select(func.count(models.EventExpense.id)).where(models.EventExpense.event_id == event_id)) or 0
    payout_labels = {
        "missing": "לא הוגשו", "submitted": "הוגשו", "under_review": "בבדיקה", "verified": "מאומתים", "rejected": "נדחו",
    }
    sections.append(ControlSection(
        key="money", title="מתנות וכספים", link="fees",
        status="ok" if payout is not None and payout.status == "verified" else ("warn" if payout is not None and payout.status in ("submitted", "under_review") else "neutral"),
        status_label=payout_labels.get(payout.status, payout.status) if payout is not None else "אין פרטי חשבון",
        facts=[
            Fact(label="מתנות ששולמו", value=str(paid[0])),
            Fact(label="סכום לבעלי האירוע", value=f"₪{paid[1] / 100:,.0f}"),
            Fact(label="עמלות שנגבו", value=f"₪{paid[2] / 100:,.2f}"),
            Fact(label="פרטי חשבון", value=payout_labels.get(payout.status, payout.status) if payout is not None else "לא הוגשו"),
            Fact(label="הוצאות מתועדות", value=str(expenses)),
        ],
    ))

    post = postponement_service.latest(db, event_id)
    if post is not None:
        labels = {"pending": "ממתינה לאישור", "approved": "אושרה", "completed": "הושלמה", "rejected": "נדחתה"}
        sections.append(ControlSection(
            key="postponement", title="בקשת דחייה", link="postponements",
            status="warn" if post.status == "pending" else "neutral", status_label=labels.get(post.status, post.status),
            facts=[
                Fact(label="נפתחה", value=local_time.to_israel(post.requested_at).strftime("%d.%m.%Y") if post.requested_at else "—"),
                Fact(label="תאריך קודם", value=_ddmm(post.previous_event_date)),
            ],
        ))

    return EventControl(
        id=e.id, label=_hosts(e), event_type=e.event_type,
        event_type_label=EVENT_TYPE_LABELS.get(e.event_type, e.event_type), event_date=e.event_date or "",
        event_time=e.event_time or "", venue_name=e.venue_name or "", venue_address=e.venue_address or "",
        cycle_number=e.cycle_number or 1, created_at=e.created_at,
        owner={"id": owner.id, "email": owner.email, "name": owner.display_name or "", "disabled": bool(owner.disabled)} if owner else None,
        members=[
            {"id": u.id, "email": u.email, "name": u.display_name or "", "role": m.role, "status": m.status}
            for m, u in members
        ],
        sections=sections,
    )


@router.get("/events/{event_id}/activity")
def event_activity(
    event_id: int,
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("events.view")),
):
    """פעילות אחרונה באירוע (יומן האירוע הקיים) — לתמיכה, לא יומן האדמין."""
    rows = db.execute(
        select(models.AuditLog, models.User.display_name, models.User.email)
        .outerjoin(models.User, models.AuditLog.user_id == models.User.id)
        .where(models.AuditLog.event_id == event_id)
        .order_by(models.AuditLog.created_at.desc(), models.AuditLog.id.desc()).limit(limit)
    ).all()
    return [
        {"id": log.id, "action": log.action, "detail": log.detail or "", "actor": name or email or "",
         "created_at": log.created_at}
        for log, name, email in rows
    ]
