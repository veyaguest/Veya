"""נקודות API למנוע האוטומציות של אישורי הגעה (RSVP Automation Engine).

זרימת "תור לאישור": הבעלים מגדיר חוקים ותבניות → המערכת מחשבת מי אמור לקבל
הודעה עכשיו (``GET /automation/due``) → הבעלים מאשר ושולח בלחיצה
(``POST /automation/run-due``). שום דבר לא נשלח בלי אישור מפורש. השליחה
עצמה עוברת דרך אותו ספק (mock/Meta) של שאר המערכת — בלי נתיב חדש.

המנוע הדטרמיניסטי (``app/automation.py``) עצמאי לגמרי ואינו נוגע ב-seating.py.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datetime import datetime

from app import (
    audit,
    automation,
    invitations,
    messaging,
    models,
    rsvp_timeline,
    rsvp_track,
    schemas,
)
from app.auth import get_current_user
from app.database import get_db
from app.deps import get_current_event

router = APIRouter(prefix="/automation", tags=["automation"])


# ---- עזרי טעינה ----

def _rules(db: Session, event_id: int) -> list[models.AutomationRule]:
    return list(db.scalars(
        select(models.AutomationRule)
        .where(models.AutomationRule.event_id == event_id)
        .order_by(models.AutomationRule.created_at)
    ).all())


def _templates(db: Session, event_id: int) -> list[models.MessageTemplate]:
    return list(db.scalars(
        select(models.MessageTemplate)
        .where(models.MessageTemplate.event_id == event_id)
        .order_by(models.MessageTemplate.created_at)
    ).all())


def _guests(db: Session, event_id: int) -> list[models.Guest]:
    return list(db.scalars(
        select(models.Guest).where(models.Guest.event_id == event_id)
    ).all())


def _messages(db: Session, event_id: int) -> list[models.Message]:
    return list(db.scalars(
        select(models.Message).where(models.Message.event_id == event_id)
    ).all())


# ---- תבניות הודעה בעלות שם ----

@router.get("/placeholders", response_model=list[schemas.TemplatePlaceholder])
def list_placeholders():
    """רשימת המשתנים הזמינים לתבניות (עבור כפתורי הוספת-משתנה בממשק)."""
    return [
        schemas.TemplatePlaceholder(key=p["key"], desc=p["desc"], token=p.get("token", ""))
        for p in messaging.AUTOMATION_PLACEHOLDERS
    ]


@router.get("/templates", response_model=list[schemas.AutomationTemplateRead])
def list_templates(
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    return _templates(db, event.id)


@router.post("/templates", response_model=schemas.AutomationTemplateRead)
def create_template(
    payload: schemas.AutomationTemplateCreate,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    tmpl = models.MessageTemplate(
        event_id=event.id,
        name=payload.name,
        kind=payload.kind,
        body=payload.body,
    )
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return tmpl


@router.put("/templates/{template_id}", response_model=schemas.AutomationTemplateRead)
def update_template(
    template_id: int,
    payload: schemas.AutomationTemplateUpdate,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    tmpl = db.get(models.MessageTemplate, template_id)
    if tmpl is None or tmpl.event_id != event.id:
        raise HTTPException(status_code=404, detail="תבנית לא נמצאה")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(tmpl, key, value)
    db.commit()
    db.refresh(tmpl)
    return tmpl


@router.delete("/templates/{template_id}")
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    tmpl = db.get(models.MessageTemplate, template_id)
    if tmpl is None or tmpl.event_id != event.id:
        raise HTTPException(status_code=404, detail="תבנית לא נמצאה")
    # חוקים שמפנים לתבנית הזו — מנתקים אותם (לא מוחקים אותם) כדי לא לאבד חוק.
    for rule in _rules(db, event.id):
        if rule.template_id == template_id:
            rule.template_id = None
    db.delete(tmpl)
    db.commit()
    return {"deleted": True}


# ---- חוקי אוטומציה ----

@router.get("/rules", response_model=list[schemas.AutomationRuleRead])
def list_rules(
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    return _rules(db, event.id)


@router.post("/rules", response_model=schemas.AutomationRuleRead)
def create_rule(
    payload: schemas.AutomationRuleCreate,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    _validate_template(db, event.id, payload.template_id)
    rule = models.AutomationRule(
        event_id=event.id,
        rule_name=payload.rule_name,
        trigger_type=payload.trigger_type,
        delay_days=payload.delay_days,
        target_group=payload.target_group,
        target_group_value=payload.target_group_value,
        template_id=payload.template_id,
        active=payload.active,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.put("/rules/{rule_id}", response_model=schemas.AutomationRuleRead)
def update_rule(
    rule_id: int,
    payload: schemas.AutomationRuleUpdate,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    rule = db.get(models.AutomationRule, rule_id)
    if rule is None or rule.event_id != event.id:
        raise HTTPException(status_code=404, detail="חוק לא נמצא")
    changes = payload.model_dump(exclude_unset=True)
    if "template_id" in changes:
        _validate_template(db, event.id, changes["template_id"])
    for key, value in changes.items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/rules/{rule_id}")
def delete_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    rule = db.get(models.AutomationRule, rule_id)
    if rule is None or rule.event_id != event.id:
        raise HTTPException(status_code=404, detail="חוק לא נמצא")
    db.delete(rule)
    db.commit()
    return {"deleted": True}


def _validate_template(db: Session, event_id: int, template_id: Optional[int]) -> None:
    if template_id is None:
        return
    tmpl = db.get(models.MessageTemplate, template_id)
    if tmpl is None or tmpl.event_id != event_id:
        raise HTTPException(status_code=400, detail="התבנית שנבחרה אינה קיימת")


# ---- התור לאישור + שליחה ----

def _due_actions(db: Session, event: models.Event) -> list[automation.DueActionData]:
    templates_by_id = {t.id: t for t in _templates(db, event.id)}
    return automation.compute_due_actions(
        event=event,
        guests=_guests(db, event.id),
        rules=[r for r in _rules(db, event.id) if r.active],
        messages=_messages(db, event.id),
        templates_by_id=templates_by_id,
    )


def _process_actions(
    db: Session, event: models.Event, actions: list[automation.DueActionData]
) -> dict:
    """מבצע בפועל פעולות שהגיע זמנן — שליחת WhatsApp (mock) או הכנסה לרשימת
    מעקב טלפוני, לפי ``action_kind`` של החוק. כל פעולה נרשמת ביומן ההודעות עם
    ``rule_id`` (dedup: המנוע לא יחזור על אותו חוק+מוזמן). לא עושה commit."""
    templates_by_id = {t.id: t for t in _templates(db, event.id)}
    provider = messaging.get_provider()
    sent = failed = skipped = phoned = 0
    last_detail = ""

    for a in actions:
        if not a.guest.phone:
            skipped += 1
            continue
        # שלב מעקב טלפוני — לא נשלחת הודעה, נרשמת משימת שיחה (הכנה בלבד).
        if a.rule.action_kind == "phone_followup":
            db.add(models.Message(
                event_id=event.id,
                guest_id=a.guest.id,
                direction="outbound",
                kind="call_task",
                body=f"מעקב טלפוני: {a.guest.full_name} עדיין לא אישר/ה הגעה",
                status="queued",
                provider="mock",
                channel="phone",
                rule_id=a.rule.id,
            ))
            phoned += 1
            continue
        # שלב שליחה — הודעת WhatsApp (mock עד חיבור אמיתי).
        tmpl = templates_by_id.get(a.rule.template_id) if a.rule.template_id else None
        kind = tmpl.kind if tmpl else "custom"
        res = provider.send_invitation(a.guest.phone, a.preview)
        db.add(models.Message(
            event_id=event.id,
            guest_id=a.guest.id,
            direction="outbound",
            kind=kind,
            body=a.preview,
            status=res.status,
            provider=res.provider,
            channel="whatsapp",
            rule_id=a.rule.id,
        ))
        if res.ok:
            sent += 1
        else:
            failed += 1
            last_detail = res.detail

    return {
        "sent": sent, "failed": failed, "skipped": skipped,
        "phoned": phoned, "detail": last_detail,
    }


@router.get("/due", response_model=schemas.DueQueue)
def get_due(
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """התור לאישור — מי אמור לקבל הודעה עכשיו (מחושב חי, לא נשלח כלום)."""
    actions = _due_actions(db, event)
    return schemas.DueQueue(
        mode=messaging.current_mode(),
        actions=[
            schemas.DueAction(
                rule_id=a.rule.id,
                rule_name=a.rule.rule_name,
                trigger_type=a.rule.trigger_type,
                guest_id=a.guest.id,
                guest_name=a.guest.full_name,
                phone=a.guest.phone,
                channel="whatsapp",
                preview=a.preview,
            )
            for a in actions
        ],
    )


@router.post("/run-due", response_model=schemas.RunDueResult)
def run_due(
    payload: schemas.RunDueRequest,
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
    user: models.User = Depends(get_current_user),
):
    """שולח בפועל את הפעולות שהגיע זמנן — רק אחרי לחיצת אישור של הבעלים.

    אפשר לצמצם לחוקים מסוימים דרך ``rule_ids``. כל שליחה נרשמת ביומן ההודעות
    עם ``rule_id`` (למניעת כפילות בעתיד ולבניית ה-Timeline).
    """
    actions = _due_actions(db, event)
    if payload.rule_ids is not None:
        wanted = set(payload.rule_ids)
        actions = [a for a in actions if a.rule.id in wanted]

    if not actions:
        raise HTTPException(status_code=400, detail="אין כרגע פעולות לשליחה בתור")

    r = _process_actions(db, event, actions)
    detail = r["detail"]
    if r["phoned"]:
        detail = (detail + " · " if detail else "") + f"{r['phoned']} נכנסו למעקב טלפוני"

    audit.record(
        db, "automation_run_due",
        event_id=event.id, user_id=user.id,
        detail=(
            f"אוטומציה: נשלחו {r['sent']}, נכשלו {r['failed']}, "
            f"דולגו {r['skipped']}, מעקב טלפוני {r['phoned']}"
        ),
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return schemas.RunDueResult(
        mode=messaging.current_mode(),
        sent=r["sent"], failed=r["failed"], skipped=r["skipped"],
        detail=detail or None,
    )


# ---- מסלול אישורי-ההגעה הקבוע (VEYA RSVP Track) ----

def _track_status(db: Session, event: models.Event) -> schemas.RsvpTrackStatus:
    """מרכיב את תמונת המצב של המסלול למסך הזוג — ספירות, רשימת מעקב, שלבים."""
    guests = _guests(db, event.id)
    messages = _messages(db, event.id)

    def count(status: str) -> int:
        return sum(1 for g in guests if g.rsvp_status == status)

    invited_ids = {
        m.guest_id for m in messages
        if m.direction == "outbound" and m.kind == "invitation"
        and m.status == "sent" and m.guest_id is not None
    }

    # רשימת המעקב הטלפוני: ממתינים שנרשמה להם משימת שיחה (call_task).
    call_task_guest_ids = {
        m.guest_id for m in messages
        if m.kind == "call_task" and m.guest_id is not None
    }
    guests_by_id = {g.id: g for g in guests}
    phone_list: list[schemas.RsvpTrackPhoneRow] = []
    for gid in call_task_guest_ids:
        g = guests_by_id.get(gid)
        if g is None or g.rsvp_status != "pending":
            continue
        phone_list.append(schemas.RsvpTrackPhoneRow(
            guest_id=g.id, guest_name=g.full_name,
            phone=g.phone or "", side=g.side or "",
        ))

    # שלבי המסלול = חוקי האוטומציה של האירוע, עם ספירת "בוצע" לפי rule_id.
    fired_by_rule: dict[int, set[int]] = {}
    for m in messages:
        if m.rule_id is not None and m.guest_id is not None:
            fired_by_rule.setdefault(m.rule_id, set()).add(m.guest_id)
    steps = [
        schemas.RsvpTrackStepRow(
            rule_id=r.id,
            name=r.rule_name,
            offset_days=r.delay_days,
            action_kind=r.action_kind or "send",
            active=r.active,
            done=len(fired_by_rule.get(r.id, set())),
        )
        for r in sorted(_rules(db, event.id), key=lambda r: r.delay_days)
    ]

    due = _due_actions(db, event) if event.rsvp_track_active else []

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
        steps=steps,
        due_now=len(due),
    )


@router.get("/track", response_model=schemas.RsvpTrackStatus)
def get_track(
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """סטטוס מסלול אישורי-ההגעה למסך הזוג (פעיל/לא, ספירות, רשימת מעקב)."""
    return _track_status(db, event)


@router.get("/track/preview", response_model=schemas.InvitationSendPreview)
def preview_send(
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
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
    event: models.Event = Depends(get_current_event),
    user: models.User = Depends(get_current_user),
):
    """שולח הזמנות ומפעיל את מסלול אישורי-ההגעה (מקצה תבניות+חוקים, idempotent).

    היקף השליחה נקבע ב-``payload``:
    - ``retry_ids``   — שליחה חוזרת רק למוזמנים אלה (ניסיון חוזר לנכשלים). גובר על scope.
    - ``scope=all``   — שליחה מחדש לכל מי שיש לו טלפון תקין.
    - ``scope=new``   — (ברירת מחדל) רק מי שעדיין לא קיבל הזמנה.

    מוזמנים בלי טלפון / עם מספר לא תקין מדולגים ונספרים בנפרד. הטיימר (עוגן
    האוטומציות) נדלק בקריאה הראשונה; מכאן כל התזכורות מחושבות מזמן השליחה בפועל.
    """
    payload = payload or schemas.RsvpTrackActivateRequest()
    result = rsvp_track.provision_rsvp_track(db, event)

    newly_activated = not event.rsvp_track_active
    if not event.rsvp_track_active:
        event.rsvp_track_active = True
    if event.rsvp_track_started_at is None:
        event.rsvp_track_started_at = datetime.utcnow()

    already_invited = invitations.invited_guest_ids(db, event.id)
    guests = _guests(db, event.id)

    # קביעת קהל היעד לפי היקף הבקשה.
    if payload.retry_ids:
        retry_set = set(payload.retry_ids)
        targets = [g for g in guests if g.id in retry_set]
    elif payload.scope == "all":
        targets = list(guests)
    else:  # "new" — רק מי שעדיין לא קיבל הזמנה (idempotent).
        targets = [g for g in guests if g.id not in already_invited]

    body = rsvp_track.invitation_template_body(db, event)
    provider = messaging.get_provider()
    date_display = automation.event_date_display(event)
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
        text = messaging.render_automation_template(
            body,
            guest_name=g.full_name,
            groom=event.groom_name,
            bride=event.bride_name,
            venue=event.venue_name,
            venue_address=event.venue_address or "",
            date=date_display,
            time=event.event_time or "",
            link=messaging.confirm_link(g.guest_token),
        )
        res = provider.send_invitation(g.phone, text)
        db.add(models.Message(
            event_id=event.id,
            guest_id=g.id,
            direction="outbound",
            kind="invitation",
            body=text,
            status=res.status,
            provider=res.provider,
            channel="whatsapp",
        ))
        if res.ok:
            invitations_sent += 1
        else:
            failed += 1
            failed_ids.append(g.id)

    # יומן הפעילות — רישום קריא לזוג (רק מה שקרה בפועל).
    ip = request.client.host if request.client else None
    if invitations_sent or failed:
        detail = f"נשלחו {invitations_sent} הזמנות בהצלחה"
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
            detail=f"{skipped_total} מוזמנים לא קיבלו הזמנה עקב מספר טלפון חסר או לא תקין",
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
    db.refresh(event)

    status = _track_status(db, event)
    return schemas.RsvpTrackActivateResult(
        **status.model_dump(),
        templates_created=result["templates_created"],
        rules_created=result["rules_created"],
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
    event: models.Event = Depends(get_current_event),
    user: models.User = Depends(get_current_user),
):
    """מקדם את המסלול אוטומטית: מעבד את כל הפעולות שהבשילו — תזכורות WhatsApp
    (mock) נשלחות, שלבי טלפון נכנסים לרשימת המעקב. רק ממתינים; מי שכבר ענה
    יוצא מהמסלול (target=pending). idempotent — dedup לפי rule_id מונע כפילות,
    כך שאפשר לקרוא לזה שוב ושוב (למשל בכל טעינת מסך RSVP) בלי נזק."""
    sent = phoned = failed = 0
    if event.rsvp_track_active:
        actions = _due_actions(db, event)
        if actions:
            r = _process_actions(db, event, actions)
            sent, phoned, failed = r["sent"], r["phoned"], r["failed"]
            if sent or phoned or failed:
                audit.record(
                    db, "rsvp_track_advance",
                    event_id=event.id, user_id=user.id,
                    detail=(
                        f"התקדמות מסלול: נשלחו {sent}, מעקב טלפוני {phoned}, "
                        f"נכשלו {failed}"
                    ),
                    ip=request.client.host if request.client else None,
                )
            db.commit()
            db.refresh(event)

    status = _track_status(db, event)
    return schemas.RsvpTrackAdvanceResult(
        **status.model_dump(), sent=sent, phoned=phoned, failed=failed,
    )


# ---- Timeline של מוזמן ----

_KIND_LABEL = {
    "invitation": "הזמנה",
    "reminder": "תזכורת",
    "pre_event": "לפני האירוע",
    "thank_you": "תודה",
    "reply": "תשובת המוזמן",
    "custom": "הודעה",
}


@router.get("/timeline/{guest_id}", response_model=schemas.GuestTimeline)
def guest_timeline(
    guest_id: int,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
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


# ---- Timeline יומי של אישורי-ההגעה (חישוב לאחור מיום ההתחייבות) ----


@router.get("/timeline", response_model=schemas.RsvpTimelineView)
def rsvp_timeline_view(
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """לוח הזמנים המלא לזוג — מה קורה היום, מה מחר, ומה עד יום ההתחייבות לאולם.

    מחושב חי ודטרמיניסטית (``app/rsvp_timeline.py``) — קריאה טהורה, בלי שליחה
    ובלי כתיבה. אם אין עדיין תאריך אירוע או יום התחייבות, מוחזר מצב 'לא הוגדר'.
    """
    guests = _guests(db, event.id)
    return schemas.RsvpTimelineView(**rsvp_timeline.compute_timeline(event, guests))


# ---- דשבורד "ניהול אישורי הגעה" ----

@router.get("/dashboard", response_model=schemas.AutomationDashboard)
def dashboard(
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """תמונת מצב מלאה של מסע אישורי ההגעה + המלצות מעקב חכם."""
    guests = _guests(db, event.id)
    messages = _messages(db, event.id)

    def count(status: str) -> int:
        return sum(1 for g in guests if g.rsvp_status == status)

    # כמה מוזמנים קיבלו הזמנה בפועל.
    invited_ids = {
        m.guest_id for m in messages
        if m.direction == "outbound" and m.kind == "invitation"
        and m.status == "sent" and m.guest_id is not None
    }
    # ממתינים שכבר קיבלו לפחות מעקב אחד (תזכורת/לפני האירוע/הודעת חוק).
    followed_ids = {
        m.guest_id for m in messages
        if m.direction == "outbound" and m.guest_id is not None
        and (m.rule_id is not None or m.kind in ("reminder", "pre_event"))
    }
    pending_ids = {g.id for g in guests if g.rsvp_status == "pending"}
    in_reminder = len(pending_ids & followed_ids)

    from datetime import datetime
    event_date = automation.parse_event_date(event.event_date)
    days_to_event = (event_date - datetime.utcnow().date()).days if event_date else None

    active_rules = db.scalar(
        select(func.count()).select_from(models.AutomationRule)
        .where(models.AutomationRule.event_id == event.id)
        .where(models.AutomationRule.active.is_(True))
    ) or 0

    due = _due_actions(db, event)
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
        active_rules=int(active_rules),
        due_now=len(due),
        recommendations=[
            schemas.SmartFollowUp(severity=r["severity"], text=r["text"])
            for r in recs
        ],
    )
