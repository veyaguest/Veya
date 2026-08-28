"""דף אישור הגעה ציבורי — קישור אישי לכל מוזמן (/confirm/{token}).

זהו הנתיב היחיד ללא התחברות: המוזמן פותח את הקישור האישי שקיבל ב-WhatsApp,
רואה את פרטי האירוע *שלו בלבד*, ומסמן אם הוא מגיע וכמה אנשים. אין דרך
לראות מוזמן אחר — הטוקן אקראי ובלתי-ניתן-לניחוש, וכל בקשה מחזירה רק את
הנתונים של בעל הטוקן.
"""
from __future__ import annotations

import secrets
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import (
    audit,
    calendar_links,
    event_terms,
    gift as gift_money,
    gift_service,
    gift_status,
    guest_journey,
    media,
    messaging,
    models,
    rsvp_response,
    schemas,
)
from app.database import IS_POSTGRES, get_db, set_guest_token

router = APIRouter(prefix="/confirm", tags=["confirm"])

# הגבלת ניסיונות בסיסית מול ניחוש טוקנים: מונה כשלונות פר-IP בחלון זמן.
_FAILS: dict[str, list[float]] = {}
_WINDOW = 60.0       # שניות
_MAX_FAILS = 20      # מקסימום כשלונות ל-IP בחלון


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _check_rate(ip: str) -> None:
    now = time.time()
    hits = [t for t in _FAILS.get(ip, []) if now - t < _WINDOW]
    if len(hits) >= _MAX_FAILS:
        raise HTTPException(status_code=429, detail="יותר מדי ניסיונות. נסו שוב בעוד רגע.")
    _FAILS[ip] = hits


def _record_fail(ip: str) -> None:
    _FAILS.setdefault(ip, []).append(time.time())


def _event_title(event: models.Event | None) -> str:
    """כותרת האירוע כפי שהמוזמן יראה אותה ביומן — "החתונה של אביב ודנה",
    "בר המצווה של יונתן". עוברת דרך מנוע המונחים ולא מקבעת שפה חתונתית."""
    if event is None:
        return ""
    return event_terms.event_display_title(
        event.event_type, event.groom_name, event.bride_name
    )


def _hub_url(token: str) -> str:
    """הקישור הקבוע של המוזמן — אותו קישור לכל אורך חיי האירוע."""
    return messaging.confirm_link(token)


def _public(db: Session, guest: models.Guest) -> schemas.ConfirmGuestPublic:
    event = db.get(models.Event, guest.event_id)
    address = event.venue_address if event else ""
    title = _event_title(event)
    window = (
        calendar_links.parse_window(event.event_date, event.event_time)
        if event
        else None
    )

    acts = guest_journey.compute_actions(event, has_calendar=window is not None)

    cal = schemas.ConfirmCalendarLinks()
    if event is not None and window is not None:
        details = _hub_url(guest.guest_token or "")
        cal = schemas.ConfirmCalendarLinks(
            google=calendar_links.google_link(
                title=title,
                venue_name=event.venue_name,
                venue_address=address,
                description=details,
                window=window,
            ),
            outlook=calendar_links.outlook_link(
                title=title,
                venue_name=event.venue_name,
                venue_address=address,
                description=details,
                window=window,
            ),
            # נתיב יחסי בכוונה: ה-Frontend יושב בדומיין אחר מה-API, והוא
            # היחיד שמכיר את כתובת השרת (``VITE_API_URL``) — בדיוק כמו
            # ``mediaUrl``. הרכבה כאן הייתה מייצרת קישור לדומיין הלא נכון.
            ics=f"/confirm/{guest.guest_token}/calendar.ics",
        )

    return schemas.ConfirmGuestPublic(
        full_name=guest.full_name,
        party_size=guest.party_size,
        rsvp_status=guest.rsvp_status,
        confirmed_count=guest.confirmed_count,
        guest_note=guest.guest_note,
        event=schemas.ConfirmEventInfo(
            event_type=(event.event_type or "wedding") if event else "wedding",
            groom_name=event.groom_name if event else "",
            bride_name=event.bride_name if event else "",
            venue_name=event.venue_name if event else "",
            venue_address=address,
            maps_link=messaging.maps_link(address),
            waze_link=messaging.waze_link(address),
            apple_maps_link=messaging.apple_maps_link(address),
            event_date=event.event_date if event else "",
            event_time=event.event_time if event else "",
            invite_image=media.to_url(event.invite_image) if event else None,
            title=title,
            calendar=cal,
        ),
        # הזמינות כולה מגיעה ממנוע מסע האורח — מקור אמת יחיד, שגם נקודת
        # קצה עתידית למתנה תיאכף מולו (guest_journey.assert_action_allowed).
        actions=schemas.ConfirmActions(**vars(acts)),
    )


