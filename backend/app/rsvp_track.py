"""שירות מסלול אישורי-ההגעה של VEYA — הקצאת המסלול הקבוע לאירוע ספציפי.

כשהזוג מפעיל את המסלול, המערכת מעתיקה את ברירות המחדל הגלובליות
(``VeyaTemplate`` + ``VeyaWorkflowStep``) אל האירוע: תבניות הודעה ניתנות
לעריכה (``MessageTemplate``) וחוקי אוטומציה (``AutomationRule``). כך מנוע
ה-due/dedup/timeline הקיים (``automation.py``) ממשיך לעבוד בלי שכפול לוגיקה.

הפונקציה ``provision_rsvp_track`` idempotent — הפעלה חוזרת לא משכפלת תבניות
או חוקים (מזוהים לפי שם). אין כאן קריאות LLM ואין תלות ב-``seating.py``.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import cache, models

# TTL לספריית ברירות המחדל הגלובליות (תבניות + מסלול) — נקראת בכל
# GET /automation/templates ובכל הפעלת מסלול, אבל משתנה רק כשאדמין עורך
# בפאנל הניהול. invalidate_prefix ב-admin.py מבטיח שהעריכה תיראה מיד.
LIBRARY_CACHE_TTL_SECONDS = 300  # 5 דקות

# מיפוי שלב VEYA -> סוג ה-MessageTemplate של האירוע (לתיוג/סינון בלבד).
STAGE_TO_KIND = {
    "invitation": "invitation",
    "first_reminder": "reminder",
    "second_reminder": "reminder",
    "thank_you": "thank_you",
    "before_event": "pre_event",
}


def _active_veya_templates(db: Session) -> list:
    """תבניות ברירת המחדל הפעילות, מסודרות — ממוטמן (נקרא בכל אירוע/הפעלה)."""

    def _load():
        rows = db.scalars(
            select(models.VeyaTemplate)
            .where(models.VeyaTemplate.active.is_(True))
            .order_by(models.VeyaTemplate.sort_order, models.VeyaTemplate.id)
        ).all()
        return cache.snapshot_all(rows)

    return cache.get_or_set(
        "veya_templates:active", LIBRARY_CACHE_TTL_SECONDS, _load
    )


def _active_workflow_steps(db: Session) -> list:
    """שלבי המסלול הקבוע הפעילים, לפי סדר — ממוטמן (נקרא בכל הפעלת מסלול)."""

    def _load():
        rows = db.scalars(
            select(models.VeyaWorkflowStep)
            .where(models.VeyaWorkflowStep.active.is_(True))
            .order_by(models.VeyaWorkflowStep.step_order)
        ).all()
        return cache.snapshot_all(rows)

    return cache.get_or_set(
        "veya_workflow:active", LIBRARY_CACHE_TTL_SECONDS, _load
    )


def _default_templates_by_stage(db: Session) -> dict[str, models.VeyaTemplate]:
    """תבנית ברירת המחדל לכל שלב (הראשונה לפי sort_order אם יש כמה)."""
    rows = _active_veya_templates(db)
    out: dict[str, models.VeyaTemplate] = {}
    for t in rows:
        if not t.is_default:
            continue
        out.setdefault(t.stage, t)
    return out


def provision_rsvp_track(db: Session, event: models.Event) -> dict:
    """מעתיק את ברירות המחדל הגלובליות של VEYA אל האירוע. idempotent.

    מחזיר {"templates_created": n, "rules_created": m}. לא עושה commit —
    הקורא אחראי לכך (כדי לאגד עם פעולות נוספות באותה טרנזקציה).
    """
    veya_by_stage = _default_templates_by_stage(db)

    # תבניות קיימות של האירוע לפי שם — למניעת יצירה כפולה.
    existing_templates = {
        t.name: t
        for t in db.scalars(
            select(models.MessageTemplate).where(
                models.MessageTemplate.event_id == event.id
            )
        ).all()
    }
    stage_template_id: dict[str, int] = {}
    templates_created = 0
    for stage, vt in veya_by_stage.items():
        existing = existing_templates.get(vt.name)
        if existing is None:
            mt = models.MessageTemplate(
                event_id=event.id,
                name=vt.name,
                kind=STAGE_TO_KIND.get(stage, "custom"),
                body=vt.body,
            )
            db.add(mt)
            db.flush()
            stage_template_id[stage] = mt.id
            existing_templates[vt.name] = mt
            templates_created += 1
        else:
            stage_template_id[stage] = existing.id

    # חוקי אוטומציה קיימים של האירוע לפי שם — למניעת יצירה כפולה.
    existing_rule_names = {
        r.rule_name
        for r in db.scalars(
            select(models.AutomationRule).where(
                models.AutomationRule.event_id == event.id
            )
        ).all()
    }
    steps = _active_workflow_steps(db)
    rules_created = 0
    for step in steps:
        if step.name in existing_rule_names:
            continue
        template_id = (
            stage_template_id.get(step.template_stage) if step.template_stage else None
        )
        db.add(
            models.AutomationRule(
                event_id=event.id,
                rule_name=step.name,
                trigger_type="no_response",
                delay_days=step.offset_days,
                target_group="pending",
                template_id=template_id,
                action_kind=step.action_kind,
                active=True,
            )
        )
        existing_rule_names.add(step.name)
        rules_created += 1

    db.flush()
    return {"templates_created": templates_created, "rules_created": rules_created}


def invitation_template_body(db: Session, event: models.Event) -> str:
    """גוף תבנית ההזמנה שהוקצתה לאירוע (או ריק אם עדיין לא הוקצתה)."""
    tmpl = db.scalars(
        select(models.MessageTemplate)
        .where(models.MessageTemplate.event_id == event.id)
        .where(models.MessageTemplate.kind == "invitation")
        .order_by(models.MessageTemplate.created_at)
    ).first()
    return tmpl.body if tmpl else ""
