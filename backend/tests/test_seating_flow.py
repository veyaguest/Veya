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


def _table(num: int, x: int, y: int, capacity: int = 12, locked: bool = False,
           guest_ids=None) -> dict:
    """שולחן במבנה ש-``PUT /hall`` מצפה לו."""
    return {
        "table_number": num, "x": x, "y": y, "guest_ids": guest_ids or [],
        "table_type": "round", "capacity": capacity, "rotation": 0,
        "name": "", "color": "", "notes": "", "locked": locked,
        "is_reserve": False,
    }


def test_locked_table_is_not_touched() -> None:
    """שולחן נעול שומר בדיוק על מי שיושב בו גם אחרי "הושבה בקליק".

    זה מה שהופך את הכפתור לבטוח: עבודה ידנית שהמשתמש נעל בכוונה לא נמחקת.
    """
    api, teardown = bootstrap()
    try:
        keep_a = api.add_guest("אורח נעול א", "0501000001")
        keep_b = api.add_guest("אורח נעול ב", "0501000002")
        for i in range(8):
            api.add_guest(f"אורח חופשי {i}", f"05020000{i:02d}")

        api.save_hall([
            _table(1, 100, 100, capacity=6, locked=True,
                   guest_ids=[keep_a["id"], keep_b["id"]]),
            _table(2, 400, 100, capacity=6),
            _table(3, 700, 100, capacity=6),
        ], seats_per_table=6)

        r = api.generate(seats_per_table=6, persist=True)
        assert r.status_code == 200, r.text
        assert r.json()["violations"] == [], r.json()["violations"]

        hall = api.get_hall()
        assert _table_of(hall, "אורח נעול א") == 1, "מוזמן הוזז משולחן נעול"
        assert _table_of(hall, "אורח נעול ב") == 1, "מוזמן הוזז משולחן נעול"
        print("✓ שולחן נעול נשמר כפי שהוא")
    finally:
        teardown()


def test_only_unassigned_keeps_everyone_in_place() -> None:
    """מצב "השלמת מקומות": מי שכבר משובץ לא זז, ומי שלא — מקבל שולחן."""
    api, teardown = bootstrap()
    try:
        seated = [api.add_guest(f"יושב {i}", f"05030000{i:02d}") for i in range(4)]
        api.save_hall([
            _table(1, 100, 100, capacity=6, guest_ids=[g["id"] for g in seated]),
            _table(2, 400, 100, capacity=6),
        ], seats_per_table=6)

        before = {g["full_name"]: 1 for g in seated}
        newcomer = api.add_guest("מאחר לארוחה", "0504000001")

        r = api.generate(seats_per_table=6, persist=True, only_unassigned=True)
        assert r.status_code == 200, r.text
        hall = api.get_hall()
        for name, tnum in before.items():
            assert _table_of(hall, name) == tnum, (
                f"{name} הוזז למרות only_unassigned"
            )
        assert _table_of(hall, newcomer["full_name"]) is not None, "המאחר לא שובץ"
        print("✓ only_unassigned לא מזיז אף מוזמן משובץ")
    finally:
        teardown()


def test_group_constraint_applies_to_whole_group() -> None:
    """"לא לשבת ליד עובדים" באירוע עסקי חל על **כל** בני הקבוצה."""
    api, teardown = bootstrap(event_type="business")
    try:
        api.add_guest("מנכ\"לית", "0505000001", group_type="management",
                      seating_notes="לא לשבת ליד עובדים")
        for i in range(3):
            api.add_guest(f"עובד {i}", f"05060000{i:02d}", group_type="employees")
        for i in range(2):
            api.add_guest(f"לקוח {i}", f"05070000{i:02d}", group_type="clients")

        hall = api.get_hall()
        assert len(hall["forbidden_pairs"]) == 3, (
            f"ציפינו ל-3 אילוצים (מנכ\"לית מול 3 עובדים): {hall['forbidden_pairs']}"
        )

        api.save_hall([
            _table(1, 100, 100, capacity=3),
            _table(2, 400, 100, capacity=3),
        ], seats_per_table=3)
        r = api.generate(seats_per_table=3, persist=True)
        assert r.status_code == 200, r.text
        assert r.json()["violations"] == [], r.json()["violations"]

        hall = api.get_hall()
        boss = _table_of(hall, "מנכ\"לית")
        for i in range(3):
            assert _table_of(hall, f"עובד {i}") != boss, (
                f"עובד {i} שובץ עם המנכ\"לית — אילוץ הקבוצה הופר"
            )
        print("✓ אילוץ ברמת קבוצה חל על כל בני הקבוצה")
    finally:
        teardown()


