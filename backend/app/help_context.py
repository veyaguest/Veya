"""העובדות שמערכת העזרה רשאית לקבל — מצומצם, מפורש, קריאה בלבד.

HELP_CENTER_PLAN.md שלב 3, והחלטות המייסד (2026-09-29):

- **אין "כל פרטי האירוע".** כל מסך מקבל רק את רשימת העובדות שהוגדרה לו
  (``help_contexts.json``), וכל בדיקה על מוזמן — רק את מה שהבדיקה צריכה.
  בדיקה בפרונט (``helpKb``/``helpContexts`` tests) מוודאת שהרשימות האלה
  זהות בדיוק למה שבסיס הידע של העזרה משתמש בו — לא יותר ולא פחות.
- **בלי מידע אישי.** ספירות, סטטוסים, תאריכים ודגלים. אין שמות, אין טלפונים,
  אין תוכן הודעות, אין סיבת כשל גולמית. היחיד שמחזיר שמות: ``guest_options``
  — כי כדי לבדוק מוזמן צריך לבחור אותו — ורק מזהה + שם.
- **קריאה בלבד.** שום פונקציה כאן לא כותבת, לא שולחת ולא מקצה (גם לא
  ``provision_event_messages``). נבדק ב-``tests/test_help_context.py``.
- **לא ידוע = ``None``.** כשאי אפשר לדעת בוודאות — מחזירים ``None``, והעזרה
  אומרת "אי אפשר לבדוק" במקום לנחש.
- **בלי שירות חיצוני ובלי AI.** רק ה-DB ופונקציות קיימות של VEYA.

כל עובדה מחושבת ע"י **אותה פונקציה** שהמוצר עצמו משתמש בה (לוח הזמנים,
סיווג טלפון, סטטוס הזמנה) — לא לוגיקה מקבילה שעלולה לסטות.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Union

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import (
    communication, event_cycle, features, guest_journey, invitations,
    messaging, models, postponement_service, rsvp_timeline,
)
from app.automation import parse_event_date

FactValue = Union[bool, int, str, None]

# ── ההגדרה: איזו עובדה לאיזה מסך / לאיזו בדיקה ─────────────────────────────
# קובץ JSON אחד שגם בדיקות הפרונט קוראות — מקור אמת יחיד לשני הצדדים.
_SPEC = json.loads((Path(__file__).with_name("help_contexts.json")).read_text(encoding="utf-8"))
SCREENS: dict[str, list[str]] = _SPEC["screens"]
GUEST_CHECKS: dict[str, list[str]] = _SPEC["guest_checks"]

#: כמה מוזמנים לכל היותר מחזיר חיפוש המוזמנים של העזרה.
GUEST_OPTIONS_LIMIT = 8


class _Ctx:
    """הקשר לחישוב עובדות לאירוע אחד — טוען רק מה שעובדה ביקשה, פעם אחת."""

    def __init__(self, db: Session, event: models.Event, now: Optional[datetime] = None):
        self.db = db
        self.event = event
        self.now = now or datetime.utcnow()
        self._guests: Optional[list[models.Guest]] = None
        self._timeline: Optional[dict] = None
        self._invited: Optional[set[int]] = None
        self._ems: Optional[dict[str, models.EventMessage]] = None

    @property
    def guests(self) -> list[models.Guest]:
        if self._guests is None:
            self._guests = list(self.db.scalars(
                select(models.Guest).where(models.Guest.event_id == self.event.id)
            ).all())
        return self._guests

    @property
    def invited(self) -> set[int]:
        if self._invited is None:
            self._invited = invitations.invited_guest_ids(self.db, self.event.id, self.event)
        return self._invited

    @property
    def timeline(self) -> dict:
        # אותו חישוב של מסך "אישורי הגעה" (routers/automation.py::rsvp_timeline_view).
        if self._timeline is None:
            self._timeline = rsvp_timeline.compute_timeline(self.event, self.guests, now=self.now)
        return self._timeline

    @property
    def ems(self) -> dict[str, models.EventMessage]:
        # קריאה בלבד — בכוונה לא provision_event_messages (שכותב).
        if self._ems is None:
            self._ems = communication.event_messages_by_type(self.db, self.event.id)
        return self._ems

    def today(self) -> date:
        return guest_journey.today_in_israel(self.now)


def _ddmm_to_iso(value: Optional[str]) -> Optional[str]:
    """"29/10/2026" (הפורמט של compute_timeline) → "2026-10-29"."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def _bad_phone(ctx: _Ctx) -> int:
    # בדיוק כמו DashboardStats.bad_phone_guests (routers/stats.py).
    return sum(1 for g in ctx.guests if invitations.classify_phone(g.phone) != "valid")


