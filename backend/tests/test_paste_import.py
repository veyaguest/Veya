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

from app.importer import parse_freeform_text  # noqa: E402


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


if __name__ == "__main__":
    tests = [obj for name, obj in list(globals().items()) if name.startswith("test_")]
    for fn in tests:
        fn()
        print(f"OK  {fn.__name__}")
    print(f"\n{len(tests)} tests passed.")
