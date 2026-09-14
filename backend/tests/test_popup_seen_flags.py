"""שלושה פופאפי "פעם אחת למשתמש": תנאי שימוש, מדריך הושבה, מוזמנים.

נועלת שהמקור-אמת של כל אחד הוא ה-DB (לא localStorage): משתמש חדש רואה כל
פופאפ בפעם הראשונה, ואחרי שסימן "נראה" — הדגל חוזר ``True``/``guide_seen``
חוזר ``True`` גם מקריאת API טרייה (סימולציה של מכשיר/דפדפן אחר, כי אין כאן
שום state בזיכרון הלקוח — כל בדיקה משתמשת ב-token בלבד מול ה-API האמיתי).

הרצה: ``python tests/test_popup_seen_flags.py``
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


def test_guests_popup_seen_flag() -> None:
    """מסך ההיכרות עם ניהול מוזמנים: פעם אחת לכל חשבון, ברמת /auth/me."""
    api, teardown = bootstrap()
    try:
        me = api.client.get("/auth/me", headers=api.headers).json()
        assert me["guests_popup_seen"] is False, me

        r = api.client.post("/auth/guests-popup-seen", headers=api.headers)
        assert r.status_code == 204, f"סימון נכשל: {r.status_code} {r.text}"

        # "מכשיר אחר" = קריאת /auth/me טרייה, בלי שום state בצד לקוח.
        me_again = api.client.get("/auth/me", headers=api.headers).json()
        assert me_again["guests_popup_seen"] is True, me_again

        # אידמפוטנטי — קריאה חוזרת לא נכשלת ולא משנה כלום.
        r2 = api.client.post("/auth/guests-popup-seen", headers=api.headers)
        assert r2.status_code == 204
        print("✓ guests_popup_seen: פעם אחת לחשבון, נשמר בשרת")
    finally:
        teardown()


def test_seating_guide_seen_flag_per_event() -> None:
    """מדריך ההושבה: פעם אחת לכל אירוע (לא רק לחשבון) — ב-GET /hall."""
    api, teardown = bootstrap()
    try:
        hall = api.get_hall()
        assert hall["guide_seen"] is False, hall

        r = api.client.post("/hall/guide-seen", headers=api.headers)
        assert r.status_code == 200, f"סימון נכשל: {r.status_code} {r.text}"
        assert r.json()["guide_seen"] is True

        hall_again = api.get_hall()
        assert hall_again["guide_seen"] is True, hall_again

        r2 = api.client.post("/hall/guide-seen", headers=api.headers)
        assert r2.status_code == 200
        print("✓ seating guide guide_seen: פעם אחת לאירוע, נשמר בשרת")
    finally:
        teardown()


def test_seating_guide_seen_does_not_leak_across_events() -> None:
    """אותו משתמש, אירוע חדש אחרי מחיקת הקודם: guide_seen לא "עובר" איתו.

    היום המוצר מגביל "אירוע אחד בכל חשבון" (routers/events.py) — אי אפשר
    לבדוק שני אירועים *במקביל* דרך ה-API הציבורי. הבדיקה הזו בכל זאת נועלת
    את העיקרון ("ברמת אירוע, לא ברמת משתמש"): מוחקים את האירוע שסומן,
    יוצרים אירוע חדש לאותו משתמש/טוקן — והוא חייב לקבל guide_seen=False
    משלו, לא לרשת את הערך של האירוע שנמחק.
    """
    api, teardown = bootstrap()
    try:
        api.client.post("/hall/guide-seen", headers=api.headers)
        assert api.get_hall()["guide_seen"] is True

        auth_headers = {"Authorization": f"Bearer {api.token}"}
        del_r = api.client.delete(f"/events/{api.event_id}", headers=auth_headers)
        assert del_r.status_code == 204, del_r.text

        new_event = api.client.post(
            "/events",
            headers=auth_headers,
            json={
                "groom_name": "יוסי",
                "bride_name": "מיכל",
                "event_type": "wedding",
                "venue_name": "אולם שני",
            },
        )
        assert new_event.status_code == 201, new_event.text
        new_headers = {**auth_headers, "X-Event-Id": str(new_event.json()["id"])}
        new_hall = api.client.get("/hall", headers=new_headers).json()
        assert new_hall["guide_seen"] is False, new_hall
        print("✓ guide_seen ברמת אירוע — אירוע חדש לא יורש את הערך מהקודם")
    finally:
        teardown()


def test_terms_reconsent_unaffected_by_guests_popup() -> None:
    """סימון פופאפ מוזמנים לא נוגע במנגנון ה-reconsent הקיים (תנאי שימוש)."""
    api, teardown = bootstrap()
    try:
        before = api.client.get("/auth/me", headers=api.headers).json()
        assert before["needs_reconsent"] is False, before

        api.client.post("/auth/guests-popup-seen", headers=api.headers)

        after = api.client.get("/auth/me", headers=api.headers).json()
        assert after["needs_reconsent"] is False, after
        print("✓ needs_reconsent (תנאי שימוש) לא מושפע מסימון פופאפ אחר")
    finally:
        teardown()


if __name__ == "__main__":
    test_guests_popup_seen_flag()
    test_seating_guide_seen_flag_per_event()
    test_seating_guide_seen_does_not_leak_across_events()
    test_terms_reconsent_unaffected_by_guests_popup()
    shutdown()
    print("\nכל הבדיקות עברו ✓")
