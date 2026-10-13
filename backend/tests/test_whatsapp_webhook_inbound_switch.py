"""מתג ``WHATSAPP_WEBHOOK_INBOUND`` (2026-10-13): "עדכוני סטטוס בלבד".

ב-Meta אי אפשר להירשם לעדכוני סטטוס בלי הודעות נכנסות — שניהם מגיעים בשדה
``messages``. לכן, בשלב הראשון של חיבור Meta לייצור, המתג כבוי: הודעה נכנסת
לא נשמרת ולא נוגעת בשום נתון (כדי שהודעת בדיקה למספר לא תיכנס לאירוע אמיתי),
ועדכוני סטטוס ממשיכים לעבוד כרגיל.

מכסה:
1. המתג כבוי כברירת מחדל — במערכת ובסביבת הבדיקות.
2. כבוי: טקסט, תמונה, לחיצת כפתור ותגובה (גם עם ``WHATSAPP_INBOUND_RSVP=1``) —
   אין שורת הודעה, אין שורת יומן, האורח לא משתנה. גם כשה-webhook חוזר.
3. כבוי: עדכוני סטטוס באותה קריאה ממשיכים לעבוד (נשלחה/נמסרה/נקראה/נכשלה,
   השלמת pending).
4. כבוי: הלוג — סוג ההודעה בלבד; בלי תוכן, טלפון או wamid.
5. דלוק: אותה הודעה נשמרת כ"דורש טיפול" — המתג באמת שולט.

הרצה: ``venv/bin/python tests/test_whatsapp_webhook_inbound_switch.py`` (עצמאי, או pytest).
"""
from __future__ import annotations

import io
import os
import secrets
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402
from tests.test_whatsapp_safety import (  # noqa: E402
    _db, _guest_row, _open_rsvp, _payload, _phone, _post, _reply,
)


def _counts(event_id) -> tuple[int, int]:
    from app import models

    db = _db()
    try:
        inbound = db.scalar(select(func.count()).select_from(models.Message).where(
            models.Message.event_id == event_id, models.Message.direction == "inbound"))
        audits = db.scalar(select(func.count()).select_from(models.AuditLog).where(
            models.AuditLog.action.in_(("confirm_submit", "whatsapp_reply_unmatched",
                                        "whatsapp_message_unmatched"))))
        return inbound, audits
    finally:
        db.close()


def _setup():
    """אירוע עם חלון אישורים פתוח, מוזמן עם תשובה והערה קיימות, הודעה יוצאת
    שנשלחה והודעה שהתוצאה שלה לא ידועה."""
    from app import models

    api, _ = bootstrap()
    _open_rsvp(api)
    phone = _phone()
    g = api.add_guest("מוזמן קיים", phone, party_size=4)
    sent_wamid = "wamid.HBgM" + secrets.token_hex(12)
    db = _db()
    try:
        guest = db.get(models.Guest, g["id"])
        guest.rsvp_status, guest.confirmed_count, guest.guest_note = "declined", 0, "הערה קיימת"
        sent = models.Message(event_id=api.event_id, guest_id=g["id"], direction="outbound",
                              kind="invitation", body="x", status="sent", provider="meta",
                              provider_message_id=sent_wamid)
        pend = models.Message(event_id=api.event_id, guest_id=g["id"], direction="outbound",
                              kind="reminder_1", body="x", status="pending", provider="meta")
        db.add_all([sent, pend])
        db.commit()
        ids = (sent.id, pend.id)
    finally:
        db.close()
    return api, g, phone, sent_wamid, ids


def _inbound_payload(phone: str, sent_wamid: str, text: str) -> list[dict]:
    intl = "972" + phone[1:]
    return [
        {"from": intl, "id": "wamid.HBgM" + secrets.token_hex(12), "type": "text",
         "text": {"body": text}},
        {"from": intl, "id": "wamid.HBgM" + secrets.token_hex(12), "type": "image",
         "image": {"id": "123"}},
        _reply(intl, "wamid.HBgM" + secrets.token_hex(12), coming=True),
        _reply(intl, "wamid.HBgM" + secrets.token_hex(12), coming=True, context=sent_wamid),
        {"from": intl, "id": "wamid.HBgM" + secrets.token_hex(12), "type": "reaction",
         "reaction": {"message_id": sent_wamid, "emoji": "👍"}},
    ]


