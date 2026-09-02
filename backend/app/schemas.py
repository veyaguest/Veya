"""סכימות Pydantic — ולידציה של קלט/פלט ל-API של המוזמנים."""
import re
from datetime import datetime
from typing import Optional

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.validators import normalize_israeli_phone

Side = Literal["groom", "bride", "shared"]
# סוג האירוע — קובע את השפה הדינמית. חתונה היא ברירת המחדל (תאימות אחורה).
EventType = Literal[
    "wedding", "bar_mitzvah", "bat_mitzvah", "henna", "brit", "brita", "business",
]
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
    # notes_raw = הערה פנימית (לא משפיעה על ההושבה)
    notes_raw: Optional[str] = None
    # seating_notes = הערות הושבה — המקור היחיד שמנוע ההושבה קורא מהבעלים
    seating_notes: Optional[str] = None
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
    seating_notes: Optional[str] = None
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
    seating_notes: Optional[str] = None
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
    # היסטורי — Deprecated. עד 2026-08-19 שלט האם לסנן למי שאישר הגעה; מאז
    # ה-Audit RSVP↔הושבה ``/seating/generate`` תמיד מסנן ל"מגיע" בלבד (ראו
    # ``routers/seating.py::generate``), בלי קשר לערך הזה. נשאר בסכמה רק כדי
    # שלא לשבור קריאות ישנות ששולחות אותו.
    only_confirmed: bool = False
    persist: bool = False                     # לשמור table_number חזרה על המוזמנים
    # מצב "השלמת מקומות": מי שכבר משובץ נשאר בדיוק במקומו, והמנוע רק מוצא
    # שולחן למי שאין לו. מחליף את מנוע ה"מילוי" הנפרד שהיה בצד הלקוח, כך
    # שיש מנוע ניקוד אחד בלבד לשני המצבים.
    only_unassigned: bool = False
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


class SeatingUndoResult(BaseModel):
    """תוצאת "החזרת הסידור הקודם"."""

    restored_guests: int
    can_undo: bool


class SeatingUndoState(BaseModel):
    """האם יש סידור קודם לשחזור, ומתי נשמר."""

    can_undo: bool
    at: Optional[str] = None


class SeatingViolation(BaseModel):
    """הפרה בודדת שנמצאה בבדיקת התקינות שאחרי השיבוץ."""

    kind: str                       # capacity / forbidden_pair / unseated
    table_number: Optional[int] = None
    guest_ids: list[int] = []
    names: list[str] = []
    text: str                       # ניסוח בעברית, מוכן לתצוגה


class SeatingResponse(BaseModel):
    tables: list[SeatingTableRead]
    total_people: int
    num_tables: int
    seats_per_table: int
    score: int
    hard_ok: bool
    unseated: list[int]
    persisted: bool
    # דוח בדיקת התקינות שרץ **אחרי** השיבוץ. ריק = ההושבה תקינה.
    violations: list[SeatingViolation] = []
    # האם קיים סידור קודם לשחזור ("החזרת הסידור הקודם").
    can_undo: bool = False
    # הסברי שיבוץ למוזמנים שהיו להם העדפה מההערות (רשימה יכולה להיות ריקה).
    explanations: list[SeatingExplanation] = []


# ---- פרסור הערות + הבהרות (שלב 4) ----


class NoteSplitCandidate(BaseModel):
    """הערה פנימית שנראית כמו העדפת ישיבה, אצל מוזמן ששדה ההושבה שלו ריק."""

    guest_id: int
    full_name: str
    notes_raw: str


class NoteSplitSuggestions(BaseModel):
    candidates: list[NoteSplitCandidate] = []


class NoteSplitApply(BaseModel):
    guest_ids: list[int] = []


class NoteSplitResult(BaseModel):
    moved: int


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
    # קטגוריה לקיבוץ בעורך ההודעות (guest / event / when_where / links / extra).
    # שדה תוספתי: לקוח ותיק שלא מכיר אותו פשוט מתעלם ממנו, כך שאפשר לפרוס
    # שרת לפני פרונט בלי לשבור את המסך. התוויות בעברית חיות ב-strings/he.ts.
    cat: str = ""


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


# ---- תקשורת עם אורחים (רצף ההודעות הקבוע — EventMessage/MessageDefault) ----

MessageType = Literal[
    "invitation", "reminder_1", "reminder_2",
    "final_reminder", "event_day", "thank_you",
]
TargetAudience = Literal["all", "pending", "confirmed", "declined"]


class EventMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message_type: str
    title: str
    content: str
    variables_supported: list[str]
    is_active: bool
    trigger_offset_days: int
    target_audience: str
    updated_at: datetime


class EventMessageUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    is_active: Optional[bool] = None
    trigger_offset_days: Optional[int] = None
    target_audience: Optional[TargetAudience] = None


class CommunicationPreview(BaseModel):
    preview: str  # ריק אם אין עדיין תוכן


class CommunicationDue(BaseModel):
    """שורה בתור לאישור של רצף התקשורת (עדיין לא נשלחה)."""

    event_message_id: int
    message_type: str
    guest_id: int
    guest_name: str
    phone: str
    preview: str


class CommunicationDueQueue(BaseModel):
    mode: str
    actions: list[CommunicationDue]


class CommunicationSendRequest(BaseModel):
    """אישור שליחה של התור. ריק => לשלוח את כל התור; אחרת רק הצירופים שסומנו
    (event_message_id, guest_id)."""
    items: Optional[list[tuple[int, int]]] = None


class CommunicationSendResult(BaseModel):
    mode: str
    sent: int
    failed: int
    detail: Optional[str] = None


class CommunicationManualSend(BaseModel):
    """שליחה ידנית של הודעה לקהל נבחר (היום: הודעת "אירוע נדחה").

    ``guest_ids`` גובר על ``audience`` — כך אפשר גם "לכולם לפי סטטוס" וגם
    "רק לאלה שסימנתי", בלי שני נתיבים.
    """

    # all / pending / confirmed / declined
    audience: str = "all"
    guest_ids: Optional[list[int]] = None


class CommunicationManualSendResult(BaseModel):
    """תוצאת שליחה ידנית — כולל מי דולג ולמה, כדי שהזוג יידע מה קרה בפועל."""

    mode: str
    sent: int
    failed: int
    #: מוזמנים ללא מספר טלפון או עם מספר שאינו תקין — לא נשלחה אליהם הודעה.
    skipped_no_phone: int = 0
    detail: Optional[str] = None


class MessageDefaultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    message_type: str
    title: str
    content: str
    variables_supported: list[str]
    is_active: bool
    updated_at: datetime


class MessageDefaultUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    is_active: Optional[bool] = None
    variables_supported: Optional[list[str]] = None


class MessageDefaultsBackfillResult(BaseModel):
    events_processed: int
    messages_created: int


class MessageDefaultOptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    message_type: str
    option_number: int
    tone: str
    title: str
    content: str
    variables_supported: list[str]
    is_active: bool
    updated_at: datetime


class MessageDefaultOptionCreate(BaseModel):
    event_type: str
    message_type: str
    tone: str = ""
    title: str = ""
    content: str = ""
    variables_supported: list[str] = []


class MessageDefaultOptionUpdate(BaseModel):
    tone: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    variables_supported: Optional[list[str]] = None
    is_active: Optional[bool] = None


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
    confirmed_people: int      # כמה שאישרו בפועל (confirmed_count אם קיים, אחרת party_size)
    # RSVP
    confirmed: int
    declined: int
    maybe: int                 # סימנו "עדיין לא בטוחים"
    pending: int
    # כמה אנשים מיוצגים בכל קבוצת סטטוס (סכום party_size) — לתצוגה בלבד
    # ("לא מגיעים: 3 מוזמנים, 7 אנשים"), לא חלק מהספירה הפעילה בהושבה.
    declined_people: int = 0
    maybe_people: int = 0
    pending_people: int = 0
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
    # האם כבר הועלתה סקיצת אולם — לצ'ק-ליסט של כרטיס "הושבה בקליק" בתמונת המצב
    has_hall_sketch: bool = False
    # פרטי אירוע
    groom_name: str
    bride_name: str
    venue_name: str


class EventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: EventType = "wedding"
    groom_name: str
    bride_name: str
    # שורות ההורים כמזמינים — נדרשות לנוסחי ההזמנה הדתי/חב"ד/חרדי, שבהם
    # ההורים מזמינים ולא בעלי האירוע. ריק = הנוסח נופל בעדינות לפתיח בלבד.
    groom_parents_line: str = ""
    bride_parents_line: str = ""
    venue_name: str
    venue_address: str = ""
    event_date: str = ""
    event_time: str = ""
    invite_image: Optional[str] = None
    # מועד סגירת הרשימה: כמה ימים לפני האירוע (1–10). None = טרם נבחר.
    venue_commit_days_before: Optional[int] = None
    # האם הבחירה כבר ננעלה (נבחרה בעבר) — הפרונט מציג אותה כקריאה-בלבד.
    venue_commit_locked: bool = False
    # שעת שליחה — "HH:MM", שעון ישראל, 10:00–19:00 (ראו app/communication.py).
    # rsvp_send_time חל על כל מסלול אישורי ההגעה; thank_you_send_time נפרד.
    rsvp_send_time: str = "16:00"
    thank_you_send_time: str = "16:00"

    # ---- נוהל דחייה ----
    # מחזור האירוע. 1 = האירוע המקורי; 2 ומעלה = אחרי דחייה.
    cycle_number: int = 1
    # באיזה שלב האירוע נמצא — הערך שמזין את באנר המצב במסך. הערכים מוגדרים
    # ב-``app/postponement_service.py`` (STAGE_*). מחושב בשרת בכוונה: מקור
    # אמת אחד, כדי שהמסך לא יסיק מצב בעצמו מתוך צירוף של דגלים.
    event_stage: str = "normal"
    # האם פרטי הליבה נעולים כרגע לעריכה.
    edit_locked: bool = True
    # אילו שדות נעולים — כדי שהמסך יציג בדיוק אותם כקריאה-בלבד ולא ינחש.
    locked_fields: list[str] = []


class EventUpdate(BaseModel):
    event_type: Optional[EventType] = None
    groom_name: Optional[str] = None
    bride_name: Optional[str] = None
    groom_parents_line: Optional[str] = None
    bride_parents_line: Optional[str] = None
    venue_name: Optional[str] = None
    venue_address: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    invite_image: Optional[str] = None
    # בחירה חד-פעמית (1–10). ניתן להגדיר רק פעם אחת; ניסיון לשנות ערך קיים נדחה.
    venue_commit_days_before: Optional[int] = None
    # ולידציית פורמט+טווח מתבצעת ב-router (app/communication.py:validate_send_time),
    # לא כאן — בדיוק כמו venue_commit_days_before ממש למעלה.
    rsvp_send_time: Optional[str] = None
    thank_you_send_time: Optional[str] = None


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
    # גודל עצמאי (פיקסלים) — None = ללא override, גודל נגזר מ-table_type+density
    # כרגיל. מוגדר רק לשולחנות שיובאו מסקיצת AI, כדי לשמר את הגודל/הפרופורציה
    # שזוהו בסקיצה במקום גודל אחיד לכל השולחנות מאותו סוג.
    width: Optional[float] = Field(default=None, gt=0)
    height: Optional[float] = Field(default=None, gt=0)
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


class HallSketchTransform(BaseModel):
    """מיקום/גודל/סיבוב/שקיפות/נעילה של שכבת הסקיצה על הלוח (world coords).

    None ברמת ``HallState``/``SaveHallRequest`` => תאימות אחורה: מפות ישנות
    ממשיכות להיראות בדיוק כמו היום (רקע מלא, ללא transform עצמאי) — ראה
    ``routers/hall.py: get_hall`` שממלא ברירת מחדל תואמת.
    """

    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    rotation: float = 0
    opacity: float = Field(default=0.5, ge=0, le=1)
    locked: bool = False
    hidden: bool = False


class DetectedHallElement(BaseModel):
    """אלמנט אחד שזוהה ע"י ניתוח AI Vision לסקיצה — לפני שהמשתמש אישר.

    קואורדינטות מנורמלות [0,1] יחסית לתמונת הסקיצה (לא לפיקסלים של הלוח) —
    הצד הלקוח ממפה אותן לקואורדינטות world לפי ``hall_sketch_transform``
    ברגע האישור בלבד (לא לפני).
    """

    type: str            # round_table|square_table|rectangle_table|knights_table|bar|
                          # dance_floor|stage|entrance|pillar|wall|obstacle|other_area
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)
    rotation: float = 0
    capacity: Optional[int] = Field(default=None, ge=1, le=60)
    # מספר השולחן כפי שהוא כתוב בסקיצה עצמה (None = לא זוהה מספר, ואז הלקוח
    # ממספר מרחבית — ראה assignTableNumbers ב-hallSketchGeometry.ts).
    table_number: Optional[int] = Field(default=None, ge=1, le=999)
    confidence: float = Field(ge=0, le=1)
    label: str = ""


class SketchAnalyzeResponse(BaseModel):
    """תשובת ``POST /hall/sketch/analyze`` — תצוגה מקדימה בלבד, שום דבר לא נשמר."""

    elements: list[DetectedHallElement]


class SketchAnalyzeRequest(BaseModel):
    image: str  # data URL (base64) — תמונה או PDF


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
    sketch_transform: Optional[HallSketchTransform] = None  # מיקום שכבת הסקיצה
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
    width: Optional[float] = Field(default=None, gt=0)
    height: Optional[float] = Field(default=None, gt=0)
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
    sketch_transform: Optional[HallSketchTransform] = None  # None => לא לשנות

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


# ── ולידציה של פרטי חשבון (שם + טלפון) ──────────────────────────────────────
# מקור אמת יחיד: אותם כללים בדיוק חלים בהרשמה (``UserCreate``), בהשלמת פרטים
# ובעדכון פרופיל (``ProfileUpdate``) — כדי שלא ייווצר מצב שבו אפשר "להתחמק"
# דרך מסך אחד. ההודעות בעברית טבעית, לא טכנית: המשתמש צריך להבין מה לתקן,
# לא לקרוא את שם השדה בקוד.


def validate_account_name(v: str) -> str:
    """שם מלא של בעל/ת החשבון — חובה, ולא רווחים בלבד."""
    v = (v or "").strip()
    if not v:
        raise ValueError("צריך למלא שם מלא")
    if len(v) < 2:
        raise ValueError("השם קצר מדי — אפשר למלא שם מלא")
    return v


def validate_account_phone(v: str) -> str:
    """טלפון של בעל/ת החשבון — חובה, ובפורמט ישראלי תקין.

    עוטף את ``normalize_israeli_phone`` (מקור האמת לפורמט, משותף עם טלפוני
    המוזמנים) ומחליף את הודעת השגיאה הטכנית שלו בניסוח שאפשר לפעול לפיו.
    """
    raw = (v or "").strip()
    if not raw:
        raise ValueError("צריך למלא מספר טלפון")
    try:
        return normalize_israeli_phone(raw)
    except ValueError:
        raise ValueError("מספר הטלפון לא נראה תקין. אפשר לכתוב אותו כך: 050-1234567")


class UserCreate(BaseModel):
    email: str
    password: str
    # שם וטלפון הם שדות חובה: בלעדיהם אי אפשר לפנות לזוג, ובלעדיהם גם
    # ההזמנה לניהול משותף לא יודעת בשם מי היא נשלחת. נאכף כאן ולא רק ב-UI.
    display_name: str = ""
    phone: str = ""
    # חובה: תיבת "אני מאשר/ת את תנאי השימוש ואת מדיניות הפרטיות" בהרשמה —
    # לא מסומנת מראש בפרונט, ונאכפת גם כאן (422 אם false), לא רק ב-UI
    # (ראו legal/11-dev-compliance-tasklist.md, Frontend #2 / Backend #1).
    accepted_terms: bool = False
    # אופציונלי: תיבה נפרדת ("אני מעוניין/ת לקבל עדכונים מ-VEYA") — לא חובה
    # ליצירת חשבון, נשמרת כהסכמת שיווק נפרדת אם סומנה.
    accepted_marketing: bool = False

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

    @field_validator("display_name")
    @classmethod
    def _name_required(cls, v: str) -> str:
        return validate_account_name(v)

    @field_validator("phone")
    @classmethod
    def _phone_valid(cls, v: str) -> str:
        return validate_account_phone(v)

    @field_validator("accepted_terms")
    @classmethod
    def _terms_required(cls, v: bool) -> bool:
        if not v:
            raise ValueError("יש לאשר את תנאי השימוש ואת מדיניות הפרטיות כדי ליצור חשבון")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email_lower(cls, v: str) -> str:
        return (v or "").strip().lower()


class GoogleExchangeRequest(BaseModel):
    """טוקן access של Supabase (מה-Frontend, אחרי OAuth של גוגל).

    ה-Backend מוודא אותו מול ה-JWKS הציבורי של Supabase (SUPABASE_URL), מוציא
    ממנו email + user_metadata, ומחזיר טוקן פנימי שלנו (TokenResponse) — משם
    כל המערכת עובדת כרגיל.
    """
    supabase_access_token: str


