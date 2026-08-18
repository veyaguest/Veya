"""בדיקות למיון/סינון תצוגתיים ברשימת המוזמנים (GET /guests).

החלטת בעלים (2026-08-18): ברירת המחדל היא מיון א-ב לפי שם. אפשר למיין גם
לפי סטטוס/שולחן/כמות/תאריך הוספה, ולסנן לפי סטטוס אישור הגעה או "ללא
שולחן". הפעולות תצוגתיות בלבד — לא משנות שום נתון במסד הנתונים.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


def _names(rows: list[dict]) -> list[str]:
    return [r["full_name"] for r in rows]


def test_default_sort_is_alphabetical_by_name() -> None:
    api, teardown = bootstrap()
    try:
        api.add_guest("גיל אבידן", "0500000001", party_size=1)
        api.add_guest("אבי כהן", "0500000002", party_size=1)
        api.add_guest("בתיה לוי", "0500000003", party_size=1)

        r = api.client.get("/guests", headers=api.headers)
        assert r.status_code == 200, r.text
        assert _names(r.json()["items"]) == ["אבי כהן", "בתיה לוי", "גיל אבידן"]
        print("✓ ברירת מחדל: מיון א-ב לפי שם")
    finally:
        teardown()


def test_sort_by_status_table_and_party_size() -> None:
    api, teardown = bootstrap()
    try:
        a = api.add_guest("מגיע גדול", "0500000011", party_size=5)
        b = api.add_guest("לא מגיע", "0500000012", party_size=1)
        c = api.add_guest("מגיע קטן", "0500000013", party_size=2)
        api.client.patch(f"/guests/{a['id']}", headers=api.headers,
                          json={"rsvp_status": "confirmed"})
        api.client.patch(f"/guests/{b['id']}", headers=api.headers,
                          json={"rsvp_status": "declined"})
        api.client.patch(f"/guests/{c['id']}", headers=api.headers,
                          json={"rsvp_status": "confirmed"})

        # מיון לפי סטטוס: מגיע לפני לא מגיע (תוך שמירה על א-ב בתוך אותו סטטוס).
        r = api.client.get("/guests", headers=api.headers, params={"sort": "status"})
        assert _names(r.json()["items"]) == ["מגיע גדול", "מגיע קטן", "לא מגיע"]

        # מיון לפי כמות אנשים — מהגדול לקטן.
        r = api.client.get("/guests", headers=api.headers, params={"sort": "party_size"})
        assert _names(r.json()["items"])[0] == "מגיע גדול"
        assert _names(r.json()["items"])[-1] == "לא מגיע"

        # מיון לפי שולחן: מי שיש לו שולחן קודם, מי שאין — בסוף.
        api.save_hall([
            {"table_number": 1, "x": 0, "y": 0, "guest_ids": [c["id"]],
             "table_type": "round", "capacity": 12, "rotation": 0,
             "name": "", "color": "", "notes": "", "locked": False, "is_reserve": False},
        ])
        r = api.client.get("/guests", headers=api.headers, params={"sort": "table"})
        names = _names(r.json()["items"])
        assert names[0] == "מגיע קטן", names  # יש לו שולחן 1
        print("✓ מיון לפי סטטוס/כמות/שולחן עובד כמצופה")
    finally:
        teardown()


def test_filter_by_status_and_no_table() -> None:
    api, teardown = bootstrap()
    try:
        a = api.add_guest("אחד מגיע", "0500000021", party_size=1)
        b = api.add_guest("שתיים לא מגיע", "0500000022", party_size=1)
        api.add_guest("שלוש מתלבט", "0500000023", party_size=1)
        api.client.patch(f"/guests/{a['id']}", headers=api.headers,
                          json={"rsvp_status": "confirmed"})
        api.client.patch(f"/guests/{b['id']}", headers=api.headers,
                          json={"rsvp_status": "declined"})

        r = api.client.get("/guests", headers=api.headers, params={"filter_status": "confirmed"})
        data = r.json()
        assert _names(data["items"]) == ["אחד מגיע"]
        assert data["total"] == 1, "total חייב לשקף את הרשימה המסוננת"

        r = api.client.get("/guests", headers=api.headers, params={"filter_status": "no_table"})
        data = r.json()
        assert data["total"] == 3, "כל שלושת המוזמנים עדיין ללא שולחן"
        assert set(_names(data["items"])) == {"אחד מגיע", "שתיים לא מגיע", "שלוש מתלבט"}

        api.save_hall([
            {"table_number": 1, "x": 0, "y": 0, "guest_ids": [a["id"]],
             "table_type": "round", "capacity": 12, "rotation": 0,
             "name": "", "color": "", "notes": "", "locked": False, "is_reserve": False},
        ])
        r = api.client.get("/guests", headers=api.headers, params={"filter_status": "no_table"})
        assert set(_names(r.json()["items"])) == {"שתיים לא מגיע", "שלוש מתלבט"}
        print("✓ סינון לפי סטטוס ולפי 'ללא שולחן' עובד כמצופה")
    finally:
        teardown()


def test_sort_and_filter_do_not_mutate_data() -> None:
    """שילוב סינון + מיון לא משנה שום נתון אמיתי במסד — רק את סדר ההחזרה."""
    api, teardown = bootstrap()
    try:
        g = api.add_guest("בדיקת שינוי", "0500000031", party_size=3)
        api.client.patch(f"/guests/{g['id']}", headers=api.headers,
                          json={"rsvp_status": "maybe"})

        before = api.client.get("/guests", headers=api.headers).json()
        api.client.get("/guests", headers=api.headers,
                        params={"sort": "party_size", "filter_status": "maybe"})
        after = api.client.get("/guests", headers=api.headers).json()

        assert before["items"] == after["items"], "מיון/סינון לא אמורים לשנות נתונים"
        print("✓ מיון/סינון תצוגתיים בלבד — לא משנים נתונים")
    finally:
        teardown()


if __name__ == "__main__":
    try:
        test_default_sort_is_alphabetical_by_name()
        test_sort_by_status_table_and_party_size()
        test_filter_by_status_and_no_table()
        test_sort_and_filter_do_not_mutate_data()
        print("OK — מיון וסינון בניהול מוזמנים עובדים כמפרט.")
    finally:
        shutdown()
