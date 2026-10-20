"""תיבת WhatsApp — מסך הצוות (``routers/admin_inbox.py``).

מה נבדק:
  1. הרשאות: Support ומעלה ו**טלפנים** נכנסים; משתמש רגיל / בלי התחברות — לא.
  2. רשימה, סינון ("פתוחות", "שלי") וספירה לתפריט.
  3. מענה בתוך 24 שעות: נשמר, השיחה "נענתה", משויכת למי שענה; במצב mock לא
     פונה ל-Meta. אחרי 24 שעות — 409 בשרת, בלי שורה חדשה.
  4. לחיצה כפולה (אותו client_token) → הודעה אחת. שדה נמען → 422.
  5. סטטוס ושיוך (רק לאיש צוות), ויומן האדמין בלי תוכן ההודעה.
  6. פרטי חשבון (מייל, אירועים) רק למי שיש לו users.view.
  7. מחיקת חשבון מוחקת את השיחות שלו. RLS: קובץ 29 רשום ותקין.

הרצה: ``venv/bin/python -m pytest tests/test_whatsapp_inbox_api.py``
"""
from __future__ import annotations

import sys
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from tests.e2e_seating import make_client  # noqa: E402
from tests.test_help_context import _db, _h, _register, _uid  # noqa: E402
from tests.test_help_requests import _make_admin  # noqa: E402
from tests.test_whatsapp_inbox import _MetaSpy  # noqa: E402
from tests.test_whatsapp_safety import _phone  # noqa: E402

BASE = "/admin/inbox"


def _thread(*, user_id: int | None = None, hours_ago: float = 1.0, phone: str | None = None) -> int:
    from app import models, whatsapp_inbox

    def make(db):
        now = whatsapp_inbox._now()
        t = models.WhatsAppThread(
            phone=phone or _phone(), profile_name="דנה מהוואטסאפ", user_id=user_id,
            sender_kind="account" if user_id else "unknown", status="open",
            last_inbound_at=now - timedelta(hours=hours_ago), last_message_at=now - timedelta(hours=hours_ago),
        )
        db.add(t)
        db.flush()
        db.add(models.WhatsAppThreadMessage(thread_id=t.id, direction="inbound", kind="text",
                                            body="איך מוסיפים מוזמנים?", status="received"))
        return t.id

    return _db(make)


def _phone_agent(client) -> str:
    from app import models

    _, token = _register(client, "טלפן")
    uid = _uid(token)

    def promote(db):
        db.get(models.User, uid).account_type = "phone_agent"

    _db(promote)
    return token


def _reply(client, token: str, tid: int, body: str = "היי, כאן VEYA. בודקים ומעדכנים.", ctoken: str | None = None, **extra):
    return client.post(f"{BASE}/threads/{tid}/reply", headers=_h(token),
                       json={"body": body, "client_token": ctoken or uuid.uuid4().hex, **extra})


def test_permissions() -> None:
    client, _ = make_client()
    tid = _thread()
    # המשתמש הראשון שנרשם במסד ריק הופך לאדמין (auth.py) — לכן הצוות נרשם קודם.
    support = _make_admin(client, "support")
    agent = _phone_agent(client)
    _, couple = _register(client, "זוג")
    for token in (couple,):
        assert client.get(f"{BASE}/threads", headers=_h(token)).status_code == 403
        assert _reply(client, token, tid).status_code == 403
    assert client.get(f"{BASE}/threads").status_code == 401
    for token in (support, agent):
        r = client.get(f"{BASE}/threads", headers=_h(token))
        assert r.status_code == 200 and any(row["id"] == tid for row in r.json())
        assert client.get(f"{BASE}/threads/{tid}", headers=_h(token)).status_code == 200
    assert client.get(f"{BASE}/threads/999999", headers=_h(support)).status_code == 404


