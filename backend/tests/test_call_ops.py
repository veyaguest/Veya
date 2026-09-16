"""מרכז שליטה בטלפנים — תרחישי הבדיקה של המייסד (1–8) + הרשאות ויומן.

הלוח הוא תמיד לוח הזמנים האמיתי (``rsvp_timeline``); הבדיקות רק מכוונות את
תאריך האירוע ויום הפעלת המסלול, בדיוק כמו ``call_center_helpers``.
"""
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402
from tests.call_center_helpers import configure_track, phone_agent  # noqa: E402


def setup_module(module) -> None:  # noqa: ARG001
    from app import call_ops

    call_ops.SYNC_TTL_SECONDS = 0


def _session():
    from app.database import SessionLocal

    return SessionLocal()


def _admin(role="super_admin"):
    from app import auth, models

    db = _session()
    try:
        u = models.User(
            email=f"ops-{uuid.uuid4().hex[:10]}@veya.test", password_hash=auth.hash_password("Test12345!"),
            display_name="אביב", is_admin=True, admin_role=role,
        )
        db.add(u)
        db.commit()
        return u.id, {"Authorization": f"Bearer {auth.create_access_token(u)}"}
    finally:
        db.close()


def _tasks(event_id, **where):
    from sqlalchemy import select

    from app import models

    db = _session()
    try:
        stmt = select(models.CallTask).where(models.CallTask.event_id == event_id)
        for k, v in where.items():
            stmt = stmt.where(getattr(models.CallTask, k) == v)
        return db.scalars(stmt.order_by(models.CallTask.id)).all()
    finally:
        db.close()


def _set_guest(guest_id, **fields):
    from app import models

    db = _session()
    try:
        g = db.get(models.Guest, guest_id)
        for k, v in fields.items():
            setattr(g, k, v)
        db.commit()
    finally:
        db.close()


def _sync(event_id=None, now=None):
    from app import call_ops

    db = _session()
    try:
        stats = call_ops.sync(db, now=now, event_ids={event_id} if event_id else None, force=True)
        db.commit()
        return stats
    finally:
        db.close()


def _rounds(event_id, now=None):
    from app import models, rsvp_timeline

    db = _session()
    try:
        return rsvp_timeline.call_rounds(db.get(models.Event, event_id), now)
    finally:
        db.close()


def _started_days_ago_for_round_on(target: date, days_to_event=8, commit_days=3) -> int:
    """started_days_ago שבו סבב כלשהו נופל בדיוק ב-target (לפי המנוע האמיתי)."""
    from app import models, rsvp_timeline

    for ago in range(0, 60):
        probe = models.Event(
            event_date=(date.today() + timedelta(days=days_to_event)).isoformat(), event_time="19:00",
            venue_commit_days_before=commit_days, rsvp_track_active=True,
            rsvp_track_started_at=datetime.utcnow() - timedelta(days=ago),
        )
        if any(p.date == target for p in rsvp_timeline.call_rounds(probe)):
            return ago
    raise AssertionError("לא נמצא לוח שבו יש סבב בתאריך המבוקש")


def _phone(i: int) -> str:
    return f"05{i:08d}"


# ── תרחיש 1: 300 מוזמנים, סבב היום — כולם מופיעים, פעם אחת ──────────────

def test_scenario_1_three_hundred_guests_all_listed_once() -> None:
    api, _ = bootstrap()
    from app import models

    db = _session()
    try:
        for i in range(300):
            db.add(models.Guest(event_id=api.event_id, full_name=f"אורח {i:03d}", phone=_phone(i + 1000)))
        db.commit()
    finally:
        db.close()
    configure_track(api)
    _, admin = _admin()

    first = _sync(api.event_id)
    again = _sync(api.event_id)
    assert first.created == 300
    assert again.created == 0, "sync שני יצר כפילויות"
    tasks = _tasks(api.event_id)
    assert len(tasks) == 300
    assert len({(t.guest_id, t.round_number) for t in tasks}) == 300

    seen = set()
    offset = 0
    while True:
        r = api.client.get(
            f"/admin/call-ops/tasks?group=pending&event_id={api.event_id}&limit=200&offset={offset}", headers=admin,
        )
        assert r.status_code == 200, r.text
        page = r.json()
        assert page["total"] == 300
        seen.update(row["guest_id"] for row in page["items"])
        offset += 200
        if offset >= page["total"]:
            break
    assert len(seen) == 300

    day = api.client.get("/admin/call-ops/day", headers=admin).json()
    mine = [x for x in day["rounds"] if x["event_id"] == api.event_id]
    assert mine and mine[0]["total"] == 300 and mine[0]["pending"] == 300 and not mine[0]["complete"]


