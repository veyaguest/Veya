"""בדיקות עומק לשכבת סטטוס ההודעות (app/message_status.py) — הביקורת
שהתבקשה על התאמה לסמנטיקה האמיתית של WhatsApp Cloud API.

מכסה את 10 התרחישים שהתבקשו:
1. הודעה queued (טלפון תקין, טרם נשלחה)
2. הודעה sent
3. הודעה delivered
4. הודעה read
5. הודעה failed
6. מספר לא תקין (local — חסר/פורמט שגוי, לא webhook)
7. חסימה (evidence-based בלבד — קוד שגיאה ספציפי, לא כל כשל)
8. webhook שמגיע בסדר לא צפוי (לא נסוגים אחורה)
9. webhook כפול (אידמפוטנטי)
10. webhook של הודעה אחרת לא משפיע על ההודעה הנוכחית (בידוד לפי provider_message_id)

הרצה: ``venv/bin/python tests/test_message_status.py`` (עצמאי, בלי pytest).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import message_status as ms  # noqa: E402
from app import models  # noqa: E402
from app.database import Base  # noqa: E402


def _fresh_session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _make_event(db: Session) -> models.Event:
    ev = models.Event(groom_name="יואב", bride_name="דנה", event_type="wedding")
    db.add(ev)
    db.commit()
    return ev


def _make_guest(db: Session, event_id: int, phone: str, name: str = "מוזמן") -> models.Guest:
    g = models.Guest(event_id=event_id, full_name=name, phone=phone, side="groom")
    db.add(g)
    db.commit()
    return g


def test_1_queued_guest_with_valid_phone_and_no_message() -> None:
    """מוזמן עם טלפון תקין, בלי אף הודעה יוצאת — ⏳ ממתינים לשליחה."""
    db = _fresh_session()
    ev = _make_event(db)
    g = _make_guest(db, ev.id, "0501234567")
    counts = ms.summarize([g], [])
    assert counts[ms.QUEUED] == 1
    assert sum(counts.values()) == 1
    print("✓ 1: מוזמן בלי הודעה + טלפון תקין → queued")


def test_2_sent_message() -> None:
    """הודעה שנשלחה — status='sent', sent_at מוזן ע"י outbound_fields."""

    class FakeSendResult:
        ok, provider, status, detail, provider_message_id = True, "mock", "sent", "", "wamid-1"

    fields = ms.outbound_fields(FakeSendResult())
    assert fields["status"] == "sent"
    assert fields["provider_message_id"] == "wamid-1"
    assert "sent_at" in fields and fields["sent_at"] is not None
    print("✓ 2: outbound_fields בונה שורת 'sent' תקינה עם sent_at")


def test_3_delivered_via_webhook() -> None:
    """webhook עם status='delivered' מעדכן את ההודעה ואת delivered_at."""
    db = _fresh_session()
    ev = _make_event(db)
    g = _make_guest(db, ev.id, "0501234567")
    msg = models.Message(
        event_id=ev.id, guest_id=g.id, direction="outbound", kind="invitation",
        body="hi", status="sent", provider="meta", provider_message_id="wamid-3",
    )
    db.add(msg)
    db.commit()

    ok = ms.apply_status_update(db, provider_message_id="wamid-3", status=ms.DELIVERED)
    db.commit()
    assert ok is True
    db.refresh(msg)
    assert msg.status == ms.DELIVERED
    assert msg.delivered_at is not None
    counts = ms.summarize([g], [msg])
    assert counts[ms.DELIVERED] == 1
    print("✓ 3: webhook 'delivered' מעדכן status + delivered_at + מופיע בסיכום")


def test_4_read_via_webhook() -> None:
    """webhook עם status='read' אחרי 'delivered' — מתקדם כמצופה."""
    db = _fresh_session()
    ev = _make_event(db)
    g = _make_guest(db, ev.id, "0501234567")
    msg = models.Message(
        event_id=ev.id, guest_id=g.id, direction="outbound", kind="invitation",
        body="hi", status="sent", provider="meta", provider_message_id="wamid-4",
    )
    db.add(msg)
    db.commit()

    ms.apply_status_update(db, provider_message_id="wamid-4", status=ms.DELIVERED)
    ms.apply_status_update(db, provider_message_id="wamid-4", status=ms.READ)
    db.commit()
    db.refresh(msg)
    assert msg.status == ms.READ
    assert msg.read_at is not None
    print("✓ 4: התקדמות sent → delivered → read עובדת")


