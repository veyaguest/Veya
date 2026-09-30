"""בדיקות ל"סיימנו לספור" במאזן האירוע (PUT /finance/counting-done).

מה שהקובץ הזה שומר עליו (החלטות מייסד 2026-09-30):

1. **סימון "סיימנו לספור" הופך את המאזן לסופי** — ונשמר מי סימן.
2. **"סיימנו" = נכון לאותו רגע, לא נעילה.** מעטפה שנוספה אחרי הסימון
   מחזירה את המאזן ל"עד עכשיו" אוטומטית, ומסמנת שנוספה מתנה מאז.
3. **מתנת אשראי — אותו עיקרון בדיוק.** מתנה ששולמה אחרי הסימון מחזירה
   ל"עד עכשיו". מתנה שעדיין ממתינה (pending) לא נחשבת "מתנה שנכנסה".
4. **ביטול ידני** מחזיר ל"עד עכשיו" בלי הודעת "נוספה מתנה".
5. **לפני יום האירוע אין מה לסיים** — הסימון נדחה.

## למה הבדיקות מזיזות חותמות זמן

המצב "סופי" נגזר מהשוואת זמנים: חותמת הסימון מול זמן יצירת המעטפה / זמן
התשלום של מתנת האשראי — כולם משעון מסד הנתונים. SQLite (סביבת הבדיקות)
שומר שניות שלמות, ולכן שתי פעולות באותה שנייה נראות "בו-זמניות". כדי
שהבדיקות לא יהיו תלויות במזל, הן מזיזות חותמת אחת אחורה במפורש. ב-Postgres
(ייצור) הדיוק הוא מיקרו-שניות.

הרצה: ``venv/bin/python tests/test_gift_counting_done.py`` (או pytest).
"""
from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["VEYA_GIFT_ENABLED"] = "1"

from app import gift_service, gift_status, guest_journey, models  # noqa: E402
from app.database import SessionLocal, set_request_identity  # noqa: E402
from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


def _event_after(days_ago: int = 1):
    """אירוע שכבר קרה — ספירת המתנות פתוחה."""
    api, _ = bootstrap()
    date = (guest_journey.today_in_israel() - timedelta(days=days_ago)).isoformat()
    _patch_event_date(api.event_id, date)
    return api


def _patch_event_date(event_id: int, iso: str) -> None:
    # ישירות למסד: ה-API לא מאפשר לקבוע תאריך שכבר עבר, וזה לא מה שנבדק כאן.
    set_request_identity(None)
    db = SessionLocal()
    try:
        db.get(models.Event, event_id).event_date = iso
        db.commit()
    finally:
        db.close()


def _shift(model, row_id: int, field: str, seconds: int) -> None:
    """מזיז חותמת זמן אחורה — ראו "למה הבדיקות מזיזות חותמות זמן" למעלה."""
    set_request_identity(None)
    db = SessionLocal()
    try:
        row = db.get(model, row_id)
        setattr(row, field, getattr(row, field) - timedelta(seconds=seconds))
        db.commit()
    finally:
        db.close()


def _envelope(api, guest_id: int, agorot: int = 50_000) -> int:
    r = api.client.post(
        "/finance/envelopes", headers=api.headers,
        json={"amount_agorot": agorot, "guest_id": guest_id},
    )
    assert r.status_code == 201, r.text
    return r.json()["envelope"]["id"]


def _mark(api, done: bool) -> dict:
    r = api.client.put("/finance/counting-done", headers=api.headers, json={"done": done})
    assert r.status_code == 200, r.text
    return r.json()


def _summary(api) -> dict:
    r = api.client.get("/finance", headers=api.headers)
    assert r.status_code == 200, r.text
    return r.json()


def _credit_gift(guest_id: int, key: str, *, paid: bool) -> None:
    """מתנת אשראי — דרך אותה נקודה שבה עסקה הופכת ל-paid במוצר
    (``gift_service.set_status``), לא כתיבה ישירה לסטטוס."""
    set_request_identity(None)
    db = SessionLocal()
    try:
        guest = db.get(models.Guest, guest_id)
        row, _ = gift_service.create_gift(
            db, guest, gift_amount_agorot=30_000, client_idempotency_key=key)
        if paid:
            gift_service.set_status(db, row, gift_status.PAID)
        db.commit()
    finally:
        db.close()


def _done_fields(event_id: int):
    set_request_identity(None)
    db = SessionLocal()
    try:
        e = db.get(models.Event, event_id)
        return e.gift_counting_done_at, e.gift_counting_done_by
    finally:
        db.close()


# ---- 1. הסימון הופך את המאזן לסופי ------------------------------------------

def test_marking_done_makes_the_balance_final() -> None:
    api = _event_after()
    g = api.add_guest("דנה לוי", "0503330001")
    env = _envelope(api, g["id"])
    _shift(models.GiftEnvelope, env, "created_at", 60)

    body = _mark(api, True)
    assert body["counting_done"] is True
    assert body["counting_reopened"] is False

    done_at, done_by = _done_fields(api.event_id)
    assert done_at is not None, "חותמת הסימון נשמרת באירוע"
    assert done_by is not None, "ונשמר גם מי סימן"
    assert _summary(api)["counting_done"] is True, "והמצב נשמר גם בקריאה הבאה"
    print("✓ סיימנו לספור ⇒ המאזן סופי, ונשמר מי סימן ומתי")


