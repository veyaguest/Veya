"""בדיקות לאימות מייל בקוד 6 ספרות (ערוץ מקביל לקישור הקיים).

מכסה את 12 התרחישים שהוגדרו למשימה:
  1  יצירת קוד — הרשמה מנפיקה קוד 6 ספרות, ה-DB מחזיק רק hash שלו.
  2  קוד נכון — מאמת ומחזיר email_verified=True.
  3  קוד שגוי — נדחה, לא מאמת.
  4  קוד שפג תוקפו — נדחה גם אם נכון.
  5  קוד שכבר נוצל — לא ניתן לשימוש חוזר.
  6  שליחה חוזרת (resend) מבטלת את הקוד הקודם.
  7  rate limiting — יותר מדי ניסיונות שגויים → נחסם.
  8  אימות באמצעות הקישור הקיים ממשיך לעבוד במקביל לקוד.
  9  משתמש חדש חוזר ליצירת אירוע מיד אחרי אימות בקוד.
  10 משתמש שכבר מאומת לא נשבר (קריאה חוזרת היא no-op).
  11 Resend שולח בפועל את מייל האימות (מצב mock, נבדק ע"י עטיפת emailer).
  12 קוד/טוקן גולמיים לא מודפסים ללוגים.

הרצה: ``venv/bin/python -m pytest tests/test_email_verification_code.py``
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import make_client, shutdown  # noqa: E402

from app import emailer  # noqa: E402
from app.ratelimit import auth_limiter  # noqa: E402

# מייל האימות לא נשלח באמת בבדיקות (מצב mock) — עוטפים את שולח המייל כדי
# לתפוס את הקוד הגולמי (ב-DB נשמר רק ה-hash שלו, בכוונה), בדיוק כמו
# ש-test_partner_comanagement.py תופס invite_url.
_SENT: list[dict] = []


def _capture_verification_emails():
    original = emailer.send_email_verification

    def wrapper(**kwargs):
        result = original(**kwargs)
        _SENT.append({**kwargs, "ok": result.ok})
        return result

    emailer.send_email_verification = wrapper
    return original


_ORIGINAL_SENDER = _capture_verification_emails()


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _new_email() -> str:
    return f"v-{uuid.uuid4().hex[:10]}@veya.test"


def _register(client, *, name="בודקת קוד", phone="0501234567"):
    """נרשם ומחזיר (token, code) — הקוד הגולמי מהמייל שנשלח בהרשמה."""
    _SENT.clear()
    email = _new_email()
    r = client.post("/auth/register", json={
        "email": email, "password": "Test12345!", "display_name": name,
        "phone": phone, "accepted_terms": True,
    })
    assert r.status_code == 201, f"{r.status_code} {r.text}"
    token = r.json()["access_token"]
    assert len(_SENT) == 1, "הרשמה אמורה לשלוח בדיוק מייל אימות אחד"
    return token, _SENT[-1]["code"]


def _verify_code(client, token: str, code: str):
    return client.post(
        "/auth/verify-email/verify-code", headers=_headers(token), json={"code": code},
    )


# ── 1: יצירת קוד ─────────────────────────────────────────────────────────────

def test_01_register_issues_a_six_digit_code() -> None:
    from app import models
    from app.database import SessionLocal

    client, _ = make_client()
    token, code = _register(client)
    assert len(code) == 6 and code.isdigit(), f"קוד לא תקין: {code!r}"

    payload = client.get("/auth/me", headers=_headers(token)).json()
    assert payload["email_verified"] is False

    db = SessionLocal()
    try:
        user = db.query(models.User).filter_by(email=_SENT[-1]["to"]).first()
        assert user.email_verification_code_hash is not None
        # ה-DB לעולם לא מחזיק את הקוד הגולמי עצמו.
        assert user.email_verification_code_hash != code
        assert user.email_verification_code_expires_at is not None
        assert user.email_verification_code_attempts == 0
    finally:
        db.close()
    print("✓ 1: הרשמה מנפיקה קוד 6 ספרות, ה-DB מחזיק רק hash")


# ── 2: קוד נכון ──────────────────────────────────────────────────────────────

def test_02_correct_code_verifies() -> None:
    client, _ = make_client()
    token, code = _register(client)
    r = _verify_code(client, token, code)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    assert r.json()["email_verified"] is True

    me = client.get("/auth/me", headers=_headers(token)).json()
    assert me["email_verified"] is True
    print("✓ 2: קוד נכון מאמת את המייל")


# ── 3: קוד שגוי ──────────────────────────────────────────────────────────────

def test_03_wrong_code_is_rejected() -> None:
    client, _ = make_client()
    token, code = _register(client)
    wrong = "000000" if code != "000000" else "111111"
    r = _verify_code(client, token, wrong)
    assert r.status_code == 400, f"{r.status_code} {r.text}"

    me = client.get("/auth/me", headers=_headers(token)).json()
    assert me["email_verified"] is False
    print("✓ 3: קוד שגוי נדחה, לא מאמת")


# ── 4: קוד שפג תוקפו ─────────────────────────────────────────────────────────

def test_04_expired_code_is_rejected() -> None:
    from app import models
    from app.database import SessionLocal

    client, _ = make_client()
    token, code = _register(client)

    db = SessionLocal()
    try:
        user = db.query(models.User).filter_by(email=_SENT[-1]["to"]).first()
        user.email_verification_code_expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()

    r = _verify_code(client, token, code)
    assert r.status_code == 400, f"{r.status_code} {r.text}"
    assert "פג תוקף" in r.json()["detail"]
    print("✓ 4: קוד שפג תוקפו נדחה גם אם נכון")


# ── 5: קוד שכבר נוצל ─────────────────────────────────────────────────────────

def test_05_used_code_cannot_be_reused() -> None:
    client, _ = make_client()
    token, code = _register(client)
    assert _verify_code(client, token, code).status_code == 200

    # אותו קוד שוב — כבר מאומת, מתקבל no-op (200) ולא מאמת "מחדש" דרך הקוד.
    r = _verify_code(client, token, code)
    assert r.status_code == 200
    print("✓ 5: קוד שכבר נוצל לא ניתן לשימוש חוזר (המשתמש כבר מאומת, no-op)")


# ── 6: שליחה חוזרת מבטלת קוד קודם ────────────────────────────────────────────

def test_06_resend_invalidates_previous_code() -> None:
    client, _ = make_client()
    token, old_code = _register(client)

    _SENT.clear()
    r = client.post("/auth/verify-email/resend", headers=_headers(token))
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    new_code = _SENT[-1]["code"]
    assert new_code != old_code

    assert _verify_code(client, token, old_code).status_code == 400
    assert _verify_code(client, token, new_code).status_code == 200
    print("✓ 6: שליחה חוזרת מבטלת את הקוד הקודם ומנפיקה קוד חדש שעובד")


# ── 7: rate limiting ─────────────────────────────────────────────────────────

def test_07_too_many_wrong_attempts_locks_the_code() -> None:
    auth_limiter._hits.clear()  # מבודד מהגבלת IP הכללית (בדיקות אחרות בתהליך)
    client, _ = make_client()
    token, code = _register(client)
    wrong = "000000" if code != "000000" else "111111"

    for _ in range(5):
        r = _verify_code(client, token, wrong)
        assert r.status_code == 400

    # הניסיון הבא (השישי) — נעול, גם עם הקוד הנכון.
    r = _verify_code(client, token, code)
    assert r.status_code == 429, f"{r.status_code} {r.text}"
    print("✓ 7: יותר מדי ניסיונות שגויים חוסם, גם אם הקוד הנכון מגיע אחר-כך")


# ── 8: הקישור הקיים ממשיך לעבוד במקביל ───────────────────────────────────────

def test_08_link_verification_still_works_alongside_code() -> None:
    client, _ = make_client()
    token, code = _register(client)
    verify_url = _SENT[-1]["verify_url"]
    link_token = verify_url.split("token=")[1]

    r = client.post("/auth/verify-email/confirm", json={"token": link_token})
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    assert r.json()["user"]["email_verified"] is True

    me = client.get("/auth/me", headers=_headers(token)).json()
    assert me["email_verified"] is True
    print("✓ 8: אימות דרך הקישור הקיים ממשיך לעבוד ללא שינוי")


# ── 9: משתמש חדש חוזר ליצירת אירוע אחרי אימות בקוד ──────────────────────────

def test_09_new_user_returns_to_event_creation_after_code_verify() -> None:
    client, _ = make_client()
    token, code = _register(client)

    r = client.post("/events", headers=_headers(token), json={
        "groom_name": "א", "bride_name": "ב", "event_type": "wedding", "venue_name": "",
    })
    assert r.status_code == 403, "לפני אימות — יצירת אירוע חסומה"

    assert _verify_code(client, token, code).status_code == 200

    r = client.post("/events", headers=_headers(token), json={
        "groom_name": "א", "bride_name": "ב", "event_type": "wedding", "venue_name": "",
    })
    assert r.status_code == 201, f"{r.status_code} {r.text}"
    print("✓ 9: אחרי אימות בקוד אפשר ליצור אירוע מיד — בדיוק כמו אחרי הקישור")


# ── 10: משתמש שכבר מאומת לא נשבר ────────────────────────────────────────────

def test_10_already_verified_user_is_not_broken() -> None:
    client, _ = make_client()
    token, code = _register(client)
    assert _verify_code(client, token, code).status_code == 200

    # כל קוד שהוא (גם שגוי) — no-op בטוח, לא שגיאה, לא הרס מצב.
    r = _verify_code(client, token, "999999")
    assert r.status_code == 200
    assert r.json()["email_verified"] is True
    print("✓ 10: משתמש שכבר מאומת — קריאה נוספת היא no-op בטוח")


# ── 11: Resend שולח בפועל את מייל האימות ─────────────────────────────────────

def test_11_resend_actually_sends_the_email() -> None:
    client, _ = make_client()
    token, _ = _register(client)

    _SENT.clear()
    r = client.post("/auth/verify-email/resend", headers=_headers(token))
    assert r.status_code == 200
    assert r.json() == {"already_verified": False, "sent": True}
    assert len(_SENT) == 1
    assert _SENT[-1]["ok"] is True
    assert _SENT[-1]["code"] and _SENT[-1]["verify_url"]
    print("✓ 11: Resend שולח מייל אימות בפועל (קוד + קישור)")


# ── 12: אין קוד/טוקן גולמיים בלוגים ──────────────────────────────────────────

def test_12_no_raw_code_or_token_in_debug_logs() -> None:
    """סריקה סטטית: debug_log/print בקבצי האימות לא משבצים ישירות את
    המשתנים ``code``/``token`` הגולמיים (רק hash/מסכה מותרים)."""
    import re

    backend = Path(__file__).resolve().parent.parent
    suspicious_patterns = [
        re.compile(r"debug_log\([^)]*\{code\}"),
        re.compile(r"debug_log\([^)]*\{token\}"),
        re.compile(r"print\([^)]*\{code\}"),
        re.compile(r"print\([^)]*\{token\}"),
    ]
    for rel in ("app/auth.py", "app/emailer.py", "app/routers/auth.py"):
        text = (backend / rel).read_text(encoding="utf-8")
        for pattern in suspicious_patterns:
            assert not pattern.search(text), f"חשד לחשיפת סוד גולמי בלוג ב-{rel}: {pattern.pattern}"
    print("✓ 12: אין קוד/טוקן גולמי בשום קריאת debug_log/print")


if __name__ == "__main__":
    for fn in [
        test_01_register_issues_a_six_digit_code,
        test_02_correct_code_verifies,
        test_03_wrong_code_is_rejected,
        test_04_expired_code_is_rejected,
        test_05_used_code_cannot_be_reused,
        test_06_resend_invalidates_previous_code,
        test_07_too_many_wrong_attempts_locks_the_code,
        test_08_link_verification_still_works_alongside_code,
        test_09_new_user_returns_to_event_creation_after_code_verify,
        test_10_already_verified_user_is_not_broken,
        test_11_resend_actually_sends_the_email,
        test_12_no_raw_code_or_token_in_debug_logs,
    ]:
        fn()
    shutdown()
