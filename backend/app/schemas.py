"""סכימות Pydantic — ולידציה של קלט/פלט ל-API של המוזמנים."""
from datetime import datetime
from typing import Optional

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from app.validators import normalize_israeli_phone

Side = Literal["groom", "bride", "shared"]
GroupType = Literal["close_family", "extended_family", "friends", "work", "other"]
RsvpStatus = Literal["pending", "confirmed", "declined"]


class GuestCreate(BaseModel):
    full_name: str
    phone: str
    side: Side = "shared"
    group_type: GroupType = "other"
    party_size: int = 1
    notes_raw: Optional[str] = None

    @field_validator("full_name")
    @classmethod
    def _name_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("שם מלא הוא שדה חובה")
        return v

    @field_validator("phone")
    @classmethod
    def _phone_valid(cls, v: str) -> str:
        return normalize_israeli_phone(v)

    @field_validator("party_size")
    @classmethod
    def _party_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("כמות אנשים חייבת להיות לפחות 1")
        return v


class GuestUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    side: Optional[Side] = None
    group_type: Optional[GroupType] = None
    party_size: Optional[int] = None
    notes_raw: Optional[str] = None
    rsvp_status: Optional[RsvpStatus] = None
    table_number: Optional[int] = None

    @field_validator("phone")
    @classmethod
    def _phone_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return normalize_israeli_phone(v)


class GuestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    phone: str
    side: str
    group_type: str
    party_size: int
    notes_raw: Optional[str]
    rsvp_status: str
    table_number: Optional[int]
    created_at: datetime


# ---- שיבוץ הושבה (שלב 3) ----


class SeatingRequest(BaseModel):
    seats_per_table: int = 12
    num_tables: Optional[int] = None          # None => חישוב אוטומטי
    only_confirmed: bool = False              # לשבץ רק מי שאישר הגעה
    persist: bool = False                     # לשמור table_number חזרה על המוזמנים
    forbidden_pairs: list[tuple[int, int]] = []  # זוגות "לא לשבת יחד" (שלב 4)

    @field_validator("seats_per_table")
    @classmethod
    def _seats_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("מספר הכיסאות לשולחן חייב להיות לפחות 1")
        return v


class SeatingPartyRead(BaseModel):
    id: int
    full_name: str
    party_size: int
    side: str
    group_type: str


class SeatingTableRead(BaseModel):
    table_number: int
    seats_used: int
    capacity: int
    parties: list[SeatingPartyRead]


class SeatingResponse(BaseModel):
    tables: list[SeatingTableRead]
    total_people: int
    num_tables: int
    seats_per_table: int
    score: int
    hard_ok: bool
    unseated: list[int]
    persisted: bool


# ---- פרסור הערות + הבהרות (שלב 4) ----


class AnalyzeResult(BaseModel):
    guests_analyzed: int
    relations_found: int
    resolved: int
    ambiguous: int
    unresolved: int
    pending_clarifications: int


class ClarificationCandidate(BaseModel):
    id: int
    full_name: str


class ClarificationRead(BaseModel):
    id: int
    source_guest_id: int
    source_guest_name: str
    relation_type: str  # avoid/together
    target_text: str
    candidates: list[ClarificationCandidate]


class ResolveClarification(BaseModel):
    # מזהה המוזמן שנבחר, או null אם "אף אחד מהם" (דחייה)
    chosen_guest_id: Optional[int] = None


# ---- WhatsApp / RSVP (שלב 5) ----


class SendInvitationsRequest(BaseModel):
    # ברירת מחדל: לשלוח רק למי שעדיין לא ענה (pending). False => לכולם.
    only_pending: bool = True
    # לשלוח רק למוזמן בודד (אופציונלי). None => לכל הרשימה לפי only_pending.
    guest_id: Optional[int] = None


class SendInvitationsResult(BaseModel):
    mode: str            # mock/live
    sent: int
    failed: int
    skipped: int
    detail: Optional[str] = None


class SimulateReplyRequest(BaseModel):
    guest_id: int
    coming: bool         # True => "מגיע/ה", False => "לא מגיע/ה"


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    guest_id: Optional[int]
    direction: str
    kind: str
    body: str
    status: str
    provider: str
    created_at: datetime


class RsvpSummary(BaseModel):
    total_guests: int
    confirmed: int
    declined: int
    pending: int
    invitations_sent: int
    mode: str


# ---- דשבורד (שלב 6) ----


class DashboardStats(BaseModel):
    # מוזמנים
    total_guests: int
    total_people: int          # סכום party_size (כולל בני/בנות זוג וילדים)
    confirmed_people: int      # סכום party_size של מי שאישר
    # RSVP
    confirmed: int
    declined: int
    pending: int
    response_rate: int         # אחוז מי שענה (אישר/ביטל) מכלל המוזמנים
    invitations_sent: int
    # פילוחים
    by_side: dict              # {groom, bride, shared}
    by_group: dict             # {close_family, ...}
    # הושבה + אילוצים
    tables_assigned: int       # כמה שולחנות שובצו (table_number ייחודי)
    seated_guests: int         # כמה מוזמנים כבר משובצים
    pending_clarifications: int
    # פרטי אירוע
    groom_name: str
    bride_name: str
    venue_name: str


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    groom_name: str
    bride_name: str
    venue_name: str


class EventUpdate(BaseModel):
    groom_name: Optional[str] = None
    bride_name: Optional[str] = None
    venue_name: Optional[str] = None


# ---- מפת אולם (שלב 7) ----


class HallGuest(BaseModel):
    id: int
    full_name: str
    party_size: int
    side: str
    group_type: str
    rsvp_status: str


class HallTable(BaseModel):
    table_number: int
    x: float
    y: float
    seats_used: int
    guests: list[HallGuest]


class HallState(BaseModel):
    seats_per_table: int
    tables: list[HallTable]
    unassigned: list[HallGuest]          # מוזמנים ללא שולחן
    warnings: list[str]                  # חריגות (קיבולת/זוג אסור באותו שולחן)


class HallTableSave(BaseModel):
    table_number: int
    x: float
    y: float
    guest_ids: list[int]


class SaveHallRequest(BaseModel):
    seats_per_table: Optional[int] = None
    tables: list[HallTableSave]