def test_switch_is_off_by_default_and_in_tests() -> None:
    from app import whatsapp_inbound
    from tests.safe_env import WHATSAPP_SAFE_ENV

    assert WHATSAPP_SAFE_ENV["WHATSAPP_WEBHOOK_INBOUND"] == ""
    assert os.environ.get("WHATSAPP_WEBHOOK_INBOUND") == ""
    assert whatsapp_inbound.inbound_enabled() is False
    prev = os.environ.pop("WHATSAPP_WEBHOOK_INBOUND")
    try:
        assert whatsapp_inbound.inbound_enabled() is False, "לא מוגדר בכלל = כבוי"
        for value in ("0", "true", "yes", "on", " 1x", "TRUE"):
            os.environ["WHATSAPP_WEBHOOK_INBOUND"] = value
            assert whatsapp_inbound.inbound_enabled() is False, value
        os.environ["WHATSAPP_WEBHOOK_INBOUND"] = " 1 "
        assert whatsapp_inbound.inbound_enabled() is True
    finally:
        os.environ["WHATSAPP_WEBHOOK_INBOUND"] = prev
    print("✓ 1: המתג כבוי כברירת מחדל ובבדיקות; רק '1' מדליק אותו")


def test_off_inbound_changes_nothing_statuses_still_work() -> None:
    from app import models

    api, g, phone, sent_wamid, (sent_id, pend_id) = _setup()
    before_guest = _guest_row(g["id"])
    before_counts = _counts(api.event_id)
    secret_text = "נגיע 3 " + secrets.token_hex(6)
    statuses = [
        {"id": sent_wamid, "status": "delivered", "timestamp": "1790000000", "recipient_id": "972" + phone[1:]},
        {"id": sent_wamid, "status": "read", "timestamp": "1790000100", "recipient_id": "972" + phone[1:]},
        {"id": "wamid.HBgM" + secrets.token_hex(12), "status": "sent", "timestamp": "1790000000",
         "recipient_id": "972" + phone[1:],
         "biz_opaque_callback_data": f"veya:m{pend_id}:e{api.event_id}:g{g['id']}"},
    ]
    payload = _payload(*_inbound_payload(phone, sent_wamid, secret_text), statuses=statuses)
    buf = io.StringIO()
    with redirect_stdout(buf):
        for _ in range(2):  # גם webhook חוזר
            r = _post(api, payload, inbound_rsvp=True, inbound=False)
            assert r.status_code == 200, r.text
    log = buf.getvalue()

    after_guest = _guest_row(g["id"])
    assert (after_guest.rsvp_status, after_guest.confirmed_count, after_guest.guest_note) == \
        (before_guest.rsvp_status, before_guest.confirmed_count, before_guest.guest_note) == \
        ("declined", 0, "הערה קיימת")
    assert _counts(api.event_id) == before_counts, "אין שורת הודעה נכנסת ואין שורת יומן"

    db = _db()
    try:
        sent = db.get(models.Message, sent_id)
        pend = db.get(models.Message, pend_id)
        assert (sent.status, sent.read_at is not None, sent.delivered_at is not None) == ("read", True, True)
        assert pend.status == "sent" and pend.provider_message_id, "השלמת pending עובדת"
    finally:
        db.close()

    assert log.count("inbound skipped (WHATSAPP_WEBHOOK_INBOUND off)") == 10
    for leak in (secret_text, phone, "972" + phone[1:], phone[1:], sent_wamid, "HBgM", "👍"):
        assert leak not in log, "דליפה בלוג"
    print("✓ 2–4: מתג כבוי — הודעות נכנסות לא נוגעות בנתונים (גם עם INBOUND_RSVP=1 ו-webhook "
          "חוזר), סטטוסים עובדים, בלוג רק סוג ההודעה")


def test_on_inbound_is_recorded() -> None:
    from tests.test_whatsapp_safety import _inbound_rows

    api, g, phone, sent_wamid, _ = _setup()
    text = "שאלה " + secrets.token_hex(4)
    msg = {"from": "972" + phone[1:], "id": "wamid.HBgM" + secrets.token_hex(12),
           "type": "text", "text": {"body": text}}
    assert _post(api, _payload(msg), inbound_rsvp=False, inbound=True).status_code == 200
    rows = _inbound_rows(api.event_id)
    assert len(rows) == 1 and rows[0].status == "needs_attention" and rows[0].body == text
    assert _guest_row(g["id"]).rsvp_status == "declined"
    print("✓ 5: מתג דלוק — אותה הודעה נשמרת כ'דורש טיפול' (בלי שינוי RSVP)")


if __name__ == "__main__":
    try:
        test_switch_is_off_by_default_and_in_tests()
        test_off_inbound_changes_nothing_statuses_still_work()
        test_on_inbound_is_recorded()
        print("\n=== מתג הודעות נכנסות — עבר ===")
    finally:
        shutdown()
