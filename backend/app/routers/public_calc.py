"""מחשבונים ציבוריים — **אותו מנוע חישוב של המוצר, בלי לוגיקה מקבילה.**

## למה זה קיים בכלל

באתר השיווקי יש מחשבונים פתוחים (``/calculators/...``). הפיתוי הטבעי הוא
לממש אותם ב-JavaScript בדפדפן, וזו בדיוק הטעות שאסור לעשות כאן: ברגע
שנוסחת ההתחייבות חיה גם ב-``finance.py`` וגם בקובץ JS, נוצרים **שני
מקורות אמת לאותו מספר** — והם יסטו זה מזה בתיקון הראשון שייעשה רק בצד
אחד. זוג שיראה באתר מספר אחד ובמערכת מספר אחר יפסיק להאמין לשניהם.

לכן: הדפדפן **מצייר**, השרת **מחשב**. הנתיבים כאן הם מעטפת דקה בלבד סביב
``app/finance.py`` ו-``app/rsvp_timeline.py``.

## למה בונים כאן אובייקטים "מדומים" ולא כותבים חישוב חדש

``finance._line_total`` ו-``rsvp_timeline.compute_schedule`` מקבלים
אובייקטי ORM. שניהם **פונקציות טהורות** שרק *קוראות* שדות — אין בהם
גישה ל-DB ואין תופעות לוואי. לכן אפשר להזין אותם באובייקטים זמניים
שנוצרים בזיכרון ולא נכנסים ל-Session, ולקבל בדיוק את אותה תשובה שהזוג
יקבל בתוך המערכת. **האובייקטים האלה לעולם לא נשמרים** — אין כאן
``db.add`` ואין ``commit``, וממילא אין ל-router הזה תלות במסד נתונים.

## מה שבמפורש לא נמצא כאן

אין אימות, אין ``event_id``, ואין נגיעה בנתוני משתמש. אלה נתיבים
אנונימיים לגמרי שמקבלים מספרים ומחזירים מספרים — ולכן גם מוגבלים בקצב
(``calc_limiter``) כדי שלא ישמשו כמנוע חישוב חינמי לצד שלישי.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import finance, models, rsvp_timeline
from app.finance_categories import FIXED, PER_ATTENDEE
from app.ratelimit import RateLimiter, client_ip

router = APIRouter(prefix="/public/calculators", tags=["public-calculators"])

# מגביל קצב לנתיבים האנונימיים: 60 חישובים לדקה ל-IP. נדיב מספיק
# למשתמש שמשחק עם המחוונים, צר מספיק כדי שלא יהפוך ל-API ציבורי.
calc_limiter = RateLimiter(
    max_hits=60,
    window=60.0,
    message="בוצעו יותר מדי חישובים מהכתובת הזו. אפשר לנסות שוב בעוד דקה.",
)


def _guard(request: Request) -> None:
    ip = client_ip(request)
    calc_limiter.check(ip)
    calc_limiter.record_fail(ip)  # כאן כל קריאה נספרת, לא רק כישלון


# ════════════════════════════════════════════════════════════════════════
#  התחייבות לאולם
# ════════════════════════════════════════════════════════════════════════

class CommitmentIn(BaseModel):
    """כל הסכומים באגורות שלמות — אותו כלל כמו בכל השרשרת הכספית."""

    attendees: int = Field(ge=0, le=finance.MAX_QUANTITY)
    meal_price_agorot: int = Field(ge=0, le=finance.MAX_AMOUNT_AGOROT)
    committed_quantity: Optional[int] = Field(default=None, ge=0, le=finance.MAX_QUANTITY)
    min_total_agorot: Optional[int] = Field(default=None, ge=0, le=finance.MAX_AMOUNT_AGOROT)
    #: הוצאות נוספות **לאדם** מעבר למנה (אלכוהול, מתנה לאורח). נכנסות
    #: כשורת ``per_attendee`` נפרדת בלי התחייבות — וזה מה שהופך את
    #: "כמה מוסיף אדם נוסף" לנכון גם מתחת להתחייבות: המנה לא מתווספת,
    #: אבל האלכוהול כן.
    extra_per_attendee_agorot: int = Field(default=0, ge=0, le=finance.MAX_AMOUNT_AGOROT)
    #: הוצאות קבועות (צילום, מוזיקה, עיצוב) — לא זזות עם מספר המגיעים,
    #: אבל כן משנות את העלות לאורח.
    fixed_agorot: int = Field(default=0, ge=0, le=finance.MAX_AMOUNT_AGOROT)


class LineOut(BaseModel):
    total_agorot: int
    total_display: str


class CommitmentOut(BaseModel):
    attendees: int
    committed_quantity: Optional[int]
    #: על כמה מנות משלמים בפועל — ``MAX(מגיעים, התחייבות)``.
    billed_quantity: int
    #: כמה מההתחייבות לא ינוצל (0 כשאין התחייבות או כשעברו אותה).
    unused_quantity: int
    #: כמה מגיעים מעבר להתחייבות.
    over_commitment: int
    #: האם המינימום הכספי בחוזה הוא זה שקבע את המחיר.
    min_total_applied: bool
    meal_line: LineOut
    total_agorot: int
    total_display: str
    cost_per_attendee_agorot: Optional[int]
    cost_per_attendee_display: Optional[str]
    next_attendee_agorot: int
    next_attendee_display: str
    #: לוח תרחישים: מה תהיה העלות במספרי מגיעים אחרים.
    scenarios: list["ScenarioOut"]


class ScenarioOut(BaseModel):
    attendees: int
    total_agorot: int
    total_display: str
    is_current: bool
    is_commitment: bool


CommitmentOut.model_rebuild()


def _expense(
    expense_id: int,
    *,
    method: str,
    amount_agorot: int,
    committed: Optional[int] = None,
    min_total: Optional[int] = None,
) -> models.EventExpense:
    """שורת הוצאה זמנית בזיכרון — **לא נשמרת ולא נכנסת ל-Session.**

    ``id`` נקבע ידנית כי ``finance.cost_breakdown`` ממפה תוצאות לפי מזהה
    השורה, ואובייקט שלא נשמר עדיין אין לו מזהה משלו.
    """
    return models.EventExpense(
        id=expense_id,
        event_id=0,
        category="other",
        item_key="",
        label="",
        calc_method=method,
        amount_agorot=amount_agorot,
        quantity=None,
        committed_quantity=committed,
        min_total_agorot=min_total,
        vendor="",
        is_estimated=True,
        is_paid=False,
        paid_amount_agorot=0,
        sort_order=expense_id,
    )


def _build_expenses(payload: CommitmentIn) -> list[models.EventExpense]:
    """שלוש שורות לכל היותר: המנה (עם ההתחייבות), תוספת לאדם, וקבוע."""
    rows = [
        _expense(
            1,
            method=PER_ATTENDEE,
            amount_agorot=payload.meal_price_agorot,
            committed=payload.committed_quantity or None,
            min_total=payload.min_total_agorot or None,
        )
    ]
    if payload.extra_per_attendee_agorot:
        rows.append(
            _expense(2, method=PER_ATTENDEE, amount_agorot=payload.extra_per_attendee_agorot)
        )
    if payload.fixed_agorot:
        rows.append(_expense(3, method=FIXED, amount_agorot=payload.fixed_agorot))
    return rows


@router.post("/venue-commitment", response_model=CommitmentOut)
def venue_commitment(payload: CommitmentIn, request: Request) -> CommitmentOut:
    """כמה משלמים בפועל מול ההתחייבות, וכמה מוסיף כל אדם נוסף.

    **כל מספר כאן מגיע מ-``app/finance.py``**, כולל כלל ההתחייבות
    (``MAX(מגיעים, התחייבות)``), המינימום הכספי, ו"האורח הבא" שנגזר
    כהפרש בין שני מצבים ולא כסכום מחירים.
    """
    _guard(request)

    expenses = _build_expenses(payload)
    # ``invited`` שווה ל-``attendees`` כי אין כאן שורות ``per_guest``.
    breakdown = finance.cost_breakdown(expenses, payload.attendees, payload.attendees)
    meal = breakdown.lines[1]

    scenarios = [
        ScenarioOut(
            attendees=n,
            total_agorot=finance.total_for(expenses, n, n),
            total_display=finance.format_shekels(finance.total_for(expenses, n, n)),
            is_current=n == payload.attendees,
            is_commitment=bool(payload.committed_quantity) and n == payload.committed_quantity,
        )
        for n in finance.scenario_points(payload.attendees, expenses)
    ]

    return CommitmentOut(
        attendees=payload.attendees,
        committed_quantity=payload.committed_quantity,
        billed_quantity=meal.billed_quantity or 0,
        unused_quantity=meal.unused_quantity,
        over_commitment=meal.over_commitment,
        min_total_applied=meal.min_total_applied,
        meal_line=LineOut(
            total_agorot=meal.total_agorot,
            total_display=finance.format_shekels(meal.total_agorot),
        ),
        total_agorot=breakdown.total_agorot,
        total_display=finance.format_shekels(breakdown.total_agorot),
        cost_per_attendee_agorot=breakdown.cost_per_attendee_agorot,
        cost_per_attendee_display=(
            finance.format_shekels(breakdown.cost_per_attendee_agorot)
            if breakdown.cost_per_attendee_agorot is not None
            else None
        ),
        next_attendee_agorot=breakdown.next_attendee_agorot,
        next_attendee_display=finance.format_shekels(breakdown.next_attendee_agorot),
        scenarios=scenarios,
    )


# ════════════════════════════════════════════════════════════════════════
#  לוח הזמנים של אישורי ההגעה
# ════════════════════════════════════════════════════════════════════════

class TimelineIn(BaseModel):
    #: תאריך האירוע, ``YYYY-MM-DD``.
    event_date: str
    #: כמה ימים לפני האירוע צריך למסור לאולם מספר סופי (1–10) — בדיוק
    #: אותו טווח שנאכף במערכת עצמה.
    commit_days_before: int = Field(ge=1, le=10)


#: תוויות ציבוריות לשלבי הסבב.
#:
#: **למה לא משתמשים ב-``rsvp_timeline.CYCLE[...]["label"]`` ישירות:** התווית
#: שם נכתבה למסך של בעל האירוע בתוך המערכת, והיא נוקבת בערוץ השליחה
#: ("בקשת אישור ראשונה ב-WhatsApp"). באתר הציבורי אסור להבטיח ערוץ שליחה
#: שאינו פעיל בייצור, ולכן המחשבון מתאר את **השלב** ולא את הערוץ.
#: זו החלפת תצוגה בלבד — התאריכים, הסדר והמספר עדיין מגיעים מהמנוע.
PUBLIC_STEP_LABELS = {
    "whatsapp_first": "בקשת אישור הגעה ראשונה",
    "reminder": "תזכורת",
    "call_round": "סבב מעקב טלפוני",
}


class PlacementOut(BaseModel):
    type: str
    label: str
    icon: str
    date: date
    weekday: str
    days_before_event: int
    #: השלב הוזז ממיקומו הטבעי בסבב. הסיבה יכולה להיות סוף שבוע **או**
    #: אכיפת הפער המינימלי מהשלב הקודם — ולכן השם גנרי ולא "הוזז מסוף
    #: שבוע", שהיה טענה שאינה נכונה בחלק מהמקרים.
    shifted: bool
    round_number: Optional[int]


class TimelineOut(BaseModel):
    event_date: date
    commitment_date: date
    commitment_weekday: str
    #: לוח דחוס = לא נשאר מספיק זמן לסבב המלא, והשלבים התכווצו.
    compressed: bool
    placements: list[PlacementOut]


def _public_label(placement: rsvp_timeline.Placement) -> str:
    """תווית השלב לאתר הציבורי, ממוספרת כשיש כמה שלבים מאותו סוג."""
    base = PUBLIC_STEP_LABELS.get(placement.step["type"], placement.step["label"])
    if placement.round_number:
        return f"{base} {placement.round_number}"
    return base


@router.post("/rsvp-timeline", response_model=TimelineOut)
def rsvp_schedule(payload: TimelineIn, request: Request) -> TimelineOut:
    """לוח הזמנים של אישורי ההגעה, נפרס **לאחור** ממועד סגירת הרשימה.

    מריץ את ``rsvp_timeline.compute_schedule`` על אירוע זמני בזיכרון —
    אותו מנוע בדיוק שמזין את מסך אישורי ההגעה ואת תור השיחות.
    """
    _guard(request)

    try:
        parsed = datetime.strptime(payload.event_date.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="נשמח שתזינו תאריך אירוע תקין.")

    if parsed < date.today():
        raise HTTPException(status_code=400, detail="תאריך האירוע כבר עבר. אפשר לבחור תאריך עתידי?")

    event = models.Event(
        event_date=parsed.isoformat(),
        venue_commit_days_before=payload.commit_days_before,
        rsvp_track_started_at=None,
    )
    schedule = rsvp_timeline.compute_schedule(event)
    if schedule is None:  # pragma: no cover — נחסם כבר בוולידציה למעלה
        raise HTTPException(status_code=400, detail="לא הצלחנו לחשב לוח זמנים לתאריך הזה.")

    return TimelineOut(
        event_date=parsed,
        commitment_date=schedule.commitment_date,
        commitment_weekday=rsvp_timeline.hebrew_weekday(schedule.commitment_date),
        compressed=schedule.compressed,
        placements=[
            PlacementOut(
                type=p.step["type"],
                label=_public_label(p),
                icon=p.step["icon"],
                date=p.date,
                weekday=rsvp_timeline.hebrew_weekday(p.date),
                days_before_event=(parsed - p.date).days,
                shifted=p.moved_from_weekend,
                round_number=p.round_number,
            )
            for p in schedule.placements
        ],
    )
