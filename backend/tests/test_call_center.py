"""בדיקות ל-Call Center של האדמין (backend/app/call_center.py).

הדבר המרכזי שנבדק כאן הוא **החיבור ל-Workflow אישורי ההגעה**: המודול לא
מנהל תאריכים משלו, ולכן כל ההתנהגות שלו נגזרת מ-``rsvp_timeline`` ומסטטוסי
ה-RSVP הקיימים:

- אירוע שסבב השיחות שלו עוד לא הגיע — לא מוצג בכלל.
- מוזמן שאישר או ביטל (בכל ערוץ) — יורד מהתור מיד.
- "לא ענה" מוריד מהתור עד הסבב הבא; "לחזור מאוחר יותר" מחזיר במועד שנבחר.
- "אישר הגעה" בשיחה מעדכן בדיוק את אותם שדות שהמוזמן היה מעדכן בעצמו.
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


def _admin_headers(api) -> dict:
    """הופך את המשתמש של הבדיקה לאדמין ומחזיר כותרות מתאימות."""
    from app.database import SessionLocal
    from app import auth, models

    db = SessionLocal()
    try:
        event = db.get(models.Event, api.event_id)
        user = db.get(models.User, event.owner_id)
        user.is_admin = True
        db.commit()
        return {"Authorization": f"Bearer {auth.create_access_token(user)}"}
    finally:
        db.close()


def _configure_track(api, *, days_to_event: int, commit_days: int, started_days_ago: int) -> None:
    """מכוון את האירוע כך שסבב שיחות מסוים יהיה פעיל — דרך אותם שדות שה-
    Workflow האמיתי משתמש בהם, בלי להמציא מנגנון תאריכים לבדיקה."""
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    try:
        event = db.get(models.Event, api.event_id)
        event.event_date = (date.today() + timedelta(days=days_to_event)).isoformat()
        event.event_time = "19:00"
        event.venue_commit_days_before = commit_days
        event.rsvp_track_active = True
        event.rsvp_track_started_at = datetime.utcnow() - timedelta(days=started_days_ago)
        db.commit()
    finally:
        db.close()


def _rounds(api) -> list:
    from app.database import SessionLocal
    from app import models, rsvp_timeline

    db = SessionLocal()
    try:
        return rsvp_timeline.call_rounds(db.get(models.Event, api.event_id))
    finally:
        db.close()


def test_event_hidden_until_its_call_round_arrives() -> None:
    """אירוע שהסבב הראשון שלו עוד לפנינו — לא מופיע ב-Call Center."""
    api, teardown = bootstrap()
    try:
        headers = _admin_headers(api)
        api.add_guest("אורח ממתין", "0501111111", party_size=2)
        # המסלול הופעל היום, והאירוע רחוק — סבב השיחות הראשון עוד לא הגיע.
        _configure_track(api, days_to_event=60, commit_days=5, started_days_ago=0)

        r = api.client.get("/admin/call-center", headers=headers)
        assert r.status_code == 200, r.text
        ids = [e["event_id"] for e in r.json()["events"]]
        assert api.event_id not in ids
        print("✓ אירוע שסבב השיחות שלו לא הגיע — לא מוצג")
    finally:
        teardown()


def test_due_round_lists_only_open_guests() -> None:
    """כשסבב השיחות הגיע — מוצגים רק מי שעדיין לא אישר ולא ביטל."""
    api, teardown = bootstrap()
    try:
        headers = _admin_headers(api)
        waiting = api.add_guest("ממתין לשיחה", "0502222222", party_size=3)
        confirmed = api.add_guest("כבר אישר", "0503333333", party_size=2)
        declined = api.add_guest("כבר ביטל", "0504444444", party_size=1)
        api.client.patch(f"/guests/{confirmed['id']}", headers=api.headers,
                         json={"rsvp_status": "confirmed"})
        api.client.patch(f"/guests/{declined['id']}", headers=api.headers,
                         json={"rsvp_status": "declined"})

        # המסלול התחיל לפני 10 ימים — סבב שיחות כבר נפתח.
        _configure_track(api, days_to_event=8, commit_days=3, started_days_ago=12)
        assert any(p.date <= date.today() for p in _rounds(api)), "הבדיקה מצפה לסבב פעיל"

        r = api.client.get("/admin/call-center/queue", headers=headers,
                           params={"event_id": api.event_id})
        assert r.status_code == 200, r.text
        names = [g["full_name"] for g in r.json()["items"]]
        assert names == ["ממתין לשיחה"], names

        overview = api.client.get("/admin/call-center", headers=headers).json()
        row = next(e for e in overview["events"] if e["event_id"] == api.event_id)
        assert row["waiting"] == 1
        assert row["round_number"] >= 1
        print("✓ בסבב פעיל מוצג רק מי שעדיין לא ענה")
    finally:
        teardown()


def test_no_answer_removes_from_queue_until_next_round() -> None:
    """'לא ענה' מתעד ניסיון ומוריד מהתור — בלי לגעת בסטטוס אישור ההגעה."""
    api, teardown = bootstrap()
    try:
        headers = _admin_headers(api)
        guest = api.add_guest("לא עונה", "0505555555", party_size=2)
        _configure_track(api, days_to_event=8, commit_days=3, started_days_ago=12)

        r = api.client.post(
            f"/admin/call-center/guests/{guest['id']}/outcome",
            headers=headers, json={"outcome": "no_answer", "note": "לא ענה, ננסה שוב"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["rsvp_status"] == "pending"  # הסטטוס לא השתנה

        q = api.client.get("/admin/call-center/queue", headers=headers,
                           params={"event_id": api.event_id}).json()
        assert q["total"] == 0, q
        print("✓ 'לא ענה' מוריד מהתור ולא נוגע בסטטוס")
    finally:
        teardown()


def test_callback_returns_the_guest_at_the_chosen_time() -> None:
    """'לחזור מאוחר יותר' מסתיר עד המועד שנבחר, ומחזיר אחריו."""
    api, teardown = bootstrap()
    try:
        headers = _admin_headers(api)
        guest = api.add_guest("ביקש שנחזור", "0506666666", party_size=1)
        _configure_track(api, days_to_event=8, commit_days=3, started_days_ago=12)

        future = (datetime.utcnow() + timedelta(hours=3)).isoformat() + "Z"
        r = api.client.post(
            f"/admin/call-center/guests/{guest['id']}/outcome",
            headers=headers, json={"outcome": "callback", "callback_at": future},
        )
        assert r.status_code == 200, r.text

        q = api.client.get("/admin/call-center/queue", headers=headers,
                           params={"event_id": api.event_id}).json()
        assert q["total"] == 0, "לפני המועד שנבחר המוזמן לא אמור להופיע"

        # מזיזים את מועד החזרה לעבר — המוזמן חוזר לתור.
        from app.database import SessionLocal
        from app import models

        db = SessionLocal()
        try:
            log = db.query(models.CallLog).filter_by(guest_id=guest["id"]).one()
            log.callback_at = datetime.utcnow() - timedelta(minutes=1)
            db.commit()
        finally:
            db.close()

        q = api.client.get("/admin/call-center/queue", headers=headers,
                           params={"event_id": api.event_id}).json()
        assert q["total"] == 1, q
        print("✓ 'לחזור מאוחר יותר' מחזיר את המוזמן במועד שנבחר")
    finally:
        teardown()


def test_confirm_by_phone_uses_the_same_rsvp_logic() -> None:
    """אישור בשיחה מעדכן בדיוק את מה שהמוזמן היה מעדכן בעצמו בקישור."""
    api, teardown = bootstrap()
    try:
        headers = _admin_headers(api)
        guest = api.add_guest("מאשר בטלפון", "0507777777", party_size=4)
        _configure_track(api, days_to_event=8, commit_days=3, started_days_ago=12)

        r = api.client.post(
            f"/admin/call-center/guests/{guest['id']}/outcome",
            headers=headers,
            json={"outcome": "confirmed", "count": 3, "guest_note": "מגיעים עם תינוק"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["rsvp_status"] == "confirmed"
        assert r.json()["confirmed_count"] == 3

        # אותה שורת מוזמן שבעל/ת האירוע רואה — התעדכנה מיד.
        rows = api.client.get("/guests", headers=api.headers).json()["items"]
        row = next(g for g in rows if g["id"] == guest["id"])
        assert row["rsvp_status"] == "confirmed"
        assert row["confirmed_count"] == 3
        assert row["guest_note"] == "מגיעים עם תינוק"

        # וירד מהתור.
        q = api.client.get("/admin/call-center/queue", headers=headers,
                           params={"event_id": api.event_id}).json()
        assert q["total"] == 0
        print("✓ אישור בשיחה = אותו עדכון בדיוק כמו אישור מהקישור")
    finally:
        teardown()


def test_timeline_merges_calls_and_messages() -> None:
    """יומן הפעילות של המוזמן מציג גם שיחות טלפון וגם הודעות, לפי הזמן."""
    api, teardown = bootstrap()
    try:
        headers = _admin_headers(api)
        guest = api.add_guest("עם היסטוריה", "0508888888", party_size=2)
        _configure_track(api, days_to_event=8, commit_days=3, started_days_ago=12)

        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=headers, json={"outcome": "busy"})
        detail = api.client.get(f"/admin/call-center/guests/{guest['id']}",
                                headers=headers).json()
        calls = [i for i in detail["timeline"] if i["channel"] == "phone"]
        assert len(calls) == 1
        assert "תפוס" in calls[0]["label"]
        assert calls[0]["round_number"] >= 1
        print("✓ יומן הפעילות כולל את שיחות הטלפון")
    finally:
        teardown()


def test_regular_user_cannot_reach_the_call_center() -> None:
    """המודול הוא אדמין בלבד — משתמש רגיל מקבל 403."""
    api, teardown = bootstrap()
    try:
        r = api.client.get("/admin/call-center", headers=api.headers)
        assert r.status_code == 403, r.status_code
        print("✓ משתמש רגיל חסום מ-Call Center")
    finally:
        teardown()


if __name__ == "__main__":
    try:
        test_event_hidden_until_its_call_round_arrives()
        test_due_round_lists_only_open_guests()
        test_no_answer_removes_from_queue_until_next_round()
        test_callback_returns_the_guest_at_the_chosen_time()
        test_confirm_by_phone_uses_the_same_rsvp_logic()
        test_timeline_merges_calls_and_messages()
        test_regular_user_cannot_reach_the_call_center()
    finally:
        shutdown()