def _not_yet_invited(ctx: _Ctx) -> int:
    # בדיוק כמו InvitationSendPreview.not_yet_sent (invitations.build_send_preview).
    return sum(
        1 for g in ctx.guests
        if invitations.classify_phone(g.phone) == "valid" and g.id not in ctx.invited
    )


def _invitation_empty(ctx: _Ctx) -> Optional[bool]:
    em = ctx.ems.get("invitation")
    if em is None:
        # רצף ההודעות עוד לא הוקצה — הוא יוקצה (עם התוכן שלו) רק בשליחה. לא מנחשים.
        return None
    return not (em.content or "").strip()


def _postpone(ctx: _Ctx) -> str:
    row = postponement_service.latest(ctx.db, ctx.event.id)
    return row.status if row is not None else "none"


def _can_request_postpone(ctx: _Ctx) -> bool:
    # כמו routers/postpone.py::_read — אפשר לבקש כשאין בקשה פתוחה.
    from app import postponement_status

    row = postponement_service.latest(ctx.db, ctx.event.id)
    return row is None or not postponement_status.is_open(row.status)


#: כל העובדות שהשרת יודע לחשב. מפתח שלא מופיע כאן — לא קיים.
FACTS: dict[str, Callable[[_Ctx], FactValue]] = {
    # ── האירוע ──
    "event.days_to_event": lambda c: guest_journey.days_until_event(c.event, today=c.today()),
    "event.has_date": lambda c: parse_event_date(c.event.event_date) is not None,
    "event.commit_chosen": lambda c: c.event.venue_commit_days_before is not None,
    "event.edit_unlocked": lambda c: postponement_service.edit_unlocked(c.db, c.event),
    "event.postpone": _postpone,
    "event.can_request_postpone": _can_request_postpone,
    # ── אישורי הגעה (אותו לוח זמנים של המסך) ──
    "rsvp.phase": lambda c: rsvp_timeline.track_phase(c.event, c.now),
    "rsvp.start_date": lambda c: (
        d.isoformat() if (d := rsvp_timeline.rsvp_request_date(c.event, c.now)) else None
    ),
    "rsvp.commit_date": lambda c: _ddmm_to_iso(c.timeline.get("commitment_date")),
    "rsvp.next_date": lambda c: _ddmm_to_iso(c.timeline.get("next_action_date")),
    # התווית כפי שהשרת מחשב אותה ("סבב שיחות ראשון"); הפרונט ממיר לניסוח של
    # בעלי האירוע עם plainStepLabel הקיים (RsvpTimeline.tsx) — כמו במסך עצמו.
    "rsvp.next_label": lambda c: c.timeline.get("next_action_label"),
    "rsvp.today_is_weekend": lambda c: rsvp_timeline.is_weekend(c.today()),
    # ── הודעות ──
    "messaging.mode": lambda c: messaging.current_mode(),
    "messaging.emergency_stop": lambda c: messaging.emergency_stop_active(),
    "messaging.invitation_empty": _invitation_empty,
    "invites.sent": lambda c: len(c.invited),
    "invites.not_yet": _not_yet_invited,
    # ── מוזמנים (ספירות בלבד) ──
    "guests.total": lambda c: len(c.guests),
    "guests.bad_phone": _bad_phone,
    "guests.confirmed": lambda c: sum(1 for g in c.guests if g.rsvp_status == "confirmed"),
    # ── פיצ'רים והושבה ──
    "feature.calls": lambda c: features.enabled("calls", c.event),
    "seating.undo_available": lambda c: bool((c.event.seating_snapshot or {}).get("tables")),
}


def _check_spec() -> None:
    """כל עובדה שמוגדרת למסך — קיימת. נכשל בעליית השרת, לא בזמן בקשה."""
    for screen, names in SCREENS.items():
        for n in names:
            if n not in FACTS:
                raise RuntimeError(f"help_contexts.json: עובדה לא מוכרת '{n}' במסך '{screen}'")
    for check, names in GUEST_CHECKS.items():
        for n in names:
            if n not in FACTS and n not in GUEST_FACTS:
                raise RuntimeError(f"help_contexts.json: עובדה לא מוכרת '{n}' בבדיקה '{check}'")


