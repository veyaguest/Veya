"""פניות מדף הבית — מסך הצוות (2026-10-29).

- ``GET /admin/leads`` — הפניות מטופס "רוצים שנדבר קודם?", מהחדשה לישנה.

זה מסך קריאה בלבד: הטבלה ``landing_leads`` יודעת רק להוסיף שורות (ראו
``routers/public_leads.py``), ולפי RLS רק אדמין קורא אותה. אין כאן עדכון
ואין מחיקה. הרשאה: ``leads.view`` (דרגת Support, כמו פניות התמיכה).
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import admin_rbac, models
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
    return [
        LeadRow(
            id=r.id, name=r.name, phone=r.phone, event_type=r.event_type,
            event_type_label=EVENT_TERMS[r.event_type].label if r.event_type in EVENT_TERMS else r.event_type,
            event_date=r.event_date or "", days_to_event=_days(r.event_date or ""),
            created_at=r.created_at,
        )
        for r in rows
    ]
