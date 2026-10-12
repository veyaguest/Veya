"""שלב 3 (2026-10-12): החיבור ל-Meta Cloud API — מול Meta מזויפת, בלי רשת.

מכסה:
A. הגדרות — שמות חדשים וישנים, גרסת API, דוח "מוגדר/חסר" בלי ערכים.
B. הלקוח (``whatsapp_meta``) — גוף בקשת Template, הצלחה, כשל, טוקן פג, ניסיון
   חוזר רק כשבטוח, timeout = "לא ידוע" בלי ניסיון חוזר, תשובות פגומות.
C. ``MetaProvider`` + ``send_batch`` — שלב בלי Template לא נשלח ולא "נשרף";
   עם Template: הכפתור והמזהה הפנימי יוצאים; timeout נשאר pending ולא נשלח שוב.
D. השלמת הודעה תקועה מ-webhook (``biz_opaque_callback_data``) — רק בהתאמה מלאה.
E. הודעה חופשית מאורח — "דורש טיפול", בלי שינוי RSVP, בלי תוכן בלוג.
F. כלי ``hello_world`` — כל תנאי בטיחות בנפרד.
G. סודות — הטוקן לא בלוג ולא בסיבת כשל; ``hub.verify_token`` לא בלוג של uvicorn
   (שרת uvicorn אמיתי), והאימות עצמו עובד.
H. עצירת חירום גוברת על כל מצב.

הרצה: ``venv/bin/python tests/test_whatsapp_meta_api.py`` (עצמאי, או pytest).
"""
from __future__ import annotations

import io
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import contextmanager, redirect_stdout
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402
from tests.test_whatsapp_safety import (  # noqa: E402
    _db, _engine, _event, _guest, _open_rsvp, _payload, _phone, _post, _reply,
)

TOKEN = "EAAtest-" + "x" * 40  # טוקן מזויף — לבדוק שהוא לא דולף


# ---- Meta מזויפת ------------------------------------------------------------

