"""בדיקות לחיבור סטטוס אישור הגעה (RSVP) → תמונת מצב + סידורי הושבה.

החלטת בעלים (2026-08-18): לכל מוזמן יש סטטוס אישור הגעה — טרם השיב (ברירת
מחדל) / מגיע / לא מגיע / מתלבט. ניתן לשנות אותו ידנית בעריכת מוזמן. הכלל:
רק "מגיע" נספר כפעיל בסידורי ההושבה (``Guest.effective_seats``); שינוי
סטטוס לעולם לא מוחק שיבוץ קיים (``table_number``) — רק משנה אם המוזמן
נספר כתופס מקום.

הרצה: ``python tests/test_rsvp_seating_link.py`` (עצמאי, בלי pytest) או
``pytest tests/test_rsvp_seating_link.py``.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import Guest  # noqa: E402
from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


# ---- 1. יחידה טהורה על ה-property עצמו — בלי DB, כל הסטטוסים ----

def test_effective_seats_only_confirmed_counts() -> None:
    g = Guest(full_name="בדיקה", phone="0500000000", party_size=2)

    g.rsvp_status = "pending"
    assert g.effective_seats == 0, "טרם השיב חייב להיספר כ-0"

    g.rsvp_status = "maybe"
    assert g.effective_seats == 0, "מתלבט חייב להיספר כ-0"

    g.rsvp_status = "declined"
    assert g.effective_seats == 0, "לא מגיע חייב להיספר כ-0"

    g.rsvp_status = "confirmed"
    assert g.effective_seats == 2, "מגיע בלי confirmed_count נופל ל-party_size"

    g.confirmed_count = 1
    assert g.effective_seats == 1, "מגיע עם confirmed_count משתמש בו, לא ב-party_size"

    g.rsvp_status = "maybe"
    assert g.effective_seats == 0, "חזרה ל'מתלבט' — שוב 0, גם אם confirmed_count עדיין שמור"

    g.rsvp_status = "confirmed"
    assert g.effective_seats == 1, "חזרה ל'מגיע' — חוזר אוטומטית להשתמש ב-confirmed_count השמור"
    print("✓ effective_seats: רק 'מגיע' נספר כפעיל, בכל הכיוונים")


# ---- 2. עריכה ידנית דרך ה-API משפיעה מיד על הספירה הפעילה ----

def test_manual_status_change_via_api_updates_active_seats() -> None:
    api, teardown = bootstrap()
    try:
        g = api.add_guest("תמר לוי", "0501111111", party_size=2)
        gid = g["id"]

        # ברירת מחדל: טרם השיב → לא נספר.
        hall = api.get_hall()
        unassigned = {u["id"]: u for u in hall["unassigned"]}
        assert unassigned[gid]["rsvp_status"] == "pending"
        assert unassigned[gid]["seats"] == 0, "טרם השיב לא אמור להיספר כתופס מקום"

        # מגיע → 2.
        r = api.client.patch(f"/guests/{gid}", headers=api.headers,
                              json={"rsvp_status": "confirmed"})
        assert r.status_code == 200, r.text
        hall = api.get_hall()
        unassigned = {u["id"]: u for u in hall["unassigned"]}
        assert unassigned[gid]["seats"] == 2, "מגיע עם party_size=2 חייב להיספר כ-2"

        # לא מגיע → 0.
        r = api.client.patch(f"/guests/{gid}", headers=api.headers,
                              json={"rsvp_status": "declined"})
        assert r.status_code == 200, r.text
        hall = api.get_hall()
        unassigned = {u["id"]: u for u in hall["unassigned"]}
        assert unassigned[gid]["seats"] == 0, "לא מגיע חייב לרדת מהספירה"

        # מתלבט → 0.
        r = api.client.patch(f"/guests/{gid}", headers=api.headers,
                              json={"rsvp_status": "maybe"})
        assert r.status_code == 200, r.text
        hall = api.get_hall()
        unassigned = {u["id"]: u for u in hall["unassigned"]}
        assert unassigned[gid]["seats"] == 0, "מתלבט לא אמור להיספר כמגיע"

        # חזרה למגיע → חוזר אוטומטית ל-2.
        r = api.client.patch(f"/guests/{gid}", headers=api.headers,
                              json={"rsvp_status": "confirmed"})
        assert r.status_code == 200, r.text
        hall = api.get_hall()
        unassigned = {u["id"]: u for u in hall["unassigned"]}
        assert unassigned[gid]["seats"] == 2, "חזרה למגיע חייבת להחזיר את הספירה המלאה"

        print("✓ שינוי סטטוס ידני דרך ה-API משפיע מיד על הספירה הפעילה")
    finally:
        teardown()


# ---- 3. שינוי סטטוס לעולם לא "מוחק" מוזמן מהשולחן שהוא כבר משובץ אליו ----

def test_status_change_never_unseats_guest() -> None:
    api, teardown = bootstrap()
    try:
        g = api.add_guest("רועי כהן", "0502222222", party_size=2)
        gid = g["id"]
        r = api.client.patch(f"/guests/{gid}", headers=api.headers,
                              json={"rsvp_status": "confirmed"})
        assert r.status_code == 200, r.text

        api.save_hall([
            {"table_number": 1, "x": 100, "y": 100, "guest_ids": [gid],
             "table_type": "round", "capacity": 12, "rotation": 0,
             "name": "", "color": "", "notes": "", "locked": False, "is_reserve": False},
        ])

        hall = api.get_hall()
        table = next(t for t in hall["tables"] if t["table_number"] == 1)
        assert [x["id"] for x in table["guests"]] == [gid]
        assert table["seats_used"] == 2

        # מסמנים "מתלבט" — נשאר על השולחן, אבל מפסיק להיספר כתופס מקום.
        r = api.client.patch(f"/guests/{gid}", headers=api.headers,
                              json={"rsvp_status": "maybe"})
        assert r.status_code == 200, r.text
        hall = api.get_hall()
        table = next(t for t in hall["tables"] if t["table_number"] == 1)
        assert [x["id"] for x in table["guests"]] == [gid], (
            "מוזמן לא אמור להימחק מהשולחן בגלל שינוי סטטוס"
        )
        assert table["seats_used"] == 0, "אבל לא נספר כתופס מקום כל עוד הוא לא 'מגיע'"

        # חזרה למגיע — חוזר להיספר, בלי לגעת בשיבוץ עצמו.
        r = api.client.patch(f"/guests/{gid}", headers=api.headers,
                              json={"rsvp_status": "confirmed"})
        assert r.status_code == 200, r.text
        hall = api.get_hall()
        table = next(t for t in hall["tables"] if t["table_number"] == 1)
        assert [x["id"] for x in table["guests"]] == [gid]
        assert table["seats_used"] == 2

        print("✓ שינוי סטטוס לא מוחק שיבוץ קיים — רק את הספירה הפעילה")
    finally:
        teardown()


# ---- 4. תמונת המצב מציגה מוזמנים + אנשים לכל אחד מ-4 הסטטוסים ----

def test_dashboard_shows_guests_and_people_per_status() -> None:
    api, teardown = bootstrap()
    try:
        a = api.add_guest("מגיע אחד", "0503333331", party_size=2)
        b = api.add_guest("לא מגיע", "0503333332", party_size=3)
        c = api.add_guest("מתלבט", "0503333333", party_size=2)
        api.add_guest("טרם השיב", "0503333334", party_size=1)  # נשאר בברירת המחדל

        for guest, status in ((a, "confirmed"), (b, "declined"), (c, "maybe")):
            r = api.client.patch(f"/guests/{guest['id']}", headers=api.headers,
                                  json={"rsvp_status": status})
            assert r.status_code == 200, r.text

        r = api.client.get("/stats", headers=api.headers)
        assert r.status_code == 200, r.text
        stats = r.json()

        assert stats["confirmed"] == 1 and stats["confirmed_people"] == 2
        assert stats["declined"] == 1 and stats["declined_people"] == 3
        assert stats["maybe"] == 1 and stats["maybe_people"] == 2
        assert stats["pending"] == 1 and stats["pending_people"] == 1
        print("✓ תמונת המצב מציגה מוזמנים+אנשים נכון לכל אחד מ-4 הסטטוסים")
    finally:
        teardown()


# ---- 5. שינוי סטטוס ידני מעריכת מוזמן נרשם ביומן הפעילות — בלי כפילויות ----

def _audit_action_rows(api, action: str) -> list[dict]:
    """שורות היומן לפעולה נתונה, מהחדשה לישנה — ממוין לפי id (לא created_at,
    שברזולוציית שנייה ב-SQLite עלול להיות זהה לשתי רשומות שנוצרו סמוך זו לזו)."""
    r = api.client.get("/event/audit", headers=api.headers)
    assert r.status_code == 200, r.text
    rows = [row for row in r.json() if row["action"] == action]
    return sorted(rows, key=lambda row: row["id"], reverse=True)


def test_manual_status_change_creates_audit_event_for_dashboard_feed() -> None:
    api, teardown = bootstrap()
    try:
        g = api.add_guest("ישראל כהן", "0507654321", party_size=1)
        gid = g["id"]

        r = api.client.patch(f"/guests/{gid}", headers=api.headers,
                              json={"rsvp_status": "confirmed"})
        assert r.status_code == 200, r.text

        rows = _audit_action_rows(api, "guest_rsvp_manual_update")
        assert len(rows) == 1, f"ציפינו לרשומת יומן אחת: {rows}"
        assert rows[0]["detail"] == "ישראל כהן — אישור הגעה התקבל", rows[0]

        # PATCH עם אותו ערך — לא אמור ליצור רשומה כפולה.
        r = api.client.patch(f"/guests/{gid}", headers=api.headers,
                              json={"rsvp_status": "confirmed"})
        assert r.status_code == 200, r.text
        rows = _audit_action_rows(api, "guest_rsvp_manual_update")
        assert len(rows) == 1, "PATCH עם אותו ערך יצר רשומה כפולה"

        # עריכה שלא נגעה בסטטוס — גם לא אמורה ליצור רשומה.
        r = api.client.patch(f"/guests/{gid}", headers=api.headers,
                              json={"party_size": 3})
        assert r.status_code == 200, r.text
        rows = _audit_action_rows(api, "guest_rsvp_manual_update")
        assert len(rows) == 1, "עריכה שלא נגעה בסטטוס יצרה רשומה"

        # שינוי אמיתי נוסף — רשומה שנייה, עם הסטטוס הקודם הנכון.
        r = api.client.patch(f"/guests/{gid}", headers=api.headers,
                              json={"rsvp_status": "maybe"})
        assert r.status_code == 200, r.text
        rows = _audit_action_rows(api, "guest_rsvp_manual_update")
        assert len(rows) == 2, rows
        assert rows[0]["detail"] == "ישראל כהן — עדכון הגעה: אולי", rows[0]

        print("✓ שינוי סטטוס ידני יוצר רשומת יומן פעילות אחת, בלי כפילויות")
    finally:
        teardown()


if __name__ == "__main__":
    try:
        test_effective_seats_only_confirmed_counts()
        test_manual_status_change_via_api_updates_active_seats()
        test_status_change_never_unseats_guest()
        test_dashboard_shows_guests_and_people_per_status()
        test_manual_status_change_creates_audit_event_for_dashboard_feed()
        print("OK — חיבור RSVP↔הושבה↔תמונת מצב עובד כמפרט.")
    finally:
        shutdown()