class ProfileUpdate(BaseModel):
    """עדכון פרטי הפרופיל של המשתמש המחובר (שם תצוגה + טלפון)."""

    display_name: str
    phone: Optional[str] = None

    @field_validator("display_name")
    @classmethod
    def _name_not_empty(cls, v: str) -> str:
        return validate_account_name(v)

    @field_validator("phone")
    @classmethod
    def _phone_valid(cls, v: Optional[str]) -> Optional[str]:
        # None = "לא נשלח שדה טלפון בבקשה" (עדכון חלקי) ולכן לא נבדק. ערך
        # שכן נשלח חייב להיות תקין — כולל מחרוזת ריקה, שנחסמת.
        if v is None:
            return v
        return validate_account_phone(v)


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
    avatar_url: str = ""
    is_admin: bool = False
    # couple (זוג) / planner (מפיק) / venue (אולם) — ציר נפרד מ-is_admin.
    account_type: str = "couple"
    # True אם המשתמש אישר גרסה ישנה של תנאי השימוש/מדיניות הפרטיות מהעדכנית
    # (app/legal.py::needs_reconsent) — לא שדה על ה-ORM, מחושב בזמן קריאה
    # ב-routers/auth.py::me, לכן ברירת המחדל כאן היא False בלבד.
    needs_reconsent: bool = False
    # האם כתובת המייל אומתה. נגזר מ-``User.email_verified_at`` (ראו
    # routers/auth.py) — הפרונט צריך רק "כן/לא" כדי להציג "✓ מאומת" ולחסום
    # יצירת אירוע, לא את החותמת עצמה.
    email_verified: bool = True
    # האם חסרים פרטים שחובה למלא לפני יצירת אירוע (שם/טלפון). מאפשר לפרונט
    # להציג השלמת פרטים למשתמשים קיימים בלי לנחש.
    profile_complete: bool = True


class ConsentAccept(BaseModel):
    """אישור/אישור-מחדש מפורש למסמך אחד או יותר (למשל אחרי עדכון תנאים)."""

    types: list[Literal["terms", "privacy", "marketing"]] = ["terms", "privacy"]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserRead


# ---- ניהול אירועים (שלב 8) ----


class EventCreate(BaseModel):
    event_type: EventType = "wedding"
    groom_name: str = ""
    bride_name: str = ""
    venue_name: str = ""


class EventSummary(BaseModel):
    """סיכום אירוע לרשימת האירועים של המשתמש."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: EventType = "wedding"
    groom_name: str
    bride_name: str
    venue_name: str
    #: האם האירוע זכאי לשירות "מתנות באשראי".
    #:
    #: **נגזר בשרת מ-``gift_eligibility.is_eligible``** — מקור האמת היחיד.
    #: הפרונט משתמש בו כדי להסתיר את פריט הניווט ואת המסך; ההסתרה היא
    #: נוחות בלבד, והאכיפה היא ב-``routers/gifts.py`` (404).
    #:
    #: זכאות **אינה** אומרת שהשירות פעיל — לשם כך צריך גם חשבון מאומת.
    gift_service_eligible: bool = False


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
    # phone_agent = "טלפן": איש צוות שמבצע שיחות אישורי הגעה בלבד. תפקיד
    # מגביל — ראו app/roles.py לרשימת מה שהוא חסום ממנו.
    account_type: Optional[Literal["couple", "planner", "venue", "phone_agent"]] = None
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
    event_type: EventType = "wedding"
    hosts: str                     # שמות בעלי האירוע, מותאם לסוג האירוע (event_terms.hosts_names)
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
    # phone_agent (טלפן) נוסף לאותו מסלול בדיוק: גם לו אין הרשמה עצמאית,
    # והאדמין הוא שיוצר לו חשבון עם סיסמה זמנית. אין כאן מנגנון משתמשים
    # או אימות חדש — אותה שורת ``users`` ואותו ``create_access_token``.
    account_type: Literal["planner", "venue", "phone_agent"]
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


# ---- ניהול טלפנים (phone_agent) בפאנל האדמין ----
# אין כאן שום מודל נתונים חדש: המשתמש הוא שורת ``users`` רגילה, ההקצאה היא
# ``call_assignments`` שכבר נבנתה, והמונים נגזרים מ-``call_logs`` ומתור
# השיחות הקיים (``app/call_center.py``) — לא מטבלת סטטיסטיקות חדשה.

class AdminCallerRow(BaseModel):
    """שורת טלפן במסך ניהול הטלפנים."""

    id: int
    email: str
    display_name: str
    phone: str = ""
    disabled: bool = False
    # כמה שיחות תיעד בפועל — ספירה ישירה מ-call_logs.created_by_id.
    calls_made: int = 0
    # כמה שיחות ממתינות לו *עכשיו*, לפי אותו חישוב שמזין את מסך השיחות שלו.
    waiting_tasks: int = 0
    assigned_event_ids: list[int] = []
    created_at: datetime


class AdminCallerEventOption(BaseModel):
    """אירוע שניתן להקצות לטלפן — רק מה שדרוש לבחירה ברשימה."""

    event_id: int
    event_type: EventType = "wedding"
    hosts: str
    venue_name: str = ""
    event_date: str = ""
    # כמה שיחות ממתינות באירוע הזה כרגע (0 = אין סבב פתוח / הכול טופל).
    waiting: int = 0


class AdminCallersPage(BaseModel):
    """כל מה שמסך "ניהול טלפנים" צריך, בבקשה אחת."""

    callers: list[AdminCallerRow] = []
    events: list[AdminCallerEventOption] = []


class AdminCallerAssignmentUpdate(BaseModel):
    """החלפת רשימת האירועים המוקצים לטלפן (רשימה ריקה = תור משותף)."""

    event_ids: list[int] = []


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
    event_type: EventType = "wedding"
    couple: str                    # שמות בעלי האירוע, מותאם לסוג האירוע (event_terms.hosts_names)
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


class AdminEventTypeCount(BaseModel):
    """כמות אירועים מסוג נתון — לפילוח סטטיסטיקות האדמין לפי event_type."""

    event_type: EventType
    label: str                     # תווית עברית לתצוגה (event_terms.label)
    count: int


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
    events_by_type: list[AdminEventTypeCount] = []


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


class ConfirmCalendarLinks(BaseModel):
    """שלוש הדרכים להוסיף את האירוע ליומן (ריקות כשאין תאריך לאירוע).

    ``ics`` הוא **כתובת אמיתית בשרת** ולא קובץ שנבנה בדפדפן — זה מה שגורם
    ל-iPhone לפתוח את מסך "הוספה ליומן" של אפל בלחיצה אחת.
    """

    google: str = ""
    outlook: str = ""
    ics: str = ""


class ConfirmActions(BaseModel):
    """אילו פעולות זמינות למוזמן בעמוד שלו — נקודת ההרחבה של ה-Guest Hub.

    השרת מחליט, לא ה-Frontend: כך פעולה חדשה (מתנה) או פעולה שנפתחת בשלב
    מסוים נדלקת במקום אחד בלבד, בלי לגעת בעמוד. פעולה שאין לה נתונים
    (אירוע בלי כתובת → ניווט) פשוט לא מוצגת, במקום כפתור שלא עושה כלום.
    """

    invitation: bool = False    # יש תמונת הזמנה לצפייה
    calendar: bool = False      # יש תאריך → אפשר להוסיף ליומן
    navigation: bool = False    # יש כתובת → אפשר לנווט
    rsvp: bool = True           # אישור הגעה — פתוח מרגע ההזמנה (ראו confirm.py)
    # מתנה — נפתחת 3 ימי לוח לפני האירוע ונסגרת כשהאירוע מסתיים. החישוב
    # כולו ב-``guest_journey.gift_is_open`` (שעון ישראל), ולא כאן.
    gift: bool = False


class ConfirmEventInfo(BaseModel):
    """פרטי האירוע שמוצגים למוזמן בדף האישור (מידע ציבורי בלבד)."""

    event_type: EventType = "wedding"
    groom_name: str
    bride_name: str
    venue_name: str
    venue_address: str = ""            # כתובת האולם — להצגה וניווט
    maps_link: str = ""               # קישור ניווט Google Maps (נגזר מהכתובת)
    waze_link: str = ""               # קישור ניווט Waze (נגזר מהכתובת)
    apple_maps_link: str = ""         # קישור ניווט Apple Maps (נגזר מהכתובת)
    event_date: str = ""
    event_time: str = ""
    invite_image: Optional[str] = None  # תמונת ההזמנה שהזוג העלה (data URL / כתובת)
    title: str = ""                    # "החתונה של אביב ודנה" — לפי סוג האירוע
    calendar: ConfirmCalendarLinks = ConfirmCalendarLinks()


class ConfirmGuestPublic(BaseModel):
    """מה שמוזמן רואה בקישור האישי — רק הנתונים שלו, לא של אחרים."""

    full_name: str
    party_size: int
    rsvp_status: str
    confirmed_count: Optional[int]
    guest_note: Optional[str]
    event: ConfirmEventInfo
    actions: ConfirmActions = ConfirmActions()


class GiftQuoteRequest(BaseModel):
    """בקשת תמחור למתנה — **רק** הסכום שהזוג אמור לקבל.

    שים לב למה שאין כאן: ``fee`` ו-``total``. הם לא שדות קלט בכלל, ולכן
    אין דרך "לשלוח" אותם. השרת מחשב אותם מחדש בכל בקשה מ-
    ``gift.quote_from_input``, ושדות מיותרים שיישלחו פשוט נזרקים ע"י
    Pydantic. זו ההגנה מפני "לקוח שמחליט כמה הוא משלם".

    הסכום מגיע כאגורות (``int``) ולא כשקלים עשרוניים — כדי שלא ייווצר
    ``float`` בשום נקודה בדרך, כולל ב-JSON.
    """

    gift_amount_agorot: int


class GiftQuoteRead(BaseModel):
    """פירוט התשלום כפי שהאורח רואה אותו. כל הסכומים באגורות."""

    gift_amount_agorot: int    # מה שהזוג יקבל — במלואו, בלי ניכוי
    fee_agorot: int            # עמלת השירות, משולמת ע"י האורח
    total_agorot: int          # מה שהאורח מחויב בפועל
    fee_percent: int           # 4 — נשלח כדי שהטקסט במסך לא יקבע מספר משלו


class GiftCheckoutRequest(BaseModel):
    """שליחת מתנה. ``simulate`` קיים רק כל עוד אין סליקה אמיתית."""

    gift_amount_agorot: int
    giver_name: str = ""
    blessing: Optional[str] = None
    # מפתח למניעת כפילות. הלקוח מייצר אותו פעם אחת לכל ניסיון תשלום,
    # והשרת ממרחב-שם אותו לפי המוזמן (gift_service.build_idempotency_key)
    # כדי ששני מוזמנים לא יתנגשו על אותו ערך.
    idempotency_key: Optional[str] = None
    # בדיקת ה-Flow מקצה לקצה דורשת גם מסלול כישלון. כשתיכנס סליקה אמיתית
    # השדה הזה נמחק — התוצאה תגיע מספק הסליקה, לא מהלקוח.
    simulate: Literal["success", "failure"] = "success"


class GiftCheckoutResult(BaseModel):
    """תוצאת התשלום המדומה."""

    status: Literal["success", "failure"]
    quote: GiftQuoteRead
    reference: str             # מזהה העסקה אצל הספק (מדומה בשלב הזה)
    gift_id: int               # מזהה העסקה אצלנו
    gift_status: str           # pending / paid / failed / cancelled / refunded
    mock: bool = True          # תמיד True בשלב הזה — אין סליקה אמיתית
    message: str = ""


class OwnerGiftRead(BaseModel):
    """שורת מתנה כפי שבעלי האירוע רואים אותה.

    **סכמה ייעודית למסך בעלי האירוע** — השם כולל ``Owner`` בכוונה, כדי
    שלא תיבחר בטעות לנתיב שפונה למוזמן. למוזמן יש סכמות משלו
    (``GiftQuoteRead`` / ``GiftCheckoutResult``), והן *כן* כוללות עמלה —
    כי נותן המתנה הוא זה שמשלם אותה וחייב לראות אותה לפני התשלום.

    **מה שבמפורש לא נמצא כאן:**

    - ``fee_agorot`` / ``total_agorot`` — כמה VEYA גבתה וכמה המוזמן שילם
      בפועל. זה עניין שבין VEYA לנותן המתנה. בעלי האירוע מקבלים את מלוא
      סכום המתנה ולא משלמים עמלה, ולכן אין להם מה לעשות עם המספרים האלה.
    - ``currency`` — לא מוצג במסך (הסכומים מעוצבים ב-₪).
    - ``provider`` / ``provider_transaction_id`` / ``idempotency_key`` /
      ``event_id`` / ``guest_id`` — מידע תפעולי פנימי.

    השדות נשארים כמובן בטבלה ובשימוש הפנימי — זו הגבלת *תצוגה*, לא
    שינוי נתונים.
    """

    id: int                    # למפתח רינדור ברשימה
    sender_name: str
    message: Optional[str] = None
    #: מה שהאירוע מקבל — במלואו, בלי ניכוי.
    #:
    #: **``None`` כל עוד חשבון קבלת המתנות אינו מאומת במלואו.** זו הגנה
    #: בשרת ולא הסתרה ב-UI: לפני ששתי הבדיקות (VEYA + ספק הסליקה) אושרו,
    #: הסכום כלל אינו נכתב לתשובה — ראו ``routers/gifts.py``. הנתון נשאר
    #: כמובן בטבלה; זו הגבלת *החזרה*, לא מחיקה.
    gift_amount_agorot: Optional[int] = None
    status: str                # pending / paid / failed / cancelled / refunded
    created_at: datetime


class GiftsSummary(BaseModel):
    """מסך "מתנות באשראי" של בעלי האירוע — סיכום + רשימה, בקריאה אחת."""

    #: האם הסכומים מוחזרים בתשובה הזו. ``False`` ⇒ שדות הסכום כולם
    #: ``None``, גם בסיכום וגם בכל שורה. השדה קיים כדי שהמסך ידע להציג
    #: הסבר במקום סכום, ולא ינחש מדוע קיבל ``None``.
    amounts_visible: bool = True

    # הסיכום נספר **רק** מעסקאות ``paid`` — לא ``pending``/``failed``/
    # ``cancelled``/``refunded``. נחשב בשרת (routers/gifts.py), לא בפרונט.
    #
    # ``None`` כשהחשבון אינו מאומת במלואו — ראו ``OwnerGiftRead``.
    total_received_agorot: Optional[int] = None
    total_received_display: Optional[str] = None   # "₪1,240" — מוכן לתצוגה
    #: **כמה** מתנות התקבלו — נתון תפעולי של האירוע, לא סכום כספי, ולכן
    #: מוחזר תמיד. בעלי האירוע רשאים לדעת שמתנות מגיעות גם בזמן שהחשבון
    #: עוד בבדיקה.
    paid_count: int
    # כמה עסקאות קיימות בסך הכול (כולל שנכשלו) — נתון של האירוע עצמו,
    # לא מידע מסחרי של VEYA. סכום העמלות שנגבו **אינו** מוחזר כאן.
    total_count: int
    gifts: list[OwnerGiftRead]


class ConfirmSubmit(BaseModel):
    """תשובת המוזמן בדף האישור."""

    coming: bool                       # True => מגיע, False => לא מגיע
    maybe: bool = False                # True => "אולי" (גובר על coming)
    count: Optional[int] = None        # כמה אנשים מגיעים (אם מגיע)
    note: Optional[str] = None         # הערה חופשית (נגישות/תינוק וכו')


# ---- יומן אבטחה (audit log) ----


class AuditLogRow(BaseModel):
    """שורת יומן פעילות לתצוגה בדשבורד המנהל.

    ``actor_name`` נגזר ב-router (לא שדה על ה-ORM) כדי שיומן של אירוע
    בניהול משותף יראה **מי** ביצע כל שינוי — "אביב שינה..." מול "דנה
    שיבצה...". שני המנהלים רואים בדיוק את אותו יומן.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    detail: str
    ip: Optional[str] = None
    created_at: datetime
    actor_name: str = ""
    # מזהה המבצע — כדי שה-Frontend יבחין בין "אתם" למנהל השני ("אביב"),
    # בלי לחשוף שם/מזהה מיותר בפעולה של המשתמש עצמו. ``None`` בפעולות מערכת.
    actor_id: Optional[int] = None


