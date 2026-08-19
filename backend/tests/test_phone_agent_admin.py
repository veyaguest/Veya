"""ניהול טלפנים מפאנל האדמין — יצירה, השבתה/הפעלה והקצאת אירועים.

השלב הזה לא הוסיף אף מנגנון חדש, ולכן הבדיקות כאן מוודאות בעיקר שהוא באמת
נשען על הקיים:
- היצירה עוברת ב-``POST /admin/accounts`` (אותו מסלול של מפיק/אולם).
- ההשבתה/הפעלה ב-``/admin/users/{id}/disable|enable`` הקיימים, שכבר מעלים
  ``token_version`` ולכן פוסלים גם טוקן שכבר בידי המשתמש.
- ההקצאה נשמרת ב-``call_assignments`` שנבנתה בשלב הקודם.

וכן — שהיסטוריה לא נעלמת: השבתה אינה מוחקת ``call_logs`` ואינה נוגעת ביומן
הפעילות של בעל/ת האירוע.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap  # noqa: E402
from tests.call_center_helpers import (  # noqa: E402
    call_logs_of,
    configure_track,
    phone_agent,
    plain_headers,
    standalone_admin,
)


def _new_email() -> str:
    return f"caller-{uuid.uuid4().hex[:8]}@veya.test"


def _create_caller(api, admin, *, email=None, name="דנה מוקד", password="Test12345!"):
    return api.client.post(
        "/admin/accounts", headers=admin,
        json={
            "email": email or _new_email(),
            "display_name": name,
            "account_type": "phone_agent",
            "new_password": password,
        },
    )


def _login(api, email: str, password: str = "Test12345!"):
    return api.client.post("/auth/login", json={"email": email, "password": password})


# ── 1–3. יצירה והתחברות ──────────────────────────────────────────────────

def test_admin_creates_a_caller_who_can_log_in() -> None:
    """(1)(2)(3) אדמין יוצר טלפן; הוא נוצר עם התפקיד הנכון ומצליח להתחבר."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        email = _new_email()
        r = _create_caller(api, admin, email=email)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body["account_type"] == "phone_agent"
        assert body["temporary_password"]

        login = _login(api, email)
        assert login.status_code == 200, login.text
        user = login.json()["user"]
        assert user["account_type"] == "phone_agent"
        assert user["is_admin"] is False

        # והטוקן שהתקבל באמת פותח את מסך השיחות — ורק אותו.
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert api.client.get("/admin/call-center", headers=headers).status_code == 200
        assert api.client.get("/admin/users", headers=headers).status_code == 403
        print("✓ אדמין יוצר טלפן, והוא מתחבר ומגיע רק למסך השיחות")
    finally:
        teardown()


def test_new_caller_appears_in_the_callers_screen() -> None:
    """הטלפן החדש מופיע במסך ניהול הטלפנים, עם המונים שלו."""
    api, teardown = bootstrap()
    try:
        configure_track(api)
        admin = standalone_admin(api)
        email = _new_email()
        caller_id = _create_caller(api, admin, email=email).json()["user_id"]

        page = api.client.get("/admin/callers", headers=admin)
        assert page.status_code == 200, page.text
        row = next(c for c in page.json()["callers"] if c["id"] == caller_id)
        assert row["email"] == email
        assert row["disabled"] is False
        assert row["calls_made"] == 0
        assert row["assigned_event_ids"] == []
        # רשימת האירועים להקצאה מגיעה באותה בקשה.
        assert any(e["event_id"] == api.event_id for e in page.json()["events"])
        print("✓ הטלפן החדש מופיע במסך ניהול הטלפנים")
    finally:
        teardown()


def test_calls_made_counter_uses_existing_call_logs() -> None:
    """מונה "שיחות שביצע" נספר מ-call_logs הקיים, לא ממקור נתונים חדש."""
    api, teardown = bootstrap()
    try:
        configure_track(api)
        admin = standalone_admin(api)
        agent_id, agent = phone_agent(api)
        guest = api.add_guest("ישראל כהן", "0509300001", party_size=2)

        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=agent, json={"outcome": "no_answer"})

        row = next(c for c in api.client.get("/admin/callers", headers=admin).json()["callers"]
                   if c["id"] == agent_id)
        assert row["calls_made"] == 1
        assert row["waiting_tasks"] >= 0
        print("✓ מונה השיחות נגזר מיומן השיחות הקיים")
    finally:
        teardown()


