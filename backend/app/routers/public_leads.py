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

## התראה לצוות

אחרי שהשורה נשמרה יוצא מייל קצר לכתובת הצוות (``VEYA_SUPPORT_EMAIL`` — אותה
כתובת של התראות פניות התמיכה), עם קישור למסך "פניות מדף הבית" בפאנל הניהול.
המייל נשלח ברקע: הגולש לא מחכה לו, ותקלה בו לא נוגעת בפנייה שכבר נשמרה.

``lead_limiter`` מגביל ל-5 פניות לשעה מאותו IP. זה נדיב למי שטעה והקליד
שוב, וצר מספיק כדי שהטופס לא יהפוך לצינור זבל. הולידציה זהה לזו של
המוצר: ``normalize_israeli_phone`` (אותה פונקציה שמנרמלת טלפון של מוזמן)
וסוגי האירוע מגיעים מ-``event_terms.EVENT_TERMS`` — לא מרשימה מקבילה.
"""
from __future__ import annotations

import html
from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app import emailer, help_support, models
from app.database import get_db
from app.event_terms import EVENT_TERMS
from app.guest_journey import today_in_israel
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


def notify_team(lead_id: int, name: str, phone: str, event_type: str, event_date: str) -> None:
    """מייל לצוות על פנייה חדשה מדף הבית. בלי כתובת צוות — לא שולח. לעולם לא זורק."""
    to = help_support.support_email()
    if not to:
        print(f"[veya:leads] פנייה #{lead_id} נשמרה — VEYA_SUPPORT_EMAIL לא מוגדר, לא נשלחה התראה", flush=True)
        return
    try:
        label = EVENT_TERMS[event_type].label if event_type in EVENT_TERMS else event_type
        days = (date.fromisoformat(event_date) - today_in_israel()).days if event_date else None
        link = f"{emailer.public_base_url()}/app#/admin/leads"
        lines = [
            f"שם: {name}",
            f"טלפון: {phone}",
            f"סוג האירוע: {label}",
            f"תאריך האירוע: {event_date}" + (f" (בעוד {days} ימים)" if isinstance(days, int) else ""),
        ]
        body_html = (
            "".join(f"<p style=\"margin:0 0 8px\">{html.escape(line)}</p>" for line in lines)
            + f"<p style=\"margin:16px 0 0\"><a href=\"{html.escape(link)}\">לכל הפניות במסך הניהול</a></p>"
        )
        text = "\n".join(lines) + f"\n\nלכל הפניות במסך הניהול: {link}"
        emailer.send_email(
            to=to, subject=f"פנייה חדשה מדף הבית: {name}", html_body=body_html, text_body=text,
        )
    except Exception as exc:  # noqa: BLE001 — הפנייה כבר נשמרה; כשל במייל רק נרשם
        print(f"[veya:leads] פנייה #{lead_id}: שליחת ההתראה נכשלה ({type(exc).__name__})", flush=True)


@router.post("/leads", response_model=LeadAck, status_code=201)
def create_lead(
    payload: LeadCreate, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)
) -> LeadAck:
    ip = client_ip(request)
    lead_limiter.check(ip)
    lead_limiter.record_fail(ip)

    lead = models.LandingLead(
        name=payload.name,
        phone=payload.phone,
        event_type=payload.event_type,
        event_date=payload.event_date,
        source="landing_page",
    )
    db.add(lead)
    db.commit()
    background.add_task(
        notify_team, lead.id, payload.name, payload.phone, payload.event_type, payload.event_date,
    )
    return LeadAck()
