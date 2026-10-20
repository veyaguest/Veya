"""התראות האדמין על הודעות שלא הגיעו (``/admin/rsvp/delivery-alerts``).

- לכל מוזמן שההודעה האחרונה אליו לא הגיעה: הסבר בעברית לפי קוד Meta, ו"אצל
  המוזמן" או "אצלנו"; קוד לא מוכר — עם הטקסט המקורי של Meta.
- "לשלוח שוב": פעם אחת בלבד (לחיצה כפולה נעצרת), לעולם לא על ``pending``, לא
  בעצירת חירום; רק Admin ומעלה; נרשם ביומן האדמין.
"""
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


def teardown_module(module) -> None:  # noqa: ARG001
    shutdown()


def _session():
    from app.database import SessionLocal

    return SessionLocal()


def _admin(role: str):
    from app import auth, models

    db = _session()
    try:
        u = models.User(
            email=f"alerts-{uuid.uuid4().hex[:10]}@veya.test", password_hash=auth.hash_password("Test12345!"),
            display_name="צוות", is_admin=True, admin_role=role,
        )
        db.add(u)
        db.commit()
        return {"Authorization": f"Bearer {auth.create_access_token(u)}"}
    finally:
        db.close()


def _event_with_messages(api) -> None:
    from app import communication, models

    db = _session()
    try:
        communication.provision_event_messages(db, db.get(models.Event, api.event_id))
        em = communication.event_messages_by_type(db, api.event_id)["invitation"]
        em.content = em.content or "שלום {{guest_name}}, מוזמנים!"
        db.commit()
    finally:
        db.close()


def _msg(event_id: int, guest_id: int, *, status: str = "failed", code=None, reason: str = "") -> None:
    from app import models

    db = _session()
    try:
        db.add(models.Message(
            event_id=event_id, guest_id=guest_id, direction="outbound", kind="invitation",
            channel="whatsapp", status=status, provider="meta", failure_code=code,
            failure_reason=reason, created_at=datetime.utcnow() - timedelta(hours=3), cycle_number=1,
        ))
        db.commit()
    finally:
        db.close()


def _alerts(headers) -> dict:
    from tests.e2e_seating import make_client

    client, _ = make_client()
    r = client.get("/admin/rsvp/delivery-alerts", headers=headers)
    assert r.status_code == 200, r.text
    return {a["guest_id"]: a for a in r.json()["alerts"]}


def test_alerts_explain_each_failure() -> None:
    api, _ = bootstrap()
    support = _admin("support")
    gone = api.add_guest("טל כהן", "0501111111")
    template = api.add_guest("רוני לוי", "0502222222")
    odd = api.add_guest("נועה בר", "0503333333")
    fine = api.add_guest("איתי גל", "0504444444")
    _msg(api.event_id, gone["id"], code=131026, reason="Message undeliverable")
    _msg(api.event_id, template["id"], code=132001, reason="Template name does not exist")
    _msg(api.event_id, odd["id"], code=999999, reason="Something new from Meta")
    _msg(api.event_id, fine["id"], status="delivered")

    alerts = _alerts(support)
    assert fine["id"] not in alerts
    assert alerts[gone["id"]]["side"] == "guest" and "WhatsApp" in alerts[gone["id"]]["title"]
    assert alerts[gone["id"]]["reason"] == "undeliverable"
    assert alerts[template["id"]]["side"] == "veya" and "תבנית" in alerts[template["id"]]["title"]
    assert alerts[odd["id"]]["title"] == "סיבה לא מוכרת"
    assert alerts[odd["id"]]["raw_reason"] == "Something new from Meta"
    assert alerts[odd["id"]]["code"] == 999999 and alerts[odd["id"]]["message_label"] == "הזמנה"


