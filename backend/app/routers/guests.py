"""נקודות API לניהול מוזמנים (CRUD)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_event

router = APIRouter(prefix="/guests", tags=["guests"])

# תקרת גודל עמוד — מונעת שליפה ענקית אחת שתעמיס על השרת/דפדפן.
MAX_PAGE_LIMIT = 200
DEFAULT_PAGE_LIMIT = 50


@router.get("", response_model=schemas.GuestListPage)
def list_guests(
    q: Optional[str] = None,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """עמוד מתוך רשימת המוזמנים של האירוע הפעיל.

    תומך בחיפוש חופשי (``q`` לפי שם/טלפון) ובדפדוף (``limit``/``offset``).
    הסכומים (total/total_people/confirmed_people) מחושבים על *כל* הרשומות
    התואמות ולא רק על העמוד — כדי שסיכום המסך יישאר מדויק גם עם דפדוף.
    """
    limit = max(1, min(limit, MAX_PAGE_LIMIT))
    offset = max(0, offset)

    filters = [models.Guest.event_id == event.id]
    if q:
        like = f"%{q.strip()}%"
        filters.append(
            or_(models.Guest.full_name.ilike(like), models.Guest.phone.ilike(like))
        )

    # סכומים על כל הרשימה המסוננת (שאילתת אגרגציה אחת).
    confirmed_seats = case(
        (
            models.Guest.rsvp_status == "confirmed",
            func.coalesce(models.Guest.confirmed_count, models.Guest.party_size),
        ),
        else_=0,
    )
    total, total_people, confirmed_people = db.execute(
        select(
            func.count(),
            func.coalesce(func.sum(models.Guest.party_size), 0),
            func.coalesce(func.sum(confirmed_seats), 0),
        ).where(*filters)
    ).one()

    items = db.scalars(
        select(models.Guest)
        .where(*filters)
        .order_by(models.Guest.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    return schemas.GuestListPage(
        items=items,
        total=total,
        total_people=total_people,
        confirmed_people=confirmed_people,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=schemas.GuestRead, status_code=201)
def create_guest(
    payload: schemas.GuestCreate,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    guest = models.Guest(event_id=event.id, **payload.model_dump())
    db.add(guest)
    db.commit()
    db.refresh(guest)
    return guest


@router.patch("/{guest_id}", response_model=schemas.GuestRead)
def update_guest(
    guest_id: int,
    payload: schemas.GuestUpdate,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    guest = db.get(models.Guest, guest_id)
    if guest is None or guest.event_id != event.id:
        raise HTTPException(status_code=404, detail="מוזמן לא נמצא")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(guest, key, value)
    db.commit()
    db.refresh(guest)
    return guest


@router.delete("/{guest_id}", status_code=204)
def delete_guest(
    guest_id: int,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    guest = db.get(models.Guest, guest_id)
    if guest is None or guest.event_id != event.id:
        raise HTTPException(status_code=404, detail="מוזמן לא נמצא")
    db.delete(guest)
    db.commit()
