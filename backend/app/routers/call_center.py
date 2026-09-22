"""Call Center — נקודות ה-API של מסך השיחות.

Router דק בכוונה: כל ההיגיון (מי צריך שיחה, באיזה סבב, ומה קורה אחרי) יושב
ב-``app/call_center.py`` ו-``app/rsvp_timeline.py``. כאן רק הרשאות, סינון
תצוגה והמרה לסכימות.

**הרשאות.** מוגן ב-``get_current_caller``: אדמין-על או טלפן
(``account_type='phone_agent'``, ראו ``app/roles.py``). בעל אירוע רגיל יקבל
403. זה ה-router **היחיד** במערכת שטלפן רשאי לגשת אליו.

**היקף.** אדמין רואה את כל האירועים שסבב שלהם נפתח; טלפן רואה רק את
האירועים שהוקצו לו (``models.CallAssignment``), ואם עוד לא הוקצה לו כלום —
את התור המשותף. ההיקף נאכף כאן בכל endpoint, גם באלה שמקבלים ``guest_id``
ישירות, כדי שלא ניתן יהיה להגיע למוזמן של אירוע אחר בניחוש מזהה.
"""
from __future__ import annotations

from datetime import date, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import (
    audit,
    automation,
    call_center,
    call_ops,
    communication,
    event_terms,
    models,
    rsvp_response,
    rsvp_timeline,
    schemas,
)
from app.auth import get_current_caller
from app.database import get_db

router = APIRouter(prefix="/admin/call-center", tags=["call-center"])

MAX_PAGE_LIMIT = 200
DEFAULT_PAGE_LIMIT = 50

# תוויות ליומן הפעילות של מוזמן. ששת סוגי ההודעה מגיעים מרצף התקשורת עצמו
# (מקור אמת יחיד — communication.py), ולא נכתבים כאן מחדש.
_EXTRA_KIND_LABELS = {
    "reply": "תשובת המוזמן",
    "custom": "הודעה",
}


def _ddmm(d: Optional[date]) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _kind_label(kind: str) -> str:
    return (
        communication.MESSAGE_TYPE_LABELS.get(kind)
        or _EXTRA_KIND_LABELS.get(kind)
        or kind
    )


def _hosts(event: models.Event) -> str:
    return event_terms.hosts_names(event.event_type, event.groom_name, event.bride_name)


def _round_label(round_number: int) -> str:
    """שם הסבב כפי שהוא מוגדר ב-Workflow אישורי ההגעה (rsvp_timeline.CYCLE)."""
    labels = [s["label"] for s in rsvp_timeline.CYCLE if s["type"] == "call_round"]
    if 1 <= round_number <= len(labels):
        return labels[round_number - 1]
    return f"סבב שיחות {round_number}"


def _validated_scope(scope: str) -> str:
    if scope not in call_center.SCOPES:
        raise HTTPException(status_code=400, detail="טווח לא מוכר")
    return scope


@router.get("", response_model=schemas.CallCenterOverview)
def overview(
    scope: str = "today",
    db: Session = Depends(get_db),
    agent: models.User = Depends(get_current_caller),
):
    """מסך ה-Call Center הראשי — מונים וקיבוץ לפי אירוע, לטווח נבחר.

    ברירת המחדל "היום" (``scope=today``): רק שיחות שצריך לבצע היום, לפי
    Workflow אישורי ההגעה. ``scope=tomorrow``/``later`` מציגים תצוגה מקדימה
    של מה שיהיה חייב שיחה מחר / בהמשך — לתכנון בלבד, לא משנה מי "צריך שיחה
    עכשיו". אירוע בלי אף שיחה בטווח הנבחר פשוט לא מופיע (לא נטען עם 0).
    """
    scope = _validated_scope(scope)
    today = date.today()
    queues = call_center.build_queues_for_scope(
        db, scope, allowed_event_ids=call_center.visible_event_ids(db, agent)
    )
    rows: list[schemas.CallCenterEventRow] = []
    for q in queues:
        event_date = automation.parse_event_date(q.event.event_date)
        rows.append(schemas.CallCenterEventRow(
            event_id=q.event.id,
            event_type=q.event.event_type,
            hosts=_hosts(q.event),
            venue_name=q.event.venue_name or "",
            event_date=q.event.event_date or "",
            event_time=q.event.event_time or "",
            days_until=(event_date - today).days if event_date else None,
            round_number=q.round_number,
            round_label=_round_label(q.round_number),
            round_date=_ddmm(q.round_date),
            waiting=len(q.guests),
            done=q.done_count,
        ))
    waiting = sum(r.waiting for r in rows)
    done = sum(r.done for r in rows)
    return schemas.CallCenterOverview(
        scope=scope,
        total=waiting + done,
        done=done,
        waiting=waiting,
        events_needing_attention=len(rows),
        events=rows,
    )


