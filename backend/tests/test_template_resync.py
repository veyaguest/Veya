"""סנכרון תבניות ברירת מחדל — בלי עמודה בסכימה.

הרצה: ``venv/bin/python tests/test_template_resync.py`` (עצמאי, בלי pytest).

הבעיה שזה פותר: ``provision_rsvp_track`` הוא idempotent לפי *שם* התבנית,
ולכן תבנית שנוצרה פעם אחת הייתה קפואה לנצח. אירוע עסקי שנפתח לפני שנוסחי
ברירת המחדל תוקנו המשיך להציג "אנחנו [שמות בני הזוג]" גם אחרי כל תיקון —
וגם שינוי סוג האירוע לא הזיז אותה.

הפתרון שנבחר *לא* מוסיף עמודה (``is_customized``), אלא משווה את הגוף השמור
מול כל ברירות המחדל שהמערכת אי-פעם הקצתה. זה בטוח יותר: עמודה חדשה הייתה
מקבלת ערך ברירת מחדל לכל השורות הקיימות — כלומר *הנחה* שהן לא נערכו.
ההשוואה *מוכיחה* את זה, שורה-שורה.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import models, rsvp_track  # noqa: E402
from app.message_library import DEFAULT_INVITATION_BY_TYPE  # noqa: E402

# הנוסח החתונתי ההיסטורי — בדיוק מה ששמור היום ב-DB של אירועים ותיקים.
LEGACY_WEDDING_BODY = (
    "שלום [שם אורח]! ✨\n"
    "אנחנו [שמות בני הזוג], ונשמח מאוד לראות אתכם.\n\n"
    "📅 [תאריך האירוע] בשעה [שעה]\n"
    "📍 [שם האולם], [כתובת]\n\n"
    "נשמח לדעת אם תגיעו — לאישור הגעה: [קישור אישור]\n"
    "מחכים לראותכם!"
)

STAGES = [
    ("invitation", "הזמנה", "invitation"),
    ("first_reminder", "תזכורת ראשונה", "reminder"),
    ("second_reminder", "תזכורת שנייה", "reminder"),
    ("thank_you", "תודה על האישור", "thank_you"),
    ("before_event", "לפני האירוע", "pre_event"),
]


def _fresh_db():
    """DB זמני בזיכרון עם ברירות המחדל הגלובליות זרועות, כמו בפרודקשן."""
    engine = create_engine("sqlite://")
    models.Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    for order, (stage, name, _kind) in enumerate(STAGES, start=1):
        db.add(models.VeyaTemplate(
            stage=stage, name=name, sort_order=order,
            body=LEGACY_WEDDING_BODY, active=True, is_default=True,
        ))
    db.add(models.VeyaWorkflowStep(
        step_order=1, name="תזכורת ראשונה", offset_days=3,
        action_kind="send", template_stage="first_reminder", active=True,
    ))
    db.commit()
    # המטמון של ברירות המחדל הגלובליות משותף בין בדיקות — מנקים אותו.
    from app import cache
    cache.invalidate_prefix("veya_")
    return db


def _seed_event(db, event_type: str, stale_body: str = LEGACY_WEDDING_BODY):
    """אירוע שכבר הוקצה בעבר, עם הנוסח החתונתי הישן שמור בכל השלבים."""
    ev = models.Event(event_type=event_type, groom_name="יונתן", venue_name="הגן")
    db.add(ev)
    db.flush()
    for _stage, name, kind in STAGES:
        db.add(models.MessageTemplate(
            event_id=ev.id, name=name, kind=kind, body=stale_body))
    db.commit()
    return ev


def _invitation(db, event_id: int) -> models.MessageTemplate:
    return db.scalars(
        select(models.MessageTemplate)
        .where(models.MessageTemplate.event_id == event_id)
        .where(models.MessageTemplate.kind == "invitation")
    ).first()


def test_stale_defaults_are_refreshed():
    """אירוע ותיק עם נוסח חתונתי ישן מתרענן לנוסח הנכון לסוגו."""
    db = _fresh_db()
    ev = _seed_event(db, "bat_mitzvah")

    result = rsvp_track.provision_rsvp_track(db, ev)
    db.commit()

    assert result["templates_created"] == 0, "לא אמורות להיווצר תבניות חדשות"
    assert result["templates_synced"] == len(STAGES), (
        f"ציפינו לרענן {len(STAGES)} תבניות, רועננו {result['templates_synced']}")
    body = _invitation(db, ev.id).body
    assert body == DEFAULT_INVITATION_BY_TYPE["bat_mitzvah"], (
        "ההזמנה לא התרעננה לנוסח בת המצווה")
    assert "[שמות בני הזוג]" not in body, "נשאר ניסוח זוגי באירוע מארח יחיד"
    print("✓ תבניות ברירת מחדל ותיקות מתרעננות לנוסח הנכון לסוג")


def test_edited_templates_are_never_touched():
    """תבנית שהזוג ערך בפועל נשארת בדיוק כפי שהיא — גם אחרי הקצאה חוזרת."""
    db = _fresh_db()
    ev = _seed_event(db, "business")
    mine = "היי [שם פרטי], זה הנוסח שכתבתי בעצמי ואני רוצה לשמור עליו."
    _invitation(db, ev.id).body = mine
    db.commit()

    result = rsvp_track.provision_rsvp_track(db, ev)
    db.commit()

    assert _invitation(db, ev.id).body == mine, "נוסח שהזוג כתב נדרס!"
    # שאר השלבים כן מתרעננים — הם עדיין ברירת מחדל.
    assert result["templates_synced"] == len(STAGES) - 1
    print("✓ תבנית שנערכה ידנית לא נדרסת, והשאר כן מתרעננות")


def test_event_type_change_moves_the_messages():
    """שינוי סוג האירוע אחרי ההקצאה — ההודעות עוברות לשפה של הסוג החדש."""
    db = _fresh_db()
    ev = _seed_event(db, "wedding")
    rsvp_track.provision_rsvp_track(db, ev)
    db.commit()
    assert _invitation(db, ev.id).body == DEFAULT_INVITATION_BY_TYPE["wedding"]

    ev.event_type = "brit"
    db.commit()
    rsvp_track.provision_rsvp_track(db, ev)
    db.commit()

    body = _invitation(db, ev.id).body
    assert body == DEFAULT_INVITATION_BY_TYPE["brit"], (
        "ההודעות לא עברו לשפת הסוג החדש אחרי שינוי סוג האירוע")
    print("✓ שינוי סוג אירוע מעביר את ההודעות לשפה הנכונה")


def test_provisioning_is_stable_when_nothing_changed():
    """הקצאה חוזרת בלי שינוי לא מדווחת על רענון — כדי לא לבזבז commit."""
    db = _fresh_db()
    ev = _seed_event(db, "family")
    rsvp_track.provision_rsvp_track(db, ev)
    db.commit()

    again = rsvp_track.provision_rsvp_track(db, ev)
    assert again["templates_created"] == 0
    assert again["templates_synced"] == 0, "רענון חוזר על תבנית שכבר מעודכנת"
    print("✓ הקצאה חוזרת יציבה — אפס רענונים מיותרים")


if __name__ == "__main__":
    test_stale_defaults_are_refreshed()
    test_edited_templates_are_never_touched()
    test_event_type_change_moves_the_messages()
    test_provisioning_is_stable_when_nothing_changed()
    print()
    print("=== כל בדיקות סנכרון התבניות עברו ===")