def test_list_filters_and_summary() -> None:
    client, _ = make_client()
    support = _make_admin(client, "support")
    a, b = _thread(), _thread()
    me = _uid(support)
    assert client.post(f"{BASE}/threads/{a}/assign", headers=_h(support),
                       json={"assignee_id": me}).status_code == 200
    assert client.post(f"{BASE}/threads/{b}/status", headers=_h(support),
                       json={"status": "closed"}).status_code == 200
    mine = client.get(f"{BASE}/threads?mine=true", headers=_h(support)).json()
    assert [r["id"] for r in mine] == [a]
    open_ids = {r["id"] for r in client.get(f"{BASE}/threads", headers=_h(support)).json()}
    assert a in open_ids and b not in open_ids
    closed = {r["id"] for r in client.get(f"{BASE}/threads?status=closed", headers=_h(support)).json()}
    assert b in closed
    s = client.get(f"{BASE}/summary", headers=_h(support)).json()
    assert s["mine"] == 1 and s["open"] >= 1
    row = next(r for r in mine)
    assert row["window_open"] is True and row["preview"] == "איך מוסיפים מוזמנים?"
    assert row["name"] == "דנה מהוואטסאפ"


def test_reply_inside_window_mock_and_double_click() -> None:
    from app import models

    client, _ = make_client()
    agent = _phone_agent(client)
    tid = _thread()
    token = uuid.uuid4().hex
    with _MetaSpy() as spy:
        r = _reply(client, agent, tid, ctoken=token)
        assert r.status_code == 200, r.text
        r2 = _reply(client, agent, tid, ctoken=token)  # לחיצה כפולה
        assert r2.status_code == 200
        assert spy.calls == [], "מצב mock — לא פונה ל-Meta"
    d = r2.json()
    out = [m for m in d["messages"] if m["direction"] == "outbound"]
    assert len(out) == 1 and out[0]["status"] == "mock" and out[0]["sent_by"]["name"] == "טלפן"
    assert d["status"] == "answered" and d["assigned_to"]["id"] == _uid(agent)
    assert _reply(client, agent, tid, body="נוסח אחר", ctoken=token).status_code == 409
    assert _reply(client, agent, tid, to="0500000000").status_code == 422, "אין שדה נמען"

    def audit(db):
        rows = db.scalars(select(models.AdminAuditLog).where(
            models.AdminAuditLog.action == "inbox.reply", models.AdminAuditLog.target_id == str(tid))).all()
        return [r.summary for r in rows]

    summaries = _db(audit)
    assert len(summaries) == 1 and "בודקים ומעדכנים" not in summaries[0]


def test_reply_after_24h_is_refused_by_server() -> None:
    from app import models

    client, _ = make_client()
    support = _make_admin(client, "support")
    tid = _thread(hours_ago=25)
    detail = client.get(f"{BASE}/threads/{tid}", headers=_h(support)).json()
    assert detail["window_open"] is False
    r = _reply(client, support, tid)
    assert r.status_code == 409 and "24 שעות" in r.json()["detail"]
    count = _db(lambda db: len(db.scalars(select(models.WhatsAppThreadMessage).where(
        models.WhatsAppThreadMessage.thread_id == tid)).all()))
    assert count == 1


def test_assign_only_to_staff_and_status_values() -> None:
    client, _ = make_client()
    support = _make_admin(client, "support")
    agent = _phone_agent(client)
    _, couple = _register(client, "זוג")
    tid = _thread()
    d = client.get(f"{BASE}/threads/{tid}", headers=_h(support)).json()
    agent_ids = {a["id"] for a in d["agents"]}
    assert _uid(agent) in agent_ids and _uid(support) in agent_ids and _uid(couple) not in agent_ids
    assert client.post(f"{BASE}/threads/{tid}/assign", headers=_h(support),
                       json={"assignee_id": _uid(couple)}).status_code == 422
    r = client.post(f"{BASE}/threads/{tid}/assign", headers=_h(support), json={"assignee_id": _uid(agent)})
    assert r.json()["assigned_to"]["id"] == _uid(agent)
    r = client.post(f"{BASE}/threads/{tid}/assign", headers=_h(support), json={"assignee_id": None})
    assert r.json()["assigned_to"] is None
    assert client.post(f"{BASE}/threads/{tid}/status", headers=_h(support),
                       json={"status": "deleted"}).status_code == 422


def test_account_details_only_with_users_view() -> None:
    client, _ = make_client()
    support = _make_admin(client, "support")
    agent = _phone_agent(client)
    _, couple = _register(client, "בעלת חשבון")
    tid = _thread(user_id=_uid(couple))
    for_support = client.get(f"{BASE}/threads/{tid}", headers=_h(support)).json()
    assert for_support["account"]["email"].endswith("@veya.test")
    assert for_support["name"] == "בעלת חשבון"
    for_agent = client.get(f"{BASE}/threads/{tid}", headers=_h(agent)).json()
    assert for_agent["account"]["email"] == "" and for_agent["account"]["events"] == []


