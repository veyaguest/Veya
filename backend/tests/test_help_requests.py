"""עזרה בתוך VEYA — שלב 7: פנייה לצוות VEYA.

מה נבדק (HELP_CENTER_PLAN.md §10 + החלטות המייסד 2026-09-29):
  1. פיצ'ר כבוי → הנתיבים לא קיימים (404).
  2. רק מנהלי האירוע (בעלים / בן-בת זוג). מפיק, זר, אדמין עם הטוקן שלו → 404;
     טלפן → 403. **בכניסה לתמיכה (התחזות) → 403, ושום דבר לא נשמר.**
  3. רק השדות המותרים: שדה נוסף / מזהה לא תקין / הודעה ארוכה / מסך לא מוכר → 422.
  4. תמונת המצב: בדיוק הרשימה הלבנה; הודעות שגיאה מנוקות שוב בשרת; מזהים
     בנתיב מוחלפים; העובדות מחושבות בשרת; אין שמות/טלפונים של מוזמנים.
  5. דחיפות בשרת: עד יומיים לאירוע = high.
  6. הגבלת קצב: 5 בשעה למשתמש.
  7. "הפניות שלי": רק שלי, רק באירוע הזה.
  8. מייל לצוות: רק לכתובת ב-VEYA_SUPPORT_EMAIL; בלי כתובת — לא נשלח;
     במייל אין את הטקסט שנכתב ואין את פרטי הלקוח.
  9. מסך הצוות: הרשאות Support, שינוי סטטוס נרשם ביומן האדמין.
 10. מחיקת אירוע / חשבון מוחקת את הפניות; ייצוא המידע האישי כולל אותן.
 11. מייל אישור לפונה (2026-10-06): לכתובת המאומתת של החשבון בלבד, ברקע,
     פעם אחת, עם Auto-Submitted, בעיצוב ובלוגו של VEYA, בלי הטקסט שנכתב;
     כשל ב-Resend לא נוגע בפנייה; התוצאה נרשמת עליה; לא בכניסה לתמיכה.

הרצה: ``venv/bin/python -m pytest tests/test_help_requests.py``
"""
from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import make_client  # noqa: E402
from tests.test_help_context import (  # noqa: E402
    SECRET_GUESTS, _db, _h, _register, _setup, _uid,
)

from app import help_context  # noqa: E402


def _body(**over) -> dict:
    body = {
        "message": "המוזמנת לא קיבלה את ההזמנה, בדקנו את המספר",
        "screen": "guests",
        "topic_id": "invitation.how-to-send",
        "tree_id": "invite-not-received",
        "outcome": "out-unknown",
        "recent_errors": [],
        "platform": "desktop",
    }
    body.update(over)
    return body


def _reset_limit() -> None:
    from app.routers import help as help_router

    help_router.support_limiter.reset()


def _post(client, s: dict, token: str | None = None, **over):
    return client.post("/help/requests", headers=_h(token or s["token"], s["event_id"]), json=_body(**over))


def _rows(event_id: int | None = None) -> list:
    from sqlalchemy import select

    from app import models

    def read(db):
        q = select(models.SupportRequest)
        if event_id is not None:
            q = q.where(models.SupportRequest.event_id == event_id)
        return [
            {c.name: getattr(r, c.name) for c in models.SupportRequest.__table__.columns}
            for r in db.scalars(q).all()
        ]

    return _db(read)


class _CaptureEmails:
    """מחליף את emailer.send_email בזמן הבדיקה (שומר ומחזיר את מה שהיה).

    ``mode="live"`` מדמה Resend שקיבל את המייל; ``fail="reject"`` — Resend
    דחה (4xx/5xx); ``fail="raise"`` — תקלה לא צפויה בשליחה.
    """

    def __init__(self, mode: str = "mock", fail: str = "") -> None:
        self.sent: list[dict] = []
        self.mode = mode
        self.fail = fail

    def team(self) -> list[dict]:
        return [m for m in self.sent if not m["subject"].startswith("קיבלנו את הפנייה")]

    def confirmations(self) -> list[dict]:
        return [m for m in self.sent if m["subject"].startswith("קיבלנו את הפנייה")]

    def __enter__(self):
        from app import emailer

        self._saved = emailer.send_email

        def capture(**kw):
            self.sent.append(kw)
            if self.fail == "raise":
                raise RuntimeError("resend down")
            if self.fail == "reject":
                return emailer.SendResult(ok=False, mode="live", error="Resend 500: boom")
            return emailer.SendResult(ok=True, mode=self.mode, provider_id="test")

        emailer.send_email = capture
        return self

    def __exit__(self, *exc):
        from app import emailer

        emailer.send_email = self._saved


