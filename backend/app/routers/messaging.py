"""נקודות API לערוץ WhatsApp ו-RSVP (שלב 5).

זרימה:
1. הבעלים לוחץ "שלח הזמנות" → נשלחת הזמנה לכל מוזמן שעדיין לא ענה (או לכולם).
   במצב mock ההודעה רק נרשמת ביומן (בלי שליחה אמיתית ובלי עלות).
2. המוזמן לוחץ כפתור "מגיע/ה"/"לא מגיע/ה" → מגיע webhook מ-Meta, וה-RSVP
   מתעדכן אוטומטית. במצב mock אפשר "לדמות" את הלחיצה דרך המסך.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import messaging, models, schemas
from app.database import get_db
from app.deps import get_current_event

router = APIRouter(prefix="/messaging", tags=["messaging"])


def _record_reply(db: Session, guest: models.Guest, status: str, provider: str) -> None:
    """מעדכן RSVP של מוזמן ורושם הודעה נכנסת ביומן."""
    guest.rsvp_status = status
    label = "אישר/ה הגעה" if status == "confirmed" else "ביטל/ה הגעה"
    db.add(models.Message(
        event_id=guest.event_id,
        guest_id=guest.id,
        direction="inbound",
        kind="reply",
        body=label,
        status="received",
        provider=provider,
    ))


@router.get("/summary", response_model=schemas.RsvpSummary)
def summary(
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """תמונת מצב RSVP: כמה אישרו/ביטלו/ממתינים + כמה הזמנות נשלחו."""
    def count(**where) -> int:
        stmt = (
            select(func.count())
            .select_from(models.Guest)
            .where(models.Guest.event_id == event.id)
        )
        for k, v in where.items():
            stmt = stmt.where(getattr(models.Guest, k) == v)
        return db.scalar(stmt) or 0

    sent = db.scalar(
        select(func.count()).select_from(models.Message)
        .where(models.Message.event_id == event.id)
        .where(models.Message.direction == "outbound")
        .where(models.Message.kind == "invitation")
        .where(models.Message.status == "sent")
    ) or 0

    return schemas.RsvpSummary(
        total_guests=count(),
        confirmed=count(rsvp_status="confirmed"),
        declined=count(rsvp_status="declined"),
        pending=count(rsvp_status="pending"),
        invitations_sent=sent,
        mode=messaging.current_mode(),
    )


@router.post("/invitations/send", response_model=schemas.SendInvitationsResult)
def send_invitations(
    payload: schemas.SendInvitationsRequest,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    stmt = select(models.Guest).where(models.Guest.event_id == event.id)
    if payload.guest_id is not None:
        stmt = stmt.where(models.Guest.id == payload.guest_id)
    elif payload.only_pending:
        stmt = stmt.where(models.Guest.rsvp_status == "pending")
    guests = db.scalars(stmt).all()

    if not guests:
        raise HTTPException(status_code=400, detail="אין מוזמנים לשליחה")

    provider = messaging.get_provider()
    sent = failed = skipped = 0
    last_detail = ""

    template = event.message_template or messaging.DEFAULT_TEMPLATE
    for g in guests:
        if not g.phone:
            skipped += 1
            continue
        text = messaging.render_template(
            template,
            guest_name=g.full_name,
            groom=event.groom_name,
            bride=event.bride_name,
            venue=event.venue_name,
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
        ))
        if res.ok:
            sent += 1
        else:
            failed += 1
            last_detail = res.detail

    db.commit()
    return schemas.SendInvitationsResult(
        mode=messaging.current_mode(),
        sent=sent, failed=failed, skipped=skipped,
        detail=last_detail or None,
    )


@router.get("/template", response_model=schemas.MessageTemplateRead)
def get_template(event: models.Event = Depends(get_current_event)):
    """מחזיר את תבנית ההודעה של האירוע (או ברירת המחדל) + רשימת המשתנים."""
    return schemas.MessageTemplateRead(
        template=event.message_template or messaging.DEFAULT_TEMPLATE,
        is_custom=bool(event.message_template),
        default_template=messaging.DEFAULT_TEMPLATE,
        placeholders=[
            schemas.TemplatePlaceholder(key=p["key"], desc=p["desc"])
            for p in messaging.PLACEHOLDERS
        ],
    )


@router.put("/template", response_model=schemas.MessageTemplateRead)
def save_template(
    payload: schemas.MessageTemplateSave,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """שומר תבנית מותאמת אישית. ריק => חזרה לתבנית ברירת המחדל."""
    text = (payload.template or "").strip()
    event.message_template = text or None
    db.commit()
    db.refresh(event)
    return get_template(event=event)


@router.post("/template/preview", response_model=schemas.TemplatePreview)
def preview_template(
    payload: schemas.MessageTemplateSave,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """תצוגה מקדימה של התבנית עם מוזמן אמיתי (הראשון) או ערכי דוגמה."""
    sample = db.scalars(
        select(models.Guest).where(models.Guest.event_id == event.id).limit(1)
    ).first()
    name = sample.full_name if sample else "ישראל ישראלי"
    token = sample.guest_token if sample else "example"
    text = messaging.render_template(
        payload.template or messaging.DEFAULT_TEMPLATE,
        guest_name=name,
        groom=event.groom_name,
        bride=event.bride_name,
        venue=event.venue_name,
        link=messaging.confirm_link(token),
    )
    return schemas.TemplatePreview(preview=text)


@router.post("/simulate-reply", response_model=schemas.RsvpSummary)
def simulate_reply(
    payload: schemas.SimulateReplyRequest,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """בדיקה במצב mock: מדמה לחיצת כפתור RSVP של מוזמן ומעדכן את הסטטוס."""
    guest = db.get(models.Guest, payload.guest_id)
    if guest is None or guest.event_id != event.id:
        raise HTTPException(status_code=404, detail="מוזמן לא נמצא")
    status = "confirmed" if payload.coming else "declined"
    _record_reply(db, guest, status, provider="mock")
    db.commit()
    return summary(db=db, event=event)


@router.get("/log", response_model=list[schemas.MessageRead])
def message_log(
    limit: int = 50,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """יומן ההודעות האחרונות של האירוע (יוצאות ונכנסות)."""
    stmt = (
        select(models.Message)
        .where(models.Message.event_id == event.id)
        .order_by(models.Message.created_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    return db.scalars(stmt).all()


# ---- Webhook ל-Meta (מצב live) ----

@router.get("/webhook")
def verify_webhook(request: Request):
    """אימות webhook מול Meta (handshake חד-פעמי בהגדרה)."""
    import os
    params = request.query_params
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "veya-verify")
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == verify_token:
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="אימות webhook נכשל")


@router.post("/webhook")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    """קבלת תשובות RSVP מ-Meta. מזהה את המוזמן לפי מספר הטלפון ומעדכן סטטוס."""
    data = await request.json()
    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    from_phone = msg.get("from", "")
                    button_id = (
                        msg.get("interactive", {}).get("button_reply", {}).get("id")
                        or msg.get("button", {}).get("payload")
                    )
                    status = messaging.rsvp_from_button(button_id or "")
                    if not status:
                        continue
                    guest = _match_guest_by_phone(db, from_phone)
                    if guest:
                        _record_reply(db, guest, status, provider="meta")
        db.commit()
    except Exception:
        # לעולם לא מחזירים שגיאה ל-Meta — אחרת היא תנסה שוב ושוב.
        db.rollback()
    return {"received": True}


def _match_guest_by_phone(db: Session, from_phone: str):
    """מתאים מספר שהגיע מ-Meta (972...) למוזמן לפי הספרות האחרונות."""
    digits = "".join(ch for ch in from_phone if ch.isdigit())
    tail = digits[-9:]
    if not tail:
        return None
    for g in db.scalars(select(models.Guest)).all():
        g_digits = "".join(ch for ch in (g.phone or "") if ch.isdigit())
        if g_digits.endswith(tail):
            return g
    return None
