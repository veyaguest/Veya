"""בדיקות ה-API של "לא קיבלו את ההודעה" (``/automation/delivery-issues``).

- הזוג רואה רק את המוזמנים שלו, עם סיבה וקישור wa.me מוכן.
- "שליחה אישית" נרשמת, ומבטלת את השליחה החוזרת האוטומטית.
- אירוע של זוג אחר — 404, גם עם מזהה מוזמן אמיתי.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


def teardown_module(module) -> None:  # noqa: ARG001
    shutdown()


def _fail(event_id: int, guest_id: int, code: int, status: str = "failed") -> None:
    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        db.add(models.Message(
            event_id=event_id, guest_id=guest_id, direction="outbound", kind="invitation",
            channel="whatsapp", status=status, provider="meta", failure_code=code,
            created_at=datetime.utcnow() - timedelta(hours=2), cycle_number=1,
        ))
        db.commit()
    finally:
        db.close()


def test_list_and_personal_send() -> None:
    api, _ = bootstrap()
    capped = api.add_guest("רוני לוי", "0501111111")
    gone = api.add_guest("טל כהן", "0502222222")
    api.add_guest("נועה בר", "0503333333")       # בלי בעיה — לא ברשימה
    _fail(api.event_id, capped["id"], 131049)
    _fail(api.event_id, gone["id"], 131026)

    r = api.client.get("/automation/delivery-issues", headers=api.headers)
    assert r.status_code == 200, r.text
    rows = {row["guest_id"]: row for row in r.json()["issues"]}
    assert set(rows) == {capped["id"], gone["id"]}
    assert rows[capped["id"]]["reason"] == "marketing_cap"
    assert rows[capped["id"]]["resend_at"] is not None
    assert rows[gone["id"]]["reason"] == "undeliverable"
    link = rows[capped["id"]]["whatsapp_link"]
    assert link.startswith("https://wa.me/972501111111?text=")
    assert "היי רוני," in unquote(link) and "/confirm/" in unquote(link)

    r = api.client.post(f"/automation/delivery-issues/{capped['id']}/personal", headers=api.headers)
    assert r.status_code == 200, r.text
    row = next(x for x in r.json()["issues"] if x["guest_id"] == capped["id"])
    assert row["sent_personally_at"] is not None
    assert row["resend_at"] is None, "אחרי שליחה אישית — אין שליחה חוזרת אוטומטית"


def test_other_couple_cannot_touch_guests() -> None:
    owner, _ = bootstrap()
    other, _ = bootstrap()
    g = owner.add_guest("דנה כהן", "0504444444")
    _fail(owner.event_id, g["id"], 131026)

    r = other.client.get("/automation/delivery-issues", headers=other.headers)
    assert r.status_code == 200 and r.json()["issues"] == []
    r = other.client.post(f"/automation/delivery-issues/{g['id']}/personal", headers=other.headers)
    assert r.status_code == 404, r.text
    # בלי הרשאה לאירוע בכלל.
    r = other.client.get("/automation/delivery-issues", headers={
        **other.headers, "X-Event-Id": str(owner.event_id)})
    assert r.status_code in (403, 404), r.text
