"""נקודת API לפרטי האירוע (שם החתן/כלה/אולם) — שלב 6.

בשלב הנוכחי יש אירוע יחיד. הפרטים משמשים לכותרת ההזמנה שנשלחת בוואטסאפ
ולכותרת הדשבורד.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, communication, media, models, schemas, venues
from app.auth import get_current_owner
from app.database import get_db
from app.deps import EventAccess, get_current_event

# עדכון פרטי הליבה של האירוע (שם/תאריך/אולם/תמונה) נשאר בעלים/אדמין בלבד —
# אין הרשאת חבר-אירוע שפותחת את זה (בשונה מהושבה/הודעות/מוזמנים, שיש להן
# הרשאה ייעודית). ראו backend/rls/RLS_REPORT.md להסבר המלא של ההחלטה הזו.
_owner_only = EventAccess(owner_only=True)

router = APIRouter(prefix="/event", tags=["event"])


def _describe_changed_fields(changed: dict) -> str:
    """הופך את שמות השדות הטכניים שהשתנו למשפט עברי קריא ליומן הפעילות.

    כך הזוג רואה "עדכנתם: שמות בני הזוג, פרטי האולם" ולא "עודכנו שדות:
    groom_name, venue_name".
    """
    categories = [
        (("event_type",), "סוג האירוע"),
        (("groom_name", "bride_name"), "שמות בעלי האירוע"),
        (("groom_parents_line", "bride_parents_line"), "שמות ההורים בהזמנה"),
        (("venue_name", "venue_address"), "פרטי האולם"),
        (("event_date", "event_time"), "תאריך ושעת האירוע"),
        (("invite_image",), "תמונת ההזמנה"),
        (("venue_commit_days_before",), "מועד סגירת הרשימה"),
        (("rsvp_send_time", "thank_you_send_time"), "שעת שליחת ההודעות"),
    ]
    labels = [label for keys, label in categories if any(k in changed for k in keys)]
    if not labels:
        return "עדכנתם את פרטי האירוע"
    return "עדכנתם: " + ", ".join(labels)


def _event_read(event: models.Event) -> schemas.EventRead:
    """בונה תשובה עם URL מלא לתמונת ההזמנה (במקום הנתיב הגולמי שב-DB)."""
    return schemas.EventRead(
        id=event.id,
        event_type=event.event_type or "wedding",
        groom_name=event.groom_name,
        bride_name=event.bride_name,
        groom_parents_line=event.groom_parents_line or "",
        bride_parents_line=event.bride_parents_line or "",
        venue_name=event.venue_name,
        venue_address=event.venue_address or "",
        event_date=event.event_date or "",
        event_time=event.event_time or "",
        invite_image=media.to_url(event.invite_image),
        venue_commit_days_before=event.venue_commit_days_before,
        venue_commit_locked=event.venue_commit_days_before is not None,
        rsvp_send_time=event.rsvp_send_time or communication.DEFAULT_SEND_TIME,
        thank_you_send_time=event.thank_you_send_time or communication.DEFAULT_SEND_TIME,
    )


@router.get("", response_model=schemas.EventRead)
def read_event(event: models.Event = Depends(get_current_event)):
    return _event_read(event)


@router.patch("", response_model=schemas.EventRead)
def update_event(
    payload: schemas.EventUpdate,
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_owner_only),
    user: models.User = Depends(get_current_owner),
):
    changed = payload.model_dump(exclude_unset=True)
    for key, value in changed.items():
        if key == "invite_image":
            # תמונה: data URL → קובץ; ריק → מחיקה; URL קיים → ללא שינוי.
            event.invite_image = media.resolve_incoming(
                db, value, event.invite_image, prefix=f"invite-{event.id}", optimize=True
            )
        elif key == "venue_commit_days_before":
            # מועד סגירת הרשימה — בחירה חד-פעמית ובלתי-הפיכה. אפשר להגדיר רק פעם
            # אחת; ניסיון לשנות ערך שכבר נקבע נדחה, כי כל לוח הזמנים של אישורי
            # ההגעה נבנה סביבו. None בגוף הבקשה => התעלמות (לא מאפס בטעות).
            if value is None:
                continue
            if not isinstance(value, int) or not (1 <= value <= 10):
                raise HTTPException(
                    status_code=400,
                    detail="בחרו כמה ימים לפני האירוע צריך למסור לאולם (בין 1 ל-10).",
                )
            if event.venue_commit_days_before is not None:
                if event.venue_commit_days_before != value:
                    raise HTTPException(
                        status_code=400,
                        detail="מועד סגירת הרשימה כבר נקבע ואי אפשר לשנות אותו — כל לוח הזמנים של אישורי ההגעה נבנה סביבו.",
                    )
                continue
            event.venue_commit_days_before = value
        elif key in ("rsvp_send_time", "thank_you_send_time"):
            # None בגוף הבקשה => התעלמות (לא מאפס בטעות) — כמו venue_commit_days_before.
            if value is None:
                continue
            try:
                setattr(event, key, communication.validate_send_time(value))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        else:
            setattr(event, key, (value or "").strip())
    # מאגר אולמות משותף: כל שם+כתובת שזוג שומר נרשם למאגר, כדי שזוגות אחרים
    # יקבלו הצעת השלמה עם הכתובת המוכנה. שם ריק => נדלג (record_venue מתעלם).
    if "venue_name" in changed or "venue_address" in changed:
        venues.record_venue(db, event.venue_name, event.venue_address or "")
    audit.record(
        db, "update_event",
        event_id=event.id, user_id=user.id,
        detail=_describe_changed_fields(changed),
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return _event_read(event)


@router.get("/audit", response_model=list[schemas.AuditLogRow])
def read_audit(
    limit: int = 30,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """יומן הפעילות של האירוע — מי עשה מה ומתי (למנהלי האירוע בלבד).

    שני המנהלים (בעלים ובן/בת זוג) רואים את אותו יומן בדיוק — הוא תלוי
    אירוע, לא משתמש.
    """
    stmt = (
        select(models.AuditLog)
        .where(models.AuditLog.event_id == event.id)
        .order_by(models.AuditLog.created_at.desc())
        .limit(max(1, min(limit, 100)))
    )
    rows = db.scalars(stmt).all()

    # שם המבצע בשאילתה אחת לכל השורות (ולא db.get בלולאה — N+1), באותה
    # תבנית שכבר קיימת ב-routers/event_members.py.
    actor_ids = {r.user_id for r in rows if r.user_id is not None}
    names: dict[int, str] = {}
    if actor_ids:
        for u in db.scalars(
            select(models.User).where(models.User.id.in_(actor_ids))
        ).all():
            names[u.id] = u.display_name or u.email.split("@")[0]

    result = []
    for row in rows:
        item = schemas.AuditLogRow.model_validate(row)
        item.actor_name = names.get(row.user_id, "") if row.user_id else ""
        result.append(item)
    return result
