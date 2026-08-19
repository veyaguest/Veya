""""שיחות להיום" — טווחי תצוגה (היום / מחר / בהמשך / לא טופל) במסך ה-Call Center.

עיקרון מנחה: **אין כאן מנוע תאריכים חדש.** כל טווח מחושב ע"י הרצה חוזרת של
``call_center.build_queues`` הקיים עם ``now`` וירטואלי אחר (בדיוק אותו פרמטר
שהפונקציה כבר תומכת בו — ראו ``app/rsvp_timeline.py::due_call_round``),
והפרש-קבוצות/פיצול בין ההרצות (ראו ``call_center.build_queues_for_scope``).
לא נוצר סבב/תאריך/סטטוס חדש; ה-Workflow הקיים נשאר יחיד ולא נגוע.

"אירוע שהסתיים" נגזר מ-``Event.event_date`` הקיים בלבד (``event_date <
היום``) — אין שדה/דגל "סגור" נפרד. אירוע כזה יוצא לגמרי מכל הטווחים, כולל
"לא טופל", גם אם נשארו לו שיחות שלא בוצעו מעולם (ראו ``event_has_ended``).

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
    assign_events,
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


def _days_to_event_pair_with_backlog(
    *, commit_days=COMMIT_DAYS, started_days_ago=12, search_from=5, search_to=25,
) -> tuple[int, int]:
    """מוצא שני ערכי ``days_to_event`` ששניהם מניבים סבב 1 שכבר עבר (backlog),
    כדי לבדוק מיון-לפי-קרבה בין שני אירועים ב"לא טופל" גם ביום שבו הריצה
    היחידה עם started_days_ago גדול לא מספיקה (ראו ``configure_track``: מעבר
    לנקודה מסוימת ``days_to_event`` גדול "מציף" את הסבב לעתיד, בלי קשר
    ל-started_days_ago). מריץ את המנוע האמיתי בזיכרון, לא נוסחה עצמאית.
    """
    from app import models, rsvp_timeline

    today = date.today()
    hits: list[int] = []
    for dte in range(search_from, search_to):
        probe = models.Event(
            event_date=(today + timedelta(days=dte)).isoformat(),
            event_time="19:00",
            venue_commit_days_before=commit_days,
            rsvp_track_active=True,
            rsvp_track_started_at=datetime.utcnow() - timedelta(days=started_days_ago),
        )
        rounds = rsvp_timeline.call_rounds(probe)
        if rounds and rounds[0].date < today:
            hits.append(dte)
        if len(hits) >= 2:
            return hits[0], hits[1]
    raise AssertionError("לא נמצאו שני תרחישי backlog מתאימים למיון")


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
    """(8) מיון ראשי: האירוע עם יותר שיחות ממתינות מופיע קודם.

    המיון (``_event_sort_key``) חל באופן זהה על כל הטווחים — נבדק כאן דרך
    "לא טופל" (``started_days_ago=12`` מפורש = סבב שנפתח לפני היום), כדי
    לבודד את בדיקת המיון עצמה מהשאלה "איזה טווח זה בדיוק".
    """
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        admin = standalone_admin(api_a)
        # שני האירועים באותם פרמטרים בדיוק (סבב פעיל ודאי, שנפתח לפני היום —
        # מחושב דינמית) — רק כמות המוזמנים הממתינים שונה, כדי לבודד את המיון
        # הראשי מהתאריך המדויק.
        dte, _ = _days_to_event_pair_with_backlog(commit_days=3, started_days_ago=12)
        api_a.add_guest("A1", "0509400010", party_size=1)
        api_a.add_guest("A2", "0509400011", party_size=1)
        configure_track(api_a, days_to_event=dte, commit_days=3, started_days_ago=12)
        api_b.add_guest("B1", "0509400012", party_size=1)
        configure_track(api_b, days_to_event=dte, commit_days=3, started_days_ago=12)

        overview = _overview(api_a, admin, "not_handled")
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
    """(8) בשוויון מספר שיחות — האירוע הקרוב יותר בתאריך מופיע קודם.

    נבדק דרך "לא טופל" מאותה סיבה כמו בבדיקה הקודמת.
    """
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        admin = standalone_admin(api_a)
        # אותה כמות שיחות ממתינות (1) בשני האירועים — רק המרחק שונה. שני
        # ה-days_to_event (מחושבים דינמית) מניבים שניהם סבב שכבר עבר
        # (backlog) — אחרת הם היו נופלים לטווחים שונים (היום/לא טופל)
        # ולא רק במיקום שונה בתוך אותו טווח.
        closer, farther = _days_to_event_pair_with_backlog(commit_days=3, started_days_ago=12)
        api_a.add_guest("A1", "0509400013", party_size=1)
        configure_track(api_a, days_to_event=closer, commit_days=3, started_days_ago=12)
        api_b.add_guest("B1", "0509400014", party_size=1)
        configure_track(api_b, days_to_event=farther, commit_days=3, started_days_ago=12)

        overview = _overview(api_a, admin, "not_handled")
        ids_in_order = [e["event_id"] for e in overview["events"]
                        if e["event_id"] in (api_a.event_id, api_b.event_id)]
        assert ids_in_order == [api_a.event_id, api_b.event_id], (
            f"בשוויון שיחות, האירוע הקרוב יותר (A, בעוד {closer} ימים) אמור להופיע ראשון"
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
    """(9) חיפוש לפי שם/טלפון פועל בתוך הטווח שנבחר בלבד.

    מסונן ל-``event_id`` של הבדיקה עצמה: ``admin`` הוא אדמין-על שרואה את כל
    המערכת, וה-DB בסביבת הריצה הזו משותף בין כל קובצי הבדיקה (ולפעמים אף עם
    ה-DB האמיתי — ראו הערה בדוח המסירה). בדיקת שוויון-רשימה גלובלית בלי
    סינון אירוע היא שברירה במשותף כזה; סינון לפי event_id הוא הדרך הנכונה
    לבודד את מה שהבדיקה הזו באמת בודקת (החיפוש בתוך טווח), לא כמה עוד
    "רוני"-ים יש במערכת.
    """
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        api.add_guest("רוני שני", "0509400016", party_size=1)
        started = _days_ago_for_first_round_on(date.today())
        configure_track(api, days_to_event=DAYS_TO_EVENT, commit_days=COMMIT_DAYS,
                        started_days_ago=started)

        today_hit = _queue(api, admin, scope="today", q="רוני", event_id=api.event_id)["items"]
        assert [g["full_name"] for g in today_hit] == ["רוני שני"]

        # אותו חיפוש בטווח "מחר" — האירוע לא רלוונטי שם, אין תוצאה.
        tomorrow_hit = _queue(api, admin, scope="tomorrow", q="רוני", event_id=api.event_id)["items"]
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


# ── סטטוס האירוע: אירוע שהסתיים / "לא טופל" ──────────────────────────────
# "הסתיים" = event_date כבר עבר. אין דגל/סטטוס נפרד — ראו call_center.py::
# event_has_ended. סגירה כזו קורית מעצמה כשהתאריך חולף, ואינה נוגעת ב-RSVP
# או ב-CallLog בשום צורה.

def _set_event_date(event_id: int, iso: str) -> None:
    """מזיז את תאריך האירוע — מדמה "האירוע כבר קרה" בלי שום דגל/מנגנון חדש."""
    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        db.get(models.Event, event_id).event_date = iso
        db.commit()
    finally:
        db.close()


def test_ended_event_disappears_from_every_scope_even_unhandled() -> None:
    """אירוע שהסתיים ויש לו שיחה ישנה שלא טופלה — לא מופיע בשום תור,
    לא ב'לא טופל' ולא בשום טווח אחר, למרות שהשיחה מעולם לא בוצעה."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        api.add_guest("לא נענה מעולם", "0509400022", party_size=1)
        # סבב פעיל שכבר עבר (backlog) — לפני שהאירוע "מסתיים".
        configure_track(api, days_to_event=8, commit_days=3, started_days_ago=12)
        assert _queue(api, admin, scope="not_handled", event_id=api.event_id)["items"], (
            "הבדיקה מצפה שהשיחה תופיע ב'לא טופל' לפני שהאירוע מסתיים"
        )

        # "סיום" האירוע: תאריך שכבר עבר — בלי שום פעולה נוספת.
        _set_event_date(api.event_id, (date.today() - timedelta(days=1)).isoformat())

        for scope in ("today", "tomorrow", "later", "not_handled"):
            ids = [e["event_id"] for e in _overview(api, admin, scope)["events"]]
            assert api.event_id not in ids, f"אירוע שהסתיים מופיע עדיין תחת scope={scope}"
        print("✓ אירוע שהסתיים נעלם מכל הטווחים, כולל 'לא טופל'")
    finally:
        teardown()


