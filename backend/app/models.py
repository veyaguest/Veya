"""מודלי מסד הנתונים (SQLAlchemy) — שלב 2: אירועים ומוזמנים."""
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
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
    # תמונת פרופיל — כרגע מגיעה רק ממשתמשי גוגל (Supabase user_metadata.picture).
    # משתמשי אימייל+סיסמה נשארים עם מחרוזת ריקה; אין העלאת תמונה ידנית עדיין.
    avatar_url: Mapped[str] = mapped_column(String, default="")
    # מתי כתובת המייל אומתה. None = טרם אומתה. משתמשי גוגל מסומנים כמאומתים
    # מיד (גוגל כבר אימתה את הכתובת מולם), ומשתמשים שנרשמו לפני שהאימות
    # הוצג במערכת מסומנים כמאומתים במיגרציה — כדי לא לנעול חשבונות קיימים.
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # ה-hash של טוקן האימות הפעיל (אף פעם לא הטוקן עצמו — אותו עיקרון כמו
    # ההזמנות: מי שמשיג גישה ל-DB לא יכול להתחזות לבעל הכתובת).
    email_verification_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email_verification_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    # קוד אימות בן 6 ספרות — ערוץ מקביל לקישור (אותו hash+expiry principle).
    # תוקף קצר בהרבה מהקישור (10 דקות מול 24 שעות): קוד שמוקלד ידנית נועד
    # להישאר רלוונטי רק לחלון ההרשמה המיידי, לא לשבת בתיבת דואר ליום.
    email_verification_code_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    email_verification_code_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    # מונה ניסיונות שגויים — הגנה מפני ניחוש (6 ספרות = מיליון אפשרויות,
    # קטן מספיק שדורש הגבלה מפורשת). מתאפס בכל הנפקת קוד חדש (resend).
    email_verification_code_attempts: Mapped[int] = mapped_column(Integer, default=0)
    # טוקן איפוס סיסמה עצמאי ("שכחתי סיסמה") — אותו עיקרון hash-only כמו
    # אימות המייל למעלה (רק ה-hash נשמר, הטוקן עצמו רק במייל). תוקף קצר
    # בהרבה (שעה, לא 24 שעות) — איפוס סיסמה הוא פעולה רגישה יותר מאימות כתובת.
    password_reset_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    password_reset_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
    # אדמין = הבעלים של המערכת, רואה ומנהל את כל המשתמשים והאירועים.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # סוג החשבון: couple (זוג, ברירת מחדל) / planner (מפיק) / venue (אולם).
    # ציר נפרד מ-is_admin — is_admin הוא "אדמין-על", account_type הוא "מי המשתמש".
    # שלב 1 בלבד: השדה קיים אך אינו נקרא בשום מקום עדיין (אין שינוי התנהגות).
    account_type: Mapped[str] = mapped_column(String, default="couple")
    # חשבון מושבת ע"י אדמין — המשתמש לא יכול להתחבר וכל הטוקנים שלו נפסלים.
    # ניתן לביטול (אפשר להפעיל מחדש). לא מוחק שום נתון.
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # גרסת הטוקן: כל טוקן JWT נושא את הגרסה שהייתה בזמן ההנפקה. העלאת המספר
    # (יציאה מכל המכשירים / שינוי סיסמה / איפוס) פוסלת מיד את כל הטוקנים הישנים.
    token_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    events: Mapped[list["Event"]] = relationship(back_populates="owner")


