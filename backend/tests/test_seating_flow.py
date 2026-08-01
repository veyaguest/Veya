"""בדיקות מקצה-לקצה למערכת ההושבה — דרך ה-API האמיתי, לא רק הפונקציות.

הרצה: ``python tests/test_seating_flow.py``
(עובד גם בלי pytest מותקן — סקריפט עצמאי עם ``assert``).

מה נבדק כאן:
- **הפרדת ההערות:** הערה פנימית (``notes_raw``) לא משפיעה על ההושבה בשום
  מסלול; הערת הושבה (``seating_notes``) משפיעה בכל המסלולים.
- **החוק הקשיח:** "לא לשבת ליד X" לעולם לא נשבר, גם כשקל יותר לשבור אותו.
- **הצינור המלא:** האילוצים מגיעים גם ל-``GET /hall`` (האזהרות והבדיקות
  בצד הלקוח) וגם ל-``POST /seating/generate`` (השיבוץ עצמו).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


def _table_of(hall: dict, guest_name: str):
    """מספר השולחן שבו יושב מוזמן לפי שם, או None אם אינו משובץ."""
    for t in hall["tables"]:
        for g in t["guests"]:
            if g["full_name"] == guest_name:
                return t["table_number"]
    return None


def test_internal_note_does_not_affect_seating() -> None:
    """הערה פנימית עם ניסוח שנראה כמו אילוץ — לא יוצרת אילוץ."""
    api, teardown = bootstrap()
    try:
        api.add_guest("דני כהן", "0501111111", notes_raw="לא לשבת ליד משה לוי")
        api.add_guest("משה לוי", "0502222222", notes_raw="צריך לחזור אליו")
        hall = api.get_hall()
        assert hall["forbidden_pairs"] == [], (
            f"הערה פנימית יצרה אילוץ: {hall['forbidden_pairs']}"
        )
        assert hall["together_pairs"] == []
        assert hall["warnings"] == [], f"הערה פנימית יצרה אזהרה: {hall['warnings']}"
        print("✓ הערה פנימית לא משפיעה על ההושבה")
    finally:
        teardown()


def test_seating_note_creates_constraints() -> None:
    """הערת הושבה יוצרת אילוץ קשיח ומגיעה גם ל-GET /hall."""
    api, teardown = bootstrap()
    try:
        a = api.add_guest("דני כהן", "0501111111",
                          seating_notes="לא לשבת ליד משה לוי")
        b = api.add_guest("משה לוי", "0502222222")
        c = api.add_guest("רותי כהן", "0503333333",
                          seating_notes="לשבת עם דני כהן")

        hall = api.get_hall()
        pair = sorted([a["id"], b["id"]])
        assert [pair[0], pair[1]] in [list(p) for p in hall["forbidden_pairs"]], (
            f"האילוץ לא הגיע ל-/hall: {hall['forbidden_pairs']}"
        )
        together = sorted([a["id"], c["id"]])
        assert [together[0], together[1]] in [list(p) for p in hall["together_pairs"]]
        print("✓ הערת הושבה יוצרת אילוצים ומגיעה ל-/hall")
    finally:
        teardown()


def test_hard_constraint_is_never_broken() -> None:
    """"לא לשבת ליד" נאכף גם כשהאולם צפוף ונוח לשבור אותו.

    שני שולחנות של 4 מקומות ו-8 אנשים: המנוע *חייב* למלא את שניהם, ובכל
    זאת אסור לו לשים את השניים האסורים יחד.
    """
    api, teardown = bootstrap()
    try:
        api.add_guest("דני כהן", "0501111111",
                      seating_notes="לא לשבת ליד משה לוי")
        api.add_guest("משה לוי", "0502222222")
        for i in range(6):
            api.add_guest(f"אורח {i}", f"05055500{i:02d}")

        api.save_hall(
            [
                {"table_number": 1, "x": 100, "y": 100, "guest_ids": [],
                 "table_type": "round", "capacity": 4, "rotation": 0,
                 "name": "", "color": "", "notes": "", "locked": False,
                 "is_reserve": False},
                {"table_number": 2, "x": 400, "y": 100, "guest_ids": [],
                 "table_type": "round", "capacity": 4, "rotation": 0,
                 "name": "", "color": "", "notes": "", "locked": False,
                 "is_reserve": False},
            ],
            seats_per_table=4,
        )

        r = api.generate(seats_per_table=4, persist=True)
        assert r.status_code == 200, f"השיבוץ נכשל: {r.status_code} {r.text}"
        body = r.json()
        assert body["hard_ok"], f"המנוע דיווח על הפרת חוק קשיח: {body}"

        hall = api.get_hall()
        t_dani = _table_of(hall, "דני כהן")
        t_moshe = _table_of(hall, "משה לוי")
        assert t_dani is not None and t_moshe is not None, "מישהו לא שובץ"
        assert t_dani != t_moshe, (
            f'"לא לשבת ליד" הופר — שניהם בשולחן {t_dani}'
        )
        assert hall["warnings"] == [], f"נותרו אזהרות: {hall['warnings']}"
        print("✓ החוק הקשיח נאכף גם באולם צפוף")
    finally:
        teardown()


def test_internal_note_cannot_break_seating() -> None:
    """אותו תרחיש, אבל האילוץ נכתב כהערה פנימית — ולכן *לא* אמור לחייב.

    זו הבדיקה ההפוכה: היא מוודאת שההפרדה אמיתית ולא רק "לא נבדקה".
    שני מוזמנים בלבד ושולחן אחד גדול — אם ההערה הפנימית הייתה נאכפת,
    אחד מהם היה נשאר בלי שולחן.
    """
    api, teardown = bootstrap()
    try:
        api.add_guest("דני כהן", "0501111111",
                      notes_raw="לא לשבת ליד משה לוי")
        api.add_guest("משה לוי", "0502222222")
        api.save_hall(
            [
                {"table_number": 1, "x": 100, "y": 100, "guest_ids": [],
                 "table_type": "round", "capacity": 12, "rotation": 0,
                 "name": "", "color": "", "notes": "", "locked": False,
                 "is_reserve": False},
            ],
        )
        r = api.generate(persist=True)
        assert r.status_code == 200, r.text
        hall = api.get_hall()
        assert _table_of(hall, "דני כהן") == _table_of(hall, "משה לוי"), (
            "הערה פנימית מנעה ישיבה משותפת — ההפרדה לא עובדת"
        )
        print("✓ הערה פנימית לא חוסמת ישיבה משותפת")
    finally:
        teardown()


def test_zone_preference_from_seating_note() -> None:
    """"קרוב לבר" מהערת הושבה מזיז את המוזמן לשולחן שליד הבר."""
    api, teardown = bootstrap()
    try:
        api.add_guest("דני כהן", "0501111111", seating_notes="קרוב לבר")
        for i in range(3):
            api.add_guest(f"אורח {i}", f"05055500{i:02d}")

        api.save_hall(
            [
                # שולחן 1 רחוק מהבר, שולחן 2 צמוד אליו.
                {"table_number": 1, "x": 100, "y": 100, "guest_ids": [],
                 "table_type": "round", "capacity": 2, "rotation": 0,
                 "name": "", "color": "", "notes": "", "locked": False,
                 "is_reserve": False},
                {"table_number": 2, "x": 900, "y": 900, "guest_ids": [],
                 "table_type": "round", "capacity": 2, "rotation": 0,
                 "name": "", "color": "", "notes": "", "locked": False,
                 "is_reserve": False},
            ],
            elements=[
                {"id": "bar-1", "type": "bar", "x": 880, "y": 880,
                 "width": 100, "height": 40, "rotation": 0, "shape": "rectangle",
                 "color": "", "locked": False},
            ],
            seats_per_table=2,
        )

        r = api.generate(seats_per_table=2, persist=True)
        assert r.status_code == 200, r.text
        body = r.json()
        hall = api.get_hall()
        assert _table_of(hall, "דני כהן") == 2, (
            f'"קרוב לבר" לא כובד — שובץ לשולחן {_table_of(hall, "דני כהן")}'
        )
        reasons = [e for e in body["explanations"] if e["full_name"] == "דני כהן"]
        assert reasons and any("בר" in x for x in reasons[0]["reasons"]), (
            f"אין הסבר 'קרוב לבר': {body['explanations']}"
        )
        print("✓ העדפת אזור מהערת הושבה מכובדת ומוסברת")
    finally:
        teardown()


if __name__ == "__main__":
    try:
        test_internal_note_does_not_affect_seating()
        test_seating_note_creates_constraints()
        test_hard_constraint_is_never_broken()
        test_internal_note_cannot_break_seating()
        test_zone_preference_from_seating_note()
        print("OK — מערכת ההושבה עוברת את בדיקות הקצה-לקצה.")
    finally:
        shutdown()