@router.get("/{token}", response_model=schemas.ConfirmGuestPublic)
def get_confirm(token: str, request: Request, db: Session = Depends(get_db)):
    """מחזיר את פרטי האירוע והמוזמן לפי הטוקן האישי (ללא נתוני מוזמנים אחרים)."""
    ip = _client_ip(request)
    _check_rate(ip)
    # מזריקים את הטוקן ל-session *לפני* השאילתה הראשונה, כדי שמדיניות ה-RLS
    # (guests/events/messages) תזהה את המוזמן האנונימי — ראו database.py.
    set_guest_token(token, db)
    guest = db.scalar(select(models.Guest).where(models.Guest.guest_token == token))
    if guest is None:
        _record_fail(ip)
        audit.record(db, "confirm_invalid_token", detail="ניסיון גישה לקישור לא תקין", ip=ip)
        db.commit()
        raise HTTPException(status_code=404, detail="הקישור כבר לא פעיל — בקשו ממארגני האירוע קישור חדש.")
    return _public(db, guest)


@router.get("/{token}/calendar.ics")
def get_confirm_ics(token: str, request: Request, db: Session = Depends(get_db)):
    """קובץ יומן (ICS) לאירוע של בעל הטוקן — "הוספה ליומן" באייפון ובאאוטלוק.

    אותה הגנה בדיוק כמו העמוד עצמו: הגבלת ניסיונות, הזרקת הטוקן ל-RLS, ו-404
    זהה לטוקן שגוי. הקובץ מכיל **רק פרטי אירוע** — לא שם המוזמן, לא סטטוס
    ההגעה שלו ולא שום נתון אישי, כי קובץ יומן נוטה להישמר ולהשתתף בשיתופים.
    """
    ip = _client_ip(request)
    _check_rate(ip)
    set_guest_token(token, db)
    guest = db.scalar(select(models.Guest).where(models.Guest.guest_token == token))
    if guest is None:
        _record_fail(ip)
        audit.record(db, "confirm_invalid_token", detail="ניסיון הורדת יומן לקישור לא תקין", ip=ip)
        db.commit()
        raise HTTPException(status_code=404, detail="הקישור כבר לא פעיל — בקשו ממארגני האירוע קישור חדש.")

    event = db.get(models.Event, guest.event_id)
    window = (
        calendar_links.parse_window(event.event_date, event.event_time)
        if event
        else None
    )
    if event is None or window is None:
        raise HTTPException(status_code=404, detail="עדיין אין תאריך לאירוע.")

    body = calendar_links.build_ics(
        title=_event_title(event),
        event_id=event.id,
        venue_name=event.venue_name,
        venue_address=event.venue_address,
        description=_hub_url(token),
        window=window,
    )
    # שם הקובץ בעברית: ASCII כ-fallback + RFC 5987 לדפדפנים מודרניים.
    ascii_name = "veya-event.ics"
    utf8_name = quote(calendar_links.ics_filename(_event_title(event)))
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{utf8_name}"
            ),
            # פרטי אירוע יכולים להשתנות (שעה/אולם) — לא שומרים בקאש ארוך.
            "Cache-Control": "no-store",
        },
    )


