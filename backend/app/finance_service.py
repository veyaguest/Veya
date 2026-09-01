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
    """**שורה מלאה אחת לכל מוזמן** — הגעה ומתנה יחד.

    זו היחידה שממנה נבנה הדוח הסופי, ולכן היא מחזיקה את שני צירי המידע
    בבת אחת: מה המוזמן ענה, כמה אנשים הגיעו ממנו בפועל, ומה התקבל ממנו —
    בפירוט מעטפה מול אשראי.

    ## RSVP ומתנה הם שני צירים נפרדים

    ``rsvp_status`` ו-``status`` **אינם נגזרים זה מזה ולא משפיעים זה על
    זה**. מוזמן שביטל הגעה יכול בהחלט לשלוח מתנה, ומוזמן שהגיע יכול לא
    לתת. כל לוגיקה שתקשור ביניהם תייצר דוח שקרי — ולכן אין כאן שום
    מקום שבו אחד נגזר מהשני.
    """

    guest_id: int
    full_name: str
    phone: str
    #: מה המוזמן ענה — pending / confirmed / declined / maybe.
    rsvp_status: str
    #: כמה אנשים הוזמנו ברשומה הזו.
    party_size: int
    #: כמה הגיעו בפועל (0 למי שלא אישר) — ``Guest.effective_seats``.
    attended_count: int

    #: counted / credit / not_counted — מצב **המתנה**, לא ההגעה.
    status: str
    total_agorot: Optional[int]
    #: פירוט לפי מקור, כדי שהדוח יוכל להציג עמודה לכל אחד.
    envelope_agorot: int
    credit_agorot: Optional[int]
    envelope_count: int
    credit_count: int
    gift_count: int
    envelope_numbers: list[int]
    #: הערות המוזמן (ההערה הפנימית של הבעלים + מה שהמוזמן כתב בדף האישור).
    note: str


def guest_gift_rows(
    db: Session, event: models.Event, *, credit_visible: bool
) -> list[GuestGiftRow]:
    """**שורה מלאה אחת לכל מוזמן** — הגעה ומתנה, בלי לחבר מסכים.

    זו הפונקציה שממנה נבנים גם המסך "לפי מוזמן" וגם הדוח הסופי, ולכן
    היא מחזירה את שני צירי המידע יחד.

    ## שלושה כללים שהיא אוכפת

    1. **כל מוזמן מופיע**, גם מי שאין לו מתנה וגם מי שלא הגיע. מוזמן
       שנעדר מהרשימה הוא מוזמן שהזוג לא יידע שנשאר לספור אותו.
    2. **``rsvp_status`` ו-``status`` אינם נגזרים זה מזה.** מוזמן שביטל
       הגעה ונתן ₪1,000 יופיע כ"לא מגיע" **וגם** כ"נספרה". אין כאן שום
       שורה שבה סטטוס אחד משפיע על השני.
    3. **"עדיין לא נספרה" אינו "לא נתן".** מוזמן בלי מתנה מקבל
       ``total_agorot=None`` ולא ``0``: אפס הוא טענה עובדתית ("נספרה
       מעטפה ריקה") שהמערכת לא יכולה להצדיק. מעטפה שנספרה בסכום 0 —
       מצב אמיתי וקביל — מקבלת ``status=counted`` עם ``total=0``, וכך
       שני המצבים נבדלים זה מזה בנתונים עצמם, לא רק בתצוגה.

    כמה מתנות לאותו מוזמן **מצטברות ולא דורסות** — שתי מעטפות מדוד לוי
    הן ₪1,000, לא ₪500.
    """
    guests = list(
        db.scalars(
            select(models.Guest)
            .where(models.Guest.event_id == event.id)
            .order_by(models.Guest.full_name)
        ).all()
    )

    env_totals: dict[int, int] = {}
    env_counts: dict[int, int] = {}
    numbers: dict[int, list[int]] = {}
    credit_totals: dict[int, int] = {}
    credit_counts: dict[int, int] = {}

    for env in envelopes_for(db, event.id):
        # מתנה משותפת נזקפת לכל המוזמנים המשויכים **בסכום המלא**, ולא
        # מפוצלת. הסכום הזה הוא לתצוגה ברמת המוזמן; הסיכום הכללי נספר
        # מהמעטפות עצמן (``gift_income``) ולכן אינו נספר פעמיים.
        linked = [g for g in [env.guest_id, *(env.shared_guest_ids or [])] if g]
        for gid in linked:
            env_totals[gid] = env_totals.get(gid, 0) + env.amount_agorot
            env_counts[gid] = env_counts.get(gid, 0) + 1
            numbers.setdefault(gid, []).append(env.envelope_number)

    if gift_eligibility.is_eligible(event):
        for row in db.scalars(
            select(models.Gift)
            .where(models.Gift.event_id == event.id)
            .where(models.Gift.status == gift_status.PAID)
        ).all():
            credit_counts[row.guest_id] = credit_counts.get(row.guest_id, 0) + 1
            credit_totals[row.guest_id] = (
                credit_totals.get(row.guest_id, 0) + row.gift_amount_agorot
            )

    rows: list[GuestGiftRow] = []
    for guest in guests:
        env_n = env_counts.get(guest.id, 0)
        cr_n = credit_counts.get(guest.id, 0)
        count = env_n + cr_n

        if count == 0:
            status = NOT_COUNTED
        elif env_n == 0:
            status = CREDIT
        else:
            status = COUNTED

        env_sum = env_totals.get(guest.id, 0)
        # סכום האשראי חסום ⇒ ``None``, וגם הסך הכולל ``None``. סכום חלקי
        # שמוצג כ"סה״כ" הוא מספר שקרי, לא קירוב.
        cr_sum: Optional[int] = credit_totals.get(guest.id, 0) if credit_visible else None
        if cr_n and not credit_visible:
            total: Optional[int] = None
        elif count == 0:
            total = None
        else:
            total = env_sum + (cr_sum or 0)

        # ההערה של המוזמן: הפנימית של הבעלים ומה שהמוזמן כתב בדף האישור.
        # מאוחדות לשדה אחד כי בדוח יש עמודת "הערות" אחת.
        note = " · ".join(
            part.strip()
            for part in (guest.notes_raw, guest.guest_note)
            if part and part.strip()
        )

        rows.append(
            GuestGiftRow(
                guest_id=guest.id,
                full_name=guest.full_name,
                phone=guest.phone or "",
                rsvp_status=guest.rsvp_status,
                party_size=guest.party_size,
                # ``effective_seats`` ולא ספירה מקומית — אותו מקור בדיוק
                # שמנוע ההושבה משתמש בו.
                attended_count=guest.effective_seats,
                status=status,
                total_agorot=total,
                envelope_agorot=env_sum,
                credit_agorot=cr_sum,
                envelope_count=env_n,
                credit_count=cr_n,
                gift_count=count,
                envelope_numbers=sorted(numbers.get(guest.id, [])),
                note=note,
            )
        )
    return rows


