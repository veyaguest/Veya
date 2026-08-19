"""רגרסיה — "מספר שגוי": תוצאת שיחה + התראת דאטה לבעל/ת האירוע.

שלושה עולמות נפרדים שאסור לערבב (וזה מה שנבדק כאן):

  RSVP        ממתין / מגיע / לא מגיע / מתלבט     — לא נוגעים בו
  Call Result לא ענה / תפוס / מספר שגוי / ...    — נשמר ב-call_logs
  Data Alert  "נדרש תיקון מספר טלפון"            — נגזר, לא סטטוס

"מספר שגוי" אינו ניסיון שיחה שנכשל אלא תקלת דאטה: אין טעם לחייג שוב לאותו
מספר בסבב הבא. לכן המוזמן יוצא מתור השיחות **לגמרי** עד שהמספר יתוקן, ובמקביל
נפתחת התראה לבעל/ת האירוע. ההתראה נסגרת מעצמה ברגע שהמספר מתעדכן — אין דגל
"טופל" שצריך לתחזק.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402
from tests.call_center_helpers import (  # noqa: E402
    call_logs_of,
    configure_track,
    event_of,
    guest_of,
    standalone_admin,
)


def _queue(api, headers) -> dict:
    return api.client.get("/admin/call-center/queue", headers=headers,
                          params={"event_id": api.event_id}).json()


def _alerts(api) -> dict:
    return api.client.get("/guests/data-alerts", headers=api.headers).json()


def test_wrong_number_is_recorded_as_a_call_result() -> None:
    """(1) התוצאה נשמרת ב-call_logs עם תאריך, שעה, מבצע והמספר שנוסה."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("מספר שגוי", "0501230001", party_size=2)

        r = api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                            headers=admin,
                            json={"outcome": "wrong_number", "note": "מספר לא מחובר"})
        assert r.status_code == 200, r.text
        assert r.json()["outcome"] == "wrong_number"

        logs = call_logs_of(api, guest["id"])
        assert len(logs) == 1
        log = logs[0]
        assert log.outcome == "wrong_number"
        assert log.note == "מספר לא מחובר"
        assert log.created_at is not None          # תאריך ושעה
        assert log.created_by_id is not None       # מי ביצע
        assert log.phone_at_call == "0501230001"   # לאיזה מספר חייגנו
        assert log.round_number >= 1
        print("✓ 'מספר שגוי' נשמר כתוצאת שיחה מלאה")
    finally:
        teardown()


