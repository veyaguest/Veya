""""שיחות להיום" — טווחי תצוגה (היום / מחר / בהמשך) במסך ה-Call Center.

עיקרון מנחה: **אין כאן מנוע תאריכים חדש.** כל טווח מחושב ע"י הרצה חוזרת של
``call_center.build_queues`` הקיים עם ``now`` וירטואלי אחר (בדיוק אותו פרמטר
שהפונקציה כבר תומכת בו — ראו ``app/rsvp_timeline.py::due_call_round``),
והפרש-קבוצות בין ההרצות (ראו ``call_center.build_queues_for_scope``).
לא נוצר סבב/תאריך/סטטוס חדש; ה-Workflow הקיים נשאר יחיד ולא נגוע.

לבניית תרחישי "סבב שנפתח בדיוק מחר" בלי לנחש תאריכים, הבדיקות כאן משתמשות
ב-``_days_ago_for_first_round_on`` — פונקציית עזר שמריצה את המנוע האמיתי
(``rsvp_timeline.call_rounds``) על אובייקט אירוע זמני (בזיכרון בלבד, בלי
DB) ומוצאת את הפרמטר המתאים. זו עדיין קריאה ל-**מנוע האמיתי** — לא נוסחה
עצמאית לבדיקה שיכולה לסטות ממנו.
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap  # noqa: E402
from tests.call_center_helpers import (  # noqa: E402
    call_logs_of,
    configure_track,
    guest_of,
    phone_agent,
    standalone_admin,
)

# פרמטרים שנבדקו בפועל מול המנוע (ראו הבדיקות למטה): עם אלה, הסבב הראשון
# יכול לנחות בדיוק על "היום" (started_days_ago גבוה) או בדיוק על "מחר"
# (started_days_ago קטן ב-1 עד 3), בכל יום בשבוע.
DAYS_TO_EVENT = 9
COMMIT_DAYS = 2


def _days_ago_for_first_round_on(target: date, *, days_to_event=DAYS_TO_EVENT, commit_days=COMMIT_DAYS) -> int:
    """מוצא ``started_days_ago`` כך שהסבב הראשון ייפול בדיוק ב-``target``.

    מריץ את ``rsvp_timeline.call_rounds`` (המנוע האמיתי) על אירוע זמני
    בזיכרון — לא נוגע ב-DB, מהיר, ותקף בכל יום בשבוע שבו רצה הבדיקה.
    """
    from app import models, rsvp_timeline

    for started_days_ago in range(0, 45):
        probe = models.Event(
            event_date=(date.today() + timedelta(days=days_to_event)).isoformat(),
            event_time="19:00",
            venue_commit_days_before=commit_days,
            rsvp_track_active=True,
            rsvp_track_started_at=datetime.utcnow() - timedelta(days=started_days_ago),
        )
        rounds = rsvp_timeline.call_rounds(probe)
        if rounds and rounds[0].date == target:
            return started_days_ago
    raise AssertionError(f"לא נמצא started_days_ago שמעמיד סבב 1 בתאריך {target}")


def _overview(api, headers, scope="today") -> dict:
    r = api.client.get("/admin/call-center", headers=headers, params={"scope": scope})
    assert r.status_code == 200, r.text
    return r.json()


def _queue(api, headers, *, scope="today", **params) -> dict:
    r = api.client.get("/admin/call-center/queue", headers=headers,
                       params={"scope": scope, **params})
    assert r.status_code == 200, r.text
    return r.json()


# ── 1–3. היום / אתמול / מחר ──────────────────────────────────────────────

def test_round_due_today_appears_in_today_scope() -> None:
    """(1) סבב שהיום בדיוק תאריך הפתיחה שלו — מופיע ב'היום'."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        api.add_guest("ישראל כהן", "0509400001", party_size=2)
        started = _days_ago_for_first_round_on(date.today())
        configure_track(api, days_to_event=DAYS_TO_EVENT, commit_days=COMMIT_DAYS,
                        started_days_ago=started)

        overview = _overview(api, admin, "today")
        ids = [e["event_id"] for e in overview["events"]]
        assert api.event_id in ids, overview
        assert overview["scope"] == "today"

        items = _queue(api, admin, scope="today", event_id=api.event_id)["items"]
        assert [g["full_name"] for g in items] == ["ישראל כהן"]
        print("✓ סבב שנפתח היום מופיע בתצוגת 'היום'")
    finally:
        teardown()