# ── תרחיש 2: אישר לפני התור — לא מופיע; אישר אחרי — נסגר ─────────────────

def test_scenario_2_confirmed_guest_never_stays_in_queue() -> None:
    api, _ = bootstrap()
    early = api.add_guest("אישרה מוקדם", _phone(2001))
    late = api.add_guest("מאשר אחרי", _phone(2002))
    _set_guest(early["id"], rsvp_status="confirmed")
    configure_track(api)
    _, admin = _admin()

    _sync(api.event_id)
    assert [t.guest_id for t in _tasks(api.event_id)] == [late["id"]]

    _set_guest(late["id"], rsvp_status="declined")
    r = api.client.get(f"/admin/call-ops/tasks?group=pending&event_id={api.event_id}", headers=admin)
    assert r.json()["total"] == 0
    (task,) = _tasks(api.event_id)
    assert task.status == "closed_by_rsvp" and task.closed_reason == "rsvp_declined"


# ── תרחיש 3: לא ענה — מקבל את הפעולה הבאה לפי חוקי המעקב ─────────────────

def test_scenario_3_no_answer_moves_to_next_round() -> None:
    api, _ = bootstrap()
    g = api.add_guest("לא עונה", _phone(3001))
    configure_track(api)
    _, admin = _admin()
    _sync(api.event_id)

    r = api.client.post(
        f"/admin/call-center/guests/{g['id']}/outcome", headers=admin, json={"outcome": "no_answer"},
    )
    assert r.status_code == 200, r.text
    (t1,) = _tasks(api.event_id)
    assert t1.status == "done" and t1.last_outcome == "no_answer" and t1.attempts == 1

    rounds = _rounds(api.event_id)
    assert len(rounds) >= 2
    second = rounds[1]
    now_round2 = datetime.combine(second.date, datetime.min.time()) + timedelta(hours=9)
    _sync(api.event_id, now=now_round2)
    tasks = _tasks(api.event_id)
    expected = [(1, "done"), (2, "open")]
    # סבב שנופל למחרת מוכן מראש (כדי שאפשר יהיה להקצות אותו) — זה תקין.
    expected += [(p.round_number, "open") for p in rounds if p.date == second.date + timedelta(days=1)]
    assert [(t.round_number, t.status) for t in tasks] == expected
    assert tasks[1].planned_date == second.date.isoformat()


# ── תרחיש 4: טלפן לא פעיל — לא מקבל משימות ───────────────────────────────

def test_scenario_4_inactive_caller_gets_no_tasks() -> None:
    api, _ = bootstrap()
    api.add_guest("אורח א", _phone(4001))
    api.add_guest("אורח ב", _phone(4002))
    configure_track(api)
    _, admin = _admin()
    idle_id, _ = phone_agent(api, display_name="לא פעיל")
    busy_id, _ = phone_agent(api, display_name="פעיל")
    assert api.client.patch(
        f"/admin/call-ops/callers/{idle_id}", headers=admin, json={"availability": "inactive"},
    ).status_code == 200
    _sync(api.event_id)
    ids = [t.id for t in _tasks(api.event_id)]

    r = api.client.post("/admin/call-ops/tasks/assign", headers=admin, json={"task_ids": ids, "assignee_id": idle_id})
    assert r.status_code == 400

    preview = api.client.post(
        "/admin/call-ops/tasks/auto-assign/preview", headers=admin,
        json={"task_ids": ids, "caller_ids": [idle_id, busy_id]},
    ).json()
    assert {p["assignee_id"] for p in preview["proposals"]} == {busy_id}

    # חופשה בטווח שכולל היום — גם לא
    assert api.client.patch(
        f"/admin/call-ops/callers/{busy_id}", headers=admin,
        json={"availability": "vacation", "unavailable_from": date.today().isoformat(),
              "unavailable_until": (date.today() + timedelta(days=2)).isoformat()},
    ).status_code == 200
    r = api.client.post("/admin/call-ops/tasks/assign", headers=admin, json={"task_ids": ids, "assignee_id": busy_id})
    assert r.status_code == 400


# ── תרחיש 5: משימה מאתמול שלא טופלה — נמצאת דרך "אתמול" ודרך תאריך ───────

