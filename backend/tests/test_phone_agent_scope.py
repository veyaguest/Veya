"""היקף העבודה של הטלפן — הקצאת אירועים ובידוד בין לקוחות (§9–§10 באפיון).

המודל שנבחר, אחרי בדיקת הארכיטקטורה הקיימת:

במודול הזה **אין ישות "משימת שיחה"**. התור מחושב חי בכל בקשה מ-Workflow
אישורי ההגעה + סטטוס המוזמנים (``app/call_center.py``), ואין שורה בטבלה
שמייצגת שיחה שצריך לבצע — אז אין למה לתלות ``assigned_to``. היחידה היציבה
היחידה שאפשר להקצות היא **האירוע**, ולכן ההקצאה היא
``CallAssignment(event_id, user_id)``.

התנהגות:
- אדמין                     → כל האירועים.
- טלפן עם הקצאה אחת לפחות   → רק האירועים שהוקצו לו.
- טלפן בלי הקצאות           → תור משותף (שלב א', עד שייבנה מסך ההקצאה).

הבדיקות כאן מוכיחות את שלושת המצבים, ובעיקר שהצמצום נכנס לתוקף **מעצמו**
ברגע שנוצרת ההקצאה הראשונה — בלי שינוי קוד ב-Call Center.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap  # noqa: E402
from tests.call_center_helpers import (  # noqa: E402
    assign_events,
    call_logs_of,
    configure_track,
    phone_agent,
)


def test_unassigned_agent_gets_the_shared_queue() -> None:
    """שלב א': טלפן בלי הקצאות רואה את כל האירועים שסבב שלהם נפתח."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        configure_track(api_a)
        configure_track(api_b)
        api_a.add_guest("אורח A", "0509200001", party_size=1)
        api_b.add_guest("אורח B", "0509200002", party_size=1)
        _, agent = phone_agent(api_a)

        # הסקירה (לא מדפדפת) — שני האירועים נמצאים בה.
        overview = api_a.client.get("/admin/call-center", headers=agent).json()
        listed = {e["event_id"] for e in overview["events"]}
        assert {api_a.event_id, api_b.event_id} <= listed, listed

        # ובתור עצמו הוא באמת מגיע למוזמנים של שניהם.
        for api, name in ((api_a, "אורח A"), (api_b, "אורח B")):
            items = api_a.client.get(
                "/admin/call-center/queue", headers=agent,
                params={"event_id": api.event_id},
            ).json()["items"]
            assert name in [g["full_name"] for g in items], (name, items)
        print("✓ טלפן בלי הקצאות מקבל את התור המשותף")
    finally:
        teardown_a()
        teardown_b()


def test_assigned_agent_sees_only_assigned_events() -> None:
    """ברגע שיש הקצאה — הטלפן רואה **רק** אותה, בסקירה ובתור."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        configure_track(api_a)
        configure_track(api_b)
        api_a.add_guest("אורח A", "0509200003", party_size=1)
        api_b.add_guest("אורח B", "0509200004", party_size=1)
        agent_id, agent = phone_agent(api_a)
        assign_events(agent_id, [api_a.event_id])

        overview = api_a.client.get("/admin/call-center", headers=agent).json()
        assert [e["event_id"] for e in overview["events"]] == [api_a.event_id]

        items = api_a.client.get("/admin/call-center/queue", headers=agent).json()["items"]
        assert [g["full_name"] for g in items] == ["אורח A"]
        print("✓ טלפן עם הקצאה רואה רק את האירועים שהוקצו לו")
    finally:
        teardown_a()
        teardown_b()


def test_assigned_agent_cannot_reach_a_guest_of_another_event() -> None:
    """ניחוש מזהה מוזמן של אירוע לא-מוקצה מוחזר כ-404, גם בקריאה ישירה."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        configure_track(api_a)
        configure_track(api_b)
        api_a.add_guest("אורח A", "0509200005", party_size=1)
        guest_b = api_b.add_guest("אורח B", "0509200006", party_size=1)
        agent_id, agent = phone_agent(api_a)
        assign_events(agent_id, [api_a.event_id])

        r = api_a.client.get(f"/admin/call-center/guests/{guest_b['id']}", headers=agent)
        assert r.status_code == 404, r.status_code

        r = api_a.client.post(
            f"/admin/call-center/guests/{guest_b['id']}/outcome",
            headers=agent, json={"outcome": "confirmed", "count": 1},
        )
        assert r.status_code == 404, r.status_code
        # ובאמת לא נכתבה שום שורה ולא השתנה שום סטטוס.
        assert call_logs_of(api_b, guest_b["id"]) == []
        rows = api_b.client.get("/guests", headers=api_b.headers).json()["items"]
        assert rows[0]["rsvp_status"] == "pending"
        print("✓ טלפן לא מגיע למוזמן של אירוע שלא הוקצה לו")
    finally:
        teardown_a()
        teardown_b()