def test_resend_once_admin_only_and_logged() -> None:
    from sqlalchemy import func, select

    from app import messaging, models

    api, _ = bootstrap()
    _event_with_messages(api)
    support, admin = _admin("support"), _admin("admin")
    g = api.add_guest("דנה כהן", "0505555555")
    _msg(api.event_id, g["id"], code=131000, reason="Something went wrong")
    url = f"/admin/rsvp/delivery-alerts/{g['id']}/resend"

    assert api.client.post(url, headers=support).status_code == 403

    original = messaging.emergency_stop_active
    messaging.emergency_stop_active = lambda: True
    try:
        r = api.client.post(url, headers=admin)
    finally:
        messaging.emergency_stop_active = original
    assert r.status_code == 409 and "עצירת החירום" in r.json()["detail"]

    r = api.client.post(url, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["sent"] == 1
    # לחיצה כפולה — ההודעה כבר יצאה.
    r = api.client.post(url, headers=admin)
    assert r.status_code == 409, r.text
    assert g["id"] not in _alerts(admin)

    db = _session()
    try:
        rows = db.scalar(select(func.count()).select_from(models.Message).where(
            models.Message.guest_id == g["id"], models.Message.kind == "invitation"))
        logged = db.scalar(select(func.count()).select_from(models.AdminAuditLog).where(
            models.AdminAuditLog.action == "message.resend"))
    finally:
        db.close()
    assert rows == 2 and logged >= 1


def test_never_resend_pending() -> None:
    api, _ = bootstrap()
    _event_with_messages(api)
    admin = _admin("admin")
    g = api.add_guest("עומר גל", "0506666666")
    _msg(api.event_id, g["id"], code=131026)
    _msg(api.event_id, g["id"], status="pending")       # ניסיון שלא ידוע איך הסתיים
    r = api.client.post(f"/admin/rsvp/delivery-alerts/{g['id']}/resend", headers=admin)
    assert r.status_code == 409, r.text
    assert g["id"] not in _alerts(admin)


# ---- מספרים שצריך לתקן → התראה לבעלי האירוע ----

def _raw_guest(event_id: int, name: str, phone: str) -> int:
    from app import models

    db = _session()
    try:
        ev = db.get(models.Event, event_id)
        ev.event_date = ev.event_date or "2027-03-01"
        g = models.Guest(event_id=event_id, full_name=name, phone=phone, side="shared")
        db.add(g)
        db.commit()
        return g.id
    finally:
        db.close()


def test_admin_alerts_couple_about_phone_numbers() -> None:
    api, _ = bootstrap()
    other, _ = bootstrap()
    support = _admin("support")
    missing = _raw_guest(api.event_id, "בלי מספר", "")
    invalid = _raw_guest(api.event_id, "מספר קצר", "123")
    unreachable = _raw_guest(api.event_id, "לא מגיע", "0507777777")
    _msg(api.event_id, unreachable, code=131026)
    _raw_guest(api.event_id, "תקין", "0508888888")

    r = api.client.get("/admin/rsvp/phone-alerts", headers=support)
    assert r.status_code == 200, r.text
    ev = next(e for e in r.json()["events"] if e["event_id"] == api.event_id)
    problems = {g["guest_id"]: g["problem"] for g in ev["guests"]}
    assert problems == {missing: "missing", invalid: "invalid", unreachable: "whatsapp"}
    assert all(g["alerted_at"] is None for g in ev["guests"])

    # לפני ההתראה — בעלי האירוע לא רואים כלום.
    assert api.client.get("/guests/data-alerts", headers=api.headers).json()["total"] == 0

    r = api.client.post("/admin/rsvp/phone-alerts", headers=support,
                        json={"guest_ids": [missing, invalid, unreachable]})
    assert r.status_code == 200 and r.json()["alerted"] == 3

    data = api.client.get("/guests/data-alerts", headers=api.headers).json()
    reasons = {a["guest_id"]: a["reason"] for a in data["phone_fix"]}
    assert reasons == {missing: "missing", invalid: "invalid", unreachable: "whatsapp"}
    assert other.client.get("/guests/data-alerts", headers=other.headers).json()["total"] == 0

    # בעלי האירוע מתקנים מספר — ההתראה עליו נסגרת מעצמה.
    r = api.client.patch(f"/guests/{invalid}", headers=api.headers, json={"phone": "0509999999"})
    assert r.status_code == 200, r.text
    data = api.client.get("/guests/data-alerts", headers=api.headers).json()
    assert invalid not in {a["guest_id"] for a in data["phone_fix"]}


def test_phone_alert_requires_permission() -> None:
    api, _ = bootstrap()
    g = _raw_guest(api.event_id, "בלי מספר", "")
    r = api.client.post("/admin/rsvp/phone-alerts", headers=api.headers, json={"guest_ids": [g]})
    assert r.status_code in (401, 403), r.text


# ---- העברה לבעלי האירוע: שליחה מה-WhatsApp האישי ----

def test_hand_off_to_couple_personal_whatsapp() -> None:
    from urllib.parse import unquote

    api, _ = bootstrap()
    other, _ = bootstrap()
    _event_with_messages(api)
    support, admin = _admin("support"), _admin("admin")
    g = api.add_guest("רוני לוי", "0501212121")
    for _ in range(3):                                   # מקור + שני ניסיונות אוטומטיים
        _msg(api.event_id, g["id"], code=131049)
    alert = _alerts(support)[g["id"]]
    assert alert["resend_at"] is None and alert["handed_off_at"] is None and alert["can_hand_off"]

    # לפני ההעברה — בעלי האירוע לא רואים כלום.
    assert api.client.get("/guests/data-alerts", headers=api.headers).json()["send_personally"] == []

    r = api.client.post(f"/admin/rsvp/delivery-alerts/{g['id']}/handoff", headers=support)
    assert r.status_code == 200, r.text
    assert _alerts(support)[g["id"]]["handed_off_at"] is not None

    data = api.client.get("/guests/data-alerts", headers=api.headers).json()
    [item] = data["send_personally"]
    assert item["guest_id"] == g["id"] and item["opened_at"] is None
    link = unquote(item["whatsapp_link"])
    assert link.startswith("https://wa.me/972501212121?text=") and "היי רוני," in link and "/confirm/" in link
    assert other.client.get("/guests/data-alerts", headers=other.headers).json()["send_personally"] == []
    assert other.client.post(
        f"/guests/{g['id']}/whatsapp-handoff/opened", headers=other.headers).status_code == 404

    # בעלי האירוע פתחו WhatsApp — הצוות כבר לא שולח שוב (שלא יקבל פעמיים).
    r = api.client.post(f"/guests/{g['id']}/whatsapp-handoff/opened", headers=api.headers)
    assert r.status_code == 200 and r.json()["send_personally"][0]["opened_at"] is not None
    assert _alerts(support)[g["id"]]["couple_opened_at"] is not None
    r = api.client.post(f"/admin/rsvp/delivery-alerts/{g['id']}/resend", headers=admin)
    assert r.status_code == 409 and "בעצמם" in r.json()["detail"], r.text


def test_hand_off_disappears_when_message_arrives() -> None:
    api, _ = bootstrap()
    support = _admin("support")
    g = api.add_guest("טל אבן", "0503434343")
    _msg(api.event_id, g["id"], code=131026)
    assert api.client.post(f"/admin/rsvp/delivery-alerts/{g['id']}/handoff", headers=support).status_code == 200
    _msg(api.event_id, g["id"], status="delivered")       # הודעה מאוחרת יותר כן הגיעה
    assert api.client.get("/guests/data-alerts", headers=api.headers).json()["send_personally"] == []
    # ואין מה להעביר שוב.
    r = api.client.post(f"/admin/rsvp/delivery-alerts/{g['id']}/handoff", headers=support)
    assert r.status_code == 409, r.text
