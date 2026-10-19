"""בדיקות לכלי ניהול התבניות — בלי רשת ובלי Keychain (Meta מדומה).

הרצה (מתיקיית השורש):
    backend/venv/bin/python -m pytest tools/meta-templates-mcp -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402
import veya_meta as vm  # noqa: E402

TOKEN = "EAAtesttoken1234567890"
WABA = "111222333"
CONFIRM = vm.VEYA_CONFIRM_URL


def _tpl(name, body, buttons=(), header=None, status="APPROVED", lang="he", tid=None):
    comps = []
    if header:
        comps.append({"type": "HEADER", "format": header})
    comps.append({"type": "BODY", "text": body})
    if buttons:
        comps.append({"type": "BUTTONS", "buttons": list(buttons)})
    return {"id": tid or f"id_{name}", "name": name, "language": lang, "status": status,
            "category": "UTILITY", "components": comps}


INV_BODY = vm.doc_expectations()["veya_invitation"]["body_text"]
URL_BTN = {"type": "URL", "text": "לצפייה בהזמנה", "url": CONFIRM}


class FakeMeta:
    def __init__(self, templates):
        self.templates = templates
        self.calls = []

    def __call__(self, request: httpx.Request):
        self.calls.append((request.method, request.url.path, request))
        path = request.url.path.split("/", 2)[-1]  # בלי /v26.0/
        if path == "debug_token":
            return httpx.Response(200, json={"data": {
                "is_valid": True, "type": "SYSTEM_USER", "app_id": "999", "application": "VEYA",
                "expires_at": 0, "scopes": ["whatsapp_business_management"],
                "granular_scopes": [{"scope": "whatsapp_business_management", "target_ids": [WABA]}],
            }})
        if path == f"{WABA}/message_templates" and request.method == "GET":
            name = request.url.params.get("name")
            data = [t for t in self.templates if not name or name in t["name"]]
            return httpx.Response(200, json={"data": data, "paging": {}})
        if path == f"{WABA}/message_templates" and request.method == "POST":
            body = json.loads(request.content)
            return httpx.Response(200, json={"id": "new1", "status": "PENDING", "category": body["category"]})
        if path.startswith("id_") and request.method == "POST":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(400, json={"error": {
            "code": 100, "message": f"unknown path {path} token={TOKEN}"}})


@pytest.fixture
def meta(monkeypatch):
    def make(templates):
        fake = FakeMeta(templates)
        monkeypatch.setattr(vm, "_transport", httpx.MockTransport(fake))
        monkeypatch.setattr(vm, "_token_override", TOKEN)
        monkeypatch.delenv("VEYA_META_WABA_ID", raising=False)
        vm._drafts.clear()
        return fake
    return make


def _good_draft(**kw):
    d = {"name": "veya_reminder_1", "language": "he", "category": "UTILITY",
         "body": "היי {{1}},\nרצינו לוודא שההזמנה ל{{2}} של {{3}} הגיעה אליכם.\nנשמח לדעת אם תגיעו.",
         "body_examples": ["דנה", "חתונה", "דניאל ושירה"],
         "buttons": [{"type": "url", "text": "לאישור הגעה", "url": CONFIRM,
                      "url_example": "https://veyaguest.co.il/confirm/AbCdEf123456"}]}
    d.update(kw)
    return d


# ---- בדיקה מקומית ----

def test_all_approved_doc_wordings_pass_validation():
    for name, exp in vm.doc_expectations().items():
        n = exp["body_variables"]
        d = {"name": name, "body": exp["body_text"], "body_examples": ["x"] * n}
        if exp["url_button"]:
            d["buttons"] = [{"type": "url", "text": exp["button_text"], "url": CONFIRM,
                             "url_example": "https://veyaguest.co.il/confirm/AbCdEf123456"}]
        v = vm.validate_draft(d)
        assert v["ok"], (name, v["errors_he"])
        assert v["body_variables"] == n


@pytest.mark.parametrize("patch,needle", [
    ({"name": "Veya-Reminder"}, "שם"),
    ({"body": "{{1}} שלום לכם", "body_examples": ["דנה"]}, "מתחילה או נגמרת"),
    ({"body": "שלום לכם {{1}}", "body_examples": ["דנה"]}, "מתחילה או נגמרת"),
    ({"body": "היי {{1}} ו-{{3}} שלום", "body_examples": ["a", "b"]}, "ברצף"),
    ({"body_examples": ["דנה"]}, "דוגמאות"),
    ({"buttons": [{"type": "url", "text": "x", "url": "https://a.co/{{1}}/x", "url_example": "https://a.co/1/x"}]},
     "בסוף הכתובת"),
    ({"buttons": [{"type": "quick_reply", "text": "א" * 26}]}, "25"),
])
def test_validation_catches_meta_rule_breaks(patch, needle):
    v = vm.validate_draft(_good_draft(**patch))
    assert not v["ok"]
    assert any(needle in e for e in v["errors_he"]), v["errors_he"]


def test_validation_warns_on_veya_conventions():
    v = vm.validate_draft(_good_draft(language="en", category="MARKETING",
                                      body="היי {{1}}, שמחים 🎉 ל{{2}} של {{3}} היום",))
    w = " ".join(v["warnings_he"])
    assert "he" in w and "Utility" in w and "🎉" in w


# ---- התאמה לקוד ----

def test_alignment_flags_missing_header_and_wrong_button(meta):
    meta([
        _tpl("veya_inv_pilot", "היי {{1}}, מוזמנים לחתונה", [
            {"type": "URL", "text": "לאישור", "url": CONFIRM},
            {"type": "URL", "text": "ניווט", "url": "https://waze.com/ul"}]),
        _tpl("veya_invitation", INV_BODY, [URL_BTN]),
        _tpl("veya_invitation_image", INV_BODY, [{"type": "URL", "text": "לצפייה בהזמנה",
                                                  "url": "https://other.example/{{1}}"}]),
        _tpl("hello_world", "Hello World", lang="en_US"),
    ])
    r = {x["name"]: x for x in vm.check_alignment(vm.fetch_templates())["checked"]}
    assert r["veya_inv_pilot"]["ok"], r["veya_inv_pilot"]
    assert r["veya_invitation"]["ok"], r["veya_invitation"]
    probs = " ".join(r["veya_invitation_image"]["problems_he"])
    assert "Image" in probs and "other.example" in probs
    assert r["veya_reminder_1"]["exists"] is False and r["veya_reminder_1"]["ok"]  # מתוכננת, לא שגיאה


def test_alignment_wrong_language_and_pending(meta):
    meta([_tpl("veya_invitation", INV_BODY, [URL_BTN], lang="en"),
          _tpl("veya_inv_pilot", "היי {{1}}, מוזמנים", [URL_BTN], status="PENDING")])
    r = {x["name"]: x for x in vm.check_alignment(vm.fetch_templates())["checked"]}
    assert "en" in r["veya_invitation"]["problems_he"][0]
    assert any("PENDING" in p for p in r["veya_inv_pilot"]["problems_he"])


# ---- כתיבה: רק בשני שלבים ועם אישור ----

def test_create_needs_prepare_then_exact_confirm(meta):
    fake = meta([])
    prep = vm.prepare_create(_good_draft())
    assert prep["validation"]["ok"], prep
    assert all(m == "GET" for m, _, _ in fake.calls), "prepare לא כותב ל-Meta"
    with pytest.raises(vm.MetaError):
        vm.submit_create(prep["draft_id"], "veya_reminder_2")
    with pytest.raises(vm.MetaError):
        vm.submit_create("d_unknown", "veya_reminder_1")
    res = vm.submit_create(prep["draft_id"], "veya_reminder_1")
    assert res["created"] and res["status"] == "PENDING"
    posts = [r for m, _, r in fake.calls if m == "POST"]
    assert len(posts) == 1
    sent = json.loads(posts[0].content)
    assert sent["language"] == "he" and sent["category"] == "UTILITY"
    btn = next(c for c in sent["components"] if c["type"] == "BUTTONS")["buttons"][0]
    assert btn["url"] == CONFIRM and btn["example"][0].startswith("https://veyaguest.co.il/confirm/")
    with pytest.raises(vm.MetaError):  # טיוטה משמשת פעם אחת
        vm.submit_create(prep["draft_id"], "veya_reminder_1")


def test_create_refuses_existing_name(meta):
    meta([_tpl("veya_reminder_1", "היי {{1}} שלום")])
    prep = vm.prepare_create(_good_draft())
    assert not prep["validation"]["ok"] and "draft_id" not in prep


def test_update_locked_pilot_and_status_rules(meta):
    meta([_tpl("veya_inv_pilot", "היי {{1}} שלום"),
          _tpl("veya_reminder_1", "היי {{1}} שלום", status="PENDING")])
    with pytest.raises(vm.MetaError) as e:
        vm.prepare_update(_good_draft(name="veya_inv_pilot"))
    assert "נעולה" in e.value.info["explanation_he"]
    prep = vm.prepare_update(_good_draft())
    assert not prep["validation"]["ok"] and "draft_id" not in prep


def test_update_flow(meta):
    fake = meta([_tpl("veya_reminder_1", "היי {{1}} שלום", status="REJECTED")])
    prep = vm.prepare_update(_good_draft())
    assert prep["validation"]["ok"], prep
    res = vm.submit_update(prep["draft_id"], "veya_reminder_1")
    assert res["updated"]
    assert [p for m, p, _ in fake.calls if m == "POST"] == ["/v26.0/id_veya_reminder_1"]


# ---- בטיחות ----

def test_token_never_leaks_in_errors(meta):
    meta([])
    out = server.call_tool("get_template", {"name": "x", "waba_id": "nope"})
    text = out["content"][0]["text"]
    assert out["isError"] and TOKEN not in text and "[redacted]" in text


def test_no_send_tools_and_no_messages_endpoint(meta):
    fake = meta([_tpl("veya_inv_pilot", "היי {{1}} שלום", [URL_BTN])])
    names = {t["name"] for t in server.TOOLS}
    assert not any("send" in n for n in names)
    for n in ("meta_connection_status", "list_templates", "check_veya_alignment"):
        server.call_tool(n, {})
    assert not any(p.endswith("/messages") or p.endswith("/media") for _, p, _ in fake.calls)
    src = (Path(vm.__file__).read_text() + Path(server.__file__).read_text())
    assert "/messages\"" not in src and "/media\"" not in src


def test_missing_keychain_token_is_explained(monkeypatch):
    monkeypatch.setattr(vm, "_token_override", "")
    out = server.call_tool("list_templates", {})
    assert out["isError"] and "Keychain" in out["content"][0]["text"]


# ---- פרוטוקול ----

def test_jsonrpc_handshake_and_list():
    init = server.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2025-06-18", "capabilities": {}}})
    assert init["result"]["protocolVersion"] == "2025-06-18"
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert {t["name"] for t in tools} == set(server.HANDLERS)
    bad = server.handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})
    assert bad["error"]["code"] == -32601
