"""מענה לפניות מתוך מסך "פניות תמיכה" (2026-10-07).

מה נבדק:
  1. מורשה (Support ומעלה) שולח; משתמש רגיל / בעלי האירוע / בלי התחברות — לא.
  2. הנמען — כתובת החשבון שפתח את הפנייה. שדה נמען מהדפדפן נדחה (422).
  3. השליחה דרך Resend: ה-payload ל-api.resend.com — to, reply_to=support@,
     Idempotency-Key. בלי רשת אמיתית.
  4. תשובה שנשלחה נשמרת (טקסט, מי, מתי) ומוצגת בפנייה.
  5. **סטטוס:** תשובה — מוצלחת או כושלת — לא משנה את הסטטוס. רק "/status".
  6. כשל ב-Resend → 502, השורה failed, לא "נשלחה"; ניסיון חוזר על אותה שורה.
  7. לחיצה כפולה (אותו client_token) → מייל אחד. בשליחה → 409.
  8. המייל: התבנית והלוגו של VEYA, RTL, טקסט בלבד (HTML של האדמין לא מרונדר),
     HTML תקין ומותאם לטלפון.
  9. מחיקת חשבון מוחקת גם את התשובות; ייצוא המידע כולל רק תשובות שנשלחו.
 10. RLS: קובץ 27 רשום, ENABLE + FORCE, כתיבה לאדמין בלבד.

הרצה: ``venv/bin/python -m pytest tests/test_support_replies.py``
"""
from __future__ import annotations

import html.parser
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import make_client  # noqa: E402
from tests.test_help_context import _db, _h, _setup, _uid  # noqa: E402
from tests.test_help_requests import (  # noqa: E402
    _CaptureEmails, _make_admin, _post, _register, _reset_limit, _with_env,
)

REPLY = "שלום,\n\nבדקנו את ההזמנה — <b>הכול תקין</b>.\nאפשר לשלוח שוב מהמסך."


def _token() -> str:
    return uuid.uuid4().hex


def _reply(client, admin: str, rid: int, body: str = REPLY, token: str | None = None, **extra):
    return client.post(
        f"/admin/support/requests/{rid}/replies", headers=_h(admin),
        json={"body": body, "client_token": token or _token(), **extra},
    )


def _status(client, admin: str, rid: int) -> str:
    return client.get(f"/admin/support/requests/{rid}", headers=_h(admin)).json()["status"]


def _fresh(client):
    _reset_limit()
    s = _setup(client)
    with _CaptureEmails():  # מייל האישור לפונה — לא חלק מהבדיקות כאן
        rid = _post(client, s).json()["id"]
    return s, rid


def _owner_email(s: dict) -> str:
    from app import models

    return _db(lambda db: db.get(models.User, _uid(s["token"])).email)


# ── 1. הרשאות ─────────────────────────────────────────────────────────────

def test_only_support_staff_can_reply() -> None:
    client, _ = make_client()
    s, rid = _fresh(client)
    _, stranger = _register(client, "זר")
    with _CaptureEmails(mode="live") as mails:
        assert _reply(client, s["token"], rid).status_code in (401, 403), "בעלי האירוע לא עונים לעצמם"
        assert _reply(client, stranger, rid).status_code in (401, 403)
        assert client.post(f"/admin/support/requests/{rid}/replies", json={"body": "x", "client_token": _token()}).status_code == 401
        assert mails.sent == []
    support = _make_admin(client, "support")
    with _CaptureEmails(mode="live") as mails:
        r = _reply(client, support, rid)
        assert r.status_code == 200, r.text
        assert len(mails.sent) == 1
    assert client.post("/admin/support/requests/999999/replies", headers=_h(support),
                       json={"body": "x", "client_token": _token()}).status_code == 404


# ── 2–3. הנמען מהפנייה, השליחה דרך Resend ─────────────────────────────────

