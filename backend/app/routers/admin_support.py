"""פניות תמיכה — מסך הצוות (HELP_CENTER_PLAN.md §10.4, שלב 7).

- ``GET  /admin/support/requests``            — רשימה (סינון לפי סטטוס).
- ``GET  /admin/support/requests/{id}``       — פנייה אחת, עם תמונת המצב.
- ``POST /admin/support/requests/{id}/status`` — new / in_progress / resolved.
- ``POST /admin/support/requests/{id}/replies`` — "השב לפונה": מייל לפונה
  (2026-10-07). הנמען — כתובת החשבון שפתח את הפנייה, מה-DB בלבד. התשובה
  נשמרת (``SupportReply``) **ולא משנה את הסטטוס**: "נענתה" ו"טופלה" נפרדים,
  ורק "סימון טופלה" (``/status``) משנה סטטוס.

הרשאות: ``support.view`` לקריאה, ``support.handle`` לשינוי סטטוס ולמענה (שתיהן
דרגת Support ומעלה — אותם אנשים). כל שינוי סטטוס וכל תשובה שנשלחה נרשמים
ביומן האדמין (בלי תוכן התשובה).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import admin_audit, admin_rbac, emailer, help_analytics, help_support, models, partners
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


class SupportReplyRead(BaseModel):
    id: int
    #: sent = יצא באמת · mock = נשמר אבל אין חיבור למייל בסביבה · failed · sending
    status: str
    body: str
    created_at: Optional[datetime]
    sent_at: Optional[datetime]
    admin: Optional[SupportPerson]


class SupportRequestDetail(SupportRequestRow):
    message: str
    context: dict
    handled_by: Optional[SupportPerson]
    replies: list[SupportReplyRead] = []


class SupportReplyCreate(BaseModel):
    """רק הטקסט ומזהה החלון. **אין** שדה נמען — שדה נוסף נדחה (422)."""

    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=emailer.REPLY_MAX_CHARS)
    #: נוצר בדפדפן בכל פתיחה של חלון המענה; אותו מזהה = אותה תשובה.
    client_token: str = Field(pattern=r"^[A-Za-z0-9-]{16,64}$")


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
        replies=_replies(db, r.id),
    )


def _replies(db: Session, request_id: int) -> list[SupportReplyRead]:
    rows = db.scalars(
        select(models.SupportReply).where(models.SupportReply.request_id == request_id)
        .order_by(models.SupportReply.id)
    ).all()
    return [
        SupportReplyRead(
            id=x.id, status=x.status, body=x.body, created_at=x.created_at, sent_at=x.sent_at,
            admin=_person(db.get(models.User, x.admin_id) if x.admin_id else None),
        )
        for x in rows
    ]


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


_SEND_FAILED = "המייל לא נשלח, והתשובה לא הגיעה לפונה. אפשר לנסות לשלוח שוב."
_IN_FLIGHT = "התשובה הזו כבר בשליחה."


@router.post("/requests/{request_id}/replies", response_model=SupportRequestDetail)
def send_reply(
    request_id: int,
    payload: SupportReplyCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("support.handle")),
) -> SupportRequestDetail:
    """שולח לפונה את תשובת הצוות. **לא** נוגע בסטטוס הפנייה.

    - הנמען: כתובת המייל של החשבון שפתח את הפנייה — מה-DB, לא מהדפדפן.
    - פעם אחת: ``(request_id, client_token)`` ייחודי. אותו מזהה שוב — אם
      כבר נשלח, מחזירים את המצב הקיים בלי לשלוח; אם בשליחה — 409; אם נכשל —
      ניסיון חוזר על אותה שורה.
    - כשל ב-Resend → השורה ``failed``, תשובה 502, ושום דבר לא נרשם כנשלח.
    """
    r = _get(db, request_id)
    text = payload.body.strip()
    if not text:
        raise HTTPException(status_code=422, detail="התשובה ריקה")
    person = db.get(models.User, r.user_id)
    to = (getattr(person, "email", "") or "").strip()
    if not to:
        raise HTTPException(status_code=409, detail="לפונה אין כתובת מייל, ולכן אי אפשר לשלוח תשובה")

    R = models.SupportReply
    reply = db.scalar(select(R).where(R.request_id == r.id, R.client_token == payload.client_token))
    if reply is not None:
        if reply.status in ("sent", "mock"):
            if reply.body != text:
                raise HTTPException(status_code=409, detail="התשובה הזו כבר נשלחה")
            return get_request(request_id, db, admin)  # לחיצה כפולה — בלי לשלוח שוב
        if reply.status == "sending":
            raise HTTPException(status_code=409, detail=_IN_FLIGHT)
        attempt = (reply.attempts or 1) + 1
        claimed = db.execute(
            update(R).where(R.id == reply.id, R.status == "failed")
            .values(status="sending", body=text, admin_id=admin.id, attempts=attempt)
        ).rowcount
        db.commit()
        if claimed != 1:
            raise HTTPException(status_code=409, detail=_IN_FLIGHT)
        reply_id = reply.id
    else:
        attempt = 1
        reply = R(
            request_id=r.id, admin_id=admin.id, client_token=payload.client_token,
            body=text, status="sending", attempts=1,
        )
        db.add(reply)
        try:
            db.commit()
        except IntegrityError:  # שתי לחיצות באותו רגע — רק אחת נכנסת
            db.rollback()
            raise HTTPException(status_code=409, detail=_IN_FLIGHT)
        reply_id = reply.id

    try:
        result = emailer.send_support_reply(
            to=to, request_id=r.id, reply_text=text,
            idempotency_key=f"veya-support-reply-{reply_id}-{attempt}",
        )
    except Exception:  # noqa: BLE001 — emailer לא זורק, אבל לא סומכים על זה
        result = None
    sent = result is not None and result.ok
    status = ("sent" if result.mode == "live" else "mock") if sent else "failed"
    db.execute(
        update(R).where(R.id == reply_id).values(
            status=status, sent_at=datetime.utcnow() if status == "sent" else None,
        )
    )
    if sent:
        admin_audit.record(
            db, admin, domain="support", action="support.reply",
            summary=f"פנייה #{r.id}: נשלחה תשובה לפונה" + ("" if status == "sent" else " (סביבה בלי מייל)"),
            target_type="support_request", target_id=r.id, target_label=f"פנייה #{r.id}",
            event_id=r.event_id, request=request,
        )
    db.commit()
    if not sent:
        raise HTTPException(status_code=502, detail=_SEND_FAILED)
    return get_request(request_id, db, admin)



# ─── תובנות עזרה (שלב 8) — ספירות בלבד, בלי זהות ──────────────────────────

insights_router = APIRouter(prefix="/admin/help", tags=["admin"])


@insights_router.get("/insights")
def help_insights(
    days: int = Query(default=7),
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("help.insights")),
) -> dict:
    if days not in (7, 30):
        raise HTTPException(status_code=422, detail="אפשר 7 או 30 ימים")
    # מחיקת אירועים ישנים מ-180 יום — כאן, בזהות אדמין (RLS), לכל היותר פעם בשעה.
    help_analytics.purge_old(db)
    db.commit()
    return help_analytics.insights(db, days)
