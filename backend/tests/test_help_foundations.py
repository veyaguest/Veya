"""מערכת העזרה — שלב 1 (יסודות): ``my_role`` + ``help_enabled`` ברשימת האירועים.

מה נבדק (HELP_CENTER_PLAN.md §7.3, §13.4 + החלטות המייסד 2026-09-29):
  1. ברירת מחדל: הפיצ'ר ``help_center`` כבוי — אף אחד לא רואה "עזרה".
  2. כלל פתוח לאירוע → בעלי האירוע רואים עזרה, והתפקיד הוא ``owner``.
  3. בן/בת זוג בניהול משותף → ``partner`` ורואים עזרה כמו הבעלים.
  4. מפיק/אולם (חבר-אירוע) → ``member``, ולא רואים עזרה גם כשהפיצ'ר פתוח.
  5. כלל פתוח למשתמש (הבעלים) פותח גם הוא; כלל סגור לאירוע גובר עליו.
  6. יצירת אירוע מחזירה את אותם שדות.

הרצה: ``venv/bin/python -m pytest tests/test_help_foundations.py``
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import make_client, verify_email  # noqa: E402

from app import emailer  # noqa: E402

_INVITES: list[dict] = []


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _register(client, name: str = "ישראל ישראלי") -> tuple[str, str]:
    email = f"h-{uuid.uuid4().hex[:10]}@veya.test"
    r = client.post("/auth/register", json={
        "email": email, "password": "Test12345!", "display_name": name,
        "phone": "0501234567", "accepted_terms": True,
    })
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    verify_email(client, token)
    return email, token


def _make_owner(client) -> tuple[str, int]:
    _, token = _register(client, "אביב מנחם")
    r = client.post("/events", headers=_headers(token), json={
        "groom_name": "אביב", "bride_name": "דנה",
        "event_type": "wedding", "venue_name": "אולם הבדיקות",
    })
    assert r.status_code == 201, r.text
    return token, r.json()["id"]


def _user_id(token: str) -> int:
    from app import auth as auth_module

    return int(auth_module._decode_token(token)["sub"])


def _db_write(fn) -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        fn(db)
        db.commit()
    finally:
        db.close()


def _rule(scope_type: str, scope_id: int, enabled: bool) -> None:
    from app import features, models

    _db_write(lambda db: db.add(models.FeatureRule(
        feature_key="help_center", scope_type=scope_type,
        scope_id=scope_id, enabled=enabled,
    )))
    features.invalidate()


def _my_event(client, token: str) -> dict:
    events = client.get("/events", headers=_headers(token)).json()
    assert len(events) == 1, events
    return events[0]


def test_default_is_off_for_everyone() -> None:
    client, _ = make_client()
    token, _ = _make_owner(client)
    ev = _my_event(client, token)
    assert ev["my_role"] == "owner"
    assert ev["help_enabled"] is False, "הפיצ'ר אמור להיות כבוי כברירת מחדל"


def test_event_rule_opens_help_for_owner() -> None:
    client, _ = make_client()
    token, event_id = _make_owner(client)
    _rule("event", event_id, True)
    ev = _my_event(client, token)
    assert ev["my_role"] == "owner"
    assert ev["help_enabled"] is True


def test_partner_sees_help_like_owner() -> None:
    client, _ = make_client()
    owner_token, event_id = _make_owner(client)
    _rule("event", event_id, True)

    partner_email, partner_token = _register(client, "דנה כהן")
    # עוטפים את מה שמותקן **עכשיו** ומחזירים בדיוק אותו — קבצי בדיקה אחרים
    # (test_partner_comanagement) עוטפים את אותה פונקציה בזמן הטעינה, ושחזור
    # ל"מקור" שנשמר בזמן הייבוא היה מוחק את העטיפה שלהם.
    current = emailer.send_partner_invite

    def capture(**kwargs):
        result = current(**kwargs)
        _INVITES.append(kwargs)
        return result

    _INVITES.clear()
    emailer.send_partner_invite = capture
    try:
        r = client.post("/partner/invite", headers=_headers(owner_token),
                        json={"email": partner_email})
        assert r.status_code == 201, r.text
    finally:
        emailer.send_partner_invite = current
    invite_token = _INVITES[-1]["invite_url"].split("token=")[1]
    r = client.post(f"/partner/invitations/{invite_token}/accept",
                    headers=_headers(partner_token))
    assert r.status_code == 200, r.text

    ev = _my_event(client, partner_token)
    assert ev["id"] == event_id
    assert ev["my_role"] == "partner"
    assert ev["help_enabled"] is True


def test_member_never_gets_help() -> None:
    """מפיק/אולם: אין להם flows בעזרה (החלטת המייסד) — גם כשהפיצ'ר פתוח."""
    from app import models

    client, _ = make_client()
    _, event_id = _make_owner(client)
    _rule("event", event_id, True)

    _, planner_token = _register(client, "מפיק בדיקה")
    planner_id = _user_id(planner_token)
    _db_write(lambda db: db.add(models.EventMember(
        event_id=event_id, user_id=planner_id, role="planner",
        permissions=["view_guests"], status="active",
    )))

    ev = _my_event(client, planner_token)
    assert ev["id"] == event_id
    assert ev["my_role"] == "member"
    assert ev["help_enabled"] is False


def test_user_rule_opens_and_event_rule_overrides() -> None:
    client, _ = make_client()
    token, event_id = _make_owner(client)
    _rule("user", _user_id(token), True)
    assert _my_event(client, token)["help_enabled"] is True
    # כלל לאירוע גובר על כלל למשתמש (features.decide).
    _rule("event", event_id, False)
    assert _my_event(client, token)["help_enabled"] is False


def test_create_event_returns_same_fields() -> None:
    client, _ = make_client()
    _, token = _register(client)
    r = client.post("/events", headers=_headers(token), json={
        "groom_name": "א", "bride_name": "ב", "event_type": "brit", "venue_name": "",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["my_role"] == "owner"
    assert body["help_enabled"] is False
