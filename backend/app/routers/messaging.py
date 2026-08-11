"""נקודות API לערוץ WhatsApp ו-RSVP (שלב 5).

זרימה:
1. הבעלים לוחץ "שלח הזמנות" → נשלחת הזמנה לכל מוזמן שעדיין לא ענה (או לכולם).
   במצב mock ההודעה רק נרשמת ביומן (בלי שליחה אמיתית ובלי עלות).
2. המוזמן לוחץ כפתור "מגיע/ה"/"לא מגיע/ה" → מגיע webhook מ-Meta, וה-RSVP
   מתעדכן אוטומטית. במצב mock אפשר "לדמות" את הלחיצה דרך המסך.
"""
import hashlib
import hmac
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import audit, message_status, messaging, models, permissions, schemas
from app.auth import get_current_user
from app.database import IS_POSTGRES, get_db
from app.deps import EventAccess

router = APIRouter(prefix="/messaging", tags=["messaging"])

_view = EventAccess(permissions.MESSAGES_VIEW)
_write = EventAccess(permissions.MESSAGES_WRITE)


# הערה על תאריך ושעה: עד לסבב הזה הייתה כאן ``_event_date_str`` שהחזירה
# "תאריך בשעה שעה" מאוחדים, והמחרוזת הזו הוזנה לטוקן ``[תאריך]`` בזמן
# ש-``[שעה]`` קיבל את השעה בנפרד. כל תבנית בתבנית הסטנדרטית של הספרייה
# ("📅 [תאריך] בשעה [שעה]") יצאה למוזמן ככפילות: "10/09/2026 בשעה 20:00
# בשעה 20:00". היום כל ערכי האירוע — כולל תאריך מפורמט ושעה נפרדת — מגיעים
# ממקור אחד, ``messaging.event_values(event)``.


def _record_reply(db: Session, guest: models.Guest, status: str, provider: str) -> None:
    """מעדכן RSVP של מוזמן ורושם הודעה נכנסת ביומן.

    ה-webhook רץ בלי משתמש מחובר ובלי guest_token, ולכן תחת RLS (Postgres)
    חייבים לעבור דרך פונקציית app_record_guest_rsvp_reply (SECURITY DEFINER,
    ראו backend/rls/01_helpers_and_grants.sql) — עדכון ORM רגיל היה נחסם/נכשל.
    """
    label = "אישר/ה הגעה" if status == "confirmed" else "ביטל/ה הגעה"
    if IS_POSTGRES:
        db.execute(
            text("SELECT app_record_guest_rsvp_reply(:gid, :status, :label, :provider)"),
            {"gid": guest.id, "status": status, "label": label, "provider": provider},
        )
        return
    guest.rsvp_status = status
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
    event: models.Event = Depends(_view),
):
    """תמונת מצב RSVP: כמה אישרו/ביטלו/ממתינים + כמה הזמנות נשלחו."""
    # שלב 2: שאילתת GROUP BY אחת במקום 4 שאילתות COUNT נפרדות (total/confirmed/
    # declined/pending) — אותם מספרים בדיוק (total = סכום כל הסטטוסים, כולל
    # ערכים אחרים כמו "maybe", בדיוק כמו הספירה הכוללת הקודמת), פחות round-trips.
    status_counts = dict(
        db.execute(
            select(models.Guest.rsvp_status, func.count())
            .where(models.Guest.event_id == event.id)
            .group_by(models.Guest.rsvp_status)
        ).all()
    )
    total_guests = sum(status_counts.values())

    sent = db.scalar(
        select(func.count()).select_from(models.Message)
        .where(models.Message.event_id == event.id)
        .where(models.Message.direction == "outbound")
        .where(models.Message.kind == "invitation")
        .where(models.Message.status == "sent")
    ) or 0

    return schemas.RsvpSummary(
        total_guests=total_guests,
        confirmed=status_counts.get("confirmed", 0),
        declined=status_counts.get("declined", 0),
        pending=status_counts.get("pending", 0),
        invitations_sent=sent,
        mode=messaging.current_mode(),
    )


