"""רגרסיה 1 — Call Center מול Workflow אישורי ההגעה: מנגנון תאריכים אחד.

הדרישה הנבדקת כאן: ל-Call Center **אין** לוח זמנים משלו. הוא ומסך אישורי
ההגעה של בעל האירוע קוראים את אותם תאריכים מאותו מנוע (``rsvp_timeline``).

מה שמוכח בקובץ הזה:
1. ``rsvp_track_started_at`` נקבע פעם אחת בלבד ולא נדרס בהפעלות חוזרות.
2. תאריכי הסבבים יציבים — רענון מסך לא מזיז אותם.
3. כניסה ביום אחר (או בעוד שבוע) לא מחשבת את הסבבים מחדש.
4. מסך אישורי ההגעה ו-Call Center מציגים **בדיוק** את אותם תאריכי סבבי שיחות.
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402
from tests.call_center_helpers import (  # noqa: E402
    admin_headers,
    configure_track,
    event_of,
)


def _rounds_at(event, when: datetime) -> list:
    """תאריכי סבבי השיחות כפי שהמנוע מחשב אותם בנקודת זמן נתונה."""
    from app import rsvp_timeline

    return [(p.round_number, p.date) for p in rsvp_timeline.call_rounds(event, when)]


def test_track_start_is_set_once_and_never_moves() -> None:
    """ההפעלה קובעת עוגן פעם אחת; הפעלה חוזרת לא דורסת אותו."""
    api, teardown = bootstrap()
    try:
        api.add_guest("אורח", "0501111111", party_size=2)
        api.client.patch("/event", headers=api.headers, json={
            "event_date": (date.today() + timedelta(days=30)).isoformat(),
            "event_time": "19:00",
        })

        r1 = api.client.post("/automation/track/activate", headers=api.headers, json={})
        assert r1.status_code == 200, r1.text
        first_anchor = event_of(api).rsvp_track_started_at
        assert first_anchor is not None

        # הפעלה חוזרת (המשתמש לוחץ שוב / המסך נטען שוב) — העוגן לא זז.
        api.client.post("/automation/track/activate", headers=api.headers, json={})
        api.client.post("/automation/track/advance", headers=api.headers)
        assert event_of(api).rsvp_track_started_at == first_anchor
        print("✓ rsvp_track_started_at נקבע פעם אחת ולא נדרס")
    finally:
        teardown()


def test_round_dates_are_stable_across_refreshes_and_days() -> None:
    """אותו אירוע, חישוב בימים שונים — אותם תאריכי סבבים בדיוק."""
    api, teardown = bootstrap()
    try:
        api.add_guest("אורח", "0502222222", party_size=1)
        configure_track(api)
        event = event_of(api)

        baseline = _rounds_at(event, datetime.utcnow())
        assert baseline, "הבדיקה מצפה לסבבי שיחות מחושבים"

        # רענון מיידי (אותו יום, שנייה אחר כך) — זהה.
        assert _rounds_at(event, datetime.utcnow() + timedelta(seconds=1)) == baseline
        # כניסה מחר, ובעוד שלושה ימים — עדיין אותם תאריכים.
        for days in (1, 2, 3):
            later = _rounds_at(event, datetime.utcnow() + timedelta(days=days))
            assert later == baseline, f"התאריכים זזו אחרי {days} ימים: {later} != {baseline}"
        print("✓ תאריכי הסבבים יציבים ברענון ובימים שונים")
    finally:
        teardown()


def test_owner_timeline_and_call_center_show_identical_round_dates() -> None:
    """מסך אישורי ההגעה של בעל האירוע ו-Call Center — אותם תאריכים."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        api.add_guest("אורח ממתין", "0503333333", party_size=2)
        configure_track(api)

        # מה שבעל/ת האירוע רואה במסך אישורי ההגעה.
        timeline = api.client.get("/automation/timeline", headers=api.headers).json()
        assert timeline["configured"] is True
        owner_call_dates = [
            day["date"]
            for day in timeline["days"]
            for action in day["actions"]
            if action["type"] == "call_round"
        ]
        assert owner_call_dates, "מסך אישורי ההגעה לא הציג סבבי שיחות"

        # מה שה-Call Center רואה — הסבב הפעיל חייב להיות אחד מהם.
        overview = api.client.get("/admin/call-center", headers=headers).json()
        row = next(e for e in overview["events"] if e["event_id"] == api.event_id)
        assert row["round_date"] in owner_call_dates, (
            f"תאריך הסבב ב-Call Center ({row['round_date']}) "
            f"לא מופיע במסך אישורי ההגעה ({owner_call_dates})"
        )

        # וגם: הסבב שמוצג הוא האחרון שכבר הגיע, לא סתם הראשון ברשימה.
        from app import rsvp_timeline

        expected = rsvp_timeline.due_call_round(event_of(api))
        assert row["round_number"] == expected.round_number
        assert row["round_date"] == expected.date.strftime("%d/%m/%Y")
        print("✓ שני המסכים מציגים בדיוק את אותם תאריכי סבבי שיחות")
    finally:
        teardown()


def test_call_center_ignores_events_whose_track_never_started() -> None:
    """בלי הפעלת מסלול אין עוגן — ולכן אין סבב שיחות ואין שיחות."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        api.add_guest("אורח", "0504444444", party_size=1)
        # תאריכים מוגדרים, אבל ההזמנות לא נשלחו — המסלול לא הופעל.
        configure_track(api, activate=False)

        overview = api.client.get("/admin/call-center", headers=headers).json()
        ids = [e["event_id"] for e in overview["events"]]
        assert api.event_id not in ids
        print("✓ אירוע שלא הופעל בו מסלול לא נכנס ל-Call Center")
    finally:
        teardown()


def test_recording_a_call_does_not_shift_the_workflow() -> None:
    """תיעוד שיחה הוא רישום בלבד — הוא לא נוגע בעוגן ולא בסבבים."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        guest = api.add_guest("אורח", "0505555555", party_size=1)
        configure_track(api)

        before_anchor = event_of(api).rsvp_track_started_at
        before_rounds = _rounds_at(event_of(api), datetime.utcnow())

        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=headers, json={"outcome": "no_answer"})

        assert event_of(api).rsvp_track_started_at == before_anchor
        assert _rounds_at(event_of(api), datetime.utcnow()) == before_rounds
        print("✓ תיעוד שיחה לא מזיז את ה-Workflow")
    finally:
        teardown()


if __name__ == "__main__":
    try:
        test_track_start_is_set_once_and_never_moves()
        test_round_dates_are_stable_across_refreshes_and_days()
        test_owner_timeline_and_call_center_show_identical_round_dates()
        test_call_center_ignores_events_whose_track_never_started()
        test_recording_a_call_does_not_shift_the_workflow()
    finally:
        shutdown()
