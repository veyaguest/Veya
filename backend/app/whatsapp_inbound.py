"""הודעות WhatsApp נכנסות — למי הן שייכות, ומה עושים איתן.

## זיהוי המוזמן: רק התאמה חד-משמעית
עד 2026-10-12 תשובה נכנסת שויכה לפי 9 הספרות האחרונות של הטלפון, *בכל
האירועים במערכת*, ונלקחה ההתאמה הראשונה. טלפון משפחתי משותף, או אורח
שמוזמן לשני אירועים, היו מעדכנים RSVP של מוזמן אחר. הכללים היום:

1. **``context.id``** — מזהה ההודעה שלנו שהאורח הגיב עליה (Meta שולחת אותו
   כשהתשובה היא לחיצת כפתור או תגובה להודעה). ההודעה הזו שמורה אצלנו על
   השורה של מוזמן אחד בדיוק — זו ההתאמה החזקה ביותר. אם הטלפון של אותו
   מוזמן כבר לא תואם לשולח (המספר עודכן מאז) — לא מנחשים: טיפול ידני.
2. **טלפון** — רק אם אין ``context.id`` מוכר. השוואה מלאה אחרי נרמול
   (``validators.normalize_israeli_phone``), לא סיומת. **מוזמן אחד בדיוק**
   בכל המערכת → התאמה. יותר מאחד → עמימות: לא נוגעים ב-RSVP.
3. מספר שאינו טלפון ישראלי תקין, או שלא נמצא — אין התאמה.

## החלת התשובה: אותה לוגיקה כמו הקישור האישי
תשובה שזוהתה עוברת דרך ``rsvp_response.apply_response`` (הפונקציה של הקישור
האישי ושל המוקד), עם בדיקת חלון אישורי ההגעה (``guest_journey.rsvp_is_open``)
ורישום ביומן הפעילות (``confirm_submit``) — בדיוק כמו ``routers/confirm.py``.
תשובה לפני שהחלון נפתח נשמרת ביומן ההודעות כ"דורש טיפול", בלי לשנות RSVP.

## בלי כפילויות
כל הודעה נכנסת נשמרת עם מזהה ה-Meta שלה (``provider_message_id``, אינדקס
ייחודי). webhook שחוזר עם אותה הודעה מזוהה ומדולג — ה-RSVP לא מוחל פעמיים,
ושורת יומן לא נוצרת פעמיים.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit, event_cycle, guest_journey, message_status, models, rsvp_response
from app.validators import normalize_israeli_phone

# ---- תוצאות זיהוי ----
MATCH_CONTEXT = "context"
MATCH_PHONE = "phone"
NOT_FOUND = "not_found"
AMBIGUOUS = "ambiguous"
INVALID_PHONE = "invalid_phone"
CONTEXT_MISMATCH = "context_mismatch"

# ---- תוצאות טיפול בתשובת RSVP ----
APPLIED = "applied"
DUPLICATE = "duplicate"
WINDOW_CLOSED = "window_closed"

# ניסוח קצר ליומן — בלי טלפון ובלי שם (המידע שיש לנו הוא שהשיוך נכשל).
_UNMATCHED_LABEL = {
    NOT_FOUND: "המספר לא נמצא ברשימות המוזמנים",
    AMBIGUOUS: "המספר משותף לכמה מוזמנים",
    INVALID_PHONE: "המספר אינו מספר ישראלי תקין",
    CONTEXT_MISMATCH: "מספר הטלפון של המוזמן השתנה מאז ההודעה",
}


def rsvp_replies_enabled() -> bool:
    """האם לחיצה על כפתור אישור/ביטול הגעה ב-WhatsApp מעדכנת RSVP.

    **כבוי כברירת מחדל** (``WHATSAPP_INBOUND_RSVP`` ≠ ``1``): אישור הגעה רק
    דרך הקישור האישי, והודעות נכנסות נשמרות כ"דורש טיפול" בלבד. הלוגיקה
    (``record_rsvp_reply``) נשארת קיימת ונבדקת, להפעלה מפורשת בעתיד.
    """
    return (os.getenv("WHATSAPP_INBOUND_RSVP") or "").strip() == "1"


@dataclass
class GuestMatch:
    guest: Optional[models.Guest]
    reason: str
    # כמה מוזמנים תאמו לטלפון (לעמימות). לא נחשף החוצה — רק ספירה.
    candidates: int = 0
    candidate_event_ids: tuple[int, ...] = ()


def normalize_sender(raw: Optional[str]) -> Optional[str]:
    """הטלפון בפורמט הפנימי (``05XXXXXXXX``), או ``None`` אם אינו תקין."""
    try:
        return normalize_israeli_phone(raw or "")
    except ValueError:
        return None


def _phone_digits(column):
    """ביטוי SQL: הטלפון השמור בלי מפרידים נפוצים (עובד ב-SQLite וב-Postgres)."""
    expr = column
    for ch in ("-", " ", "+", "(", ")", "."):
        expr = func.replace(expr, ch, "")
    return expr


def guests_with_phone(db: Session, normalized: str) -> list[models.Guest]:
    """כל המוזמנים (בכל האירועים) שהטלפון שלהם, אחרי נרמול, זהה בדיוק.

    הסינון ב-SQL לפי סיומת הוא רק צמצום; ההכרעה היא השוואה מלאה בפייתון.
    """
    tail = normalized[-9:]
    rows = db.scalars(
        select(models.Guest).where(_phone_digits(models.Guest.phone).like(f"%{tail}"))
    ).all()
    return [g for g in rows if normalize_sender(g.phone) == normalized]


def match_guest(
    db: Session, from_phone: Optional[str], context_id: Optional[str] = None,
) -> GuestMatch:
    """מזהה את המוזמן ששלח הודעה נכנסת — רק כשההתאמה חד-משמעית."""
    sender = normalize_sender(from_phone)
    if sender is None:
        return GuestMatch(None, INVALID_PHONE)

    if context_id:
        replied_to = db.scalar(
            select(models.Message)
            .where(models.Message.provider_message_id == context_id)
            .where(models.Message.direction == "outbound")
        )
        if replied_to is not None and replied_to.guest_id is not None:
            guest = db.get(models.Guest, replied_to.guest_id)
            if guest is not None and normalize_sender(guest.phone) == sender:
                return GuestMatch(guest, MATCH_CONTEXT, 1, (guest.event_id,))
            return GuestMatch(
                None, CONTEXT_MISMATCH, 0,
                (replied_to.event_id,) if replied_to.event_id else (),
            )
        # ``context.id`` שאינו מוכר לנו (למשל הודעה מסביבה אחרת) — ממשיכים לטלפון.

    candidates = guests_with_phone(db, sender)
    event_ids = tuple(sorted({g.event_id for g in candidates}))
    if not candidates:
        return GuestMatch(None, NOT_FOUND)
    if len(candidates) > 1:
        return GuestMatch(None, AMBIGUOUS, len(candidates), event_ids)
    return GuestMatch(candidates[0], MATCH_PHONE, 1, event_ids)


def already_processed(db: Session, provider_message_id: str) -> bool:
    """האם ההודעה הנכנסת הזו כבר נקלטה (webhook שחוזר מ-Meta)."""
    return db.scalar(
        select(models.Message.id).where(
            models.Message.provider_message_id == provider_message_id
        )
    ) is not None


def _flush_inbound(db: Session) -> None:
    """כותב את ההודעה הנכנסת (ואת עדכון ה-RSVP) עכשיו, לפני ``audit.record``.

    אותה הודעה שמגיעה פעמיים *במקביל* נעצרת באינדקס הייחודי על מזהה Meta.
    בלי flush כאן, הכתיבה הייתה קורית בתוך ה-SAVEPOINT של ``audit.record``
    (``begin_nested`` מבצע flush), שבולע כל שגיאה — והטרנזקציה הייתה נשארת
    "שבורה" עד ה-commit. כך ה-``IntegrityError`` עולה לקורא ומזוהה ככפילות.
    """
    db.flush()


def _log(outcome: str, **ids) -> None:
    """שורת לוג בלי מידע אישי — רק מזהים פנימיים ותוצאה."""
    parts = " ".join(f"{k}={v}" for k, v in ids.items() if v is not None)
    print(f"[veya:whatsapp] inbound {outcome} {parts}".rstrip(), flush=True)


def record_rsvp_reply(
    db: Session,
    *,
    provider_message_id: str,
    from_phone: Optional[str],
    context_id: Optional[str],
    decision: str,
    provider: str = "meta",
) -> str:
    """מטפל בתשובת אישור/ביטול הגעה שהגיעה ב-WhatsApp. לא עושה commit.

    מחזיר את התוצאה (``APPLIED``/``DUPLICATE``/``WINDOW_CLOSED`` או סיבת
    אי-השיוך). ``decision`` — ``confirmed`` או ``declined``.
    """
    if already_processed(db, provider_message_id):
        _log(DUPLICATE)
        return DUPLICATE

    match = match_guest(db, from_phone, context_id)
    if match.guest is None:
        reason_text = _UNMATCHED_LABEL.get(match.reason, match.reason)
        # עמימות בתוך אירוע אחד (טלפון משפחתי): נשמרת ביומן ההודעות של
        # האירוע כ"דורש טיפול" — כך יש גם מניעת כפילויות לפי מזהה Meta.
        if len(set(match.candidate_event_ids)) == 1:
            event = db.get(models.Event, match.candidate_event_ids[0])
            db.add(models.Message(
                event_id=match.candidate_event_ids[0],
                guest_id=None,
                direction="inbound",
                kind="inbound",
                body=f"תשובה ב-WhatsApp שלא שויכה למוזמן ({reason_text}) — אישור ההגעה לא עודכן",
                status=message_status.NEEDS_ATTENTION,
                provider=provider,
                channel="whatsapp",
                provider_message_id=provider_message_id,
                cycle_number=event_cycle.of(event) if event else 1,
            ))
            _flush_inbound(db)
        audit.record(
            db, "whatsapp_reply_unmatched",
            event_id=match.candidate_event_ids[0] if len(set(match.candidate_event_ids)) == 1 else None,
            detail=f"תשובת WhatsApp לא שויכה: {reason_text}",
        )
        _log(match.reason, candidates=match.candidates or None)
        return match.reason

    guest = match.guest
    event = db.get(models.Event, guest.event_id)
    if not guest_journey.rsvp_is_open(event):
        what = "אישור הגעה" if decision == "confirmed" else "ביטול הגעה"
        db.add(models.Message(
            event_id=guest.event_id,
            guest_id=guest.id,
            direction="inbound",
            kind="inbound",
            body=f"{what} ב-WhatsApp לפני שנפתחו אישורי ההגעה — לא עודכן",
            status=message_status.NEEDS_ATTENTION,
            provider=provider,
            channel="whatsapp",
            provider_message_id=provider_message_id,
            cycle_number=event_cycle.of(event),
        ))
        _log(WINDOW_CLOSED, event=guest.event_id, guest=guest.id, match=match.reason)
        return WINDOW_CLOSED

    # אותה פונקציה בדיוק כמו הקישור האישי והמוקד (``rsvp_response``).
    label = rsvp_response.apply_response(guest, decision)
    db.add(models.Message(
        event_id=guest.event_id,
        guest_id=guest.id,
        direction="inbound",
        kind="reply",
        body=label,
        status=message_status.RECEIVED,
        provider=provider,
        channel="whatsapp",
        provider_message_id=provider_message_id,
        cycle_number=event_cycle.of(event),
    ))
    _flush_inbound(db)
    audit.record(
        db, "confirm_submit",
        event_id=guest.event_id,
        detail=f"{guest.full_name}: {label}",
    )
    _log(APPLIED, event=guest.event_id, guest=guest.id, match=match.reason)
    return APPLIED


# תוכן הודעה חופשית נשמר במסד (כדי שמישהו יקרא ויטפל) — אף פעם לא בלוג.
MAX_FREE_TEXT = 1000

_TYPE_LABEL = {
    "image": "תמונה", "audio": "הקלטה", "video": "סרטון", "document": "מסמך",
    "sticker": "מדבקה", "location": "מיקום", "contacts": "איש קשר", "reaction": "תגובה (אימוג'י)",
}


def record_free_message(
    db: Session,
    *,
    provider_message_id: str,
    from_phone: Optional[str],
    context_id: Optional[str],
    message_type: str,
    text_body: Optional[str],
    provider: str = "meta",
) -> str:
    """הודעה חופשית מאורח (טקסט, תמונה, הקלטה…) — נשמרת ביומן ההודעות כ"דורש
    טיפול". **לעולם לא משנה RSVP** — גם "נגיע 3" לא מתפרש אוטומטית. לא עושה commit.

    שיוך: אותם כללים בדיוק כמו תשובת RSVP (``match_guest``). מוזמן מזוהה — על
    השורה שלו; עמימות בתוך אירוע אחד — על האירוע, בלי מוזמן; אחרת — רק שורת
    יומן אבטחה בלי התוכן.
    """
    if already_processed(db, provider_message_id):
        _log(DUPLICATE)
        return DUPLICATE

    if text_body and text_body.strip():
        body = text_body.strip()[:MAX_FREE_TEXT]
    else:
        body = f"[{_TYPE_LABEL.get(message_type, 'הודעה')}]"

    match = match_guest(db, from_phone, context_id)
    event_ids = set(match.candidate_event_ids)
    if match.guest is not None or len(event_ids) == 1:
        event_id = match.guest.event_id if match.guest is not None else next(iter(event_ids))
        event = db.get(models.Event, event_id)
        db.add(models.Message(
            event_id=event_id,
            guest_id=match.guest.id if match.guest is not None else None,
            direction="inbound",
            kind="inbound",
            body=body,
            status=message_status.NEEDS_ATTENTION,
            provider=provider,
            channel="whatsapp",
            provider_message_id=provider_message_id,
            cycle_number=event_cycle.of(event) if event else 1,
        ))
        _flush_inbound(db)
        _log("free_message", event=event_id,
             guest=match.guest.id if match.guest is not None else None, match=match.reason)
        return "recorded"

    reason_text = _UNMATCHED_LABEL.get(match.reason, match.reason)
    audit.record(
        db, "whatsapp_message_unmatched",
        detail=f"הודעת WhatsApp לא שויכה: {reason_text}",
    )
    _log("free_message_unmatched", reason=match.reason, candidates=match.candidates or None)
    return match.reason