@router.post("/invitations/send", response_model=schemas.SendInvitationsResult)
def send_invitations(
    payload: schemas.SendInvitationsRequest,
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_write),
    user: models.User = Depends(get_current_user),
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

    template = event.message_template or messaging.default_template_for(event.event_type)
    ev_values = messaging.event_values(event)
    for g in guests:
        if not g.phone:
            skipped += 1
            continue
        text = messaging.render_automation_template(
            template,
            guest_name=g.full_name,
            link=messaging.confirm_link(g.guest_token),
            table_number=g.table_number,
            guest_count=g.effective_seats,
            **ev_values,
        )
        res = provider.send_invitation(g.phone, text)
        db.add(models.Message(
            event_id=event.id,
            guest_id=g.id,
            direction="outbound",
            kind="invitation",
            body=text,
            **message_status.outbound_fields(res),
        ))
        if res.ok:
            sent += 1
        else:
            failed += 1
            last_detail = res.detail

    audit.record(
        db, "send_invitations",
        event_id=event.id, user_id=user.id,
        detail=f"נשלחו {sent}, נכשלו {failed}, דולגו {skipped}",
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return schemas.SendInvitationsResult(
        mode=messaging.current_mode(),
        sent=sent, failed=failed, skipped=skipped,
        detail=last_detail or None,
    )


@router.post("/reminders/send", response_model=schemas.SendInvitationsResult)
def send_reminders(
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_write),
    user: models.User = Depends(get_current_user),
):
    """שולח תזכורת עדינה רק למוזמנים שכבר קיבלו הזמנה אך עדיין לא ענו (pending).

    זו פעולה ידנית שהבעלים מפעיל בלחיצה — אין worker רקע בשלב הזה.
    תזמון אוטומטי (X ימים אחרי ההזמנה / יום לפני האירוע) יתווסף בעתיד.
    """
    # מזהי מוזמנים שכבר נשלחה אליהם הזמנה
    invited_ids = set(db.scalars(
        select(models.Message.guest_id)
        .where(models.Message.event_id == event.id)
        .where(models.Message.direction == "outbound")
        .where(models.Message.kind == "invitation")
        .where(models.Message.status == "sent")
        .where(models.Message.guest_id.is_not(None))
    ).all())

    if not invited_ids:
        raise HTTPException(
            status_code=400,
            detail="עדיין לא נשלחו הזמנות — שלחו הזמנות לפני תזכורת",
        )

    # רק ממתינים מתוך אלה שכבר קיבלו הזמנה
    guests = db.scalars(
        select(models.Guest)
        .where(models.Guest.event_id == event.id)
        .where(models.Guest.rsvp_status == "pending")
        .where(models.Guest.id.in_(invited_ids))
    ).all()

    if not guests:
        raise HTTPException(
            status_code=400,
            detail="אין ממתינים לתזכורת — כולם כבר ענו 🎉",
        )

    provider = messaging.get_provider()
    sent = failed = skipped = 0
    last_detail = ""

    template = event.message_template or messaging.default_template_for(event.event_type)
    ev_values = messaging.event_values(event)
    for g in guests:
        if not g.phone:
            skipped += 1
            continue
        base = messaging.render_automation_template(
            template,
            guest_name=g.full_name,
            link=messaging.confirm_link(g.guest_token),
            table_number=g.table_number,
            guest_count=g.effective_seats,
            **ev_values,
        )
        text = f"{messaging.REMINDER_PREFIX}\n\n{base}"
        res = provider.send_invitation(g.phone, text)
        db.add(models.Message(
            event_id=event.id,
            guest_id=g.id,
            direction="outbound",
            kind="reminder",
            body=text,
            **message_status.outbound_fields(res),
        ))
        if res.ok:
            sent += 1
        else:
            failed += 1
            last_detail = res.detail

    audit.record(
        db, "send_reminders",
        event_id=event.id, user_id=user.id,
        detail=f"תזכורות: נשלחו {sent}, נכשלו {failed}, דולגו {skipped}",
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return schemas.SendInvitationsResult(
        mode=messaging.current_mode(),
        sent=sent, failed=failed, skipped=skipped,
        detail=last_detail or None,
    )


@router.get("/template", response_model=schemas.MessageTemplateRead)
def get_template(event: models.Event = Depends(_view)):
    """מחזיר את תבנית ההודעה של האירוע (או ברירת המחדל) + רשימת המשתנים."""
    default_for_event = messaging.default_template_for(event.event_type)
    return schemas.MessageTemplateRead(
        template=event.message_template or default_for_event,
        is_custom=bool(event.message_template),
        default_template=default_for_event,
        placeholders=[
            schemas.TemplatePlaceholder(key=p["key"], desc=p["desc"])
            for p in messaging.PLACEHOLDERS
        ],
    )


@router.put("/template", response_model=schemas.MessageTemplateRead)
def save_template(
    payload: schemas.MessageTemplateSave,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_write),
):
    """שומר תבנית מותאמת אישית. ריק => חזרה לתבנית ברירת המחדל."""
    text = (payload.template or "").strip()
    event.message_template = text or None
    db.commit()
    return get_template(event=event)


