"""תפקיד "טלפן" (``phone_agent``) — בדיקות הרשאה מלאות ברמת ה-API.

הבדיקות כאן לא נוגעות ב-UI בכלל: הן קוראות ל-endpoints ישירות עם טוקן של
טלפן, בדיוק כמו שתוקף (או משתמש סקרן עם DevTools) היה עושה. הסתרת כפתור
במסך אינה הרשאה — מה שנבדק כאן הוא הגדר עצמה.

מבנה:
1. מה שטלפן **כן** רשאי — ששת סוגי תוצאות השיחה + צפייה בתור ובכרטיס.
2. מה שטלפן **לא** רשאי — כל שאר המערכת, אחד-אחד, לפי §15 באפיון.
3. סריקת-רוחב אוטומטית על **כל** נתיבי ה-API: אם מישהו יוסיף בעתיד endpoint
   חדש שדולף לטלפן, הבדיקה הזו תיפול בלי שיצטרכו לזכור לעדכן רשימה.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap  # noqa: E402
from tests.call_center_helpers import (  # noqa: E402
    call_logs_of,
    configure_track,
    guest_of,
    phone_agent,
)


# ── 1. מה שטלפן כן רשאי לעשות ────────────────────────────────────────────

def test_phone_agent_sees_the_call_queue() -> None:
    """טלפן רואה את מסך "שיחות להיום" — סקירה, תור וכרטיס מוזמן."""
    api, teardown = bootstrap()
    try:
        configure_track(api)
        guest = api.add_guest("ישראל כהן", "0509100001", party_size=3)
        _, agent = phone_agent(api)

        overview = api.client.get("/admin/call-center", headers=agent)
        assert overview.status_code == 200, overview.text
        assert overview.json()["waiting"] >= 1

        queue = api.client.get(
            "/admin/call-center/queue", headers=agent,
            params={"event_id": api.event_id},
        )
        assert queue.status_code == 200, queue.text
        names = [g["full_name"] for g in queue.json()["items"]]
        assert "ישראל כהן" in names
        # כל מה שדרוש לשיחה מגיע בשורה עצמה — שם, טלפון, כמות, אירוע, סבב.
        row = next(g for g in queue.json()["items"] if g["full_name"] == "ישראל כהן")
        assert row["phone"] == "0509100001"
        assert row["party_size"] == 3
        assert row["event_hosts"] and row["event_date"]
        assert row["round_number"] >= 1

        detail = api.client.get(f"/admin/call-center/guests/{guest['id']}", headers=agent)
        assert detail.status_code == 200, detail.text
        assert detail.json()["full_name"] == "ישראל כהן"
        print("✓ טלפן רואה את תור השיחות ואת כרטיס המוזמן")
    finally:
        teardown()


def test_phone_agent_can_record_every_outcome() -> None:
    """כל שש תוצאות השיחה מותרות לטלפן, ונרשמות ליומן השיחות."""
    api, teardown = bootstrap()
    try:
        configure_track(api)
        _, agent = phone_agent(api)
        cases = [
            ("confirmed", {"count": 3}),
            ("declined", {}),
            ("no_answer", {}),
            ("busy", {}),
            ("wrong_number", {}),
            ("callback", {"callback_at": "2099-01-01T10:00:00"}),
        ]
        for i, (outcome, extra) in enumerate(cases):
            guest = api.add_guest(f"מוזמן {i}", f"05091001{i:02d}", party_size=4)
            body = {"outcome": outcome}
            body.update(extra)
            r = api.client.post(
                f"/admin/call-center/guests/{guest['id']}/outcome",
                headers=agent, json=body,
            )
            assert r.status_code == 200, f"{outcome} → {r.status_code}: {r.text}"
            logs = call_logs_of(api, guest["id"])
            assert len(logs) == 1 and logs[0].outcome == outcome
        print("✓ טלפן רשאי לתעד את כל שש תוצאות השיחה")
    finally:
        teardown()


def test_phone_agent_confirm_updates_rsvp_through_the_shared_logic() -> None:
    """אישור הגעה של טלפן מעדכן את אותה שורת מוזמן שבעל/ת האירוע רואה."""
    api, teardown = bootstrap()
    try:
        configure_track(api)
        guest = api.add_guest("רותם ברק", "0509100020", party_size=5)
        _, agent = phone_agent(api)

        r = api.client.post(
            f"/admin/call-center/guests/{guest['id']}/outcome",
            headers=agent, json={"outcome": "confirmed", "count": 2},
        )
        assert r.status_code == 200, r.text
        after = guest_of(api, guest["id"])
        assert after.rsvp_status == "confirmed" and after.confirmed_count == 2

        # ובעל/ת האירוע רואה/ת את אותו נתון בדיוק במסך שלו/ה.
        rows = api.client.get("/guests", headers=api.headers).json()["items"]
        mine = next(g for g in rows if g["id"] == guest["id"])
        assert mine["rsvp_status"] == "confirmed" and mine["confirmed_count"] == 2
        print("✓ אישור הגעה של טלפן מגיע מיד לבעל/ת האירוע")
    finally:
        teardown()


def test_phone_agent_wrong_number_raises_the_owner_alert() -> None:
    """סימון "מספר שגוי" ע"י טלפן פותח את התראת תיקון המספר אצל הבעלים."""
    api, teardown = bootstrap()
    try:
        configure_track(api)
        guest = api.add_guest("עמית גל", "0509100030", party_size=1)
        _, agent = phone_agent(api)

        r = api.client.post(
            f"/admin/call-center/guests/{guest['id']}/outcome",
            headers=agent, json={"outcome": "wrong_number"},
        )
        assert r.status_code == 200, r.text

        alerts = api.client.get("/guests/data-alerts", headers=api.headers)
        assert alerts.status_code == 200, alerts.text
        ids = [a["guest_id"] for a in alerts.json()["phone_fix"]]
        assert guest["id"] in ids
        # סטטוס אישור ההגעה לא נגע — זו התראת דאטה, לא תשובה של המוזמן.
        assert guest_of(api, guest["id"]).rsvp_status == "pending"
        print("✓ 'מספר שגוי' של טלפן פותח התראה לבעל/ת האירוע, בלי לשנות RSVP")
    finally:
        teardown()


