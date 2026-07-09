"""נקודות API לניהול מוזמנים (CRUD)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_default_event

router = APIRouter(prefix="/guests", tags=["guests"])


@router.get("", response_model=list[schemas.GuestRead])
def list_guests(q: Optional[str] = None, db: Session = Depends(get_db)):
    """רשימת מוזמנים, עם חיפוש חופשי לפי שם/טלפון (פרמטר q)."""
    stmt = select(models.Guest)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(models.Guest.full_name.ilike(like), models.Guest.phone.ilike(like))
        )
    stmt = stmt.order_by(models.Guest.created_at.desc())
    return db.scalars(stmt).all()


@router.post("", response_model=schemas.GuestRead, status_code=201)
def create_guest(
    payload: schemas.GuestCreate,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_default_event),
):
    guest = models.Guest(event_id=event.id, **payload.model_dump())
    db.add(guest)
    db.commit()
    db.refresh(guest)
    return guest


@router.patch("/{guest_id}", response_model=schemas.GuestRead)
def update_guest(
    guest_id: int, payload: schemas.GuestUpdate, db: Session = Depends(get_db)
):
    guest = db.get(models.Guest, guest_id)
    if guest is None:
        raise HTTPException(status_code=404, detail="מוזמן לא נמצא")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(guest, key, value)
    db.commit()
    db.refresh(guest)
    return guest


@router.delete("/{guest_id}", status_code=204)
def delete_guest(guest_id: int, db: Session = Depends(get_db)):
    guest = db.get(models.Guest, guest_id)
    if guest is None:
        raise HTTPException(status_code=404, detail="מוזמן לא נמצא")
    db.delete(guest)
    db.commit()
