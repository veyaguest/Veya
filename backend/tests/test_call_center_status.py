"""רגרסיה 2+4 — הפרדה מוחלטת בין סטטוס RSVP לבין תוצאת שיחת טלפון.

זו הדרישה הרגישה ביותר במודול. שני צירים **נפרדים**:

  ציר א' — סטטוס אישור הגעה (``Guest.rsvp_status``):
      pending / confirmed / declined / maybe
  ציר ב' — תוצאת שיחה (``CallLog.outcome``):
      confirmed / declined / no_answer / busy / wrong_number / callback

"לא ענה" הוא **ציר ב' בלבד**. הוא לא הופך את המוזמן ל"ממתין", לא מאפס אותו,
ולא נוגע ב-rsvp_status בשום צורה. רק "אישר הגעה"/"לא מגיע" חוצים לציר א' —
ואז דרך אותה לוגיקה בדיוק שרצה כשהמוזמן עונה בעצמו בקישור מ-WhatsApp.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402
from tests.call_center_helpers import (  # noqa: E402
    admin_headers,
    call_logs_of,
    configure_track,
    guest_of,
)

# תוצאות שיחה שהן תיעוד בלבד — אסור שיגעו בסטטוס אישור ההגעה.
LOG_ONLY_OUTCOMES = ["no_answer", "busy", "wrong_number"]


def test_call_only_outcomes_never_touch_rsvp_status() -> None:
    """'לא ענה' / 'תפוס' / 'מספר שגוי' — תיעוד שיחה בלבד, מכל סטטוס פתיחה."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        configure_track(api)

        for outcome in LOG_ONLY_OUTCOMES:
            for start_status in ("pending", "maybe"):
                guest = api.add_guest(
                    f"{outcome}-{start_status}", f"05{abs(hash(outcome + start_status)) % 10**8:08d}",
                    party_size=2,
                )
                api.client.patch(f"/guests/{guest['id']}", headers=api.headers,
                                 json={"rsvp_status": start_status})

                r = api.client.post(
                    f"/admin/call-center/guests/{guest['id']}/outcome",
                    headers=headers, json={"outcome": outcome},
                )
                assert r.status_code == 200, r.text

                after = guest_of(api, guest["id"])
                assert after.rsvp_status == start_status, (
                    f"'{outcome}' שינה סטטוס מ-{start_status} ל-{after.rsvp_status}"
                )
                assert after.confirmed_count is None
                # אבל כן נרשם ביומן השיחות.
                logs = call_logs_of(api, guest["id"])
                assert [lg.outcome for lg in logs] == [outcome]
        print("✓ לא ענה / תפוס / מספר שגוי — לא נוגעים בסטטוס אישור ההגעה")
    finally:
        teardown()


def test_no_answer_does_not_reset_a_decided_guest() -> None:
    """גם אם מוזמן כבר אישר, תיעוד 'לא ענה' לא מחזיר אותו ל'ממתין'."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        configure_track(api)
        guest = api.add_guest("כבר אישר", "0507000001", party_size=3)
        # מאשר דרך הקישור האישי — הדרך האמיתית שבה נקבע confirmed_count
        # (``GuestUpdate`` בכוונה לא חושף את השדה הזה לעריכה ידנית).
        token = guest_of(api, guest["id"]).guest_token
        api.client.post(f"/confirm/{token}", json={"coming": True, "count": 3})
        assert guest_of(api, guest["id"]).confirmed_count == 3

        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=headers, json={"outcome": "no_answer"})

        after = guest_of(api, guest["id"])
        assert after.rsvp_status == "confirmed"
        assert after.confirmed_count == 3
        print("✓ 'לא ענה' לא מאפס מוזמן שכבר החליט")
    finally:
        teardown()


def test_confirm_by_phone_matches_the_public_link_exactly() -> None:
    """אישור בשיחה ואישור מהקישור הציבורי — אותה תוצאה בדיוק על שורת המוזמן."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        configure_track(api)

        by_phone = api.add_guest("אישר בטלפון", "0507000002", party_size=4)
        by_link = api.add_guest("אישר בקישור", "0507000003", party_size=4)

        api.client.post(f"/admin/call-center/guests/{by_phone['id']}/outcome",
                        headers=headers,
                        json={"outcome": "confirmed", "count": 2, "guest_note": "בלי גלוטן"})

        token = guest_of(api, by_link["id"]).guest_token
        r = api.client.post(f"/confirm/{token}",
                            json={"coming": True, "count": 2, "note": "בלי גלוטן"})
        assert r.status_code == 200, r.text

        a, b = guest_of(api, by_phone["id"]), guest_of(api, by_link["id"])
        assert (a.rsvp_status, a.confirmed_count, a.guest_note) == \
               (b.rsvp_status, b.confirmed_count, b.guest_note) == \
               ("confirmed", 2, "בלי גלוטן")
        print("✓ אישור בטלפון זהה לחלוטין לאישור מהקישור")
    finally:
        teardown()


