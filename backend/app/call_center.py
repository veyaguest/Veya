"""Call Center — תור השיחות של האדמין, נגזר במלואו מ-Workflow אישורי ההגעה.

עיקרון מנחה: **אין כאן לוח זמנים משלנו.** המודול לא מחזיק תאריכים, לא מגדיר
סבבים ולא ממציא סטטוסים — הוא רק שואל את המערכות הקיימות ומרכיב מהן תור עבודה:

- *מתי* מתקשרים   → ``app/rsvp_timeline.py`` (אותו חישוב בדיוק שמזין את מסך
  אישורי-ההגעה של בעל האירוע). סבב פעיל = הסבב האחרון שתאריכו כבר הגיע.
- *למי* מתקשרים   → ``Guest.rsvp_status`` — רק מי שעדיין לא אישר ולא ביטל.
- *מה קרה בשיחה*  → ``models.CallLog``, הטבלה היחידה שנוספה למודול הזה.
- *עדכון סטטוס*   → ``app/rsvp_response.py``, אותה פונקציה שרצה כשהמוזמן
  מאשר בעצמו דרך הקישור ב-WhatsApp.

התוצאה: כל שינוי במסך האדמין נראה מיד אצל בעל האירוע (אותה שורת ``Guest``),
וכל שינוי של בעל האירוע מסלק מיד את המוזמן מתור השיחות.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import models, roles, rsvp_timeline

# תוצאות שיחה אפשריות — מקור אמת יחיד לערכים ולתוויות שלהם.
OUTCOMES: dict[str, str] = {
    "confirmed": "אישר הגעה",
    "declined": "לא מגיע",
    "no_answer": "לא ענה",
    "busy": "תפוס",
    "wrong_number": "מספר שגוי",
    "callback": "ביקש לחזור מאוחר יותר",
}

# תוצאות שמשמעותן "ניסיון שיחה בוצע בסבב הזה" — המוזמן יורד מהתור עד שיגיע
# תאריך הסבב הבא. "ביקש לחזור" אינו כזה: הוא חוזר לתור במועד שנבחר.
# "מספר שגוי" אינו כזה גם הוא — ראו WRONG_NUMBER למטה.
ATTEMPT_OUTCOMES = ("no_answer", "busy")

# "מספר שגוי" הוא לא ניסיון שיחה שנכשל אלא **תקלת דאטה**: אין טעם להחזיר את
# המוזמן לסבב הבא, כי המספר עדיין שגוי ונקבל בדיוק את אותה תוצאה. לכן הוא
# יוצא מתור השיחות לגמרי — עד שבעל/ת האירוע יתקן/תתקן את המספר. במקביל
# נפתחת עבורו התראת דאטה במסך ניהול המוזמנים (ראו ``phone_fix_alerts``).
# זה **לא** סטטוס RSVP ולא משנה את סטטוס אישור ההגעה בשום צורה.
WRONG_NUMBER = "wrong_number"

# תוצאות שמעדכנות את סטטוס אישור ההגעה עצמו (דרך rsvp_response).
DECISION_OUTCOMES = ("confirmed", "declined")

# סטטוסים שעדיין דורשים שיחה — מי שאישר או ביטל כבר סגור.
OPEN_STATUSES = ("pending", "maybe")

# אזור הזמן שבו מוצגים מועדים לבעלי האירועים. VEYA היא מערכת ישראלית, וכל
# האירועים מתקיימים בשעון המקומי — האחסון נשאר UTC, רק התצוגה מומרת.
LOCAL_TIMEZONE = "Asia/Jerusalem"


@dataclass
class EventQueue:
    """אירוע אחד בתור השיחות, עם המוזמנים שממתינים לשיחה בסבב הנוכחי."""

    event: models.Event
    round_number: int
    round_date: date
    guests: list[models.Guest]
    done_count: int  # כמה מוזמנים כבר טופלו בסבב הנוכחי


def due_events(db: Session, now: Optional[datetime] = None) -> list[tuple[models.Event, rsvp_timeline.Placement]]:
    """האירועים שבהם סבב שיחות כבר הגיע, עם הסבב הפעיל שלהם.

    רק אירועים שמסלול אישורי-ההגעה שלהם הופעל (ההזמנות נשלחו) — לפני זה אין
    בכלל עוגן התחלה לסבב, ואין למי להתקשר.
    """
    events = db.scalars(
        select(models.Event).where(
            models.Event.rsvp_track_active.is_(True),
            models.Event.venue_commit_days_before.is_not(None),
            models.Event.event_date != "",
        )
    ).all()
    out: list[tuple[models.Event, rsvp_timeline.Placement]] = []
    for event in events:
        placement = rsvp_timeline.due_call_round(event, now)
        if placement is not None:
            out.append((event, placement))
    return out


def visible_event_ids(db: Session, user: models.User) -> Optional[set[int]]:
    """אילו אירועים המשתמש הזה רשאי לראות במסך השיחות.

    ``None`` = בלי הגבלה (כל האירועים שסבב שלהם נפתח). ``set`` = רק אלה.

    - אדמין-על                    → ``None``.
    - טלפן עם הקצאות (``CallAssignment``) → רק האירועים שהוקצו לו.
    - טלפן בלי הקצאות             → ``None`` — תור משותף, ראו ההסבר המלא
      ב-``models.CallAssignment``. זו התנהגות שלב א' מכוונת, שנעלמת מעצמה
      ברגע שנוצרת ההקצאה הראשונה.
    """
    if getattr(user, "is_admin", False):
        return None
    if not roles.is_phone_agent(user):
        return set()
    assigned = set(db.scalars(
        select(models.CallAssignment.event_id).where(
            models.CallAssignment.user_id == user.id
        )
    ).all())
    return assigned or None


def can_access_event(db: Session, user: models.User, event_id: int) -> bool:
    """האם המשתמש רשאי לגעת במוזמן של האירוע הזה דרך מסך השיחות.

    נדרש בכל endpoint שמקבל ``guest_id`` ישירות (פרטי מוזמן / תיעוד תוצאה):
    בלעדיו טלפן שהוקצה לאירוע אחד היה יכול לנחש מזהה מוזמן של אירוע אחר.
    """
    allowed = visible_event_ids(db, user)
    return allowed is None or event_id in allowed


def unresolved_wrong_numbers(
    logs: list[models.CallLog], phone_by_guest: dict[int, str]
) -> set[int]:
    """מוזמנים שסומנו 'מספר שגוי' והמספר שלהם **עדיין לא תוקן**.

    הזיהוי נגזר מהשוואה בלבד: אם הטלפון הנוכחי של המוזמן זהה לזה שהיה בזמן
    השיחה — התקלה פתוחה. ברגע שבעל/ת האירוע מעדכן/ת מספר, ההשוואה נכשלת
    והמוזמן נחשב מטופל אוטומטית. אין דגל "טופל" שצריך לתחזק.
    """
    open_ids: set[int] = set()
    for log in logs:
        if log.outcome != WRONG_NUMBER:
            continue
        current = (phone_by_guest.get(log.guest_id) or "").strip()
        if current and current == (log.phone_at_call or "").strip():
            open_ids.add(log.guest_id)
    return open_ids


def _handled_guest_ids(
    logs: list[models.CallLog],
    current_round: dict[int, int],
    now: datetime,
    phone_by_guest: dict[int, str],
) -> set[int]:
    """מי לא יוצג עכשיו:
    - כבר ניסו להתקשר אליו בסבב הנוכחי (לא ענה / תפוס),
    - ביקש שיחזרו אליו במועד שעוד לא הגיע,
    - או שהמספר שלו שגוי ועדיין לא תוקן (מוסתר מכל הסבבים, לא רק מהנוכחי).
    """
    hidden = unresolved_wrong_numbers(logs, phone_by_guest)
    for log in logs:
        if log.outcome in ATTEMPT_OUTCOMES:
            if current_round.get(log.event_id) == log.round_number:
                hidden.add(log.guest_id)
        elif log.outcome == "callback" and log.callback_at and log.callback_at > now:
            hidden.add(log.guest_id)
    return hidden


def build_queues(
    db: Session,
    *,
    now: Optional[datetime] = None,
    event_id: Optional[int] = None,
    query: Optional[str] = None,
    status: Optional[str] = None,
    allowed_event_ids: Optional[set[int]] = None,
) -> list[EventQueue]:
    """בונה את תור השיחות: אירועים עם סבב פעיל, וכל אירוע עם המוזמנים שממתינים.

    ``event_id``/``query``/``status`` הם סינוני *תצוגה* בלבד (אירוע מסוים,
    חיפוש לפי שם/טלפון, סטטוס אישור-הגעה) — הם לא משנים מי "צריך שיחה".

    ``allowed_event_ids`` הוא משהו אחר לגמרי: סינון **הרשאה**. ``None`` =
    בלי הגבלה; אחרת רק האירועים שברשימה (ראו ``visible_event_ids``). הוא
    מופרד מ-``event_id`` בכוונה, כדי שסינון תצוגה לעולם לא יוכל להרחיב גישה.
    """
    now = now or datetime.utcnow()
    due = due_events(db, now)
    if allowed_event_ids is not None:
        due = [(e, p) for e, p in due if e.id in allowed_event_ids]
    if event_id is not None:
        due = [(e, p) for e, p in due if e.id == event_id]
    if not due:
        return []

    event_ids = [e.id for e, _ in due]
    current_round = {e.id: p.round_number for e, p in due}

    statuses = [status] if status in OPEN_STATUSES else list(OPEN_STATUSES)
    filters = [
        models.Guest.event_id.in_(event_ids),
        models.Guest.rsvp_status.in_(statuses),
        models.Guest.phone != "",
    ]
    if query:
        like = f"%{query.strip()}%"
        filters.append(
            or_(models.Guest.full_name.ilike(like), models.Guest.phone.ilike(like))
        )
    guests = db.scalars(
        select(models.Guest).where(*filters).order_by(models.Guest.full_name)
    ).all()

    logs = db.scalars(
        select(models.CallLog).where(models.CallLog.event_id.in_(event_ids))
    ).all()
    phone_by_guest = {g.id: g.phone or "" for g in guests}
    hidden = _handled_guest_ids(list(logs), current_round, now, phone_by_guest)

    waiting_by_event: dict[int, list[models.Guest]] = {eid: [] for eid in event_ids}
    for guest in guests:
        if guest.id not in hidden:
            waiting_by_event[guest.event_id].append(guest)

    done_by_event: dict[int, set[int]] = {eid: set() for eid in event_ids}
    for log in logs:
        if current_round.get(log.event_id) == log.round_number:
            done_by_event[log.event_id].add(log.guest_id)

    queues = []
    for event, placement in due:
        waiting = waiting_by_event[event.id]
        # "טופלו" ו"ממתינות" חייבים להיות חלוקה זרה של אותו סבב, אחרת הסכום
        # מנפח את המספרים. מוזמן שביקש שנחזור אליו כבר יש לו שיחה בסבב הזה
        # *וגם* הוא חזר לתור — הוא נספר כממתין בלבד.
        waiting_ids = {g.id for g in waiting}
        queues.append(EventQueue(
            event=event,
            round_number=placement.round_number,
            round_date=placement.date,
            guests=waiting,
            done_count=len(done_by_event[event.id] - waiting_ids),
        ))
    # הכי דחוף קודם: מי שיש לו הכי הרבה שיחות פתוחות.
    queues.sort(key=lambda q: len(q.guests), reverse=True)
    return queues


# ---- יומן הפעילות של בעל/ת האירוע ----
# בעל/ת האירוע לא אמור/ה לדעת שקיים מודול פנימי בשם Call Center, ולא לראות
# שמות שדות, סטטוסים פנימיים או מונחים באנגלית. לכן כל פעולת שיחה נרשמת
# ליומן הפעילות **הקיים** (``AuditLog`` → ``GET /event/audit`` → ה-Feed
# בתמונת המצב) עם משפט מוכן בעברית טבעית. המידע התפעולי המלא (מי חייג,
# לאיזה מספר, מה נאמר) נשאר ב-``CallLog`` ואינו מוצג כאן.

# שם הפעולה ביומן לכל תוצאת שיחה. שם נפרד לכל תוצאה (ולא שם גנרי אחד) כדי
# שה-Frontend יוכל לבחור אייקון בלי לנתח את הטקסט עצמו.
FEED_ACTIONS: dict[str, str] = {
    "confirmed": "guest_call_confirmed",
    "declined": "guest_call_declined",
    "no_answer": "guest_call_no_answer",
    "busy": "guest_call_busy",
    "wrong_number": "guest_call_wrong_number",
    "callback": "guest_call_callback",
}
# שיחת המשך שבוצעה למי שביקש שנחזור אליו — נרשמת בנוסף לתוצאה עצמה.
FOLLOWUP_ACTION = "guest_call_followup"


def _callback_phrase(callback_at: Optional[datetime]) -> str:
    """מועד החזרה בשעון מקומי — זה מה שבעל/ת האירוע מצפה לראות.

    כל הזמנים במערכת נשמרים כ-UTC נאיבי (``datetime.utcnow``). בלי ההמרה
    הזו המשפט היה מציג את שעת ה-UTC (למשל 06:15 במקום 09:15) — שעה שאף אחד
    לא בחר. אם אזור הזמן לא זמין בסביבה, נשארים על הערך הגולמי במקום ליפול.
    """
    if callback_at is None:
        return ""
    shown = callback_at
    try:
        from zoneinfo import ZoneInfo

        aware = callback_at.replace(tzinfo=timezone.utc) if callback_at.tzinfo is None else callback_at
        shown = aware.astimezone(ZoneInfo(LOCAL_TIMEZONE))
    except Exception:  # noqa: BLE001 — תצוגה בלבד; לא מפילים רישום ליומן
        pass
    return f" בתאריך {shown.strftime('%d/%m')} בשעה {shown.strftime('%H:%M')}"


def feed_message(
    outcome: str,
    guest_name: str,
    *,
    confirmed_count: Optional[int] = None,
    callback_at: Optional[datetime] = None,
    note: str = "",
) -> str:
    """המשפט שבעל/ת האירוע תראה ביומן הפעילות — עברית טבעית בלבד.

    צורות ההטיה ("אישר/ה") עקביות עם שאר ה-Feed הקיים
    (``frontend/src/strings/he.ts``), כי מין המוזמן אינו ידוע למערכת.
    """
    name = guest_name or "המוזמן"
    if outcome == "confirmed":
        line = f"{name} אישר/ה הגעה"
        if confirmed_count:
            line += f" – {confirmed_count} אנשים"
    elif outcome == "declined":
        line = f"{name} עדכן/ה שלא יגיע/ה"
    elif outcome == "no_answer":
        line = f"לא התקבלה תשובה מ{name}"
    elif outcome == "busy":
        line = f"לא ניתן היה להשיג את {name}"
    elif outcome == "wrong_number":
        line = f"מספר הטלפון של {name} אינו תקין"
    elif outcome == "callback":
        line = f"נקבע ליצור קשר עם {name}{_callback_phrase(callback_at)}"
    else:
        line = f"בוצעה שיחה עם {name}"

    cleaned = (note or "").strip()
    if cleaned:
        line += f"\nהערה: {cleaned}"
    return line


def followup_message(guest_name: str) -> str:
    """שיחת המשך למי שביקש שנחזור אליו."""
    return f"בוצעה שיחת המשך עם {guest_name or 'המוזמן'}"


def has_pending_followup(db: Session, guest_id: int) -> bool:
    """האם למוזמן יש בקשת "חזרו אליי" פתוחה — כלומר השיחה הבאה אליו היא
    שיחת המשך. "פתוחה" = בקשת ה-callback היא הפעולה האחרונה שנרשמה לו."""
    last = db.scalars(
        select(models.CallLog)
        .where(models.CallLog.guest_id == guest_id)
        .order_by(models.CallLog.created_at.desc(), models.CallLog.id.desc())
        .limit(1)
    ).first()
    return last is not None and last.outcome == "callback"


@dataclass
class PhoneFixAlert:
    """התראת דאטה לבעל/ת האירוע: מספר טלפון שנמצא שגוי בשיחה."""

    guest: models.Guest
    reported_at: datetime
    attempts: int


def phone_fix_alerts(db: Session, event_id: int) -> list[PhoneFixAlert]:
    """המוזמנים באירוע שדורשים תיקון מספר טלפון.

    זו **התראת איכות-דאטה, לא סטטוס RSVP**: סטטוס אישור ההגעה של המוזמן לא
    השתנה, הוא לא סומן "לא מגיע" והוא לא נמחק — פשוט אי אפשר להשיג אותו.
    ההתראה נסגרת מעצמה ברגע שהמספר מתעדכן (ראו ``unresolved_wrong_numbers``).
    """
    logs = list(db.scalars(
        select(models.CallLog)
        .where(models.CallLog.event_id == event_id)
        .where(models.CallLog.outcome == WRONG_NUMBER)
        .order_by(models.CallLog.created_at, models.CallLog.id)
    ).all())
    if not logs:
        return []

    guests = {
        g.id: g for g in db.scalars(
            select(models.Guest).where(
                models.Guest.id.in_({lg.guest_id for lg in logs})
            )
        ).all()
    }
    open_ids = unresolved_wrong_numbers(
        logs, {gid: g.phone or "" for gid, g in guests.items()}
    )

    latest: dict[int, models.CallLog] = {}
    attempts: dict[int, int] = {}
    for log in logs:
        if log.guest_id in open_ids:
            latest[log.guest_id] = log
            attempts[log.guest_id] = attempts.get(log.guest_id, 0) + 1

    alerts = [
        PhoneFixAlert(
            guest=guests[gid], reported_at=log.created_at, attempts=attempts[gid],
        )
        for gid, log in latest.items()
        if gid in guests
    ]
    alerts.sort(key=lambda a: a.guest.full_name or "")
    return alerts


def guest_call_history(db: Session, guest_id: int) -> list[models.CallLog]:
    """כל השיחות שבוצעו למוזמן, מהישנה לחדשה."""
    return list(db.scalars(
        select(models.CallLog)
        .where(models.CallLog.guest_id == guest_id)
        .order_by(models.CallLog.created_at, models.CallLog.id)
    ).all())
