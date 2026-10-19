"""הודעות WhatsApp שלא הגיעו — מה קרה לכל מוזמן, ומה עושים עם זה.

ההזמנה יוצאת כתבנית **שיווקית** (Meta מסווגת הזמנה לשמחה כשיווק, 2026-10-19),
ולכן חלק מהמוזמנים לא יקבלו אותה. Meta מחזירה קוד שגיאה (``Message.failure_code``),
וכאן הוא הופך לאחד מארבעה מצבים — מקור אמת אחד לכל המסכים:

- ``marketing_cap`` (131049): Meta הגבילה זמנית כמה הודעות שיווק המוזמן מקבל.
  Meta מבקשת לחכות לפחות 24 שעות לפני ניסיון נוסף → **שליחה חוזרת אוטומטית
  של ההזמנה** (``resend_due``): אחרי 24 שעות, ועוד אחת לכל היותר אחרי עוד 24.
- ``marketing_opt_out`` (131050, ``message_status.BLOCKED``): המוזמן ביקש מ-WhatsApp
  לא לקבל הודעות שיווק. לא שולחים שוב הזמנה; התזכורות (תבניות שירות) ממשיכות
  במסלול כרגיל.
- ``undeliverable`` (131026): Meta לא מצליחה למסור ולא אומרת למה (אולי אין
  WhatsApp במספר, גרסה ישנה, תנאי שימוש — ראו ``message_status``). לא שולחים
  שוב ב-WhatsApp; המוזמן נכנס מיד לתור השיחות (``call_ops.sync``).
- ``failed_other``: כל כשל אחר — מוצג לזוג, בלי פעולה אוטומטית.

**המצב נקבע לפי ההודעה היוצאת האחרונה** של המוזמן במחזור הנוכחי. הודעה מאוחרת
יותר שיצאה או נמסרה (למשל תזכורת) מבטלת את הבעיה מעצמה. ``pending`` ("לא ידוע
אם יצאה") אף פעם אינו בעיה, ולעולם לא נשלח שוב — עדיף מוזמן שמקבל שיחה מאשר
מוזמן שמקבל הודעה פעמיים.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import automation, event_cycle, invitations, local_time, message_status, models

# ---- אוצר המילים ----
MARKETING_CAP = "marketing_cap"
MARKETING_OPT_OUT = "marketing_opt_out"
UNDELIVERABLE = "undeliverable"
FAILED_OTHER = "failed_other"
REASONS = (MARKETING_CAP, MARKETING_OPT_OUT, UNDELIVERABLE, FAILED_OTHER)

CODE_MARKETING_CAP = 131049
CODE_UNDELIVERABLE = 131026

# רק ההזמנה היא תבנית שיווקית. תזכורות הן תבניות שירות — 131049 לא חל עליהן,
# ויש להן כבר כלל משלהן (סבב אחד לכל מוזמן, ``communication._already_sent``).
RESEND_KINDS = frozenset({"invitation"})
RESEND_AFTER = timedelta(hours=24)
MAX_RESENDS = 2

# שעות השליחה של המסלול (``communication.SEND_TIME_MIN/MAX``), שעון ישראל.
SEND_FROM = time(10, 0)
SEND_UNTIL = time(19, 0)


@dataclass
class Issue:
    """מוזמן אחד שההודעה האחרונה אליו לא הגיעה."""

    guest: models.Guest
    reason: str
    message: models.Message
    # כמה פעמים ההודעה הזו (אותו סוג) נעצרה על הגבלת השיווק — כולל המקור.
    cap_failures: int = 0
    # מתי תצא שליחה חוזרת אוטומטית (UTC נאיבי), או ``None`` — לא מתוכננת.
    resend_at: Optional[datetime] = None


def classify(msg: Optional[models.Message]) -> Optional[str]:
    """המצב של הודעה יוצאת אחת, או ``None`` — אין בעיה (או עוד לא ידוע)."""
    if msg is None:
        return None
    if msg.status == message_status.BLOCKED:
        return MARKETING_OPT_OUT
    if msg.status != message_status.FAILED:
        return None
    if msg.failure_code == CODE_MARKETING_CAP:
        return MARKETING_CAP
    if msg.failure_code == CODE_UNDELIVERABLE:
        return UNDELIVERABLE
    return FAILED_OTHER


def _order(msg: models.Message) -> tuple:
    return (msg.created_at or datetime.min, msg.id or 0)


def cycle_outbound(db: Session, event: models.Event) -> list[models.Message]:
    """הודעות WhatsApp יוצאות למוזמנים במחזור הנוכחי, מהישנה לחדשה."""
    rows = db.scalars(
        select(models.Message)
        .where(models.Message.event_id == event.id)
        .where(models.Message.direction == "outbound")
        .where(models.Message.channel == "whatsapp")
        .where(models.Message.guest_id.is_not(None))
        .where(event_cycle.current_sends(event))
    ).all()
    return sorted(rows, key=_order)


def latest_by_guest(messages: list[models.Message]) -> dict[int, models.Message]:
    out: dict[int, models.Message] = {}
    for m in messages:
        if m.direction != "outbound" or m.guest_id is None:
            continue
        cur = out.get(m.guest_id)
        if cur is None or _order(m) > _order(cur):
            out[m.guest_id] = m
    return out


def is_send_moment(now: datetime) -> bool:
    """האם מותר לשלוח עכשיו: יום חול (לא שישי/שבת), 10:00–19:00 בישראל."""
    from app import rsvp_timeline

    local = local_time.to_israel(now)
    if rsvp_timeline.is_weekend(local.date()):
        return False
    return SEND_FROM <= local.time() < SEND_UNTIL


def next_send_moment(moment: datetime) -> datetime:
    """הרגע המותר הראשון החל מ-``moment`` (UTC נאיבי)."""
    from app import rsvp_timeline

    if is_send_moment(moment):
        return moment
    local = local_time.to_israel(moment)
    day = local.date()
    if local.time() >= SEND_UNTIL or rsvp_timeline.is_weekend(day):
        day = rsvp_timeline.next_active_day(day + timedelta(days=1))
    start = local_time.israel_day_start_utc(day)
    # חצות + 10 שעות = 10:00 בישראל (גם ביום החלפת שעון — סטייה של שעה לכל היותר).
    return start + timedelta(hours=SEND_FROM.hour)


def _event_day(event: models.Event) -> Optional[date]:
    return automation.parse_event_date(event.event_date)


def _resend_at(
    event: models.Event, guest: models.Guest, msg: models.Message, cap_failures: int,
    invited: set[int], now: Optional[datetime],
) -> Optional[datetime]:
    """מתי תצא השליחה החוזרת למוזמן הזה, או ``None`` אם היא לא תצא בכלל."""
    if msg.kind not in RESEND_KINDS or cap_failures > MAX_RESENDS:
        return None
    if guest.rsvp_status != "pending" or sent_personally(guest, msg):
        return None
    if invitations.classify_phone(guest.phone) != "valid" or guest.id in invited:
        return None
    if msg.created_at is None:
        return None
    earliest = msg.created_at + RESEND_AFTER
    # ריצה שפוספסה (למשל אחרי 19:00) — הניסיון יוצא ברגע המותר הבא, לא "בעבר".
    at = next_send_moment(max(earliest, now) if now is not None else earliest)
    event_day = _event_day(event)
    if event_day is not None and local_time.israel_date(at) >= event_day:
        return None
    return at


def issues_for_event(
    db: Session,
    event: models.Event,
    *,
    guests: Optional[list[models.Guest]] = None,
    messages: Optional[list[models.Message]] = None,
    now: Optional[datetime] = None,
) -> list[Issue]:
    """כל המוזמנים באירוע שההודעה האחרונה אליהם לא הגיעה, לפי שם.

    ``now`` — כדי שמועד השליחה החוזרת לא יוצג כרגע שכבר עבר."""
    if guests is None:
        guests = list(db.scalars(
            select(models.Guest).where(models.Guest.event_id == event.id)
        ).all())
    if messages is None:
        messages = cycle_outbound(db, event)
    latest = latest_by_guest(messages)
    invited: Optional[set[int]] = None

    issues: list[Issue] = []
    for g in guests:
        msg = latest.get(g.id)
        reason = classify(msg)
        if reason is None:
            continue
        issue = Issue(guest=g, reason=reason, message=msg)
        if reason == MARKETING_CAP:
            issue.cap_failures = sum(
                1 for m in messages
                if m.guest_id == g.id and m.kind == msg.kind
                and m.status == message_status.FAILED and m.failure_code == CODE_MARKETING_CAP
            )
            if invited is None:
                invited = invitations.invited_guest_ids(db, event.id, event, include_uncertain=True)
            issue.resend_at = _resend_at(event, g, msg, issue.cap_failures, invited, now)
        issues.append(issue)
    issues.sort(key=lambda i: i.guest.full_name or "")
    return issues


def resend_due(db: Session, event: models.Event, now: datetime) -> tuple[int, int]:
    """שולח שוב את ההזמנה למי שנעצר על הגבלת השיווק והגיע זמנו.

    נקרא מהמשימה המתוזמנת (``rsvp_scheduler.process_event``), שכבר בודקת עצירת
    חירום ובקשה פתוחה לשינוי מועד. כאן: שעות ויום שליחה, ושוב — מתחת לנעילת
    השליחה של האירוע — מי כבר קיבל הזמנה (גם "אולי יצאה"), כדי ששתי ריצות או
    שליחה ידנית באותו רגע לא ישלחו פעמיים. השליחה עצמה דרך ``outbound.send_batch``
    (רישום ``pending`` לפני כל ניסיון). מחזיר ``(נשלחו, נכשלו)``.
    """
    from app import communication, outbound

    if not is_send_moment(now):
        return 0, 0
    event_day = _event_day(event)
    if event_day is None or local_time.israel_date(now) >= event_day:
        return 0, 0
    outbound.lock_event_sends(db, event.id)
    due = [
        i for i in issues_for_event(db, event, now=now)
        if i.reason == MARKETING_CAP and i.resend_at is not None and i.resend_at <= now
    ]
    if not due:
        return 0, 0
    ems = communication.event_messages_by_type(db, event.id)
    items = []
    for issue in due:
        em = ems.get(issue.message.kind)
        if em is None or not em.content:
            continue
        text = communication.render_message(
            em.content, communication.communication_values(event, issue.guest),
            message_type=issue.message.kind,
        )
        if not text:
            continue
        items.append(outbound.OutboundItem(
            guest=issue.guest, phone=issue.guest.phone, text=text,
            kind=issue.message.kind, event_message_id=em.id,
        ))
    if not items:
        return 0, 0
    result = outbound.send_batch(db, event, items)
    print(
        f"[veya:whatsapp] marketing-cap resend event={event.id} "
        f"sent={result.sent} failed={result.failed} unknown={result.unknown}",
        flush=True,
    )
    return result.sent, result.failed


# ---- שליחה אישית מהטלפון של הזוג ----

def wa_me_link(phone: str, text: str) -> Optional[str]:
    """קישור שפותח WhatsApp אצל הזוג, עם המוזמן כנמען וההודעה מוכנה."""
    from app.whatsapp_meta import to_wa_number

    number = to_wa_number(phone)
    if number is None:
        return None
    return f"https://wa.me/{number}?text={quote(text)}"


def personal_text(event: models.Event, guest: models.Guest, *, rsvp_open: bool) -> str:
    """ההודעה שהזוג שולח בעצמו (הנוסח: ``messaging.PERSONAL_RESEND_*``)."""
    from app import communication, messaging

    values = communication.communication_values(event, guest)
    name = values.get("guest_name") or ""
    template = messaging.PERSONAL_RESEND_RSVP_TEXT if rsvp_open else messaging.PERSONAL_RESEND_TEXT
    return template.format(
        greeting=f"היי {name}," if name else "היי,",
        occasion=values.get("event_type") or "האירוע",
        link=values.get("rsvp_link") or "",
    )


def sent_personally(guest: models.Guest, msg: Optional[models.Message]) -> bool:
    """האם הזוג פתח WhatsApp לשליחה אישית *אחרי* ההודעה הזו (לא במחזור קודם)."""
    at = guest.personal_whatsapp_at
    if at is None or msg is None:
        return False
    return msg.created_at is None or at >= msg.created_at
