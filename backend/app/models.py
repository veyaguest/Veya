"""מודלי מסד הנתונים (SQLAlchemy) — שלב 2: אירועים ומוזמנים."""
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


def generate_guest_token() -> str:
    """טוקן אישי, אקראי ובלתי-ניתן-לניחוש, לקישור אישור ההגעה של מוזמן."""
    return secrets.token_urlsafe(12)


class User(Base):
    """משתמש רשום (בעל אירוע). מתחבר עם אימייל + סיסמה (שלב 8).

    לכל משתמש יכולים להיות כמה אירועים (חתונות).
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    display_name: Mapped[str] = mapped_column(String, default="")
    # אדמין = הבעלים של המערכת, רואה ומנהל את כל המשתמשים והאירועים.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    events: Mapped[list["Event"]] = relationship(back_populates="owner")


class Event(Base):
    """אירוע (חתונה). שייך למשתמש דרך owner_id (שלב 8)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    groom_name: Mapped[str] = mapped_column(String, default="")
    bride_name: Mapped[str] = mapped_column(String, default="")
    venue_name: Mapped[str] = mapped_column(String, default="")
    # תאריך ושעת האירוע (טקסט חופשי/ISO) — מוצג בדף האישור ובתבנית ההודעה.
    event_date: Mapped[str] = mapped_column(String, default="")   # YYYY-MM-DD
    event_time: Mapped[str] = mapped_column(String, default="")   # HH:MM
    # מיקומי השולחנות במפת האולם (שלב 7): {"1": {"x": .., "y": ..}, ...}
    table_positions: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # אלמנטים מיוחדים במפה (שולחן ראש, רחבת ריקודים, בר, במה...):
    # [{"id": .., "type": .., "x": .., "y": .., "width": .., "height": .., "label": ..}]
    hall_elements: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    seats_per_table: Mapped[int] = mapped_column(Integer, default=12)
    # תבנית הודעת ההזמנה (שלב RSVP 2). None => משתמשים בתבנית ברירת המחדל.
    message_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # תמונת ההזמנה שהזוג העלה (data URL בבסיס64). None => אין תמונה.
    invite_image: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # סקיצה/תמונה של האולם למפת ההושבה (data URL). מוצגת כרקע עדין מתחת לשולחנות.
    hall_sketch: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    owner: Mapped[Optional["User"]] = relationship(back_populates="events")
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
    rsvp_status: Mapped[str] = mapped_column(String, default="pending")  # pending/confirmed/declined/maybe
    table_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # קישור אישי לאישור הגעה: טוקן ייחודי לכל מוזמן (שלב RSVP).
    guest_token: Mapped[Optional[str]] = mapped_column(
        String, unique=True, index=True, nullable=True, default=generate_guest_token
    )
    # כמה אנשים באמת מגיעים (נמסר ע"י המוזמן בדף האישור). None = טרם ענה.
    confirmed_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # הערה חופשית שהמוזמן השאיר בדף האישור (נגישות, תינוק וכו').
    guest_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    event: Mapped["Event"] = relationship(back_populates="guests")

    @property
    def effective_seats(self) -> int:
        """כמות המקומות שהמוזמן הזה באמת תופס — הבסיס לכל ספירת אנשים במערכת.

        אחרי שהמוזמן ענה, סופרים לפי מה שאישר (``confirmed_count``) ולא לפי כמה
        שהוזמן (``party_size``):
        - ביטל הגעה → 0 (לא תופס מקום).
        - אישר → הכמות שהזין (ואם משום מה חסרה — נופלים ל-``party_size``).
        - עדיין לא ענה / "אולי" → ``party_size`` (מתכננים לפי ההזמנה).
        """
        if self.rsvp_status == "declined":
            return 0
        if self.rsvp_status == "confirmed" and self.confirmed_count is not None:
            return self.confirmed_count
        return self.party_size


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


class AuditLog(Base):
    """יומן אבטחה — מתעד פעולות רגישות (שליחת הודעות, עדכון אירוע, גישה לקישור).

    מטרה (PRD אבטחה): לאפשר מעקב מי עשה מה ומתי, ולזהות ניסיונות גישה חריגים
    לקישורים אישיים. אין כאן מידע רגיש — רק סוג הפעולה ותיאור קצר.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("events.id"), nullable=True, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(String, index=True)  # send_invitations/update_event/...
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
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
