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
    ITEMS,
    PER_ATTENDEE,
    PER_GUEST,
    PER_UNIT,
    PERCENT,
    TEMPLATES,
    catalog_for,
    category_label,
    default_items_for,
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
#  6. אחוזים
# ════════════════════════════════════════════════════════════════════════

def test_percent_is_computed_on_the_non_percent_base() -> None:
    """טיפים של 10% נגזרים מסך שאר ההוצאות, לא מהסך שכולל אותם."""
    expenses = [line(1, FIXED, 100_000), line(2, PERCENT, 0, quantity=10)]
    breakdown = finance.cost_breakdown(expenses, 100, 100)

    assert breakdown.lines[2].total_agorot == 10_000 * S
    assert breakdown.total_agorot == 110_000 * S


def test_two_percent_lines_do_not_feed_each_other() -> None:
    """שתי שורות אחוז נגזרות מאותו בסיס יציב. אילו אחוז היה נגזר מהסך
    שכולל אותו, השתיים היו מזינות זו את זו — והתוצאה הייתה תלויה בסדר
    שבו הוזנו."""
    expenses = [
        line(1, FIXED, 100_000),
        line(2, PERCENT, 0, quantity=10),
        line(3, PERCENT, 0, quantity=5),
    ]
    breakdown = finance.cost_breakdown(expenses, 100, 100)

    assert breakdown.lines[2].total_agorot == 10_000 * S
    assert breakdown.lines[3].total_agorot == 5_000 * S
    assert breakdown.total_agorot == 115_000 * S


def test_percent_grows_with_the_attendee_count() -> None:
    """שורת אחוז זזה עם מספר המגיעים, כי הבסיס שלה זז. לכן היא נספרת
    כ"הוצאה לפי כמות" ולא כהוצאה קבועה."""
    expenses = [line(1, PER_ATTENDEE, 320), line(2, PERCENT, 0, quantity=10)]

    small = finance.cost_breakdown(expenses, 100, 100)
    big = finance.cost_breakdown(expenses, 200, 200)

    assert big.lines[2].total_agorot == small.lines[2].total_agorot * 2
    assert small.fixed_agorot == 0, "אחוז אינו הוצאה קבועה"


def test_percent_rounds_half_up_in_integers() -> None:
    """עיגול חצי-כלפי-מעלה בחשבון שלמים — כמו ``gift.fee_for``."""
    expenses = [line(1, FIXED, 0), line(2, PERCENT, 0, quantity=3)]
    expenses[0].amount_agorot = 15  # 15 אגורות × 3% = 0.45 → 0
    assert finance.cost_breakdown(expenses, 0, 0).lines[2].total_agorot == 0

    expenses[0].amount_agorot = 20  # 20 × 3% = 0.6 → 1
    assert finance.cost_breakdown(expenses, 0, 0).lines[2].total_agorot == 1


# ════════════════════════════════════════════════════════════════════════
#  7. תבנית לכל סוג אירוע (Event-first)
# ════════════════════════════════════════════════════════════════════════

#: שבעת הסוגים שקיימים בפועל, לפי ה-Audit של הקוד. הרשימה כאן היא
#: **הנעילה**: תבנית לסוג שאי אפשר ליצור היא קוד מת, וסוג בלי תבנית
#: הוא זוג שמקבל רשימה גנרית.
REAL_EVENT_TYPES = (
    "wedding", "henna", "bar_mitzvah", "bat_mitzvah", "brit", "brita", "business",
)

#: סוגים שהתבקשו במפורש **לא** להתקיים. הבדיקה שומרת שלא ייכנסו בדלת
#: האחורית דרך תבנית.
FORBIDDEN_EVENT_TYPES = ("engagement", "birthday", "shabbat_chatan", "sheva_brachot")


def test_templates_match_the_real_event_types_exactly() -> None:
    from app import event_terms

    assert set(TEMPLATES) == set(REAL_EVENT_TYPES)
    # והרשימה זהה למנוע המונחים — שני מקורות שחייבים להישאר מסונכרנים.
    assert set(TEMPLATES) == set(event_terms.EVENT_TERMS)


def test_no_invented_event_types() -> None:
    for forbidden in FORBIDDEN_EVENT_TYPES:
        assert forbidden not in TEMPLATES, f"סוג אירוע שאינו קיים במערכת: {forbidden}"


def test_every_type_has_a_substantial_template() -> None:
    """"תבנית" של ארבעה סעיפים אינה תבנית — היא רשימה גנרית בתחפושת."""
    for event_type in REAL_EVENT_TYPES:
        categories = catalog_for(event_type)
        items = [i for c in categories for i in c.items]
        defaults = [i for i in items if i.is_default]

        assert len(categories) >= 6, f"{event_type}: מעט מדי קטגוריות"
        assert len(items) >= 25, f"{event_type}: מיפוי דל מדי"
        # ברירות המחדל הן מה שנפתח על המסך — צריכות להספיק להתחיל,
        # ולא להציף.
        assert 5 <= len(defaults) <= 25, f"{event_type}: {len(defaults)} ברירות מחדל"


