"""דרגות אדמין (Support / Admin / Super Admin) ויומן פעולות האדמין.

מה נבדק כאן — כולו אכיפה בשרת, לא ב-UI:
- תאימות לאחור: אדמין קיים בלי דרגה = Super Admin (לא נשברה גישה לאף אחד).
- Support לא מגיע לפעולות מסוכנות (מחיקה, כסף, ניהול אדמינים).
- הסלמת הרשאות חסומה: Support לא מאפס סיסמה/חוסם/מתחזה ל-Super Admin, ואף
  אדמין לא מעניק דרגה גבוהה משלו או משנה את עצמו.
- תמיד נשאר Super Admin פעיל אחד.
- משתמש רגיל וטלפן לא מגיעים לשום נתיב של מרכז השליטה.
- כל פעולה נרשמת ביומן האדמין עם לפני/אחרי.
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402
from tests.call_center_helpers import phone_agent, plain_headers  # noqa: E402


def _admin(role=None, *, name="אדמין בדיקות") -> tuple[int, dict]:
    from app import auth, models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = models.User(
            email=f"rbac-{uuid.uuid4().hex[:10]}@veya.test",
            password_hash=auth.hash_password("Test12345!"),
            display_name=name,
            is_admin=True,
            admin_role=role,
        )
        db.add(user)
        db.commit()
        return user.id, {"Authorization": f"Bearer {auth.create_access_token(user)}"}
    finally:
        db.close()


def _plain_user() -> tuple[int, dict]:
    from app import auth, models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        user = models.User(
            email=f"plain-{uuid.uuid4().hex[:10]}@veya.test",
            password_hash=auth.hash_password("Test12345!"),
            display_name="משתמש רגיל",
        )
        db.add(user)
        db.commit()
        return user.id, {"Authorization": f"Bearer {auth.create_access_token(user)}"}
    finally:
        db.close()


def _audit_rows(**where):
    from sqlalchemy import select

    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        stmt = select(models.AdminAuditLog)
        for k, v in where.items():
            stmt = stmt.where(getattr(models.AdminAuditLog, k) == v)
        return db.scalars(stmt.order_by(models.AdminAuditLog.id)).all()
    finally:
        db.close()


def test_legacy_admin_without_role_is_super_admin() -> None:
    api, _ = bootstrap()
    _, legacy = _admin(None)
    r = api.client.get("/admin/me", headers=legacy)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "super_admin"
    assert "users.delete" in body["permissions"]
    assert "commerce.edit" in body["permissions"]


def test_support_is_blocked_from_dangerous_actions() -> None:
    api, _ = bootstrap()
    _, support = _admin("support")
    victim_id, _ = _plain_user()

    assert api.client.get("/admin/users", headers=support).status_code == 200
    assert api.client.get("/admin/me", headers=support).json()["role"] == "support"
    # מחיקות
    assert api.client.delete(f"/admin/users/{victim_id}", headers=support).status_code == 403
    assert api.client.delete(f"/admin/events/{api.event_id}", headers=support).status_code == 403
    # כסף וניהול אדמינים
    assert api.client.get("/admin/payout?scope=pending", headers=support).status_code == 403
    assert api.client.get("/admin/admins", headers=support).status_code == 403
    assert api.client.put(
        f"/admin/admins/{victim_id}/role", headers=support, json={"role": "support"},
    ).status_code == 403
    # יומן וחסימה — מעל Support
    assert api.client.get("/admin/audit", headers=support).status_code == 403
    assert api.client.post(f"/admin/users/{victim_id}/disable", headers=support).status_code == 403


def test_support_cannot_take_over_a_super_admin() -> None:
    api, _ = bootstrap()
    _, support = _admin("support")
    super_id, _ = _admin("super_admin")

    r = api.client.post(
        f"/admin/users/{super_id}/reset-password", headers=support, json={},
    )
    assert r.status_code == 403, "Support איפס סיסמה ל-Super Admin"
    r = api.client.patch(
        f"/admin/users/{super_id}", headers=support, json={"display_name": "נפרץ"},
    )
    assert r.status_code == 403
    r = api.client.patch(
        f"/admin/users/{super_id}", headers=support, json={"is_admin": False},
    )
    assert r.status_code == 403


def test_support_cannot_grant_admin_via_user_edit() -> None:
    api, _ = bootstrap()
    _, support = _admin("support")
    target_id, _ = _plain_user()
    r = api.client.patch(f"/admin/users/{target_id}", headers=support, json={"is_admin": True})
    assert r.status_code == 403


def test_role_change_rules_and_audit() -> None:
    api, _ = bootstrap()
    super_id, super_h = _admin("super_admin", name="אביב")
    admin_id, admin_h = _admin("admin")
    target_id, _ = _plain_user()

    # אדמין רגיל לא מנהל דרגות בכלל
    assert api.client.put(
        f"/admin/admins/{target_id}/role", headers=admin_h, json={"role": "support"},
    ).status_code == 403
    # אי אפשר לשנות את עצמך
    assert api.client.put(
        f"/admin/admins/{super_id}/role", headers=super_h, json={"role": "support"},
    ).status_code == 400
    # טלפן לא יכול להיות אדמין
    caller_id, _ = phone_agent(api)
    assert api.client.put(
        f"/admin/admins/{caller_id}/role", headers=super_h, json={"role": "admin"},
    ).status_code == 400

    r = api.client.put(
        f"/admin/admins/{target_id}/role", headers=super_h,
        json={"role": "support", "reason": "מצטרפ/ת לתמיכה"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "support"

    rows = _audit_rows(action="admin.role_change", target_id=str(target_id))
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_id == super_id
    assert row.actor_label == "אביב"
    assert row.changes == [
        {"field": "admin_role", "label": "דרגה", "before": "לא אדמין", "after": "Support"}
    ]
    assert row.reason == "מצטרפ/ת לתמיכה"

    # טוקן ישן של מי שהדרגה שלו השתנתה נפסל
    from app import auth, models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        admin_user = db.get(models.User, admin_id)
        old_token = {"Authorization": f"Bearer {auth.create_access_token(admin_user)}"}
    finally:
        db.close()
    assert api.client.put(
        f"/admin/admins/{admin_id}/role", headers=super_h, json={"role": "support"},
    ).status_code == 200
    assert api.client.get("/admin/me", headers=old_token).status_code == 401


def test_super_admin_demotion_needs_another_super_admin() -> None:
    """הורדת Super Admin אפשרית רק ע"י Super Admin אחר — ולכן תמיד נשאר אחד:
    את עצמך אי אפשר להוריד, ומי שאינו Super Admin לא מנהל דרגות בכלל."""
    api, _ = bootstrap()
    first_id, first_h = _admin("super_admin")
    second_id, second_h = _admin("super_admin")

    assert api.client.put(
        f"/admin/admins/{first_id}/role", headers=second_h, json={"role": "admin"},
    ).status_code == 200
    # first הוא עכשיו Admin — לא יכול לגעת בדרגה של second
    from app import auth, models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        first = db.get(models.User, first_id)
        fresh_first = {"Authorization": f"Bearer {auth.create_access_token(first)}"}
    finally:
        db.close()
    assert api.client.put(
        f"/admin/admins/{second_id}/role", headers=fresh_first, json={"role": "admin"},
    ).status_code == 403
    assert api.client.put(
        f"/admin/admins/{second_id}/role", headers=second_h, json={"role": "admin"},
    ).status_code == 400


def test_plain_user_and_caller_get_nothing() -> None:
    api, _ = bootstrap()
    _, plain = _plain_user()
    _, caller = phone_agent(api)
    owner = plain_headers(api)
    for headers in (plain, caller, owner):
        for path in ("/admin/me", "/admin/admins", "/admin/audit", "/admin/users"):
            assert api.client.get(path, headers=headers).status_code in (401, 403), path


def test_disable_writes_admin_audit_with_before_after() -> None:
    api, _ = bootstrap()
    admin_id, admin_h = _admin("admin", name="מנהלת")
    victim_id, _ = _plain_user()
    assert api.client.post(f"/admin/users/{victim_id}/disable", headers=admin_h).status_code == 204

    rows = _audit_rows(action="user.disable", target_id=str(victim_id))
    assert len(rows) == 1
    assert rows[0].actor_role == "admin"
    assert rows[0].changes == [{"field": "disabled", "label": "סטטוס", "before": "פעיל", "after": "חסום"}]

    r = api.client.get(f"/admin/audit?target_type=user&target_id={victim_id}", headers=admin_h)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items and items[0]["summary"].startswith("חסם/ה את המשתמש")
    assert items[0]["domain_label"] == "משתמשים"


def teardown_module(module) -> None:  # noqa: ARG001
    shutdown()
