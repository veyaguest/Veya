"""בדיקות אבטחה (סקירת OWASP Top 10:2025) — כל בדיקה כאן נכתבה קודם כהוכחה
שהפרצה קיימת, ורק אחר כך תוקן הקוד. אם אחת מהן נכשלת — הפרצה חזרה.

  A05 הזרקה     — העלאת "תמונה" שהיא בעצם HTML/JS נדחית; מדיה מוגשת עם
                  nosniff + CSP sandbox (גם בלובים ישנים שכבר שמורים).
  A10 חריגות    — סיסמה מעל 72 בייט מחזירה 422 ברור, לא 500.
  A07 הזדהות    — "שכחתי סיסמה", "שלחו שוב" והרשמה מוגבלים בקצב (הצפת מיילים);
                  ניחוש הסיסמה הנוכחית בשינוי סיסמה נחסם; טוקן התחזות קצר-מועד.
  A01/A06       — כתובת ה-IP נלקחת מה-hop האחרון של X-Forwarded-For (מאחורי
                  ה-proxy של Render), וזיוף הערך השמאלי לא עוקף את הגבלת הקצב.
  A02 הגדרות    — כותרות אבטחה בכל תשובה; תיעוד ה-API כבוי בייצור; אימות
                  ה-webhook נכשל-סגור כשאין טוקן מוגדר.

הרצה: ``venv/bin/python -m pytest tests/test_security_owasp.py``
"""
from __future__ import annotations

import base64
import io
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from tests.e2e_seating import create_event, make_client, register, shutdown  # noqa: E402

from app import emailer  # noqa: E402
from app import ratelimit  # noqa: E402


@pytest.fixture(scope="module")
def client():
    c, _ = make_client()
    yield c
    shutdown()


@pytest.fixture(autouse=True)
def _fresh_limiters():
    """כל בדיקה מתחילה ממונים נקיים — אחרת בדיקה אחת "מבזבזת" לשנייה."""
    for limiter in ratelimit.all_limiters():
        limiter.reset()
    yield


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _png_data_url() -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 100, 50)).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ---------------------------------------------------------------------------
# A05 — מדיה: תוכן פעיל (HTML/JS) לא נשמר ולא מוגש כדף
# ---------------------------------------------------------------------------

def test_invite_image_rejects_html_disguised_as_upload(client):
    token = register(client)
    create_event(client, token)
    html = base64.b64encode(b"<script>alert(document.domain)</script>").decode()
    r = client.patch(
        "/event", headers=_h(token),
        json={"invite_image": f"data:text/html;base64,{html}"},
    )
    assert r.status_code == 415, f"HTML נשמר כתמונה: {r.status_code} {r.text[:200]}"
    assert not (client.get("/event", headers=_h(token)).json().get("invite_image"))


def test_hall_sketch_rejects_non_image_types(client):
    token = register(client)
    create_event(client, token)
    js = base64.b64encode(b"alert(1)").decode()
    r = client.put("/hall", headers=_h(token), json={"tables": [], "sketch": f"data:application/javascript;base64,{js}"})
    assert r.status_code == 415, r.text[:200]


def test_media_served_with_sandbox_and_nosniff(client):
    token = register(client)
    create_event(client, token)
    r = client.patch("/event", headers=_h(token), json={"invite_image": _png_data_url()})
    assert r.status_code == 200, r.text[:200]
    url = client.get("/event", headers=_h(token)).json()["invite_image"]
    got = client.get(url)
    assert got.status_code == 200
    assert got.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in got.headers["content-security-policy"]
    assert got.headers["content-type"].startswith("image/")


def test_legacy_active_blob_is_downloaded_not_rendered(client):
    """בלוב HTML שנשמר לפני התיקון (יש כאלה במסד?) לא יוצג כדף."""
    from app import models
    from app.database import SessionLocal

    blob_id = f"legacy-{uuid.uuid4().hex[:8]}"
    db = SessionLocal()
    try:
        db.add(models.MediaBlob(id=blob_id, content_type="text/html", data=b"<script>1</script>"))
        db.commit()
    finally:
        db.close()
    got = client.get(f"/media/{blob_id}")
    assert got.status_code == 200
    assert got.headers["content-type"].startswith("application/octet-stream")
    assert got.headers["content-disposition"].startswith("attachment")
    assert "sandbox" in got.headers["content-security-policy"]


# ---------------------------------------------------------------------------
# A10 — סיסמה ארוכה מ-72 בייט (מגבלת bcrypt) לא מפילה את השרת
# ---------------------------------------------------------------------------

def test_overlong_password_is_a_clear_validation_error(client):
    r = client.post("/auth/register", json={
        "email": f"long-{uuid.uuid4().hex[:8]}@veya.test",
        "password": "סיסמהארוכה1" * 8,  # ~170 בייט ב-UTF-8
        "display_name": "בודקת", "phone": "0501234567", "accepted_terms": True,
    })
    assert r.status_code == 422, f"{r.status_code} {r.text[:200]}"


# ---------------------------------------------------------------------------
# A07 — הצפת מיילים וניחוש סיסמה
# ---------------------------------------------------------------------------