def _guest_or_404(token: str, request: Request, db: Session, *, what: str):
    """אימות הטוקן — זהה לחלוטין לשאר הנתיבים הציבוריים.

    אותה הגבלת ניסיונות, אותה הזרקת RLS ואותה תשובת 404 בדיוק. חשוב
    שהתשובה תהיה זהה: הבדל בין "טוקן לא קיים" ל"טוקן קיים אבל" היה מאפשר
    למפות טוקנים תקינים בניחוש.
    """
    ip = _client_ip(request)
    _check_rate(ip)
    set_guest_token(token, db)
    guest = db.scalar(select(models.Guest).where(models.Guest.guest_token == token))
    if guest is None:
        _record_fail(ip)
        audit.record(db, "confirm_invalid_token", detail=f"ניסיון {what} לקישור לא תקין", ip=ip)
        db.commit()
        raise HTTPException(status_code=404, detail="הקישור כבר לא פעיל — בקשו ממארגני האירוע קישור חדש.")
    return guest, ip


def _gift_gate(db: Session, guest: models.Guest) -> models.Event:
    """מוודא שאזור המתנה באמת פתוח למוזמן הזה **עכשיו**.

    זו נקודת האכיפה האמיתית: לא הכפתור ב-UI ולא ``?action=gift`` בכתובת.
    ``assert_action_allowed`` זורק 403 מחוץ לחלון הזמינות, כך שגם מי
    שיקרא לנתיב ישירות מחוץ לחלון לא יקבל תמחור ולא יוכל "לשלם".
    """
    event = db.get(models.Event, guest.event_id)
    window = (
        calendar_links.parse_window(event.event_date, event.event_time)
        if event
        else None
    )
    guest_journey.assert_action_allowed(
        event, "gift", has_calendar=window is not None
    )
    return event


def _quote_read(q: gift_money.GiftQuote) -> schemas.GiftQuoteRead:
    return schemas.GiftQuoteRead(
        gift_amount_agorot=q.gift_amount_agorot,
        fee_agorot=q.fee_agorot,
        total_agorot=q.total_agorot,
        fee_percent=q.fee_percent,
    )


