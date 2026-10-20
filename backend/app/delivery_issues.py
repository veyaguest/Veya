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
    # כמה ניסיונות מהסוג הזה לא הגיעו (כל סיבה) — כולל המקור.
    attempts: int = 1
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
    if guest.rsvp_status != "pending" or handed_off(guest, msg):
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
        issue.attempts = sum(
            1 for m in messages
            if m.guest_id == g.id and m.kind == msg.kind
            and m.status in (message_status.FAILED, message_status.BLOCKED)
        )
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


def _outbound_item(event: models.Event, guest: models.Guest, kind: str, ems: dict):
    """אותה הודעה שוב, בנוסח העדכני של האירוע — או ``None`` אם אין לה תוכן."""
    from app import communication, outbound

    em = ems.get(kind)
    if em is None or not em.content:
        return None
    text = communication.render_message(
        em.content, communication.communication_values(event, guest), message_type=kind,
    )
    if not text:
        return None
    return outbound.OutboundItem(
        guest=guest, phone=guest.phone, text=text, kind=kind, event_message_id=em.id,
    )


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
    items = [it for it in (_outbound_item(event, i.guest, i.message.kind, ems) for i in due) if it]
    if not items:
        return 0, 0
    result = outbound.send_batch(db, event, items)
    print(
        f"[veya:whatsapp] marketing-cap resend event={event.id} "
        f"sent={result.sent} failed={result.failed} unknown={result.unknown}",
        flush=True,
    )
    return result.sent, result.failed


# ---- פירוט הסיבה לאדמין ----

GUEST_SIDE = "guest"   # משהו אצל המוזמן — משפיע רק עליו
VEYA_SIDE = "veya"     # משהו אצלנו (תבנית/חשבון/מגבלה) — משפיע על כולם, לתקן לפני ניסיון נוסף


@dataclass(frozen=True)
class ErrorHelp:
    title: str
    detail: str
    side: str


# קודי השגיאה של Meta (statuses[].errors[].code / תגובת ה-API), בעברית לצוות.
# מקור: developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes.
META_ERROR_HELP: dict[int, ErrorHelp] = {
    131049: ErrorHelp(
        "הגבלת הודעות פרסום של WhatsApp",
        "WhatsApp מגבילה כמה הודעות שיווק אדם מקבל. VEYA תנסה שוב אוטומטית אחרי 24 שעות "
        "(עד פעמיים). התזכורות (הודעות שירות) לא מושפעות.", GUEST_SIDE),
    131050: ErrorHelp(
        "המוזמן ויתר על הודעות פרסום",
        "המוזמן ביקש מ-WhatsApp לא לקבל הודעות שיווק. שליחה חוזרת של ההזמנה לא תעזור; "
        "התזכורות ימשיכו להגיע.", GUEST_SIDE),
    131026: ErrorHelp(
        "WhatsApp לא מצליח למסור למספר",
        "ייתכן שאין במספר WhatsApp, שהגרסה ישנה או שלא אושרו תנאי השימוש — Meta לא אומרת "
        "איזה מהם. המוזמן נכנס לתור השיחות; כדאי לבדוק את המספר עם בעלי האירוע.", GUEST_SIDE),
    131021: ErrorHelp(
        "המספר הוא מספר העסק עצמו",
        "המוזמן נרשם עם מספר ה-WhatsApp של VEYA. צריך לתקן את המספר.", GUEST_SIDE),
    131047: ErrorHelp(
        "עברו 24 שעות מההודעה האחרונה של המוזמן",
        "הודעה חופשית מותרת רק בתוך 24 שעות מתשובה של המוזמן. צריך לשלוח תבנית מאושרת.",
        VEYA_SIDE),
    132000: ErrorHelp(
        "מספר הערכים לא תואם לתבנית",
        "חסר או מיותר ערך במשתני התבנית. לבדוק את מיפוי התבנית לפני ניסיון נוסף.", VEYA_SIDE),
    132001: ErrorHelp(
        "התבנית לא קיימת או לא אושרה",
        "התבנית לא נמצאה ב-Meta בשם ובשפה האלה. לבדוק את סטטוס התבנית לפני ניסיון נוסף.",
        VEYA_SIDE),
    132012: ErrorHelp(
        "ערך לא בפורמט שהתבנית מצפה לו",
        "אחד הערכים (קישור/תמונה/טקסט) לא מתאים להגדרת התבנית ב-Meta.", VEYA_SIDE),
    131052: ErrorHelp(
        "Meta לא הצליחה להוריד את התמונה",
        "תמונת ההזמנה לא נטענה. VEYA מעלה אותה מחדש במנה הבאה; אם חוזר — לבדוק את הקובץ.",
        VEYA_SIDE),
    131053: ErrorHelp(
        "העלאת התמונה ל-Meta נכשלה",
        "לבדוק שתמונת ההזמנה היא JPEG או PNG עד 5MB.", VEYA_SIDE),
    130429: ErrorHelp(
        "מגבלת קצב שליחה של החשבון",
        "נשלחו יותר מדי הודעות בזמן קצר. כדאי לחכות כמה דקות ולנסות שוב.", VEYA_SIDE),
    131056: ErrorHelp(
        "יותר מדי הודעות לאותו מספר בזמן קצר",
        "Meta מבקשת לחכות לפני הודעה נוספת לאותו מוזמן.", VEYA_SIDE),
    131048: ErrorHelp(
        "מגבלת ספאם",
        "Meta הגבילה את המספר שלנו בגלל איכות. לבדוק את דירוג האיכות ב-WhatsApp Manager.",
        VEYA_SIDE),
    131031: ErrorHelp(
        "חשבון ה-WhatsApp נעול",
        "Meta נעלה את החשבון (מדיניות/אבטחה). לבדוק ב-WhatsApp Manager — שום הודעה לא תצא.",
        VEYA_SIDE),
    368: ErrorHelp(
        "הגבלה בגלל הפרת מדיניות",
        "Meta הגבילה את החשבון. לבדוק ב-WhatsApp Manager.", VEYA_SIDE),
    131042: ErrorHelp(
        "בעיית תשלום בחשבון Meta",
        "אמצעי התשלום בחשבון ה-WhatsApp Business לא תקין. שום הודעה בתשלום לא תצא.",
        VEYA_SIDE),
    190: ErrorHelp(
        "הטוקן של WhatsApp פג",
        "צריך טוקן חדש בהגדרות השרת. שום הודעה לא תצא עד אז.", VEYA_SIDE),
}