def _with_env(name: str, value: str | None):
    class _Env:
        def __enter__(self):
            self._saved = os.environ.get(name)
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

        def __exit__(self, *exc):
            if self._saved is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = self._saved

    return _Env()


def _add_partner(client, s: dict) -> str:
    from app import emailer

    partner_email, partner_token = _register(client, "דנה כהן")
    captured: list[dict] = []
    current = emailer.send_partner_invite

    def capture(**kw):
        captured.append(kw)
        return current(**kw)

    emailer.send_partner_invite = capture
    try:
        assert client.post("/partner/invite", headers=_h(s["token"]), json={"email": partner_email}).status_code == 201
    finally:
        emailer.send_partner_invite = current
    tok = captured[-1]["invite_url"].split("token=")[1]
    assert client.post(f"/partner/invitations/{tok}/accept", headers=_h(partner_token)).status_code == 200
    return partner_token


def _make_admin(client, role: str = "support") -> str:
    from app import models

    _, token = _register(client, f"צוות {role}")
    uid = _uid(token)

    def promote(db):
        u = db.get(models.User, uid)
        u.is_admin = True
        u.admin_role = role

    _db(promote)
    return token


def _set_event_date(event_id: int, days_from_today: int | None) -> None:
    from app import guest_journey, models

    def set_date(db):
        ev = db.get(models.Event, event_id)
        ev.event_date = (
            "" if days_from_today is None
            else (guest_journey.today_in_israel() + timedelta(days=days_from_today)).isoformat()
        )

    _db(set_date)


# ── 1. פיצ'ר כבוי ─────────────────────────────────────────────────────────

def test_flag_off_means_no_support_endpoints() -> None:
    _reset_limit()
    client, _ = make_client()
    s = _setup(client, help_on=False)
    assert _post(client, s).status_code == 404
    assert client.get("/help/requests/mine", headers=_h(s["token"], s["event_id"])).status_code == 404
    assert _rows(s["event_id"]) == []


# ── 2. מי רשאי ─────────────────────────────────────────────────────────────

def test_only_event_managers_and_never_in_impersonation() -> None:
    from app import auth as auth_module
    from app import models

    _reset_limit()
    client, _ = make_client()
    s = _setup(client)
    assert _post(client, s).status_code == 201

    partner_token = _add_partner(client, s)
    assert _post(client, s, partner_token).status_code == 201

    _, planner = _register(client, "מפיק")
    pid = _uid(planner)
    _db(lambda db: db.add(models.EventMember(
        event_id=s["event_id"], user_id=pid, role="planner",
        permissions=["view_guests", "edit_guests", "send_messages"], status="active",
    )))
    assert _post(client, s, planner).status_code == 404

    _, stranger = _register(client, "זר")
    assert _post(client, s, stranger).status_code == 404

    admin_token = _make_admin(client, "super_admin")
    assert _post(client, s, admin_token).status_code == 404

    _, agent = _register(client, "טלפן")
    aid = _uid(agent)
    _db(lambda db: setattr(db.get(models.User, aid), "account_type", "phone_agent"))
    assert _post(client, s, agent).status_code == 403

    before = len(_rows(s["event_id"]))
    # כניסה לתמיכה: טוקן של בעל/ת האירוע עם imp — חסום, ושום דבר לא נשמר.
    owner = _db(lambda db: db.get(models.User, _uid(s["token"])))
    imp_token = auth_module.create_access_token(
        owner, expires=auth_module.IMPERSONATION_EXPIRE, impersonated_by=_uid(admin_token),
    )
    r = _post(client, s, imp_token)
    assert r.status_code == 403, r.text
    assert len(_rows(s["event_id"])) == before
    # קריאה של "הפניות שלי" בכניסה לתמיכה — מותרת (כמו כל מסך אחר של הלקוח).
    assert client.get("/help/requests/mine", headers=_h(imp_token, s["event_id"])).status_code == 200


