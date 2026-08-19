"""רגרסיה 5+6 — בידוד בין לקוחות (multi-tenant) והרשאות ל-Call Center.

שתי שכבות הגנה נבדקות כאן:

1. **שכבת ה-API** (הנבדקת בקובץ הזה, על SQLite): כל נקודות הקצה של
   ``/admin/call-center`` חסומות ל-``get_current_admin`` בלבד, ואין לבעל
   אירוע שום דרך להגיע ליומן השיחות של אירוע אחר — כי אין לו בכלל endpoint
   כזה.
2. **שכבת ה-RLS** (Postgres): ``backend/rls/06_call_logs_rls.sql``. RLS הוא
   no-op ב-SQLite, ולכן **אי אפשר לאמת אותו כאן** — האימות שלו נעשה מול
   Supabase (ראו ``rls/STAGING_PLAN.md``). הבדיקות כאן מוודאות שהשכבה
   הראשונה מחזיקה גם בלי RLS.

בנוסף נבדק שאין רשומות יתומות: מחיקת אירוע/מוזמן מנקה את יומן השיחות.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402
from tests.call_center_helpers import (  # noqa: E402
    call_logs_of,
    configure_track,
    plain_headers,
    standalone_admin,
)

CALL_CENTER_ENDPOINTS = [
    ("GET", "/admin/call-center"),
    ("GET", "/admin/call-center/queue"),
]


def _all_call_logs() -> list:
    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        rows = db.query(models.CallLog).all()
        for r in rows:
            db.expunge(r)
        return rows
    finally:
        db.close()


def test_regular_user_is_blocked_from_every_call_center_endpoint() -> None:
    """משתמש רגיל (בעל אירוע) מקבל 403 מכל נקודות הקצה, כולל הפעולות."""
    api, teardown = bootstrap()
    try:
        configure_track(api)
        guest = api.add_guest("אורח", "0509000001", party_size=1)
        # בעל האירוע — משתמש רגיל, בלי הרשאת אדמין.
        plain = plain_headers(api)

        for method, path in CALL_CENTER_ENDPOINTS:
            r = api.client.request(method, path, headers=plain)
            assert r.status_code == 403, f"{method} {path} → {r.status_code}"

        r = api.client.get(f"/admin/call-center/guests/{guest['id']}", headers=plain)
        assert r.status_code == 403, r.status_code
        r = api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                            headers=plain, json={"outcome": "no_answer"})
        assert r.status_code == 403, r.status_code
        # ובאמת לא נכתב כלום.
        assert call_logs_of(api, guest["id"]) == []
        print("✓ משתמש רגיל חסום מכל נקודות הקצה של Call Center")
    finally:
        teardown()


def test_no_auth_is_rejected() -> None:
    """בלי טוקן בכלל — אין גישה."""
    api, teardown = bootstrap()
    try:
        for method, path in CALL_CENTER_ENDPOINTS:
            r = api.client.request(method, path)
            assert r.status_code in (401, 403), f"{method} {path} → {r.status_code}"
        print("✓ גישה ללא אימות נדחית")
    finally:
        teardown()


def test_two_tenants_do_not_leak_guests_or_call_logs() -> None:
    """User A ו-User B — אין דליפה לשום כיוון."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        configure_track(api_a)
        configure_track(api_b)
        guest_a = api_a.add_guest("אורח של A", "0509000002", party_size=2)
        guest_b = api_b.add_guest("אורח של B", "0509000003", party_size=2)

        # אדמין (משתמש נפרד) מתעד שיחה בכל אירוע.
        admin = standalone_admin(api_a)
        api_a.client.post(f"/admin/call-center/guests/{guest_a['id']}/outcome",
                          headers=admin, json={"outcome": "no_answer"})
        api_a.client.post(f"/admin/call-center/guests/{guest_b['id']}/outcome",
                          headers=admin, json={"outcome": "busy"})

        # --- A לא רואה מוזמנים של B ---
        rows_a = api_a.client.get("/guests", headers=api_a.headers).json()["items"]
        assert [g["full_name"] for g in rows_a] == ["אורח של A"]
        rows_b = api_b.client.get("/guests", headers=api_b.headers).json()["items"]
        assert [g["full_name"] for g in rows_b] == ["אורח של B"]

        # --- A לא יכול לשלוף מוזמן של B דרך X-Event-Id מזויף ---
        spoof = dict(api_a.headers)
        spoof["X-Event-Id"] = str(api_b.event_id)
        r = api_a.client.get("/guests", headers=spoof)
        assert r.status_code in (403, 404), f"A הצליח לגשת לאירוע של B: {r.status_code}"

        # --- ליומן השיחות אין בכלל endpoint לבעל אירוע ---
        b_plain = plain_headers(api_b)
        r = api_b.client.get(f"/admin/call-center/guests/{guest_a['id']}", headers=b_plain)
        assert r.status_code == 403

        # --- כל שיחה נרשמה לאירוע הנכון ---
        log_a = call_logs_of(api_a, guest_a["id"])[0]
        log_b = call_logs_of(api_b, guest_b["id"])[0]
        assert log_a.event_id == api_a.event_id and log_a.outcome == "no_answer"
        assert log_b.event_id == api_b.event_id and log_b.outcome == "busy"
        print("✓ אין דליפת מוזמנים או יומני שיחות בין שני לקוחות")
    finally:
        teardown_a()
        teardown_b()


