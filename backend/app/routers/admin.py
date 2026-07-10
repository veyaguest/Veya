"""Router לפאנל האדמין (הבעלים) — שלב 8.

מאפשר לבעלים (משתמש עם ``is_admin``) לראות את *כל* המשתמשים ו*כל* האירועים
במערכת, כולל ספירת מוזמנים לכל אחד. מוגן ב-``get_current_admin`` — משתמש רגיל
יקבל 403.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_admin
from app.database import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[schemas.AdminUserRow])
def list_users(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """כל המשתמשים במערכת, עם מספר האירועים והמוזמנים של כל אחד."""
    # ספירת אירועים לכל בעלים.
    events_by_owner = dict(
        db.execute(
            select(models.Event.owner_id, func.count(models.Event.id))
            .group_by(models.Event.owner_id)
        ).all()
    )
    # ספירת מוזמנים לכל בעלים (דרך האירועים שלו).
    guests_by_owner = dict(
        db.execute(
            select(models.Event.owner_id, func.count(models.Guest.id))
            .join(models.Guest, models.Guest.event_id == models.Event.id)
            .group_by(models.Event.owner_id)
        ).all()
    )

    users = db.scalars(select(models.User).order_by(models.User.id)).all()
    return [
        schemas.AdminUserRow(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            is_admin=u.is_admin,
            events_count=events_by_owner.get(u.id, 0),
            guests_count=guests_by_owner.get(u.id, 0),
            created_at=u.created_at,
        )
        for u in users
    ]


@router.get("/events", response_model=list[schemas.AdminEventRow])
def list_all_events(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """כל האירועים במערכת (מכל המשתמשים), עם בעלים וספירת מוזמנים."""
    guests_by_event = dict(
        db.execute(
            select(models.Guest.event_id, func.count(models.Guest.id))
            .group_by(models.Guest.event_id)
        ).all()
    )
    emails = {u.id: u.email for u in db.scalars(select(models.User)).all()}

    events = db.scalars(select(models.Event).order_by(models.Event.id.desc())).all()
    return [
        schemas.AdminEventRow(
            id=e.id,
            groom_name=e.groom_name,
            bride_name=e.bride_name,
            venue_name=e.venue_name,
            owner_id=e.owner_id,
            owner_email=emails.get(e.owner_id) if e.owner_id else None,
            guests_count=guests_by_event.get(e.id, 0),
        )
        for e in events
    ]
