"""איחוד מרכז הטלפנים — ``call_tasks`` הוא מקור האמת היחיד לתור.

אירוע → לוח RSVP → אורח זכאי → סבב → משימה → טלפן משויך → שיחה → תוצאה.
הבדיקות כאן מכסות את שלבי A–I של התיקון שאחרי ה-Audit.
"""
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402
from tests.call_center_helpers import call_logs_of, configure_track, guest_of, phone_agent  # noqa: E402
from tests.test_call_ops import _admin, _phone, _session, _set_guest, _sync, _tasks  # noqa: E402


def setup_module(module) -> None:  # noqa: ARG001
    from app import call_ops

    call_ops.SYNC_TTL_SECONDS = 0


def teardown_module(module) -> None:  # noqa: ARG001
    from app import call_ops

    call_ops.SYNC_TTL_SECONDS = 45
    shutdown()


def _tag() -> str:
    return "".join("abcdefghijklmnop"[int(c, 16)] for c in uuid.uuid4().hex[:8])


def _assign(api, admin, task_id, agent_id):
    r = api.client.post("/admin/call-ops/tasks/assign", headers=admin,
                        json={"task_ids": [task_id], "assignee_id": agent_id})
    assert r.status_code == 200, r.text


def _one_task(api, guest_id, **where):
    rows = [t for t in _tasks(api.event_id, **where) if t.guest_id == guest_id]
    assert rows, f"אין משימה לאורח {guest_id}"
    return rows[-1]


def _setup(n=1):
    api, _ = bootstrap()
    tag = _tag()
    guests = [api.add_guest(f"אורח {tag} {i}", _phone(40000 + i + (hash(tag) % 50000))) for i in range(n)]
    configure_track(api)
    _, admin = _admin()
    agent_id, agent = phone_agent(api)
    _sync(api.event_id)
    for g in guests:
        _assign(api, admin, _one_task(api, g["id"]).id, agent_id)
    return api, admin, agent_id, agent, guests


# ── A: הטלפן רואה רק משימות שלו, מהפנקס ─────────────────────────────────

def test_caller_sees_only_assigned_tasks_with_full_detail() -> None:
    api, admin, agent_id, agent, (mine, other) = _setup(2)
    other_agent_id, other_agent = phone_agent(api, display_name="אחר")
    other_task = _one_task(api, other["id"])
    _assign(api, admin, other_task.id, other_agent_id)

    page = api.client.get("/admin/call-ops/my/tasks?group=work", headers=agent).json()
    ids = {row["guest_id"] for row in page["items"]}
    assert mine["id"] in ids and other["id"] not in ids

    my_task = _one_task(api, mine["id"])
    r = api.client.get(f"/admin/call-ops/my/tasks/{my_task.id}", headers=agent)
    assert r.status_code == 200, r.text
    row = r.json()["task"]
    for key in ("task_id", "guest_name", "event_label", "event_date", "phone", "round_number",
                "reason_label", "status_label", "attempts", "callback_at", "event_cycle"):
        assert key in row, key
    assert r.json()["card"]["next_action"]

    # משימה של טלפן אחר — לא קיימת מבחינתו (404, לא 403).
    assert api.client.get(f"/admin/call-ops/my/tasks/{other_task.id}", headers=agent).status_code == 404
    r = api.client.post(f"/admin/call-ops/my/tasks/{other_task.id}/outcome", headers=agent,
                        json={"outcome": "no_answer"})
    assert r.status_code == 404
    assert call_logs_of(api, other["id"]) == []


# ── B: תוצאות שיחה מעדכנות את המשימה; CallLog הוא היסטוריה ─────────────

def test_task_outcomes_update_the_task_and_history() -> None:
    api, admin, agent_id, agent, (maybe_g, answered_g, confirm_g) = _setup(3)

    def outcome(g, **body):
        t = _one_task(api, g["id"])
        r = api.client.post(f"/admin/call-ops/my/tasks/{t.id}/outcome", headers=agent, json=body)
        assert r.status_code == 200, r.text
        return t, r.json()

    t, res = outcome(maybe_g, outcome="maybe")
    assert res["rsvp_status"] == "maybe"
    assert _one_task(api, maybe_g["id"]).status == "done"

    t, res = outcome(answered_g, outcome="answered", note="ביקש שנשלח שוב קישור")
    assert guest_of(api, answered_g["id"]).rsvp_status == "pending"
    after = _one_task(api, answered_g["id"])
    assert after.status == "done" and after.last_outcome == "answered" and after.attempts == 1

    t, res = outcome(confirm_g, outcome="confirmed", count=2)
    assert guest_of(api, confirm_g["id"]).confirmed_count == 2
    (log,) = call_logs_of(api, confirm_g["id"])
    assert (log.task_id, log.round_number, log.event_cycle) == (t.id, t.round_number, t.event_cycle)
    assert log.created_by_id == agent_id