# ---- 2. מעטפה אחרי הסימון -----------------------------------------------------

def test_envelope_after_done_reopens_the_balance() -> None:
    api = _event_after()
    g = api.add_guest("יוסי כהן", "0503330002")
    env = _envelope(api, g["id"])
    _shift(models.GiftEnvelope, env, "created_at", 120)
    _mark(api, True)
    _shift(models.Event, api.event_id, "gift_counting_done_at", 60)

    _envelope(api, g["id"], 20_000)
    body = _summary(api)
    assert body["counting_done"] is False, "מתנה חדשה ⇒ המאזן כבר לא סופי"
    assert body["counting_reopened"] is True, "והמסך יודע שנוספה מתנה מאז הסימון"
    assert body["income"]["envelopes_agorot"] == 70_000, "המעטפה החדשה נכנסה לסכום"
    print("✓ מעטפה אחרי הסימון ⇒ חזרה ל'עד עכשיו', עם סימון שנוספה מתנה")


def test_marking_again_after_a_new_envelope_is_final_again() -> None:
    api = _event_after()
    g = api.add_guest("רוני אבן", "0503330003")
    env = _envelope(api, g["id"])
    _shift(models.GiftEnvelope, env, "created_at", 120)
    _mark(api, True)
    _shift(models.Event, api.event_id, "gift_counting_done_at", 60)
    env2 = _envelope(api, g["id"], 10_000)
    assert _summary(api)["counting_reopened"] is True

    _shift(models.GiftEnvelope, env2, "created_at", 30)
    body = _mark(api, True)
    assert body["counting_done"] is True, "סימון מחדש — סופי שוב"
    assert body["counting_reopened"] is False
    print("✓ סימון מחדש אחרי מתנה חדשה ⇒ סופי שוב")


# ---- 3. מתנת אשראי אחרי הסימון -----------------------------------------------

def test_paid_credit_gift_after_done_reopens_the_balance() -> None:
    api = _event_after()
    g = api.add_guest("מיכל שגב", "0503330004")
    env = _envelope(api, g["id"])
    _shift(models.GiftEnvelope, env, "created_at", 120)
    _mark(api, True)
    _shift(models.Event, api.event_id, "gift_counting_done_at", 60)

    _credit_gift(g["id"], "after-done-paid", paid=True)
    body = _summary(api)
    assert body["counting_done"] is False, "מתנת אשראי ששולמה אחרי הסימון ⇒ לא סופי"
    assert body["counting_reopened"] is True
    print("✓ מתנת אשראי ששולמה אחרי הסימון ⇒ חזרה ל'עד עכשיו'")


def test_pending_credit_gift_does_not_reopen() -> None:
    """עסקה שלא הושלמה אינה "מתנה שנכנסה" — בדיוק כמו בסכום עצמו."""
    api = _event_after()
    g = api.add_guest("אורי גל", "0503330005")
    env = _envelope(api, g["id"])
    _shift(models.GiftEnvelope, env, "created_at", 120)
    _mark(api, True)
    _shift(models.Event, api.event_id, "gift_counting_done_at", 60)

    _credit_gift(g["id"], "after-done-pending", paid=False)
    body = _summary(api)
    assert body["counting_done"] is True, "pending לא נספרת — המאזן נשאר סופי"
    assert body["counting_reopened"] is False
    print("✓ מתנת אשראי שעדיין ממתינה לא מבטלת את הסימון")


# ---- 4. ביטול ידני ---------------------------------------------------------------

def test_manual_undo_returns_to_so_far_without_a_new_gift_notice() -> None:
    api = _event_after()
    g = api.add_guest("שירה בר", "0503330006")
    env = _envelope(api, g["id"])
    _shift(models.GiftEnvelope, env, "created_at", 60)
    _mark(api, True)

    body = _mark(api, False)
    assert body["counting_done"] is False
    assert body["counting_reopened"] is False, "ביטול ידני אינו 'נוספה מתנה'"
    assert _done_fields(api.event_id) == (None, None), "הסימון נמחק, כולל מי סימן"
    print("✓ ביטול ידני ⇒ 'עד עכשיו', בלי הודעת מתנה חדשה")


# ---- 4ב. עריכה ומחיקה אחרי הסימון (החלטת מייסד 2026-09-30) ---------------------

def _edit_envelope(api, envelope_id: int, *, agorot: int, guest_id) -> None:
    r = api.client.put(
        f"/finance/envelopes/{envelope_id}", headers=api.headers,
        json={"amount_agorot": agorot, "guest_id": guest_id},
    )
    assert r.status_code == 200, r.text