def test_phone_agent_can_manage_own_account() -> None:
    """"החשבון שלי" נשאר פתוח — זה כל מה שיש לטלפן מלבד מסך השיחות."""
    api, teardown = bootstrap()
    try:
        _, agent = phone_agent(api)
        me = api.client.get("/auth/me", headers=agent)
        assert me.status_code == 200, me.text
        assert me.json()["account_type"] == "phone_agent"
        assert me.json()["is_admin"] is False

        patched = api.client.patch(
            "/auth/me", headers=agent, json={"display_name": "דנה מוקד"},
        )
        assert patched.status_code == 200, patched.text
        print("✓ טלפן יכול לצפות ולערוך את החשבון שלו בלבד")
    finally:
        teardown()


# ── 2. מה שטלפן לא רשאי לעשות (§15 באפיון) ───────────────────────────────

def test_phone_agent_is_blocked_from_every_management_area() -> None:
    """מטריצת החסימות המלאה — ניסיון גישה ישיר ל-API, לא דרך ה-UI."""
    api, teardown = bootstrap()
    try:
        configure_track(api)
        guest = api.add_guest("לא נגיש", "0509100040", party_size=2)
        _, agent = phone_agent(api)
        scoped = dict(agent)
        scoped["X-Event-Id"] = str(api.event_id)

        blocked = [
            # פאנל האדמין המלא
            ("GET", "/admin/dashboard", None),
            ("GET", "/admin/users", None),
            ("GET", "/admin/events", None),
            ("PATCH", "/admin/users/1", {"display_name": "פריצה"}),
            # ניהול אירועים
            ("GET", "/events", None),
            ("POST", "/events", {"groom_name": "א", "bride_name": "ב"}),
            ("DELETE", f"/events/{api.event_id}", None),
            ("PATCH", "/event", {"venue_name": "אולם אחר"}),
            ("GET", "/event/audit", None),
            # ניהול מוזמנים
            ("GET", "/guests", None),
            ("POST", "/guests", {"full_name": "חדש", "phone": "0509100099"}),
            ("PATCH", f"/guests/{guest['id']}", {"phone": "0501111111"}),
            ("DELETE", f"/guests/{guest['id']}", None),
            ("GET", "/guests/data-alerts", None),
            # הושבה ואולם
            ("GET", "/hall", None),
            ("POST", "/seating/generate", {}),
            # הודעות ו-WhatsApp
            ("GET", "/messages", None),
            ("POST", "/invitations/send", {}),
            ("GET", "/communication/sequence", None),
            ("GET", "/communication/library", None),
            # Workflow / אוטומציה
            ("GET", "/automation/timeline", None),
            ("POST", "/automation/track/activate", {}),
            # חברי-אירוע ואולמות
            ("GET", "/event-members?event_id=1", None),
            ("GET", "/venues/search?q=אולם", None),
            # סטטיסטיקות
            ("GET", "/stats", None),
        ]
        for method, path, body in blocked:
            r = api.client.request(method, path, headers=scoped, json=body)
            assert r.status_code in (403, 404), f"{method} {path} → {r.status_code}: {r.text[:120]}"
            assert r.status_code != 200
        print(f"✓ טלפן חסום מ-{len(blocked)} נקודות ניהול (בדיקה ישירה מול ה-API)")
    finally:
        teardown()


