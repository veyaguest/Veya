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


def test_percent_line_cannot_be_computed_in_isolation() -> None:
    """רגרסיה: שורת אחוז שמחושבת לבדה מקבלת בסיס ריק, כלומר 0 ₪.

    זה בדיוק הבאג שנתפס ב-QA: ``routers/finance.py`` החזיר בתשובת
    ה-POST/PUT את השורה אחרי ``cost_breakdown([expense])`` — ואז אותה
    שורה הראתה 0 ₪ בתשובת השמירה ו-24,087 ₪ בסיכום. שני מספרים לאותה
    שורה, משני נתיבים באותו API.

    התיקון: ``_single_expense_read`` מחשב תמיד על כל שורות האירוע.
    הבדיקה כאן נועלת את ההתנהגות שגרמה לבאג, כדי שהיא לא תחזור דרך
    נתיב אחר.
    """
    pct = line(2, PERCENT, 0, quantity=10)
    alone = finance.cost_breakdown([pct], 100, 100)
    assert alone.lines[2].total_agorot == 0, "שורת אחוז לבדה אין לה בסיס"

    in_context = finance.cost_breakdown([line(1, FIXED, 100_000), pct], 100, 100)
    assert in_context.lines[2].total_agorot == 10_000 * S
    # המסקנה המעשית: לעולם לא לחשב שורה בודדת מחוץ להקשר שלה.
    assert alone.lines[2].total_agorot != in_context.lines[2].total_agorot


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


# ════════════════════════════════════════════════════════════════════════
#  איחוד שורות ברירת המחדל
# ════════════════════════════════════════════════════════════════════════
#
# שורה אחת לרכישה אחת. "תאורה" ו"הגברה" מגיעות כמעט תמיד מאותו ספק
# ובאותה הצעת מחיר, ושתי שורות נפרדות אילצו את הזוג לפצל סכום שקיבל
# כמקשה אחת. **האיחוד הוא בברירת המחדל בלבד** — מי שקיבל שתי הצעות
# עדיין מוצא את הפריטים הבודדים תחת "הוספת הוצאה".

#: (מפתח מאוחד, המפתחות שהוא עשוי להחליף). הרשימה רחבה בכוונה: "צילום
#: ווידאו" מחליף ``photo_stills`` בחתונה ו-``photo`` בחינה ובבר מצווה —
#: אותה רכישה, שם אחר לפי הסוג.
MERGED_ITEMS = (
    ("sound_lighting", ("sound", "lighting")),
    ("photo_video", ("photo_stills", "photo", "video")),
    ("design_flowers", ("flowers", "venue_design")),
    ("hair_makeup", ("makeup", "hair")),
)


def test_merged_items_exist_in_the_pool() -> None:
    for merged, _ in MERGED_ITEMS:
        assert merged in ITEMS, f"פריט מאוחד חסר מהמאגר: {merged}"


def test_merging_never_removes_the_separate_items() -> None:
    """**האיחוד מקצר, הוא לא מוחק שליטה.** בכל תבנית שהפריט המאוחד הוא
    בה ברירת מחדל, שני הפריטים הבודדים חייבים להישאר זמינים בקטלוג —
    אחרת זוג שקיבל שתי הצעות נפרדות לא יוכל לנהל אותן בנפרד."""
    for event_type in REAL_EVENT_TYPES:
        items = {i.key: i for c in catalog_for(event_type) for i in c.items}
        for merged, parts in MERGED_ITEMS:
            if not (items.get(merged) and items[merged].is_default):
                continue
            present = [p for p in parts if p in items]
            assert len(present) >= 2, (
                f"{event_type}: {merged} מוצע, אבל אין לצידו שני פריטים "
                "בודדים שאפשר לנהל בנפרד"
            )
            for part in present:
                assert not items[part].is_default, (
                    f"{event_type}: {part} נשאר ברירת מחדל לצד {merged} — "
                    "השורה תיווצר פעמיים"
                )