@router.post("/template/preview", response_model=schemas.TemplatePreview)
def preview_template(
    payload: schemas.MessageTemplateSave,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_view),
):
    """תצוגה מקדימה של התבנית עם מוזמן אמיתי (הראשון) או ערכי דוגמה."""
    sample = db.scalars(
        select(models.Guest).where(models.Guest.event_id == event.id).limit(1)
    ).first()
    name = sample.full_name if sample else "ישראל ישראלי"
    token = sample.guest_token if sample else "example"
    text = messaging.render_automation_template(
        payload.template or messaging.default_template_for(event.event_type),
        guest_name=name,
        link=messaging.confirm_link(token),
        table_number=sample.table_number if sample else None,
        guest_count=sample.effective_seats if sample else None,
        **messaging.event_values(event),
    )
    return schemas.TemplatePreview(preview=text)


@router.post("/simulate-reply", response_model=schemas.RsvpSummary)
def simulate_reply(
    payload: schemas.SimulateReplyRequest,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_write),
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
    event: models.Event = Depends(_view),
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


def _verify_signature(body: bytes, signature_header: Optional[str]) -> bool:
    """מאמת שהבקשה נחתמה ע"י Meta עם ה-App Secret (HMAC-SHA256 על גוף הבקשה).

    אם ``WHATSAPP_APP_SECRET`` לא מוגדר (פיתוח/mock) — מדלגים על האימות כדי
    שהזרימה המקומית תמשיך לעבוד. בייצור חובה להגדיר את הסוד כדי לחסום בקשות
    מזויפות שמתחזות ל-Meta.
    """
    app_secret = os.getenv("WHATSAPP_APP_SECRET", "").strip()
    if not app_secret:
        return True  # אין סוד מוגדר → מצב פיתוח, לא אוכפים.
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        app_secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


@router.post("/webhook")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    """Webhook יחיד מ-Meta — כמו בפועל אצל Meta, אותה קריאה נושאת גם תשובות
    RSVP נכנסות (``messages[]``, מזהה מוזמן לפי טלפון) וגם עדכוני מסירה
    להודעות יוצאות (``statuses[]``: נשלחה/נמסרה/נקראה/נכשלה, מזהה הודעה
    לפי provider_message_id — ראו ``app/message_status.py``)."""
    # קוראים את הגוף הגולמי (bytes) לפני הפענוח — נדרש לאימות החתימה בדיוק.
    raw_body = await request.body()
    if not _verify_signature(raw_body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=403, detail="חתימת webhook לא תקינה")
    import json
    data = json.loads(raw_body or b"{}")
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
                for st in value.get("statuses", []):
                    mapped = message_status.map_meta_status(st.get("status", ""))
                    provider_message_id = st.get("id", "")
                    if not mapped or not provider_message_id:
                        continue
                    ts = None
                    raw_ts = st.get("timestamp")
                    if raw_ts:
                        try:
                            from datetime import datetime as _dt
                            ts = _dt.utcfromtimestamp(int(raw_ts))
                        except (TypeError, ValueError):
                            ts = None
                    errors = st.get("errors") or []
                    reason = (errors[0].get("title") or errors[0].get("message") or "") if errors else ""
                    message_status.apply_status_update(
                        db,
                        provider_message_id=provider_message_id,
                        status=mapped,
                        timestamp=ts,
                        reason=reason,
                    )
        db.commit()
    except Exception:
        # לעולם לא מחזירים שגיאה ל-Meta — אחרת היא תנסה שוב ושוב.
        db.rollback()
    return {"received": True}


def _match_guest_by_phone(db: Session, from_phone: str):
    """מתאים מספר שהגיע מ-Meta (972...) למוזמן לפי הספרות האחרונות.

    מגבלה ידועה (לטיפול עתידי): הסריקה היא על *כל* המוזמנים בכל האירועים,
    ומחזירה את ההתאמה הראשונה. אם אותו מספר טלפון מופיע בשני אירועים שונים,
    תשובת ה-RSVP עלולה להירשם לאירוע הלא-נכון. פתרון עתידי: לשייך את הודעת
    ה-WhatsApp הנכנסת למספר העסקי/אירוע שאליו נשלחה, ולסנן לפי event_id.

    תחת RLS (Postgres) אין כאן זהות מחוברת ואין guest_token, אז שאילתת ORM
    רגילה הייתה מחזירה תמיד 0 שורות — לכן עוברים דרך app_find_guest_by_phone
    (SECURITY DEFINER, ראו backend/rls/01_helpers_and_grants.sql).
    """
    digits = "".join(ch for ch in from_phone if ch.isdigit())
    tail = digits[-9:]
    if not tail:
        return None
    if IS_POSTGRES:
        row = db.execute(
            text("SELECT * FROM app_find_guest_by_phone(:tail)"), {"tail": tail}
        ).mappings().first()
        if row is None or row.get("id") is None:
            return None
        return models.Guest(**dict(row))
    for g in db.scalars(select(models.Guest)).all():
        g_digits = "".join(ch for ch in (g.phone or "") if ch.isdigit())
        if g_digits.endswith(tail):
            return g
    return None