def test_display_filter_cannot_widen_an_agent_scope() -> None:
    """סינון התצוגה (``event_id``) לא יכול להרחיב הרשאה — רק לצמצם.

    זו הסיבה שהיקף ההרשאה מועבר בפרמטר נפרד (``allowed_event_ids``) ולא
    מתערבב עם סינון התצוגה.
    """
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        configure_track(api_a)
        configure_track(api_b)
        api_a.add_guest("אורח A", "0509200007", party_size=1)
        api_b.add_guest("אורח B", "0509200008", party_size=1)
        agent_id, agent = phone_agent(api_a)
        assign_events(agent_id, [api_a.event_id])

        r = api_a.client.get(
            "/admin/call-center/queue", headers=agent,
            params={"event_id": api_b.event_id},
        )
        assert r.status_code == 200, r.text
        assert r.json()["items"] == [], r.json()
        print("✓ סינון תצוגה לא פותח גישה לאירוע שלא הוקצה")
    finally:
        teardown_a()
        teardown_b()


def test_two_agents_do_not_see_each_other_events() -> None:
    """טלפן א' וטלפן ב' — כל אחד רק עם האירוע שלו."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        configure_track(api_a)
        configure_track(api_b)
        api_a.add_guest("אורח A", "0509200009", party_size=1)
        api_b.add_guest("אורח B", "0509200010", party_size=1)
        id1, agent1 = phone_agent(api_a, display_name="טלפן 1")
        id2, agent2 = phone_agent(api_a, display_name="טלפן 2")
        assign_events(id1, [api_a.event_id])
        assign_events(id2, [api_b.event_id])

        names1 = [g["full_name"] for g in
                  api_a.client.get("/admin/call-center/queue", headers=agent1).json()["items"]]
        names2 = [g["full_name"] for g in
                  api_a.client.get("/admin/call-center/queue", headers=agent2).json()["items"]]
        assert names1 == ["אורח A"] and names2 == ["אורח B"], (names1, names2)
        print("✓ שני טלפנים עובדים על תורים נפרדים לחלוטין")
    finally:
        teardown_a()
        teardown_b()


def test_admin_still_sees_everything() -> None:
    """התפקיד החדש לא צמצם את האדמין: הוא ממשיך לראות את כל האירועים."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        from tests.call_center_helpers import standalone_admin

        configure_track(api_a)
        configure_track(api_b)
        api_a.add_guest("אורח A", "0509200011", party_size=1)
        api_b.add_guest("אורח B", "0509200012", party_size=1)
        agent_id, _ = phone_agent(api_a)
        assign_events(agent_id, [api_a.event_id])

        admin = standalone_admin(api_a)
        listed = {e["event_id"] for e in
                  api_a.client.get("/admin/call-center", headers=admin).json()["events"]}
        assert {api_a.event_id, api_b.event_id} <= listed, listed
        for api, name in ((api_a, "אורח A"), (api_b, "אורח B")):
            items = api_a.client.get(
                "/admin/call-center/queue", headers=admin,
                params={"event_id": api.event_id},
            ).json()["items"]
            assert name in [g["full_name"] for g in items], (name, items)
        print("✓ אדמין ממשיך לראות את כל האירועים, גם אחרי הוספת התפקיד החדש")
    finally:
        teardown_a()
        teardown_b()


def test_deleting_an_event_removes_its_assignments() -> None:
    """מחיקת אירוע מנקה את ההקצאות שלו — בלי רשומות יתומות."""
    api, teardown = bootstrap()
    try:
        from app import models
        from app.database import SessionLocal

        configure_track(api)
        agent_id, _ = phone_agent(api)
        assign_events(agent_id, [api.event_id])

        r = api.client.delete(f"/events/{api.event_id}", headers=api.headers)
        assert r.status_code in (200, 204), r.text

        db = SessionLocal()
        try:
            left = db.query(models.CallAssignment).filter_by(event_id=api.event_id).count()
        finally:
            db.close()
        assert left == 0, f"נשארו {left} הקצאות יתומות"
        print("✓ מחיקת אירוע מנקה את הקצאות הטלפנים שלו")
    finally:
        teardown()
