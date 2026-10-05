"""עזרה בתוך VEYA — שלב 9: שחרור מדורג ומתג כיבוי.

מה נבדק (HELP_CENTER_PLAN.md §19 שלב 9 + החלטת המייסד 2026-10-05):
  1. בלי סטטוס שנקבע — "בטא": סגור לכולם, פתוח רק לחריגה (אירוע בדיקה / משתמש).
  2. השלבים דרך מסך האדמין: חריגה לאירוע → חריגה למשתמש → "פעיל" לכולם.
  3. **"כבוי" = מתג כיבוי:** סוגר את העזרה גם למי שיש לו חריגה פתוחה — הנתיבים
     מחזירים 404 ו-``help_enabled`` נהיה false. החריגות לא נמחקות, ו"בטא"
     מחזיר אותן כמו שהיו.
  4. רק בעזרה: לפיצ'ר אחר (טלפנים) "כבוי" עדיין לא גובר על חריגה.
  5. מסך האדמין מציג "בטא" כברירת המחדל של העזרה ומסמן שהיא עם מתג כיבוי.

הרצה: ``venv/bin/python -m pytest tests/test_help_rollout.py``
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import make_client, verify_email  # noqa: E402


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client, name: str) -> str:
    r = client.post("/auth/register", json={
        "email": f"r-{uuid.uuid4().hex[:10]}@veya.test", "password": "Test12345!", "display_name": name,
        "phone": "0501234567", "accepted_terms": True,
    })
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    verify_email(client, token)
    return token


def _uid(token: str) -> int:
    from app import auth as auth_module

    return int(auth_module._decode_token(token)["sub"])


def _db(fn):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        out = fn(db)
        db.commit()
        return out
    finally:
        db.close()


def _couple(client) -> tuple[str, int]:
    token = _register(client, "בעלי אירוע")
    r = client.post("/events", headers=_h(token), json={
        "groom_name": "אביב", "bride_name": "דנה", "event_type": "wedding", "venue_name": "אולם",
    })
    assert r.status_code == 201, r.text
    return token, r.json()["id"]


def _admin(client) -> str:
    from app import models

    token = _register(client, "Admin")

    def make(db):
        u = db.get(models.User, _uid(token))
        u.is_admin = True
        u.admin_role = "admin"

    _db(make)
    return token


def _clean() -> None:
    from app import features, models

    def wipe(db):
        for m in (models.FeatureRule, models.FeatureFlag):
            for row in db.query(m).filter(m.feature_key == "help_center" if m is models.FeatureRule
                                          else m.key == "help_center").all():
                db.delete(row)

    _db(wipe)
    features.invalidate()


def _help_on(client, token: str, event_id: int) -> bool:
    """עזרה פתוחה = הנתיב עונה, וגם ``help_enabled`` ברשימת האירועים — שני הצדדים תמיד יחד."""
    from app import features

    features.invalidate()
    r = client.get("/help/context/guests", headers={**_h(token), "X-Event-Id": str(event_id)})
    listed = next(e for e in client.get("/events", headers=_h(token)).json() if e["id"] == event_id)
    assert (r.status_code == 200) == bool(listed["help_enabled"]), (r.status_code, listed["help_enabled"])
    return r.status_code == 200


def _status(client, admin: str, status: str) -> None:
    r = client.put("/admin/features/help_center", headers=_h(admin), json={"status": status, "reason": "בדיקה"})
    assert r.status_code == 200, r.text


def _add_rule(client, admin: str, scope_type: str, scope_id: int, enabled: bool = True) -> None:
    r = client.post("/admin/features/help_center/rules", headers=_h(admin), json={
        "scope_type": scope_type, "scope_id": scope_id, "enabled": enabled, "note": "שחרור מדורג",
    })
    assert r.status_code == 201, r.text


def _help_row(client, admin: str) -> dict:
    r = client.get("/admin/features", headers=_h(admin))
    assert r.status_code == 200, r.text
    return next(f for f in r.json()["features"] if f["key"] == "help_center")


def test_staged_rollout_and_kill_switch():
    client, _ = make_client()
    _clean()
    admin = _admin(client)
    test_tok, test_ev = _couple(client)       # אירוע הבדיקה
    beta_tok, beta_ev = _couple(client)       # זוג בבטא
    other_tok, other_ev = _couple(client)     # כל השאר

    # 0. ברירת המחדל — "בטא" בלי אף חריגה: אף אחד.
    row = _help_row(client, admin)
    assert row["status"] == "beta" and row["source"] == "default" and row["off_closes_rules"] is True
    assert not any(_help_on(client, t, e) for t, e in ((test_tok, test_ev), (beta_tok, beta_ev), (other_tok, other_ev)))

    # 1. אירוע בדיקה.
    _add_rule(client, admin, "event", test_ev)
    assert _help_on(client, test_tok, test_ev)
    assert not _help_on(client, beta_tok, beta_ev) and not _help_on(client, other_tok, other_ev)

    # 2. בטא — זוג נבחר (חריגה למשתמש).
    _add_rule(client, admin, "user", _uid(beta_tok))
    assert _help_on(client, beta_tok, beta_ev)
    assert not _help_on(client, other_tok, other_ev)

    # 3. מתג כיבוי: "כבוי" סוגר לכולם — גם לחריגות הפתוחות.
    _status(client, admin, "off")
    assert not _help_on(client, test_tok, test_ev), "חריגה לאירוע לא גוברת על מתג הכיבוי"
    assert not _help_on(client, beta_tok, beta_ev), "חריגה למשתמש לא גוברת על מתג הכיבוי"
    r = client.post("/help/events", headers={**_h(beta_tok), "X-Event-Id": str(beta_ev)}, json={
        "session_id": uuid.uuid4().hex, "platform": "desktop", "kb_version": "2026-09-30",
        "events": [{"name": "search_no_results", "screen": "guests", "props": {}}],
    })
    assert r.status_code == 404, "גם המדידה נסגרת"
    row = _help_row(client, admin)
    assert row["status"] == "off" and len(row["rules"]) == 2, "החריגות נשמרות"

    # 4. "בטא" מחזיר בדיוק את מי שהיה פתוח.
    _status(client, admin, "beta")
    assert _help_on(client, test_tok, test_ev) and _help_on(client, beta_tok, beta_ev)
    assert not _help_on(client, other_tok, other_ev)

    # 5. 100% — וחריגה סגורה לאירוע עדיין גוברת.
    _status(client, admin, "active")
    assert _help_on(client, other_tok, other_ev)
    _add_rule(client, admin, "event", other_ev, enabled=False)
    assert not _help_on(client, other_tok, other_ev)
    assert _help_on(client, test_tok, test_ev)

    # 6. ושוב כיבוי — מכולם.
    _status(client, admin, "off")
    assert not any(_help_on(client, t, e) for t, e in ((test_tok, test_ev), (beta_tok, beta_ev), (other_tok, other_ev)))
    _clean()


def test_kill_switch_is_help_only():
    """לפיצ'ר אחר "כבוי" ממשיך להתנהג כמו היום: חריגה פתוחה גוברת."""
    from app import features, models

    make_client()
    _db(lambda db: db.add(models.FeatureFlag(key="calls", label="טלפנים", status="off")))
    _db(lambda db: db.add(models.FeatureRule(feature_key="calls", scope_type="event", scope_id=987654, enabled=True)))
    features.invalidate()

    class _Ev:
        id = 987654
        owner_id = 0

    try:
        assert features.enabled("calls", _Ev()) is True
        assert features.decide("calls", _Ev()).source == "event_rule"
    finally:
        def wipe(db):
            for r in db.query(models.FeatureRule).filter(models.FeatureRule.feature_key == "calls",
                                                         models.FeatureRule.scope_id == 987654).all():
                db.delete(r)
            for f in db.query(models.FeatureFlag).filter(models.FeatureFlag.key == "calls").all():
                db.delete(f)

        _db(wipe)
        features.invalidate()


def teardown_module(module):  # noqa: ARG001
    _clean()