# ---- Timeline של אישורי-ההגעה (המנוע החופשי הישן — כללי/תבניות/תור —
#      הוחלף ב-EventMessage/MessageDefault, ראו למעלה "תקשורת עם אורחים") ----


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
    steps: list[RsvpTrackStepRow]
    due_now: int            # כמה פעולות במסלול הבשילו וממתינות כרגע


class MessageStatusSummary(BaseModel):
    """סיכום מצב ההודעות שנשלחו למוזמנים — לכרטיס "מעקב אחרי המוזמנים"
    במסך ניהול ההודעות. כל מוזמן נספר פעם אחת, לפי ההודעה היוצאת האחרונה
    שנשלחה אליו (ראו ``app/message_status.py: summarize``). לא נתוני RSVP —
    רק מה קרה להודעה עצמה.

    כל שדה מייצג *רק* מה שהמערכת באמת יודעת (ראו "כלל הברזל" בראש
    ``message_status.py``): ``no_valid_number`` הוא ידע מקומי (טלפון חסר/
    בפורמט לא תקין), לא אישור מ-WhatsApp שהמספר לא קיים שם."""

    mode: str              # mock / live
    total_guests: int
    sent: int               # ✓ נשלחו
    delivered: int          # ✓✓ נמסרו למכשיר (webhook — 0 עד חיבור חי)
    read: int               # 👁 נקראו (webhook, לא תמיד זמין)
    failed: int             # ⚠️ לא נמסרו (כולל כשל שהספק לא סיווג בנפרד)
    no_valid_number: int    # 📵 אין מספר תקין (ידע מקומי בלבד — חסר/פורמט שגוי)
    blocked: int            # 🔒 חסומים — ‏[לאימות] ייתכן שלא ניתן לאישור כלל מול Meta
    queued: int              # ⏳ ממתינים לשליחה


class MessageTypeGuestRow(BaseModel):
    """שורת מוזמן ברשימת "מי קיבל את ההודעה" — לכרטיס "מעקב אחרי המוזמנים"
    כשמסננים לפי סוג הודעה נבחר. ``status`` הוא אחד מערכי אוצר המילים של
    ``app/message_status.py``. ``updated_at`` הוא חותמת הזמן האחרונה הידועה
    (נקראה/נמסרה/נשלחה/נוצרה, לפי הזמינה) — None למוזמן שעדיין לא קיבל הודעה
    מהסוג הזה (queued/no_valid_number)."""

    guest_id: int
    guest_name: str
    phone: str
    status: str
    updated_at: Optional[datetime] = None