@router.post("/{token}/gift/quote", response_model=schemas.GiftQuoteRead)
def gift_quote(
    token: str,
    payload: schemas.GiftQuoteRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """מחשב עמלה וסכום כולל מהסכום שהזוג אמור לקבל.

    ה-Frontend קורא לזה בכל שינוי סכום ומציג את מה שחוזר — הוא **לא**
    מחשב כסף בעצמו. כך המספר שהאורח רואה על המסך הוא תמיד המספר שהשרת
    יחייב בו, ואין מצב שהם נפרדים.
    """
    guest, _ = _guest_or_404(token, request, db, what="תמחור מתנה")
    _gift_gate(db, guest)
    try:
        return _quote_read(gift_money.quote_from_input(payload.gift_amount_agorot))
    except gift_money.GiftAmountError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/{token}/gift/checkout", response_model=schemas.GiftCheckoutResult)
def gift_checkout(
    token: str,
    payload: schemas.GiftCheckoutRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """תשלום **מדומה** — אין כאן סליקה, ספק תשלומים או תנועת כסף.

    הנתיב קיים כדי שאפשר יהיה לבדוק את המסלול המלא מקצה לקצה לפני
    שמחברים ספק אמיתי. הוא מחשב את הסכומים מחדש (ולא סומך על כלום שהגיע
    מהלקוח), רושם שורה ביומן הפעילות של הזוג, ומחזיר תוצאה מדומה.

    **לא נשמר שום רישום כספי** — אין טבלת מתנות ואין מיגרציה, בדיוק כפי
    שאין עדיין כסף אמיתי לרשום.
    """
    guest, ip = _guest_or_404(token, request, db, what="תשלום מתנה")
    _gift_gate(db, guest)

    # חישוב מחדש בשרת. מה שהלקוח חשב לגבי עמלה או סכום כולל לא נכנס לכאן
    # בכלל — הוא אפילו לא שדה קלט (ראו schemas.GiftCheckoutRequest).
    try:
        q = gift_money.quote_from_input(payload.gift_amount_agorot)
    except gift_money.GiftAmountError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    giver = (payload.giver_name or guest.full_name or "").strip()

    # יצירת עסקה (או החזרת הקיימת, אם זו לחיצה כפולה/ניסיון חוזר).
    try:
        gift_row, created = gift_service.create_gift(
            db,
            guest,
            gift_amount_agorot=payload.gift_amount_agorot,
            sender_name=payload.giver_name,
            message=payload.blessing,
            client_idempotency_key=payload.idempotency_key,
        )
    except gift_service.GiftConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    # פנייה לספק וסנכרון הסטטוס **מתשובתו**. הסטטוס לא נקבע מ-payload.
    gift_row = gift_service.start_payment(db, gift_row, simulate=payload.simulate)
    ok = gift_row.status == gift_status.PAID

    if created:
        audit.record(
            db,
            "gift_mock_checkout",
            event_id=guest.event_id,
            detail=(
                f"[הדמיה] {giver}: מתנה {gift_money.format_shekels(q.gift_amount_agorot)} · "
                f"עמלה {gift_money.format_shekels(q.fee_agorot)} · "
                f"סה\"כ {gift_money.format_shekels(q.total_agorot)} · "
                f"{gift_row.status} · {gift_row.provider_transaction_id}"
            ),
            ip=ip,
        )
    db.commit()

    return schemas.GiftCheckoutResult(
        status="success" if ok else "failure",
        quote=_quote_read(q),
        reference=gift_row.provider_transaction_id or gift_row.idempotency_key,
        gift_id=gift_row.id,
        gift_status=gift_row.status,
        mock=True,
        message="" if ok else "התשלום לא עבר. אפשר לנסות שוב.",
    )


@router.post("/{token}", response_model=schemas.ConfirmGuestPublic)
def submit_confirm(
    token: str,
    payload: schemas.ConfirmSubmit,
    request: Request,
    db: Session = Depends(get_db),
):
    """המוזמן מסמן אם הוא מגיע, כמה אנשים, והערה. מעדכן סטטוס ורושם ביומן."""
    ip = _client_ip(request)
    _check_rate(ip)
    set_guest_token(token, db)
    guest = db.scalar(select(models.Guest).where(models.Guest.guest_token == token))
    if guest is None:
        _record_fail(ip)
        audit.record(db, "confirm_invalid_token", detail="ניסיון שליחה לקישור לא תקין", ip=ip)
        db.commit()
        raise HTTPException(status_code=404, detail="הקישור כבר לא פעיל — בקשו ממארגני האירוע קישור חדש.")

    # אכיפת חלון אישורי ההגעה בשרת — לא רק הסתרת הכפתור ב-UI. אורח שקיבל
    # את הקישור מוקדם (או שקורא ישירות ל-API) לא יכול לאשר לפני שהחלון נפתח.
    event = db.get(models.Event, guest.event_id)
    if not guest_journey.rsvp_is_open(event):
        raise HTTPException(
            status_code=403,
            detail="אישורי ההגעה עדיין לא נפתחו לאירוע הזה — הקישור יתעדכן מעצמו כשאפשר יהיה לאשר.",
        )

    # אותה לוגיקה בדיוק שרצה כשהאדמין מסמן במקום המוזמן בשיחת טלפון
    # (Call Center) — ראו app/rsvp_response.py.
    note = (payload.note or "").strip()
    decision = "maybe" if payload.maybe else ("confirmed" if payload.coming else "declined")
    label = rsvp_response.apply_response(
        guest, decision, count=payload.count, note=note
    )

    body = label + (f" · הערה: {note}" if note else "")
    # מוזמן אנונימי (רק guest_token, בלי משתמש) — messages_select דורש הרשאת
    # משתמש, אז INSERT רגיל (עם RETURNING שברירת המחדל של SQLAlchemy) היה
    # נדחה ע"י RLS. עוברים דרך app_record_confirm_message (SECURITY DEFINER).
    if IS_POSTGRES:
        db.execute(
            text("SELECT app_record_confirm_message(:gid, :body)"),
            {"gid": guest.id, "body": body},
        )
    else:
        db.add(models.Message(
            event_id=guest.event_id,
            guest_id=guest.id,
            direction="inbound",
            kind="reply",
            body=body,
            status="received",
            provider="web",
        ))
    audit.record(
        db, "confirm_submit",
        event_id=guest.event_id,
        detail=f"{guest.full_name}: {label}",
        ip=ip,
    )
    db.commit()
    return _public(db, guest)
