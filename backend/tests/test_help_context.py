"""עזרה בתוך VEYA — שלב 3: ה-context שהשרת נותן לעזרה.

מה נבדק (HELP_CENTER_PLAN.md שלב 3 + החלטות המייסד 2026-09-29):
  1. פיצ'ר כבוי → הנתיבים לא קיימים (404). אין שינוי התנהגות.
  2. הרשאות: בעלים ובן/בת זוג בלבד. מפיק, אולם, זר, אדמין עם הטוקן שלו → 404;
     טלפן → 403. החלפת X-Event-Id לאירוע אחר → 404.
  3. כל מסך מקבל **בדיוק** את רשימת העובדות שלו — לא יותר ולא פחות.
     כל בדיקת מוזמן — בדיוק את העובדות שלה.
  4. אין מידע אישי: אף תשובה לא כוללת שם או טלפון של מוזמן (חוץ מבחירת
     מוזמן — מזהה + שם בלבד, עד 8, רק עם חיפוש), ואין שדות מוזמן מעבר לבדיקה.
  5. ערכים אמיתיים: זהים למה שהמסכים הקיימים מציגים (stats, preview, timeline).
  6. קריאה בלבד: אף שורה במסד לא נוספת או משתנה.
  7. בלי שירות חיצוני: כל קריאת רשת חסומה — והנתיבים עדיין עובדים.
  8. לא ידוע → null (לא ניחוש).

הרצה: ``venv/bin/python -m pytest tests/test_help_context.py``
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import make_client, verify_email  # noqa: E402

from app import help_context, messaging  # noqa: E402

# שמות וטלפונים מובחנים — כדי לחפש אותם בכל תשובה ולוודא שלא דלפו.
SECRET_GUESTS = [
    ("זהבית סודית", "0527770011"),
    ("אלמוג נסתר", "0527770022"),
    ("ירדן חסוי", "0527770033"),
]
BAD_PHONE_NAME = "שקד בלי מספר"


def _h(token: str, event_id: int | None = None) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    if event_id is not None:
        h["X-Event-Id"] = str(event_id)
    return h


def _register(client, name: str = "ישראל ישראלי") -> tuple[str, str]:
    email = f"hc-{uuid.uuid4().hex[:10]}@veya.test"
    r = client.post("/auth/register", json={
        "email": email, "password": "Test12345!", "display_name": name,
        "phone": "0501234567", "accepted_terms": True,
    })
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    verify_email(client, token)
    return email, token


def _uid(token: str) -> int:
    from app import auth as auth_module

    return int(auth_module._decode_token(token)["sub"])


def _db(fn):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        out = fn(db)
        db.commit()
        return out
    finally:
        db.close()


def _enable_help(event_id: int) -> None:
    from app import features, models

    _db(lambda db: db.add(models.FeatureRule(
        feature_key="help_center", scope_type="event", scope_id=event_id, enabled=True,
    )))
    features.invalidate()


def _add_bad_phone_guest(db, event_id: int) -> int:
    from app import models

    g = models.Guest(event_id=event_id, full_name=BAD_PHONE_NAME, phone="12")
    db.add(g)
    db.flush()
    return g.id


def _setup(client, *, help_on: bool = True) -> dict:
    """בעלים + אירוע + מוזמנים (כולל אחד בלי מספר תקין)."""
    _, token = _register(client, "אביב מנחם")
    r = client.post("/events", headers=_h(token), json={
        "groom_name": "אביב", "bride_name": "דנה", "event_type": "wedding", "venue_name": "אולם",
    })
    assert r.status_code == 201, r.text
    event_id = r.json()["id"]
    guest_ids = []
    for name, phone in SECRET_GUESTS:
        g = client.post("/guests", headers=_h(token, event_id), json={"full_name": name, "phone": phone})
        assert g.status_code == 201, g.text
        guest_ids.append(g.json()["id"])
    # מוזמן בלי מספר תקין — ה-API לא מאפשר ליצור כזה (דורש מספר תקין), הוא
    # מגיע רק מנתונים ישנים. מדמים את זה ישירות במסד.
    bad_id = _db(lambda db: _add_bad_phone_guest(db, event_id))
    if help_on:
        _enable_help(event_id)
    return {"token": token, "event_id": event_id, "guest_ids": guest_ids, "bad_id": bad_id}


def _set_invitation_text(client, s: dict) -> None:
    """נוסח הזמנה — כמו שבעלי האירוע בוחרים לפני שליחה. בלי נוסח השליחה מדלגת
    על כולם (ומציגה אותם כ"בלי טלפון" — באג ידוע שלא מתוקן במסגרת העזרה)."""
    r = client.put("/communication/sequence/invitation", headers=_h(s["token"], s["event_id"]),
                   json={"content": "היי {{guest_name}}, אנחנו מתחתנים ומזמינים אתכם"})
    assert r.status_code == 200, r.text


def _three_endpoints(client, token: str, event_id: int, guest_id: int) -> list[int]:
    """הסטטוס של שלושת הנתיבים לאותו משתמש/אירוע/מוזמן."""
    h = _h(token, event_id)
    return [
        client.get("/help/context/guests", headers=h).status_code,
        client.get("/help/guest-options?q=סוד", headers=h).status_code,
        client.get(f"/help/guest-check/invite-not-received/{guest_id}", headers=h).status_code,
    ]


def _all_responses(client, s: dict) -> list[str]:
    """כל מה שהעזרה יכולה לקבל על האירוע, כטקסט — לחיפוש דליפות."""
    out = []
    for screen in help_context.SCREENS:
        r = client.get(f"/help/context/{screen}", headers=_h(s["token"], s["event_id"]))
        assert r.status_code == 200, r.text
        out.append(r.text)
    for check in help_context.GUEST_CHECKS:
        for gid in [*s["guest_ids"], s["bad_id"]]:
            r = client.get(f"/help/guest-check/{check}/{gid}", headers=_h(s["token"], s["event_id"]))
            assert r.status_code == 200, r.text
            out.append(r.text)
    return out


# ── 1. פיצ'ר כבוי ──────────────────────────────────────────────────────────

def test_flag_off_means_no_help_endpoints() -> None:
    client, _ = make_client()
    s = _setup(client, help_on=False)
    assert _three_endpoints(client, s["token"], s["event_id"], s["guest_ids"][0]) == [404, 404, 404]


def test_flag_off_after_on_closes_again() -> None:
    from app import features, models

    client, _ = make_client()
    s = _setup(client)
    assert _three_endpoints(client, s["token"], s["event_id"], s["guest_ids"][0]) == [200, 200, 200]
    # מכבים לאירוע (כלל לאירוע גובר) → הכול נסגר מיד.
    def turn_off(db):
        rule = db.query(models.FeatureRule).filter_by(
            feature_key="help_center", scope_type="event", scope_id=s["event_id"]).one()
        rule.enabled = False
    _db(turn_off)
    features.invalidate()
    assert _three_endpoints(client, s["token"], s["event_id"], s["guest_ids"][0]) == [404, 404, 404]


# ── 2. הרשאות ─────────────────────────────────────────────────────────────

def test_owner_and_partner_only() -> None:
    from app import emailer, models

    client, _ = make_client()
    s = _setup(client)
    gid = s["guest_ids"][0]
    assert _three_endpoints(client, s["token"], s["event_id"], gid) == [200, 200, 200]

    # בן/בת זוג — כמו הבעלים.
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
    assert _three_endpoints(client, partner_token, s["event_id"], gid) == [200, 200, 200]

    # מפיק ואולם (חברי-אירוע, גם עם הרשאות רחבות) — לא.
    for role, perms in (
        ("planner", ["view_guests", "edit_guests", "manage_seating", "send_messages", "view_reports"]),
        ("venue", ["view_event", "view_seating", "edit_seating", "manage_venue_data"]),
    ):
        _, member_token = _register(client, role)
        member_id = _uid(member_token)
        _db(lambda db, mid=member_id, r=role, p=perms: db.add(models.EventMember(
            event_id=s["event_id"], user_id=mid, role=r, permissions=p, status="active",
        )))
        assert _three_endpoints(client, member_token, s["event_id"], gid) == [404, 404, 404], role

    # זר — לא (ולא נחשף שהאירוע קיים).
    _, stranger = _register(client, "זר")
    assert _three_endpoints(client, stranger, s["event_id"], gid) == [404, 404, 404]

    # אדמין עם הטוקן שלו — לא (בתמיכה הוא נכנס כבעל/ת האירוע).
    _, admin_token = _register(client, "אדמין")
    admin_id = _uid(admin_token)
    _db(lambda db: setattr(db.get(models.User, admin_id), "is_admin", True))
    assert _three_endpoints(client, admin_token, s["event_id"], gid) == [404, 404, 404]

    # טלפן — חסום כבר ב-EventAccess.
    _, agent_token = _register(client, "טלפן")
    agent_id = _uid(agent_token)
    _db(lambda db: setattr(db.get(models.User, agent_id), "account_type", "phone_agent"))
    assert _three_endpoints(client, agent_token, s["event_id"], gid) == [403, 403, 403]


def test_cannot_reach_another_event_by_changing_event_id() -> None:
    client, _ = make_client()
    a = _setup(client)
    b = _setup(client)
    # בעלי A עם X-Event-Id של B — כאילו B לא קיים.
    assert _three_endpoints(client, a["token"], b["event_id"], b["guest_ids"][0]) == [404, 404, 404]
    # ומוזמן של B לא נבדק גם דרך האירוע של A.
    h = _h(a["token"], a["event_id"])
    for check in help_context.GUEST_CHECKS:
        assert client.get(f"/help/guest-check/{check}/{b['guest_ids'][0]}", headers=h).status_code == 404
        assert client.get(f"/help/guest-check/{check}/{b['bad_id']}", headers=h).status_code == 404
    # מזהה שלא קיים בכלל — אותה תשובה.
    assert client.get("/help/guest-check/invite-not-received/99999999", headers=h).status_code == 404


def test_unknown_screen_or_check_is_404() -> None:
    client, _ = make_client()
    s = _setup(client)
    h = _h(s["token"], s["event_id"])
    assert client.get("/help/context/everything", headers=h).status_code == 404
    assert client.get("/help/context/all", headers=h).status_code == 404
    assert client.get(f"/help/guest-check/all-details/{s['guest_ids'][0]}", headers=h).status_code == 404


# ── 3. בדיוק הרשימה שהוגדרה ───────────────────────────────────────────────

def test_each_screen_gets_exactly_its_facts() -> None:
    client, _ = make_client()
    s = _setup(client)
    for screen, names in help_context.SCREENS.items():
        body = client.get(f"/help/context/{screen}", headers=_h(s["token"], s["event_id"])).json()
        assert set(body) == {"screen", "facts"}, body
        assert sorted(body["facts"]) == sorted(names), f"{screen}: {sorted(body['facts'])} != {sorted(names)}"
        # ערכים פשוטים בלבד — בלי רשימות/אובייקטים שיכולים להכיל פרטים.
        for k, v in body["facts"].items():
            assert v is None or isinstance(v, (bool, int, str)), (screen, k, v)


def test_each_guest_check_gets_exactly_its_facts() -> None:
    client, _ = make_client()
    s = _setup(client)
    personal = {"full_name", "phone", "name", "notes_raw", "seating_notes", "guest_note", "guest_token"}
    for check, names in help_context.GUEST_CHECKS.items():
        r = client.get(f"/help/guest-check/{check}/{s['guest_ids'][0]}", headers=_h(s["token"], s["event_id"]))
        body = r.json()
        assert set(body) == {"check", "facts"}, body
        assert sorted(body["facts"]) == sorted(names), check
        assert not personal & set(body["facts"])


# ── 4. בלי מידע אישי ──────────────────────────────────────────────────────

def test_no_names_or_phones_leak() -> None:
    client, _ = make_client()
    s = _setup(client)
    blob = "\n".join(_all_responses(client, s))
    for name, phone in SECRET_GUESTS:
        assert name not in blob, f"שם דלף: {name}"
        assert phone not in blob and phone[1:] not in blob, f"טלפון דלף: {phone}"
    assert BAD_PHONE_NAME not in blob
    # גם פרטי האירוע עצמו (שמות בעלי האירוע, המקום) אינם חלק מה-context.
    for secret in ("אביב", "דנה", "אולם"):
        assert secret not in blob, f"פרט אירוע דלף: {secret}"


def test_guest_options_returns_only_id_and_name() -> None:
    client, _ = make_client()
    s = _setup(client)
    h = _h(s["token"], s["event_id"])
    r = client.get("/help/guest-options?q=סוד", headers=h)
    assert r.status_code == 200
    assert r.json() == [{"id": s["guest_ids"][0], "name": "זהבית סודית"}]
    assert "0527770011" not in r.text
    assert r.headers.get("cache-control") == "no-store"
    # רק מהאירוע הזה.
    other = _setup(client)
    assert client.get("/help/guest-options?q=סוד", headers=_h(other["token"], other["event_id"])).json() == [
        {"id": other["guest_ids"][0], "name": "זהבית סודית"}
    ]


def test_guest_options_cannot_dump_the_whole_list() -> None:
    client, _ = make_client()
    s = _setup(client)
    h = _h(s["token"], s["event_id"])
    for i in range(12):
        assert client.post("/guests", headers=h, json={"full_name": f"משפחת רבים {i}", "phone": f"05277701{i:02d}"}).status_code == 201
    # בלי חיפוש / חיפוש של תו אחד / רווחים — נדחה.
    assert client.get("/help/guest-options", headers=h).status_code == 422
    assert client.get("/help/guest-options?q=מ", headers=h).status_code == 422
    assert client.get("/help/guest-options?q=%20%20", headers=h).json() == []
    # חיפוש רחב → עד 8, לא כולם.
    assert len(client.get("/help/guest-options?q=רבים", headers=h).json()) == help_context.GUEST_OPTIONS_LIMIT
    # תווים כלליים של SQL (% / _) הם טקסט רגיל, לא "הכול".
    assert client.get("/help/guest-options?q=%25%25", headers=h).json() == []
    assert client.get("/help/guest-options?q=__", headers=h).json() == []


# ── 5. ערכים אמיתיים, כמו במסכים הקיימים; לא ידוע = null ─────────────────

def test_values_match_existing_screens_and_unknown_is_null() -> None:
    client, _ = make_client()
    s = _setup(client)
    h = _h(s["token"], s["event_id"])
    ctx: dict = {}
    for screen in help_context.SCREENS:
        ctx.update(client.get(f"/help/context/{screen}", headers=h).json()["facts"])
    stats = client.get("/stats", headers=h).json()
    preview = client.get("/automation/track/preview", headers=h).json()
    timeline = client.get("/automation/timeline", headers=h).json()

    assert ctx["guests.bad_phone"] == stats["bad_phone_guests"] == 1
    assert ctx["guests.total"] == stats["total_guests"] == 4
    assert ctx["guests.confirmed"] == stats["confirmed"]
    assert ctx["invites.sent"] == stats["invitations_sent"] == 0
    assert ctx["invites.not_yet"] == preview["not_yet_sent"] == 3
    assert ctx["rsvp.phase"] == timeline["track_phase"]
    assert ctx["messaging.mode"] == messaging.current_mode()
    assert ctx["event.has_date"] is False
    assert ctx["event.commit_chosen"] is False
    assert ctx["seating.undo_available"] is False
    assert ctx["event.postpone"] == "none"
    # אין תאריך → אי אפשר לדעת: null, לא 0 ולא ניחוש.
    assert ctx["event.days_to_event"] is None
    assert ctx["rsvp.start_date"] is None
    assert ctx["rsvp.commit_date"] is None
    assert ctx["rsvp.next_date"] is None

    # אין עדיין נוסח להזמנה — העובדה אומרת את זה (העזרה בודקת את זה לפני הטלפונים).
    assert ctx["messaging.invitation_empty"] is True
    _set_invitation_text(client, s)
    assert client.get("/help/context/messages", headers=h).json()["facts"]["messaging.invitation_empty"] is False

    # אחרי שליחת הזמנות (mock) — הספירות זזות בדיוק כמו במסכים.
    assert client.post("/automation/track/activate", headers=h, json={}).status_code == 200
    ctx2 = client.get("/help/context/messages", headers=h).json()["facts"]
    assert ctx2["invites.sent"] == client.get("/stats", headers=h).json()["invitations_sent"] == 3
    assert ctx2["invites.not_yet"] == 0


def test_guest_check_values_and_unknowns() -> None:
    client, _ = make_client()
    s = _setup(client)
    h = _h(s["token"], s["event_id"])
    good, bad = s["guest_ids"][0], s["bad_id"]
    f = client.get(f"/help/guest-check/invite-not-received/{good}", headers=h).json()["facts"]
    assert f["guest.phone"] == "valid" and f["guest.invitation"] == "none"
    f = client.get(f"/help/guest-check/invite-not-received/{bad}", headers=h).json()["facts"]
    assert f["guest.phone"] == "invalid" and f["guest.invitation"] == "none"
    _set_invitation_text(client, s)
    assert client.post("/automation/track/activate", headers=h, json={}).status_code == 200
    f = client.get(f"/help/guest-check/invite-not-received/{good}", headers=h).json()["facts"]
    assert f["guest.invitation"] == "sent"
    # אין מסלול (אין תאריך/מועד סגירה) → אף סבב לא יצא → לא ידוע, לא "false".
    r = client.get(f"/help/guest-check/reminder-not-received/{good}", headers=h).json()["facts"]
    assert r["guest.joined_after_last_round"] is None
    assert r["guest.rsvp"] == "pending"


# ── 6. קריאה בלבד ─────────────────────────────────────────────────────────

def test_help_endpoints_are_read_only() -> None:
    from sqlalchemy import func, select

    from app import models

    client, _ = make_client()
    s = _setup(client)
    tables = [models.Message, models.EventMessage, models.AuditLog, models.Guest, models.Event,
              models.PostponementRequest, models.FeatureRule, models.EventMember]

    def snapshot():
        def read(db):
            counts = {t.__tablename__: db.scalar(select(func.count()).select_from(t)) for t in tables}
            ev = db.get(models.Event, s["event_id"])
            counts["event_row"] = json.dumps({c.name: str(getattr(ev, c.name)) for c in models.Event.__table__.columns})
            guests = db.scalars(select(models.Guest).where(models.Guest.event_id == s["event_id"])).all()
            counts["guest_rows"] = json.dumps(sorted(
                [{c.name: str(getattr(g, c.name)) for c in models.Guest.__table__.columns} for g in guests],
                key=lambda x: x["id"],
            ))
            return counts
        return _db(read)

    before = snapshot()
    _all_responses(client, s)
    client.get("/help/guest-options?q=סוד", headers=_h(s["token"], s["event_id"]))
    assert snapshot() == before, "נתיבי העזרה שינו משהו במסד"


def test_only_get_methods_exist() -> None:
    from app.main import app

    help_routes = [r for r in app.routes if getattr(r, "path", "").startswith("/help")]
    assert len(help_routes) == 3, [r.path for r in help_routes]
    for r in help_routes:
        assert r.methods == {"GET"}, (r.path, r.methods)
    client, _ = make_client()
    s = _setup(client)
    h = _h(s["token"], s["event_id"])
    for method in ("post", "put", "patch", "delete"):
        assert getattr(client, method)("/help/context/guests", headers=h).status_code == 405


# ── 7. בלי שירות חיצוני ───────────────────────────────────────────────────

def test_no_external_calls() -> None:
    """חוסמים את הרשת האמיתית — ה-transport של httpx (שדרכו עוברים Meta,
    Resend ו-Claude) וכל socket. ה-TestClient עצמו עובד בתוך התהליך, בלי רשת."""
    import socket

    import httpx

    client, _ = make_client()
    s = _setup(client)

    def blocked(*_a, **_kw):
        raise AssertionError("קריאת רשת מתוך נתיב עזרה")

    saved = (httpx.HTTPTransport.handle_request, httpx.AsyncHTTPTransport.handle_async_request,
             socket.socket.connect, socket.create_connection)
    httpx.HTTPTransport.handle_request = blocked  # type: ignore[method-assign]
    httpx.AsyncHTTPTransport.handle_async_request = blocked  # type: ignore[method-assign]
    socket.socket.connect = blocked  # type: ignore[method-assign]
    socket.create_connection = blocked  # type: ignore[assignment]
    try:
        _all_responses(client, s)
        assert client.get("/help/guest-options?q=סוד", headers=_h(s["token"], s["event_id"])).status_code == 200
    finally:
        (httpx.HTTPTransport.handle_request, httpx.AsyncHTTPTransport.handle_async_request,
         socket.socket.connect, socket.create_connection) = saved


def test_help_modules_import_no_network_or_ai() -> None:
    root = Path(__file__).resolve().parent.parent / "app"
    for rel in ("help_context.py", "routers/help.py"):
        src = (root / rel).read_text(encoding="utf-8")
        for banned in ("httpx", "requests", "urllib", "anthropic", "openai", "hall_vision", "emailer"):
            assert f"import {banned}" not in src and f"from {banned}" not in src and f"{banned}." not in src, (rel, banned)


# ── 8. ההגדרה עצמה ────────────────────────────────────────────────────────

def test_spec_has_no_personal_fields() -> None:
    names = {n for v in help_context.SCREENS.values() for n in v}
    names |= {n for v in help_context.GUEST_CHECKS.values() for n in v}
    for n in names:
        assert not any(bad in n for bad in ("name", "phone_number", "email", "note", "token", "body", "address")), n
    # עובדות מוזמן — רק בבדיקות מוזמן, אף פעם לא ב-context של מסך.
    for screen, v in help_context.SCREENS.items():
        assert not [n for n in v if n.startswith("guest.")], screen