def test_round_due_only_tomorrow_is_hidden_from_today() -> None:
    """(3) סבב שעוד לא נפתח (ייפתח רק מחר) — לא מופיע ב'היום'."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        api.add_guest("דוד לוי", "0509400002", party_size=1)
        started = _days_ago_for_first_round_on(date.today() + timedelta(days=1))
        configure_track(api, days_to_event=DAYS_TO_EVENT, commit_days=COMMIT_DAYS,
                        started_days_ago=started)

        today_ids = [e["event_id"] for e in _overview(api, admin, "today")["events"]]
        assert api.event_id not in today_ids, "סבב שעוד לא נפתח לא אמור להופיע ב'היום'"
        print("✓ סבב שנפתח רק מחר לא מופיע בתצוגת 'היום'")
    finally:
        teardown()


def test_round_due_only_tomorrow_appears_in_tomorrow_scope() -> None:
    """(3 המשך) אותו סבב — כן מופיע תחת 'מחר', בלי לחזור גם ב'היום'."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        api.add_guest("דוד לוי", "0509400003", party_size=1)
        started = _days_ago_for_first_round_on(date.today() + timedelta(days=1))
        configure_track(api, days_to_event=DAYS_TO_EVENT, commit_days=COMMIT_DAYS,
                        started_days_ago=started)

        tomorrow_ids = [e["event_id"] for e in _overview(api, admin, "tomorrow")["events"]]
        assert api.event_id in tomorrow_ids
        items = _queue(api, admin, scope="tomorrow", event_id=api.event_id)["items"]
        assert [g["full_name"] for g in items] == ["דוד לוי"]
        print("✓ סבב שנפתח מחר מופיע תחת 'מחר' בלבד")
    finally:
        teardown()


def test_event_fully_resolved_yesterday_does_not_linger_today() -> None:
    """(2) אירוע שהסבב שלו כבר טופל במלואו לא נשאר תקוע בתצוגת 'היום'.

    "לא להציג שיחות מאתמול" — אירוע שכל מוזמניו כבר אישרו/ביטלו לא אמור
    להמשיך להופיע יום אחרי יום כאילו נשאר בו עוד עבודה.
    """
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        guest = api.add_guest("נענה אתמול", "0509400004", party_size=1)
        configure_track(api)  # started_days_ago=12 — סבב פעיל כבר כמה ימים

        r = api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                            headers=admin, json={"outcome": "confirmed", "count": 1})
        assert r.status_code == 200, r.text

        overview = _overview(api, admin, "today")
        ids = [e["event_id"] for e in overview["events"]]
        assert api.event_id not in ids, "אירוע שכל מוזמניו טופלו לא אמור להישאר ברשימה"
        print("✓ אירוע שנסגר במלואו לא נשאר תקוע בתצוגת 'היום'")
    finally:
        teardown()


# ── 4–5. Follow-up היום / מחר ────────────────────────────────────────────

def test_followup_due_today_appears_today() -> None:
    """(4) Follow-up שהגיע מועדו (כולל עבר) חוזר לתור תחת 'היום'."""
    api, teardown = bootstrap()
    try:
        from tests.call_center_helpers import shift_callback

        admin = standalone_admin(api)
        guest = api.add_guest("ביקש לחזור", "0509400005", party_size=1)
        configure_track(api)
        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=admin,
                        json={"outcome": "callback",
                              "callback_at": (datetime.utcnow() + timedelta(hours=2)).isoformat() + "Z"})
        shift_callback(guest["id"], minutes_from_now=-1)  # "הגיע" — כבר עבר

        items = _queue(api, admin, scope="today", event_id=api.event_id)["items"]
        assert [g["full_name"] for g in items] == ["ביקש לחזור"]
        assert items[0]["is_followup"] is True
        print("✓ Follow-up שהגיע מועדו מופיע תחת 'היום'")
    finally:
        teardown()