def test_violations_are_reported_when_unsolvable() -> None:
    """כשאין פתרון — המערכת לא מציגה את ההושבה כתקינה ומפרטת מה נכשל."""
    api, teardown = bootstrap()
    try:
        # שני אנשים שאסור להם יחד, ורק שולחן אחד באולם => בהכרח הפרה.
        api.add_guest("דני כהן", "0508000001",
                      seating_notes="לא לשבת ליד משה לוי")
        api.add_guest("משה לוי", "0508000002")
        api.save_hall([_table(1, 100, 100, capacity=12)])

        r = api.generate(persist=True)
        assert r.status_code == 200, r.text
        body = r.json()
        assert not body["hard_ok"], "הושבה עם הפרה סומנה כתקינה"
        assert body["violations"], "אין דוח הפרות למרות שההושבה נכשלה"
        assert not body["persisted"], "הושבה עם הפרה נשמרה"
        kinds = {v["kind"] for v in body["violations"]}
        assert "unseated" in kinds or "forbidden_pair" in kinds, kinds
        assert all(v["text"] for v in body["violations"]), "הפרה בלי ניסוח לתצוגה"
        print(f"✓ דוח הפרות מלא: {[v['text'] for v in body['violations']]}")
    finally:
        teardown()


def test_zone_words_do_not_become_fake_people() -> None:
    """"רחוק מהרעש" היא העדפת אזור — ולא יחס "להתרחק מאדם בשם הרעש"."""
    api, teardown = bootstrap()
    try:
        api.add_guest("סבתא רחל", "0509000001",
                      seating_notes="רחוק מהרעש, קרוב לכניסה")
        api.add_guest("אורח רגיל", "0509000002")
        hall = api.get_hall()
        assert hall["forbidden_pairs"] == [], (
            f"ביטוי אזור יצר אילוץ מזויף: {hall['forbidden_pairs']}"
        )
        assert hall["together_pairs"] == [], (
            f"ביטוי אזור יצר קשר מזויף: {hall['together_pairs']}"
        )
        print("✓ ביטויי אזור לא הופכים לאילוצים בין אנשים")
    finally:
        teardown()


def test_undo_restores_previous_arrangement() -> None:
    """"החזרת הסידור הקודם" מחזירה בדיוק את המצב שלפני ההרצה.

    כולל שינוי ידני שנעשה **לפני** ההושבה — הוא לא נמחק (דרישה 6).
    """
    api, teardown = bootstrap()
    try:
        manual = api.add_guest("שובץ ידנית", "0510000001")
        others = [api.add_guest(f"אורח {i}", f"05110000{i:02d}") for i in range(5)]

        # סידור ידני: המוזמן הראשון בשולחן 2, השאר ללא שולחן.
        api.save_hall([
            _table(1, 100, 100, capacity=6),
            _table(2, 400, 100, capacity=6, guest_ids=[manual["id"]]),
        ], seats_per_table=6)
        before = {g["full_name"]: _table_of(api.get_hall(), g["full_name"])
                  for g in [manual] + others}
        assert before["שובץ ידנית"] == 2

        # לפני הרצה — אין מה לשחזר.
        st = api.client.get("/seating/undo-state", headers=api.headers).json()
        assert st["can_undo"] is False, st

        r = api.generate(seats_per_table=6, persist=True)
        assert r.status_code == 200, r.text
        assert r.json()["can_undo"] is True, "לא נשמר תצלום לשחזור"
        after = {name: _table_of(api.get_hall(), name) for name in before}
        assert after != before, "ההושבה לא שינתה כלום — הבדיקה לא בודקת כלום"

        # שחזור.
        u = api.client.post("/seating/undo", headers=api.headers)
        assert u.status_code == 200, u.text
        assert u.json()["restored_guests"] >= 1, u.json()

        restored = {name: _table_of(api.get_hall(), name) for name in before}
        assert restored == before, (
            f"השחזור לא החזיר את המצב הקודם: {restored} != {before}"
        )

        # אחרי שחזור — אין מה לשחזר שוב (לא "מבטלים את הביטול").
        st = api.client.get("/seating/undo-state", headers=api.headers).json()
        assert st["can_undo"] is False, st
        again = api.client.post("/seating/undo", headers=api.headers)
        assert again.status_code == 400, "שחזור כפול לא נחסם"
        print("✓ החזרת הסידור הקודם משחזרת במדויק, כולל שיבוץ ידני")
    finally:
        teardown()


