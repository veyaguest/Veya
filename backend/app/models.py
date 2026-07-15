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
    # מספר טלפון של בעל/ת החשבון (לא של המוזמנים) — נאסף בהרשמה.
    phone: Mapped[str] = mapped_column(String, default="")
    # אדמין = הבעלים של המערכת, רואה ומנהל את כל המשתמשים והאירועים.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # סוג החשבון: couple (זוג, ברירת מחדל) / planner (מפיק) / venue (אולם).
    # ציר נפרד מ-is_admin — is_admin הוא "אדמין-על", account_type הוא "מי המשתמש".
    # שלב 1 בלבד: השדה קיים אך אינו נקרא בשום מקום עדיין (אין שינוי התנהגות).
    account_type: Mapped[str] = mapped_column(String, default="couple")
    # גרסת הטוקן: כל טוקן JWT נושא את הגרסה שהייתה בזמן ההנפקה. העלאת המספר
    # (יציאה מכל המכשירים / שינוי סיסמה / איפוס) פוסלת מיד את כל הטוקנים הישנים.
    token_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    events: Mapped[list["Event"]] = relationship(back_populates="owner")


class Event(Base):
    """אירוע (חתונה). שייך למשתמש דרך owner_id (שלב 8)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    groom_name: Mapped[str] = mapped_column(String, default="")
    bride_name: Mapped[str] = mapped_column(String, default="")
    venue_name: Mapped[str] = mapped_column(String, default="")
    # כתובת מלאה של האולם — לשימוש במשתנה {{venue_address}} ובקישור Google Maps
    # ({{maps_link}} נגזר ממנה אוטומטית, בלי עמודה נוספת).
    venue_address: Mapped[str] = mapped_column(String, default="")
    # תאריך ושעת האירוע (טקסט חופשי/ISO) — מוצג בדף האישור ובתבנית ההודעה.
    event_date: Mapped[str] = mapped_column(String, default="")   # YYYY-MM-DD
    event_time: Mapped[str] = mapped_column(String, default="")   # HH:MM
    # הערות/העדפות ברמת קבוצה (סבב B): {"<group_type>": "רחוק מהרעש", ...}.
    # אחסון קליל בלבד — הצגה ושמירה; חיבור למנוע ההושבה יתווסף בעתיד.
    group_notes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
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
    # מסלול אישורי-ההגעה האוטומטי של VEYA — האם הופעל לאירוע הזה (provision בוצע).
    rsvp_track_active: Mapped[bool] = mapped_column(Boolean, default=False)
    # מתי הופעל המסלול — עוגן לחישוב מועדי השלבים (offset_days מהיום הזה).
    rsvp_track_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # כמה ימים לפני האירוע הזוג חייב למסור לאולם מספר סופי (1–10). זהו העוגן
    # ל-Timeline של אישורי-ההגעה: כל הסבב מחושב *לאחור* מיום ההתחייבות
    # (event_date − venue_commit_days_before). None = טרם נבחר. הבחירה
    # בלתי-הפיכה מרגע שנקבעה — כל לוח הזמנים נבנה סביבה (נאכף ב-router).
    venue_commit_days_before: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    owner: Mapped[Optional["User"]] = relationship(back_populates="events")
    guests: Mapped[list["Guest"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )


class Guest(Base):
    """מוזמן — מקור האמת המרכזי של המערכת (PRD חלק 4)."""

    __tablename__ = "guests"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    full_name: Mapped[str] = mapped_column(String)
    phone: Mapped[str] = mapped_column(String)
    side: Mapped[str] = mapped_column(String, default="shared")  # groom/bride/shared
    group_type: Mapped[str] = mapped_column(String, default="other")
    party_size: Mapped[int] = mapped_column(Integer, default=1)
    notes_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # נגזר אוטומטית מ-notes_raw ע"י ה-AI בשלב 4 (כרגע ריק)
    constraints_parsed: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    rsvp_status: Mapped[str] = mapped_column(String, default="pending")  # pending/confirmed/declined/maybe
    table_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    # קישור אישי לאישור הגעה: טוקן ייחודי לכל מוזמן (שלב RSVP).
    guest_token: Mapped[Optional[str]] = mapped_column(
        String, unique=True, index=True, nullable=True, default=generate_guest_token
    )
    # כמה אנשים באמת מגיעים (נמסר ע"י המוזמן בדף האישור). None = טרם ענה.
    confirmed_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # הערה חופשית שהמוזמן השאיר בדף האישור (נגישות, תינוק וכו').
    guest_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # מסומן במפורש כ"ילד/ה" ע"י הבעלים (לא ניחוש) — לשימוש עוזר ההושבה החכם
    # (בדיקת "ילד יושב בלי אף מבוגר מהמשפחה").
    is_child: Mapped[bool] = mapped_column(Boolean, default=False)
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


class EventMember(Base):
    """שיתוף גישה לאירוע — מפיק/אולם שקיבלו הרשאה לאירוע של זוג מסוים.

    הבעלים (``Event.owner_id``) תמיד עם גישה מלאה ואינו מיוצג כאן. שורה בטבלה
    הזו מייצגת גישה *חלקית* שניתנה במפורש למשתמש אחר, לפי רשימת ``permissions``.

    שלב 1 בלבד: הטבלה קיימת אך אין עדיין שום קוד שיוצר/קורא ממנה — לא נוגעת
    בהתנהגות הקיימת.
    """

    __tablename__ = "event_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String)  # planner/venue
    # רשימת מחרוזות הרשאה, למשל ["view_guests", "manage_seating"].
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    invited_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String, default="active")  # active/pending
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Clarification(Base):
    """הבהרה ממתינה — נוצרת כשפרסור ההערות מזהה שם עמום (PRD: לולאת הבהרות).

    מוצגת למשתמש כשאלה סגורה עם כפתורים (בחירת המוזמן הנכון מבין המועמדים).
    """

    __tablename__ = "clarifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
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
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    guest_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("guests.id"), nullable=True, index=True
    )
    direction: Mapped[str] = mapped_column(String)  # outbound/inbound
    # invitation/reply/reminder/pre_event/thank_you/custom — מסע התקשורת המלא
    kind: Mapped[str] = mapped_column(String, default="invitation")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String, default="sent")  # sent/delivered/failed/received
    provider: Mapped[str] = mapped_column(String, default="mock")  # mock/meta
    # ערוץ ההודעה — היום רק whatsapp (mock/live). מכין את הקרקע ל-SMS/טלפון/AI
    # בעתיד: פעולה יודעת דרך איזה ערוץ נשלחה, בלי לשנות את המבנה בהמשך.
    channel: Mapped[str] = mapped_column(String, default="whatsapp")
    # אם ההודעה נשלחה ע"י חוק אוטומציה — המזהה שלו. משמש למניעת כפילויות
    # ("האם חוק X כבר ירה למוזמן Y?") ולבניית ה-Timeline של האורח.
    rule_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("automation_rules.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MessageTemplate(Base):
    """תבנית הודעה בעלת שם (מנוע האוטומציות של אישורי הגעה).

    היום המערכת שומרת תבנית *אחת* לאירוע (``Event.message_template``). כאן
    אפשר להחזיק כמה תבניות בעלות שם (הזמנה / תזכורת / לפני האירוע / תודה /
    מותאם), שכל חוק אוטומציה מפנה אל אחת מהן. התבנית הישנה ממשיכה לעבוד —
    זו שכבה נוספת מעליה, לא החלפה.
    """

    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    name: Mapped[str] = mapped_column(String, default="")
    # invitation / reminder / pre_event / thank_you / custom — לצורך תיוג/סינון בלבד.
    kind: Mapped[str] = mapped_column(String, default="custom")
    body: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AutomationRule(Base):
    """חוק אוטומציה במסע אישורי ההגעה (RSVP Automation Engine).

    כל חוק אומר: "כשמתקיים טריגר X, אחרי delay_days ימים, שלח את התבנית
    template_id לקהל target_group". המנוע (``automation.py``) דטרמיניסטי —
    הוא רק *מחשב* אילו פעולות הגיע זמנן; שום דבר לא נשלח בלי אישור מפורש
    של הבעלים (מודל "תור לאישור").
    """

    __tablename__ = "automation_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    rule_name: Mapped[str] = mapped_column(String, default="")
    # event_created / invitation_sent / no_response / before_event_date / guest_confirmed
    trigger_type: Mapped[str] = mapped_column(String, default="no_response")
    # כמה ימים אחרי הטריגר (או לפניו, ב-before_event_date) לפעול.
    delay_days: Mapped[int] = mapped_column(Integer, default=0)
    # all / pending / confirmed / declined / maybe / side_groom / side_bride / group
    target_group: Mapped[str] = mapped_column(String, default="pending")
    # ערך משלים לקהל — למשל שם הקבוצה כאשר target_group == "group". אחרת ריק.
    target_group_value: Mapped[str] = mapped_column(String, default="")
    template_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("message_templates.id"), nullable=True
    )
    # send = שליחת הודעת WhatsApp (mock) ; phone_followup = הכנסה לרשימת מעקב טלפוני.
    action_kind: Mapped[str] = mapped_column(String, default="send")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class VeyaTemplate(Base):
    """תבנית הודעה גלובלית של VEYA (ברירת מחדל ברמת המערכת, לא לכל אירוע).

    זו "ספריית התבניות המומלצות" שהאדמין מנהל פעם אחת, והמערכת מעתיקה
    אוטומטית לכל זוג חדש. הזוג לא רואה קוד — הוא רואה תבנית מוכנה שאפשר
    לערוך. השדה ``stage`` מסמן באיזה שלב במסלול התבנית משמשת.
    """

    __tablename__ = "veya_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    # invitation / first_reminder / second_reminder / thank_you / before_event
    stage: Mapped[str] = mapped_column(String, default="invitation", index=True)
    name: Mapped[str] = mapped_column(String, default="")
    body: Mapped[str] = mapped_column(Text, default="")
    # ברירת המחדל שתוצע לזוג עבור השלב הזה (יכולה להיות כמה תבניות לשלב).
    is_default: Mapped[bool] = mapped_column(Boolean, default=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class VeyaWorkflowStep(Base):
    """שלב במסלול אישורי-ההגעה הקבוע של VEYA (ברירת מחדל גלובלית).

    המסלול הקבוע: הזמנה → תזכורת ראשונה → תזכורת שנייה → מעקב טלפוני →
    מעקב טלפוני שני. כל שלב אומר: "אחרי ``offset_days`` ימים מתחילת המסלול,
    בצע ``action_kind`` עם תבנית מהשלב ``template_stage`` — רק לממתינים".
    האדמין עורך את המרווחים/ההפעלה; המערכת מקצה את זה לכל אירוע.
    """

    __tablename__ = "veya_workflow_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    step_order: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String, default="")
    # ימים מתחילת המסלול עד שהשלב מתבצע (0 = מיידי בהפעלה).
    offset_days: Mapped[int] = mapped_column(Integer, default=0)
    # send = שליחת הודעת WhatsApp (mock) ; phone_followup = הכנסה לרשימת מעקב טלפוני
    action_kind: Mapped[str] = mapped_column(String, default="send")
    # לאיזו תבנית (stage) השלב מפנה. ריק ל-phone_followup טהור.
    template_stage: Mapped[str] = mapped_column(String, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Venue(Base):
    """מאגר אולמות משותף — נבנה אוטומטית מכל אירוע ששומר שם+כתובת אולם.

    מטרה: כשזוג מקליד שם אולם, מציעים לו השלמה מהמאגר (שם + כתובת + ניווט),
    כדי שלא יצטרך להקליד כתובת מלאה בעצמו. מכיל **מידע ציבורי בלבד** (שם מקום
    וכתובתו), לא נתונים אישיים של מוזמנים או זוגות. דדופ לפי שם מנורמל.
    """

    __tablename__ = "venues"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, index=True)
    address: Mapped[str] = mapped_column(String, default="")
    # מפתח דדופ = שם מנורמל (lower + רווחים מכווצים), כדי לא לכפול אולמות.
    dedup_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    # כמה אירועים השתמשו באולם — לדירוג ההצעות (הפופולריים קודם).
    usage_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
