"""בדיקות מקצה-לקצה לניהול משותף של אירוע (שני חשבונות, אירוע אחד).

מכסה את רשימת הבדיקות שהוגדרה למשימה:
  1-3   הרשמה: בלי שם / בלי טלפון → נחסמת; מלאה → מצליחה.
  4-5   אימות מייל נדרש; משתמש בלי שם/טלפון נדרש להשלים לפני יצירת אירוע.
  6-8   יצירת אירוע, הזמנת בן/בת זוג, ומייל שיצא בפועל.
  9-10  משתמש קיים / משתמש חדש מצטרפים לאותו אירוע דרך ההזמנה.
  11-13 אימייל לא תואם / טוקן שפג / טוקן שכבר נוצל → נחסמים.
  14    אין יצירת אירוע כפול בשום שלב.
  15-17 שני המשתמשים רואים את אותו מידע, ושינוי של אחד נראה לשני.
  18    יומן הפעילות מציג מי ביצע כל שינוי.
  19    משתמש שאינו member חסום לחלוטין.
  20    מחיקת אחד המנהלים לא שוברת את האירוע ולא את השני.

הרצה: ``venv/bin/python -m pytest tests/test_partner_comanagement.py``
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import make_client, shutdown, verify_email  # noqa: E402

from app import emailer  # noqa: E402

# ── עזרי בדיקה ──────────────────────────────────────────────────────────────

# מייל ההזמנה לא נשלח באמת בבדיקות (מצב mock), אבל אנחנו חייבים את הטוקן
# שבתוך הקישור — ב-DB נשמר רק ה-hash שלו, בכוונה. לכן עוטפים את שולח המייל
# ותופסים את הקישור, וכך גם מוודאים שהמייל אכן נשלח (בדיקה 8).
_SENT: list[dict] = []


def _capture_invites():
    original = emailer.send_partner_invite

    def wrapper(**kwargs):
        result = original(**kwargs)
        _SENT.append({**kwargs, "ok": result.ok})
        return result

    emailer.send_partner_invite = wrapper
    return original


_ORIGINAL_SENDER = _capture_invites()


def _headers(token: str, event_id: int | None = None) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    if event_id is not None:
        h["X-Event-Id"] = str(event_id)
    return h


def _new_email() -> str:
    return f"p-{uuid.uuid4().hex[:10]}@veya.test"


def _register(client, email: str | None = None, *, name="ישראל ישראלי",
              phone="0501234567", expect=201):
    email = email or _new_email()
    r = client.post("/auth/register", json={
        "email": email, "password": "Test12345!", "display_name": name,
        "phone": phone, "accepted_terms": True,
    })
    assert r.status_code == expect, f"{r.status_code} {r.text}"
    if r.status_code != 201:
        return email, None
    return email, r.json()["access_token"]


def _make_owner(client, name="אביב מנחם"):
    """משתמש מאומת עם אירוע — נקודת הפתיחה של רוב הבדיקות."""
    email, token = _register(client, name=name)
    verify_email(client, token)
    r = client.post("/events", headers=_headers(token), json={
        "groom_name": "אביב", "bride_name": "דנה",
        "event_type": "wedding", "venue_name": "אולם הבדיקות",
    })
    assert r.status_code == 201, f"{r.status_code} {r.text}"
    return email, token, r.json()["id"]


def _invite(client, token: str, invitee_email: str, expect=201):
    _SENT.clear()
    r = client.post("/partner/invite", headers=_headers(token),
                    json={"email": invitee_email})
    assert r.status_code == expect, f"{r.status_code} {r.text}"
    if r.status_code != 201:
        return None
    url = _SENT[-1]["invite_url"]
    return url.split("token=")[1]


# ── 1-3: ולידציה בהרשמה ─────────────────────────────────────────────────────

def test_01_register_without_name_is_blocked() -> None:
    client, _ = make_client()
    _register(client, name="", expect=422)
    _register(client, name="   ", expect=422)
    print("✓ 1: הרשמה בלי שם נחסמת")


def test_02_register_without_phone_is_blocked() -> None:
    client, _ = make_client()
    _register(client, phone="", expect=422)
    _register(client, phone="123", expect=422)
    print("✓ 2: הרשמה בלי טלפון (או עם טלפון לא תקין) נחסמת")


def test_03_full_register_succeeds() -> None:
    client, _ = make_client()
    _, token = _register(client)
    assert token
    me = client.get("/auth/me", headers=_headers(token)).json()
    assert me["display_name"] == "ישראל ישראלי"
    assert me["phone"] == "0501234567"
    print("✓ 3: הרשמה מלאה מצליחה")


# ── 4-5: אימות מייל והשלמת פרטים ────────────────────────────────────────────

def test_04_new_user_must_verify_email_before_creating_event() -> None:
    client, _ = make_client()
    _, token = _register(client)
    me = client.get("/auth/me", headers=_headers(token)).json()
    assert me["email_verified"] is False, "משתמש חדש אמור להיות לא-מאומת"

    r = client.post("/events", headers=_headers(token), json={
        "groom_name": "א", "bride_name": "ב", "event_type": "wedding",
        "venue_name": "",
    })
    assert r.status_code == 403, f"ציפינו לחסימה, קיבלנו {r.status_code}"
    assert "לאמת" in r.json()["detail"]

    verify_email(client, token)
    r = client.post("/events", headers=_headers(token), json={
        "groom_name": "א", "bride_name": "ב", "event_type": "wedding",
        "venue_name": "",
    })
    assert r.status_code == 201, f"{r.status_code} {r.text}"
    print("✓ 4: משתמש חדש נדרש לאמת מייל לפני יצירת אירוע")


def test_05_existing_user_missing_details_must_complete_first() -> None:
    """משתמש ותיק בלי טלפון (למשל מגוגל) לא נשבר — מתבקש להשלים."""
    from app import models
    from app.database import SessionLocal, set_request_identity
    from app import auth as auth_module

    client, _ = make_client()
    _, token = _register(client)
    verify_email(client, token)

    # מדמים משתמש ותיק: מרוקנים את הטלפון ישירות ב-DB (כמו חשבון שנוצר
    # לפני שהשדה היה חובה).
    user_id = int(auth_module._decode_token(token)["sub"])
    set_request_identity(user_id)
    db = SessionLocal()
    try:
        u = db.get(models.User, user_id)
        u.phone = ""
        db.commit()
    finally:
        db.close()

    me = client.get("/auth/me", headers=_headers(token)).json()
    assert me["profile_complete"] is False

    r = client.post("/events", headers=_headers(token), json={
        "groom_name": "א", "bride_name": "ב", "event_type": "wedding",
        "venue_name": "",
    })
    assert r.status_code == 400 and "להשלים" in r.json()["detail"]

    # אחרי השלמת הפרטים — עובר.
    r = client.patch("/auth/me", headers=_headers(token),
                     json={"display_name": "ישראל ישראלי", "phone": "0521111111"})
    assert r.status_code == 200, r.text
    assert r.json()["profile_complete"] is True
    r = client.post("/events", headers=_headers(token), json={
        "groom_name": "א", "bride_name": "ב", "event_type": "wedding",
        "venue_name": "",
    })
    assert r.status_code == 201
    print("✓ 5: משתמש קיים בלי פרטים נדרש להשלים אותם לפני יצירת אירוע")


# ── 6-8: יצירת אירוע, הזמנה, ומייל ──────────────────────────────────────────

def test_06_07_08_create_event_invite_and_email() -> None:
    client, _ = make_client()
    _, token, event_id = _make_owner(client)

    invitee = _new_email()
    invite_token = _invite(client, token, invitee)
    assert invite_token, "לא התקבל טוקן הזמנה"

    assert len(_SENT) == 1, "מייל ההזמנה לא נשלח"
    sent = _SENT[-1]
    assert sent["to"] == invitee
    assert sent["ok"] is True
    assert "אביב" in sent["inviter_name"]
    assert sent["event_title"] == "החתונה של אביב ודנה"
    print("✓ 6-8: אירוע נוצר, הזמנה נשלחה, ומייל Resend יצא עם התוכן הנכון")


# ── 9: משתמש קיים מצטרף לאותו אירוע ─────────────────────────────────────────

def test_09_existing_user_joins_same_event() -> None:
    client, _ = make_client()
    _, owner_token, event_id = _make_owner(client)

    partner_email, partner_token = _register(client, name="דנה כהן")
    verify_email(client, partner_token)

    invite_token = _invite(client, owner_token, partner_email)

    preview = client.get(f"/partner/invitations/{invite_token}",
                         headers=_headers(partner_token)).json()
    assert preview["state"] == "ready", preview
    assert preview["event_title"] == "החתונה של אביב ודנה"

    r = client.post(f"/partner/invitations/{invite_token}/accept",
                    headers=_headers(partner_token))
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "joined"

    # אותו אירוע בדיוק — לא אירוע חדש (בדיקה 14).
    events = client.get("/events", headers=_headers(partner_token)).json()
    assert len(events) == 1, f"נוצר אירוע כפול: {events}"
    assert events[0]["id"] == event_id
    print("✓ 9 + 14: משתמש קיים הצטרף לאותו אירוע, בלי יצירת אירוע כפול")


# ── 10: משתמש חדש נרשם דרך ההזמנה ───────────────────────────────────────────

def test_10_new_user_registers_through_invitation() -> None:
    client, _ = make_client()
    _, owner_token, event_id = _make_owner(client)

    invitee = _new_email()
    invite_token = _invite(client, owner_token, invitee)

    # לפני התחברות — ההזמנה מוצגת, אבל דורשת כניסה.
    preview = client.get(f"/partner/invitations/{invite_token}").json()
    assert preview["state"] == "needs_login", preview
    assert preview["event_title"] == "החתונה של אביב ודנה"

    # נרשם עכשיו עם אותה כתובת.
    _, new_token = _register(client, invitee, name="דנה חדשה")

    # לפני אימות מייל — חסום.
    r = client.post(f"/partner/invitations/{invite_token}/accept",
                    headers=_headers(new_token))
    assert r.status_code == 403 and "לאמת" in r.json()["detail"]

    verify_email(client, new_token)
    r = client.post(f"/partner/invitations/{invite_token}/accept",
                    headers=_headers(new_token))
    assert r.status_code == 200, r.text

    events = client.get("/events", headers=_headers(new_token)).json()
    assert len(events) == 1 and events[0]["id"] == event_id
    print("✓ 10: משתמש חדש נרשם דרך ההזמנה, אימת מייל, והצטרף לאותו אירוע")


# ── 11-13: חסימות ───────────────────────────────────────────────────────────

def test_11_email_mismatch_is_blocked() -> None:
    client, _ = make_client()
    _, owner_token, event_id = _make_owner(client)
    invite_token = _invite(client, owner_token, _new_email())

    _, other_token = _register(client, name="זר גמור")
    verify_email(client, other_token)

    preview = client.get(f"/partner/invitations/{invite_token}",
                         headers=_headers(other_token)).json()
    assert preview["state"] == "wrong_account", preview

    r = client.post(f"/partner/invitations/{invite_token}/accept",
                    headers=_headers(other_token))
    assert r.status_code == 403, f"אימייל לא תואם לא נחסם: {r.status_code}"

    events = client.get("/events", headers=_headers(other_token)).json()
    assert all(e["id"] != event_id for e in events), "זר קיבל גישה לאירוע!"
    print("✓ 11: אימייל שאינו תואם את ההזמנה — חסום")


def test_12_expired_token_is_blocked() -> None:
    from app import models
    from app.database import SessionLocal

    client, _ = make_client()
    _, owner_token, _ = _make_owner(client)
    invitee, invitee_token = _register(client, name="דנה מאחרת")
    verify_email(client, invitee_token)
    invite_token = _invite(client, owner_token, invitee)

    # מזיזים את התוקף לאחור — כמו הזמנה שנשלחה לפני שבועיים.
    db = SessionLocal()
    try:
        inv = db.query(models.EventInvitation).order_by(
            models.EventInvitation.id.desc()).first()
        inv.expires_at = datetime.utcnow() - timedelta(days=1)
        db.commit()
    finally:
        db.close()

    preview = client.get(f"/partner/invitations/{invite_token}",
                         headers=_headers(invitee_token)).json()
    assert preview["state"] == "expired", preview
    r = client.post(f"/partner/invitations/{invite_token}/accept",
                    headers=_headers(invitee_token))
    assert r.status_code == 403
    print("✓ 12: טוקן שפג תוקפו — חסום")


def test_13_used_token_cannot_be_reused() -> None:
    client, _ = make_client()
    _, owner_token, _ = _make_owner(client)
    invitee, invitee_token = _register(client, name="דנה כהן")
    verify_email(client, invitee_token)
    invite_token = _invite(client, owner_token, invitee)

    assert client.post(f"/partner/invitations/{invite_token}/accept",
                       headers=_headers(invitee_token)).status_code == 200

    # מישהו אחר עם אותו קישור — נחסם (ההזמנה כבר מומשה).
    _, third_token = _register(client, name="שלישי")
    verify_email(client, third_token)
    preview = client.get(f"/partner/invitations/{invite_token}",
                         headers=_headers(third_token)).json()
    assert preview["state"] == "used", preview
    r = client.post(f"/partner/invitations/{invite_token}/accept",
                    headers=_headers(third_token))
    assert r.status_code == 403
    print("✓ 13: טוקן שכבר נוצל — לא ניתן לשימוש חוזר")


# ── 15-18: מידע משותף ויומן פעילות ──────────────────────────────────────────

def _join(client, owner_token, name="דנה כהן"):
    """מחזיר (partner_token) אחרי הצטרפות מלאה לאירוע של owner_token."""
    email, token = _register(client, name=name)
    verify_email(client, token)
    invite_token = _invite(client, owner_token, email)
    r = client.post(f"/partner/invitations/{invite_token}/accept",
                    headers=_headers(token))
    assert r.status_code == 200, r.text
    return token


def test_15_16_17_both_see_and_change_the_same_data() -> None:
    client, _ = make_client()
    _, owner_token, event_id = _make_owner(client)
    partner_token = _join(client, owner_token)

    # A מוסיף מוזמן → B רואה אותו.
    r = client.post("/guests", headers=_headers(owner_token, event_id),
                    json={"full_name": "משפחת כהן", "phone": "0509999999",
                          "party_size": 2})
    assert r.status_code == 201, r.text
    guest_id = r.json()["id"]

    guests_b = client.get("/guests", headers=_headers(partner_token, event_id)).json()["items"]
    assert any(g["id"] == guest_id for g in guests_b), "B לא רואה את מה ש-A הוסיף"

    # B משנה כמות → A רואה.
    r = client.patch(f"/guests/{guest_id}",
                     headers=_headers(partner_token, event_id),
                     json={"party_size": 4})
    assert r.status_code == 200, r.text
    guests_a = client.get("/guests", headers=_headers(owner_token, event_id)).json()["items"]
    changed = next(g for g in guests_a if g["id"] == guest_id)
    assert changed["party_size"] == 4, "A לא רואה את השינוי של B"

    # B עורך גם את פרטי האירוע עצמם (פעולה ששמורה ל"בעלים") — הוא מנהל שווה.
    r = client.patch("/event", headers=_headers(partner_token, event_id),
                     json={"venue_name": "אולם חדש"})
    assert r.status_code == 200, f"בן/בת זוג נחסמו מעריכת האירוע: {r.text}"
    ev_a = client.get("/event", headers=_headers(owner_token, event_id)).json()
    assert ev_a["venue_name"] == "אולם חדש"

    print("✓ 15-17: שני המנהלים רואים ומשנים בדיוק את אותו מידע")


def test_18_activity_log_shows_who_did_what() -> None:
    client, _ = make_client()
    _, owner_token, event_id = _make_owner(client)
    partner_token = _join(client, owner_token, name="דנה כהן")

    r = client.post("/guests", headers=_headers(owner_token, event_id),
                    json={"full_name": "משפחת לוי", "phone": "0508888888",
                          "party_size": 2})
    guest_id = r.json()["id"]

    # דנה משנה כמות ומשבצת לשולחן.
    client.patch(f"/guests/{guest_id}", headers=_headers(partner_token, event_id),
                 json={"party_size": 4})
    client.post("/seating/assign", headers=_headers(partner_token, event_id),
                json={"guest_id": guest_id, "table_number": 12})

    log = client.get("/event/audit", headers=_headers(owner_token, event_id)).json()
    actions = {row["action"]: row for row in log}

    assert "guest_party_size_update" in actions, [r["action"] for r in log]
    size_row = actions["guest_party_size_update"]
    assert size_row["actor_name"] == "דנה כהן", size_row
    assert "מ-2 ל-4" in size_row["detail"], size_row["detail"]

    assert "seating_assign" in actions, [r["action"] for r in log]
    seat_row = actions["seating_assign"]
    assert seat_row["actor_name"] == "דנה כהן"
    assert "שולחן 12" in seat_row["detail"], seat_row["detail"]

    assert "partner_joined" in actions

    # שני המנהלים רואים את אותו יומן בדיוק.
    log_b = client.get("/event/audit", headers=_headers(partner_token, event_id)).json()
    assert [r["id"] for r in log_b] == [r["id"] for r in log]
    print("✓ 18: יומן הפעילות מציג מי ביצע כל שינוי, ושניהם רואים אותו יומן")


# ── 19: מי שאינו חבר — חסום ─────────────────────────────────────────────────

def test_19_non_member_is_blocked_everywhere() -> None:
    client, _ = make_client()
    _, owner_token, event_id = _make_owner(client)
    client.post("/guests", headers=_headers(owner_token, event_id),
                json={"full_name": "סודי", "phone": "0507777777"})

    _, outsider_token = _register(client, name="זר")
    verify_email(client, outsider_token)

    for method, path, body in [
        ("get", "/guests", None),
        ("get", "/event", None),
        ("get", "/event/audit", None),
        ("get", "/hall", None),
        ("patch", "/event", {"venue_name": "פריצה"}),
        ("post", "/guests", {"full_name": "פריצה", "phone": "0501111111"}),
    ]:
        r = getattr(client, method)(
            path, headers=_headers(outsider_token, event_id),
            **({"json": body} if body else {}),
        )
        assert r.status_code in (403, 404), (
            f"{method.upper()} {path} החזיר {r.status_code} לזר — דליפת מידע!"
        )
    print("✓ 19: משתמש שאינו חבר באירוע חסום בקריאה ובכתיבה")


# ── 20: מחיקת אחד המנהלים ───────────────────────────────────────────────────

def test_20_deleting_one_manager_keeps_event_alive() -> None:
    client, _ = make_client()
    _, owner_token, event_id = _make_owner(client)
    partner_token = _join(client, owner_token, name="דנה כהן")

    client.post("/guests", headers=_headers(owner_token, event_id),
                json={"full_name": "משפחת כהן", "phone": "0506666666",
                      "party_size": 3})

    # הבעלים מוחק את החשבון שלו.
    r = client.delete("/auth/me", headers=_headers(owner_token))
    assert r.status_code == 204, r.text

    # האירוע והמוזמנים שרדו, והשותפה עדיין מנהלת אותם.
    events = client.get("/events", headers=_headers(partner_token)).json()
    assert len(events) == 1 and events[0]["id"] == event_id, (
        f"האירוע נעלם אחרי מחיקת אחד המנהלים: {events}"
    )
    guests = client.get("/guests", headers=_headers(partner_token, event_id)).json()["items"]
    assert any(g["full_name"] == "משפחת כהן" for g in guests), "המוזמנים נמחקו"

    # והיא עדיין יכולה לערוך — הבעלות עברה אליה.
    r = client.patch("/event", headers=_headers(partner_token, event_id),
                     json={"venue_name": "אולם ההמשך"})
    assert r.status_code == 200, r.text

    overview = client.get("/partner/overview", headers=_headers(partner_token)).json()
    assert len(overview["managers"]) == 1
    assert overview["managers"][0]["display_name"] == "דנה כהן"
    assert overview["can_invite_partner"] is True
    print("✓ 20: מחיקת אחד המנהלים לא שוברת את האירוע ולא את המנהל/ת השני/ה")


def test_21_cannot_create_second_event() -> None:
    client, _ = make_client()
    _, token, _ = _make_owner(client)
    r = client.post("/events", headers=_headers(token), json={
        "groom_name": "שני", "bride_name": "נוסף", "event_type": "wedding",
        "venue_name": "",
    })
    assert r.status_code == 409, f"נוצר אירוע שני! {r.status_code}"

    # וגם מי שהצטרף כבן/בת זוג לא יכול לפתוח אירוע משלו.
    partner_token = _join(client, token)
    r = client.post("/events", headers=_headers(partner_token), json={
        "groom_name": "של השותף", "bride_name": "", "event_type": "wedding",
        "venue_name": "",
    })
    assert r.status_code == 409, f"בן/בת זוג יצרו אירוע נוסף! {r.status_code}"
    print("✓ אירוע אחד למשתמש — נאכף לבעלים ולבן/בת הזוג כאחד")


if __name__ == "__main__":
    for fn in [
        test_01_register_without_name_is_blocked,
        test_02_register_without_phone_is_blocked,
        test_03_full_register_succeeds,
        test_04_new_user_must_verify_email_before_creating_event,
        test_05_existing_user_missing_details_must_complete_first,
        test_06_07_08_create_event_invite_and_email,
        test_09_existing_user_joins_same_event,
        test_10_new_user_registers_through_invitation,
        test_11_email_mismatch_is_blocked,
        test_12_expired_token_is_blocked,
        test_13_used_token_cannot_be_reused,
        test_15_16_17_both_see_and_change_the_same_data,
        test_18_activity_log_shows_who_did_what,
        test_19_non_member_is_blocked_everywhere,
        test_20_deleting_one_manager_keeps_event_alive,
        test_21_cannot_create_second_event,
    ]:
        fn()
    shutdown()
    print("\n=== כל בדיקות הניהול המשותף עברו ===")