def test_natural_hebrew_negations_separate_guests() -> None:
    """כל ניסוח שלילה טבעי בעברית מפריד בפועל בין השניים — לא רק מתפרש נכון.

    זה היה הבאג: הפרסר זיהה את הטריגר החיובי "ליד" והתעלם מה"לא" שלפניו,
    ולכן ההערה התפרשה כ**בקשה להושיב יחד** — היפוך משמעות מוחלט. הבדיקה
    מריצה את המסלול המלא דרך ה-API לכל ניסוח בנפרד, ומוודאת שהשניים באמת
    יושבים בשולחנות שונים.

    האולם מכוון בכוונה לשני שולחנות של 4 עם 8 אנשים — המנוע *חייב* למלא
    את שניהם, כך שהפרדה אינה יכולה לקרות במקרה.
    """
    phrasings = [
        "לא יושב ליד משה לוי",
        "לא רוצה לשבת ליד משה לוי",
        "שלא ישב ליד משה לוי",
        "אסור לשבת ליד משה לוי",
        "לא ליד משה לוי",
    ]
    for note in phrasings:
        api, teardown = bootstrap()
        try:
            api.add_guest("גדי אבן", "0509990001", seating_notes=note)
            api.add_guest("משה לוי", "0509990002")
            for i in range(6):
                api.add_guest(f"אורח {i}", f"05099910{i:02d}")

            hall = api.get_hall()
            assert len(hall["forbidden_pairs"]) == 1, (
                f"{note!r} לא יצר אילוץ קשיח: {hall['forbidden_pairs']}"
            )
            assert hall["together_pairs"] == [], (
                f"{note!r} נקרא כבקשה לשבת יחד — היפוך משמעות: "
                f"{hall['together_pairs']}"
            )

            api.save_hall([
                _table(1, 100, 100, capacity=4),
                _table(2, 400, 100, capacity=4),
            ], seats_per_table=4)
            r = api.generate(seats_per_table=4, persist=True)
            assert r.status_code == 200, r.text
            assert r.json()["violations"] == [], r.json()["violations"]

            hall = api.get_hall()
            t_gadi = _table_of(hall, "גדי אבן")
            t_moshe = _table_of(hall, "משה לוי")
            assert t_gadi is not None and t_moshe is not None, (
                f"{note!r}: מישהו לא שובץ"
            )
            assert t_gadi != t_moshe, (
                f"{note!r} הופר — שניהם בשולחן {t_gadi}"
            )
            print(f"  ✓ {note:<26} → גדי בשולחן {t_gadi}, משה בשולחן {t_moshe}")
        finally:
            teardown()
    print(f"✓ כל {len(phrasings)} ניסוחי השלילה הטבעיים מפרידים בפועל")


if __name__ == "__main__":
    try:
        test_internal_note_does_not_affect_seating()
        test_seating_note_creates_constraints()
        test_hard_constraint_is_never_broken()
        test_internal_note_cannot_break_seating()
        test_zone_preference_from_seating_note()
        test_locked_table_is_not_touched()
        test_only_unassigned_keeps_everyone_in_place()
        test_group_constraint_applies_to_whole_group()
        test_violations_are_reported_when_unsolvable()
        test_zone_words_do_not_become_fake_people()
        test_undo_restores_previous_arrangement()
        test_natural_hebrew_negations_separate_guests()
        print("OK — מערכת ההושבה עוברת את בדיקות הקצה-לקצה.")
    finally:
        shutdown()
