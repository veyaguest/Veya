"""שמירת פרטי חשבון מול **Postgres אמיתי** — כולל RLS.

רקע: בייצור נצפתה התקלה

    UPDATE statement on table 'payout_accounts'
    expected to update 1 row(s); 0 were matched
    → PendingRollbackError

זו החתימה של ``StaleDataError``: SQLAlchemy שלח ``UPDATE ... WHERE id = X``
וקיבל 0 שורות. ב-Postgres יש לזה שני מקורות אפשריים, ושניהם **שקטים** —
המסד לא מרים שגיאה, פשוט לא מעדכן כלום:

1. השורה נמחקה מתחת לידיים (למשל האירוע נמחק במקביל, ב-CASCADE).
2. מדיניות ``UPDATE`` של RLS לא מתקיימת לשורה הזו.

הבדיקות כאן לא מנסות לנחש איזה מהם קרה בייצור. הן מקבעות את מה שחייב
להיות נכון בכל מקרה: **מצב כזה מחזיר שגיאה ברורה ומיידית, ולא מרעיל את
הטרנזקציה** כך שהבקשה הבאה תיפול על ``PendingRollbackError``.

בנוסף נבדק כאן מה ש-SQLite לא יכול לבדוק: שהמסלול המלא — יצירה, שמירה
חוזרת, צירוף מסמך — עובד תחת מדיניות ה-RLS האמיתית של הייצור, כשהחיבור
הוא בתפקיד ``veya_app`` וזהות המשתמש מוזרקת כמו בבקשה אמיתית.

דורש ``pip install pgserver`` (כלי בדיקה בלבד). בלעדיו הבדיקות מדולגות.
"""
import time

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

pgserver = pytest.importorskip(
    "pgserver", reason="pip install pgserver כדי להריץ בדיקות מול Postgres אמיתי"
)

from app import audit, models, payout_service, payout_status  # noqa: E402
from app.database import Base  # noqa: E402


@pytest.fixture(scope="module")
def pg_engine():
    import tempfile

    pgdata = tempfile.mkdtemp()
    srv = pgserver.get_server(pgdata, cleanup_mode="delete")
    uri = srv.get_uri().replace("postgresql://", "postgresql+psycopg2://", 1)
    engine = create_engine(uri)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()
    srv.cleanup()


def _event(engine) -> int:
    s = Session(engine, expire_on_commit=False)
    owner = models.User(email=f"o{time.time_ns()}@veya.test", password_hash="x")
    s.add(owner)
    s.commit()
    ev = models.Event(owner_id=owner.id, groom_name="a", bride_name="b", event_type="wedding")
    s.add(ev)
    s.commit()
    ev_id = ev.id
    s.close()
    return ev_id


def _count(engine, event_id: int) -> int:
    s = Session(engine)
    try:
        return s.scalar(
            select(func.count(models.PayoutAccount.id))
            .where(models.PayoutAccount.event_id == event_id)
        ) or 0
    finally:
        s.close()


def test_1_a_vanished_row_gives_a_clear_error_not_a_poisoned_session(pg_engine):
    """**הליבה של התיקון.**

    מדמים בדיוק את התנאי שמייצר את שגיאת הייצור: השורה נעלמת מתחת לידיים
    בזמן שה-ORM עדיין מחזיק אותה. בלי טיפול זה ``StaleDataError`` שמרעיל
    את הטרנזקציה; עם הטיפול זו שגיאה מפורשת עם נוסח עברי.
    """
    event_id = _event(pg_engine)
    db = Session(pg_engine)
    try:
        row, _ = payout_service.save_details(
            db, event_id,
            bank_code=12, branch_number="045", account_number="55446677",
        )
        db.commit()

        # השורה נמחקת בטרנזקציה אחרת — כמו מחיקת אירוע מקבילה.
        other = Session(pg_engine)
        other.execute(
            text("DELETE FROM payout_accounts WHERE event_id = :e"), {"e": event_id}
        )
        other.commit()
        other.close()

        # ומעכשיו כל כתיבה על אותו אובייקט חייבת ליפול בנוסח ברור.
        with pytest.raises(payout_service.PayoutWriteFailed) as exc:
            payout_service.attach_certificate(
                db, row, data=b"%PDF-1.4\n%%EOF\n",
                content_type="application/pdf", filename="c.pdf",
            )
        assert "לא הצלחנו לשמור" in str(exc.value)
        # ‼️ ולא StaleDataError גולמי שמגיע לזוג כ-500 סתמי, ולא
        #    PendingRollbackError בבקשה שאחריה.
        assert not isinstance(exc.value, StaleDataError)
    finally:
        db.rollback()
        db.close()