# ── 3. רק השדות המותרים ─────────────────────────────────────────────────────

def test_rejects_unknown_fields_and_bad_values() -> None:
    _reset_limit()
    client, _ = make_client()
    s = _setup(client)
    bad = [
        {"guest_phone": "0527770011"},                 # שדה שלא ברשימה
        {"message": "א" * 1001},                        # ארוך מדי
        {"message": "  "},                              # ריק
        {"message": "אב"},                              # קצר מדי
        {"screen": "admin"},                            # מסך לא מוכר
        {"topic_id": "<script>"},                       # מזהה לא תקין
        {"tree_id": "Invite Not Sent"},                 # מזהה לא תקין
        {"platform": "tablet"},
        {"recent_errors": [{"method": "POST", "path": "/guests", "status": 422}] * 6},
        {"recent_errors": [{"method": "POST", "path": "https://evil.example/x", "status": 422}]},
        {"recent_errors": [{"method": "POST", "path": "/guests", "status": 422, "guest_name": "x"}]},
    ]
    for over in bad:
        r = _post(client, s, **over)
        assert r.status_code == 422, (over, r.status_code, r.text)
    assert _rows(s["event_id"]) == []


# ── 4. תמונת המצב ─────────────────────────────────────────────────────────

def test_context_is_the_whitelist_redacted_and_server_computed() -> None:
    _reset_limit()
    client, _ = make_client()
    s = _setup(client)
    r = _post(client, s, recent_errors=[
        {"method": "PATCH", "path": "/guests/555", "status": 422,
         "message": "נראה שהמספר 0527770011 לא תקין. למשל 050-1234567"},
        {"method": "POST", "path": "/seating/generate", "status": 400,
         "message": "חבורה גדולה ממספר הכיסאות לשולחן: זהבית סודית, אלמוג נסתר"},
        {"method": "POST", "path": "/guests", "status": 0, "message": "dana@example.com לא הצליח"},
    ])
    assert r.status_code == 201, r.text
    row = _rows(s["event_id"])[0]
    ctx = row["context"]
    assert set(ctx) == {
        "event_type", "role", "screen", "topic_id", "tree_id", "outcome", "tour_flow",
        "days_to_event", "platform", "recent_errors", "facts",
    }
    assert ctx["role"] == "owner" and ctx["screen"] == "guests" and ctx["tree_id"] == "invite-not-received"
    assert ctx["recent_errors"][0]["path"] == "/guests/{id}"
    assert ctx["facts"] == _db(lambda db: help_context.screen_facts(db, db.get(__import__("app.models", fromlist=["Event"]).Event, s["event_id"]), "guests"))
    stored = json.dumps(row, default=str, ensure_ascii=False)
    for name, phone in SECRET_GUESTS:
        for part in [phone, phone[3:], *name.split()]:
            assert part not in stored, (part, stored)
    for secret in ("555", "dana", "example.com", "1234567"):
        assert secret not in stored, (secret, stored)
    assert row["status"] == "new" and row["contact_channel"] == "email"
    assert row["message"] == _body()["message"]


# ── 5. דחיפות ─────────────────────────────────────────────────────────────

def test_urgency_is_decided_by_the_server() -> None:
    _reset_limit()
    client, _ = make_client()
    s = _setup(client)
    expected = [(None, "normal"), (10, "normal"), (2, "high"), (1, "high"), (0, "high"), (-3, "normal")]
    for days, urgency in expected:
        _reset_limit()
        _set_event_date(s["event_id"], days)
        assert _post(client, s).status_code == 201
        assert _rows(s["event_id"])[-1]["urgency"] == urgency, (days, urgency)