# ── 4–5. השבתה והפעלה ────────────────────────────────────────────────────

def test_disabled_caller_cannot_log_in_or_act() -> None:
    """(4) טלפן מושבת: לא מתחבר, וגם טוקן שכבר בידו נפסל מיד."""
    api, teardown = bootstrap()
    try:
        configure_track(api)
        admin = standalone_admin(api)
        email = _new_email()
        caller_id = _create_caller(api, admin, email=email).json()["user_id"]
        login = _login(api, email)
        live = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert api.client.get("/admin/call-center", headers=live).status_code == 200

        r = api.client.post(f"/admin/users/{caller_id}/disable", headers=admin)
        assert r.status_code == 204, r.text

        # התחברות חדשה נחסמת...
        assert _login(api, email).status_code in (401, 403)
        # ...וגם הטוקן שכבר היה בידו (token_version עלה).
        assert api.client.get("/admin/call-center", headers=live).status_code == 401
        guest = api.add_guest("לא ייענה", "0509300002", party_size=1)
        blocked = api.client.post(
            f"/admin/call-center/guests/{guest['id']}/outcome",
            headers=live, json={"outcome": "no_answer"},
        )
        assert blocked.status_code == 401, blocked.status_code
        assert call_logs_of(api, guest["id"]) == []

        row = next(c for c in api.client.get("/admin/callers", headers=admin).json()["callers"]
                   if c["id"] == caller_id)
        assert row["disabled"] is True
        print("✓ טלפן מושבת חסום — גם עם טוקן שכבר היה בידו")
    finally:
        teardown()