def test_account_deletion_removes_threads() -> None:
    from app import account, models

    client, _ = make_client()
    _, couple = _register(client, "נמחקת")
    uid = _uid(couple)
    tid = _thread(user_id=uid)

    def delete(db):
        account.delete_support_requests_for_user(db, uid)

    _db(delete)
    assert _db(lambda db: db.get(models.WhatsAppThread, tid)) is None


def test_rls_file_registered() -> None:
    from app import main

    assert "29_whatsapp_inbox_rls.sql" in main._RLS_MIGRATION_FILES
    sql = (Path(__file__).resolve().parent.parent / "rls" / "29_whatsapp_inbox_rls.sql").read_text()
    for table in ("whatsapp_threads", "whatsapp_thread_messages"):
        assert f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"ALTER TABLE {table} FORCE  ROW LEVEL SECURITY" in sql
    assert "app_is_phone_agent()" in sql


def test_followup_after_24h_once_until_the_sender_replies() -> None:
    """(2026-10-20) אחרי 24 שעות — "הודעת חזרה" בתבנית מאושרת, פעם אחת לכל
    הודעה של הפונה. בתוך החלון — לא צריך (עונים ישירות)."""
    from app import models

    client, _ = make_client()
    support = _make_admin(client, "support")
    open_tid = _thread(hours_ago=2)
    r = client.post(f"{BASE}/threads/{open_tid}/followup", headers=_h(support))
    assert r.status_code == 409 and "פתוח" in r.json()["detail"]

    tid = _thread(hours_ago=30)
    r = client.post(f"{BASE}/threads/{tid}/followup", headers=_h(support))
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["followup_waiting"] is True
    out = [m for m in detail["messages"] if m["direction"] == "outbound"]
    assert [(m["kind"], m["status"]) for m in out] == [("followup", "mock")]
    again = client.post(f"{BASE}/threads/{tid}/followup", headers=_h(support))
    assert again.status_code == 409 and "כבר נשלחה" in again.json()["detail"]
    count = _db(lambda db: len(db.scalars(select(models.WhatsAppThreadMessage).where(
        models.WhatsAppThreadMessage.thread_id == tid)).all()))
    assert count == 2
    print("✓ הודעת חזרה אחרי 24 שעות — פעם אחת, ורק כשהחלון סגור")


def test_followup_sends_the_approved_template_in_meta_mode() -> None:
    import json

    from app import models, whatsapp_inbox
    from app import whatsapp_template_status as status
    from tests.test_whatsapp_inbox import _env

    def pending_followup(phone):
        def make(db):
            now = whatsapp_inbox._now()
            t = models.WhatsAppThread(phone=phone, last_inbound_at=now - timedelta(hours=30),
                                      last_message_at=now - timedelta(hours=30))
            db.add(t)
            db.flush()
            row = models.WhatsAppThreadMessage(thread_id=t.id, direction="outbound", kind="followup",
                                               body=whatsapp_inbox.FOLLOWUP_TEXT, status="pending")
            db.add(row)
            db.flush()
            return row.id
        return _db(make)

    def deliver(row_id):
        def run(db):
            row = db.get(models.WhatsAppThreadMessage, row_id)
            whatsapp_inbox.deliver(db, row)
            return row.status, row.failure_reason
        return _db(run)

    env = {"WHATSAPP_MODE": "meta", "WHATSAPP_ACCESS_TOKEN": "test-token-not-real",
           "WHATSAPP_PHONE_NUMBER_ID": "123"}
    try:
        with _MetaSpy() as spy, _env(**env):
            status._override = {(whatsapp_inbox.FOLLOWUP_TEMPLATE, "he"): "PENDING"}
            st, reason = deliver(pending_followup(_phone()))
            assert st == "failed" and "ממתינה לאישור" in reason and spy.calls == []
            status._override = {(whatsapp_inbox.FOLLOWUP_TEMPLATE, "he"): "APPROVED"}
            st, _ = deliver(pending_followup(_phone()))
            assert st == "sent" and len(spy.calls) == 1
            body = json.loads(spy.calls[0].content)
            assert body["type"] == "template" and body["template"]["name"] == "veya_support_followup"
    finally:
        status._override = None
    print("✓ במצב meta — נשלחת התבנית המאושרת; לפני אישור — לא")
