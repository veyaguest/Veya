"""בודקת את ``messaging.default_template_for(event_type)``.

החוזה: כל שמונת סוגי האירוע — חתונה בכללם — מקבלים נוסח הזמנה שנכתב
להם במפורש ב-``DEFAULT_INVITATION_BY_TYPE``, ולא נוסח שנבחר בהיוריסטיקה
מהספרייה. שאר שלבי המסלול (תזכורות/תודה/יום האירוע) כן ממשיכים להיבחר
מהספרייה, לפי קטגוריה ואז סגנון.

הרצה: ``python tests/test_default_template.py`` (עצמאי, בלי pytest).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import messaging  # noqa: E402
from app.message_library import _LIBRARY_BY_TYPE  # noqa: E402


ALL_EVENT_TYPES = list(_LIBRARY_BY_TYPE.keys())
# None ו-"" → חתונה (התנהגות היסטורית: "לא יודעים מה הסוג" = חתונה).
# סוג *לא-מוכר* לעומת זאת נופל לנוסח הנייטרלי של "אחר".
IDENTITY_FALLBACK_INPUTS = [None, ""]


def test_every_type_returns_its_explicit_default():
    """כל סוג — כולל חתונה — מחזיר את הנוסח שנכתב לו במפורש.

    עד סבב "ברירות המחדל" חתונה החזירה את הקבוע ההיסטורי
    ``DEFAULT_TEMPLATE`` כדי לא לשנות התנהגות. היום כל שמונת הסוגים,
    חתונה בכללם, מקבלים נוסח מפורש מ-``DEFAULT_INVITATION_BY_TYPE`` —
    זו ההודעה הראשונה שכל משתמש חדש רואה, ולכן היא לא נבחרת בהיוריסטיקה.

    זהות אובייקט (is) חזקה יותר משוויון, ומוודאת שלא נוצר עותק בדרך.
    """
    from app.message_library import DEFAULT_INVITATION_BY_TYPE

    for etype in ALL_EVENT_TYPES:
        got = messaging.default_template_for(etype)
        want = DEFAULT_INVITATION_BY_TYPE[etype]
        assert got is want, (
            f"{etype}: חייב להחזיר את הנוסח המפורש מ-DEFAULT_INVITATION_BY_TYPE "
            f"(זהות אובייקט), קיבלתי מחרוזת באורך {len(got)}"
        )
    print(f"✓ כל {len(ALL_EVENT_TYPES)} הסוגים → identity לנוסח המפורש שלהם")


def test_all_event_types_return_non_empty_string():
    """כל 8 סוגי האירוע חייבים להחזיר תבנית לא-ריקה."""
    for etype in ALL_EVENT_TYPES:
        got = messaging.default_template_for(etype)
        assert isinstance(got, str), f"{etype}: לא מחרוזת (קיבלתי {type(got).__name__})"
        assert got, f"{etype}: הוחזרה מחרוזת ריקה"
    print(f"✓ כל {len(ALL_EVENT_TYPES)} סוגי האירוע מחזירים מחרוזת לא-ריקה")


def test_none_and_empty_fall_to_wedding():
    """None/מחרוזת ריקה → נוסח החתונה (התנהגות היסטורית: "לא יודעים" = חתונה)."""
    from app.message_library import DEFAULT_INVITATION_BY_TYPE

    for inp in IDENTITY_FALLBACK_INPUTS:
        got = messaging.default_template_for(inp)
        assert got is DEFAULT_INVITATION_BY_TYPE["wedding"], (
            f"קלט {inp!r} היה אמור ליפול לנוסח החתונה אבל קיבלתי מחרוזת שונה"
        )
    print(f"✓ {len(IDENTITY_FALLBACK_INPUTS)} ערכי null/empty נופלים לנוסח החתונה")


def test_unknown_type_falls_to_neutral_default():
    """סוג לא מוכר → הנוסח של "אחר", הנייטרלי ביותר.

    לא לנוסח החתונה: סוג שלא הוגדר ב-``EventType`` הוא באג או ערך עתידי,
    ועדיף שיקבל הזמנה שלא מניחה כלום על אופי האירוע.
    """
    from app.message_library import DEFAULT_INVITATION_BY_TYPE

    for inp in ("unknown_type", "not_a_real_type"):
        got = messaging.default_template_for(inp)
        assert got is DEFAULT_INVITATION_BY_TYPE["other"], (
            f"קלט {inp!r} היה אמור ליפול לנוסח הנייטרלי של 'אחר'"
        )
    print("✓ סוגים לא-מוכרים נופלים לנוסח הנייטרלי של 'אחר'")


def test_other_stages_still_come_from_library():
    """שלבים שאינם ``invitation`` ממשיכים להיבחר מהספרייה של הסוג.

    שלב ההזמנה עבר למפה מפורשת (``DEFAULT_INVITATION_BY_TYPE``), אבל
    התזכורות, התודה ויום האירוע עדיין נבחרים מהספרייה — וחשוב שהבחירה
    תמשיך לכבד את הקטגוריה והסגנון ולא תיפול לתבנית אקראית.
    """
    from app.message_library import default_body_for, entries_for

    checked = 0
    for etype in ALL_EVENT_TYPES:
        if etype == "wedding":
            continue  # לחתונה שאר השלבים מגיעים מ-VeyaTemplate הגלובלי
        for stage in ("first_reminder", "second_reminder", "thank_you", "before_event"):
            got = default_body_for(etype, stage)
            if got is None:
                continue
            bodies = {e["body"] for e in entries_for(etype) if e.get("stage") == stage}
            assert got in bodies, f"{etype}/{stage}: הנוסח אינו מהספרייה של הסוג"
            checked += 1
    print(f"✓ {checked} שלבים לא-הזמנתיים — הנוסח מגיע מהספרייה של הסוג")


def test_stage_priority_respects_category_then_style():
    """בשלבים שנבחרים מהספרייה — קודם הקטגוריה של השלב, ואז הסגנון."""
    from app.message_library import (
        DEFAULT_STYLE_PRIORITY, STAGE_PREFERRED_CATEGORY, default_body_for, entries_for,
    )

    for etype in ALL_EVENT_TYPES:
        if etype == "wedding":
            continue
        for stage, want_cat in STAGE_PREFERRED_CATEGORY.items():
            if stage == "invitation":
                continue
            got = default_body_for(etype, stage)
            if got is None:
                continue
            entry = next(e for e in entries_for(etype)
                         if e["body"] == got and e["stage"] == stage)
            in_stage = [e for e in entries_for(etype) if e["stage"] == stage]
            cats = {e["category"] for e in in_stage}
            if want_cat in cats:
                assert entry["category"] == want_cat, (
                    f"{etype}/{stage}: קטגוריה '{entry['category']}' במקום '{want_cat}'")
            candidates = [e for e in in_stage if e["category"] == entry["category"]]
            avail = {e["style"] for e in candidates}
            for prio in DEFAULT_STYLE_PRIORITY:
                if prio in avail:
                    assert entry["style"] == prio, (
                        f"{etype}/{stage}: סגנון '{prio}' זמין אך נבחר '{entry['style']}'")
                    break
    print("✓ קטגוריית השלב קודמת, והסגנון נבחר בתוכה לפי סדר העדיפות")


def test_explicit_defaults_are_independent_of_the_library():
    """נוסחי ההזמנה המפורשים אינם נגזרים מהספרייה — שינוי שם לא ישנה אותם."""
    from app.message_library import DEFAULT_INVITATION_BY_TYPE, entries_for

    for etype in ALL_EVENT_TYPES:
        got = messaging.default_template_for(etype)
        assert got is DEFAULT_INVITATION_BY_TYPE[etype]
        library_bodies = {e["body"] for e in entries_for(etype)}
        assert got not in library_bodies, (
            f"{etype}: נוסח ההזמנה זהה לתבנית בספרייה — הוא אמור להיות עצמאי")
    print("✓ נוסחי ההזמנה המפורשים עצמאיים מהספרייה")


if __name__ == "__main__":
    test_every_type_returns_its_explicit_default()
    test_all_event_types_return_non_empty_string()
    test_none_and_empty_fall_to_wedding()
    test_unknown_type_falls_to_neutral_default()
    test_other_stages_still_come_from_library()
    test_stage_priority_respects_category_then_style()
    test_explicit_defaults_are_independent_of_the_library()
    print()
    print("=== כל בדיקות נוסחי ברירת המחדל עברו ===")
