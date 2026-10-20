"""תיבת WhatsApp לשירות לקוחות — קליטה, ניתוב ותשובה אוטומטית (2026-10-19).

מה נבדק:
  1. בעל חשבון ב-VEYA שכותב → תור השירות (גם אם הוא מוזמן באירוע של עצמו).
  2. מספר לא מוכר → תור השירות, עם שם הפרופיל מ-WhatsApp.
  3. מוזמן מזוהה → בעלי האירוע (שורה על האירוע), בלי שיחה בתור ובלי תשובה.
  4. מוזמן בכמה אירועים שונים → תור השירות ("מוזמן שלא זוהה בוודאות").
  5. webhook שחוזר → הודעה אחת ותשובה אוטומטית אחת.
  6. תשובה אוטומטית פעם ב-24 שעות; נוסח לפי שעות הפעילות; מתג כיבוי.
  7. בטיחות שליחה: mock / עצירת חירום / meta_test לא פונים ל-Meta; meta כן.
  8. עדכון מסירה מ-Meta מגיע לתשובה מהתיבה.
  9. לוג בלי טלפון, שם או תוכן. מתג ההודעות הנכנסות כבוי → שום דבר לא נשמר.

הרצה: ``venv/bin/python -m pytest tests/test_whatsapp_inbox.py``
"""
from __future__ import annotations

import io
import os
import secrets
import sys
from contextlib import contextmanager, redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from tests.e2e_seating import bootstrap  # noqa: E402
from tests.test_whatsapp_safety import _db, _payload, _phone, _post  # noqa: E402


def _wamid() -> str:
    return "wamid.HBgM" + secrets.token_hex(12)


def _text(phone: str, body: str, wamid: str | None = None, name: str = "") -> tuple[dict, dict]:
    intl = "972" + phone[1:]
    msg = {"from": intl, "id": wamid or _wamid(), "type": "text", "text": {"body": body}}
    contact = {"wa_id": intl, "profile": {"name": name}} if name else None
    return msg, contact


def _send(api, *messages, contacts=()) -> None:
    payload = _payload(*messages)
    if contacts:
        payload["entry"][0]["changes"][0]["value"]["contacts"] = [c for c in contacts if c]
    r = _post(api, payload, inbound_rsvp=False, inbound=True)
    assert r.status_code == 200, r.text


def _thread(phone: str):
    from app import models

    db = _db()
    try:
        t = db.scalar(select(models.WhatsAppThread).where(models.WhatsAppThread.phone == phone))
        if t is None:
            return None, []
        rows = db.scalars(select(models.WhatsAppThreadMessage)
                          .where(models.WhatsAppThreadMessage.thread_id == t.id)
                          .order_by(models.WhatsAppThreadMessage.id)).all()
        db.expunge_all()
        return t, rows
    finally:
        db.close()


def _set_user_phone(api, phone: str) -> int:
    from app import auth as auth_module, models

    uid = int(auth_module._decode_token(api.token)["sub"])
    db = _db()
    try:
        db.get(models.User, uid).phone = phone
        db.commit()
    finally:
        db.close()
    return uid


def _event_inbound(event_id: int) -> list:
    from app import models

    db = _db()
    try:
        rows = db.scalars(select(models.Message).where(
            models.Message.event_id == event_id, models.Message.direction == "inbound")).all()
        db.expunge_all()
        return list(rows)
    finally:
        db.close()