def test_forgot_password_cannot_flood_one_mailbox(client, monkeypatch):
    sent: list[str] = []
    original = emailer.send_password_reset

    def spy(**kw):
        sent.append(kw["to"])
        return original(**kw)

    monkeypatch.setattr(emailer, "send_password_reset", spy)
    email = f"flood-{uuid.uuid4().hex[:8]}@veya.test"
    r = client.post("/auth/register", json={
        "email": email, "password": "Test12345!", "display_name": "יעד",
        "phone": "0501234567", "accepted_terms": True,
    })
    assert r.status_code == 201
    codes = [client.post("/auth/forgot-password", json={"email": email}).status_code for _ in range(12)]
    assert 429 in codes, f"אין הגבלה: {codes}"
    assert len(sent) <= ratelimit.EMAIL_PER_TARGET_MAX, f"נשלחו {len(sent)} מיילים לאותה תיבה"


def test_forgot_password_same_answer_for_unknown_email(client):
    """ההגבלה לא חושפת אם הכתובת רשומה — אותה תשובה בדיוק עד החסימה."""
    r = client.post("/auth/forgot-password", json={"email": f"nobody-{uuid.uuid4().hex[:6]}@veya.test"})
    assert r.status_code == 200
    assert "אם קיימת כתובת" in r.json()["message"]


def test_resend_verification_is_limited(client):
    token = register(client)
    codes = [client.post("/auth/verify-email/resend", headers=_h(token)).status_code for _ in range(8)]
    assert 429 in codes, f"אין הגבלה: {codes}"


def test_change_password_blocks_guessing(client):
    token = register(client)
    codes = [
        client.post("/auth/change-password", headers=_h(token), json={
            "current_password": f"Wrong{i}123", "new_password": "NewPass123",
        }).status_code
        for i in range(15)
    ]
    assert 429 in codes, f"אפשר לנחש את הסיסמה הנוכחית בלי הגבלה: {codes}"


def test_impersonation_token_is_short_lived(client):
    from app import auth, models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        admin = models.User(
            email=f"imp-admin-{uuid.uuid4().hex[:8]}@veya.test",
            password_hash=auth.hash_password("Test12345!"),
            display_name="אדמין", is_admin=True,
        )
        target = models.User(
            email=f"imp-user-{uuid.uuid4().hex[:8]}@veya.test",
            password_hash=auth.hash_password("Test12345!"),
            display_name="משתמשת",
        )
        db.add_all([admin, target])
        db.commit()
        admin_token = auth.create_access_token(admin)
        target_id, admin_id = target.id, admin.id
    finally:
        db.close()

    r = client.post(f"/admin/users/{target_id}/impersonate", headers=_h(admin_token))
    assert r.status_code == 200, r.text[:200]
    payload = auth._decode_token(r.json()["token"])
    lifetime = payload["exp"] - payload["iat"]
    assert lifetime <= 2 * 3600, f"טוקן התחזות תקף {lifetime / 86400:.1f} ימים"
    assert payload.get("imp") == admin_id
    # הטוקן עדיין עובד כמו טוקן של המשתמש עצמו
    assert client.get("/auth/me", headers=_h(r.json()["token"])).json()["id"] == target_id


# ---------------------------------------------------------------------------
# A01/A06 — כתובת IP אמיתית מאחורי proxy, בלי אפשרות זיוף
# ---------------------------------------------------------------------------

def _client_host_through(hops: int, headers: list[tuple[bytes, bytes]]) -> str:
    import asyncio

    from app.http_security import TrustedProxyMiddleware

    seen: dict = {}

    async def inner(scope, receive, send):
        seen["client"] = scope.get("client")

    mw = TrustedProxyMiddleware(inner, hops=hops)
    scope = {"type": "http", "client": ("10.0.0.1", 5555), "headers": headers}
    asyncio.run(mw(scope, None, None))
    return seen["client"][0]


def test_proxy_uses_rightmost_forwarded_hop():
    xff = [(b"x-forwarded-for", b"6.6.6.6, 203.0.113.7")]  # 6.6.6.6 = זיוף של הלקוח
    assert _client_host_through(1, xff) == "203.0.113.7"


def test_proxy_disabled_keeps_socket_peer():
    xff = [(b"x-forwarded-for", b"203.0.113.7")]
    assert _client_host_through(0, xff) == "10.0.0.1"


def test_proxy_ignores_garbage_header():
    assert _client_host_through(1, [(b"x-forwarded-for", b"not-an-ip")]) == "10.0.0.1"
    assert _client_host_through(1, []) == "10.0.0.1"


# ---------------------------------------------------------------------------
# A02 — הגדרות אבטחה
# ---------------------------------------------------------------------------

def test_security_headers_on_api_responses(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_api_docs_disabled_in_production():
    from app.http_security import docs_settings

    assert docs_settings(production=True) == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    assert docs_settings(production=False) == {}


def test_webhook_handshake_fails_closed_without_token(client, monkeypatch):
    monkeypatch.delenv("WHATSAPP_VERIFY_TOKEN", raising=False)
    r = client.get("/messaging/webhook", params={
        "hub.mode": "subscribe", "hub.verify_token": "veya-verify", "hub.challenge": "42",
    })
    assert r.status_code == 403, "ברירת מחדל ידועה (veya-verify) עדיין מתקבלת"
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "a-real-secret-token")
    r = client.get("/messaging/webhook", params={
        "hub.mode": "subscribe", "hub.verify_token": "a-real-secret-token", "hub.challenge": "42",
    })
    assert r.status_code == 200 and r.text == "42"


def test_rate_limiter_forgets_idle_keys():
    limiter = ratelimit.RateLimiter(max_hits=3, window=0.0, message="x")
    for i in range(ratelimit.MAX_TRACKED_KEYS + 50):
        limiter.record_fail(f"198.51.100.{i}")
    assert len(limiter._hits) <= ratelimit.MAX_TRACKED_KEYS + 1

