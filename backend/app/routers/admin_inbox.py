"""תיבת WhatsApp — מסך הצוות (``app/whatsapp_inbox.py``).

- ``GET  /admin/inbox/summary``                 — כמה שיחות פתוחות (לתפריט).
- ``GET  /admin/inbox/threads``                 — רשימה (סינון: open/answered/closed/all, "שלי").
- ``GET  /admin/inbox/threads/{id}``            — שיחה אחת עם כל ההודעות.
- ``POST /admin/inbox/threads/{id}/reply``      — מענה בטקסט חופשי, רק בתוך 24 שעות.
- ``POST /admin/inbox/threads/{id}/status``     — open / answered / closed.
- ``POST /admin/inbox/threads/{id}/assign``     — שיוך לאיש צוות (או הסרה).

## מי נכנס (החלטת המייסד, 2026-10-19)
אדמין בדרגת Support ומעלה (``inbox.view`` / ``inbox.handle``), **וגם טלפנים**
(``account_type=phone_agent``) — לשונית "WhatsApp" במסך הטלפן. פרטי חשבון
(מייל, אירועים) מוצגים רק למי שיש לו ``users.view``.

## מענה
- הנמען — המספר של השיחה, מה-DB. אין שדה נמען בבקשה (422).
- **חלון 24 השעות נאכף כאן**, לא רק במסך: אחריו — 409.
- פעם אחת: ``(thread_id, client_token)`` ייחודי. אותו מזהה שוב — אם יצא/נשמר,
  מחזירים את המצב בלי לשלוח; אם בשליחה — 409; אם נכשל — ניסיון חוזר על אותה שורה.
- רישום לפני שליחה: השורה נשמרת כ-``pending`` (commit), ורק אז ``deliver``.
- כל מענה, שינוי סטטוס ושיוך נרשמים ביומן האדמין — **בלי** תוכן ההודעה.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import admin_audit, admin_rbac, message_status, models, roles, whatsapp_inbox
from app.auth import get_current_caller
from app.database import get_db

router = APIRouter(prefix="/admin/inbox", tags=["admin"])

REPLY_MAX = 4096
_LIST_LIMIT = 200


def _agent(permission: str):
    """אדמין עם ההרשאה, או טלפן. ``get_current_caller`` דוחה כל מי שאינו אחד מהם."""
    admin_rbac.require(permission)  # טעות מפתח נתפסת בעליית השרת

    def dependency(user: models.User = Depends(get_current_caller)) -> models.User:
        if roles.is_phone_agent(user) or admin_rbac.has_permission(user, permission):
            return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="אין לך הרשאה לפעולה הזו")

    return dependency


def is_agent(user: Optional[models.User]) -> bool:
    """מי יכול לקבל שיחה בשיוך: טלפן, או אדמין עם ``inbox.handle``."""
    if user is None or user.disabled:
        return False
    return roles.is_phone_agent(user) or admin_rbac.has_permission(user, "inbox.handle")


# ─── סכמות ─────────────────────────────────────────────────────────────────

class InboxPerson(BaseModel):
    id: int
    name: str


class InboxAccountEvent(BaseModel):
    id: int
    title: str


class InboxAccount(BaseModel):
    id: int
    name: str
    #: רק למי שיש לו ``users.view``; אחרת ריק.
    email: str = ""
    events: list[InboxAccountEvent] = []


class InboxThreadRow(BaseModel):
    id: int
    phone: str
    name: str
    sender_kind: str
    status: str
    assigned_to: Optional[InboxPerson]
    last_message_at: Optional[datetime]
    last_inbound_at: Optional[datetime]
    preview: str
    preview_direction: str
    window_open: bool
    window_closes_at: Optional[datetime]


class InboxMessage(BaseModel):
    id: int
    direction: str
    kind: str
    body: str
    status: str
    failure_reason: str
    created_at: Optional[datetime]
    sent_by: Optional[InboxPerson]


class InboxThreadDetail(InboxThreadRow):
    profile_name: str
    account: Optional[InboxAccount]
    messages: list[InboxMessage]
    agents: list[InboxPerson]


class InboxSummary(BaseModel):
    open: int
    mine: int


class InboxReplyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str = Field(min_length=1, max_length=REPLY_MAX)
    client_token: str = Field(pattern=r"^[A-Za-z0-9-]{16,64}$")


class InboxStatusUpdate(BaseModel):
    status: Literal["open", "answered", "closed"]


class InboxAssign(BaseModel):
    assignee_id: Optional[int] = None


# ─── עזרים ─────────────────────────────────────────────────────────────────

def _person(db: Session, user_id: Optional[int]) -> Optional[InboxPerson]:
    if not user_id:
        return None
    u = db.get(models.User, user_id)
    if u is None:
        return None
    return InboxPerson(id=u.id, name=u.display_name or u.email or f"#{u.id}")


def _display_name(db: Session, t: models.WhatsAppThread) -> str:
    if t.user_id:
        u = db.get(models.User, t.user_id)
        if u is not None and (u.display_name or "").strip():
            return u.display_name.strip()
    return t.profile_name or ""


def _last_message(db: Session, thread_id: int) -> Optional[models.WhatsAppThreadMessage]:
    M = models.WhatsAppThreadMessage
    return db.scalar(select(M).where(M.thread_id == thread_id).order_by(M.id.desc()).limit(1))


def _row(db: Session, t: models.WhatsAppThread) -> dict:
    last = _last_message(db, t.id)
    return dict(
        id=t.id, phone=t.phone, name=_display_name(db, t), sender_kind=t.sender_kind,
        status=t.status, assigned_to=_person(db, t.assigned_to_id),
        last_message_at=t.last_message_at, last_inbound_at=t.last_inbound_at,
        preview=(last.body[:140] if last else ""), preview_direction=(last.direction if last else ""),
        window_open=whatsapp_inbox.window_open(t), window_closes_at=whatsapp_inbox.window_closes_at(t),
    )


def _get(db: Session, thread_id: int) -> models.WhatsAppThread:
    t = db.get(models.WhatsAppThread, thread_id)
    if t is None:
        raise HTTPException(status_code=404, detail="השיחה לא נמצאה")
    return t


def _agents(db: Session) -> list[InboxPerson]:
    U = models.User
    rows = db.scalars(
        select(U).where(or_(U.is_admin.is_(True), U.account_type == roles.PHONE_AGENT))
        .where(U.disabled.is_(False)).order_by(U.display_name)
    ).all()
    return [InboxPerson(id=u.id, name=u.display_name or u.email or f"#{u.id}") for u in rows if is_agent(u)]


def _account(db: Session, t: models.WhatsAppThread, viewer: models.User) -> Optional[InboxAccount]:
    if not t.user_id:
        return None
    u = db.get(models.User, t.user_id)
    if u is None:
        return None
    if not admin_rbac.has_permission(viewer, "users.view"):
        return InboxAccount(id=u.id, name=u.display_name or "")
    from app import event_terms, partners

    E = models.Event
    owned = db.scalars(select(E).where(E.owner_id == u.id)).all()
    member_ids = db.scalars(
        select(models.EventMember.event_id).where(
            models.EventMember.user_id == u.id, models.EventMember.status == "active",
            models.EventMember.role == partners.PARTNER_ROLE)
    ).all()
    shared = db.scalars(select(E).where(E.id.in_(member_ids))).all() if member_ids else []
    events = [
        InboxAccountEvent(id=e.id, title=event_terms.event_display_title(e.event_type, e.groom_name, e.bride_name))
        for e in [*owned, *shared]
    ]
    return InboxAccount(id=u.id, name=u.display_name or "", email=u.email or "", events=events)


def _detail(db: Session, t: models.WhatsAppThread, viewer: models.User) -> InboxThreadDetail:
    M = models.WhatsAppThreadMessage
    rows = db.scalars(select(M).where(M.thread_id == t.id).order_by(M.id)).all()
    return InboxThreadDetail(
        **_row(db, t), profile_name=t.profile_name or "", account=_account(db, t, viewer),
        messages=[
            InboxMessage(
                id=m.id, direction=m.direction, kind=m.kind, body=m.body, status=m.status,
                failure_reason=m.failure_reason or "", created_at=m.created_at,
                sent_by=_person(db, m.sent_by_id),
            ) for m in rows
        ],
        agents=_agents(db),
    )


def _label(t: models.WhatsAppThread) -> str:
    return f"שיחת WhatsApp #{t.id}"


# ─── Endpoints ─────────────────────────────────────────────────────────────

@router.get("/summary", response_model=InboxSummary)
def summary(
    db: Session = Depends(get_db),
    user: models.User = Depends(_agent("inbox.view")),
) -> InboxSummary:
    T = models.WhatsAppThread
    open_count = db.scalar(select(func.count()).select_from(T).where(T.status == whatsapp_inbox.OPEN)) or 0
    mine = db.scalar(select(func.count()).select_from(T).where(
        T.status == whatsapp_inbox.OPEN, T.assigned_to_id == user.id)) or 0
    return InboxSummary(open=open_count, mine=mine)


@router.get("/threads", response_model=list[InboxThreadRow])
def list_threads(
    status_filter: Literal["open", "answered", "closed", "all"] = Query(default="open", alias="status"),
    mine: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: models.User = Depends(_agent("inbox.view")),
) -> list[InboxThreadRow]:
    T = models.WhatsAppThread
    q = select(T)
    if status_filter != "all":
        q = q.where(T.status == status_filter)
    if mine:
        q = q.where(T.assigned_to_id == user.id)
    q = q.order_by(T.last_message_at.desc().nullslast(), T.id.desc()).limit(_LIST_LIMIT)
    return [InboxThreadRow(**_row(db, t)) for t in db.scalars(q).all()]


@router.get("/threads/{thread_id}", response_model=InboxThreadDetail)
def get_thread(
    thread_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(_agent("inbox.view")),
) -> InboxThreadDetail:
    return _detail(db, _get(db, thread_id), user)


_IN_FLIGHT = "התשובה הזו כבר בשליחה."
_WINDOW_CLOSED = (
    "עברו 24 שעות מההודעה האחרונה של הפונה. WhatsApp מאפשר לפנות שוב רק בתבנית מאושרת."
)


@router.post("/threads/{thread_id}/reply", response_model=InboxThreadDetail)
def reply(
    thread_id: int,
    payload: InboxReplyCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(_agent("inbox.handle")),
) -> InboxThreadDetail:
    t = _get(db, thread_id)
    text = payload.body.strip()
    if not text:
        raise HTTPException(status_code=422, detail="התשובה ריקה")
    if not whatsapp_inbox.window_open(t):
        raise HTTPException(status_code=409, detail=_WINDOW_CLOSED)

    M = models.WhatsAppThreadMessage
    row = db.scalar(select(M).where(M.thread_id == t.id, M.client_token == payload.client_token))
    if row is not None:
        if whatsapp_inbox.is_delivered_or_saved(row):
            if row.body != text:
                raise HTTPException(status_code=409, detail="התשובה הזו כבר נשלחה")
            return _detail(db, t, user)  # לחיצה כפולה — בלי לשלוח שוב
        if row.status == message_status.PENDING:
            raise HTTPException(status_code=409, detail=_IN_FLIGHT)
        claimed = db.execute(
            update(M).where(M.id == row.id, M.status.in_((message_status.FAILED, whatsapp_inbox.BLOCKED)))
            .values(status=message_status.PENDING, body=text, sent_by_id=user.id, failure_reason="")
            .execution_options(synchronize_session=False)
        ).rowcount
        db.commit()
        if claimed != 1:
            raise HTTPException(status_code=409, detail=_IN_FLIGHT)
        db.refresh(row)
    else:
        row = M(
            thread_id=t.id, direction="outbound", kind="reply", body=text,
            status=message_status.PENDING, sent_by_id=user.id, client_token=payload.client_token,
            created_at=whatsapp_inbox._now(),
        )
        db.add(row)
        try:
            db.commit()  # רישום לפני שליחה
        except IntegrityError:  # שתי לחיצות באותו רגע — רק אחת נכנסת
            db.rollback()
            raise HTTPException(status_code=409, detail=_IN_FLIGHT)

    whatsapp_inbox.deliver(db, row)
    if whatsapp_inbox.is_delivered_or_saved(row):
        t.last_message_at = whatsapp_inbox._now()
        t.updated_at = t.last_message_at
        if t.status == whatsapp_inbox.OPEN:
            t.status = whatsapp_inbox.ANSWERED
        if t.assigned_to_id is None:
            t.assigned_to_id = user.id
    admin_audit.record(
        db, user, domain="messages", action="inbox.reply",
        summary=f"{_label(t)}: מענה ב-WhatsApp ({row.status})",
        target_type="whatsapp_thread", target_id=t.id, target_label=_label(t), request=request,
    )
    db.commit()
    return _detail(db, t, user)


_STATUS_LABEL = {"open": "פתוחה", "answered": "נענתה", "closed": "סגורה"}


@router.post("/threads/{thread_id}/status", response_model=InboxThreadDetail)
def set_status(
    thread_id: int,
    payload: InboxStatusUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(_agent("inbox.handle")),
) -> InboxThreadDetail:
    t = _get(db, thread_id)
    before = t.status
    if before != payload.status:
        t.status = payload.status
        t.updated_at = whatsapp_inbox._now()
        admin_audit.record(
            db, user, domain="messages", action="inbox.status",
            summary=f"{_label(t)}: {_STATUS_LABEL.get(before, before)} → {_STATUS_LABEL[payload.status]}",
            target_type="whatsapp_thread", target_id=t.id, target_label=_label(t),
            changes=[{"field": "status", "label": "סטטוס",
                      "before": _STATUS_LABEL.get(before, before), "after": _STATUS_LABEL[payload.status]}],
            request=request,
        )
        db.commit()
    return _detail(db, t, user)


@router.post("/threads/{thread_id}/assign", response_model=InboxThreadDetail)
def assign(
    thread_id: int,
    payload: InboxAssign,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(_agent("inbox.handle")),
) -> InboxThreadDetail:
    t = _get(db, thread_id)
    if payload.assignee_id is not None and not is_agent(db.get(models.User, payload.assignee_id)):
        raise HTTPException(status_code=422, detail="אפשר לשייך רק לאיש צוות")
    if t.assigned_to_id != payload.assignee_id:
        before, after = _person(db, t.assigned_to_id), _person(db, payload.assignee_id)
        t.assigned_to_id = payload.assignee_id
        t.updated_at = whatsapp_inbox._now()
        admin_audit.record(
            db, user, domain="messages", action="inbox.assign",
            summary=f"{_label(t)}: שיוך ל{after.name if after else 'אף אחד'}",
            target_type="whatsapp_thread", target_id=t.id, target_label=_label(t),
            changes=[{"field": "assigned_to", "label": "משויכת ל",
                      "before": before.name if before else "", "after": after.name if after else ""}],
            request=request,
        )
        db.commit()
    return _detail(db, t, user)
