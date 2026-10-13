"""שלב הבטיחות לפני חיבור Meta (2026-10-12): שיוך תשובות, מניעת שליחה כפולה,
ספירת ההודעות, ו-webhook חסין לכפילויות ולכשל זמני.

מכסה:
A. שיוך תשובה נכנסת למוזמן (``app/whatsapp_inbound.py``) — רק התאמה חד-משמעית:
   context.id, טלפון יחיד, טלפון משפחתי, אותו טלפון בשני אירועים, מספר לא
   תקין, מספר שהשתנה מאז ההודעה.
B. "רושמים, שולחים, מעדכנים" (``app/outbound.py``) — השורה קיימת ב-DB לפני
   שהספק נקרא; נפילה באמצע לא גורמת לשליחה חוזרת; כשל ספק לא עוצר את המנה.
C. עדכוני מסירה — "נכשלה" לא דורסת "נמסרה"/"נקראה".
D. ה-webhook מקצה לקצה — לוגיקת ה-RSVP הקיימת (חלון, ספירה, יומן), כפילויות,
   כשל DB זמני (500 ואז ניסיון חוזר), הצלחה חלקית, payload לא צפוי.
E. ספירת "הזמנות שנשלחו" במסך התקשורת כוללת נמסרה/נקראה.

הרצה: ``venv/bin/python tests/test_whatsapp_safety.py`` (עצמאי, או pytest).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402

WEBHOOK_URL = "/messaging/webhook"
_SECRET = "test-whatsapp-app-secret-safety"


# ---- עזרים: DB זמני (קובץ, כדי שסשן שני יראה רק מה שעבר commit) ----------

def _engine():
    from app.database import Base

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_engine(f"sqlite:///{tmp.name}")
    Base.metadata.create_all(bind=engine)
    return engine


def _event(db: Session, **kw):
    from app import models

    ev = models.Event(
        groom_name="יואב", bride_name="דנה", event_type="wedding",
        event_date="2026-09-08", rsvp_send_time="10:00", thank_you_send_time="10:00",
        **{"venue_commit_days_before": 2, **kw},
    )
    db.add(ev)
    db.commit()
    return ev


def _guest(db: Session, event_id: int, phone: str, name: str = "מוזמן בדיקה"):
    from app import models

    g = models.Guest(event_id=event_id, full_name=name, phone=phone, side="groom",
                     created_at=datetime(2026, 1, 1))
    db.add(g)
    db.commit()
    return g


def _phone() -> str:
    return "05" + f"{secrets.randbelow(10 ** 8):08d}"


def _intl(local: str) -> str:
    return "972" + local[1:]


def _outbound(db: Session, guest, wamid: str, status: str = "sent"):
    from app import models

    m = models.Message(
        event_id=guest.event_id, guest_id=guest.id, direction="outbound",
        kind="invitation", body="hi", status=status, provider="meta",
        provider_message_id=wamid,
    )
    db.add(m)
    db.commit()
    return m


# ============================================================================
# A. שיוך תשובה נכנסת
# ============================================================================

def test_match_single_phone_any_format() -> None:
    from app import whatsapp_inbound as wi

    db = Session(_engine())
    ev = _event(db)
    local = _phone()
    # מוזמן ישן שנשמר עם מפרידים (לפני שהנרמול נכנס) — עדיין מזוהה.
    dashed = f"{local[:3]}-{local[3:6]}-{local[6:]}"
    g = _guest(db, ev.id, dashed)
    m = wi.match_guest(db, _intl(local))
    assert m.guest is not None and m.guest.id == g.id and m.reason == wi.MATCH_PHONE
    m2 = wi.match_guest(db, "+" + _intl(local))
    assert m2.guest is not None and m2.guest.id == g.id
    print("✓ A1: טלפון יחיד מזוהה — 972/+972 מול 05X, גם עם מפרידים")


def test_match_household_phone_same_event_is_ambiguous_without_context() -> None:
    from app import whatsapp_inbound as wi

    db = Session(_engine())
    ev = _event(db)
    phone = _phone()
    g1 = _guest(db, ev.id, phone, "אבא")
    g2 = _guest(db, ev.id, phone, "אמא")
    m = wi.match_guest(db, _intl(phone))
    assert m.guest is None and m.reason == wi.AMBIGUOUS and m.candidates == 2

    # עם context.id — ההודעה שלנו שנשלחה לאמא — השיוך חד-משמעי.
    _outbound(db, g2, "wamid-household-2")
    m = wi.match_guest(db, _intl(phone), "wamid-household-2")
    assert m.guest is not None and m.guest.id == g2.id and m.reason == wi.MATCH_CONTEXT
    assert g1.id != g2.id
    print("✓ A2: טלפון משפחתי — בלי context עמימות; עם context המוזמן הנכון")


def test_match_same_phone_two_events_is_ambiguous() -> None:
    from app import whatsapp_inbound as wi

    db = Session(_engine())
    ev_a, ev_b = _event(db), _event(db)
    phone = _phone()
    _guest(db, ev_a.id, phone)
    _guest(db, ev_b.id, phone)
    m = wi.match_guest(db, _intl(phone))
    assert m.guest is None and m.reason == wi.AMBIGUOUS
    assert set(m.candidate_event_ids) == {ev_a.id, ev_b.id}
    print("✓ A3: אותו טלפון בשני אירועים — עמימות, בלי לבחור 'הראשון'")


def test_match_not_found_and_invalid() -> None:
    from app import whatsapp_inbound as wi

    db = Session(_engine())
    ev = _event(db)
    _guest(db, ev.id, _phone())
    assert wi.match_guest(db, _intl(_phone())).reason == wi.NOT_FOUND
    for bad in ("14155550100", "", None, "abc", "97212"):
        assert wi.match_guest(db, bad).reason == wi.INVALID_PHONE, bad
    print("✓ A4: מספר שלא נמצא / לא ישראלי / ריק — אין שיוך")


def test_match_context_with_changed_phone_goes_manual() -> None:
    from app import whatsapp_inbound as wi

    db = Session(_engine())
    ev = _event(db)
    old_phone, new_phone = _phone(), _phone()
    g = _guest(db, ev.id, old_phone)
    _outbound(db, g, "wamid-changed")
    g.phone = new_phone
    db.commit()
    # השולח הוא המספר הישן, והוא מגיב להודעה שנשלחה ל-g — אבל ל-g כבר יש
    # מספר אחר. לא מנחשים ולא נופלים לחיפוש לפי טלפון.
    m = wi.match_guest(db, _intl(old_phone), "wamid-changed")
    assert m.guest is None and m.reason == wi.CONTEXT_MISMATCH
    print("✓ A5: מספר המוזמן השתנה מאז ההודעה — טיפול ידני, לא שיוך")


def test_match_unknown_context_falls_back_to_phone() -> None:
    from app import whatsapp_inbound as wi

    db = Session(_engine())
    ev = _event(db)
    phone = _phone()
    g = _guest(db, ev.id, phone)
    m = wi.match_guest(db, _intl(phone), "wamid-from-another-environment")
    assert m.guest is not None and m.guest.id == g.id and m.reason == wi.MATCH_PHONE
    print("✓ A6: context.id לא מוכר — חוזרים לחיפוש לפי טלפון")


# ============================================================================
# B. רושמים, שולחים, מעדכנים
# ============================================================================

class _SpyProvider:
    """ספק "אמיתי" לבדיקה: בכל שליחה בודק מה כבר שמור ב-DB (סשן נפרד)."""

    name = "spy"
    external = True

    def __init__(self, engine, crash_on: int | None = None, raise_on: int | None = None):
        self.engine = engine
        self.calls = 0
        self.crash_on = crash_on
        self.raise_on = raise_on
        self.seen_statuses: list[list[str]] = []

    def send_invitation(self, phone, text):  # noqa: ARG002
        from app import messaging, models

        self.calls += 1
        with Session(self.engine) as other:
            self.seen_statuses.append(
                [m.status for m in other.scalars(select(models.Message).order_by(models.Message.id))]
            )
        if self.crash_on == self.calls:
            raise _ProcessCrash()
        if self.raise_on == self.calls:
            raise RuntimeError("network down")
        return messaging.SendResult(
            ok=True, provider=self.name, status="sent",
            provider_message_id=f"wamid-spy-{secrets.token_hex(6)}",
        )


class _ProcessCrash(BaseException):
    """מדמה נפילת תהליך (לא Exception רגיל — הקוד לא אמור "לבלוע" אותו)."""


def test_rows_are_committed_before_provider_is_called() -> None:
    from app import outbound

    engine = _engine()
    db = Session(engine)
    ev = _event(db)
    guests = [_guest(db, ev.id, _phone()) for _ in range(3)]
    spy = _SpyProvider(engine)
    res = outbound.send_batch(db, ev, [
        outbound.OutboundItem(guest=g, phone=g.phone, text="שלום", kind="reminder_1")
        for g in guests
    ], provider=spy)
    db.commit()
    assert res.sent == 3 and res.failed == 0
    # בקריאה הראשונה לספק — כל שלוש השורות כבר שמורות (commit) כ-pending.
    assert spy.seen_statuses[0] == ["pending", "pending", "pending"], spy.seen_statuses[0]
    # בקריאה השלישית — שתי הראשונות כבר עודכנו ונשמרו.
    assert spy.seen_statuses[2] == ["sent", "sent", "pending"], spy.seen_statuses[2]
    print("✓ B1: כל הודעה רשומה ב-DB לפני הניסיון, ומתעדכנת ונשמרת מיד אחריו")


def test_crash_mid_batch_never_resends() -> None:
    """נפילה אחרי ש-Meta (אולי) קיבלה את ההודעה ולפני שמירת התוצאה: ריצה
    נוספת של המסלול לא שולחת שוב — לא למי שנשלח, ולא למי שבמצב לא ידוע."""
    from app import communication as c
    from app import models, outbound

    engine = _engine()
    db = Session(engine)
    ev = _event(db)
    guests = [_guest(db, ev.id, _phone()) for _ in range(3)]
    em = models.EventMessage(
        event_id=ev.id, message_type="event_day", content="שלום {{guest_name}}",
        is_active=True, trigger_offset_days=0, target_audience="all",
    )
    db.add(em)
    db.commit()
    now = datetime(2026, 9, 8, 8, 0)  # יום האירוע, 11:00 בישראל
    actions = c.compute_due_messages(db, ev, now=now)
    assert len(actions) == 3

    spy = _SpyProvider(engine, crash_on=2)
    try:
        outbound.send_batch(db, ev, [
            outbound.OutboundItem(guest=a.guest, phone=a.guest.phone, text=a.preview,
                                  kind="event_day", event_message_id=em.id)
            for a in actions
        ], provider=spy)
        raise AssertionError("ציפינו לנפילה")
    except _ProcessCrash:
        pass
    event_id = ev.id
    db.close()  # התהליך "מת" — מה שלא נשמר, אבד.

    fresh = Session(engine)
    statuses = sorted(m.status for m in fresh.scalars(select(models.Message)))
    assert statuses == ["pending", "pending", "sent"], statuses
    ev2 = fresh.get(models.Event, event_id)
    again = c.compute_due_messages(fresh, ev2, now=now)
    assert again == [], "אחרי נפילה — אף מוזמן לא אמור לחזור לתור"
    print("✓ B2: נפילה באמצע מנה — אין שליחה חוזרת (גם לא למצב 'לא ידוע')")


def test_provider_exception_is_unknown_and_batch_continues() -> None:
    """חריגה לא צפויה מספק *אמיתי* יכולה לקרות גם אחרי שהבקשה יצאה — לכן
    השורה נשארת "לא ידוע" (pending, לא נשלחת שוב) ולא "נכשלה" (שלב 3)."""
    from app import models, outbound

    engine = _engine()
    db = Session(engine)
    ev = _event(db)
    guests = [_guest(db, ev.id, _phone()) for _ in range(3)]
    spy = _SpyProvider(engine, raise_on=2)
    res = outbound.send_batch(db, ev, [
        outbound.OutboundItem(guest=g, phone=g.phone, text="שלום", kind="reminder_1")
        for g in guests
    ], provider=spy)
    db.commit()
    assert (res.sent, res.failed, res.unknown) == (2, 0, 1)
    assert res.failed_guest_ids == [], "לא מוצע לניסיון חוזר"
    rows = db.scalars(select(models.Message).order_by(models.Message.id)).all()
    assert [r.status for r in rows] == ["sent", "pending", "sent"]
    assert "network" not in rows[1].failure_reason, "פרטי חריגה פנימיים לא נשמרים כסיבה"
    print("✓ B3: חריגה בספק אמיתי — 'לא ידוע' (pending), שאר המנה ממשיכה")


def test_mock_provider_exception_marks_failed() -> None:
    from app import messaging, models, outbound

    class _Broken(messaging.MockProvider):
        def send_invitation(self, phone, text):  # noqa: ARG002
            raise RuntimeError("boom")

    db = Session(_engine())
    ev = _event(db)
    g = _guest(db, ev.id, _phone())
    res = outbound.send_batch(db, ev, [
        outbound.OutboundItem(guest=g, phone=g.phone, text="שלום", kind="reminder_1")
    ], provider=_Broken())
    db.commit()
    assert (res.failed, res.unknown) == (1, 0)
    assert db.scalars(select(models.Message)).one().status == "failed"
    print("✓ B3b: חריגה בספק בלי תופעת לוואי חיצונית (mock) — נכשלה, כמו קודם")


def test_mock_send_outcome_unchanged() -> None:
    from app import messaging, models, outbound

    engine = _engine()
    db = Session(engine)
    ev = _event(db)
    g = _guest(db, ev.id, _phone())
    res = outbound.send_batch(db, ev, [
        outbound.OutboundItem(guest=g, phone=g.phone, text="שלום", kind="invitation")
    ], provider=messaging.MockProvider())
    db.commit()
    row = db.scalars(select(models.Message)).one()
    assert res.sent == 1 and row.status == "sent" and row.provider == "mock"
    assert row.provider_message_id.startswith("mock-") and row.sent_at is not None
    assert row.channel == "whatsapp" and row.cycle_number == 1
    print("✓ B4: במצב mock התוצאה זהה לקודם (sent, mock-id, sent_at)")


def test_pending_counts_as_invited_only_for_dedup() -> None:
    from app import invitations

    engine = _engine()
    db = Session(engine)
    ev = _event(db)
    g = _guest(db, ev.id, _phone())
    _outbound(db, g, "wamid-pending-inv", status="pending")
    assert g.id in invitations.invited_guest_ids(db, ev.id, ev, include_uncertain=True)
    assert g.id not in invitations.invited_guest_ids(db, ev.id, ev)
    print("✓ B5: 'לא ידוע' חוסם הזמנה חוזרת, אבל לא נספר כ'נשלחה' בתצוגה")


# ============================================================================
# C. עדכוני מסירה
# ============================================================================

def test_failed_does_not_override_delivered_or_read() -> None:
    from app import message_status as ms

    db = Session(_engine())
    ev = _event(db)
    g = _guest(db, ev.id, _phone())
    for start in ("delivered", "read"):
        wamid = f"wamid-{start}-{secrets.token_hex(4)}"
        m = _outbound(db, g, wamid, status=start)
        assert ms.apply_status_update(db, provider_message_id=wamid, status=ms.FAILED,
                                      reason="late", failure_code=131026)
        db.commit()
        assert m.status == start, f"{start} נדרס ל-{m.status}"
        assert m.failure_code == 131026, "הקוד הגולמי עדיין נשמר"
    print("✓ C1: 'נכשלה' מאוחרת לא דורסת 'נמסרה'/'נקראה' (מסלול אחד לשני סוגי ה-DB)")


def test_status_update_never_touches_inbound_row() -> None:
    from app import message_status as ms
    from app import models

    db = Session(_engine())
    ev = _event(db)
    g = _guest(db, ev.id, _phone())
    inbound = models.Message(event_id=ev.id, guest_id=g.id, direction="inbound", kind="reply",
                             body="x", status="received", provider="meta",
                             provider_message_id="wamid-inbound-x")
    db.add(inbound)
    db.commit()
    assert ms.apply_status_update(db, provider_message_id="wamid-inbound-x", status=ms.READ) is False
    assert inbound.status == "received"
    print("✓ C2: עדכון מסירה לא נוגע בהודעה נכנסת עם אותו מזהה")


# ============================================================================
# D. ה-webhook מקצה לקצה
# ============================================================================

@contextmanager
def _secret(inbound_rsvp: bool = True, inbound: bool = True):
    """סוד ה-webhook לזמן הקריאה, ושני המתגים — כבויים במערכת כברירת מחדל:
    ``inbound`` (``WHATSAPP_WEBHOOK_INBOUND``, עיבוד הודעות נכנסות בכלל) ו-
    ``inbound_rsvp`` (``WHATSAPP_INBOUND_RSVP``, עדכון RSVP מלחיצת כפתור).
    הבדיקות בקובץ הזה בודקות את הלוגיקה הזו עצמה, ולכן מדליקות במפורש."""
    keys = {
        "WHATSAPP_APP_SECRET": _SECRET,
        "WHATSAPP_WEBHOOK_PHONE_NUMBER_ID": TEST_PHONE_NUMBER_ID,
        "WHATSAPP_WEBHOOK_INBOUND": "1" if inbound else "",
        "WHATSAPP_INBOUND_RSVP": "1" if inbound_rsvp else "",
    }
    prev = {k: os.environ.get(k) for k in keys}
    os.environ.update(keys)
    try:
        yield
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _post(api, payload: dict, inbound_rsvp: bool = True, inbound: bool = True):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = "sha256=" + hmac.new(_SECRET.encode(), body, hashlib.sha256).hexdigest()
    with _secret(inbound_rsvp, inbound):
        return api.client.post(WEBHOOK_URL, content=body, headers={
            "Content-Type": "application/json", "X-Hub-Signature-256": sig,
        })


def _reply(from_phone: str, wamid: str, coming: bool = True, context: str | None = None) -> dict:
    msg = {
        "from": from_phone, "id": wamid, "type": "interactive",
        "interactive": {"type": "button_reply",
                        "button_reply": {"id": "rsvp_yes" if coming else "rsvp_no"}},
    }
    if context:
        msg["context"] = {"id": context}
    return msg


# מזהה המספר (Phone Number ID) שבו מגיעים אירועי ה-webhook בבדיקות — ראו
# ``WHATSAPP_WEBHOOK_PHONE_NUMBER_ID`` ו-``routers/messaging._webhook_items``.
TEST_PHONE_NUMBER_ID = "100000000000001"


def _payload(*messages, statuses=(), phone_number_id=TEST_PHONE_NUMBER_ID) -> dict:
    value: dict = {"messages": list(messages), "statuses": list(statuses)}
    if phone_number_id is not None:
        value["metadata"] = {"display_phone_number": "15550000000", "phone_number_id": phone_number_id}
    return {"entry": [{"changes": [{"field": "messages", "value": value}]}]}


def _db():
    from app.database import SessionLocal, set_request_identity

    set_request_identity(None)
    return SessionLocal()


def _open_rsvp(api) -> None:
    """תאריך אירוע + מסלול פעיל עם מועד סגירה כך שחלון אישורי ההגעה פתוח היום
    (כמו ``tests/test_guest_hub.py::_open_rsvp``)."""
    from app import guest_journey, models

    ev_date = guest_journey.today_in_israel() + timedelta(days=30)
    commit_days = (ev_date - (guest_journey.today_in_israel() - timedelta(days=21))).days
    db = _db()
    try:
        ev = db.get(models.Event, api.event_id)
        ev.event_date = ev_date.isoformat()
        ev.rsvp_track_active = True
        ev.rsvp_track_started_at = datetime.utcnow() - timedelta(days=40)
        ev.venue_commit_days_before = max(commit_days, 1)
        db.commit()
        assert guest_journey.rsvp_is_open(ev)
    finally:
        db.close()


def _guest_row(guest_id: int):
    from app import models

    db = _db()
    try:
        return db.get(models.Guest, guest_id)
    finally:
        db.close()


def _inbound_rows(event_id: int):
    from app import models

    db = _db()
    try:
        return db.scalars(
            select(models.Message)
            .where(models.Message.event_id == event_id, models.Message.direction == "inbound")
            .order_by(models.Message.id)
        ).all()
    finally:
        db.close()


def _audit_count(event_id, action: str) -> int:
    from app import models

    db = _db()
    try:
        return len(db.scalars(
            select(models.AuditLog)
            .where(models.AuditLog.event_id == event_id, models.AuditLog.action == action)
        ).all())
    finally:
        db.close()


def test_webhook_reply_uses_existing_rsvp_logic() -> None:
    api, _ = bootstrap()
    _open_rsvp(api)
    phone = _phone()
    g = api.add_guest("מוזמנת וואטסאפ", phone, party_size=3)
    r = _post(api, _payload(_reply(_intl(phone), "wamid-in-" + secrets.token_hex(6))))
    assert r.status_code == 200, r.text
    row = _guest_row(g["id"])
    assert row.rsvp_status == "confirmed"
    assert row.confirmed_count == 3, "כמו בקישור האישי: ברירת המחדל = כמה שהוזמנו"
    inbound = _inbound_rows(api.event_id)
    assert len(inbound) == 1 and inbound[0].status == "received" and inbound[0].kind == "reply"
    assert _audit_count(api.event_id, "confirm_submit") == 1, "נרשם ביומן הפעילות"
    print("✓ D1: תשובה מ-WhatsApp → rsvp_response (כמות + יומן), כמו הקישור האישי")


def test_webhook_duplicate_delivery_applies_once() -> None:
    api, _ = bootstrap()
    _open_rsvp(api)
    phone = _phone()
    g = api.add_guest("מוזמן כפול", phone)
    payload = _payload(_reply(_intl(phone), "wamid-dup-" + secrets.token_hex(6)))
    for _ in range(3):
        assert _post(api, payload).status_code == 200
    assert _guest_row(g["id"]).rsvp_status == "confirmed"
    assert len(_inbound_rows(api.event_id)) == 1, "הודעה אחת ביומן, לא שלוש"
    assert _audit_count(api.event_id, "confirm_submit") == 1
    print("✓ D2: אותו webhook שלוש פעמים → מוחל ונרשם פעם אחת")


def test_webhook_duplicate_does_not_revert_newer_answer() -> None:
    """האורח לחץ 'מגיע', אחר כך שינה בקישור ל'לא מגיע'. retry מאוחר של אותה
    לחיצה מ-Meta לא מחזיר אותו ל'מגיע'."""
    api, _ = bootstrap()
    _open_rsvp(api)
    phone = _phone()
    g = api.add_guest("מוזמן שהתחרט", phone)
    payload = _payload(_reply(_intl(phone), "wamid-late-" + secrets.token_hex(6)))
    assert _post(api, payload).status_code == 200
    from app import models

    db = _db()
    try:
        db.get(models.Guest, g["id"]).rsvp_status = "declined"
        db.commit()
    finally:
        db.close()
    assert _post(api, payload).status_code == 200
    assert _guest_row(g["id"]).rsvp_status == "declined"
    print("✓ D3: retry מאוחר של webhook לא דורס תשובה חדשה יותר")


def test_webhook_window_closed_does_not_change_rsvp() -> None:
    api, _ = bootstrap()  # בלי תאריך/מסלול — אישורי ההגעה סגורים
    phone = _phone()
    g = api.add_guest("מוזמן מוקדם", phone)
    assert _post(api, _payload(_reply(_intl(phone), "wamid-early-" + secrets.token_hex(6)))).status_code == 200
    assert _guest_row(g["id"]).rsvp_status == "pending"
    inbound = _inbound_rows(api.event_id)
    assert len(inbound) == 1 and inbound[0].status == "needs_attention"
    assert _audit_count(api.event_id, "confirm_submit") == 0
    print("✓ D4: לפני שנפתח חלון אישורי ההגעה — לא משנים RSVP, נשמר 'דורש טיפול'")


def test_webhook_household_phone() -> None:
    from app import models

    api, _ = bootstrap()
    _open_rsvp(api)
    phone = _phone()
    g1 = api.add_guest("בן משפחה א", phone)
    g2 = api.add_guest("בן משפחה ב", phone)

    # בלי context — עמימות: אף אחד לא מתעדכן, נשמר "דורש טיפול".
    assert _post(api, _payload(_reply(_intl(phone), "wamid-hh-" + secrets.token_hex(6)))).status_code == 200
    assert _guest_row(g1["id"]).rsvp_status == "pending"
    assert _guest_row(g2["id"]).rsvp_status == "pending"
    rows = _inbound_rows(api.event_id)
    assert len(rows) == 1 and rows[0].status == "needs_attention" and rows[0].guest_id is None
    assert phone not in rows[0].body, "בלי מספר טלפון ביומן"

    # תשובה להודעה שנשלחה ל-g2 — רק g2 מתעדכן.
    wamid_out = "wamid-out-" + secrets.token_hex(6)
    db = _db()
    try:
        db.add(models.Message(event_id=api.event_id, guest_id=g2["id"], direction="outbound",
                              kind="invitation", body="hi", status="delivered", provider="meta",
                              provider_message_id=wamid_out))
        db.commit()
    finally:
        db.close()
    reply = _reply(_intl(phone), "wamid-hh2-" + secrets.token_hex(6), context=wamid_out)
    assert _post(api, _payload(reply)).status_code == 200
    assert _guest_row(g1["id"]).rsvp_status == "pending"
    assert _guest_row(g2["id"]).rsvp_status == "confirmed"
    print("✓ D5: טלפון משפחתי — בלי context טיפול ידני; עם context המוזמן הנכון בלבד")


def test_webhook_same_phone_two_events_untouched() -> None:
    api_a, _ = bootstrap()
    api_b, _ = bootstrap()
    _open_rsvp(api_a)
    _open_rsvp(api_b)
    phone = _phone()
    ga = api_a.add_guest("מוזמן באירוע א", phone)
    gb = api_b.add_guest("מוזמן באירוע ב", phone)
    assert _post(api_a, _payload(_reply(_intl(phone), "wamid-x-" + secrets.token_hex(6)))).status_code == 200
    assert _guest_row(ga["id"]).rsvp_status == "pending"
    assert _guest_row(gb["id"]).rsvp_status == "pending"
    print("✓ D6: אותו טלפון בשני אירועים — אף RSVP לא משתנה")


def test_webhook_db_failure_returns_500_then_retry_succeeds() -> None:
    from sqlalchemy.exc import OperationalError

    from app import whatsapp_inbound

    api, _ = bootstrap()
    _open_rsvp(api)
    p1, p2 = _phone(), _phone()
    g1 = api.add_guest("ראשון", p1)
    g2 = api.add_guest("שני", p2)
    payload = _payload(
        _reply(_intl(p1), "wamid-p1-" + secrets.token_hex(6)),
        _reply(_intl(p2), "wamid-p2-" + secrets.token_hex(6)),
    )

    real = whatsapp_inbound.record_rsvp_reply
    calls = {"n": 0}

    def flaky(db, **kw):
        calls["n"] += 1
        if calls["n"] == 2:  # הפריט השני נופל — הראשון כבר נשמר
            raise OperationalError("SELECT 1", {}, Exception("connection reset"))
        return real(db, **kw)

    whatsapp_inbound.record_rsvp_reply = flaky
    try:
        r = _post(api, payload)
    finally:
        whatsapp_inbound.record_rsvp_reply = real
    assert r.status_code == 500, f"כשל DB זמני → 500 כדי ש-Meta תנסה שוב ({r.status_code})"
    assert "connection" not in r.text.lower()
    assert _guest_row(g1["id"]).rsvp_status == "confirmed", "הצלחה חלקית נשמרה"
    assert _guest_row(g2["id"]).rsvp_status == "pending"

    # Meta שולחת שוב את כל הקריאה.
    assert _post(api, payload).status_code == 200
    assert _guest_row(g2["id"]).rsvp_status == "confirmed"
    assert len(_inbound_rows(api.event_id)) == 2, "הראשון לא נרשם פעמיים"
    assert _audit_count(api.event_id, "confirm_submit") == 2
    print("✓ D7: כשל DB באמצע → 500; הניסיון החוזר משלים בלי כפילות")


def test_webhook_malformed_items_are_skipped() -> None:
    api, _ = bootstrap()
    _open_rsvp(api)
    phone = _phone()
    g = api.add_guest("מוזמן תקין", phone)
    weird = {"entry": [
        {"changes": "not-a-list"},
        {"changes": [{"value": {"messages": "nope", "statuses": [42, None]}}]},
        {"changes": [{"value": {"metadata": {"phone_number_id": TEST_PHONE_NUMBER_ID}, "messages": [
            {"from": _intl(phone), "interactive": {"button_reply": {"id": "rsvp_yes"}}},  # בלי id
            {"from": 5, "id": 7, "interactive": None},
            {"from": _intl(phone), "id": "wamid-text-" + secrets.token_hex(4), "type": "text",
             "text": {"body": "נגיע 3"}},
        ], "statuses": [{"id": "wamid-unknown", "status": "delivered", "timestamp": "nan"},
                        {"id": "", "status": "read"}, {"status": "weird"}]}}]},
        {"changes": [{"value": {"metadata": {"phone_number_id": TEST_PHONE_NUMBER_ID}, "messages": [
            _reply(_intl(phone), "wamid-good-" + secrets.token_hex(6))]}}]},
    ]}
    r = _post(api, weird)
    assert r.status_code == 200, r.text
    assert _guest_row(g["id"]).rsvp_status == "confirmed", "הפריט התקין עובד גם בתוך payload פגום"
    # מאז שלב 3 גם הטקסט החופשי ("נגיע 3") נשמר — כ"דורש טיפול", בלי לשנות RSVP.
    rows = _inbound_rows(api.event_id)
    assert sorted(r.status for r in rows) == ["needs_attention", "received"], [r.status for r in rows]
    print("✓ D8: payload לא צפוי — מה שפגום מדולג, מה שתקין מטופל, 200")


def test_webhook_status_updates_are_idempotent() -> None:
    from app import models

    api, _ = bootstrap()
    g = api.add_guest("מוזמן סטטוס", _phone())
    wamid = "wamid-st-" + secrets.token_hex(6)
    db = _db()
    try:
        db.add(models.Message(event_id=api.event_id, guest_id=g["id"], direction="outbound",
                              kind="invitation", body="hi", status="sent", provider="meta",
                              provider_message_id=wamid))
        db.commit()
    finally:
        db.close()
    read = {"id": wamid, "status": "read", "timestamp": "1790000000"}
    delivered = {"id": wamid, "status": "delivered", "timestamp": "1789999990"}
    failed = {"id": wamid, "status": "failed", "errors": [{"code": 131026, "title": "x"}]}
    for st in (read, delivered, read, failed):
        assert _post(api, _payload(statuses=[st])).status_code == 200
    db = _db()
    try:
        m = db.scalars(select(models.Message).where(models.Message.provider_message_id == wamid)).one()
        assert m.status == "read", m.status
        assert m.read_at is not None
    finally:
        db.close()
    print("✓ D9: עדכוני מסירה כפולים/לא לפי הסדר — נשאר 'נקראה'")


# ============================================================================
# E. ספירת "הזמנות שנשלחו" במסך התקשורת
# ============================================================================

def test_summary_counts_delivered_and_read_invitations() -> None:
    from app import models

    api, _ = bootstrap()
    statuses = ["sent", "delivered", "read", "failed", "pending"]
    db = _db()
    try:
        for i, st in enumerate(statuses):
            g = models.Guest(event_id=api.event_id, full_name=f"מוזמן {i}", phone=_phone())
            db.add(g)
            db.flush()
            db.add(models.Message(event_id=api.event_id, guest_id=g.id, direction="outbound",
                                  kind="invitation", body="hi", status=st, provider="meta",
                                  provider_message_id=f"wamid-sum-{secrets.token_hex(6)}"))
        db.commit()
    finally:
        db.close()
    r = api.client.get("/messaging/summary", headers=api.headers)
    assert r.status_code == 200, r.text
    assert r.json()["invitations_sent"] == 3, r.json()
    print("✓ E1: 'הזמנות שנשלחו' כולל נמסרה/נקראה (3), לא נכשלה/לא ידוע")


def test_activate_track_leaves_no_pending_rows_in_mock() -> None:
    from app import models

    api, _ = bootstrap()
    for i in range(3):
        api.add_guest(f"מוזמן הזמנה {i}", _phone())
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
    r = api.client.post("/automation/track/activate", headers=api.headers, json={})
    assert r.status_code == 200, r.text
    assert r.json()["invitations_sent"] == 3, r.json()
    r2 = api.client.post("/automation/track/activate", headers=api.headers, json={})
    assert r2.status_code == 200 and r2.json()["invitations_sent"] == 0, "בלי הזמנה כפולה"
    db = _db()
    try:
        rows = db.scalars(select(models.Message).where(
            models.Message.event_id == api.event_id, models.Message.kind == "invitation")).all()
        assert sorted(m.status for m in rows) == ["sent"] * 3
    finally:
        db.close()
    print("✓ E2: שליחת הזמנות במצב mock — 3 נשלחו, אין pending, אין כפילות בלחיצה שנייה")


def test_stuck_pending_invitation_is_never_resent_by_couple() -> None:
    """הזמנה שנתקעה ב-pending (השרת נפל אחרי שאולי יצאה): אף אחת מדרכי
    השליחה של הזוג — "חדשים", "כולם", "ניסיון חוזר לנכשלים" — לא שולחת שוב."""
    from app import models

    api, _ = bootstrap()
    g = api.add_guest("מוזמן תקוע", _phone())
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
        db.add(models.Message(event_id=api.event_id, guest_id=g["id"], direction="outbound",
                              kind="invitation", body="x", status="pending", provider="meta"))
        db.commit()
    finally:
        db.close()
    for body in ({}, {"scope": "all"}, {"retry_ids": [g["id"]]}, {"guest_ids": [g["id"]]}):
        r = api.client.post("/automation/track/activate", headers=api.headers, json=body)
        assert r.status_code == 200, r.text
        assert r.json()["invitations_sent"] == 0, (body, r.json())
    db = _db()
    try:
        rows = db.scalars(select(models.Message).where(
            models.Message.event_id == api.event_id, models.Message.guest_id == g["id"])).all()
        assert [m.status for m in rows] == ["pending"], "לא נוצרה שליחה נוספת"
    finally:
        db.close()
    print("✓ E3: הזמנה תקועה ב-pending — אף דרך שליחה של הזוג לא שולחת שוב")


if __name__ == "__main__":
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_") and callable(fn):
                fn()
        print()
        print("=== כל בדיקות הבטיחות של WhatsApp עברו ===")
    finally:
        shutdown()
