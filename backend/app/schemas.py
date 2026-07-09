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