def test_phone_agent_cannot_change_a_guest_phone_number() -> None:
    """הבדיקה המפורשת מ-§5: הטלפן מסמן "מספר שגוי" אך לא מתקן אותו בעצמו."""
    api, teardown = bootstrap()
    try:
        configure_track(api)
        guest = api.add_guest("מספר שמור", "0509100050", party_size=1)
        _, agent = phone_agent(api)
        scoped = dict(agent)
        scoped["X-Event-Id"] = str(api.event_id)

        r = api.client.patch(
            f"/guests/{guest['id']}", headers=scoped, json={"phone": "0500000000"},
        )
        assert r.status_code in (403, 404), r.status_code
        assert guest_of(api, guest["id"]).phone == "0509100050", "המספר שונה ע\"י טלפן"

        # אבל כן מותר לו לדווח שהמספר שגוי.
        ok = api.client.post(
            f"/admin/call-center/guests/{guest['id']}/outcome",
            headers=agent, json={"outcome": "wrong_number"},
        )
        assert ok.status_code == 200, ok.text
        print("✓ טלפן מדווח על מספר שגוי אך לא יכול לשנות אותו")
    finally:
        teardown()


def test_phone_agent_cannot_escalate_through_a_self_owned_event() -> None:
    """חור אפשרי שנסגר: טלפן שיוצר אירוע משלו ונכנס דרכו לממשק הבעלים.

    יצירת אירוע חסומה, וגם אם קיים אירוע בבעלותו (למשל משתמש קיים שהוסב
    לתפקיד טלפן) — ``EventAccess`` דוחה אותו לפני בדיקת הבעלות.
    """
    api, teardown = bootstrap()
    try:
        agent_id, agent = phone_agent(api)
        r = api.client.post(
            "/events", headers=agent, json={"groom_name": "א", "bride_name": "ב"},
        )
        assert r.status_code == 403, r.status_code

        # מדמים משתמש שהוסב לטלפן ונשאר בעלים של אירוע קיים.
        from app import models
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            event = db.get(models.Event, api.event_id)
            original_owner = event.owner_id
            event.owner_id = agent_id
            db.commit()
        finally:
            db.close()

        owned = dict(agent)
        owned["X-Event-Id"] = str(api.event_id)
        assert api.client.get("/guests", headers=owned).status_code == 403
        assert api.client.get("/hall", headers=owned).status_code == 403
        assert api.client.get("/automation/timeline", headers=owned).status_code == 403

        db = SessionLocal()
        try:
            db.get(models.Event, api.event_id).owner_id = original_owner
            db.commit()
        finally:
            db.close()
        print("✓ טלפן לא מקבל ממשק בעלים גם כשהאירוע רשום עליו")
    finally:
        teardown()