class Event(Base):
    """אירוע. חתונה היא ברירת המחדל, אך המערכת תומכת בכל סוגי האירועים
    (בר/בת מצווה, חינה, ברית, אירוע משפחתי/עסקי ועוד) דרך event_type.
    שייך למשתמש דרך owner_id (שלב 8)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    # סוג האירוע — קובע את השפה הדינמית בכל המערכת (חתן/כלה מול בעל השמחה וכו').
    # ברירת המחדל 'wedding' שומרת על תאימות אחורה: כל אירוע קיים נשאר חתונה.
    # ערכים: wedding / bar_mitzvah / bat_mitzvah / henna / brit / brita / family / business / other.
    # ברית ובריתה הם סוגי אירוע עצמאיים ונפרדים — לא תת-קטגוריה של אחד השני.
    event_type: Mapped[str] = mapped_column(String, default="wedding")
    # שמות בעלי האירוע. שמורים בשמות groom/bride מטעמי תאימות אחורה, אך
    # התוויות בממשק דינמיות לפי event_type (מנוע המונחים ב-Frontend).
    groom_name: Mapped[str] = mapped_column(String, default="")
    bride_name: Mapped[str] = mapped_column(String, default="")
    # שמות ההורים כשורה מוכנה להצגה בהזמנה — לא כשם פרטי בודד.
    # רגיסטרים דתי/חב"ד/חרדי דורשים ההורים כמזמינים. בעלים ממלא בפורמט הרצוי:
    # "משפחת כהן" / "יצחק ורבקה כהן" / "פנחס וחיה שרה שיחיו". ריק = הזוג מזמין.
    groom_parents_line: Mapped[str] = mapped_column(String, default="")
    bride_parents_line: Mapped[str] = mapped_column(String, default="")
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
    # רזרבה מפוזרת: כמה מקומות סה"כ להשאיר פנויים בשיבוץ האוטומטי, מפוזרים
    # אחיד בין השולחנות הפעילים (למשל 10 → שולחן של 12 מאויש עד 11/10). שולחן
    # שלם המסומן כרזרבה נשמר בתוך table_positions (is_reserve) ואינו נספר כאן.
    reserve_seats: Mapped[int] = mapped_column(Integer, default=0)
    # פרופיל הפריסה של האולם (נקבע בהגדרה הראשונית, נשמר נעול):
    # {"density": "spacious|comfortable|compact|dense", "planned_tables": int}
    hall_layout: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # תצלום מצב ההושבה **לפני** ההרצה האחרונה של "הושבה בקליק", לצורך
    # "החזרת הסידור הקודם": {"at": ISO, "tables": {"<guest_id>": table|None}}.
    # נשמר בשרת (ולא בזיכרון הדפדפן) כדי שהביטול ישרוד רענון דף ומעבר מכשיר.
    # None = אין מה לשחזר (עוד לא הורצה הושבה, או שהשחזור כבר בוצע).
    seating_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # תבנית הודעת ההזמנה (שלב RSVP 2). None => משתמשים בתבנית ברירת המחדל.
    message_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # תמונת ההזמנה שהזוג העלה (data URL בבסיס64). None => אין תמונה.
    invite_image: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # סקיצה/תמונה של האולם למפת ההושבה (data URL). מוצגת כרקע עדין מתחת לשולחנות.
    hall_sketch: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # מיקום/גודל/סיבוב/שקיפות/נעילה של שכבת הסקיצה על הלוח (world coordinates).
    # None => תאימות אחורה: הסקיצה מוצגת כרקע מלא כמו שהייתה תמיד (ראה hall.py).
    hall_sketch_transform: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # מסלול אישורי-ההגעה האוטומטי של VEYA — האם הופעל לאירוע הזה (provision בוצע).
    rsvp_track_active: Mapped[bool] = mapped_column(Boolean, default=False)
    # מתי הופעל המסלול — עוגן לחישוב מועדי השלבים (offset_days מהיום הזה).
    rsvp_track_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # כמה ימים לפני האירוע הזוג חייב למסור לאולם מספר סופי (1–10). זהו העוגן
    # ל-Timeline של אישורי-ההגעה: כל הסבב מחושב *לאחור* ממועד סגירת הרשימה
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
    # שלב 2 (אופטימיזציית שאילתות): כמעט כל סינון לפי סטטוס RSVP מגיע יחד עם
    # event_id (למשל "כמה ממתינים באירוע הזה") — אינדקס מורכב עוזר לשאילתות
    # האלה במקום full scan של כל המוזמנים של האירוע. ראה QUERY_OPTIMIZATION.md.
    __table_args__ = (
        Index("ix_guests_event_rsvp", "event_id", "rsvp_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    full_name: Mapped[str] = mapped_column(String)
    phone: Mapped[str] = mapped_column(String)
    side: Mapped[str] = mapped_column(String, default="shared")  # groom/bride/shared
    group_type: Mapped[str] = mapped_column(String, default="other")
    party_size: Mapped[int] = mapped_column(Integer, default=1)
    # הערה פנימית של הבעלים ("דיברנו איתו", "צריך לחזור אליו"). מידע בלבד —
    # **לא** מוזנת למנוע ההושבה ולא מנותחת לאילוצים.
    notes_raw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # הערות הושבה ("לא לשבת ליד משה", "קרוב לבר", "רחוק מהרעש"). זה **המקור
    # היחיד** שמנוע ההושבה קורא מהבעלים. ההפרדה נעשתה כדי שהערה תפעולית
    # ("צריך לבדוק מולו") לא תתפרש בטעות כאילוץ ישיבה.
    seating_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # נגזר אוטומטית מ-seating_notes (ניתוח ההערות + תור ההבהרות)
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
        """כמות המקומות שהמוזמן הזה באמת תופס — הבסיס לכל ספירת אנשים במערכת
        (תמונת המצב וסידורי ההושבה כאחד).

        החלטת בעלים (2026-08-18): רק "מגיע" נספר כפעיל בהושבה. כל השאר —
        כולל "טרם השיב" ו"מתלבט" — נספרים כ-0 מקומות, גם אם הוזמנו. זה לא
        מוחק שיבוץ קיים (``table_number`` לא נוגע כאן): אם מוזמן כבר משובץ
        לשולחן והסטטוס שלו משתנה, הוא נשאר על השולחן אבל מפסיק להיספר
        כתופס מקום עד שיחזרו ויסמנו אותו "מגיע" — ואז זה חוזר אוטומטית.
        - ביטל הגעה → 0.
        - אישר → הכמות שהזין (``confirmed_count``); אם חסרה — נופלים ל-``party_size``.
        - "אולי" / טרם השיב → 0.
        """
        if self.rsvp_status == "confirmed":
            return self.confirmed_count if self.confirmed_count is not None else self.party_size
        return 0


class LoginEvent(Base):
    """רישום התחברות מוצלחת — היסטוריית כניסות למשתמש (לפאנל האדמין).

    נרשם בכל login מוצלח. מכיל רק מטא-דאטה של האירוע (מתי, מאיזה IP/דפדפן),
    לא סיסמאות ולא תוכן. מאפשר לאדמין לראות "מתי המשתמש התחבר לאחרונה".
    """

    __tablename__ = "login_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EventInvitation(Base):
    """הזמנה לניהול משותף של אירוע — נשלחת במייל לבן/בת הזוג.

    למה טבלה נפרדת מ-``EventMember``: חברות היא מצב קיים ("יש לך גישה"),
    והזמנה היא תהליך ("שלחנו קישור, אולי יתקבל"). ההזמנה חייבת להיות תקפה
    לפני שקיים בכלל משתמש בצד השני — מי שמקבל את המייל אולי עדיין לא נרשם.

    אבטחה: הטוקן עצמו לא נשמר — רק ה-hash שלו (``token_hash``). הטוקן המלא
    קיים רק בקישור שנשלח במייל. כך גם למי שיש גישת קריאה ל-DB אין דרך לייצר
    קישור הצטרפות תקף. מזהה האירוע לעולם אינו משמש כהרשאה בפני עצמו.
    """

    __tablename__ = "event_invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    # הכתובת שאליה נשלחה ההזמנה — רק חשבון עם הכתובת הזו יוכל לממש אותה.
    invited_email: Mapped[str] = mapped_column(String, index=True)
    invited_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    token_hash: Mapped[str] = mapped_column(String, index=True)
    # pending / accepted / expired / cancelled
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # מי מימש בפועל את ההזמנה (לתיעוד — לא בהכרח זהה ל-invited_email אם
    # בעתיד נאפשר מימוש גמיש יותר; היום זו תמיד התאמה מדויקת).
    accepted_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EventMember(Base):
    """שיתוף גישה לאירוע — מי שאינו הבעלים אך יש לו גישה לאירוע.

    הבעלים (``Event.owner_id``) תמיד עם גישה מלאה ואינו מיוצג כאן.

    שני סוגי חברות שונים במהותם:
    - ``partner`` — בן/בת הזוג. מנהל/ת שווה לכל דבר: אותה גישה בדיוק כמו
      הבעלים, לאותו אירוע, בלי שכפול נתונים. זה הבסיס ל"מנהלים את האירוע
      יחד" (שני חשבונות, אירוע אחד).
    - ``planner`` / ``venue`` — מפיק או אולם. גישה *חלקית* לפי רשימת
      ``permissions``, בדיוק כפי שהייתה עד היום.
    """

    __tablename__ = "event_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String)  # partner/planner/venue
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


class ConsentRecord(Base):
    """אישור מפורש של משתמש למסמך משפטי (תנאי שימוש/מדיניות פרטיות/שיווק).

    שורה חדשה נוספת בכל אישור — לא עדכון-במקום — כך שמשתמש שאישר כמה
    גרסאות לאורך זמן שומר היסטוריה מלאה (ראו legal/11-dev-compliance-tasklist.md).
    ההשוואה ל"האם המשתמש עדכני" (``needs_reconsent``) נעשית ב-app/legal.py
    מול ``LEGAL_DOCS_VERSION``, לא כאן.
    """

    __tablename__ = "consent_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Optional (לא FK-required בפועל, בדומה ל-AuditLog.user_id): במחיקת חשבון
    # עצמית (auth.py::delete_my_account) השורה נשארת לצורך רישום/שקיפות, אבל
    # מנותקת מהמשתמש (user_id=None) — כדי לא לשמור מזהה של חשבון שנמחק.
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    # terms / privacy / marketing — ראו app/legal.py::ConsentType.
    consent_type: Mapped[str] = mapped_column(String, index=True)
    document_version: Mapped[str] = mapped_column(String)
    # מאיפה ניתנה ההסכמה, למשל "signup_form" / "reconsent_modal".
    source: Mapped[str] = mapped_column(String, default="signup_form")
    ip: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


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
    # אינדקס: נסרק ע"י admin.py בעת מחיקת משתמש (ניקוי/ניתוק יומן שלו) וב-
    # רשימת יומן האדמין (outerjoin לפי user_id).
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
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
    # שלב 2: שאילתות ספירה/סינון חוזרות (הזמנות שנשלחו, תזכורות, וכו') תמיד
    # מסננות את ארבע העמודות האלה יחד (event_id+direction+kind+status) — ראה
    # app/routers/messaging.py ו-stats.py. QUERY_OPTIMIZATION.md.
    __table_args__ = (
        Index(
            "ix_messages_event_direction_kind_status",
            "event_id", "direction", "kind", "status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    guest_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("guests.id"), nullable=True, index=True
    )
    direction: Mapped[str] = mapped_column(String)  # outbound/inbound
    # invitation/reply/reminder/pre_event/thank_you/custom — מסע התקשורת המלא
    kind: Mapped[str] = mapped_column(String, default="invitation")
    body: Mapped[str] = mapped_column(Text, default="")
    # מקור אמת יחיד לערכים: ``app/message_status.py``. להודעה יוצאת:
    # pending/queued (טרם נשלחה בפועל — עתידי, לתור אסינכרוני) · sent
    # (התקבלה ע"י הספק) · delivered/read (webhook חי) · failed (השליחה
    # נכשלה — כולל כל כשל שהספק לא סיווג בנפרד) · blocked (המוזמן חסם את
    # העסק, webhook — [לאימות], ראו message_status.py). שימו לב:
    # no_valid_number (טלפון חסר/פורמט לא תקין) הוא ידע *מקומי בלבד* ולעולם
    # לא נכתב לעמודה הזו — מוזמן כזה לא מקבל שורת Message בכלל, הסטטוס
    # נגזר חי בזמן קריאה (ראו message_status.py: guest_effective_status).
    # להודעה נכנסת: ``received`` בלבד.
    status: Mapped[str] = mapped_column(String, default="sent")
    provider: Mapped[str] = mapped_column(String, default="mock")  # mock/meta
    # ערוץ ההודעה — היום רק whatsapp (mock/live). מכין את הקרקע ל-SMS/טלפון/AI
    # בעתיד: פעולה יודעת דרך איזה ערוץ נשלחה, בלי לשנות את המבנה בהמשך.
    channel: Mapped[str] = mapped_column(String, default="whatsapp")
    # אם ההודעה נשלחה ע"י חוק אוטומציה — המזהה שלו. משמש למניעת כפילויות
    # ("האם חוק X כבר ירה למוזמן Y?") ולבניית ה-Timeline של האורח.
    rule_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("automation_rules.id"), nullable=True, index=True
    )
    # הודעה חדשה שנשלחה מרצף "תקשורת עם אורחים" (``EventMessage``) — המקביל
    # העדכני ל-``rule_id`` (שנשאר רק לתיעוד היסטורי של הודעות ישנות).
    event_message_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("event_messages.id"), nullable=True, index=True
    )
    # מזהה ההודעה אצל הספק (למשל wamid של Meta) — המפתח שדרכו webhook עתידי
    # מעדכן סטטוס (נמסרה/נקראה/נכשלה) להודעה הנכונה. ריק במצב mock.
    # בלי ``index=True`` כאן בכוונה: האינדקס עליה חייב להיות ייחודי (כדי
    # שהתאמת webhook לעולם לא תדלוף לעדכן הודעה של מוזמן אחר) — מנוהל
    # במפורש דרך ``_EXTRA_UNIQUE_INDEXES``/``_ensure_unique_indexes`` ב-
    # main.py, לא דרך הדגל הרגיל (שהיה יוצר גם אינדקס לא-ייחודי מיותר).
    provider_message_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # חותמות זמן לפי שלב במחזור החיים של ההודעה. ``created_at`` הוא זמן
    # היצירה ביומן; ``sent_at`` הוא זמן הקבלה בפועל ע"י הספק (יכול לחפוף
    # ל-created_at היום כי השליחה סינכרונית) — delivered_at/read_at מגיעים
    # רק מ-webhook חי, ולכן None עד שיש חיבור WhatsApp אמיתי.
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # סיבת כשל/אי-מסירה — טקסט קריא לבני אדם, מהספק (mock/Meta) או מוולידציה
    # מקומית (טלפון לא תקין).
    failure_reason: Mapped[str] = mapped_column(String, default="")
    # קוד השגיאה הגולמי כפי שה-webhook/תגובת השליחה של הספק מחזירים (למשל
    # errors[].code של Meta — 131026/131050/...). לא מתפרש/מנוקה — נשמר
    # כמו שהוא כדי שאפשר יהיה לחקור בעתיד גם מה שהמיפוי שלנו (message_status.py)
    # עוד לא יודע לסווג. None כשאין שגיאה (sent/delivered/read תקינים).
    failure_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # מחרוזת הסטטוס הגולמית שהספק שלח (למשל "failed" מ-webhook Meta), *לפני*
    # המיפוי הפנימי שלנו. לרוב זהה ל-status, אבל יכול להיות שונה כשאנחנו
    # ממפים קוד שגיאה ספציפי לסטטוס מדויק יותר משלנו (למשל blocked) —
    # כך אפשר תמיד לשחזר בדיוק מה הספק אמר, גם אם המיפוי שלנו ישתנה בעתיד.
    provider_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MessageTemplate(Base):
    """DEPRECATED — הוחלף ב-``EventMessage`` (ראו ``communication.py``).

    נשאר בקוד רק כי ``Message.rule_id``/``AutomationRule.template_id``
    ישנים מצביעים לכאן (תיעוד היסטורי, אין Alembic למחיקת טבלה בבטחה). אין
    לכתוב שורות חדשות לכאן.
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
    """DEPRECATED — הוחלף ב-``EventMessage`` (תזמון/קהל יעד קבועים לכל
    message_type, ראו ``communication.py``). נשאר בקוד כי ``Message.rule_id``
    ישן מצביע לכאן (תיעוד היסטורי). אין לכתוב שורות חדשות לכאן.
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
    """DEPRECATED — הוחלף ב-``MessageDefault`` (event_type × message_type,
    ראו ``communication.py``). נשאר בקוד כתיעוד היסטורי בלבד; האדמין מנהל
    ברירות מחדל היום דרך ``/admin/message-defaults``, לא כאן.
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
    """DEPRECATED — התזמון הקבוע עבר ל-``EventMessage.trigger_offset_days``
    (ראו ``communication.py``). נשאר בקוד כתיעוד היסטורי בלבד.
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


class MessageDefault(Base):
    """קטלוג ברירות המחדל הגלובלי לרצף התקשורת — event_type × message_type.

    כאן הבעלים מזין את הטקסטים הסופיים (מסך אדמין ``/admin/message-defaults``).
    כל אירוע חדש מעתיק ממנו את השורה המתאימה לסוג שלו אל ``EventMessage``
    (ראו ``communication.py: provision_event_messages``). ``content`` ריק
    (``""``) עד שיוזנו הטקסטים הסופיים — לא ממציאים תוכן כאן.
    """

    __tablename__ = "message_defaults"
    __table_args__ = (
        UniqueConstraint("event_type", "message_type", name="uq_message_default_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    # invitation / reminder_1 / reminder_2 / final_reminder / event_day / thank_you
    message_type: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    variables_supported: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class MessageDefaultOption(Base):
    """ספריית נוסחים לבחירה — עד 12 וריאציות ל-event_type × message_type,
    שהזוג יכול לבחור מתוכן (2026-08-06, decisions.md). לא מחליפה את
    ``MessageDefault``: ``MessageDefault.content`` נשאר "הנוסח שמוקצה
    אוטומטית לאירוע חדש" (idempotent, ללא שינוי). כשהזוג בוחר וריאציה כאן
    (``GET /communication/sequence/{message_type}/options``), התוכן מועתק
    לתוך ה-``EventMessage`` שלו — עדיין חופשי לעריכה אחר כך, בדיוק כמו היום.
    האדמין הוא מקור האמת לכל התוכן כאן (עריכה/הוספה) — לא נכתב טקסט קשיח
    בקוד.
    """

    __tablename__ = "message_default_options"
    __table_args__ = (
        UniqueConstraint(
            "event_type", "message_type", "option_number",
            name="uq_message_default_option",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String, index=True)
    message_type: Mapped[str] = mapped_column(String, index=True)
    option_number: Mapped[int] = mapped_column(Integer)  # 1..12, סדר תצוגה
    # תיאור קצר של הטון הרגשי של הנוסח הזה (למשל "חם ותמציתי") — עוזר לזוג
    # לבחור מהר בלי לקרוא את כל 12 הנוסחים במלואם.
    tone: Mapped[str] = mapped_column(String, default="")
    title: Mapped[str] = mapped_column(String, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    variables_supported: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class EventMessage(Base):
    """הודעה אחת ברצף התקשורת של אירוע ספציפי — מקור האמת היחיד לתוכן
    שנשלח בפועל למוזמנים. מוקצית אוטומטית (idempotent) מ-``MessageDefault``
    לפי ``event.event_type`` כשהאירוע נוצר; הזוג עורך כאן — לא בוחר
    מתבניות ולא מדפדף בספרייה. מחליפה את הצירוף הישן
    MessageTemplate+AutomationRule+VeyaTemplate לרצף הקבוע (ראו
    ``communication.py``).
    """

    __tablename__ = "event_messages"
    __table_args__ = (
        UniqueConstraint("event_id", "message_type", name="uq_event_message_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    message_type: Mapped[str] = mapped_column(String, index=True)
    title: Mapped[str] = mapped_column(String, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    variables_supported: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # ימים ביחס לעוגן הקבוע של message_type (חיובי=אחרי, שלילי=לפני). ראו
    # communication.py: DEFAULT_TRIGGER_OFFSET_DAYS לברירות המחדל לכל סוג.
    trigger_offset_days: Mapped[int] = mapped_column(Integer, default=0)
    # all / pending / confirmed / declined — קהל היעד לשליחה.
    target_audience: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CallLog(Base):
    """תיעוד ניסיון שיחת טלפון אחת מ-Call Center של האדמין.

    זו המידע היחיד בכל המודול שאין לו בית קיים במערכת: **מה קרה בשיחה**.
    כל השאר ממשיך לחיות במקום שלו ואינו משוכפל לכאן —
    - מועדי סבבי השיחות: מחושבים חי מ-``app/rsvp_timeline.py`` (אותו מנוע
      שמזין את מסך אישורי-ההגעה של בעל האירוע). אין כאן עמודת תאריך-סבב.
    - סטטוס ההגעה: נשאר על ``Guest.rsvp_status``/``confirmed_count``.
    - הודעות WhatsApp: נשארות ב-``Message``.

    ``round_number`` הוא סידורי הסבב (1, 2, 3...) לפי סדר שלבי ה-``call_round``
    ב-``rsvp_timeline.CYCLE`` — ולא תאריך, כדי שהרשומה תישאר נכונה גם אם
    לוח הזמנים יחושב מחדש (למשל אחרי שינוי תאריך האירוע).
    """

    __tablename__ = "call_logs"
    __table_args__ = (
        Index("ix_call_logs_event_round", "event_id", "round_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    guest_id: Mapped[int] = mapped_column(ForeignKey("guests.id"), index=True)
    round_number: Mapped[int] = mapped_column(Integer, default=1)
    # confirmed / declined / no_answer / busy / wrong_number / callback —
    # מקור אמת יחיד לערכים: ``app/call_center.py: OUTCOMES``.
    outcome: Mapped[str] = mapped_column(String, index=True)
    # מה שהאדמין רשם בשיחה. לא נכתב אוטומטית ל-``Guest.guest_note`` —
    # הערת המוזמן נשארת שלו; זו הערת המוקדן.
    note: Mapped[str] = mapped_column(Text, default="")
    # מתי לחזור אל המוזמן (רק ב-outcome="callback"). עד המועד הזה הוא לא
    # מוצג בתור, גם אם הסבב הנוכחי עדיין פתוח.
    callback_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # מספר הטלפון כפי שהיה בזמן השיחה. קיים כדי ש"מספר שגוי" ייסגר **מעצמו**:
    # ההתראה לבעל האירוע וההסתרה מתור השיחות נגזרות מהשוואה בין המספר הזה
    # למספר הנוכחי של המוזמן. ברגע שהמספר עודכן — השוואה נכשלת, ההתראה
    # נעלמת והמוזמן חוזר להיות מועמד לסבב הבא. בלי דגל "טופל" נפרד שצריך
    # לתחזק ושיכול לצאת מסנכרון מול הנתון האמיתי.
    phone_at_call: Mapped[str] = mapped_column(String, default="")
    # מי ביצע את השיחה (אדמין או טלפן). nullable כדי שמחיקת משתמש לא תפיל
    # רשומות — היומן מתעד מה קרה מול המוזמן, גם אחרי שהמוקדן עזב.
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CallAssignment(Base):
    """הקצאת אירוע לטלפן — "הטלפן הזה עובד על האירוע הזה".

    למה ברמת אירוע ולא ברמת "משימת שיחה": במודול הזה **אין ישות משימה**. תור
    השיחות מחושב חי בכל בקשה מ-Workflow אישורי ההגעה + סטטוס המוזמנים (ראו
    ``app/call_center.py``), ואין שורה בטבלה שמייצגת "שיחה שצריך לבצע". לכן
    ההקצאה נתלית על היחידה היציבה היחידה — האירוע.

    התנהגות (מתועדת ונבדקת ב-tests/test_phone_agent_scope.py):
    - אדמין                      → רואה את כל האירועים, תמיד.
    - טלפן עם הקצאה אחת לפחות    → רואה **רק** את האירועים שהוקצו לו.
    - טלפן בלי אף הקצאה          → תור משותף (כל האירועים שסבב שלהם נפתח).

    השורה האחרונה היא התנהגות **שלב א' מכוונת**: היום אין עדיין מסך הקצאה
    בפאנל האדמין, ובלעדיה טלפן ללא הקצאות היה מקבל מסך ריק ולא יכול לעבוד.
    ברגע שנוצרת ההקצאה הראשונה עבורו, הצמצום נכנס לתוקף אוטומטית — בלי לשנות
    שורה אחת ב-Call Center.
    """

    __tablename__ = "call_assignments"
    __table_args__ = (
        UniqueConstraint("event_id", "user_id", name="uq_call_assignment"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # מי הקצה (אדמין). nullable כדי שמחיקת אדמין לא תפיל הקצאות פעילות.
    assigned_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
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
    # עיר — שדה אופציונלי לניהול/סינון במאגר האדמין (לא נדרש להשלמה האוטומטית).
    city: Mapped[str] = mapped_column(String, default="")
    # מפתח דדופ = שם מנורמל (lower + רווחים מכווצים), כדי לא לכפול אולמות.
    dedup_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    # כמה אירועים השתמשו באולם — לדירוג ההצעות (הפופולריים קודם).
    usage_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MediaBlob(Base):
    """אחסון קבוע של קובצי תמונה (הזמנה/סקיצת אולם) בתוך מסד הנתונים.

    למה בטבלה נפרדת ולא בשורת האירוע: כדי שהבייטים הכבדים (מאות KB לתמונה)
    לא ייטענו בכל שאילתת אירוע — הם נשלפים רק כשהדפדפן מבקש את ה-URL של
    התמונה בפועל (``/media/<id>``). למה ב-DB ולא על הדיסק: הדיסק של Render
    זמני ונמחק בכל אתחול; מסד הנתונים (Postgres) קבוע, אז התמונות נשמרות
    לתמיד. בשורת האירוע נשמר רק נתיב קצר (``/media/<id>``).
    """

    __tablename__ = "media_blobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    content_type: Mapped[str] = mapped_column(String(100), default="application/octet-stream")
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