def test_recipient_comes_from_the_request_not_the_browser() -> None:
    client, _ = make_client()
    s, rid = _fresh(client)
    support = _make_admin(client, "support")
    with _CaptureEmails(mode="live") as mails:
        bad = _reply(client, support, rid, to="attacker@example.com")
        assert bad.status_code == 422, "שדה נמען מהדפדפן נדחה"
        assert _reply(client, support, rid, body="   ").status_code == 422
        assert _reply(client, support, rid, body="x" * 5001).status_code == 422
        assert mails.sent == []
        assert _reply(client, support, rid).status_code == 200
    assert [m["to"] for m in mails.sent] == [_owner_email(s)]


def test_sent_through_resend_with_reply_to_support() -> None:
    import httpx

    client, _ = make_client()
    s, rid = _fresh(client)
    support = _make_admin(client, "support")
    calls: list[dict] = []

    class _Resp:
        status_code = 200
        text = '{"id":"re_test"}'

        def json(self):
            return {"id": "re_test"}

    saved = httpx.post

    def fake_post(url, **kw):
        calls.append({"url": url, **kw})
        return _Resp()

    httpx.post = fake_post  # type: ignore[assignment]
    try:
        with _with_env("RESEND_API_KEY", "re_test_key_not_real"):
            r = _reply(client, support, rid)
    finally:
        httpx.post = saved  # type: ignore[assignment]
    assert r.status_code == 200, r.text
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == "https://api.resend.com/emails"
    assert call["json"]["to"] == [_owner_email(s)]
    assert call["json"]["reply_to"] == "support@veyaguest.co.il"
    assert call["json"]["from"] == "VEYA <invite@veyaguest.co.il>", "כתובת השליחה הקיימת — לא השתנתה"
    assert call["headers"]["Idempotency-Key"].startswith("veya-support-reply-")
    assert "Auto-Submitted" not in call["json"].get("headers", {}), "תשובה של אדם — לא מסומנת אוטומטית"
    reply = r.json()["replies"][-1]
    assert reply["status"] == "sent" and reply["sent_at"]


# ── 4–5. היסטוריה, וסטטוס נפרד ────────────────────────────────────────────

def test_reply_is_saved_and_never_changes_the_status() -> None:
    from sqlalchemy import select

    from app import models

    client, _ = make_client()
    s, rid = _fresh(client)
    support = _make_admin(client, "support")
    assert _status(client, support, rid) == "new"
    with _CaptureEmails(mode="live"):
        r = _reply(client, support, rid)
    assert r.status_code == 200
    detail = r.json()
    assert detail["status"] == "new", "תשובה לא מסמנת טופלה"
    assert detail["handled_by"] is None
    reply = detail["replies"][-1]
    assert reply["body"] == REPLY.strip() and reply["status"] == "sent" and reply["sent_at"]
    assert reply["admin"]["id"] == _uid(support)
    # נכנסים שוב לפנייה — התשובה שם.
    again = client.get(f"/admin/support/requests/{rid}", headers=_h(support)).json()
    assert [x["body"] for x in again["replies"]] == [REPLY.strip()]
    # גם אחרי "בטיפול" — תשובה נוספת לא נוגעת בסטטוס.
    client.post(f"/admin/support/requests/{rid}/status", headers=_h(support), json={"status": "in_progress"})
    with _CaptureEmails(mode="live"):
        assert _reply(client, support, rid, body="עדכון נוסף").json()["status"] == "in_progress"
    # רק "סימון טופלה" משנה.
    done = client.post(f"/admin/support/requests/{rid}/status", headers=_h(support), json={"status": "resolved"})
    assert done.json()["status"] == "resolved"
    # ביומן האדמין: התשובה נרשמה — בלי התוכן.
    audit = _db(lambda db: db.scalars(
        select(models.AdminAuditLog).where(models.AdminAuditLog.action == "support.reply",
                                           models.AdminAuditLog.target_id == str(rid))
    ).all())
    assert len(audit) == 2
    for row in audit:
        assert "הכול תקין" not in (row.summary or "") and "עדכון נוסף" not in (row.summary or "")