def test_admin_cannot_create_a_hybrid_admin_phone_agent() -> None:
    """אי אפשר להגדיר משתמש גם כאדמין וגם כטלפן — שילוב חסר משמעות."""
    api, teardown = bootstrap()
    try:
        from tests.call_center_helpers import standalone_admin

        admin = standalone_admin(api)
        agent_id, _ = phone_agent(api)
        r = api.client.patch(
            f"/admin/users/{agent_id}", headers=admin, json={"is_admin": True},
        )
        assert r.status_code == 400, r.text
        assert "טלפן" in r.json()["detail"]
        print("✓ לא ניתן להגדיר משתמש גם כאדמין וגם כטלפן")
    finally:
        teardown()


# ── 3. סריקת-רוחב: אף נתיב מחוץ לרשימת ההיתר לא מחזיר 200 לטלפן ─────────

# הנתיבים שטלפן אמור להצליח בהם. כל השאר חייב להיחסם.
ALLOWED_PREFIXES = (
    "/admin/call-center",   # מסך השיחות — כל תפקידו
    "/auth/",               # החשבון שלי (me / logout / שינוי סיסמה)
    "/legal",               # מסמכים משפטיים ציבוריים
    "/health",
    # דפי התיעוד האוטומטיים של FastAPI — סטטיים, זהים לכל מבקר, ואינם
    # חושפים נתונים. חסימתם היא החלטת פריסה (VEYA_ENV), לא הרשאת תפקיד.
    "/docs",
    "/redoc",
)


def test_no_unlisted_endpoint_answers_a_phone_agent() -> None:
    """סורק את כל נתיבי ה-GET של האפליקציה ומוודא שאף אחד מחוץ לרשימת ההיתר
    לא מחזיר 200 לטלפן.

    רק GET בכוונה: זו הבדיקה הרחבה ("מה דולף"), והפעולות המשנות נבדקות
    מפורשות למעלה עם גוף בקשה אמיתי. הבדיקה נועדה לתפוס endpoint **חדש**
    שיתווסף בעתיד בלי הרשאה מתאימה.
    """
    api, teardown = bootstrap()
    try:
        configure_track(api)
        api.add_guest("סריקה", "0509100060", party_size=1)
        _, agent = phone_agent(api)
        scoped = dict(agent)
        scoped["X-Event-Id"] = str(api.event_id)

        from app.main import app

        leaked = []
        checked = 0
        for route in app.routes:
            path = getattr(route, "path", "")
            methods = getattr(route, "methods", set()) or set()
            if "GET" not in methods or not path.startswith("/"):
                continue
            if path.startswith(ALLOWED_PREFIXES) or path in ("/", "/openapi.json"):
                continue
            # פרמטרי נתיב → ערך אמיתי מהאירוע של הבדיקה.
            concrete = path.replace("{event_id}", str(api.event_id))
            if "{" in concrete.replace("{event_id}", ""):
                concrete = concrete.replace("{user_id}", "1").replace("{guest_id}", "1")
                concrete = concrete.replace("{member_id}", "1").replace("{message_id}", "1")
            if "{" in concrete:
                continue  # פרמטר שלא ידענו למלא — נבדק מפורשות למעלה
            r = api.client.get(concrete, headers=scoped)
            checked += 1
            if r.status_code == 200:
                leaked.append(f"{concrete} → 200")
        assert not leaked, "נתיבים שדלפו לטלפן: " + ", ".join(leaked)
        assert checked > 15, f"הסריקה בדקה רק {checked} נתיבים — כנראה לא רצה כמו שצריך"
        print(f"✓ סריקת {checked} נתיבי GET — אף אחד מחוץ לרשימת ההיתר לא נענה לטלפן")
    finally:
        teardown()