UNKNOWN_HELP = ErrorHelp(
    "סיבה לא מוכרת", "Meta החזירה קוד שאין לנו עליו הסבר. הפירוט המקורי מופיע למטה.",
    GUEST_SIDE,
)


def help_for(msg: models.Message) -> ErrorHelp:
    if msg.status == message_status.BLOCKED:
        return META_ERROR_HELP[131050]
    return META_ERROR_HELP.get(msg.failure_code or 0, UNKNOWN_HELP)


# ---- התראות לאדמין ----

# כמה אחורה מחפשים אירועים עם הודעות שלא הגיעו.
ALERT_LOOKBACK_DAYS = 30


@dataclass
class AdminAlert:
    event: models.Event
    issue: Issue
    help: ErrorHelp
    has_open_call: bool


def admin_alerts(db: Session, now: Optional[datetime] = None) -> list[AdminAlert]:
    """כל המוזמנים (באירועים שעוד לא התקיימו) שההודעה האחרונה אליהם לא הגיעה,
    ועדיין לא ענו. רק שליחות אמיתיות (``event_cycle.current_sends``)."""
    now = now or datetime.utcnow()
    today = local_time.israel_date(now)
    since = now - timedelta(days=ALERT_LOOKBACK_DAYS)
    event_ids = set(db.scalars(
        select(models.Message.event_id).where(
            models.Message.direction == "outbound",
            models.Message.status.in_((message_status.FAILED, message_status.BLOCKED)),
            models.Message.created_at >= since,
        ).distinct()
    ).all())
    if not event_ids:
        return []
    events = [
        e for e in db.scalars(select(models.Event).where(models.Event.id.in_(event_ids))).all()
        if (_event_day(e) or today) >= today
    ]
    open_calls = set(db.scalars(
        select(models.CallTask.guest_id).where(
            models.CallTask.event_id.in_([e.id for e in events] or [0]),
            models.CallTask.status == "open",
        )
    ).all())
    out: list[AdminAlert] = []
    for e in events:
        for issue in issues_for_event(db, e, now=now):
            if issue.guest.rsvp_status in ("confirmed", "declined"):
                continue  # כבר ענו (למשל בשיחה) — אין מה לפתור
            out.append(AdminAlert(
                event=e, issue=issue, help=help_for(issue.message),
                has_open_call=issue.guest.id in open_calls,
            ))
    out.sort(key=lambda a: (a.event.event_date or "", a.event.id, a.issue.guest.full_name or ""))
    return out


