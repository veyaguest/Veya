"""שלב 2 (2026-10-12): מצב ``meta_test`` ורשימת נמענים מורשים.

הכלל: במצב ``meta_test`` הודעה יוצאת ל-Meta **רק** לטלפון שב-
``WHATSAPP_TEST_RECIPIENTS``. כל נמען אחר נחסם לפני שמשהו יוצא — ובלי שורה
במסד, כך שגם הפעלה בטעות מול מסד הייצור לא מגיעה לאורחים ולא משנה את נתוניהם.

מכסה:
A. קריאת ההגדרות — מצב חסר/ריק/שגוי → mock; רשימת נמענים בכל פורמט, רשומות
   פגומות, רשימה חסרה → הכול חסום.
B. השומר עצמו (``TestRecipientGuard``) ו-``outbound.send_batch``.
C. כל מסלולי השליחה: המשימה המתוזמנת, השליחה מהתור, שליחה ידנית (הודעת
   דחייה), שליחת הזמנות, "שליחת בדיקה" לטלפון של בעלי האירוע, ושני
   ה-endpoints הישנים (חסומים בכל מצב שאינו mock).

ספק Meta מוחלף כאן בזיוף שרק סופר קריאות — שום בדיקה לא יוצאת לרשת.

הרצה: ``venv/bin/python tests/test_whatsapp_meta_test_mode.py`` (עצמאי, או pytest).
"""
from __future__ import annotations

import os
import secrets
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402
from tests.test_whatsapp_safety import _db, _engine, _event, _guest, _phone  # noqa: E402

OWNER_PHONE = "0501234567"  # הטלפון שאיתו נרשם כל משתמש בדיקה (tests/e2e_seating.register)


class _FakeMeta:
    """במקום ``messaging.MetaProvider``: לא יוצא לרשת, רק רושם למי "נשלח"."""

    name = "meta"
    external = True
    calls: list[str] = []

    def send_invitation(self, phone, text):  # noqa: ARG002
        from app import messaging

        _FakeMeta.calls.append(phone)
        return messaging.SendResult(
            ok=True, provider="meta", status="sent",
            provider_message_id=f"wamid-fake-{secrets.token_hex(6)}",
        )


@contextmanager
def _whatsapp(mode, recipients=None):
    """מגדיר WHATSAPP_MODE / WHATSAPP_TEST_RECIPIENTS ומחליף את ספק Meta בזיוף."""
    from app import messaging

    keys = ("WHATSAPP_MODE", "WHATSAPP_TEST_RECIPIENTS")
    prev = {k: os.environ.get(k) for k in keys}
    real_meta = messaging.MetaProvider
    for k, v in zip(keys, (mode, recipients)):
        # "לא מוגדר" = ריק ולא מחוק — כך שום load_dotenv לא ממלא מהקובץ האמיתי.
        os.environ[k] = "" if v is None else v
    messaging.MetaProvider = _FakeMeta
    _FakeMeta.calls = []
    try:
        yield _FakeMeta.calls
    finally:
        messaging.MetaProvider = real_meta
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _intl(local: str) -> str:
    return "+972 " + local[1:3] + "-" + local[3:]


# ============================================================================
# A. קריאת ההגדרות
# ============================================================================

def test_mode_missing_empty_or_invalid_is_mock() -> None:
    from app import messaging

    cases = {
        None: "mock", "": "mock", "   ": "mock", "mock": "mock",
        "meta_test": "meta_test", " Meta_Test ": "meta_test",
        "meta": "meta", "live": "meta", "LIVE": "meta",
        "metatest": "mock", "meta-test": "mock", "production": "mock", "true": "mock",
    }
    for raw, expected in cases.items():
        with _whatsapp(raw):
            assert messaging.whatsapp_mode() == expected, (raw, messaging.whatsapp_mode())
            provider = messaging.get_provider()
            if expected == "mock":
                assert isinstance(provider, messaging.MockProvider), raw
    print("✓ A1: מצב חסר/ריק/שגוי → mock; meta_test/meta/live מזוהים (גם באותיות גדולות)")


