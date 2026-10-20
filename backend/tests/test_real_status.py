"""הסטטוס בעמוד אישורי ההגעה = רק מה שבאמת יצא ב-WhatsApp (2026-10-19).

- כש-WhatsApp אמיתי (``meta_test``/``meta``), שורות של מצב ההדגמה (``mock``) לא
  נספרות: לא "נשלחו", לא "כבר קיבל הזמנה", לא "כבר קיבל את התזכורת".
- במצב mock — הכול כמו קודם.
- ``pending`` (הבקשה יצאה ואין עדכון) מוצג בשורה כ-pending, לא כ"ממתין לשליחה".
- כל עדכון מ-Meta מסמן ``status_updated_at`` (בדיקת חיבור ה-webhook באדמין).
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import event_cycle, invitations, message_status as ms, models  # noqa: E402
from app.database import Base  # noqa: E402


def _db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _setup(db: Session):
    ev = models.Event(groom_name="יואב", bride_name="דנה", event_type="wedding", event_date="2026-12-01")
    db.add(ev)
    db.flush()
    demo = models.Guest(event_id=ev.id, full_name="הדגמה", phone="0501111111")
    real = models.Guest(event_id=ev.id, full_name="אמיתי", phone="0502222222")
    db.add_all([demo, real])
    db.flush()
    db.add_all([
        models.Message(event_id=ev.id, guest_id=demo.id, direction="outbound", kind="invitation",
                       status="sent", provider="mock", created_at=datetime(2026, 10, 1)),
        models.Message(event_id=ev.id, guest_id=real.id, direction="outbound", kind="invitation",
                       status="delivered", provider="meta", provider_message_id="wamid.A",
                       created_at=datetime(2026, 10, 1)),
    ])
    db.commit()
    return ev, demo, real


def _cycle_messages(db: Session, ev: models.Event) -> list[models.Message]:
    return list(db.scalars(
        select(models.Message).where(models.Message.event_id == ev.id)
        .where(event_cycle.current_sends(ev))
    ).all())


@pytest.mark.parametrize("mode", ["meta_test", "meta"])
def test_demo_sends_do_not_count_when_whatsapp_is_real(monkeypatch, mode) -> None:
    monkeypatch.setenv("WHATSAPP_MODE", mode)
    db = _db()
    ev, demo, real = _setup(db)
    assert invitations.invited_guest_ids(db, ev.id, ev, include_uncertain=True) == {real.id}
    counts = ms.summarize([demo, real], _cycle_messages(db, ev))
    assert counts["sent"] == 0 and counts["delivered"] == 1 and counts["queued"] == 1


def test_demo_mode_unchanged(monkeypatch) -> None:
    monkeypatch.setenv("WHATSAPP_MODE", "mock")
    db = _db()
    ev, demo, real = _setup(db)
    assert invitations.invited_guest_ids(db, ev.id, ev) == {demo.id, real.id}
    counts = ms.summarize([demo, real], _cycle_messages(db, ev))
    assert counts["sent"] == 1 and counts["delivered"] == 1


def test_pending_row_is_not_waiting_to_send() -> None:
    db = _db()
    ev, demo, _ = _setup(db)
    db.add(models.Message(event_id=ev.id, guest_id=demo.id, direction="outbound", kind="reminder_1",
                          status="pending", provider="meta", created_at=datetime(2026, 10, 2)))
    db.commit()
    counts, rows = ms.summarize_by_type([demo], _cycle_messages(db, ev), "reminder_1", "all")
    assert counts["queued"] == 1
    assert [status for _, status, _ in rows] == ["pending"]


def test_webhook_update_marks_status_updated_at() -> None:
    db = _db()
    ev, _, real = _setup(db)
    msg = db.scalar(select(models.Message).where(models.Message.provider_message_id == "wamid.A"))
    assert msg.status_updated_at is None
    assert ms.apply_status_update(db, provider_message_id="wamid.A", status=ms.READ)
    assert msg.status_updated_at is not None and msg.status == ms.READ
    # גם עדכון כפול/מיושן — הוא עדיין סימן שה-webhook מחובר.
    first = msg.status_updated_at
    ms.apply_status_update(db, provider_message_id="wamid.A", status=ms.DELIVERED)
    assert msg.status == ms.READ and msg.status_updated_at >= first


def test_admin_webhook_health(monkeypatch) -> None:
    from datetime import timedelta

    from app.routers.admin_rsvp import _webhook_health

    db = _db()
    ev, demo, real = _setup(db)
    now = datetime(2026, 10, 1, 12, 0)
    msg = db.scalar(select(models.Message).where(models.Message.provider_message_id == "wamid.A"))
    msg.created_at = now - timedelta(hours=3)
    db.commit()

    monkeypatch.setenv("WHATSAPP_MODE", "mock")
    assert _webhook_health(db, now)["relevant"] is False

    monkeypatch.setenv("WHATSAPP_MODE", "meta")
    health = _webhook_health(db, now)
    assert health["relevant"] and health["stale"] and health["recent_real_sends"] == 1
    assert health["last_update"] is None

    ms.apply_status_update(db, provider_message_id="wamid.A", status=ms.READ)
    health = _webhook_health(db, now)
    assert not health["stale"] and health["last_update"] is not None
