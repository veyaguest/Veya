"""לוגיקה משותפת לשליחת הזמנות ידנית — סיווג טלפונים, גזירת סטטוס וספירה מקדימה.

מרוכז כאן כדי שגם ה-endpoint של התצוגה-המקדימה (preview), גם השליחה בפועל
(activate) וגם רשימת המוזמנים יגזרו את אותם הנתונים בדיוק — בלי כפילות לוגיקה.

עיקרון: הכול דטרמיניסטי (בלי LLM). "נמסרה"/"נקראה" יגיעו בעתיד מ-webhook של
Meta במצב חי; במצב bדיקה (mock) אין נתון כזה, לכן הם לא נגזרים כאן.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.validators import normalize_israeli_phone

# ערכי הסטטוס הנגזר לכל מוזמן (מקור אמת יחיד, נחשף גם ל-frontend).
STATUS_NOT_SENT = "not_sent"      # לא נשלחה הזמנה
STATUS_SENT = "sent"             # נשלחה הזמנה (טרם התקבלה תשובה)
STATUS_DELIVERED = "delivered"    # נמסרה (עתידי — webhook חי)
STATUS_READ = "read"             # נקראה (עתידי — webhook חי)
STATUS_CONFIRMED = "confirmed"    # אישר/ה הגעה
STATUS_DECLINED = "declined"      # סירב/ה להגיע
STATUS_AWAITING = "awaiting"      # ממתין/ה למענה (נשלחה, עוד לא ענה)


def classify_phone(raw: str | None) -> str:
    """מסווג מספר טלפון לאחת משלוש קטגוריות: valid / missing / invalid.

    - ``missing``  — אין מספר כלל.
    - ``invalid``  — יש טקסט אך הוא לא מספר טלפון ישראלי תקין.
    - ``valid``    — מספר תקין שאפשר לשלוח אליו.
    """
    if not (raw or "").strip():
        return "missing"
    try:
        normalize_israeli_phone(raw)
    except ValueError:
        return "invalid"
    return "valid"


def invited_guest_ids(db: Session, event_id: int) -> set[int]:
    """מזהי המוזמנים שכבר נשלחה אליהם הזמנה (הודעת invitation יוצאת שנשלחה)."""
    rows = db.scalars(
        select(models.Message.guest_id)
        .where(models.Message.event_id == event_id)
        .where(models.Message.direction == "outbound")
        .where(models.Message.kind == "invitation")
        .where(models.Message.status == "sent")
        .where(models.Message.guest_id.is_not(None))
    ).all()
    return {gid for gid in rows if gid is not None}


def derive_invite_status(rsvp_status: str, has_invite: bool) -> str:
    """גוזר את סטטוס המוזמן לתצוגה מתוך הנתונים הקיימים (בלי עמודה חדשה).

    התשובה של המוזמן גוברת על מצב השליחה: מי שאישר/סירב מוצג לפי תשובתו גם אם
    ההזמנה נשלחה. אחרת — לפי אם נשלחה הזמנה (ממתין למענה) או לא (לא נשלחה).
    """
    if rsvp_status == "confirmed":
        return STATUS_CONFIRMED
    if rsvp_status == "declined":
        return STATUS_DECLINED
    if not has_invite:
        return STATUS_NOT_SENT
    return STATUS_AWAITING


class SendPreview:
    """תמונת מצב מקדימה לפני שליחה — הבסיס לדיאלוג האישור ולמניעת כפילות."""

    def __init__(
        self,
        total_guests: int,
        can_receive: int,
        not_yet_sent: int,
        already_sent: int,
        missing_phone: int,
        invalid_phone: int,
        already_activated: bool,
    ) -> None:
        self.total_guests = total_guests
        self.can_receive = can_receive
        self.not_yet_sent = not_yet_sent
        self.already_sent = already_sent
        self.missing_phone = missing_phone
        self.invalid_phone = invalid_phone
        self.already_activated = already_activated


def build_send_preview(db: Session, event: models.Event) -> SendPreview:
    """סופר כמה יקבלו הזמנה, כמה לא (וסיבה), וכמה כבר קיבלו — לדיאלוג האישור."""
    guests = db.scalars(
        select(models.Guest).where(models.Guest.event_id == event.id)
    ).all()
    invited = invited_guest_ids(db, event.id)

    can_receive = not_yet_sent = already_sent = 0
    missing_phone = invalid_phone = 0
    for g in guests:
        kind = classify_phone(g.phone)
        if kind == "missing":
            missing_phone += 1
        elif kind == "invalid":
            invalid_phone += 1
        else:  # valid
            can_receive += 1
            if g.id in invited:
                already_sent += 1
            else:
                not_yet_sent += 1

    return SendPreview(
        total_guests=len(guests),
        can_receive=can_receive,
        not_yet_sent=not_yet_sent,
        already_sent=already_sent,
        missing_phone=missing_phone,
        invalid_phone=invalid_phone,
        already_activated=bool(event.rsvp_track_active),
    )