def test_followup_due_tomorrow_is_hidden_from_today() -> None:
    """(5) Follow-up שנקבע למחר לא מופיע היום."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        guest = api.add_guest("יחזרו אליו מחר", "0509400006", party_size=1)
        configure_track(api)
        tomorrow = datetime.utcnow() + timedelta(days=1, hours=1)
        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=admin,
                        json={"outcome": "callback", "callback_at": tomorrow.isoformat() + "Z"})

        items = _queue(api, admin, scope="today", event_id=api.event_id)["items"]
        assert items == [], f"Follow-up של מחר לא אמור להופיע היום: {items}"
        print("✓ Follow-up שנקבע למחר לא מופיע ב'היום'")
    finally:
        teardown()


def test_followup_due_tomorrow_appears_in_tomorrow_scope() -> None:
    """אותו Follow-up (בטווח 24 השעות הקרובות) — כן מופיע תחת 'מחר'.

    "טווח מחר" נבדק כאן דרך אותה שיטת ההרצה-הכפולה (ראו מבוא הקובץ): 20
    שעות מעכשיו הוא עתיד ביחס ל-"עכשיו" (לכן לא ב-"היום"), אך כבר בעבר
    ביחס ל-"עכשיו פלוס יממה" (לכן כן ב-"מחר").
    """
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        guest = api.add_guest("יחזרו אליו מחר", "0509400007", party_size=1)
        configure_track(api)
        soon = datetime.utcnow() + timedelta(hours=20)
        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=admin,
                        json={"outcome": "callback", "callback_at": soon.isoformat() + "Z"})

        items = _queue(api, admin, scope="tomorrow", event_id=api.event_id)["items"]
        assert [g["full_name"] for g in items] == ["יחזרו אליו מחר"]
        assert items[0]["is_followup"] is True
        print("✓ Follow-up של מחר מופיע תחת 'מחר'")
    finally:
        teardown()


# ── 6–7. שיחות שטופלו / אירוע ריק ────────────────────────────────────────

def test_call_handled_today_does_not_stay_in_active_queue() -> None:
    """(6) 'לא ענה'/'תפוס' שתועדו כרגע לא נשארים בתור הפעיל של היום."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        guest = api.add_guest("לא ענה עכשיו", "0509400008", party_size=1)
        configure_track(api)

        r = api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                            headers=admin, json={"outcome": "no_answer"})
        assert r.status_code == 200, r.text

        items = _queue(api, admin, scope="today", event_id=api.event_id)["items"]
        assert items == [], "שיחה שתועדה כרגע לא אמורה להישאר בתור"
        print("✓ שיחה שטופלה היום לא נשארת בתור הפעיל")
    finally:
        teardown()