def test_merged_item_and_its_parts_share_a_category() -> None:
    """הפריט המאוחד והפריטים שהוא מחליף יושבים באותה קבוצה — אחרת
    "הצג עוד" בקבוצה הנכונה לא יגלה אותם."""
    for event_type in REAL_EVENT_TYPES:
        placement = {
            item.key: category.key
            for category in catalog_for(event_type)
            for item in category.items
        }
        for merged, parts in MERGED_ITEMS:
            if merged not in placement:
                continue
            for part in parts:
                if part in placement:
                    assert placement[part] == placement[merged], (
                        f"{event_type}: {part} בקבוצה אחרת מ-{merged}"
                    )


# ════════════════════════════════════════════════════════════════════════
#  קיבוץ ההוצאות לתצוגה
# ════════════════════════════════════════════════════════════════════════


def test_group_totals_add_up_to_the_summary() -> None:
    """**האינווריאנטה שמגינה על כותרת הקבוצה.**

    המסך מציג סכום לכל קבוצה מעל השורות שבתוכה. אם סכום הקבוצות אינו
    שווה בדיוק לסה״כ שבכותרת המסך, הזוג רואה שני מספרים שלא מסתדרים —
    וזו בדיוק הצורה שבה מסך כספי מאבד אמון. שורת אחוז היא המקרה המסוכן:
    היא נגזרת משאר ההוצאות, ולכן אסור לחשב אותה בתוך קבוצה מבודדת.
    """
    expenses = [
        line(1, FIXED, 45_000, category="venue"),
        line(2, PER_ATTENDEE, 320, category="venue", committed_quantity=500),
        line(3, FIXED, 12_000, category="music"),
        line(4, PER_ATTENDEE, 45, category="food"),
        line(5, PER_GUEST, 12, category="guests"),
        line(6, PERCENT, 0, category="logistics", quantity=10),
    ]
    breakdown = finance.cost_breakdown(expenses, attendees=391, invited=551)

    groups: dict[str, int] = {}
    for expense in expenses:
        groups[expense.category] = (
            groups.get(expense.category, 0) + breakdown.lines[expense.id].total_agorot
        )

    assert sum(groups.values()) == breakdown.total_agorot
    # ובפרט: שורת האחוז אינה אפס בקבוצה שלה.
    assert groups["logistics"] > 0


def test_group_total_uses_the_committed_quantity() -> None:
    """קבוצת המקום נספרת לפי ההתחייבות ולא לפי המגיעים — אותו כלל
    שנועל את המנוע, גם בכותרת הקבוצה."""
    expenses = [
        line(1, FIXED, 45_000, category="venue"),
        line(2, PER_ATTENDEE, 320, category="venue", committed_quantity=500),
    ]
    breakdown = finance.cost_breakdown(expenses, attendees=391, invited=551)
    venue = sum(breakdown.lines[e.id].total_agorot for e in expenses)
    assert venue == (45_000 + 500 * 320) * S


# ════════════════════════════════════════════════════════════════════════
#  תשלום: טרם שולם · מקדמה · שולם במלואו
# ════════════════════════════════════════════════════════════════════════
#
# "כמה כבר שילמנו" מוצג בשלושה מקומות (כותרת המסך, כותרת הקבוצה,
# הסיכום). כולם קוראים מ-``finance.paid_total``, ולכן אין דרך שהם יסטו.


def test_unpaid_line_contributes_nothing() -> None:
    e = line(1, FIXED, 12_000)
    assert finance.paid_for_line(e, 12_000 * S) == 0


def test_fully_paid_line_follows_the_line_total() -> None:
    """"שולם במלואו" הוא דגל ולא סכום שמור — ולכן הוא נשאר נכון גם
    כשעלות השורה זזה. שורת מנה ששולמה במלואה ואז קיבלה עוד עשרה
    מגיעים עדיין "שולמה במלואה"; סכום שנשמר ברגע התשלום היה מתיישן."""
    e = line(1, PER_ATTENDEE, 320, is_paid=True)
    assert finance.paid_for_line(e, 391 * 320 * S) == 391 * 320 * S
    assert finance.paid_for_line(e, 500 * 320 * S) == 500 * 320 * S


def test_advance_payment_counts_as_paid() -> None:
    e = line(1, FIXED, 45_000, paid_amount_agorot=15_000 * S)
    assert finance.paid_for_line(e, 45_000 * S) == 15_000 * S