@router.get("/queue", response_model=schemas.CallCenterQueue)
def queue(
    scope: str = "today",
    event_id: Optional[int] = None,
    q: Optional[str] = None,
    status: Optional[str] = None,
    round_number: Optional[int] = None,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    agent: models.User = Depends(get_current_caller),
):
    """רשימת המוזמנים לטווח נבחר (היום/מחר/בהמשך), עם חיפוש, סינון ודפדוף.

    הסינונים תצוגתיים בלבד — הם לא משנים מי "צריך שיחה" לפי ה-Workflow.
    החיפוש (``q``) פועל **בתוך הטווח שנבחר בלבד**: הוא מועבר ל-Backend לפני
    שהתור נבנה, ולא מסנן תוצאה שכבר נשלפה.
    """
    scope = _validated_scope(scope)
    limit = max(1, min(limit, MAX_PAGE_LIMIT))
    offset = max(0, offset)

    queues = call_center.build_queues_for_scope(
        db,
        scope,
        event_id=event_id,
        query=q,
        status=status,
        allowed_event_ids=call_center.visible_event_ids(db, agent),
    )
    if round_number is not None:
        queues = [x for x in queues if x.round_number == round_number]

    guest_ids = [g.id for x in queues for g in x.guests]
    last_log: dict[int, models.CallLog] = {}
    followups: dict[int, int] = {}
    if guest_ids:
        for log in db.scalars(
            select(models.CallLog)
            .where(models.CallLog.guest_id.in_(guest_ids))
            .order_by(models.CallLog.created_at, models.CallLog.id)
        ).all():
            last_log[log.guest_id] = log
            if log.outcome == "callback":
                followups[log.guest_id] = followups.get(log.guest_id, 0) + 1

    def _is_followup(guest_id: int) -> bool:
        log = last_log.get(guest_id)
        return bool(log and log.outcome == "callback")

    rows: list[schemas.CallCenterGuestRow] = []
    for x in queues:
        hosts = _hosts(x.event)
        # בתוך כל אירוע: קודם מי שמחכה לשיחת המשך שהובטחה, ואז שאר האורחים
        # לפי א-ב — כדי שהמוקדן לא ישכח לחזור למי שכבר דיברו איתו.
        ordered_guests = sorted(
            x.guests, key=lambda g: (0 if _is_followup(g.id) else 1, g.full_name)
        )
        for guest in ordered_guests:
            log = last_log.get(guest.id)
            rows.append(schemas.CallCenterGuestRow(
                guest_id=guest.id,
                event_id=x.event.id,
                event_type=x.event.event_type,
                event_hosts=hosts,
                event_date=x.event.event_date or "",
                full_name=guest.full_name,
                phone=guest.phone or "",
                party_size=guest.party_size,
                side=guest.side or "shared",
                guest_note=guest.guest_note,
                rsvp_status=guest.rsvp_status,
                round_number=x.round_number,
                round_date=_ddmm(x.round_date),
                last_outcome=log.outcome if log else None,
                last_outcome_label=(
                    call_center.OUTCOMES.get(log.outcome, log.outcome) if log else None
                ),
                callback_at=log.callback_at if log and log.outcome == "callback" else None,
                # חזר לתור בגלל מועד ה-Follow-up שהוא ביקש — לא בגלל סבב חדש.
                is_followup=_is_followup(guest.id),
                followup_count=followups.get(guest.id, 0),
            ))

    return schemas.CallCenterQueue(
        scope=scope,
        items=rows[offset:offset + limit],
        total=len(rows),
        limit=limit,
        offset=offset,
    )


