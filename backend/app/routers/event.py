"""נקודת API לפרטי האירוע (שם החתן/כלה/אולם) — שלב 6.

בשלב הנוכחי יש אירוע יחיד. הפרטים משמשים לכותרת ההזמנה שנשלחת בוואטסאפ
ולכותרת הדשבורד.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, media, models, schemas, venues
from app.auth import get_current_user
from app.database import get_db
from app.deps import get_current_event

router = APIRouter(prefix="/event", tags=["event"])


def _describe_changed_fields(changed: dict) -> str:
    """הופך את שמות השדות הטכניים שהשתנו למשפט עברי קריא ליומן הפעילות.

    כך הזוג רואה "עדכנתם: שמות בני הזוג, פרטי האולם" ולא "עודכנו שדות:
    groom_name, venue_name".
    """
    categories = [
        (("groom_name", "bride_name"), "שמות בני הזוג"),
        (("venue_name", "venue_address"), "פרטי האולם"),
        (("event_date", "event_time"), "תאריך ושעת האירוע"),
        (("invite_image",), "תמונת ההזמנה"),
        (("venue_commit_days_before",), "יום ההתחייבות לאולם"),
    ]
    labels = [label for keys, label in categories if any(k in changed for k in keys)]
    if not labels:
        return "עדכנתם את פרטי האירוע"
    return "עדכנתם: " + ", ".join(labels)


def _event_read(event: models.Event) -> schemas.EventRead:
    """בונה תשובה עם URL מלא לתמונת ההזמנה (במקום הנתיב הגולמי שב-DB)."""
    return schemas.EventRead(
        id=event.id,
        groom_name=event.groom_name,
        bride_name=event.bride_name,
        venue_name=event.venue_name,
        venue_address=event.venue_address or "",
        event_date=event.event_date or "",
        event_time=event.event_time or "",
        invite_image=media.to_url(event.invite_image),
        venue_commit_days_before=event.venue_commit_days_before,
        venue_commit_locked=event.venue_commit_days_before is not None,
    )


@router.get("", response_model=schemas.EventRead)
def read_event(event: models.Event = Depends(get_current_event)):
    return _event_read(event)


@router.patch("", response_model=schemas.EventRead)
def update_event(
    payload: schemas.EventUpdate,
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
    user: models.User = Depends(get_current_user),
):
    changed = payload.model_dump(exclude_unset=True)
    for key, value in changed.items():
        if key == "invite_image":
            # תמונה: data URL → קובץ; ריק → מחיקה; URL קיים → ללא שינוי.
            event.invite_image = media.resolve_incoming(
                value, event.invite_image, prefix=f"invite-{event.id}"
            )
        elif key == "venue_commit_days_before":
            # יום ההתחייבות — בחירה חד-פעמית ובלתי-הפיכה. אפשר להגדיר רק פעם
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
                        detail="יום ההתחייבות כבר נקבע ואי אפשר לשנות אותו — כל לוח הזמנים של אישורי ההגעה נבנה סביבו.",
                    )
                continue
            event.venue_commit_days_before = value
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
    db.refresh(event)
    return _event_read(event)


@router.get("/audit", response_model=list[schemas.AuditLogRow])
def read_audit(
    limit: int = 30,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """יומן האבטחה של האירוע — הפעולות הרגישות האחרונות (למנהל האירוע בלבד)."""
    stmt = (
        select(models.AuditLog)
        .where(models.AuditLog.event_id == event.id)
        .order_by(models.AuditLog.created_at.desc())
        .limit(max(1, min(limit, 100)))
    )
    return db.scalars(stmt).all()