def test_advance_is_capped_at_the_line_total() -> None:
    """מקדמה גבוהה מעלות השורה אינה "שולם יותר מהמחיר" — היא החזר,
    והוא לא שייך לצד ההוצאות. בלי החיתוך הזה "נשאר לשלם" היה יורד
    למספר שלילי בכותרת המסך."""
    e = line(1, FIXED, 10_000, paid_amount_agorot=20_000 * S)
    assert finance.paid_for_line(e, 10_000 * S) == 10_000 * S


def test_paid_total_mixes_all_three_states() -> None:
    expenses = [
        line(1, FIXED, 45_000, is_paid=True),                       # שולם
        line(2, FIXED, 12_000, paid_amount_agorot=5_000 * S),       # מקדמה
        line(3, FIXED, 8_000),                                      # טרם
        line(4, PER_ATTENDEE, 320, committed_quantity=500, paid_amount_agorot=50_000 * S),
    ]
    breakdown = finance.cost_breakdown(expenses, attendees=391, invited=551)
    paid = finance.paid_total(expenses, breakdown.lines)

    assert paid == (45_000 + 5_000 + 0 + 50_000) * S
    # ולעולם לא יותר מהסך.
    assert paid <= breakdown.total_agorot


def test_paid_never_exceeds_the_total() -> None:
    """האינווריאנטה שמגינה על "נשאר לשלם": הוא לא יכול לצאת שלילי."""
    expenses = [
        line(1, FIXED, 1_000, paid_amount_agorot=99_000 * S),
        line(2, FIXED, 2_000, is_paid=True),
    ]
    breakdown = finance.cost_breakdown(expenses, attendees=100, invited=120)
    assert finance.paid_total(expenses, breakdown.lines) == breakdown.total_agorot


def test_full_payment_flag_wins_over_a_stale_advance() -> None:
    """שורה שסומנה "שולם" אחרי שהייתה מקדמה נספרת פעם אחת, לא פעמיים."""
    e = line(1, FIXED, 30_000, is_paid=True, paid_amount_agorot=10_000 * S)
    assert finance.paid_for_line(e, 30_000 * S) == 30_000 * S


# ════════════════════════════════════════════════════════════════════════
#  יומן התשלומים
# ════════════════════════════════════════════════════════════════════════
#
# "נשאר לשלם = עלות השורה − סכום התשלומים" הוא המשפט שהמסך מבטיח.
# הבדיקות כאן נועלות אותו, ובמיוחד את שני הקצוות שבהם הוא נשבר בשקט:
# תשלום יתר, ושורה שעלותה זזה אחרי שכבר שולמה.


def pay(shekels: int, **kw) -> models.ExpensePayment:
    return models.ExpensePayment(amount_agorot=shekels * S, **kw)


def test_payments_sum_is_what_was_paid() -> None:
    e = line(1, FIXED, 12_000)
    e.payments = [pay(3_000, kind="advance"), pay(2_000)]
    assert finance.paid_for_line(e, 12_000 * S) == 5_000 * S


def test_remaining_is_cost_minus_payments() -> None:
    e = line(1, FIXED, 12_000)
    e.payments = [pay(3_000), pay(2_000)]
    total = 12_000 * S
    assert total - finance.paid_for_line(e, total) == 7_000 * S


def test_ledger_wins_over_the_legacy_fields() -> None:
    """שורה שהומרה נושאת גם דגל ישן וגם שורת יומן. אסור שתיספר פעמיים."""
    e = line(1, FIXED, 12_000, is_paid=True, paid_amount_agorot=4_000 * S)
    e.payments = [pay(12_000)]
    assert finance.paid_for_line(e, 12_000 * S) == 12_000 * S


def test_legacy_fields_still_read_before_the_migration_runs() -> None:
    """שרת שעלה על DB שטרם הומר חייב להציג מספר נכון, לא אפס."""
    e = line(1, FIXED, 12_000, is_paid=True)
    assert finance.paid_for_line(e, 12_000 * S) == 12_000 * S

    e2 = line(2, FIXED, 12_000, paid_amount_agorot=4_000 * S)
    assert finance.paid_for_line(e2, 12_000 * S) == 4_000 * S


