"""בדיקות למנוע פענוח רשימה מודבקת (`parse_freeform_text` ב-app/importer.py).

הרקע: מפרט מפורט מהבעלים (2026-08-11) שקבע כלל ברזל — "המערכת לא מנחשת
ולא ממציאה מידע שלא מופיע בטקסט". הבדיקות כאן מכסות את כל הדוגמאות
מהמפרט (זיהוי כמות במילים ובמספרים בעברית, "ילד" = אדם נוסף, איסור על
יצירת קשרי משפחה בין שורות, איסור על ניחוש כמות שלא נכתבה) ואת המקרה
של ContactsImportDialog (`assume_single_if_no_count=True`), שמשתמש באותו
מנוע פענוח בלי לשבור אותו.

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
# 6) אין ניחוש כמות שלא נכתבה — הכלל המרכזי במפרט
# ---------------------------------------------------------------------------

def test_missing_count_is_not_guessed_as_single():
    r = _row("יואב כהן 0501234567")
    assert r["guest_count_text"] is None
    assert r["party_size"] == 0  # sentinel: "טרם זוהתה כמות", לא כמות אמיתית
    assert r["valid"] is False
    assert "חסרה כמות" in r["warnings"]


def test_missing_count_not_guessed_as_family_default_either():
    # "משפחת לוי" בלי כמות מפורשת — לפני התיקון זה היה מקבל בברירת מחדל 2.
    # עכשיו: לא מנחשים גם כשיש רמז משפחה, בדיוק כמו שהמפרט דורש.
    r = _row("משפחת לוי 0501234567")
    assert r["party_size"] == 0
    assert r["valid"] is False
    assert "חסרה כמות" in r["warnings"]


def test_assume_single_if_no_count_flag_for_contacts_flow():
    # הדגל הזה קיים רק כדי לא לשבור את ContactsImportDialog, ששולח שורות
    # "שם טלפון" בלי אפשרות לכמות מלכתחילה — שם 1 היא עובדה ידועה, לא ניחוש.
    r = _row("יואב כהן 0501234567", assume_single_if_no_count=True)
    assert r["party_size"] == 1
    assert r["valid"] is True
    assert "חסרה כמות" not in r["warnings"]


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
    assert family["guest_count_text"] is None
    assert family["party_size"] == 0  # sentinel ל"טרם זוהתה"
    assert family["valid"] is False
    assert "חסרה כמות" in family["warnings"]
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
    assert family["party_size"] == 0


def test_quantity_does_not_move_to_next_line():
    # הכיוון ההפוך: "משפחת אדרי" (בלי כמות) מיד לפני שורה עם כמות אמיתית —
    # הכמות של השורה הבאה לא "זולגת אחורה" לשורה חסרת-הכמות.
    text = "משפחת אדרי 0522222222\nתומר אדרי 0533333333 2"
    result = parse_freeform_text(text)
    family, tomer = result["rows"]
    assert family["party_size"] == 0
    assert tomer["party_size"] == 2


def test_row_order_does_not_affect_result():
    """מקרה א (משפחת אדרי לפני תומר) מול מקרה ב (תומר לפני משפחת אדרי) —
    התוצאה חייבת להיות זהה: סדר השורות לא משפיע על שיוך הכמות."""
    order_a = "משפחת אדרי 0522222222\nתומר אדרי 0533333333 2"
    order_b = "תומר אדרי 0533333333 2\nמשפחת אדרי 0522222222"

    rows_a = {r["full_name"]: r["party_size"] for r in parse_freeform_text(order_a)["rows"]}
    rows_b = {r["full_name"]: r["party_size"] for r in parse_freeform_text(order_b)["rows"]}

    assert rows_a == rows_b == {"משפחת אדרי": 0, "תומר אדרי": 2}


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
        "משפחת אדרי": 0,
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


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for fn in tests:
        fn()
        print(f"OK  {fn.__name__}")
    print(f"\n{len(tests)} tests passed.")