def test_active_event_with_old_unhandled_call_appears_in_not_handled_only() -> None:
    """אירוע פעיל + שיחה ישנה שלא טופלה → מופיעה ב'לא טופל' בלבד, לא ב'היום'."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        api.add_guest("ממתין הרבה זמן", "0509400023", party_size=1)
        configure_track(api, days_to_event=8, commit_days=3, started_days_ago=12)

        not_handled = _queue(api, admin, scope="not_handled", event_id=api.event_id)["items"]
        assert [g["full_name"] for g in not_handled] == ["ממתין הרבה זמן"]

        today_items = _queue(api, admin, scope="today", event_id=api.event_id)["items"]
        assert today_items == [], "שיחה ישנה שלא טופלה לא אמורה להופיע ב'היום'"
        print("✓ אירוע פעיל עם שיחה ישנה — מופיע רק ב'לא טופל'")
    finally:
        teardown()


def test_not_handled_hidden_for_events_without_backlog() -> None:
    """אירוע פעיל עם שיחה של היום (לא backlog) — לא מופיע ב'לא טופל'."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        api.add_guest("ישראל כהן", "0509400024", party_size=1)
        configure_track(api)  # ברירת המחדל: סבב שנפתח בדיוק היום

        not_handled_ids = [e["event_id"] for e in _overview(api, admin, "not_handled")["events"]]
        assert api.event_id not in not_handled_ids
        print("✓ אירוע בלי backlog לא מופיע ב'לא טופל'")
    finally:
        teardown()


