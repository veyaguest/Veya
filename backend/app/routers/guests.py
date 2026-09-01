"""נקודות API לניהול מוזמנים (CRUD)."""
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app import audit, call_center, invitations, models, permissions, schemas
from app.auth import get_current_owner
from app.database import get_db
from app.deps import EventAccess

_view = EventAccess(permissions.GUESTS_VIEW)
_write = EventAccess(permissions.GUESTS_WRITE)

router = APIRouter(prefix="/guests", tags=["guests"])

# ניסוח שורת יומן הפעילות לפי הסטטוס החדש — נייטרלי, בלי הטיית מין
# (המערכת אינה שומרת מין מוזמן) ובלי "השתנה מ-X ל-Y".
_RSVP_ACTIVITY_PHRASE = {
    "confirmed": "אישור הגעה התקבל",
    "declined": "ביטול הגעה התקבל",
    "maybe": "עדכון הגעה: אולי",
    "pending": "עדכון הגעה: ממתין לתשובה",
}

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


# סדר הסטטוסים למיון "לפי סטטוס" — תואם לסדר שבו הם מוצגים באפשרויות הסינון.
_STATUS_SORT_RANK = case(
    (models.Guest.rsvp_status == "confirmed", 0),
    (models.Guest.rsvp_status == "declined", 1),
    (models.Guest.rsvp_status == "maybe", 2),
    (models.Guest.rsvp_status == "pending", 3),
    else_=4,
)


@router.get("", response_model=schemas.GuestListPage)
def list_guests(
    q: Optional[str] = None,
    sort: Optional[str] = None,
    filter_status: Optional[str] = None,
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_view),
):
    """עמוד מתוך רשימת המוזמנים של האירוע הפעיל.

    תומך בחיפוש חופשי (``q`` לפי שם/טלפון), בדפדוף (``limit``/``offset``),
    ובמיון/סינון תצוגתיים (``sort``/``filter_status``) — לא משנים שום נתון,
    רק את סדר/היקף התוצאות המוחזרות. הסכומים (total/total_people/
    confirmed_people) מחושבים על *כל* הרשומות התואמות (כולל הסינון) ולא רק
    על העמוד — כדי שסיכום המסך יישאר מדויק גם עם דפדוף.
    """
    limit = max(1, min(limit, MAX_PAGE_LIMIT))
    offset = max(0, offset)

    filters = [models.Guest.event_id == event.id]
    if q:
        like = f"%{q.strip()}%"
        filters.append(
            or_(models.Guest.full_name.ilike(like), models.Guest.phone.ilike(like))
        )
    if filter_status == "no_table":
        filters.append(models.Guest.table_number.is_(None))
    elif filter_status in ("confirmed", "declined", "maybe", "pending"):
        filters.append(models.Guest.rsvp_status == filter_status)

    if sort == "status":
        order_by = (_STATUS_SORT_RANK, models.Guest.full_name.asc())
    elif sort == "table":
        order_by = (
            models.Guest.table_number.is_(None),
            models.Guest.table_number.asc(),
            models.Guest.full_name.asc(),
        )
    elif sort == "party_size":
        order_by = (models.Guest.party_size.desc(), models.Guest.full_name.asc())
    elif sort == "recent":
        order_by = (models.Guest.created_at.desc(),)
    else:
        order_by = (models.Guest.full_name.asc(),)

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
        .order_by(*order_by)
        .limit(limit)
        .offset(offset)
    ).all()

    # סטטוס נגזר לכל מוזמן בעמוד (שאילתה אחת ל"מי כבר קיבל הזמנה").
    invited = invitations.invited_guest_ids(db, event.id, event)
    for g in items:
        g.invite_status = invitations.derive_invite_status(
            g.rsvp_status, g.id in invited
        )

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
    event: models.Event = Depends(_write),
):
    guest = models.Guest(event_id=event.id, **payload.model_dump())
    db.add(guest)
    db.commit()
    return guest


@router.get("/data-alerts", response_model=schemas.GuestDataAlerts)
def data_alerts(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_view),
):
    """התראות איכות-דאטה על מוזמני האירוע — כרגע "נדרש תיקון מספר טלפון".

    נוצרות כשצוות VEYA מסמן "מספר שגוי" בשיחת טלפון (Call Center). זו התראה
    על **פרטי הקשר בלבד** — סטטוס אישור ההגעה של המוזמן לא השתנה, והוא לא
    סומן "לא מגיע". ההתראה נסגרת מעצמה ברגע שמספר הטלפון מתעדכן.
    """
    alerts = call_center.phone_fix_alerts(db, event.id)
    rows = [
        schemas.GuestDataAlert(
            guest_id=a.guest.id,
            full_name=a.guest.full_name,
            phone=a.guest.phone or "",
            rsvp_status=a.guest.rsvp_status,
            attempts=a.attempts,
            reported_at=a.reported_at,
        )
        for a in alerts
    ]
    return schemas.GuestDataAlerts(phone_fix=rows, total=len(rows))


