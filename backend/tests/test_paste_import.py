"""בדיקות למנוע פענוח רשימה מודבקת (`parse_freeform_text` ב-app/importer.py).

הרקע: מפרט מפורט מהבעלים (2026-08-11) שקבע כלל ברזל — "המערכת לא מנחשת
ולא ממציאה מידע שלא מופיע בטקסט". הבדיקות כאן מכסות את כל הדוגמאות
מהמפרט (זיהוי כמות במילים ובמספרים בעברית, "ילד" = אדם נוסף, איסור על
יצירת קשרי משפחה בין שורות).

עדכון (2026-08-13): הכלל רוכך **רק** לגבי כמות חסרה — שורה בלי ביטוי כמות
מקבלת ברירת מחדל 1 ותקינה לייבוא (`guest_count_text` נשאר None, כדי לא
להמציא טקסט שלא נכתב). שם/טלפון/קבוצה עדיין לעולם לא מנוחשים.

הרצה: ``python tests/test_paste_import.py``
(עובד גם בלי pytest מותקן — סקריפט עצמאי עם ``assert``).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.importer import parse_freeform_text, parse_line  # noqa: E402


def _row(text: str, **kwargs):
    result = parse_freeform_text(text, **kwargs)
    assert result["total"] == 1, f"ציפינו לשורה אחת, קיבלנו {result['total']}: {result['rows']}"
    return result["rows"][0]


# ---------------------------------------------------------------------------
# 1) הדוגמאות המדויקות מהמפרט
# ---------------------------------------------------------------------------

def test_couple_example():
    r = _row("יואב כהן 0501234567 זוג")
    assert r["full_name"] == "יואב כהן"
    assert r["phone"] == "0501234567"
    assert r["guest_count_text"] == "זוג"
    assert r["party_size"] == 2


def test_single_child_example():
    r = _row("נועה כהן 0501234567 ילד")
    assert r["full_name"] == "נועה כהן"
    assert r["guest_count_text"] == "ילד"
    assert r["party_size"] == 2  # האורח + הילד


def test_family_two_children_example():
    r = _row("משפחת לוי 0501234567 שני ילדים")
    assert r["full_name"] == "משפחת לוי"
    assert r["guest_count_text"] == "שני ילדים"
    assert r["party_size"] == 3  # האורח הראשי + שני ילדים
    assert r["group_type"] == "close_family"


# ---------------------------------------------------------------------------
# 2) כל צורות הכמות
# ---------------------------------------------------------------------------

def test_single_forms():
    for text, expected in [
        ("דנה לוי 0501234567 יחיד", 1),
        ("דנה לוי 0501234567 אחד", 1),
        ("דנה לוי 0501234567 1", 1),
        ("דנה לוי 0501234567 אחד מגיע", 1),
    ]:
        r = _row(text)
        assert r["party_size"] == expected, f"{text!r} -> {r['party_size']}, ציפינו {expected}"


def test_couple_forms():
    for text, expected in [
        ("דנה לוי 0501234567 זוג", 2),
        ("דנה לוי 0501234567 שניים", 2),
        ("דנה לוי 0501234567 שתי אנשים", 2),
        ("דנה לוי 0501234567 שני אנשים", 2),
        ("דנה לוי 0501234567 2", 2),
        ("דנה לוי 0501234567 שני מבוגרים", 2),
    ]:
        r = _row(text)
        assert r["party_size"] == expected, f"{text!r} -> {r['party_size']}, ציפינו {expected}"


def test_children_forms():
    for text, expected in [
        ("דנה לוי 0501234567 ילד", 2),
        ("דנה לוי 0501234567 ילדה", 2),
        ("דנה לוי 0501234567 ילד אחד", 2),
        ("דנה לוי 0501234567 ילד 1", 2),
        ("דנה לוי 0501234567 שני ילדים", 3),
        ("דנה לוי 0501234567 שתי ילדים", 3),
        ("דנה לוי 0501234567 2 ילדים", 3),
        ("דנה לוי 0501234567 שלושה ילדים", 4),
        ("דנה לוי 0501234567 שלוש ילדים", 4),
        ("דנה לוי 0501234567 3 ילדים", 4),
        ("דנה לוי 0501234567 ארבעה ילדים", 5),
        ("דנה לוי 0501234567 ארבע ילדים", 5),
        ("דנה לוי 0501234567 4 ילדים", 5),
    ]:
        r = _row(text)
        assert r["party_size"] == expected, f"{text!r} -> {r['party_size']}, ציפינו {expected}"


def test_plain_number_words_mean_total_directly():
    # מספר רגיל (או מילת-מספר עצמאית שלא צמודה ל"ילד") = כמות אנשים ישירה,
    # לא "אדם ראשי + N": "5" = 5 אנשים, לא 6.
    for text, expected in [
        ("יוסי מזרחי 0501234567 5", 5),
        ("יוסי מזרחי 0501234567 שלושה", 3),
        ("יוסי מזרחי 0501234567 חמישה", 5),
        ("יוסי מזרחי 0501234567 עשרה", 10),
    ]:
        r = _row(text)
        assert r["party_size"] == expected, f"{text!r} -> {r['party_size']}, ציפינו {expected}"


def test_combined_couple_and_children():
    for text, expected in [
        ("דני ואיה 0501234567 זוג + ילד", 3),
        ("דני ואיה 0501234567 זוג עם ילד", 3),
        ("דני ואיה 0501234567 זוג עם שני ילדים", 4),
    ]:
        r = _row(text)
        assert r["party_size"] == expected, f"{text!r} -> {r['party_size']}, ציפינו {expected}"


# ---------------------------------------------------------------------------
# 3) שני שדות נפרדים: guest_count_text (מה שנכתב) מול party_size (מחושב)
# ---------------------------------------------------------------------------

def test_guest_count_text_preserves_original_wording():
    r = _row("רון אבני 0501234567 שלושה ילדים")
    assert r["guest_count_text"] == "שלושה ילדים"
    assert r["party_size"] == 4


# ---------------------------------------------------------------------------
# 4) זיהוי טלפון — לעולם לא נכנס לתוך השם, מזוהה בכל פורמט
# ---------------------------------------------------------------------------

def test_phone_never_leaks_into_name():
    for text in [
        "יוסי כהן 0501234567",
        "יוסי כהן 050-1234567",
        "יוסי כהן 050 1234567",
        "יוסי כהן +972501234567",
    ]:
        r = _row(text)
        assert r["full_name"] == "יוסי כהן", f"{text!r} -> name={r['full_name']!r}"
        assert r["phone"], f"{text!r}: טלפון לא זוהה"


# ---------------------------------------------------------------------------
# 5) איסור מוחלט על ניחוש קשרים/משפחות בין שורות
# ---------------------------------------------------------------------------

def test_no_automatic_family_linking_by_surname():
    result = parse_freeform_text("יוסי כהן 0501234567 זוג\nדני כהן 0501234568 זוג")
    rows = result["rows"]
    assert len(rows) == 2
    # כל שורה עצמאית לחלוטין: אין שדה שמקשר בין השורות, ואף אחת לא מסומנת
    # כמשפחה רק בגלל שם משפחה זהה (אין "משפחת" בטקסט המקורי).
    for r in rows:
        assert r["group_type"] == "other"
    assert rows[0]["full_name"] != rows[1]["full_name"]


def test_family_group_only_from_explicit_text():
    r = _row("משפחת כהן 0501234567 4")
    assert r["group_type"] == "close_family"
    r2 = _row("כהן ולוי 0501234567 4")  # בלי "משפחת" מפורש
    assert r2["group_type"] == "other"


def test_shared_surname_across_three_guests_stays_fully_independent():
    """מקרה קצה מהבעלים (2026-08-11): 3 מוזמנים בשם משפחה "כהן" (בדיוק
    MIN_CLUSTER של group_suggestions ב-routers/guests.py) + מוזמן רביעי
    בשם אחר, בפורמטים מעורבים (מספר רגיל / ילד / זוג). paste import חייב
    להישאר Parsing גרידא: 4 שורות עצמאיות לחלוטין, בלי group_type משותף,
    בלי שדה שמקשר בין שורות, ובלי שום רמז לקבוצה/משפחה — כי לא נכתב
    "משפחת" בטקסט המקורי אף פעם."""
    text = (
        "יוסי כהן 0501234567 2\n"
        "דני כהן 0507654321 3\n"
        "רועי כהן 0521111111 ילד\n"
        "נועה לוי 0532222222 זוג"
    )
    result = parse_freeform_text(text)
    rows = result["rows"]
    assert len(rows) == 4
    assert result["valid_count"] == 4

    names = [r["full_name"] for r in rows]
    assert names == ["יוסי כהן", "דני כהן", "רועי כהן", "נועה לוי"]

    # כל שורה: group_type = "other" (ברירת המחדל) — לא "close_family",
    # לא "משפחת כהן", ולא שום ערך שמרמז על שיוך. שם משפחה זהה לא משנה כלום.
    for r in rows:
        assert r["group_type"] == "other", (
            f"{r['full_name']!r} קיבל group_type={r['group_type']!r} — "
            "אסור שהפענוח ישייך קבוצה על בסיס שם משפחה"
        )

    # אין שום שדה בפלט שמצביע על מזהה/קשר בין שורות (guest_ids, cluster,
    # surname וכו') — הפלט של כל שורה הוא בדיוק סכימת ה-preview הרגילה.
    expected_keys = {
        "row_number", "full_name", "phone", "side", "group_type",
        "guest_count_text", "party_size", "notes_raw", "seating_notes",
        "valid", "errors", "warnings", "duplicate",
    }
    for r in rows:
        assert set(r.keys()) == expected_keys

    # הכמויות עדיין מחושבות נכון (בדיקת רגרסיה משולבת): 2, 3, אורח+ילד=2, זוג=2.
    assert [r["party_size"] for r in rows] == [2, 3, 2, 2]

    # paste-import לעולם לא ניגש למודל ה-DB (Guest) או לפונקציות clustering —
    # מוודאים סטטית שאין קישור import כזה בכל המודול (לא רק בהרצה הזו).
    import inspect
    from app import importer as importer_module
    source = inspect.getsource(importer_module)
    for forbidden in ("_surname", "GroupSuggestion", "bulk_group", "models.Guest", "cluster"):
        assert forbidden not in source, (
            f"importer.py מכיל אזכור ל-{forbidden!r} — paste import צריך "
            "להישאר Parsing בלבד, בלי כל תלות בלוגיקת קבוצות/DB"
        )


# ---------------------------------------------------------------------------
# 6) כמות שלא נכתבה → ברירת מחדל 1 (החלטת בעלים, 2026-08-13)
# ---------------------------------------------------------------------------
# עד לתאריך הזה השורה נשארה בלי כמות, סומנה "חסרה כמות" ונחסמה לייבוא.
# ההחלטה שונתה: שורה בלי ביטוי כמות מקבלת 1 ותקינה לייבוא. `guest_count_text`
# נשאר None — כדי שהתצוגה תבדיל בין "כתבתי 1" לבין "לא כתבתי ולכן ברירת מחדל".

def test_missing_count_defaults_to_one():
    r = _row("תמר לוי 0589012345")
    assert r["full_name"] == "תמר לוי"
    assert r["phone"] == "0589012345"
    assert r["guest_count_text"] is None  # לא נכתב כלום — לא ממציאים טקסט
    assert r["party_size"] == 1
    assert r["valid"] is True
    assert "חסרה כמות" not in r["warnings"]


def test_missing_count_defaults_to_one_for_family_prefix_too():
    """גם כשיש רמז "משפחת…" — ברירת המחדל היא 1, לא 2. הרמז משפיע רק על
    שיוך הקבוצה, אף פעם לא על הכמות."""
    r = _row("משפחת לוי 0501234567")
    assert r["party_size"] == 1
    assert r["guest_count_text"] is None
    assert r["valid"] is True
    assert r["group_type"] == "close_family"


def test_explicit_quantity_still_wins_over_default():
    """ברירת המחדל חלה **רק** כשלא זוהתה כמות — ביטוי מפורש גובר תמיד."""
    for text, qty, size in [
        ("א ב 0501234567 ילד", "ילד", 2),
        ("א ב 0501234567 זוג", "זוג", 2),
        ("א ב 0501234567 שני ילדים", "שני ילדים", 3),
        ("א ב 0501234567 שלושה ילדים", "שלושה ילדים", 4),
        ("א ב 0501234567 1", "1", 1),
    ]:
        r = _row(text)
        assert r["guest_count_text"] == qty, f"{text!r} -> {r['guest_count_text']!r}"
        assert r["party_size"] == size, f"{text!r} -> {r['party_size']}"


def test_written_one_is_distinguishable_from_defaulted_one():
    """שתי שורות מגיעות ל-party_size=1, אבל רק באחת המשתמש באמת כתב "1".
    ההבחנה נשמרת ב-guest_count_text כדי שהתצוגה המקדימה תוכל להראות אותה."""
    written = _row("א ב 0501234567 1")
    defaulted = _row("ג ד 0501234567")
    assert written["party_size"] == defaulted["party_size"] == 1
    assert written["guest_count_text"] == "1"
    assert defaulted["guest_count_text"] is None


# ---------------------------------------------------------------------------
# 7) בדיקות ל-parse_line — יחידת הפענוח האטומית (מפרט הבעלים, 2026-08-13)
# ---------------------------------------------------------------------------
# שני באגים דווחו: (1) מילות כמות נכנסות לתוך השם, (2) כמות של מוזמן אחד
# משויכת בטעות למוזמן אחר. הבדיקות כאן בודקות ישירות את parse_line (יחידת
# הפענוח לשורה בודדת) כדי שההפרדה תהיה מוכחת ברמת היחידה, לא רק ברמת
# האינטגרציה של parse_freeform_text.

def test_couple_word_not_in_name():
    r = parse_line("יוסי כהן 0501234567 זוג")
    assert r["full_name"] == "יוסי כהן"
    assert "זוג" not in r["full_name"]
    assert r["guest_count_text"] == "זוג"
    assert r["party_size"] == 2


def test_child_word_not_in_name():
    r = parse_line("יוסי כהן 0501234567 ילד")
    assert r["full_name"] == "יוסי כהן"
    assert "ילד" not in r["full_name"]
    assert r["party_size"] == 2


def test_number_word_not_in_name():
    r = parse_line("יוסי כהן 0501234567 שלושה")
    assert r["full_name"] == "יוסי כהן"
    assert "שלושה" not in r["full_name"]
    assert r["party_size"] == 3


def test_two_children_phrase_not_in_name():
    r = parse_line("יוסי כהן 0501234567 שני ילדים")
    assert r["full_name"] == "יוסי כהן"
    assert "ילדים" not in r["full_name"] and "שני" not in r["full_name"]
    assert r["party_size"] == 3


def test_couple_with_two_children_phrase_not_in_name():
    r = parse_line("יוסי כהן 0501234567 זוג עם שני ילדים")
    assert r["full_name"] == "יוסי כהן"
    assert "זוג" not in r["full_name"]
    assert r["guest_count_text"] == "זוג עם שני ילדים"
    assert r["party_size"] == 4


def test_bare_digit_not_in_name():
    r = parse_line("תומר אדרי 0533333333 2")
    assert r["full_name"] == "תומר אדרי"
    assert "2" not in r["full_name"]
    assert r["party_size"] == 2


def test_phone_not_in_name_via_parse_line():
    r = parse_line("יוסי כהן 0501234567 זוג")
    assert "0501234567" not in r["full_name"]
    assert r["phone"] == "0501234567"


def test_parse_line_has_no_cross_line_state():
    """קריאה חוזרת ל-parse_line על שורה בלי כמות, אחרי שורה *עם* כמות,
    לא מקבלת "שאריות" מהקריאה הקודמת — אין state גלובלי/מודול שמצטבר."""
    r1 = parse_line("תומר אדרי 0533333333 2")
    assert r1["party_size"] == 2
    r2 = parse_line("משפחת אדרי 0522222222")
    assert r2["party_size"] is None
    assert r2["guest_count_text"] is None
    # קריאה שלישית שוב עם כמות — מוודאת שאין "נעילה" על המצב הקודם בכיוון ההפוך
    r3 = parse_line("דני לוי 0555555555 זוג")
    assert r3["party_size"] == 2


# ---------------------------------------------------------------------------
# 8) התרחיש המרכזי מהבעלים: "משפחת אדרי" + תומר/רוני/דני, סדרים הפוכים
# ---------------------------------------------------------------------------

_ADRI_TEXT = (
    "משפחת אדרי 0522222222\n"
    "תומר אדרי 0533333333 2\n"
    "רוני אדרי 0544444444 שלושה ילדים\n"
    "דני לוי 0555555555 זוג"
)


def test_central_edge_case_adri_family():
    result = parse_freeform_text(_ADRI_TEXT)
    rows = {r["full_name"]: r for r in result["rows"]}
    assert len(rows) == 4

    family = rows["משפחת אדרי"]
    assert family["guest_count_text"] is None  # לא נכתבה כמות בשורה
    assert family["party_size"] == 1           # ברירת המחדל, לא 2 של תומר
    assert family["valid"] is True
    assert family["group_type"] == "close_family"  # מהטקסט המפורש בלבד

    tomer = rows["תומר אדרי"]
    assert tomer["guest_count_text"] == "2"
    assert tomer["party_size"] == 2
    assert tomer["group_type"] == "other"

    roni = rows["רוני אדרי"]
    assert roni["guest_count_text"] == "שלושה ילדים"
    assert roni["party_size"] == 4
    assert roni["group_type"] == "other"

    dani = rows["דני לוי"]
    assert dani["guest_count_text"] == "זוג"
    assert dani["party_size"] == 2
    assert dani["group_type"] == "other"


def test_quantity_does_not_move_to_previous_line():
    # אם "2" של תומר היה "נופל אחורה" לשורה הקודמת, למשפחת אדרי היה יוצא 2.
    result = parse_freeform_text(_ADRI_TEXT)
    family = next(r for r in result["rows"] if r["full_name"] == "משפחת אדרי")
    assert family["party_size"] != 2
    assert family["party_size"] == 1  # ברירת המחדל שלה עצמה, לא של שורה אחרת
    assert family["guest_count_text"] is None


def test_quantity_does_not_move_to_next_line():
    # הכיוון ההפוך: "משפחת אדרי" (בלי כמות) מיד לפני שורה עם כמות אמיתית —
    # הכמות של השורה הבאה לא "זולגת אחורה" לשורה חסרת-הכמות.
    text = "משפחת אדרי 0522222222\nתומר אדרי 0533333333 2"
    result = parse_freeform_text(text)
    family, tomer = result["rows"]
    assert family["party_size"] == 1  # ברירת מחדל, לא ה-2 של השורה הבאה
    assert family["guest_count_text"] is None
    assert tomer["party_size"] == 2


def test_row_order_does_not_affect_result():
    """מקרה א (משפחת אדרי לפני תומר) מול מקרה ב (תומר לפני משפחת אדרי) —
    התוצאה חייבת להיות זהה: סדר השורות לא משפיע על שיוך הכמות."""
    order_a = "משפחת אדרי 0522222222\nתומר אדרי 0533333333 2"
    order_b = "תומר אדרי 0533333333 2\nמשפחת אדרי 0522222222"

    rows_a = {r["full_name"]: r["party_size"] for r in parse_freeform_text(order_a)["rows"]}
    rows_b = {r["full_name"]: r["party_size"] for r in parse_freeform_text(order_b)["rows"]}

    assert rows_a == rows_b == {"משפחת אדרי": 1, "תומר אדרי": 2}


def test_same_surname_does_not_affect_quantity_assignment():
    # שלושה "אדרי" ברצף, כל אחד עם כמות אחרת — שם משפחה זהה לא גורם לערבוב.
    text = (
        "תומר אדרי 0533333333 2\n"
        "משפחת אדרי 0522222222\n"
        "רוני אדרי 0544444444 שלושה ילדים"
    )
    result = parse_freeform_text(text)
    rows = {r["full_name"]: r["party_size"] for r in result["rows"]}
    assert rows == {
        "תומר אדרי": 2,
        "משפחת אדרי": 1,
        "רוני אדרי": 4,
    }
    # ואף אחד לא קיבל group_type מלבד השורה שכתבה "משפחת" במפורש.
    groups = {r["full_name"]: r["group_type"] for r in result["rows"]}
    assert groups["תומר אדרי"] == "other"
    assert groups["רוני אדרי"] == "other"
    assert groups["משפחת אדרי"] == "close_family"


def test_no_grouping_side_effect_within_paste_import():
    """שוב מוודא (ברמת ה-regression suite הזו) שאין grouping/family-matching
    בתוך paste import: כל השורות מקבלות group_type עצמאי, ואין שום מפתח
    בפלט שמצביע על "קבוצה" שנוצרה בין שורות."""
    result = parse_freeform_text(_ADRI_TEXT)
    for r in result["rows"]:
        assert set(r.keys()) <= {
            "row_number", "full_name", "phone", "side", "group_type",
            "guest_count_text", "party_size", "notes_raw", "seating_notes",
            "valid", "errors", "warnings", "duplicate",
        }


# ---------------------------------------------------------------------------
# תווים בלתי-נראים בהדבקה אמיתית — הבאג שנצפה בפועל אצל המשתמש (2026-08-13)
# ---------------------------------------------------------------------------
# רקע: כל הבדיקות למעלה עברו, אבל במערכת האמיתית מספרים ומילות-כמות עדיין
# "נדבקו" לשם. הסיבה: הדבקה אמיתית מ-WhatsApp / מקלדת עברית בנייד / אקסל
# RTL מזריקה תווי כיווניות בלתי-נראים (RLM/LRM וכו') **דווקא סביב מספרים**.
# הם אינם רווח ואינם סוף-מחרוזת, ולכן שברו את עוגני הסוף של הביטויים
# הרגולריים. הבדיקות כאן משתמשות בתווים האמיתיים כדי שהרגרסיה לא תחזור.

RLM = "‏"   # Right-To-Left Mark
LRM = "‎"   # Left-To-Right Mark
NBSP = " "  # Non-Breaking Space
RLE = "‫"   # Right-To-Left Embedding
PDF_ = "‬"  # Pop Directional Formatting
ZWSP = "​"  # Zero Width Space


def test_trailing_rtl_mark_does_not_push_digit_into_name():
    """"תומר אדרי 0533333333 2‏" — RLM אחרי הספרה. לפני התיקון: הכמות לא
    זוהתה כלל והספרה נפלה לתוך השם ("תומר אדרי 2")."""
    r = parse_line("תומר אדרי 0533333333 2" + RLM)
    assert r["full_name"] == "תומר אדרי", f"השם התלכלך: {r['full_name']!r}"
    assert r["guest_count_text"] == "2"
    assert r["party_size"] == 2


def test_trailing_rtl_mark_does_not_push_number_word_into_name():
    """אותו באג בדיוק, עם מילת-מספר עברית במקום ספרה."""
    r = parse_line("מאיה פרץ 0534567890 שלושה" + RLM)
    assert r["full_name"] == "מאיה פרץ", f"השם התלכלך: {r['full_name']!r}"
    assert r["guest_count_text"] == "שלושה"
    assert r["party_size"] == 3


def test_invisible_marks_in_every_position_are_neutralised():
    """סימני כיווניות בכל מיקום אפשרי בשורה — לפני/אחרי הטלפון, לפני הכמות,
    עוטפים את כל השורה — וגם רווחים חריגים (NBSP). בכולם התוצאה חייבת להיות
    זהה לשורה נקייה, והשם חייב לצאת בלי שאריות בלתי-נראות."""
    cases = [
        "תומר אדרי 0533333333 זוג" + RLM,
        "תומר אדרי " + LRM + "0533333333" + LRM + " זוג",
        "תומר אדרי 0533333333 " + RLM + "זוג",
        "תומר אדרי" + NBSP + "0533333333" + NBSP + "זוג",
        RLE + "תומר אדרי 0533333333 זוג" + PDF_,
        "תומר אדרי 0533333333 זוג" + ZWSP,
    ]
    for line in cases:
        r = parse_line(line)
        assert r["full_name"] == "תומר אדרי", f"{line!r} -> name={r['full_name']!r}"
        assert r["phone"] == "0533333333", f"{line!r} -> phone={r['phone']!r}"
        assert r["guest_count_text"] == "זוג"
        assert r["party_size"] == 2


def test_leading_rtl_mark_still_detects_family_prefix():
    """RLM בתחילת השורה שבר את "^\\s*משפח[הת]" — ולכן "משפחת אדרי" איבדה את
    תיוג הקבוצה שנכתב במפורש בטקסט."""
    r = parse_line(RLM + "משפחת אדרי 0522222222")
    assert r["full_name"] == "משפחת אדרי"
    assert r["group_type"] == "close_family"
    # `parse_line` מדווחת מה **נמצא** בשורה — None = לא נמצא ביטוי כמות.
    # ברירת המחדל (1) מוחלת שכבה מעל, ב-`parse_freeform_text`.
    assert r["party_size"] is None


def test_name_never_keeps_invisible_residue():
    """גם כשהפענוח 'הצליח', שאריות בלתי-נראות נשארו בתוך השם ונשמרו למסד
    הנתונים. השם חייב לצאת נקי מכל תו מקטגוריית Cf."""
    import unicodedata
    r = parse_line("רוני אדרי 0544444444 שלושה ילדים" + RLM)
    assert r["full_name"] == "רוני אדרי"
    assert not [c for c in r["full_name"] if unicodedata.category(c) == "Cf"]


# ---------------------------------------------------------------------------
# שם-עצם מונה אחרי מילת-מספר ("שלושה אנשים")
# ---------------------------------------------------------------------------

def test_counted_noun_with_hebrew_number_word_leaves_clean_name():
    """באג שהוסתר ע"י בדיקה חלשה: `test_couple_forms` בדק רק את party_size
    ולכן לא גילה ש"שני אנשים" השאיר את המילה "אנשים" בתוך השם. כאן נבדק
    **גם השם וגם הכמות** לכל צורות "מספר + שם-עצם מונה"."""
    for text, name, qty, size in [
        ("דן לוי 0501234567 שלושה אנשים", "דן לוי", "שלושה אנשים", 3),
        ("רן כהן 0501234567 ארבעה אנשים", "רן כהן", "ארבעה אנשים", 4),
        ("דנה לוי 0501234567 שני אנשים", "דנה לוי", "שני אנשים", 2),
        ("דנה לוי 0501234567 שתי אנשים", "דנה לוי", "שתי אנשים", 2),
        ("עוז כהן 0501234567 שני מוזמנים", "עוז כהן", "שני מוזמנים", 2),
        ("אבי כהן 0501234567 5 אנשים", "אבי כהן", "5 אנשים", 5),
        ("גיל לוי 0501234567 4 נפשות", "גיל לוי", "4 נפשות", 4),
    ]:
        r = parse_line(text)
        assert r["full_name"] == name, f"{text!r} -> name={r['full_name']!r}"
        assert r["guest_count_text"] == qty, f"{text!r} -> qty={r['guest_count_text']!r}"
        assert r["party_size"] == size, f"{text!r} -> size={r['party_size']}"


# ---------------------------------------------------------------------------
# סעיף 11 במפרט: שורה ללא טלפון
# ---------------------------------------------------------------------------

def test_line_without_phone_still_splits_name_and_quantity():
    """שורה בלי טלפון חייבת עדיין להתפצל לשם + כמות — אסור שכל השורה תהפוך
    לשם, והטלפון פשוט מסומן כחסר."""
    for text, name, qty, size in [
        ("יוסי כהן זוג", "יוסי כהן", "זוג", 2),
        ("דנה לוי שני ילדים", "דנה לוי", "שני ילדים", 3),
        ("אבי מזרחי 3", "אבי מזרחי", "3", 3),
    ]:
        r = parse_line(text)
        assert r["full_name"] == name, f"{text!r} -> name={r['full_name']!r}"
        assert r["guest_count_text"] == qty
        assert r["party_size"] == size
        assert r["phone"] == ""
    row = _row("יוסי כהן זוג")
    assert "חסר טלפון" in row["warnings"]


# ---------------------------------------------------------------------------
# סעיף 3 במפרט: כל קידומות הסלולר + כל פורמטי הכתיבה
# ---------------------------------------------------------------------------

def test_all_mobile_prefixes_and_formats_are_extracted():
    for prefix in ("050", "052", "053", "054", "055", "056", "057", "058", "059"):
        r = parse_line(f"יוסי כהן {prefix}1234567 זוג")
        assert r["full_name"] == "יוסי כהן"
        assert r["phone"] == f"{prefix}1234567"
    for text in (
        "יוסי כהן 050-1234567 זוג",
        "יוסי כהן 050 1234567 זוג",
        "יוסי כהן +972501234567 זוג",
        "יוסי כהן +972 50 1234567 זוג",
    ):
        r = parse_line(text)
        assert r["full_name"] == "יוסי כהן", f"{text!r} -> {r['full_name']!r}"
        assert r["phone"] == "0501234567", f"{text!r} -> {r['phone']!r}"
        assert r["guest_count_text"] == "זוג"


def test_couple_with_three_children_combo():
    r = parse_line("אורן כהן 0545678901 זוג עם שלושה ילדים")
    assert r["full_name"] == "אורן כהן"
    assert r["guest_count_text"] == "זוג עם שלושה ילדים"
    assert r["party_size"] == 5  # 2 מבוגרים + 3 ילדים


def test_full_spec_list_end_to_end():
    """הרשימה המלאה מסעיף 16 במפרט — כל 10 השורות, כולל השם, הטלפון,
    טקסט הכמות והסכום המחושב."""
    text = (
        "משפחת אדרי 0522222222\n"
        "תומר אדרי 0533333333 2\n"
        "רוני אדרי 0544444444 שלושה ילדים\n"
        "דני לוי 0555555555 זוג\n"
        "יוסי כהן 0501234567 ילד\n"
        "נועה לוי 0512345678 שני ילדים\n"
        "איתי פרץ 0523456789 5\n"
        "מאיה פרץ 0534567890 שלושה\n"
        "אורן כהן 0545678901 זוג עם ילד\n"
        "קרן לוי 0556789012"
    )
    expected = [
        ("משפחת אדרי", "0522222222", None, 1),
        ("תומר אדרי", "0533333333", "2", 2),
        ("רוני אדרי", "0544444444", "שלושה ילדים", 4),
        ("דני לוי", "0555555555", "זוג", 2),
        ("יוסי כהן", "0501234567", "ילד", 2),
        ("נועה לוי", "0512345678", "שני ילדים", 3),
        ("איתי פרץ", "0523456789", "5", 5),
        ("מאיה פרץ", "0534567890", "שלושה", 3),
        ("אורן כהן", "0545678901", "זוג עם ילד", 3),
        ("קרן לוי", "0556789012", None, 1),
    ]
    rows = parse_freeform_text(text)["rows"]
    assert len(rows) == len(expected)
    for r, (name, phone, qty, size) in zip(rows, expected):
        assert r["full_name"] == name, f"{r['row_number']}: name={r['full_name']!r}"
        assert r["phone"] == phone, f"{r['row_number']}: phone={r['phone']!r}"
        assert r["guest_count_text"] == qty, f"{r['row_number']}: qty={r['guest_count_text']!r}"
        assert r["party_size"] == size, f"{r['row_number']}: size={r['party_size']}"


def test_full_spec_list_survives_realistic_rtl_marks():
    """אותה רשימה בדיוק, אבל כפי שהיא באמת מגיעה מהדבקה בעברית: כל שורה
    שמסתיימת במספר עטופה בסימני כיווניות. זו הבדיקה שמדמה את מה שהמשתמש
    חווה בפועל."""
    lines = [
        "משפחת אדרי 0522222222",
        "תומר אדרי 0533333333 " + LRM + "2" + RLM,
        "רוני אדרי 0544444444 שלושה ילדים" + RLM,
        "דני לוי 0555555555 זוג" + RLM,
        "יוסי כהן 0501234567 ילד",
        "נועה לוי 0512345678 שני ילדים" + RLM,
        "איתי פרץ 0523456789 " + LRM + "5" + RLM,
        "מאיה פרץ 0534567890 שלושה" + RLM,
        "אורן כהן 0545678901 זוג עם ילד",
        "קרן לוי 0556789012" + RLM,
    ]
    expected_sizes = [1, 2, 4, 2, 2, 3, 5, 3, 3, 1]
    expected_names = [
        "משפחת אדרי", "תומר אדרי", "רוני אדרי", "דני לוי", "יוסי כהן",
        "נועה לוי", "איתי פרץ", "מאיה פרץ", "אורן כהן", "קרן לוי",
    ]
    rows = parse_freeform_text("\n".join(lines))["rows"]
    for r, name, size in zip(rows, expected_names, expected_sizes):
        assert r["full_name"] == name, f"{r['row_number']}: name={r['full_name']!r}"
        assert r["party_size"] == size, f"{r['row_number']}: size={r['party_size']}"


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for fn in tests:
        fn()
        print(f"OK  {fn.__name__}")
    print(f"\n{len(tests)} tests passed.")
