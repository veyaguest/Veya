"""פניות מדף הבית — מסך הצוות והתראה במייל (2026-10-29).

מה נבדק:
  1. ``GET /admin/leads``: בלי התחברות 401, משתמש רגיל 403, צוות (Support) 200.
  2. הפניות חוזרות מהחדשה לישנה, עם שם הסוג בעברית וימים עד האירוע.
  3. פנייה חדשה שולחת מייל לכתובת הצוות, עם השם, הטלפון, הסוג והקישור למסך.
  4. בלי כתובת צוות — הפנייה נשמרת (201) ולא נשלח כלום.
  5. תקלה בשליחת המייל לא מפילה את הפנייה.

הרצה: ``venv/bin/python -m pytest tests/test_admin_leads.py``
"""
from __future__ import annotations

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import make_client  # noqa: E402
from tests.test_help_context import _h  # noqa: E402
from tests.test_help_requests import _CaptureEmails, _make_admin, _register, _with_env  # noqa: E402


def _reset() -> None:
    from app.routers import public_leads

    public_leads.lead_limiter.reset()


def _date(days: int) -> str:
    from app.guest_journey import today_in_israel

    return (today_in_israel() + timedelta(days=days)).isoformat()


def _lead(client, name: str = "דנה כהן", phone: str = "050-1234567", event_type: str = "bar_mitzvah", days: int = 40):
    _reset()
    return client.post("/public/leads", json={
        "name": name, "phone": phone, "event_type": event_type, "event_date": _date(days),
    })


def test_only_staff_can_read_leads() -> None:
    client, _ = make_client()
    with _with_env("VEYA_SUPPORT_EMAIL", None):
        assert _lead(client).status_code == 201
    _, user = _register(client, "משתמש רגיל")
    assert client.get("/admin/leads").status_code == 401
    assert client.get("/admin/leads", headers=_h(user)).status_code == 403
    support = _make_admin(client, "support")
    r = client.get("/admin/leads", headers=_h(support))
    assert r.status_code == 200, r.text
    assert any(row["name"] == "דנה כהן" for row in r.json())


def test_newest_first_with_hebrew_label_and_days() -> None:
    client, _ = make_client()
    with _with_env("VEYA_SUPPORT_EMAIL", None):
        assert _lead(client, name="ראשונה", event_type="wedding", days=90).status_code == 201
        assert _lead(client, name="שנייה", phone="052-7654321", event_type="brit", days=12).status_code == 201
    support = _make_admin(client, "support")
    rows = client.get("/admin/leads", headers=_h(support)).json()
    names = [r["name"] for r in rows]
    assert names.index("שנייה") < names.index("ראשונה"), "החדשה ראשונה"
    second = next(r for r in rows if r["name"] == "שנייה")
    assert second["event_type_label"] == "ברית"
    assert second["days_to_event"] == 12
    assert second["phone"].startswith("05")


def test_new_lead_emails_the_team() -> None:
    client, _ = make_client()
    with _with_env("VEYA_SUPPORT_EMAIL", "team@example.com"), _CaptureEmails(mode="live") as mails:
        assert _lead(client, name="יוסי לוי", event_type="business", days=30).status_code == 201
    assert len(mails.sent) == 1
    m = mails.sent[0]
    assert m["to"] == "team@example.com"
    assert "יוסי לוי" in m["subject"]
    body = m.get("text_body") or m.get("text") or ""
    assert "אירוע עסקי" in body and "בעוד 30 ימים" in body
    assert "/app#/admin/leads" in body


def test_no_team_address_still_saves_without_email() -> None:
    client, _ = make_client()
    with _with_env("VEYA_SUPPORT_EMAIL", None), _CaptureEmails(mode="live") as mails:
        assert _lead(client, name="בלי כתובת").status_code == 201
    assert mails.sent == []
    support = _make_admin(client, "support")
    assert any(r["name"] == "בלי כתובת" for r in client.get("/admin/leads", headers=_h(support)).json())


def test_email_failure_does_not_lose_the_lead() -> None:
    client, _ = make_client()
    with _with_env("VEYA_SUPPORT_EMAIL", "team@example.com"), _CaptureEmails(mode="live", fail="raise"):
        assert _lead(client, name="מייל נכשל").status_code == 201
    support = _make_admin(client, "support")
    assert any(r["name"] == "מייל נכשל" for r in client.get("/admin/leads", headers=_h(support)).json())
