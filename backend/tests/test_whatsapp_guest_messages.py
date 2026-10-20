""""מוזמנים כתבו לכם" — הודעות ממוזמנים לבעלי האירוע (``routers/guest_messages.py``).

מה נבדק:
  1. מוזמן כותב → בעלי האירוע רואים: שם, טלפון (לקישור wa.me), ההודעה. "טופל" מוריד.
  2. בעלי אירוע אחר לא רואים ולא מסמנים (404).
  3. מייל לבעלי האירוע: רק לכתובת מאומתת, בלי תוכן ההודעה ובלי טלפון;
     הודעה נוספת בתוך 3 שעות — בלי מייל נוסף.

הרצה: ``venv/bin/python -m pytest tests/test_whatsapp_guest_messages.py``
"""
from __future__ import annotations

import secrets
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap  # noqa: E402
from tests.test_help_requests import _CaptureEmails  # noqa: E402
from tests.test_whatsapp_inbox import _send, _text  # noqa: E402
from tests.test_whatsapp_safety import _db, _phone  # noqa: E402


def _verify_owner(api, verified: bool = True) -> str:
    from app import auth as auth_module, models

    uid = int(auth_module._decode_token(api.token)["sub"])
    db = _db()
    try:
        u = db.get(models.User, uid)
        u.email_verified_at = datetime.utcnow() if verified else None
        email = u.email
        db.commit()
        return email
    finally:
        db.close()


def test_hosts_see_and_handle_guest_messages() -> None:
    api, _ = bootstrap()
    phone = _phone()
    api.add_guest("רותם לוי", phone)
    _send(api, _text(phone, "אפשר להגיע עם הילדים?")[0])

    r = api.client.get("/guest-messages", headers=api.headers)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["waiting"] == 1
    item = data["items"][0]
    assert (item["guest_name"], item["phone"], item["body"], item["handled"]) == \
        ("רותם לוי", phone, "אפשר להגיע עם הילדים?", False)

    other, _ = bootstrap()
    assert other.client.post(f"/guest-messages/{item['id']}/handled", headers=other.headers).status_code == 404
    assert other.client.get("/guest-messages", headers=other.headers).json()["items"] == []

    r = api.client.post(f"/guest-messages/{item['id']}/handled", headers=api.headers)
    assert r.status_code == 200 and r.json()["handled"] is True
    assert api.client.get("/guest-messages", headers=api.headers).json() == {"waiting": 0, "items": []}
    everything = api.client.get("/guest-messages?all=true", headers=api.headers).json()
    assert [i["handled"] for i in everything["items"]] == [True]


def test_email_to_hosts_without_content_and_throttled() -> None:
    api, _ = bootstrap()
    email = _verify_owner(api)
    phone = _phone()
    api.add_guest("מוזמן ששואל", phone)
    secret = "שאלה פרטית " + secrets.token_hex(4)
    with _CaptureEmails(mode="live") as mails:
        _send(api, _text(phone, secret)[0])
        _send(api, _text(phone, "ועוד שאלה")[0])
    assert len(mails.sent) == 1, "מייל אחד בלבד בתוך 3 שעות"
    mail = mails.sent[0]
    assert mail["to"] == email and mail["subject"] == "מוזמנים כתבו לכם בוואטסאפ"
    for part in (mail["html_body"], mail["text_body"]):
        assert secret not in part and phone not in part and phone[1:] not in part
        assert "/app/rsvp" in part
    for banned in ("מערכת", "פלטפורמה"):  # הנוסח שלנו (הכותרת התחתונה המשותפת — לא כאן)
        assert banned not in mail["text_body"]
    assert api.client.get("/guest-messages", headers=api.headers).json()["waiting"] == 2


def test_unverified_owner_gets_no_email() -> None:
    api, _ = bootstrap()
    _verify_owner(api, verified=False)
    phone = _phone()
    api.add_guest("מוזמן", phone)
    with _CaptureEmails(mode="live") as mails:
        _send(api, _text(phone, "שאלה")[0])
    assert mails.sent == []