def test_admin_can_re_enable_a_caller() -> None:
    """(5) הפעלה מחדש מחזירה אותו לעבודה (עם התחברות מחדש)."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        email = _new_email()
        caller_id = _create_caller(api, admin, email=email).json()["user_id"]
        api.client.post(f"/admin/users/{caller_id}/disable", headers=admin)

        r = api.client.post(f"/admin/users/{caller_id}/enable", headers=admin)
        assert r.status_code == 204, r.text

        login = _login(api, email)
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert api.client.get("/admin/call-center", headers=headers).status_code == 200
        print("✓ אדמין מפעיל טלפן מחדש והוא חוזר לעבוד")
    finally:
        teardown()


def test_disabling_a_caller_keeps_all_history() -> None:
    """(13)(14) השבתה לא מוחקת יומן שיחות ולא את יומן הפעילות של הבעלים."""
    api, teardown = bootstrap()
    try:
        configure_track(api)
        admin = standalone_admin(api)
        email = _new_email()
        caller_id = _create_caller(api, admin, email=email).json()["user_id"]
        login = _login(api, email)
        agent = {"Authorization": f"Bearer {login.json()['access_token']}"}

        guest = api.add_guest("רותם ברק", "0509300003", party_size=3)
        r = api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                            headers=agent, json={"outcome": "confirmed", "count": 2})
        assert r.status_code == 200, r.text

        feed_before = [row for row in api.client.get(
            "/event/audit", headers=api.headers, params={"limit": 100},
        ).json() if row["action"].startswith("guest_call")]
        assert feed_before, "לא נרשמה פעילות מלכתחילה"

        api.client.post(f"/admin/users/{caller_id}/disable", headers=admin)

        # יומן השיחות — נשאר במלואו, כולל מי חייג.
        logs = call_logs_of(api, guest["id"])
        assert len(logs) == 1
        assert logs[0].outcome == "confirmed"
        assert logs[0].created_by_id == caller_id
        # סטטוס אישור ההגעה — נשאר.
        rows = api.client.get("/guests", headers=api.headers).json()["items"]
        mine = next(g for g in rows if g["id"] == guest["id"])
        assert mine["rsvp_status"] == "confirmed" and mine["confirmed_count"] == 2
        # יומן הפעילות של בעל/ת האירוע — זהה לחלוטין.
        feed_after = [row for row in api.client.get(
            "/event/audit", headers=api.headers, params={"limit": 100},
        ).json() if row["action"].startswith("guest_call")]
        assert [r["detail"] for r in feed_after] == [r["detail"] for r in feed_before]
        print("✓ השבתת טלפן שומרת על כל ההיסטוריה — שיחות, RSVP ויומן פעילות")
    finally:
        teardown()


# ── 6–9. הקצאת אירועים ───────────────────────────────────────────────────

def test_admin_assigns_and_removes_events() -> None:
    """(6)(7)(8)(9) הקצאה, צמצום התור בפועל, והסרה שמחזירה לתור המשותף."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        configure_track(api_a)
        configure_track(api_b)
        api_a.add_guest("אורח A", "0509300010", party_size=1)
        api_b.add_guest("אורח B", "0509300011", party_size=1)
        admin = standalone_admin(api_a)
        agent_id, agent = phone_agent(api_a)

        # (6) הקצאה
        r = api_a.client.put(
            f"/admin/callers/{agent_id}/assignments", headers=admin,
            json={"event_ids": [api_a.event_id]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["assigned_event_ids"] == [api_a.event_id]

        # (7)(8) הטלפן רואה רק את שלו
        listed = {e["event_id"] for e in
                  api_a.client.get("/admin/call-center", headers=agent).json()["events"]}
        assert listed == {api_a.event_id}, listed

        # (9) הסרת ההקצאה → חזרה לתור המשותף
        r = api_a.client.put(
            f"/admin/callers/{agent_id}/assignments", headers=admin, json={"event_ids": []},
        )
        assert r.status_code == 200, r.text
        assert r.json()["assigned_event_ids"] == []
        listed = {e["event_id"] for e in
                  api_a.client.get("/admin/call-center", headers=agent).json()["events"]}
        assert {api_a.event_id, api_b.event_id} <= listed, listed
        print("✓ הקצאה מצמצמת את התור, והסרה מחזירה לתור המשותף")
    finally:
        teardown_a()
        teardown_b()


def test_assignment_replaces_rather_than_appends() -> None:
    """שליחת רשימה חדשה מחליפה את הקודמת (ולא מצטברת), בלי כפילויות."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        configure_track(api_a)
        configure_track(api_b)
        admin = standalone_admin(api_a)
        agent_id, _ = phone_agent(api_a)

        api_a.client.put(f"/admin/callers/{agent_id}/assignments", headers=admin,
                         json={"event_ids": [api_a.event_id]})
        r = api_a.client.put(f"/admin/callers/{agent_id}/assignments", headers=admin,
                             json={"event_ids": [api_b.event_id]})
        assert r.json()["assigned_event_ids"] == [api_b.event_id]

        # ושליחה חוזרת של אותה רשימה לא יוצרת שורה כפולה.
        r = api_a.client.put(f"/admin/callers/{agent_id}/assignments", headers=admin,
                             json={"event_ids": [api_b.event_id]})
        assert r.json()["assigned_event_ids"] == [api_b.event_id]

        from app import models
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            count = db.query(models.CallAssignment).filter_by(user_id=agent_id).count()
        finally:
            db.close()
        assert count == 1, f"נוצרו {count} שורות הקצאה במקום אחת"
        print("✓ ההקצאה מחליפה ולא מצטברת, ואין שורות כפולות")
    finally:
        teardown_a()
        teardown_b()


def test_assignment_rejects_unknown_targets() -> None:
    """אי אפשר להקצות אירוע שלא קיים, ואי אפשר להקצות למי שאינו טלפן."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        agent_id, _ = phone_agent(api)

        r = api.client.put(f"/admin/callers/{agent_id}/assignments", headers=admin,
                           json={"event_ids": [9_999_999]})
        assert r.status_code == 400, r.status_code

        owner_id = api.client.get("/admin/callers", headers=admin)  # נגיעה תמימה
        assert owner_id.status_code == 200
        from app import models
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            plain_user_id = db.get(models.Event, api.event_id).owner_id
        finally:
            db.close()
        r = api.client.put(f"/admin/callers/{plain_user_id}/assignments", headers=admin,
                           json={"event_ids": [api.event_id]})
        assert r.status_code == 404, r.status_code
        print("✓ הקצאה נדחית לאירוע לא קיים ולמשתמש שאינו טלפן")
    finally:
        teardown()


# ── 10–12. אבטחה (§8) ────────────────────────────────────────────────────

def test_caller_cannot_manage_callers_through_the_api() -> None:
    """(10)(11) טלפן לא יוצר טלפן, לא משנה תפקיד ולא מקצה לעצמו אירועים."""
    api, teardown = bootstrap()
    try:
        configure_track(api)
        agent_id, agent = phone_agent(api)

        # לא יוצר טלפן נוסף
        r = api.client.post("/admin/accounts", headers=agent, json={
            "email": _new_email(), "display_name": "טלפן מזויף",
            "account_type": "phone_agent", "new_password": "Test12345!",
        })
        assert r.status_code == 403, r.status_code

        # לא רואה ולא מנהל את מסך הטלפנים
        assert api.client.get("/admin/callers", headers=agent).status_code == 403

        # לא מקצה לעצמו אירועים
        r = api.client.put(f"/admin/callers/{agent_id}/assignments", headers=agent,
                           json={"event_ids": [api.event_id]})
        assert r.status_code == 403, r.status_code

        # לא הופך את עצמו לאדמין ולא משנה את סוג החשבון שלו
        r = api.client.patch(f"/admin/users/{agent_id}", headers=agent,
                             json={"is_admin": True, "account_type": "couple"})
        assert r.status_code == 403, r.status_code

        # וגם לא דרך עדכון הפרופיל האישי (השדות פשוט לא קיימים שם)
        r = api.client.patch("/auth/me", headers=agent, json={
            "display_name": "דנה", "account_type": "couple", "is_admin": True,
        })
        assert r.status_code == 200, r.text
        me = api.client.get("/auth/me", headers=agent).json()
        assert me["account_type"] == "phone_agent" and me["is_admin"] is False

        from app import models
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            assert db.query(models.CallAssignment).filter_by(user_id=agent_id).count() == 0
        finally:
            db.close()
        print("✓ טלפן לא יכול ליצור טלפן, לשנות תפקיד או להקצות לעצמו אירועים")
    finally:
        teardown()


def test_regular_user_cannot_create_or_manage_callers() -> None:
    """(12) בעל אירוע רגיל חסום מכל ניהול הטלפנים."""
    api, teardown = bootstrap()
    try:
        configure_track(api)
        agent_id, _ = phone_agent(api)
        plain = plain_headers(api)

        r = api.client.post("/admin/accounts", headers=plain, json={
            "email": _new_email(), "display_name": "טלפן מזויף",
            "account_type": "phone_agent", "new_password": "Test12345!",
        })
        assert r.status_code == 403, r.status_code
        assert api.client.get("/admin/callers", headers=plain).status_code == 403
        r = api.client.put(f"/admin/callers/{agent_id}/assignments", headers=plain,
                           json={"event_ids": [api.event_id]})
        assert r.status_code == 403, r.status_code
        print("✓ משתמש רגיל חסום מיצירה ומניהול של טלפנים")
    finally:
        teardown()


def test_caller_management_requires_authentication() -> None:
    """בלי טוקן בכלל — אין גישה לניהול הטלפנים."""
    api, teardown = bootstrap()
    try:
        agent_id, _ = phone_agent(api)
        assert api.client.get("/admin/callers").status_code in (401, 403)
        assert api.client.put(
            f"/admin/callers/{agent_id}/assignments", json={"event_ids": []},
        ).status_code in (401, 403)
        print("✓ ניהול טלפנים דורש אימות")
    finally:
        teardown()