class ResendRefused(ValueError):
    """למה אי אפשר לשלוח שוב עכשיו — טקסט לאדמין."""


def resend_one(db: Session, event: models.Event, guest: models.Guest, now: Optional[datetime] = None):
    """שליחה חוזרת ידנית (כפתור האדמין) של ההודעה האחרונה שלא הגיעה למוזמן.

    כל הבדיקות שוב תחת נעילת השליחה של האירוע: ההודעה האחרונה עדיין לא הגיעה
    (**לעולם לא** ``pending`` או נשלחה — לחיצה כפולה נעצרת כאן), עצירת חירום,
    בקשה פתוחה לשינוי מועד, יום האירוע, טלפון תקין, ולהזמנה — שאין לו כבר הזמנה
    (גם "אולי יצאה"). מחזיר ``outbound.BatchResult``; זורק ``ResendRefused``.
    """
    from app import communication, messaging, outbound, postponement_service

    now = now or datetime.utcnow()
    if messaging.emergency_stop_active():
        raise ResendRefused("עצירת החירום פעילה — שום הודעה לא יוצאת.")
    if postponement_service.open_request_of(db, event.id) is not None:
        raise ResendRefused("יש לאירוע בקשה פתוחה לשינוי מועד — לא שולחים עד שתיסגר.")
    event_day = _event_day(event)
    if event_day is not None and local_time.israel_date(now) > event_day:
        raise ResendRefused("האירוע כבר התקיים.")
    if invitations.classify_phone(guest.phone) != "valid":
        raise ResendRefused("למוזמן אין מספר טלפון תקין.")
    outbound.lock_event_sends(db, event.id)
    issue = next((i for i in issues_for_event(db, event, guests=[guest], now=now)), None)
    if issue is None:
        raise ResendRefused("ההודעה האחרונה למוזמן כבר יצאה או ממתינה לעדכון — לא שולחים שוב.")
    kind = issue.message.kind
    if handed_off(guest, issue.message) and guest.whatsapp_handoff_sent_at is not None:
        raise ResendRefused("בעלי האירוע כבר פתחו WhatsApp כדי לשלוח בעצמם — לא שולחים שוב.")
    if kind == "invitation" and guest.id in invitations.invited_guest_ids(
        db, event.id, event, include_uncertain=True,
    ):
        raise ResendRefused("למוזמן כבר יש הזמנה שיצאה — לא שולחים שוב.")
    item = _outbound_item(event, guest, kind, communication.event_messages_by_type(db, event.id))
    if item is None:
        raise ResendRefused("להודעה הזו אין כרגע תוכן לשליחה.")
    return outbound.send_batch(db, event, [item])


# ---- מספרים שצריך לתקן (אדמין → בעלי האירוע) ----

PHONE_MISSING = "missing"
PHONE_INVALID = "invalid"
PHONE_WHATSAPP = "whatsapp"   # הפורמט תקין, אבל Meta לא מצליחה למסור (131026)


def phone_problem(guest: models.Guest, delivery: Optional[str]) -> Optional[str]:
    """למה צריך לבדוק את המספר של המוזמן, או ``None``."""
    kind = invitations.classify_phone(guest.phone)
    if kind == "missing":
        return PHONE_MISSING
    if kind == "invalid":
        return PHONE_INVALID
    if delivery == UNDELIVERABLE:
        return PHONE_WHATSAPP
    return None


def alert_active(guest: models.Guest) -> bool:
    """הצוות התריע, והמספר עוד לא השתנה מאז."""
    return guest.phone_alert_at is not None and (guest.phone or "") == (guest.phone_alert_phone or "")


@dataclass
class PhoneProblem:
    guest: models.Guest
    problem: str


def phone_problems(db: Session, now: Optional[datetime] = None) -> list[tuple[models.Event, list[PhoneProblem]]]:
    """לכל אירוע שעוד לא התקיים: מוזמנים שעוד לא ענו ושהמספר שלהם צריך בדיקה."""
    from app import call_ops

    now = now or datetime.utcnow()
    today = local_time.israel_date(now)
    events = [
        e for e in db.scalars(select(models.Event).where(models.Event.event_date != "")).all()
        if (_event_day(e) or today) >= today
    ]
    if not events:
        return []
    guests = list(db.scalars(select(models.Guest).where(
        models.Guest.event_id.in_([e.id for e in events]),
        models.Guest.rsvp_status.in_(("pending", "maybe")),
    ).order_by(models.Guest.full_name)).all())
    delivery = call_ops.delivery_states(db, guests)
    by_event: dict[int, list[PhoneProblem]] = {}
    for g in guests:
        problem = phone_problem(g, delivery.get(g.id))
        if problem:
            by_event.setdefault(g.event_id, []).append(PhoneProblem(g, problem))
    out = [(e, by_event[e.id]) for e in events if e.id in by_event]
    out.sort(key=lambda pair: (pair[0].event_date or "", pair[0].id))
    return out


