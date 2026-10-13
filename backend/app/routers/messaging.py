"""נקודות API לערוץ WhatsApp ו-RSVP (שלב 5).

זרימה:
1. הבעלים לוחץ "שלח הזמנות" → נשלחת הזמנה לכל מוזמן שעדיין לא ענה (או לכולם).
   במצב mock ההודעה רק נרשמת ביומן (בלי שליחה אמיתית ובלי עלות).
2. המוזמן לוחץ כפתור "מגיע/ה"/"לא מגיע/ה" → מגיע webhook מ-Meta, וה-RSVP
   מתעדכן דרך אותה לוגיקה של הקישור האישי (``app/whatsapp_inbound.py``). במצב
   mock אפשר "לדמות" את הלחיצה דרך המסך.
"""
import hashlib
import hmac
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app import (
    audit, event_cycle, invitations, message_status, messaging, models, outbound,
    permissions, schemas, whatsapp_inbound,
)
from app.auth import get_current_owner
from app.database import IS_POSTGRES, MigrationSessionLocal, get_db
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
    """מעדכן RSVP של מוזמן ורושם הודעה נכנסת ביומן — **רק ל"דימוי תשובה" במצב
    mock** (``/simulate-reply``), שנשאר בדיוק כפי שהיה.

    תשובות אמיתיות מ-webhook לא עוברות כאן מאז 2026-10-12, אלא דרך
    ``whatsapp_inbound.record_rsvp_reply`` (שיוך חד-משמעי, חלון אישורי ההגעה,
    ``rsvp_response``, יומן פעילות, מניעת כפילויות).
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
        .where(event_cycle.current_sends(event))
        .where(models.Message.direction == "outbound")
        .where(models.Message.kind == "invitation")
        # נשלחה — וגם מה שהתקדם ממנה (נמסרה/נקראה, מ-webhook). "sent" לבד
        # היה מוריד את המספר ברגע ש-Meta מעדכנת מסירה (2026-10-12).
        .where(models.Message.status.in_(invitations.DELIVERED_OR_BETTER))
    ) or 0

    return schemas.RsvpSummary(
        total_guests=total_guests,
        confirmed=status_counts.get("confirmed", 0),
        declined=status_counts.get("declined", 0),
        pending=status_counts.get("pending", 0),
        invitations_sent=sent,
        mode=messaging.current_mode(),
    )


def _legacy_send_guard() -> None:
    """שני נתיבי השליחה הישנים כאן (אין להם כפתור במסכים מאז רצף "תקשורת עם
    אורחים") לא אוכפים "הזמנה אחת לכל אורח" ולא בודקים מי כבר קיבל. במצב
    mock זה לא מזיק (אין שליחה), ולכן הם נשארים כמו שהם; בכל מצב אחר —
    חסומים, כדי שאי אפשר יהיה לעקוף דרכם את מניעת הכפילויות."""
    if messaging.whatsapp_mode() != messaging.MODE_MOCK:
        raise HTTPException(
            status_code=409,
            detail="השליחה מכאן לא זמינה כשהודעות WhatsApp יוצאות באמת. "
                   "שולחים הזמנות ותזכורות ממסך התקשורת עם האורחים.",
        )


@router.post("/invitations/send", response_model=schemas.SendInvitationsResult)
def send_invitations(
    payload: schemas.SendInvitationsRequest,
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_write),
    user: models.User = Depends(get_current_owner),
):
    _legacy_send_guard()
    stmt = select(models.Guest).where(models.Guest.event_id == event.id)
    if payload.guest_id is not None:
        stmt = stmt.where(models.Guest.id == payload.guest_id)
    elif payload.only_pending:
        stmt = stmt.where(models.Guest.rsvp_status == "pending")
    guests = db.scalars(stmt).all()

    if not guests:
        raise HTTPException(status_code=400, detail="אין מוזמנים לשליחה")

    skipped = 0
    items: list[outbound.OutboundItem] = []

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
        items.append(outbound.OutboundItem(guest=g, phone=g.phone, text=text, kind="invitation"))
    batch = outbound.send_batch(db, event, items)
    sent, failed, last_detail = batch.sent, batch.failed, batch.last_detail

    _detail = f"נשלחו {sent} הזמנות"
    if failed:
        _detail += f" · {failed} לא נשלחו"
    audit.record(
        db, "send_invitations",
        event_id=event.id, user_id=user.id,
        detail=_detail,
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
    user: models.User = Depends(get_current_owner),
):
    """שולח תזכורת עדינה רק למוזמנים שכבר קיבלו הזמנה אך עדיין לא ענו (pending).

    זו פעולה ידנית שהבעלים מפעיל בלחיצה — אין worker רקע בשלב הזה.
    תזמון אוטומטי (X ימים אחרי ההזמנה / יום לפני האירוע) יתווסף בעתיד.
    """
    _legacy_send_guard()
    # מזהי מוזמנים שכבר נשלחה אליהם הזמנה
    invited_ids = set(db.scalars(
        select(models.Message.guest_id)
        .where(models.Message.event_id == event.id)
        .where(models.Message.direction == "outbound")
        .where(models.Message.kind == "invitation")
        .where(models.Message.status.in_(invitations.DELIVERED_OR_BETTER))
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

    skipped = 0
    items: list[outbound.OutboundItem] = []

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
        items.append(outbound.OutboundItem(guest=g, phone=g.phone, text=text, kind="reminder"))
    batch = outbound.send_batch(db, event, items)
    sent, failed, last_detail = batch.sent, batch.failed, batch.last_detail

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
    # נכשל-סגור: בלי טוקן מוגדר אין handshake. ברירת מחדל ידועה ("veya-verify")
    # הייתה מאפשרת לכל אחד להשלים את האימות מול הכתובת שלנו.
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip()
    given = params.get("hub.verify_token") or ""
    if (
        verify_token
        and params.get("hub.mode") == "subscribe"
        and hmac.compare_digest(given.encode(), verify_token.encode())
    ):
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="אימות webhook נכשל")


def _verify_signature(body: bytes, signature_header: Optional[str]) -> bool:
    """מאמת שהבקשה נחתמה ע"י Meta עם ה-App Secret (HMAC-SHA256 על גוף הבקשה).

    **דוחים תמיד כשאין סוד מוגדר** — לא "מדלגים על האימות". ה-endpoint הזה
    ציבורי לגמרי (בלי טוקן, בלי guest_token) והוא רץ על חיבור המערכת למסד
    (עוקף RLS, ראו ``_process_webhook_items``) — כך שחתימה היא שכבת ההגנה
    **היחידה** נגד בקשות מזויפות, ולא דבר-מה שאפשר לדלג עליו "עד שיוגדר סוד".
    התנהגות ישנה (החזרת True בלי סוד) אפשרה לזייף אישור/ביטול הגעה לכל
    מוזמן במערכת — Security Audit, שלב 6.

    כותרת פגומה (לא hex, אורך שגוי, תווים שאינם ASCII) → ``False``, לא חריגה:
    ``hmac.compare_digest`` זורק על מחרוזת עם תווים שאינם ASCII, ועד
    2026-10-13 כל אחד, בלי שום סוד, יכול היה לקבל כאן 500 (ושורת traceback בלוג).
    """
    app_secret = os.getenv("WHATSAPP_APP_SECRET", "").strip()
    if not app_secret:
        return False  # אין סוד מוגדר → דוחים. אין "מצב פיתוח" מיוחס כאן.
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    provided = signature_header[len("sha256="):].strip().lower()
    if len(provided) != 64 or not all(c in "0123456789abcdef" for c in provided):
        return False
    expected = hmac.new(
        app_secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected.encode("ascii"), provided.encode("ascii"))


# גודל מקסימלי לגוף webhook. Meta מגבילה payload של webhook ל-3MB; כל דבר
# גדול מזה לא מגיע ממנה — ונקרא *לפני* בדיקת החתימה, כך שבלי תקרה כל אחד
# יכול היה לשלוח גוף ענק ולהעמיס על הזיכרון של השרת.
MAX_WEBHOOK_BODY_BYTES = 3 * 1024 * 1024


async def _read_capped_body(request: Request) -> Optional[bytes]:
    """גוף הבקשה, או ``None`` אם הוא חורג מ-``MAX_WEBHOOK_BODY_BYTES``
    (גם כשאין Content-Length או כשהוא משקר — נקרא בחלקים ונעצר בתקרה)."""
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > MAX_WEBHOOK_BODY_BYTES:
                return None
        except ValueError:
            return None
    buf = bytearray()
    async for chunk in request.stream():
        buf.extend(chunk)
        if len(buf) > MAX_WEBHOOK_BODY_BYTES:
            return None
    return bytes(buf)


@router.post("/webhook")
async def receive_webhook(request: Request):
    """Webhook יחיד מ-Meta — אותה קריאה נושאת גם הודעות נכנסות (``messages[]``)
    וגם עדכוני מסירה להודעות יוצאות (``statuses[]``).

    עקרונות (2026-10-12):
    - **כל פריט בטרנזקציה משלו.** כשל באמצע לא מבטל את מה שכבר נקלט, וכשל
      בפריט אחד לא "מרעיל" את האחרים.
    - **חסין לכפילויות.** Meta שולחת שוב כשלא קיבלה 200, ולפעמים גם סתם.
      הודעה נכנסת מזוהה לפי מזהה ה-Meta שלה (``whatsapp_inbound``); עדכון
      סטטוס חוזר לא משנה דבר (``message_status._should_skip_regression``).
    - **כשל זמני ב-DB → 500**, כדי ש-Meta תנסה שוב. בזכות שני הסעיפים
      הקודמים, ניסיון חוזר אחרי הצלחה חלקית לא מכפיל כלום.
    - **payload לא צפוי → מדולג ונרשם ללוג, 200.** פריט שלא ניתן לפענח לא
      יצליח גם בניסיון הבא; 500 עליו היה גורם ל-Meta לנסות שוב לנצח.
    - **בלי מידע אישי בלוג** — לא טלפון, לא שם, לא תוכן ההודעה.
    """
    # קוראים את הגוף הגולמי (bytes) לפני הפענוח — נדרש לאימות החתימה בדיוק.
    raw_body = await _read_capped_body(request)
    if raw_body is None:
        raise HTTPException(status_code=413, detail="גוף הבקשה גדול מדי")
    if not _verify_signature(raw_body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=403, detail="חתימת webhook לא תקינה")
    import json
    try:
        data = json.loads(raw_body or b"{}")
    except Exception:
        # גוף לא-JSON תקין (גם אם החתימה כן תקינה) — 400 מבוקר, לא 500 ולא
        # traceback/פרטי הפענוח החוצה. JSON תקין-תחבירית שאינו בצורת webhook
        # מטופל למטה (מדולג, 200).
        raise HTTPException(status_code=400, detail="גוף הבקשה אינו JSON תקין")

    items = _webhook_items(data)
    transient = await run_in_threadpool(_process_webhook_items, items)
    if transient:
        raise HTTPException(status_code=500, detail="שגיאה זמנית — ננסה שוב")
    return {"received": True}


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _webhook_items(data) -> list[tuple[str, dict]]:
    """מפרק את גוף ה-webhook לפריטים לטיפול: ``("message", msg)`` /
    ``("status", st)``. סובלני לחלוטין לצורה לא צפויה — מה שלא מתאים מדולג."""
    items: list[tuple[str, dict]] = []
    for entry in _as_list(_as_dict(data).get("entry")):
        for change in _as_list(_as_dict(entry).get("changes")):
            value = _as_dict(_as_dict(change).get("value"))
            for msg in _as_list(value.get("messages")):
                if isinstance(msg, dict):
                    items.append(("message", msg))
            for st in _as_list(value.get("statuses")):
                if isinstance(st, dict):
                    items.append(("status", st))
    return items


def _process_webhook_items(items: list[tuple[str, dict]]) -> bool:
    """מעבד את הפריטים, כל אחד ב-commit משלו. מחזיר ``True`` אם הייתה שגיאת
    DB זמנית (ואז עוצרים — Meta תשלח את כל הקריאה שוב).

    חיבור המערכת (``MigrationSessionLocal``), כמו המשימות המתוזמנות: ל-webhook
    אין זהות משתמש שה-RLS יכול לסנן לפיה. ההגנה היא החתימה (``_verify_signature``),
    שנבדקת לפני שמגיעים לכאן.
    """
    with MigrationSessionLocal() as db:
        for kind, item in items:
            try:
                if kind == "message":
                    _handle_inbound_message(db, item)
                else:
                    _handle_status(db, item)
                db.commit()
            except IntegrityError:
                # אותה הודעה נכנסת נקלטה במקביל ע"י קריאה אחרת (אינדקס ייחודי
                # על מזהה Meta) — כבר טופלה. לא שגיאה.
                db.rollback()
                print("[veya:whatsapp] webhook duplicate (concurrent)", flush=True)
            except SQLAlchemyError as exc:
                db.rollback()
                print(f"[veya:whatsapp] webhook db error {type(exc).__name__} — retry", flush=True)
                return True
            except Exception as exc:  # noqa: BLE001 — פריט לא צפוי לא עוצר את האחרים
                db.rollback()
                print(f"[veya:whatsapp] webhook item skipped {type(exc).__name__}", flush=True)
    return False


def _handle_inbound_message(db: Session, msg: dict) -> None:
    """הודעה נכנסת מאורח. **היום שום הודעה נכנסת לא משנה RSVP** — אישור הגעה
    רק דרך הקישור האישי (החלטת המייסד, 2026-10-13).

    שני מתגים, שניהם כבויים כברירת מחדל:
    - ``WHATSAPP_WEBHOOK_INBOUND`` (``whatsapp_inbound.inbound_enabled``) — כבוי:
      הודעות נכנסות **לא נשמרות בכלל** ולא נוגעות בשום נתון; רק נספרות בלוג (סוג
      ההודעה, בלי תוכן ובלי שולח). כך ה-webhook מקבל "עדכוני סטטוס בלבד" — ב-Meta
      אי אפשר להירשם לסטטוסים בלי הודעות נכנסות (שניהם בשדה ``messages``).
    - דלוק: כל הודעה (טקסט, תמונה, הקלטה, וגם לחיצת כפתור אישור/ביטול מהנוסח
      הישן) נשמרת כ"דורש טיפול" (``whatsapp_inbound.record_free_message``).
      עדכון RSVP מלחיצת כפתור (``record_rsvp_reply``) — רק אם בנוסף
      ``WHATSAPP_INBOUND_RSVP=1`` (``whatsapp_inbound.rsvp_replies_enabled``).
    """
    if not whatsapp_inbound.inbound_enabled():
        msg_type = msg.get("type") if isinstance(msg.get("type"), str) else "unknown"
        print(f"[veya:whatsapp] inbound skipped (WHATSAPP_WEBHOOK_INBOUND off) "
              f"type={msg_type[:20]}", flush=True)
        return
    wamid = msg.get("id")
    if not isinstance(wamid, str) or not wamid:
        print("[veya:whatsapp] inbound skipped: missing message id", flush=True)
        return
    from_phone = msg.get("from") if isinstance(msg.get("from"), str) else None
    context_id = _as_dict(msg.get("context")).get("id")
    context_id = context_id if isinstance(context_id, str) else None
    button_id = (
        _as_dict(_as_dict(msg.get("interactive")).get("button_reply")).get("id")
        or _as_dict(msg.get("button")).get("payload")
    )
    decision = messaging.rsvp_from_button(button_id if isinstance(button_id, str) else "")
    if decision and whatsapp_inbound.rsvp_replies_enabled():
        whatsapp_inbound.record_rsvp_reply(
            db, provider_message_id=wamid, from_phone=from_phone,
            context_id=context_id, decision=decision,
        )
        return
    msg_type = msg.get("type") if isinstance(msg.get("type"), str) else "unknown"
    text_body = _as_dict(msg.get("text")).get("body")
    if not isinstance(text_body, str):
        # כפתור של Template (לא בשימוש היום) — הטקסט שעל הכפתור.
        text_body = _as_dict(msg.get("button")).get("text")
    if decision:
        # לחיצה על "מגיע/ה"/"לא מגיע/ה" כשעדכון RSVP מהודעות נכנסות כבוי: נשמרת
        # כ"דורש טיפול" ולא משנה כלום — אישור הגעה רק דרך הקישור האישי.
        what = "אישור הגעה" if decision == "confirmed" else "ביטול הגעה"
        text_body = f"לחיצה על כפתור {what} ב-WhatsApp — לא עודכן (אישור הגעה דרך הקישור האישי)"
    whatsapp_inbound.record_free_message(
        db, provider_message_id=wamid, from_phone=from_phone, context_id=context_id,
        message_type=msg_type, text_body=text_body if isinstance(text_body, str) else None,
    )


def _handle_status(db: Session, st: dict) -> None:
    """עדכון מסירה להודעה יוצאת (נשלחה/נמסרה/נקראה/נכשלה)."""
    raw_status = st.get("status") if isinstance(st.get("status"), str) else ""
    errors = [e for e in _as_list(st.get("errors")) if isinstance(e, dict)]
    mapped = message_status.map_meta_status(raw_status, errors)
    provider_message_id = st.get("id")
    if not mapped or not isinstance(provider_message_id, str) or not provider_message_id:
        print(f"[veya:whatsapp] status skipped raw={raw_status or 'none'}", flush=True)
        return
    ts = None
    raw_ts = st.get("timestamp")
    if raw_ts:
        try:
            ts = datetime.utcfromtimestamp(int(raw_ts))
        except (TypeError, ValueError, OverflowError, OSError):
            ts = None
    reason = (errors[0].get("title") or errors[0].get("message") or "") if errors else ""
    fields = dict(
        status=mapped,
        timestamp=ts,
        reason=str(reason)[:500],
        failure_code=message_status.first_error_code(errors),
        provider_status=raw_status or None,
    )
    found = message_status.apply_status_update(db, provider_message_id=provider_message_id, **fields)
    reconciled = False
    callback = st.get("biz_opaque_callback_data")
    if not found and isinstance(callback, str) and callback:
        # הודעה שהתוצאה שלה לא ידועה (``pending`` בלי מזהה Meta) — נסגרת רק
        # בהתאמה מלאה; אחרת לא נוגעים (``message_status.reconcile_pending``).
        recipient = st.get("recipient_id")
        reconciled = message_status.reconcile_pending(
            db, callback_data=callback, provider_message_id=provider_message_id,
            recipient_id=recipient if isinstance(recipient, str) else None, **fields,
        )
    print(
        f"[veya:whatsapp] status {mapped} known={'yes' if found else 'no'}"
        + (f" reconciled={'yes' if reconciled else 'no'}" if not found and callback else "")
        + (f" code={message_status.first_error_code(errors)}" if errors else ""),
        flush=True,
    )