# ── 6. הגבלת קצב ──────────────────────────────────────────────────────────

def test_rate_limited_to_five_an_hour_per_user() -> None:
    _reset_limit()
    client, _ = make_client()
    s = _setup(client)
    for _ in range(5):
        assert _post(client, s).status_code == 201
    r = _post(client, s)
    assert r.status_code == 429 and "פניות" in r.json()["detail"]
    assert len(_rows(s["event_id"])) == 5
    _reset_limit()


# ── 7. הפניות שלי ─────────────────────────────────────────────────────────

def test_mine_lists_only_my_requests_in_this_event() -> None:
    _reset_limit()
    client, _ = make_client()
    s = _setup(client)
    other = _setup(client)
    partner_token = _add_partner(client, s)
    assert _post(client, s).status_code == 201
    assert _post(client, s, partner_token).status_code == 201
    assert _post(client, other).status_code == 201
    mine = client.get("/help/requests/mine", headers=_h(s["token"], s["event_id"])).json()
    assert len(mine) == 1 and set(mine[0]) == {"id", "status", "created_at"}
    theirs = client.get("/help/requests/mine", headers=_h(partner_token, s["event_id"])).json()
    assert len(theirs) == 1 and theirs[0]["id"] != mine[0]["id"]


# ── 8. מייל לצוות ─────────────────────────────────────────────────────────

def test_team_email_only_to_configured_address_and_without_personal_text() -> None:
    _reset_limit()
    client, _ = make_client()
    s = _setup(client)
    with _with_env("VEYA_SUPPORT_EMAIL", None), _CaptureEmails() as mails:
        assert _post(client, s).status_code == 201
        assert mails.team() == []  # בלי כתובת — לא נשלח כלום לצוות
    with _with_env("VEYA_SUPPORT_EMAIL", "team-inbox@veya.test"), _CaptureEmails() as mails:
        _set_event_date(s["event_id"], 1)
        r = _post(client, s)
        assert r.status_code == 201
        assert len(mails.team()) == 1
        mail = mails.team()[0]
        assert mail["to"] == "team-inbox@veya.test"
        rid = r.json()["id"]
        assert f"#{rid}" in mail["subject"] and "דחוף" in mail["subject"]
        assert f"/app#/admin/support/{rid}" in mail["text_body"]
        from app import models

        owner = _db(lambda db: db.get(models.User, _uid(s["token"])))
        everything = mail["subject"] + mail["html_body"] + mail["text_body"]
        for secret in (_body()["message"], owner.email, owner.display_name, *[n for n, _ in SECRET_GUESTS]):
            assert secret not in everything, secret


