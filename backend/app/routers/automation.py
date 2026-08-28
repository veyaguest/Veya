"""נקודות API למסלול אישורי-ההגעה הקבוע של VEYA (מסך "אישורי הגעה" של הזוג).

זרימת "תור לאישור": שליחת ההזמנה עצמה היא פעולה מפורשת של הבעלים
(``/track/activate``); התקדמות המסלול (תזכורות/יום-אירוע/תודה) מחושבת
דטרמיניסטית ונשלחת בפועל רק כשה-Frontend קורא ל-``/track/advance`` (מופעל
אוטומטית בכל טעינת מסך, אבל עדיין תלוי בכך שהבעלים כבר לחץ "שלח הזמנות"
פעם אחת). שום דבר לא נשלח בלי שהבעלים כבר הפעיל את המסלול.

תוכן ההודעות עצמו מגיע מ-``EventMessage`` (ראו ``app/communication.py``) —
לא עוד ספרייה/תבניות/חוקים חופשיים.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from datetime import datetime

from app import (
    audit,
    automation,
    communication,
    event_cycle,
    invitations,
    message_status,
    messaging,
    models,
    permissions,
    rsvp_timeline,
    schemas,
)
from app.auth import get_current_owner
from app.database import get_db
from app.deps import EventAccess

router = APIRouter(prefix="/automation", tags=["automation"])

_access = EventAccess(permissions.AUTOMATION)


# ---- עזרי טעינה ----

def _guests(db: Session, event_id: int) -> list[models.Guest]:
    return list(db.scalars(
        select(models.Guest).where(models.Guest.event_id == event_id)
    ).all())


def _messages(db: Session, event: models.Event) -> list[models.Message]:
    """הודעות המחזור הנוכחי של האירוע.

    כל הצרכנים של הרשימה הזו סופרים **שליחות** (``direction == "outbound"``)
    — כמה קיבלו הזמנה, מי כבר קיבל תזכורת, מה מצב המסירה. אחרי דחייה כל
    אלה צריכים להתחיל מאפס, ולכן הרשימה מצומצמת למחזור הנוכחי
    (``app/event_cycle.py``).
    """
    return list(db.scalars(
        select(models.Message)
        .where(models.Message.event_id == event.id)
        .where(event_cycle.current_sends(event))
    ).all())


# ---- מסלול אישורי-ההגעה הקבוע (VEYA RSVP Track) ----

def _track_status(
    db: Session,
    event: models.Event,
    *,
    guests: Optional[list[models.Guest]] = None,
    messages: Optional[list[models.Message]] = None,
) -> schemas.RsvpTrackStatus:
    """מרכיב את תמונת המצב של המסלול למסך הזוג — ספירות, רשימת מעקב טלפוני."""
    if guests is None:
        guests = _guests(db, event.id)
    if messages is None:
        messages = _messages(db, event)

    def count(status: str) -> int:
        return sum(1 for g in guests if g.rsvp_status == status)

    invited_ids = {
        m.guest_id for m in messages
        if m.direction == "outbound" and m.kind == "invitation"
        and m.status == "sent" and m.guest_id is not None
    }

    # רשימת המעקב הטלפוני: ממתינים שכבר קיבלו את שתי התזכורות האוטומטיות
    # (reminder_1 + reminder_2) ועדיין לא ענו — הגיע הזמן להתקשר בעצמכם.
    reminder2_sent_ids = {
        m.guest_id for m in messages
        if m.kind == "reminder_2" and m.guest_id is not None
    }
    guests_by_id = {g.id: g for g in guests}
    phone_list: list[schemas.RsvpTrackPhoneRow] = []
    for gid in reminder2_sent_ids:
        g = guests_by_id.get(gid)
        if g is None or g.rsvp_status != "pending":
            continue
        phone_list.append(schemas.RsvpTrackPhoneRow(
            guest_id=g.id, guest_name=g.full_name,
            phone=g.phone or "", side=g.side or "",
        ))

    due = (
        communication.compute_due_messages(db, event, guests=guests, messages=messages)
        if event.rsvp_track_active else []
    )

    return schemas.RsvpTrackStatus(
        active=bool(event.rsvp_track_active),
        started_at=event.rsvp_track_started_at,
        mode=messaging.current_mode(),
        total_guests=len(guests),
        invited=len(invited_ids),
        confirmed=count("confirmed"),
        declined=count("declined"),
        maybe=count("maybe"),
        pending=count("pending"),
        in_phone_followup=len(phone_list),
        phone_list=phone_list,
        steps=[],  # התזמון הקבוע נערך היום דרך "תקשורת עם אורחים", לא כרשימת שלבים כאן
        due_now=len(due),
    )


@router.get("/track", response_model=schemas.RsvpTrackStatus)
def get_track(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
):
    """סטטוס מסלול אישורי-ההגעה למסך הזוג (פעיל/לא, ספירות, רשימת מעקב)."""
    return _track_status(db, event)


@router.get("/message-status", response_model=schemas.MessageStatusSummary)
def message_status_summary(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
):
    """סיכום מצב ההודעות שנשלחו למוזמנים (נמסרו/נקראו/נכשלו/...) — לכרטיס
    "מעקב אחרי המוזמנים". נפרד לגמרי מסטטוס ה-RSVP (``/track``)."""
    guests = _guests(db, event.id)
    messages = _messages(db, event)
    counts = message_status.summarize(guests, messages)
    return schemas.MessageStatusSummary(
        mode=messaging.current_mode(),
        total_guests=len(guests),
        **counts,
    )


@router.get("/message-status/{message_type}", response_model=schemas.MessageTypeStatus)
def message_status_by_type(
    message_type: str,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
):
    """סטטוס ההודעות לפי סוג הודעה נבחר (הזמנה/תזכורת ראשונה/.../תודה) —
    לכרטיס "מעקב אחרי המוזמנים" כשהזוג בוחר "מעקב אחר: X". בכוונה נפרד
    מ-``/message-status`` הכללי (שנשאר כפי שהוא): כאן כל סוג הודעה נספר
    לגמרי בנפרד, כדי שסטטוס ההזמנה של מוזמן לא ישפיע על סטטוס התזכורת שלו.
    """
    if message_type not in communication.MESSAGE_TYPES:
        raise HTTPException(status_code=404, detail="סוג הודעה לא קיים")

    guests = _guests(db, event.id)
    messages = _messages(db, event)

    has_any = any(
        m.direction == "outbound" and m.kind == message_type for m in messages
    )
    if not has_any:
        # שום הודעה מהסוג הזה עוד לא נשלחה לאף מוזמן — לא מציגים "0 נשלחו"
        # כאילו הייתה שליחה (ראו schemas.MessageTypeStatus).
        return schemas.MessageTypeStatus(
            message_type=message_type,
            not_sent_yet=True,
            total=0, sent=0, delivered=0, read=0, failed=0,
            no_valid_number=0, blocked=0, queued=0,
            guests=[],
        )

    em = communication.event_messages_by_type(db, event.id).get(message_type)
    audience = (
        em.target_audience if em is not None
        else communication.DEFAULT_TARGET_AUDIENCE.get(message_type, "all")
    )
    counts, rows = message_status.summarize_by_type(guests, messages, message_type, audience)
    return schemas.MessageTypeStatus(
        message_type=message_type,
        not_sent_yet=False,
        total=len(rows),
        **counts,
        guests=[
            schemas.MessageTypeGuestRow(
                guest_id=g.id,
                guest_name=g.full_name,
                phone=g.phone or "",
                status=status,
                updated_at=(
                    (msg.read_at or msg.delivered_at or msg.sent_at or msg.created_at)
                    if msg is not None else None
                ),
            )
            for g, status, msg in rows
        ],
    )


@router.get("/track/preview", response_model=schemas.InvitationSendPreview)
def preview_send(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
):
    """ספירה מקדימה לדיאלוג האישור: כמה יקבלו הזמנה, כמה לא (וסיבה), כמה כבר
    קיבלו, והאם המסלול כבר הופעל (לזיהוי שליחה כפולה). לא משנה שום נתון."""
    p = invitations.build_send_preview(db, event)
    return schemas.InvitationSendPreview(
        total_guests=p.total_guests,
        can_receive=p.can_receive,
        not_yet_sent=p.not_yet_sent,
        already_sent=p.already_sent,
        missing_phone=p.missing_phone,
        invalid_phone=p.invalid_phone,
        already_activated=p.already_activated,
    )


@router.post("/track/activate", response_model=schemas.RsvpTrackActivateResult)
def activate_track(
    request: Request,
    payload: Optional[schemas.RsvpTrackActivateRequest] = None,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
    user: models.User = Depends(get_current_owner),
):
    """שולח הזמנות ומפעיל את מסלול אישורי-ההגעה (מקצה את רצף ההודעות, idempotent).

    היקף השליחה נקבע ב-``payload``:
    - ``retry_ids``   — שליחה חוזרת רק למוזמנים אלה (ניסיון חוזר לנכשלים). גובר על scope.
    - ``scope=all``   — שליחה מחדש לכל מי שיש לו טלפון תקין.
    - ``scope=new``   — (ברירת מחדל) רק מי שעדיין לא קיבל הזמנה.

    מוזמנים בלי טלפון / עם מספר לא תקין מדולגים ונספרים בנפרד. הטיימר (עוגן
    האוטומציות) נדלק בקריאה הראשונה; מכאן כל התזכורות מחושבות מזמן השליחה בפועל.
    """
    payload = payload or schemas.RsvpTrackActivateRequest()
    messages_created = communication.provision_event_messages(db, event)

    newly_activated = not event.rsvp_track_active
    if not event.rsvp_track_active:
        event.rsvp_track_active = True
    if event.rsvp_track_started_at is None:
        event.rsvp_track_started_at = datetime.utcnow()

    already_invited = invitations.invited_guest_ids(db, event.id, event)
    guests = _guests(db, event.id)

    # קביעת קהל היעד לפי היקף הבקשה.
    if payload.guest_ids is not None:
        chosen = set(payload.guest_ids)
        targets = [g for g in guests if g.id in chosen]
    elif payload.retry_ids:
        retry_set = set(payload.retry_ids)
        targets = [g for g in guests if g.id in retry_set]
    elif payload.scope == "all":
        targets = list(guests)
    else:  # "new" — רק מי שעדיין לא קיבל הזמנה (idempotent).
        targets = [g for g in guests if g.id not in already_invited]

    # --- אכיפת "הזמנה אחת בלבד לכל אורח" ---
    # כל אורח מקבל הזמנה פעם אחת. שליחה חוזרת למי שכבר קיבל הזמנה מותרת
    # לאדמין-על בלבד; לזוג רגיל מדלגים תמיד על מי שכבר קיבל, כדי שאף אורח
    # לא יקבל הזמנה כפולה בטעות. (ניסיון חוזר לנכשלים אינו "שליחה חוזרת" —
    # מי שהשליחה אליו נכשלה אינו נספר כ"כבר קיבל".)
    resend_skipped = 0
    if not user.is_admin:
        before = len(targets)
        targets = [g for g in targets if g.id not in already_invited]
        resend_skipped = before - len(targets)

    invitation_msg = communication.event_messages_by_type(db, event.id).get("invitation")
    body = invitation_msg.content if invitation_msg else ""
    provider = messaging.get_provider()
    invitations_sent = skipped_missing = skipped_invalid = failed = 0
    failed_ids: list[int] = []
    for g in targets:
        kind = invitations.classify_phone(g.phone)
        if kind == "missing":
            skipped_missing += 1
            continue
        if kind == "invalid":
            skipped_invalid += 1
            continue
        text = communication.render_message(
            body, communication.communication_values(event, g), message_type="invitation"
        )
        if not text:
            skipped_missing += 1  # אין עדיין תוכן להזמנה — לא נשלח כלום
            continue
        res = provider.send_invitation(g.phone, text)
        db.add(models.Message(
            event_id=event.id,
            guest_id=g.id,
            direction="outbound",
            kind="invitation",
            body=text,
            channel="whatsapp",
            event_message_id=invitation_msg.id if invitation_msg else None,
            cycle_number=event_cycle.of(event),
            **message_status.outbound_fields(res),
        ))
        if res.ok:
            invitations_sent += 1
        else:
            failed += 1
            failed_ids.append(g.id)

    # יומן הפעילות — רישום קריא לזוג (רק מה שקרה בפועל).
    ip = request.client.host if request.client else None
    if invitations_sent or failed:
        detail = f"נשלחו {invitations_sent} הזמנות"
        if failed:
            detail += f" · {failed} נכשלו"
        audit.record(
            db, "send_invitations",
            event_id=event.id, user_id=user.id, detail=detail, ip=ip,
        )
    skipped_total = skipped_missing + skipped_invalid
    if skipped_total:
        audit.record(
            db, "send_invitations",
            event_id=event.id, user_id=user.id,
            detail=f"{skipped_total} מוזמנים לא קיבלו הזמנה עקב מספר טלפון חסר/לא תקין או תוכן ריק",
            ip=ip,
        )
    if resend_skipped:
        audit.record(
            db, "send_invitations",
            event_id=event.id, user_id=user.id,
            detail=f"{resend_skipped} מוזמנים כבר קיבלו הזמנה — לא נשלחה שוב "
                   "(שליחה חוזרת מותרת לאדמין בלבד)",
            ip=ip,
        )
    if newly_activated:
        audit.record(
            db, "rsvp_track_activate",
            event_id=event.id, user_id=user.id,
            detail="מערכת אישורי ההגעה הופעלה",
            ip=ip,
        )

    db.commit()

    status = _track_status(db, event)
    return schemas.RsvpTrackActivateResult(
        **status.model_dump(),
        templates_created=messages_created,
        rules_created=0,
        invitations_sent=invitations_sent,
        skipped_missing=skipped_missing,
        skipped_invalid=skipped_invalid,
        failed=failed,
        failed_ids=failed_ids,
        newly_activated=newly_activated,
    )


@router.post("/track/advance", response_model=schemas.RsvpTrackAdvanceResult)
def advance_track(
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
    user: models.User = Depends(get_current_owner),
):
    """מקדם את המסלול אוטומטית: תזכורות/יום-אירוע/תודה שהגיע זמנן נשלחות
    (mock/live). רק ממתינים/מאושרים לפי קהל היעד של כל הודעה; מי שכבר ענה
    יוצא מהתזכורות. idempotent — dedup לפי event_message_id מונע כפילות,
    כך שאפשר לקרוא לזה שוב ושוב (בכל טעינת מסך RSVP) בלי נזק."""
    sent = failed = 0
    if event.rsvp_track_active:
        actions = communication.compute_due_messages(db, event)
        if actions:
            r = communication.send_due_messages(db, event, actions)
            sent, failed = r["sent"], r["failed"]
            audit.record(
                db, "rsvp_track_advance",
                event_id=event.id, user_id=user.id,
                detail=f"התקדמות מסלול: נשלחו {sent}, נכשלו {failed}",
                ip=request.client.host if request.client else None,
            )
            db.commit()

    status = _track_status(db, event)
    return schemas.RsvpTrackAdvanceResult(
        **status.model_dump(), sent=sent, phoned=0, failed=failed,
    )


# ---- Timeline של מוזמן ----

_KIND_LABEL = {
    "invitation": "הזמנה",
    "reminder_1": "תזכורת ראשונה",
    "reminder_2": "תזכורת שנייה",
    "final_reminder": "תזכורת אחרונה",
    "event_day": "יום האירוע",
    "thank_you": "תודה",
    "reply": "תשובת המוזמן",
    "custom": "הודעה",
}


@router.get("/timeline/{guest_id}", response_model=schemas.GuestTimeline)
def guest_timeline(
    guest_id: int,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
):
    """ה-Timeline של מוזמן — כל ההודעות היוצאות והנכנסות לפי סדר כרונולוגי."""
    guest = db.get(models.Guest, guest_id)
    if guest is None or guest.event_id != event.id:
        raise HTTPException(status_code=404, detail="מוזמן לא נמצא")
    msgs = db.scalars(
        select(models.Message)
        .where(models.Message.event_id == event.id)
        .where(models.Message.guest_id == guest_id)
        .order_by(models.Message.created_at)
    ).all()
    return schemas.GuestTimeline(
        guest_id=guest.id,
        guest_name=guest.full_name,
        rsvp_status=guest.rsvp_status,
        events=[
            schemas.TimelineEvent(
                kind=m.kind,
                direction=m.direction,
                channel=m.channel or "whatsapp",
                text=m.body,
                status=m.status,
                created_at=m.created_at,
            )
            for m in msgs
        ],
    )


# ---- Timeline יומי של אישורי-ההגעה (חישוב לאחור ממועד סגירת הרשימה) ----


@router.get("/timeline", response_model=schemas.RsvpTimelineView)
def rsvp_timeline_view(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
):
    """לוח הזמנים המלא לזוג — מה קורה היום, מה מחר, ומה עד מועד סגירת הרשימה.

    מחושב חי ודטרמיניסטית (``app/rsvp_timeline.py``) — קריאה טהורה, בלי שליחה
    ובלי כתיבה. אם אין עדיין תאריך אירוע או מועד סגירת רשימה, מוחזר מצב 'לא הוגדר'.
    """
    guests = _guests(db, event.id)
    return schemas.RsvpTimelineView(**rsvp_timeline.compute_timeline(event, guests))


# ---- דשבורד "ניהול אישורי הגעה" ----

@router.get("/dashboard", response_model=schemas.AutomationDashboard)
def dashboard(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
):
    """תמונת מצב מלאה של מסע אישורי ההגעה + המלצות מעקב חכם."""
    guests = _guests(db, event.id)
    messages = _messages(db, event)

    def count(status: str) -> int:
        return sum(1 for g in guests if g.rsvp_status == status)

    # כמה מוזמנים קיבלו הזמנה בפועל.
    invited_ids = {
        m.guest_id for m in messages
        if m.direction == "outbound" and m.kind == "invitation"
        and m.status == "sent" and m.guest_id is not None
    }
    # ממתינים שכבר קיבלו לפחות מעקב אחד (תזכורת כלשהי ברצף).
    followed_ids = {
        m.guest_id for m in messages
        if m.direction == "outbound" and m.guest_id is not None
        and m.kind in ("reminder_1", "reminder_2", "final_reminder")
    }
    pending_ids = {g.id for g in guests if g.rsvp_status == "pending"}
    in_reminder = len(pending_ids & followed_ids)

    from datetime import datetime as _dt
    event_date = automation.parse_event_date(event.event_date)
    days_to_event = (event_date - _dt.utcnow().date()).days if event_date else None

    active_messages = sum(
        1 for em in communication.event_messages_by_type(db, event.id).values()
        if em.is_active
    )

    due = communication.compute_due_messages(db, event, guests=guests, messages=messages)
    recs = automation.compute_recommendations(event, guests)

    return schemas.AutomationDashboard(
        total_guests=len(guests),
        invited=len(invited_ids),
        confirmed=count("confirmed"),
        declined=count("declined"),
        maybe=count("maybe"),
        pending=count("pending"),
        in_reminder_process=in_reminder,
        days_to_event=days_to_event,
        active_rules=active_messages,
        due_now=len(due),
        recommendations=[
            schemas.SmartFollowUp(severity=r["severity"], text=r["text"])
            for r in recs
        ],
    )
