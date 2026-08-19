"""עזרי בדיקה משותפים ל-Call Center — כדי שכל קובצי הרגרסיה יגדירו תרחיש
זהה ולא ישכפלו לוגיקת הקמה.

עיקרון: ההקמה נוגעת רק בשדות שה-Workflow האמיתי משתמש בהם
(``event_date`` / ``venue_commit_days_before`` / ``rsvp_track_*``) — אין כאן
מנגנון תאריכים חלופי לבדיקות.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

# הפרמטרים האלה נבחרו כך שסבב שיחות כבר ייפתח בבטחה בכל יום בשבוע
# (ראו tests/test_call_center.py — נבדק מול המנוע עצמו).
DEFAULT_DAYS_TO_EVENT = 8
DEFAULT_COMMIT_DAYS = 3
DEFAULT_STARTED_DAYS_AGO = 12


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
    started_days_ago: int = DEFAULT_STARTED_DAYS_AGO,
    activate: bool = True,
) -> None:
    """מכוון אירוע כך שסבב שיחות יהיה פעיל (או לא, עם ``activate=False``)."""
    from app import models
    from app.database import SessionLocal

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