def test_public_mode_keeps_existing_screens_working() -> None:
    from app import messaging

    for raw, public in (("mock", "mock"), ("live", "live"), ("meta", "live"), ("meta_test", "meta_test")):
        with _whatsapp(raw):
            assert messaging.current_mode() == public, raw
    print("✓ A2: מה שהמסכים מקבלים — mock / meta_test / live (meta נשאר live כמו קודם)")


def test_recipients_parsing() -> None:
    from app import messaging

    with _whatsapp("meta_test", "050-111-2233, +972 52-444-5566;0547778899\n abc , 12345"):
        assert messaging.test_recipients() == frozenset(
            {"0501112233", "0524445566", "0547778899"}
        )
    with _whatsapp("meta_test", None):
        assert messaging.test_recipients() == frozenset()
    with _whatsapp("meta_test", "  ,, ; "):
        assert messaging.test_recipients() == frozenset()
    with _whatsapp("meta_test", "not-a-phone"):
        assert messaging.test_recipients() == frozenset()
    print("✓ A3: רשימת נמענים — כל הפורמטים, פגומים מדולגים, חסרה/ריקה → ריקה")


# ============================================================================
# B. השומר ו-send_batch
# ============================================================================

def test_guard_blocks_before_meta() -> None:
    from app import messaging

    allowed = _phone()
    with _whatsapp("meta_test", allowed) as calls:
        guard = messaging.get_provider()
        assert isinstance(guard, messaging.TestRecipientGuard)
        res = guard.send_invitation(_phone(), "שלום")
        assert not res.ok and res.status == "failed" and res.detail == messaging.TEST_BLOCKED_DETAIL
        assert calls == [], "נמען לא מורשה לא אמור להגיע ל-Meta"
        for bad in ("", "abc", None):
            assert not guard.send_invitation(bad, "x").ok
        assert calls == []
        res = guard.send_invitation(_intl(allowed), "שלום")
        assert res.ok and calls == [_intl(allowed)]
    print("✓ B1: נמען לא מורשה נחסם לפני Meta; מורשה (גם בפורמט +972) עובר")


def test_guard_with_missing_list_blocks_everything() -> None:
    from app import messaging

    for recipients in (None, "", "garbage"):
        with _whatsapp("meta_test", recipients) as calls:
            guard = messaging.get_provider()
            assert not guard.send_invitation(OWNER_PHONE, "x").ok
            assert not guard.send_invitation(_phone(), "x").ok
            assert calls == []
    print("✓ B2: רשימה חסרה/ריקה/פגומה → הכול חסום")


def test_send_batch_blocked_recipients_get_no_rows() -> None:
    from app import models, outbound

    engine = _engine()
    db = Session(engine)
    ev = _event(db)
    allowed = _phone()
    guests = [_guest(db, ev.id, allowed, "מורשה")] + [_guest(db, ev.id, _phone()) for _ in range(3)]
    with _whatsapp("meta_test", allowed) as calls:
        res = outbound.send_batch(db, ev, [
            outbound.OutboundItem(guest=g, phone=g.phone, text="שלום", kind="reminder_1")
            for g in guests
        ])
        db.commit()
    assert (res.sent, res.failed, res.blocked) == (1, 0, 3)
    assert calls == [allowed]
    rows = db.scalars(select(models.Message)).all()
    assert [(r.guest_id, r.status) for r in rows] == [(guests[0].id, "sent")], "לחסומים אין שורה"
    print("✓ B3: send_batch — נמענים חסומים לא נרשמים ולא נשלחים")


# ============================================================================
# C. כל מסלולי השליחה
# ============================================================================

def _event_day_setup(db, allowed_phone):
    from app import models

    ev = _event(db)
    g_ok = _guest(db, ev.id, allowed_phone, "מורשה")
    g_real = _guest(db, ev.id, _phone(), "אורח אמיתי")
    em = models.EventMessage(
        event_id=ev.id, message_type="event_day", content="שלום {{guest_name}}",
        is_active=True, trigger_offset_days=0, target_audience="all",
    )
    db.add(em)
    db.commit()
    return ev, g_ok, g_real