def test_editing_an_amount_after_done_returns_to_so_far() -> None:
    """הסכום הסופי השתנה ⇒ המאזן כבר לא "סופי"."""
    api = _event_after()
    g = api.add_guest("נוי ברק", "0503330008")
    env = _envelope(api, g["id"], 50_000)
    _shift(models.GiftEnvelope, env, "created_at", 60)
    _mark(api, True)

    _edit_envelope(api, env, agorot=40_000, guest_id=g["id"])
    body = _summary(api)
    assert body["counting_done"] is False, "סכום שתוקן אחרי הסימון ⇒ 'עד עכשיו'"
    assert _done_fields(api.event_id) == (None, None)
    print("✓ תיקון סכום אחרי הסימון ⇒ חזרה ל'עד עכשיו'")


def test_attributing_an_envelope_without_changing_its_amount_keeps_done() -> None:
    """שיוך מעטפה שלא זוהתה למוזמן לא משנה אף סכום — הסימון נשאר."""
    api = _event_after()
    g = api.add_guest("טל אור", "0503330009")
    env = _envelope(api, None, 30_000)
    _shift(models.GiftEnvelope, env, "created_at", 60)
    _mark(api, True)

    _edit_envelope(api, env, agorot=30_000, guest_id=g["id"])
    assert _summary(api)["counting_done"] is True
    print("✓ שיוך בלי שינוי סכום ⇒ הסימון נשאר")


def test_entries_expose_shared_ids_so_an_edit_keeps_them() -> None:
    """עריכה שולחת את כל השורה — כולל מי נתן יחד. בלי המזהים ברשימה, תיקון
    סכום היה מוחק בשקט את השותפים למתנה."""
    api = _event_after()
    a = api.add_guest("רון מור", "0503330011")
    b = api.add_guest("שני מור", "0503330012")
    r = api.client.post(
        "/finance/envelopes", headers=api.headers,
        json={"amount_agorot": 60_000, "guest_id": a["id"], "shared_guest_ids": [b["id"]]},
    )
    assert r.status_code == 201, r.text
    entry = r.json()["envelope"]
    assert entry["shared_guest_ids"] == [b["id"]], "המזהים חוזרים גם ביצירה"

    listed = api.client.get("/finance/gifts", headers=api.headers).json()["entries"]
    row = next(x for x in listed if x["id"] == entry["id"])
    assert row["shared_guest_ids"] == [b["id"]], "וגם ברשימה"

    r = api.client.put(
        f"/finance/envelopes/{entry['id']}", headers=api.headers,
        json={"amount_agorot": 50_000, "guest_id": a["id"],
              "shared_guest_ids": row["shared_guest_ids"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["shared_names"] == ["שני מור"], "תיקון הסכום לא מחק את השותפה"
    print("✓ הרשימה מחזירה את מזהי השותפים, ועריכה שומרת עליהם")


def test_deleting_an_envelope_after_done_returns_to_so_far() -> None:
    api = _event_after()
    g = api.add_guest("עדי רון", "0503330010")
    env = _envelope(api, g["id"], 50_000)
    env2 = _envelope(api, g["id"], 10_000)
    _shift(models.GiftEnvelope, env, "created_at", 60)
    _shift(models.GiftEnvelope, env2, "created_at", 60)
    _mark(api, True)

    r = api.client.delete(f"/finance/envelopes/{env2}", headers=api.headers)
    assert r.status_code == 204, r.text
    body = _summary(api)
    assert body["counting_done"] is False, "מחיקה אחרי הסימון ⇒ 'עד עכשיו'"
    assert body["counting_reopened"] is False, "זו פעולה של הזוג עצמו, לא 'נוספה מתנה'"
    print("✓ מחיקת מעטפה אחרי הסימון ⇒ חזרה ל'עד עכשיו'")


# ---- 5. לפני יום האירוע -----------------------------------------------------------

def test_cannot_mark_done_before_the_event_day() -> None:
    api, _ = bootstrap()
    future = (guest_journey.today_in_israel() + timedelta(days=10)).isoformat()
    _patch_event_date(api.event_id, future)

    r = api.client.put("/finance/counting-done", headers=api.headers, json={"done": True})
    assert r.status_code == 409, r.text
    assert _done_fields(api.event_id) == (None, None)
    assert _summary(api)["counting_done"] is False
    print("✓ לפני יום האירוע אי אפשר לסמן 'סיימנו לספור'")


if __name__ == "__main__":
    try:
        test_marking_done_makes_the_balance_final()
        test_envelope_after_done_reopens_the_balance()
        test_marking_again_after_a_new_envelope_is_final_again()
        test_paid_credit_gift_after_done_reopens_the_balance()
        test_pending_credit_gift_does_not_reopen()
        test_manual_undo_returns_to_so_far_without_a_new_gift_notice()
        test_editing_an_amount_after_done_returns_to_so_far()
        test_attributing_an_envelope_without_changing_its_amount_keeps_done()
        test_deleting_an_envelope_after_done_returns_to_so_far()
        test_entries_expose_shared_ids_so_an_edit_keeps_them()
        test_cannot_mark_done_before_the_event_day()
        print("OK — 'סיימנו לספור' מתנהג לפי החלטות המייסד.")
    finally:
        shutdown()
