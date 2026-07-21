"""סכימות Pydantic — ולידציה של קלט/פלט ל-API של המוזמנים."""
import re
from datetime import datetime
from typing import Optional

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.validators import normalize_israeli_phone

Side = Literal["groom", "bride", "shared"]
# קבוצה: אחת מהמוכרות, או קבוצה מותאמת אישית (טקסט חופשי) — לכן str ולא Literal
GroupType = str
# "maybe" = המוזמן סימן "אולי" בדף האישור (עקבי עם ערכי ה-DB האפשריים).
RsvpStatus = Literal["pending", "confirmed", "declined", "maybe"]


def validate_password_strength(v: str) -> str:
    """כלל סיסמה אחיד לכל המערכת: לפחות 8 תווים + אות אחת וספרה אחת.

    מקבל אותיות עבריות או לטיניות. משמש בהרשמה, בשינוי סיסמה ובאיפוס.
    """
    v = v or ""
    if len(v) < 8:
        raise ValueError("הסיסמה חייבת לכלול לפחות 8 תווים")
    if not re.search(r"[A-Za-zא-ת]", v) or not re.search(r"\d", v):
        raise ValueError("הסיסמה חייבת לכלול לפחות אות אחת וספרה אחת")
    return v


class GuestCreate(BaseModel):
    full_name: str
    phone: str
    side: Side = "shared"
    group_type: GroupType = "other"
    party_size: int = 1
    notes_raw: Optional[str] = None
    is_child: bool = False

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

    @field_validator("group_type")
    @classmethod
    def _group_default(cls, v: str) -> str:
        return (v or "").strip() or "other"


class GuestUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    side: Optional[Side] = None
    group_type: Optional[GroupType] = None
    party_size: Optional[int] = None
    notes_raw: Optional[str] = None
    rsvp_status: Optional[RsvpStatus] = None
    table_number: Optional[int] = None
    is_child: Optional[bool] = None

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
    guest_token: Optional[str] = None
    confirmed_count: Optional[int] = None
    guest_note: Optional[str] = None
    is_child: bool = False
    # סטטוס נגזר (לא עמודה ב-DB): not_sent/sent/awaiting/confirmed/declined
    # ובעתיד delivered/read. מחושב מתוך rsvp_status + יומן ההודעות. ברירת המחדל
    # מתאימה למוזמן חדש שטרם נשלחה אליו הזמנה.
    invite_status: str = "not_sent"
    created_at: datetime


class GuestListPage(BaseModel):
    """עמוד מתוך רשימת המוזמנים + סכומים לכל הרשימה המסוננת (לא רק לעמוד)."""

    items: list[GuestRead]
    total: int              # סך המוזמנים התואמים לסינון
    total_people: int       # סכום כמות ההזמנה של כל התואמים
    confirmed_people: int   # סכום המקומות בפועל של מי שאישר
    limit: int
    offset: int


# ---- שיבוץ הושבה (שלב 3) ----


