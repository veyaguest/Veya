"""רגרסיה 3 — זרימת Follow-up ("ביקש שנחזור אליו") מקצה לקצה.

הכלל: Follow-up הוא **דחייה של משימת שיחה בודדת**, לא שינוי של Workflow
אישורי ההגעה. הוא לא יוצר סבב חדש, לא מזיז את תאריכי הסבבים הקיימים, ולא
נוגע בסטטוס אישור ההגעה — הוא רק אומר "אל תציג לי את המוזמן הזה עד השעה X".
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402
from tests.call_center_helpers import (  # noqa: E402
    admin_headers,
    call_logs_of,
    configure_track,
    event_of,
    guest_of,
    shift_callback,
)


def _queue(api, headers) -> dict:
    return api.client.get("/admin/call-center/queue", headers=headers,
                          params={"event_id": api.event_id}).json()


def test_followup_hides_then_returns_the_guest_marked() -> None:
    """הזרימה המלאה: קביעת מועד → ירידה מהתור → חזרה מסומנת כ-Follow-up."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        configure_track(api)
        guest = api.add_guest("ביקש שנחזור", "0508000001", party_size=2)

        when = datetime.utcnow() + timedelta(hours=4)
        r = api.client.post(
            f"/admin/call-center/guests/{guest['id']}/outcome",
            headers=headers,
            json={"outcome": "callback", "callback_at": when.isoformat() + "Z",
                  "note": "באמצע ישיבה, ביקש שנחזור אחרי 18:00"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["callback_at"] is not None

        # לפני המועד — לא בתור.
        assert _queue(api, headers)["total"] == 0

        # אחרי המועד — חוזר, ומסומן כ-Follow-up.
        shift_callback(guest["id"], minutes_from_now=-1)
        q = _queue(api, headers)
        assert q["total"] == 1, q
        row = q["items"][0]
        assert row["is_followup"] is True
        assert row["followup_count"] == 1
        assert row["last_outcome"] == "callback"
        assert row["callback_at"] is not None
        # הסטטוס לא זז.
        assert guest_of(api, guest["id"]).rsvp_status == "pending"
        print("✓ Follow-up: יורד מהתור וחוזר מסומן במועד שנקבע")
    finally:
        teardown()


def test_followup_note_and_time_are_persisted_in_call_logs() -> None:
    """ההערה והמועד נשמרים ב-call_logs, עם מי שביצע את הפעולה."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        configure_track(api)
        guest = api.add_guest("עם הערה", "0508000002", party_size=1)

        when = datetime.utcnow() + timedelta(days=1)
        api.client.post(
            f"/admin/call-center/guests/{guest['id']}/outcome",
            headers=headers,
            json={"outcome": "callback", "callback_at": when.isoformat() + "Z",
                  "note": "לחזור מחר בבוקר"},
        )
        logs = call_logs_of(api, guest["id"])
        assert len(logs) == 1
        log = logs[0]
        assert log.outcome == "callback"
        assert log.note == "לחזור מחר בבוקר"
        assert log.callback_at is not None
        assert log.callback_at.tzinfo is None, "הזמן נשמר כ-UTC נאיבי, כמו כל המערכת"
        assert abs((log.callback_at - when).total_seconds()) < 2
        assert log.created_by_id is not None, "לא נרשם מי ביצע את השיחה"
        assert log.event_id == api.event_id
        print("✓ מועד, הערה ומבצע נשמרים ב-call_logs")
    finally:
        teardown()


def test_callback_requires_a_time() -> None:
    """אי אפשר לבקש 'לחזור מאוחר יותר' בלי לקבוע מתי."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        configure_track(api)
        guest = api.add_guest("בלי מועד", "0508000003", party_size=1)

        r = api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                            headers=headers, json={"outcome": "callback"})
        assert r.status_code == 400, r.text
        assert call_logs_of(api, guest["id"]) == []
        print("✓ Follow-up בלי מועד נדחה")
    finally:
        teardown()


def test_repeated_followups_accumulate_and_latest_wins() -> None:
    """כמה Follow-ups לאותו מוזמן לאורך זמן — כולם נשמרים, האחרון קובע."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        configure_track(api)
        guest = api.add_guest("דחיין סדרתי", "0508000004", party_size=2)

        for i in range(3):
            # כל פעם הוא חוזר לתור, ואנחנו דוחים שוב.
            api.client.post(
                f"/admin/call-center/guests/{guest['id']}/outcome",
                headers=headers,
                json={"outcome": "callback",
                      "callback_at": (datetime.utcnow() + timedelta(hours=2)).isoformat() + "Z",
                      "note": f"דחייה {i + 1}"},
            )
            assert _queue(api, headers)["total"] == 0, f"אחרי דחייה {i + 1} הוא עדיין בתור"
            shift_callback(guest["id"], minutes_from_now=-1)
            q = _queue(api, headers)
            assert q["total"] == 1
            assert q["items"][0]["followup_count"] == i + 1

        logs = call_logs_of(api, guest["id"])
        assert [lg.outcome for lg in logs] == ["callback"] * 3
        assert [lg.note for lg in logs] == ["דחייה 1", "דחייה 2", "דחייה 3"]
        # כולם באותו סבב — לא נוצר סבב חדש בגלל ה-Follow-ups.
        assert len({lg.round_number for lg in logs}) == 1
        print("✓ Follow-ups חוזרים נצברים, בלי ליצור סבב חדש")
    finally:
        teardown()


def test_pending_followup_survives_a_new_round() -> None:
    """מועד Follow-up עתידי גובר גם כשנפתח סבב שיחות חדש."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        configure_track(api)
        guest = api.add_guest("דחה רחוק", "0508000005", party_size=1)

        api.client.post(
            f"/admin/call-center/guests/{guest['id']}/outcome",
            headers=headers,
            json={"outcome": "callback",
                  "callback_at": (datetime.utcnow() + timedelta(days=2)).isoformat() + "Z"},
        )
        before_round = _round_number(api)

        # מקדמים את האירוע כך שסבב מאוחר יותר נפתח.
        configure_track(api, days_to_event=5, commit_days=2, started_days_ago=14)
        after_round = _round_number(api)
        assert after_round >= before_round

        # עדיין מוסתר — ההבטחה למוזמן גוברת על פתיחת הסבב.
        assert _queue(api, headers)["total"] == 0
        print("✓ מועד Follow-up עתידי גובר גם על סבב חדש")
    finally:
        teardown()


def test_followup_does_not_change_the_workflow_schedule() -> None:
    """Follow-up לא מזיז את עוגן המסלול ולא את תאריכי הסבבים."""
    api, teardown = bootstrap()
    try:
        from app import rsvp_timeline

        headers = admin_headers(api)
        configure_track(api)
        guest = api.add_guest("אורח", "0508000006", party_size=1)

        before_anchor = event_of(api).rsvp_track_started_at
        before = [(p.round_number, p.date) for p in rsvp_timeline.call_rounds(event_of(api))]

        api.client.post(
            f"/admin/call-center/guests/{guest['id']}/outcome",
            headers=headers,
            json={"outcome": "callback",
                  "callback_at": (datetime.utcnow() + timedelta(hours=5)).isoformat() + "Z"},
        )

        assert event_of(api).rsvp_track_started_at == before_anchor
        after = [(p.round_number, p.date) for p in rsvp_timeline.call_rounds(event_of(api))]
        assert after == before
        # וגם מסך אישורי ההגעה של בעל האירוע לא השתנה.
        timeline = api.client.get("/automation/timeline", headers=api.headers).json()
        owner_dates = [
            day["date"] for day in timeline["days"]
            for a in day["actions"] if a["type"] == "call_round"
        ]
        assert owner_dates == [d.strftime("%d/%m/%Y") for _, d in after]
        print("✓ Follow-up לא נוגע ב-Workflow אישורי ההגעה")
    finally:
        teardown()


def test_followup_then_decision_closes_the_guest() -> None:
    """אחרי Follow-up, החלטה אמיתית מורידה את המוזמן סופית מהתור."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        configure_track(api)
        guest = api.add_guest("סוגר בסוף", "0508000007", party_size=3)

        api.client.post(
            f"/admin/call-center/guests/{guest['id']}/outcome",
            headers=headers,
            json={"outcome": "callback",
                  "callback_at": (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"},
        )
        shift_callback(guest["id"], minutes_from_now=-1)
        assert _queue(api, headers)["total"] == 1

        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=headers, json={"outcome": "confirmed", "count": 3})

        assert _queue(api, headers)["total"] == 0
        after = guest_of(api, guest["id"])
        assert (after.rsvp_status, after.confirmed_count) == ("confirmed", 3)
        assert [lg.outcome for lg in call_logs_of(api, guest["id"])] == ["callback", "confirmed"]
        print("✓ Follow-up ואז החלטה — המוזמן נסגר סופית")
    finally:
        teardown()


def test_waiting_and_done_never_double_count() -> None:
    """מוזמן שחזר מ-Follow-up נספר כ'ממתין' בלבד — לא גם כ'הושלם'."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        configure_track(api)
        back = api.add_guest("חזר מ-Follow-up", "0508000008", party_size=1)
        api.add_guest("עוד ממתין", "0508000009", party_size=1)
        done = api.add_guest("לא ענה", "0508000010", party_size=1)

        api.client.post(f"/admin/call-center/guests/{done['id']}/outcome",
                        headers=headers, json={"outcome": "no_answer"})
        api.client.post(
            f"/admin/call-center/guests/{back['id']}/outcome",
            headers=headers,
            json={"outcome": "callback",
                  "callback_at": (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"},
        )
        shift_callback(back["id"], minutes_from_now=-1)

        overview = api.client.get("/admin/call-center", headers=headers).json()
        row = next(e for e in overview["events"] if e["event_id"] == api.event_id)
        assert row["waiting"] == 2, row      # החוזר + מי שעוד לא טופל
        assert row["done"] == 1, row         # רק "לא ענה"
        assert row["waiting"] + row["done"] == 3, "סך המשימות חייב להיות 3 מוזמנים"
        print("✓ ספירת 'ממתינות' ו'הושלמו' היא חלוקה זרה, בלי כפילות")
    finally:
        teardown()


def _round_number(api) -> int:
    from app import rsvp_timeline

    placement = rsvp_timeline.due_call_round(event_of(api))
    return placement.round_number if placement else 0


if __name__ == "__main__":
    try:
        test_followup_hides_then_returns_the_guest_marked()
        test_followup_note_and_time_are_persisted_in_call_logs()
        test_callback_requires_a_time()
        test_repeated_followups_accumulate_and_latest_wins()
        test_pending_followup_survives_a_new_round()
        test_followup_does_not_change_the_workflow_schedule()
        test_followup_then_decision_closes_the_guest()
        test_waiting_and_done_never_double_count()
    finally:
        shutdown()