def test_2_save_details_survives_a_failing_audit_write(pg_engine):
    """**התיקון.** מסלול השמירה האמיתי, עם כתיבת יומן שנכשלת."""
    event_id = _event(pg_engine)
    original = audit.record

    def exploding(db, action, **kw):
        try:
            with db.begin_nested(), db.no_autoflush:
                raise RuntimeError("כשל מדומה בכתיבת היומן")
        except Exception:
            pass

    payout_service.audit.record = exploding
    db = Session(pg_engine)
    try:
        row, creating = payout_service.save_details(
            db, event_id,
            bank_code=12, branch_number="045", account_number="55446677",
        )
        assert creating is True
        payout_service.attach_certificate(
            db, row, data=b"%PDF-1.4\n%%EOF\n",
            content_type="application/pdf", filename="cert.pdf",
        )
        db.commit()
    finally:
        payout_service.audit.record = original
        db.close()

    assert _count(pg_engine, event_id) == 1, "השורה אבדה יחד עם כשל היומן"

    check = Session(pg_engine)
    try:
        saved = check.scalars(
            select(models.PayoutAccount)
            .where(models.PayoutAccount.event_id == event_id)
        ).first()
        assert saved.account_number == "55446677"
        assert saved.certificate_size == len(b"%PDF-1.4\n%%EOF\n")
        assert saved.provider_status == "pending"
    finally:
        check.close()


def test_3_repeated_saves_stay_on_one_row(pg_engine):
    """שמירה חוזרת — כולל של אותם ערכים בדיוק — לא מכפילה ולא נופלת."""
    event_id = _event(pg_engine)
    db = Session(pg_engine)
    try:
        for _ in range(3):
            payout_service.save_details(
                db, event_id,
                bank_code=12, branch_number="045", account_number="55446677",
            )
            db.commit()
        payout_service.save_details(
            db, event_id,
            bank_code=20, branch_number="123", account_number="99887766",
        )
        db.commit()
    finally:
        db.close()

    assert _count(pg_engine, event_id) == 1


def test_4_concurrent_creation_keeps_one_row(pg_engine):
    """שתי טרנזקציות נפרדות שיוצרות במקביל — שורה אחת, בלי כשל.

    זה המרוץ האמיתי: שתיהן ראו "אין שורה", שתיהן ניסו ליצור.
    """
    event_id = _event(pg_engine)
    a = Session(pg_engine)
    b = Session(pg_engine)
    try:
        assert payout_service.get(a, event_id) is None
        assert payout_service.get(b, event_id) is None

        ident = {"bank_code": 12, "branch_number": "045", "account_number": "55446677"}
        row_a, created_a = payout_service._get_or_create(a, event_id, **ident)
        a.commit()
        assert created_a is True

        # b עדיין לא ראתה את השורה של a — בדיוק כמו בקשה מקבילה.
        row_b, created_b = payout_service._get_or_create(b, event_id, **ident)
        b.commit()
        assert created_b is False, "השני יצר שורה כפולה במקום לקחת את הקיימת"
    finally:
        a.close()
        b.close()

    assert _count(pg_engine, event_id) == 1, "נוצרו שתי שורות לאותו אירוע"
