"""בודקת את ``messaging.default_template_for(event_type)`` (סבב 3ט, קומיט 1).

הפונקציה עצמה עדיין לא נקראת מאף מקום — לכן הבדיקה כאן היא סטטית בלבד:
מוודאת שהחוזה של הפונקציה מתקיים לכל 8 סוגי האירוע, ושחתונה שומרת על
זהות מוחלטת (identity) לקבוע ``DEFAULT_TEMPLATE`` הקיים.

הרצה: ``python tests/test_default_template.py`` (עצמאי, בלי pytest).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import messaging  # noqa: E402
from app.message_library import _LIBRARY_BY_TYPE  # noqa: E402


ALL_EVENT_TYPES = list(_LIBRARY_BY_TYPE.keys())
# None ו-"" נופלים במפורש ל-DEFAULT_TEMPLATE (התנהגות היסטורית — "לא יודעים
# מה הסוג" → חתונה, כי זו התנהגות הפרודקשן היום).
IDENTITY_FALLBACK_INPUTS = [None, ""]
# סוג שלא מוכר → נופל ל-GENERIC_LIBRARY דרך ``entries_for`` (התכנון של
# message_library עצמו). זו התנהגות בטוחה יותר מהחתונה, כי לפחות הטקסט גנרי.


def test_wedding_is_identity():
    """חתונה חייבת להחזיר את אותו אובייקט מחרוזת של DEFAULT_TEMPLATE.

    זהות אובייקט (is) חזקה יותר משוויון (==), ומוודאת שלא נוצר עותק —
    כל שינוי עתידי ב-DEFAULT_TEMPLATE ישקף עצמו אוטומטית כאן.
    """
    got = messaging.default_template_for("wedding")
    assert got is messaging.DEFAULT_TEMPLATE, (
        "wedding חייב להחזיר את הקבוע DEFAULT_TEMPLATE (זהות אובייקט), "
        f"קיבלתי מחרוזת שונה באורך {len(got)}"
    )
    print("✓ wedding → identity ל-DEFAULT_TEMPLATE")


def test_all_event_types_return_non_empty_string():
    """כל 8 סוגי האירוע חייבים להחזיר תבנית לא-ריקה."""
    for etype in ALL_EVENT_TYPES:
        got = messaging.default_template_for(etype)
        assert isinstance(got, str), f"{etype}: לא מחרוזת (קיבלתי {type(got).__name__})"
        assert got, f"{etype}: הוחזרה מחרוזת ריקה"
    print(f"✓ כל {len(ALL_EVENT_TYPES)} סוגי האירוע מחזירים מחרוזת לא-ריקה")


def test_none_and_empty_fall_to_default_template():
    """None/מחרוזת ריקה → fallback מפורש ל-DEFAULT_TEMPLATE (התנהגות היסטורית)."""
    for inp in IDENTITY_FALLBACK_INPUTS:
        got = messaging.default_template_for(inp)
        assert got is messaging.DEFAULT_TEMPLATE, (
            f"קלט {inp!r} היה אמור ליפול ל-DEFAULT_TEMPLATE אבל קיבלתי מחרוזת שונה"
        )
    print(f"✓ {len(IDENTITY_FALLBACK_INPUTS)} ערכי null/empty נופלים ל-DEFAULT_TEMPLATE")


def test_unknown_type_falls_to_generic_library():
    """סוג לא מוכר → תבנית מ-GENERIC_LIBRARY (fallback המובנה של message_library)."""
    from app.message_library import GENERIC_LIBRARY

    generic_bodies = {e["body"] for e in GENERIC_LIBRARY if e.get("stage") == "invitation"}
    for inp in ("unknown_type", "not_a_real_type"):
        got = messaging.default_template_for(inp)
        assert got in generic_bodies, (
            f"קלט {inp!r} היה אמור ליפול לתבנית מ-GENERIC_LIBRARY, "
            f"קיבלתי מחרוזת שלא מופיעה בו"
        )
    print("✓ סוגים לא-מוכרים נופלים ל-GENERIC_LIBRARY (fallback של message_library)")


def test_non_wedding_types_come_from_library():
    """לסוגים לא-חתונתיים — התבנית חייבת להיות אחת מ-entries_for(etype).

    מוודא שלא מוחזרת מחרוזת שהומצאה במקום, וגם שהיא באמת stage='invitation'.
    """
    from app.message_library import entries_for

    for etype in ALL_EVENT_TYPES:
        if etype == "wedding":
            continue  # נבדק ב-test_wedding_is_identity
        got = messaging.default_template_for(etype)
        invitations = [e for e in entries_for(etype) if e.get("stage") == "invitation"]
        bodies = {e["body"] for e in invitations}
        assert got in bodies, (
            f"{etype}: התבנית שהוחזרה אינה חלק מרשימת ההזמנות ב-message_library "
            f"({len(invitations)} מועמדות)"
        )
    print(f"✓ {len(ALL_EVENT_TYPES) - 1} סוגים לא-חתונתיים — התבניות מגיעות מ-library")


def test_style_priority_order():
    """סדר העדיפות formal > elegant > family חייב להישמר.

    לכל סוג לא-חתונתי, מוודא שאם יש formal — הוא נבחר; אחרת elegant; אחרת
    family; אחרת הראשונה הזמינה. לא מסתמכים על סדר הופעה במערך.
    """
    from app.message_library import entries_for

    for etype in ALL_EVENT_TYPES:
        if etype == "wedding":
            continue
        got = messaging.default_template_for(etype)
        invitations = [e for e in entries_for(etype) if e.get("stage") == "invitation"]
        chosen_entry = next(e for e in invitations if e["body"] == got)
        chosen_style = chosen_entry.get("style")

        # מזהה את הסגנון הצפוי לפי סדר העדיפות + הזמינות בפועל בספרייה
        available_styles = {e.get("style") for e in invitations}
        expected_style = None
        for prio in ("formal", "elegant", "family"):
            if prio in available_styles:
                expected_style = prio
                break
        if expected_style is None:
            # אין formal/elegant/family — צפוי לקבל את הראשונה בפועל
            expected_body = invitations[0]["body"]
            assert got == expected_body, (
                f"{etype}: אין formal/elegant/family, ציפינו לראשונה אבל קיבלנו "
                f"סגנון '{chosen_style}'"
            )
        else:
            assert chosen_style == expected_style, (
                f"{etype}: סגנון זמין '{expected_style}' לא נבחר; במקום זה '{chosen_style}'"
            )
    print("✓ סדר עדיפות formal > elegant > family > first-available נשמר בכל הסוגים")


def test_wedding_is_not_affected_by_library_changes():
    """מוודא שגם אם library של חתונה משתנה, wedding עדיין מחזיר DEFAULT_TEMPLATE."""
    got = messaging.default_template_for("wedding")
    assert got == messaging.DEFAULT_TEMPLATE
    # אם היינו משתמשים ב-entries_for('wedding') לחתונה, היינו מקבלים תבנית של library,
    # שאורכה שונה מ-DEFAULT_TEMPLATE (188 מול 122). זה מאמת שהמסלול השני לא נגע בחתונה.
    assert len(got) == len(messaging.DEFAULT_TEMPLATE)
    print("✓ wedding לא מושפע מ-library — נשאר בקבוע")


if __name__ == "__main__":
    test_wedding_is_identity()
    test_all_event_types_return_non_empty_string()
    test_none_and_empty_fall_to_default_template()
    test_unknown_type_falls_to_generic_library()
    test_non_wedding_types_come_from_library()
    test_style_priority_order()
    test_wedding_is_not_affected_by_library_changes()
    print()
    print("=== כל הבדיקות עברו — קומיט 1 של 3ט תקין ===")
