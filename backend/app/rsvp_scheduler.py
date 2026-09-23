"""המשימה המתוזמנת של מסלול אישורי ההגעה — השליחה האוטומטית בפועל.

עד 2026-09-23 הסבבים יצאו רק כשבעל האירוע פתח את מסך "הודעות" או "אישורים"
(``POST /automation/track/advance`` מתוך ה-Frontend). כלומר — מי שלא נכנס,
לא קיבל תזכורות, ואפילו לא הודעת יום האירוע. מעכשיו המסלול רץ כאן, בלי שום
תלות במסכים:

- **מי מפעיל:** ``POST /internal/jobs/rsvp-tick`` (``routers/jobs.py``), כל
  15 דקות בשעות השליחה, מ-GitHub Actions (``.github/workflows/rsvp-tick.yml``)
  — אותו מנגנון כמו תכנון השיחות, שעובד גם כשהשרת החינמי ב-Render "נרדם".
- **שלוש שכבות נפרדות:** *מה אמור לקרות* — ``rsvp_timeline`` +
  ``communication.compute_due_messages`` (טהור); *ביצוע* — ``run`` כאן, דרך
  ``communication.send_due_messages``; *תצוגה* — המסכים קוראים סטטוס בלבד.
- **תחילת המסלול:** ביום שבו הסבב הראשון מגיע, המסלול "מתחיל" —
  ``rsvp_track_active`` + ``rsvp_track_started_at`` נקבעים כאן (לא בשליחת
  הזמנה), ומאז לוח הזמנים קפוא ולא "בורח" קדימה.
- **אין שליחה כפולה:** נעילה אחת לכל ריצה (Postgres advisory lock), dedup לפי
  (הודעה, מוזמן) במחזור הנוכחי, ו-commit אחרי כל אירוע — כך שריצה שנפלה
  באמצע לא שולחת שוב את מה שכבר יצא.
- **עצירת חירום** (``whatsapp.emergency_stop``): לא שולחים ולא "שורפים" את
  הסבב — הוא יוצא כשהעצירה מוסרת, כל עוד החלון שלו פתוח.
- **נוהל דחייה פתוח:** לא שולחים. התאריך עשוי להשתנות, והמחזור החדש יבנה
  לוח זמנים משלו.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import (
    audit, automation, communication, local_time, messaging, models,
    postponement_service, rsvp_timeline,
)

# מפתח נעילה ייחודי למשימה הזו (שונה מזה של תכנון השיחות).
_TICK_LOCK_KEY = 815402118

# אירועים שהסתיימו לפני יותר מזה לא נבדקים — הודעת התודה (יום אחרי, עם
# דחיית סוף שבוע) היא הדבר האחרון שנשלח.
_KEEP_AFTER_EVENT_DAYS = 4


@dataclass
class TickStats:
    events: int = 0
    started: int = 0
    sent: int = 0
    failed: int = 0
    skipped_locked: bool = False
    skipped_emergency: bool = False


def _candidate_events(db: Session) -> list[models.Event]:
    """אירועים שהמסלול שלהם רשאי לפעול (``rsvp_timeline.track_enabled``) ויש
    להם תאריך. הסינון לפי תאריך נעשה בפייתון, כי התאריך נשמר כטקסט."""
    return list(db.scalars(
        select(models.Event)
        .where(models.Event.event_date != "")
        .where(rsvp_timeline.track_enabled_clause())
    ).all())


def process_event(
    db: Session, event: models.Event, now: datetime, *, send: bool = True
) -> tuple[bool, int, int]:
    """מריץ את המסלול לאירוע אחד: מתחיל אותו אם הגיע היום, ושולח את מה
    שהגיע זמנו. מחזיר ``(התחיל עכשיו, נשלחו, נכשלו)``. לא עושה commit."""
    today = local_time.israel_date(now)
    event_date = automation.parse_event_date(event.event_date)
    if event_date is None or event_date < today - timedelta(days=_KEEP_AFTER_EVENT_DAYS):
        return False, 0, 0
    if not rsvp_timeline.track_enabled(event):
        return False, 0, 0
    if postponement_service.open_request_of(db, event.id) is not None:
        return False, 0, 0

    started = False
    schedule = rsvp_timeline.compute_schedule(event, now)
    if (
        not event.rsvp_track_active
        and schedule is not None
        and schedule.placements
        and schedule.placements[0].date <= today <= schedule.commitment_date
    ):
        event.rsvp_track_active = True
        event.rsvp_track_started_at = now
        started = True
        audit.record(
            db, "rsvp_track_started", event_id=event.id,
            detail="מסלול אישורי ההגעה התחיל",
        )

    if not send:
        return started, 0, 0
    # idempotent — מבטיח שיש שורת הודעה לכל סבב (אירועים ישנים).
    communication.provision_event_messages(db, event)
    actions = communication.compute_due_messages(db, event, now=now)
    if not actions:
        return started, 0, 0
    result = communication.send_due_messages(db, event, actions)
    audit.record(
        db, "rsvp_track_advance", event_id=event.id,
        detail=f"סבב אוטומטי: נשלחו {result['sent']}, נכשלו {result['failed']}",
    )
    return started, result["sent"], result["failed"]


def _try_lock(db: Session) -> Optional[object]:
    """נעילה לכל משך הריצה (גם מעבר ל-commit של כל אירוע). Postgres: נעילת
    session על חיבור נפרד; SQLite: אין מקביליות — תמיד מצליח."""
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return True
    conn = bind.connect()
    if conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _TICK_LOCK_KEY}).scalar():
        return conn
    conn.close()
    return None


def _release(lock: object) -> None:
    if lock is True or lock is None:
        return
    try:
        lock.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _TICK_LOCK_KEY})
    finally:
        lock.close()


def run(db: Session, now: Optional[datetime] = None) -> TickStats:
    """ריצה אחת של המשימה: עוברת על כל האירועים הרלוונטיים. commit לכל אירוע."""
    now = now or datetime.utcnow()
    stats = TickStats()
    lock = _try_lock(db)
    if lock is None:
        stats.skipped_locked = True  # ריצה אחרת באמצע — התוצאה שלה זהה
        return stats
    try:
        send = not messaging.emergency_stop_active()
        stats.skipped_emergency = not send
        for event in _candidate_events(db):
            try:
                started, sent, failed = process_event(db, event, now, send=send)
                db.commit()
            except Exception as exc:  # noqa: BLE001 — אירוע אחד לא עוצר את כולם
                db.rollback()
                print(f"[veya:rsvp-tick] אירוע {event.id} נכשל: {exc!r}", flush=True)
                continue
            stats.events += 1
            stats.started += int(started)
            stats.sent += sent
            stats.failed += failed
    finally:
        _release(lock)
    return stats
