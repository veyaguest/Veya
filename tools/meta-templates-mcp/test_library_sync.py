"""בדיקות לסנכרון ספריית הנוסחים ↔ תבניות Meta — בלי רשת (ספרייה ו-Meta מדומות)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import library_sync as ls  # noqa: E402
import server  # noqa: E402
import veya_meta as vm  # noqa: E402
from test_veya_meta import TOKEN, FakeMeta, _tpl  # noqa: E402

INV = ("היי {{guest_name}},\n\nאנחנו שמחים להזמין אתכם לחתונה שלנו.\n\n{{groom_name}} & {{bride_name}}\n\n"
       "📅 {{event_date}}\n\nנשמח לראות אתכם.\n\nלאישור הגעה:\n{{rsvp_link}}\n\nלניווט:\n{{navigation_link}}")
REM = "היי {{guest_name}},\n\nרק מזכירים שהחתונה מתקרבת 😊\n\nלאישור הגעה:\n{{rsvp_link}}"
THX = "היי {{guest_name}} ❤️\n\nתודה שהייתם איתנו.\n\n{{groom_name}} & {{bride_name}}"


def _w(mt, n, content):
    return {"event_type": "wedding", "message_type": mt, "option_number": n, "tone": "t", "content": content}


LIB = {"categories": [{"key": "x", "wordings": [
    _w("invitation", 1, INV), _w("reminder_1", 2, REM), _w("thank_you", 1, THX)]}]}


class FakeMetaWithUploads(FakeMeta):
    """+ העלאת תמונת הדוגמה (Resumable Upload) לגרסת התמונה של ההזמנה."""

    def __call__(self, request):
        import httpx

        path = request.url.path.split("/", 2)[-1]
        if path == "999/uploads":
            self.calls.append((request.method, request.url.path, request))
            return httpx.Response(200, json={"id": "upload:abc"})
        if path == "upload:abc":
            self.calls.append((request.method, request.url.path, request))
            return httpx.Response(200, json={"h": "HANDLE-1"})
        return super().__call__(request)


@pytest.fixture
def env(monkeypatch):
    def make(templates):
        fake = FakeMetaWithUploads(templates)
        import httpx
        monkeypatch.setattr(vm, "_transport", httpx.MockTransport(fake))
        monkeypatch.setattr(vm, "_token_override", TOKEN)
        monkeypatch.setattr(ls, "_library_override", LIB)
        monkeypatch.setattr(ls, "TEMPLATE_CAP", 250)
        ls._batches.clear()
        return fake
    return make


def test_conversion_matches_site_rendering():
    d = ls.to_draft(_w("invitation", 1, INV))
    assert d["name"] == "veya_wed_inv_01" and d["state"] == "ok"
    body = d["draft"]["body"]
    assert "לאישור הגעה" not in body and "לניווט" not in body and "rsvp_link" not in body
    assert body.startswith("היי {{1}},") and "{{2}} & {{3}}" in body and "📅 {{4}}" in body
    assert d["params"] == ["guest_name", "groom_name", "bride_name", "event_date"]
    assert [b["text"] for b in d["draft"]["buttons"]] == ["לצפייה בהזמנה", "ניווט למקום"]
    assert d["draft"]["buttons"][0]["url"] == vm.VEYA_CONFIRM_URL


def test_ending_with_variable_is_never_padded():
    d = ls.to_draft(_w("thank_you", 1, THX))
    assert d["state"] == "needs_source_fix"
    assert d["draft"]["body"].rstrip().endswith("{{3}}")  # לא הוספנו טקסט


def test_sync_report(env):
    same = ls.to_draft(_w("reminder_1", 2, REM))["draft"]
    env([_tpl("veya_wed_rem1_02", same["body"], [{"type": "URL", "text": "אישור הגעה", "url": vm.VEYA_CONFIRM_URL}]),
         _tpl("veya_wed_inv_01", "היי {{1}} נוסח אחר", [])])
    r = ls.check_sync(vm.fetch_templates(), LIB)
    assert [x["name"] for x in r["details"]["in_sync"]] == ["veya_wed_rem1_02"]
    assert [x["name"] for x in r["details"]["differs"]] == ["veya_wed_inv_01"]
    assert [x["name"] for x in r["details"]["needs_source_fix"]] == ["veya_wed_thx_01"]
    # לכל הזמנה גם גרסת תמונה (Header) — חסרה עד שתיווצר.
    assert r["details"]["missing"] == ["veya_wed_inv_01_img"]


def test_batch_needs_exact_count_and_respects_cap(env, monkeypatch):
    fake = env([])
    prep = ls.prepare_batch(event_type="wedding")
    # הזמנה + גרסת התמונה שלה + תזכורת; בלי התודה שצריכה תיקון.
    assert prep["count"] == 3 and "batch_id" in prep
    assert prep["categories"] == {"MARKETING": 2, "UTILITY": 1} and prep["with_image"] == 1
    assert all(m == "GET" for m, _, _ in fake.calls)
    with pytest.raises(vm.MetaError):
        ls.submit_batch(prep["batch_id"], "2")
    res = ls.submit_batch(prep["batch_id"], "3", pause=0)
    assert res["created"] == 3
    uploads = [p for m, p, _ in fake.calls if m == "POST" and ("uploads" in p or "upload:" in p)]
    assert len(uploads) == 2  # פתיחת העלאה + הקובץ — פעם אחת למנה
    created = [json.loads(r.content) for m, p, r in fake.calls
               if m == "POST" and p.endswith("/message_templates")]
    assert [c["name"] for c in created] == ["veya_wed_inv_01", "veya_wed_inv_01_img", "veya_wed_rem1_02"]
    img = next(c for c in created if c["name"].endswith("_img"))
    header = next(c for c in img["components"] if c["type"] == "HEADER")
    assert header["format"] == "IMAGE" and header["example"]["header_handle"] == ["HANDLE-1"]
    assert [c["category"] for c in created] == ["MARKETING", "MARKETING", "UTILITY"]
    with pytest.raises(vm.MetaError):  # מנה משמשת פעם אחת
        ls.submit_batch(prep["batch_id"], "3")
    monkeypatch.setattr(ls, "TEMPLATE_CAP", 1)
    assert "error_he" in ls.prepare_batch(event_type="wedding")


def test_server_exposes_library_tools(env):
    env([])
    names = {t["name"] for t in server.TOOLS}
    assert {"check_library_sync", "prepare_library_batch", "submit_library_batch"} <= names
    out = server.call_tool("check_library_sync", {"event_type": "wedding"})
    assert not out["isError"] and TOKEN not in out["content"][0]["text"]
