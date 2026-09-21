"""מסחר: גרסאות מסלול לא דורסות היסטוריה, עמלה נשלטת ומדויקת, מסלול פותח פיצ'רים."""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


def setup_module(module) -> None:  # noqa: ARG001
    from app import commerce, features

    commerce.CACHE_SECONDS = 0
    features.CACHE_SECONDS = 0


def teardown_module(module) -> None:  # noqa: ARG001
    from app import commerce, features

    # קובץ ה-DB הזמני נמחק ב-shutdown; רק מחזירים את המטמונים למצב רגיל
    # כדי שהעמלה/הזכאויות שנקבעו כאן לא ידלפו לקובץ הבדיקות הבא.
    commerce.CACHE_SECONDS = 30
    features.CACHE_SECONDS = 30
    commerce.invalidate()
    features.invalidate()
    shutdown()


def _admin(role="super_admin"):
    from app import auth, models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        u = models.User(email=f"com-{uuid.uuid4().hex[:8]}@veya.test", password_hash=auth.hash_password("Test12345!"),
                        display_name="אביב", is_admin=True, admin_role=role)
        db.add(u)
        db.commit()
        return {"Authorization": f"Bearer {auth.create_access_token(u)}"}
    finally:
        db.close()


def test_price_change_is_a_new_version_existing_event_keeps_old() -> None:
    api, _ = bootstrap()
    admin = _admin()
    key = f"plus_{uuid.uuid4().hex[:5]}"
    p = api.client.post("/admin/commerce/plans", headers=admin, json={
        "key": key, "name": "Plus", "price_agorot": 29900, "features": ["calls"],
    })
    assert p.status_code == 201, p.text
    plan = p.json()
    v1 = plan["current"]["id"]
    ent = api.client.post("/admin/commerce/subscriptions", headers=admin,
                          json={"event_id": api.event_id, "plan_version_id": v1})
    assert ent.status_code == 201, ent.text

    r = api.client.post(f"/admin/commerce/plans/{plan['id']}/versions", headers=admin, json={
        "price_agorot": 34900, "features": ["calls"], "change_note": "עליית מחיר",
    })
    assert r.status_code == 201
    body = r.json()
    assert [v["version"] for v in body["versions"]] == [2, 1]
    assert body["current"]["price_agorot"] == 34900

    subs = api.client.get(f"/admin/commerce/subscriptions?q={api.event_id}", headers=admin).json()["items"][0]
    assert (subs["version"], subs["price_agorot"], subs["on_old_version"]) == (1, 29900, True)

    log = api.client.get(f"/admin/audit?target_type=plan&target_id={plan['id']}", headers=admin).json()["items"][0]
    assert log["changes"][0]["before"] == "₪299 (v1)" and log["changes"][0]["after"] == "₪349 (v2)"
    api.client.post(f"/admin/commerce/subscriptions/{subs['id']}/status", headers=admin,
                    json={"status": "cancelled", "reason": "סוף בדיקה"})


def test_gift_fee_rule_changes_quote_exactly() -> None:
    api, _ = bootstrap()
    admin, admin_role = _admin(), _admin("admin")
    from app import commerce, gift

    # מסד הבדיקות משותף בין ריצות — מתחילים תמיד מ-4%
    api.client.put("/admin/commerce/fees/gift", headers=admin, json={"percent_bp": 400, "reason": "איפוס לפני בדיקה"})
    commerce.invalidate()
    assert gift.fee_for(50000) == 2000
    assert api.client.put("/admin/commerce/fees/gift", headers=admin_role,
                          json={"percent_bp": 350, "reason": "ניסיון"}).status_code == 403
    r = api.client.put("/admin/commerce/fees/gift", headers=admin, json={
        "percent_bp": 350, "fixed_agorot": 100, "max_agorot": 3000, "reason": "הורדת עמלה",
    })
    assert r.status_code == 200, r.text
    commerce.invalidate()
    assert gift.fee_for(50000) == 1850          # 3.5% = 1750 + ₪1
    assert gift.fee_for(200000) == 3000         # תקרה
    q = gift.quote(50000)
    assert q.total_agorot == 51850 and q.fee_percent == 3.5
    log = api.client.get("/admin/audit?domain=commerce", headers=admin).json()["items"][0]
    assert log["changes"][0]["before"] == "4%" and log["changes"][0]["after"].startswith("3.5%")

    history = r.json()["history"]
    assert history[0]["active"] and history[0]["percent_bp"] == 350
    # חזרה ל-4% — זהה בדיוק לברירת המחדל, כדי לא לזלוג לקבצי בדיקה אחרים
    api.client.put("/admin/commerce/fees/gift", headers=admin, json={"percent_bp": 400, "reason": "חזרה לברירת מחדל"})
    commerce.invalidate()
    assert gift.fee_for(10000) == 400 and gift.quote(10000).fee_percent == 4


def test_plan_opens_beta_feature_for_its_event_only() -> None:
    api, _ = bootstrap()
    other, _ = bootstrap()
    admin = _admin()
    from app import features, models
    from app.database import SessionLocal

    assert api.client.post("/admin/features", headers=admin, json={"key": f"album_{uuid.uuid4().hex[:4]}", "label": "אלבום"}).status_code == 201
    key = next(f["key"] for f in api.client.get("/admin/features", headers=admin).json()["features"] if f["label"] == "אלבום")
    assert api.client.post("/admin/commerce/addons", headers=admin,
                           json={"key": f"a_{key}", "name": "אלבום תמונות", "price_agorot": 9900, "feature_key": "calls"}).status_code == 201
    plan = api.client.post("/admin/commerce/plans", headers=admin, json={
        "key": f"prem_{uuid.uuid4().hex[:4]}", "name": "Premium", "price_agorot": 49900, "features": ["gifts"],
    }).json()
    api.client.put("/admin/features/gifts", headers=admin, json={"status": "beta", "reason": "רק לפרימיום"})
    ent = api.client.post("/admin/commerce/subscriptions", headers=admin,
                          json={"event_id": api.event_id, "plan_version_id": plan["current"]["id"]}).json()
    db = SessionLocal()
    try:
        mine, theirs = db.get(models.Event, api.event_id), db.get(models.Event, other.event_id)
        features.invalidate()
        assert features.decide("gifts", mine).enabled is True and features.decide("gifts", mine).source == "plan"
        assert features.decide("gifts", theirs).enabled is False
    finally:
        db.close()
        api.client.post(f"/admin/commerce/subscriptions/{ent['id']}/status", headers=admin,
                        json={"status": "cancelled", "reason": "סוף בדיקה"})
        db2 = SessionLocal()
        db2.query(models.FeatureFlag).filter(models.FeatureFlag.key.in_(("gifts", key))).delete()
        db2.commit()
        db2.close()
        features.invalidate()


def test_coupon_validation_and_permissions() -> None:
    api, _ = bootstrap()
    admin, support = _admin(), _admin("support")
    assert api.client.get("/admin/commerce/plans", headers=support).status_code == 403
    code = f"WED{uuid.uuid4().hex[:4].upper()}"
    assert api.client.post("/admin/commerce/coupons", headers=admin, json={"code": code, "kind": "percent", "value": 150}).status_code == 400
    r = api.client.post("/admin/commerce/coupons", headers=admin, json={
        "code": code.lower(), "kind": "percent", "value": 20, "starts_on": "2026-01-01", "ends_on": "2026-12-31", "max_uses": 50,
    })
    assert r.status_code == 201 and r.json()["code"] == code
    assert api.client.post("/admin/commerce/coupons", headers=admin, json={"code": code, "kind": "amount", "value": 100}).status_code == 400