@dataclass(frozen=True)
class GiftBreakdown:
    """הפילוח שמראה את **הפער בין הגעה למתנות**.

    זו התובנה שדוח כספי רגיל מפספס: מי שלא הגיע עדיין יכול היה לתת, ומי
    שהגיע לא בהכרח נתן. שני המספרים האלה זה לצד זה הם התמונה האמיתית.

    הסכומים כאן נספרים **מהמעטפות ומהעסקאות**, לא מסכומי המוזמנים — כדי
    שמתנה משותפת (שמופיעה אצל שני מוזמנים) לא תיספר פעמיים.
    """

    from_attendees_agorot: int
    from_non_attendees_agorot: int
    #: מעטפות שאין להן שיוך, ולכן אי אפשר לשייך אותן לאף אחד מהצדדים.
    unattributed_agorot: int
    guests_counted: int
    guests_not_counted: int


def gift_breakdown(
    db: Session, event: models.Event, *, credit_visible: bool
) -> GiftBreakdown:
    """פילוח המתנות לפי הגעה בפועל.

    "הגיע" נקבע לפי ``Guest.effective_seats > 0`` — כלומר מי שאישר הגעה.
    מוזמן שביטל, התלבט או לא ענה נספר בצד השני, **בלי שזה אומר עליו
    שום דבר**: זו חלוקה תיאורית לדוח, לא שיפוט.
    """
    attended: dict[int, bool] = {
        g.id: g.effective_seats > 0
        for g in db.scalars(
            select(models.Guest).where(models.Guest.event_id == event.id)
        ).all()
    }

    from_att = from_non = unattributed = 0

    for env in envelopes_for(db, event.id):
        if env.guest_id is None:
            unattributed += env.amount_agorot
        elif attended.get(env.guest_id):
            from_att += env.amount_agorot
        else:
            from_non += env.amount_agorot

    if credit_visible and gift_eligibility.is_eligible(event):
        for row in db.scalars(
            select(models.Gift)
            .where(models.Gift.event_id == event.id)
            .where(models.Gift.status == gift_status.PAID)
        ).all():
            if attended.get(row.guest_id):
                from_att += row.gift_amount_agorot
            else:
                from_non += row.gift_amount_agorot

    rows = guest_gift_rows(db, event, credit_visible=credit_visible)
    return GiftBreakdown(
        from_attendees_agorot=from_att,
        from_non_attendees_agorot=from_non,
        unattributed_agorot=unattributed,
        guests_counted=sum(1 for r in rows if r.status != NOT_COUNTED),
        guests_not_counted=sum(1 for r in rows if r.status == NOT_COUNTED),
    )


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
