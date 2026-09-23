"""כללי המערכת, Overrides לאירוע, פיצ'רים — ושבלי הגדרות שום דבר לא משתנה."""
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402
from tests.call_center_helpers import configure_track  # noqa: E402


def setup_module(module) -> None:  # noqa: ARG001
    from app import call_ops, features, settings_registry

    call_ops.SYNC_TTL_SECONDS = 0
    settings_registry.CACHE_SECONDS = 0
    features.CACHE_SECONDS = 0


def teardown_function(fn) -> None:  # noqa: ARG001
    """כל בדיקה מנקה את ההגדרות שלה — ההגדרות גלובליות ומשפיעות על קבצים אחרים."""
    from app import features, models, settings_registry
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        for M in (models.SystemSetting, models.SettingOverride, models.FeatureFlag, models.FeatureRule):
            db.query(M).delete()
        db.commit()
    finally:
        db.close()
    settings_registry.invalidate()
    features.invalidate()


def _admin(role="super_admin"):
    from app import auth, models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        u = models.User(email=f"rules-{uuid.uuid4().hex[:8]}@veya.test", password_hash=auth.hash_password("Test12345!"),
                        display_name="אביב", is_admin=True, admin_role=role)
        db.add(u)
        db.commit()
        return {"Authorization": f"Bearer {auth.create_access_token(u)}"}
    finally:
        db.close()


def _event(event_id):
    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        e = db.get(models.Event, event_id)
        db.expunge(e)
        return e
    finally:
        db.close()


def test_no_settings_means_identical_schedule() -> None:
    api, _ = bootstrap()
    configure_track(api)
    from app import rsvp_timeline

    ev = _event(api.event_id)
    assert rsvp_timeline.policy_for(ev) == rsvp_timeline.DEFAULT_POLICY
    assert rsvp_timeline.policy_for(ev).max_rounds == 7


def test_system_rounds_change_is_applied_and_audited() -> None:
    api, _ = bootstrap()
    configure_track(api, days_to_event=16, commit_days=2, started_days_ago=0)
    admin = _admin()
    from app import rsvp_timeline

    r = api.client.put("/admin/rules", headers=admin, json={"changes": {"rsvp.max_rounds": 4}, "reason": "פחות סבבים"})
    assert r.status_code == 200, r.text
    ev = _event(api.event_id)
    sched = rsvp_timeline.compute_schedule(ev)
    kinds = ["P" if p.step["type"] == "call_round" else "W" for p in sched.placements]
    assert kinds == list(rsvp_timeline.SEQUENCES[4]), kinds
    assert sched.placements[-1].date == sched.commitment_date, "הסבב האחרון זז מיום הסגירה"

    log = api.client.get("/admin/audit?domain=settings", headers=admin).json()["items"][0]
    assert log["changes"] == [{"field": "rsvp.max_rounds", "label": "מספר סבבים מקסימלי", "before": "7 סבבים", "after": "4 סבבים"}]
    # חזרה לברירת המחדל מוחקת את השורה
    api.client.put("/admin/rules", headers=admin, json={"changes": {"rsvp.max_rounds": 7}})
    rows = [s for s in api.client.get("/admin/rules", headers=admin).json()["settings"] if s["key"] == "rsvp.max_rounds"]
    assert rows[0]["source"] == "code"


def test_event_override_source_and_reset() -> None:
    api, _ = bootstrap()
    configure_track(api, days_to_event=16, commit_days=2, started_days_ago=0)
    admin = _admin()
    r = api.client.put(f"/admin/rules/events/{api.event_id}", headers=admin,
                       json={"changes": {"rsvp.max_rounds": 2}, "reason": "בקשת הזוג"})
    assert r.status_code == 200, r.text
    row = next(s for s in r.json()["settings"] if s["key"] == "rsvp.max_rounds")
    assert (row["value"], row["source"], row["system_value"]) == (2, "event", 7)
    from app import rsvp_timeline

    sched = rsvp_timeline.compute_schedule(_event(api.event_id))
    assert [p.step["type"] for p in sched.placements] == ["whatsapp_first", "call_round"]

    r = api.client.put(f"/admin/rules/events/{api.event_id}", headers=admin,
                       json={"changes": {"rsvp.max_rounds": None}})
    row = next(s for s in r.json()["settings"] if s["key"] == "rsvp.max_rounds")
    assert (row["value"], row["source"]) == (7, "code")


def test_retired_round_settings_are_converted() -> None:
    """"מספר תזכורות" + "מספר סבבי טלפונים" (ישנות) → "מספר סבבים מקסימלי"."""
    api, _ = bootstrap()
    from app import main, models, settings_registry as sr
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        db.add(models.SystemSetting(key="calls.rounds", value=2))
        db.add(models.SettingOverride(scope_type="event", scope_id=api.event_id,
                                      key="rsvp.whatsapp_reminders", value=1))
        db.commit()
    finally:
        db.close()
    main._migrate_rsvp_round_settings()
    main._migrate_rsvp_round_settings()  # idempotent
    sr.invalidate()
    assert sr.value("rsvp.max_rounds") == 1 + 3 + 2
    assert sr.value("rsvp.max_rounds", api.event_id) == 1 + 1 + 3
    db = SessionLocal()
    try:
        from sqlalchemy import select

        left = db.scalars(select(models.SettingOverride.key)).all() + db.scalars(select(models.SystemSetting.key)).all()
        assert not set(left) & set(sr.RETIRED_ROUND_KEYS), left
    finally:
        db.close()


