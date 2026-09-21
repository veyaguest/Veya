"""מרכז שליטה בטלפנים — פנקס משימות השיחה מעל לוח הזמנים של אישורי ההגעה.

שרשרת מקור האמת (לא משתנה):
    Event → rsvp_timeline (מתי כל סבב) → Guest.rsvp_status (מי עדיין פתוח)
    → CallTask (מה נקבע, אצל מי, מה קרה) → CallLog (כל ניסיון שיחה)

עקרונות:
- **``sync`` אידמפוטנטי.** אפשר להריץ אותו בכל בקשה; הוא לא יוצר כפילות
  (UNIQUE במסד) ולא דורס שינוי ידני (``pinned``).
- **עבר נשמר, עתיד מחושב.** משימות נוצרות עד מחר (כדי שאפשר יהיה להקצות
  מראש). מעבר למחר — תצוגה מקדימה חיה מלוח הזמנים, בלי שורות במסד, ולכן
  שינוי במועד סגירת הרשימה מתעדכן בה מעצמו.
- **מי שסיים מעקב לא נשאר ברשימה.** אישר/ביטל (בכל ערוץ) → המשימה נסגרת
  ב-sync הבא כ-``closed_by_rsvp``.
- **"היום" = ישראל** (``local_time``).
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app import call_center, event_cycle, local_time, models, roles, rsvp_timeline
from app.automation import parse_event_date

# ── אוצר מילים ─────────────────────────────────────────────────────────────
OPEN = "open"
DONE = "done"
CLOSED_BY_RSVP = "closed_by_rsvp"
CANCELLED = "cancelled"
SKIPPED = "skipped"
STATUSES = (OPEN, DONE, CLOSED_BY_RSVP, CANCELLED, SKIPPED)
HANDLED = (DONE, CLOSED_BY_RSVP)

MANUAL_ROUND = 0

REASON_LABELS = {
    "no_response": "עדיין לא אישר/ה הגעה",
    "no_whatsapp_reply": "לא הגיב/ה להודעות WhatsApp",
    "maybe": "השיב/ה 'אולי'",
    "callback": "ביקש/ה שיחה חוזרת",
    "manual": "נוספה ידנית",
    "wrong_number_fixed": "מספר הטלפון תוקן",
}

CLOSED_REASON_LABELS = {
    "confirmed": "אישר/ה הגעה בשיחה",
    "declined": "עדכן/ה שלא יגיע/ה בשיחה",
    "no_answer": "לא ענה/תה",
    "busy": "לא ניתן היה להשיג",
    "wrong_number": "מספר שגוי",
    "rsvp_confirmed": "אישר/ה הגעה בערוץ אחר",
    "rsvp_declined": "ביטל/ה הגעה בערוץ אחר",
    "next_round": "עבר לסבב הבא בלי טיפול",
    "event_passed": "האירוע כבר התקיים",
    "track_inactive": "מסלול אישורי ההגעה לא פעיל",
    "no_phone": "אין מספר טלפון",
    "schedule_changed": "לוח הזמנים השתנה",
    "round_stopped": "הסבב נעצר",
    "manual": "בוטלה ידנית",
    "feature_off": "הטלפנים כבויים לאירוע",
}

# ניסיונות שמהם המוזמן נחשב "דורש טיפול נוסף" (לאורך כל המחזור). ברירת
# מחדל — ניתן לשינוי ב"כללי המערכת" (``calls.many_attempts``).
MANY_ATTEMPTS = 3


def many_attempts() -> int:
    try:
        from app import settings_registry

        return int(settings_registry.value("calls.many_attempts"))
    except Exception:  # noqa: BLE001
        return MANY_ATTEMPTS
UNREACHABLE_OUTCOMES = ("no_answer", "busy")

AVAILABILITY_LABELS = {"active": "פעיל", "inactive": "לא פעיל", "vacation": "בחופשה"}

# כמה זמן תוצאת sync מלא נחשבת טרייה (שניות). פעולה שמשנה משימה מריצה
# sync ממוקד לאירוע שלה בלי קשר למגבלה הזו.
SYNC_TTL_SECONDS = 45
_last_full_sync: dict[str, float] = {}


def _iso(d: date) -> str:
    return d.isoformat()


def parse_day(value: Optional[str], default: date) -> date:
    if not value:
        return default
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


# ── סבבים פעילים לאירוע ────────────────────────────────────────────────────

def _controls(db: Session, event_ids: Iterable[int]) -> dict[tuple[int, int, int], models.CallRoundControl]:
    ids = list(event_ids)
    if not ids:
        return {}
    rows = db.scalars(
        select(models.CallRoundControl).where(models.CallRoundControl.event_id.in_(ids))
    ).all()
    return {(r.event_id, r.event_cycle, r.round_number): r for r in rows}


@dataclass
class RoundPlan:
    round_number: int
    date: date
    total_rounds: int
    state: str = ""          # "" / paused / stopped / started


def round_plans(
    event: models.Event,
    now: datetime,
    controls: dict[tuple[int, int, int], models.CallRoundControl],
) -> list[RoundPlan]:
    """סבבי השיחות של האירוע לפי לוח הזמנים, כולל הפעלה ידנית מוקדמת."""
    cycle = event_cycle.of(event)
    placements = rsvp_timeline.call_rounds(event, now)
    total = len(placements)
    plans = []
    for p in placements:
        ctrl = controls.get((event.id, cycle, p.round_number))
        d = p.date
        if ctrl is not None and ctrl.state == "started" and ctrl.created_at is not None:
            d = min(d, local_time.israel_date(ctrl.created_at))
        plans.append(RoundPlan(p.round_number, d, total, ctrl.state if ctrl else ""))
    return plans


def _default_assignees(db: Session, event_ids: Iterable[int]) -> dict[int, list[int]]:
    ids = list(event_ids)
    out: dict[int, list[int]] = defaultdict(list)
    if not ids:
        return out
    for event_id, user_id in db.execute(
        select(models.CallAssignment.event_id, models.CallAssignment.user_id)
        .where(models.CallAssignment.event_id.in_(ids))
    ).all():
        out[event_id].append(user_id)
    return out


# ── זמינות טלפנים ──────────────────────────────────────────────────────────

def profiles(db: Session, user_ids: Optional[Iterable[int]] = None) -> dict[int, models.CallerProfile]:
    stmt = select(models.CallerProfile)
    if user_ids is not None:
        ids = list(user_ids)
        if not ids:
            return {}
        stmt = stmt.where(models.CallerProfile.user_id.in_(ids))
    return {p.user_id: p for p in db.scalars(stmt).all()}


def is_available(user: models.User, profile: Optional[models.CallerProfile], day: date) -> bool:
    """האם הטלפן יכול לקבל משימות ליום הזה. נאכף בשרת בכל הקצאה."""
    if user is None or user.disabled or not roles.is_phone_agent(user):
        return False
    if profile is None or profile.availability == "active":
        return True
    if profile.availability == "inactive":
        return False
    # vacation: לא זמין בטווח; טווח ריק = לא זמין עד שיוחזר לפעיל.
    start = profile.unavailable_from or ""
    end = profile.unavailable_until or ""
    iso = _iso(day)
    if not start and not end:
        return False
    return not ((not start or start <= iso) and (not end or iso <= end))


def availability_label(user: models.User, profile: Optional[models.CallerProfile], day: date) -> str:
    if user.disabled:
        return "חסום"
    if profile is None or profile.availability == "active":
        return "פעיל"
    if profile.availability == "vacation":
        return "בחופשה" if not is_available(user, profile, day) else "פעיל"
    return AVAILABILITY_LABELS.get(profile.availability, profile.availability)


# ── sync ───────────────────────────────────────────────────────────────────

@dataclass
class SyncStats:
    created: int = 0
    rescheduled: int = 0
    closed_by_rsvp: int = 0
    skipped: int = 0
    cancelled: int = 0
    reopened: int = 0
    events: int = 0


def sync(
    db: Session,
    *,
    now: Optional[datetime] = None,
    event_ids: Optional[set[int]] = None,
    force: bool = False,
) -> SyncStats:
    """מיישר את פנקס המשימות מול לוח הזמנים ומצב המוזמנים. לא מבצע commit.

    ``event_ids`` — סנכרון ממוקד (למשל אחרי שיחה). בלי — כל האירועים,
    לכל היותר פעם ב-``SYNC_TTL_SECONDS`` לתהליך (אלא אם ``force``).
    """
    now = now or datetime.utcnow()
    key = "all" if event_ids is None else ""
    if key and not force:
        last = _last_full_sync.get(key)
        if last is not None and time.monotonic() - last < SYNC_TTL_SECONDS:
            return SyncStats()

    stats = SyncStats()
    today = local_time.israel_date(now)
    tomorrow = today + timedelta(days=1)
    today_iso, tomorrow_iso = _iso(today), _iso(tomorrow)
    stamp = datetime.utcnow()

    ev_stmt = select(models.Event).where(
        models.Event.rsvp_track_active.is_(True), models.Event.event_date != "",
    )
    if event_ids is not None:
        if not event_ids:
            return stats
        ev_stmt = ev_stmt.where(models.Event.id.in_(event_ids))
    from app import features

    events = [
        e for e in db.scalars(ev_stmt).all()
        if not call_center.event_has_ended(e, today) and features.enabled("calls", e)
    ]
    active_ids = {e.id for e in events}
    stats.events = len(events)
    controls = _controls(db, active_ids)
    defaults = _default_assignees(db, active_ids)

    # יעדי יצירה: הסבב האחרון שהגיע (היום) + סבב שמתוכנן בדיוק למחר.
    targets: dict[int, list[tuple[RoundPlan, bool]]] = {}
    plans_by_event: dict[int, list[RoundPlan]] = {}
    for e in events:
        plans = round_plans(e, now, controls)
        plans_by_event[e.id] = plans
        arrived = [p for p in plans if p.date <= today]
        chosen: list[tuple[RoundPlan, bool]] = []
        if arrived:
            chosen.append((arrived[-1], True))
        chosen.extend((p, False) for p in plans if p.date == tomorrow)
        targets[e.id] = chosen

    guests_by_event: dict[int, list[models.Guest]] = defaultdict(list)
    all_guests: dict[int, models.Guest] = {}
    if active_ids:
        # רק מוזמנים שעדיין צריכים שיחה — השאר נטענים בנפרד רק אם יש להם משימה פתוחה.
        for g in db.scalars(select(models.Guest).where(
            models.Guest.event_id.in_(active_ids),
            models.Guest.rsvp_status.in_(call_center.OPEN_STATUSES),
        )).all():
            guests_by_event[g.event_id].append(g)
            all_guests[g.id] = g
        wrong_logs = db.scalars(
            select(models.CallLog).where(
                models.CallLog.event_id.in_(active_ids),
                models.CallLog.outcome == call_center.WRONG_NUMBER,
            )
        ).all()
        unresolved_wrong = call_center.unresolved_wrong_numbers(
            list(wrong_logs), {gid: g.phone or "" for gid, g in all_guests.items()}
        )
    else:
        unresolved_wrong = set()

    task_stmt = select(models.CallTask)
    if event_ids is not None:
        task_stmt = task_stmt.where(models.CallTask.event_id.in_(event_ids))
    else:
        # כל המשימות הפתוחות + כל משימות האירועים הפעילים (לבדיקת קיום).
        task_stmt = task_stmt.where(or_(
            models.CallTask.status == OPEN,
            models.CallTask.event_id.in_(active_ids or {0}),
        ))
    tasks = db.scalars(task_stmt).all()
    by_key = {(t.guest_id, t.event_cycle, t.round_number): t for t in tasks}
    missing_guest_ids = {t.guest_id for t in tasks if t.status == OPEN and t.guest_id not in all_guests}
    if missing_guest_ids:
        for g in db.scalars(select(models.Guest).where(models.Guest.id.in_(missing_guest_ids))).all():
            all_guests[g.id] = g

    # עומס להקצאת ברירת מחדל (רק בין טלפני האירוע, רק זמינים).
    caller_ids = {uid for ids in defaults.values() for uid in ids}
    callers = {
        u.id: u for u in db.scalars(select(models.User).where(models.User.id.in_(caller_ids or {0}))).all()
    }
    profs = profiles(db, callers.keys())
    load: dict[tuple[int, str], int] = defaultdict(int)
    for t in tasks:
        if t.status == OPEN and t.assignee_id:
            load[(t.assignee_id, t.due_date)] += 1

    def pick_default(event_id: int, day: date) -> Optional[int]:
        options = [
            uid for uid in defaults.get(event_id, [])
            if uid in callers and is_available(callers[uid], profs.get(uid), day)
        ]
        if not options:
            return None
        return min(options, key=lambda uid: (load[(uid, _iso(day))], uid))

    # שיחות שכבר תועדו לפני שנוצרה משימה (למשל לפני שהפנקס הופעל) — המשימה
    # נולדת עם מה שכבר קרה, ולא "מתחילה מאפס" מול היסטוריה קיימת.
    prior_logs: dict[tuple[int, int], list[models.CallLog]] = defaultdict(list)
    if active_ids:
        for lg in db.scalars(
            select(models.CallLog).where(models.CallLog.event_id.in_(active_ids))
            .order_by(models.CallLog.created_at, models.CallLog.id)
        ).all():
            prior_logs[(lg.guest_id, lg.round_number)].append(lg)

    # 1) יצירה / עדכון מועד / פתיחה מחדש אחרי תיקון מספר
    for e in events:
        cycle = event_cycle.of(e)
        for plan, arrived in targets.get(e.id, []):
            if plan.state in ("paused", "stopped"):
                continue
            plan_iso = _iso(plan.date)
            for g in guests_by_event.get(e.id, []):
                if g.rsvp_status not in call_center.OPEN_STATUSES or not (g.phone or "").strip():
                    continue
                task = by_key.get((g.id, cycle, plan.round_number))
                if task is None:
                    if g.id in unresolved_wrong:
                        continue
                    assignee = pick_default(e.id, plan.date)
                    task = models.CallTask(
                        event_id=e.id, guest_id=g.id, event_cycle=cycle,
                        round_number=plan.round_number, planned_date=plan_iso,
                        due_date=plan_iso,
                        reason="maybe" if g.rsvp_status == "maybe" else "no_response",
                        status=OPEN, assignee_id=assignee, created_at=stamp, updated_at=stamp,
                    )
                    logs = prior_logs.get((g.id, plan.round_number), [])
                    if logs:
                        last = logs[-1]
                        task.attempts = len(logs)
                        task.last_outcome = last.outcome
                        task.last_attempt_at = last.created_at
                        task.handled_by_id = last.created_by_id
                        if last.outcome == "callback" and last.callback_at is not None:
                            task.reason = "callback"
                            task.due_date = max(plan_iso, _iso(local_time.israel_date(last.callback_at)))
                        elif last.outcome in call_center.ATTEMPT_OUTCOMES or last.outcome in call_center.DECISION_OUTCOMES:
                            task.status, task.closed_reason, task.closed_at = DONE, last.outcome, last.created_at
                    db.add(task)
                    by_key[(g.id, cycle, plan.round_number)] = task
                    if assignee:
                        load[(assignee, plan_iso)] += 1
                    stats.created += 1
                    continue
                if (
                    task.status == OPEN and not task.pinned and task.attempts == 0
                    and task.planned_date > today_iso and task.planned_date != plan_iso
                ):
                    task.planned_date = plan_iso
                    task.due_date = plan_iso
                    task.updated_at = stamp
                    stats.rescheduled += 1
                elif (
                    task.status == DONE and task.last_outcome == call_center.WRONG_NUMBER
                    and g.id not in unresolved_wrong and arrived
                ):
                    task.status = OPEN
                    task.reason = "wrong_number_fixed"
                    task.due_date = max(today_iso, task.due_date)
                    task.closed_reason = ""
                    task.closed_at = None
                    task.updated_at = stamp
                    stats.reopened += 1

    # 2) סגירת מה שכבר לא צריך שיחה
    inactive_events: dict[int, Optional[models.Event]] = {}
    for t in list(by_key.values()):
        if t.status != OPEN:
            continue
        reason = ""
        new_status = SKIPPED
        guest = all_guests.get(t.guest_id)
        if t.event_id not in active_ids:
            # אירוע שהסתיים / מסלול שכובה (או לא נטען בסנכרון ממוקד).
            if event_ids is not None and t.event_id not in event_ids:
                continue
            ev = inactive_events.get(t.event_id)
            if ev is None:
                ev = inactive_events[t.event_id] = db.get(models.Event, t.event_id)
            if ev is not None and call_center.event_has_ended(ev, today):
                reason = "event_passed"
            elif ev is not None and not features.enabled("calls", ev):
                reason = "feature_off"
            else:
                reason = "track_inactive"
        elif guest is None:
            continue
        elif guest.rsvp_status not in call_center.OPEN_STATUSES:
            reason = f"rsvp_{guest.rsvp_status}" if guest.rsvp_status in ("confirmed", "declined") else "rsvp_confirmed"
            new_status = CLOSED_BY_RSVP
        elif not (guest.phone or "").strip():
            reason = "no_phone"
        elif t.guest_id in unresolved_wrong and t.round_number != MANUAL_ROUND:
            reason = "wrong_number"
            new_status = DONE
        else:
            plans = plans_by_event.get(t.event_id, [])
            plan = next((p for p in plans if p.round_number == t.round_number), None)
            if t.round_number != MANUAL_ROUND:
                if plan is not None and plan.state == "stopped":
                    reason, new_status = "round_stopped", CANCELLED
                elif t.planned_date > today_iso and not t.pinned and t.attempts == 0 and (
                    plan is None or plan.date > tomorrow
                ):
                    reason, new_status = "schedule_changed", CANCELLED
                else:
                    arrived = [p for p in plans if p.date <= today]
                    current = arrived[-1].round_number if arrived else None
                    replacement = (
                        by_key.get((t.guest_id, t.event_cycle, current)) if current is not None else None
                    )
                    if (
                        replacement is not None and t.round_number < current
                        and t.reason != "callback"
                    ):
                        reason = "next_round"
        if not reason:
            continue
        t.status = new_status
        t.closed_reason = reason
        t.closed_at = stamp
        t.updated_at = stamp
        if new_status == CLOSED_BY_RSVP:
            stats.closed_by_rsvp += 1
        elif new_status == CANCELLED:
            stats.cancelled += 1
        else:
            stats.skipped += 1

    # callback ישן שסבב חדש כבר מכסה — נסגר כדי שהמוזמן לא יופיע פעמיים.
    open_by_guest: dict[int, list[models.CallTask]] = defaultdict(list)
    for t in by_key.values():
        if t.status == OPEN and t.round_number != MANUAL_ROUND:
            open_by_guest[t.guest_id].append(t)
    for gid, items in open_by_guest.items():
        arrived_items = [t for t in items if t.planned_date <= today_iso]
        if len(arrived_items) > 1:
            keep = max(arrived_items, key=lambda t: t.round_number)
            for t in arrived_items:
                if t is not keep:
                    t.status, t.closed_reason, t.closed_at, t.updated_at = SKIPPED, "next_round", stamp, stamp
                    stats.skipped += 1

    db.flush()
    if key:
        _last_full_sync[key] = time.monotonic()
    return stats


def invalidate_sync_cache() -> None:
    _last_full_sync.clear()


# ── אחרי שיחה ─────────────────────────────────────────────────────────────

def on_outcome(
    db: Session,
    *,
    guest: models.Guest,
    event: models.Event,
    round_number: int,
    outcome: str,
    callback_at: Optional[datetime],
    agent: models.User,
    now: Optional[datetime] = None,
) -> models.CallTask:
    """מעדכן את משימת הסבב אחרי תיעוד שיחה (``routers/call_center.record_outcome``).

    אם אין משימה (למשל sync עוד לא רץ היום) — נוצרת אחת, כדי שכל שיחה תיספר.
    """
    now = now or datetime.utcnow()
    today_iso = _iso(local_time.israel_date(now))
    cycle = event_cycle.of(event)
    task = db.scalar(select(models.CallTask).where(
        models.CallTask.guest_id == guest.id,
        models.CallTask.event_cycle == cycle,
        models.CallTask.round_number == round_number,
    ))
    if task is None:
        task = models.CallTask(
            event_id=event.id, guest_id=guest.id, event_cycle=cycle, round_number=round_number,
            planned_date=today_iso, due_date=today_iso, reason="no_response", status=OPEN,
            created_at=now,
        )
        db.add(task)
    task.attempts = (task.attempts or 0) + 1
    task.last_outcome = outcome
    task.last_attempt_at = now
    task.handled_by_id = agent.id
    task.updated_at = now
    if task.assignee_id is None and roles.is_phone_agent(agent):
        task.assignee_id = agent.id
    if outcome == "callback" and callback_at is not None:
        task.status = OPEN
        task.reason = "callback"
        task.due_date = max(today_iso, _iso(local_time.israel_date(callback_at)))
        task.closed_reason = ""
        task.closed_at = None
    else:
        task.status = DONE
        task.closed_reason = outcome
        task.closed_at = now
    # משימה ידנית פתוחה לאותו מוזמן — השיחה הזו מטפלת גם בה.
    if round_number != MANUAL_ROUND:
        manual = db.scalar(select(models.CallTask).where(
            models.CallTask.guest_id == guest.id,
            models.CallTask.event_cycle == cycle,
            models.CallTask.round_number == MANUAL_ROUND,
            models.CallTask.status == OPEN,
        ))
        if manual is not None and task.status == DONE:
            manual.status, manual.closed_reason, manual.closed_at = DONE, outcome, now
            manual.attempts = (manual.attempts or 0) + 1
            manual.last_outcome, manual.last_attempt_at, manual.handled_by_id = outcome, now, agent.id
    return task


# ── ניקוי לפני מחיקה ──────────────────────────────────────────────────────

def delete_for_guest(db: Session, guest_id: int) -> None:
    for t in db.scalars(select(models.CallTask).where(models.CallTask.guest_id == guest_id)).all():
        db.delete(t)


def delete_for_event(db: Session, event_id: int) -> None:
    for t in db.scalars(select(models.CallTask).where(models.CallTask.event_id == event_id)).all():
        db.delete(t)
    for c in db.scalars(
        select(models.CallRoundControl).where(models.CallRoundControl.event_id == event_id)
    ).all():
        db.delete(c)
    # Overrides וכללי פיצ'רים של האירוע — אין להם FK, אבל אין סיבה להשאיר שאריות.
    for o in db.scalars(select(models.SettingOverride).where(
        models.SettingOverride.scope_type == "event", models.SettingOverride.scope_id == event_id,
    )).all():
        db.delete(o)
    for r in db.scalars(select(models.FeatureRule).where(
        models.FeatureRule.scope_type == "event", models.FeatureRule.scope_id == event_id,
    )).all():
        db.delete(r)
    for ent in db.scalars(select(models.EventEntitlement).where(models.EventEntitlement.event_id == event_id)).all():
        db.delete(ent)


def detach_user(db: Session, user_id: int) -> None:
    for t in db.scalars(select(models.CallTask).where(models.CallTask.assignee_id == user_id)).all():
        t.assignee_id = None
    for p in db.scalars(select(models.CallerProfile).where(models.CallerProfile.user_id == user_id)).all():
        db.delete(p)


# ── שאילתות תצוגה ─────────────────────────────────────────────────────────

GROUPS = ("all", "pending", "handled", "not_handled", "unreachable", "followup", "overdue", "cancelled")


def _visible_filter(user: models.User, db: Session):
    """טלפן רואה: מה שהוקצה לו, ומשימות פנויות באירועים שלו. אדמין — הכול."""
    if getattr(user, "is_admin", False):
        return None
    allowed = call_center.visible_event_ids(db, user)
    unassigned = models.CallTask.assignee_id.is_(None)
    if allowed is not None:
        unassigned = and_(unassigned, models.CallTask.event_id.in_(allowed or {0}))
    return or_(models.CallTask.assignee_id == user.id, unassigned)


def group_filter(group: str, day_iso: str, today_iso: str):
    T = models.CallTask
    if group == "pending":
        return and_(T.status == OPEN, T.due_date == day_iso)
    if group == "overdue":
        return and_(T.status == OPEN, T.due_date < today_iso)
    if group == "handled":
        return and_(T.planned_date == day_iso, T.status.in_(HANDLED))
    if group == "not_handled":
        return and_(T.planned_date == day_iso, T.status.not_in(HANDLED))
    if group == "unreachable":
        return and_(T.planned_date == day_iso, T.status == DONE, T.last_outcome.in_(UNREACHABLE_OUTCOMES))
    if group == "followup":
        return or_(
            and_(T.status == OPEN, T.reason == "callback", T.due_date == day_iso),
            and_(T.planned_date == day_iso, T.last_outcome == call_center.WRONG_NUMBER, T.status == DONE),
            and_(T.planned_date == day_iso, T.attempts >= many_attempts()),
        )
    if group == "cancelled":
        return and_(T.planned_date == day_iso, T.status.in_((CANCELLED, SKIPPED)))
    # all: כל מה שקשור ליום — תוכנן אליו או צריך טיפול בו
    return or_(T.planned_date == day_iso, and_(T.status == OPEN, T.due_date == day_iso))


def day_counts(db: Session, day: date, today: date, visible=None) -> dict:
    T = models.CallTask
    d, t = _iso(day), _iso(today)

    def count(*conds) -> int:
        stmt = select(func.count(T.id)).where(*conds)
        if visible is not None:
            stmt = stmt.where(visible)
        return db.scalar(stmt) or 0

    pending_cond = group_filter("pending", d, t)
    return {
        "planned": count(T.planned_date == d),
        "handled": count(group_filter("handled", d, t)),
        "pending": count(pending_cond),
        "not_handled": count(group_filter("not_handled", d, t)),
        "overdue": count(group_filter("overdue", d, t)) if day == today else 0,
        "unreachable": count(group_filter("unreachable", d, t)),
        "followup": count(group_filter("followup", d, t)),
        "cancelled": count(group_filter("cancelled", d, t)),
        "assigned": count(pending_cond, T.assignee_id.is_not(None)),
        "unassigned": count(pending_cond, T.assignee_id.is_(None)),
    }


@dataclass
class PreviewRow:
    event: models.Event
    guest: models.Guest
    round: RoundPlan
    default_assignee: Optional[int]


def preview(
    db: Session, day: date, *, now: Optional[datetime] = None,
    event_id: Optional[int] = None, allowed_event_ids: Optional[set[int]] = None,
) -> list[PreviewRow]:
    """מי יקבל שיחה ביום עתידי (אחרי מחר) — מחושב חי מלוח הזמנים ומהמצב הנוכחי."""
    now = now or datetime.utcnow()
    today = local_time.israel_date(now)
    stmt = select(models.Event).where(
        models.Event.rsvp_track_active.is_(True), models.Event.event_date != "",
    )
    if event_id is not None:
        stmt = stmt.where(models.Event.id == event_id)
    if allowed_event_ids is not None:
        stmt = stmt.where(models.Event.id.in_(allowed_event_ids or {0}))
    events = [
        e for e in db.scalars(stmt).all()
        if not call_center.event_has_ended(e, today)
        and (parse_event_date(e.event_date) or date.max) >= day
    ]
    controls = _controls(db, [e.id for e in events])
    rounds: dict[int, RoundPlan] = {}
    for e in events:
        for p in round_plans(e, now, controls):
            if p.date == day and p.state not in ("paused", "stopped"):
                rounds[e.id] = p
    if not rounds:
        return []
    defaults = _default_assignees(db, rounds.keys())
    by_id = {e.id: e for e in events}
    guests = db.scalars(
        select(models.Guest).where(
            models.Guest.event_id.in_(rounds.keys()),
            models.Guest.rsvp_status.in_(call_center.OPEN_STATUSES),
            models.Guest.phone != "",
        ).order_by(models.Guest.full_name)
    ).all()
    wrong = db.scalars(select(models.CallLog).where(
        models.CallLog.event_id.in_(rounds.keys()), models.CallLog.outcome == call_center.WRONG_NUMBER,
    )).all()
    unresolved = call_center.unresolved_wrong_numbers(list(wrong), {g.id: g.phone or "" for g in guests})
    return [
        PreviewRow(
            by_id[g.event_id], g, rounds[g.event_id],
            defaults[g.event_id][0] if len(defaults.get(g.event_id, [])) == 1 else None,
        )
        for g in guests if g.id not in unresolved
    ]


def last_whatsapp(db: Session, guest_ids: list[int]) -> dict[int, tuple[int, int]]:
    """לכל מוזמן: (כמה הודעות WhatsApp יצאו אליו, כמה הודעות נכנסו ממנו)."""
    if not guest_ids:
        return {}
    out: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for gid, direction, n in db.execute(
        select(models.Message.guest_id, models.Message.direction, func.count(models.Message.id))
        .where(models.Message.guest_id.in_(guest_ids), models.Message.channel == "whatsapp")
        .group_by(models.Message.guest_id, models.Message.direction)
    ).all():
        out[gid][0 if direction == "outbound" else 1] += n
    return {k: (v[0], v[1]) for k, v in out.items()}


def reason_label(task_reason: str, guest: models.Guest, wa: Optional[tuple[int, int]]) -> str:
    if task_reason == "no_response":
        if guest.rsvp_status == "maybe":
            return REASON_LABELS["maybe"]
        if wa and wa[0] > 0 and wa[1] == 0:
            return REASON_LABELS["no_whatsapp_reply"]
    return REASON_LABELS.get(task_reason, task_reason)


# ── חלוקה אוטומטית ────────────────────────────────────────────────────────

@dataclass
class Proposal:
    task_id: int
    assignee_id: int
    why: str


def propose_assignments(
    db: Session, tasks: list[models.CallTask], day: date, caller_ids: Optional[list[int]] = None,
) -> tuple[list[Proposal], list[int], str]:
    """חלוקה מאוזנת למשימות **לא מוקצות** בלבד. לא מבצעת כלום — מחזירה הצעה.

    סדר עדיפות לכל משימה:
    1. שיחה חוזרת → הטלפן שדיבר עם המוזמן בפעם האחרונה (אם זמין).
    2. טלפן ברירת המחדל של האירוע (אם זמין ויש לו מקום).
    3. הטלפן הזמין עם העומס הנמוך ביותר ביום הזה; בשוויון — מי שכבר מטפל
       באותו אירוע, כדי שאירוע לא יתפזר בין הרבה טלפנים.
    """
    stmt = select(models.User).where(
        models.User.account_type == roles.PHONE_AGENT, models.User.disabled.is_(False),
    )
    if caller_ids:
        stmt = stmt.where(models.User.id.in_(caller_ids))
    callers = {u.id: u for u in db.scalars(stmt).all()}
    profs = profiles(db, callers.keys())
    available = [uid for uid, u in callers.items() if is_available(u, profs.get(uid), day)]
    if not available:
        return [], [t.id for t in tasks], "אין טלפנים זמינים ליום הזה"

    day_iso = _iso(day)
    load: dict[int, int] = defaultdict(int)
    event_load: dict[tuple[int, int], int] = defaultdict(int)
    for uid, eid, n in db.execute(
        select(models.CallTask.assignee_id, models.CallTask.event_id, func.count(models.CallTask.id))
        .where(
            models.CallTask.assignee_id.in_(available),
            models.CallTask.status == OPEN,
            models.CallTask.due_date == day_iso,
        )
        .group_by(models.CallTask.assignee_id, models.CallTask.event_id)
    ).all():
        load[uid] += n
        event_load[(uid, eid)] += n

    def capacity_left(uid: int) -> float:
        cap = profs.get(uid).daily_capacity if profs.get(uid) else None
        return float("inf") if cap is None else cap - load[uid]

    defaults = _default_assignees(db, {t.event_id for t in tasks})
    last_caller: dict[int, int] = {}
    callback_guests = [t.guest_id for t in tasks if t.reason == "callback"]
    if callback_guests:
        for log in db.scalars(
            select(models.CallLog).where(models.CallLog.guest_id.in_(callback_guests))
            .order_by(models.CallLog.created_at, models.CallLog.id)
        ).all():
            if log.created_by_id:
                last_caller[log.guest_id] = log.created_by_id

    proposals: list[Proposal] = []
    leftover: list[int] = []
    for t in sorted(tasks, key=lambda t: (t.reason != "callback", t.event_id, t.id)):
        if t.assignee_id is not None or t.status != OPEN:
            continue
        choice: Optional[int] = None
        why = ""
        prev = last_caller.get(t.guest_id)
        if t.reason == "callback" and prev in available and capacity_left(prev) > 0:
            choice, why = prev, "שיחה חוזרת — אותו טלפן"
        if choice is None:
            for uid in defaults.get(t.event_id, []):
                if uid in available and capacity_left(uid) > 0:
                    if choice is None or load[uid] < load[choice]:
                        choice, why = uid, "טלפן האירוע"
        if choice is None:
            candidates = [uid for uid in available if capacity_left(uid) > 0]
            if candidates:
                choice = min(candidates, key=lambda uid: (load[uid], -event_load[(uid, t.event_id)], uid))
                why = "העומס הנמוך ביותר"
        if choice is None:
            leftover.append(t.id)
            continue
        load[choice] += 1
        event_load[(choice, t.event_id)] += 1
        proposals.append(Proposal(t.id, choice, why))
    note = "" if not leftover else "לא נמצא מקום לכל המשימות — כל הטלפנים הזמינים הגיעו לקיבולת"
    return proposals, leftover, note


def preview_counts(db: Session, days: list[date], *, now: Optional[datetime] = None) -> dict[str, tuple[int, int]]:
    """לכל יום עתידי: (כמה שיחות צפויות, כמה בלי טלפן קבוע). חישוב אחד לכל
    אירוע ושאילתת מוזמנים אחת — לא הרצה של ``preview`` לכל יום בנפרד."""
    if not days:
        return {}
    now = now or datetime.utcnow()
    today = local_time.israel_date(now)
    wanted = set(days)
    events = [
        e for e in db.scalars(select(models.Event).where(
            models.Event.rsvp_track_active.is_(True), models.Event.event_date != "",
        )).all()
        if not call_center.event_has_ended(e, today)
    ]
    controls = _controls(db, [e.id for e in events])
    day_by_event: dict[int, list[date]] = defaultdict(list)
    for e in events:
        for p in round_plans(e, now, controls):
            if p.date in wanted and p.state not in ("paused", "stopped"):
                day_by_event[e.id].append(p.date)
    if not day_by_event:
        return {}
    open_counts = dict(db.execute(
        select(models.Guest.event_id, func.count(models.Guest.id)).where(
            models.Guest.event_id.in_(day_by_event.keys()),
            models.Guest.rsvp_status.in_(call_center.OPEN_STATUSES),
            models.Guest.phone != "",
        ).group_by(models.Guest.event_id)
    ).all())
    # מספרים שגויים שלא תוקנו לא נכנסים לתור — בדיוק כמו ב-``preview``.
    wrong = db.scalars(select(models.CallLog).where(
        models.CallLog.event_id.in_(day_by_event.keys()), models.CallLog.outcome == call_center.WRONG_NUMBER,
    )).all()
    if wrong:
        phones = {gid: (ph or "") for gid, ph in db.execute(
            select(models.Guest.id, models.Guest.phone).where(
                models.Guest.id.in_({lg.guest_id for lg in wrong}),
                models.Guest.rsvp_status.in_(call_center.OPEN_STATUSES),
            )
        ).all()}
        by_guest_event = {lg.guest_id: lg.event_id for lg in wrong}
        for gid in call_center.unresolved_wrong_numbers(list(wrong), phones):
            if gid in phones and phones[gid]:
                eid = by_guest_event[gid]
                open_counts[eid] = max(0, open_counts.get(eid, 0) - 1)
    defaults = _default_assignees(db, day_by_event.keys())
    out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for eid, ds in day_by_event.items():
        n = open_counts.get(eid, 0)
        for d in ds:
            out[_iso(d)][0] += n
            if len(defaults.get(eid, [])) != 1:
                out[_iso(d)][1] += n
    return {k: (v[0], v[1]) for k, v in out.items()}
