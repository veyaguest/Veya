"""פניות מדף הבית — מסך הצוות (2026-10-29).

- ``GET /admin/leads`` — הפניות מטופס "רוצים שנדבר קודם?", מהחדשה לישנה.
- ``POST /admin/leads/{id}/contacted`` — סימון "חזרנו" (או ביטול הסימון).

הדבר היחיד שאפשר לשנות בפנייה הוא הסימון הזה: לפי RLS רק אדמין קורא ומעדכן,
והעדכון פתוח רק לשתי עמודות הסימון (``rls/18_landing_leads_rls.sql``). אין
מחיקה. הרשאות: ``leads.view`` לצפייה, ``leads.handle`` לסימון (שתיהן דרגת
Support, כמו פניות התמיכה). כל סימון נרשם ביומן הפעולות של הצוות.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import admin_audit, admin_rbac, models
from app.database import get_db
from app.event_terms import EVENT_TERMS
from app.guest_journey import today_in_israel

router = APIRouter(prefix="/admin/leads", tags=["admin"])


class LeadRow(BaseModel):
    id: int
    name: str
    phone: str
    event_type: str
    #: שם הסוג בעברית ("בר מצווה") — מאותו מקור של שאר המערכת
    event_type_label: str
    event_date: str
    #: ימים עד האירוע (שלילי = כבר עבר); ``None`` כשאין תאריך תקין
    days_to_event: Optional[int]
    created_at: Optional[datetime]
    #: מתי הצוות סימן "חזרנו"; ``None`` = ממתינה
    contacted_at: Optional[datetime] = None
    #: שם איש הצוות שסימן (ריק אם המשתמש כבר לא קיים)
    contacted_by_name: str = ""


class ContactedUpdate(BaseModel):
    contacted: bool


def _days(event_date: str) -> Optional[int]:
    try:
        return (date.fromisoformat(event_date) - today_in_israel()).days
    except (TypeError, ValueError):
        return None


@router.get("", response_model=list[LeadRow])
def list_leads(
    limit: int = Query(default=300, ge=1, le=1000),
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("leads.view")),
) -> list[LeadRow]:
    L = models.LandingLead
    rows = db.scalars(select(L).order_by(L.created_at.desc(), L.id.desc()).limit(limit)).all()
    staff_ids = {r.contacted_by_id for r in rows if r.contacted_by_id}
    names = {
        u.id: u.display_name or u.email or ""
        for u in db.scalars(select(models.User).where(models.User.id.in_(staff_ids)))
    } if staff_ids else {}
    return [_row(r, names) for r in rows]


@router.post("/{lead_id}/contacted", response_model=LeadRow)
def set_contacted(
    lead_id: int,
    payload: ContactedUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("leads.handle")),
) -> LeadRow:
    lead = db.get(models.LandingLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="הפנייה לא נמצאה")
    was = lead.contacted_at is not None
    if was != payload.contacted:
        lead.contacted_at = datetime.utcnow() if payload.contacted else None
        lead.contacted_by_id = admin.id if payload.contacted else None
        admin_audit.record(
            db, admin, domain="leads", action="leads.contacted",
            summary=f"פנייה מדף הבית #{lead.id}: {'חזרנו' if payload.contacted else 'בוטל הסימון חזרנו'}",
            target_type="landing_lead", target_id=lead.id, target_label=lead.name,
            changes=[admin_audit.change(
                "contacted", "חזרנו", "כן" if was else "לא", "כן" if payload.contacted else "לא",
            )],
            request=request,
        )
        db.commit()
        db.refresh(lead)
    names = {admin.id: admin.display_name or admin.email or ""}
    return _row(lead, names)


def _row(r: models.LandingLead, names: dict[int, str]) -> LeadRow:
    return LeadRow(
        id=r.id, name=r.name, phone=r.phone, event_type=r.event_type,
        event_type_label=EVENT_TERMS[r.event_type].label if r.event_type in EVENT_TERMS else r.event_type,
        event_date=r.event_date or "", days_to_event=_days(r.event_date or ""),
        created_at=r.created_at,
        contacted_at=r.contacted_at,
        contacted_by_name=names.get(r.contacted_by_id, "") if r.contacted_by_id else "",
    )