def test_scheduler_sends_only_to_allowed() -> None:
    from app import models, rsvp_scheduler

    db = Session(_engine())
    allowed = _phone()
    ev, g_ok, g_real = _event_day_setup(db, allowed)
    now = datetime(2026, 9, 8, 8, 0)  # יום האירוע, 11:00 בישראל
    with _whatsapp("meta_test", allowed) as calls:
        for _ in range(3):  # שלוש ריצות של המשימה
            rsvp_scheduler.process_event(db, ev, now)
            db.commit()
    assert calls == [allowed], calls
    rows = db.scalars(select(models.Message)).all()
    assert [r.guest_id for r in rows] == [g_ok.id], "לאורח האמיתי אין שורה"
    print("✓ C1: המשימה המתוזמנת — רק לנמען המורשה, פעם אחת, בלי שורה לאורח אמיתי")


def test_scheduler_all_blocked_writes_nothing() -> None:
    """כמו הפעלה בטעות מול מסד הייצור: אף נמען לא ברשימה — שום כתיבה של הודעה
    ושום שורת יומן, גם אחרי כמה ריצות."""
    from app import models, rsvp_scheduler

    db = Session(_engine())
    ev, _, _ = _event_day_setup(db, _phone())
    now = datetime(2026, 9, 8, 8, 0)
    with _whatsapp("meta_test", _phone()) as calls:
        for _ in range(3):
            rsvp_scheduler.process_event(db, ev, now)
            db.commit()
    assert calls == []
    assert db.scalar(select(func.count()).select_from(models.Message)) == 0
    assert db.scalar(
        select(func.count()).select_from(models.AuditLog)
        .where(models.AuditLog.action == "rsvp_track_advance")
    ) == 0
    print("✓ C2: כל הנמענים חסומים — אין הודעות ואין שורות יומן, גם אחרי 3 ריצות")


def test_due_queue_send_only_to_allowed() -> None:
    """השליחה הידנית מהתור (``/communication/due/send``) עוברת דרך אותה
    ``send_due_messages`` — בודקים אותה ישירות, עם החשבון שהיא מחזירה."""
    from app import communication as c

    db = Session(_engine())
    allowed = _phone()
    ev, _, _ = _event_day_setup(db, allowed)
    actions = c.compute_due_messages(db, ev, now=datetime(2026, 9, 8, 8, 0))
    assert len(actions) == 2
    with _whatsapp("meta_test", allowed) as calls:
        result = c.send_due_messages(db, ev, actions)
        db.commit()
    assert calls == [allowed]
    assert (result["sent"], result["failed"], result["blocked"]) == (1, 0, 1)
    print("✓ C3: שליחה מהתור — נשלח 1, נחסם 1")


def test_manual_postponement_send_only_to_allowed() -> None:
    from app import models
    from app.routers import communication as router

    db = Session(_engine())
    ev = _event(db)
    allowed = _phone()
    g_ok = _guest(db, ev.id, allowed, "מורשה")
    _guest(db, ev.id, _phone(), "אורח אמיתי")
    db.add(models.EventMessage(event_id=ev.id, message_type="postponement", title="אירוע נדחה",
                               content="שלום {{guest_name}}, האירוע נדחה", is_active=True,
                               target_audience="all"))
    user = models.User(email=f"u-{secrets.token_hex(4)}@veya.test", password_hash="x")
    db.add(user)
    db.commit()

    class _Req:
        client = None

    real_assert = router._assert_known_type
    router._assert_known_type = lambda *a, **k: None  # הנוהל עצמו נבדק ב-test_postponement
    try:
        with _whatsapp("meta_test", allowed) as calls:
            res = router.manual_send(
                message_type="postponement",
                payload=router.schemas.CommunicationManualSend(audience="all"),
                request=_Req(), db=db, event=ev, user=user,
            )
    finally:
        router._assert_known_type = real_assert
    assert calls == [allowed]
    assert (res.sent, res.failed) == (1, 0)
    assert "נחסמו במצב בדיקה" in (res.detail or "")
    rows = db.scalars(select(models.Message)).all()
    assert [r.guest_id for r in rows] == [g_ok.id]
    print("✓ C4: שליחה ידנית (הודעת דחייה) — רק למורשה, והתשובה אומרת כמה נחסמו")