def test_wrong_number_raises_an_alert_for_the_owner() -> None:
    """(2) נוצרת התראת 'נדרש תיקון מספר טלפון' לבעל/ת האירוע."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("ישראל כהן", "0501230002", party_size=3)
        assert _alerts(api)["total"] == 0

        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=admin, json={"outcome": "wrong_number"})

        alerts = _alerts(api)
        assert alerts["total"] == 1
        row = alerts["phone_fix"][0]
        assert row["kind"] == "phone_fix"
        assert row["guest_id"] == guest["id"]
        assert row["full_name"] == "ישראל כהן"
        assert row["phone"] == "0501230002"
        assert row["attempts"] == 1
        # ההתראה מציגה את סטטוס ה-RSVP כדי להבהיר שהוא *לא* השתנה.
        assert row["rsvp_status"] == "pending"
        print("✓ נוצרת התראת 'נדרש תיקון מספר טלפון' לבעל האירוע")
    finally:
        teardown()


def test_wrong_number_guest_does_not_return_to_the_queue() -> None:
    """(3) המוזמן לא חוזר אוטומטית לתור — גם לא בסבב שיחות מאוחר יותר."""
    api, teardown = bootstrap()
    try:
        from app import rsvp_timeline

        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("לא יחזור", "0501230003", party_size=1)
        api.add_guest("כן ממתין", "0501230004", party_size=1)

        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=admin, json={"outcome": "wrong_number"})
        q = _queue(api, admin)
        assert [g["full_name"] for g in q["items"]] == ["כן ממתין"]

        # מקדמים לסבב שיחות מאוחר יותר — הוא עדיין לא חוזר.
        before = rsvp_timeline.due_call_round(event_of(api)).round_number
        configure_track(api, days_to_event=4, commit_days=2, started_days_ago=16)
        after = rsvp_timeline.due_call_round(event_of(api)).round_number
        assert after >= before

        q = _queue(api, admin)
        names = [g["full_name"] for g in q["items"]]
        assert "לא יחזור" not in names, f"המוזמן חזר לתור למרות מספר שגוי: {names}"
        print("✓ מוזמן עם מספר שגוי לא חוזר לתור בסבב הבא")
    finally:
        teardown()


def test_wrong_number_does_not_change_rsvp_or_delete_the_guest() -> None:
    """(4) סטטוס ה-RSVP לא משתנה, אין סימון 'לא מגיע', והמוזמן לא נמחק."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        for idx, start in enumerate(("pending", "maybe")):
            guest = api.add_guest(f"שומר סטטוס {start}", f"05012319{idx:02d}", party_size=2)
            api.client.patch(f"/guests/{guest['id']}", headers=api.headers,
                             json={"rsvp_status": start})

            api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                            headers=admin, json={"outcome": "wrong_number"})

            after = guest_of(api, guest["id"])
            assert after is not None, "המוזמן נמחק"
            assert after.rsvp_status == start
            assert after.rsvp_status != "declined"
            assert after.confirmed_count is None
        print("✓ 'מספר שגוי' לא נוגע בסטטוס ה-RSVP ולא מוחק את המוזמן")
    finally:
        teardown()


def test_owner_can_fix_the_phone_number() -> None:
    """(5) בעל/ת האירוע מעדכן/ת את המספר דרך עריכת המוזמן הרגילה."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("צריך תיקון", "0501230005", party_size=1)
        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=admin, json={"outcome": "wrong_number"})

        r = api.client.patch(f"/guests/{guest['id']}", headers=api.headers,
                             json={"phone": "0521230099"})
        assert r.status_code == 200, r.text
        assert guest_of(api, guest["id"]).phone == "0521230099"
        print("✓ בעל האירוע יכול לעדכן את המספר")
    finally:
        teardown()


def test_alert_closes_itself_after_the_number_is_fixed() -> None:
    """(6) אחרי עדכון המספר ההתראה נסגרת — בלי פעולה נוספת."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("יתוקן", "0501230006", party_size=1)
        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=admin, json={"outcome": "wrong_number"})
        assert _alerts(api)["total"] == 1

        api.client.patch(f"/guests/{guest['id']}", headers=api.headers,
                         json={"phone": "0521230098"})

        assert _alerts(api)["total"] == 0
        # יומן השיחות נשאר — ההיסטוריה לא נמחקת, רק ההתראה נסגרה.
        assert [lg.outcome for lg in call_logs_of(api, guest["id"])] == ["wrong_number"]
        print("✓ ההתראה נסגרת מעצמה אחרי תיקון המספר")
    finally:
        teardown()


