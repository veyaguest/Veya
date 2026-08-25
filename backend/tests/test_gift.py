"""בדיקות למתנה — חשבון הכסף, הוולידציה, והאכיפה בשרת.

שלושת הדברים שהקובץ הזה נועל:

1. **מי משלם את העמלה.** העמלה מתווספת מעל סכום המתנה ולא מנוכה ממנו.
   בעלי האירוע מקבלים בדיוק את מה שהאורח הזין. זו הבטחה ללקוח, ובדיקה
   שנשברת כאן היא שינוי מהותי במוצר — לא באג קטן.
2. **השרת מחשב, לא הלקוח.** אי אפשר לשלוח עמלה או סכום כולל משלך.
3. **החלון אוכף.** מחוץ לחלון הזמינות אין תמחור ואין תשלום — 403.

הרצה: ``venv/bin/python tests/test_gift.py`` (עצמאי, בלי pytest).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["VEYA_GIFT_ENABLED"] = "1"

from app import gift  # noqa: E402
from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


def _set_event(api, **fields):
    r = api.client.patch("/event", headers=api.headers, json=fields)
    assert r.status_code == 200, f"עדכון אירוע נכשל: {r.status_code} {r.text}"
    return r.json()


def _token(api, guest_id: int) -> str:
    from app import models
    from app.database import SessionLocal, set_request_identity

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


# ---- 1. שלוש הדוגמאות מהאפיון --------------------------------------------

def test_headline_examples() -> None:
    cases = [
        (100, 4, 104),
        (500, 20, 520),
        (1000, 40, 1040),
    ]
    for shekels, want_fee, want_total in cases:
        q = gift.quote(shekels * 100)
        assert q.gift_amount_agorot == shekels * 100, "סכום המתנה השתנה — אסור"
        assert q.fee_agorot == want_fee * 100, f"₪{shekels}: עמלה {q.fee_agorot}"
        assert q.total_agorot == want_total * 100, f"₪{shekels}: סה\"כ {q.total_agorot}"
    print("✓ ₪100→₪104 · ₪500→₪520 · ₪1,000→₪1,040")


def test_fee_is_added_never_deducted() -> None:
    """הלב של ההחלטה: הזוג מקבל את מלוא הסכום."""
    q = gift.quote(50000)
    assert q.gift_amount_agorot == 50000, "הזוג חייב לקבל בדיוק את מה שהוזן"
    assert q.total_agorot > q.gift_amount_agorot, "העמלה חייבת להתווסף, לא להיות מנוכה"
    assert q.total_agorot - q.gift_amount_agorot == q.fee_agorot
    # הבדיקה ההפוכה, במפורש: אסור שהזוג יקבל 480 מתוך 500.
    assert q.gift_amount_agorot != q.total_agorot - 2 * q.fee_agorot
    print("✓ העמלה מתווספת מעל — הזוג מקבל ₪500 מלאים, האורח משלם ₪520")


# ---- 2. אגורות ועיגול דטרמיניסטי -----------------------------------------

def test_agorot_amounts_stay_integers() -> None:
    cases = {
        10050: 402,    # ₪100.50 → 4.02
        10001: 400,    # ₪100.01 → 4.0004 → 4.00
        12345: 494,    # ₪123.45 → 4.938  → 4.94 (חצי כלפי מעלה)
        33333: 1333,   # ₪333.33 → 13.3332
        1: 0,          # אגורה אחת → 0.04 אגורות → 0
        13: 1,         # 13 אגורות → 0.52 → 1
        12: 0,         # 12 אגורות → 0.48 → 0
    }
    for amount, want_fee in cases.items():
        q = gift.quote(amount)
        assert isinstance(q.fee_agorot, int) and isinstance(q.total_agorot, int)
        assert q.fee_agorot == want_fee, f"{amount} אג׳: ציפינו {want_fee}, קיבלנו {q.fee_agorot}"
        assert q.total_agorot == amount + want_fee
    print("✓ סכומים עם אגורות: חשבון שלמים, עיגול חצי-כלפי-מעלה, בלי float")


def test_calculation_is_deterministic() -> None:
    """אותו קלט → אותה תוצאה, תמיד. חשוב במיוחד לכסף."""
    for amount in (1, 999, 50000, 123456, 7777777):
        results = {gift.fee_for(amount) for _ in range(50)}
        assert len(results) == 1, f"{amount}: חישוב לא יציב {results}"
    print("✓ החישוב דטרמיניסטי לחלוטין")


def test_no_floats_anywhere_in_the_result() -> None:
    q = gift.quote_from_input(50000)
    for name, value in vars(q).items():
        assert not isinstance(value, float), f"{name} הוא float — אסור בכסף"
    print("✓ אין אף float בתוצאה")


# ---- 3. ולידציה ----------------------------------------------------------

def test_invalid_amounts_are_rejected() -> None:
    bad_inputs = [
        0, -1, -50000,                      # אפס ושליליים
        "abc", "", "   ", "12.5", "₪500",   # לא מספרי
        None, True, False, [], {}, object(),
        3.14, float("nan"), float("inf"), float("-inf"),
    ]
    for raw in bad_inputs:
        try:
            gift.quote_from_input(raw)
            raise AssertionError(f"{raw!r} התקבל בטעות כסכום תקין")
        except gift.GiftAmountError as exc:
            assert str(exc), "הודעת שגיאה ריקה"
            # השגיאה מנוסחת למוזמן, לא למפתח.
            assert "Error" not in str(exc) and "None" not in str(exc)
    print(f"✓ {len(bad_inputs)} סוגי קלט לא תקין נדחו, עם הודעה בעברית")


def test_smallest_valid_amount() -> None:
    q = gift.quote_from_input(1)
    assert q.gift_amount_agorot == 1 and q.total_agorot == 1
    print("✓ אגורה אחת עוברת (אין מינימום עסקי מומצא)")


def test_no_invented_maximum() -> None:
    """אין מגבלת מקסימום — לא הומצאה כזו, כי אין החלטה עסקית עליה."""
    huge = 100_000_000        # מיליון ש"ח
    q = gift.quote(huge)
    assert q.fee_agorot == 4_000_000 and q.total_agorot == 104_000_000
    print("✓ אין תקרה מומצאת — סכום גדול מחושב נכון")


def test_shekel_formatting() -> None:
    assert gift.format_shekels(52000) == "₪520"
    assert gift.format_shekels(10450) == "₪104.50"
    assert gift.format_shekels(104000000) == "₪1,040,000"
    assert gift.format_shekels(1) == "₪0.01"
    print("✓ עיצוב שקלים: אגורות מוצגות רק כשיש")


# ---- 4. השרת מחשב — לא הלקוח --------------------------------------------

def test_server_recomputes_and_ignores_client_money() -> None:
    api, _ = bootstrap()
    _set_event(api, event_date=_event_date_in(1), event_time="19:30",
               venue_address="הרצל 5, תל אביב")
    g = api.add_guest("נותן מתנה", "0508000001")
    tok = _token(api, g["id"])

    # הלקוח מנסה לשלוח עמלה וסכום כולל משלו — הם פשוט לא קיימים כשדות קלט.
    r = api.client.post(f"/confirm/{tok}/gift/quote", json={
        "gift_amount_agorot": 50000,
        "fee_agorot": 0,            # "אני לא משלם עמלה"
        "total_agorot": 1,          # "אני משלם אגורה"
        "fee_percent": 0,
    })
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["fee_agorot"] == 2000, f"השרת קיבל עמלה מהלקוח: {q}"
    assert q["total_agorot"] == 52000, f"השרת קיבל סה\"כ מהלקוח: {q}"
    assert q["fee_percent"] == 4

    # אותו ניסיון בתשלום עצמו.
    r = api.client.post(f"/confirm/{tok}/gift/checkout", json={
        "gift_amount_agorot": 50000,
        "fee_agorot": 0, "total_agorot": 1,
        "giver_name": "נותן מתנה",
    })
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["quote"]["fee_agorot"] == 2000 and out["quote"]["total_agorot"] == 52000
    assert out["mock"] is True, "חייב להיות מסומן כהדמיה"
    print("✓ השרת מחשב מחדש — עמלה/סה\"כ שנשלחו מהלקוח נזרקים")


def test_api_rejects_bad_amounts() -> None:
    api, _ = bootstrap()
    _set_event(api, event_date=_event_date_in(1), event_time="19:30")
    g = api.add_guest("בודק", "0508000002")
    tok = _token(api, g["id"])
    for bad in (0, -100, "abc", None, 3.5):
        r = api.client.post(f"/confirm/{tok}/gift/quote", json={"gift_amount_agorot": bad})
        assert r.status_code == 422, f"{bad!r} התקבל: {r.status_code} {r.text}"
    print("✓ ה-API דוחה סכומים לא תקינים ב-422")


def test_live_amount_changes_stay_consistent() -> None:
    """"שינוי סכום בזמן אמת" — כל תמחור עומד בפני עצמו ותמיד עקבי."""
    api, _ = bootstrap()
    _set_event(api, event_date=_event_date_in(2), event_time="19:30")
    g = api.add_guest("משנה סכום", "0508000003")
    tok = _token(api, g["id"])
    for shekels in (50, 100, 250, 500, 1000, 1800, 72):
        r = api.client.post(f"/confirm/{tok}/gift/quote",
                            json={"gift_amount_agorot": shekels * 100})
        q = r.json()
        assert q["gift_amount_agorot"] == shekels * 100
        assert q["fee_agorot"] == gift.fee_for(shekels * 100)
        assert q["total_agorot"] == q["gift_amount_agorot"] + q["fee_agorot"]
    print("✓ שינוי סכום חוזר: כל תמחור עקבי עם עצמו ועם מנוע החישוב")


# ---- 5. חלון הזמינות אוכף בשרת -------------------------------------------

def test_gift_endpoints_blocked_outside_window() -> None:
    api, _ = bootstrap()
    g = api.add_guest("מוקדם", "0508000004")
    tok = _token(api, g["id"])

    for days, label in ((30, "חודש לפני"), (4, "4 ימים לפני"), (-3, "אחרי האירוע")):
        _set_event(api, event_date=_event_date_in(days), event_time="19:30")
        for path in ("quote", "checkout"):
            r = api.client.post(f"/confirm/{tok}/gift/{path}",
                                json={"gift_amount_agorot": 50000})
            assert r.status_code == 403, f"{label} / {path}: {r.status_code}"

    # בתוך החלון — עובד.
    _set_event(api, event_date=_event_date_in(2))
    for path in ("quote", "checkout"):
        r = api.client.post(f"/confirm/{tok}/gift/{path}",
                            json={"gift_amount_agorot": 50000})
        assert r.status_code == 200, f"בתוך החלון {path} נכשל: {r.text}"
    print("✓ מחוץ לחלון: 403 גם בתמחור וגם בתשלום. בתוך החלון: עובד")


def test_action_gift_param_does_not_unlock_endpoints() -> None:
    """``?action=gift`` הוא ניתוב — הוא לא פותח את הנתיבים."""
    api, _ = bootstrap()
    _set_event(api, event_date=_event_date_in(20), event_time="19:30")
    g = api.add_guest("מנחש", "0508000005")
    tok = _token(api, g["id"])
    for q in ("?action=gift", "?action=gift&gift=true", "?gift_enabled=1"):
        r = api.client.post(f"/confirm/{tok}/gift/quote{q}",
                            json={"gift_amount_agorot": 50000})
        assert r.status_code == 403, f"'{q}' פתח את התמחור: {r.status_code}"
    print("✓ ?action=gift לא פותח את נתיבי המתנה")


# ---- 6. בידוד ואבטחה -----------------------------------------------------

def test_gift_is_isolated_per_guest_and_event() -> None:
    api_a, _ = bootstrap()
    _set_event(api_a, event_date=_event_date_in(30), event_time="19:30")   # מחוץ לחלון
    ga = api_a.add_guest("אורח רחוק", "0508000006")
    tok_a = _token(api_a, ga["id"])

    api_b, _ = bootstrap()
    _set_event(api_b, event_date=_event_date_in(1), event_time="19:30")    # בתוך החלון
    gb = api_b.add_guest("אורח קרוב", "0508000007")
    tok_b = _token(api_b, gb["id"])

    # הטוקן של האירוע הרחוק לא מקבל גישה, גם אם אירוע אחר כן בחלון.
    assert api_a.client.post(f"/confirm/{tok_a}/gift/quote",
                             json={"gift_amount_agorot": 10000}).status_code == 403
    assert api_a.client.post(f"/confirm/{tok_b}/gift/quote",
                             json={"gift_amount_agorot": 10000}).status_code == 200

    # טוקן מומצא — 404, בדיוק כמו בשאר הנתיבים הציבוריים.
    for bad in ("not-a-token", "abcdefghijkl", ""):
        r = api_a.client.post(f"/confirm/{bad}/gift/quote", json={"gift_amount_agorot": 10000})
        assert r.status_code in (404, 405), f"טוקן '{bad}': {r.status_code}"

    # פרמטרים ב-URL לא מחליפים זהות.
    r = api_b.client.post(f"/confirm/{tok_b}/gift/checkout?guest_id={ga['id']}",
                          json={"gift_amount_agorot": 10000, "giver_name": "אורח קרוב"})
    assert r.status_code == 200 and r.json()["quote"]["gift_amount_agorot"] == 10000
    print("✓ בידוד: טוקן אחד לא פותח מתנה של אירוע אחר, ואין זהות ב-query")


def test_checkout_leaks_no_personal_data() -> None:
    api, _ = bootstrap()
    _set_event(api, event_date=_event_date_in(1), event_time="19:30")
    api.add_guest("אורח אחר לגמרי", "0508000099")
    g = api.add_guest("השולח", "0508000008")
    tok = _token(api, g["id"])
    body = api.client.post(f"/confirm/{tok}/gift/checkout", json={
        "gift_amount_agorot": 25000, "giver_name": "השולח", "blessing": "מזל טוב!",
    }).text
    assert "אורח אחר לגמרי" not in body, "דלף שם של מוזמן אחר"
    assert "0508000099" not in body and "0508000008" not in body, "דלף טלפון"
    print("✓ תשובת התשלום לא חושפת מוזמנים אחרים ולא מספרי טלפון")


# ---- 7. מסלול ההדמיה -----------------------------------------------------

def test_mock_checkout_success_and_failure() -> None:
    api, _ = bootstrap()
    _set_event(api, event_date=_event_date_in(0), event_time="19:30")
    g = api.add_guest("בודק מסלול", "0508000009")
    tok = _token(api, g["id"])

    ok = api.client.post(f"/confirm/{tok}/gift/checkout", json={
        "gift_amount_agorot": 50000, "giver_name": "דנה", "blessing": "מזל טוב",
        "simulate": "success",
    }).json()
    assert ok["status"] == "success" and ok["mock"] is True
    assert ok["reference"].startswith("MOCK-"), "האסמכתא חייבת להיות מסומנת כהדמיה"

    fail = api.client.post(f"/confirm/{tok}/gift/checkout", json={
        "gift_amount_agorot": 50000, "simulate": "failure",
    }).json()
    assert fail["status"] == "failure" and fail["message"]
    assert fail["quote"]["total_agorot"] == 52000, "גם בכישלון הסכומים נכונים"
    print("✓ הדמיה: הצלחה וכישלון, שניהם מסומנים MOCK בבירור")


def test_mock_checkout_writes_to_activity_log() -> None:
    """הזוג רואה ביומן שהייתה הדמיה — בלי שנשמר רישום כספי אמיתי."""
    api, _ = bootstrap()
    _set_event(api, event_date=_event_date_in(0), event_time="19:30")
    g = api.add_guest("רושם ביומן", "0508000010")
    tok = _token(api, g["id"])
    api.client.post(f"/confirm/{tok}/gift/checkout", json={
        "gift_amount_agorot": 50000, "giver_name": "רושם ביומן",
    })
    rows = api.client.get("/event/audit", headers=api.headers).json()
    entry = next((r for r in rows if r["action"] == "gift_mock_checkout"), None)
    assert entry is not None, "לא נרשמה שורה ביומן הפעילות"
    assert "הדמיה" in entry["detail"], "השורה ביומן לא מסומנת כהדמיה"
    assert "₪500" in entry["detail"] and "₪520" in entry["detail"]
    print("✓ יומן הפעילות מתעד את ההדמיה, מסומנת במפורש")


if __name__ == "__main__":
    try:
        test_headline_examples()
        test_fee_is_added_never_deducted()
        test_agorot_amounts_stay_integers()
        test_calculation_is_deterministic()
        test_no_floats_anywhere_in_the_result()
        test_invalid_amounts_are_rejected()
        test_smallest_valid_amount()
        test_no_invented_maximum()
        test_shekel_formatting()
        test_server_recomputes_and_ignores_client_money()
        test_api_rejects_bad_amounts()
        test_live_amount_changes_stay_consistent()
        test_gift_endpoints_blocked_outside_window()
        test_action_gift_param_does_not_unlock_endpoints()
        test_gift_is_isolated_per_guest_and_event()
        test_checkout_leaks_no_personal_data()
        test_mock_checkout_success_and_failure()
        test_mock_checkout_writes_to_activity_log()
        print("\nכל בדיקות המתנה עברו ✓")
    finally:
        shutdown()
