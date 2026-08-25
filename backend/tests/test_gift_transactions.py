"""בדיקות לשכבת עסקאות המתנה — טבלה, idempotency, סטטוסים וספק הסליקה.

מה שהקובץ הזה שומר עליו:

1. **הכסף לא ניתן להזזה מהלקוח.** סכום, עמלה, סה"כ, event_id ו-guest_id
   נקבעים בשרת מתוך הטוקן — לא מגוף הבקשה.
2. **לחיצה כפולה לא יוצרת שני חיובים.** ה-idempotency מוגן באינדקס ייחודי
   ב-DB, לא רק בבדיקה ב-Python.
3. **``paid`` מגיע רק מהספק.** גם בהדמיה, הסטטוס נקרא מהספק ולא נקבע
   מבקשת ה-Frontend.

הרצה: ``venv/bin/python tests/test_gift_transactions.py`` (עצמאי, בלי pytest).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["VEYA_GIFT_ENABLED"] = "1"

from app import gift, gift_service, gift_status, models, payments  # noqa: E402
from app.database import SessionLocal, set_request_identity  # noqa: E402
from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


def _set_event(api, **fields):
    r = api.client.patch("/event", headers=api.headers, json=fields)
    assert r.status_code == 200, f"עדכון אירוע נכשל: {r.status_code} {r.text}"
    return r.json()


def _token(api, guest_id: int) -> str:
    set_request_identity(None)
    db = SessionLocal()
    try:
        return db.get(models.Guest, guest_id).guest_token
    finally:
        db.close()


def _event_date_in(days: int) -> str:
    from datetime import timedelta

    from app import guest_journey

    return (guest_journey.today_in_israel() + timedelta(days=days)).isoformat()


def _gifts(event_id: int | None = None) -> list[models.Gift]:
    from sqlalchemy import select

    set_request_identity(None)
    db = SessionLocal()
    try:
        stmt = select(models.Gift)
        if event_id is not None:
            stmt = stmt.where(models.Gift.event_id == event_id)
        return list(db.scalars(stmt).all())
    finally:
        db.close()


def _ready_guest(name: str, phone: str, days: int = 1):
    """אירוע בתוך חלון המתנה + מוזמן עם טוקן."""
    api, _ = bootstrap()
    _set_event(api, event_date=_event_date_in(days), event_time="19:30",
               venue_address="הרצל 5, תל אביב")
    g = api.add_guest(name, phone)
    return api, g, _token(api, g["id"])


# ---- 1. יצירת עסקה ------------------------------------------------------

def test_gift_row_is_created_with_correct_money() -> None:
    api, g, tok = _ready_guest("נותן מתנה", "0509000001")
    r = api.client.post(f"/confirm/{tok}/gift/checkout", json={
        "gift_amount_agorot": 50000, "giver_name": "דנה", "blessing": "מזל טוב",
        "idempotency_key": "k-create-1",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["gift_id"] > 0 and body["gift_status"] == gift_status.PAID

    rows = _gifts(api.event_id)
    assert len(rows) == 1, f"ציפינו לעסקה אחת, יש {len(rows)}"
    row = rows[0]
    assert row.gift_amount_agorot == 50000, "הזוג חייב לקבל את מלוא הסכום"
    assert row.fee_agorot == 2000
    assert row.total_agorot == 52000
    assert row.gift_amount_agorot + row.fee_agorot == row.total_agorot
    assert row.currency == "ILS"
    assert row.event_id == api.event_id and row.guest_id == g["id"]
    assert row.provider == "mock" and row.provider_transaction_id
    assert row.sender_name == "דנה" and row.message == "מזל טוב"
    assert row.created_at is not None and row.updated_at is not None
    print("✓ יצירת עסקה: ₪500 → עמלה ₪20 → סה\"כ ₪520, כל השדות נשמרו")


def test_no_floats_stored() -> None:
    api, g, tok = _ready_guest("בלי פלוט", "0509000002")
    api.client.post(f"/confirm/{tok}/gift/checkout", json={
        "gift_amount_agorot": 12345, "idempotency_key": "k-float"})
    row = _gifts(api.event_id)[0]
    for field in ("gift_amount_agorot", "fee_agorot", "total_agorot"):
        value = getattr(row, field)
        assert isinstance(value, int), f"{field} אינו int: {type(value)}"
        assert not isinstance(value, float)
    assert row.fee_agorot == gift.fee_for(12345)
    print("✓ אין float בטבלה — שלושת הסכומים נשמרים כמספרים שלמים")


def test_no_card_data_columns_exist() -> None:
    """הגנה מבנית: אסור שיהיה בכלל *מקום* לשמור פרטי אשראי."""
    columns = {c.name.lower() for c in models.Gift.__table__.columns}
    forbidden = ("card", "pan", "cvv", "cvc", "expiry", "exp_month", "exp_year",
                 "cardholder", "track2", "iban", "account_number")
    found = [c for c in columns for bad in forbidden if bad in c]
    assert not found, f"נמצאו עמודות חשודות לנתוני אשראי: {found}"
    print("✓ אין בטבלה שום עמודה שיכולה להכיל פרטי אשראי")


# ---- 2. Idempotency -----------------------------------------------------

def test_same_key_does_not_create_second_gift() -> None:
    api, g, tok = _ready_guest("לוחץ פעמיים", "0509000003")
    payload = {"gift_amount_agorot": 30000, "giver_name": "יוסי",
               "idempotency_key": "double-click-1"}

    first = api.client.post(f"/confirm/{tok}/gift/checkout", json=payload).json()
    second = api.client.post(f"/confirm/{tok}/gift/checkout", json=payload).json()
    third = api.client.post(f"/confirm/{tok}/gift/checkout", json=payload).json()

    assert first["gift_id"] == second["gift_id"] == third["gift_id"], "נוצרו עסקאות כפולות"
    assert len(_gifts(api.event_id)) == 1, "יותר מעסקה אחת נשמרה ב-DB"
    print("✓ לחיצה כפולה/משולשת עם אותו מפתח → עסקה אחת בלבד")


def test_same_key_different_amount_is_rejected() -> None:
    api, g, tok = _ready_guest("מפתח ממוחזר", "0509000004")
    api.client.post(f"/confirm/{tok}/gift/checkout",
                    json={"gift_amount_agorot": 10000, "idempotency_key": "reuse"})
    r = api.client.post(f"/confirm/{tok}/gift/checkout",
                        json={"gift_amount_agorot": 99999, "idempotency_key": "reuse"})
    assert r.status_code == 409, f"ציפינו ל-409, קיבלנו {r.status_code}"
    assert len(_gifts(api.event_id)) == 1
    print("✓ אותו מפתח עם סכום אחר → 409, בלי עסקה נוספת")


def test_different_keys_create_separate_gifts() -> None:
    api, g, tok = _ready_guest("שתי מתנות", "0509000005")
    a = api.client.post(f"/confirm/{tok}/gift/checkout",
                        json={"gift_amount_agorot": 10000, "idempotency_key": "a"}).json()
    b = api.client.post(f"/confirm/{tok}/gift/checkout",
                        json={"gift_amount_agorot": 20000, "idempotency_key": "b"}).json()
    assert a["gift_id"] != b["gift_id"]
    assert len(_gifts(api.event_id)) == 2, "שתי מתנות נפרדות אמורות להישמר"
    print("✓ מפתחות שונים → עסקאות נפרדות (מתנה שנייה היא לגיטימית)")


def test_key_is_namespaced_per_guest() -> None:
    """שני מוזמנים ששולחים אותו מפתח לא מתנגשים — ולא רואים זה את זה."""
    api, g1, tok1 = _ready_guest("מוזמן א׳", "0509000006")
    g2 = api.add_guest("מוזמן ב׳", "0509000007")
    tok2 = _token(api, g2["id"])

    r1 = api.client.post(f"/confirm/{tok1}/gift/checkout",
                         json={"gift_amount_agorot": 10000, "idempotency_key": "same"}).json()
    r2 = api.client.post(f"/confirm/{tok2}/gift/checkout",
                         json={"gift_amount_agorot": 20000, "idempotency_key": "same"}).json()
    assert r1["gift_id"] != r2["gift_id"], "מוזמן ב׳ קיבל את העסקה של מוזמן א׳"
    rows = {row.guest_id: row for row in _gifts(api.event_id)}
    assert rows[g1["id"]].gift_amount_agorot == 10000
    assert rows[g2["id"]].gift_amount_agorot == 20000
    print("✓ המפתח ממורחב-שם לפי מוזמן — אין התנגשות בין מוזמנים")


def test_missing_key_never_merges_requests() -> None:
    api, g, tok = _ready_guest("בלי מפתח", "0509000008")
    for _ in range(2):
        api.client.post(f"/confirm/{tok}/gift/checkout", json={"gift_amount_agorot": 5000})
    assert len(_gifts(api.event_id)) == 2, (
        "בלי מפתח אין דרך לדעת שזו אותה כוונה — חייבות להיווצר שתי עסקאות"
    )
    print("✓ בקשה בלי מפתח לא מתאחדת בטעות עם קודמת")


def test_unique_index_exists_in_db() -> None:
    """ההגנה האמיתית מפני מרוץ — לא הבדיקה ב-Python."""
    from sqlalchemy import inspect

    from app.database import migrations_engine

    indexes = inspect(migrations_engine).get_indexes("gifts")
    unique_cols = [tuple(i["column_names"]) for i in indexes if i.get("unique")]
    assert ("idempotency_key",) in unique_cols, f"אין אינדקס ייחודי: {indexes}"
    print("✓ אינדקס ייחודי על idempotency_key קיים ב-DB")


# ---- 3. הלקוח לא קובע כסף או זהות ---------------------------------------

def test_client_cannot_set_fee_total_event_or_guest() -> None:
    api, g, tok = _ready_guest("מנסה לרמות", "0509000009")
    other = api.add_guest("מוזמן אחר", "0509000010")

    api_b, gb, tok_b = _ready_guest("אירוע אחר", "0509000011")

    r = api.client.post(f"/confirm/{tok}/gift/checkout", json={
        "gift_amount_agorot": 50000,
        "fee_agorot": 0,            # "לא משלם עמלה"
        "total_agorot": 1,          # "משלם אגורה"
        "event_id": api_b.event_id,  # אירוע של מישהו אחר
        "guest_id": other["id"],     # מוזמן אחר
        "status": "paid",
        "provider": "real-bank",
        "provider_transaction_id": "FAKE-1",
        "idempotency_key": "cheat",
    })
    assert r.status_code == 200, r.text
    row = _gifts(api.event_id)[0]
    assert row.fee_agorot == 2000, "השרת קיבל עמלה מהלקוח"
    assert row.total_agorot == 52000, "השרת קיבל סה\"כ מהלקוח"
    assert row.event_id == api.event_id, "הלקוח הצליח לשנות event_id"
    assert row.guest_id == g["id"], "הלקוח הצליח לשנות guest_id"
    assert row.provider == "mock", "הלקוח הצליח לשנות ספק"
    assert row.provider_transaction_id != "FAKE-1", "הלקוח הצליח לשתול מזהה עסקה"
    assert not _gifts(api_b.event_id), "נוצרה עסקה באירוע של מישהו אחר"
    print("✓ הלקוח לא יכול לקבוע עמלה, סה\"כ, event_id, guest_id, ספק או מזהה עסקה")


def test_invalid_token_creates_nothing() -> None:
    api, g, tok = _ready_guest("תקין", "0509000012")
    before = len(_gifts())
    for bad in ("not-a-token", "abcdefghijkl", ""):
        r = api.client.post(f"/confirm/{bad}/gift/checkout",
                            json={"gift_amount_agorot": 10000})
        assert r.status_code in (404, 405), f"טוקן '{bad}': {r.status_code}"
    assert len(_gifts()) == before, "טוקן לא תקין יצר עסקה"
    print("✓ טוקן לא תקין: 404, ואף עסקה לא נוצרה")


def test_gift_isolated_between_events() -> None:
    api_a, ga, tok_a = _ready_guest("אירוע א׳", "0509000013")
    api_b, gb, tok_b = _ready_guest("אירוע ב׳", "0509000014")

    api_a.client.post(f"/confirm/{tok_a}/gift/checkout",
                      json={"gift_amount_agorot": 11100, "idempotency_key": "ev-a"})
    api_b.client.post(f"/confirm/{tok_b}/gift/checkout",
                      json={"gift_amount_agorot": 22200, "idempotency_key": "ev-b"})

    a_rows = _gifts(api_a.event_id)
    b_rows = _gifts(api_b.event_id)
    assert len(a_rows) == 1 and a_rows[0].gift_amount_agorot == 11100
    assert len(b_rows) == 1 and b_rows[0].gift_amount_agorot == 22200
    assert a_rows[0].guest_id == ga["id"] and b_rows[0].guest_id == gb["id"]
    print("✓ בידוד מלא בין אירועים — כל עסקה תחת האירוע והמוזמן שלה")


# ---- 4. סטטוסים ---------------------------------------------------------

def test_status_starts_pending_before_provider() -> None:
    """עסקה נולדת ``pending`` — לא ``paid``."""
    api, g, tok = _ready_guest("סטטוס פתיחה", "0509000015")
    set_request_identity(None)
    db = SessionLocal()
    try:
        guest = db.get(models.Guest, g["id"])
        row, created = gift_service.create_gift(
            db, guest, gift_amount_agorot=40000, client_idempotency_key="start")
        assert created is True
        assert row.status == gift_status.PENDING, f"נולד כ-{row.status}"
        assert row.provider_transaction_id is None, "אין עדיין מזהה ספק"
        db.rollback()
    finally:
        db.close()
    print("✓ עסקה נולדת ב-pending, לפני שדיברנו עם הספק בכלל")


def test_paid_comes_from_provider_not_from_client() -> None:
    """גם כשהלקוח מבקש 'הצלחה', הסטטוס נקרא מהספק."""
    api, g, tok = _ready_guest("מקור הסטטוס", "0509000016")
    ok = api.client.post(f"/confirm/{tok}/gift/checkout", json={
        "gift_amount_agorot": 50000, "simulate": "success", "idempotency_key": "s-ok"}).json()
    assert ok["gift_status"] == gift_status.PAID

    fail = api.client.post(f"/confirm/{tok}/gift/checkout", json={
        "gift_amount_agorot": 50000, "simulate": "failure", "idempotency_key": "s-fail"}).json()
    assert fail["status"] == "failure" and fail["gift_status"] == gift_status.FAILED

    rows = {r.idempotency_key.split(":")[-1]: r for r in _gifts(api.event_id)}
    statuses = sorted(r.status for r in rows.values())
    assert statuses == [gift_status.FAILED, gift_status.PAID], statuses

    # והראיה שזה באמת מהספק: אותו מזהה עסקה מדווח אצלו כמו אצלנו.
    provider = payments.get_provider()
    for row in _gifts(api.event_id):
        intent = provider.get_payment_status(row.provider_transaction_id)
        assert payments.PROVIDER_TO_GIFT_STATUS[intent.status] == row.status
    print("✓ הסטטוס נקרא מהספק — הצלחה וכישלון שניהם מגיעים משם")


def test_status_transition_rules() -> None:
    allowed = [
        (gift_status.PENDING, gift_status.PAID),
        (gift_status.PENDING, gift_status.FAILED),
        (gift_status.PENDING, gift_status.CANCELLED),
        (gift_status.PAID, gift_status.REFUNDED),
        (gift_status.PAID, gift_status.PAID),          # אותו סטטוס = idempotent
    ]
    forbidden = [
        (gift_status.PAID, gift_status.PENDING),
        (gift_status.PAID, gift_status.FAILED),
        (gift_status.FAILED, gift_status.PAID),
        (gift_status.FAILED, gift_status.PENDING),
        (gift_status.CANCELLED, gift_status.PAID),
        (gift_status.REFUNDED, gift_status.PAID),
        (gift_status.PENDING, gift_status.REFUNDED),
    ]
    for src, dst in allowed:
        assert gift_status.can_transition(src, dst), f"{src}→{dst} אמור להיות מותר"
        gift_status.assert_transition(src, dst)
    for src, dst in forbidden:
        assert not gift_status.can_transition(src, dst), f"{src}→{dst} אמור להיות אסור"
        try:
            gift_status.assert_transition(src, dst)
            raise AssertionError(f"{src}→{dst} עבר בלי שגיאה")
        except gift_status.InvalidStatusTransition:
            pass
    try:
        gift_status.assert_transition(gift_status.PENDING, "מומצא")
        raise AssertionError("סטטוס מומצא התקבל")
    except gift_status.InvalidStatusTransition:
        pass
    print(f"✓ מעברי סטטוס: {len(allowed)} מותרים, {len(forbidden)} חסומים, וסטטוס מומצא נדחה")


def test_only_five_statuses_exist() -> None:
    assert set(gift_status.ALL) == {"pending", "paid", "failed", "cancelled", "refunded"}
    assert set(gift_status.TRANSITIONS) == set(gift_status.ALL), "כל סטטוס חייב רשומה"
    print("✓ חמישה סטטוסים בלבד — לא הומצאו נוספים")


# ---- 5. שכבת ספק התשלומים ------------------------------------------------

def test_provider_interface_shape() -> None:
    provider = payments.get_provider()
    assert isinstance(provider, payments.PaymentProvider)
    for method in ("create_payment", "get_payment_status", "refund_payment"):
        assert callable(getattr(provider, method)), f"חסרה פעולה {method}"
    assert provider.name == "mock", "ברירת המחדל חייבת להיות ספק מדומה"

    # אי אפשר לממש את הממשק בלי לספק את שלוש הפעולות.
    try:
        class Broken(payments.PaymentProvider):
            name = "broken"

        Broken()
        raise AssertionError("ספק חסר-פעולות הצליח להיווצר")
    except TypeError:
        pass
    print("✓ ממשק הספק: create_payment / get_payment_status / refund_payment")


def test_provider_never_receives_card_data() -> None:
    """הממשק לא מקבל פרטי אשראי — לא היום ולא בטעות בעתיד."""
    import inspect as _inspect

    sig = _inspect.signature(payments.PaymentProvider.create_payment)
    params = set(sig.parameters)
    forbidden = {"card_number", "cvv", "cvc", "pan", "expiry", "cardholder"}
    assert not (params & forbidden), f"הממשק מקבל פרטי אשראי: {params & forbidden}"
    assert {"amount_agorot", "currency", "reference"} <= params
    print("✓ ממשק הספק לא מקבל פרטי אשראי בשום פרמטר")


def test_mock_refund_flow() -> None:
    api, g, tok = _ready_guest("החזר", "0509000017")
    api.client.post(f"/confirm/{tok}/gift/checkout",
                    json={"gift_amount_agorot": 50000, "idempotency_key": "refund-me"})
    row = _gifts(api.event_id)[0]
    assert row.status == gift_status.PAID

    provider = payments.get_provider()
    refunded = provider.refund_payment(row.provider_transaction_id)
    assert refunded.status == payments.PROVIDER_REFUNDED

    set_request_identity(None)
    db = SessionLocal()
    try:
        fresh = db.get(models.Gift, row.id)
        updated = gift_service.sync_status_from_provider(db, fresh)
        assert updated.status == gift_status.REFUNDED
        db.commit()
    finally:
        db.close()
    print("✓ החזר: הספק מדווח refunded, והעסקה עוקבת אחריו")


def test_unknown_provider_is_rejected() -> None:
    try:
        payments.get_provider("stripe-real")
        raise AssertionError("ספק לא רשום התקבל")
    except ValueError:
        pass
    print("✓ ספק שלא נרשם נדחה — אין ברירת מחדל שקטה")


if __name__ == "__main__":
    try:
        test_gift_row_is_created_with_correct_money()
        test_no_floats_stored()
        test_no_card_data_columns_exist()
        test_same_key_does_not_create_second_gift()
        test_same_key_different_amount_is_rejected()
        test_different_keys_create_separate_gifts()
        test_key_is_namespaced_per_guest()
        test_missing_key_never_merges_requests()
        test_unique_index_exists_in_db()
        test_client_cannot_set_fee_total_event_or_guest()
        test_invalid_token_creates_nothing()
        test_gift_isolated_between_events()
        test_status_starts_pending_before_provider()
        test_paid_comes_from_provider_not_from_client()
        test_status_transition_rules()
        test_only_five_statuses_exist()
        test_provider_interface_shape()
        test_provider_never_receives_card_data()
        test_mock_refund_flow()
        test_unknown_provider_is_rejected()
        print("\nכל בדיקות שכבת העסקאות עברו ✓")
    finally:
        shutdown()