def test_address_is_not_hardcoded() -> None:
    src = (Path(__file__).resolve().parent.parent / "app" / "help_support.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in src.splitlines() if not line.strip().startswith("#"))
    import re

    assert "VEYA_SUPPORT_EMAIL" in code
    # שום כתובת מייל בקוד עצמו (מחוץ לתיעוד).
    body = code.split('"""', 2)[-1]
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", body), "כתובת מייל קבועה בקוד"


def test_no_external_calls_when_sending() -> None:
    import socket

    import httpx

    _reset_limit()
    client, _ = make_client()
    s = _setup(client)

    def blocked(*_a, **_kw):
        raise AssertionError("קריאת רשת מתוך פנייה לצוות")

    saved = (httpx.HTTPTransport.handle_request, socket.socket.connect, socket.create_connection)
    httpx.HTTPTransport.handle_request = blocked  # type: ignore[method-assign]
    socket.socket.connect = blocked  # type: ignore[method-assign]
    socket.create_connection = blocked  # type: ignore[assignment]
    try:
        with _with_env("VEYA_SUPPORT_EMAIL", None):
            assert _post(client, s).status_code == 201
        with _with_env("VEYA_SUPPORT_EMAIL", "team-inbox@veya.test"), _with_env("RESEND_API_KEY", None):
            assert _post(client, s).status_code == 201  # מצב mock — בלי רשת
    finally:
        (httpx.HTTPTransport.handle_request, socket.socket.connect, socket.create_connection) = saved


# ── 9. מסך הצוות ──────────────────────────────────────────────────────────

def test_admin_screen_permissions_and_status_audit() -> None:
    from sqlalchemy import select

    from app import models

    _reset_limit()
    client, _ = make_client()
    s = _setup(client)
    rid = _post(client, s).json()["id"]

    # לא-אדמין → אין גישה.
    assert client.get("/admin/support/requests", headers=_h(s["token"])).status_code in (401, 403)

    support = _make_admin(client, "support")
    listing = client.get("/admin/support/requests", headers=_h(support))
    assert listing.status_code == 200
    item = next(i for i in listing.json() if i["id"] == rid)
    assert item["status"] == "new" and item["user"]["email"] and item["event"]["id"] == s["event_id"]

    detail = client.get(f"/admin/support/requests/{rid}", headers=_h(support)).json()
    assert detail["message"] == _body()["message"] and detail["context"]["screen"] == "guests"

    bad = client.post(f"/admin/support/requests/{rid}/status", headers=_h(support), json={"status": "deleted"})
    assert bad.status_code == 422
    ok = client.post(f"/admin/support/requests/{rid}/status", headers=_h(support), json={"status": "in_progress"})
    assert ok.status_code == 200 and ok.json()["status"] == "in_progress"
    assert ok.json()["handled_by"]["id"] == _uid(support)
    audit = _db(lambda db: db.scalars(
        select(models.AdminAuditLog).where(models.AdminAuditLog.action == "support.status",
                                           models.AdminAuditLog.target_id == str(rid))
    ).all())
    assert len(audit) == 1 and audit[0].domain == "support"

    # "פתוחות" (ברירת המחדל) לא כולל טופלו.
    client.post(f"/admin/support/requests/{rid}/status", headers=_h(support), json={"status": "resolved"})
    open_ids = [i["id"] for i in client.get("/admin/support/requests", headers=_h(support)).json()]
    assert rid not in open_ids
    done_ids = [i["id"] for i in client.get("/admin/support/requests?status=resolved", headers=_h(support)).json()]
    assert rid in done_ids
    assert client.get("/admin/support/requests/999999", headers=_h(support)).status_code == 404


# ── 10. מחיקה וייצוא ─────────────────────────────────────────────────────

def test_event_and_account_deletion_remove_requests_and_export_includes_them() -> None:
    _reset_limit()
    client, _ = make_client()
    s = _setup(client)
    partner_token = _add_partner(client, s)
    assert _post(client, s).status_code == 201
    assert _post(client, s, partner_token).status_code == 201

    export = client.get("/auth/me/export", headers=_h(s["token"])).json()
    assert len(export["support_requests"]) == 1
    assert export["support_requests"][0]["message"] == _body()["message"]

    # מחיקת האירוע בידי הבעלים — גם הפנייה של בן/בת הזוג על האירוע נמחקת.
    assert client.delete(f"/events/{s['event_id']}", headers=_h(s["token"])).status_code == 204
    assert _rows(s["event_id"]) == []

    # מחיקת חשבון — הפניות שלו נמחקות.
    _reset_limit()
    other = _setup(client)
    assert _post(client, other).status_code == 201
    uid = _uid(other["token"])
    assert client.request("DELETE", "/auth/me", headers=_h(other["token"]),
                          json={"password": "Test12345!", "confirm": True}).status_code in (200, 204)
    from sqlalchemy import select

    from app import models

    left = _db(lambda db: db.scalars(select(models.SupportRequest).where(models.SupportRequest.user_id == uid)).all())
    assert left == []


# ── 11. מייל אישור לפונה ──────────────────────────────────────────────────

def _confirmation_row(rid: int) -> dict:
    return next(r for r in _rows() if r["id"] == rid)


def test_confirmation_goes_to_the_verified_account_email_in_veya_design() -> None:
    from app import emailer, models

    _reset_limit()
    client, _ = make_client()
    s = _setup(client)
    owner = _db(lambda db: db.get(models.User, _uid(s["token"])))
    with _with_env("VEYA_SUPPORT_EMAIL", "team-inbox@veya.test"), _CaptureEmails(mode="live") as mails:
        r = _post(client, s)
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
        assert len(mails.confirmations()) == 1, "מייל אישור אחד לפונה"
        assert len(mails.team()) == 1, "ההתראה לצוות לא השתנתה"
    mail = mails.confirmations()[0]
    # הנמען: המייל של החשבון — לא משהו שהדפדפן שלח.
    assert mail["to"] == owner.email
    assert mail["reply_to"] == emailer.SUPPORT_ADDRESS == "support@veyaguest.co.il"
    assert mail["headers"] == {"Auto-Submitted": "auto-generated"}
    assert mail["idempotency_key"] == f"veya-support-confirmation-{rid}"
    # התוכן: מה שהמייסד ביקש, מספר הפנייה, חתימה.
    everything = mail["subject"] + mail["html_body"] + mail["text_body"]
    for line in (
        "קיבלנו את הפנייה שלך", "קיבלנו את הפנייה שלך לצוות VEYA והיא נקלטה בהצלחה.",
        "נחזור אליך במייל לאחר שנבדוק את הפנייה.", "אין צורך לשלוח את הפנייה שוב.",
        f"#{rid}", "צוות VEYA", "support@veyaguest.co.il",
    ):
        assert line in mail["html_body"] and line in mail["text_body"], line
    # בלי הטקסט שנכתב, בלי פרטי מוזמנים, בלי זמן תגובה, בלי מידע פנימי.
    for secret in (_body()["message"], *[n for n, _ in SECRET_GUESTS], "/admin", "team-inbox"):
        assert secret not in everything, secret
    for promise in ("שעות", "ימי עבודה", "תוך", "עד מחר"):
        assert promise not in everything, f"הבטחת זמן תגובה: {promise}"
    # העיצוב של VEYA: אותה מעטפת, אותו לוגו (frontend/public/logo.png), RTL.
    html_body = mail["html_body"]
    assert '<html dir="rtl" lang="he">' in html_body
    assert f'src="{emailer.logo_url()}"' in html_body and emailer.logo_url().endswith("/logo.png")
    assert (Path(__file__).resolve().parents[2] / "frontend" / "public" / "logo.png").is_file()
    for token in (emailer._SURFACE, emailer._GOLD, "Frank Ruhl Libre", "Assistant", "max-width:460px"):
        assert token in html_body, token
    # התוצאה נרשמה על הפנייה.
    row = _confirmation_row(rid)
    assert row["confirmation_status"] == "sent" and row["confirmation_sent_at"] is not None


def test_request_is_saved_even_when_resend_fails() -> None:
    _reset_limit()
    client, _ = make_client()
    s = _setup(client)
    for fail in ("reject", "raise"):
        with _CaptureEmails(mode="live", fail=fail) as mails:
            r = _post(client, s)
            assert r.status_code == 201, (fail, r.text)
            assert len(mails.confirmations()) == 1
        row = _confirmation_row(r.json()["id"])
        assert row["message"] == _body()["message"], "הפנייה נשמרה כמו שהיא"
        assert row["confirmation_status"] == "failed" and row["confirmation_sent_at"] is None, fail


def test_confirmation_is_never_sent_twice() -> None:
    from app import help_support

    _reset_limit()
    client, _ = make_client()
    s = _setup(client)
    with _CaptureEmails(mode="live") as mails:
        rid = _post(client, s).json()["id"]
        assert help_support.send_confirmation(rid) == "duplicate"
        assert help_support.send_confirmation(rid) == "duplicate"
        assert len(mails.confirmations()) == 1
    assert _confirmation_row(rid)["confirmation_status"] == "sent"
    # פנייה שכבר נכשלה — גם היא לא נשלחת שוב אוטומטית.
    with _CaptureEmails(mode="live", fail="reject") as mails:
        rid2 = _post(client, s).json()["id"]
    with _CaptureEmails(mode="live") as mails:
        assert help_support.send_confirmation(rid2) == "duplicate"
        assert mails.sent == []


def test_recipient_only_from_the_verified_account() -> None:
    from app import models

    _reset_limit()
    client, _ = make_client()
    s = _setup(client)
    # הדפדפן לא יכול לבחור לאן יישלח האישור.
    with _CaptureEmails(mode="live") as mails:
        r = _post(client, s, email="someone-else@example.com")
        assert r.status_code == 422
        assert mails.sent == []
    # חשבון בלי מייל מאומת — הפנייה נשמרת, אישור לא נשלח.
    uid = _uid(s["token"])
    verified_at = _db(lambda db: db.get(models.User, uid).email_verified_at)
    _db(lambda db: setattr(db.get(models.User, uid), "email_verified_at", None))
    try:
        with _CaptureEmails(mode="live") as mails:
            r = _post(client, s)
            assert r.status_code == 201
            assert mails.confirmations() == []
        assert _confirmation_row(r.json()["id"])["confirmation_status"] == "skipped"
    finally:
        _db(lambda db: setattr(db.get(models.User, uid), "email_verified_at", verified_at))
    # בן/בת זוג — האישור הולך לכתובת שלהם, לא לבעלים.
    partner_token = _add_partner(client, s)
    partner = _db(lambda db: db.get(models.User, _uid(partner_token)))
    with _CaptureEmails(mode="live") as mails:
        assert _post(client, s, partner_token).status_code == 201
        assert [m["to"] for m in mails.confirmations()] == [partner.email]


def test_no_confirmation_in_impersonation_or_when_help_is_off() -> None:
    from app import auth as auth_module
    from app import models

    _reset_limit()
    client, _ = make_client()
    s = _setup(client)
    admin_token = _make_admin(client, "super_admin")
    owner = _db(lambda db: db.get(models.User, _uid(s["token"])))
    imp = auth_module.create_access_token(owner, expires=auth_module.IMPERSONATION_EXPIRE, impersonated_by=_uid(admin_token))
    off = _setup(client, help_on=False)
    with _CaptureEmails(mode="live") as mails:
        assert _post(client, s, imp).status_code == 403
        assert _post(client, off).status_code == 404
        assert mails.sent == []


def test_confirmation_columns_migrate_and_rls_is_unchanged() -> None:
    root = Path(__file__).resolve().parent.parent
    main_src = (root / "app" / "main.py").read_text(encoding="utf-8")
    assert '"support_requests": {' in main_src and '"confirmation_status": "TEXT DEFAULT \'\'"' in main_src
    sql = (root / "rls" / "25_help_rls.sql").read_text(encoding="utf-8")
    # עדכון פנייה — עדיין אדמין בלבד. מייל האישור נרשם בחיבור המערכת, לא בהרחבת RLS.
    assert "FOR UPDATE\n  USING (app_is_admin())\n  WITH CHECK (app_is_admin());" in sql
    src = (root / "app" / "help_support.py").read_text(encoding="utf-8")
    assert "MigrationSessionLocal" in src and 'SR.confirmation_status == ""' in src


def test_rls_file_is_registered_and_forced() -> None:
    root = Path(__file__).resolve().parent.parent
    sql = (root / "rls" / "25_help_rls.sql").read_text(encoding="utf-8")
    for clause in ("ENABLE ROW LEVEL SECURITY", "FORCE  ROW LEVEL SECURITY"):
        assert f"ALTER TABLE support_requests {clause}" in sql
    main_src = (root / "app" / "main.py").read_text(encoding="utf-8")
    assert '"25_help_rls.sql"' in main_src


def teardown_module(_module) -> None:
    """הבדיקות כאן מדליקות את העזרה לאירועים; מטמון הפיצ'רים חי בתהליך, ובקובץ
    הבא מסד חדש עלול לתת לאירוע חדש אותו מזהה — מנקים כדי שלא "יירש" דגל."""
    from app import features

    features.invalidate()
    _reset_limit()