def test_5_failed_message() -> None:
    """כשל שליחה סינכרוני — status='failed', failure_reason ו-failure_code נשמרים."""

    class FakeSendResult:
        ok, provider, status = False, "meta", "failed"
        detail = "Meta 400: template not approved"
        provider_message_id = ""
        error_code = 132000

    fields = ms.outbound_fields(FakeSendResult())
    assert fields["status"] == "failed"
    assert fields["failure_reason"] == "Meta 400: template not approved"
    assert fields["failure_code"] == 132000
    print("✓ 5: כשל שליחה שומר failure_reason + failure_code גולמי")


def test_6_no_valid_number_is_local_only() -> None:
    """מספר חסר/לא תקין — נגזר מקומית, בלי אף Message, ואף פעם לא מגיע מ-webhook."""
    db = _fresh_session()
    ev = _make_event(db)
    missing = _make_guest(db, ev.id, "", "בלי טלפון")
    invalid = _make_guest(db, ev.id, "123", "טלפון שגוי")
    counts = ms.summarize([missing, invalid], [])
    assert counts[ms.NO_VALID_NUMBER] == 2
    # וידוא שהחוק לא נשבר: אף webhook לא יכול לייצר את הסטטוס הזה.
    assert ms.map_meta_status("failed", [{"code": 999999}]) == ms.FAILED
    assert ms.NO_VALID_NUMBER not in ms._META_STATUS_MAP.values()
    assert ms.NO_VALID_NUMBER not in ms._META_ERROR_CODE_STATUS.values()
    print("✓ 6: no_valid_number תמיד מקומי — לעולם לא תוצר אפשרית של מיפוי webhook")


def test_7_blocked_is_evidence_based_only() -> None:
    """'חסום' רק עם קוד שגיאה ספציפי (131050) — כשל גנרי/131026 לא מספיקים."""
    assert ms.map_meta_status("failed", [{"code": 131050, "title": "opted out"}]) == ms.BLOCKED
    # 131026 (הקטגוריה המעורפלת של Meta) לא נחשב הוכחה מספקת ל"חסום".
    assert ms.map_meta_status("failed", [{"code": 131026}]) == ms.FAILED
    # כשל גנרי בלי קוד בכלל — גם הוא FAILED, לא BLOCKED.
    assert ms.map_meta_status("failed", []) == ms.FAILED
    assert ms.map_meta_status("failed", None) == ms.FAILED
    print("✓ 7: 'חסום' רק על בסיס קוד ספציפי — לא כל כשל, ולא הקוד המעורפל 131026")


def test_8_out_of_order_webhook_does_not_regress() -> None:
    """webhook 'sent' מאוחר שמגיע אחרי שכבר יש 'read' — לא חוזר אחורה."""
    db = _fresh_session()
    ev = _make_event(db)
    g = _make_guest(db, ev.id, "0501234567")
    msg = models.Message(
        event_id=ev.id, guest_id=g.id, direction="outbound", kind="invitation",
        body="hi", status="sent", provider="meta", provider_message_id="wamid-8",
    )
    db.add(msg)
    db.commit()

    ms.apply_status_update(db, provider_message_id="wamid-8", status=ms.READ)
    db.commit()
    # webhook "sent" ישן שמגיע באיחור (למשל retry של Meta) — לא אמור לדרוס.
    ok = ms.apply_status_update(db, provider_message_id="wamid-8", status=ms.SENT)
    db.commit()
    db.refresh(msg)
    assert ok is True  # ההודעה נמצאה — רק העדכון בפועל דולג
    assert msg.status == ms.READ, f"נסוג ל-{msg.status}! webhook לא-לפי-סדר שבר את הסטטוס"

    # גם 'failed' מאוחר לא אמור לדרוס הודעה שכבר אושרה כנקראה.
    ms.apply_status_update(db, provider_message_id="wamid-8", status=ms.FAILED, reason="stale")
    db.commit()
    db.refresh(msg)
    assert msg.status == ms.READ
    print("✓ 8: webhook לא-לפי-סדר (sent/failed מאוחר) לא מחזיר סטטוס אחורה")


