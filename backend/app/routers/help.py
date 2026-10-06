"""עזרה בתוך VEYA — ה-context שהעזרה צריכה, ורק הוא (HELP_CENTER_PLAN.md שלב 3).

שלושה נתיבים של **קריאה בלבד**:

- ``GET /help/context/{screen}`` — העובדות של מסך אחד (help_contexts.json).
- ``GET /help/guest-options?q=`` — בחירת מוזמן לבדיקה: מזהה + שם בלבד.
- ``GET /help/guest-check/{check}/{guest_id}`` — העובדות של בדיקה אחת על
  מוזמן אחד. בלי שם, בלי טלפון, בלי שאר שדות המוזמן.

מי רשאי: רק מי שמנהל את האירוע — בעלים או בן/בת זוג (החלטת המייסד
2026-09-29) — וגם רק כשהפיצ'ר ``help_center`` פתוח לאירוע. אחרת 404: בלי
הפיצ'ר העזרה פשוט לא קיימת, והתנהגות המערכת לא משתנה. טלפן נחסם כבר
ב-``EventAccess``. אדמין שנכנס עם הטוקן שלו לא עובר (הוא לא מנהל האירוע);
בכניסה לאירוע לתמיכה (התחזות) הוא משתמש בטוקן של בעל/ת האירוע.

שום דבר מהם לא נשמר ולא נשלח לשירות חיצוני. ה-context נבנה בכל בקשה ונזרק.

ושני נתיבים של פנייה לצוות (שלב 7, ``help_support.py``):

- ``POST /help/requests`` — המשתמש לוחץ בעצמו "שליחה לצוות". הודעה עד 1000
  תווים + תמונת מצב בפורמט קבוע. 5 בשעה למשתמש. **חסום בכניסה לתמיכה**
  (צוות לא פונה לצוות בשם הלקוח). אחרי השמירה — מייל אישור לפונה, ברקע.
- ``GET /help/requests/mine`` — הפניות שלי באירוע הזה והסטטוס שלהן.

ונתיב אחד של מדידת שימוש (שלב 8, ``help_analytics.py``):

- ``POST /help/events`` — עד 50 אירועים מאוצר מילים סגור, **בלי זהות ובלי
  טקסט חופשי**. בכניסה לתמיכה לא נשמר כלום (לא סופרים צוות כמשתמש).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional, Union

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import features, help_analytics, help_context, help_support, models, partners
from app.auth import get_current_user, token_impersonator_id
from app.database import get_db
from app.deps import EventAccess
from app.ratelimit import RateLimiter

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


# ─── פנייה לצוות VEYA (שלב 7) ──────────────────────────────────────────────

support_limiter = RateLimiter(
    max_hits=5, window=3600, message="נשלחו כמה פניות בשעה האחרונה. אפשר לשלוח שוב בעוד קצת.",
)

#: מזהי נושא/בדיקה/תוצאה/הדרכה מבסיס הידע — אותיות קטנות, ספרות, נקודה ומקף.
_KB_ID = r"^[a-z0-9][a-z0-9.\-]{0,59}$"


class SupportErrorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", ""]
    #: תבנית נתיב (בלי מזהים) — כמו ב-errorBus.ts::pathTemplate.
    path: str = Field(pattern=r"^(/[a-z0-9/{}_\-.]{0,80}|ui:crash)$")
    status: int = Field(ge=-1, le=599)
    message: Optional[str] = Field(default=None, max_length=300)


class SupportRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=1000)
    screen: Optional[str] = None
    topic_id: Optional[str] = Field(default=None, pattern=_KB_ID)
    tree_id: Optional[str] = Field(default=None, pattern=_KB_ID)
    outcome: Optional[str] = Field(default=None, pattern=_KB_ID)
    tour_flow: Optional[str] = Field(default=None, pattern=_KB_ID)
    recent_errors: list[SupportErrorIn] = Field(default_factory=list, max_length=5)
    platform: Literal["desktop", "mobile"]

    @field_validator("message")
    @classmethod
    def _message(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("כתבו בכמה מילים במה אפשר לעזור")
        return v

    @field_validator("screen")
    @classmethod
    def _screen(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in help_context.SCREENS:
            raise ValueError("מסך לא מוכר")
        return v


class SupportRequestRead(BaseModel):
    id: int
    status: str
    created_at: Optional[datetime]


@router.post("/requests", response_model=SupportRequestRead, status_code=201)
def create_support_request(
    payload: SupportRequestCreate,
    background: BackgroundTasks,
    event: models.Event = Depends(_help_event),
    user: models.User = Depends(get_current_user),
    impersonator: Optional[int] = Depends(token_impersonator_id),
    db: Session = Depends(get_db),
) -> SupportRequestRead:
    if impersonator is not None:
        raise HTTPException(status_code=403, detail="בכניסה לתמיכה אי אפשר לשלוח פנייה בשם בעלי האירוע")
    key = f"user:{user.id}"
    support_limiter.check(key)
    ctx = help_support.build_context(
        db, event, user,
        screen=payload.screen, topic_id=payload.topic_id, tree_id=payload.tree_id,
        outcome=payload.outcome, tour_flow=payload.tour_flow,
        recent_errors=[e.model_dump() for e in payload.recent_errors],
        platform=payload.platform,
    )
    row = models.SupportRequest(
        user_id=user.id, event_id=event.id, status="new",
        urgency=help_support.urgency_for(event),
        topic_id=payload.topic_id or "", tree_id=payload.tree_id or "",
        message=payload.message, contact_channel="email", context=ctx,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    support_limiter.record_fail(key)
    help_support.notify_team(row)
    # מייל אישור לפונה — ברקע, אחרי שהפנייה נשמרה: לא מעכב את התשובה, וכשל
    # בו לא נוגע בפנייה (help_support.send_confirmation).
    background.add_task(help_support.send_confirmation, row.id)
    return SupportRequestRead(id=row.id, status=row.status, created_at=row.created_at)


@router.get("/requests/mine", response_model=list[SupportRequestRead])
def my_support_requests(
    event: models.Event = Depends(_help_event),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SupportRequestRead]:
    rows = db.scalars(
        select(models.SupportRequest)
        .where(models.SupportRequest.user_id == user.id, models.SupportRequest.event_id == event.id)
        .order_by(models.SupportRequest.id.desc())
        .limit(20)
    ).all()
    return [SupportRequestRead(id=r.id, status=r.status, created_at=r.created_at) for r in rows]


# ─── מדידת שימוש בעזרה (שלב 8) ──────────────────────────────────────────────

events_limiter = RateLimiter(
    max_hits=30, window=60, message="יותר מדי בקשות. אפשר לנסות שוב בעוד רגע.",
)


class HelpEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=40)
    screen: str = Field(max_length=20)
    props: dict = Field(default_factory=dict)


class HelpEventsBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    platform: Literal["desktop", "mobile"]
    kb_version: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    events: list[HelpEventIn] = Field(min_length=1, max_length=50)


@router.post("/events", status_code=204)
def post_help_events(
    payload: HelpEventsBatch,
    event: models.Event = Depends(_help_event),
    user: models.User = Depends(get_current_user),
    impersonator: Optional[int] = Depends(token_impersonator_id),
    db: Session = Depends(get_db),
) -> Response:
    # צוות בכניסה לתמיכה — לא נספר כמשתמש. מחזירים 204 בשקט (בלי לשמור).
    if impersonator is not None:
        return Response(status_code=204)
    key = f"user:{user.id}"
    events_limiter.check(key)
    events_limiter.record_fail(key)
    for e in payload.events:
        if e.screen not in help_analytics.SCREENS:
            raise HTTPException(status_code=422, detail="מסך לא מוכר")
        problem = help_analytics.validate_event(e.name, e.props)
        if problem:
            raise HTTPException(status_code=422, detail=problem)
    role = "owner" if event.owner_id == user.id else "partner"
    for e in payload.events:
        db.add(models.HelpEvent(
            session_id=help_analytics.session_key(payload.session_id), name=e.name, props=e.props or None,
            screen=e.screen, event_type=event.event_type, role=role,
            platform=payload.platform, kb_version=payload.kb_version,
        ))
    db.commit()
    return Response(status_code=204)
