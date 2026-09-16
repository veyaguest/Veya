"""פניות מדף הנחיתה — "השאירו פרטים ונחזור אליכם".

## למה נתיב ציבורי נפרד

זו הפנייה היחידה במערכת שמגיעה ממי שעדיין **אינו משתמש**: אין טוקן, אין
אירוע ואין הרשמה. לכן היא לא יכולה לחיות באף router קיים — כולם מניחים
``EventAccess`` או משתמש מחובר — והיא גם לא צריכה כלום מהם.

## מה נשמר

שם, טלפון (מנורמל), סוג אירוע ותאריך. שום שדה מעבר לזה, ראו
``models.LandingLead``. אין כאן חיפוש, אין עדכון ואין מחיקה: הנתיב יודע
רק להוסיף שורה. קריאה נעשית דרך ה-DB (ולפי RLS — אדמין בלבד).

## הגנות

``lead_limiter`` מגביל ל-5 פניות לשעה מאותו IP. זה נדיב למי שטעה והקליד
שוב, וצר מספיק כדי שהטופס לא יהפוך לצינור זבל. הולידציה זהה לזו של
המוצר: ``normalize_israeli_phone`` (אותה פונקציה שמנרמלת טלפון של מוזמן)
וסוגי האירוע מגיעים מ-``event_terms.EVENT_TERMS`` — לא מרשימה מקבילה.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.event_terms import EVENT_TERMS
from app.ratelimit import RateLimiter, client_ip
from app.validators import normalize_israeli_phone

router = APIRouter(prefix="/public", tags=["public-leads"])

lead_limiter = RateLimiter(
    max_hits=5,
    window=60 * 60,
    message="נשלחו כמה פניות מהכתובת הזו. נסו שוב בעוד שעה, או כתבו לנו במייל.",
)

#: חלון תאריכים סביר לאירוע: מהיום ועד שלוש שנים קדימה. תאריך מחוץ לטווח
#: הוא כמעט תמיד טעות הקלדה, ועדיף להגיד את זה מאשר לשמור שורה שגויה.
_MAX_AHEAD = timedelta(days=365 * 3)


class LeadCreate(BaseModel):
    name: str
    phone: str
    event_type: str = "wedding"
    event_date: str = ""

    @field_validator("name")
    @classmethod
    def _name_required(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 2:
            raise ValueError("נשמח לדעת איך קוראים לכם")
        return v[:80]

    @field_validator("phone")
    @classmethod
    def _phone_valid(cls, v: str) -> str:
        try:
            return normalize_israeli_phone(v)
        except ValueError:
            raise ValueError("נראה שהמספר לא תקין — בואו נבדוק שוב")

    @field_validator("event_type")
    @classmethod
    def _type_known(cls, v: str) -> str:
        v = (v or "").strip()
        if v not in EVENT_TERMS:
            raise ValueError("בחרו סוג אירוע מהרשימה")
        return v

    @field_validator("event_date")
    @classmethod
    def _date_sane(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("בחרו את תאריך האירוע")
        try:
            parsed = date.fromisoformat(v)
        except ValueError:
            raise ValueError("בחרו את תאריך האירוע")
        today = date.today()
        if parsed < today or parsed > today + _MAX_AHEAD:
            raise ValueError("בחרו תאריך מהיום והלאה")
        return parsed.isoformat()


class LeadAck(BaseModel):
    """תשובה בלי תוכן: הלקוח לא צריך את הפרטים שהוא בדיוק שלח."""

    ok: bool = True


@router.post("/leads", response_model=LeadAck, status_code=201)
def create_lead(
    payload: LeadCreate, request: Request, db: Session = Depends(get_db)
) -> LeadAck:
    ip = client_ip(request)
    lead_limiter.check(ip)
    lead_limiter.record_fail(ip)

    db.add(
        models.LandingLead(
            name=payload.name,
            phone=payload.phone,
            event_type=payload.event_type,
            event_date=payload.event_date,
            source="landing_page",
        )
    )
    db.commit()
    return LeadAck()
