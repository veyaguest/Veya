"""תיבת WhatsApp לשירות לקוחות — מי שכותב למספר של VEYA, ומה עושים עם זה.

המספר של VEYA מחובר ל-Cloud API של Meta, ולכן אי אפשר לפתוח אותו באפליקציית
WhatsApp. כל מענה יוצא מכאן (מסך "WhatsApp" באדמין ובמסך הטלפן).

## לאן הולכת הודעה נכנסת (החלטות המייסד, 2026-10-19)
הקורא (``routers/messaging._handle_inbound_message``) כבר טיפל בלחיצה על כפתור
אישור/ביטול הגעה. מה שמגיע לכאן — ``route_inbound``:

1. **הטלפון שייך לחשבון ב-VEYA** (``User.phone`` אחרי נרמול) → תור השירות.
   הרבה בעלי אירוע מוסיפים את עצמם כמוזמנים; מי שיש לו חשבון ושכותב —
   מדבר עם VEYA, לא עם האירוע של עצמו.
2. **מוזמן שזוהה בוודאות**, או טלפון משותף לכמה מוזמנים *באותו אירוע* → עובר
   לבעלי האירוע (``whatsapp_inbound.record_free_message`` — שורת ``Message`` על
   האירוע, כמו קודם), ונשלח להם מייל. VEYA **לא** עונה למוזמן.
3. **כל השאר** (לא מוכר, מוזמן בכמה אירועים שונים) → תור השירות.

## תשובה אוטומטית
בתור השירות בלבד, פעם אחת ל-24 שעות לכל מספר (``claim_auto_reply`` — תפיסה
אטומית, כך ששתי הודעות באותו רגע לא מייצרות שתי תשובות). הנוסח לפי שעות
הפעילות (א׳–ה׳ 9:00–18:00, שעון ישראל) — ``messaging.support_auto_reply``.
מתג כיבוי: ``whatsapp.inbox_auto_reply`` בהגדרות האדמין.

## שליחה — אותם כללי בטיחות כמו כל WhatsApp ב-VEYA (``deliver``)
- עצירת חירום → לא יוצא כלום (``blocked``).
- מצב ``mock`` → לא יוצא כלום. ההודעה נשמרת כ-``mock`` ("לא נשלחה — מצב הדגמה").
- מצב ``meta_test`` → רק למספרים שברשימת הבדיקה.
- מצב ``meta`` → ``whatsapp_meta.send_text``.
טקסט חופשי מותר רק בתוך 24 שעות מההודעה האחרונה של הפונה (``window_open``) —
אחרת Meta דוחה (131047) וצריך תבנית מאושרת.

## רישום לפני שליחה
כל הודעה יוצאת נשמרת כ-``pending`` (commit) לפני הפנייה ל-Meta, ומתעדכנת
לתוצאה אחרי. כך נפילה באמצע לא משאירה הודעה שיצאה בלי עקבות (כמו ``outbound``).

## לוגים
רק מזהים פנימיים ותוצאה. לעולם לא טלפון, שם או תוכן.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app import audit, local_time, message_status, messaging, models, whatsapp_inbound

# ---- סטטוס שיחה ----
OPEN = "open"
ANSWERED = "answered"
CLOSED = "closed"
STATUSES = (OPEN, ANSWERED, CLOSED)

# ---- מי כתב ----
SENDER_ACCOUNT = "account"
SENDER_UNKNOWN = "unknown"
SENDER_GUEST = "guest"  # מוזמן שלא זוהה בוודאות (כמה אירועים / מספר שהשתנה)

# ---- סטטוס הודעה יוצאת (בנוסף לערכי ``message_status``) ----
MOCK = "mock"
BLOCKED = "blocked"

# ---- תוצאות ניתוב ----
TO_SUPPORT = "support"
TO_HOSTS = "hosts"
DUPLICATE = "duplicate"

#: חלון שירות הלקוחות של Meta — טקסט חופשי מותר רק בתוכו.
WINDOW = timedelta(hours=24)
#: תשובה אוטומטית — לכל היותר פעם אחת בפרק הזמן הזה, לכל מספר.
AUTO_REPLY_EVERY = timedelta(hours=24)
#: שעות הפעילות (שעון ישראל). ראשון–חמישי = weekday 6, 0, 1, 2, 3.
SERVICE_DAYS = frozenset({6, 0, 1, 2, 3})
SERVICE_OPEN_HOUR = 9
SERVICE_CLOSE_HOUR = 18

MAX_BODY = 4096
#: מייל לבעלי האירוע — לכל היותר אחד לאירוע בפרק הזמן הזה.
HOST_EMAIL_EVERY = timedelta(hours=3)
HOST_EMAIL_AUDIT = "guest_message_email"

_CALLBACK_RE = re.compile(r"^veya:w(\d+)$")

_TYPE_LABEL = {
    "image": "תמונה", "audio": "הקלטה", "video": "סרטון", "document": "מסמך",
    "sticker": "מדבקה", "location": "מיקום", "contacts": "איש קשר",
    "reaction": "תגובה (אימוג'י)", "button": "לחיצה על כפתור", "interactive": "לחיצה על כפתור",
}


def _now() -> datetime:
    """נקודת החלפה לבדיקות."""
    return datetime.utcnow()


def _log(outcome: str, **ids) -> None:
    parts = " ".join(f"{k}={v}" for k, v in ids.items() if v is not None)
    print(f"[veya:whatsapp] inbox {outcome} {parts}".rstrip(), flush=True)


# ─── זיהוי ─────────────────────────────────────────────────────────────────

def thread_phone(raw: Optional[str]) -> Optional[str]:
    """המספר כפי שנשמר על השיחה: ``05XXXXXXXX`` לישראלי, ``+<ספרות>`` לאחר."""
    local = whatsapp_inbound.normalize_sender(raw)
    if local:
        return local
    digits = re.sub(r"\D", "", raw or "")
    return f"+{digits}" if 6 <= len(digits) <= 20 else None


def accounts_with_phone(db: Session, normalized: str) -> list[models.User]:
    """חשבונות VEYA שהטלפון שלהם, אחרי נרמול, זהה בדיוק."""
    tail = normalized[-9:]
    rows = db.scalars(
        select(models.User).where(whatsapp_inbound._phone_digits(models.User.phone).like(f"%{tail}"))
    ).all()
    return [u for u in rows if whatsapp_inbound.normalize_sender(u.phone) == normalized]


def already_processed(db: Session, provider_message_id: str) -> bool:
    """האם ההודעה כבר נקלטה — בתיבה או ביומן ההודעות של אירוע."""
    if whatsapp_inbound.already_processed(db, provider_message_id):
        return True
    return db.scalar(
        select(models.WhatsAppThreadMessage.id).where(
            models.WhatsAppThreadMessage.provider_message_id == provider_message_id
        )
    ) is not None


def describe_body(message_type: str, text_body: Optional[str]) -> str:
    if text_body and text_body.strip():
        return text_body.strip()[:MAX_BODY]
    return f"[{_TYPE_LABEL.get(message_type, 'הודעה')}]"


# ─── קליטה ─────────────────────────────────────────────────────────────────

@dataclass
class Routed:
    outcome: str
    thread_id: Optional[int] = None
    message_id: Optional[int] = None
    #: הודעה יוצאת (תשובה אוטומטית) שנרשמה ומחכה לשליחה אחרי ה-commit.
    auto_reply_id: Optional[int] = None
    #: אירוע שבעליו צריכים לקבל מייל "מוזמן כתב לכם".
    host_event_id: Optional[int] = None


def route_inbound(
    db: Session,
    *,
    provider_message_id: str,
    from_phone: Optional[str],
    context_id: Optional[str],
    message_type: str,
    text_body: Optional[str],
    profile_name: str = "",
) -> Routed:
    """מנתב הודעה נכנסת (שאינה תשובת RSVP). לא עושה commit, לא שולח כלום."""
    if already_processed(db, provider_message_id):
        _log(DUPLICATE)
        return Routed(DUPLICATE)

    sender = whatsapp_inbound.normalize_sender(from_phone)
    accounts = accounts_with_phone(db, sender) if sender else []
    if accounts:
        return record_support_message(
            db, provider_message_id=provider_message_id, from_phone=from_phone,
            message_type=message_type, text_body=text_body, profile_name=profile_name,
            sender_kind=SENDER_ACCOUNT, user_id=accounts[0].id if len(accounts) == 1 else None,
        )

    reason, event_id = whatsapp_inbound.record_free_message(
        db, provider_message_id=provider_message_id, from_phone=from_phone,
        context_id=context_id, message_type=message_type, text_body=text_body,
    )
    if reason == "recorded":
        return Routed(TO_HOSTS, host_event_id=event_id)
    if reason == whatsapp_inbound.DUPLICATE:
        return Routed(DUPLICATE)
    kind = SENDER_GUEST if reason in (whatsapp_inbound.AMBIGUOUS, whatsapp_inbound.CONTEXT_MISMATCH) else SENDER_UNKNOWN
    return record_support_message(
        db, provider_message_id=provider_message_id, from_phone=from_phone,
        message_type=message_type, text_body=text_body, profile_name=profile_name,
        sender_kind=kind, user_id=None,
    )


def record_support_message(
    db: Session,
    *,
    provider_message_id: str,
    from_phone: Optional[str],
    message_type: str,
    text_body: Optional[str],
    profile_name: str,
    sender_kind: str,
    user_id: Optional[int],
) -> Routed:
    """שומר הודעה בתור השירות, ותופס תשובה אוטומטית אם הגיע הזמן. בלי commit."""
    phone = thread_phone(from_phone)
    if phone is None:
        _log("skipped_no_phone")
        return Routed(DUPLICATE)
    now = _now()
    T = models.WhatsAppThread
    thread = db.scalar(select(T).where(T.phone == phone))
    if thread is None:
        thread = T(phone=phone, created_at=now)
        db.add(thread)
    if profile_name:
        thread.profile_name = profile_name.strip()[:120]
    thread.sender_kind = sender_kind
    if sender_kind == SENDER_ACCOUNT:
        thread.user_id = user_id
    thread.status = OPEN
    thread.last_inbound_at = now
    thread.last_message_at = now
    thread.updated_at = now
    db.flush()

    msg = models.WhatsAppThreadMessage(
        thread_id=thread.id, direction="inbound", kind=message_type or "text",
        body=describe_body(message_type, text_body), status=message_status.RECEIVED,
        provider_message_id=provider_message_id, created_at=now,
    )
    db.add(msg)
    db.flush()  # כפילות במקביל → IntegrityError עכשיו, לא בתוך SAVEPOINT מאוחר

    auto_id = None
    if claim_auto_reply(db, thread, now):
        auto = models.WhatsAppThreadMessage(
            thread_id=thread.id, direction="outbound", kind="auto_reply",
            body=messaging.support_auto_reply(in_service_hours(now)),
            status=message_status.PENDING, created_at=now,
        )
        db.add(auto)
        db.flush()
        auto_id = auto.id
    _log("support_message", thread=thread.id, kind=sender_kind, auto_reply="yes" if auto_id else "no")
    return Routed(TO_SUPPORT, thread_id=thread.id, message_id=msg.id, auto_reply_id=auto_id)


def auto_reply_enabled() -> bool:
    try:
        from app import settings_registry

        return bool(settings_registry.value("whatsapp.inbox_auto_reply"))
    except Exception:  # noqa: BLE001 — הגדרות לא זמינות → ברירת המחדל (דלוק)
        return True


def claim_auto_reply(db: Session, thread: models.WhatsAppThread, now: datetime) -> bool:
    """תפיסה אטומית של "התשובה האוטומטית של 24 השעות האלה". ``True`` = לשלוח."""
    if not auto_reply_enabled():
        return False
    T = models.WhatsAppThread
    claimed = db.execute(
        update(T)
        .where(T.id == thread.id)
        .where(or_(T.auto_reply_at.is_(None), T.auto_reply_at <= now - AUTO_REPLY_EVERY))
        .values(auto_reply_at=now)
        .execution_options(synchronize_session=False)
    ).rowcount
    if claimed == 1:
        thread.auto_reply_at = now
        return True
    return False


def in_service_hours(moment: datetime) -> bool:
    """א׳–ה׳, 9:00–18:00 שעון ישראל. ``moment`` — UTC נאיבי."""
    il = local_time.to_israel(moment)
    return il.weekday() in SERVICE_DAYS and SERVICE_OPEN_HOUR <= il.hour < SERVICE_CLOSE_HOUR


# ─── חלון 24 השעות ─────────────────────────────────────────────────────────

def window_closes_at(thread: models.WhatsAppThread) -> Optional[datetime]:
    return thread.last_inbound_at + WINDOW if thread.last_inbound_at else None


def window_open(thread: models.WhatsAppThread, now: Optional[datetime] = None) -> bool:
    closes = window_closes_at(thread)
    return closes is not None and (now or _now()) < closes


# ─── שליחה ─────────────────────────────────────────────────────────────────

def callback_ref(row: models.WhatsAppThreadMessage) -> str:
    return f"veya:w{row.id}"


def deliver(db: Session, row: models.WhatsAppThreadMessage) -> None:
    """שולח הודעה יוצאת שכבר נשמרה כ-``pending``, ומעדכן אותה לתוצאה. בלי commit.

    לעולם לא זורק. כל ההחלטות "לשלוח או לא" כאן, במקום אחד.
    """
    thread = db.get(models.WhatsAppThread, row.thread_id)
    now = _now()

    def done(status: str, reason: str = "") -> None:
        row.status = status
        row.failure_reason = reason[:500]

    if thread is None:
        return done(message_status.FAILED, "השיחה לא נמצאה")
    if messaging.emergency_stop_active():
        _log("not_sent", message=row.id, reason="emergency_stop")
        return done(BLOCKED, "לא נשלחה — עצירת חירום של WhatsApp פעילה")
    if not window_open(thread, now):
        _log("not_sent", message=row.id, reason="window_closed")
        return done(message_status.FAILED, "עברו 24 שעות מההודעה האחרונה של הפונה — אפשר לפנות רק בתבנית מאושרת")
    mode = messaging.whatsapp_mode()
    if mode == messaging.MODE_MOCK:
        _log("not_sent", message=row.id, reason="mock")
        return done(MOCK, "לא נשלחה — מצב הדגמה")
    local = whatsapp_inbound.normalize_sender(thread.phone)
    if local is None:
        _log("not_sent", message=row.id, reason="not_israeli")
        return done(message_status.FAILED, "אפשר לענות כאן רק למספר ישראלי")
    if mode == messaging.MODE_META_TEST and local not in messaging.test_recipients():
        _log("not_sent", message=row.id, reason="test_blocked")
        return done(BLOCKED, messaging.TEST_BLOCKED_DETAIL)

    from app import whatsapp_meta

    try:
        res = whatsapp_meta.send_text(phone=local, body=row.body, callback_data=callback_ref(row))
    except Exception as exc:  # noqa: BLE001 — אחרי שהבקשה אולי יצאה: "לא ידוע"
        _log("send_error", message=row.id, error=type(exc).__name__)
        return done(message_status.PENDING, "לא ידוע אם ההודעה יצאה — ממתינים לעדכון מ-WhatsApp")
    row.status = res.status
    row.failure_reason = (res.detail or "")[:500] if not res.ok else ""
    row.failure_code = res.error_code
    if res.provider_message_id:
        row.provider_message_id = res.provider_message_id
    if res.ok:
        row.sent_at = now
    _log("sent" if res.ok else res.status, message=row.id, code=res.error_code)


def is_delivered_or_saved(row: models.WhatsAppThreadMessage) -> bool:
    """הודעה שיצאה (או נשמרה במצב הדגמה) — נחשבת "ענינו"."""
    return row.status in (message_status.SENT, message_status.DELIVERED, message_status.READ, MOCK)


def send_auto_reply(db: Session, message_id: int) -> None:
    """רץ אחרי ה-commit של ההודעה הנכנסת (ברקע). עושה commit."""
    row = db.get(models.WhatsAppThreadMessage, message_id)
    if row is None or row.status != message_status.PENDING or row.provider_message_id:
        return
    deliver(db, row)
    db.commit()


# ─── עדכוני מסירה מ-Meta ───────────────────────────────────────────────────

def apply_status(
    db: Session, *, provider_message_id: str, status: str, callback_data: Optional[str],
    reason: str = "", failure_code: Optional[int] = None,
) -> bool:
    """עדכון סטטוס להודעה יוצאת מהתיבה. ``True`` אם נמצאה הודעה שלנו."""
    M = models.WhatsAppThreadMessage
    row = db.scalar(select(M).where(M.provider_message_id == provider_message_id))
    if row is None and callback_data:
        m = _CALLBACK_RE.match(callback_data)
        if m:
            candidate = db.get(M, int(m.group(1)))
            if (candidate is not None and candidate.direction == "outbound"
                    and not candidate.provider_message_id
                    and candidate.status == message_status.PENDING):
                candidate.provider_message_id = provider_message_id
                row = candidate
    if row is None or row.direction != "outbound":
        return False
    rank = {message_status.SENT: 1, message_status.DELIVERED: 2, message_status.READ: 3}
    if status in rank and rank.get(row.status, 0) >= rank[status]:
        return True  # לא נסוגים (Meta לא מבטיחה סדר)
    if status not in message_status.OUTBOUND_STATUSES:
        return True
    row.status = status
    if status in (message_status.FAILED, message_status.BLOCKED):
        row.failure_reason = (reason or "")[:500]
        row.failure_code = failure_code
    elif row.sent_at is None:
        row.sent_at = _now()
    return True


# ─── שאלות של מוזמנים → בעלי האירוע ───────────────────────────────────────

def notify_hosts(db: Session, event_id: int) -> int:
    """מייל "מוזמן כתב לכם" לבעלי האירוע (בעלים + שותף/ה, מייל מאומת).

    לכל היותר מייל אחד לאירוע כל ``HOST_EMAIL_EVERY`` (לפי יומן הפעילות). בלי
    תוכן ההודעה ובלי טלפון. מחזיר כמה מיילים יצאו. עושה commit.
    """
    from app import emailer, event_terms, partners

    event = db.get(models.Event, event_id)
    if event is None:
        return 0
    now = _now()
    recent = db.scalar(
        select(models.AuditLog.id).where(
            models.AuditLog.event_id == event_id,
            models.AuditLog.action == HOST_EMAIL_AUDIT,
            models.AuditLog.created_at >= now - HOST_EMAIL_EVERY,
        )
    )
    if recent is not None:
        _log("host_email_throttled", event=event_id)
        return 0
    audit.record(db, HOST_EMAIL_AUDIT, event_id=event_id, detail="נשלח מייל: מוזמנים כתבו בוואטסאפ")
    db.commit()  # התפיסה נשמרת לפני השליחה — שתי קריאות במקביל לא שולחות פעמיים
    sent = 0
    for user in partners.managers_of(db, event):
        if not user.email or user.email_verified_at is None or user.disabled:
            continue
        res = emailer.send_guest_messages_notice(
            to=user.email, guests_label=event_terms.get_event_terms(event.event_type).guests_label,
            idempotency_key=f"veya-guest-msg-{event.id}-{user.id}-{now:%Y%m%d%H%M}",
        )
        sent += 1 if res.ok else 0
    _log("host_email", event=event_id, sent=sent)
    return sent


def guest_messages(db: Session, event_id: int, *, include_handled: bool = False) -> list[models.Message]:
    """הודעות שמוזמנים כתבו לבעלי האירוע (שורות ``Message`` נכנסות)."""
    M = models.Message
    statuses = [message_status.NEEDS_ATTENTION]
    if include_handled:
        statuses.append(message_status.HANDLED)
    return list(db.scalars(
        select(M).where(
            M.event_id == event_id, M.direction == "inbound", M.kind == "inbound",
            M.channel == "whatsapp", M.status.in_(statuses),
        ).order_by(M.created_at.desc(), M.id.desc())
    ).all())


# ─── מחיקת חשבון ───────────────────────────────────────────────────────────

def delete_for_user(db: Session, user_id: int) -> None:
    """לפני מחיקת משתמש: השיחות שלו (מידע אישי) נמחקות; שיוך והודעות שהוא
    שלח כאיש צוות — רק מנותקים ממנו. בלי commit."""
    T, M = models.WhatsAppThread, models.WhatsAppThreadMessage
    for thread in db.scalars(select(T).where(T.user_id == user_id)).all():
        for row in db.scalars(select(M).where(M.thread_id == thread.id)).all():
            db.delete(row)
        db.flush()
        db.delete(thread)
    for thread in db.scalars(select(T).where(T.assigned_to_id == user_id)).all():
        thread.assigned_to_id = None
    for row in db.scalars(select(M).where(M.sent_by_id == user_id)).all():
        row.sent_by_id = None
    db.flush()
