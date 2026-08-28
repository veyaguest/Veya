"""נקודות API ל"תקשורת עם אורחים" — רצף ההודעות הקבוע של אירוע (שלב 1: תשתית).

מחליף את הצירוף הישן ספריית-הודעות + תבניות/חוקי-אוטומציה חופשיים ברצף אחד,
קבוע לפי event_type (ראו ``app/communication.py``). עקרון "תור לאישור" נשמר:
``/due`` רק מחשב, ``/due/send`` שולח בפועל רק אחרי אישור מפורש.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import (
    audit, communication, event_cycle, invitations, message_status, messaging,
    models, permissions, postponement_service, schemas,
)
from app.auth import get_current_owner
from app.database import get_db
from app.deps import EventAccess

router = APIRouter(prefix="/communication", tags=["communication"])

_view = EventAccess(permissions.MESSAGES_VIEW)
_write = EventAccess(permissions.MESSAGES_WRITE)


def _get_sequence(db: Session, event: models.Event) -> list[models.EventMessage]:
    """רצף ההודעות שהזוג רואה.

    ששת השלבים הקבועים תמיד, ואחריהם — **רק כשנוהל הדחייה פתוח** — כרטיס
    "אירוע נדחה". השורה עצמה נשארת ב-DB גם אחרי שהנוהל נסגר (כולל הנוסח
    שהזוג ערך), אבל יוצאת מהתצוגה: אירוע שחזר לשגרה לא צריך כרטיס דחייה
    על המסך.
    """
    if communication.provision_event_messages(db, event):
        db.commit()
    by_type = communication.event_messages_by_type(db, event.id)
    rows = [by_type[mt] for mt in communication.MESSAGE_TYPES if mt in by_type]
    if postponement_service.edit_unlocked(db, event):
        extra = by_type.get(communication.POSTPONEMENT)
        if extra is not None:
            rows.append(extra)
    return rows


def _assert_known_type(db: Session, event: models.Event, message_type: str) -> None:
    """סוג הודעה מוכר לאירוע הזה כרגע.

    ``postponement`` מוכר רק בזמן נוהל דחייה פתוח — אחרת אין מה לערוך או
    לשלוח, וההגבלה נאכפת כאן ולא רק בהסתרת כרטיס במסך.
    """
    if message_type in communication.MESSAGE_TYPES:
        return
    if message_type == communication.POSTPONEMENT:
        if postponement_service.edit_unlocked(db, event):
            return
        raise HTTPException(
            status_code=409,
            detail="הודעת הדחייה נפתחת רק אחרי אישור נוהל דחייה",
        )
    raise HTTPException(status_code=400, detail="סוג הודעה לא מוכר")


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
    _assert_known_type(db, event, message_type)
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
    הטקסטרה של ``PUT /sequence/{message_type}``, בדיוק כמו עריכה חופשית.

    הגישה נבדקת גם כאן, ולא רק בעריכה ובשליחה: נוסחי "אירוע נדחה" נפתחים רק
    כשנוהל הדחייה אושר. בלי הבדיקה הזו כל זוג היה יכול לשלוף אותם בקריאה
    ישירה, גם בלי שהאירוע שלו נדחה בכלל.
    """
    _assert_known_type(db, event, message_type)
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
    return schemas.CommunicationPreview(
        preview=communication.render_message(em.content, values, message_type=message_type)
    )


@router.post("/sequence/{message_type}/test-send", response_model=schemas.CommunicationSendResult)
def test_send_message(
    message_type: str,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_write),
    user: models.User = Depends(get_current_owner),
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
    text = communication.render_message(em.content, values, message_type=message_type)
    if not text:
        raise HTTPException(status_code=400, detail="אין עדיין תוכן להודעה הזו")
    res = messaging.get_provider().send_invitation(user.phone, text)
    return schemas.CommunicationSendResult(
        mode=messaging.current_mode(),
        sent=1 if res.ok else 0,
        failed=0 if res.ok else 1,
        detail=res.detail or None,
    )


@router.post(
    "/sequence/{message_type}/send",
    response_model=schemas.CommunicationManualSendResult,
)
def manual_send(
    message_type: str,
    payload: schemas.CommunicationManualSend,
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_write),
    user: models.User = Depends(get_current_owner),
):
    """שליחה ידנית של הודעה לקהל נבחר.

    **מוגבל להודעות שנשלחות ידנית מטבען** (היום: "אירוע נדחה"). ההזמנה
    אינה כאן במכוון — היא נשלחת דרך ``POST /automation/track/activate``,
    שאוכף את הכלל "הזמנה אחת בלבד לכל אורח". שני מסלולים לאותה שליחה היו
    בדיוק הדרך שבה אורח מקבל הזמנה כפולה.

    בשונה מהודעות הרצף, כאן **אין dedup**: אם הזוג בחר לשלוח שוב הודעת
    דחייה (למשל אחרי שתיקן נוסח) — זו הכוונה שלו, לא תקלה.
    """
    if message_type not in communication.MANUAL_SEND_TYPES:
        raise HTTPException(
            status_code=400,
            detail="ההודעה הזו נשלחת אוטומטית לפי לוח הזמנים, לא ידנית",
        )
    _assert_known_type(db, event, message_type)
    em = _get_message(db, event, message_type)
    if not em.content:
        raise HTTPException(status_code=400, detail="אין עדיין תוכן להודעה הזו")

    guests = db.scalars(
        select(models.Guest).where(models.Guest.event_id == event.id)
    ).all()
    if payload.guest_ids is not None:
        chosen = set(payload.guest_ids)
        targets = [g for g in guests if g.id in chosen]
    else:
        targets = [
            g for g in guests
            if communication.matches_audience(g, payload.audience)
        ]

    provider = messaging.get_provider()
    sent = failed = skipped = 0
    last_detail = ""
    for g in targets:
        if invitations.classify_phone(g.phone) != "valid":
            skipped += 1
            continue
        text = communication.render_message(
            em.content, communication.communication_values(event, g), message_type=message_type
        )
        if not text:
            skipped += 1
            continue
        res = provider.send_invitation(g.phone, text)
        db.add(models.Message(
            event_id=event.id,
            guest_id=g.id,
            direction="outbound",
            kind=message_type,
            body=text,
            channel="whatsapp",
            event_message_id=em.id,
            cycle_number=event_cycle.of(event),
            **message_status.outbound_fields(res),
        ))
        if res.ok:
            sent += 1
        else:
            failed += 1
            last_detail = res.detail
    audit.record(
        db, "manual_message_send",
        event_id=event.id, user_id=user.id,
        detail=f"שלחתם '{em.title or message_type}' ל-{sent} מוזמנים",
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return schemas.CommunicationManualSendResult(
        mode=messaging.current_mode(),
        sent=sent,
        failed=failed,
        skipped_no_phone=skipped,
        detail=last_detail or None,
    )


@router.get("/library", response_model=list[schemas.MessageDefaultRead])
def get_library(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_owner),
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
    user: models.User = Depends(get_current_owner),
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