def test_9_duplicate_webhook_is_idempotent() -> None:
    """אותו webhook 'delivered' פעמיים — לא שגיאה, לא מכפיל, אותה תוצאה."""
    db = _fresh_session()
    ev = _make_event(db)
    g = _make_guest(db, ev.id, "0501234567")
    msg = models.Message(
        event_id=ev.id, guest_id=g.id, direction="outbound", kind="invitation",
        body="hi", status="sent", provider="meta", provider_message_id="wamid-9",
    )
    db.add(msg)
    db.commit()

    ok1 = ms.apply_status_update(db, provider_message_id="wamid-9", status=ms.DELIVERED)
    db.commit()
    first_delivered_at = msg.delivered_at
    ok2 = ms.apply_status_update(db, provider_message_id="wamid-9", status=ms.DELIVERED)
    db.commit()
    db.refresh(msg)
    assert ok1 is True and ok2 is True
    assert msg.status == ms.DELIVERED
    assert msg.delivered_at is not None and first_delivered_at is not None
    # רק הודעה אחת קיימת — webhook כפול לא יצר עוד שורה.
    assert db.query(models.Message).count() == 1
    print("✓ 9: webhook כפול (delivered פעמיים) אידמפוטנטי — בלי שגיאה ובלי כפילות")


def test_10_webhook_does_not_leak_to_other_message() -> None:
    """webhook עם provider_message_id של הודעה א' לא נוגע בהודעה ב' של מוזמן אחר."""
    db = _fresh_session()
    ev = _make_event(db)
    g1 = _make_guest(db, ev.id, "0501234567", "מוזמן א")
    g2 = _make_guest(db, ev.id, "0521234567", "מוזמן ב")
    m1 = models.Message(
        event_id=ev.id, guest_id=g1.id, direction="outbound", kind="invitation",
        body="hi", status="sent", provider="meta", provider_message_id="wamid-A",
    )
    m2 = models.Message(
        event_id=ev.id, guest_id=g2.id, direction="outbound", kind="invitation",
        body="hi", status="sent", provider="meta", provider_message_id="wamid-B",
    )
    db.add_all([m1, m2])
    db.commit()

    ms.apply_status_update(db, provider_message_id="wamid-A", status=ms.READ)
    db.commit()
    db.refresh(m1)
    db.refresh(m2)
    assert m1.status == ms.READ
    assert m2.status == "sent", "webhook של הודעה אחרת דלף למוזמן הלא-נכון!"

    # מזהה לא קיים כלל — לא נופל, לא נוגע בכלום.
    ok = ms.apply_status_update(db, provider_message_id="does-not-exist", status=ms.READ)
    db.commit()
    db.refresh(m1)
    db.refresh(m2)
    assert ok is False
    assert m1.status == ms.READ and m2.status == "sent"
    print("✓ 10: webhook מבודד לחלוטין לפי provider_message_id — אין דליפה בין מוזמנים")


def test_unique_index_prevents_duplicate_provider_message_id() -> None:
    """הגנה נוספת ברמת ה-DB: שני Message עם אותו provider_message_id נחסמים."""
    from sqlalchemy import inspect

    from app import main as app_main

    db = _fresh_session()
    engine = db.get_bind()
    original = app_main.migrations_engine
    try:
        app_main.migrations_engine = engine
        app_main._ensure_unique_indexes()
    finally:
        app_main.migrations_engine = original

    assert any(
        i["name"] == "ux_messages_provider_message_id" and i["unique"]
        for i in inspect(engine).get_indexes("messages")
    ), "האינדקס הייחודי לא נוצר"

    ev = _make_event(db)
    g = _make_guest(db, ev.id, "0501234567")
    db.add(models.Message(
        event_id=ev.id, guest_id=g.id, direction="outbound", kind="invitation",
        body="x", status="sent", provider="meta", provider_message_id="dup-id",
    ))
    db.commit()

    raised = False
    try:
        db.add(models.Message(
            event_id=ev.id, guest_id=g.id, direction="outbound", kind="invitation",
            body="y", status="sent", provider="meta", provider_message_id="dup-id",
        ))
        db.commit()
    except Exception:
        raised = True
        db.rollback()
    assert raised, "האינדקס הייחודי לא חסם provider_message_id כפול!"
    print("✓ בונוס: אינדקס ייחודי ב-DB חוסם provider_message_id כפול ברמת המסד עצמו")


if __name__ == "__main__":
    test_1_queued_guest_with_valid_phone_and_no_message()
    test_2_sent_message()
    test_3_delivered_via_webhook()
    test_4_read_via_webhook()
    test_5_failed_message()
    test_6_no_valid_number_is_local_only()
    test_7_blocked_is_evidence_based_only()
    test_8_out_of_order_webhook_does_not_regress()
    test_9_duplicate_webhook_is_idempotent()
    test_10_webhook_does_not_leak_to_other_message()
    test_unique_index_prevents_duplicate_provider_message_id()
    print()
    print("=== כל 10 התרחישים + הגנת ה-DB עברו ===")
