"""בדיקות מקצה-לקצה למערכת ההודעות — הבאגים שתוקנו בסבב "סיום מערכת ההודעות".

הרצה: ``venv/bin/python tests/test_messages_end_to_end.py`` (עצמאי, בלי pytest).

כל בדיקה כאן נכתבה מול באג אמיתי שנמצא בקוד, כדי שלא יחזור. הבדיקות של
ספריית הנוסחים הישנה (``message_library``/``rsvp_track``) הוסרו יחד עם הקוד
עצמו (5/8/2026) — הנוסחים חיים היום בהודעות המסלול (``communication.py``).

2. תאריך ושעה הוזנו מאוחדים לטוקן ``[תאריך]``, והתוצאה הייתה
   "10/09/2026 בשעה 20:00 בשעה 20:00".
3. שורות ההורים להזמנה דתית לא הועברו לאף מסלול שליחה, ולכן נמחקו תמיד.
4. ``hosts_names`` חיבר "יונתן ושרה" גם באירוע עם חוגג יחיד, ולא ניקה רווחים.
5. טוקנים שהוצאו מהבורר (מתנה/גלריות) היו נכתבים למוזמן כטקסט גולמי אילו
   הוסרו גם ממפת הערכים.
6. מפריד שנשען על ערך ריק נשאר תלוי ("דנה ויואב · ").
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import event_terms, messaging  # noqa: E402

# כל סוגי האירוע שהמערכת מכירה (הלקסיקון הוא מקור האמת).
ALL_TYPES = list(event_terms.EVENT_TERMS.keys())


class FakeEvent:
    """מינימום השדות ש-``messaging.event_values`` נוגע בהם."""

    def __init__(self, **kw):
        self.groom_name = ""
        self.bride_name = ""
        self.venue_name = ""
        self.venue_address = ""
        self.event_date = ""
        self.event_time = ""
        self.event_type = "wedding"
        self.groom_parents_line = ""
        self.bride_parents_line = ""
        self.__dict__.update(kw)


def _render(body: str, ev: FakeEvent, **kw) -> str:
    return messaging.render_automation_template(
        body, guest_name="דנה כהן", link="https://veya.co.il/c/ab12",
        **{**messaging.event_values(ev), **kw},
    )


def test_date_and_time_are_not_duplicated():
    """באג 2: "[תאריך] בשעה [שעה]" לא יוצר "בשעה 20:00 בשעה 20:00"."""
    ev = FakeEvent(event_type="bar_mitzvah", groom_name="יונתן",
                   venue_name="אולמי הגן", event_date="2026-09-10", event_time="20:00")
    out = _render("📅 [תאריך] בשעה [שעה]", ev)
    assert out == "📅 10/09/2026 בשעה 20:00", f"קיבלתי {out!r}"
    assert out.count("בשעה") == 1, f"'בשעה' מופיע פעמיים: {out!r}"
    assert out.count("20:00") == 1, f"השעה מופיעה פעמיים: {out!r}"
    print("✓ באג 2: תאריך ושעה לא מוכפלים")


def test_parents_lines_reach_the_message():
    """באג 3: שורות ההורים מגיעות לנוסח הדתי — ונעלמות בעדינות כשהן ריקות."""
    # נוסח שבו ההורים מזמינים — שורת ההורים בשורה משלה, כמו בנוסחים המסורתיים.
    religious = (
        "[הורי החתן]\n"
        "שמחים להזמינכם לבר המצווה של [שמות בעלי האירוע]\n"
        "📅 [תאריך] בשעה [שעה]\n"
        "[קישור אישור]"
    )
    base = dict(event_type="bar_mitzvah", groom_name="יונתן",
                venue_name="אולמי הגן", event_date="2026-09-10", event_time="20:00")

    with_parents = _render(religious, FakeEvent(groom_parents_line="משפחת כהן", **base))
    assert "משפחת כהן" in with_parents, "שורת ההורים לא הגיעה להודעה"

    without = _render(religious, FakeEvent(**base))
    assert "[הורי" not in without, "טוקן ההורים נכתב כטקסט גולמי"
    assert "\n\n\n" not in without, "נשארה שורה ריקה כפולה במקום השורה שנמחקה"
    print("✓ באג 3: שורות ההורים מגיעות, וריק נעלם בלי להשאיר חור")


def test_hosts_names_single_host_and_whitespace():
    """באג 4: חוגג יחיד לא מקבל "ו", ורווחים בלבד נחשבים ריק."""
    assert event_terms.hosts_names("bar_mitzvah", "יונתן", "שרה") == "יונתן"
    assert event_terms.hosts_names("bar_mitzvah", "  ", "") == "החוגג"
    assert event_terms.hosts_names("wedding", " דניאל ", " שירה ") == "דניאל ושירה"
    assert event_terms.hosts_names("wedding", "דניאל", "") == "דניאל"
    assert event_terms.hosts_names("business", "", "") == "המארגנים"
    print("✓ באג 4: hosts_names נכון לחוגג יחיד, לזוג ולרווחים")


def test_retired_tokens_still_resolve():
    """באג 5: טוקן שהוסר מהבורר חייב להישאר במפת הערכים.

    אחרת תבנית שמורה ותיקה שכוללת אותו הייתה שולחת למוזמן "[קישור מתנה]"
    כטקסט במקום להיעלם.
    """
    values = messaging.build_automation_values(
        guest_name="דנה", groom="א", bride="ב", venue="ג")
    for tok in messaging.RETIRED_TOKENS:
        assert tok in values, f"{tok} נעלם ממפת הערכים ויישלח כטקסט גולמי"
        assert values[tok] == "", f"{tok} אמור להיות ריק (אין לו מקור נתונים)"
    # והם באמת לא מוצעים יותר לבחירה.
    offered = {p["token"] for p in messaging.AUTOMATION_PLACEHOLDERS}
    assert not (offered & set(messaging.RETIRED_TOKENS)), "טוקן ללא מקור נתונים עדיין מוצע בבורר"
    print("✓ באג 5: טוקנים שהוסרו עדיין מתפרשים, ואינם מוצעים")


def test_offered_tokens_all_have_a_data_source():
    """כל טוקן שמוצע לזוג חייב לקבל ערך אמיתי באירוע מלא."""
    full = dict(groom_name="יואב", bride_name="דנה", venue_name="אולמי הגן",
                venue_address="הרצל 1, תל אביב", event_date="2026-09-10",
                event_time="20:00", groom_parents_line="משפחת כהן",
                bride_parents_line="משפחת לוי")
    for etype in ALL_TYPES:
        ev = FakeEvent(event_type=etype, **full)
        values = messaging.build_automation_values(
            guest_name="דנה כהן", link="L", table_number=12, guest_count=2,
            **messaging.event_values(ev))
        for p in messaging.AUTOMATION_PLACEHOLDERS:
            tok = p["token"]
            if tok == "[פרטי שינוי]":
                continue  # ממולא ידנית בשליחת עדכון, ריק בכוונה
            assert tok in values, f"{etype}: {tok} אינו במפת הערכים"
            assert values[tok] != "", f"{etype}: {tok} נשאר ריק גם באירוע מלא"
    print("✓ כל טוקן שמוצע מקבל ערך אמיתי, בכל סוג אירוע")


def test_dangling_separator_is_removed():
    """באג 6: מפריד שנשען על ערך ריק יורד — אבל פיסוק שהזוג כתב נשאר."""
    ev = FakeEvent(groom_name="יואב", bride_name="דנה")  # בלי תאריך/אולם
    assert _render("[שמות בני הזוג] · [תאריך]", ev) == "יואב ודנה"
    assert _render("📍 [שם האולם], [כתובת]",
                   FakeEvent(venue_name="אולמי הגן")) == "📍 אולמי הגן"
    # פסיק שהוא חלק מהפנייה — לא נוגעים בו.
    assert _render("[שם פרטי] שלום,\nמחכים לכם.", ev) == "דנה שלום,\nמחכים לכם."
    print("✓ באג 6: מפריד תלוי יורד, פיסוק מכוון נשאר")


def test_localized_tokens_all_resolve():
    """כל טוקן מתורגם חייב להתפרש בשליחה — אחרת יישלח כטקסט גולמי."""
    values = messaging.build_automation_values(
        guest_name="דנה", groom="יונתן", bride="", venue="הגן",
        groom_parents_line="משפחת כהן")
    for etype, vocab in messaging.TOKEN_VOCABULARY.items():
        for canonical, localized in vocab.items():
            if not localized.startswith("["):
                continue  # הטיית מגדר, לא טוקן
            assert localized in values, (
                f"{etype}: הטוקן {localized} מוצג למשתמש אך אינו מתפרש בשליחה")
            assert values[localized] == values[canonical], (
                f"{etype}: {localized} ו-{canonical} אמורים לתת אותו ערך")
    print("✓ סבב 3י: כל טוקן מתורגם מתפרש לאותו ערך כמו הקנוני")


if __name__ == "__main__":
    test_date_and_time_are_not_duplicated()
    test_parents_lines_reach_the_message()
    test_hosts_names_single_host_and_whitespace()
    test_retired_tokens_still_resolve()
    test_offered_tokens_all_have_a_data_source()
    test_dangling_separator_is_removed()
    test_localized_tokens_all_resolve()
    print("\nכל בדיקות מערכת ההודעות עברו ✓")
