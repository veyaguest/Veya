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


def _body_for_event(event: models.Event, stage: str, veya_body: str) -> str:
    """גוף התבנית שהאירוע יקבל בשלב מסוים — מותאם לסוג האירוע.

    למה זה קיים: ברירות המחדל הגלובליות (``VeyaTemplate``) נכתבו בשפת חתונה
    ("אנחנו [שמות בני הזוג]"). עד כה הן הועתקו כמו-שהן לכל אירוע, ולכן בר
    מצווה קיבל בעורך ההודעות נוסח חתונתי שנקרא "אנחנו יונתן" — גם אחרי
    שמסלול השליחה הישיר כבר ידע לבחור נוסח לפי סוג.

    חתונה (וכל אירוע בלי סוג) מקבלת בדיוק את גוף ה-``VeyaTemplate`` כמו קודם
    — אפס שינוי התנהגות, כולל האפשרות של האדמין לערוך את ברירות המחדל בפאנל.
    שאר הסוגים מקבלים את הנוסח שנכתב במיוחד לסוג שלהם ב-``message_library``;
    אם אין התאמה לשלב, נופלים בעדינות חזרה לגוף הגלובלי.
    """
    from app import messaging
    from app.message_library import default_body_for

    body = default_body_for(event.event_type, stage)
    if body is None:
        return veya_body
    # מתרגמים את הטוקנים לשפת הסוג לפני השמירה, כדי שהחוגג יראה בעורך
    # "[שם החוגג]" ולא "[שמות בעלי האירוע]" — ניסוח זוגי באירוע מארח יחיד.
    return messaging.localize_tokens(body, event.event_type)


# נוסחי before_event *ישנים*, מלפני הוספת שורת "מספר שולחן" (commits
# eb543f3 / 4de99f6). עדיין נחוצים כאן: אירוע שהמסלול שלו הופעל *לפני*
# השינוי קיבל לתוכו את הנוסח הישן, ומאותו רגע הוא לא תואם לאף ברירת מחדל
# *נוכחית* — כך שבלי הרשימה הזו הוא נראה (בטעות) כמו נוסח שהזוג ערך ידנית
# ולעולם לא היה מתרענן. הזוגות שכבר יש להם השורה החדשה לא נפגעים מזה —
# ``_known_default_bodies`` רק מרחיב את קבוצת "מותר לרענן", לא כופה שינוי.
_LEGACY_BEFORE_EVENT_BODIES: list[tuple[str | None, str]] = [
    (None, (
        "היי [שם פרטי]!\n"
        "מזכירים שהיום [שמחת] [שמות בני הזוג] ואתם מוזמנים!\n\n"
        "📅 [תאריך האירוע] בשעה [שעה]\n"
        "📍 [שם האולם], [כתובת]\n\n"
        "לניווט נוח: [קישור ניווט]\n"
        "נתראה!"
    )),
    (None, (
        "[שם פרטי], היום זה קורה 🤍\n"
        "מזכירים שהיום [שמחת] [שמות בעלי האירוע] ואתם מוזמנים.\n\n"
        "📅 בשעה [שעה] · 📍 [שם האולם]\n"
        "🧭 לניווט: [קישור ניווט]\n"
        "נתראה!"
    )),
    (None, (
        "[שם פרטי],\n"
        "מתראים היום ב[שמחת] [שמות בעלי האירוע].\n"
        "📍 [שם האולם] · [שעה]\n"
        "🧭 [קישור ניווט]"
    )),
    ("henna", (
        "[שם פרטי], הערב זה קורה! 🎶\n"
        "ב[שמחת] [שמות בעלי האירוע] מחכים לכם צבע, מוזיקה וריקודים.\n"
        "🕗 [שעה]\n"
        "📍 [שם האולם]\n"
        "🧭 [קישור ניווט]"
    )),
    ("henna", (
        "[שם פרטי],\n"
        "מתראים הערב ב[שמחת] [שמות בעלי האירוע].\n"
        "📍 [שם האולם] · [שעה]\n"
        "🧭 [קישור ניווט]"
    )),
    ("bar_mitzvah", (
        "[שם פרטי], היום זה קורה!\n"
        "מזכירים שהיום [שמחת] [שמות בעלי האירוע] — ואתם חלק חשוב ממנו.\n"
        "📅 בשעה [שעה] · 📍 [שם האולם]\n"
        "🧭 [קישור ניווט]\n"
        "נתראה!"
    )),
    ("bat_mitzvah", (
        "[שם פרטי], היום זה קורה!\n"
        "מזכירים שהיום [שמחת] [שמות בעלי האירוע] — ואתם חלק חשוב ממנו.\n"
        "📅 בשעה [שעה] · 📍 [שם האולם]\n"
        "🧭 [קישור ניווט]\n"
        "נתראה!"
    )),
    ("brit", (
        "[שם פרטי],\n"
        "מזכירים שהיום [שמחת] [שמות בעלי האירוע] — ואתם חלק חשוב ממנו.\n"
        "📅 בשעה [שעה] · 📍 [שם האולם]\n"
        "🧭 [קישור ניווט]"
    )),
    ("business", (
        "שלום [שם פרטי],\n"
        "לקראת [האירוע] היום, מספר פרטים:\n"
        "📅 בשעה [שעה]\n"
        "📍 [שם האולם], [כתובת]\n"
        "לניווט: [קישור ניווט]"
    )),
    ("family", (
        "[שם פרטי],\n"
        "היום זה קורה — [שמחת] [שמות בעלי האירוע]! מחכים לראות אתכם.\n"
        "📅 בשעה [שעה] · 📍 [שם האולם]\n"
        "🧭 [קישור ניווט]"
    )),
    ("other", (
        "[שם פרטי],\n"
        "מזכירים שהיום [שמחת] [שמות בעלי האירוע] — מחכים לראותכם.\n"
        "📅 בשעה [שעה] · 📍 [שם האולם]\n"
        "🧭 [קישור ניווט]"
    )),
]


