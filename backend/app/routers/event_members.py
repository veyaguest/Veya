"""Router לניהול חברי-אירוע (מפיק/אולם ששותפו על אירוע של זוג).

רק בעל האירוע (או אדמין-על) יכול לנהל מי מחובר לאירוע שלו ובאילו הרשאות —
חברי-האירוע עצמם לא יכולים לשנות את הגישה שלהם. הוספת חבר נעשית לפי אימייל
מדויק, ורק לחשבונות מסוג planner/venue קיימים (לא נחשפים משתמשים אחרים —
עקבי עם עקרון בידוד המידע בין אירועים).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_user
from app.database import get_db
from app.schemas import PLANNER_PERMISSIONS, VENUE_PERMISSIONS

router = APIRouter(prefix="/events/{event_id}/members", tags=["event-members"])


def _permissions_for_role(role: str) -> list[str]:
    return PLANNER_PERMISSIONS if role == "planner" else VENUE_PERMISSIONS


def _require_owner(event_id: int, db: Session, user: models.User) -> models.Event:
    event = db.get(models.Event, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="האירוע לא נמצא")
    if event.owner_id != user.id and not user.is_admin:
        # 404 ולא 403 — לא חושפים למי שאינו הבעלים שהאירוע קיים בכלל.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="האירוע לא נמצא")
    return event


def _to_read(member: models.EventMember, db: Session) -> schemas.EventMemberRead:
    u = db.get(models.User, member.user_id)
    return schemas.EventMemberRead(
        id=member.id,
        user_id=member.user_id,
        email=u.email if u else "",
        display_name=u.display_name if u else "",
        role=member.role,
        permissions=member.permissions or [],
        status=member.status,
    )


@router.get("", response_model=list[schemas.EventMemberRead])
def list_members(
    event_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """כל חברי-האירוע (מפיקים/אולמות) שיש להם גישה לאירוע הזה."""
    _require_owner(event_id, db, user)
    members = db.scalars(
        select(models.EventMember).where(models.EventMember.event_id == event_id)
    ).all()
    return [_to_read(m, db) for m in members]


@router.post("", response_model=schemas.EventMemberRead, status_code=201)
def add_member(
    event_id: int,
    payload: schemas.EventMemberCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """הוספת מפיק/אולם לאירוע, לפי אימייל מדויק (רק חשבונות מפיק/אולם קיימים)."""
    _require_owner(event_id, db, user)

    target = db.scalars(
        select(models.User).where(models.User.email == payload.email)
    ).first()
    if target is None or target.account_type not in ("planner", "venue"):
        # לא חושפים אם קיים משתמש כלשהו עם האימייל הזה — מונע חשיפת מידע.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="לא נמצא חשבון מפיק/אולם עם האימייל הזה",
        )

    existing = db.scalars(
        select(models.EventMember).where(
            models.EventMember.event_id == event_id,
            models.EventMember.user_id == target.id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="למשתמש הזה כבר יש גישה לאירוע",
        )

    allowed = set(_permissions_for_role(target.account_type))
    permissions = [p for p in payload.permissions if p in allowed]

    member = models.EventMember(
        event_id=event_id,
        user_id=target.id,
        role=target.account_type,
        permissions=permissions,
        invited_by_id=user.id,
        status="active",
    )
    db.add(member)
    db.commit()
    return _to_read(member, db)


@router.patch("/{member_id}", response_model=schemas.EventMemberRead)
def update_member(
    event_id: int,
    member_id: int,
    payload: schemas.EventMemberUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """עדכון רשימת ההרשאות של חבר-אירוע קיים."""
    _require_owner(event_id, db, user)
    member = db.get(models.EventMember, member_id)
    if member is None or member.event_id != event_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="חבר-האירוע לא נמצא")

    allowed = set(_permissions_for_role(member.role))
    member.permissions = [p for p in payload.permissions if p in allowed]
    db.commit()
    return _to_read(member, db)


@router.delete("/{member_id}", status_code=204)
def remove_member(
    event_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """הסרת גישה של מפיק/אולם לאירוע."""
    _require_owner(event_id, db, user)
    member = db.get(models.EventMember, member_id)
    if member is None or member.event_id != event_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="חבר-האירוע לא נמצא")
    db.delete(member)
    db.commit()
