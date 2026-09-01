"""מנוע החישוב של כספי האירוע — אגורות בלבד, מספרים שלמים בלבד.

אותו כלל ברזל כמו ב-``app/gift.py``, ומאותה סיבה: **אין כאן ``float``.**
0.1 + 0.2 אינו 0.3 בבינארי, וסיכום של ₪180,000 שסוטה באגורה הוא בדיוק סוג
התקלה שמתגלה רק כשמישהו משווה מול חשבונית. כל סכום כאן הוא ``int`` של
אגורות (₪1 = 100 אגורות).

**המודול הזה הוא מקור-האמת היחיד לחישוב.** ה-Frontend לא מחשב כסף — הוא
שואל את השרת ומצייר את מה שקיבל. שני מקורות חישוב לאותו מספר הם ההגדרה
של באג שמתגלה מאוחר.

## הרעיון המרכזי: העלות היא **פונקציה של מספר המגיעים**

כל החישובים במסך — הסיכום, עלות לאורח, "כמה עולה כל אורח נוסף", ולוח
התרחישים — נגזרים מפונקציה אחת: ``total_for(expenses, n, invited)``.

זו לא אלגנטיות לשמה. בלי זה, "כמה עולה אורח נוסף" היה מחושב כסכום מחירי
המנה — וזו **תשובה שגויה** ברוב חייו של אירוע ישראלי:

    התחייבתם על 500 מנות. מגיעים 463.
    אורח נוסף עולה לכם ₪0 — אתם כבר משלמים עליו.
    האורח ה-501 יעלה ₪320.

הפונקציה נותנת את התשובה הנכונה בשתי המדרגות בלי שאף מסך יצטרך להכיר
את הכלל. תשובה שמחושבת כהפרש בין שני מצבים לא יכולה לסטות מהסיכום.

## ההתחייבות לאולם

    מנות לחיוב = MAX(מגיעים בפועל, כמות ההתחייבות)
    עלות השורה = MAX(מנות לחיוב × מחיר ליחידה, מינימום כספי)

שני התנאים יכולים להתקיים יחד (חוזה שנוקב גם בכמות וגם בסכום), ואז הגבוה
מנצח. זהו כלל ההתקשרות בפועל, ולא הנחה שמספר המגיעים לבדו קובע.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from app import models
from app.finance_categories import FIXED, PER_ATTENDEE, PER_GUEST, PER_UNIT, PERCENT

AGOROT_PER_SHEKEL = 100

#: תקרת שפיות לסכום יחיד: ₪10,000,000. לא "מגבלה עסקית" מומצאת — הגנה מפני
#: הקלדה שגויה שתהפוך את כל המסך ללא-קריא (ומפני ``int`` ענק ב-DB).
MAX_AMOUNT_AGOROT = 10_000_000 * AGOROT_PER_SHEKEL
#: תקרת כמות ליחידות/התחייבות. אולם של 100,000 מנות אינו אירוע.
MAX_QUANTITY = 100_000


class FinanceInputError(ValueError):
    """קלט כספי לא תקין. ההודעה מנוסחת לזוג, לא למפתח."""


# ════════════════════════════════════════════════════════════════════════
#  ולידציה
# ════════════════════════════════════════════════════════════════════════

def parse_agorot(raw: object, *, field: str = "הסכום", allow_zero: bool = True) -> int:
    """ממיר קלט לאגורות שלמות, או זורק שגיאה מנוסחת בעברית.

    אותה קפדנות כמו ב-``gift.parse_amount_agorot``: ``bool`` הוא תת-מחלקה
    של ``int`` בפייתון ו-``True`` היה הופך לאגורה אחת, ו-``float`` נדחה ולא
    "מעוגל בנימוס" — ערך שהגיע כ-float כבר עלול לשאת שגיאת ייצוג.
    """
    if isinstance(raw, bool) or raw is None:
        raise FinanceInputError(f"נשמח שתזינו {field}.")
    if isinstance(raw, int):
        agorot = raw
    elif isinstance(raw, float):
        raise FinanceInputError(f"{field} צריך להיות מספר שלם של אגורות.")
    elif isinstance(raw, str):
        text = raw.strip()
        if not text or not text.lstrip("-").isdigit():
            raise FinanceInputError(f"נשמח שתזינו {field} בשקלים.")
        agorot = int(text)
    else:
        raise FinanceInputError(f"נשמח שתזינו {field} בשקלים.")

    if agorot < 0:
        raise FinanceInputError(f"{field} לא יכול להיות שלילי.")
    if agorot == 0 and not allow_zero:
        raise FinanceInputError(f"{field} צריך להיות גדול מאפס.")
    if agorot > MAX_AMOUNT_AGOROT:
        raise FinanceInputError(f"{field} גבוה מדי. אפשר לבדוק שוב?")
    return agorot


def parse_quantity(raw: object, *, field: str = "הכמות") -> int:
    if isinstance(raw, bool) or raw is None:
        raise FinanceInputError(f"נשמח שתזינו {field}.")
    if isinstance(raw, int):
        value = raw
    elif isinstance(raw, str) and raw.strip().isdigit():
        value = int(raw.strip())
    else:
        raise FinanceInputError(f"{field} צריכה להיות מספר שלם.")
    if value < 0:
        raise FinanceInputError(f"{field} לא יכולה להיות שלילית.")
    if value > MAX_QUANTITY:
        raise FinanceInputError(f"{field} גבוהה מדי. אפשר לבדוק שוב?")
    return value


# ════════════════════════════════════════════════════════════════════════
#  ספירת אנשים — נשענת על המקור הקיים, לא סופרת מחדש
# ════════════════════════════════════════════════════════════════════════

def attendee_count(guests: Iterable[models.Guest]) -> int:
    """כמה אנשים מגיעים בפועל.

    נשען על ``Guest.effective_seats`` — **אותו מקור בדיוק** שמנוע ההושבה
    וסידור השולחנות משתמשים בו. זו לא הימנעות מכפילות בלבד: אילו המסך
    הכספי היה סופר אחרת ממסך ההושבה, הזוג היה רואה שני מספרי "מגיעים"
    שונים באותו מוצר, וזה מסוג הפערים שהורסים אמון במספרים.

    לפי ההחלטה שכבר נעולה שם: רק "מגיע" נספר. "מתלבט" ו"טרם השיב" הם 0.
    """
    return sum(g.effective_seats for g in guests)


def invited_count(guests: Iterable[models.Guest]) -> int:
    """כמה אנשים הוזמנו — לפי ``party_size``, בלי קשר לתשובה.

    זה הבסיס ל-``per_guest``: הזמנה מודפסת ומעטפה נקנות לפי מי שהוזמן,
    לא לפי מי שבסוף הגיע.
    """
    return sum(g.party_size for g in guests)


# ════════════════════════════════════════════════════════════════════════
#  חישוב שורה בודדת
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LineResult:
    """התוצאה של שורת הוצאה אחת, במצב אורחים נתון."""

    expense_id: int
    #: העלות בפועל של השורה, באגורות.
    total_agorot: int
    #: הכמות שהשורה חויבה עליה בפועל (מנות/יחידות/אנשים). ``None`` לשורה
    #: קבועה — שם אין כמות, ו-1 היה מספר ממציא.
    billed_quantity: Optional[int]
    #: כמה מהכמות שחויבה **לא נוצלה** — מנות ששולמו ואיש לא ישב בהן.
    #: 0 כשאין התחייבות או כשהמגיעים עברו אותה.
    unused_quantity: int
    #: כמה מגיעים **מעבר** לכמות ההתחייבות. 0 כשאין חריגה.
    over_commitment: int
    #: האם המינימום הכספי הוא זה שקבע את המחיר בפועל.
    min_total_applied: bool


def _line_total(expense: models.EventExpense, attendees: int, invited: int) -> LineResult:
    """עלות שורה אחת במצב אורחים נתון. **הפונקציה היחידה שמכירה את הכללים.**

    מספר המגיעים מגיע כפרמטר ולא נקרא מהאירוע: זה בדיוק מה שמאפשר לשאול
    "מה יקרה ב-525 אורחים" בלי לגעת בנתונים, ולקבל תשובה שנגזרת מאותה
    לוגיקה כמו הסיכום האמיתי.
    """
    method = expense.calc_method
    unit = expense.amount_agorot or 0
    committed = expense.committed_quantity
    min_total = expense.min_total_agorot

    if method == PER_ATTENDEE:
        # ── כאן חי כלל ההתחייבות ──────────────────────────────────────
        # משלמים על הגבוה מבין "מי שמגיע" ל"מה שהתחייבנו עליו".
        billable = attendees
        unused = 0
        over = 0
        if committed:
            billable = max(attendees, committed)
            unused = max(0, committed - attendees)
            over = max(0, attendees - committed)
        total = billable * unit
    elif method == PER_GUEST:
        billable = invited
        unused = over = 0
        total = billable * unit
    elif method == PER_UNIT:
        billable = expense.quantity or 0
        unused = over = 0
        total = billable * unit
    elif method == PERCENT:
        # שורת אחוז אינה יכולה להיות מחושבת כאן: היא תלויה בסך שאר
        # השורות, ולכן היא מקבלת 0 בשלב הזה ומחושבת ב-``total_for``
        # אחרי שהבסיס ידוע. חישוב במקום אחד ולא בשניים.
        billable = expense.quantity
        unused = over = 0
        total = 0
    else:  # FIXED — וגם כל שיטה לא מוכרת, שנופלת לבטוחה שבהן
        billable = None
        unused = over = 0
        total = unit

    # המינימום הכספי מוחל **אחרי** חישוב הכמות, על כל שיטה. חוזה יכול
    # לנקוב גם בכמות מינימלית וגם בסכום מינימלי, ואז הגבוה מנצח.
    min_applied = False
    if min_total and total < min_total:
        total = min_total
        min_applied = True

    return LineResult(
        expense_id=expense.id,
        total_agorot=total,
        billed_quantity=billable,
        unused_quantity=unused,
        over_commitment=over,
        min_total_applied=min_applied,
    )


def percent_base(
    expenses: Sequence[models.EventExpense], attendees: int, invited: int
) -> int:
    """הבסיס שממנו נגזרות שורות האחוז: **סך כל השורות שאינן אחוז.**

    הגדרה מפורשת ולא "אחוז מהסה״כ", כדי למנוע מעגליות: אילו אחוז היה
    נגזר מהסך שכולל אותו, שתי שורות אחוז היו מזינות זו את זו. כך גם
    "10% טיפים" ו-"5% בלתי צפויות" נשארים שניהם נגזרים מאותו בסיס יציב,
    ולא תלויים בסדר שבו הוזנו.
    """
    return sum(
        _line_total(e, attendees, invited).total_agorot
        for e in expenses
        if e.calc_method != PERCENT
    )


def percent_line_total(expense: models.EventExpense, base: int) -> int:
    """שורת אחוז אחת. עיגול חצי-כלפי-מעלה בחשבון שלמים בלבד —
    בדיוק כמו ``gift.fee_for``, ומאותה סיבה: אין float בשרשרת הכספית."""
    percent = expense.quantity or 0
    return (base * percent + 50) // 100


def total_for(
    expenses: Sequence[models.EventExpense], attendees: int, invited: int
) -> int:
    """סך העלות במצב אורחים נתון — **הפונקציה שכל השאר נגזר ממנה.**

    הסיכום, התרחישים, "כמה עולה אורח נוסף" והשורה התחתונה כולם קוראים
    לה. לכן אין מצב שבו שני מספרים במסך סותרים זה את זה: הם לא מחושבים
    בשתי דרכים, הם אותה פונקציה בשתי נקודות.

    שני שלבים, כי שורות אחוז תלויות בשאר: קודם הבסיס, ואז האחוזים עליו.
    """
    base = percent_base(expenses, attendees, invited)
    return base + sum(
        percent_line_total(e, base) for e in expenses if e.calc_method == PERCENT
    )


# ════════════════════════════════════════════════════════════════════════
#  סיכום מלא
# ════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CostBreakdown:
    """התמונה הכספית של צד ההוצאות."""

    total_agorot: int
    #: הוצאות שאינן תלויות בכמות האנשים.
    fixed_agorot: int
    #: הוצאות שכן — מנה, אלכוהול, הזמנות. הפילוח הוא לתצוגה; הסיכום
    #: מגיע מ-``total_for`` ולא מחיבור שני החלקים, כדי שלא ייווצר מסלול
    #: חישוב שני לאותו מספר.
    variable_agorot: int
    attendees: int
    invited: int
    #: עלות ממוצעת לאורח שמגיע. ``None`` כשאין מגיעים — חלוקה באפס אינה
    #: "0 ₪ לאורח", היא שאלה בלי תשובה, וכך היא מוצגת.
    cost_per_attendee_agorot: Optional[int]
    #: כמה יעלה **האורח הבא**. נגזר כהפרש בין שני מצבים, ולכן נכון גם
    #: מתחת להתחייבות (₪0) וגם מעליה (מחיר מנה מלא).
    next_attendee_agorot: int
    lines: dict[int, LineResult]


def cost_breakdown(
    expenses: Sequence[models.EventExpense], attendees: int, invited: int
) -> CostBreakdown:
    lines = {e.id: _line_total(e, attendees, invited) for e in expenses}

    # שורות האחוז מקבלות את הערך שלהן רק עכשיו, כשהבסיס ידוע.
    base = percent_base(expenses, attendees, invited)
    for expense in expenses:
        if expense.calc_method == PERCENT:
            line = lines[expense.id]
            lines[expense.id] = LineResult(
                expense_id=line.expense_id,
                total_agorot=percent_line_total(expense, base),
                billed_quantity=line.billed_quantity,
                unused_quantity=0,
                over_commitment=0,
                min_total_applied=False,
            )

    total = sum(l.total_agorot for l in lines.values())

    # שורת אחוז נספרת כ"לפי כמות": היא זזה עם מספר המגיעים, בדיוק כמו
    # המנה שהיא נגזרת ממנה. סיווגה כ"קבועה" היה מציג טיפים כהוצאה
    # שאינה משתנה — וזה בדיוק ההפך מהאמת.
    fixed = sum(
        lines[e.id].total_agorot for e in expenses if e.calc_method == FIXED
    )
    variable = total - fixed

    per_attendee = total // attendees if attendees > 0 else None
    next_attendee = total_for(expenses, attendees + 1, invited) - total

    return CostBreakdown(
        total_agorot=total,
        fixed_agorot=fixed,
        variable_agorot=variable,
        attendees=attendees,
        invited=invited,
        cost_per_attendee_agorot=per_attendee,
        next_attendee_agorot=next_attendee,
        lines=lines,
    )


# ── תרחישים ─────────────────────────────────────────────────────────────

#: המדרגות שמוצגות ב"מה קורה אם יגיעו עוד". נבחרו כי הן הסדר גודל שבו
#: רשימת מוזמנים באמת זזה בשבועיים האחרונים.
STEP_SIZES = (10, 25, 50)

_SCENARIO_GRID = 25


def _round_to_grid(n: int) -> int:
    return max(_SCENARIO_GRID, round(n / _SCENARIO_GRID) * _SCENARIO_GRID)


def scenario_points(attendees: int, expenses: Sequence[models.EventExpense]) -> list[int]:
    """נקודות לוח התרחישים.

    שלושה סוגי נקודות, ובכוונה מעורבבות: מדרגות עגולות סביב המצב הנוכחי
    (450 · 475 · 500), **מספר המגיעים בפועל** (463 — כי זו הנקודה שהזוג
    באמת עומד בה), ו**כמות ההתחייבות** אם קיימת (500 — כי זו המדרגה שבה
    המחיר מתחיל לזוז). בלי שתי האחרונות הלוח היה יפה ולא רלוונטי.
    """
    center = _round_to_grid(attendees) if attendees else 100
    points = {center - 2 * _SCENARIO_GRID, center - _SCENARIO_GRID, center,
              center + _SCENARIO_GRID, center + 2 * _SCENARIO_GRID}
    if attendees > 0:
        points.add(attendees)
    for expense in expenses:
        if expense.calc_method == PER_ATTENDEE and expense.committed_quantity:
            points.add(expense.committed_quantity)
    return sorted(p for p in points if p > 0)


# ════════════════════════════════════════════════════════════════════════
#  הצגה
# ════════════════════════════════════════════════════════════════════════

def format_shekels(agorot: Optional[int]) -> str:
    """הצגה לבני אדם: 16000000 → "160,000 ₪".

    **סדר הכתיבה: המספר ואז הסימן**, עם רווח דק שאינו נשבר (U+202F) —
    זה הכתיב הישראלי, ו-"₪160,000" הוא סדר אנגלי שנראה כמו תרגום. אותו
    כלל בדיוק כמו ב-``GiftsPage.tsx``. אין כאן float — האגורות מופרדות
    בחשבון שלמים.
    """
    if agorot is None:
        return ""
    whole, remainder = divmod(abs(agorot), AGOROT_PER_SHEKEL)
    sign = "-" if agorot < 0 else ""
    body = f"{whole:,}" if not remainder else f"{whole:,}.{remainder:02d}"
    return f"{sign}{body} ₪"