def raise_phone_alerts(guests: list[models.Guest], now: Optional[datetime] = None) -> int:
    """מסמן "צוות VEYA ביקש לבדוק את המספר" — מופיע לבעלי האירוע במסך המוזמנים."""
    now = now or datetime.utcnow()
    for g in guests:
        g.phone_alert_at = now
        g.phone_alert_phone = g.phone or ""
    return len(guests)


def couple_phone_alerts(db: Session, event: models.Event) -> list[PhoneProblem]:
    """מה בעלי האירוע רואים: מוזמנים שהצוות התריע עליהם, המספר לא השתנה,
    והבעיה עדיין קיימת."""
    from app import call_ops

    flagged = [
        g for g in db.scalars(select(models.Guest).where(
            models.Guest.event_id == event.id, models.Guest.phone_alert_at.is_not(None),
        )).all()
        if alert_active(g)
    ]
    delivery = call_ops.delivery_states(db, flagged)
    out = []
    for g in flagged:
        problem = phone_problem(g, delivery.get(g.id))
        if problem:
            out.append(PhoneProblem(g, problem))
    out.sort(key=lambda p: p.guest.full_name or "")
    return out


# ---- העברה לבעלי האירוע: שליחה מה-WhatsApp האישי ----

def handed_off(guest: models.Guest, msg: Optional[models.Message]) -> bool:
    """הצוות העביר לבעלי האירוע *אחרי* ההודעה הזו (לא במחזור/שליחה קודמים)."""
    at = guest.whatsapp_handoff_at
    if at is None or msg is None:
        return False
    return msg.created_at is None or at >= msg.created_at


def hand_off(guests: list[models.Guest], now: Optional[datetime] = None) -> int:
    now = now or datetime.utcnow()
    for g in guests:
        g.whatsapp_handoff_at = now
        g.whatsapp_handoff_sent_at = None
    return len(guests)


def wa_me_link(phone: str, text: str) -> Optional[str]:
    """קישור שפותח WhatsApp אצל בעלי האירוע, עם המוזמן כנמען וההודעה מוכנה."""
    from app.whatsapp_meta import to_wa_number

    number = to_wa_number(phone)
    if number is None:
        return None
    return f"https://wa.me/{number}?text={quote(text)}"


def personal_text(event: models.Event, guest: models.Guest, *, rsvp_open: bool) -> str:
    """ההודעה שבעלי האירוע שולחים בעצמם (הנוסח: ``messaging.PERSONAL_RESEND_*``)."""
    from app import communication, messaging

    values = communication.communication_values(event, guest)
    name = values.get("guest_name") or ""
    template = messaging.PERSONAL_RESEND_RSVP_TEXT if rsvp_open else messaging.PERSONAL_RESEND_TEXT
    return template.format(
        greeting=f"היי {name}," if name else "היי,",
        occasion=values.get("event_type") or "האירוע",
        link=values.get("rsvp_link") or "",
    )


@dataclass
class Handoff:
    guest: models.Guest
    message: models.Message
    link: Optional[str]


def handoffs_for_couple(db: Session, event: models.Event) -> list[Handoff]:
    """מה בעלי האירוע רואים: מוזמנים שהצוות העביר אליהם, וההודעה האחרונה אליהם
    עדיין לא הגיעה (אם בינתיים כן הגיעה — הפריט נעלם מעצמו)."""
    from app import guest_journey

    guests = list(db.scalars(select(models.Guest).where(
        models.Guest.event_id == event.id, models.Guest.whatsapp_handoff_at.is_not(None),
    )).all())
    if not guests:
        return []
    rsvp_open = guest_journey.rsvp_is_open(event)
    out = []
    for issue in issues_for_event(db, event, guests=guests):
        g = issue.guest
        if not handed_off(g, issue.message) or g.rsvp_status in ("confirmed", "declined"):
            continue
        out.append(Handoff(
            guest=g, message=issue.message,
            link=wa_me_link(g.phone or "", personal_text(event, g, rsvp_open=rsvp_open)),
        ))
    out.sort(key=lambda h: h.guest.full_name or "")
    return out