@contextmanager
def _env(**values):
    prev = {k: os.environ.get(k) for k in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class _MetaSpy:
    """``whatsapp_meta._transport`` שסופר בקשות ומחזיר הצלחה — בלי רשת אמיתית."""

    def __init__(self) -> None:
        self.calls: list = []

    def __enter__(self):
        import httpx

        from app import whatsapp_meta

        def handler(request):
            self.calls.append(request)
            return httpx.Response(200, json={"messages": [{"id": "wamid.SPY" + secrets.token_hex(6)}]})

        self._saved = whatsapp_meta._transport
        whatsapp_meta._transport = httpx.MockTransport(handler)
        return self

    def __exit__(self, *exc):
        from app import whatsapp_meta

        whatsapp_meta._transport = self._saved


# ── 1–2. תור השירות ───────────────────────────────────────────────────────

def test_account_holder_goes_to_support_even_if_also_a_guest() -> None:
    api, _ = bootstrap()
    phone = _phone()
    uid = _set_user_phone(api, phone)
    api.add_guest("אני עצמי", phone)  # בעלי אירוע שהוסיפו את עצמם כמוזמנים
    with _MetaSpy() as spy:
        msg, contact = _text(phone, "שאלה על החשבון", name="דנה")
        _send(api, msg, contacts=[contact])
        assert spy.calls == [], "מצב mock — שום דבר לא יוצא ל-Meta"
    t, rows = _thread(phone)
    assert t is not None and t.sender_kind == "account" and t.user_id == uid
    assert t.status == "open" and t.profile_name == "דנה" and t.last_inbound_at is not None
    assert [(r.direction, r.kind, r.status) for r in rows] == [
        ("inbound", "text", "received"), ("outbound", "auto_reply", "mock")]
    assert rows[0].body == "שאלה על החשבון"
    assert "א׳–ה׳, 9:00–18:00" in rows[1].body
    assert _event_inbound(api.event_id) == [], "לא נרשם כהודעה של מוזמן לאירוע"


def test_unknown_number_goes_to_support() -> None:
    api, _ = bootstrap()
    phone = _phone()
    msg, contact = _text(phone, "היי, כמה זה עולה?", name="Noa")
    _send(api, msg, contacts=[contact])
    t, rows = _thread(phone)
    assert t.sender_kind == "unknown" and t.user_id is None and t.profile_name == "Noa"
    assert len(rows) == 2


def test_foreign_number_is_stored_with_plus() -> None:
    api, _ = bootstrap()
    msg = {"from": "4479" + f"{secrets.randbelow(10 ** 8):08d}", "id": _wamid(),
           "type": "text", "text": {"body": "hello"}}
    _send(api, msg)
    t, rows = _thread("+" + msg["from"])
    assert t is not None and rows[0].body == "hello"
    # תשובה אוטומטית למספר לא ישראלי — לא נשלחת, נרשם למה (מצב mock קודם לכך).
    assert rows[1].status == "mock"


# ── 3–4. מוזמנים ──────────────────────────────────────────────────────────

def test_known_guest_goes_to_hosts_not_support() -> None:
    from app import models

    api, _ = bootstrap()
    phone = _phone()
    api.add_guest("מוזמן ששואל", phone)
    msg, _ = _text(phone, "יש חניה באולם?")
    _send(api, msg)
    assert _thread(phone) == (None, [])
    rows = _event_inbound(api.event_id)
    assert len(rows) == 1 and rows[0].status == "needs_attention" and rows[0].body == "יש חניה באולם?"
    db = _db()
    try:
        emails = db.scalar(select(func.count()).select_from(models.AuditLog).where(
            models.AuditLog.event_id == api.event_id, models.AuditLog.action == "guest_message_email"))
    finally:
        db.close()
    assert emails == 1, "נשלח (או נוסה) מייל לבעלי האירוע"


def test_guest_in_two_events_goes_to_support() -> None:
    a, _ = bootstrap()
    b, _ = bootstrap()
    phone = _phone()
    a.add_guest("מוזמן א", phone)
    b.add_guest("מוזמן ב", phone)
    msg, _ = _text(phone, "מתי האירוע?")
    _send(a, msg)
    t, rows = _thread(phone)
    assert t.sender_kind == "guest" and len(rows) == 2
    assert _event_inbound(a.event_id) == [] and _event_inbound(b.event_id) == []


# ── 5–6. כפילות ותשובה אוטומטית ───────────────────────────────────────────

def test_duplicate_webhook_and_auto_reply_once_per_day() -> None:
    from app import models, whatsapp_inbox

    api, _ = bootstrap()
    phone = _phone()
    first, _ = _text(phone, "הודעה ראשונה")
    _send(api, first)
    _send(api, first)  # Meta שולחת שוב
    _send(api, _text(phone, "הודעה שנייה")[0])
    t, rows = _thread(phone)
    assert [r.kind for r in rows] == ["text", "auto_reply", "text"]

    # עברו 25 שעות מהתשובה האוטומטית — שיחה חדשה מקבלת תשובה חדשה.
    db = _db()
    try:
        th = db.get(models.WhatsAppThread, t.id)
        th.auto_reply_at = whatsapp_inbox._now() - timedelta(hours=25)
        th.status = "closed"
        db.commit()
    finally:
        db.close()
    _send(api, _text(phone, "שוב אני")[0])
    t, rows = _thread(phone)
    assert [r.kind for r in rows] == ["text", "auto_reply", "text", "text", "auto_reply"]
    assert t.status == "open", "הודעה חדשה פותחת שיחה סגורה"


def test_auto_reply_switch_off() -> None:
    from app import whatsapp_inbox

    api, _ = bootstrap()
    phone = _phone()
    saved = whatsapp_inbox.auto_reply_enabled
    whatsapp_inbox.auto_reply_enabled = lambda: False
    try:
        _send(api, _text(phone, "בלי תשובה אוטומטית")[0])
    finally:
        whatsapp_inbox.auto_reply_enabled = saved
    _, rows = _thread(phone)
    assert [r.kind for r in rows] == ["text"]


def test_service_hours_and_wording() -> None:
    from app import messaging, whatsapp_inbox

    # שעון ישראל באוקטובר 2026 (אחרי 25.10 — חורף, UTC+2; לפני — קיץ, UTC+3).
    sunday_10 = datetime(2026, 11, 1, 8, 0)    # ראשון 10:00
    thursday_17 = datetime(2026, 11, 5, 15, 59)  # חמישי 17:59
    thursday_18 = datetime(2026, 11, 5, 16, 0)   # חמישי 18:00
    friday_10 = datetime(2026, 11, 6, 8, 0)
    saturday_12 = datetime(2026, 11, 7, 10, 0)
    sunday_0859 = datetime(2026, 11, 1, 6, 59)
    assert whatsapp_inbox.in_service_hours(sunday_10)
    assert whatsapp_inbox.in_service_hours(thursday_17)
    for closed in (thursday_18, friday_10, saturday_12, sunday_0859):
        assert not whatsapp_inbox.in_service_hours(closed), closed
    open_text, closed_text = messaging.support_auto_reply(True), messaging.support_auto_reply(False)
    assert open_text != closed_text
    for text in (open_text, closed_text):
        assert "א׳–ה׳, 9:00–18:00" in text and "VEYA" in text
        for banned in ("מערכת", "פלטפורמה", "אנא", "!"):
            assert banned not in text


# ── 7. בטיחות שליחה ──────────────────────────────────────────────────────

def _pending_reply(phone: str, minutes_ago: int = 5) -> int:
    from app import message_status, models, whatsapp_inbox

    db = _db()
    try:
        now = whatsapp_inbox._now()
        t = models.WhatsAppThread(phone=phone, last_inbound_at=now - timedelta(minutes=minutes_ago),
                                  last_message_at=now)
        db.add(t)
        db.flush()
        row = models.WhatsAppThreadMessage(thread_id=t.id, direction="outbound", kind="reply",
                                           body="תשובה", status=message_status.PENDING)
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _deliver(row_id: int):
    from app import models, whatsapp_inbox

    db = _db()
    try:
        row = db.get(models.WhatsAppThreadMessage, row_id)
        whatsapp_inbox.deliver(db, row)
        db.commit()
        return row.status, row.failure_reason, row.provider_message_id
    finally:
        db.close()


def test_send_safety_by_mode() -> None:
    from app import messaging

    bootstrap()
    phone = _phone()
    meta_env = {"WHATSAPP_ACCESS_TOKEN": "test-token-not-real", "WHATSAPP_PHONE_NUMBER_ID": "123"}

    with _MetaSpy() as spy:
        assert _deliver(_pending_reply(_phone()))[0] == "mock"

        with _env(WHATSAPP_MODE="meta", **meta_env):
            saved = messaging.emergency_stop_active
            messaging.emergency_stop_active = lambda: True
            try:
                status, reason, _ = _deliver(_pending_reply(_phone()))
            finally:
                messaging.emergency_stop_active = saved
            assert status == "blocked" and "עצירת חירום" in reason

        with _env(WHATSAPP_MODE="meta_test", WHATSAPP_TEST_RECIPIENTS="0500000001", **meta_env):
            status, _, _ = _deliver(_pending_reply(_phone()))
            assert status == "blocked"

        with _env(WHATSAPP_MODE="meta", **meta_env):
            status, reason, _ = _deliver(_pending_reply(_phone(), minutes_ago=25 * 60))
            assert status == "failed" and "24 שעות" in reason
        assert spy.calls == [], "אף אחד מהמקרים האלה לא פנה ל-Meta"

        with _env(WHATSAPP_MODE="meta_test", WHATSAPP_TEST_RECIPIENTS=phone, **meta_env):
            status, _, wamid = _deliver(_pending_reply(phone))
        assert status == "sent" and wamid.startswith("wamid.SPY") and len(spy.calls) == 1
        body = spy.calls[0].read().decode()
        assert '"type":"text"' in body.replace(" ", "") and "veya:w" in body


# ── 8. עדכון מסירה ────────────────────────────────────────────────────────

def test_status_webhook_updates_inbox_reply() -> None:
    from app import models

    api, _ = bootstrap()
    row_id = _pending_reply(_phone())
    wamid = _wamid()
    db = _db()
    try:
        row = db.get(models.WhatsAppThreadMessage, row_id)
        row.status, row.provider_message_id = "sent", wamid
        db.commit()
    finally:
        db.close()
    st = {"id": wamid, "status": "delivered", "timestamp": "1790000000", "recipient_id": "972500000000"}
    assert _post(api, _payload(statuses=[st]), inbound_rsvp=False, inbound=True).status_code == 200
    st2 = dict(st, status="sent")  # מגיע באיחור — לא נסוגים
    assert _post(api, _payload(statuses=[st2]), inbound_rsvp=False, inbound=True).status_code == 200
    db = _db()
    try:
        assert db.get(models.WhatsAppThreadMessage, row_id).status == "delivered"
    finally:
        db.close()


# ── 9. לוג ומתג ───────────────────────────────────────────────────────────

def test_log_has_no_personal_data_and_switch_off_stores_nothing() -> None:
    api, _ = bootstrap()
    phone = _phone()
    secret = "סוד " + secrets.token_hex(5)
    msg, contact = _text(phone, secret, name="שם פרטי מאוד")
    buf = io.StringIO()
    with redirect_stdout(buf):
        _send(api, msg, contacts=[contact])
    log = buf.getvalue()
    assert "inbox support_message" in log
    for leak in (secret, phone, phone[1:], "שם פרטי מאוד"):
        assert leak not in log

    other = _phone()
    payload = _payload(_text(other, "לא נשמר")[0])
    assert _post(api, payload, inbound_rsvp=False, inbound=False).status_code == 200
    assert _thread(other) == (None, [])