def test_active_event_future_followup_appears_only_at_its_own_time() -> None:
    """(4) Follow-up עתידי באירוע פעיל — לא 'לא טופל', גם אם הסבב עצמו הוא
    backlog; חוזר לתור רק במועד ה-Follow-up (כאן: 'מחר', לא 'היום' ולא
    'לא טופל')."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        guest = api.add_guest("יחזרו אליו מחר", "0509400025", party_size=1)
        # הסבב עצמו כבר backlog (started_days_ago=12) — כדי לוודא שה-Follow-up
        # העתידי לא "נדבק" ל'לא טופל' בגלל זה.
        configure_track(api, days_to_event=8, commit_days=3, started_days_ago=12)
        soon = datetime.utcnow() + timedelta(hours=20)  # עוד לא עבר יממה — "מחר"
        r = api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                            headers=admin,
                            json={"outcome": "callback", "callback_at": soon.isoformat() + "Z"})
        assert r.status_code == 200, r.text

        assert _queue(api, admin, scope="not_handled", event_id=api.event_id)["items"] == [], (
            "Follow-up עתידי לא אמור להופיע ב'לא טופל'"
        )
        assert _queue(api, admin, scope="today", event_id=api.event_id)["items"] == []
        tomorrow_items = _queue(api, admin, scope="tomorrow", event_id=api.event_id)["items"]
        assert [g["full_name"] for g in tomorrow_items] == ["יחזרו אליו מחר"]
        print("✓ Follow-up עתידי לא נחשב 'לא טופל' — חוזר רק במועד שלו")
    finally:
        teardown()


def test_closing_event_preserves_rsvp_and_call_history() -> None:
    """(5) 'סגירת' אירוע (הזזת תאריך לעבר) לא נוגעת ב-RSVP ולא מוחקת
    היסטוריית CallLog — היא רק מוציאה אותו מתור השיחות."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        guest = api.add_guest("ישראל כהן", "0509400026", party_size=3)
        configure_track(api, days_to_event=8, commit_days=3, started_days_ago=12)
        r = api.client.post(f"/admin/call-center/guests/{guest['id']}/outcome",
                            headers=admin, json={"outcome": "confirmed", "count": 2})
        assert r.status_code == 200, r.text
        before_logs = call_logs_of(api, guest["id"])
        assert len(before_logs) == 1

        _set_event_date(api.event_id, (date.today() - timedelta(days=1)).isoformat())

        after = guest_of(api, guest["id"])
        assert (after.rsvp_status, after.confirmed_count) == ("confirmed", 2), (
            "סגירת אירוע לא אמורה לשנות RSVP"
        )
        after_logs = call_logs_of(api, guest["id"])
        assert len(after_logs) == 1 and after_logs[0].outcome == "confirmed", (
            "סגירת אירוע לא אמורה למחוק היסטוריית שיחות"
        )
        for scope in ("today", "not_handled"):
            ids = [e["event_id"] for e in _overview(api, admin, scope)["events"]]
            assert api.event_id not in ids
        print("✓ סגירת אירוע לא נוגעת ב-RSVP ולא מוחקת CallLog — רק מוציאה מהתור")
    finally:
        teardown()