class FakeMeta:
    """מחזירה תשובות לפי תור; רושמת כל בקשה. ``"connect"``/``"timeout"`` = חריגה."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        nxt = self.responses.pop(0) if self.responses else (200, {"messages": [{"id": "wamid.default"}]})
        if nxt == "connect":
            raise httpx.ConnectError("refused", request=request)
        if nxt == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        status, body = nxt
        if isinstance(body, (dict, list)):
            return httpx.Response(status, json=body)
        return httpx.Response(status, text=body)

    def bodies(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests]


def ok(wamid="wamid.OK1", status="accepted"):
    return 200, {"messaging_product": "whatsapp", "messages": [{"id": wamid, "message_status": status}]}


def err(code, message="error", http=400):
    return http, {"error": {"message": message, "type": "OAuthException", "code": code,
                            "fbtrace_id": "AbC123"}}


@contextmanager
def meta_env(mode="meta", recipients=None, token=TOKEN, phone_id="1234567890", fake=None, **extra):
    from app import whatsapp_meta

    values = {
        "WHATSAPP_MODE": mode, "WHATSAPP_TEST_RECIPIENTS": recipients,
        "WHATSAPP_ACCESS_TOKEN": token, "WHATSAPP_PHONE_NUMBER_ID": phone_id,
        "WHATSAPP_TOKEN": None, "WHATSAPP_PHONE_ID": None,
        "WHATSAPP_GRAPH_API_VERSION": None, "VEYA_ENV": None, **extra,
    }
    prev = {k: os.environ.get(k) for k in values}
    for k, v in values.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    fake = fake or FakeMeta()
    real_transport, real_sleep = whatsapp_meta._transport, whatsapp_meta._sleep
    whatsapp_meta._transport = httpx.MockTransport(fake.handler)
    sleeps: list[float] = []
    whatsapp_meta._sleep = sleeps.append
    fake.sleeps = sleeps
    try:
        yield fake
    finally:
        whatsapp_meta._transport, whatsapp_meta._sleep = real_transport, real_sleep
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextmanager
def templates(**specs):
    from app import whatsapp_templates

    saved = dict(whatsapp_templates.TEMPLATES)
    whatsapp_templates.TEMPLATES.clear()
    whatsapp_templates.TEMPLATES.update(specs)
    try:
        yield
    finally:
        whatsapp_templates.TEMPLATES.clear()
        whatsapp_templates.TEMPLATES.update(saved)


def _spec(**kw):
    from app.whatsapp_templates import TemplateSpec

    return TemplateSpec(**{"name": "veya_test_tpl", "language": "he",
                           "body_params": ("guest_name", "host_names"), "url_button": True, **kw})


def _captured(fn):
    buf = io.StringIO()
    with redirect_stdout(buf):
        result = fn()
    return result, buf.getvalue()


# ============================================================================
# A. הגדרות
# ============================================================================

def test_config_new_names_old_names_and_version() -> None:
    from app import whatsapp_meta as wm

    with meta_env(token="new-token", phone_id="111"):
        cfg = wm.load_config()
        assert (cfg.access_token, cfg.phone_number_id, cfg.graph_version) == ("new-token", "111", "v26.0")
    with meta_env(token=None, phone_id=None, WHATSAPP_TOKEN="old-token", WHATSAPP_PHONE_ID="222"):
        cfg = wm.load_config()
        assert (cfg.access_token, cfg.phone_number_id) == ("old-token", "222")
    with meta_env(WHATSAPP_GRAPH_API_VERSION="v27.0"):
        assert wm.load_config().graph_version == "v27.0"
    with meta_env(WHATSAPP_GRAPH_API_VERSION="27; drop"):
        assert wm.load_config().graph_version == "v26.0"
    with meta_env(token=None, phone_id=None):
        assert wm.load_config().missing() == ["WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID"]
    print("✓ A1: שמות חדשים, נפילה לשמות הישנים, גרסה ברירת מחדל v26.0 / ערך לא תקין")


def test_config_report_has_no_values() -> None:
    from app import whatsapp_meta as wm

    with meta_env(WHATSAPP_APP_SECRET="app-secret-value", WHATSAPP_VERIFY_TOKEN="verify-value"):
        report = wm.config_report()
    text = json.dumps(report, ensure_ascii=False)
    for secret in (TOKEN, "app-secret-value", "verify-value", "1234567890"):
        assert secret not in text
    assert report["WHATSAPP_ACCESS_TOKEN"] == "מוגדר" and report["WHATSAPP_BUSINESS_ACCOUNT_ID"] == "חסר"
    print("✓ A2: דוח ההגדרות — 'מוגדר'/'חסר' בלבד, אף ערך")


# ============================================================================
# B. הלקוח
# ============================================================================

def test_template_send_success_and_request_shape() -> None:
    from app import whatsapp_meta as wm

    with meta_env(fake=FakeMeta(ok("wamid.A", "held_for_quality_assessment"))) as fake:
        res = wm.send_template(phone="050-123-4567", name="tpl", language="he",
                               body_params=["דנה", "יואב ונועה"], url_suffix="tok123",
                               callback_data="veya:m1:e2:g3")
    assert res.ok and res.status == "sent" and res.provider_message_id == "wamid.A"
    assert res.provider_status == "held_for_quality_assessment"
    req = fake.requests[0]
    assert str(req.url) == "https://graph.facebook.com/v26.0/1234567890/messages"
    assert req.headers["Authorization"] == f"Bearer {TOKEN}"
    assert fake.bodies()[0] == {
        "messaging_product": "whatsapp", "recipient_type": "individual", "to": "972501234567",
        "type": "template",
        "template": {"name": "tpl", "language": {"code": "he"}, "components": [
            {"type": "body", "parameters": [{"type": "text", "text": "דנה"},
                                            {"type": "text", "text": "יואב ונועה"}]},
            {"type": "button", "sub_type": "url", "index": "0",
             "parameters": [{"type": "text", "text": "tok123"}]},
        ]},
        "biz_opaque_callback_data": "veya:m1:e2:g3",
    }
    print("✓ B1: שליחת Template — גוף הבקשה, כפתור קישור, מזהה פנימי, 'נשלחה' עם wamid")


def test_api_failure_not_retried() -> None:
    from app import whatsapp_meta as wm

    for code in (131026, 132001, 131050, 131049, 131056, 100):
        with meta_env(fake=FakeMeta(err(code))) as fake:
            res = wm.send_template(phone=_phone(), name="t", language="he", body_params=[])
        assert res.status == "failed" and res.error_code == code, (code, res)
        assert len(fake.requests) == 1 and fake.sleeps == [], f"{code} לא אמור לחזור"
    print("✓ B2: שגיאה קבועה (131026/132001/131050/131049/131056/100) — נכשלה, בלי ניסיון חוזר")


def test_auth_failure() -> None:
    from app import whatsapp_meta as wm

    for code in (190, 0, 200):
        with meta_env(fake=FakeMeta(err(code, http=401))) as fake:
            res = wm.send_template(phone=_phone(), name="t", language="he", body_params=[])
        assert res.status == "failed" and res.error_code == code and len(fake.requests) == 1
    print("✓ B3: טוקן פג/חסר (190/0/200) — נכשלה מיד, בלי ניסיון חוזר")


def test_retry_only_when_meta_did_not_accept() -> None:
    from app import whatsapp_meta as wm

    with meta_env(fake=FakeMeta(err(130429, http=429), ok("wamid.R"))) as fake:
        res = wm.send_template(phone=_phone(), name="t", language="he", body_params=[])
    assert res.ok and len(fake.requests) == 2 and fake.sleeps == [1.0]
    with meta_env(fake=FakeMeta("connect", "connect", ok("wamid.C"))) as fake:
        res = wm.send_template(phone=_phone(), name="t", language="he", body_params=[])
    assert res.ok and len(fake.requests) == 3 and fake.sleeps == [1.0, 3.0]
    with meta_env(fake=FakeMeta(err(131000, http=500), err(131000, http=500), err(131000, http=500))) as fake:
        res = wm.send_template(phone=_phone(), name="t", language="he", body_params=[])
    assert res.status == "failed" and res.error_code == 131000 and len(fake.requests) == 3
    with meta_env(fake=FakeMeta((429, "Too Many"), ok())) as fake:
        res = wm.send_template(phone=_phone(), name="t", language="he", body_params=[])
    assert res.ok and len(fake.requests) == 2
    print("✓ B4: ניסיון חוזר רק בקוד זמני / כשל התחברות — עד 3 ניסיונות, המתנה 1s→3s")


def test_timeout_is_unknown_and_never_retried() -> None:
    from app import whatsapp_meta as wm

    cases = [
        ("timeout", "ReadTimeout"),
        ((200, {"messages": []}), "2xx בלי מזהה"),
        ((502, "<html>bad gateway</html>"), "5xx בלי גוף של Meta"),
        ((200, "not json"), "2xx לא JSON"),
    ]
    for response, label in cases:
        with meta_env(fake=FakeMeta(response)) as fake:
            res = wm.send_template(phone=_phone(), name="t", language="he", body_params=[])
        assert res.status == "pending" and not res.ok, label
        assert res.provider_status == wm.OUTCOME_UNKNOWN, label
        assert len(fake.requests) == 1 and fake.sleeps == [], f"{label}: אסור לנסות שוב"
    print("✓ B5: timeout / תשובה בלי מזהה / 5xx לא מזוהה — 'לא ידוע', בלי ניסיון חוזר")


def test_invalid_phone_or_missing_config_never_calls_meta() -> None:
    from app import whatsapp_meta as wm

    with meta_env() as fake:
        for bad in ("", "123", "+1 415 555 0100", None):
            assert wm.send_template(phone=bad, name="t", language="he", body_params=[]).status == "failed"
    assert fake.requests == []
    with meta_env(token=None) as fake:
        res = wm.send_template(phone=_phone(), name="t", language="he", body_params=[])
    assert res.status == "failed" and "WHATSAPP_ACCESS_TOKEN" in res.detail and fake.requests == []
    print("✓ B6: טלפון לא תקין / חסר טוקן — לא פונים ל-Meta בכלל")


def test_token_never_in_logs_or_failure_reason() -> None:
    from app import whatsapp_meta as wm

    leaky = err(190, message=f"Invalid token {TOKEN} for app")
    with meta_env(fake=FakeMeta(leaky, "timeout", "connect", "connect", "connect")):
        (res1, log1) = _captured(lambda: wm.send_template(phone=_phone(), name="t", language="he", body_params=[]))
        (res2, log2) = _captured(lambda: wm.send_template(phone=_phone(), name="t", language="he", body_params=[]))
        (res3, log3) = _captured(lambda: wm.send_template(phone=_phone(), name="t", language="he", body_params=[]))
    for text in (log1, log2, log3, res1.detail, res2.detail, res3.detail):
        assert TOKEN not in text and "Bearer" not in text
    assert "[redacted]" in res1.detail
    print("✓ B7: הטוקן לא מופיע בלוג ולא בסיבת הכשל — גם כש-Meta מחזירה אותו בשגיאה")


# ============================================================================
# C. MetaProvider + send_batch
# ============================================================================

def _round_setup(db):
    from app import models

    ev = _event(db)
    g = _guest(db, ev.id, _phone(), "דנה כהן")
    g.guest_token = "tok-" + secrets.token_hex(6)
    em = models.EventMessage(event_id=ev.id, message_type="event_day", content="נוסח של הזוג",
                             is_active=True, trigger_offset_days=0, target_audience="all")
    db.add(em)
    db.commit()
    return ev, g, em


def _messages(db):
    from app import models

    return db.scalars(select(models.Message).order_by(models.Message.id)).all()


NOW = datetime(2026, 9, 8, 8, 0)  # יום האירוע, 11:00 בישראל


def test_step_without_template_is_not_sent_or_consumed() -> None:
    from app import communication as c

    db = Session(_engine())
    ev, g, em = _round_setup(db)
    for mode in ("meta", "meta_test"):
        with meta_env(mode=mode, recipients=g.phone) as fake, templates():
            actions = c.compute_due_messages(db, ev, now=NOW)
            result = c.send_due_messages(db, ev, actions)
            db.commit()
        assert fake.requests == [] and _messages(db) == []
        assert (result["sent"], result["failed"]) == (0, 0)
    # הסבב לא "נשרף": כשהתבנית מאושרת, אותה הודעה עדיין בתור.
    with meta_env(fake=FakeMeta(ok("wamid.late"))) as fake, templates(event_day=_spec()):
        actions = c.compute_due_messages(db, ev, now=NOW)
        assert len(actions) == 1
        c.send_due_messages(db, ev, actions)
        db.commit()
    assert len(fake.requests) == 1 and [m.status for m in _messages(db)] == ["sent"]
    print("✓ C1: שלב בלי Template — לא נשלח, לא נרשם, לא נשרף; אחרי אישור יוצא")


def test_template_send_through_batch() -> None:
    from app import communication as c
    from app import outbound

    db = Session(_engine())
    ev, g, em = _round_setup(db)
    with meta_env(fake=FakeMeta(ok("wamid.B"))) as fake, templates(event_day=_spec()):
        actions = c.compute_due_messages(db, ev, now=NOW)
        c.send_due_messages(db, ev, actions)
        db.commit()
    row = _messages(db)[0]
    body = fake.bodies()[0]
    assert body["template"]["name"] == "veya_test_tpl"
    params = body["template"]["components"][0]["parameters"]
    assert [p["text"] for p in params] == ["דנה", "יואב ודנה"], params
    assert body["template"]["components"][1]["parameters"][0]["text"] == g.guest_token
    assert body["biz_opaque_callback_data"] == outbound.callback_ref(row)
    assert (row.status, row.provider, row.provider_message_id) == ("sent", "meta", "wamid.B")
    assert row.body.startswith("[Template veya_test_tpl]") and g.guest_token not in row.body
    assert "נוסח של הזוג" not in row.body, "נרשם מה שבאמת נשלח, לא הנוסח שלא יצא"
    print("✓ C2: Template דרך המסלול — ערכים, טוקן בכפתור, מזהה פנימי, נרשם מה שנשלח")


def test_missing_value_is_not_sent() -> None:
    from app import communication as c

    db = Session(_engine())
    ev, g, em = _round_setup(db)
    g.guest_token = None
    db.commit()
    with meta_env() as fake, templates(event_day=_spec()):
        result = c.send_due_messages(db, ev, c.compute_due_messages(db, ev, now=NOW))
        db.commit()
    assert fake.requests == [] and _messages(db) == [] and result["sent"] == 0
    print("✓ C3: חסר ערך למילוי (טוקן) — לא נשלח ולא נרשם, במקום להיכשל ב-Meta")


def test_timeout_in_batch_stays_unknown_and_is_not_resent() -> None:
    from app import communication as c
    from app import whatsapp_meta as wm

    db = Session(_engine())
    ev, g, em = _round_setup(db)
    with meta_env(fake=FakeMeta("timeout")) as fake, templates(event_day=_spec()):
        result = c.send_due_messages(db, ev, c.compute_due_messages(db, ev, now=NOW))
        db.commit()
        again = c.compute_due_messages(db, ev, now=NOW)
    row = _messages(db)[0]
    assert (row.status, row.provider_status) == ("pending", wm.OUTCOME_UNKNOWN)
    assert "לא ידוע" in row.failure_reason and row.provider_message_id is None
    assert (result["sent"], result["failed"]) == (0, 0) and len(fake.requests) == 1
    assert again == [], "תוצאה לא ידועה — לא נשלח שוב"
    print("✓ C4: timeout בתוך המסלול — 'pending' + 'לא ידוע', לא נשלח שוב")


def test_owner_free_text_not_sent_in_meta_mode() -> None:
    from app import messaging

    with meta_env() as fake:
        res = messaging.get_provider().send_invitation(_phone(), "טקסט חופשי")
    assert res.status == "failed" and fake.requests == []
    print("✓ C5: טקסט חופשי בלי Template (למשל 'שליחת בדיקה') — לא יוצא ל-Meta")


# ============================================================================
# D. השלמת הודעה תקועה מ-webhook
# ============================================================================

def _pending_row(api, guest, provider="meta"):
    from app import models

    db = _db()
    try:
        m = models.Message(event_id=api.event_id, guest_id=guest["id"], direction="outbound",
                           kind="event_day", body="x", status="pending", provider=provider,
                           provider_status="send_outcome_unknown",
                           failure_reason="לא ידוע אם Meta קיבלה")
        db.add(m)
        db.commit()
        return m.id
    finally:
        db.close()


def _row(row_id):
    from app import models

    db = _db()
    try:
        return db.get(models.Message, row_id)
    finally:
        db.close()


def _status(wamid, callback, recipient, status="delivered"):
    st = {"id": wamid, "status": status, "timestamp": "1790000000", "recipient_id": recipient}
    if callback is not None:
        st["biz_opaque_callback_data"] = callback
    return _payload(statuses=[st])


def test_reconcile_pending_full_match() -> None:
    api, _ = bootstrap()
    phone = _phone()
    g = api.add_guest("מוזמן תקוע", phone)
    rid = _pending_row(api, g)
    ref = f"veya:m{rid}:e{api.event_id}:g{g['id']}"
    wamid = "wamid.rec-" + secrets.token_hex(6)
    assert _post(api, _status(wamid, ref, "972" + phone[1:])).status_code == 200
    row = _row(rid)
    assert (row.status, row.provider_message_id) == ("delivered", wamid)
    assert row.failure_reason == "" and row.delivered_at is not None and row.sent_at is not None
    # עדכון "נקראה" מאוחר יותר מגיע כבר לפי wamid.
    assert _post(api, _status(wamid, ref, "972" + phone[1:], "read")).status_code == 200
    assert _row(rid).status == "read"
    print("✓ D1: הודעה תקועה נסגרת מ-webhook בהתאמה מלאה; עדכונים הבאים לפי wamid")


def test_reconcile_refuses_any_mismatch() -> None:
    api, _ = bootstrap()
    phone, other_phone = _phone(), _phone()
    g = api.add_guest("מוזמן א", phone)
    g2 = api.add_guest("מוזמן ב", other_phone)
    intl = "972" + phone[1:]
    rid = _pending_row(api, g)
    good = f"veya:m{rid}:e{api.event_id}:g{g['id']}"
    taken_wamid = "wamid.taken-" + secrets.token_hex(6)
    from app import models

    db = _db()
    try:
        db.add(models.Message(event_id=api.event_id, guest_id=g2["id"], direction="outbound",
                              kind="invitation", body="x", status="sent", provider="meta",
                              provider_message_id=taken_wamid))
        db.commit()
    finally:
        db.close()
    cases = {
        "ערך זר": ("veya:hello_world", intl, None),
        "פורמט שבור": (f"veya:m{rid}:e{api.event_id}", intl, None),
        "מוזמן אחר בערך": (f"veya:m{rid}:e{api.event_id}:g{g2['id']}", intl, None),
        "אירוע אחר בערך": (f"veya:m{rid}:e{api.event_id + 999}:g{g['id']}", intl, None),
        "טלפון אחר": (good, "972" + other_phone[1:], None),
        "בלי recipient_id": (good, None, None),
        "wamid כבר תפוס": (good, intl, taken_wamid),
    }
    for label, (ref, recipient, wamid) in cases.items():
        st = {"id": wamid or "wamid.x-" + secrets.token_hex(6), "status": "delivered",
              "timestamp": "1790000000", "biz_opaque_callback_data": ref}
        if recipient:
            st["recipient_id"] = recipient
        assert _post(api, _payload(statuses=[st])).status_code == 200
        row = _row(rid)
        assert (row.status, row.provider_message_id) == ("pending", None), label
    # שורה שכבר לא pending — לא נדרסת.
    rid2 = _pending_row(api, g)
    db = _db()
    try:
        db.get(models.Message, rid2).status = "failed"
        db.commit()
    finally:
        db.close()
    ref2 = f"veya:m{rid2}:e{api.event_id}:g{g['id']}"
    _post(api, _status("wamid.y-" + secrets.token_hex(6), ref2, intl))
    assert _row(rid2).status == "failed"
    print(f"✓ D2: כל אי-התאמה ({len(cases) + 1} מקרים) — השורה לא משתנה")


# ============================================================================
# E. הודעה חופשית מאורח
# ============================================================================

def _text(from_phone, wamid, body, msg_type="text"):
    msg = {"from": from_phone, "id": wamid, "type": msg_type}
    if msg_type == "text":
        msg["text"] = {"body": body}
    return msg


def test_free_text_needs_attention_no_rsvp_change() -> None:
    from tests.test_whatsapp_safety import _guest_row, _inbound_rows

    api, _ = bootstrap()
    _open_rsvp(api)
    phone = _phone()
    g = api.add_guest("מוזמן כותב", phone)
    secret_text = "נגיע 3 אנשים, תודה " + secrets.token_hex(4)
    payload = _payload(_text("972" + phone[1:], "wamid.t-" + secrets.token_hex(6), secret_text))
    buf = io.StringIO()
    with redirect_stdout(buf):
        for _ in range(2):
            assert _post(api, payload).status_code == 200
    rows = _inbound_rows(api.event_id)
    assert len(rows) == 1 and rows[0].status == "needs_attention" and rows[0].guest_id == g["id"]
    assert rows[0].body == secret_text
    assert _guest_row(g["id"]).rsvp_status == "pending", "טקסט חופשי לא משנה RSVP"
    assert secret_text not in buf.getvalue() and phone not in buf.getvalue(), "בלי תוכן/טלפון בלוג"
    print("✓ E1: טקסט חופשי — 'דורש טיפול', RSVP לא משתנה, פעם אחת, בלי תוכן בלוג")


def test_free_media_and_unmatched() -> None:
    from tests.test_whatsapp_safety import _inbound_rows

    api, _ = bootstrap()
    phone = _phone()
    api.add_guest("מוזמן תמונה", phone)
    _post(api, _payload(_text("972" + phone[1:], "wamid.i-" + secrets.token_hex(6), None, "image")))
    rows = _inbound_rows(api.event_id)
    assert len(rows) == 1 and rows[0].body == "[תמונה]" and rows[0].status == "needs_attention"
    # שולח שלא ברשימות — 200, בלי שורת הודעה באף אירוע.
    assert _post(api, _payload(_text("972" + _phone()[1:], "wamid.u-" + secrets.token_hex(6), "שלום"))).status_code == 200
    assert len(_inbound_rows(api.event_id)) == 1
    print("✓ E2: תמונה → '[תמונה]'; שולח לא מוכר → 200 בלי שורה")


# ============================================================================
# F. כלי hello_world
# ============================================================================

def test_hello_world_requires_every_safety_condition() -> None:
    from app import messaging
    from app import whatsapp_meta as wm

    me = _phone()
    with meta_env(mode="meta_test", recipients=me, fake=FakeMeta(ok("wamid.hw"))) as fake:
        check, res = wm.send_hello_world(me)
    assert check.ok and res.ok and res.provider_message_id == "wamid.hw"
    body = fake.bodies()[0]
    assert body["template"] == {"name": "hello_world", "language": {"code": "en_US"}}
    assert body["to"] == "972" + me[1:]

    refusals = {
        "mock": dict(mode="mock", recipients=me),
        "meta (לא בדיקה)": dict(mode="meta", recipients=me),
        "מצב שגוי": dict(mode="meta-test", recipients=me),
        "production": dict(mode="meta_test", recipients=me, VEYA_ENV="production"),
        "לא ברשימה": dict(mode="meta_test", recipients=_phone()),
        "רשימה ריקה": dict(mode="meta_test", recipients=""),
        "חסר טוקן": dict(mode="meta_test", recipients=me, token=None),
    }
    for label, kw in refusals.items():
        with meta_env(**kw) as fake:
            check, res = wm.send_hello_world(me)
        assert not check.ok and res is None and fake.requests == [], label
    real_stop = messaging.emergency_stop_active
    messaging.emergency_stop_active = lambda: True
    try:
        with meta_env(mode="meta_test", recipients=me) as fake:
            check, res = wm.send_hello_world(me)
        assert not check.ok and "עצירת החירום פעילה" in check.reasons and fake.requests == []
    finally:
        messaging.emergency_stop_active = real_stop
    print(f"✓ F1: hello_world — שולח רק כשכל התנאים מתקיימים; {len(refusals) + 1} סירובים")


def test_hello_world_script_dry_run_by_default() -> None:
    from scripts import whatsapp_hello_world as script

    me = _phone()
    with meta_env(mode="meta_test", recipients=me) as fake:
        code, out = _captured(lambda: script.main(["--to", me]))
    assert code == 0 and fake.requests == [] and "בדיקה בלבד" in out
    assert TOKEN not in out and me not in out and "1234567890" not in out
    with meta_env(mode="meta_test", recipients=me, fake=FakeMeta(ok("wamid.s"))) as fake:
        code, out = _captured(lambda: script.main(["--to", me, "--send"]))
    assert code == 0 and len(fake.requests) == 1 and TOKEN not in out
    print("✓ F2: הסקריפט — בלי --send לא שולח; לא מדפיס טוקן, מזהה מספר או טלפון מלא")


def test_hello_world_script_reads_env_file_before_settings() -> None:
    """הכלי טוען את קובץ ה-.env לפני שהוא קורא הגדרות (אחרת היה מסרב תמיד),
    ומשתנה שכבר מוגדר בסביבה גובר על הקובץ. רץ בתהליך נפרד — סביבה נקייה."""
    me = _phone()
    with tempfile.TemporaryDirectory() as tmp:
        env_file = Path(tmp) / ".env"
        env_file.write_text(
            "WHATSAPP_MODE=meta_test\n"
            f"WHATSAPP_TEST_RECIPIENTS={me}\n"
            f"WHATSAPP_ACCESS_TOKEN={TOKEN}\n"
            "WHATSAPP_PHONE_NUMBER_ID=1234567890\n"
            f"DATABASE_URL=sqlite:///{tmp}/x.db\n",
            encoding="utf-8",
        )
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("WHATSAPP_") and k not in ("VEYA_ENV", "DATABASE_URL")}
        backend = Path(__file__).resolve().parent.parent
        script = str(backend / "scripts" / "whatsapp_hello_world.py")
        run = lambda extra_env: subprocess.run(  # noqa: E731
            [sys.executable, script, "--env-file", str(env_file), "--to", me],
            cwd=tmp, env={**env, **extra_env}, capture_output=True, text=True, timeout=60,
        )
        ok_run = run({})
        assert ok_run.returncode == 0, ok_run.stdout + ok_run.stderr
        assert "כל תנאי הבטיחות מתקיימים" in ok_run.stdout and "בדיקה בלבד" in ok_run.stdout
        assert TOKEN not in ok_run.stdout and me not in ok_run.stdout
        # משתנה בסביבה גובר על הקובץ: mock בסביבה → מסרב.
        mock_run = run({"WHATSAPP_MODE": "mock"})
        assert mock_run.returncode == 2 and "meta_test" in mock_run.stdout
    print("✓ F3: הכלי טוען את .env לפני ההגדרות; משתנה בסביבה גובר על הקובץ")


# ============================================================================
# G. hub.verify_token בלוג של uvicorn אמיתי
# ============================================================================

def test_verify_token_redacted_in_real_uvicorn_log() -> None:
    verify = "vt-" + secrets.token_hex(12)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{tmp.name}", WHATSAPP_VERIFY_TOKEN=verify,
               JWT_SECRET="test-secret-not-for-production-usage")
    env.pop("VEYA_ENV", None)
    backend = Path(__file__).resolve().parent.parent
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=str(backend), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(120):
            try:
                urllib.request.urlopen(base + "/health", timeout=1)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.25)
        url = f"{base}/messaging/webhook?hub.mode=subscribe&hub.verify_token={verify}&hub.challenge=4242"
        body = urllib.request.urlopen(url, timeout=5).read().decode()
        assert body == "4242", "האימות עצמו חייב להמשיך לעבוד"
        time.sleep(0.5)
    finally:
        proc.terminate()
        out, _ = proc.communicate(timeout=10)
        os.unlink(tmp.name)
    assert "/messaging/webhook?" in out, "שורת הגישה צריכה להופיע בלוג"
    assert verify not in out, "הטוקן נכתב ללוג!"
    assert "hub.verify_token=[redacted]" in out
    print("✓ G1: שרת uvicorn אמיתי — האימות עובד, והטוקן מוסתר בלוג")


# ============================================================================
# H. עצירת חירום
# ============================================================================

def test_emergency_stop_beats_every_mode() -> None:
    from app import messaging

    real_stop = messaging.emergency_stop_active
    messaging.emergency_stop_active = lambda: True
    try:
        for mode in ("mock", "meta_test", "meta"):
            with meta_env(mode=mode, recipients=_phone()) as fake:
                provider = messaging.get_provider()
                assert isinstance(provider, messaging.StoppedProvider), mode
                assert not provider.send_invitation(_phone(), "x").ok and fake.requests == []
    finally:
        messaging.emergency_stop_active = real_stop
    print("✓ H1: עצירת חירום גוברת על mock / meta_test / meta")


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
        print()
        print("=== כל בדיקות החיבור ל-Meta עברו ===")
    finally:
        shutdown()
