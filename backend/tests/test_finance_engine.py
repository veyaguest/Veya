"""בדיקות למנוע כספי האירוע — עלות, התחייבות לאולם, ותרחישים.

שלושה דברים שהקובץ הזה נועל, וכל אחד מהם הוא **מספר שהזוג מוסר לאולם**
או משלם בפועל. בדיקה שנשברת כאן אינה באג בתצוגה:

1. **ההתחייבות לאולם קובעת את המחיר, לא מספר המגיעים.** זוג שהתחייב על
   500 מנות ומגיעים אליו 463 משלם על 500. הכלל:
   ``MAX(MAX(מגיעים, התחייבות) × מחיר, מינימום כספי)``.
2. **"כמה עולה אורח נוסף" נגזר כהפרש בין שני מצבים.** לכן הוא 0 מתחת
   לכמות ההתחייבות (כבר משלמים על האורח הזה) ומחיר מנה מלא מעליה. חישוב
   שהיה מחזיר "מחיר מנה" תמיד הוא תשובה שגויה ברוב חייו של אירוע ישראלי.
3. **אין ``float`` בשום מקום בשרשרת.** אגורות שלמות בלבד, כמו ב-``gift.py``.

הרצה: ``venv/bin/python tests/test_finance_engine.py`` (עצמאי, בלי pytest).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import finance, models  # noqa: E402
from app.finance_categories import (  # noqa: E402
    FIXED,
    PER_ATTENDEE,
    PER_GUEST,
    PER_UNIT,
    catalog_for,
)

#: ₪1 = 100 אגורות. הבדיקות כתובות בשקלים כדי שיהיו קריאות, וממירות כאן.
S = 100


def line(row_id: int, method: str, shekels: int, **kw) -> models.EventExpense:
    expense = models.EventExpense(
        calc_method=method, amount_agorot=shekels * S, **kw
    )
    expense.id = row_id
    return expense


# ════════════════════════════════════════════════════════════════════════
#  1. ההתחייבות לאולם
# ════════════════════════════════════════════════════════════════════════

def test_below_commitment_pays_for_the_commitment() -> None:
    """463 מגיעים, 500 התחייבות, ₪320 למנה ⇒ ₪160,000 (ולא ₪148,160)."""
    meal = line(1, PER_ATTENDEE, 320, committed_quantity=500)
    result = finance._line_total(meal, attendees=463, invited=560)

    assert result.total_agorot == 500 * 320 * S, "משלמים על ההתחייבות, לא על המגיעים"
    assert result.billed_quantity == 500
    assert result.unused_quantity == 37, "37 מנות שולמו ואיש לא ישב בהן"
    assert result.over_commitment == 0


def test_above_commitment_pays_for_actual_attendees() -> None:
    """527 מגיעים מול 500 התחייבות ⇒ ₪168,640 — ההתחייבות כבר לא רלוונטית."""
    meal = line(1, PER_ATTENDEE, 320, committed_quantity=500)
    result = finance._line_total(meal, attendees=527, invited=560)

    assert result.total_agorot == 527 * 320 * S
    assert result.billed_quantity == 527
    assert result.over_commitment == 27
    assert result.unused_quantity == 0


def test_money_minimum_wins_when_higher() -> None:
    """מינימום כספי מובטח גובר על מכפלת הכמות כשהוא הגבוה מבין השניים.

    שני התנאים יכולים להתקיים יחד בחוזה אחד, ואז הגבוה מנצח — זה כלל
    ההתקשרות, לא הנחה שמספר המגיעים לבדו קובע.
    """
    meal = line(1, PER_ATTENDEE, 320, committed_quantity=400, min_total_agorot=155_000 * S)
    result = finance._line_total(meal, attendees=380, invited=420)

    assert result.total_agorot == 155_000 * S
    assert result.min_total_applied is True


def test_commitment_ignored_when_method_is_not_per_attendee() -> None:
    """שדה התחייבות על שורה שאינה "לפי אורח" אינו משנה דבר.

    ה-API מנקה את השדה במעבר בין שיטות, אבל המנוע לא סומך על זה —
    שורה ישנה בבסיס נתונים קיים עדיין צריכה להתנהג נכון.
    """
    fixed = line(1, FIXED, 8_000, committed_quantity=500)
    assert finance._line_total(fixed, attendees=10, invited=10).total_agorot == 8_000 * S


# ════════════════════════════════════════════════════════════════════════
#  2. עלות האורח הבא — המדרגה שרוב המערכות מפספסות
# ════════════════════════════════════════════════════════════════════════

def test_next_attendee_is_free_below_commitment() -> None:
    """מתחת להתחייבות אורח נוסף עולה ₪0 — כבר שילמו עליו."""
    expenses = [line(1, PER_ATTENDEE, 320, committed_quantity=500), line(2, FIXED, 8_000)]

    assert finance.cost_breakdown(expenses, 463, 560).next_attendee_agorot == 0
    assert finance.cost_breakdown(expenses, 499, 560).next_attendee_agorot == 0


def test_next_attendee_costs_full_price_at_and_above_commitment() -> None:
    """מהאורח ה-501 ואילך כל אחד מוסיף מחיר מנה מלא."""
    expenses = [line(1, PER_ATTENDEE, 320, committed_quantity=500), line(2, FIXED, 8_000)]

    assert finance.cost_breakdown(expenses, 500, 560).next_attendee_agorot == 320 * S
    assert finance.cost_breakdown(expenses, 527, 560).next_attendee_agorot == 320 * S


def test_step_costs_cross_the_commitment_correctly() -> None:
    """קפיצה של 50 אורחים מ-480 חוצה את ההתחייבות — רק 30 מהם עולים כסף."""
    expenses = [line(1, PER_ATTENDEE, 320, committed_quantity=500)]
    added = finance.total_for(expenses, 530, 560) - finance.total_for(expenses, 480, 560)

    assert added == 30 * 320 * S, "20 האורחים הראשונים כבר שולמו בהתחייבות"


# ════════════════════════════════════════════════════════════════════════
#  3. שיטות החישוב
# ════════════════════════════════════════════════════════════════════════

def test_per_guest_counts_invited_not_attendees() -> None:
    """הזמנה ומעטפה נקנות לפי מי שהוזמן, לא לפי מי שבסוף הגיע."""
    envelopes = line(1, PER_GUEST, 12)
    assert finance._line_total(envelopes, attendees=463, invited=560).total_agorot == 560 * 12 * S


def test_per_unit_uses_quantity() -> None:
    albums = line(1, PER_UNIT, 900, quantity=3)
    assert finance._line_total(albums, attendees=463, invited=560).total_agorot == 2_700 * S


def test_fixed_ignores_all_counts() -> None:
    dj = line(1, FIXED, 8_000)
    assert finance._line_total(dj, 0, 0).total_agorot == 8_000 * S
    assert finance._line_total(dj, 900, 900).total_agorot == 8_000 * S


def test_totals_split_fixed_and_variable() -> None:
    expenses = [line(1, PER_ATTENDEE, 320, committed_quantity=500), line(2, FIXED, 8_000)]
    breakdown = finance.cost_breakdown(expenses, 463, 560)

    assert breakdown.total_agorot == 168_000 * S
    assert breakdown.fixed_agorot == 8_000 * S
    assert breakdown.variable_agorot == 160_000 * S
    # הסיכום מגיע מ-``total_for`` ולא מחיבור שני החלקים, אבל הם חייבים
    # להסתדר — אחרת הפילוח במסך לא יסתכם לסך שמעליו.
    assert breakdown.fixed_agorot + breakdown.variable_agorot == breakdown.total_agorot


def test_cost_per_attendee_is_none_without_attendees() -> None:
    """אין מגיעים ⇒ אין "עלות לאורח". חלוקה באפס אינה 0 ₪, היא שאלה בלי
    תשובה — ומספר מומצא במסך כספי גרוע מהיעדרו."""
    assert finance.cost_breakdown([line(1, FIXED, 8_000)], 0, 0).cost_per_attendee_agorot is None


# ════════════════════════════════════════════════════════════════════════
#  4. תרחישים
# ════════════════════════════════════════════════════════════════════════

def test_scenarios_include_actual_and_commitment_points() -> None:
    """הלוח חייב לכלול את המצב בפועל ואת כמות ההתחייבות, לא רק מספרים
    עגולים — אלה בדיוק שתי הנקודות שהזוג עומד בהן."""
    expenses = [line(1, PER_ATTENDEE, 320, committed_quantity=500)]
    points = finance.scenario_points(463, expenses)

    assert 463 in points, "המצב בפועל"
    assert 500 in points, "כמות ההתחייבות"
    assert all(p > 0 for p in points)
    assert points == sorted(points)


def test_scenario_totals_match_the_summary_at_the_current_point() -> None:
    """התרחיש שמייצג את המצב הנוכחי חייב להיות זהה לסיכום. שני מספרים
    שונים לאותו מצב באותו מסך הם ההגדרה של אובדן אמון."""
    expenses = [line(1, PER_ATTENDEE, 320, committed_quantity=500), line(2, FIXED, 8_000)]
    breakdown = finance.cost_breakdown(expenses, 463, 560)

    assert finance.total_for(expenses, 463, 560) == breakdown.total_agorot


# ════════════════════════════════════════════════════════════════════════
#  5. ולידציה ואגורות שלמות
# ════════════════════════════════════════════════════════════════════════

def test_parse_agorot_rejects_floats_and_bools() -> None:
    """אותה קפדנות כמו ב-``gift.parse_amount_agorot``: ``bool`` הוא תת-מחלקה
    של ``int`` ו-``True`` היה הופך לאגורה אחת; ``float`` כבר עלול לשאת
    שגיאת ייצוג ולכן נדחה ולא "מעוגל בנימוס"."""
    for bad in (True, False, None, 3.5, "abc", "", [], -1):
        try:
            finance.parse_agorot(bad)
        except finance.FinanceInputError:
            continue
        raise AssertionError(f"קלט לא תקין התקבל: {bad!r}")

    assert finance.parse_agorot(32_000) == 32_000
    assert finance.parse_agorot("32000") == 32_000


def test_format_shekels_puts_the_sign_after_the_number() -> None:
    """הכתיב הישראלי: המספר ואז הסימן. "₪160,000" הוא סדר אנגלי שנראה
    כמו תרגום — ראו ``hebrew-writing-rules``."""
    assert finance.format_shekels(160_000 * S).startswith("160,000")
    assert finance.format_shekels(160_000 * S).endswith("₪")
    assert finance.format_shekels(10_450) == "104.50\u202f₪"
    assert finance.format_shekels(None) == ""


def test_no_floats_anywhere_in_the_result() -> None:
    expenses = [line(1, PER_ATTENDEE, 320, committed_quantity=500), line(2, PER_UNIT, 900, quantity=3)]
    breakdown = finance.cost_breakdown(expenses, 463, 560)

    for value in (breakdown.total_agorot, breakdown.fixed_agorot,
                  breakdown.variable_agorot, breakdown.next_attendee_agorot):
        assert isinstance(value, int) and not isinstance(value, bool)


# ════════════════════════════════════════════════════════════════════════
#  6. הקטלוג מותאם לסוג האירוע (Event-first)
# ════════════════════════════════════════════════════════════════════════

def test_wedding_categories_do_not_leak_into_other_event_types() -> None:
    """"כלה"/"חתן"/"טבעות" הן קטגוריות חתונתיות. הצגתן בברית או באירוע
    עסקי אינה טעות ניסוח — היא מוצר שבור."""
    wedding_keys = {c.key for c in catalog_for("wedding")}
    assert {"bride", "groom", "rings"} <= wedding_keys
    assert "attire" not in wedding_keys, "בחתונה יש שתי קטגוריות לבוש, לא אחת גנרית"

    for event_type in ("bar_mitzvah", "brit", "business"):
        keys = {c.key for c in catalog_for(event_type)}
        assert not ({"bride", "groom", "rings"} & keys), f"קטגוריה חתונתית דלפה ל-{event_type}"
        assert "attire" in keys, f"אין קטגוריית לבוש ל-{event_type}"


def test_chuppah_is_filtered_out_of_non_wedding_design() -> None:
    """פריט חתונתי בתוך קטגוריה משותפת מסונן בנפרד, בלי לשכפל קטגוריה."""
    design = {c.key: c for c in catalog_for("business")}["design"]
    assert "chuppah" not in {i.key for i in design.items}

    wedding_design = {c.key: c for c in catalog_for("wedding")}["design"]
    assert "chuppah" in {i.key for i in wedding_design.items}


def test_unknown_event_type_gets_the_safe_default() -> None:
    """סוג לא מוכר מקבל את ברירת המחדל הרחבה ולא רשימה ריקה — מוצר שבור
    לא ייווצר מטעות הקלדה בשם סוג."""
    keys = {c.key for c in catalog_for("something_new")}
    assert "venue_food" in keys and "attire" in keys


def test_meal_is_the_only_item_opened_with_commitment_fields() -> None:
    """"מינימום התחייבות" אינו פריט נפרד בקטלוג אלא שדה על שורת המנה.
    פריט נפרד היה נספר פעמיים בסיכום."""
    venue = {c.key: c for c in catalog_for("wedding")}["venue_food"]
    item_keys = {i.key for i in venue.items}

    assert "meal_price" in item_keys
    assert not any("minimum" in k for k in item_keys)
    assert [i.key for i in venue.items if i.supports_commitment] == ["meal_price"]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")
    print(f"\n{len(tests)} בדיקות עברו.")