def test_phone_agent_and_admin_get_the_same_event_status_filtering() -> None:
    """טלפן ואדמין מקבלים את אותו סינון לפי סטטוס האירוע: אירוע שהסתיים
    נעלם משניהם, ואירוע פעיל עם backlog מופיע לשניהם תחת 'לא טופל'."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        admin = standalone_admin(api_a)

        # אירוע A: פעיל, עם backlog — אמור להופיע לשניהם ב'לא טופל'.
        api_a.add_guest("פעיל עם עבר", "0509400027", party_size=1)
        configure_track(api_a, days_to_event=8, commit_days=3, started_days_ago=12)

        # אירוע B: הסתיים — לא אמור להופיע לאף אחד, גם עם backlog.
        api_b.add_guest("אירוע שנגמר", "0509400028", party_size=1)
        configure_track(api_b, days_to_event=8, commit_days=3, started_days_ago=12)
        _set_event_date(api_b.event_id, (date.today() - timedelta(days=3)).isoformat())

        agent_id, agent = phone_agent(api_a)
        assign_events(agent_id, [api_a.event_id, api_b.event_id])

        for headers, label in ((admin, "אדמין"), (agent, "טלפן")):
            not_handled_ids = [e["event_id"] for e in _overview(api_a, headers, "not_handled")["events"]]
            assert api_a.event_id in not_handled_ids, f"{label}: אירוע פעיל לא מופיע ב'לא טופל'"
            assert api_b.event_id not in not_handled_ids, f"{label}: אירוע שהסתיים לא הוסתר"
            for scope in ("today", "tomorrow", "later"):
                ids = [e["event_id"] for e in _overview(api_a, headers, scope)["events"]]
                assert api_b.event_id not in ids, f"{label}: אירוע שהסתיים דלף תחת scope={scope}"
        print("✓ טלפן ואדמין מקבלים בדיוק אותו סינון לפי סטטוס האירוע")
    finally:
        teardown_a()
        teardown_b()