def test_overpayment_is_capped_so_remaining_never_goes_negative() -> None:
    """המקרה שמופיע בפועל: שולמה מקדמה, ואז המחיר ירד. העודף הוא החזר —
    הוא לא הופך את "נשאר לשלם" למספר שלילי בכותרת המסך."""
    e = line(1, FIXED, 10_000)
    e.payments = [pay(9_000), pay(4_000)]
    total = 10_000 * S
    assert finance.paid_for_line(e, total) == total
    assert total - finance.paid_for_line(e, total) == 0
    # אבל היומן עצמו נשאר נאמן למה שנרשם.
    assert finance.payments_total(e) == 13_000 * S


def test_fully_paid_meal_line_owes_again_when_more_guests_confirm() -> None:
    """ההבדל המהותי בין יומן לדגל.

    שורת מנה ששולמה במלואה ב-391 מגיעים ואז עלתה ל-420 **באמת חייבת עוד
    כסף**. הדגל הישן היה ממשיך לומר "שולם"; היומן אומר את האמת."""
    e = line(1, PER_ATTENDEE, 320)
    e.payments = [pay(391 * 320)]

    at_391 = finance.cost_breakdown([e], attendees=391, invited=500)
    assert finance.paid_for_line(e, at_391.lines[1].total_agorot) == 391 * 320 * S
    assert at_391.lines[1].total_agorot - finance.paid_for_line(e, at_391.lines[1].total_agorot) == 0

    at_420 = finance.cost_breakdown([e], attendees=420, invited=500)
    remaining = at_420.lines[1].total_agorot - finance.paid_for_line(
        e, at_420.lines[1].total_agorot
    )
    assert remaining == 29 * 320 * S


def test_paid_total_across_lines_never_exceeds_the_event_total() -> None:
    expenses = [
        line(1, FIXED, 45_000),
        line(2, FIXED, 12_000),
        line(3, PER_ATTENDEE, 320, committed_quantity=500),
    ]
    expenses[0].payments = [pay(45_000)]
    expenses[1].payments = [pay(99_000)]  # תשלום יתר גס
    expenses[2].payments = []
    breakdown = finance.cost_breakdown(expenses, attendees=391, invited=551)
    assert finance.paid_total(expenses, breakdown.lines) <= breakdown.total_agorot


# ════════════════════════════════════════════════════════════════════════
#  כמה הגיעו בפועל
# ════════════════════════════════════════════════════════════════════════
#
# ההחלטה הנעולה: הנוסחה לא משתנה, רק **הקלט** שלה. הבדיקות כאן נועלות
# את נקודת ההכרעה היחידה (``billing_attendees``) ואת מה שהיא לא עושה.


class _Ev:
    """אירוע מינימלי — ``billing_attendees`` נוגעת בשדה אחד בלבד."""

    def __init__(self, actual=None):
        self.actual_attendance = actual


def guest(seats: int) -> models.Guest:
    g = models.Guest(full_name="בדיקה", rsvp_status="confirmed", confirmed_count=seats)
    return g


def test_before_the_event_the_count_comes_from_rsvp() -> None:
    guests = [guest(2), guest(3)]
    assert finance.billing_attendees(_Ev(), guests) == 5


def test_actual_attendance_replaces_the_rsvp_count() -> None:
    guests = [guest(2), guest(3)]
    assert finance.billing_attendees(_Ev(508), guests) == 508


def test_zero_attendance_is_a_real_answer_not_a_missing_one() -> None:
    """אירוע שבוטל ברגע האחרון הוא מצב אמיתי. ``0`` אינו "טרם הוזן"."""
    guests = [guest(2), guest(3)]
    assert finance.billing_attendees(_Ev(0), guests) == 0


def test_clearing_the_count_returns_to_rsvp() -> None:
    guests = [guest(4)]
    assert finance.billing_attendees(_Ev(None), guests) == 4