def test_event_with_no_calls_today_is_absent_from_overview() -> None:
    """(7) אירוע בלי אף שיחה בטווח הנבחר לא מופיע בכלל (לא עם 0)."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        guest = api.add_guest("היחיד", "0509400009", party_size=1)
        configure_track(api)
        api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                        headers=admin, json={"outcome": "declined"})

        overview = _overview(api, admin, "today")
        ids = [e["event_id"] for e in overview["events"]]
        assert api.event_id not in ids
        print("✓ אירוע בלי שיחות בטווח לא מופיע (לא כשורה עם 0)")
    finally:
        teardown()


# ── 8. חלוקה ומיון לפי אירועים ───────────────────────────────────────────

def test_events_sorted_by_call_count_first() -> None:
    """(8) מיון ראשי: האירוע עם יותר שיחות ממתינות מופיע קודם."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        admin = standalone_admin(api_a)
        # שני האירועים באותם פרמטרים בדיוק (סבב פעיל ודאי) — רק כמות
        # המוזמנים הממתינים שונה, כדי לבודד את המיון הראשי.
        api_a.add_guest("A1", "0509400010", party_size=1)
        api_a.add_guest("A2", "0509400011", party_size=1)
        configure_track(api_a, days_to_event=8, commit_days=3, started_days_ago=12)
        api_b.add_guest("B1", "0509400012", party_size=1)
        configure_track(api_b, days_to_event=8, commit_days=3, started_days_ago=12)

        overview = _overview(api_a, admin, "today")
        ids_in_order = [e["event_id"] for e in overview["events"]
                        if e["event_id"] in (api_a.event_id, api_b.event_id)]
        assert ids_in_order == [api_a.event_id, api_b.event_id], (
            "האירוע עם יותר שיחות (A, 2) אמור להופיע לפני זה עם פחות (B, 1)"
        )
        print("✓ האירוע עם יותר שיחות ממתינות מופיע ראשון")
    finally:
        teardown_a()
        teardown_b()


def test_events_tie_break_by_nearest_event_date() -> None:
    """(8) בשוויון מספר שיחות — האירוע הקרוב יותר בתאריך מופיע קודם."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        admin = standalone_admin(api_a)
        # אותה כמות שיחות ממתינות (1) בשני האירועים — רק המרחק שונה.
        api_a.add_guest("A1", "0509400013", party_size=1)
        configure_track(api_a, days_to_event=8, commit_days=3, started_days_ago=12)
        api_b.add_guest("B1", "0509400014", party_size=1)
        configure_track(api_b, days_to_event=10, commit_days=3, started_days_ago=12)

        overview = _overview(api_a, admin, "today")
        ids_in_order = [e["event_id"] for e in overview["events"]
                        if e["event_id"] in (api_a.event_id, api_b.event_id)]
        assert ids_in_order == [api_a.event_id, api_b.event_id], (
            "בשוויון שיחות, האירוע הקרוב יותר (A, בעוד 8 ימים) אמור להופיע ראשון"
        )
        print("✓ בשוויון מספר שיחות — האירוע הקרוב יותר מופיע ראשון")
    finally:
        teardown_a()
        teardown_b()


def test_within_event_followups_come_first_then_alphabetical() -> None:
    """(8 המשך) בתוך אירוע: Follow-up קודם, ואז שאר האורחים לפי א-ב."""
    api, teardown = bootstrap()
    try:
        from tests.call_center_helpers import shift_callback

        admin = standalone_admin(api)
        api.add_guest("תמר", "0509400013", party_size=1)
        api.add_guest("אבי", "0509400014", party_size=1)
        followup = api.add_guest("זה חוזר", "0509400015", party_size=1)
        configure_track(api)
        api.client.post(f"/admin/call-center/guests/{followup['id']}/outcome",
                        headers=admin,
                        json={"outcome": "callback",
                              "callback_at": (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"})
        shift_callback(followup["id"], minutes_from_now=-1)

        items = _queue(api, admin, scope="today", event_id=api.event_id)["items"]
        names = [g["full_name"] for g in items]
        assert names == ["זה חוזר", "אבי", "תמר"], names
        print("✓ בתוך אירוע: Follow-up קודם, אחר כך א-ב")
    finally:
        teardown()


# ── 9. חיפוש בתוך הטווח הנבחר ─────────────────────────────────────────────

def test_search_is_scoped_to_the_selected_range() -> None:
    """(9) חיפוש לפי שם/טלפון פועל בתוך הטווח שנבחר בלבד."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        api.add_guest("רוני שני", "0509400016", party_size=1)
        started = _days_ago_for_first_round_on(date.today())
        configure_track(api, days_to_event=DAYS_TO_EVENT, commit_days=COMMIT_DAYS,
                        started_days_ago=started)

        today_hit = _queue(api, admin, scope="today", q="רוני")["items"]
        assert [g["full_name"] for g in today_hit] == ["רוני שני"]

        # אותו חיפוש בטווח "מחר" — האירוע לא רלוונטי שם, אין תוצאה.
        tomorrow_hit = _queue(api, admin, scope="tomorrow", q="רוני")["items"]
        assert tomorrow_hit == []
        print("✓ החיפוש פועל בתוך הטווח הנבחר בלבד")
    finally:
        teardown()