def _known_default_bodies(db: Session) -> set[str]:
    """כל נוסח שהמערכת *עצמה* הקצתה אי-פעם, בכל סוג אירוע ובכל שלב.

    משמש לזיהוי "התבנית הזו לא נערכה ע"י הזוג" בלי עמודה נוספת בסכימה:
    אם הגוף השמור זהה לאחד מהנוסחים כאן — הוא ברירת מחדל שאיש לא נגע בה,
    ולכן מותר לרענן אותו. אם הוא שונה — הזוג כתב אותו, ולא נוגעים.

    האוסף כולל בכוונה גם את גופי ה-``VeyaTemplate`` *הנוכחיים* (שהאדמין
    יכול לערוך, והם גם מה ששמור אצל אירועים ותיקים) וגם את כל נוסחי
    הספרייה בכל צורותיהם — לפני ואחרי תרגום הטוקנים לשפת הסוג — וגם את
    נוסחי ה-before_event הישנים (ראו ``_LEGACY_BEFORE_EVENT_BODIES``).
    """
    from app import messaging
    from app.message_library import (
        DEFAULT_INVITATION_BY_TYPE, _LIBRARY_BY_TYPE, GENERIC_LIBRARY,
    )

    known = {vt.body for vt in _active_veya_templates(db) if vt.body}
    known.add(messaging.DEFAULT_TEMPLATE)
    known.update(DEFAULT_INVITATION_BY_TYPE.values())

    libraries = list(_LIBRARY_BY_TYPE.items()) + [(None, GENERIC_LIBRARY)]
    for etype, entries in libraries:
        for entry in entries:
            body = entry.get("body", "")
            if not body:
                continue
            known.add(body)
            known.add(messaging.localize_tokens(body, etype))

    for etype, body in _LEGACY_BEFORE_EVENT_BODIES:
        known.add(body)
        known.add(messaging.localize_tokens(body, etype))
    return known


def provision_rsvp_track(db: Session, event: models.Event) -> dict:
    """מעתיק את ברירות המחדל הגלובליות של VEYA אל האירוע. idempotent.

    גוף כל תבנית נבחר לפי *סוג האירוע* (ראו ``_body_for_event``) — התבניות
    הגלובליות קובעות אילו שלבים קיימים ואיך הם נקראים, וסוג האירוע קובע איך
    ההודעה מנוסחת.

    *סנכרון מחדש:* תבנית שכבר קיימת אך גופה עדיין זהה לאחת מברירות המחדל
    המוכרות (ראו ``_known_default_bodies``) מתרעננת לנוסח הנכון לסוג האירוע
    הנוכחי. בלי זה, כל אירוע שנוצר פעם אחת היה קפוא לנצח על הנוסח שקיבל
    ביום הראשון — גם אחרי שיפור הנוסחים, וגם אחרי שהזוג שינה את סוג האירוע.
    תבנית שהזוג ערך בפועל (הגוף שונה מכל ברירת מחדל) לא נוגעים בה.

    מחזיר {"templates_created": n, "rules_created": m, "templates_synced": k}.
    לא עושה commit — הקורא אחראי לכך (כדי לאגד עם פעולות נוספות באותה
    טרנזקציה).
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
    # נטען רק אם יש בכלל תבנית קיימת לבדוק מולה.
    known_defaults: set[str] | None = None
    stage_template_id: dict[str, int] = {}
    templates_created = 0
    templates_synced = 0
    for stage, vt in veya_by_stage.items():
        existing = existing_templates.get(vt.name)
        want_body = _body_for_event(event, stage, vt.body)
        if existing is None:
            mt = models.MessageTemplate(
                event_id=event.id,
                name=vt.name,
                kind=STAGE_TO_KIND.get(stage, "custom"),
                body=want_body,
            )
            db.add(mt)
            db.flush()
            stage_template_id[stage] = mt.id
            existing_templates[vt.name] = mt
            templates_created += 1
        else:
            stage_template_id[stage] = existing.id
            if existing.body != want_body:
                if known_defaults is None:
                    known_defaults = _known_default_bodies(db)
                if existing.body in known_defaults:
                    existing.body = want_body
                    templates_synced += 1

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
    return {
        "templates_created": templates_created,
        "rules_created": rules_created,
        "templates_synced": templates_synced,
    }


def invitation_template_body(db: Session, event: models.Event) -> str:
    """גוף תבנית ההזמנה שהוקצתה לאירוע (או ריק אם עדיין לא הוקצתה)."""
    tmpl = db.scalars(
        select(models.MessageTemplate)
        .where(models.MessageTemplate.event_id == event.id)
        .where(models.MessageTemplate.kind == "invitation")
        .order_by(models.MessageTemplate.created_at)
    ).first()
    return tmpl.body if tmpl else ""
