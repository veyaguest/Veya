"""שליחת הודעות WhatsApp יוצאות — "רושמים, שולחים, מעדכנים", במקום אחד.

עד שלב הבטיחות של חיבור Meta (2026-10-12) כל אתר שליחה קרא קודם לספק ורק
אחר כך הוסיף שורת ``Message`` לסשן, וה-commit היה בסוף הבקשה. נפילה באמצע
(timeout, השרת החינמי ב-Render, שגיאת DB) השאירה הודעות שיצאו בפועל בלי
שום עקבות — והסבב הבא שלח אותן שוב. כאן הסדר הפוך:

1. **רישום לפני ניסיון.** לכל הודעה נוצרת שורה בסטטוס ``pending`` ("ניסיון
   שליחה התחיל, התוצאה עוד לא ידועה"), וכל השורות נשמרות ב-commit *לפני*
   שהספק נקרא.
2. **שליחה ועדכון.** אחרי כל ניסיון השורה מתעדכנת לתוצאה (sent/failed).
   מול ספק אמיתי (``provider.external``) — commit אחרי כל הודעה, כדי שנפילה
   באמצע לא תמחק את מה שכבר יצא. במצב mock אין תופעת לוואי חיצונית, ולכן
   אין commit לכל הודעה (אותה מהירות כמו קודם).
3. **שורה שנתקעה ב-``pending``** = ייתכן שההודעה יצאה (Meta קיבלה אותה והשרת
   נפל לפני שהספיק לשמור). היא נחשבת "אולי נשלחה": המסלול האוטומטי לא שולח
   שוב (dedup ב-``communication._already_sent`` ו-``invitations.invited_guest_ids``).
   עדיף מוזמן שמפספס הודעה ומקבל שיחה בסבב הבא, מאשר מוזמן שמקבל אותה פעמיים.
   השלמת התוצאה מ-webhook של Meta (לפי מזהה השורה שנשלח יחד עם ההודעה) —
   שלב החיבור ל-Meta.

**נעילה לאירוע** (``lock_event_sends``): שתי שליחות של אותו אירוע במקביל
(לחיצה כפולה, או שליחה ידנית מהתור באותו רגע שהמשימה המתוזמנת רצה) היו
מחשבות את אותו קהל לפני שאחת מהן רשמה משהו. הנעילה נלקחת לפני חישוב הקהל
ומשתחררת ב-commit של שלב 1 — ואז הבקשה השנייה כבר רואה את שורות ה-``pending``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import event_cycle, message_status, messaging, models

# מפתח ראשי לנעילת השליחה לאירוע (שונה ממפתחות המשימות המתוזמנות).
_SEND_LOCK_KEY = 815402119


@dataclass
class OutboundItem:
    """הודעה אחת שאמורה לצאת: למי, לאיזה טלפון, מה הטקסט ומאיזה סוג."""

    guest: models.Guest
    phone: str
    text: str
    kind: str
    event_message_id: Optional[int] = None


@dataclass
class BatchResult:
    sent: int = 0
    failed: int = 0
    failed_guest_ids: list[int] = field(default_factory=list)
    last_detail: str = ""
    messages: list[models.Message] = field(default_factory=list)


def lock_event_sends(db: Session, event_id: int) -> None:
    """נעילת טרנזקציה לשליחות של אירוע אחד (Postgres). משתחררת ב-commit/rollback.

    SQLite: אין מקביליות כתיבה ממילא — לא עושה כלום.
    """
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(
        text("SELECT pg_advisory_xact_lock(:k, :e)"),
        {"k": _SEND_LOCK_KEY, "e": int(event_id)},
    )


def send_batch(
    db: Session,
    event: models.Event,
    items: list[OutboundItem],
    *,
    provider=None,
) -> BatchResult:
    """רושם את כל ההודעות כ-``pending``, שולח אחת-אחת ומעדכן כל שורה לתוצאה.

    עושה commit (שלב 1, ואחרי כל הודעה מול ספק אמיתי). ה-commit האחרון —
    של העדכונים האחרונים ושל כל מה שהקורא עוד מוסיף — באחריות הקורא, כמו קודם.
    """
    result = BatchResult()
    if not items:
        return result
    provider = provider or messaging.get_provider()
    external = bool(getattr(provider, "external", False))

    cycle = event_cycle.of(event)
    rows: list[models.Message] = []
    for item in items:
        row = models.Message(
            event_id=event.id,
            guest_id=item.guest.id,
            direction="outbound",
            kind=item.kind,
            body=item.text,
            channel="whatsapp",
            event_message_id=item.event_message_id,
            cycle_number=cycle,
            status=message_status.PENDING,
            provider=provider.name,
        )
        db.add(row)
        rows.append(row)
    db.commit()  # שלב 1: הרישום שורד גם אם מה שאחריו נופל.

    for row, item in zip(rows, items):
        try:
            res = provider.send_invitation(item.phone, item.text)
        except Exception as exc:  # noqa: BLE001 — כשל ספק לא מפיל את שאר המנה
            print(
                f"[veya:whatsapp] send error event={event.id} message={row.id} "
                f"error={type(exc).__name__}",
                flush=True,
            )
            res = messaging.SendResult(
                ok=False, provider=provider.name, status=message_status.FAILED,
                detail="שגיאה לא צפויה בשליחה",
            )
        for key, value in message_status.outbound_fields(res).items():
            setattr(row, key, value)
        if res.ok:
            result.sent += 1
        else:
            result.failed += 1
            result.failed_guest_ids.append(item.guest.id)
            result.last_detail = res.detail
        if external:
            db.commit()
    db.flush()
    result.messages = rows
    return result
