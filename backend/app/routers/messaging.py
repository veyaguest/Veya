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
from app.deps import get_default_event

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
def summary(db: Session = Depends(get_db)):
    """תמונת מצב RSVP: כמה אישרו/ביטלו/ממתינים + כמה הזמנות נשלחו."""
    def count(**where) -> int:
        stmt = select(func.count()).select_from(models.Guest)
        for k, v in where.items():
            stmt = stmt.where(getattr(models.Guest, k) == v)
        return db.scalar(stmt) or 0

    sent = db.scalar(
        select(func.count()).select_from(models.Message)
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
    event: models.Event = Depends(get_default_event),
):
    stmt = select(models.Guest)
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

    for g in guests:
        if not g.phone:
            skipped += 1
            continue
        text = messaging.build_invitation_text(
            g.full_name, event.groom_name, event.bride_name, event.venue_name
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


@router.post("/simulate-reply", response_model=schemas.RsvpSummary)
def simulate_reply(payload: schemas.SimulateReplyRequest, db: Session = Depends(get_db)):
    """בדיקה במצב mock: מדמה לחיצת כפתור RSVP של מוזמן ומעדכן את הסטטוס."""
    guest = db.get(models.Guest, payload.guest_id)
    if guest is None:
        raise HTTPException(status_code=404, detail="מוזמן לא נמצא")
    status = "confirmed" if payload.coming else "declined"
    _record_reply(db, guest, status, provider="mock")
    db.commit()
    return summary(db)


@router.get("/log", response_model=list[schemas.MessageRead])
def message_log(limit: int = 50, db: Session = Depends(get_db)):
    """יומן ההודעות האחרונות (יוצאות ונכנסות)."""
    stmt = (
        select(models.Message)
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