class MessageTypeStatus(BaseModel):
    """סטטוס ההודעות לפי סוג הודעה נבחר (הזמנה/תזכורת.../תודה) — הכרטיס
    מציג הודעה אחת בכל פעם, לא סיכום מצטבר על פני כל הרצף (ראו
    ``app/message_status.py: summarize_by_type``).

    ``not_sent_yet=True`` אומר שאף הודעה מהסוג הזה עוד לא נשלחה לאף מוזמן —
    במצב הזה שאר השדות מוצגים כ-0 אך אינם משמעותיים; ה-frontend מציג הודעת
    "עדיין לא נשלחה X" במקום רשת סטטיסטיקה, כדי לא לרמוז על שליחה שלא הייתה.
    """

    message_type: str
    not_sent_yet: bool
    total: int               # כמה מוזמנים רלוונטיים (קיבלו + עוד בקהל היעד)
    sent: int
    delivered: int
    read: int
    failed: int
    no_valid_number: int
    blocked: int
    queued: int
    guests: list[MessageTypeGuestRow]


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


# ---- Timeline של אישורי-ההגעה (חישוב לאחור ממועד סגירת הרשימה) ----


class TimelineAction(BaseModel):
    """פעולה בודדת ביום מסוים בלוח הזמנים (הודעה / סבב שיחות / ציון דרך)."""

    type: str               # whatsapp_first/reminder/call_round/day_of/thank_you
    icon: str               # אימוג'י לתצוגה
    label: str
    audience: str           # "כל המוזמנים" / "מי שעדיין לא אישר" / ...
    audience_count: int
    moved_from_weekend: bool = False
    # שורת הסבר נוספת מתחת לפעולה (למשל: סבב השיחות האחרון שגם סוגר את
    # הרשימה). ריק = לא מוצג.
    note: str = ""


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
    """תצוגת לוח הזמנים המלאה לזוג — 'מה קורה היום/מחר ועד מועד סגירת הרשימה'."""

    configured: bool                        # האם יש תאריך אירוע + מועד סגירת רשימה
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


# ---------------------------------------------------------------------------
# Call Center (אדמין) — תור השיחות, נגזר מ-Workflow אישורי ההגעה
# ראו app/call_center.py: אין כאן תאריכים או סטטוסים חדשים, רק תצוגה.
# ---------------------------------------------------------------------------


class CallCenterEventRow(BaseModel):
    """אירוע אחד בתור השיחות של היום."""

    event_id: int
    event_type: str
    hosts: str                  # שמות בעלי האירוע (לפי סוג האירוע)
    venue_name: str = ""
    event_date: str = ""
    event_time: str = ""
    days_until: Optional[int] = None
    round_number: int           # סבב השיחות הפעיל (1, 2, 3...)
    round_label: str            # "סבב שיחות ראשון" וכו' — מ-rsvp_timeline.CYCLE
    round_date: str             # DD/MM/YYYY — התאריך שנקבע ב-Workflow
    waiting: int                # כמה שיחות עוד ממתינות
    done: int                   # כמה כבר טופלו בסבב הזה


class CallCenterOverview(BaseModel):
    """מסך ה-Call Center הראשי: מונים + רשימת האירועים, לטווח נבחר."""

    # today / tomorrow / later — ראו app/call_center.py: SCOPES.
    scope: str = "today"
    total: int                  # סך כל השיחות בטווח הנבחר
    done: int
    waiting: int
    events_needing_attention: int
    events: list[CallCenterEventRow] = []


class CallCenterGuestRow(BaseModel):
    """שורת מוזמן בתור השיחות."""

    guest_id: int
    event_id: int
    event_type: str
    event_hosts: str
    # תאריך האירוע (YYYY-MM-DD כפי שנשמר) — כדי שהמוקדן ידע על מה הוא מדבר
    # בלי לפתוח את כרטיס המוזמן.
    event_date: str = ""
    full_name: str
    phone: str = ""
    party_size: int
    side: str                   # groom/bride/shared
    # הערת המוזמן (למשל "מגיע עם תינוק") — רלוונטית לשיחה עצמה. ההערה
    # הפנימית (``notes_raw``) לא נחשפת כאן, רק בכרטיס המוזמן.
    guest_note: Optional[str] = None
    rsvp_status: str            # pending/maybe בלבד (מי שסגר כבר לא בתור)
    round_number: int
    round_date: str             # DD/MM/YYYY — מתי נוצרה משימת השיחה
    last_outcome: Optional[str] = None       # תוצאת השיחה האחרונה שבוצעה
    last_outcome_label: Optional[str] = None
    callback_at: Optional[datetime] = None   # אם ביקש שיחזרו אליו
    # המוזמן חזר לתור כי הגיע מועד ה-Follow-up שהוא ביקש (ולא כי נפתח סבב
    # חדש) — מסומן בנפרד כדי שהמוקדן ידע שהוא *מחזיר שיחה שהובטחה*.
    is_followup: bool = False
    # כמה פעמים כבר ביקש שנחזור אליו (Follow-up חוזר לאורך זמן).
    followup_count: int = 0


class CallCenterQueue(BaseModel):
    scope: str = "today"
    items: list[CallCenterGuestRow]
    total: int
    limit: int
    offset: int


class CallCenterTimelineItem(BaseModel):
    """שורה ביומן הפעילות של מוזמן — הודעת WhatsApp או שיחת טלפון."""

    kind: str                   # invitation/reminder_1/.../reply/call
    channel: str                # whatsapp/phone/web
    label: str                  # תיאור עברי מוכן לתצוגה
    text: str = ""
    status: str = ""
    round_number: Optional[int] = None
    actor: Optional[str] = None  # מי ביצע (בשיחות טלפון)
    created_at: datetime


class CallCenterGuestDetail(BaseModel):
    """מסך ביצוע שיחה — כל מה שצריך כדי לדבר עם המוזמן."""

    guest_id: int
    full_name: str
    phone: str = ""
    side: str
    party_size: int
    rsvp_status: str
    confirmed_count: Optional[int] = None
    guest_note: Optional[str] = None      # הערה שהמוזמן מסר
    notes_raw: Optional[str] = None       # הערה פנימית של בעל האירוע
    event_id: int
    event_type: str
    hosts: str
    event_date: str = ""
    event_time: str = ""
    venue_name: str = ""
    venue_address: str = ""
    round_number: Optional[int] = None
    round_date: Optional[str] = None
    timeline: list[CallCenterTimelineItem] = []


class CallOutcomeRequest(BaseModel):
    """תוצאת שיחה שהאדמין מדווח. ערכי ``outcome``: ראו call_center.OUTCOMES."""

    outcome: str
    count: Optional[int] = None        # מספר מאשרים (רק ב-outcome="confirmed")
    guest_note: Optional[str] = None   # הערה שהמוזמן מסר — נשמרת אצל המוזמן
    note: str = ""                     # הערת המוקדן על השיחה עצמה
    callback_at: Optional[datetime] = None  # רק ב-outcome="callback"


class CallOutcomeResult(BaseModel):
    guest_id: int
    outcome: str
    outcome_label: str
    rsvp_status: str
    confirmed_count: Optional[int] = None
    callback_at: Optional[datetime] = None


class GuestDataAlert(BaseModel):
    """התראת איכות-דאטה על מוזמן — כרגע רק "מספר טלפון שגוי".

    **לא** סטטוס RSVP: סטטוס אישור ההגעה של המוזמן לא השתנה. זו בעיה בפרטי
    הקשר בלבד, שנפתרת בעדכון המספר (ראו app/call_center.py: phone_fix_alerts).
    """

    kind: str = "phone_fix"      # מזהה סוג ההתראה (מקום להתראות דאטה נוספות)
    guest_id: int
    full_name: str
    phone: str = ""              # המספר השגוי שעליו דווח
    rsvp_status: str             # מוצג כדי להבהיר שהסטטוס *לא* השתנה
    attempts: int                # כמה פעמים כבר דווח מספר שגוי
    reported_at: datetime


class GuestDataAlerts(BaseModel):
    phone_fix: list[GuestDataAlert] = []
    total: int = 0


# ---- ניהול משותף של האירוע (בן/בת זוג) ----------------------------------