@router.get("/group-suggestions", response_model=list[GroupSuggestion])
def group_suggestions(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_view),
):
    """הצעות קבוצה חכמות: איתור מקבצי שם-משפחה זהה ברשימת המוזמנים.

    לכל שם משפחה שמופיע אצל ``MIN_CLUSTER`` מוזמנים ומעלה, מוצע לאחד אותם
    לקבוצה. מוחזרים רק מוזמנים שעדיין לא בקבוצה המוצעת, וההצעה מדולגת אם
    כולם כבר משויכים אליה. שם הקבוצה המוצע תלוי-סוג-אירוע: "משפחת X" לחתונה/
    בר-בת-מצווה/חינה/ברית/משפחתי (איחוד סביר של שם משפחה זהה), "קבוצת X"
    לעסקי/אחר — כי עמיתים בעלי שם משפחה זהה הם צירוף מקרים, לא בהכרח משפחה.
    """
    guests = db.scalars(
        select(models.Guest).where(models.Guest.event_id == event.id)
    ).all()

    clusters: dict[str, list[models.Guest]] = defaultdict(list)
    for g in guests:
        s = _surname(g.full_name)
        if len(s) >= 2:
            clusters[s].append(g)

    is_business_like = event.event_type in ("business", "other")
    suggestions: list[GroupSuggestion] = []
    for surname, members in clusters.items():
        if len(members) < MIN_CLUSTER:
            continue
        group_name = f"{'קבוצת' if is_business_like else 'משפחת'} {surname}"
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
    event: models.Event = Depends(_write),
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
    event: models.Event = Depends(_view),
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
    event: models.Event = Depends(_write),
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
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_write),
    user: models.User = Depends(get_current_owner),
):
    guest = db.get(models.Guest, guest_id)
    if guest is None or guest.event_id != event.id:
        raise HTTPException(status_code=404, detail="מוזמן לא נמצא")
    changed = payload.model_dump(exclude_unset=True)
    prev_rsvp_status = guest.rsvp_status
    prev_party_size = guest.party_size
    for key, value in changed.items():
        setattr(guest, key, value)

    # יומן פעילות: עריכה ידנית של אישור הגעה (ניהול מוזמנים → עריכת מוזמן)
    # נרשמת באותו מנגנון יומן פעילות ובאותה עוגן (event_id) כמו שינוי שמגיע
    # ממנגנון אישורי ההגעה עצמו (routers/confirm.py) — כדי שתופיע יחד איתם
    # ב"עדכוני אישורי הגעה" בתמונת המצב. נכתבת רק כשהסטטוס באמת השתנה, כדי
    # שלא ייווצר אירוע כפול על שינוי לא-שינוי (למשל עריכה שלא נגעה בסטטוס).
    # יומן פעילות: שינוי כמות המוזמנים ("אביב שינה את כמות המוזמנים של
    # משפחת כהן מ-2 ל-4"). זו אחת הפעולות שהכי חשוב לדעת מי עשה, כי היא
    # משפיעה ישירות על המספר שנמסר לאולם — ובניהול משותף שני הצדדים
    # משנים אותה.
    if "party_size" in changed and guest.party_size != prev_party_size:
        audit.record(
            db, "guest_party_size_update",
            event_id=event.id, user_id=user.id,
            detail=f"עודכנה כמות המוזמנים — {guest.full_name} ({guest.party_size})",
            ip=request.client.host if request.client else None,
        )

    if "rsvp_status" in changed and guest.rsvp_status != prev_rsvp_status:
        phrase = _RSVP_ACTIVITY_PHRASE.get(guest.rsvp_status, "עדכון אישור הגעה")
        if guest.rsvp_status == "confirmed" and guest.confirmed_count:
            phrase += f" ({guest.confirmed_count})"
        audit.record(
            db, "guest_rsvp_manual_update",
            event_id=event.id, user_id=user.id,
            detail=f"{guest.full_name} — {phrase}",
            ip=request.client.host if request.client else None,
        )

    db.commit()
    return guest


@router.delete("/{guest_id}", status_code=204)
def delete_guest(
    guest_id: int,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_write),
):
    guest = db.get(models.Guest, guest_id)
    if guest is None or guest.event_id != event.id:
        raise HTTPException(status_code=404, detail="מוזמן לא נמצא")
    # יומן השיחות מצביע על המוזמן ואין לו ON DELETE CASCADE — בלי הניקוי הזה
    # מחיקת מוזמן שכבר התקשרו אליו הייתה נכשלת ב-foreign key.
    for call in db.scalars(
        select(models.CallLog).where(models.CallLog.guest_id == guest_id)
    ).all():
        db.delete(call)
    db.delete(guest)
    db.commit()