def test_permissions_for_rules() -> None:
    api, _ = bootstrap()
    support, admin_role = _admin("support"), _admin("admin")
    assert api.client.get("/admin/rules", headers=support).status_code == 200
    assert api.client.put("/admin/rules", headers=support, json={"changes": {"rsvp.max_rounds": 2}}).status_code == 403
    r = api.client.put("/admin/rules", headers=admin_role, json={"changes": {"whatsapp.emergency_stop": True}})
    assert r.status_code == 403, "Admin (לא Super) הפעיל עצירת חירום"
    r = api.client.put("/admin/rules", headers=admin_role, json={"changes": {"whatsapp.mode": "live"}})
    assert r.status_code == 400, "הגדרה שלא מחוברת נשמרה"
    r = api.client.put("/admin/rules", headers=admin_role, json={"changes": {"rsvp.max_rounds": 9}})
    assert r.status_code == 400


def test_emergency_stop_blocks_every_send() -> None:
    api, _ = bootstrap()
    admin = _admin()
    from app import messaging

    assert api.client.put("/admin/rules", headers=admin, json={"changes": {"whatsapp.emergency_stop": True}}).status_code == 200
    res = messaging.get_provider().send_invitation("0501234567", "בדיקה")
    assert res.ok is False and res.status == "failed" and "עצירת חירום" in res.detail
    api.client.put("/admin/rules", headers=admin, json={"changes": {"whatsapp.emergency_stop": False}})
    assert messaging.get_provider().send_invitation("0501234567", "בדיקה").ok is True


def test_gift_rule_for_single_event() -> None:
    api, _ = bootstrap()
    admin, admin_role = _admin(), _admin("admin")
    from app import gift_eligibility

    before = gift_eligibility.resolve(_event(api.event_id))
    r = api.client.post("/admin/features/gifts/rules", headers=admin_role,
                        json={"scope_type": "event", "scope_id": api.event_id, "enabled": True})
    assert r.status_code == 403, "Admin פתח שירות כסף"
    r = api.client.post("/admin/features/gifts/rules", headers=admin,
                        json={"scope_type": "event", "scope_id": api.event_id, "enabled": True, "note": "פיילוט"})
    assert r.status_code == 201, r.text
    d = gift_eligibility.resolve(_event(api.event_id))
    assert d.eligible is True and d.source == "admin_features"
    rule_id = next(f for f in r.json()["features"] if f["key"] == "gifts")["rules"][0]["id"]
    api.client.delete(f"/admin/features/gifts/rules/{rule_id}", headers=admin)
    assert gift_eligibility.resolve(_event(api.event_id)).source == before.source


def test_calls_off_for_event_creates_no_tasks() -> None:
    api, _ = bootstrap()
    api.add_guest("אורח", "0501119999")
    configure_track(api)
    admin = _admin()
    r = api.client.post("/admin/features/calls/rules", headers=admin,
                        json={"scope_type": "event", "scope_id": api.event_id, "enabled": False})
    assert r.status_code == 201, r.text
    from app import call_ops, models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        call_ops.sync(db, event_ids={api.event_id}, force=True)
        db.commit()
        assert db.query(models.CallTask).filter(models.CallTask.event_id == api.event_id).count() == 0
    finally:
        db.close()


def test_uncontrollable_feature_rejected_and_custom_flag() -> None:
    api, _ = bootstrap()
    admin = _admin()
    assert api.client.put("/admin/features/seating", headers=admin, json={"status": "off"}).status_code == 400
    r = api.client.post("/admin/features", headers=admin, json={"key": "photo_album", "label": "אלבום תמונות"})
    assert r.status_code == 201, r.text
    row = next(f for f in r.json()["features"] if f["key"] == "photo_album")
    assert row["builtin"] is False and row["consumed"] is False and row["status"] == "off"
    assert api.client.post("/admin/features", headers=admin, json={"key": "Bad Key", "label": "x"}).status_code in (400, 422)


def teardown_module(module) -> None:  # noqa: ARG001
    from app import call_ops, features, settings_registry

    # מחזירים את המטמון — אחרת כל קובץ בדיקות שרץ אחרי זה פונה למסד בכל חישוב לוח זמנים.
    settings_registry.CACHE_SECONDS = 30
    features.CACHE_SECONDS = 30
    call_ops.SYNC_TTL_SECONDS = 45
    settings_registry.invalidate()
    features.invalidate()
    shutdown()


_ = datetime