def test_queue_filter_cannot_mix_events() -> None:
    """סינון לפי אירוע מחזיר רק את המוזמנים של אותו אירוע."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        configure_track(api_a)
        configure_track(api_b)
        api_a.add_guest("רק של A", "0509000004", party_size=1)
        api_b.add_guest("רק של B", "0509000005", party_size=1)
        admin = standalone_admin(api_a)

        qa = api_a.client.get("/admin/call-center/queue", headers=admin,
                              params={"event_id": api_a.event_id}).json()
        qb = api_a.client.get("/admin/call-center/queue", headers=admin,
                              params={"event_id": api_b.event_id}).json()
        assert [g["full_name"] for g in qa["items"]] == ["רק של A"]
        assert [g["full_name"] for g in qb["items"]] == ["רק של B"]
        assert all(g["event_id"] == api_a.event_id for g in qa["items"])
        assert all(g["event_id"] == api_b.event_id for g in qb["items"])
        print("✓ סינון לפי אירוע לא מערבב בין אירועים")
    finally:
        teardown_a()
        teardown_b()


def test_deleting_a_guest_removes_its_call_logs() -> None:
    """מחיקת מוזמן מנקה את יומן השיחות שלו — בלי רשומות יתומות."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("יימחק", "0509000006", party_size=1)
        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=admin, json={"outcome": "no_answer"})
        assert len(call_logs_of(api, guest["id"])) == 1

        r = api.client.delete(f"/guests/{guest['id']}", headers=api.headers)
        assert r.status_code == 204, r.text
        assert call_logs_of(api, guest["id"]) == []
        print("✓ מחיקת מוזמן מנקה את יומן השיחות שלו")
    finally:
        teardown()


def test_deleting_an_event_removes_its_call_logs() -> None:
    """מחיקת אירוע מנקה את כל יומני השיחות שלו, ולא נוגעת באירוע אחר."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        admin = standalone_admin(api_a)
        configure_track(api_a)
        configure_track(api_b)
        guest_a = api_a.add_guest("של A", "0509000007", party_size=1)
        guest_b = api_b.add_guest("של B", "0509000008", party_size=1)
        api_a.client.post(f"/admin/call-center/guests/{guest_a['id']}/outcome",
                          headers=admin, json={"outcome": "busy"})
        api_a.client.post(f"/admin/call-center/guests/{guest_b['id']}/outcome",
                          headers=admin, json={"outcome": "busy"})

        before = {lg.id for lg in _all_call_logs()}
        assert len(before) >= 2

        r = api_a.client.delete(f"/events/{api_a.event_id}", headers=api_a.headers)
        assert r.status_code in (200, 204), r.text

        remaining = _all_call_logs()
        assert all(lg.event_id != api_a.event_id for lg in remaining), "נשארו רשומות יתומות"
        assert any(lg.event_id == api_b.event_id for lg in remaining), "נמחקו רשומות של אירוע אחר"
        print("✓ מחיקת אירוע מנקה רק את יומני השיחות שלו")
    finally:
        teardown_a()
        teardown_b()


def test_no_orphan_call_logs_anywhere() -> None:
    """בדיקת שפיות כוללת: אין רשומת שיחה שמצביעה על אירוע/מוזמן שלא קיים."""
    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        event_ids = {e.id for e in db.query(models.Event.id).all()}
        guest_ids = {g.id for g in db.query(models.Guest.id).all()}
        orphans = [
            (lg.id, lg.event_id, lg.guest_id)
            for lg in db.query(models.CallLog).all()
            if lg.event_id not in event_ids or lg.guest_id not in guest_ids
        ]
        assert orphans == [], f"נמצאו רשומות יתומות: {orphans}"
        print("✓ אין רשומות יתומות ב-call_logs")
    finally:
        db.close()


if __name__ == "__main__":
    try:
        test_regular_user_is_blocked_from_every_call_center_endpoint()
        test_no_auth_is_rejected()
        test_two_tenants_do_not_leak_guests_or_call_logs()
        test_queue_filter_cannot_mix_events()
        test_deleting_a_guest_removes_its_call_logs()
        test_deleting_an_event_removes_its_call_logs()
        test_no_orphan_call_logs_anywhere()
    finally:
        shutdown()