def screen_facts(db: Session, event: models.Event, screen: str, *, now: Optional[datetime] = None) -> dict[str, FactValue]:
    """העובדות של מסך אחד — ורק הן."""
    ctx = _Ctx(db, event, now)
    return {name: FACTS[name](ctx) for name in SCREENS[screen]}


# ── בדיקה על מוזמן אחד ──────────────────────────────────────────────────────

_INVITATION_STATES = {"sent", "delivered", "read", "failed", "blocked"}


def _guest_invitation(ctx: _Ctx, guest: models.Guest) -> Optional[str]:
    """סטטוס ההזמנה האחרונה למוזמן, במחזור הנוכחי. ``none`` = לא נשלחה.
    סטטוס שאינו סופי (queued/pending) → ``None``: לא יודעים עדיין."""
    row = ctx.db.scalars(
        select(models.Message)
        .where(models.Message.event_id == ctx.event.id)
        .where(models.Message.guest_id == guest.id)
        .where(models.Message.direction == "outbound")
        .where(models.Message.kind == "invitation")
        .where(event_cycle.current_sends(ctx.event))
        .order_by(models.Message.id.desc())
        .limit(1)
    ).first()
    if row is None:
        return "none"
    return row.status if row.status in _INVITATION_STATES else None


def _joined_after_last_round(ctx: _Ctx, guest: models.Guest) -> Optional[bool]:
    """האם המוזמן נוסף אחרי שסבב ה-WhatsApp האחרון של המסלול כבר יצא.

    אותו כלל של השליחה (communication.compute_due_messages → _existed_by):
    מוזמן מצטרף רק לסבבים שהתחילו אחרי שנוסף. אין עדיין סבב שיצא → ``None``.
    """
    now = ctx.now.replace(tzinfo=timezone.utc) if ctx.now.tzinfo is None else ctx.now
    starts = []
    for mt in communication.TRACK_ROUND_TYPES:
        start = communication.track_round_start(mt, ctx.event, ctx.ems, ctx.now)
        if start is not None and start <= now:
            starts.append(start)
    if not starts:
        return None
    return not communication._existed_by(guest, max(starts))


GUEST_FACTS: dict[str, Callable[[_Ctx, models.Guest], FactValue]] = {
    "guest.phone": lambda c, g: invitations.classify_phone(g.phone),
    "guest.invitation": _guest_invitation,
    "guest.rsvp": lambda c, g: g.rsvp_status,
    "guest.joined_after_last_round": _joined_after_last_round,
}


def guest_check_facts(
    db: Session, event: models.Event, guest: models.Guest, check: str,
    *, now: Optional[datetime] = None,
) -> dict[str, FactValue]:
    """העובדות שבדיקה אחת צריכה על מוזמן אחד — ורק הן. בלי שם ובלי טלפון."""
    ctx = _Ctx(db, event, now)
    out: dict[str, FactValue] = {}
    for name in GUEST_CHECKS[check]:
        out[name] = GUEST_FACTS[name](ctx, guest) if name in GUEST_FACTS else FACTS[name](ctx)
    return out


def guest_options(db: Session, event: models.Event, q: str) -> list[dict]:
    """בחירת מוזמן לבדיקה: מזהה + שם בלבד, עד ``GUEST_OPTIONS_LIMIT``.

    זה המקום היחיד בעזרה שמחזיר שמות — כי בלי לבחור מוזמן אי אפשר לבדוק
    אותו. אין כאן טלפון, סטטוס או כל שדה אחר.
    """
    needle = (q or "").strip().lower()
    # חיפוש ריק (למשל רק רווחים) היה מתאים לכולם — כלומר "תנו לי את הרשימה".
    # לא מחזירים כלום בלי לפחות 2 תווים של חיפוש אמיתי.
    if len(needle) < 2:
        return []
    rows = db.scalars(
        select(models.Guest)
        .where(models.Guest.event_id == event.id)
        .order_by(models.Guest.full_name)
    ).all()
    hits = [g for g in rows if needle in (g.full_name or "").lower()]
    return [{"id": g.id, "name": g.full_name} for g in hits[:GUEST_OPTIONS_LIMIT]]


_check_spec()
