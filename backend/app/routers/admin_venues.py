"""מאגר האולמות — CMS באדמין.

הנתיבים הוותיקים (``/admin/venues``) נשארים; כאן ``/admin/venue-cms`` עם כל
שדות המאגר המנוהל, תמונות, שכפול, סטטוס ומחיקה בטוחה.

סטטוס:
- ``active``  — מוצע לזוגות בהשלמה האוטומטית.
- ``hidden``  — קיים במאגר, לא מוצע.
- ``draft``   — בעבודה, לא מוצע.
אירועים שומרים את שם האולם אצלם (אין FK) — מחיקת אולם לא פוגעת באירוע.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import admin_audit, admin_rbac, cache, media, models, venues
from app.database import get_db

router = APIRouter(prefix="/admin/venue-cms", tags=["admin"])

EVENT_TYPES = ("wedding", "henna", "bar_mitzvah", "bat_mitzvah", "brit", "brita", "family", "business", "other")
KINDS = ("hall", "garden", "complex", "restaurant", "other")
STATUS_LABELS = {"active": "פעיל", "hidden": "מוסתר", "draft": "טיוטה"}
MAX_IMAGES = 20

FIELD_LABELS = {
    "name": "שם", "description": "תיאור", "city": "עיר", "address": "כתובת", "phone": "טלפון", "website": "אתר",
    "venue_kind": "סוג מקום", "event_types": "סוגי אירועים", "capacity_min": "קיבולת מינימלית",
    "capacity_max": "קיבולת מקסימלית", "capacity_by_type": "קיבולת לפי סוג אירוע", "kashrut": "כשרות",
    "parking": "חניה", "accessibility": "נגישות", "is_open": "פתוח", "contact_name": "איש קשר",
    "contact_phone": "טלפון איש קשר", "source": "מקור", "internal_notes": "הערות פנימיות",
    "partnership": "שיתוף פעולה", "verified": "מאומת", "priority": "עדיפות",
}


class VenueFields(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    description: Optional[str] = Field(default=None, max_length=2000)
    city: Optional[str] = Field(default=None, max_length=80)
    address: Optional[str] = Field(default=None, max_length=200)
    phone: Optional[str] = Field(default=None, max_length=30)
    website: Optional[str] = Field(default=None, max_length=300)
    venue_kind: Optional[Literal["", "hall", "garden", "complex", "restaurant", "other"]] = None
    event_types: Optional[list[str]] = None
    capacity_min: Optional[int] = Field(default=None, ge=0, le=10000)
    capacity_max: Optional[int] = Field(default=None, ge=0, le=10000)
    capacity_by_type: Optional[dict[str, int]] = None
    kashrut: Optional[str] = Field(default=None, max_length=120)
    parking: Optional[str] = Field(default=None, max_length=120)
    accessibility: Optional[str] = Field(default=None, max_length=120)
    is_open: Optional[bool] = None
    contact_name: Optional[str] = Field(default=None, max_length=100)
    contact_phone: Optional[str] = Field(default=None, max_length=30)
    source: Optional[str] = Field(default=None, max_length=60)
    internal_notes: Optional[str] = Field(default=None, max_length=4000)
    partnership: Optional[str] = Field(default=None, max_length=200)
    verified: Optional[bool] = None
    priority: Optional[int] = Field(default=None, ge=0, le=100)


def _nav(address: str, name: str) -> dict:
    from urllib.parse import quote

    q = quote(f"{name} {address}".strip())
    return {
        "waze": f"https://waze.com/ul?q={q}&navigate=yes" if (address or name) else "",
        "google": f"https://www.google.com/maps/search/?api=1&query={q}" if (address or name) else "",
    }


def _images(db: Session, venue_id: int) -> list[dict]:
    rows = db.scalars(
        select(models.VenueImage).where(models.VenueImage.venue_id == venue_id)
        .order_by(models.VenueImage.is_main.desc(), models.VenueImage.sort_order, models.VenueImage.id)
    ).all()
    return [{"id": r.id, "url": media.to_url(r.stored), "caption": r.caption, "is_main": r.is_main,
             "sort_order": r.sort_order} for r in rows]


def _row(v: models.Venue, main_image: Optional[str] = None) -> dict:
    return {
        "id": v.id, "name": v.name, "city": v.city or "", "address": v.address or "",
        "status": v.status or "active", "status_label": STATUS_LABELS.get(v.status or "active", v.status),
        "verified": bool(v.verified), "priority": v.priority or 0, "usage_count": v.usage_count or 0,
        "venue_kind": v.venue_kind or "", "event_types": v.event_types or [],
        "capacity_min": v.capacity_min, "capacity_max": v.capacity_max, "main_image": main_image,
        "source": v.source or "", "updated_at": v.updated_at, "created_at": v.created_at,
    }


def _detail(db: Session, v: models.Venue) -> dict:
    data = _row(v)
    data.update({
        field: getattr(v, field) for field in FIELD_LABELS
        if field not in data
    })
    data["event_types"] = v.event_types or []
    data["capacity_by_type"] = v.capacity_by_type or {}
    data["images"] = _images(db, v.id)
    data["main_image"] = next((i["url"] for i in data["images"] if i["is_main"]), data["images"][0]["url"] if data["images"] else None)
    data["navigation"] = _nav(v.address or "", v.name)
    return data


@router.get("")
def list_venues(
    q: str = Query("", max_length=100),
    status: str = Query("", pattern="^(|active|hidden|draft)$"),
    city: str = "",
    event_type: str = "",
    verified: str = Query("", pattern="^(|yes|no)$"),
    sort: str = Query("usage", pattern="^(usage|name|recent|priority)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("venues.view")),
):
    V = models.Venue
    filters = []
    if q.strip():
        like = f"%{q.strip()}%"
        filters.append(or_(V.name.ilike(like), V.city.ilike(like), V.address.ilike(like)))
    if status:
        filters.append(V.status == status)
    if city.strip():
        filters.append(V.city.ilike(f"%{city.strip()}%"))
    if verified == "yes":
        filters.append(V.verified.is_(True))
    elif verified == "no":
        filters.append(or_(V.verified.is_(False), V.verified.is_(None)))
    rows = db.scalars(select(V).where(*filters)).all() if event_type else None
    if event_type:
        matched = [v for v in rows if event_type in (v.event_types or [])]
        total = len(matched)
        ids = [v.id for v in matched]
        filters.append(V.id.in_(ids or [0]))
    else:
        total = db.scalar(select(func.count(V.id)).where(*filters)) or 0
    order = {
        "usage": (V.usage_count.desc(), V.name),
        "name": (V.name,),
        "recent": (V.id.desc(),),
        "priority": (V.priority.desc(), V.usage_count.desc()),
    }[sort]
    page = db.scalars(select(V).where(*filters).order_by(*order).limit(limit).offset(offset)).all()
    mains = {}
    for img in db.scalars(
        select(models.VenueImage).where(models.VenueImage.venue_id.in_([v.id for v in page] or [0]))
        .order_by(models.VenueImage.is_main.desc(), models.VenueImage.sort_order, models.VenueImage.id)
    ).all():
        mains.setdefault(img.venue_id, media.to_url(img.stored))
    counts = dict(db.execute(select(V.status, func.count(V.id)).group_by(V.status)).all())
    return {
        "total": total, "limit": limit, "offset": offset,
        "items": [_row(v, mains.get(v.id)) for v in page],
        "counts": {"active": counts.get("active", 0) + counts.get(None, 0), "hidden": counts.get("hidden", 0), "draft": counts.get("draft", 0)},
    }


@router.get("/{venue_id}")
def get_venue(venue_id: int, db: Session = Depends(get_db),
              admin: models.User = Depends(admin_rbac.require("venues.view"))):
    v = db.get(models.Venue, venue_id)
    if v is None:
        raise HTTPException(status_code=404, detail="האולם לא נמצא")
    data = _detail(db, v)
    data["events_using"] = db.scalar(
        select(func.count(models.Event.id)).where(func.lower(func.trim(models.Event.venue_name)) == v.dedup_key)
    ) or 0
    return data


def _apply(db: Session, v: models.Venue, payload: VenueFields) -> list[dict]:
    data = payload.model_dump(exclude_unset=True)
    if "event_types" in data and data["event_types"] is not None:
        bad = [t for t in data["event_types"] if t not in EVENT_TYPES]
        if bad:
            raise HTTPException(status_code=400, detail="סוג אירוע לא מוכר")
    if "capacity_by_type" in data and data["capacity_by_type"] is not None:
        if any(k not in EVENT_TYPES or not (0 <= int(n) <= 10000) for k, n in data["capacity_by_type"].items()):
            raise HTTPException(status_code=400, detail="קיבולת לפי סוג אירוע לא תקינה")
    cmin = data.get("capacity_min", v.capacity_min)
    cmax = data.get("capacity_max", v.capacity_max)
    if cmin is not None and cmax is not None and cmin > cmax:
        raise HTTPException(status_code=400, detail="קיבולת מינימלית גדולה מהמקסימלית")
    changes = []
    if "name" in data:
        new_name = (data["name"] or "").strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="שם האולם לא יכול להיות ריק")
        key = venues._dedup_key(new_name)
        clash = db.scalar(select(models.Venue).where(models.Venue.dedup_key == key, models.Venue.id != (v.id or 0)))
        if clash is not None:
            raise HTTPException(status_code=400, detail=f"כבר קיים אולם בשם הזה (#{clash.id})")
        v.dedup_key = key
        data["name"] = new_name
    for field, value in data.items():
        if isinstance(value, str):
            value = value.strip()
        before = getattr(v, field)
        if before == value:
            continue
        setattr(v, field, value)
        shown = (lambda x: ", ".join(x) if isinstance(x, list) else ("—" if x in (None, "") else x))
        changes.append(admin_audit.change(field, FIELD_LABELS.get(field, field), shown(before), shown(value)))
    v.updated_at = datetime.utcnow()
    return changes


@router.post("", status_code=201)
def create_venue(payload: VenueFields, request: Request, db: Session = Depends(get_db),
                 admin: models.User = Depends(admin_rbac.require("venues.edit"))):
    if not (payload.name or "").strip():
        raise HTTPException(status_code=400, detail="צריך שם לאולם")
    v = models.Venue(name="", dedup_key=f"__new__{datetime.utcnow().timestamp()}", usage_count=0,
                     status="draft", source="admin")
    _apply(db, v, payload)
    db.add(v)
    db.flush()
    admin_audit.record(db, admin, domain="venues", action="venue.create", summary=f"הוסיף/ה את האולם {v.name}",
                       target_type="venue", target_id=v.id, target_label=v.name, request=request)
    db.commit()
    cache.invalidate_prefix("venues:")
    return _detail(db, v)


@router.patch("/{venue_id}")
def update_venue(venue_id: int, payload: VenueFields, request: Request, db: Session = Depends(get_db),
                 admin: models.User = Depends(admin_rbac.require("venues.edit"))):
    v = db.get(models.Venue, venue_id)
    if v is None:
        raise HTTPException(status_code=404, detail="האולם לא נמצא")
    changes = _apply(db, v, payload)
    if changes:
        admin_audit.record(db, admin, domain="venues", action="venue.update", summary=f"ערך/ה את האולם {v.name}",
                           target_type="venue", target_id=v.id, target_label=v.name, changes=changes, request=request)
    db.commit()
    cache.invalidate_prefix("venues:")
    return _detail(db, v)


class StatusWrite(BaseModel):
    status: Literal["active", "hidden", "draft"]
    reason: str = Field(default="", max_length=500)


@router.post("/{venue_id}/status")
def set_status(venue_id: int, payload: StatusWrite, request: Request, db: Session = Depends(get_db),
               admin: models.User = Depends(admin_rbac.require("venues.edit"))):
    v = db.get(models.Venue, venue_id)
    if v is None:
        raise HTTPException(status_code=404, detail="האולם לא נמצא")
    before = v.status or "active"
    if before != payload.status:
        v.status, v.updated_at = payload.status, datetime.utcnow()
        admin_audit.record(
            db, admin, domain="venues", action="venue.status",
            summary=f"{'הסתיר/ה' if payload.status == 'hidden' else 'עדכן/ה סטטוס של'} האולם {v.name}",
            target_type="venue", target_id=v.id, target_label=v.name, reason=payload.reason, request=request,
            changes=[admin_audit.change("status", "סטטוס", STATUS_LABELS.get(before, before), STATUS_LABELS[payload.status])],
        )
        db.commit()
        cache.invalidate_prefix("venues:")
    return _detail(db, v)


@router.post("/{venue_id}/duplicate", status_code=201)
def duplicate_venue(venue_id: int, request: Request, db: Session = Depends(get_db),
                    admin: models.User = Depends(admin_rbac.require("venues.edit"))):
    src = db.get(models.Venue, venue_id)
    if src is None:
        raise HTTPException(status_code=404, detail="האולם לא נמצא")
    base, n = f"{src.name} (עותק)", 1
    name = base
    while db.scalar(select(models.Venue).where(models.Venue.dedup_key == venues._dedup_key(name))):
        n += 1
        name = f"{base} {n}"
    copy = models.Venue(name=name, dedup_key=venues._dedup_key(name), usage_count=0, status="draft", source="admin",
                        updated_at=datetime.utcnow())
    for field in FIELD_LABELS:
        if field not in ("name", "verified", "source", "priority"):
            setattr(copy, field, getattr(src, field))
    db.add(copy)
    db.flush()
    admin_audit.record(db, admin, domain="venues", action="venue.duplicate",
                       summary=f"שכפל/ה את האולם {src.name}", target_type="venue", target_id=copy.id,
                       target_label=copy.name, request=request)
    db.commit()
    return _detail(db, copy)


class DeleteWrite(BaseModel):
    confirm_name: str
    reason: str = Field(default="", max_length=500)


@router.post("/{venue_id}/delete")
def delete_venue(venue_id: int, payload: DeleteWrite, request: Request, db: Session = Depends(get_db),
                 admin: models.User = Depends(admin_rbac.require("venues.delete"))):
    """מחיקה בטוחה: חובה להקליד את שם האולם. אירועים לא מושפעים (שומרים שם משלהם)."""
    v = db.get(models.Venue, venue_id)
    if v is None:
        raise HTTPException(status_code=404, detail="האולם לא נמצא")
    if payload.confirm_name.strip() != v.name:
        raise HTTPException(status_code=400, detail="השם שהוקלד לא תואם לשם האולם")
    for img in db.scalars(select(models.VenueImage).where(models.VenueImage.venue_id == venue_id)).all():
        media.delete_stored(db, img.stored)
        db.delete(img)
    db.flush()  # התמונות לפני האולם — אין relationship שיסדר את הסדר לבד
    admin_audit.record(db, admin, domain="venues", action="venue.delete", summary=f"מחק/ה את האולם {v.name}",
                       target_type="venue", target_id=v.id, target_label=v.name, reason=payload.reason, request=request)
    db.delete(v)
    db.commit()
    cache.invalidate_prefix("venues:")
    return {"deleted": True}


class ImageWrite(BaseModel):
    data_url: str = Field(min_length=20)
    caption: str = Field(default="", max_length=200)


@router.post("/{venue_id}/images", status_code=201)
def add_image(venue_id: int, payload: ImageWrite, request: Request, db: Session = Depends(get_db),
              admin: models.User = Depends(admin_rbac.require("venues.edit"))):
    v = db.get(models.Venue, venue_id)
    if v is None:
        raise HTTPException(status_code=404, detail="האולם לא נמצא")
    if not payload.data_url.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="אפשר להעלות תמונה בלבד")
    count = db.scalar(select(func.count(models.VenueImage.id)).where(models.VenueImage.venue_id == venue_id)) or 0
    if count >= MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"עד {MAX_IMAGES} תמונות לאולם")
    stored = media._write_data_url(db, payload.data_url, "venue", optimize=True)
    db.add(models.VenueImage(venue_id=venue_id, stored=stored, caption=payload.caption.strip(),
                             sort_order=count, is_main=count == 0))
    v.updated_at = datetime.utcnow()
    admin_audit.record(db, admin, domain="venues", action="venue.image_add", summary=f"הוסיף/ה תמונה לאולם {v.name}",
                       target_type="venue", target_id=v.id, target_label=v.name, request=request)
    db.commit()
    return _detail(db, v)


class ImagesOrderWrite(BaseModel):
    order: list[int] = Field(min_length=1)
    main_id: Optional[int] = None


@router.put("/{venue_id}/images")
def reorder_images(venue_id: int, payload: ImagesOrderWrite, db: Session = Depends(get_db),
                   admin: models.User = Depends(admin_rbac.require("venues.edit"))):
    v = db.get(models.Venue, venue_id)
    if v is None:
        raise HTTPException(status_code=404, detail="האולם לא נמצא")
    imgs = {i.id: i for i in db.scalars(select(models.VenueImage).where(models.VenueImage.venue_id == venue_id)).all()}
    if set(payload.order) != set(imgs):
        raise HTTPException(status_code=400, detail="סדר התמונות לא תואם")
    main = payload.main_id if payload.main_id in imgs else None
    for pos, iid in enumerate(payload.order):
        imgs[iid].sort_order = pos
        if main is not None:
            imgs[iid].is_main = iid == main
    v.updated_at = datetime.utcnow()
    db.commit()
    return _detail(db, v)


@router.delete("/{venue_id}/images/{image_id}")
def delete_image(venue_id: int, image_id: int, request: Request, db: Session = Depends(get_db),
                 admin: models.User = Depends(admin_rbac.require("venues.edit"))):
    img = db.get(models.VenueImage, image_id)
    v = db.get(models.Venue, venue_id)
    if img is None or v is None or img.venue_id != venue_id:
        raise HTTPException(status_code=404, detail="התמונה לא נמצאה")
    was_main = img.is_main
    media.delete_stored(db, img.stored)
    db.delete(img)
    db.flush()
    if was_main:
        first = db.scalar(select(models.VenueImage).where(models.VenueImage.venue_id == venue_id)
                          .order_by(models.VenueImage.sort_order, models.VenueImage.id))
        if first is not None:
            first.is_main = True
    admin_audit.record(db, admin, domain="venues", action="venue.image_delete",
                       summary=f"מחק/ה תמונה מהאולם {v.name}", target_type="venue", target_id=v.id,
                       target_label=v.name, request=request)
    db.commit()
    return _detail(db, v)
