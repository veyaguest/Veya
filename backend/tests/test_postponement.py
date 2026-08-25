"""בדיקות "נוהל דחייה" — נעילת פרטי האירוע, אישור אדמין, ומחזור RSVP חדש.

הקובץ הזה שומר על שלושה דברים:

1. **הנעילה נאכפת בשרת** — לא בהסתרת שדות במסך. אין פרמטר, כותרת או בקשה
   ידנית שמשנה תאריך או שמות באירוע נעול.
2. **מי שמבקש לדחות אינו מי שמאשר** — כל נתיבי האישור חסומים לבעלי האירוע.
3. **מחזור חדש לא מוחק כלום** — התשובות הישנות עוברות לארכיון לפני האיפוס,
   ואפשר לשלוף אותן משם.

הרצה: ``venv/bin/python tests/test_postponement.py``
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import models  # noqa: E402
from app.database import SessionLocal, set_request_identity  # noqa: E402
from tests.e2e_seating import bootstrap, register, shutdown  # noqa: E402


# ── עזרים ────────────────────────────────────────────────────────────────

def _admin(api):
    """מייצר משתמש אדמין ומחזיר את כותרות ההרשאה שלו.

    האדמין נוצר במסד ולא דרך ה-API — אין (ובכוונה) נתיב שבו משתמש מסמן את
    עצמו כאדמין.
    """
    token = register(api.client)
    set_request_identity(None)
    db = SessionLocal()
    try:
        user = db.scalars(
            select(models.User).order_by(models.User.id.desc())
        ).first()
        user.is_admin = True
        db.commit()
    finally:
        db.close()
    return {"Authorization": f"Bearer {token}"}


def _event(api):
    r = api.client.get("/event", headers=api.headers)
    assert r.status_code == 200, r.text
    return r.json()


def _patch(api, **fields):
    return api.client.patch("/event", headers=api.headers, json=fields)


def _seed_event(api, date="2026-11-12", time="19:30"):
    """ממלא את פרטי הליבה בפעם הראשונה — כמו אשף ההקמה בייצור."""
    r = _patch(api, event_date=date, event_time=time)
    assert r.status_code == 200, f"מילוי ראשון נכשל: {r.text}"
    return r.json()


def _open_and_approve(api, admin):
    r = api.client.post("/postpone", headers=api.headers)
    assert r.status_code == 201, r.text
    r = api.client.post(f"/admin/postpone/{api.event_id}/approve", headers=admin)
    assert r.status_code == 200, r.text
    return r.json()


# ── 1. נעילה: מה חסום ומה פתוח ────────────────────────────────────────────

def test_locked_fields_are_blocked() -> None:
    api, _ = bootstrap()
    _seed_event(api)

    for field, value in [
        ("event_date", "2027-01-01"),
        ("event_time", "21:00"),
        ("groom_name", "יוסי"),
        ("bride_name", "מיכל"),
        ("event_type", "bar_mitzvah"),
    ]:
        r = _patch(api, **{field: value})
        assert r.status_code == 409, f"{field} היה אמור להיחסם, קיבלנו {r.status_code}"
        assert "נוהל דחייה" in r.json()["detail"], r.text

    ev = _event(api)
    assert ev["event_date"] == "2026-11-12", "תאריך השתנה למרות הנעילה"
    assert ev["groom_name"] == "דני", "שם השתנה למרות הנעילה"
    assert ev["edit_locked"] is True
    print("✓ תאריך, שעה, שמות וסוג אירוע נעולים בשרת")


def test_open_fields_still_editable() -> None:
    api, _ = bootstrap()
    _seed_event(api)

    r = _patch(
        api,
        venue_name="אולם חדש",
        venue_address="הרצל 5, תל אביב",
        invite_image="",
    )
    assert r.status_code == 200, f"עריכה מותרת נחסמה: {r.text}"
    ev = r.json()
    assert ev["venue_name"] == "אולם חדש"
    assert ev["venue_address"] == "הרצל 5, תל אביב"

    r = _patch(api, rsvp_send_time="17:00")
    assert r.status_code == 200, r.text
    assert _event(api)["rsvp_send_time"] == "17:00"
    print("✓ אולם, כתובת, תמונה ושעות שליחה נשארו פתוחים")


def test_empty_core_field_can_be_filled_once() -> None:
    api, _ = bootstrap()
    ev = _event(api)
    assert ev["event_date"] == "", "אירוע חדש אמור להיוולד בלי תאריך"

    r = _patch(api, event_date="2026-09-09")
    assert r.status_code == 200, f"מילוי ראשון נחסם: {r.text}"

    r = _patch(api, event_date="2026-09-10")
    assert r.status_code == 409, "שינוי אחרי המילוי הראשון היה אמור להיחסם"

    # אותו ערך בדיוק — עובר בשקט, כדי שטופס שמחזיר הכול לא ייכשל סתם.
    r = _patch(api, event_date="2026-09-09", venue_name="אולם")
    assert r.status_code == 200, f"שליחת ערך זהה נחסמה: {r.text}"
    print("✓ שדה ריק נכתב פעם אחת; ערך זהה עובר; שינוי נחסם")


# ── 2. הבקשה ──────────────────────────────────────────────────────────────

def test_request_needs_no_date() -> None:
    api, _ = bootstrap()
    _seed_event(api)

    # בלי גוף בקשה כלל — אין שדה תאריך חדש ואין מועד סגירת רשימה.
    r = api.client.post("/postpone", headers=api.headers)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending"
    assert r.json()["can_request"] is False

    r = api.client.post("/postpone", headers=api.headers)
    assert r.status_code == 409, "בקשה שנייה בזמן שיש בקשה פתוחה היתה אמורה להיחסם"
    print("✓ בקשה נפתחת בלי תאריך, ובקשה כפולה נחסמת")


def test_request_reaches_admin_queue_only() -> None:
    api, _ = bootstrap()
    _seed_event(api)
    api.client.post("/postpone", headers=api.headers)

    # בעלי האירוע אינם מגיעים לתור הבדיקה ולא לפעולת האישור.
    r = api.client.get("/admin/postpone", headers=api.headers)
    assert r.status_code in (401, 403), f"זוג הגיע לתור האדמין: {r.status_code}"
    r = api.client.post(f"/admin/postpone/{api.event_id}/approve", headers=api.headers)
    assert r.status_code in (401, 403), f"זוג הצליח לאשר לעצמו: {r.status_code}"

    admin = _admin(api)
    rows = api.client.get("/admin/postpone", headers=admin).json()
    mine = [r for r in rows if r["event_id"] == api.event_id]
    assert len(mine) == 1, f"הבקשה לא הופיעה בתור: {rows}"
    assert mine[0]["status"] == "pending"
    assert mine[0]["event_date"] == "2026-11-12"
    print("✓ הבקשה מגיעה לאדמין בלבד — הזוג חסום מאישור")


def test_no_full_edit_before_approval() -> None:
    api, _ = bootstrap()
    _seed_event(api)
    api.client.post("/postpone", headers=api.headers)

    r = _patch(api, event_date="2027-03-03")
    assert r.status_code == 409, "עריכה נפתחה עוד לפני האישור"
    assert _event(api)["event_stage"] == "requested"
    print("✓ לפני האישור פרטי האירוע עדיין נעולים")


def test_reject_frees_the_queue() -> None:
    api, _ = bootstrap()
    _seed_event(api)
    api.client.post("/postpone", headers=api.headers)
    admin = _admin(api)

    empty = api.client.post(
        f"/admin/postpone/{api.event_id}/reject", headers=admin, json={"reason": ""}
    )
    assert empty.status_code == 409, "דחייה בלי סיבה היתה אמורה להיחסם"

    r = api.client.post(
        f"/admin/postpone/{api.event_id}/reject",
        headers=admin,
        json={"reason": "נפתח בטעות"},
    )
    assert r.status_code == 200, r.text

    status = api.client.get("/postpone", headers=api.headers).json()
    assert status["status"] == "rejected"
    assert status["rejection_reason"] == "נפתח בטעות"
    assert status["can_request"] is True, "אחרי דחייה צריך להיות אפשר לבקש שוב"
    assert _patch(api, event_date="2027-03-03").status_code == 409
    print("✓ דחייה משחררת את התור ומאפשרת בקשה חדשה")


# ── 3. אחרי האישור ────────────────────────────────────────────────────────

def test_approval_opens_full_edit() -> None:
    api, _ = bootstrap()
    _seed_event(api)
    _patch(api, venue_commit_days_before=5)
    admin = _admin(api)
    _open_and_approve(api, admin)

    ev = _event(api)
    assert ev["edit_locked"] is False
    assert ev["event_stage"] == "open"
    assert ev["venue_commit_locked"] is False, "מועד סגירת הרשימה נשאר נעול"

    r = _patch(
        api,
        event_date="2027-05-20",
        event_time="20:00",
        groom_name="דני",
        bride_name="רותי כהן",
        venue_commit_days_before=8,
    )
    assert r.status_code == 200, f"עריכה מלאה נחסמה אחרי אישור: {r.text}"
    ev = r.json()
    assert ev["event_date"] == "2027-05-20"
    assert ev["venue_commit_days_before"] == 8, "מועד סגירת רשימה חדש לא נשמר"
    assert ev["event_stage"] == "new_date_set"
    print("✓ אחרי אישור נפתחת עריכה מלאה, כולל מועד סגירת רשימה חדש")


def test_postponement_message_opens_on_approval() -> None:
    api, _ = bootstrap()
    _seed_event(api)
    admin = _admin(api)

    before = api.client.get("/communication/sequence", headers=api.headers).json()
    types_before = {m["message_type"] for m in before}
    assert "postponement" not in types_before, "כרטיס הדחייה הופיע לפני שנדחה כלום"

    # שליחה ידנית של הודעת דחייה חסומה כל עוד אין נוהל פתוח.
    blocked = api.client.post(
        "/communication/sequence/postponement/send",
        headers=api.headers, json={"audience": "all"},
    )
    assert blocked.status_code == 409, f"שליחה נפתחה בלי נוהל: {blocked.status_code}"

    _open_and_approve(api, admin)

    after = api.client.get("/communication/sequence", headers=api.headers).json()
    row = next((m for m in after if m["message_type"] == "postponement"), None)
    assert row is not None, "כרטיס 'אירוע נדחה' לא נפתח אחרי האישור"
    assert row["target_audience"] == "all"
    print("✓ קטגוריית 'אירוע נדחה' נפתחת רק באישור, וסגורה לפניו")


def test_postponement_message_can_be_sent() -> None:
    api, _ = bootstrap()
    _seed_event(api)
    api.add_guest("אורח א", "0501234567")
    api.add_guest("אורח ב", "0507654321")
    # מוזמן בלי טלפון — ה-API לא מאפשר להוסיף כזה, אבל רשימות מיובאות
    # מכילות כאלה בפועל. מרוקנים ישירות ב-DB כדי לבדוק את הדילוג.
    no_phone = api.add_guest("בלי טלפון", "0503333333")
    set_request_identity(None)
    db = SessionLocal()
    try:
        db.get(models.Guest, no_phone["id"]).phone = ""
        db.commit()
    finally:
        db.close()
    admin = _admin(api)
    _open_and_approve(api, admin)

    # אין תוכן עדיין — לא שולחים הודעה ריקה.
    r = api.client.post(
        "/communication/sequence/postponement/send",
        headers=api.headers, json={"audience": "all"},
    )
    assert r.status_code == 400, f"שליחה בלי תוכן לא נחסמה: {r.status_code}"

    api.client.put(
        "/communication/sequence/postponement",
        headers=api.headers,
        json={"content": "שלום {{guest_name}}, האירוע שלנו נדחה. נעדכן בקרוב."},
    )
    r = api.client.post(
        "/communication/sequence/postponement/send",
        headers=api.headers, json={"audience": "all"},
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["sent"] == 2, f"נשלח למספר לא צפוי: {result}"
    assert result["skipped_no_phone"] == 1, f"מוזמן בלי טלפון לא דולג: {result}"
    print("✓ הודעת הדחייה נשלחת ידנית, ומי שאין לו טלפון מדולג")


# ── 4. מחזור חדש ──────────────────────────────────────────────────────────

def test_new_cycle_resets_rsvp_without_losing_history() -> None:
    api, _ = bootstrap()
    _seed_event(api)
    g1 = api.add_guest("אורח מאשר", "0501111111")
    g2 = api.add_guest("אורח מסרב", "0502222222")
    api.confirm(g1["id"], count=3)
    api.client.patch(
        f"/guests/{g2['id']}", headers=api.headers, json={"rsvp_status": "declined"}
    )
    # שיבוץ לשולחן — אמור לשרוד את המחזור החדש.
    api.client.patch(
        f"/guests/{g1['id']}", headers=api.headers, json={"table_number": 4}
    )
    # כמות המאשרים והערת המוזמן מגיעות בייצור מדף אישור ההגעה, לא מ-PATCH
    # של הבעלים — נכתבות כאן ישירות כדי לבדוק שהן מגיעות לארכיון ומתאפסות.
    set_request_identity(None)
    db = SessionLocal()
    try:
        row = db.get(models.Guest, g1["id"])
        row.confirmed_count = 3
        row.guest_note = "מגיעים עם תינוק"
        db.commit()
    finally:
        db.close()

    admin = _admin(api)
    _open_and_approve(api, admin)

    # בלי תאריך חדש אין מחזור חדש — אחרת היינו מאפסים אישורים לחינם.
    r = api.client.post("/postpone/complete", headers=api.headers)
    assert r.status_code == 409, "מחזור חדש נפתח בלי שנקבע תאריך חדש"

    _patch(api, event_date="2027-05-20")
    r = api.client.post("/postpone/complete", headers=api.headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"

    guests = api.client.get("/guests", headers=api.headers).json()["items"]
    by_name = {g["full_name"]: g for g in guests}
    assert all(g["rsvp_status"] == "pending" for g in guests), f"סטטוס לא אופס: {guests}"
    assert by_name["אורח מאשר"]["confirmed_count"] in (None, 0)
    assert not by_name["אורח מאשר"].get("guest_note"), "הערת המוזמן לא אופסה"
    assert by_name["אורח מאשר"]["table_number"] == 4, "השיבוץ נמחק — הוא אמור להישמר"

    # ההיסטוריה נשמרה, ואפשר לשייך אותה למחזור הקודם.
    set_request_identity(None)
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(models.GuestCycleRsvp)
            .where(models.GuestCycleRsvp.event_id == api.event_id)
        ).all()
        archived = {r.guest_id: r for r in rows}
        assert len(rows) == 2, f"ארכיון חסר: {rows}"
        assert archived[g1["id"]].rsvp_status == "confirmed"
        assert archived[g1["id"]].confirmed_count == 3
        assert archived[g1["id"]].guest_note == "מגיעים עם תינוק"
        assert archived[g1["id"]].table_number == 4
        assert archived[g2["id"]].rsvp_status == "declined"
        assert all(r.cycle_number == 1 for r in rows)

        cycle = db.scalars(
            select(models.EventCycle).where(models.EventCycle.event_id == api.event_id)
        ).first()
        assert cycle is not None and cycle.cycle_number == 1
        assert cycle.event_date == "2026-11-12", "צילום המחזור שמר את התאריך הישן"

        event = db.get(models.Event, api.event_id)
        assert event.cycle_number == 2
        assert event.rsvp_track_active is False, "האוטומציות לא נותקו מהתאריך הישן"
        assert event.rsvp_track_started_at is None
    finally:
        db.close()
    print("✓ מחזור חדש מאפס אישורים, שומר שיבוץ, ולא מוחק שום היסטוריה")


def test_new_cycle_reopens_invitations_and_relocks() -> None:
    api, _ = bootstrap()
    _seed_event(api)
    api.add_guest("אורח", "0501111111")
    admin = _admin(api)

    # מחזור 1: שולחים הזמנה, ואז המוזמן כבר "קיבל". תוכן ההזמנה מגיע בייצור
    # מקטלוג האדמין (MessageDefault) שריק בבדיקות — כותבים אותו כאן, אחרת
    # אין מה לשלוח והשליחה מדולגת בשקט.
    api.client.get("/communication/sequence", headers=api.headers)
    api.client.put(
        "/communication/sequence/invitation",
        headers=api.headers,
        json={"content": "שלום {{guest_name}}, אתם מוזמנים!"},
    )
    api.client.post("/automation/track/activate", headers=api.headers, json={})
    preview = api.client.get("/automation/track/preview", headers=api.headers).json()
    assert preview["already_sent"] == 1 and preview["not_yet_sent"] == 0, preview

    _open_and_approve(api, admin)
    _patch(api, event_date="2027-05-20")
    api.client.post("/postpone/complete", headers=api.headers)

    preview = api.client.get("/automation/track/preview", headers=api.headers).json()
    assert preview["not_yet_sent"] == 1, f"ההזמנה החדשה לא נפתחה: {preview}"
    assert preview["already_sent"] == 0, f"הזמנה מהמועד הישן עדיין נספרת: {preview}"

    ev = _event(api)
    assert ev["cycle_number"] == 2
    assert ev["edit_locked"] is True, "האירוע לא ננעל בחזרה"
    assert ev["event_stage"] == "rsvp_reopened"
    assert _patch(api, event_date="2028-01-01").status_code == 409

    # כרטיס הדחייה יוצא מהתצוגה כשהאירוע חוזר לשגרה.
    seq = api.client.get("/communication/sequence", headers=api.headers).json()
    assert "postponement" not in {m["message_type"] for m in seq}

    # ההודעות של המחזור הקודם לא נמחקו — רק יצאו מהתמונה הנוכחית.
    set_request_identity(None)
    db = SessionLocal()
    try:
        old = db.scalars(
            select(models.Message)
            .where(models.Message.event_id == api.event_id)
            .where(models.Message.cycle_number == 1)
        ).all()
        assert len(old) >= 1, "הודעות המחזור הקודם נמחקו"
    finally:
        db.close()
    print("✓ מחזור חדש פותח הזמנה מחדש, נועל את האירוע, ולא מוחק הודעות")


def test_second_postponement_works() -> None:
    api, _ = bootstrap()
    _seed_event(api)
    api.add_guest("אורח", "0501111111")
    admin = _admin(api)

    _open_and_approve(api, admin)
    _patch(api, event_date="2027-05-20")
    api.client.post("/postpone/complete", headers=api.headers)

    _open_and_approve(api, admin)
    _patch(api, event_date="2027-09-09")
    r = api.client.post("/postpone/complete", headers=api.headers)
    assert r.status_code == 200, f"דחייה שנייה נכשלה: {r.text}"

    ev = _event(api)
    assert ev["cycle_number"] == 3, f"מחזור שלישי לא נפתח: {ev['cycle_number']}"
    assert ev["edit_locked"] is True

    set_request_identity(None)
    db = SessionLocal()
    try:
        cycles = db.scalars(
            select(models.EventCycle)
            .where(models.EventCycle.event_id == api.event_id)
            .order_by(models.EventCycle.cycle_number)
        ).all()
        assert [c.cycle_number for c in cycles] == [1, 2], f"מחזורים: {cycles}"
        assert cycles[0].event_date == "2026-11-12"
        assert cycles[1].event_date == "2027-05-20"
    finally:
        db.close()
    print("✓ המערכת תומכת ביותר מדחייה אחת — מחזור 1 → 2 → 3")


def test_event_delete_removes_postponement_data() -> None:
    """מחיקת אירוע לא נופלת על נתוני נוהל הדחייה, ולא משאירה אותם יתומים."""
    api, _ = bootstrap()
    _seed_event(api)
    api.add_guest("אורח", "0501111111")
    admin = _admin(api)
    _open_and_approve(api, admin)
    _patch(api, event_date="2027-05-20")
    api.client.post("/postpone/complete", headers=api.headers)

    r = api.client.delete(f"/events/{api.event_id}", headers=api.headers)
    assert r.status_code == 204, f"מחיקת אירוע נכשלה: {r.status_code} {r.text}"

    set_request_identity(None)
    db = SessionLocal()
    try:
        for model in (
            models.PostponementRequest, models.EventCycle, models.GuestCycleRsvp,
        ):
            left = db.scalars(
                select(model).where(model.event_id == api.event_id)
            ).all()
            assert not left, f"נשארו שורות יתומות ב-{model.__tablename__}: {left}"
    finally:
        db.close()
    print("✓ מחיקת אירוע מנקה את כל נתוני נוהל הדחייה")


if __name__ == "__main__":
    try:
        test_locked_fields_are_blocked()
        test_open_fields_still_editable()
        test_empty_core_field_can_be_filled_once()
        test_request_needs_no_date()
        test_request_reaches_admin_queue_only()
        test_no_full_edit_before_approval()
        test_reject_frees_the_queue()
        test_approval_opens_full_edit()
        test_postponement_message_opens_on_approval()
        test_postponement_message_can_be_sent()
        test_new_cycle_resets_rsvp_without_losing_history()
        test_new_cycle_reopens_invitations_and_relocks()
        test_second_postponement_works()
        test_event_delete_removes_postponement_data()
        print("\nכל בדיקות נוהל הדחייה עברו ✓")
    finally:
        shutdown()
