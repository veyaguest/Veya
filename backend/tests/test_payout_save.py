"""בדיקות לשמירת פרטי חשבון — ``PUT /payout``.

הקובץ נולד מתקלת ייצור אמיתית:

    UPDATE statement on table 'payout_accounts'
    expected to update 1 row(s); 0 were matched
    → PendingRollbackError

**השורש:** שורת החשבון החדשה נשארה "ממתינה" ב-ORM עד ה-autoflush הראשון,
וה-autoflush הראשון קרה בתוך ה-SAVEPOINT של ``audit.record``. כשל שם
גלגל אחורה גם את ה-INSERT — בשקט, כי ``audit.record`` בולע שגיאות — בעוד
ה-ORM המשיך להחזיק אובייקט ``persistent`` עם מזהה שאין לו שורה. ה-``UPDATE``
הבא עליו מצא 0 שורות והרעיל את הטרנזקציה.

**למה זה לא נתפס בפיתוח:** ב-SQLite ה-SAVEPOINT כמעט חסר-משמעות (מגבלה
ידועה של pysqlite), ולכן ה-INSERT שרד שם תמיד. הבאג היה גלוי רק מול
Postgres. הבדיקה ``test_creation_survives_a_failing_audit_write`` מדמה את
הכשל במפורש ולכן תופסת אותו גם על SQLite.

הרצה: ``venv/bin/python tests/test_payout_save.py``
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402

from app import audit, models, payout_service, payout_status  # noqa: E402
from app.database import SessionLocal, set_request_identity  # noqa: E402
from tests.e2e_seating import bootstrap, register, shutdown  # noqa: E402

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
PDF_URL = "data:application/pdf;base64," + base64.b64encode(PDF).decode()

ACCOUNT = "55446677"


def _body(**over):
    b = {"bank_code": 12, "branch_number": "045",
         "account_number": ACCOUNT, "certificate": PDF_URL}
    b.update(over)
    return b


def _put(api, headers=None, **over):
    return api.client.put("/payout", headers=headers or api.headers, json=_body(**over))


def _rows(event_id: int) -> int:
    set_request_identity(None)
    db = SessionLocal()
    try:
        return db.scalar(
            select(func.count(models.PayoutAccount.id))
            .where(models.PayoutAccount.event_id == event_id)
        ) or 0
    finally:
        db.close()


# ── 1. יצירה ראשונה ──────────────────────────────────────────────────────


def test_first_save_creates_and_persists() -> None:
    """המקרה שנשבר בייצור: אירוע בלי שורת payout, שמירה ראשונה עם אישור."""
    api, _ = bootstrap()
    assert _rows(api.event_id) == 0, "האירוע אמור להתחיל בלי שורת חשבון"

    r = _put(api)
    assert r.status_code == 200, f"שמירה ראשונה נכשלה: {r.status_code} {r.text}"

    body = r.json()
    assert body["configured"] is True
    assert body["bank_name"] and body["branch_number"] == "045"
    assert body["account_number_masked"].endswith(ACCOUNT[-4:])
    assert body["certificate"]["content_type"] == "application/pdf"
    assert body["status"] == payout_status.MISSING
    assert body["provider_status"] == "pending", "עמודת הספק נשארה ריקה ביצירה"

    # ובאמת נכתב למסד — לא רק חזר ב-JSON.
    assert _rows(api.event_id) == 1
    set_request_identity(None)
    db = SessionLocal()
    try:
        row = db.scalars(select(models.PayoutAccount)
                         .where(models.PayoutAccount.event_id == api.event_id)).first()
        assert row.account_number == ACCOUNT
        assert row.certificate_size == len(PDF)
        assert row.provider_status == "pending"
    finally:
        db.close()
    print("✓ שמירה ראשונה יוצרת שורה ונכתבת למסד מקצה לקצה")


def test_creation_survives_a_failing_audit_write() -> None:
    """**בדיקת הרגרסיה של התקלה עצמה.**

    מפילים במכוון את כתיבת היומן. ``audit.record`` בולע את הכשל, אבל
    ה-SAVEPOINT שלו לא אמור לגרור איתו את יצירת השורה — היא כבר נכתבה
    בטרנזקציה החיצונית לפני שהיומן נקרא בכלל.
    """
    api, _ = bootstrap()
    original = audit.record

    def exploding(db, action, **kw):
        # מדמה בדיוק את מה שקורה ב-Postgres: השגיאה נזרקת בתוך ה-SAVEPOINT,
        # ואז נבלעת — כמו כל כשל אמיתי בכתיבת היומן.
        try:
            with db.begin_nested(), db.no_autoflush:
                raise RuntimeError("כשל מדומה בכתיבת היומן")
        except Exception:
            pass

    audit.record = exploding
    payout_service.audit.record = exploding
    try:
        r = _put(api)
        assert r.status_code == 200, (
            f"שמירה נכשלה כשהיומן נכשל: {r.status_code} {r.text}"
        )
    finally:
        audit.record = original
        payout_service.audit.record = original

    assert _rows(api.event_id) == 1, "השורה אבדה יחד עם כשל היומן"
    body = api.client.get("/payout", headers=api.headers).json()
    assert body["configured"] is True
    assert body["account_number_masked"].endswith(ACCOUNT[-4:])
    print("✓ כשל בכתיבת היומן אינו מבטל את יצירת השורה")


# ── 2. שמירה חוזרת ───────────────────────────────────────────────────────


def test_resaving_identical_details_is_idempotent() -> None:
    """שמירה חוזרת של אותם פרטים בדיוק — לא נופלת, ולא יוצרת שורה שנייה."""
    api, _ = bootstrap()
    assert _put(api).status_code == 200

    for attempt in range(3):
        r = _put(api)
        assert r.status_code == 200, f"שמירה חוזרת #{attempt + 2} נכשלה: {r.text}"

    assert _rows(api.event_id) == 1, "שמירה חוזרת יצרה שורה נוספת"
    body = api.client.get("/payout", headers=api.headers).json()
    assert body["account_number_masked"].endswith(ACCOUNT[-4:])
    assert body["status"] == payout_status.MISSING
    print("✓ שמירה חוזרת של אותם פרטים עוברת ואינה מכפילה שורות")


def test_resaving_changed_details_updates_in_place() -> None:
    api, _ = bootstrap()
    assert _put(api).status_code == 200

    r = _put(api, bank_code=20, branch_number="123",
             account_number="99887766", certificate=None)
    assert r.status_code == 200, r.text

    assert _rows(api.event_id) == 1
    body = api.client.get("/payout", headers=api.headers).json()
    assert body["bank_code"] == 20
    assert body["branch_number"] == "123"
    assert body["account_number_masked"].endswith("7766")
    # האישור שכבר הועלה נשמר — לא צריך להעלות אותו שוב בכל עדכון.
    assert body["certificate"] is not None
    print("✓ עדכון פרטים כותב על אותה שורה ושומר את האישור הקיים")


def test_certificate_can_be_replaced_on_an_existing_row() -> None:
    api, _ = bootstrap()
    assert _put(api).status_code == 200

    bigger = PDF + b"%" * 500
    url = "data:application/pdf;base64," + base64.b64encode(bigger).decode()
    r = _put(api, certificate=url)
    assert r.status_code == 200, r.text
    assert r.json()["certificate"]["size"] == len(bigger)
    assert _rows(api.event_id) == 1
    print("✓ החלפת אישור ניהול חשבון על שורה קיימת עובדת")


# ── 3. אירוע בלי שורת payout ─────────────────────────────────────────────


def test_reading_an_event_without_a_payout_row() -> None:
    """קריאה לאירוע שאין לו שורה — מצב ריק תקין, לא שגיאה, ובלי ליצור שורה."""
    api, _ = bootstrap()
    r = api.client.get("/payout", headers=api.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["configured"] is False
    assert body["status"] == payout_status.MISSING
    assert body["locked"] is False
    assert body["bank_code"] is None and body["certificate"] is None
    assert _rows(api.event_id) == 0, "קריאה בלבד יצרה שורה"

    # והגשה לפני שיש פרטים נחסמת בנוסח ברור ולא בשגיאת מסד.
    r = api.client.post("/payout/submit", headers=api.headers)
    assert r.status_code == 409, r.status_code
    assert "אין פרטי חשבון" in r.json()["detail"]
    print("✓ אירוע בלי שורת חשבון: מצב ריק תקין, בלי יצירה ובלי קריסה")


def test_saving_without_a_certificate_on_a_new_event_is_refused_cleanly() -> None:
    """שמירה ראשונה בלי אישור נדחית — **ובלי להשאיר שורה חלקית מאחור.**"""
    api, _ = bootstrap()
    r = _put(api, certificate=None)
    assert r.status_code == 422, r.status_code

    # הבקשה נדחתה, ולכן הטרנזקציה התגלגלה אחורה במלואה.
    assert _rows(api.event_id) == 0, "נשארה שורת חשבון אחרי בקשה שנדחתה"
    assert api.client.get("/payout", headers=api.headers).json()["configured"] is False

    # והמסלול התקין מיד אחריה עדיין עובד — הסשן לא הורעל.
    assert _put(api).status_code == 200
    assert _rows(api.event_id) == 1
    print("✓ דחייה בשמירה ראשונה לא משאירה שורה חלקית, וההמשך עובד")


# ── 4. בידוד בין אירועים ─────────────────────────────────────────────────


def test_saving_to_another_users_event_is_blocked() -> None:
    owner_a, _ = bootstrap()
    owner_b, _ = bootstrap()

    # בעלים א׳ מנסה לכתוב לאירוע של ב׳ — 404, בלי לחשוף שהאירוע קיים.
    r = api_put_cross = owner_a.client.put(
        "/payout",
        headers={"Authorization": owner_a.headers["Authorization"],
                 "X-Event-Id": str(owner_b.event_id)},
        json=_body(account_number="11112222"),
    )
    assert r.status_code == 404, f"כתיבה חוצת-אירועים החזירה {r.status_code}"
    assert _rows(owner_b.event_id) == 0, "נוצרה שורה באירוע של משתמש אחר"

    # וגם חבר-אירוע עם הרשאת צפייה במתנות אינו נוגע בחשבון הבנק.
    member_token = register(owner_b.client)
    set_request_identity(None)
    db = SessionLocal()
    try:
        member = db.scalars(select(models.User).order_by(models.User.id.desc())).first()
        db.add(models.EventMember(
            event_id=owner_b.event_id, user_id=member.id,
            role="producer", status="active", permissions=["view_reports"],
        ))
        db.commit()
    finally:
        db.close()

    r = owner_b.client.put("/payout", headers={
        "Authorization": f"Bearer {member_token}",
        "X-Event-Id": str(owner_b.event_id),
    }, json=_body())
    assert r.status_code in (403, 404), f"מפיק כתב לחשבון הבנק ({r.status_code})"
    assert _rows(owner_b.event_id) == 0

    # ובעלים ב׳ עצמו — כן.
    assert _put(owner_b).status_code == 200
    assert _rows(owner_b.event_id) == 1
    assert _rows(owner_a.event_id) == 0, "השמירה של ב׳ נגעה באירוע של א׳"
    print("✓ אין כתיבה לאירוע של משתמש אחר, וגם לא ע\"י חבר-אירוע")


# ── 5. חשבון נעול ────────────────────────────────────────────────────────


def test_a_locked_account_stays_locked_through_the_save_path() -> None:
    api, _ = bootstrap()
    assert _put(api).status_code == 200
    api.client.post("/payout/submit", headers=api.headers)

    set_request_identity(None)
    db = SessionLocal()
    try:
        payout_service.set_status(db, api.event_id, payout_status.UNDER_REVIEW)
        payout_service.set_status(db, api.event_id, payout_status.VERIFIED)
        db.commit()
    finally:
        db.close()

    assert api.client.get("/payout", headers=api.headers).json()["locked"] is True

    # שינוי פרטים, החלפת מסמך, ואפילו שמירה של **אותם ערכים בדיוק** —
    # כולן נדחות. הנעילה אינה תלויה בשאלה אם משהו באמת השתנה.
    for label, over in (
        ("פרטים אחרים", {"bank_code": 20, "branch_number": "123",
                         "account_number": "99887766", "certificate": None}),
        ("מסמך חדש", {"certificate": PDF_URL}),
        ("אותם ערכים", {}),
    ):
        r = _put(api, **over)
        assert r.status_code == 409, f"{label}: התקבל {r.status_code}"

    body = api.client.get("/payout", headers=api.headers).json()
    assert body["status"] == payout_status.VERIFIED
    assert body["account_number_masked"].endswith(ACCOUNT[-4:])
    assert _rows(api.event_id) == 1
    print("✓ חשבון נעול נשאר נעול בכל וריאציה של שמירה")


# ── מרוץ יצירה ───────────────────────────────────────────────────────────


def test_concurrent_creation_does_not_duplicate_or_fail() -> None:
    """שתי בקשות שרואות "אין שורה" ומנסות ליצור — אחת מנצחת, השנייה נופלת
    בחזרה לשורה שלה, ואף אחת לא נכשלת."""
    api, _ = bootstrap()

    set_request_identity(None)
    first, second = SessionLocal(), SessionLocal()
    try:
        # שני הסשנים רואים "אין שורה" — בדיוק המצב של שתי בקשות במקביל.
        assert payout_service.get(first, api.event_id) is None
        assert payout_service.get(second, api.event_id) is None

        ident = {"bank_code": 12, "branch_number": "045", "account_number": ACCOUNT}
        row_a, created_a = payout_service._get_or_create(first, api.event_id, **ident)
        first.commit()

        row_b, created_b = payout_service._get_or_create(second, api.event_id, **ident)
        second.commit()

        assert created_a is True, "הראשון לא יצר"
        assert created_b is False, "השני יצר שורה כפולה במקום לקחת את הקיימת"
        assert row_a.event_id == row_b.event_id
    finally:
        first.close()
        second.close()

    assert _rows(api.event_id) == 1, "נוצרו שתי שורות לאותו אירוע"
    print("✓ מרוץ יצירה: שורה אחת, בלי כשל ובלי כפילות")


if __name__ == "__main__":
    try:
        test_first_save_creates_and_persists()
        test_creation_survives_a_failing_audit_write()

        test_resaving_identical_details_is_idempotent()
        test_resaving_changed_details_updates_in_place()
        test_certificate_can_be_replaced_on_an_existing_row()

        test_reading_an_event_without_a_payout_row()
        test_saving_without_a_certificate_on_a_new_event_is_refused_cleanly()

        test_saving_to_another_users_event_is_blocked()
        test_a_locked_account_stays_locked_through_the_save_path()
        test_concurrent_creation_does_not_duplicate_or_fail()
        print("\nכל בדיקות שמירת פרטי החשבון עברו ✓")
    finally:
        shutdown()
