"""עזרי בדיקה משותפים ל-Call Center — כדי שכל קובצי הרגרסיה יגדירו תרחיש
זהה ולא ישכפלו לוגיקת הקמה.

עיקרון: ההקמה נוגעת רק בשדות שה-Workflow האמיתי משתמש בהם
(``event_date`` / ``venue_commit_days_before`` / ``rsvp_track_*``) — אין כאן
מנגנון תאריכים חלופי לבדיקות.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

# הפרמטרים האלה נבחרו כך שסבב שיחות כבר ייפתח בבטחה בכל יום בשבוע
# (ראו tests/test_call_center.py — נבדק מול המנוע עצמו).
DEFAULT_DAYS_TO_EVENT = 8
DEFAULT_COMMIT_DAYS = 3
# היסטורי — לא ברירת המחדל האוטומטית יותר (ראו days_ago_for_round_due_today
# ו-configure_track למטה). נשאר כערך מוכן לבדיקה מפורשת של תרחיש "לא טופל"
# (סבב שנפתח לפני היום), שם רוצים במפורש started_days_ago גדול מהמחושב.
DEFAULT_STARTED_DAYS_AGO = 12


def days_ago_for_round_due_today(
    days_to_event: int = DEFAULT_DAYS_TO_EVENT,
    commit_days: int = DEFAULT_COMMIT_DAYS,
) -> int:
    """מוצא ``started_days_ago`` כך שהסבב הראשון ייפול **בדיוק היום** —
    לא "כבר פעיל" (יכול להיות מכל יום בעבר), אלא נפתח היום ממש.

    מריץ את ``rsvp_timeline.call_rounds`` (המנוע האמיתי) על אירוע זמני
    בזיכרון בלבד — לא נוגע ב-DB — ולכן תקף בכל יום שבו רצה הבדיקה, בלי
    נוסחה עצמאית שיכולה לסטות מהמנוע האמיתי. משמש כברירת המחדל של
    ``configure_track`` כדי שמסך "שיחות להיום" (``scope=today``, ראו
    ``app/call_center.py``) ימצא בו סבב פעיל, בלי שכל קובץ בדיקה יצטרך
    לדעת את הפרטים.
    """
    from app import models, rsvp_timeline

    for started_days_ago in range(0, 60):
        probe = models.Event(
            event_date=(date.today() + timedelta(days=days_to_event)).isoformat(),
            event_time="19:00",
            venue_commit_days_before=commit_days,
            rsvp_track_active=True,
            rsvp_track_started_at=datetime.utcnow() - timedelta(days=started_days_ago),
        )
        rounds = rsvp_timeline.call_rounds(probe)
        if rounds and rounds[0].date == date.today():
            return started_days_ago
    raise AssertionError(
        f"לא נמצא started_days_ago שמעמיד סבב 1 בדיוק היום "
        f"(days_to_event={days_to_event}, commit_days={commit_days})"
    )


def admin_headers(api) -> dict:
    """הופך את המשתמש של הבדיקה לאדמין ומחזיר כותרות מתאימות."""
    from app import auth, models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        event = db.get(models.Event, api.event_id)
        user = db.get(models.User, event.owner_id)
        user.is_admin = True
        db.commit()
        return {"Authorization": f"Bearer {auth.create_access_token(user)}"}
    finally:
        db.close()


def standalone_admin(api) -> dict:
    """יוצר משתמש אדמין **נפרד**, שאינו בעלים של אף אירוע בבדיקה.

    קריטי לבדיקות בידוד: אם מקדמים את בעל האירוע עצמו לאדמין, הוא מקבל גישה
    גלובלית וכל בדיקת "האם A רואה את B" הופכת חסרת משמעות.
    """
    import uuid

    from app import auth, models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = models.User(
            email=f"cc-admin-{uuid.uuid4().hex[:10]}@veya.test",
            password_hash=auth.hash_password("Test12345!"),
            display_name="מוקד בדיקות",
            is_admin=True,
        )
        db.add(user)
        db.commit()
        return {"Authorization": f"Bearer {auth.create_access_token(user)}"}
    finally:
        db.close()


def phone_agent(api, *, display_name: str = "טלפן בדיקות") -> tuple[int, dict]:
    """יוצר משתמש **טלפן** (``account_type='phone_agent'``) ומחזיר (id, כותרות).

    בכוונה לא אדמין ולא בעלים של שום אירוע — בדיוק המצב האמיתי של איש צוות
    שמבצע שיחות בלבד.
    """
    import uuid

    from app import auth, models, roles
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = models.User(
            email=f"caller-{uuid.uuid4().hex[:10]}@veya.test",
            password_hash=auth.hash_password("Test12345!"),
            display_name=display_name,
            is_admin=False,
            account_type=roles.PHONE_AGENT,
        )
        db.add(user)
        db.commit()
        return user.id, {"Authorization": f"Bearer {auth.create_access_token(user)}"}
    finally:
        db.close()


def assign_events(agent_id: int, event_ids) -> None:
    """מקצה אירועים לטלפן — כפי שמסך ההקצאה העתידי בפאנל האדמין יעשה."""
    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        for event_id in event_ids:
            db.add(models.CallAssignment(event_id=event_id, user_id=agent_id))
        db.commit()
    finally:
        db.close()


def plain_headers(api) -> dict:
    """כותרות של משתמש רגיל (לא אדמין) — לבדיקות הרשאה."""
    from app import auth, models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        event = db.get(models.Event, api.event_id)
        user = db.get(models.User, event.owner_id)
        user.is_admin = False
        db.commit()
        return {
            "Authorization": f"Bearer {auth.create_access_token(user)}",
            "X-Event-Id": str(api.event_id),
        }
    finally:
        db.close()


def configure_track(
    api,
    *,
    days_to_event: int = DEFAULT_DAYS_TO_EVENT,
    commit_days: int = DEFAULT_COMMIT_DAYS,
    started_days_ago: Optional[int] = None,
    activate: bool = True,
) -> None:
    """מכוון אירוע כך שסבב שיחות יהיה פעיל (או לא, עם ``activate=False``).

    ``started_days_ago=None`` (ברירת המחדל) → מחושב דינמית כך שהסבב הראשון
    ייפול **בדיוק היום** (ראו ``days_ago_for_round_due_today``), כדי שהתרחיש
    הרגיל של רוב הבדיקות ("יש סבב פעיל") ימצא את עצמו תחת ``scope=today``
    מבלי שכל קובץ יצטרך לדעת את הפרטים. בדיקה שרוצה תרחיש "לא טופל"
    (סבב שנפתח *לפני* היום ועדיין לא טופל) מעבירה ``started_days_ago``
    מפורש וגדול מהערך המחושב.
    """
    from app import models
    from app.database import SessionLocal

    if started_days_ago is None:
        started_days_ago = days_ago_for_round_due_today(days_to_event, commit_days)

    db = SessionLocal()
    try:
        event = db.get(models.Event, api.event_id)
        event.event_date = (date.today() + timedelta(days=days_to_event)).isoformat()
        event.event_time = "19:30"
        event.venue_commit_days_before = commit_days
        event.rsvp_track_active = activate
        event.rsvp_track_started_at = (
            datetime.utcnow() - timedelta(days=started_days_ago) if activate else None
        )
        db.commit()
    finally:
        db.close()


def event_of(api):
    """שורת האירוע העדכנית מה-DB (מנותקת מה-session)."""
    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        event = db.get(models.Event, api.event_id)
        db.expunge(event)
        return event
    finally:
        db.close()


def guest_of(api, guest_id: int):
    """שורת המוזמן העדכנית מה-DB."""
    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        guest = db.get(models.Guest, guest_id)
        db.expunge(guest)
        return guest
    finally:
        db.close()


def call_logs_of(api, guest_id: int) -> list:
    """כל רשומות יומן השיחות של מוזמן, מהישנה לחדשה."""
    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        rows = list(
            db.query(models.CallLog)
            .filter_by(guest_id=guest_id)
            .order_by(models.CallLog.id)
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows
    finally:
        db.close()


def shift_callback(guest_id: int, *, minutes_from_now: int) -> None:
    """מזיז את מועד ה-Follow-up האחרון — כדי לדמות "הגיע הזמן" בלי להמתין."""
    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        log = (
            db.query(models.CallLog)
            .filter_by(guest_id=guest_id, outcome="callback")
            .order_by(models.CallLog.id.desc())
            .first()
        )
        log.callback_at = datetime.utcnow() + timedelta(minutes=minutes_from_now)
        db.commit()
    finally:
        db.close()
