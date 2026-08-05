"""נקודות API ל"תקשורת עם אורחים" — רצף ההודעות הקבוע של אירוע (שלב 1: תשתית).

מחליף את הצירוף הישן ספריית-הודעות + תבניות/חוקי-אוטומציה חופשיים ברצף אחד,
קבוע לפי event_type (ראו ``app/communication.py``). עקרון "תור לאישור" נשמר:
``/due`` רק מחשב, ``/due/send`` שולח בפועל רק אחרי אישור מפורש.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, communication, messaging, models, permissions, schemas
from app.auth import get_current_user
from app.database import get_db
from app.deps import EventAccess

router = APIRouter(prefix="/communication", tags=["communication"])

_view = EventAccess(permissions.MESSAGES_VIEW)
_write = EventAccess(permissions.MESSAGES_WRITE)


def _get_sequence(db: Session, event: models.Event) -> list[models.EventMessage]:
    if communication.provision_event_messages(db, event):
        db.commit()
    by_type = communication.event_messages_by_type(db, event.id)
    return [by_type[mt] for mt in communication.MESSAGE_TYPES if mt in by_type]


def _get_message(db: Session, event: models.Event, message_type: str) -> models.EventMessage:
    em = db.scalar(
        select(models.EventMessage)
        .where(models.EventMessage.event_id == event.id)
        .where(models.EventMessage.message_type == message_type)
    )
    if em is None:
        raise HTTPException(status_code=404, detail="ההודעה לא נמצאה")
    return em


@router.get("/sequence", response_model=list[schemas.EventMessageRead])
def get_sequence(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_view),
):
    """רצף 6 ההודעות של האירוע, בסדר קבוע. מקצה אוטומטית אם עדיין חסר."""
    return _get_sequence(db, event)


@router.put("/sequence/{message_type}", response_model=schemas.EventMessageRead)
def update_message(
    message_type: str,
    payload: schemas.EventMessageUpdate,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_write),
):
    if message_type not in communication.MESSAGE_TYPES:
        raise HTTPException(status_code=400, detail="סוג הודעה לא מוכר")
    em = _get_message(db, event, message_type)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(em, key, value)
    db.commit()
    return em


@router.get(
    "/sequence/{message_type}/options",
    response_model=list[schemas.MessageDefaultOptionRead],
)
def get_message_options(
    message_type: str,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_view),
):
    """נוסחים מוכנים לבחירה עבור ההודעה הזו וסוג האירוע — לקריאה בלבד. הבחירה
    בפועל (שימוש בנוסח) מתבצעת בצד הלקוח: מעתיקים את ``content`` הנבחר לתוך
    הטקסטרה של ``PUT /sequence/{message_type}``, בדיוק כמו עריכה חופשית."""
    rows = db.scalars(
        select(models.MessageDefaultOption)
        .where(models.MessageDefaultOption.event_type == event.event_type)
        .where(models.MessageDefaultOption.message_type == message_type)
        .where(models.MessageDefaultOption.is_active == True)  # noqa: E712
        .where(models.MessageDefaultOption.content != "")
        .order_by(models.MessageDefaultOption.option_number)
    ).all()
    return rows


@router.post("/sequence/{message_type}/preview", response_model=schemas.CommunicationPreview)
def preview_message(
    message_type: str,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_view),
):
    em = _get_message(db, event, message_type)
    sample_guest = db.scalar(
        select(models.Guest).where(models.Guest.event_id == event.id)
    )
    values = communication.communication_values(event, sample_guest)
    return schemas.CommunicationPreview(preview=communication.render_message(em.content, values))


@router.post("/sequence/{message_type}/test-send", response_model=schemas.CommunicationSendResult)
def test_send_message(
    message_type: str,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_write),
    user: models.User = Depends(get_current_user),
):
    """שולח תצוגה מקדימה לטלפון הבעלים עצמו — לא נספר בסטטיסטיקות אמיתיות
    ולא נרשם ביומן ההודעות (אינו חלק מה-Timeline של אף מוזמן)."""
    em = _get_message(db, event, message_type)
    if not user.phone:
        raise HTTPException(status_code=400, detail="הוסיפו מספר טלפון לפרופיל שלכם כדי לשלוח בדיקה")
    sample_guest = db.scalar(
        select(models.Guest).where(models.Guest.event_id == event.id)
    )
    values = communication.communication_values(event, sample_guest)
    text = communication.render_message(em.content, values)
    if not text:
        raise HTTPException(status_code=400, detail="אין עדיין תוכן להודעה הזו")
    res = messaging.get_provider().send_invitation(user.phone, text)
    return schemas.CommunicationSendResult(
        mode=messaging.current_mode(),
        sent=1 if res.ok else 0,
        failed=0 if res.ok else 1,
        detail=res.detail or None,
    )


@router.get("/library", response_model=list[schemas.MessageDefaultRead])
def get_library(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """ספריית הודעות מוכנות — קריאה בלבד: כל ברירות המחדל (8 סוגי אירוע ×
    6 סוגי הודעה) לצפייה מתוך אזור האירוע. אינו תלוי-אירוע ספציפי (לכן אין
    EventAccess כאן) — כל משתמש מחובר יכול לעיין בכל סוגי האירוע. זה בדיוק
    התוכן שמוקצה אוטומטית לכל אירוע חדש מאותו סוג (``provision_event_messages``).
    """
    order = {mt: i for i, mt in enumerate(communication.MESSAGE_TYPES)}
    rows = db.scalars(select(models.MessageDefault)).all()
    return sorted(rows, key=lambda r: (r.event_type, order.get(r.message_type, 99)))


@router.get("/due", response_model=schemas.CommunicationDueQueue)
def get_due(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_view),
):
    """התור לאישור — מי אמור לקבל הודעה עכשיו (מחושב חי, לא נשלח כלום)."""
    actions = communication.compute_due_messages(db, event)
    return schemas.CommunicationDueQueue(
        mode=messaging.current_mode(),
        actions=[
            schemas.CommunicationDue(
                event_message_id=a.event_message.id,
                message_type=a.event_message.message_type,
                guest_id=a.guest.id,
                guest_name=a.guest.full_name,
                phone=a.guest.phone,
                preview=a.preview,
            )
            for a in actions
        ],
    )


@router.post("/due/send", response_model=schemas.CommunicationSendResult)
def send_due(
    payload: schemas.CommunicationSendRequest,
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_write),
    user: models.User = Depends(get_current_user),
):
    """שולח בפועל את מה שנבחר מהתור — רק אחרי לחיצת אישור של הבעלים."""
    actions = communication.compute_due_messages(db, event)
    if payload.items is not None:
        wanted = set(payload.items)
        actions = [
            a for a in actions
            if (a.event_message.id, a.guest.id) in wanted
        ]
    if not actions:
        raise HTTPException(status_code=400, detail="אין כרגע פעולות לשליחה בתור")

    result = communication.send_due_messages(db, event, actions)
    audit.record(
        db, "communication_send_due",
        event_id=event.id, user_id=user.id,
        detail=f"תקשורת עם אורחים: נשלחו {result['sent']}, נכשלו {result['failed']}",
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return schemas.CommunicationSendResult(
        mode=messaging.current_mode(),
        sent=result["sent"], failed=result["failed"],
        detail=result["detail"] or None,
    )