def test_templates_are_actually_different_from_each_other() -> None:
    """תבנית שזהה לאחרת פירושה שסוג האירוע לא קיבל התאמה אמיתית."""
    signatures = {
        et: frozenset(i.key for c in catalog_for(et) for i in c.items)
        for et in REAL_EVENT_TYPES
    }
    for a in REAL_EVENT_TYPES:
        for b in REAL_EVENT_TYPES:
            if a < b:
                assert signatures[a] != signatures[b], f"{a} ו-{b} קיבלו אותה תבנית"


def test_type_specific_items_do_not_leak() -> None:
    """הבדיקה המרכזית של Event-first: פריט שמוגדר לסוג אחד לא מופיע
    בסוג שאין לו שום קשר אליו."""
    def keys(event_type: str) -> set:
        return {i.key for c in catalog_for(event_type) for i in c.items}

    # חופה, טבעות וכתובה — חתונה בלבד.
    for wedding_only in ("chuppah", "rings", "ketubah"):
        assert wedding_only in keys("wedding")
        for other in ("brit", "brita", "business", "bar_mitzvah", "bat_mitzvah"):
            assert wedding_only not in keys(other), f"{wedding_only} דלף ל-{other}"

    # מוהל — ברית בלבד. לא בבריתה, ובוודאי לא באירוע עסקי.
    assert "mohel" in keys("brit")
    for other in ("brita", "wedding", "business", "bar_mitzvah"):
        assert "mohel" not in keys(other), f"מוהל דלף ל-{other}"

    # תפילין — בר מצווה בלבד.
    assert "tefillin" in keys("bar_mitzvah")
    assert "tefillin" not in keys("bat_mitzvah")

    # מרצה, תגי שם וסטרימינג — אירוע עסקי.
    for business_only in ("speaker", "name_tags", "streaming"):
        assert business_only in keys("business")
        assert business_only not in keys("brit")

    # עיצוב חינה — חינה בלבד.
    assert "henna_design" in keys("henna")
    assert "henna_design" not in keys("wedding")


def test_meal_line_carries_the_commitment_fields() -> None:
    """שדות ההתחייבות פתוחים על שורת המנה בכל סוג שיש בו מנות — שם
    נמצא רוב הכסף, ושם החוזה נוקב במינימום."""
    for event_type in ("wedding", "henna", "bar_mitzvah", "bat_mitzvah"):
        items = {i.key: i for c in catalog_for(event_type) for i in c.items}
        meal = items.get("meal_price") or items.get("meals")
        assert meal is not None, f"{event_type}: אין שורת מנה"
        assert meal.supports_commitment, f"{event_type}: המנה בלי שדות התחייבות"
        assert meal.calc_method == PER_ATTENDEE


def test_default_items_are_a_subset_of_the_catalog() -> None:
    for event_type in REAL_EVENT_TYPES:
        catalog = {i.key for c in catalog_for(event_type) for i in c.items}
        defaults = {item.key for _, item in default_items_for(event_type)}
        assert defaults <= catalog


def test_unknown_event_type_falls_back_without_breaking() -> None:
    """סוג לא מוכר נופל לתבנית החתונה — נפילה שמורידה דיוק, לא שוברת
    מסך. **בלי** ליצור "תבנית גנרית" שהיא סוג אירוע שמיני."""
    assert catalog_for("something_new") == catalog_for("wedding")


def test_no_raw_category_key_ever_reaches_the_screen() -> None:
    """מפתח קטגוריה שהוסר מהתבניות עדיין יושב על שורות קיימות ב-DB.
    בלי מפת התאימות הזוג היה רואה "venue_food" ככותרת קבוצה — מפתח
    פנימי שדלף למסך."""
    for legacy in ("venue_food", "bride", "groom", "rings", "invitations",
                   "transport", "tips", "other"):
        label = category_label(legacy, "wedding")
        assert label != legacy, f"מפתח גולמי דלף למסך: {legacy}"
        assert not any(c.isascii() and c.isalpha() for c in label)


def test_category_label_is_event_type_aware() -> None:
    """אותו מפתח, ניסוח אחר לפי הסוג: אב לתינוק לא אמור לראות
    "התינוקת", ואירוע עסקי לא אמור לראות "מקום ואירוח"."""
    assert category_label("baby", "brit") == "התינוק"
    assert category_label("baby", "brita") == "התינוקת"
    assert category_label("venue", "wedding") == "מקום ואירוח"
    assert category_label("venue", "business") == "מקום"


def test_every_template_item_exists_in_the_pool() -> None:
    """שגיאת הקלדה במפתח פריט הייתה מפילה את הייבוא — הבדיקה תופסת
    אותה בשם, לא ב-KeyError סתום."""
    for event_type in REAL_EVENT_TYPES:
        for category in catalog_for(event_type):
            for item in category.items:
                assert item.key in ITEMS


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")
    print(f"\n{len(tests)} בדיקות עברו.")
