"""אישורי הגעה — תמונת מצב תפעולית לאדמין.

מה יוצא היום (ובכל תאריך) לפי לוח הזמנים האמיתי של כל אירוע, איפה השליחה
נכשלה, ואילו אירועים עם מוזמנים עוד לא הפעילו את המסלול. קריאה בלבד — השליטה
בכללים עצמם נמצאת ב"כללי המערכת", והחריגות לאירוע במרכז השליטה של האירוע.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import admin_rbac, call_center, event_terms, local_time, messaging, models, rsvp_timeline
from app.database import get_db

router = APIRouter(prefix="/admin/rsvp", tags=["admin"])

STEP_ORDER = {"whatsapp_first": 0, "reminder": 1, "call_round": 2}


def _hosts(e: models.Event) -> str:
    return event_terms.hosts_names(e.event_type, e.groom_name, e.bride_name) or f"אירוע #{e.id}"


@router.get("/overview")
def rsvp_overview(
    date_: Optional[str] = Query(None, alias="date"),
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("settings.view")),
):
    today = local_time.israel_date()
    try:
        day = datetime.strptime(date_[:10], "%Y-%m-%d").date() if date_ else today
    except ValueError:
        raise HTTPException(status_code=400, detail="תאריך לא תקין")
    E, G = models.Event, models.Guest

    active = [
        e for e in db.scalars(select(E).where(E.rsvp_track_active.is_(True), E.event_date != "")).all()
        if not call_center.event_has_ended(e, today)
    ]
    ids = [e.id for e in active] or [0]
    pending = dict(db.execute(
        select(G.event_id, func.count(G.id))
        .where(G.event_id.in_(ids), G.rsvp_status.in_(call_center.OPEN_STATUSES))
        .group_by(G.event_id)
    ).all())

    steps = []
    totals: dict[str, dict[str, int]] = defaultdict(lambda: {"events": 0, "guests": 0})
    for e in active:
        schedule = rsvp_timeline.compute_schedule(e)
        if schedule is None:
            continue
        for p in schedule.placements:
            if p.date != day:
                continue
            kind = p.step["type"]
            label = p.step["label"]
            is_last = p.round_number is not None and p.date == schedule.commitment_date
            steps.append({
                "event_id": e.id, "event_label": _hosts(e), "event_date": e.event_date,
                "type": kind, "label": "סבב שיחות אחרון וסגירת הרשימה" if is_last else label,
                "audience": pending.get(e.id, 0),
                "send_time": e.rsvp_send_time if kind != "call_round" else "",
            })
            key = "whatsapp" if kind != "call_round" else "calls"
            totals[key]["events"] += 1
            totals[key]["guests"] += pending.get(e.id, 0)
    steps.sort(key=lambda s: (STEP_ORDER.get(s["type"], 9), s["event_date"], s["event_id"]))

    since = datetime.utcnow() - timedelta(days=7)
    M = models.Message
    failed_rows = db.execute(
        select(M.event_id, func.count(M.id), func.max(M.created_at), func.max(M.failure_reason))
        .where(M.direction == "outbound", M.status == "failed", M.created_at >= since)
        .group_by(M.event_id).order_by(func.count(M.id).desc()).limit(20)
    ).all()
    events = {e.id: e for e in db.scalars(select(E).where(E.id.in_([r[0] for r in failed_rows] or [0]))).all()}
    failed = [
        {"event_id": eid, "event_label": _hosts(events[eid]) if eid in events else f"#{eid}", "count": n,
         "last_at": last, "reason": reason or ""}
        for eid, n, last, reason in failed_rows
    ]

    horizon = (today + timedelta(days=45)).isoformat()
    not_started_q = (
        select(E, func.count(G.id)).join(G, G.event_id == E.id)
        .where(E.rsvp_track_active.is_(False), E.event_date >= today.isoformat(), E.event_date <= horizon)
        .group_by(E.id).order_by(E.event_date).limit(20)
    )
    not_started = [
        {"event_id": e.id, "event_label": _hosts(e), "event_date": e.event_date, "guests": n}
        for e, n in db.execute(not_started_q).all()
    ]
    sent_today_start, sent_today_end = local_time.israel_day_bounds_utc(today)
    sent = dict(db.execute(
        select(M.status, func.count(M.id)).where(
            M.direction == "outbound", M.created_at >= sent_today_start, M.created_at < sent_today_end,
        ).group_by(M.status)
    ).all())

    return {
        "date": day.isoformat(),
        "today": today.isoformat(),
        "whatsapp_mode": messaging.current_mode(),
        "emergency_stop": messaging.emergency_stop_active(),
        "active_tracks": len(active),
        "totals": {k: v for k, v in totals.items()},
        "steps": steps,
        "sent_today": {"total": sum(sent.values()), "failed": sent.get("failed", 0)},
        "failed_recent": failed,
        "not_started": not_started,
    }



