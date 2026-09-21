"""הדשבורד של האדמין — "מה אני צריך לדעת או לעשות עכשיו?"

כל מספר כאן נגזר מנתון אמיתי במסד או ממשתנה סביבה אמיתי. אין מונים
"לקישוט": פריט מופיע ב"דורש תשומת לב" רק אם יש מאחוריו פעולה שאפשר לבצע,
ו"מצב המערכת" מציג רק מודולים שקיימים בקוד — לא פיצ'רים עתידיים.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import (
    call_center, gift_eligibility, local_time, message_status, messaging, models,
    payout_service, postponement_service, roles,
)

ACTIVE_USER_DAYS = 30
NEW_EVENT_DAYS = 7
FAILED_MESSAGE_DAYS = 7


@dataclass
class AttentionItem:
    key: str
    severity: str          # critical / warning / info
    title: str
    detail: str
    count: int
    page: str              # יעד הניווט באדמין
    event_ids: list[int] = field(default_factory=list)


@dataclass
class ModuleStatus:
    key: str
    label: str
    status: str            # active / beta / off / mock / issue
    detail: str
    page: str = ""


def _env_on(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def modules(db: Session) -> list[ModuleStatus]:
    """מצב המודולים הקיימים בפועל. mock ≠ פעיל: מוצג כמצב נפרד וברור."""
    out: list[ModuleStatus] = []

    wa_mode = messaging.current_mode()
    since = datetime.utcnow() - timedelta(days=FAILED_MESSAGE_DAYS)
    sent_recent = db.scalar(
        select(func.count(models.Message.id)).where(
            models.Message.direction == "outbound",
            models.Message.channel == "whatsapp",
            models.Message.created_at >= since,
        )
    ) or 0
    failed_recent = db.scalar(
        select(func.count(models.Message.id)).where(
            models.Message.direction == "outbound",
            models.Message.status == message_status.FAILED,
            models.Message.created_at >= since,
        )
    ) or 0
    if wa_mode == "live":
        issue = sent_recent >= 20 and failed_recent * 5 > sent_recent  # מעל 20% כשלון
        out.append(ModuleStatus(
            "whatsapp", "WhatsApp", "issue" if issue else "active",
            f"שליחה אמיתית · {failed_recent} כשלונות מתוך {sent_recent} ב-7 ימים", "rules",
        ))
    else:
        out.append(ModuleStatus(
            "whatsapp", "WhatsApp", "mock",
            "מצב הדגמה — הודעות לא נשלחות למוזמנים באמת", "rules",
        ))

    active_callers = db.scalar(
        select(func.count(models.User.id)).where(
            models.User.account_type == roles.PHONE_AGENT,
            models.User.disabled.is_(False),
        )
    ) or 0
    out.append(ModuleStatus(
        "calls", "טלפנים", "active" if active_callers else "off",
        f"{active_callers} טלפנים פעילים" if active_callers else "אין טלפנים פעילים",
        "calls",
    ))

    out.append(ModuleStatus("seating", "הושבה", "active", "מנוע שיבוץ ועורך אולם", "rules"))

    ai_on = _env_on("ANTHROPIC_API_KEY")
    out.append(ModuleStatus(
        "hall_vision", "זיהוי סקיצת אולם (AI)", "active" if ai_on else "off",
        "מחובר" if ai_on else "אין מפתח API מוגדר", "rules",
    ))

    gifts_on = gift_eligibility.service_switch_on()
    pay_mode = (os.getenv("VEYA_PAYMENT_PROVIDER", "mock") or "mock").strip().lower()
    if not gifts_on:
        out.append(ModuleStatus("gifts", "מתנות באשראי", "off", "כבוי (מתג סביבה)", "fees"))
    else:
        out.append(ModuleStatus(
            "gifts", "מתנות באשראי", "mock" if pay_mode == "mock" else "active",
            "סליקה בהדגמה" if pay_mode == "mock" else f"ספק: {pay_mode}", "fees",
        ))

    out.append(ModuleStatus("finance", "כספי האירוע", "active", "ניהול הוצאות וספירת מעטפות", "rules"))

    email_on = _env_on("RESEND_API_KEY")
    out.append(ModuleStatus(
        "email", "אימייל", "active" if email_on else "issue",
        "מחובר" if email_on else "אין מפתח — מיילי אימות ואיפוס לא יישלחו", "",
    ))
    return out


def attention(db: Session, now: Optional[datetime] = None) -> list[AttentionItem]:
    now = now or datetime.utcnow()
    items: list[AttentionItem] = []

    postponements = postponement_service.pending_requests(db)
    if postponements:
        items.append(AttentionItem(
            "postponements", "warning", "בקשות דחייה ממתינות",
            "בעלי האירוע חסומים מעריכה עד להחלטה", len(postponements), "postponements",
            sorted({p.event_id for p in postponements}),
        ))

    payouts = payout_service.awaiting_veya_review(db)
    if payouts:
        items.append(AttentionItem(
            "payouts", "warning", "פרטי חשבון לקבלת מתנות ממתינים לאישור",
            "בלי אישור, בעלי האירוע לא יכולים לקבל כספים", len(payouts), "fees",
            sorted({a.event_id for a in payouts}),
        ))

    since = now - timedelta(days=FAILED_MESSAGE_DAYS)
    failed_by_event = dict(db.execute(
        select(models.Message.event_id, func.count(models.Message.id))
        .where(
            models.Message.direction == "outbound",
            models.Message.status == message_status.FAILED,
            models.Message.created_at >= since,
        )
        .group_by(models.Message.event_id)
    ).all())
    if failed_by_event:
        items.append(AttentionItem(
            "failed_messages", "critical", "הודעות WhatsApp שנכשלו",
            f"ב-{len(failed_by_event)} אירועים, ב-{FAILED_MESSAGE_DAYS} הימים האחרונים",
            sum(failed_by_event.values()), "rsvp", sorted(failed_by_event),
        ))

    # אותו מקור כמו מרכז הטלפנים (פנקס המשימות), כדי ששני המסכים לא יסתרו.
    from app import call_ops

    today_iso = local_time.israel_date(now).isoformat()
    overdue_rows = db.execute(
        select(models.CallTask.event_id, func.count(models.CallTask.id)).where(
            models.CallTask.status == call_ops.OPEN, models.CallTask.due_date < today_iso,
        ).group_by(models.CallTask.event_id)
    ).all()
    overdue = sum(n for _, n in overdue_rows)
    if overdue:
        items.append(AttentionItem(
            "overdue_calls", "critical", "שיחות שהיו צריכות להתבצע ולא טופלו",
            f"ב-{len(overdue_rows)} אירועים", overdue, "calls",
            sorted(e for e, _ in overdue_rows),
        ))

    wrong_logs = db.scalars(
        select(models.CallLog).where(models.CallLog.outcome == call_center.WRONG_NUMBER)
    ).all()
    if wrong_logs:
        phones = dict(db.execute(
            select(models.Guest.id, models.Guest.phone)
            .where(models.Guest.id.in_({lg.guest_id for lg in wrong_logs}))
        ).all())
        open_ids = call_center.unresolved_wrong_numbers(list(wrong_logs), phones)
        if open_ids:
            events = sorted({lg.event_id for lg in wrong_logs if lg.guest_id in open_ids})
            items.append(AttentionItem(
                "wrong_numbers", "info", "מספרי טלפון שגויים שלא תוקנו",
                "המוזמנים יצאו מתור השיחות עד שבעלי האירוע יתקנו", len(open_ids), "calls", events,
            ))

    if messaging.current_mode() != "live":
        live_tracks = db.scalar(
            select(func.count(models.Event.id)).where(models.Event.rsvp_track_active.is_(True))
        ) or 0
        if live_tracks:
            items.append(AttentionItem(
                "whatsapp_mock", "warning", "WhatsApp במצב הדגמה",
                f"{live_tracks} אירועים עם מסלול אישורי הגעה פעיל — ההודעות לא יוצאות באמת",
                live_tracks, "rules",
            ))

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    items.sort(key=lambda i: severity_order.get(i.severity, 3))
    return items


def pulse(db: Session, items: list[AttentionItem], mods: list[ModuleStatus],
          now: Optional[datetime] = None) -> dict:
    now = now or datetime.utcnow()
    today = local_time.israel_date(now).isoformat()
    active_users = db.scalar(
        select(func.count(func.distinct(models.LoginEvent.user_id))).where(
            models.LoginEvent.created_at >= now - timedelta(days=ACTIVE_USER_DAYS)
        )
    ) or 0
    upcoming_events = db.scalar(
        select(func.count(models.Event.id)).where(
            models.Event.event_date >= today, models.Event.event_date != "",
        )
    ) or 0
    new_events = db.scalar(
        select(func.count(models.Event.id)).where(
            models.Event.created_at >= now - timedelta(days=NEW_EVENT_DAYS)
        )
    ) or 0
    events_needing = {eid for i in items if i.key != "whatsapp_mock" for eid in i.event_ids}
    pending_requests = sum(i.count for i in items if i.key in ("postponements", "payouts"))
    warnings = sum(1 for m in mods if m.status in ("issue", "mock"))
    return {
        "active_users": active_users,
        "active_users_days": ACTIVE_USER_DAYS,
        "upcoming_events": upcoming_events,
        "new_events": new_events,
        "new_events_days": NEW_EVENT_DAYS,
        "events_needing_attention": len(events_needing),
        "pending_requests": pending_requests,
        "warnings": warnings,
    }


def overview(db: Session) -> dict:
    now = datetime.utcnow()
    # פתיחת הדשבורד היא גם "טריגר יומי": בלי cron, זה מה שמבטיח שתכנון השיחות
    # של היום נשמר גם אם אף אחד לא נכנס למרכז הטלפנים.
    from app import call_ops

    call_ops.sync(db)
    db.commit()
    mods = modules(db)
    items = attention(db, now)
    return {
        "today": local_time.israel_date(now).isoformat(),
        "pulse": pulse(db, items, mods, now),
        "attention": [asdict(i) for i in items],
        "modules": [asdict(m) for m in mods],
    }


# ---------------------------------------------------------------------------
# חיפוש גלובלי
# ---------------------------------------------------------------------------

SEARCH_LIMIT = 6


def search(db: Session, q: str) -> list[dict]:
    """חיפוש אחד על פני משתמשים, אירועים, מוזמנים, אולמות ויומן האדמין.

    מחזיר קבוצות קטנות (עד ``SEARCH_LIMIT`` לכל סוג) — זה מסך קפיצה, לא דוח.
    """
    from app import event_terms

    q = (q or "").strip()
    if len(q) < 2:
        return []
    like = f"%{q}%"
    digits = "".join(ch for ch in q if ch.isdigit())
    groups: list[dict] = []

    user_filters = [models.User.email.ilike(like), models.User.display_name.ilike(like)]
    if len(digits) >= 4:
        user_filters.append(models.User.phone.ilike(f"%{digits}%"))
    if q.isdigit():
        user_filters.append(models.User.id == int(q))
    users = db.scalars(select(models.User).where(or_(*user_filters)).limit(SEARCH_LIMIT)).all()
    if users:
        groups.append({"type": "user", "label": "משתמשים", "items": [
            {
                "id": u.id,
                "title": u.display_name or u.email,
                "subtitle": " · ".join(filter(None, [
                    u.email, roles.ACCOUNT_TYPE_LABELS.get(u.account_type or "", ""),
                    "חסום" if u.disabled else "", "אדמין" if u.is_admin else "",
                ])),
            }
            for u in users
        ]})

    event_filters = [
        models.Event.groom_name.ilike(like), models.Event.bride_name.ilike(like),
        models.Event.venue_name.ilike(like),
    ]
    if q.isdigit():
        event_filters.append(models.Event.id == int(q))
    events = db.scalars(
        select(models.Event).where(or_(*event_filters)).order_by(models.Event.id.desc()).limit(SEARCH_LIMIT)
    ).all()
    if events:
        owner_emails = dict(db.execute(
            select(models.User.id, models.User.email)
            .where(models.User.id.in_({e.owner_id for e in events if e.owner_id}))
        ).all())
        guest_counts = dict(db.execute(
            select(models.Guest.event_id, func.count(models.Guest.id))
            .where(models.Guest.event_id.in_([e.id for e in events]))
            .group_by(models.Guest.event_id)
        ).all())
        groups.append({"type": "event", "label": "אירועים", "items": [
            {
                "id": e.id,
                "title": event_terms.hosts_names(e.event_type, e.groom_name, e.bride_name) or f"אירוע #{e.id}",
                "subtitle": " · ".join(filter(None, [
                    owner_emails.get(e.owner_id, ""), _ddmmyyyy(e.event_date),
                    f"{guest_counts.get(e.id, 0)} מוזמנים",
                ])),
            }
            for e in events
        ]})

    guest_filters = [models.Guest.full_name.ilike(like)]
    if len(digits) >= 4:
        guest_filters.append(models.Guest.phone.ilike(f"%{digits}%"))
    guests = db.execute(
        select(models.Guest, models.Event)
        .join(models.Event, models.Guest.event_id == models.Event.id)
        .where(or_(*guest_filters)).limit(SEARCH_LIMIT)
    ).all()
    if guests:
        groups.append({"type": "guest", "label": "מוזמנים", "items": [
            {
                "id": g.id,
                "event_id": e.id,
                "title": g.full_name,
                "subtitle": " · ".join(filter(None, [
                    event_terms.hosts_names(e.event_type, e.groom_name, e.bride_name),
                    _ddmmyyyy(e.event_date),
                ])),
            }
            for g, e in guests
        ]})

    venues = db.scalars(
        select(models.Venue).where(or_(models.Venue.name.ilike(like), models.Venue.city.ilike(like)))
        .limit(SEARCH_LIMIT)
    ).all()
    if venues:
        groups.append({"type": "venue", "label": "אולמות", "items": [
            {"id": v.id, "title": v.name, "subtitle": " · ".join(filter(None, [v.city, v.address]))}
            for v in venues
        ]})

    feature_hits = []
    from app import features as feature_registry

    ql = q.lower()
    for key, f in feature_registry.BUILTIN.items():
        if ql in f.label.lower() or ql in key:
            feature_hits.append({"id": key, "title": f.label, "subtitle": "פיצ'ר"})
    for flag in db.scalars(select(models.FeatureFlag).where(
        or_(models.FeatureFlag.label.ilike(like), models.FeatureFlag.key.ilike(like))
    ).limit(SEARCH_LIMIT)).all():
        if flag.key not in feature_registry.BUILTIN:
            feature_hits.append({"id": flag.key, "title": flag.label or flag.key, "subtitle": "פיצ'ר"})
    if feature_hits:
        groups.append({"type": "feature", "label": "פיצ'רים", "items": feature_hits[:SEARCH_LIMIT]})

    plans = db.scalars(select(models.Plan).where(
        or_(models.Plan.name.ilike(like), models.Plan.key.ilike(like))
    ).limit(SEARCH_LIMIT)).all()
    if plans:
        groups.append({"type": "plan", "label": "מסלולים", "items": [
            {"id": p.id, "title": p.name, "subtitle": p.key} for p in plans
        ]})

    logs = db.scalars(
        select(models.AdminAuditLog)
        .where(or_(models.AdminAuditLog.summary.ilike(like), models.AdminAuditLog.target_label.ilike(like)))
        .order_by(models.AdminAuditLog.id.desc()).limit(SEARCH_LIMIT)
    ).all()
    if logs:
        groups.append({"type": "audit", "label": "יומן פעילות", "items": [
            {
                "id": r.id, "title": r.summary,
                "subtitle": " · ".join(filter(None, [
                    r.actor_label,
                    local_time.to_israel(r.created_at).strftime("%d.%m.%Y %H:%M") if r.created_at else "",
                ])),
            }
            for r in logs
        ]})
    return groups


def _ddmmyyyy(iso: str) -> str:
    if not iso or len(iso) < 10:
        return ""
    y, m, d = iso[:10].split("-")
    return f"{d}.{m}.{y}"
