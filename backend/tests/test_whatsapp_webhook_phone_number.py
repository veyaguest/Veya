"""(1) ה-webhook מקבל רק אירועים של המספר שלנו — ``WHATSAPP_WEBHOOK_PHONE_NUMBER_ID``.
(2) זמן המסירה עקבי גם כש"נקראה" מגיעה לפני "נמסרה" (2026-10-13).

מכסה:
A. התאמה — סטטוס מוחל, הודעה נכנסת נקלטת (כשהמתג שלה דלוק).
B. אי-התאמה / מזהה חסר באירוע / משתנה סביבה חסר או ריק — שום נתון לא משתנה,
   גם כשהמתגים של הודעות נכנסות ו-RSVP דלוקים; התשובה 200.
C. כמה מזהים מוגדרים; payload עם change אחד תואם ואחד לא.
D. הלוג: הסיבה והכמות בלבד — בלי ערכי המזהים.
E. סדר הסטטוסים: "נקראה" לפני "נמסרה", "נמסרה" מאוחרת, "נשלחה"/"נכשלה" אחרי
   "נקראה", הסדר הרגיל, והשלמת pending שמתחילה ב"נקראה".

הרצה: ``venv/bin/python tests/test_whatsapp_webhook_phone_number.py`` (עצמאי, או pytest).
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import os
import secrets
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402
from tests.test_whatsapp_safety import (  # noqa: E402
    _SECRET, _db, _engine, _event, _guest, _guest_row, _open_rsvp, _payload, _phone, _reply,
)

OURS = "100000000000011"
OTHER = "100000000000099"
URL = "/messaging/webhook"
T1, T2, T3 = 1790000000, 1790000300, 1790000600


def _post(api, payload: dict, configured, *, inbound: bool = True):
    """POST חתום. ``configured`` — ערך ``WHATSAPP_WEBHOOK_PHONE_NUMBER_ID``
    (``None`` = לא מוגדר בכלל). המתגים של הודעות נכנסות ו-RSVP דלוקים, כדי
    להוכיח שהדחייה חוסמת גם אותם."""
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = "sha256=" + hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()
    keys = {"WHATSAPP_APP_SECRET": _SECRET, "WHATSAPP_WEBHOOK_PHONE_NUMBER_ID": configured,
            "WHATSAPP_WEBHOOK_INBOUND": "1" if inbound else "", "WHATSAPP_INBOUND_RSVP": "1"}
    prev = {k: os.environ.get(k) for k in keys}
    for k, v in keys.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        return api.client.post(URL, content=body, headers={
            "Content-Type": "application/json", "X-Hub-Signature-256": sig})
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _setup():
    from app import models

    api, _ = bootstrap()
    _open_rsvp(api)
    phone = _phone()
    g = api.add_guest("מוזמן מספר", phone, party_size=2)
    wamid = "wamid.HBgM" + secrets.token_hex(12)
    db = _db()
    try:
        db.add(models.Message(event_id=api.event_id, guest_id=g["id"], direction="outbound",
                              kind="invitation", body="x", status="sent", provider="meta",
                              provider_message_id=wamid))
        db.commit()
    finally:
        db.close()
    return api, g, phone, wamid


def _event_payload(phone, wamid, pnid="__default__"):
    kw = {} if pnid == "__default__" else {"phone_number_id": pnid}
    return _payload(
        _reply("972" + phone[1:], "wamid.HBgM" + secrets.token_hex(12), coming=True),
        {"from": "972" + phone[1:], "id": "wamid.HBgM" + secrets.token_hex(12), "type": "text",
         "text": {"body": "שלום"}},
        statuses=[{"id": wamid, "status": "read", "timestamp": str(T1)}],
        **kw,
    )


def _state(api, g, wamid):
    from app import models

    db = _db()
    try:
        msg = db.scalars(select(models.Message).where(models.Message.provider_message_id == wamid)).one()
        inbound = db.scalar(select(func.count()).select_from(models.Message).where(
            models.Message.event_id == api.event_id, models.Message.direction == "inbound"))
    finally:
        db.close()
    guest = _guest_row(g["id"])
    return msg.status, inbound, guest.rsvp_status, guest.confirmed_count


# ============================================================================
# A–D. מזהה המספר
# ============================================================================

def test_matching_phone_number_id_is_processed() -> None:
    api, g, phone, wamid = _setup()
    assert _post(api, _event_payload(phone, wamid, OURS), OURS).status_code == 200
    status, inbound, rsvp, count = _state(api, g, wamid)
    assert status == "read" and inbound == 2 and rsvp == "confirmed" and count == 2
    print("✓ A1: מזהה תואם — סטטוס מוחל, הודעות נכנסות נקלטות (כשהמתגים דלוקים)")


def test_rejected_events_change_nothing() -> None:
    cases = {
        "מזהה אחר": (OTHER, OURS),
        "מזהה חסר באירוע": (None, OURS),
        "מזהה ריק באירוע": ("", OURS),
        "מזהה שאינו מחרוזת": (12345, OURS),
        "משתנה סביבה לא מוגדר": (OURS, None),
        "משתנה סביבה ריק": (OURS, ""),
        "משתנה סביבה רווחים ופסיקים": (OURS, " , , "),
    }
    for label, (in_event, configured) in cases.items():
        api, g, phone, wamid = _setup()
        before = _state(api, g, wamid)
        r = _post(api, _event_payload(phone, wamid, in_event), configured)
        assert r.status_code == 200, (label, r.status_code)
        assert _state(api, g, wamid) == before == ("sent", 0, "pending", None), label
    print(f"✓ B1: {len(cases)} מקרי דחייה — שום נתון לא משתנה (גם עם הודעות נכנסות ו-RSVP דלוקים)")


def test_multiple_ids_and_mixed_payload() -> None:
    from app import models

    api, g, phone, wamid = _setup()
    assert _post(api, _event_payload(phone, wamid, OURS), f" {OTHER} ,{OURS}").status_code == 200
    assert _state(api, g, wamid)[0] == "read"

    api, g, phone, wamid = _setup()
    other_wamid = "wamid.HBgM" + secrets.token_hex(12)
    db = _db()
    try:
        db.add(models.Message(event_id=api.event_id, guest_id=g["id"], direction="outbound",
                              kind="reminder_1", body="x", status="sent", provider="meta",
                              provider_message_id=other_wamid))
        db.commit()
    finally:
        db.close()
    ours = _payload(statuses=[{"id": wamid, "status": "delivered", "timestamp": str(T1)}],
                    phone_number_id=OURS)
    theirs = _payload(statuses=[{"id": other_wamid, "status": "delivered", "timestamp": str(T1)}],
                      phone_number_id=OTHER)
    mixed = {"entry": ours["entry"] + theirs["entry"]}
    assert _post(api, mixed, OURS).status_code == 200
    db = _db()
    try:
        by_id = {m.provider_message_id: m.status for m in db.scalars(select(models.Message).where(
            models.Message.provider_message_id.in_((wamid, other_wamid))))}
    finally:
        db.close()
    assert by_id == {wamid: "delivered", other_wamid: "sent"}
    print("✓ C1: כמה מזהים מוגדרים; payload מעורב — רק ה-change של המספר שלנו מעובד")


def test_rejection_log_has_no_ids() -> None:
    api, g, phone, wamid = _setup()
    buf = io.StringIO()
    with redirect_stdout(buf):
        _post(api, _event_payload(phone, wamid, OTHER), OURS)
        _post(api, _event_payload(phone, wamid, None), OURS)
        _post(api, _event_payload(phone, wamid, OURS), None)
    log = buf.getvalue()
    for reason in ("phone_number_id_mismatch", "missing_phone_number_id", "not_configured"):
        assert f"items=3 reason={reason}" in log, reason
    for leak in (OURS, OTHER, phone, phone[1:], wamid, "HBgM"):
        assert leak not in log, "דליפה בלוג"
    print("✓ D1: בלוג — סיבת הדחייה וכמות הפריטים בלבד, בלי ערכי מזהים")


# ============================================================================
# E. סדר הסטטוסים וזמן המסירה
# ============================================================================

def _msg(db, status="sent", provider_message_id=None):
    from app import models

    ev = _event(db)
    g = _guest(db, ev.id, _phone())
    m = models.Message(event_id=ev.id, guest_id=g.id, direction="outbound", kind="invitation",
                       body="x", status=status, provider="meta",
                       provider_message_id=provider_message_id or "wamid.o-" + secrets.token_hex(6))
    db.add(m)
    db.commit()
    return m


def _at(t: int) -> datetime:
    return datetime.utcfromtimestamp(t)


def test_read_before_delivered_fills_delivered_at() -> None:
    from app import message_status as ms

    db = Session(_engine())
    m = _msg(db)
    pmid = m.provider_message_id

    def apply(status, t):
        ms.apply_status_update(db, provider_message_id=pmid, status=status, timestamp=_at(t))
        db.commit()

    apply(ms.READ, T2)
    assert (m.status, m.delivered_at, m.read_at) == ("read", _at(T2), _at(T2)), "נקרא = נמסר"
    apply(ms.DELIVERED, T1)  # מגיעה באיחור, עם הזמן האמיתי (מוקדם יותר)
    assert (m.status, m.delivered_at, m.read_at) == ("read", _at(T1), _at(T2)), "הזמן האמיתי, בלי נסיגה"
    apply(ms.DELIVERED, T3)  # זמן מאוחר יותר — לא דורס
    assert m.delivered_at == _at(T1)
    apply(ms.SENT, T3)
    assert (m.status, m.delivered_at, m.read_at) == ("read", _at(T1), _at(T2))
    ms.apply_status_update(db, provider_message_id=pmid, status=ms.FAILED, timestamp=_at(T3), reason="late")
    db.commit()
    assert m.status == "read" and m.delivered_at == _at(T1)
    print("✓ E1: 'נקראה' לפני 'נמסרה' — זמן מסירה מתמלא, מתעדכן לזמן האמיתי, בלי נסיגת סטטוס")


def test_normal_order_unchanged() -> None:
    from app import message_status as ms

    db = Session(_engine())
    m = _msg(db)
    for status, t in ((ms.SENT, T1), (ms.DELIVERED, T2), (ms.READ, T3), (ms.DELIVERED, T3)):
        ms.apply_status_update(db, provider_message_id=m.provider_message_id, status=status, timestamp=_at(t))
        db.commit()
    assert (m.status, m.delivered_at, m.read_at) == ("read", _at(T2), _at(T3))
    print("✓ E2: הסדר הרגיל — 'נמסרה' ב-T2, 'נקראה' ב-T3, כמו קודם")


def test_reconciled_pending_starting_with_read() -> None:
    api, _ = bootstrap()
    from app import models

    phone = _phone()
    g = api.add_guest("מוזמן תקוע", phone)
    db = _db()
    try:
        m = models.Message(event_id=api.event_id, guest_id=g["id"], direction="outbound",
                           kind="reminder_1", body="x", status="pending", provider="meta")
        db.add(m)
        db.commit()
        rid = m.id
    finally:
        db.close()
    st = {"id": "wamid.HBgM" + secrets.token_hex(12), "status": "read", "timestamp": str(T2),
          "recipient_id": "972" + phone[1:],
          "biz_opaque_callback_data": f"veya:m{rid}:e{api.event_id}:g{g['id']}"}
    assert _post(api, _payload(statuses=[st], phone_number_id=OURS), OURS, inbound=False).status_code == 200
    db = _db()
    try:
        row = db.get(models.Message, rid)
        assert (row.status, row.delivered_at, row.read_at) == ("read", _at(T2), _at(T2))
    finally:
        db.close()
    print("✓ E3: השלמת pending שמתחילה ב'נקראה' — גם זמן המסירה מתמלא")


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
        print("\n=== מזהה המספר וסדר הסטטוסים — עבר ===")
    finally:
        shutdown()