def test_note_is_logged_without_counting_an_attempt() -> None:
    api, admin, agent_id, agent, (g,) = _setup(1)
    t = _one_task(api, g["id"])
    r = api.client.post(f"/admin/call-ops/my/tasks/{t.id}/outcome", headers=agent, json={"outcome": "note"})
    assert r.status_code == 400, "הערה ריקה התקבלה"
    r = api.client.post(f"/admin/call-ops/my/tasks/{t.id}/outcome", headers=agent,
                        json={"outcome": "note", "note": "לחייג אחרי 18:00"})
    assert r.status_code == 200, r.text
    after = _one_task(api, g["id"])
    assert after.status == "open" and after.attempts == 0 and "18:00" in after.note
    assert [lg.outcome for lg in call_logs_of(api, g["id"])] == ["note"]


def test_admin_records_on_a_task_through_the_same_logic() -> None:
    api, admin, agent_id, agent, (g,) = _setup(1)
    t = _one_task(api, g["id"])
    r = api.client.post(f"/admin/call-ops/tasks/{t.id}/outcome", headers=admin, json={"outcome": "declined"})
    assert r.status_code == 200, r.text
    assert guest_of(api, g["id"]).rsvp_status == "declined"
    assert _one_task(api, g["id"]).status in ("done", "closed_by_rsvp")
    # הטלפן לא יכול להשתמש ב-endpoint של האדמין.
    assert api.client.post(f"/admin/call-ops/tasks/{t.id}/outcome", headers=agent,
                           json={"outcome": "no_answer"}).status_code in (401, 403)


# ── F: שיחה חוזרת — נשמרת, ומופיעה רק כשמגיע הזמן ────────────────────────

def test_callback_is_hidden_until_its_time_and_never_lost() -> None:
    api, admin, agent_id, agent, (g,) = _setup(1)
    t = _one_task(api, g["id"])
    r = api.client.post(f"/admin/call-ops/my/tasks/{t.id}/outcome", headers=agent, json={"outcome": "callback"})
    assert r.status_code == 400, "שיחה חוזרת בלי מועד התקבלה"

    later = (datetime.utcnow() + timedelta(hours=3)).replace(microsecond=0)
    r = api.client.post(f"/admin/call-ops/my/tasks/{t.id}/outcome", headers=agent,
                        json={"outcome": "callback", "callback_at": later.isoformat() + "Z"})
    assert r.status_code == 200, r.text
    after = _one_task(api, g["id"])
    assert after.status == "open" and after.callback_at == later and after.attempts == 1

    work = api.client.get("/admin/call-ops/my/tasks?group=work", headers=agent).json()
    assert g["id"] not in {row["guest_id"] for row in work["items"]}, "שיחה חוזרת הופיעה לפני הזמן"
    wait = api.client.get("/admin/call-ops/my/tasks?group=later", headers=agent).json()
    assert g["id"] in {row["guest_id"] for row in wait["items"]}, "שיחה חוזרת נעלמה"

    # sync חוזר לא מוחק ולא מקדים את השיחה החוזרת.
    _sync(api.event_id)
    assert _one_task(api, g["id"]).callback_at == later

    from app import models

    db = _session()
    try:
        db.get(models.CallTask, t.id).callback_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    work = api.client.get("/admin/call-ops/my/tasks?group=work", headers=agent).json()
    assert g["id"] in {row["guest_id"] for row in work["items"]}, "שיחה חוזרת לא חזרה כשהגיע זמנה"


# ── C+D: מחזור אירוע — שיחות ממחזור קודם לא נספרות אחרי דחייה ────────────

def test_postponement_opens_a_clean_cycle_and_keeps_history() -> None:
    api, admin, agent_id, agent, (g,) = _setup(1)
    t1 = _one_task(api, g["id"])
    later = (datetime.utcnow() + timedelta(days=1)).replace(microsecond=0)
    r = api.client.post(f"/admin/call-ops/my/tasks/{t1.id}/outcome", headers=agent,
                        json={"outcome": "callback", "callback_at": later.isoformat() + "Z"})
    assert r.status_code == 200, r.text

    from app import call_ops, models

    db = _session()
    try:  # אותה סגירה ש-postponement_service.complete מבצע
        event = db.get(models.Event, api.event_id)
        old = event.cycle_number or 1
        call_ops.close_cycle(db, event.id, old)
        db.add(models.EventCycle(event_id=event.id, cycle_number=old, closed_at=datetime.utcnow()))
        event.cycle_number = old + 1
        db.commit()
    finally:
        db.close()
    configure_track(api)
    _sync(api.event_id)

    old_task = next(t for t in _tasks(api.event_id) if t.id == t1.id)
    assert old_task.status == "skipped" and old_task.closed_reason == "cycle_closed"
    new = [t for t in _tasks(api.event_id) if t.guest_id == g["id"] and t.event_cycle == old + 1]
    assert new, "לא נוצרה משימה במחזור החדש"
    assert all(t.attempts == 0 and t.callback_at is None and t.reason != "callback" for t in new), \
        "שיחה חוזרת ממחזור קודם זלגה למחזור החדש"

    # ההיסטוריה נשמרת ומוצגת לאדמין, מסומנת כמחזור קודם.
    card = api.client.get(f"/admin/call-ops/guests/{g['id']}", headers=admin).json()
    assert any("מחזור" in (h["title"] + h["detail"]) for h in card["history"])
    assert [lg.event_cycle for lg in call_logs_of(api, g["id"])] == [old]

    # תיעוד על משימה ישנה — נדחה.
    r = api.client.post(f"/admin/call-ops/tasks/{t1.id}/outcome", headers=admin, json={"outcome": "no_answer"})
    assert r.status_code == 400


