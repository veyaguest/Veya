"""דף אישור הגעה ציבורי — קישור אישי לכל מוזמן (/confirm/{token}).

זהו הנתיב היחיד ללא התחברות: המוזמן פותח את הקישור האישי שקיבל ב-WhatsApp,
רואה את פרטי האירוע *שלו בלבד*, ומסמן אם הוא מגיע וכמה אנשים. אין דרך
לראות מוזמן אחר — הטוקן אקראי ובלתי-ניתן-לניחוש, וכל בקשה מחזירה רק את
הנתונים של בעל הטוקן.
"""
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import audit, media, messaging, models, schemas
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


def _public(db: Session, guest: models.Guest) -> schemas.ConfirmGuestPublic:
    event = db.get(models.Event, guest.event_id)
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
            venue_address=event.venue_address if event else "",
            maps_link=messaging.maps_link(event.venue_address) if event else "",
            waze_link=messaging.waze_link(event.venue_address) if event else "",
            event_date=event.event_date if event else "",
            event_time=event.event_time if event else "",
            invite_image=media.to_url(event.invite_image) if event else None,
        ),
    )


@router.get("/{token}", response_model=schemas.ConfirmGuestPublic)
def get_confirm(token: str, request: Request, db: Session = Depends(get_db)):
    """מחזיר את פרטי האירוע והמוזמן לפי הטוקן האישי (ללא נתוני מוזמנים אחרים)."""
    ip = _client_ip(request)
    _check_rate(ip)
    # מזריקים את הטוקן ל-session *לפני* השאילתה הראשונה, כדי שמדיניות ה-RLS
    # (guests/events/messages) תזהה את המוזמן האנונימי — ראו database.py.
    set_guest_token(token)
    guest = db.scalar(select(models.Guest).where(models.Guest.guest_token == token))
    if guest is None:
        _record_fail(ip)
        audit.record(db, "confirm_invalid_token", detail="ניסיון גישה לקישור לא תקין", ip=ip)
        db.commit()
        raise HTTPException(status_code=404, detail="הקישור כבר לא פעיל — בקשו ממארגני האירוע קישור חדש.")
    return _public(db, guest)


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
    set_guest_token(token)
    guest = db.scalar(select(models.Guest).where(models.Guest.guest_token == token))
    if guest is None:
        _record_fail(ip)
        audit.record(db, "confirm_invalid_token", detail="ניסיון שליחה לקישור לא תקין", ip=ip)
        db.commit()
        raise HTTPException(status_code=404, detail="הקישור כבר לא פעיל — בקשו ממארגני האירוע קישור חדש.")

    if payload.maybe:
        guest.rsvp_status = "maybe"
        guest.confirmed_count = None
        label = "סימן/ה 'אולי'"
    elif payload.coming:
        # כמות: ברירת מחדל = כמה שהוזמנו. המוזמן יכול להוסיף כמות בפועל,
        # גם מעבר למה שהוזמן (למשל משפחה שגדלה), עד תקרה סבירה נגד שימוש לרעה.
        count = payload.count if payload.count is not None else guest.party_size
        count = max(1, min(count, 30))
        guest.rsvp_status = "confirmed"
        guest.confirmed_count = count
        label = f"אישר/ה הגעה ({count})"
    else:
        guest.rsvp_status = "declined"
        guest.confirmed_count = 0
        label = "ביטל/ה הגעה"

    note = (payload.note or "").strip()
    guest.guest_note = note or None

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