def test_decline_by_phone_uses_the_existing_status() -> None:
    """'לא מגיע' בשיחה = בדיוק הסטטוס הקיים במערכת, כולל אפס מאשרים."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        configure_track(api)
        guest = api.add_guest("מבטל בטלפון", "0507000004", party_size=5)

        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=headers, json={"outcome": "declined"})

        after = guest_of(api, guest["id"])
        assert after.rsvp_status == "declined"
        assert after.confirmed_count == 0
        assert after.effective_seats == 0  # לא נספר בהושבה
        print("✓ 'לא מגיע' בשיחה מעדכן את הסטטוס הקיים כמו שצריך")
    finally:
        teardown()


def test_confirm_count_is_clamped_like_the_public_page() -> None:
    """אותה הגנה על כמות מאשרים בשני הערוצים (1..30)."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        configure_track(api)
        guest = api.add_guest("כמות חריגה", "0507000005", party_size=2)

        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=headers, json={"outcome": "confirmed", "count": 999})
        assert guest_of(api, guest["id"]).confirmed_count == 30

        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=headers, json={"outcome": "confirmed", "count": 0})
        assert guest_of(api, guest["id"]).confirmed_count == 1
        print("✓ כמות המאשרים מוגבלת בדיוק כמו בדף הציבורי")
    finally:
        teardown()


def test_decided_guests_leave_the_queue_whoever_decided() -> None:
    """מי שהחליט — יורד מהתור, לא משנה מאיזה ערוץ הגיעה ההחלטה."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        configure_track(api)
        open_guest = api.add_guest("נשאר בתור", "0507000006", party_size=1)
        via_owner = api.add_guest("בעל האירוע עדכן", "0507000007", party_size=1)
        via_link = api.add_guest("ענה בקישור", "0507000008", party_size=1)

        # בעל/ת האירוע מעדכן ידנית במסך המוזמנים.
        api.client.patch(f"/guests/{via_owner['id']}", headers=api.headers,
                         json={"rsvp_status": "declined"})
        # המוזמן עונה בעצמו בקישור.
        token = guest_of(api, via_link["id"]).guest_token
        api.client.post(f"/confirm/{token}", json={"coming": True, "count": 1})

        q = api.client.get("/admin/call-center/queue", headers=headers,
                           params={"event_id": api.event_id}).json()
        names = sorted(g["full_name"] for g in q["items"])
        assert names == ["נשאר בתור"], names
        assert q["items"][0]["guest_id"] == open_guest["id"]
        print("✓ החלטה בכל ערוץ מורידה מיד מהתור")
    finally:
        teardown()


def test_maybe_guests_stay_in_the_queue() -> None:
    """'מתלבט' הוא עדיין לא תשובה — הוא נשאר ברשימת השיחות."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        configure_track(api)
        guest = api.add_guest("מתלבט", "0507000009", party_size=2)
        api.client.patch(f"/guests/{guest['id']}", headers=api.headers,
                         json={"rsvp_status": "maybe"})

        q = api.client.get("/admin/call-center/queue", headers=headers,
                           params={"event_id": api.event_id}).json()
        assert [g["rsvp_status"] for g in q["items"]] == ["maybe"]
        print("✓ 'מתלבט' נשאר בתור השיחות")
    finally:
        teardown()


def test_unknown_outcome_is_rejected() -> None:
    """אין דלת אחורית להמצאת תוצאות/סטטוסים חדשים דרך ה-API."""
    api, teardown = bootstrap()
    try:
        headers = admin_headers(api)
        configure_track(api)
        guest = api.add_guest("אורח", "0507000010", party_size=1)

        for bad in ("pending", "maybe", "answered", ""):
            r = api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                                headers=headers, json={"outcome": bad})
            assert r.status_code == 400, f"'{bad}' התקבל: {r.status_code}"
        assert call_logs_of(api, guest["id"]) == []
        print("✓ תוצאת שיחה לא מוכרת נדחית")
    finally:
        teardown()


if __name__ == "__main__":
    try:
        test_call_only_outcomes_never_touch_rsvp_status()
        test_no_answer_does_not_reset_a_decided_guest()
        test_confirm_by_phone_matches_the_public_link_exactly()
        test_decline_by_phone_uses_the_existing_status()
        test_confirm_count_is_clamped_like_the_public_page()
        test_decided_guests_leave_the_queue_whoever_decided()
        test_maybe_guests_stay_in_the_queue()
        test_unknown_outcome_is_rejected()
    finally:
        shutdown()