class SeatingRequest(BaseModel):
    seats_per_table: int = 12
    num_tables: Optional[int] = None          # None => חישוב אוטומטי
    only_confirmed: bool = False              # לשבץ רק מי שאישר הגעה
    persist: bool = False                     # לשמור table_number חזרה על המוזמנים
    forbidden_pairs: list[tuple[int, int]] = []  # זוגות "לא לשבת יחד" (שלב 4)
    # רזרבה מפוזרת: כמה מקומות סה"כ להשאיר פנויים, מפוזרים אחיד בין השולחנות
    # הפעילים. None => להשתמש בערך השמור על האירוע. שולחנות רזרבה (is_reserve)
    # מוצאים מהשיבוץ האוטומטי בנפרד.
    reserve_seats: Optional[int] = None

    @field_validator("seats_per_table")
    @classmethod
    def _seats_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("מספר הכיסאות לשולחן חייב להיות לפחות 1")
        return v

    @field_validator("reserve_seats")
    @classmethod
    def _reserve_nonneg(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("מספר מקומות הרזרבה לא יכול להיות שלילי")
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


class SeatingExplanation(BaseModel):
    """הסבר קצר "למה שובץ כאן" — מוצג לזוג אחרי סידור אוטומטי (שקיפות = אמון)."""

    guest_id: int
    full_name: str
    table_number: int
    reasons: list[str]


class SeatingResponse(BaseModel):
    tables: list[SeatingTableRead]
    total_people: int
    num_tables: int
    seats_per_table: int
    score: int
    hard_ok: bool
    unseated: list[int]
    persisted: bool
    # הסברי שיבוץ למוזמנים שהיו להם העדפה מההערות (רשימה יכולה להיות ריקה).
    explanations: list[SeatingExplanation] = []


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


class TemplatePlaceholder(BaseModel):
    key: str             # המשתנה הטכני, למשל "{{guest_name}}"
    desc: str            # הסבר קצר בעברית
    # כינוי ידידותי בעברית שמוצג ומוכנס לזוג במקום המשתנה הטכני, למשל
    # "[שם אורח]". ריק כשאין כינוי (המשתנים הישנים בסגנון {name}).
    token: str = ""


class MessageTemplateRead(BaseModel):
    template: str
    is_custom: bool
    default_template: str
    placeholders: list[TemplatePlaceholder]


class MessageTemplateSave(BaseModel):
    template: str = ""


class TemplatePreview(BaseModel):
    preview: str


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
    maybe: int                 # סימנו "עדיין לא בטוחים"
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
    # העדפות ישיבה (למדד המוכנות) — כמה מוזמנים עם הערה, וכמה קבוצות עם העדפה
    guests_with_notes: int = 0
    group_notes_count: int = 0
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
    venue_address: str = ""
    event_date: str = ""
    event_time: str = ""
    invite_image: Optional[str] = None
    # יום ההתחייבות לאולם: כמה ימים לפני האירוע (1–10). None = טרם נבחר.
    venue_commit_days_before: Optional[int] = None
    # האם הבחירה כבר ננעלה (נבחרה בעבר) — הפרונט מציג אותה כקריאה-בלבד.
    venue_commit_locked: bool = False


class EventUpdate(BaseModel):
    groom_name: Optional[str] = None
    bride_name: Optional[str] = None
    venue_name: Optional[str] = None
    venue_address: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    invite_image: Optional[str] = None
    # בחירה חד-פעמית (1–10). ניתן להגדיר רק פעם אחת; ניסיון לשנות ערך קיים נדחה.
    venue_commit_days_before: Optional[int] = None


# ---- מפת אולם (שלב 7) ----


class HallGuest(BaseModel):
    id: int
    full_name: str
    party_size: int          # כמה הוזמנו (מספר ההזמנה המקורי)
    seats: int               # כמה תופסים בפועל אחרי אישור (0 אם ביטלו)
    side: str
    group_type: str
    rsvp_status: str
    is_child: bool = False


class HallTable(BaseModel):
    table_number: int
    x: float
    y: float
    seats_used: int
    guests: list[HallGuest]
    # "round" | "square" | "rectangle" | "knights" (שולחן אבירים — ארוך, מקומות גם בקצוות)
    table_type: str = "round"
    capacity: int = 12        # מספר מקומות בשולחן הזה — עצמאי לכל שולחן
    rotation: float = 0       # זווית סיבוב במעלות
    name: str = ""            # שם אופציונלי לשולחן (למשל "משפחת כהן")
    color: str = ""           # צבע מותאם (hex); ריק = ברירת מחדל לפי סוג
    notes: str = ""
    locked: bool = False
    # שולחן רזרבה — אינו מקבל אורחים בשיבוץ האוטומטי, מסומן במפה בתג "רזרבה".
    # שיבוץ ידני אליו (ביום האירוע) מותר.
    is_reserve: bool = False


class HallElement(BaseModel):
    """אלמנט מיוחד במפה: רחבת ריקודים, בר, עמדת DJ, כניסה וכו'."""

    id: str
    type: str
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0
    locked: bool = False
    label: str = ""
    shape: str = "rectangle"  # "rectangle" | "square" | "circle" | "ellipse"
    color: str = ""           # צבע מותאם (hex); ריק = ברירת מחדל לפי סוג


class HallLayout(BaseModel):
    """פרופיל הפריסה של האולם — נקבע בהגדרה הראשונית ונשמר נעול.

    density קובע את גודל האלמנטים הקבוע (spacious/comfortable/compact/dense),
    planned_tables הוא מספר השולחנות שתוכנן — לזיהוי "נוספו הרבה מעבר לתכנון".
    """

    density: str = "comfortable"   # spacious | comfortable | compact | dense
    planned_tables: int = 0


class HallState(BaseModel):
    seats_per_table: int
    # רזרבה מפוזרת: כמה מקומות סה"כ להשאיר פנויים בשיבוץ האוטומטי (0 = ללא).
    reserve_seats: int = 0
    tables: list[HallTable]
    unassigned: list[HallGuest]          # מוזמנים ללא שולחן
    elements: list[HallElement]          # אלמנטים מיוחדים במפה
    warnings: list[str]                  # חריגות (קיבולת/זוג אסור באותו שולחן)
    sketch: Optional[str] = None         # סקיצת האולם (data URL) — רקע עדין
    hall_layout: Optional[HallLayout] = None  # פרופיל צפיפות + מספר מתוכנן
    # זוגות אילוצים שכבר מחושבים היום מהערות חופשיות (constraints.py) — נחשפים
    # כאן כדי שעוזר ההושבה החכם בצד הלקוח יוכל לבדוק אותם מיידית (כולל בזמן
    # גרירה) בלי קריאת רשת נוספת. אין כאן לוגיקה חדשה, רק חשיפה.
    forbidden_pairs: list[tuple[int, int]] = []  # זוגות "לא לשבת יחד"
    together_pairs: list[tuple[int, int]] = []   # זוגות "לשבת יחד"


class HallTableSave(BaseModel):
    table_number: int
    x: float
    y: float
    guest_ids: list[int]
    table_type: str = "round"
    capacity: int = Field(default=12, ge=1, le=60)
    rotation: float = 0
    name: str = Field(default="", max_length=60)
    color: str = Field(default="", max_length=20)
    notes: str = Field(default="", max_length=400)
    locked: bool = False
    is_reserve: bool = False


class SaveHallRequest(BaseModel):
    seats_per_table: Optional[int] = None
    tables: list[HallTableSave]
    elements: Optional[list[HallElement]] = None
    sketch: Optional[str] = None         # None => לא לשנות; מחרוזת ריקה => למחוק
    hall_layout: Optional[HallLayout] = None  # None => לא לשנות
    reserve_seats: Optional[int] = None  # None => לא לשנות; 0 = ללא רזרבה מפוזרת

    @field_validator("reserve_seats")
    @classmethod
    def _reserve_nonneg(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("מספר מקומות הרזרבה לא יכול להיות שלילי")
        return v


# ---- רזרבה חכמה: סיכום, המלצת שיבוץ ושיבוץ מהיר (מצב יום האירוע) ----


class ReserveSummary(BaseModel):
    """תמונת מצב הרזרבה — לכרטיס הדשבורד ולפאנל 'מצב יום האירוע'."""

    reserve_seats: int          # יעד הרזרבה המפוזרת שהוגדר
    reserve_tables: int         # כמה שולחנות מסומנים כרזרבה
    reserve_tables_capacity: int  # סך המקומות בשולחנות הרזרבה
    free_seats_active: int      # מקומות פנויים בשולחנות הפעילים (לא-רזרבה)
    seated_people: int          # כמה אנשים כבר משובצים
    unseated_guests: int        # מוזמנים ללא שולחן (חבורות)


class SeatRecommendation(BaseModel):
    """המלצת שולחן בודדת לשיבוץ מהיר — עם 'למה' קצר ומקומות פנויים."""

    table_number: int
    table_name: str = ""
    is_reserve: bool = False
    free_seats: int             # מקומות פנויים בשולחן הזה כרגע
    score: float                # ניקוד רך (גבוה = התאמה חברתית טובה יותר)
    reasons: list[str]          # "למה כאן" — קבוצה/צד/העדפה


class RecommendSeatRequest(BaseModel):
    guest_id: int
    include_reserve: bool = True   # לכלול שולחנות רזרבה כמועמדים (יום האירוע)


class RecommendSeatResponse(BaseModel):
    guest_id: int
    guest_name: str
    seats_needed: int
    recommendations: list[SeatRecommendation]


class AssignSeatRequest(BaseModel):
    """שיבוץ מהיר בקליק אחד (מצב יום האירוע). None => החזרה ל'ללא שולחן'."""

    guest_id: int
    table_number: Optional[int] = None


class AssignSeatResult(BaseModel):
    guest_id: int
    table_number: Optional[int]
    warnings: list[str] = []       # חריגת קיבולת / זוג "לא לשבת יחד" (לא חוסם)


# ---- משתמשים והתחברות (שלב 8) ----


class UserCreate(BaseModel):
    email: str
    password: str
    display_name: str = ""
    phone: str = ""

    @field_validator("email")
    @classmethod
    def _email_valid(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("כתובת אימייל לא תקינה")
        return v

    @field_validator("password")
    @classmethod
    def _password_valid(cls, v: str) -> str:
        return validate_password_strength(v)

    @field_validator("phone")
    @classmethod
    def _phone_valid(cls, v: str) -> str:
        return normalize_israeli_phone(v)


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email_lower(cls, v: str) -> str:
        return (v or "").strip().lower()


class ProfileUpdate(BaseModel):
    """עדכון פרטי הפרופיל של המשתמש המחובר (שם תצוגה + טלפון)."""

    display_name: str
    phone: Optional[str] = None

    @field_validator("display_name")
    @classmethod
    def _name_not_empty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("שם התצוגה לא יכול להיות ריק")
        return v

    @field_validator("phone")
    @classmethod
    def _phone_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return normalize_israeli_phone(v)


class PasswordChange(BaseModel):
    """שינוי סיסמה למשתמש מחובר: הסיסמה הנוכחית + החדשה."""

    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _new_password_valid(cls, v: str) -> str:
        return validate_password_strength(v)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    phone: str = ""
    is_admin: bool = False
    # couple (זוג) / planner (מפיק) / venue (אולם) — ציר נפרד מ-is_admin.
    account_type: str = "couple"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


# ---- ניהול אירועים (שלב 8) ----


class EventCreate(BaseModel):
    groom_name: str = ""
    bride_name: str = ""
    venue_name: str = ""


class EventSummary(BaseModel):
    """סיכום אירוע לרשימת האירועים של המשתמש."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    groom_name: str
    bride_name: str
    venue_name: str


class VenueSuggestion(BaseModel):
    """הצעת אולם מהמאגר המשותף — לכשהזוג מקליד שם אולם ומקבל השלמה עם כתובת."""

    name: str
    address: str = ""
    maps_link: str = ""               # קישור ניווט Google Maps (נגזר מהכתובת)
    waze_link: str = ""               # קישור ניווט Waze (נגזר מהכתובת)


# ---- פאנל אדמין (הבעלים רואה הכל) ----


class AdminUserRow(BaseModel):
    """שורת משתמש בפאנל האדמין — כולל ספירת אירועים ומוזמנים."""

    id: int
    email: str
    display_name: str
    is_admin: bool
    account_type: str = "couple"
    disabled: bool = False
    events_count: int
    guests_count: int
    created_at: datetime


class AdminUserUpdate(BaseModel):
    """עריכת פרטי משתמש ע"י אדמין — כל השדות אופציונליים (עדכון חלקי)."""

    display_name: Optional[str] = None
    phone: Optional[str] = None
    account_type: Optional[Literal["couple", "planner", "venue"]] = None
    is_admin: Optional[bool] = None


class AdminLoginRow(BaseModel):
    """רשומת התחברות בהיסטוריית המשתמש."""

    id: int
    ip: Optional[str]
    user_agent: Optional[str]
    created_at: datetime


class AdminPasswordReset(BaseModel):
    """בקשת איפוס סיסמה ע"י אדמין. סיסמה מפורשת אופציונלית — אחרת נוצרת זמנית."""

    new_password: Optional[str] = None

    @field_validator("new_password")
    @classmethod
    def _min_len(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return validate_password_strength(v)


class AdminPasswordResetResult(BaseModel):
    """תשובת האיפוס — הסיסמה הזמנית שהאדמין ימסור למשתמש."""

    user_id: int
    email: str
    temporary_password: str


class AdminEventRow(BaseModel):
    """שורת אירוע בפאנל האדמין — כולל בעלים וספירת מוזמנים."""

    id: int
    groom_name: str
    bride_name: str
    venue_name: str
    owner_id: Optional[int]
    owner_email: Optional[str]
    guests_count: int


class AdminUserDetail(BaseModel):
    """כרטיס משתמש מלא בפאנל האדמין — פרופיל + אירועים + היסטוריית התחברות."""

    id: int
    email: str
    display_name: str
    phone: str = ""
    is_admin: bool
    account_type: str = "couple"
    disabled: bool = False
    created_at: datetime
    events: list[AdminEventRow]
    recent_logins: list[AdminLoginRow]
    login_count: int


class AdminImpersonateResult(BaseModel):
    """תוצאת התחזות אדמין: טוקן זמני שמאפשר לראות את המערכת בעיני המשתמש."""

    token: str
    user_id: int
    email: str
    display_name: str


class AdminAccountCreate(BaseModel):
    """יצירת חשבון מפיק/אולם ע"י אדמין — לתפקידים אלו אין הרשמה עצמאית,

    האדמין הוא שיוצר את החשבון (עם סיסמה זמנית), בדיוק כמו איפוס סיסמה.
    """

    email: str
    display_name: str
    account_type: Literal["planner", "venue"]
    new_password: Optional[str] = None

    @field_validator("email")
    @classmethod
    def _email_valid(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if "@" not in v or len(v) < 5:
            raise ValueError("כתובת אימייל לא תקינה")
        return v

    @field_validator("display_name")
    @classmethod
    def _name_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("שם תצוגה הוא שדה חובה")
        return v

    @field_validator("new_password")
    @classmethod
    def _min_len(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return validate_password_strength(v)


class AdminAccountCreateResult(BaseModel):
    """תשובת יצירת החשבון — הסיסמה הזמנית שהאדמין ימסור למשתמש."""

    user_id: int
    email: str
    account_type: str
    temporary_password: str


class AdminVenueRow(BaseModel):
    """שורת אולם במאגר האדמין — כולל קישורי ניווט מוכנים לפי הכתובת."""

    id: int
    name: str
    address: str = ""
    city: str = ""
    usage_count: int
    maps_link: str
    waze_link: str
    created_at: datetime


class AdminVenueUpdate(BaseModel):
    """עדכון פרטי אולם — כל השדות אופציונליים (עדכון חלקי)."""

    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None


class AdminVenueMerge(BaseModel):
    """איחוד אולם כפול לתוך אולם יעד — המקור נמחק, השימושים עוברים ליעד."""

    target_id: int


# ---- לוח הבקרה של האדמין (סקירת מערכת) ----


class AdminDashboardEvent(BaseModel):
    """אירוע בתצוגת "האירועים האחרונים" בלוח הבקרה."""

    id: int
    couple: str                    # "חתן · כלה"
    venue_name: str
    owner_email: Optional[str]
    event_date: str                # YYYY-MM-DD (יכול להיות ריק)
    guests_count: int
    days_until: Optional[int]      # ימים עד האירוע; None אם אין תאריך/עבר


class AdminDashboardPoint(BaseModel):
    """נקודה בגרף הרשמות לפי יום."""

    label: str                     # DD/MM
    count: int


class AdminDashboardAlert(BaseModel):
    """התראת מערכת נגזרת (לא קריטית — עזרה לאדמין לשים לב)."""

    level: str                     # info / warn
    text: str


class AdminDashboard(BaseModel):
    """כל הנתונים ללוח הבקרה של האדמין במסך אחד."""

    total_events: int
    upcoming_events: int
    total_users: int
    total_venues: int
    total_guests: int
    whatsapp_sent: int
    recent_events: list[AdminDashboardEvent]
    signups: list[AdminDashboardPoint]
    alerts: list[AdminDashboardAlert]


# ---- שיתוף גישה לאירוע (מפיק/אולם) ----

# הרשאות אפשריות לפי תפקיד — משמש גם לוולידציה בצד השרת וגם לתצוגה בפרונט.
PLANNER_PERMISSIONS = ["view_guests", "edit_guests", "manage_seating", "send_messages", "view_reports"]
VENUE_PERMISSIONS = ["view_event", "view_seating", "edit_seating", "manage_venue_data"]


class EventMemberCreate(BaseModel):
    """הוספת חבר-אירוע (מפיק/אולם) ע"י בעל האירוע — לפי אימייל מדויק."""

    email: str
    permissions: list[str] = []

    @field_validator("email")
    @classmethod
    def _email_valid(cls, v: str) -> str:
        return (v or "").strip().lower()


class EventMemberUpdate(BaseModel):
    """עדכון רשימת ההרשאות של חבר-אירוע קיים."""

    permissions: list[str]


class EventMemberRead(BaseModel):
    """שורת חבר-אירוע לתצוגה בעמוד ניהול הגישה של בעל האירוע."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    email: str
    display_name: str
    role: str
    permissions: list[str]
    status: str


# ---- דף אישור הגעה ציבורי (קישור אישי /confirm/{token}) ----


class ConfirmEventInfo(BaseModel):
    """פרטי האירוע שמוצגים למוזמן בדף האישור (מידע ציבורי בלבד)."""

    groom_name: str
    bride_name: str
    venue_name: str
    venue_address: str = ""            # כתובת האולם — להצגה וניווט
    maps_link: str = ""               # קישור ניווט Google Maps (נגזר מהכתובת)
    waze_link: str = ""               # קישור ניווט Waze (נגזר מהכתובת)
    event_date: str = ""
    event_time: str = ""
    invite_image: Optional[str] = None  # תמונת ההזמנה שהזוג העלה (data URL / כתובת)


class ConfirmGuestPublic(BaseModel):
    """מה שמוזמן רואה בקישור האישי — רק הנתונים שלו, לא של אחרים."""

    full_name: str
    party_size: int
    rsvp_status: str
    confirmed_count: Optional[int]
    guest_note: Optional[str]
    event: ConfirmEventInfo


class ConfirmSubmit(BaseModel):
    """תשובת המוזמן בדף האישור."""

    coming: bool                       # True => מגיע, False => לא מגיע
    maybe: bool = False                # True => "אולי" (גובר על coming)
    count: Optional[int] = None        # כמה אנשים מגיעים (אם מגיע)
    note: Optional[str] = None         # הערה חופשית (נגישות/תינוק וכו')


# ---- יומן אבטחה (audit log) ----


class AuditLogRow(BaseModel):
    """שורת יומן אבטחה לתצוגה בדשבורד המנהל."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    detail: str
    ip: Optional[str] = None
    created_at: datetime


# ---- מנוע אוטומציות לאישורי הגעה (RSVP Automation Engine) ----

# חמשת סוגי הטריגרים הנתמכים (עקבי עם AutomationRule.trigger_type).
TriggerType = Literal[
    "event_created",
    "invitation_sent",
    "no_response",
    "before_event_date",
    "guest_confirmed",
]
# קהלי היעד (עקבי עם AutomationRule.target_group).
TargetGroup = Literal[
    "all",
    "pending",
    "confirmed",
    "declined",
    "maybe",
    "side_groom",
    "side_bride",
    "group",
]
# סוגי תבנית — לתיוג/סינון בלבד.
TemplateKind = Literal["invitation", "reminder", "pre_event", "thank_you", "custom"]


class AutomationTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: str
    body: str
    created_at: datetime


class AutomationTemplateCreate(BaseModel):
    name: str = ""
    kind: TemplateKind = "custom"
    body: str = ""

    @field_validator("name")
    @classmethod
    def _name_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("שם התבנית הוא שדה חובה")
        return v


class AutomationTemplateUpdate(BaseModel):
    name: Optional[str] = None
    kind: Optional[TemplateKind] = None
    body: Optional[str] = None


# ---- ספריית ההודעות האנושית (קריאה בלבד, מוגשת מהקוד) ----

class LibraryMessage(BaseModel):
    id: int                # אינדקס יציב בתוך הספרייה (לבחירה בממשק)
    stage: str             # invitation / first_reminder / ... (שלב במסלול)
    category: str          # מפתח קטגוריה (invitation / reminder / ...)
    style: str             # מפתח סגנון (elegant / romantic / ...)
    name: str              # שם קצר שהזוג רואה
    body: str              # גוף ההודעה עם טוקנים ([שם פרטי] וכו')


class LibraryMeta(BaseModel):
    key: str               # מפתח טכני (invitation / elegant / ...)
    label: str             # תווית בעברית לתצוגה


class MessageLibrary(BaseModel):
    messages: list[LibraryMessage]
    categories: list[LibraryMeta]
    styles: list[LibraryMeta]


class AutomationRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_name: str
    trigger_type: str
    delay_days: int
    target_group: str
    target_group_value: str
    template_id: Optional[int]
    action_kind: str = "send"
    active: bool
    created_at: datetime


class AutomationRuleCreate(BaseModel):
    rule_name: str = ""
    trigger_type: TriggerType = "no_response"
    delay_days: int = 0
    target_group: TargetGroup = "pending"
    target_group_value: str = ""
    template_id: Optional[int] = None
    active: bool = True

    @field_validator("rule_name")
    @classmethod
    def _name_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("שם החוק הוא שדה חובה")
        return v

    @field_validator("delay_days")
    @classmethod
    def _delay_nonneg(cls, v: int) -> int:
        if v < 0:
            raise ValueError("מספר הימים לא יכול להיות שלילי")
        return v


class AutomationRuleUpdate(BaseModel):
    rule_name: Optional[str] = None
    trigger_type: Optional[TriggerType] = None
    delay_days: Optional[int] = None
    target_group: Optional[TargetGroup] = None
    target_group_value: Optional[str] = None
    template_id: Optional[int] = None
    active: Optional[bool] = None


class DueAction(BaseModel):
    """פעולה שהגיע זמנה — שורה בתור לאישור (עדיין לא נשלחה)."""

    rule_id: int
    rule_name: str
    trigger_type: str
    guest_id: int
    guest_name: str
    phone: str
    channel: str = "whatsapp"
    preview: str            # תצוגה מקדימה של ההודעה אחרי מילוי המשתנים


class DueQueue(BaseModel):
    actions: list[DueAction]
    mode: str               # mock / live


class RunDueRequest(BaseModel):
    """אישור שליחה של התור. ריק => לשלוח את כל התור; אחרת רק החוקים שסומנו."""

    rule_ids: Optional[list[int]] = None


class RunDueResult(BaseModel):
    mode: str
    sent: int
    failed: int
    skipped: int
    detail: Optional[str] = None


class TimelineEvent(BaseModel):
    """אירוע בודד ב-Timeline של מוזמן (הודעה יוצאת/נכנסת)."""

    kind: str               # invitation/reminder/pre_event/thank_you/reply/custom
    direction: str          # outbound/inbound
    channel: str = "whatsapp"
    text: str
    status: str
    created_at: datetime


class GuestTimeline(BaseModel):
    guest_id: int
    guest_name: str
    rsvp_status: str
    events: list[TimelineEvent]


class SmartFollowUp(BaseModel):
    """המלצת מעקב חכם (טקסט חופשי + חומרה) — נגזרת מהמצב הנוכחי."""

    severity: str           # info / warn
    text: str


class AutomationDashboard(BaseModel):
    total_guests: int
    invited: int            # כמה קיבלו הזמנה (הודעה יוצאת מסוג invitation)
    confirmed: int
    declined: int
    maybe: int
    pending: int
    in_reminder_process: int  # ממתינים שכבר קיבלו לפחות תזכורת אחת
    days_to_event: Optional[int] = None
    active_rules: int
    due_now: int            # כמה פעולות ממתינות בתור לשליחה כרגע
    recommendations: list[SmartFollowUp]


# --- ברירות מחדל גלובליות של VEYA (ספריית תבניות + מסלול קבוע, ניהול אדמין) ---

# invitation / first_reminder / second_reminder / thank_you / before_event
VeyaStage = Literal[
    "invitation", "first_reminder", "second_reminder", "thank_you", "before_event"
]


class VeyaTemplateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stage: str
    name: str
    body: str
    is_default: bool
    active: bool
    sort_order: int
    created_at: datetime


class VeyaTemplateCreate(BaseModel):
    stage: VeyaStage = "invitation"
    name: str = ""
    body: str = ""
    is_default: bool = True
    active: bool = True
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def _name_required(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("שם התבנית הוא שדה חובה")
        return v


class VeyaTemplateUpdate(BaseModel):
    stage: Optional[VeyaStage] = None
    name: Optional[str] = None
    body: Optional[str] = None
    is_default: Optional[bool] = None
    active: Optional[bool] = None
    sort_order: Optional[int] = None


class VeyaWorkflowStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step_order: int
    name: str
    offset_days: int
    action_kind: str        # send / phone_followup
    template_stage: str
    active: bool
    created_at: datetime


class VeyaWorkflowStepUpdate(BaseModel):
    name: Optional[str] = None
    offset_days: Optional[int] = None
    action_kind: Optional[str] = None
    template_stage: Optional[str] = None
    active: Optional[bool] = None

    @field_validator("offset_days")
    @classmethod
    def _offset_nonneg(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("מספר הימים לא יכול להיות שלילי")
        return v


class AdminMessageStat(BaseModel):
    """ספירת הודעות WhatsApp יוצאות לפי סוג — לתצוגת 'כמה נשלח' בפאנל האדמין."""
    kind: str
    count: int


class AdminMessageStats(BaseModel):
    """סיכום נפח הודעות במערכת: יוצאות (לפי סוג) ונכנסות."""
    total_outbound: int
    total_inbound: int
    by_kind: list[AdminMessageStat]


class AdminAuditRow(BaseModel):
    """שורת יומן פעולות אדמין — מי, מתי, איזו פעולה, ותיאור."""
    id: int
    action: str
    detail: str = ""
    ip: Optional[str] = None
    event_id: Optional[int] = None
    user_id: Optional[int] = None
    actor_email: Optional[str] = None
    actor_name: Optional[str] = None
    created_at: datetime


# --- מסלול אישורי-ההגעה של האירוע (סטטוס למסך הזוג) ---


class RsvpTrackPhoneRow(BaseModel):
    """מוזמן שנכנס לרשימת המעקב הטלפוני (ממתין, אחרי כל התזכורות)."""

    guest_id: int
    guest_name: str
    phone: str
    side: str = ""


class RsvpTrackStepRow(BaseModel):
    """שלב במסלול + כמה מוזמנים כבר עברו אותו בפועל."""

    rule_id: int
    name: str
    offset_days: int
    action_kind: str        # send / phone_followup
    active: bool
    done: int               # כמה מוזמנים כבר קיבלו/עברו את השלב הזה


class RsvpTrackStatus(BaseModel):
    active: bool
    started_at: Optional[datetime] = None
    mode: str               # mock / live
    total_guests: int
    invited: int
    confirmed: int
    declined: int
    maybe: int
    pending: int
    in_phone_followup: int  # ממתינים שנכנסו לרשימת המעקב הטלפוני
    phone_list: list[RsvpTrackPhoneRow]
    steps: list[RsvpTrackStepRow]
    due_now: int            # כמה פעולות במסלול הבשילו וממתינות כרגע


class InvitationSendPreview(BaseModel):
    """ספירה מקדימה לדיאלוג האישור לפני שליחת הזמנות ידנית."""

    total_guests: int
    can_receive: int         # בעלי טלפון תקין (כמה יכולים לקבל)
    not_yet_sent: int        # טלפון תקין ועדיין לא נשלחה אליהם הזמנה
    already_sent: int        # כבר קיבלו הזמנה
    missing_phone: int       # אין מספר טלפון
    invalid_phone: int       # מספר לא תקין
    already_activated: bool  # מסלול אישורי-ההגעה כבר הופעל (לזיהוי שליחה כפולה)


class RsvpTrackActivateRequest(BaseModel):
    """בקשת שליחה: היקף הנמענים. ברירת מחדל — רק מי שעדיין לא קיבל."""

    # new = רק מי שעדיין לא קיבל הזמנה ; all = שליחה מחדש לכולם.
    scope: str = "new"
    # אם ניתן — שולחים רק למוזמנים אלה (ניסיון חוזר לנכשלים בלבד). גובר על scope.
    retry_ids: Optional[list[int]] = None
    # בחירת נמענים מפורשת מהזוג (רשימת סימון בדיאלוג). גובר על scope ועל retry_ids.
    guest_ids: Optional[list[int]] = None


class RsvpTrackActivateResult(RsvpTrackStatus):
    templates_created: int
    rules_created: int
    invitations_sent: int
    skipped_missing: int = 0   # דולגו — אין מספר טלפון
    skipped_invalid: int = 0   # דולגו — מספר לא תקין
    failed: int = 0            # השליחה נכשלה (תקלת ספק)
    failed_ids: list[int] = []  # מזהי מוזמנים שנכשלו — לניסיון חוזר
    newly_activated: bool = False  # האם הקריאה הזו הדליקה את הטיימר לראשונה


class RsvpTrackAdvanceResult(RsvpTrackStatus):
    """תוצאת התקדמות המסלול — כמה פעולות עובדו בקריאה הזו (0 אם אין חדש)."""

    sent: int               # הודעות WhatsApp שנשלחו (mock)
    phoned: int             # מוזמנים שנכנסו לרשימת המעקב הטלפוני
    failed: int


# ---- Timeline של אישורי-ההגעה (חישוב לאחור מיום ההתחייבות) ----


class TimelineAction(BaseModel):
    """פעולה בודדת ביום מסוים בלוח הזמנים (הודעה / סבב שיחות / ציון דרך)."""

    type: str               # whatsapp_first/reminder/call_round/commitment/day_before/day_of
    icon: str               # אימוג'י לתצוגה
    label: str
    audience: str           # "כל המוזמנים" / "מי שעדיין לא אישר" / ...
    audience_count: int
    moved_from_weekend: bool = False


class TimelineDay(BaseModel):
    """יום בודד בלוח הזמנים היומי, עם אפס או יותר פעולות."""

    date: str               # DD/MM/YYYY
    iso: str                # YYYY-MM-DD (מפתח/מיון)
    weekday: str            # שם היום בעברית
    is_today: bool
    is_tomorrow: bool
    is_past: bool
    is_commitment: bool
    actions: list[TimelineAction]


class RsvpTimelineView(BaseModel):
    """תצוגת לוח הזמנים המלאה לזוג — 'מה קורה היום/מחר ועד יום ההתחייבות'."""

    configured: bool                        # האם יש תאריך אירוע + יום התחייבות
    event_date: str = ""
    commit_days_before: Optional[int] = None
    commitment_date: Optional[str] = None
    rsvp_start_date: Optional[str] = None
    days_to_commitment: Optional[int] = None
    compressed: bool = False                # מצב זמן קצר (מסלול מכווץ)
    total_guests: int = 0
    pending_count: int = 0
    confirmed_count: int = 0
    today: str = ""
    today_summary: str = ""
    tomorrow_summary: str = ""
    current_stage: Optional[str] = None
    next_action_date: Optional[str] = None
    next_action_label: Optional[str] = None
    days: list[TimelineDay] = []