# ── 6. כשל ב-Resend ───────────────────────────────────────────────────────

def test_resend_failure_is_not_saved_as_sent_and_can_be_retried() -> None:
    client, _ = make_client()
    s, rid = _fresh(client)
    support = _make_admin(client, "support")
    token = _token()
    for fail in ("reject", "raise"):
        with _CaptureEmails(mode="live", fail=fail) as mails:
            r = _reply(client, support, rid, token=token)
            assert r.status_code == 502, (fail, r.text)
            assert "לא נשלח" in r.json()["detail"]
            assert len(mails.sent) == 1
        detail = client.get(f"/admin/support/requests/{rid}", headers=_h(support)).json()
        assert detail["status"] == "new", "כשל לא מסמן טופלה"
        assert [x["status"] for x in detail["replies"]] == ["failed"]
        assert detail["replies"][0]["sent_at"] is None
    # ניסיון חוזר — אותה שורה, עכשיו נשלח.
    with _CaptureEmails(mode="live") as mails:
        r = _reply(client, support, rid, token=token)
        assert r.status_code == 200
        assert len(mails.sent) == 1
        assert mails.sent[0]["idempotency_key"].endswith("-3"), "ניסיון שלישי — מפתח חדש ל-Resend"
    detail = r.json()
    assert [x["status"] for x in detail["replies"]] == ["sent"] and detail["status"] == "new"


# ── 7. לחיצה כפולה ────────────────────────────────────────────────────────

def test_double_click_sends_one_email() -> None:
    from sqlalchemy import update

    from app import models

    client, _ = make_client()
    s, rid = _fresh(client)
    support = _make_admin(client, "support")
    token = _token()
    with _CaptureEmails(mode="live") as mails:
        first = _reply(client, support, rid, token=token)
        second = _reply(client, support, rid, token=token)
        assert first.status_code == 200 and second.status_code == 200
        assert len(mails.sent) == 1, "אותו חלון, אותה תשובה — מייל אחד"
        assert len(second.json()["replies"]) == 1
        # אותו מזהה עם טקסט אחר — לא נשלח כאילו זו אותה תשובה.
        assert _reply(client, support, rid, body="טקסט אחר", token=token).status_code == 409
        assert len(mails.sent) == 1
    # בקשה שנייה בזמן שהראשונה עוד בשליחה → 409, בלי מייל.
    token2 = _token()
    with _CaptureEmails(mode="live", fail="reject"):
        _reply(client, support, rid, token=token2)
    _db(lambda db: db.execute(
        update(models.SupportReply).where(models.SupportReply.client_token == token2).values(status="sending")
    ))
    with _CaptureEmails(mode="live") as mails:
        assert _reply(client, support, rid, token=token2).status_code == 409
        assert mails.sent == []


# ── 8. המייל ──────────────────────────────────────────────────────────────

class _Html(html.parser.HTMLParser):
    VOID = {"meta", "link", "img", "br"}

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.errors: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.errors.append(tag)


