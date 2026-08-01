"""בודקת את המעבר של הצרכנים ב-``routers/messaging.py`` מ-``render_template``
ל-``render_automation_template`` (סבב 3ט, קומיט 2).

מטרות הבדיקה:
1. **חתונה = זהות בייטים** — אותם קלטים חייבים להפיק אותה מחרוזת פלט
   דרך שני הצינורות. אם זהות זו נשברת, חתונות קיימות ב-message_template=NULL
   יראו טקסט שונה — הפרה של דרישה #2 של הבעלים.
2. **בר מצווה — {{celebration}} מתוקן** — הצינור החדש מעביר ``event_type``
   אמיתי, ולכן ``{{celebration}}`` הופך ל"אירוע בר המצווה" במקום "החתונה".
3. **אין טוקנים שלא הוחלפו** — בפלט הסופי אין ``{...}`` או ``[...]`` שנשארו.
4. **תבניות שמורות בסינטקס ישן** ({name}, {event_name}, {{celebration}})
   ממשיכות לרנדר תקין דרך ``render_automation_template`` (backward-compat).

הרצה: ``python tests/test_render_switch.py``
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import messaging  # noqa: E402


# ------- פרמטרים משותפים לכל הבדיקות (הקלטים "מלאים" יחסית) -------
COMMON_KWARGS = dict(
    guest_name="דני כהן",
    groom="יונתן",
    bride="נועה",
    venue="אולמי הגן",
    link="https://veya.co.il/confirm/abc",
    date="12.9.2026",
)


def _no_leftover_tokens(text: str) -> bool:
    """מחזירה True אם אין ``{...}`` או ``[...]`` בפלט (חוץ מסימני קריאה)."""
    # לא תופס אמוג'י או תווים סטנדרטיים — רק סוגריים סביב טקסט
    curly = re.search(r"\{[^{}]*\}", text)
    bracket = re.search(r"\[[^\[\]]*\]", text)
    return curly is None and bracket is None


def test_wedding_default_template_identity():
    """חתונה עם DEFAULT_TEMPLATE: זהות בייטים בין הצינור הישן לחדש."""
    old = messaging.render_template(
        messaging.DEFAULT_TEMPLATE, event_type="wedding", **COMMON_KWARGS
    )
    new = messaging.render_automation_template(
        messaging.DEFAULT_TEMPLATE, event_type="wedding", **COMMON_KWARGS
    )
    assert old == new, (
        f"חתונה — פלט חייב להיות זהה בין הצינורות\n"
        f"ישן ({len(old)} chars): {old!r}\n"
        f"חדש ({len(new)} chars): {new!r}"
    )
    assert _no_leftover_tokens(new), f"נשארו טוקנים לא-מוחלפים: {new!r}"
    print(f"✓ חתונה + DEFAULT_TEMPLATE: זהות בייטים ({len(new)} chars)")


def test_wedding_default_template_empty_guest_name_identity():
    """חתונה + guest_name ריק: זהות בייטים בין הצינורות (edge case חשוב)."""
    kwargs = {**COMMON_KWARGS, "guest_name": ""}
    old = messaging.render_template(messaging.DEFAULT_TEMPLATE, event_type="wedding", **kwargs)
    new = messaging.render_automation_template(
        messaging.DEFAULT_TEMPLATE, event_type="wedding", **kwargs
    )
    assert old == new, (
        f"חתונה + שם ריק — פלט חייב להיות זהה\nישן: {old!r}\nחדש: {new!r}"
    )
    print(f"✓ חתונה + guest_name='': זהות בייטים ({len(new)} chars)")


def test_wedding_custom_saved_old_syntax_template_identity():
    """תבנית מותאמת בסינטקס ישן (שמורה על-ידי משתמש) — זהות בייטים."""
    custom = (
        "היי {name}!\n"
        "{event_name} מזמינים אתכם ל{{celebration}}{venue} בתאריך {date}.\n"
        "לאישור: {personal_link}"
    )
    old = messaging.render_template(custom, event_type="wedding", **COMMON_KWARGS)
    new = messaging.render_automation_template(custom, event_type="wedding", **COMMON_KWARGS)
    assert old == new, (
        f"תבנית שמורה ישנה — פלט חייב להיות זהה\nישן: {old!r}\nחדש: {new!r}"
    )
    assert _no_leftover_tokens(new)
    print(f"✓ תבנית שמורה בסינטקס ישן: זהות בייטים ({len(new)} chars)")


def test_wedding_default_template_no_venue_identity():
    """חתונה בלי venue (לא מגיעים ל-`" באולם"`) — זהות בייטים."""
    kwargs = {**COMMON_KWARGS, "venue": ""}
    old = messaging.render_template(messaging.DEFAULT_TEMPLATE, event_type="wedding", **kwargs)
    new = messaging.render_automation_template(
        messaging.DEFAULT_TEMPLATE, event_type="wedding", **kwargs
    )
    assert old == new, f"חתונה בלי venue — פלט חייב להיות זהה\nישן: {old!r}\nחדש: {new!r}"
    print(f"✓ חתונה בלי venue: זהות בייטים ({len(new)} chars)")


def test_bar_mitzvah_celebration_now_correct():
    """בר מצווה עם DEFAULT_TEMPLATE + event_type אמיתי — {{celebration}} מתוקן.

    dev note: ``terms.celebration`` הוא "חתונה" (סתמי, בטוח אחרי ל/ב) —
    ה"א הידיעה נבלעת ב-``ל``, לכן הפלט לחתונה הוא "לחתונה" (לא "להחתונה").
    לבר מצווה: ``terms.celebration`` = "אירוע בר המצווה" → "לאירוע בר המצווה".
    """
    # לפני: render_template ללא event_type → default 'wedding' → "לחתונה"
    kwargs = {**COMMON_KWARGS, "bride": ""}  # בר מצווה: רק חוגג אחד
    before = messaging.render_template(messaging.DEFAULT_TEMPLATE, **kwargs)  # ברירת מחדל = wedding
    assert "לחתונה" in before, f"baseline לא מכיל 'לחתונה' כפי שצפוי לפני התיקון: {before!r}"

    after = messaging.render_automation_template(
        messaging.DEFAULT_TEMPLATE, event_type="bar_mitzvah", **kwargs
    )
    assert "לאירוע בר המצווה" in after, (
        f"אחרי המעבר — {{{{celebration}}}} חייב להתרחב ל-'אירוע בר המצווה': {after!r}"
    )
    # "לחתונה" עשוי להופיע כתת-מחרוזת ב"אירוע בר המצווה"? לא —
    # "חתונה" ו-"מצווה" מילים שונות. בטוח לבדוק שלילית.
    assert "לחתונה" not in after, (
        f"אחרי המעבר — אסור שיישאר 'לחתונה' באירוע בר מצווה: {after!r}"
    )
    assert _no_leftover_tokens(after)
    print(f"✓ בר מצווה: {{{{celebration}}}} תוקן ל-'אירוע בר המצווה' (במקום 'חתונה')")


def test_all_event_types_no_leftover_tokens():
    """בכל 8 הסוגים: DEFAULT_TEMPLATE דרך הצינור החדש → אין טוקנים לא-מוחלפים."""
    from app.message_library import _LIBRARY_BY_TYPE

    for etype in _LIBRARY_BY_TYPE:
        out = messaging.render_automation_template(
            messaging.DEFAULT_TEMPLATE, event_type=etype, **COMMON_KWARGS
        )
        assert _no_leftover_tokens(out), (
            f"{etype}: נשארו טוקנים לא-מוחלפים: {out!r}"
        )
    print(f"✓ כל {len(_LIBRARY_BY_TYPE)} סוגי האירוע: אין טוקנים לא-מוחלפים")


def test_single_host_event_no_orphan_vav():
    """אירוע עם חוגג יחיד (bride ריק) — לא מופיע ' ו' ליד סוף השם."""
    kwargs = {**COMMON_KWARGS, "bride": ""}
    for etype in ("bar_mitzvah", "brit"):
        out = messaging.render_automation_template(
            messaging.DEFAULT_TEMPLATE, event_type=etype, **kwargs
        )
        # שם החוגג הוא "יונתן"; חייב להופיע, אבל בלי " ו" תלוי אחריו
        assert "יונתן ו " not in out, f"{etype}: מופיע ' ו ' יתום: {out!r}"
        assert "יונתן ו\n" not in out, f"{etype}: מופיע ' ו' לפני שורה חדשה: {out!r}"
        assert not out.rstrip().endswith("ו"), (
            f"{etype}: הפלט מסתיים ב-'ו' יתום: {out!r}"
        )
    print("✓ אירועי חוגג יחיד: אין ' ו' יתום ליד השם")


if __name__ == "__main__":
    test_wedding_default_template_identity()
    test_wedding_default_template_empty_guest_name_identity()
    test_wedding_custom_saved_old_syntax_template_identity()
    test_wedding_default_template_no_venue_identity()
    test_bar_mitzvah_celebration_now_correct()
    test_all_event_types_no_leftover_tokens()
    test_single_host_event_no_orphan_vav()
    print()
    print("=== כל הבדיקות עברו — קומיט 2 של 3ט תקין ===")
