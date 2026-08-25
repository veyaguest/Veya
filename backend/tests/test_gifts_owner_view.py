"""בדיקות למסך "מתנות באשראי" של בעלי האירוע (GET /gifts).

מה שהקובץ הזה שומר עליו:

1. **הסיכום נספר רק מ-``paid``.** מתנה שנכשלה/ננטשה/ממתינה לא נכנסת
   לסכום או לספירה, אבל **כן** מופיעה ברשימה (כדי שבעלי האירוע יראו גם
   ניסיונות שלא הצליחו).
2. **שלושת הסכומים מוצגים בנפרד** — מה שהאירוע מקבל, העמלה, ומה שהאורח
   שילם. לא סכום מאוחד אחד.
3. **הרשאות/בידוד** — רק בעלים/הרשאה מתאימה, ואף פעם לא אירוע אחר.

הרצה: ``venv/bin/python tests/test_gifts_owner_view.py`` (עצמאי, בלי pytest).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["VEYA_GIFT_ENABLED"] = "1"

from app import gift_service, gift_status, guest_journey, models  # noqa: E402
from app.database import SessionLocal, set_request_identity  # noqa: E402
from tests.e2e_seating import bootstrap, register, shutdown  # noqa: E402


def _set_event(api, **fields):
    r = api.client.patch("/event", headers=api.headers, json=fields)
    assert r.status_code == 200, f"עדכון אירוע נכשל: {r.status_code} {r.text}"
    return r.json()


def _event_date_in(days: int) -> str:
    from datetime import timedelta

    return (guest_journey.today_in_israel() + timedelta(days=days)).isoformat()


def _guest_with_token(api, name: str, phone: str):
    g = api.add_guest(name, phone)
    set_request_identity(None)
    db = SessionLocal()
    try:
        tok = db.get(models.Guest, g["id"]).guest_token
    finally:
        db.close()
    return g, tok


def verify_payout(event_id: int) -> None:
    """מסמן את חשבון קבלת המתנות של האירוע כמאומת בשתי הבדיקות.

    **בלי זה השרת לא מחזיר סכומים בכלל** — לא בסיכום ולא בשורות (ראו
    ``routers/gifts.py``). הבדיקות כאן עוסקות בחישוב הסכומים ובהרשאות,
    ולכן הן מתחילות מחשבון מאומת; השער עצמו נבדק בקובץ נפרד,
    ``test_gift_amount_gating.py``.

    הכתיבה כאן ישירה למסד ולא דרך ה-API בכוונה: אין — ולא צריך להיות —
    נתיב שבו בעלי האירוע מאשרים את עצמם.
    """
    set_request_identity(None)
    db = SessionLocal()
    try:
        row = models.PayoutAccount(
            event_id=event_id, bank_code=12, branch_number="045",
            account_number="123456",
            status="verified", provider_status="approved",
        )
        db.add(row)
        db.commit()
    finally:
        db.close()


def _ready_event(days: int = 1, *, payout_verified: bool = True):
    api, _ = bootstrap()
    _set_event(api, event_date=_event_date_in(days), event_time="19:30",
               venue_address="הרצל 5, תל אביב")
    if payout_verified:
        verify_payout(api.event_id)
    return api


def _checkout(api, tok, agorot, *, giver="", blessing=None, key=None, simulate="success"):
    return api.client.post(f"/confirm/{tok}/gift/checkout", json={
        "gift_amount_agorot": agorot,
        "giver_name": giver,
        "blessing": blessing,
        "idempotency_key": key,
        "simulate": simulate,
    }).json()


# ---- 1. הסיכום נספר רק מ-paid --------------------------------------------

def test_summary_counts_only_paid() -> None:
    api = _ready_event()
    g, tok = _guest_with_token(api, "בודק סיכום", "0502220001")

    _checkout(api, tok, 50000, giver="דנה", key="paid-1", simulate="success")
    _checkout(api, tok, 10000, giver="נכשל", key="paid-2", simulate="failure")
    _checkout(api, tok, 20000, giver="רותי", key="paid-3", simulate="success")

    r = api.client.get("/gifts", headers=api.headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["paid_count"] == 2, "רק שתי המתנות המוצלחות נספרות"
    assert body["total_count"] == 3, "אבל כל השלוש מופיעות ברשימה"
    assert body["total_received_agorot"] == 70000, "500+200, לא 500+100+200"
    assert body["total_received_display"] == "₪700"
    assert len(body["gifts"]) == 3, "העסקה שנכשלה עדיין מופיעה ברשימה"
    statuses = {row["status"] for row in body["gifts"]}
    assert statuses == {gift_status.PAID, gift_status.FAILED}
    print("✓ הסיכום נספר רק מ-paid; העסקה שנכשלה מופיעה ברשימה אך לא בסכום")


def test_pending_and_cancelled_excluded_from_total() -> None:
    """עסקה שנשארה pending (לא עברה דרך הספק בכלל) לא נספרת, וגם לא cancelled."""
    api = _ready_event()
    g, tok = _guest_with_token(api, "לא הושלם", "0502220002")

    set_request_identity(None)
    db = SessionLocal()
    try:
        guest = db.get(models.Guest, g["id"])
        pending_row, _ = gift_service.create_gift(
            db, guest, gift_amount_agorot=30000, client_idempotency_key="stuck-pending")
        cancelled_row, _ = gift_service.create_gift(
            db, guest, gift_amount_agorot=40000, client_idempotency_key="user-cancelled")
        gift_service.set_status(db, cancelled_row, gift_status.CANCELLED)
        db.commit()
    finally:
        db.close()

    r = api.client.get("/gifts", headers=api.headers).json()
    assert r["paid_count"] == 0
    assert r["total_received_agorot"] == 0
    assert r["total_count"] == 2, "שתיהן עדיין ברשימה, לצפייה"
    print("✓ pending ו-cancelled לא נספרות בסכום, אבל נראות ברשימה")


def test_refunded_excluded_from_total() -> None:
    """מתנה שהוחזרה כבר לא 'מתקבלת' — לא נכללת בסכום, גם שהייתה paid בעבר."""
    api = _ready_event()
    g, tok = _guest_with_token(api, "מוחזר", "0502220003")
    _checkout(api, tok, 50000, giver="מוחזר", key="refund-flow")

    set_request_identity(None)
    db = SessionLocal()
    try:
        row = db.query(models.Gift).filter_by(idempotency_key="g%d:%s" % (
            g["id"], __import__("hashlib").sha256(b"refund-flow").hexdigest()[:32]
        )).one_or_none()
        assert row is not None and row.status == gift_status.PAID
        gift_service.set_status(db, row, gift_status.REFUNDED)
        db.commit()
    finally:
        db.close()

    r = api.client.get("/gifts", headers=api.headers).json()
    assert r["paid_count"] == 0, "מתנה שהוחזרה לא 'התקבלה'"
    assert r["total_received_agorot"] == 0
    assert r["gifts"][0]["status"] == gift_status.REFUNDED
    print("✓ מתנה שהוחזרה יוצאת מהסכום, גם שהייתה paid קודם")


# ---- 2. רק סכום המתנה — בלי עמלה ובלי הסכום ששולם -------------------------

# בדיוק השדות שבעלי האירוע אמורים לקבל, ותו לא.
OWNER_ROW_FIELDS = {"id", "sender_name", "message", "gift_amount_agorot",
                    "status", "created_at"}

# שדות שאסור שיופיעו בתשובת בעלי האירוע: עמלת VEYA, הסכום ששילם המוזמן,
# ומידע תפעולי פנימי של העסקה.
FORBIDDEN_ROW_FIELDS = {
    "fee_agorot", "total_agorot", "fee_percent", "currency",
    "provider", "provider_transaction_id", "idempotency_key",
    "event_id", "guest_id",
}


def test_owner_row_exposes_only_display_fields() -> None:
    """התשובה מכילה בדיוק את שדות התצוגה — לא יותר.

    בדיקת *קבוצה מדויקת* ולא רק "אין עמלה": כך גם עמודה חדשה שתתווסף
    לטבלת ``gifts`` בעתיד (למשל פרטי ספק סליקה) תיתפס כאן אם היא תזלוג
    בטעות לתשובה, בלי שאף אחד יזכור לעדכן את הבדיקה.
    """
    api = _ready_event()
    g, tok = _guest_with_token(api, "בדיקת שדות", "0502220004")
    _checkout(api, tok, 50000, giver="דנה", blessing="מזל טוב", key="amounts-1")

    row = api.client.get("/gifts", headers=api.headers).json()["gifts"][0]
    assert set(row) == OWNER_ROW_FIELDS, (
        f"שדות לא צפויים: {set(row) ^ OWNER_ROW_FIELDS}"
    )
    assert row["gift_amount_agorot"] == 50000, "מה שהאירוע מקבל — במלואו"
    assert row["sender_name"] == "דנה" and row["message"] == "מזל טוב"
    print(f"✓ שורת מתנה מכילה בדיוק {len(OWNER_ROW_FIELDS)} שדות תצוגה, בלי עמלה")


def test_fee_and_total_absent_from_owner_payload() -> None:
    """עמלת השירות והסכום ששולם אינם קיימים בתשובה — לא כשדה ולא כמספר."""
    api = _ready_event()
    g, tok = _guest_with_token(api, "בלי עמלה", "0502220014")
    _checkout(api, tok, 50000, giver="דנה", key="no-fee-1")
    _checkout(api, tok, 18000, giver="יוסי", key="no-fee-2")

    body = api.client.get("/gifts", headers=api.headers)
    data = body.json()

    # ברמת המבנה: אף שדה אסור, בשום שורה ובשום מקום בסיכום.
    for row in data["gifts"]:
        leaked = set(row) & FORBIDDEN_ROW_FIELDS
        assert not leaked, f"שדות אסורים דלפו לשורה: {leaked}"
    assert "total_fees_agorot" not in data, "סכום העמלות עדיין מוחזר בסיכום"

    # ברמת התוכן הגולמי: גם המספרים עצמם לא מופיעים ב-JSON, בשום שדה.
    # ₪500 → עמלה 2000 אג׳, סה"כ 52000 אג׳; ₪180 → 720 / 18720.
    # מחפשים את המספר כערך שלם (\b) ולא כתת-מחרוזת, כדי ש-52000 לא ייחשב
    # בטעות כ"2000" — ובלי תלות ברווחים בעיצוב ה-JSON.
    import re

    raw = body.text
    for forbidden_number in ("2000", "52000", "720", "18720"):
        assert not re.search(rf"(?<!\d){forbidden_number}(?!\d)", raw), (
            f"המספר {forbidden_number} (עמלה/סה\"כ) נמצא בתשובה"
        )
    print("✓ עמלה וסכום ששולם לא קיימים בתשובה — לא כשדה ולא כערך")


def test_summary_has_no_fee_information() -> None:
    api = _ready_event()
    g, tok = _guest_with_token(api, "סיכום נקי", "0502220015")
    _checkout(api, tok, 50000, giver="דנה", key="clean-summary")

    data = api.client.get("/gifts", headers=api.headers).json()
    assert set(data) == {
        "amounts_visible",
        "total_received_agorot", "total_received_display",
        "paid_count", "total_count", "gifts",
    }, f"שדות סיכום לא צפויים: {set(data)}"
    assert data["total_received_agorot"] == 50000, "מה שהאירוע קיבל"
    assert data["total_received_display"] == "₪500"
    print("✓ הסיכום מכיל רק מה שהאירוע קיבל — בלי סכום עמלות")


def test_guest_facing_endpoints_still_show_the_fee() -> None:
    """אי-רגרסיה: **למוזמן** העמלה חייבת להישאר גלויה.

    ההסתרה היא של מסך בעלי האירוע בלבד. נותן המתנה הוא זה שמשלם את
    העמלה, ולכן חייב לראות אותה במלואה לפני התשלום — זו התחייבות
    השקיפות שבתנאי השימוש (סעיף 18.5.1).
    """
    api = _ready_event()
    g, tok = _guest_with_token(api, "רואה עמלה", "0502220016")

    quote = api.client.post(f"/confirm/{tok}/gift/quote",
                            json={"gift_amount_agorot": 50000}).json()
    assert quote["fee_agorot"] == 2000, "המוזמן חייב לראות את העמלה"
    assert quote["total_agorot"] == 52000, "והסכום שהוא ישלם בפועל"
    assert quote["fee_percent"] == 4

    checkout = api.client.post(f"/confirm/{tok}/gift/checkout", json={
        "gift_amount_agorot": 50000, "idempotency_key": "guest-sees-fee"}).json()
    assert checkout["quote"]["fee_agorot"] == 2000
    assert checkout["quote"]["total_agorot"] == 52000
    print("✓ אי-רגרסיה: המוזמן עדיין רואה עמלה וסה\"כ — ההסתרה היא בצד הבעלים בלבד")


def test_fee_still_stored_in_database() -> None:
    """אי-רגרסיה: העמלה עדיין נשמרת בטבלה — זו הגבלת תצוגה, לא מחיקת נתונים."""
    from sqlalchemy import select

    from app.database import SessionLocal as SL

    api = _ready_event()
    g, tok = _guest_with_token(api, "נשמר ב-DB", "0502220017")
    _checkout(api, tok, 50000, giver="דנה", key="db-keeps-fee")

    set_request_identity(None)
    db = SL()
    try:
        row = db.scalar(
            select(models.Gift).where(models.Gift.guest_id == g["id"])
        )
        assert row.fee_agorot == 2000, "העמלה חייבת להישאר בטבלה"
        assert row.total_agorot == 52000, "והסכום הכולל גם"
        assert row.currency == "ILS"
    finally:
        db.close()
    print("✓ אי-רגרסיה: fee/total/currency עדיין בטבלה — רק לא בתשובת ה-API")


def test_no_card_data_in_response() -> None:
    api = _ready_event()
    g, tok = _guest_with_token(api, "אין אשראי", "0502220005")
    _checkout(api, tok, 50000, giver="בודק", key="no-card")
    body = api.client.get("/gifts", headers=api.headers).text
    for forbidden in ("card", "cvv", "cvc", "pan", "expiry"):
        assert forbidden not in body.lower(), f"נמצא '{forbidden}' בתשובה"
    print("✓ אין שום רמז לנתוני אשראי בתשובת ה-API")


# ---- 3. שם, ברכה, תאריך, סטטוס --------------------------------------------

def test_row_fields_complete() -> None:
    api = _ready_event()
    g, tok = _guest_with_token(api, "יעל ברקוביץ", "0502220006")
    _checkout(api, tok, 18000, giver="יעל ברקוביץ", blessing="מאחלים אושר!", key="fields-1")

    row = api.client.get("/gifts", headers=api.headers).json()["gifts"][0]
    assert row["sender_name"] == "יעל ברקוביץ"
    assert row["message"] == "מאחלים אושר!"
    assert row["status"] == gift_status.PAID
    assert row["created_at"], "חייב תאריך"
    assert row["id"] > 0
    print("✓ שם נותן המתנה, ברכה, תאריך וסטטוס — כל השדות מלאים")


def test_missing_blessing_falls_back_to_none() -> None:
    """ברכה היא אופציונלית — לא ניתנת אחת, מוצג None ולא מחרוזת ריקה."""
    api = _ready_event()
    g, tok = _guest_with_token(api, "בלי ברכה", "0502220007")
    # giver="" בכוונה: gift_service נופל לשם המוזמן עצמו (guest.full_name) —
    # זו כבר ההתנהגות הקיימת ונבדקת ב-test_gift_transactions.py. כאן בודקים
    # רק את הברכה.
    _checkout(api, tok, 10000, giver="", key="no-blessing")

    row = api.client.get("/gifts", headers=api.headers).json()["gifts"][0]
    assert row["message"] is None, "ברכה שלא ניתנה חייבת להיות None, לא מחרוזת ריקה"
    assert row["sender_name"] == "בלי ברכה", "בלי שם נותן מפורש, נופל לשם המוזמן"
    print("✓ ברכה חסרה → None; בלי שם נותן מפורש → נופל לשם המוזמן")


def test_gift_with_no_sender_name_at_all_shows_fallback() -> None:
    """המקרה שבו גם giver וגם שם המוזמן ריקים — ``_row_read`` נופל ל'אורח'."""
    from app.database import SessionLocal as SL

    api = _ready_event()
    g, tok = _guest_with_token(api, "יעל", "0502220099")

    set_request_identity(None)
    db = SL()
    try:
        guest = db.get(models.Guest, g["id"])
        row, _ = gift_service.create_gift(
            db, guest, gift_amount_agorot=5000, sender_name="",
            client_idempotency_key="blank-sender")
        # מדמים שורה שנוצרה בלי שם נותן בכלל (עוקף את הנפילה ל-full_name
        # שכבר קיימת ב-gift_service, כדי לבדוק את שכבת התצוגה עצמה).
        row.sender_name = ""
        db.commit()
    finally:
        db.close()

    displayed = api.client.get("/gifts", headers=api.headers).json()["gifts"][0]
    assert displayed["sender_name"] == "מוזמן"
    print("✓ שורה בלי שם נותן כלל → מוצגת כ-'מוזמן', לא ריקה")


# ---- 4. הרשאות ------------------------------------------------------------

def test_requires_authentication() -> None:
    api = _ready_event()
    r = api.client.get("/gifts")
    assert r.status_code == 401, f"בלי התחברות בכלל: {r.status_code}"
    print("✓ בלי התחברות: 401")


def test_owner_can_view_own_gifts() -> None:
    api = _ready_event()
    g, tok = _guest_with_token(api, "לבעלים", "0502220008")
    _checkout(api, tok, 50000, giver="דנה", key="owner-view")
    r = api.client.get("/gifts", headers=api.headers)
    assert r.status_code == 200 and r.json()["paid_count"] == 1
    print("✓ הבעלים רואה את המתנות של האירוע שלו")


def test_member_with_view_permission_can_see_gifts() -> None:
    """חבר-אירוע עם view_reports/view_event רואה — לא כל הרשאה אחרת."""
    from app.database import SessionLocal as SL

    api = _ready_event()
    g, tok = _guest_with_token(api, "חבר צפייה", "0502220009")
    _checkout(api, tok, 30000, giver="בודק", key="member-view")

    member_token = register(api.client)
    set_request_identity(None)
    db = SL()
    try:
        member = db.execute(
            __import__("sqlalchemy").select(models.User)
        ).scalars().all()
        member_user = [u for u in member if u.email.startswith("test-")][-1]
        db.add(models.EventMember(
            event_id=api.event_id, user_id=member_user.id,
            role="producer", status="active", permissions=["view_reports"],
        ))
        db.commit()
    finally:
        db.close()

    r = api.client.get("/gifts", headers={
        "Authorization": f"Bearer {member_token}", "X-Event-Id": str(api.event_id)
    })
    assert r.status_code == 200, r.text
    assert r.json()["paid_count"] == 1
    print("✓ חבר-אירוע עם view_reports רואה את המתנות")


def test_member_without_view_permission_is_blocked() -> None:
    """חבר-אירוע עם הרשאת עריכה בלבד (למשל edit_guests) — לא רואה מתנות."""
    from app.database import SessionLocal as SL

    api = _ready_event()
    g, tok = _guest_with_token(api, "חבר בלי הרשאה", "0502220010")
    _checkout(api, tok, 30000, giver="בודק", key="member-blocked")

    member_token = register(api.client)
    set_request_identity(None)
    db = SL()
    try:
        member = db.execute(
            __import__("sqlalchemy").select(models.User)
        ).scalars().all()
        member_user = [u for u in member if u.email.startswith("test-")][-1]
        db.add(models.EventMember(
            event_id=api.event_id, user_id=member_user.id,
            role="producer", status="active", permissions=["edit_guests"],
        ))
        db.commit()
    finally:
        db.close()

    r = api.client.get("/gifts", headers={
        "Authorization": f"Bearer {member_token}", "X-Event-Id": str(api.event_id)
    })
    assert r.status_code == 403, (
        f"edit_guests לבדו לא אמור לאפשר צפייה במתנות, קיבלנו {r.status_code}"
    )
    print("✓ חבר-אירוע עם edit_guests בלבד (בלי view_reports/view_event) נחסם — 403")


def test_no_cross_event_access() -> None:
    api_a = _ready_event()
    g, tok = _guest_with_token(api_a, "אירוע א׳", "0502220011")
    _checkout(api_a, tok, 50000, giver="דנה", key="isolation-a")

    api_b = _ready_event()

    # בעלים א׳ עם X-Event-Id של אירוע ב׳ — 404, לא נחשף שהאירוע קיים.
    r = api_a.client.get("/gifts", headers={
        "Authorization": api_a.headers["Authorization"], "X-Event-Id": str(api_b.event_id)
    })
    assert r.status_code == 404

    # בעלים ב׳ רואה רשימה ריקה משלו — לא את המתנות של א׳.
    r = api_b.client.get("/gifts", headers=api_b.headers)
    assert r.status_code == 200
    assert r.json() == {
        "amounts_visible": True,
        "total_received_agorot": 0, "total_received_display": "₪0",
        "paid_count": 0, "total_count": 0, "gifts": [],
    }
    print("✓ אין גישה חוצת-אירועים: X-Event-Id זר → 404, ואירוע אחר לא רואה כלום")


# ---- 5. יציבות סדר -------------------------------------------------------

def test_ordering_is_deterministic_for_same_timestamp() -> None:
    """שתי מתנות באותה שנייה עדיין חייבות סדר עקבי (id כשובר שוויון)."""
    api = _ready_event()
    g, tok = _guest_with_token(api, "סדר", "0502220012")
    _checkout(api, tok, 10000, giver="ראשון", key="order-1")
    _checkout(api, tok, 20000, giver="שני", key="order-2")
    _checkout(api, tok, 30000, giver="שלישי", key="order-3")

    first = api.client.get("/gifts", headers=api.headers).json()["gifts"]
    second = api.client.get("/gifts", headers=api.headers).json()["gifts"]
    assert [r["id"] for r in first] == [r["id"] for r in second], "הסדר לא יציב"
    assert [r["id"] for r in first] == sorted((r["id"] for r in first), reverse=True), (
        "החדש ביותר חייב להיות ראשון"
    )
    print("✓ סדר הרשימה יציב וקבוע (id כשובר שוויון), החדש ביותר קודם")


def test_empty_event_returns_zeroed_summary() -> None:
    api = _ready_event()
    r = api.client.get("/gifts", headers=api.headers).json()
    assert r["paid_count"] == 0 and r["total_received_agorot"] == 0
    assert r["total_received_display"] == "₪0" and r["gifts"] == []
    print("✓ אירוע בלי מתנות: סיכום מאופס, רשימה ריקה, לא שגיאה")


if __name__ == "__main__":
    try:
        test_summary_counts_only_paid()
        test_pending_and_cancelled_excluded_from_total()
        test_refunded_excluded_from_total()
        test_owner_row_exposes_only_display_fields()
        test_fee_and_total_absent_from_owner_payload()
        test_summary_has_no_fee_information()
        test_guest_facing_endpoints_still_show_the_fee()
        test_fee_still_stored_in_database()
        test_no_card_data_in_response()
        test_row_fields_complete()
        test_missing_blessing_falls_back_to_none()
        test_gift_with_no_sender_name_at_all_shows_fallback()
        test_requires_authentication()
        test_owner_can_view_own_gifts()
        test_member_with_view_permission_can_see_gifts()
        test_member_without_view_permission_is_blocked()
        test_no_cross_event_access()
        test_ordering_is_deterministic_for_same_timestamp()
        test_empty_event_returns_zeroed_summary()
        print("\nכל בדיקות מסך המתנות (בעלים) עברו ✓")
    finally:
        shutdown()
