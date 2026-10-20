""""מוזמנים כתבו לכם" — הודעות WhatsApp ממוזמנים, לבעלי האירוע.

מוזמן שכותב למספר של VEYA שאלה על האירוע — ההודעה עוברת לבעלי האירוע, ו-VEYA
לא עונה לו (החלטת המייסד 2026-10-19, ``app/whatsapp_inbox.py``). כאן בעלי
האירוע רואים את ההודעות, עונים מה-WhatsApp האישי שלהם (קישור ``wa.me`` בדפדפן)
ומסמנים "טופל".

- ``GET  /guest-messages``                  — ההודעות שמחכות (``?all=true`` — גם שטופלו).
- ``POST /guest-messages/{message_id}/handled`` — "טופל".

הרשאה: ``send_messages`` — כמו שאר מסך אישורי ההגעה (וכמו מדיניות ה-RLS על
``messages``).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import message_status, models, permissions, whatsapp_inbound, whatsapp_inbox
from app.database import get_db
from app.deps import EventAccess

router = APIRouter(prefix="/guest-messages", tags=["guest-messages"])

_access = EventAccess(permissions.AUTOMATION)


class GuestMessageItem(BaseModel):
    id: int
    guest_id: Optional[int]
    #: ריק כשהמספר משותף לכמה מוזמנים באירוע ולא ידוע מי מהם כתב.
    guest_name: str
    #: הטלפון של המוזמן (``05XXXXXXXX``) — לקישור "לענות מהוואטסאפ שלכם". ריק אם אין.
    phone: str
    body: str
    created_at: Optional[datetime]
    handled: bool


class GuestMessageList(BaseModel):
    waiting: int
    items: list[GuestMessageItem]


def _item(db: Session, m: models.Message) -> GuestMessageItem:
    guest = db.get(models.Guest, m.guest_id) if m.guest_id else None
    return GuestMessageItem(
        id=m.id, guest_id=m.guest_id,
        guest_name=(guest.full_name if guest is not None else ""),
        phone=(whatsapp_inbound.normalize_sender(guest.phone) or "") if guest is not None else "",
        body=m.body or "", created_at=m.created_at,
        handled=m.status == message_status.HANDLED,
    )


@router.get("", response_model=GuestMessageList)
def list_guest_messages(
    all_messages: bool = Query(default=False, alias="all"),
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
) -> GuestMessageList:
    rows = whatsapp_inbox.guest_messages(db, event.id, include_handled=all_messages)
    items = [_item(db, m) for m in rows[:200]]
    waiting = sum(1 for m in rows if m.status == message_status.NEEDS_ATTENTION)
    return GuestMessageList(waiting=waiting, items=items)


@router.post("/{message_id}/handled", response_model=GuestMessageItem)
def mark_handled(
    message_id: int,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_access),
) -> GuestMessageItem:
    m = db.get(models.Message, message_id)
    if (
        m is None or m.event_id != event.id or m.direction != "inbound" or m.kind != "inbound"
        or m.status not in (message_status.NEEDS_ATTENTION, message_status.HANDLED)
    ):
        raise HTTPException(status_code=404, detail="ההודעה לא נמצאה")
    m.status = message_status.HANDLED
    db.commit()
    return _item(db, m)