# ── טלפן / אדמין / בידוד ─────────────────────────────────────────────────

def test_phone_agent_scoping_still_works_with_today_filter() -> None:
    """(10)(11)(12) טלפן עם הקצאה רואה רק את שלו, גם עם סינון 'היום';
    אדמין ממשיך לראות הכול; אין דליפה בין אירועים."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        from tests.call_center_helpers import assign_events

        admin = standalone_admin(api_a)
        api_a.add_guest("של A", "0509400017", party_size=1)
        api_b.add_guest("של B", "0509400018", party_size=1)
        configure_track(api_a)
        configure_track(api_b)

        agent_id, agent = phone_agent(api_a)
        assign_events(agent_id, [api_a.event_id])

        agent_ids = [e["event_id"] for e in _overview(api_a, agent, "today")["events"]]
        assert agent_ids == [api_a.event_id], agent_ids

        agent_items = _queue(api_a, agent, scope="today")["items"]
        assert all(g["event_id"] == api_a.event_id for g in agent_items)
        assert not any(g["full_name"] == "של B" for g in agent_items), "דליפה מאירוע B"

        admin_ids = {e["event_id"] for e in _overview(api_a, admin, "today")["events"]}
        assert {api_a.event_id, api_b.event_id} <= admin_ids
        print("✓ טלפן מוגבל להקצאה שלו, אדמין רואה הכול, בלי דליפה — גם עם scope=today")
    finally:
        teardown_a()
        teardown_b()


def test_unassigned_phone_agent_gets_shared_queue_scoped_to_today() -> None:
    """טלפן בלי הקצאות מקבל את התור המשותף, מסונן ל'היום' כמו כל תפקיד."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        api_a.add_guest("אורח A", "0509400019", party_size=1)
        api_b.add_guest("אורח B", "0509400020", party_size=1)
        configure_track(api_a)
        configure_track(api_b)
        _, agent = phone_agent(api_a)

        ids = {e["event_id"] for e in _overview(api_a, agent, "today")["events"]}
        assert {api_a.event_id, api_b.event_id} <= ids
        print("✓ טלפן בלי הקצאות מקבל תור משותף, מסונן ל'היום'")
    finally:
        teardown_a()
        teardown_b()


# ── Workflow משותף ────────────────────────────────────────────────────────

def test_today_scope_round_date_matches_owner_timeline() -> None:
    """מסך אישורי ההגעה של הבעלים ומסך 'היום' של Call Center מציגים בדיוק
    את אותו תאריך סבב — גם אחרי הוספת הטווחים."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        api.add_guest("אורח", "0509400021", party_size=1)
        configure_track(api)

        timeline = api.client.get("/automation/timeline", headers=api.headers).json()
        owner_call_dates = [
            day["date"] for day in timeline["days"] for action in day["actions"]
            if action["type"] == "call_round"
        ]

        overview = _overview(api, admin, "today")
        row = next(e for e in overview["events"] if e["event_id"] == api.event_id)
        assert row["round_date"] in owner_call_dates
        print("✓ תאריך הסבב זהה בין 'היום' של Call Center למסך אישורי ההגעה")
    finally:
        teardown()


def test_invalid_scope_is_rejected() -> None:
    """טווח לא מוכר נדחה — לא נופל בשקט לברירת מחדל."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        r = api.client.get("/admin/call-center", headers=admin, params={"scope": "yesterday"})
        assert r.status_code == 400, r.status_code
        print("✓ טווח לא מוכר נדחה עם 400")
    finally:
        teardown()
