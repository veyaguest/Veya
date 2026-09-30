"""פניות תמיכה — מסך הצוות (HELP_CENTER_PLAN.md §10.4, שלב 7).

- ``GET  /admin/support/requests``            — רשימה (סינון לפי סטטוס).
- ``GET  /admin/support/requests/{id}``       — פנייה אחת, עם תמונת המצב.
- ``POST /admin/support/requests/{id}/status`` — new / in_progress / resolved.

הרשאות: ``support.view`` לקריאה, ``support.handle`` לשינוי סטטוס (דרגת Support
ומעלה). כל שינוי סטטוס נרשם ביומן האדמין. אין כאן שליחת הודעות ללקוח: הצוות
עונה במייל של החשבון, מחוץ למערכת (החלטת המייסד — ערוץ מייל בלבד).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import admin_audit, admin_rbac, help_support, models, partners
from app.database import get_db

router = APIRouter(prefix="/admin/support", tags=["admin"])


class SupportPerson(BaseModel):
    id: int
    name: str
    email: str


class SupportEventInfo(BaseModel):
    id: int
    title: str
    event_date: Optional[str]
    days_to_event: Optional[int]
    owner_id: Optional[int]


class SupportRequestRow(BaseModel):
    id: int
    status: str
    urgency: str
    about: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    user: Optional[SupportPerson]
    event: Optional[SupportEventInfo]


class SupportRequestDetail(SupportRequestRow):
    message: str
    context: dict
    handled_by: Optional[SupportPerson]


class SupportStatusUpdate(BaseModel):
    status: Literal["new", "in_progress", "resolved"]


def _person(user: Optional[models.User]) -> Optional[SupportPerson]:
    if user is None:
        return None
    return SupportPerson(id=user.id, name=user.display_name or "", email=user.email or "")


def _event_info(event: Optional[models.Event]) -> Optional[SupportEventInfo]:
    if event is None:
        return None
    return SupportEventInfo(
        id=event.id, title=partners.event_title(event), event_date=event.event_date,
        days_to_event=help_support.days_to_event(event), owner_id=event.owner_id,
    )


def _row(db: Session, r: models.SupportRequest) -> dict:
    return dict(
        id=r.id, status=r.status, urgency=r.urgency,
        about=r.tree_id or r.topic_id or "",
        created_at=r.created_at, updated_at=r.updated_at,
        user=_person(db.get(models.User, r.user_id)),
        event=_event_info(db.get(models.Event, r.event_id) if r.event_id else None),
    )


@router.get("/requests", response_model=list[SupportRequestRow])
def list_requests(
    status: Literal["new", "in_progress", "resolved", "open", "all"] = Query(default="open"),
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("support.view")),
) -> list[SupportRequestRow]:
    q = select(models.SupportRequest)
    if status == "open":
        q = q.where(models.SupportRequest.status.in_(("new", "in_progress")))
    elif status != "all":
        q = q.where(models.SupportRequest.status == status)
    rows = db.scalars(q.order_by(models.SupportRequest.id.desc()).limit(200)).all()
    # דחופות קודם, ובתוך כל קבוצה — החדשה ראשונה.
    rows = sorted(rows, key=lambda r: (r.urgency != "high", -r.id))
    return [SupportRequestRow(**_row(db, r)) for r in rows]


def _get(db: Session, request_id: int) -> models.SupportRequest:
    r = db.get(models.SupportRequest, request_id)
    if r is None:
        raise HTTPException(status_code=404, detail="הפנייה לא נמצאה")
    return r


@router.get("/requests/{request_id}", response_model=SupportRequestDetail)
def get_request(
    request_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("support.view")),
) -> SupportRequestDetail:
    r = _get(db, request_id)
    return SupportRequestDetail(
        **_row(db, r), message=r.message, context=r.context or {},
        handled_by=_person(db.get(models.User, r.handled_by_id) if r.handled_by_id else None),
    )


@router.post("/requests/{request_id}/status", response_model=SupportRequestDetail)
def set_status(
    request_id: int,
    payload: SupportStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("support.handle")),
) -> SupportRequestDetail:
    r = _get(db, request_id)
    before = r.status
    if before != payload.status:
        r.status = payload.status
        r.handled_by_id = admin.id
        r.updated_at = datetime.utcnow()
        admin_audit.record(
            db, admin, domain="support", action="support.status",
            summary=f"פנייה #{r.id}: {help_support.STATUS_LABELS[before]} ← {help_support.STATUS_LABELS[payload.status]}",
            target_type="support_request", target_id=r.id, target_label=f"פנייה #{r.id}",
            changes=[admin_audit.change(
                "status", "סטטוס",
                help_support.STATUS_LABELS[before], help_support.STATUS_LABELS[payload.status],
            )],
            event_id=r.event_id, request=request,
        )
        db.commit()
        db.refresh(r)
    return get_request(request_id, db, admin)