def test_fixed_number_returns_the_guest_to_the_queue() -> None:
    """(7) אחרי תיקון — המוזמן שוב מועמד לסבב, אם ה-Workflow עדיין דורש זאת."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("חוזר אחרי תיקון", "0501230007", party_size=2)

        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=admin, json={"outcome": "wrong_number"})
        assert _queue(api, admin)["total"] == 0

        api.client.patch(f"/guests/{guest['id']}", headers=api.headers,
                         json={"phone": "0521230097"})

        q = _queue(api, admin)
        assert q["total"] == 1, q
        assert q["items"][0]["guest_id"] == guest["id"]
        assert q["items"][0]["phone"] == "0521230097"
        # ועדיין: סטטוס ה-RSVP לא זז בגלל תיקון המספר.
        assert guest_of(api, guest["id"]).rsvp_status == "pending"
        print("✓ אחרי תיקון המספר המוזמן חוזר להיות מועמד לשיחה")
    finally:
        teardown()


def test_fixing_a_number_does_not_create_a_new_round() -> None:
    """(8) לא נוצר סבב שיחות חדש, וה-Workflow לא זז."""
    api, teardown = bootstrap()
    try:
        from app import rsvp_timeline

        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("אורח", "0501230008", party_size=1)

        before_anchor = event_of(api).rsvp_track_started_at
        before = [(p.round_number, p.date) for p in rsvp_timeline.call_rounds(event_of(api))]

        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=admin, json={"outcome": "wrong_number"})
        api.client.patch(f"/guests/{guest['id']}", headers=api.headers,
                         json={"phone": "0521230096"})

        assert event_of(api).rsvp_track_started_at == before_anchor
        after = [(p.round_number, p.date) for p in rsvp_timeline.call_rounds(event_of(api))]
        assert after == before, "מספר סבבי השיחות או התאריכים השתנו"
        assert len(after) == 3, "מספר הסבבים בסבב הקבוע השתנה"
        print("✓ תיקון מספר לא יוצר סבב חדש ולא מזיז את ה-Workflow")
    finally:
        teardown()


def test_repeated_wrong_numbers_are_counted() -> None:
    """דיווח חוזר על אותו מוזמן (אחרי תיקון שגוי) נספר בהתראה."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("שוב שגוי", "0501230009", party_size=1)

        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=admin, json={"outcome": "wrong_number"})
        # הבעלים תיקן — אבל גם המספר החדש שגוי.
        api.client.patch(f"/guests/{guest['id']}", headers=api.headers,
                         json={"phone": "0521230095"})
        assert _alerts(api)["total"] == 0
        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=admin, json={"outcome": "wrong_number"})

        alerts = _alerts(api)
        assert alerts["total"] == 1
        assert alerts["phone_fix"][0]["phone"] == "0521230095"
        assert len(call_logs_of(api, guest["id"])) == 2
        print("✓ דיווח חוזר על מספר שגוי נספר ומוצג נכון")
    finally:
        teardown()


