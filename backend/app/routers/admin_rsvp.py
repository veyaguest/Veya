"""אישורי הגעה — תמונת מצב תפעולית לאדמין.

מה יוצא היום (ובכל תאריך) לפי לוח הזמנים האמיתי של כל אירוע, איפה השליחה
נכשלה, ואילו אירועים עם מוזמנים עוד לא הפעילו את המסלול. קריאה בלבד — השליטה
בכללים עצמם נמצאת ב"כללי המערכת", והחריגות לאירוע במרכז השליטה של האירוע.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import (
    admin_audit, admin_rbac, call_center, communication, delivery_issues, event_cycle, event_terms,
    local_time, messaging, models, rsvp_timeline,
)
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

    M = models.Message
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
    sent_filters = [M.direction == "outbound", M.created_at >= sent_today_start, M.created_at < sent_today_end]
    if not event_cycle.counts_demo_sends():
        sent_filters.append(M.provider != event_cycle.MOCK_PROVIDER)  # רק מה שיצא באמת
    sent = dict(db.execute(
        select(M.status, func.count(M.id)).where(*sent_filters).group_by(M.status)
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
        "not_started": not_started,
    }


# ---- הודעות שלא הגיעו ----

def _alert_row(a: delivery_issues.AdminAlert) -> dict:
    msg, g = a.issue.message, a.issue.guest
    return {
        "event_id": a.event.id, "event_label": _hosts(a.event), "event_date": a.event.event_date,
        "guest_id": g.id, "guest_name": g.full_name, "phone": g.phone or "",
        "message_type": msg.kind,
        "message_label": communication.MESSAGE_TYPE_LABELS.get(msg.kind, msg.kind),
        "failed_at": msg.status_updated_at or msg.created_at,
        "code": msg.failure_code, "raw_reason": msg.failure_reason or "",
        "reason": a.issue.reason, "title": a.help.title, "detail": a.help.detail, "side": a.help.side,
        "attempts": a.issue.attempts, "resend_at": a.issue.resend_at,
        "has_open_call": a.has_open_call,
    }


@router.get("/delivery-alerts")
def delivery_alerts(
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("settings.view")),
):
    """מוזמנים שההודעה האחרונה אליהם לא הגיעה — מי, למה, מה כבר קורה."""
    return {"alerts": [_alert_row(a) for a in delivery_issues.admin_alerts(db)]}


@router.post("/delivery-alerts/{guest_id}/resend")
def resend_message(
    guest_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("messages.resend")),
):
    """"לשלוח שוב" — אותה הודעה שלא הגיעה, פעם אחת, אחרי כל בדיקות הבטיחות
    (``delivery_issues.resend_one``). נרשם ביומן האדמין."""
    guest = db.get(models.Guest, guest_id)
    event = db.get(models.Event, guest.event_id) if guest is not None else None
    if guest is None or event is None:
        raise HTTPException(status_code=404, detail="המוזמן לא נמצא")
    try:
        result = delivery_issues.resend_one(db, event, guest)
    except delivery_issues.ResendRefused as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc))
    if result.sent:
        outcome = "ההודעה נשלחה שוב"
    elif result.unknown:
        outcome = "ההודעה יצאה, ממתינים לעדכון מ-WhatsApp"
    elif result.blocked or result.no_template or result.image_blocked:
        outcome = "ההודעה לא יצאה (חסומה במצב הנוכחי של WhatsApp)"
    else:
        outcome = "גם הניסיון הזה לא הגיע"
    admin_audit.record(
        db, admin, domain="messages", action="message.resend",
        summary=f"שלח/ה שוב הודעה ל{guest.full_name} — {outcome}",
        target_type="guest", target_id=guest.id, target_label=guest.full_name,
        event_id=event.id, request=request,
    )
    db.commit()
    return {
        "sent": result.sent, "failed": result.failed, "unknown": result.unknown,
        "not_sent": result.blocked + result.no_template + result.image_blocked,
        "outcome": outcome, "detail": result.last_detail or result.image_reason or "",
    }


# ---- מספרים שצריך לתקן ----

@router.get("/phone-alerts")
def phone_alerts(
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("settings.view")),
):
    """לכל אירוע שעוד לא התקיים: מוזמנים בלי מספר תקין, או ש-WhatsApp לא מגיע
    אליהם — והאם כבר התרענו לבעלי האירוע."""
    return {"events": [
        {
            "event_id": e.id, "event_label": _hosts(e), "event_date": e.event_date,
            "guests": [
                {
                    "guest_id": p.guest.id, "guest_name": p.guest.full_name, "phone": p.guest.phone or "",
                    "problem": p.problem,
                    "alerted_at": p.guest.phone_alert_at if delivery_issues.alert_active(p.guest) else None,
                }
                for p in problems
            ],
        }
        for e, problems in delivery_issues.phone_problems(db)
    ]}


class PhoneAlertWrite(BaseModel):
    guest_ids: list[int] = Field(min_length=1, max_length=500)


@router.post("/phone-alerts")
def raise_phone_alerts(
    payload: PhoneAlertWrite,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("messages.alert")),
):
    """"להתריע לזוג" — המוזמנים יופיעו לבעלי האירוע בהתראה "כדאי לבדוק כמה
    מספרי טלפון" במסך המוזמנים, עד שהמספר יתעדכן."""
    guests = list(db.scalars(select(models.Guest).where(models.Guest.id.in_(set(payload.guest_ids)))).all())
    if not guests:
        raise HTTPException(status_code=404, detail="המוזמנים לא נמצאו")
    count = delivery_issues.raise_phone_alerts(guests)
    by_event: dict[int, list[models.Guest]] = defaultdict(list)
    for g in guests:
        by_event[g.event_id].append(g)
    for event_id, items in by_event.items():
        names = ", ".join(g.full_name for g in items[:5]) + ("…" if len(items) > 5 else "")
        admin_audit.record(
            db, admin, domain="messages", action="phone_alert.raise",
            summary=f"התריע/ה לבעלי האירוע לבדוק {len(items)} מספרי טלפון ({names})",
            target_type="event", target_id=event_id, event_id=event_id, request=request,
        )
    db.commit()
    return {"alerted": count}

