"""מנוע אוטומציות אישורי הגעה — טהור ודטרמיניסטי (RSVP Automation Engine).

עיקרון מנחה: המנוע רק *מחשב* אילו פעולות הגיע זמנן ("תור לאישור"). הוא לא
שולח כלום ולא כותב ל-DB. השליחה בפועל קורית רק אחרי אישור מפורש של הבעלים
(ב-``routers/automation.py``). אין כאן קריאות LLM ואין שום תלות ב-
``app/seating.py`` — זו שכבה עצמאית לחלוטין.

חמשת הטריגרים:
- event_created        — X ימים אחרי יצירת האירוע.
- invitation_sent      — X ימים אחרי שנשלחה הזמנה למוזמן.
- no_response          — X ימים אחרי ההזמנה, רק אם המוזמן עדיין לא ענה.
- before_event_date    — X ימים לפני תאריך האירוע.
- guest_confirmed      — X ימים אחרי שהמוזמן אישר הגעה.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from app import messaging, models


@dataclass
class DueActionData:
    """פעולה שהגיע זמנה — מקשרת חוק, מוזמן ותצוגה מקדימה מוכנה לשליחה."""

    rule: models.AutomationRule
    guest: models.Guest
    preview: str


def parse_event_date(s: str) -> Optional[date]:
    """המרת מחרוזת תאריך האירוע ל-date. תומך ב-YYYY-MM-DD וב-DD/MM/YYYY."""
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def event_date_display(event: models.Event) -> str:
    """תצוגת תאריך למוזמן בפורמט ישראלי (DD/MM/YYYY) אם ניתן לפענח."""
    d = parse_event_date(event.event_date)
    return d.strftime("%d/%m/%Y") if d else (event.event_date or "").strip()


def guest_matches_target(guest: models.Guest, target_group: str, target_group_value: str) -> bool:
    """האם המוזמן שייך לקהל היעד של החוק."""
    if target_group == "all":
        return True
    if target_group in ("pending", "confirmed", "declined", "maybe"):
        return guest.rsvp_status == target_group
    if target_group == "side_groom":
        return guest.side == "groom"
    if target_group == "side_bride":
        return guest.side == "bride"
    if target_group == "group":
        return (guest.group_type or "") == (target_group_value or "")
    return False


def _invitation_time_by_guest(messages: list[models.Message]) -> dict[int, datetime]:
    """זמן ההזמנה הראשונה של כל מוזמן (הודעה יוצאת מסוג invitation שנשלחה)."""
    out: dict[int, datetime] = {}
    for m in messages:
        if m.guest_id is None:
            continue
        if m.direction == "outbound" and m.kind == "invitation" and m.status == "sent":
            prev = out.get(m.guest_id)
            if prev is None or m.created_at < prev:
                out[m.guest_id] = m.created_at
    return out


def _confirm_time_by_guest(messages: list[models.Message]) -> dict[int, datetime]:
    """זמן התגובה האחרונה (inbound reply) של כל מוזמן — עוגן ל-guest_confirmed."""
    out: dict[int, datetime] = {}
    for m in messages:
        if m.guest_id is None:
            continue
        if m.direction == "inbound" and m.kind == "reply":
            prev = out.get(m.guest_id)
            if prev is None or m.created_at > prev:
                out[m.guest_id] = m.created_at
    return out


def _already_fired(messages: list[models.Message]) -> set[tuple[int, int]]:
    """זוגות (rule_id, guest_id) שכבר נשלחו — למניעת שליחה כפולה של אותו חוק."""
    fired: set[tuple[int, int]] = set()
    for m in messages:
        if m.rule_id is not None and m.guest_id is not None:
            fired.add((m.rule_id, m.guest_id))
    return fired


def _trigger_ready(
    rule: models.AutomationRule,
    guest: models.Guest,
    now: datetime,
    event: models.Event,
    event_date: Optional[date],
    inv_time: dict[int, datetime],
    conf_time: dict[int, datetime],
) -> bool:
    """האם הטריגר של החוק הבשיל עבור המוזמן הזה כרגע."""
    tt = rule.trigger_type
    delay = timedelta(days=max(0, rule.delay_days))

    if tt == "event_created":
        anchor = event.created_at
        return anchor is not None and now >= anchor + delay

    if tt == "invitation_sent":
        anchor = inv_time.get(guest.id)
        return anchor is not None and now >= anchor + delay

    if tt == "no_response":
        anchor = inv_time.get(guest.id)
        if anchor is None or guest.rsvp_status != "pending":
            return False
        return now >= anchor + delay

    if tt == "before_event_date":
        if event_date is None:
            return False
        trigger_day = event_date - timedelta(days=max(0, rule.delay_days))
        # נשלח רק בחלון שבין X ימים לפני האירוע ועד יום האירוע (לא אחריו).
        return trigger_day <= now.date() <= event_date

    if tt == "guest_confirmed":
        if guest.rsvp_status != "confirmed":
            return False
        anchor = conf_time.get(guest.id)
        return anchor is not None and now >= anchor + delay

    return False


def compute_due_actions(
    event: models.Event,
    guests: list[models.Guest],
    rules: list[models.AutomationRule],
    messages: list[models.Message],
    templates_by_id: dict[int, models.MessageTemplate],
    now: Optional[datetime] = None,
) -> list[DueActionData]:
    """מחשב את כל הפעולות שהגיע זמנן — התור לאישור. ללא תופעות לוואי.

    כל פעולה = (חוק פעיל, מוזמן שתואם לקהל היעד ולטריגר, ועדיין לא נשלח אליו
    החוק הזה). ה-preview כבר ממולא במשתנים כדי שהבעלים יראה בדיוק מה יישלח.
    """
    now = now or datetime.utcnow()
    inv_time = _invitation_time_by_guest(messages)
    conf_time = _confirm_time_by_guest(messages)
    fired = _already_fired(messages)
    event_date = parse_event_date(event.event_date)
    date_display = event_date_display(event)

    actions: list[DueActionData] = []
    for rule in rules:
        if not rule.active:
            continue
        template = templates_by_id.get(rule.template_id) if rule.template_id else None
        body = template.body if (template and template.body) else ""
        for guest in guests:
            if (rule.id, guest.id) in fired:
                continue
            if not guest.phone:
                continue
            if not guest_matches_target(guest, rule.target_group, rule.target_group_value):
                continue
            if not _trigger_ready(rule, guest, now, event, event_date, inv_time, conf_time):
                continue
            preview = messaging.render_automation_template(
                body,
                guest_name=guest.full_name,
                groom=event.groom_name,
                bride=event.bride_name,
                venue=event.venue_name,
                venue_address=event.venue_address or "",
                date=date_display,
                time=event.event_time or "",
                link=messaging.confirm_link(guest.guest_token),
                table_number=guest.table_number,
                guest_count=guest.effective_seats,
                event_type=event.event_type,
            )
            actions.append(DueActionData(rule=rule, guest=guest, preview=preview))
    return actions


def compute_recommendations(
    event: models.Event,
    guests: list[models.Guest],
    now: Optional[datetime] = None,
) -> list[dict]:
    """המלצות מעקב חכם (Smart Follow-Up) — נגזרות דטרמיניסטית מהמצב הנוכחי.

    מחזיר רשימת {"severity": "info"|"warn", "text": ...}. אין כאן שליחה —
    רק ניסוח המלצה שהבעלים יחליט אם לפעול לפיה.
    """
    now = now or datetime.utcnow()
    recs: list[dict] = []
    total = len(guests)
    if total == 0:
        return recs

    pending = [g for g in guests if g.rsvp_status == "pending"]
    maybe = [g for g in guests if g.rsvp_status == "maybe"]
    event_date = parse_event_date(event.event_date)
    days_left = (event_date - now.date()).days if event_date else None

    if days_left is not None and days_left >= 0 and pending:
        recs.append({
            "severity": "warn" if days_left <= 21 else "info",
            "text": (
                f"נשארו {days_left} ימים לאירוע ו-{len(pending)} מוזמנים עדיין לא אישרו."
            ),
        })
    elif pending:
        recs.append({
            "severity": "info",
            "text": f"{len(pending)} מוזמנים עדיין לא אישרו הגעה.",
        })

    # קרוב לאירוע (עד 10 ימים) עם הרבה ממתינים — כדאי לעבור לטלפונים.
    if days_left is not None and 0 <= days_left <= 10 and len(pending) >= 10:
        recs.append({
            "severity": "warn",
            "text": f"כדאי להתחיל שיחות טלפון עם {len(pending)} המוזמנים שלא הגיבו.",
        })

    if maybe:
        recs.append({
            "severity": "info",
            "text": f"{len(maybe)} מוזמנים סימנו 'אולי' — שווה לחזור אליהם לתשובה סופית.",
        })

    return recs
