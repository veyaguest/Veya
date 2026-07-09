"""מודלי מסד הנתונים (SQLAlchemy) — שלב 2: אירועים ומוזמנים."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


class Event(Base):
    """אירוע (חתונה). בשלב הנוכחי קיים אירוע ברירת-מחדל אחד בלבד."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    groom_name: Mapped[str] = mapped_column(String, default="")
    bride_name: Mapped[str] = mapped_column(String, default="")
    venue_name: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    guests: Mapped[list["Guest"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class Guest(Base):
    """מוזמן — מקור האמת המרכזי של המערכת (PRD חלק 4)."""

    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    full_name: Mapped[str] = mapped_column(String)
    phone: Mapped[str] = mapped_column(String)
    side: Mapped[str] = mapped_column(String, default="shared")  # groom/bride/shared
    group_type: Mapped[str] = mapped_column(String, default="other")
    party_size: Mapped[int] = mapped_column(Integer, default=1)
    notes_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # נגזר אוטומטית מ-notes_raw ע"י ה-AI בשלב 4 (כרגע ריק)
    constraints_parsed: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    rsvp_status: Mapped[str] = mapped_column(String, default="pending")  # pending/confirmed/declined
    table_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    event: Mapped["Event"] = relationship(back_populates="guests")


class Clarification(Base):
    """הבהרה ממתינה — נוצרת כשפרסור ההערות מזהה שם עמום (PRD: לולאת הבהרות).

    מוצגת למשתמש כשאלה סגורה עם כפתורים (בחירת המוזמן הנכון מבין המועמדים).
    """

    __tablename__ = "clarifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    source_guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"))
    relation_type: Mapped[str] = mapped_column(String)  # avoid/together
    target_text: Mapped[str] = mapped_column(String)    # השם העמום בהערה
    candidate_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending/resolved/dismissed
    chosen_guest_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Message(Base):
    """יומן הודעות WhatsApp (שלב 5).

    כל שורה = הודעה יוצאת (הזמנה/אישור) או נכנסת (תשובת RSVP מהמוזמן).
    במצב 'mock' לא נשלחת הודעה אמיתית — רק נרשמת כאן כדי לבדוק את הזרימה.
    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    guest_id: Mapped[Optional[int]] = mapped_column(ForeignKey("guests.id"), nullable=True)
    direction: Mapped[str] = mapped_column(String)  # outbound/inbound
    kind: Mapped[str] = mapped_column(String, default="invitation")  # invitation/reply/reminder
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="sent")  # sent/delivered/failed/received
    provider: Mapped[str] = mapped_column(String, default="mock")  # mock/meta
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
