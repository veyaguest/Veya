"""עזרה בתוך VEYA — ה-context שהעזרה צריכה, ורק הוא (HELP_CENTER_PLAN.md שלב 3).

שלושה נתיבים, כולם **קריאה בלבד**:

- ``GET /help/context/{screen}`` — העובדות של מסך אחד (help_contexts.json).
- ``GET /help/guest-options?q=`` — בחירת מוזמן לבדיקה: מזהה + שם בלבד.
- ``GET /help/guest-check/{check}/{guest_id}`` — העובדות של בדיקה אחת על
  מוזמן אחד. בלי שם, בלי טלפון, בלי שאר שדות המוזמן.

מי רשאי: רק מי שמנהל את האירוע — בעלים או בן/בת זוג (החלטת המייסד
2026-09-29) — וגם רק כשהפיצ'ר ``help_center`` פתוח לאירוע. אחרת 404: בלי
הפיצ'ר העזרה פשוט לא קיימת, והתנהגות המערכת לא משתנה. טלפן נחסם כבר
ב-``EventAccess``. אדמין שנכנס עם הטוקן שלו לא עובר (הוא לא מנהל האירוע);
בכניסה לאירוע לתמיכה (התחזות) הוא משתמש בטוקן של בעל/ת האירוע.

שום דבר כאן לא נשמר ולא נשלח לשירות חיצוני. ה-context נבנה בכל בקשה ונזרק.
"""
from __future__ import annotations

from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import features, help_context, models, partners
from app.auth import get_current_user
from app.database import get_db
from app.deps import EventAccess

router = APIRouter(prefix="/help", tags=["help"])

_NOT_FOUND = HTTPException(status_code=404, detail="לא נמצא")

FactValue = Union[bool, int, str, None]


class HelpContextRead(BaseModel):
    screen: str
    #: ``None`` = לא ידוע בוודאות (העזרה אומרת "אי אפשר לבדוק", לא מנחשת).
    facts: dict[str, FactValue]


class HelpGuestCheckRead(BaseModel):
    check: str
    facts: dict[str, FactValue]


class HelpGuestOption(BaseModel):
    id: int
    name: str


def _help_event(
    response: Response,
    event: models.Event = Depends(EventAccess()),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.Event:
    """האירוע — רק למנהלי האירוע, ורק כשהעזרה פתוחה לו."""
    is_manager = event.owner_id == user.id or partners.partner_member(db, event.id, user.id) is not None
    if not is_manager or not features.enabled("help_center", event):
        raise _NOT_FOUND
    # לא לשמור בדרך (דפדפן/פרוקסי) — המצב משתנה, וחלק מהתשובות כוללות שמות.
    response.headers["Cache-Control"] = "no-store"
    return event


@router.get("/context/{screen}", response_model=HelpContextRead)
def get_context(
    screen: str,
    event: models.Event = Depends(_help_event),
    db: Session = Depends(get_db),
) -> HelpContextRead:
    if screen not in help_context.SCREENS:
        raise _NOT_FOUND
    return HelpContextRead(screen=screen, facts=help_context.screen_facts(db, event, screen))


@router.get("/guest-options", response_model=list[HelpGuestOption])
def get_guest_options(
    q: str = Query(..., min_length=2, max_length=60),
    event: models.Event = Depends(_help_event),
    db: Session = Depends(get_db),
) -> list[HelpGuestOption]:
    return [HelpGuestOption(**o) for o in help_context.guest_options(db, event, q)]


@router.get("/guest-check/{check}/{guest_id}", response_model=HelpGuestCheckRead)
def get_guest_check(
    check: str,
    guest_id: int,
    event: models.Event = Depends(_help_event),
    db: Session = Depends(get_db),
) -> HelpGuestCheckRead:
    if check not in help_context.GUEST_CHECKS:
        raise _NOT_FOUND
    guest: Optional[models.Guest] = db.get(models.Guest, guest_id)
    # מוזמן מאירוע אחר — כאילו אינו קיים.
    if guest is None or guest.event_id != event.id:
        raise _NOT_FOUND
    return HelpGuestCheckRead(
        check=check, facts=help_context.guest_check_facts(db, event, guest, check),
    )