@router.get("/guests/{guest_id}", response_model=schemas.CallCenterGuestDetail)
def guest_detail(
    guest_id: int,
    db: Session = Depends(get_db),
    agent: models.User = Depends(get_current_caller),
):
    """מסך ביצוע שיחה: פרטי האירוע, פרטי המוזמן, ויומן הפעילות המלא שלו
    (הודעות WhatsApp ושיחות טלפון יחד, לפי סדר כרונולוגי)."""
    guest = db.get(models.Guest, guest_id)
    if guest is None:
        raise HTTPException(status_code=404, detail="המוזמן לא נמצא")
    event = db.get(models.Event, guest.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="האירוע לא נמצא")
    # מוזמן של אירוע שלא הוקצה לטלפן הזה — 404, לא 403: לא מאשרים לו בעקיפין
    # שהמוזמן קיים במערכת.
    if not call_center.can_access_event(db, agent, event.id):
        raise HTTPException(status_code=404, detail="המוזמן לא נמצא")

    messages = db.scalars(
        select(models.Message).where(models.Message.guest_id == guest_id)
    ).all()
    calls = call_center.guest_call_history(db, guest_id)
    actor_ids = {c.created_by_id for c in calls if c.created_by_id}
    actor_names = {
        u.id: (u.display_name or u.email)
        for u in db.scalars(
            select(models.User).where(models.User.id.in_(actor_ids))
        ).all()
    } if actor_ids else {}

    items: list[schemas.CallCenterTimelineItem] = []
    for m in messages:
        items.append(schemas.CallCenterTimelineItem(
            kind=m.kind,
            channel=m.channel or "whatsapp",
            label=_kind_label(m.kind),
            text=m.body or "",
            status=m.status or "",
            created_at=m.created_at,
        ))
    for c in calls:
        items.append(schemas.CallCenterTimelineItem(
            kind="call",
            channel="phone",
            label=f"{_round_label(c.round_number)} — {call_center.OUTCOMES.get(c.outcome, c.outcome)}",
            text=c.note or "",
            status=c.outcome,
            round_number=c.round_number,
            actor=actor_names.get(c.created_by_id),
            created_at=c.created_at,
        ))
    items.sort(key=lambda i: i.created_at)

    placement = rsvp_timeline.due_call_round(event)
    return schemas.CallCenterGuestDetail(
        guest_id=guest.id,
        full_name=guest.full_name,
        phone=guest.phone or "",
        side=guest.side or "shared",
        party_size=guest.party_size,
        rsvp_status=guest.rsvp_status,
        confirmed_count=guest.confirmed_count,
        guest_note=guest.guest_note,
        notes_raw=guest.notes_raw,
        event_id=event.id,
        event_type=event.event_type,
        hosts=_hosts(event),
        event_date=event.event_date or "",
        event_time=event.event_time or "",
        venue_name=event.venue_name or "",
        venue_address=event.venue_address or "",
        round_number=placement.round_number if placement else None,
        round_date=_ddmm(placement.date) if placement else None,
        timeline=items,
    )


@router.post("/guests/{guest_id}/outcome", response_model=schemas.CallOutcomeResult)
def record_outcome(
    guest_id: int,
    payload: schemas.CallOutcomeRequest,
    request: Request,
    db: Session = Depends(get_db),
    agent: models.User = Depends(get_current_caller),
):
    """מתעד תוצאת שיחה, ומעדכן את סטטוס אישור-ההגעה כשצריך.

    עדכון הסטטוס עובר דרך ``rsvp_response.apply_response`` — בדיוק אותה
    לוגיקה שרצה כשהמוזמן מאשר בעצמו מהקישור ב-WhatsApp, כדי שלא ייווצרו שתי
    דרכים שונות לאשר הגעה. השינוי נרשם גם ביומן הפעילות של האירוע, כך
    שבעל/ת האירוע רואה אותו מיד במסך שלו.
    """
    if payload.outcome not in call_center.OUTCOMES:
        raise HTTPException(status_code=400, detail="תוצאת שיחה לא מוכרת")
    guest = db.get(models.Guest, guest_id)
    if guest is None:
        raise HTTPException(status_code=404, detail="המוזמן לא נמצא")
    event = db.get(models.Event, guest.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="האירוע לא נמצא")
    if not call_center.can_access_event(db, agent, event.id):
        raise HTTPException(status_code=404, detail="המוזמן לא נמצא")

    # נתיב ישן (תאימות לאפליקציות שמורות בדפדפן). כל ההיגיון — אחד:
    # ``call_ops.record_call`` על המשימה הנוכחית של האורח.
    try:
        task = call_ops.task_for_guest_now(db, guest, event)
        result = call_ops.record_call(
            db, task=task, outcome=payload.outcome, agent=agent, note=payload.note or "",
            count=payload.count, guest_note=payload.guest_note, callback_at=payload.callback_at,
            ip=request.client.host if request.client else None,
        )
    except call_ops.CallError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    callback_at = result.log.callback_at if result.log else None

    return schemas.CallOutcomeResult(
        guest_id=guest.id,
        outcome=payload.outcome,
        outcome_label=call_center.OUTCOMES[payload.outcome],
        rsvp_status=guest.rsvp_status,
        confirmed_count=guest.confirmed_count,
        callback_at=callback_at,
    )