def test_the_commitment_formula_is_untouched_by_actual_attendance() -> None:
    """**הבדיקה המרכזית של השינוי הזה.**

    אותה שורה, אותה התחייבות, שני מספרי מגיעים — והתוצאה זהה בדיוק לזו
    שהייתה מתקבלת אילו המספר היה מגיע מאישורי ההגעה. אין כאן מסלול
    חישוב שני; יש קלט אחר לאותה נוסחה.
    """
    e = line(1, PER_ATTENDEE, 320, committed_quantity=500)

    # מתחת להתחייבות — משלמים על ההתחייבות, בשני המקורות.
    assert finance.total_for([e], 391, 551) == 500 * 320 * S
    assert finance.total_for([e], finance.billing_attendees(_Ev(391), []), 551) == 500 * 320 * S

    # מעליה — משלמים על מי שהגיע.
    assert finance.total_for([e], finance.billing_attendees(_Ev(508), []), 551) == 508 * 320 * S


def test_reserve_is_never_part_of_any_total() -> None:
    """רזרבה היא זכות להזמין עוד, לא התחייבות לשלם. אם היא נכנסת לחישוב
    ולו פעם אחת — זוג משלם על מנות שאיש לא אכל."""
    plain = line(1, PER_ATTENDEE, 320, committed_quantity=500)
    with_reserve = line(2, PER_ATTENDEE, 320, committed_quantity=500, reserve_quantity=50)
    assert finance.total_for([plain], 391, 551) == finance.total_for([with_reserve], 391, 551)
    assert finance.total_for([with_reserve], 391, 551) == 500 * 320 * S


# ════════════════════════════════════════════════════════════════════════
#  נותן מתנה שאינו ברשימת המוזמנים
# ════════════════════════════════════════════════════════════════════════
#
# שלושת המצבים של מעטפה, וההבחנה שאסור לטשטש ביניהם:
#
#     guest_id                מוזמן מהרשימה
#     external_name           נותן חיצוני — **מזוהה**, פשוט לא הוזמן
#     שניהם ריקים             טרם זוהתה
#
# מעטפה חיצונית שנספרת כ"לא מזוהה" שולחת את הזוג לחפש שיוך שכבר קיים.


def envelope(amount: int, *, guest_id=None, external_name=None) -> models.GiftEnvelope:
    return models.GiftEnvelope(
        amount_agorot=amount * S, guest_id=guest_id, external_name=external_name
    )


def _classify(envelopes):
    """אותה חלוקה שעושה ``finance_service.gift_income``."""
    external = [e for e in envelopes if not e.guest_id and (e.external_name or "").strip()]
    unknown = [e for e in envelopes if not e.guest_id and not (e.external_name or "").strip()]
    return external, unknown


def test_external_giver_is_not_unidentified() -> None:
    rows = [
        envelope(500, guest_id=7),
        envelope(800, external_name="רונית מהעבודה"),
        envelope(1_000),
    ]
    external, unknown = _classify(rows)
    assert len(external) == 1 and external[0].amount_agorot == 800 * S
    assert len(unknown) == 1 and unknown[0].amount_agorot == 1_000 * S


def test_blank_external_name_is_still_unidentified() -> None:
    """רווחים אינם שם. בלי ``strip`` מעטפה ריקה הייתה נספרת כמזוהה."""
    external, unknown = _classify([envelope(500, external_name="   ")])
    assert not external and len(unknown) == 1


def test_a_guest_link_wins_over_an_external_name() -> None:
    """לשורה יש זהות אחת. מוזמן שכבר ברשימה אינו "חיצוני"."""
    external, unknown = _classify([envelope(500, guest_id=7, external_name="מישהו")])
    assert not external and not unknown


def test_every_envelope_lands_in_exactly_one_bucket() -> None:
    """האינווריאנטה של הדוח: סכום הקבוצות = סכום המעטפות. בלעדיה
    "סה\"כ מתנות" גדול או קטן מסכום השורות שמתחתיו."""
    rows = [
        envelope(500, guest_id=1),
        envelope(700, guest_id=2),
        envelope(800, external_name="שכן"),
        envelope(300, external_name="קולגה"),
        envelope(1_000),
    ]
    external, unknown = _classify(rows)
    linked = [e for e in rows if e.guest_id]
    assert len(external) + len(unknown) + len(linked) == len(rows)
    assert sum(e.amount_agorot for e in external + unknown + linked) == sum(
        e.amount_agorot for e in rows
    )


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for test in tests:
        test()
        print(f"  ✓ {test.__name__}")
    print(f"\n{len(tests)} בדיקות עברו.")