def test_alerts_are_scoped_to_the_owning_event() -> None:
    """התראות דאטה לא דולפות בין אירועים."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        admin = standalone_admin(api_a)
        configure_track(api_a)
        configure_track(api_b)
        guest_a = api_a.add_guest("של A", "0501230010", party_size=1)
        api_b.add_guest("של B", "0501230011", party_size=1)

        api_a.client.post(f"/admin/call-center/guests/{guest_a['id']}/outcome",
                          headers=admin, json={"outcome": "wrong_number"})

        assert _alerts(api_a)["total"] == 1
        assert _alerts(api_b)["total"] == 0, "התראה של אירוע A דלפה לאירוע B"
        print("✓ התראות הדאטה מוגבלות לאירוע שלהן")
    finally:
        teardown_a()
        teardown_b()


def test_counts_stay_correct_with_every_outcome_mixed() -> None:
    """ספירה משולבת: ממתין, לא ענה, Follow-up שחזר, ומספר שגוי — יחד.

    הכלל: ``waiting`` ו-``done`` הם **חלוקה זרה** של מוזמני הסבב, כך שכל
    מוזמן נספר בדיוק פעם אחת ואף אחד לא "נעלם" מהמונים.
    - "מספר שגוי" נספר כ**טופל**: השיחה בוצעה בפועל (ככה בכלל גילינו שהמספר
      שגוי). הוא פשוט לא יחזור להיות *ממתין* עד שהמספר יתוקן — וזו בדיוק
      הדרישה. במקביל הוא מופיע כהתראת דאטה לבעל/ת האירוע.
    - מי שחזר מ-Follow-up נספר כ**ממתין** בלבד, למרות שיש לו שיחה בסבב.
    """
    from datetime import datetime, timedelta

    from tests.call_center_helpers import shift_callback

    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        api.add_guest("ממתין נקי", "0501240001", party_size=1)
        no_answer = api.add_guest("לא ענה", "0501240002", party_size=1)
        followup = api.add_guest("חזר מ-Follow-up", "0501240003", party_size=1)
        wrong = api.add_guest("מספר שגוי", "0501240004", party_size=1)

        api.client.post(f"/admin/call-center/guests/{no_answer['id']}/outcome",
                        headers=admin, json={"outcome": "no_answer"})
        api.client.post(
            f"/admin/call-center/guests/{followup['id']}/outcome",
            headers=admin,
            json={"outcome": "callback",
                  "callback_at": (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"},
        )
        shift_callback(followup["id"], minutes_from_now=-1)
        api.client.post(f"/admin/call-center/guests/{wrong['id']}/outcome",
                        headers=admin, json={"outcome": "wrong_number"})

        overview = api.client.get("/admin/call-center", headers=admin).json()
        row = next(e for e in overview["events"] if e["event_id"] == api.event_id)
        # ממתינים: "ממתין נקי" + מי שחזר מ-Follow-up.
        assert row["waiting"] == 2, row
        # טופלו: "לא ענה" + "מספר שגוי" (שתי שיחות שבוצעו בפועל בסבב הזה).
        assert row["done"] == 2, row
        # ארבעה מוזמנים, כל אחד נספר פעם אחת בדיוק — בלי כפילות ובלי היעלמות.
        # (נבדק ברמת האירוע: ``overview["total"]`` מסכם את *כל* האירועים
        # במסד הבדיקות המשותף, ולכן אינו מדד מבודד לבדיקה הזו.)
        assert row["waiting"] + row["done"] == 4, row

        # ואימות ההפרדה: המוזמן עם המספר השגוי מופיע כהתראת דאטה, לא כשיחה.
        alerts = _alerts(api)
        assert alerts["total"] == 1
        assert alerts["phone_fix"][0]["guest_id"] == wrong["id"]
        names = [g["full_name"] for g in _queue(api, admin)["items"]]
        assert "מספר שגוי" not in names
        print("✓ ספירת המשימות נכונה עם כל סוגי התוצאות יחד")
    finally:
        teardown()


def test_wrong_number_is_not_an_rsvp_status() -> None:
    """אין ולא ייווצר סטטוס RSVP בשם 'מספר שגוי'."""
    from app import schemas

    allowed = set(schemas.RsvpStatus.__args__)
    assert allowed == {"pending", "confirmed", "declined", "maybe"}, allowed
    assert "wrong_number" not in allowed
    # וגם: לא ניתן להזריק אותו כסטטוס דרך ה-API.
    api, teardown = bootstrap()
    try:
        guest = api.add_guest("אורח", "0501230012", party_size=1)
        r = api.client.patch(f"/guests/{guest['id']}", headers=api.headers,
                             json={"rsvp_status": "wrong_number"})
        assert r.status_code == 422, r.status_code
        print("✓ 'מספר שגוי' אינו סטטוס RSVP ואי אפשר להזריק אותו")
    finally:
        teardown()


if __name__ == "__main__":
    try:
        test_wrong_number_is_recorded_as_a_call_result()
        test_wrong_number_raises_an_alert_for_the_owner()
        test_wrong_number_guest_does_not_return_to_the_queue()
        test_wrong_number_does_not_change_rsvp_or_delete_the_guest()
        test_owner_can_fix_the_phone_number()
        test_alert_closes_itself_after_the_number_is_fixed()
        test_fixed_number_returns_the_guest_to_the_queue()
        test_fixing_a_number_does_not_create_a_new_round()
        test_repeated_wrong_numbers_are_counted()
        test_alerts_are_scoped_to_the_owning_event()
        test_wrong_number_is_not_an_rsvp_status()
    finally:
        shutdown()
