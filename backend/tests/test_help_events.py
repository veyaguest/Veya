"""עזרה בתוך VEYA — שלב 8: מדידת שימוש בעזרה, בלי זהות.

מה נבדק (HELP_CENTER_PLAN.md §12 + החלטות המייסד 2026-09-29 / 2026-09-30):
  1. אוצר מילים סגור: 11 שמות בדיוק; שם / שדה / ערך לא מוכר → 422 ושום דבר
     לא נשמר. אין באוצר המילים אף שדה של טקסט חופשי.
  2. בלי זהות: בטבלה אין user_id / event_id; השורה לא כוללת מייל, שם, טלפון,
     או מזהה אירוע/משתמש. session_id אקראי מהדפדפן בלבד.
  3. רק מנהלי האירוע וכשהעזרה פתוחה; בכניסה לתמיכה — 204 בלי לשמור.
  4. הגבלת קצב: 30 בקשות בדקה למשתמש; עד 50 אירועים בבקשה.
  5. "תובנות עזרה": רק אדמין עם help.insights; ספירות נכונות; אירועים ישנים
     מ-180 יום נמחקים.
  6. קובץ ה-RLS רשום ומוגדר ENABLE + FORCE.

הרצה: ``venv/bin/python -m pytest tests/test_help_events.py``
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import make_client  # noqa: E402
from tests.test_help_context import SECRET_GUESTS, _db, _h, _register, _setup, _uid  # noqa: E402

from app import help_analytics, help_context  # noqa: E402

GOOD = [
    {"name": "help_opened", "screen": "guests", "props": {"entry": "launcher", "had_error": False, "had_urgent": False}},
    {"name": "topic_selected", "screen": "guests", "props": {"topic_id": "guests.add-one", "source": "home"}},
    {"name": "article_opened", "screen": "guests", "props": {"topic_id": "guests.add-one", "has_action": True}},
    {"name": "guided_help_started", "screen": "guests", "props": {"flow_id": "add-guest"}},
    {"name": "guided_help_completed", "screen": "guests", "props": {"flow_id": "add-guest", "result": "target_missing", "step": 2}},
    {"name": "troubleshooting_started", "screen": "guests", "props": {"tree_id": "guest-save-failed", "source": "error"}},
    {"name": "troubleshooting_completed", "screen": "guests", "props": {"tree_id": "guest-save-failed", "outcome_id": "out-no-error", "resolution": "unknown"}},
    {"name": "help_feedback", "screen": "guests", "props": {"target": "topic", "id": "guests.add-one", "value": "not_helped"}},
    {"name": "search_no_results", "screen": "guests", "props": {}},
    {"name": "escalation_started", "screen": "guests", "props": {"from": "tree", "tree_id": "guest-save-failed"}},
    {"name": "escalation_submitted", "screen": "guests", "props": {"from": "tree", "tree_id": "guest-save-failed", "topic_id": None}},
]


def _session() -> str:
    return uuid.uuid4().hex


def _batch(events, **over) -> dict:
    body = {"session_id": _session(), "platform": "desktop", "kb_version": "2026-09-30", "events": events}
    body.update(over)
    return body


def _post(client, s, body, token=None):
    return client.post("/help/events", headers=_h(token or s["token"], s["event_id"]), json=body)


def _reset() -> None:
    from app.routers import help as help_router

    help_router.events_limiter.reset()


def _rows() -> list[dict]:
    from sqlalchemy import select

    from app import models

    return _db(lambda db: [
        {c.name: getattr(r, c.name) for c in models.HelpEvent.__table__.columns}
        for r in db.scalars(select(models.HelpEvent)).all()
    ])


def _clear() -> None:
    from sqlalchemy import delete

    from app import models

    _db(lambda db: db.execute(delete(models.HelpEvent)))


# ── 1. אוצר מילים סגור ────────────────────────────────────────────────────

def test_vocabulary_is_exactly_the_approved_eleven_without_free_text() -> None:
    assert set(help_analytics.NAMES) == {
        "help_opened", "topic_selected", "article_opened", "guided_help_started", "guided_help_completed",
        "troubleshooting_started", "troubleshooting_completed", "escalation_started", "escalation_submitted",
        "help_feedback", "search_no_results",
    }
    for name, fields in help_analytics.NAMES.items():
        for field, kind in fields.items():
            # כל שדה: רשימה סגורה, מזהה בסיס ידע, bool או int — אף פעם "string".
            assert isinstance(kind, list) or str(kind).rstrip("?") in ("kb_id", "bool", "int"), (name, field, kind)
            assert field not in ("query", "text", "q", "message", "search", "name", "email", "phone"), (name, field)
    assert help_analytics.SCREENS == sorted(help_context.SCREENS, key=help_analytics.SCREENS.index)
    assert set(help_analytics.SCREENS) == set(help_context.SCREENS)


def test_all_good_events_are_stored_and_bad_ones_rejected() -> None:
    _reset()
    client, _ = make_client()
    _clear()
    s = _setup(client)
    r = _post(client, s, _batch(GOOD))
    assert r.status_code == 204, r.text
    assert len(_rows()) == len(GOOD)

    bad_events = [
        {"name": "search", "screen": "guests", "props": {}},                                     # שם לא מאושר
        {"name": "help_opened", "screen": "guests", "props": {"entry": "launcher", "had_error": False, "had_urgent": False, "query": "דנה"}},
        {"name": "topic_selected", "screen": "guests", "props": {"topic_id": "דנה כהן", "source": "home"}},
        {"name": "topic_selected", "screen": "guests", "props": {"topic_id": "guests.add-one", "source": "twitter"}},
        {"name": "guided_help_completed", "screen": "guests", "props": {"flow_id": "add-guest", "result": "completed", "step": 999}},
        {"name": "guided_help_completed", "screen": "guests", "props": {"flow_id": "add-guest", "result": "completed", "step": True}},
        {"name": "search_no_results", "screen": "guests", "props": {"q": "זהבית"}},
        {"name": "search_no_results", "screen": "admin", "props": {}},
        {"name": "help_feedback", "screen": "guests", "props": {"target": "topic", "id": "x", "value": "maybe"}},
        {"name": "help_opened", "screen": "guests", "props": {"entry": "launcher", "had_error": "yes", "had_urgent": False}},
        {"name": "topic_selected", "screen": "guests", "props": {"topic_id": {"nested": "0527770011"}, "source": "home"}},
    ]
    for ev in bad_events:
        r = _post(client, s, _batch([ev]))
        assert r.status_code == 422, (ev, r.status_code, r.text)
    for over in (
        {"session_id": "not-a-session"}, {"session_id": "ABCDEF" * 5 + "ab"},
        {"platform": "tablet"}, {"kb_version": "latest"}, {"user_id": 1},
        {"events": []}, {"events": [GOOD[0]] * 51},
    ):
        body = _batch(GOOD[:1])
        body.update(over)
        r = _post(client, s, body)
        assert r.status_code == 422, (over, r.status_code)
    # שום דבר מהבקשות הפסולות לא נשמר (גם לא חלקית — בקשה פסולה נדחית כולה).
    assert len(_rows()) == len(GOOD)
    mixed = _post(client, s, _batch([GOOD[0], bad_events[0]]))
    assert mixed.status_code == 422 and len(_rows()) == len(GOOD)


# ── 2. בלי זהות ────────────────────────────────────────────────────────────

def test_rows_carry_no_identity() -> None:
    from app import models

    _reset()
    client, _ = make_client()
    _clear()
    s = _setup(client)
    assert _post(client, s, _batch(GOOD)).status_code == 204
    cols = {c.name for c in models.HelpEvent.__table__.columns}
    assert cols == {"id", "session_id", "name", "props", "screen", "event_type", "role", "platform", "kb_version", "created_at"}
    owner = _db(lambda db: db.get(models.User, _uid(s["token"])))
    stored = json.dumps(_rows(), default=str, ensure_ascii=False)
    for secret in (owner.email, owner.display_name, owner.phone or "0501234567",
                   *[n for n, _ in SECRET_GUESTS], *[p for _, p in SECRET_GUESTS]):
        assert secret not in stored, secret
    for row in _rows():
        assert row["role"] == "owner" and row["event_type"] == "wedding"
        assert str(s["event_id"]) != row["session_id"]
    # מזהה הסשן לא נשמר כמו שנשלח — גם אם מישהו "הסתיר" בו מספר טלפון.
    _clear()
    sneaky = "0527770011" * 3 + "ab"
    assert _post(client, s, _batch(GOOD[:2], session_id=sneaky)).status_code == 204
    kept = {r["session_id"] for r in _rows()}
    assert len(kept) == 1 and sneaky not in kept and "0527770011" not in next(iter(kept))


# ── 3. מי רשאי ────────────────────────────────────────────────────────────

def test_only_managers_with_help_on_and_never_staff() -> None:
    from app import auth as auth_module
    from app import models

    _reset()
    client, _ = make_client()
    _clear()
    off = _setup(client, help_on=False)
    assert _post(client, off, _batch(GOOD[:1])).status_code == 404
    s = _setup(client)
    _, stranger = _register(client, "זר")
    assert _post(client, s, _batch(GOOD[:1]), stranger).status_code == 404
    _, agent = _register(client, "טלפן")
    aid = _uid(agent)
    _db(lambda db: setattr(db.get(models.User, aid), "account_type", "phone_agent"))
    assert _post(client, s, _batch(GOOD[:1]), agent).status_code == 403
    assert _rows() == []

    _, admin_token = _register(client, "צוות")
    admin_id = _uid(admin_token)
    _db(lambda db: setattr(db.get(models.User, admin_id), "is_admin", True))
    owner = _db(lambda db: db.get(models.User, _uid(s["token"])))
    imp = auth_module.create_access_token(owner, expires=auth_module.IMPERSONATION_EXPIRE, impersonated_by=admin_id)
    assert _post(client, s, _batch(GOOD), imp).status_code == 204
    assert _rows() == [], "צוות בכניסה לתמיכה לא נספר"


# ── 4. הגבלת קצב ──────────────────────────────────────────────────────────

def test_rate_limited() -> None:
    _reset()
    client, _ = make_client()
    _clear()
    s = _setup(client)
    for _ in range(30):
        assert _post(client, s, _batch(GOOD[:1])).status_code == 204
    assert _post(client, s, _batch(GOOD[:1])).status_code == 429
    _reset()


# ── 5. תובנות עזרה ────────────────────────────────────────────────────────

def test_insights_permissions_counts_and_retention() -> None:
    from sqlalchemy import select

    from app import models

    _reset()
    client, _ = make_client()
    _clear()
    s = _setup(client)
    assert _post(client, s, _batch(GOOD)).status_code == 204
    assert _post(client, s, _batch(GOOD[:2])).status_code == 204

    # לא-אדמין / Support → אין גישה (help.insights = Admin).
    assert client.get("/admin/help/insights", headers=_h(s["token"])).status_code in (401, 403)
    _, sup = _register(client, "Support")
    sid = _uid(sup)

    def make_support(db):
        u = db.get(models.User, sid)
        u.is_admin = True
        u.admin_role = "support"

    _db(make_support)
    assert client.get("/admin/help/insights", headers=_h(sup)).status_code == 403

    _, adm = _register(client, "Admin")
    aid = _uid(adm)

    def make_admin(db):
        u = db.get(models.User, aid)
        u.is_admin = True
        u.admin_role = "admin"

    _db(make_admin)
    # אירוע ישן מ-180 יום — יימחק בפתיחת התובנות.
    _db(lambda db: db.add(models.HelpEvent(
        session_id=uuid.uuid4().hex, name="search_no_results", props=None, screen="hall",
        created_at=datetime.utcnow() - timedelta(days=181),
    )))
    help_analytics._last_purge = 0.0
    r = client.get("/admin/help/insights?days=30", headers=_h(adm))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["sessions"] == 2 and data["events"] == len(GOOD) + 2
    topic = next(t for t in data["topics"] if t["topic_id"] == "guests.add-one")
    assert topic["selected"] == 2 and topic["not_helped"] == 1
    tour = next(t for t in data["tours"] if t["flow_id"] == "add-guest")
    assert tour["started"] == 1 and tour["target_missing"] == 1
    tree = next(t for t in data["trees"] if t["tree_id"] == "guest-save-failed")
    assert tree["started"] == 1 and tree["escalated"] == 1 and tree["resolution_unknown"] == 1
    assert data["escalations"] == {"started": 1, "submitted": 1}
    assert data["no_results"] == [{"screen": "guests", "count": 1}]
    left = _db(lambda db: db.scalars(select(models.HelpEvent).where(models.HelpEvent.screen == "hall")).all())
    assert left == [], "אירוע ישן מ-180 יום לא נמחק"
    assert client.get("/admin/help/insights?days=90", headers=_h(adm)).status_code == 422


def test_rls_file_registered_and_forced() -> None:
    root = Path(__file__).resolve().parent.parent
    sql = (root / "rls" / "26_help_events_rls.sql").read_text(encoding="utf-8")
    for clause in ("ENABLE ROW LEVEL SECURITY", "FORCE  ROW LEVEL SECURITY"):
        assert f"ALTER TABLE help_events {clause}" in sql
    assert '"26_help_events_rls.sql"' in (root / "app" / "main.py").read_text(encoding="utf-8")


def teardown_module(_module) -> None:
    from app import features

    features.invalidate()
    _reset()