def test_scenario_5_yesterday_unhandled_is_findable() -> None:
    api, _ = bootstrap()
    g = api.add_guest("נשכח אתמול", _phone(5001))
    configure_track(api)
    _, admin = _admin()
    _sync(api.event_id)
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    from app import models

    db = _session()
    try:
        (task,) = db.query(models.CallTask).filter(models.CallTask.event_id == api.event_id).all()
        task.planned_date = task.due_date = yesterday
        db.commit()
    finally:
        db.close()

    r = api.client.get(f"/admin/call-ops/tasks?date={yesterday}&group=not_handled&event_id={api.event_id}", headers=admin)
    assert [row["guest_id"] for row in r.json()["items"]] == [g["id"]]
    r = api.client.get(f"/admin/call-ops/tasks?group=overdue&event_id={api.event_id}", headers=admin)
    assert [row["status_label"] for row in r.json()["items"]] == ["באיחור"]
    day = api.client.get(f"/admin/call-ops/day?date={yesterday}", headers=admin).json()
    assert day["relation"] == "past" and day["counts"]["not_handled"] >= 1


# ── תרחיש 6: מחר — לפי לוח הזמנים האמיתי ─────────────────────────────────

def test_scenario_6_tomorrow_follows_real_schedule() -> None:
    api, _ = bootstrap()
    tomorrow = date.today() + timedelta(days=1)
    ago = _started_days_ago_for_round_on(tomorrow)
    configure_track(api, started_days_ago=ago)
    for i in range(5):
        api.add_guest(f"מחר {i}", _phone(6000 + i))
    _, admin = _admin()
    rounds = _rounds(api.event_id)
    tomorrow_round = next(p for p in rounds if p.date == tomorrow)

    r = api.client.get(f"/admin/call-ops/tasks?date={tomorrow.isoformat()}&event_id={api.event_id}", headers=admin)
    body = r.json()
    assert body["mode"] == "tasks" and body["total"] == 5
    assert {row["round_number"] for row in body["items"]} == {tomorrow_round.round_number}

    later = next((p for p in rounds if p.date > tomorrow), None)
    if later is not None:
        r = api.client.get(f"/admin/call-ops/tasks?date={later.date.isoformat()}&event_id={api.event_id}", headers=admin)
        assert r.json()["mode"] == "preview" and r.json()["total"] == 5


# ── תרחיש 7+8: שינוי מועד סגירת הרשימה — סבבים עתידיים מחושבים מחדש ───────

def test_scenario_7_8_schedule_change_recomputes_future_rounds() -> None:
    api, _ = bootstrap()
    tomorrow = date.today() + timedelta(days=1)
    ago = _started_days_ago_for_round_on(tomorrow)
    configure_track(api, started_days_ago=ago)
    api.add_guest("עתידי", _phone(7001))
    _, admin = _admin()
    _sync(api.event_id)
    before = {t.round_number: t for t in _tasks(api.event_id)}

    from app import models

    db = _session()
    try:
        ev = db.get(models.Event, api.event_id)
        ev.venue_commit_days_before = 1
        db.commit()
    finally:
        db.close()
    new_rounds = _rounds(api.event_id)
    _sync(api.event_id)
    after = _tasks(api.event_id)

    new_tomorrow = {p.round_number for p in new_rounds if p.date == tomorrow}
    for t in after:
        if t.planned_date > date.today().isoformat() and t.status == "open":
            plan = next(p for p in new_rounds if p.round_number == t.round_number)
            assert t.planned_date == plan.date.isoformat(), "משימה עתידית לא עודכנה ללוח החדש"
        if t.round_number in before and t.round_number not in new_tomorrow and before[t.round_number].planned_date == tomorrow.isoformat():
            assert t.status in ("cancelled", "open")

    timeline = api.client.get(f"/admin/call-ops/timeline?start={date.today().isoformat()}&days=14", headers=admin).json()
    by_date = {d["date"]: d for d in timeline}
    for p in new_rounds:
        if p.date > tomorrow:
            assert by_date[p.date.isoformat()]["planned"] >= 1


# ── הרשאות, יומן, טלפן ────────────────────────────────────────────────────

