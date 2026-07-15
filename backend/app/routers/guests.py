"""נקודות API לניהול מוזמנים (CRUD)."""
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_event

router = APIRouter(prefix="/guests", tags=["guests"])

# תקרת גודל עמוד — מונעת שליפה ענקית אחת שתעמיס על השרת/דפדפן.
MAX_PAGE_LIMIT = 200
DEFAULT_PAGE_LIMIT = 50

# מספר מינימלי של מוזמנים באותו שם משפחה כדי להציע קבוצה.
MIN_CLUSTER = 3


def _surname(full_name: str) -> str:
    """שם המשפחה לצורך זיהוי מקבצים — המילה האחרונה בשם.

    ב'משפחת לוי' המילה השנייה היא שם המשפחה; אחרת המילה האחרונה.
    """
    parts = (full_name or "").strip().split()
    if not parts:
        return ""
    if parts[0].startswith("משפח"):
        return parts[1] if len(parts) > 1 else ""
    return parts[-1]


class GroupSuggestion(BaseModel):
    surname: str
    group_name: str  # "משפחת <שם>"
    count: int  # סך המוזמנים באותו שם משפחה
    guest_ids: list[int]  # מי שעוד לא בקבוצה הזו
    sample_names: list[str]


class BulkGroupRequest(BaseModel):
    guest_ids: list[int]
    group_type: str


class GroupInUse(BaseModel):
    group_type: str
    count: int


class GroupNotesResponse(BaseModel):
    notes: dict[str, str]
    groups: list[GroupInUse]


class GroupNoteUpdate(BaseModel):
    group_type: str
    note: str = ""


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


@router.get("/group-suggestions", response_model=list[GroupSuggestion])
def group_suggestions(
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """הצעות קבוצה חכמות: איתור מקבצי שם-משפחה זהה ברשימת המוזמנים.

    לכל שם משפחה שמופיע אצל ``MIN_CLUSTER`` מוזמנים ומעלה, מוצע לאחד אותם
    לקבוצה 'משפחת <שם>'. מוחזרים רק מוזמנים שעדיין לא בקבוצה המוצעת, וההצעה
    מדולגת אם כולם כבר משויכים אליה.
    """
    guests = db.scalars(
        select(models.Guest).where(models.Guest.event_id == event.id)
    ).all()

    clusters: dict[str, list[models.Guest]] = defaultdict(list)
    for g in guests:
        s = _surname(g.full_name)
        if len(s) >= 2:
            clusters[s].append(g)

    suggestions: list[GroupSuggestion] = []
    for surname, members in clusters.items():
        if len(members) < MIN_CLUSTER:
            continue
        group_name = f"משפחת {surname}"
        missing = [g for g in members if g.group_type != group_name]
        if not missing:
            continue  # כולם כבר בקבוצה — אין מה להציע
        suggestions.append(
            GroupSuggestion(
                surname=surname,
                group_name=group_name,
                count=len(members),
                guest_ids=[g.id for g in missing],
                sample_names=[g.full_name for g in members[:3]],
            )
        )

    # המקבצים הגדולים קודם — הכי משמעותיים לזוג.
    suggestions.sort(key=lambda s: s.count, reverse=True)
    return suggestions


@router.post("/bulk-group")
def bulk_group(
    payload: BulkGroupRequest,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """שיוך קבוצתי: מעדכן את ``group_type`` לרשימת מוזמנים בבת אחת."""
    group = payload.group_type.strip() or "other"
    ids = set(payload.guest_ids)
    if not ids:
        return {"updated": 0}
    rows = db.scalars(
        select(models.Guest)
        .where(models.Guest.event_id == event.id)
        .where(models.Guest.id.in_(ids))
    ).all()
    for g in rows:
        g.group_type = group
    db.commit()
    return {"updated": len(rows)}


@router.get("/group-notes", response_model=GroupNotesResponse)
def get_group_notes(
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """הערות/העדפות ברמת קבוצה + רשימת הקבוצות שבשימוש באירוע (עם ספירה)."""
    counts: dict[str, int] = defaultdict(int)
    for g in db.scalars(
        select(models.Guest).where(models.Guest.event_id == event.id)
    ).all():
        counts[g.group_type] += 1
    groups = [
        GroupInUse(group_type=gt, count=c)
        for gt, c in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return GroupNotesResponse(notes=dict(event.group_notes or {}), groups=groups)


@router.put("/group-notes", response_model=GroupNotesResponse)
def set_group_note(
    payload: GroupNoteUpdate,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """שמירת הערה לקבוצה אחת. הערה ריקה מוחקת את הרשומה."""
    notes = dict(event.group_notes or {})
    key = payload.group_type.strip()
    text_val = payload.note.strip()
    if not key:
        raise HTTPException(status_code=400, detail="קבוצה חסרה")
    if text_val:
        notes[key] = text_val
    else:
        notes.pop(key, None)
    event.group_notes = notes
    db.commit()

    counts: dict[str, int] = defaultdict(int)
    for g in db.scalars(
        select(models.Guest).where(models.Guest.event_id == event.id)
    ).all():
        counts[g.group_type] += 1
    groups = [
        GroupInUse(group_type=gt, count=c)
        for gt, c in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return GroupNotesResponse(notes=notes, groups=groups)


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