# ── E: שיחה ידנית נרשמת על הסבב שלה, לא לפי ניחוש מתאריך ─────────────────

def test_manual_followup_is_recorded_on_its_own_task() -> None:
    api, _ = bootstrap()
    g = api.add_guest(f"ידני {_tag()}", _phone(47001))
    configure_track(api, activate=False)  # אין עדיין סבב — שיחה לפני הסבב הראשון
    _, admin = _admin()
    r = api.client.post("/admin/call-ops/tasks/manual", headers=admin, json={"guest_id": g["id"]})
    assert r.status_code == 200, r.text
    task_id = r.json()["task_id"]
    r = api.client.post(f"/admin/call-ops/tasks/{task_id}/outcome", headers=admin, json={"outcome": "no_answer"})
    assert r.status_code == 200, r.text
    (log,) = call_logs_of(api, g["id"])
    assert log.task_id == task_id and log.round_number == 0


# ── G: טלפון לא תקין לא נכנס לתור; תיקון מחזיר אותו ──────────────────────

def test_invalid_phone_is_excluded_and_restored_when_fixed() -> None:
    api, _ = bootstrap()
    bad = api.add_guest(f"מספר שבור {_tag()}", _phone(47100))
    empty = api.add_guest(f"בלי מספר {_tag()}", _phone(47102))
    # מספרים שבורים מגיעים מייבוא/נתונים ישנים — ה-API עצמו לא מקבל אותם.
    _set_guest(bad["id"], phone="12")
    _set_guest(empty["id"], phone="")
    configure_track(api)
    _, admin = _admin()
    _sync(api.event_id)
    assert not [t for t in _tasks(api.event_id, status="open") if t.guest_id in (bad["id"], empty["id"])]
    assert api.client.post("/admin/call-ops/tasks/manual", headers=admin,
                           json={"guest_id": bad["id"]}).status_code == 400

    r = api.client.patch(f"/guests/{bad['id']}", headers=api.headers, json={"phone": _phone(47101)})
    assert r.status_code == 200, r.text
    _sync(api.event_id)
    assert [t for t in _tasks(api.event_id, status="open") if t.guest_id == bad["id"]], "מספר מתוקן לא חזר לתור"


# ── H: sync חוזר / מקבילי — בלי כפילויות ובלי קריסה ─────────────────────

def test_repeated_and_overlapping_sync_is_idempotent() -> None:
    api, _ = bootstrap()
    for i in range(20):
        api.add_guest(f"מקבילי {i}", _phone(47200 + i))
    configure_track(api)
    _sync(api.event_id)
    before = [(t.guest_id, t.event_cycle, t.round_number) for t in _tasks(api.event_id)]

    from app import call_ops

    db = _session()
    try:  # מדמה sync אחר שהכניס אותן שורות בדיוק באותו רגע
        rows = [dict(event_id=api.event_id, guest_id=g, event_cycle=c, round_number=r,
                     planned_date="2030-01-01", due_date="2030-01-01")
                for g, c, r in before]
        call_ops._insert_tasks(db, rows)
        db.commit()
    finally:
        db.close()
    _sync(api.event_id)
    _sync(api.event_id)
    after = [(t.guest_id, t.event_cycle, t.round_number) for t in _tasks(api.event_id)]
    assert sorted(after) == sorted(before) and len(set(after)) == len(after)


# ── I: הסנכרון היומי — מוגן ו-idempotent ─────────────────────────────────

def test_daily_sync_job_is_protected_and_idempotent(monkeypatch) -> None:
    api, _ = bootstrap()
    api.add_guest(f"לילי {_tag()}", _phone(47301))
    configure_track(api)
    path = "/internal/jobs/call-sync"

    monkeypatch.delenv("VEYA_JOB_SECRET", raising=False)
    assert api.client.post(path, headers={"X-Veya-Job-Secret": "x" * 30}).status_code == 404

    monkeypatch.setenv("VEYA_JOB_SECRET", "short")
    assert api.client.post(path, headers={"X-Veya-Job-Secret": "short"}).status_code == 404, "סוד קצר מדי התקבל"

    secret = "s" * 32
    monkeypatch.setenv("VEYA_JOB_SECRET", secret)
    assert api.client.post(path).status_code == 404
    assert api.client.post(path, headers={"X-Veya-Job-Secret": secret + "x"}).status_code == 404
    assert api.client.get(path, headers={"X-Veya-Job-Secret": secret}).status_code in (404, 405)

    first = api.client.post(path, headers={"X-Veya-Job-Secret": secret})
    assert first.status_code == 200, first.text
    count = len(_tasks(api.event_id))
    again = api.client.post(path, headers={"X-Veya-Job-Secret": secret})
    assert again.status_code == 200 and again.json()["created"] == 0
    assert len(_tasks(api.event_id)) == count