def test_reassign_is_audited_and_caller_sees_only_own_tasks() -> None:
    api, _ = bootstrap()
    a = api.add_guest("לדני", _phone(8001))
    b = api.add_guest("ליוסי", _phone(8002))
    configure_track(api)
    _, admin = _admin()
    danny_id, danny = phone_agent(api, display_name="דני")
    yossi_id, _ = phone_agent(api, display_name="יוסי")
    _sync(api.event_id)
    tasks = {t.guest_id: t for t in _tasks(api.event_id)}
    api.client.post("/admin/call-ops/tasks/assign", headers=admin,
                    json={"task_ids": [tasks[a["id"]].id], "assignee_id": danny_id})
    r = api.client.post("/admin/call-ops/tasks/assign", headers=admin,
                        json={"task_ids": [tasks[b["id"]].id], "assignee_id": yossi_id})
    assert r.status_code == 200

    from sqlalchemy import select

    from app import models

    db = _session()
    try:
        logs = db.scalars(select(models.AdminAuditLog).where(
            models.AdminAuditLog.action == "call_task.assign",
            models.AdminAuditLog.target_id == str(tasks[b["id"]].id),
        )).all()
    finally:
        db.close()
    assert logs and "ליוסי" in logs[-1].summary and logs[-1].changes[0]["after"] == "יוסי"

    mine = api.client.get("/admin/call-ops/my/tasks?q=לדני", headers=danny).json()
    others = api.client.get("/admin/call-ops/my/tasks?q=ליוסי", headers=danny).json()
    assert others["total"] == 0, "טלפן רואה משימה שהוקצתה לטלפן אחר"
    mine_ids = [row["guest_id"] for row in mine["items"]]
    assert a["id"] in mine_ids and b["id"] not in mine_ids, "טלפן רואה משימה שהוקצתה לטלפן אחר"
    assert api.client.get(f"/admin/call-ops/my/guests/{b['id']}", headers=danny).status_code in (200, 404)
    for path in ("/admin/call-ops/day", "/admin/call-ops/tasks", "/admin/call-ops/callers"):
        assert api.client.get(path, headers=danny).status_code in (401, 403), path


def test_support_cannot_stop_rounds_or_manage_callers() -> None:
    api, _ = bootstrap()
    api.add_guest("סבב", _phone(9001))
    configure_track(api)
    _, support = _admin("support")
    caller_id, _ = phone_agent(api)
    assert api.client.post(
        f"/admin/call-ops/rounds/{api.event_id}/1/stop", headers=support, json={"reason": "בדיקה"},
    ).status_code == 403
    assert api.client.patch(
        f"/admin/call-ops/callers/{caller_id}", headers=support, json={"availability": "inactive"},
    ).status_code == 403
    assert api.client.get("/admin/call-ops/day", headers=support).status_code == 200


def test_stop_and_resume_round() -> None:
    api, _ = bootstrap()
    api.add_guest("עצירה", _phone(9101))
    configure_track(api)
    _, admin = _admin()
    _sync(api.event_id)
    rnd = _tasks(api.event_id)[0].round_number
    assert api.client.post(f"/admin/call-ops/rounds/{api.event_id}/{rnd}/stop", headers=admin, json={}).status_code == 400
    r = api.client.post(f"/admin/call-ops/rounds/{api.event_id}/{rnd}/stop", headers=admin, json={"reason": "בקשת הזוג"})
    assert r.status_code == 200, r.text
    assert _tasks(api.event_id)[0].status == "cancelled"
    r = api.client.post(f"/admin/call-ops/rounds/{api.event_id}/{rnd}/resume", headers=admin, json={})
    assert r.status_code == 200
    assert _tasks(api.event_id)[0].status == "open"


def test_deleting_guest_and_event_removes_tasks() -> None:
    api, _ = bootstrap()
    g = api.add_guest("למחיקה", _phone(9201))
    configure_track(api)
    _sync(api.event_id)
    assert _tasks(api.event_id)
    r = api.client.delete(f"/guests/{g['id']}", headers=api.headers)
    assert r.status_code == 204, r.text
    assert not _tasks(api.event_id)


def test_existing_call_history_is_respected_when_task_is_created() -> None:
    """שיחות שתועדו לפני שהמשימה נוצרה (callback / לא ענה) לא נמחקות מהתמונה."""
    api, _ = bootstrap()
    cb = api.add_guest("ביקש לחזור", _phone(9301))
    na = api.add_guest("לא ענה קודם", _phone(9302))
    configure_track(api)
    _, admin = _admin()
    later = (datetime.utcnow() + timedelta(days=2)).replace(microsecond=0).isoformat() + "Z"
    assert api.client.post(f"/admin/call-center/guests/{cb['id']}/outcome", headers=admin,
                           json={"outcome": "callback", "callback_at": later}).status_code == 200
    assert api.client.post(f"/admin/call-center/guests/{na['id']}/outcome", headers=admin,
                           json={"outcome": "no_answer"}).status_code == 200
    from app import models

    db = _session()
    try:  # מדמה מצב "לפני הפנקס": יש יומן שיחות, אין משימות
        db.query(models.CallTask).filter(models.CallTask.event_id == api.event_id).delete()
        db.commit()
    finally:
        db.close()
    _sync(api.event_id)
    tasks = {t.guest_id: t for t in _tasks(api.event_id)}
    assert tasks[cb["id"]].status == "open" and tasks[cb["id"]].reason == "callback"
    assert tasks[cb["id"]].due_date > date.today().isoformat()
    assert tasks[na["id"]].status == "done" and tasks[na["id"]].attempts == 1


def teardown_module(module) -> None:  # noqa: ARG001
    shutdown()
