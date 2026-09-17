"""מאגר האולמות המנוהל — סטטוס מול ההשלמה האוטומטית, אימות, תמונות, מחיקה בטוחה."""
import base64
import io
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


def _admin(role="super_admin"):
    from app import auth, models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        u = models.User(email=f"ven-{uuid.uuid4().hex[:8]}@veya.test", password_hash=auth.hash_password("Test12345!"),
                        display_name="אביב", is_admin=True, admin_role=role)
        db.add(u)
        db.commit()
        return {"Authorization": f"Bearer {auth.create_access_token(u)}"}
    finally:
        db.close()


def _png_data_url() -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 180, 120)).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _suggested(api, name: str) -> bool:
    from app import cache

    cache.invalidate_prefix("venues:")
    r = api.client.get(f"/venues/search?q={name}", headers=api.headers)
    assert r.status_code == 200, r.text
    return any(v["name"] == name for v in r.json())


def test_status_controls_autocomplete_and_audit() -> None:
    api, _ = bootstrap()
    admin = _admin()
    name = f"גן הדקלים {uuid.uuid4().hex[:5]}"
    r = api.client.post("/admin/venue-cms", headers=admin, json={
        "name": name, "city": "חיפה", "address": "הנמל 1", "event_types": ["wedding", "brit"],
        "capacity_min": 100, "capacity_max": 400, "internal_notes": "לא לפרסם",
    })
    assert r.status_code == 201, r.text
    v = r.json()
    assert v["status"] == "draft"
    assert not _suggested(api, name), "טיוטה הוצעה לזוג"

    api.client.post(f"/admin/venue-cms/{v['id']}/status", headers=admin, json={"status": "active"})
    assert _suggested(api, name)
    api.client.post(f"/admin/venue-cms/{v['id']}/status", headers=admin, json={"status": "hidden", "reason": "נסגר"})
    assert not _suggested(api, name)

    public = api.client.get(f"/venues/search?q={name}", headers=api.headers).text
    assert "לא לפרסם" not in public

    log = api.client.get(f"/admin/audit?target_type=venue&target_id={v['id']}", headers=admin).json()["items"]
    assert {i["action"] for i in log} >= {"venue.create", "venue.status"}


def test_invalid_capacity_and_duplicate_names() -> None:
    api, _ = bootstrap()
    admin = _admin()
    name = f"אולם כפול {uuid.uuid4().hex[:5]}"
    assert api.client.post("/admin/venue-cms", headers=admin, json={"name": name, "capacity_min": 500, "capacity_max": 100}).status_code == 400
    first = api.client.post("/admin/venue-cms", headers=admin, json={"name": name}).json()
    assert api.client.post("/admin/venue-cms", headers=admin, json={"name": name}).status_code == 400
    copy = api.client.post(f"/admin/venue-cms/{first['id']}/duplicate", headers=admin)
    assert copy.status_code == 201 and copy.json()["name"].startswith(name) and copy.json()["status"] == "draft"


def test_verified_address_not_overwritten_by_couples() -> None:
    api, _ = bootstrap()
    admin = _admin()
    name = f"אולם מאומת {uuid.uuid4().hex[:5]}"
    v = api.client.post("/admin/venue-cms", headers=admin, json={"name": name, "address": "הכתובת הנכונה 7", "verified": True}).json()
    from app import models, venues
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        venues.record_venue(db, name, "כתובת אחרת שהזוג הקליד")
        db.commit()
        assert db.get(models.Venue, v["id"]).address == "הכתובת הנכונה 7"
    finally:
        db.close()


def test_images_and_safe_delete() -> None:
    api, _ = bootstrap()
    admin, support = _admin(), _admin("support")
    name = f"אולם תמונות {uuid.uuid4().hex[:5]}"
    v = api.client.post("/admin/venue-cms", headers=admin, json={"name": name}).json()
    r = api.client.post(f"/admin/venue-cms/{v['id']}/images", headers=admin, json={"data_url": _png_data_url()})
    assert r.status_code == 201, r.text
    r = api.client.post(f"/admin/venue-cms/{v['id']}/images", headers=admin, json={"data_url": _png_data_url()})
    images = r.json()["images"]
    assert len(images) == 2 and sum(i["is_main"] for i in images) == 1

    second = images[1]["id"]
    r = api.client.put(f"/admin/venue-cms/{v['id']}/images", headers=admin,
                       json={"order": [second, images[0]["id"]], "main_id": second})
    assert r.json()["images"][0]["id"] == second and r.json()["images"][0]["is_main"]

    assert api.client.post(f"/admin/venue-cms", headers=support, json={"name": "x" + name}).status_code == 403
    assert api.client.post(f"/admin/venue-cms/{v['id']}/delete", headers=admin, json={"confirm_name": "שם אחר"}).status_code == 400
    assert api.client.post(f"/admin/venue-cms/{v['id']}/delete", headers=admin, json={"confirm_name": name}).status_code == 200
    assert api.client.get(f"/admin/venue-cms/{v['id']}", headers=admin).status_code == 404


def teardown_module(module) -> None:  # noqa: ARG001
    shutdown()
