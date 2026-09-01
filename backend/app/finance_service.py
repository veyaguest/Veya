"""שכבת הנתונים של כספי האירוע — קריאה מה-DB והרכבת התמונה המלאה.

חלוקת התפקידים בין שלושת הקבצים, ובכוונה בלי חפיפה:

    finance_categories.py   *מה* אפשר להוסיף (קטלוג הצעות, לפי סוג אירוע)
    finance.py              *איך* מחשבים (אגורות שלמות, כללי התחייבות)
    finance_service.py      *מה קורה בפועל* (DB, איחוד מקורות המתנות, שערים)

``finance.py`` אינו נוגע ב-DB, ולכן ניתן לבדוק אותו בלי מסד נתונים —
וזה בדיוק החלק שאסור שיישבר.

## איחוד שני מקורות המתנות

לאירוע יש שתי דרכים לקבל מתנה, ולכל אחת מחזור חיים משלה:

    Gift           עסקת סליקה. נכתבת רק מהמסלול הציבורי, סטטוס מהספק.
    GiftEnvelope   מעטפה שהזוג ספר. נכתבת בידי הבעלים, ניתנת לעריכה.

המסך מציג אותן יחד, אבל **הן לא מתמזגות לטבלה אחת** — ראו ההסבר ב-
``models.GiftEnvelope``. האיחוד קורה כאן, בקריאה, ולכן יש לו מקום אחד
ואי אפשר לשכוח אותו במסך השלישי.

**מתנה באשראי נספרת רק כש-``status == paid``** — בדיוק כמו ב-
``routers/gifts.py``. עסקה שנכשלה, בוטלה, הוחזרה או עדיין ממתינה אינה
"מתנה שהתקבלה", והכלל הזה נאכף בשרת ולא בסינון של ה-Frontend.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import (
    finance,
    gift_eligibility,
    gift_status,
    guest_journey,
    models,
    payout_service,
)

# ── סטטוס מתנה לכל מוזמן ────────────────────────────────────────────────
# ההבחנה הקריטית של המסך הזה: **"עדיין לא נספרה" אינו "לא נתן".** מוזמן
# בלי שורת מתנה הוא מוזמן שהמעטפה שלו עוד לא הגיעה לערימה — לא מוזמן
# שהחליט לא להעניק. הצגה שמערבבת בין השניים מפילה אשמה על אנשים בלי
# שום בסיס, וזה הקו שלא חוצים.
COUNTED = "counted"        # נספרה מעטפה
CREDIT = "credit"          # התקבלה מתנה באשראי
NOT_COUNTED = "not_counted"  # עדיין לא נספרה


@dataclass(frozen=True)
class GiftEntry:
    """שורת מתנה אחת בתצוגה המאוחדת."""

    source: str               # "envelope" / "credit"
    id: int
    amount_agorot: Optional[int]
    guest_id: Optional[int]
    guest_name: str
    envelope_number: Optional[int]
    note: Optional[str]
    created_at: datetime
    #: שמות המוזמנים הנוספים במתנה משותפת (לתצוגה בלבד — הסכום לא מפוצל).
    shared_names: list[str]
    #: לשורת אשראי בלבד: הסטטוס מהספק.
    status: Optional[str] = None


# ════════════════════════════════════════════════════════════════════════
#  שער הזמן — מתי ספירת המתנות נפתחת
# ════════════════════════════════════════════════════════════════════════

def counting_open(event: models.Event, *, today: Optional[date] = None) -> bool:
    """האם ספירת המתנות פתוחה — **מיום האירוע ואילך** (החלטת בעלים).

    ``days_until_event`` מחזיר 0 ביום האירוע עצמו ומספר שלילי אחריו, ולכן
    התנאי הוא ``<= 0``. שעון ישראל, לא UTC: ביום האירוע ההפרש בין השניים
    הוא בדיוק ההבדל בין "המסך נפתח" ל"המסך עדיין נעול".

    **אירוע בלי תאריך פתוח.** אין תאריך ⇒ אין דרך לדעת שהוא עוד לא קרה,
    ונעילה על סמך ניחוש היא הדבר הגרוע יותר: היא חוסמת זוג מלספור כסף
    שכבר בידיו. השער הזה מכוון לפני-מדי-מוקדם, לא לאבטחה — אין כאן שום
    מידע רגיש שנחשף מוקדם, רק מסך שאין בו טעם לפני האירוע.
    """
    days = guest_journey.days_until_event(event, today=today)
    if days is None:
        return True
    return days <= 0


# ════════════════════════════════════════════════════════════════════════
#  הוצאות
# ════════════════════════════════════════════════════════════════════════

def expenses_for(db: Session, event_id: int) -> list[models.EventExpense]:
    return list(
        db.scalars(
            select(models.EventExpense)
            .where(models.EventExpense.event_id == event_id)
            # id כשובר-שוויון: שתי שורות שנוצרו יחד עם אותו sort_order
            # עדיין חייבות להופיע בסדר יציב בין רענון לרענון.
            .order_by(models.EventExpense.sort_order, models.EventExpense.id)
        ).all()
    )


def next_sort_order(db: Session, event_id: int) -> int:
    current = db.scalar(
        select(func.max(models.EventExpense.sort_order)).where(
            models.EventExpense.event_id == event_id
        )
    )
    return (current or 0) + 1


# ════════════════════════════════════════════════════════════════════════
#  מעטפות
# ════════════════════════════════════════════════════════════════════════

def next_envelope_number(db: Session, event_id: int) -> int:
    """המספר הרץ הבא. ממשיך מהגבוה ביותר ולא סופר שורות.

    ההבדל חשוב: מעטפה שנמחקה לא "משחררת" את המספר שלה. אילו היינו סופרים
    שורות, מחיקה של מעטפה #40 הייתה גורמת למעטפה הבאה לקבל שוב 40 —
    ובאמצע ספירה של 400 מעטפות זה בדיוק הרגע שבו הזוג מאבד את הספירה.
    """
    current = db.scalar(
        select(func.max(models.GiftEnvelope.envelope_number)).where(
            models.GiftEnvelope.event_id == event_id
        )
    )
    return (current or 0) + 1


def envelopes_for(db: Session, event_id: int) -> list[models.GiftEnvelope]:
    return list(
        db.scalars(
            select(models.GiftEnvelope)
            .where(models.GiftEnvelope.event_id == event_id)
            .order_by(models.GiftEnvelope.envelope_number.desc())
        ).all()
    )


# ════════════════════════════════════════════════════════════════════════
#  התמונה המאוחדת
# ════════════════════════════════════════════════════════════════════════

def credit_amounts_visible(db: Session, event: models.Event) -> bool:
    """האם מותר להחזיר סכומי מתנות באשראי.

    **אותו תנאי בדיוק** כמו ב-``routers/gifts.py``, ומאותה פונקציה
    מרכזית — לא העתק שלו. הסכומים נפתחים רק כשהשירות זכאי **וגם** חשבון
    קבלת המתנות עבר את שתי הבדיקות. לפני כן הם לא נכתבים לתשובה כלל.

    זה **לא** חוסם את המסך: מעטפות הן כסף פיזי שכבר בידי הזוג, ואין להן
    שום קשר לספק סליקה. אירוע בלי שירות המתנות באשראי מקבל מסך כספים
    מלא — פשוט בלי חלק האשראי.
    """
    if not gift_eligibility.is_eligible(event):
        return False
    return gift_eligibility.is_active(
        event,
        account_verified=payout_service.is_fully_verified(
            payout_service.get(db, event.id)
        ),
    )


def _guest_names(db: Session, event_id: int) -> dict[int, str]:
    rows = db.execute(
        select(models.Guest.id, models.Guest.full_name).where(
            models.Guest.event_id == event_id
        )
    ).all()
    return {row[0]: row[1] for row in rows}


def gift_entries(
    db: Session, event: models.Event, *, credit_visible: bool
) -> list[GiftEntry]:
    """כל המתנות של האירוע — מעטפות ואשראי — בשורה אחת מסודרת.

    מסודר מהחדש לישן: בערב שאחרי האירוע הזוג רוצה לראות את מה שהרגע
    הזין, לא את המעטפה הראשונה מלפני שעתיים.
    """
    names = _guest_names(db, event.id)
    entries: list[GiftEntry] = []

    for env in envelopes_for(db, event.id):
        shared = [names.get(g, "") for g in (env.shared_guest_ids or []) if names.get(g)]
        entries.append(
            GiftEntry(
                source="envelope",
                id=env.id,
                amount_agorot=env.amount_agorot,
                guest_id=env.guest_id,
                guest_name=names.get(env.guest_id or -1, ""),
                envelope_number=env.envelope_number,
                note=env.note,
                created_at=env.created_at,
                shared_names=shared,
            )
        )

    if gift_eligibility.is_eligible(event):
        credit_rows = db.scalars(
            select(models.Gift)
            .where(models.Gift.event_id == event.id)
            .where(models.Gift.status == gift_status.PAID)
            .order_by(models.Gift.created_at.desc(), models.Gift.id.desc())
        ).all()
        for row in credit_rows:
            entries.append(
                GiftEntry(
                    source="credit",
                    id=row.id,
                    # לא מאופס ולא מוסתר בכוכביות — פשוט לא נכתב לתשובה,
                    # בדיוק כמו ב-``routers/gifts.py``.
                    amount_agorot=row.gift_amount_agorot if credit_visible else None,
                    guest_id=row.guest_id,
                    guest_name=row.sender_name or names.get(row.guest_id, "מוזמן"),
                    envelope_number=None,
                    note=row.message,
                    created_at=row.created_at,
                    shared_names=[],
                    status=row.status,
                )
            )

    entries.sort(key=lambda e: e.created_at, reverse=True)
    return entries


@dataclass(frozen=True)
class GiftIncome:
    """צד ההכנסות."""

    envelopes_agorot: int
    envelopes_count: int
    #: ``None`` כשסכומי האשראי חסומים — ולא 0. אפס היה אומר "לא התקבלו
    #: מתנות באשראי", וזו טענה אחרת לגמרי מ"הסכומים עוד לא מוצגים".
    credit_agorot: Optional[int]
    credit_count: int
    #: סך ההכנסות. ``None`` כשחלק מהתמונה חסום — סכום חלקי שמוצג
    #: כ"סה״כ" הוא מספר שקרי, ועדיף לא להציג אותו מאשר להטעות.
    total_agorot: Optional[int]
    unidentified_count: int
    unidentified_agorot: int


def gift_income(db: Session, event: models.Event, *, credit_visible: bool) -> GiftIncome:
    envelopes = envelopes_for(db, event.id)
    env_total = sum(e.amount_agorot for e in envelopes)
    unidentified = [e for e in envelopes if e.guest_id is None]

    credit_total: Optional[int] = None
    credit_count = 0
    if gift_eligibility.is_eligible(event):
        paid = list(
            db.scalars(
                select(models.Gift)
                .where(models.Gift.event_id == event.id)
                .where(models.Gift.status == gift_status.PAID)
            ).all()
        )
        credit_count = len(paid)
        if credit_visible:
            credit_total = sum(r.gift_amount_agorot for r in paid)

    total: Optional[int] = env_total
    if credit_count and credit_total is None:
        total = None
    elif credit_total is not None:
        total = env_total + credit_total

    return GiftIncome(
        envelopes_agorot=env_total,
        envelopes_count=len(envelopes),
        credit_agorot=credit_total,
        credit_count=credit_count,
        total_agorot=total,
        unidentified_count=len(unidentified),
        unidentified_agorot=sum(e.amount_agorot for e in unidentified),
    )


@dataclass(frozen=True)
class GuestGiftRow:
    """שורה אחת ב"מי כבר נספר" — מוזמן והמתנות שלו."""

    guest_id: int
    full_name: str
    rsvp_status: str
    status: str                 # counted / credit / not_counted
    total_agorot: Optional[int]
    gift_count: int
    envelope_numbers: list[int]


def guest_gift_rows(
    db: Session, event: models.Event, *, credit_visible: bool
) -> list[GuestGiftRow]:
    """מצב המתנה לכל מוזמן — כולל מי שעדיין לא נספר.

    **מוזמן ללא מתנה מופיע ברשימה** עם ``not_counted``, ולא נעדר ממנה.
    זו כל הנקודה: הזוג צריך לראות את מי שנשאר לספור, ולא לנחש מי חסר.

    כמה מתנות לאותו מוזמן מצטברות (``gift_count``, ``total_agorot``) ולא
    דורסות זו את זו — שתי מעטפות מדוד לוי הן ₪1,000, לא ₪500.
    """
    guests = list(
        db.scalars(
            select(models.Guest)
            .where(models.Guest.event_id == event.id)
            .order_by(models.Guest.full_name)
        ).all()
    )

    totals: dict[int, int] = {}
    counts: dict[int, int] = {}
    numbers: dict[int, list[int]] = {}
    has_credit: set[int] = set()
    credit_blocked: set[int] = set()

    for env in envelopes_for(db, event.id):
        # מתנה משותפת נזקפת לכל המוזמנים המשויכים **בסכום המלא**, ולא
        # מפוצלת. הסכום הזה הוא לתצוגה ברמת המוזמן; הסיכום הכללי נספר
        # מהמעטפות עצמן (``gift_income``) ולכן אינו נספר פעמיים.
        linked = [g for g in [env.guest_id, *(env.shared_guest_ids or [])] if g]
        for gid in linked:
            totals[gid] = totals.get(gid, 0) + env.amount_agorot
            counts[gid] = counts.get(gid, 0) + 1
            numbers.setdefault(gid, []).append(env.envelope_number)

    if gift_eligibility.is_eligible(event):
        for row in db.scalars(
            select(models.Gift)
            .where(models.Gift.event_id == event.id)
            .where(models.Gift.status == gift_status.PAID)
        ).all():
            has_credit.add(row.guest_id)
            counts[row.guest_id] = counts.get(row.guest_id, 0) + 1
            if credit_visible:
                totals[row.guest_id] = totals.get(row.guest_id, 0) + row.gift_amount_agorot
            else:
                credit_blocked.add(row.guest_id)

    rows: list[GuestGiftRow] = []
    for guest in guests:
        count = counts.get(guest.id, 0)
        if count == 0:
            status = NOT_COUNTED
        elif guest.id in has_credit and guest.id not in numbers:
            status = CREDIT
        else:
            status = COUNTED
        # סכום שחסר בו רכיב אשראי חסום אינו מוצג בכלל — ראו GiftIncome.
        total = None if (guest.id in credit_blocked or count == 0) else totals.get(guest.id)
        rows.append(
            GuestGiftRow(
                guest_id=guest.id,
                full_name=guest.full_name,
                rsvp_status=guest.rsvp_status,
                status=status,
                total_agorot=total,
                gift_count=count,
                envelope_numbers=sorted(numbers.get(guest.id, [])),
            )
        )
    return rows


# ════════════════════════════════════════════════════════════════════════
#  השורה התחתונה
# ════════════════════════════════════════════════════════════════════════

def bottom_line(cost: finance.CostBreakdown, income: GiftIncome) -> Optional[int]:
    """הכנסות פחות הוצאות. ``None`` כשצד ההכנסות חסום חלקית.

    מספר שמוצג כ"התוצאה הכספית של האירוע" ומחושב מנתון חלקי הוא הטעיה,
    לא קירוב. עדיף לא להציג אותו.
    """
    if income.total_agorot is None:
        return None
    return income.total_agorot - cost.total_agorot