class PartnerInviteCreate(BaseModel):
    """הזמנת בן/בת זוג לניהול משותף — כתובת המייל שלהם בלבד."""

    email: str

    @field_validator("email")
    @classmethod
    def _email_valid(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("כתובת האימייל לא נראית תקינה")
        return v


class PartnerInviteRead(BaseModel):
    """הזמנה ממתינה כפי שהיא מוצגת לשולח (בלי הטוקן — הוא רק במייל)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    invited_email: str
    status: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    # False כשהמייל עצמו לא יצא (תקלת ספק) — ההזמנה נשמרה ואפשר לשלוח שוב.
    email_sent: bool = True


class InvitationPreview(BaseModel):
    """מה שרואים בדף ההצטרפות, לפני ההצטרפות בפועל.

    ``state`` מתאר מה לעשות עם ההזמנה, וכל ערך מקבל מסך משלו בפרונט:
    ``ready`` (אפשר להצטרף) / ``needs_login`` (צריך להתחבר או להירשם) /
    ``wrong_account`` (מחובר עם חשבון אחר) / ``expired`` / ``used`` /
    ``cancelled`` / ``invalid`` (טוקן לא מוכר) / ``already_member``.
    """

    state: str
    event_title: str = ""
    inviter_name: str = ""
    invited_email: str = ""
    message: str = ""


class EventManagerRead(BaseModel):
    """מנהל/ת אירוע לתצוגה במסך "ניהול משותף"."""

    user_id: int
    display_name: str
    email: str
    # "מנהל האירוע" — מוצג לשני הצדדים באותה צורה: אין "בעלים" ו"משני".
    role_label: str = "מנהל האירוע"
    is_me: bool = False


class MyEventRead(BaseModel):
    """האירוע היחיד של המשתמש, כפי שהוא מוצג במסך החשבון."""

    id: int
    title: str
    event_type: str = "wedding"
    event_date: str = ""
    venue_name: str = ""


class AccountOverview(BaseModel):
    """כל מה שמסך "החשבון שלי" צריך, בקריאה אחת."""

    user: UserRead
    event: Optional[MyEventRead] = None
    managers: list[EventManagerRead] = []
    pending_invite: Optional[PartnerInviteRead] = None
    # האם המשתמש רשאי להזמין בן/בת זוג (יש אירוע, ואין עדיין שותף/ה).
    can_invite_partner: bool = False


class VerifyEmailRequest(BaseModel):
    """מימוש קישור אימות המייל — הטוקן החד-פעמי מתוך הקישור."""

    token: str


class VerifyEmailCodeRequest(BaseModel):
    """מימוש קוד אימות המייל בן 6 הספרות (ערוץ מקביל לקישור)."""

    code: str

    @field_validator("code")
    @classmethod
    def _code_valid(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.isdigit() or len(v) != 6:
            raise ValueError("הקוד חייב להיות בן 6 ספרות")
        return v


class EmailChangeRequest(BaseModel):
    """שינוי כתובת המייל לפני שהיא אומתה (טעות הקלדה בהרשמה)."""

    email: str

    @field_validator("email")
    @classmethod
    def _email_valid(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("כתובת האימייל לא נראית תקינה")
        return v


class ForgotPasswordRequest(BaseModel):
    """בקשת קישור לאיפוס סיסמה. התגובה בשרת זהה תמיד, בלי קשר אם הכתובת
    קיימת במערכת — כדי לא לחשוף אילו כתובות מייל רשומות (email enumeration).
    ראו routers/auth.py::forgot_password.
    """

    email: str

    @field_validator("email")
    @classmethod
    def _email_lower(cls, v: str) -> str:
        return (v or "").strip().lower()


class ResetPasswordRequest(BaseModel):
    """מימוש קישור איפוס הסיסמה: הטוקן החד-פעמי מהקישור + הסיסמה החדשה."""

    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _new_password_valid(cls, v: str) -> str:
        return validate_password_strength(v)


# ── פרטי קבלת מתנות (חשבון הבנק של בעלי האירוע) ──────────────────────────


class PayoutAccountWrite(BaseModel):
    """קלט הטופס. הערכים מתקבלים כמחרוזות ומנורמלים בשרת.

    אין כאן ``Field(pattern=...)`` בכוונה: הולידציה כולה עוברת דרך
    ``app/banks.py``, שהוא מקור אמת אחד לכללים ולנוסח השגיאות בעברית —
    כך אותה בדיקה בדיוק חלה על כל נתיב שכותב פרטי חשבון.
    """

    bank_code: int
    branch_number: str
    account_number: str
    # אישור ניהול חשבון כ-data URL. ``None`` = לא נגעו בקובץ הקיים.
    certificate: Optional[str] = None


class PayoutCertificateRead(BaseModel):
    """תיאור הקובץ שהועלה — בלי הבייטים עצמם."""

    filename: Optional[str] = None
    content_type: Optional[str] = None
    size: Optional[int] = None
    uploaded_at: Optional[datetime] = None


class PayoutAccountRead(BaseModel):
    """פרטי החשבון כפי שהם חוזרים למסך.

    ``account_number_masked`` הוא מה שמוצג אחרי שמירה: אין סיבה להחזיר
    לדפדפן את מספר החשבון המלא בכל טעינת מסך רק כדי להראות "שמור". מי
    שרוצה לשנות — מקליד מחדש.

    **מה שבמפורש לא נמצא כאן:** ``provider`` ו-``provider_account_id``.
    הם מידע תפעולי פנימי של VEYA מול ספק עתידי, ואינם עניינם של בעלי
    האירוע — בדיוק כמו שעמלת השירות אינה מוחזרת במסך המתנות.
    """

    configured: bool
    #: מסלול הבדיקה של VEYA:
    #: missing / submitted / under_review / verified / rejected
    status: str
    #: אותו מסלול, מקוצר לשלוש מילים: pending / approved / rejected.
    veya_status: str = "pending"
    #: בדיקת ספק הסליקה: pending / approved / rejected. **מסלול נפרד** —
    #: אישור VEYA אינו משנה אותו.
    provider_status: str = "pending"
    #: שתי הבדיקות אושרו. **נגזר בשרת בלבד** (``payout_service.is_fully_verified``)
    #: ולא מתקבל בשום קלט — אין שדה כזה ב-``PayoutAccountWrite``.
    fully_verified: bool = False
    #: הפרטים אושרו ע"י VEYA ולכן נעולים לשינוי. גם זה נגזר בשרת: הוא
    #: מדווח על החלטה שכבר נאכפת ב-``payout_service``, ולא מבקש מהמסך
    #: לאכוף משהו בעצמו.
    locked: bool = False
    #: האם אפשר להגיש לבדיקה עכשיו (יש פרטים ואישור, והסטטוס מאפשר).
    can_submit: bool = False
    #: סיבת הדחייה של VEYA, כשהסטטוס ``rejected``.
    rejection_reason: Optional[str] = None
    #: סיבת הדחייה של ספק הסליקה, אם סיפק אותה.
    provider_rejection_reason: Optional[str] = None
    submitted_at: Optional[datetime] = None
    bank_code: Optional[int] = None
    bank_name: Optional[str] = None
    branch_number: Optional[str] = None
    account_number_masked: Optional[str] = None
    certificate: Optional[PayoutCertificateRead] = None
    updated_at: Optional[datetime] = None


# ---- בדיקת פרטי קבלת המתנות בצד VEYA (מסך האדמין) ----


class PayoutReviewRow(BaseModel):
    """חשבון אחד בתור הבדיקה של האדמין.

    **מה שיש כאן זה בדיוק מה שצריך כדי להכריע**: מי בעלי האירוע, לאיזה
    בנק וסניף, ואילו ארבע ספרות אחרונות — מספיק כדי להצליב מול אישור
    ניהול החשבון שמוצג לצידו.

    **מה שאין כאן:** מספר החשבון המלא. גם לאדמין הוא לא מוחזר ב-JSON —
    מי שבודק פותח את המסמך עצמו (``GET /admin/payout/{event_id}/certificate``)
    ומשווה מולו. תשובת רשימה לא צריכה לשאת מספר חשבון של אף אחד.
    """

    event_id: int
    event_title: str = ""
    owner_name: str = ""
    owner_email: str = ""

    bank_code: Optional[int] = None
    bank_name: Optional[str] = None
    branch_number: Optional[str] = None
    account_number_masked: Optional[str] = None
    certificate: Optional[PayoutCertificateRead] = None

    status: str
    veya_status: str
    provider_status: str
    fully_verified: bool
    rejection_reason: Optional[str] = None
    provider_rejection_reason: Optional[str] = None
    submitted_at: Optional[datetime] = None
    #: מי ב-VEYA הכריע בבדיקה האחרונה, ומתי.
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None


class PayoutRejectWrite(BaseModel):
    """דחייה. הסיבה **חובה** — ראו ``payout_service.veya_reject``."""

    reason: str = Field(min_length=1, max_length=500)


class PayoutProviderStatusWrite(BaseModel):
    """רישום תשובת ספק הסליקה.

    ``status`` הוא pending / approved / rejected. הערך נבדק שוב בשירות
    (``payout_status.normalize_review``) — הבדיקה כאן היא נוחות בלבד.
    """

    status: str
    reason: str = ""


# ---- נוהל דחייה ----


class PostponementRead(BaseModel):
    """מצב נוהל הדחייה כפי שבעלי האירוע רואים אותו.

    **אין כאן שדה תאריך חדש, ובמכוון.** הבקשה היא בקשת רשות לערוך, לא
    הצהרה על מועד. התאריך החדש נכנס אחר כך דרך עריכת האירוע הרגילה.
    """

    #: ``None`` = מעולם לא נפתחה בקשה לאירוע הזה.
    status: Optional[str] = None
    cycle_number: int = 1
    requested_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    #: סיבת הדחייה של הבקשה, כשמנהל VEYA דחה אותה. מוצגת לבעלי האירוע.
    rejection_reason: Optional[str] = None
    #: התאריך שהיה לפני הדחייה — כדי שהמסך יוכל להראות "היה X, עכשיו Y".
    previous_event_date: str = ""
    previous_event_time: str = ""
    #: האם אפשר לפתוח בקשה חדשה עכשיו. נגזר בשרת כדי שהמסך לא ינחש.
    can_request: bool = True
    #: האם אפשר לסיים את הנוהל ולפתוח מחזור חדש (נוהל פתוח + תאריך חדש נקבע).
    can_complete: bool = False


class PostponementRejectWrite(BaseModel):
    """דחיית בקשה על ידי מנהל VEYA. הסיבה חובה — בעלי האירוע רואים אותה."""

    reason: str


class PostponementReviewRow(BaseModel):
    """בקשת דחייה אחת בתור של האדמין.

    **מה שיש כאן זה בדיוק מה שצריך כדי להכריע**: איזה אירוע, מי ביקש, מתי,
    ומה מצב האירוע בפועל (תאריך, אולם, כמה כבר אישרו הגעה) — כדי שהמאשר
    יבין מה עומד להיפתח.
    """

    request_id: int
    event_id: int
    event_title: str = ""
    event_type: str = "wedding"
    cycle_number: int = 1

    owner_name: str = ""
    owner_email: str = ""
    #: מי בפועל לחץ על "פתיחת נוהל דחייה" — לא בהכרח הבעלים הרשום.
    requested_by_name: str = ""

    event_date: str = ""
    event_time: str = ""
    venue_name: str = ""
    guests_total: int = 0
    guests_confirmed: int = 0

    status: str
    requested_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════
#  כספי האירוע — עלות האירוע, ספירת מתנות וסיכום
# ════════════════════════════════════════════════════════════════════════

CalcMethod = Literal["fixed", "per_attendee", "per_guest", "per_unit", "percent"]


class ExpenseItemRead(BaseModel):
    """פריט בתבנית של סוג האירוע — הצעה למילוי, לא רשימה סגורה."""

    key: str
    label: str
    calc_method: CalcMethod
    #: האם להציג לפריט את שדות ההתחייבות (כמות מובטחת + מינימום כספי).
    supports_commitment: bool = False
    #: כמות פתיחה ל-``per_unit`` (יחידות) או ל-``percent`` (אחוזים שלמים).
    default_quantity: Optional[int] = None
    #: ``True`` = מוצע מיד בתבנית; ``False`` = קיים תחת "הוספת הוצאה".
    #: זה מה שמאפשר תבנית מקיפה בלי מסך עמוס.
    is_default: bool = False
    sort_order: int = 0


class ExpenseCategoryRead(BaseModel):
    key: str
    label: str
    items: list[ExpenseItemRead]


class ExpenseWrite(BaseModel):
    """יצירה/עדכון של שורת הוצאה.

    **הסכומים מגיעים באגורות שלמות ולא בשקלים.** ה-Frontend ממיר פעם אחת
    בקלט; מספר עשרוני שנוסע ברשת הוא בדיוק המקום שבו נולדות שגיאות עיגול.
    """

    category: str = Field(default="other", max_length=60)
    item_key: str = Field(default="", max_length=60)
    label: str = Field(min_length=1, max_length=120)
    calc_method: CalcMethod = "fixed"
    amount_agorot: int = Field(default=0, ge=0)
    #: ל-``per_unit`` בלבד.
    quantity: Optional[int] = Field(default=None, ge=0)
    #: כמות ההתחייבות מול הספק — ל-``per_attendee`` בלבד. חלק ממנוע
    #: החישוב ולא שדה מידע: משלמים על MAX(מגיעים, התחייבות).
    committed_quantity: Optional[int] = Field(default=None, ge=0)
    #: מינימום כספי מובטח בחוזה, באגורות.
    min_total_agorot: Optional[int] = Field(default=None, ge=0)
    note: Optional[str] = Field(default=None, max_length=500)
    #: שם הספק. טקסט חופשי — ניהול ספקים הוא מוצר אחר.
    vendor: str = Field(default="", max_length=120)
    #: הערכה מול מחיר שסוכם. **ברירת המחדל היא הערכה**: תקציב נבנה
    #: מהערכות, וסימון הכול כ"סוכם" מלכתחילה מרוקן את ההבחנה.
    is_estimated: bool = True
    #: נפרד לחלוטין מ-``is_estimated``: אפשר לשלם מקדמה על סכום לא סופי.
    is_paid: bool = False

    @field_validator("label")
    @classmethod
    def _trim_label(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("נשמח שתזינו שם להוצאה.")
        return trimmed


class ExpenseRead(BaseModel):
    """שורת הוצאה + התוצאה שלה במצב האורחים הנוכחי.

    התוצאה מגיעה **מהשרת** ולא מחושבת במסך. הכלל הזה הוא אותו כלל שכבר
    נאכף במתנות (``app/gift.py``): ה-Frontend מצייר כסף, לא מחשב אותו.
    """

    id: int
    category: str
    category_label: str
    item_key: str
    label: str
    calc_method: CalcMethod
    amount_agorot: int
    quantity: Optional[int] = None
    committed_quantity: Optional[int] = None
    min_total_agorot: Optional[int] = None
    note: Optional[str] = None
    vendor: str = ""
    is_estimated: bool = True
    is_paid: bool = False
    sort_order: int = 0

    #: העלות בפועל של השורה.
    total_agorot: int
    total_display: str
    #: הכמות שחויבה בפועל. ``None`` לשורה קבועה — שם אין כמות, ו-1 היה
    #: מספר ממציא.
    billed_quantity: Optional[int] = None
    #: מנות ששולמו ואיש לא ישב בהן (התחייבות פחות מגיעים).
    unused_quantity: int = 0
    #: מגיעים מעבר לכמות ההתחייבות.
    over_commitment: int = 0
    #: האם המינימום הכספי הוא שקבע את המחיר בפועל.
    min_total_applied: bool = False


class TemplateApplyResult(BaseModel):
    """תוצאת "להתחיל מהתבנית"."""

    created: int
    #: ``False`` כשכבר היו הוצאות — התבנית לא נוצרה מחדש ולא דרסה דבר.
    applied: bool
    expenses: list["ExpenseRead"] = []


class ScenarioRead(BaseModel):
    """נקודה אחת בלוח "מה יקרה אם יגיעו…"."""

    attendees: int
    total_agorot: int
    total_display: str
    #: ההפרש מהמצב הנוכחי. שלילי = חיסכון.
    delta_agorot: int
    #: האם זו הנקודה שהאירוע עומד בה כרגע.
    is_current: bool = False
    #: האם זו כמות ההתחייבות מול האולם — המדרגה שבה המחיר מתחיל לזוז.
    is_commitment: bool = False


class StepCostRead(BaseModel):
    """כמה יעלו עוד N אורחים. נגזר כהפרש בין שני מצבים, ולכן נכון גם
    מתחת לכמות ההתחייבות (שם התוספת היא 0) וגם מעליה."""

    guests: int
    added_agorot: int
    added_display: str


class CommitmentRead(BaseModel):
    """תמונת ההתחייבות מול האולם — הנתון שקובע כמה באמת משלמים.

    מוצג בנפרד מהסיכום כי זו השאלה שהזוג שואל בשבועיים האחרונים:
    "על כמה התחייבנו, כמה מגיעים, ומה זה אומר".
    """

    #: שורת ההוצאה שההתחייבות שייכת לה (שורת המנה, בדרך כלל).
    expense_id: int
    label: str
    committed_quantity: int
    attendees: int
    #: כמה מנות שולמו ולא נוצלו. 0 כשהמגיעים עברו את ההתחייבות.
    unused_quantity: int
    #: כמה מגיעים מעבר להתחייבות. 0 כשעדיין מתחת.
    over_commitment: int
    #: הכמות שמחויבת בפועל — MAX(מגיעים, התחייבות).
    billed_quantity: int
    unit_price_agorot: int
    total_agorot: int
    total_display: str
    min_total_agorot: Optional[int] = None
    min_total_applied: bool = False


class CostSummaryRead(BaseModel):
    """התמונה הכספית של צד ההוצאות."""

    total_agorot: int
    total_display: str
    fixed_agorot: int
    fixed_display: str
    variable_agorot: int
    variable_display: str

    attendees: int
    invited: int
    #: ``None`` כשאין מגיעים — חלוקה באפס אינה "0 ₪ לאורח", היא שאלה
    #: בלי תשובה, וכך היא מוצגת.
    cost_per_attendee_agorot: Optional[int] = None
    cost_per_attendee_display: str = ""
    #: כמה יעלה האורח הבא.
    next_attendee_agorot: int = 0
    next_attendee_display: str = ""

    #: כמה מהעלות כבר שולמה בפועל, וכמה עוד לפניכם. שני מספרים שהזוג
    #: שואל עליהם בכל שיחה עם ההורים, ואין להם שום קשר לשאלה אם המחיר
    #: סופי — לכן הם נספרים בנפרד מ-``estimated``.
    paid_agorot: int = 0
    paid_display: str = ""
    unpaid_agorot: int = 0
    unpaid_display: str = ""
    #: כמה מהסך עדיין מבוסס על הערכה ולא על מחיר שסוכם.
    estimated_agorot: int = 0
    estimated_display: str = ""

    steps: list[StepCostRead] = []
    scenarios: list[ScenarioRead] = []
    commitments: list[CommitmentRead] = []


class RsvpSnapshotRead(BaseModel):
    """מצב אישורי ההגעה — **נקרא מהמקור הקיים**, לא נספר מחדש.

    אותם מספרים בדיוק שמופיעים בתמונת המצב ובמסך אישורי ההגעה. שני
    מסכים שסופרים "כמה מגיעים" בשתי דרכים הם שני מספרים שיסטו זה מזה.
    """

    total_guests: int
    invited_people: int
    confirmed_guests: int
    confirmed_people: int
    declined_guests: int
    pending_guests: int
    maybe_guests: int


class GiftEntryRead(BaseModel):
    """שורת מתנה אחת — מעטפה או אשראי, באותה רשימה."""

    source: Literal["envelope", "credit"]
    id: int
    #: ``None`` = הסכום חסום (אשראי לפני אישור פרטי קבלת המתנות). לא
    #: מאופס ולא מוסתר בכוכביות — פשוט לא נכתב לתשובה.
    amount_agorot: Optional[int] = None
    amount_display: str = ""
    guest_id: Optional[int] = None
    #: ריק = מעטפה שטרם זוהתה. מצב מתועד, לא חוסר נתון.
    guest_name: str = ""
    envelope_number: Optional[int] = None
    note: Optional[str] = None
    created_at: datetime
    #: מתנה משותפת — שמות המוזמנים הנוספים. הסכום אינו מפוצל ביניהם.
    shared_names: list[str] = []
    status: Optional[str] = None


class EnvelopeWrite(BaseModel):
    """הזנת מעטפה או עריכתה."""

    #: ``0`` מותר במפורש: **"נספרה מעטפה ריקה" הוא מצב אמיתי**, והוא שונה
    #: לגמרי מ"עדיין לא נספרה מתנה". מוזמן בלי שורת מתנה מקבל ``None``
    #: בסך שלו; מוזמן שנספרה לו מעטפה ריקה מקבל ``0``. אילו אפס היה
    #: אסור כאן, הזוג היה נאלץ לרשום סכום מומצא או להשאיר את המוזמן
    #: כ"לא נספר" — ושתי האפשרויות משקרות בדוח.
    amount_agorot: int = Field(ge=0)
    #: ``None`` = "לא ידוע ממי". מצב לגיטימי שאפשר לחזור אליו.
    guest_id: Optional[int] = None
    #: מתנה משותפת — מוזמנים נוספים מעבר ל-``guest_id``.
    shared_guest_ids: list[int] = []
    note: Optional[str] = Field(default=None, max_length=500)


class EnvelopeCreated(BaseModel):
    """התשובה למעטפה שנשמרה — כוללת את מספר המעטפה **הבא**.

    המספר הבא חוזר מהשרת ולא נספר בדפדפן: זו הדרך היחידה שבה שני
    מכשירים שסופרים את אותה ערימה במקביל לא יקבלו את אותו מספר.
    """

    envelope: GiftEntryRead
    next_envelope_number: int


class GiftIncomeRead(BaseModel):
    """צד ההכנסות."""

    envelopes_agorot: int
    envelopes_display: str
    envelopes_count: int
    #: ``None`` (ולא 0) כשסכומי האשראי חסומים — "0" היה אומר "לא התקבלו
    #: מתנות באשראי", וזו טענה אחרת לגמרי.
    credit_agorot: Optional[int] = None
    credit_display: str = ""
    credit_count: int = 0
    #: ``None`` כשחלק מהתמונה חסום. סכום חלקי שמוצג כ"סה״כ" הוא מספר שקרי.
    total_agorot: Optional[int] = None
    total_display: str = ""
    unidentified_count: int = 0
    unidentified_agorot: int = 0
    unidentified_display: str = ""


class GuestGiftRowRead(BaseModel):
    """**שורה מלאה אחת לכל מוזמן** — הגעה ומתנה יחד.

    זו השורה שממנה נבנה הדוח הסופי: הזוג לא אמור לחבר מידע משלושה
    מסכים כדי לדעת מה קרה עם מוזמן אחד.

    ``rsvp_status`` ו-``status`` הם **שני צירים נפרדים** שאינם נגזרים
    זה מזה: מוזמן שביטל הגעה יכול בהחלט לתת מתנה.
    """

    guest_id: int
    full_name: str
    phone: str = ""
    #: מה המוזמן ענה. **אינו** מושפע משיוך מתנה, בשום מסלול.
    rsvp_status: str
    party_size: int = 0
    #: כמה הגיעו בפועל. 0 למי שלא אישר — כולל מי שנתן מתנה.
    attended_count: int = 0

    #: counted / credit / not_counted — מצב **המתנה**.
    #: "עדיין לא נספרה" אינו "לא נתן", ואינו 0 ₪.
    status: Literal["counted", "credit", "not_counted"]
    #: ``None`` = עדיין לא נספרה (או שסכום האשראי חסום). ``0`` = נספרה
    #: מעטפה ריקה. שני מצבים שונים, ובכוונה לא אותו ערך.
    total_agorot: Optional[int] = None
    total_display: str = ""
    envelope_agorot: int = 0
    envelope_display: str = ""
    credit_agorot: Optional[int] = None
    credit_display: str = ""
    envelope_count: int = 0
    credit_count: int = 0
    gift_count: int = 0
    envelope_numbers: list[int] = []
    note: str = ""


class GiftCountingRead(BaseModel):
    """מסך ספירת המתנות."""

    #: נפתח מיום האירוע ואילך.
    counting_open: bool
    #: כמה ימים נשארו עד שייפתח. ``None`` = אין תאריך לאירוע.
    days_until_open: Optional[int] = None
    #: האם שירות המתנות באשראי פעיל לאירוע הזה בכלל.
    credit_service_active: bool = False
    #: האם מותר להציג סכומי אשראי (החשבון אושר).
    credit_amounts_visible: bool = False
    next_envelope_number: int = 1
    income: GiftIncomeRead
    entries: list[GiftEntryRead] = []


class GiftBreakdownRead(BaseModel):
    """הפער בין הגעה למתנות — התובנה שדוח כספי רגיל מפספס."""

    from_attendees_agorot: int = 0
    from_attendees_display: str = ""
    from_non_attendees_agorot: int = 0
    from_non_attendees_display: str = ""
    #: מעטפות בלי שיוך — לא ניתן לזקוף אותן לאף צד.
    unattributed_agorot: int = 0
    unattributed_display: str = ""
    guests_counted: int = 0
    guests_not_counted: int = 0


class FinanceReportRead(BaseModel):
    """הדוח הסופי — **תמונה אחת מלאה של האירוע**, לא רק סיכום כספי.

    מוחזר כמבנה נתונים ולא כקובץ, כדי שאותו מקור יזין גם את המסך, גם את
    הייצוא ל-Excel וגם את גרסת ההדפסה/PDF. שלושה ייצוגים, חישוב אחד.
    """

    event_title: str = ""
    event_date: str = ""
    venue_name: str = ""
    generated_at: datetime

    rsvp: RsvpSnapshotRead
    cost: CostSummaryRead
    income: GiftIncomeRead
    breakdown: GiftBreakdownRead
    bottom_line_agorot: Optional[int] = None
    bottom_line_display: str = ""

    expenses: list[ExpenseRead] = []
    #: שורה לכל מוזמן — כולל מי שלא הגיע וכולל מי שעדיין לא נספרה לו מתנה.
    guests: list[GuestGiftRowRead] = []
    #: מעטפות שלא שויכו לאף מוזמן, כדי שלא ייעלמו מהדוח.
    unidentified: list[GiftEntryRead] = []


class FinanceSummaryRead(BaseModel):
    """התמונה המלאה — הוצאות, הכנסות והשורה התחתונה.

    קריאה אחת שמחזירה את כל המסך, בדיוק כמו ``/stats`` לתמונת המצב.
    שלוש קריאות נפרדות היו מציגות שלושה חלקים שנטענים בזמנים שונים —
    ובמסך כספי זה נראה כמו מספרים שקופצים.
    """

    rsvp: RsvpSnapshotRead
    cost: CostSummaryRead
    income: GiftIncomeRead
    breakdown: GiftBreakdownRead
    counting_open: bool
    #: הכנסות פחות הוצאות. ``None`` כשצד ההכנסות חסום חלקית.
    bottom_line_agorot: Optional[int] = None
    bottom_line_display: str = ""
    expenses: list[ExpenseRead] = []
