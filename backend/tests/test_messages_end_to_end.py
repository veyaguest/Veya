"""בדיקות מקצה-לקצה למערכת ההודעות — הבאגים שתוקנו בסבב "סיום מערכת ההודעות".

הרצה: ``venv/bin/python tests/test_messages_end_to_end.py`` (עצמאי, בלי pytest).

כל בדיקה כאן נכתבה מול באג אמיתי שנמצא בקוד, כדי שלא יחזור:

1. ``provision_rsvp_track`` העתיק גוף תבנית *חתונתי* לכל סוג אירוע, ולכן בר
   מצווה קיבל בעורך "אנחנו [שמות בני הזוג]" ("אנחנו יונתן").
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
from app.message_library import (  # noqa: E402
    _LIBRARY_BY_TYPE, MITZVAH_LIBRARY, default_body_for, entries_for,
)
from app.rsvp_track import _body_for_event  # noqa: E402

ALL_TYPES = list(_LIBRARY_BY_TYPE.keys())
STAGES = ("invitation", "first_reminder", "second_reminder", "thank_you", "before_event")


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


def test_provisioned_body_matches_event_type():
    """באג 1: כל סוג אירוע חייב לקבל בעורך נוסח שנכתב לסוג שלו.

    שלב ההזמנה — הנוסח המפורש של הסוג (``DEFAULT_INVITATION_BY_TYPE``),
    לכל שמונת הסוגים כולל חתונה. שאר השלבים — מהספרייה של הסוג, ולחתונה
    מגוף ה-``VeyaTemplate`` הגלובלי כמו קודם.
    """
    from app.message_library import DEFAULT_INVITATION_BY_TYPE

    wedding_body = "אנחנו [שמות בני הזוג], ונשמח מאוד לראות אתכם."

    for etype in ALL_TYPES:
        got = _body_for_event(FakeEvent(event_type=etype), "invitation", wedding_body)
        assert got == DEFAULT_INVITATION_BY_TYPE[etype], (
            f"{etype}/invitation: לא קיבל את נוסח ההזמנה המפורש שלו")

    for stage in STAGES:
        if stage == "invitation":
            continue
        got = _body_for_event(FakeEvent(event_type="wedding"), stage, wedding_body)
        assert got is wedding_body, f"חתונה/{stage}: הגוף הגלובלי הוחלף"

    for etype in ALL_TYPES:
        if etype == "wedding":
            continue
        for stage in STAGES:
            if stage == "invitation":
                continue
            got = _body_for_event(FakeEvent(event_type=etype), stage, wedding_body)
            assert got != wedding_body, f"{etype}/{stage}: עדיין מקבל נוסח חתונתי"
            # הגוף נשמר עם טוקנים מתורגמים לשפת הסוג (סבב 3י).
            bodies = {messaging.localize_tokens(e["body"], etype)
                      for e in entries_for(etype)}
            assert got in bodies, f"{etype}/{stage}: הנוסח אינו מהספרייה של הסוג"
    print(f"✓ באג 1: כל {len(ALL_TYPES)} הסוגים × {len(STAGES)} שלבים — נוסח לפי סוג")


def test_stage_picks_matching_category():
    """שלב 'לפני האירוע' חייב לקבל הודעת *יום האירוע*, לא הודעת חנייה.

    בחירה לפי סגנון בלבד נתנה לחינה את "חנייה · חם" כתבנית 'לפני האירוע',
    כי זו הייתה ההתאמה הראשונה בסדר העדיפויות.
    """
    from app.message_library import STAGE_PREFERRED_CATEGORY

    for etype in ALL_TYPES:
        if etype == "wedding":
            continue
        for stage, want_cat in STAGE_PREFERRED_CATEGORY.items():
            if stage == "invitation":
                continue  # ההזמנה מגיעה ממפה מפורשת, לא מהספרייה
            body = default_body_for(etype, stage)
            if body is None:
                continue
            entry = next(e for e in entries_for(etype) if e["body"] == body)
            cats = {e["category"] for e in entries_for(etype) if e["stage"] == stage}
            if want_cat in cats:
                assert entry["category"] == want_cat, (
                    f"{etype}/{stage}: נבחרה קטגוריה '{entry['category']}' "
                    f"במקום '{want_cat}'"
                )
    print("✓ בחירת ברירת המחדל מכבדת את קטגוריית השלב")


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
    # הרגיסטרים דתי/חב"ד/חרדי אוחדו לסגנון "מסורתי" אחד; זו התבנית שבה
    # ההורים מזמינים, והיחידה שמשתמשת בשורת ההורים.
    religious = next(
        e["body"] for e in MITZVAH_LIBRARY
        if e["style"] == "traditional" and e["stage"] == "invitation"
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
    # והם באמת לא מוצעים יותר לבחירה, באף סוג אירוע.
    for etype in ALL_TYPES:
        offered = {p["token"] for p in messaging.placeholders_for(etype)}
        assert not (offered & set(messaging.RETIRED_TOKENS)), (
            f"{etype}: טוקן ללא מקור נתונים עדיין מוצע בבורר")
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
        for p in messaging.placeholders_for(etype):
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


def test_no_broken_output_across_all_templates():
    """סריקה רוחבית: אף תבנית, באף סוג ובאף מצב נתונים, לא מייצרת פלט שבור."""
    import re

    scenarios = [
        dict(groom_name="יואב", bride_name="דנה", venue_name="אולמי הגן",
             venue_address="הרצל 1, תל אביב", event_date="2026-09-10",
             event_time="20:00"),
        dict(groom_name="יונתן", venue_name="אולמי הגן", event_date="2026-09-10",
             event_time="20:00"),
        dict(groom_name="יואב", bride_name="דנה"),
    ]
    checked = 0
    for etype in ALL_TYPES:
        for kw in scenarios:
            ev = FakeEvent(event_type=etype, **kw)
            for entry in entries_for(etype):
                out = _render(entry["body"], ev, table_number=12, guest_count=2)
                tag = f"{etype}/{entry['name']}"
                assert not re.search(r"\[[^\]\n]{1,25}\]", out), f"{tag}: טוקן לא הוחלף"
                assert "  " not in out, f"{tag}: רווח כפול"
                assert "\n\n\n" not in out, f"{tag}: שלוש שורות ריקות"
                assert not re.search(r"\sו\s|\sו$", out), f"{tag}: 'ו' יתומה"
                for ln in out.split("\n"):
                    assert ln == ln.rstrip(), f"{tag}: רווח בסוף שורה {ln!r}"
                checked += 1
    print(f"✓ {checked} רינדורים ({len(ALL_TYPES)} סוגים × {len(scenarios)} מצבים) — פלט נקי")


def test_no_couple_language_in_single_host_libraries():
    """סבב 3י: אין ניסוח זוגי בנוסח שמארח יחיד קורא בעורך.

    הבאג: גוף התבנית נכתב בטוקן קנוני "[שמות בעלי האירוע]" (מחרוזת אחת
    שמשרתת כמה סוגים). השליחה תמיד הייתה נכונה — אבל *הטקסט שהחוגג עורך*
    דיבר בלשון רבים על אירוע עם מארח אחד.
    """
    couple_words = [
        "בעלי האירוע", "בני הזוג", "בני זוג", "נישואי", "מתחתנים",
        "נישאים", "חתונת", "החתונה", "חתן", "כלה", "צאצאינו",
    ]
    single = [t for t, v in event_terms.EVENT_TERMS.items() if not v.has_two_hosts]
    for etype in single:
        for entry in entries_for(etype):
            body = messaging.localize_tokens(entry["body"], etype)
            for word in couple_words:
                assert word not in body, (
                    f"{etype}/{entry['name']}: ניסוח זוגי '{word}' באירוע מארח יחיד")
    print(f"✓ סבב 3י: אין ניסוח זוגי ב-{len(single)} סוגי מארח יחיד")


def test_shared_library_is_gender_correct():
    """``MITZVAH_LIBRARY`` משרתת בר *וגם* בת מצווה — ובלשון זכר.

    לפני התיקון, בת מצווה קיבלה הזמנה חב"דית/חרדית שאומרת "בננו".
    """
    forbidden = {
        "bat_mitzvah": ["בננו", "בנכם", "היקר ", "בכניסתו"],
        "bar_mitzvah": ["בתנו", "בתכם", "החוגגת", "בכניסתה"],
    }
    for etype, words in forbidden.items():
        for entry in entries_for(etype):
            body = messaging.localize_tokens(entry["body"], etype)
            for word in words:
                assert word not in body, (
                    f"{etype}/{entry['name']}: מגדר שגוי — '{word}'")
    print("✓ סבב 3י: בר ובת מצווה מקבלות נוסח במגדר הנכון מאותה ספרייה")


def test_picker_tokens_match_template_tokens():
    """כל טוקן שכתוב בנוסח חייב להיות מוצע גם בבורר, ולהיפך היכן שרלוונטי.

    בלי זה נוצר הפער שהמשתמש דיווח עליו: הבורר מציע "[שם החוגג]" בזמן
    שהנוסח שהוא בחר כתוב "[שמות בעלי האירוע]" — שתי מחרוזות לאותו דבר.
    """
    import re

    for etype in ALL_TYPES:
        offered = {p["token"] for p in messaging.placeholders_for(etype)}
        used: set[str] = set()
        for entry in entries_for(etype):
            body = messaging.localize_tokens(entry["body"], etype)
            used |= set(re.findall(r"\[[^\]\n]{1,30}\]", body))
        orphans = used - offered
        assert not orphans, f"{etype}: טוקנים בנוסח שאינם בבורר — {orphans}"
    print("✓ סבב 3י: הטוקנים בבורר ובנוסחים זהים בכל הסוגים")


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


def test_default_invitations_are_clean_and_human():
    """סבב ברירות המחדל: שמונת נוסחי ההזמנה עומדים בכללי הכתיבה.

    הנוסחים האלה הם ההודעה הראשונה שכל משתמש חדש רואה, ולכן הם נבדקים
    מול אותם כללים שהוסכמו: בלי שפה דתית כברירת מחדל, בלי שפה רשמית,
    ובלי ניסוח זוגי באירוע עם מארח יחיד.
    """
    from app.message_library import DEFAULT_INVITATION_BY_TYPE

    banned_everywhere = [
        "בשעה טובה", "בסימן טוב", "בשבח והודיה", "בעזהי", "השי\"ת",
        "מתכבדים להזמינכם", "הנכם מוזמנים",
    ]
    for etype, body in DEFAULT_INVITATION_BY_TYPE.items():
        for word in banned_everywhere:
            assert word not in body, f"{etype}: '{word}' אסור בברירת מחדל"
        assert body.startswith("היי ") or body.startswith("שלום "), (
            f"{etype}: הפתיח חייב להיות 'היי'/'שלום'")
        assert "[קישור אישור]" in body, f"{etype}: חסר קישור אישור"
        assert body.rstrip().endswith(("[קישור אישור]", "]")), (
            f"{etype}: ההודעה חייבת להסתיים בקישור או בחתימה")
        # פתיח קצר: עד 6 שורות לפני בלוק הפרטים.
        head = body.split("📅")[0].strip()
        assert len(head.splitlines()) <= 6, (
            f"{etype}: הפתיח ארוך מדי ({len(head.splitlines())} שורות)")

    single = [t for t, v in event_terms.EVENT_TERMS.items() if not v.has_two_hosts]
    for etype in single:
        body = DEFAULT_INVITATION_BY_TYPE[etype]
        for word in ("בעלי האירוע", "בני הזוג", "החתן", "הכלה"):
            assert word not in body, f"{etype}: ניסוח זוגי '{word}' במארח יחיד"

    # בחתונה חייבים להופיע שמות שני בני הזוג.
    assert "[שמות בני הזוג]" in DEFAULT_INVITATION_BY_TYPE["wedding"]
    print("✓ ברירות מחדל: 8 נוסחים עומדים בכללי הכתיבה")


def test_default_invitations_render_clean_for_every_type():
    """כל נוסח ברירת מחדל מרונדר נקי — עם נתונים מלאים ובלי שדות רשות."""
    import re

    from app.message_library import DEFAULT_INVITATION_BY_TYPE

    full = dict(venue_name="אולמי הגן", venue_address="הרצל 1, תל אביב",
                event_date="2026-09-10", event_time="20:00")
    for etype, body in DEFAULT_INVITATION_BY_TYPE.items():
        for label, extra in (("מלא", dict(groom_name="יואב", bride_name="דנה",
                                          groom_parents_line="משפחת כהן")),
                             ("בלי שם משפחה", dict(groom_name="יואב", bride_name="דנה"))):
            ev = FakeEvent(event_type=etype, **{**full, **extra})
            out = _render(body, ev)
            tag = f"{etype}/{label}"
            assert not re.search(r"\[[^\]\n]{1,25}\]", out), f"{tag}: טוקן לא הוחלף"
            assert "  " not in out, f"{tag}: רווח כפול"
            assert "\n\n\n" not in out, f"{tag}: שלוש שורות ריקות"
            assert not out.rstrip().endswith(","), f"{tag}: מסתיים בפסיק תלוי"
    print("✓ ברירות מחדל: 8 נוסחים × 2 מצבי נתונים — רינדור נקי")


def test_traditional_style_is_the_only_religious_register():
    """סבב ברירות המחדל: דתי/חב"ד/חרדי אוחדו לסגנון "מסורתי" אחד."""
    from app.message_library import STYLE_LABELS, entries_for

    for gone in ("religious", "chabad", "haredi"):
        assert gone not in STYLE_LABELS, f"הסגנון '{gone}' עדיין בתוויות"
    used = {e["style"] for t in ALL_TYPES for e in entries_for(t)}
    assert not (used & {"religious", "chabad", "haredi"}), (
        f"עדיין יש תבניות בסגנונות שהוסרו: {used & {'religious','chabad','haredi'}}")
    assert used <= set(STYLE_LABELS), f"סגנון בלי תווית: {used - set(STYLE_LABELS)}"
    print(f"✓ סגנון מסורתי אחד; {len(used)} סגנונות בשימוש, כולם עם תווית")


if __name__ == "__main__":
    test_provisioned_body_matches_event_type()
    test_stage_picks_matching_category()
    test_date_and_time_are_not_duplicated()
    test_parents_lines_reach_the_message()
    test_hosts_names_single_host_and_whitespace()
    test_retired_tokens_still_resolve()
    test_offered_tokens_all_have_a_data_source()
    test_dangling_separator_is_removed()
    test_no_broken_output_across_all_templates()
    test_no_couple_language_in_single_host_libraries()
    test_shared_library_is_gender_correct()
    test_picker_tokens_match_template_tokens()
    test_localized_tokens_all_resolve()
    test_default_invitations_are_clean_and_human()
    test_default_invitations_render_clean_for_every_type()
    test_traditional_style_is_the_only_religious_register()
    print()
    print("=== כל בדיקות מערכת ההודעות עברו ===")
