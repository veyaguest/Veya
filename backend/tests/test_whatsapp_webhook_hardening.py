"""הקשחת ה-webhook לפני בדיקה חיצונית (2026-10-13).

מכסה:
A. אימות GET (``hub.verify_token``) — הצלחה, טוקן שגוי/חסר, mode שגוי, בלי הגדרה.
B. חתימה פגומה (תווים שאינם ASCII, אורך שגוי, לא hex) → 403 ולא 500; אותיות
   גדולות ב-hex תקין — מתקבל.
C. גוף גדול מ-3MB → 413, לפני בדיקת החתימה (גם בלי Content-Length).
D. עדכוני סטטוס לעולם לא משנים אישור הגעה — בכל הסטטוסים, כולל השלמת pending.
E. עדכון RSVP מהודעה נכנסת כבוי כברירת מחדל — לחיצת כפתור נשמרת כ"דורש טיפול".
F. עדכון סטטוס כפול לא משנה את הזמן המקורי.
G. הלוג לא מכיל טוקן, סוד, טלפון מלא, תוכן הודעה או wamid מלא.

הרצה: ``venv/bin/python tests/test_whatsapp_webhook_hardening.py`` (עצמאי, או pytest).
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import secrets
import sys
from contextlib import contextmanager, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402
from tests.test_whatsapp_safety import (  # noqa: E402
    _SECRET, _db, _guest_row, _inbound_rows, _open_rsvp, _payload, _phone, _post, _reply,
)

URL = "/messaging/webhook"


@contextmanager
def _env(**values):
    prev = {k: os.environ.get(k) for k in values}
    for k, v in values.items():
        os.environ[k] = v
    try:
        yield
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _raw_post(api, body: bytes, signature):
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    with _env(WHATSAPP_APP_SECRET=_SECRET):
        return api.client.post(URL, content=body, headers=headers)


def _sig(body: bytes) -> str:
    return "sha256=" + hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()


# ============================================================================
# A. אימות GET
# ============================================================================

def test_get_verification() -> None:
    api, _ = bootstrap()
    token = "vt-" + secrets.token_hex(8)

    def get(params):
        return api.client.get(URL, params=params)

    with _env(WHATSAPP_VERIFY_TOKEN=token):
        r = get({"hub.mode": "subscribe", "hub.verify_token": token, "hub.challenge": "1158201444"})
        assert r.status_code == 200 and r.text == "1158201444"
        assert r.headers["content-type"].startswith("text/plain")
        assert token not in r.text
        for bad in (
            {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"},
            {"hub.mode": "subscribe", "hub.challenge": "1"},
            {"hub.mode": "unsubscribe", "hub.verify_token": token, "hub.challenge": "1"},
            {"hub.mode": "subscribe", "hub.verify_token": token + "x", "hub.challenge": "1"},
            {"hub.mode": "subscribe", "hub.verify_token": "טוקן", "hub.challenge": "1"},
            {},
        ):
            r = get(bad)
            assert r.status_code == 403, bad
            assert token not in r.text
    with _env(WHATSAPP_VERIFY_TOKEN=""):
        r = get({"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"})
        assert r.status_code == 403
    print("✓ A1: אימות GET — רק עם הטוקן המדויק ו-mode=subscribe; בלי הגדרה — 403")


# ============================================================================
# B. חתימה פגומה
# ============================================================================

def test_malformed_signature_is_403_not_500() -> None:
    api, _ = bootstrap()
    body = b'{"entry":[]}'
    good = _sig(body)
    for label, sig in (
        ("תווים שאינם ASCII", b"sha256=\xc3\xa9\xc3\xa9"),
        ("hex קצר", "sha256=abcd"),
        ("לא hex", "sha256=" + "z" * 64),
        ("hex ארוך", good + "00"),
        ("בלי קידומת", good[len("sha256="):]),
        ("sha1", "sha1=" + "a" * 40),
        ("ריק", ""),
    ):
        r = _raw_post(api, body, sig)
        assert r.status_code == 403, f"{label}: {r.status_code}"
    assert _raw_post(api, body, "sha256=" + good[len("sha256="):].upper()).status_code == 200
    assert _raw_post(api, body, good).status_code == 200
    print("✓ B1: חתימה פגומה (7 צורות) → 403, לא 500; hex באותיות גדולות — מתקבל")


# ============================================================================
# C. תקרת גודל
# ============================================================================

def test_oversized_body_rejected_before_signature() -> None:
    from app.routers import messaging as router

    api, _ = bootstrap()
    big = b'{"entry":[],"pad":"' + b"x" * (router.MAX_WEBHOOK_BODY_BYTES + 10) + b'"}'
    r = _raw_post(api, big, _sig(big))  # גם עם חתימה תקינה
    assert r.status_code == 413
    r = _raw_post(api, big, None)
    assert r.status_code == 413, "התקרה נבדקת לפני החתימה"

    def chunks():
        for _ in range(router.MAX_WEBHOOK_BODY_BYTES // 65536 + 2):
            yield b"x" * 65536

    with _env(WHATSAPP_APP_SECRET=_SECRET):
        r = api.client.post(URL, content=chunks(), headers={"X-Hub-Signature-256": "sha256=" + "0" * 64})
    assert r.status_code == 413, "גם בלי Content-Length"
    ok = b'{"entry":[]}'
    assert _raw_post(api, ok, _sig(ok)).status_code == 200
    print("✓ C1: גוף מעל 3MB → 413 לפני בדיקת החתימה, גם בלי Content-Length")


# ============================================================================
# D. סטטוסים לא נוגעים באישור הגעה
# ============================================================================

def test_status_updates_never_change_rsvp() -> None:
    from app import models

    api, _ = bootstrap()
    phone = _phone()
    g = api.add_guest("מוזמן מאושר", phone, party_size=3)
    wamid = "wamid.d-" + secrets.token_hex(6)
    db = _db()
    try:
        guest = db.get(models.Guest, g["id"])
        guest.rsvp_status, guest.confirmed_count, guest.guest_note = "confirmed", 2, "הערה"
        out = models.Message(event_id=api.event_id, guest_id=g["id"], direction="outbound",
                             kind="invitation", body="x", status="sent", provider="meta",
                             provider_message_id=wamid)
        pend = models.Message(event_id=api.event_id, guest_id=g["id"], direction="outbound",
                              kind="reminder_1", body="x", status="pending", provider="meta")
        db.add_all([out, pend])
        db.commit()
        pend_id = pend.id
    finally:
        db.close()
    before = _guest_row(g["id"])
    statuses = [
        {"id": wamid, "status": s, "timestamp": "1790000000", "recipient_id": "972" + phone[1:]}
        for s in ("sent", "delivered", "read", "played", "deleted", "warning")
    ]
    statuses.append({"id": wamid, "status": "failed", "errors": [{"code": 131050, "title": "x"}]})
    statuses.append({"id": "wamid.p-" + secrets.token_hex(6), "status": "delivered",
                     "recipient_id": "972" + phone[1:],
                     "biz_opaque_callback_data": f"veya:m{pend_id}:e{api.event_id}:g{g['id']}"})
    assert _post(api, _payload(statuses=statuses), inbound_rsvp=True).status_code == 200
    after = _guest_row(g["id"])
    assert (after.rsvp_status, after.confirmed_count, after.guest_note) == \
        (before.rsvp_status, before.confirmed_count, before.guest_note) == ("confirmed", 2, "הערה")
    db = _db()
    try:
        assert db.get(models.Message, pend_id).status == "delivered", "ההשלמה עבדה — על ההודעה בלבד"
    finally:
        db.close()
    print("✓ D1: עדכוני סטטוס (כולל נכשלה/חסום והשלמת pending) — אישור ההגעה לא משתנה")


# ============================================================================
# E. RSVP מהודעה נכנסת — כבוי כברירת מחדל
# ============================================================================

def test_inbound_rsvp_disabled_by_default() -> None:
    from app import models

    api, _ = bootstrap()
    _open_rsvp(api)
    phone = _phone()
    g = api.add_guest("מוזמן לוחץ", phone)
    assert os.environ.get("WHATSAPP_INBOUND_RSVP", "") != "1"
    for coming in (True, False):
        msg = _reply("972" + phone[1:], "wamid.e-" + secrets.token_hex(6), coming=coming)
        assert _post(api, _payload(msg), inbound_rsvp=False).status_code == 200
    assert _guest_row(g["id"]).rsvp_status == "pending", "בלי הדלקה מפורשת — RSVP לא משתנה"
    rows = _inbound_rows(api.event_id)
    assert [r.status for r in rows] == ["needs_attention", "needs_attention"]
    assert all("הקישור האישי" in r.body for r in rows)
    db = _db()
    try:
        assert db.scalars(select(models.AuditLog).where(
            models.AuditLog.event_id == api.event_id,
            models.AuditLog.action == "confirm_submit")).first() is None
    finally:
        db.close()
    print("✓ E1: לחיצת 'מגיע/ה' / 'לא מגיע/ה' — נשמרת כ'דורש טיפול', RSVP לא משתנה")


# ============================================================================
# F. עדכון כפול לא משנה את הזמן
# ============================================================================

def test_duplicate_status_keeps_first_timestamp() -> None:
    from app import models

    api, _ = bootstrap()
    g = api.add_guest("מוזמן זמן", _phone())
    wamid = "wamid.f-" + secrets.token_hex(6)
    db = _db()
    try:
        db.add(models.Message(event_id=api.event_id, guest_id=g["id"], direction="outbound",
                              kind="invitation", body="x", status="sent", provider="meta",
                              provider_message_id=wamid))
        db.commit()
    finally:
        db.close()
    first = {"id": wamid, "status": "delivered", "timestamp": "1790000000"}
    later = {"id": wamid, "status": "delivered", "timestamp": "1790009999"}
    for st in (first, later, first):
        assert _post(api, _payload(statuses=[st])).status_code == 200
    db = _db()
    try:
        m = db.scalars(select(models.Message).where(models.Message.provider_message_id == wamid)).one()
        from datetime import datetime

        assert m.delivered_at == datetime.utcfromtimestamp(1790000000)
    finally:
        db.close()
    print("✓ F1: 'נמסרה' שמגיעה שוב — הזמן המקורי נשמר")


# ============================================================================
# G. בלי מידע רגיש בלוג
# ============================================================================

def test_webhook_logs_have_no_sensitive_data() -> None:
    from app import models

    api, _ = bootstrap()
    _open_rsvp(api)
    phone = _phone()
    g = api.add_guest("מוזמן לוג", phone)
    intl = "972" + phone[1:]
    wamid_out = "wamid.HBgM" + secrets.token_hex(16)
    db = _db()
    try:
        db.add(models.Message(event_id=api.event_id, guest_id=g["id"], direction="outbound",
                              kind="invitation", body="x", status="sent", provider="meta",
                              provider_message_id=wamid_out))
        db.commit()
    finally:
        db.close()
    text = "סוד אישי " + secrets.token_hex(6)
    wamid_in = "wamid.HBgM" + secrets.token_hex(16)
    payload = _payload(
        {"from": intl, "id": wamid_in, "type": "text", "text": {"body": text}},
        _reply(intl, "wamid.HBgM" + secrets.token_hex(16), context=wamid_out),
        statuses=[
            {"id": wamid_out, "status": "delivered", "recipient_id": intl, "timestamp": "1790000000"},
            {"id": wamid_out, "status": "failed", "recipient_id": intl,
             "errors": [{"code": 131026, "title": f"undeliverable to {intl}"}]},
        ],
    )
    buf = io.StringIO()
    with redirect_stdout(buf), _env(WHATSAPP_VERIFY_TOKEN="vt-log-check"):
        assert _post(api, payload, inbound_rsvp=False).status_code == 200
        api.client.get(URL, params={"hub.mode": "subscribe", "hub.verify_token": "vt-log-check",
                                    "hub.challenge": "7"})
    log = buf.getvalue()
    assert "[veya:whatsapp]" in log, "הלוג אמור לתעד שקרה משהו"
    for leak, label in ((_SECRET, "סוד"), ("vt-log-check", "verify token"), (text, "תוכן הודעה"),
                        (phone, "טלפון"), (intl, "טלפון בינלאומי"), (phone[1:], "ספרות הטלפון"),
                        (wamid_in, "wamid נכנס"), (wamid_out, "wamid יוצא"), ("HBgM", "תחילת wamid")):
        assert leak not in log, f"דליפה בלוג: {label}"
    print("✓ G1: הלוג של ה-webhook — בלי סוד, טוקן, טלפון, תוכן הודעה או wamid")


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
        print()
        print("=== כל בדיקות הקשחת ה-webhook עברו ===")
    finally:
        shutdown()