def _set_invitation_content(api) -> None:
    from app import models

    db = _db()
    try:
        em = db.scalars(select(models.EventMessage).where(
            models.EventMessage.event_id == api.event_id,
            models.EventMessage.message_type == "invitation")).first()
        if em is None:
            em = models.EventMessage(event_id=api.event_id, message_type="invitation",
                                     title="הזמנה", content="", is_active=True)
            db.add(em)
        em.content = "שלום {{guest_name}}"
        db.commit()
    finally:
        db.close()


def _rows_for(event_id, guest_id):
    from app import models

    db = _db()
    try:
        return db.scalars(select(models.Message).where(
            models.Message.event_id == event_id, models.Message.guest_id == guest_id)).all()
    finally:
        db.close()


def test_activate_invitations_only_to_allowed() -> None:
    api, _ = bootstrap()
    allowed = _phone()
    g_ok = api.add_guest("מורשה", allowed)
    g_real = api.add_guest("אורח אמיתי", _phone())
    _set_invitation_content(api)
    with _whatsapp("meta_test", allowed) as calls:
        r = api.client.post("/automation/track/activate", headers=api.headers, json={})
    assert r.status_code == 200, r.text
    assert r.json()["invitations_sent"] == 1 and calls == [allowed]
    assert len(_rows_for(api.event_id, g_ok["id"])) == 1
    assert _rows_for(api.event_id, g_real["id"]) == [], "לאורח האמיתי אין שורה"
    print("✓ C5: שליחת הזמנות — רק למורשה; לאורח אמיתי אין שורה")


def test_owner_test_send_respects_allowlist() -> None:
    api, _ = bootstrap()
    api.add_guest("מוזמן", _phone())
    _set_invitation_content(api)
    url = "/communication/sequence/invitation/test-send"
    with _whatsapp("meta_test", _phone()) as calls:  # הטלפון של בעלי האירוע לא ברשימה
        r = api.client.post(url, headers=api.headers)
        assert r.status_code == 200, r.text
        assert r.json()["sent"] == 0 and r.json()["failed"] == 1 and calls == []
    with _whatsapp("meta_test", OWNER_PHONE) as calls:
        r = api.client.post(url, headers=api.headers)
        assert r.json()["sent"] == 1 and calls == [OWNER_PHONE]
    print("✓ C6: שליחת בדיקה לטלפון של בעלי האירוע — רק כשהוא ברשימה")


def test_legacy_endpoints_blocked_outside_mock() -> None:
    api, _ = bootstrap()
    g = api.add_guest("מוזמן ישן", _phone())
    for mode in ("meta_test", "meta", "live"):
        with _whatsapp(mode, OWNER_PHONE) as calls:
            r1 = api.client.post("/messaging/invitations/send", headers=api.headers,
                                 json={"only_pending": False})
            r2 = api.client.post("/messaging/reminders/send", headers=api.headers)
        assert r1.status_code == 409 and r2.status_code == 409, (mode, r1.text, r2.text)
        assert calls == []
    assert _rows_for(api.event_id, g["id"]) == []
    with _whatsapp(None) as calls:  # mock — ההתנהגות הקיימת נשארת
        r = api.client.post("/messaging/invitations/send", headers=api.headers,
                            json={"only_pending": False})
        assert r.status_code == 200 and r.json()["sent"] == 1 and calls == []
    print("✓ C7: endpoints ישנים — 409 בכל מצב שאינו mock; ב-mock עובדים כמו קודם")


def test_typo_mode_never_reaches_meta() -> None:
    api, _ = bootstrap()
    api.add_guest("מוזמן", _phone())
    _set_invitation_content(api)
    with _whatsapp("meta-test", OWNER_PHONE) as calls:  # שגיאת הקלדה
        r = api.client.post("/automation/track/activate", headers=api.headers, json={})
    assert r.status_code == 200 and calls == [], "מצב שגוי = mock, אף פעם לא Meta"
    print("✓ C8: שגיאת הקלדה במצב → mock, שום דבר לא יוצא ל-Meta")


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
        print()
        print("=== כל בדיקות מצב meta_test עברו ===")
    finally:
        shutdown()
