"""בדיקות לפרסור הערות ההושבה — במיוחד שלילה.

הרקע (באג אמיתי, 2026-08-01): "לא יושב ליד משה" התפרש כ-**together**,
כלומר המנוע ניסה להושיב יחד בדיוק את מי שביקשו להפריד. הסיבה: רשימת
טריגרים שטוחה שכללה "לא לשבת ליד" (מקור) אבל לא את נטיות ההווה
("לא יושב"/"לא יושבת"/"לא יושבים"), ואילו הטריגר החיובי "ליד" כן נמצא —
וה"לא" שלפניו נבלע.

זו לא "החמצה" של אילוץ אלא **היפוך משמעות**, ולכן הבדיקות כאן בודקות את
שני הכיוונים: שהשלילה נתפסת, ושביטוי חיובי לא הופך בטעות לשלילי.

הרצה: ``python tests/test_note_parsing.py``
(עובד גם בלי pytest מותקן — סקריפט עצמאי עם ``assert``).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import constraints as parser  # noqa: E402


def _kind(note: str):
    rels = parser.parse_relations(note)
    return rels[0]["type"] if rels else None


def _target(note: str):
    rels = parser.parse_relations(note)
    return rels[0]["target_text"] if rels else None


# ניסוחי שלילה שחייבים להיקרא כ"לא לשבת יחד". רובם נטיות שלא היו ברשימת
# הטריגרים — הכיסוי מגיע מזיהוי השלילה, לא מהוספת ביטוי לרשימה.
NEGATIVE = [
    "לא יושב ליד משה לוי",
    "לא יושבת ליד משה לוי",
    "לא יושבים ליד משה לוי",
    "לא יושבות ליד משה לוי",
    "לא לשבת ליד משה לוי",
    "לא לשבת עם משה לוי",
    "לא רוצה לשבת ליד משה לוי",
    "לא רוצים לשבת ליד משה לוי",
    "שלא ישב ליד משה לוי",
    "שלא ישבו ליד משה לוי",
    "אסור לשבת ליד משה לוי",
    "אין לשבת ליד משה לוי",
    "בלי לשבת ליד משה לוי",
    "לא ליד משה לוי",
    "אל תושיבו ליד משה לוי",
    "נא לא לשבת ליד משה לוי",
]

# ניסוחים חיוביים שחייבים להישאר "לשבת יחד".
POSITIVE = [
    "לשבת ליד משה לוי",
    "לשבת עם משה לוי",
    "רוצה לשבת עם משה לוי",
    "רוצים לשבת ליד משה לוי",
    "יחד עם משה לוי",
    "ביחד עם משה לוי",
    "קרוב לדני כהן",
    "בלי בעיה לשבת ליד משה לוי",
]


def test_negated_phrasings_are_avoid() -> None:
    for note in NEGATIVE:
        kind = _kind(note)
        assert kind == "avoid", (
            f"{note!r} התפרש כ-{kind!r} במקום 'avoid'. "
            f"שלילה שלא נתפסת = היפוך משמעות: המנוע יקרב את מי שצריך להרחיק."
        )
        assert _target(note), f"{note!r}: לא זוהה שם יעד"
    print(f"✓ {len(NEGATIVE)} ניסוחי שלילה נקראים כ'לא לשבת יחד'")


def test_positive_phrasings_stay_together() -> None:
    for note in POSITIVE:
        kind = _kind(note)
        assert kind == "together", (
            f"{note!r} התפרש כ-{kind!r} במקום 'together' — "
            f"זיהוי שלילה תפס יותר מדי."
        )
    print(f"✓ {len(POSITIVE)} ניסוחים חיוביים נשארו 'לשבת יחד'")


def test_distant_negation_does_not_flip() -> None:
    """שלילה רחוקה שייכת למשפט אחר ולא אמורה להפוך את המשמעות."""
    note = "לא אכפת לי בכלל מה הסידור שיהיה, שישבו ליד משה לוי"
    assert _kind(note) == "together", (
        f"שלילה רחוקה הפכה את המשמעות: {parser.parse_relations(note)}"
    )
    print("✓ שלילה רחוקה לא הופכת ביטוי חיובי")


def test_mixed_note_keeps_each_segment() -> None:
    """הערה עם שני סעיפים — כל אחד נקרא לפי השלילה שלו."""
    note = "רוצה לשבת ליד רותי כהן, לא יושב ליד משה לוי"
    rels = parser.parse_relations(note)
    kinds = {r["target_text"]: r["type"] for r in rels}
    assert kinds.get("רותי כהן") == "together", kinds
    assert kinds.get("משה לוי") == "avoid", kinds
    print("✓ הערה מעורבת: כל סעיף נקרא לפי השלילה שלו")


def test_zone_words_are_not_people() -> None:
    """ביטויי אזור לא הופכים ליחס בין אנשים (בשני הכיוונים)."""
    for note in ["רחוק מהרעש", "ליד הבר", "לא ליד הרמקולים", "קרוב לכניסה"]:
        assert parser.parse_relations(note) == [], (
            f"{note!r} יצר יחס בין אנשים: {parser.parse_relations(note)}"
        )
    print("✓ ביטויי אזור לא הופכים ליחס בין אנשים")


def test_avoid_wins_over_together_when_both_present() -> None:
    """חוק קשיח גובר: הערה ששני הצדדים שלה מתייחסים לאותו אדם."""
    guests = [
        {"id": 1, "full_name": "דני כהן", "group_type": "friends",
         "seating_notes": "לא יושב ליד משה לוי"},
        {"id": 2, "full_name": "משה לוי", "group_type": "friends",
         "seating_notes": "רוצה לשבת עם דני כהן"},
    ]
    forbidden, together = parser.build_pairs_from_guests(guests, "wedding")
    assert (1, 2) in forbidden, f"האיסור לא נוצר: {forbidden}"
    assert (1, 2) not in together, (
        f"הזוג הופיע גם כ'לשבת יחד' — חוק קשיח חייב לגבור: {together}"
    )
    print("✓ חוק קשיח גובר על בקשה הפוכה של הצד השני")


if __name__ == "__main__":
    test_negated_phrasings_are_avoid()
    test_positive_phrasings_stay_together()
    test_distant_negation_does_not_flip()
    test_mixed_note_keeps_each_segment()
    test_zone_words_are_not_people()
    test_avoid_wins_over_together_when_both_present()
    print("OK — פרסור הערות ההושבה מזהה שלילה נכון.")