def test_reply_email_uses_the_veya_template_and_logo() -> None:
    from app import emailer

    client, _ = make_client()
    s, rid = _fresh(client)
    support = _make_admin(client, "support")
    with _CaptureEmails(mode="live") as mails:
        assert _reply(client, support, rid).status_code == 200
    mail = mails.sent[0]
    assert mail["subject"] == f"צוות VEYA חזר אליך — פנייה #{rid}"
    body = mail["html_body"]
    # אותה מעטפת ואותו לוגו כמו מייל האישור.
    confirmation_html = emailer.support_confirmation_content(rid)[1]
    shell_head = confirmation_html.split("<body", 1)[0].split("<title>")[0]
    assert body.split("<body", 1)[0].split("<title>")[0] == shell_head
    assert f'src="{emailer.logo_url()}"' in body and emailer.logo_url().endswith("/logo.png")
    assert (Path(__file__).resolve().parents[2] / "frontend" / "public" / "logo.png").is_file()
    assert '<html dir="rtl" lang="he">' in body
    for piece in ("צוות VEYA חזר אליך", f"בהמשך לפנייה שלך (#{rid})", "צוות VEYA", "support@veyaguest.co.il"):
        assert piece in body and piece in mail["text_body"], piece
    # טקסט בלבד: ה-HTML שהאדמין הקליד לא מרונדר; פסקאות וירידות שורה נשמרות.
    assert "<b>הכול תקין</b>" not in body and "&lt;b&gt;הכול תקין&lt;/b&gt;" in body
    assert "<br>" in body and body.count('text-align:right') >= 2
    # בלי קישורים מלבד כתובת התמיכה, בלי כפתור/שיווק.
    import re

    assert re.findall(r'<a [^>]*href="([^"]+)"', body) == ["mailto:support@veyaguest.co.il"]
    # HTML תקין, ומותאם לטלפון.
    parser = _Html()
    parser.feed(body)
    assert parser.stack == [] and parser.errors == []
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in body
    assert "@media only screen and (max-width:480px)" in body and "max-width:460px" in body
    # בלי פרטי האירוע / מוזמנים / תמונת המצב של הפנייה.
    for leak in ("זהבית סודית", "/admin", "invite-not-received"):
        assert leak not in body


# ── 9. פרטיות: מחיקה וייצוא ───────────────────────────────────────────────

def test_export_and_account_deletion_cover_replies() -> None:
    from sqlalchemy import select

    from app import models

    client, _ = make_client()
    s, rid = _fresh(client)
    support = _make_admin(client, "support")
    with _CaptureEmails(mode="live"):
        _reply(client, support, rid)
    with _CaptureEmails(mode="live", fail="reject"):
        _reply(client, support, rid, body="טיוטה שנכשלה")
    export = client.get("/auth/me/export", headers=_h(s["token"])).json()
    mine = next(x for x in export["support_requests"] if x["message"])
    assert [x["body"] for x in mine["replies"]] == [REPLY.strip()], "רק מה שבאמת נשלח"

    uid = _uid(s["token"])
    r = client.request("DELETE", "/auth/me", headers=_h(s["token"]), json={"password": "Test12345!"})
    assert r.status_code in (200, 204), r.text
    left = _db(lambda db: db.scalars(select(models.SupportReply).where(models.SupportReply.request_id == rid)).all())
    assert left == []
    assert _db(lambda db: db.get(models.User, uid)) is None


# ── 10. RLS ───────────────────────────────────────────────────────────────

def test_rls_file_is_registered_and_forced() -> None:
    root = Path(__file__).resolve().parent.parent
    sql = (root / "rls" / "27_support_replies_rls.sql").read_text(encoding="utf-8")
    for clause in ("ENABLE ROW LEVEL SECURITY", "FORCE  ROW LEVEL SECURITY"):
        assert f"ALTER TABLE support_replies {clause}" in sql
    assert "FOR INSERT\n  WITH CHECK (app_is_admin());" in sql
    assert "FOR UPDATE\n  USING (app_is_admin())\n  WITH CHECK (app_is_admin());" in sql
    main_src = (root / "app" / "main.py").read_text(encoding="utf-8")
    assert '"27_support_replies_rls.sql"' in main_src
    # הקובץ של support_requests לא השתנה: עדכון פנייה — אדמין בלבד.
    sql25 = (root / "rls" / "25_help_rls.sql").read_text(encoding="utf-8")
    assert "support_requests_update ON support_requests FOR UPDATE\n  USING (app_is_admin())" in sql25


def teardown_module(_module) -> None:
    from app import features

    features.invalidate()
    _reset_limit()
