"""בדיקות למחיקת משתמש בפאנל האדמין בשני מצבים (app/routers/admin.py:
_delete_user_impl) — הפיצ'ר: "משתמש בלבד" מול "משתמש + כל האירועים שלו".

תרחישים:
  1-4: מצב "user_only" — אירוע/מוזמנים/הודעות נשארים בשלמותם, הבעלות עוברת
       לחשבון-המערכת (ולא ל-NULL — ראו הסבר ב-_ORPHANED_EVENTS_HOLDER_EMAIL),
       חשבון-המערכת נוצר פעם אחת ומשותף בין כמה מחיקות, ומשתמש בלי אירועים
       בכלל לא יוצר חשבון-מערכת מיותר.
  5-7: מצב "user_and_events" — הכול נמחק (cascade מלא), אטומי, ולא פוגע
       באירוע של משתמש אחר.
  8-11: שמירות בטיחות — לא ניתן למחוק את עצמך / את האדמין האחרון / את
       חשבון-המערכת עצמו / מצב לא תקין — ובכולן שום דבר לא משתנה ב-DB
       (rollback מלא, לא מצב "חצי מחוק").
  12: ניקוי נכון של קשרים ברמת המשתמש: EventMember/EventInvitation/
      ConsentRecord/CallLog/CallAssignment/AuditLog — נשארים תקינים מבחינת
      FK, ולא נמחקת בטעות גישה תקינה של מישהו אחר.

הרצה: ``venv/bin/python tests/test_admin_delete_user.py`` (עצמאי, בלי pytest).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, delete, event, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402
from app.database import Base  # noqa: E402
from app.routers.admin import (  # noqa: E402
    _ORPHANED_EVENTS_HOLDER_EMAIL,
    _delete_user_impl,
)
from fastapi import HTTPException  # noqa: E402


def _fresh_session() -> Session:
    engine = create_engine("sqlite://")

    # בדיוק כמו app/database.py: בלי PRAGMA foreign_keys=ON סקוליט לא אוכף
    # FK בכלל, וה-DELETE/UPDATE-ים היו "מצליחים" גם אם סדר/לוגיקת הניקוי
    # שגויים. בלי זה הבדיקות האלה לא היו תופסות שום באג אמיתי.
    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return Session(engine)


def _fresh_session_no_autoflush() -> Session:
    """כמו ``_fresh_session``, אבל עם ``autoflush=False`` — בדיוק כמו
    ``SessionLocal`` האמיתי (app/database.py). ``Session(engine)`` הרגיל
    בברירת המחדל (autoflush=True) "מציל" באגי-flush מהסוג הזה בטעות: כל
    SELECT מוחק אוטומטית שינויים ממתינים לפני שהוא רץ, כך שבאג שתלוי בסדר
    flush (כמו test_13 למטה) לא היה נתפס בכלל תחת ברירת המחדל. חובה להשתמש
    בזה לבדיקות שנוגעות בהתנהגות flush/autoflush עצמה.
    """
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _record):  # noqa: ANN001
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    return Session(engine, autoflush=False, expire_on_commit=False)


def _make_user(db: Session, email: str, is_admin: bool = False) -> models.User:
    u = models.User(email=email, password_hash="x", display_name="בדיקה", is_admin=is_admin)
    db.add(u)
    db.commit()
    return u


def _make_event(db: Session, owner_id: int) -> models.Event:
    ev = models.Event(owner_id=owner_id, groom_name="יואב", bride_name="דנה", event_type="wedding")
    db.add(ev)
    db.commit()
    return ev


def _make_guest(db: Session, event_id: int, phone: str = "0501234567") -> models.Guest:
    g = models.Guest(event_id=event_id, full_name="מוזמן", phone=phone, side="groom")
    db.add(g)
    db.commit()
    return g


def test_1_user_only_keeps_event_and_guests_intact() -> None:
    db = _fresh_session()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    target = _make_user(db, "couple@veya.test")
    ev = _make_event(db, target.id)
    g = _make_guest(db, ev.id)

    events_count = _delete_user_impl(db, admin, target, "user_only")
    db.commit()

    assert events_count == 1
    assert db.get(models.User, target.id) is None
    kept_event = db.get(models.Event, ev.id)
    assert kept_event is not None
    assert kept_event.owner_id is not None
    assert kept_event.owner_id != target.id
    assert db.get(models.Guest, g.id) is not None
    print("✓ 1: 'משתמש בלבד' — האירוע והמוזמנים נשארים בשלמותם, הבעלות עברה")


def test_2_user_only_owner_becomes_holder_not_null() -> None:
    """קריטי: owner_id **חייב** להישאר לא-NULL. אם היה NULL,
    auth.adopt_orphan_events (רץ בכל הרשמה חדשה) היה משייך את האירוע — עם כל
    המוזמנים והטלפונים שבו — לחשבון הבא שנרשם למערכת. דליפת מידע, לא רק באג.
    """
    db = _fresh_session()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    target = _make_user(db, "couple@veya.test")
    ev = _make_event(db, target.id)

    _delete_user_impl(db, admin, target, "user_only")
    db.commit()

    holder = db.scalar(select(models.User).where(models.User.email == _ORPHANED_EVENTS_HOLDER_EMAIL))
    assert holder is not None
    assert holder.disabled is True
    assert db.get(models.Event, ev.id).owner_id == holder.id
    print("✓ 2: הבעלות עברה לחשבון-מערכת נעול, לא ל-NULL (מונע דליפת מידע להרשמה הבאה)")


def test_3_user_only_holder_reused_across_deletions() -> None:
    db = _fresh_session()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    t1 = _make_user(db, "couple1@veya.test")
    t2 = _make_user(db, "couple2@veya.test")
    ev1 = _make_event(db, t1.id)
    ev2 = _make_event(db, t2.id)

    _delete_user_impl(db, admin, t1, "user_only")
    db.commit()
    _delete_user_impl(db, admin, t2, "user_only")
    db.commit()

    holders = db.scalars(
        select(models.User).where(models.User.email == _ORPHANED_EVENTS_HOLDER_EMAIL)
    ).all()
    assert len(holders) == 1
    assert db.get(models.Event, ev1.id).owner_id == holders[0].id
    assert db.get(models.Event, ev2.id).owner_id == holders[0].id
    print("✓ 3: חשבון-המערכת נוצר פעם אחת בלבד ומשותף בין כמה מחיקות")


def test_4_user_only_no_events_no_holder_created() -> None:
    db = _fresh_session()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    target = _make_user(db, "solo@veya.test")

    events_count = _delete_user_impl(db, admin, target, "user_only")
    db.commit()

    assert events_count == 0
    holder = db.scalar(select(models.User).where(models.User.email == _ORPHANED_EVENTS_HOLDER_EMAIL))
    assert holder is None
    print("✓ 4: משתמש בלי אירועים — נמחק נקי, בלי ליצור חשבון-מערכת מיותר")


def test_5_user_and_events_deletes_everything() -> None:
    db = _fresh_session()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    target = _make_user(db, "couple@veya.test")
    ev = _make_event(db, target.id)
    g = _make_guest(db, ev.id)

    events_count = _delete_user_impl(db, admin, target, "user_and_events")
    db.commit()

    assert events_count == 1
    assert db.get(models.User, target.id) is None
    assert db.get(models.Event, ev.id) is None
    assert db.get(models.Guest, g.id) is None
    print("✓ 5: 'משתמש + כל האירועים' — הכול נמחק, אין רשומות יתומות")


def test_6_user_and_events_with_invitation_does_not_break() -> None:
    """event_invitations הוא FK רגיל בלי cascode — ודא ש-delete_event_cascade
    (שעודכן לתמוך בו) לא נכשל כשיש הזמנת שיתוף פתוחה לאירוע."""
    db = _fresh_session()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    target = _make_user(db, "couple@veya.test")
    ev = _make_event(db, target.id)
    db.add(models.EventInvitation(
        event_id=ev.id, invited_email="partner@veya.test",
        invited_by=target.id, token_hash="x",
    ))
    db.commit()

    _delete_user_impl(db, admin, target, "user_and_events")
    db.commit()

    assert db.get(models.Event, ev.id) is None
    assert db.query(models.EventInvitation).count() == 0
    print("✓ 6: מחיקת אירוע עם הזמנת שיתוף פתוחה מצליחה (event_invitations מנוקה)")


def test_7_user_and_events_does_not_touch_other_users_event() -> None:
    db = _fresh_session()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    target = _make_user(db, "couple@veya.test")
    other = _make_user(db, "other@veya.test")
    ev_target = _make_event(db, target.id)
    ev_other = _make_event(db, other.id)

    _delete_user_impl(db, admin, target, "user_and_events")
    db.commit()

    assert db.get(models.Event, ev_target.id) is None
    assert db.get(models.Event, ev_other.id) is not None
    assert db.get(models.User, other.id) is not None
    print("✓ 7: מחיקת משתמש+אירועים לא פוגעת באירוע/משתמש אחר")


def test_8_cannot_delete_self() -> None:
    db = _fresh_session()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    try:
        _delete_user_impl(db, admin, admin, "user_only")
        raise AssertionError("הייתה אמורה להיזרק שגיאה")
    except HTTPException as exc:
        assert exc.status_code == 400
    db.rollback()
    assert db.get(models.User, admin.id) is not None
    print("✓ 8: לא ניתן למחוק את החשבון של עצמך")


def test_9_cannot_delete_last_admin() -> None:
    db = _fresh_session()
    only_admin = _make_user(db, "solo-admin@veya.test", is_admin=True)
    # "caller" משמש כאן רק לפרמטר admin.id של _delete_user_impl (ההרשאה
    # שהמבצע הוא בכלל אדמין נאכפת בשכבת ה-HTTP ע"י get_current_admin, לא
    # כאן) — מה שנבדק הוא שבמערכת יש אדמין יחיד בלבד (only_admin).
    caller = _make_user(db, "caller@veya.test")
    ev = _make_event(db, only_admin.id)

    try:
        _delete_user_impl(db, caller, only_admin, "user_and_events")
        raise AssertionError("הייתה אמורה להיזרק שגיאה")
    except HTTPException as exc:
        assert exc.status_code == 400
    db.rollback()
    assert db.get(models.User, only_admin.id) is not None
    assert db.get(models.Event, ev.id) is not None

    # ברגע שיש אדמין שני במערכת, מחיקת הראשון כבר לא חסומה.
    second_admin = _make_user(db, "second-admin@veya.test", is_admin=True)
    _delete_user_impl(db, second_admin, only_admin, "user_only")
    db.commit()
    assert db.get(models.User, only_admin.id) is None
    print("✓ 9: לא ניתן למחוק את האדמין האחרון במערכת (rollback מלא), אך כן עם אדמין שני")


def test_10_cannot_delete_orphaned_events_holder() -> None:
    db = _fresh_session()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    target = _make_user(db, "couple@veya.test")
    _make_event(db, target.id)
    _delete_user_impl(db, admin, target, "user_only")
    db.commit()
    holder = db.scalar(select(models.User).where(models.User.email == _ORPHANED_EVENTS_HOLDER_EMAIL))

    try:
        _delete_user_impl(db, admin, holder, "user_and_events")
        raise AssertionError("הייתה אמורה להיזרק שגיאה")
    except HTTPException as exc:
        assert exc.status_code == 400
    db.rollback()
    assert db.get(models.User, holder.id) is not None
    print("✓ 10: לא ניתן למחוק את חשבון-המערכת שמחזיק אירועים יתומים")


def test_11_invalid_mode_rejected() -> None:
    db = _fresh_session()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    target = _make_user(db, "couple@veya.test")
    try:
        _delete_user_impl(db, admin, target, "delete_everything_please")
        raise AssertionError("הייתה אמורה להיזרק שגיאה")
    except HTTPException as exc:
        assert exc.status_code == 400
    db.rollback()
    assert db.get(models.User, target.id) is not None
    print("✓ 11: מצב מחיקה לא מוכר נדחה, בלי לגעת ב-DB")


def test_12_user_level_relations_cleaned_correctly() -> None:
    db = _fresh_session()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    target = _make_user(db, "member@veya.test")
    owner = _make_user(db, "owner@veya.test")
    ev = _make_event(db, owner.id)

    # target חבר פעיל באירוע של owner (למשל הוזמן כשותף/מפיק).
    membership = models.EventMember(
        event_id=ev.id, user_id=target.id, role="planner", invited_by_id=owner.id,
    )
    db.add(membership)
    # target הזמין מישהו אחר לאירוע של owner — הגישה של האחר צריכה להישאר.
    other = _make_user(db, "planner2@veya.test")
    other_membership = models.EventMember(
        event_id=ev.id, user_id=other.id, role="planner", invited_by_id=target.id,
    )
    db.add(other_membership)
    db.add(models.ConsentRecord(user_id=target.id, consent_type="terms", document_version="v1"))
    db.add(models.EventInvitation(
        event_id=ev.id, invited_email="x@veya.test", invited_by=target.id, token_hash="h",
    ))
    db.commit()

    _delete_user_impl(db, admin, target, "user_only")
    db.commit()

    # החברות *של* target נמחקה.
    assert db.get(models.EventMember, membership.id) is None
    # החברות של האחר, שtarget רק הזמין, נשארת פעילה — רק מתנתקת מ-target.
    kept = db.get(models.EventMember, other_membership.id)
    assert kept is not None
    assert kept.invited_by_id is None
    assert kept.status == "active"
    # ConsentRecord נשאר (שקיפות/רגולציה) אבל מנותק.
    consent = db.query(models.ConsentRecord).one()
    assert consent.user_id is None
    # EventInvitation נשארת (תיעוד) אבל מנותקת.
    inv = db.query(models.EventInvitation).one()
    assert inv.invited_by is None
    # האירוע של owner לא נגע בו בכלל.
    assert db.get(models.Event, ev.id).owner_id == owner.id
    print("✓ 12: קשרי-משתמש (חברות/הזמנות/הסכמות) מנוקים נכון — לא נמחקת גישה תקינה של אחרים")


def test_13_audit_log_with_both_event_and_user_no_conflict() -> None:
    """רגרסיה לבאג שקרה בפועל בייצור: שורת audit_logs עם גם event_id (של
    אירוע בבעלות target) וגם user_id (=target) — למשל תיעוד של פעולה
    שtarget ביצע על האירוע שלו עצמו. במצב user_and_events, delete_event_cascade
    מוחק אותה שורה בדיוק (לפי event_id), ואם הלולאה שמאפסת AuditLog.user_id
    (_delete_user_impl) הייתה נוגעת בה שוב — היה מתרחש UPDATE על שורה
    שכבר מסומנת/נמחקה, וה-flush היה נכשל עם StaleDataError
    ("UPDATE statement on table 'audit_logs' expected to update 1 row(s);
    0 were matched") → PendingRollbackError ב-commit, כפי שקרה בפועל.

    משתמשים ב-``_fresh_session_no_autoflush`` (לא ``_fresh_session``) כי
    הבאג תלוי סדר-flush: עם autoflush=True (ברירת המחדל של Session רגיל)
    ה-SELECT השני היה מחיל את המחיקה הממתינה קודם ו"מסתיר" את הבאג.
    """
    db = _fresh_session_no_autoflush()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    target = _make_user(db, "couple@veya.test")
    ev = _make_event(db, target.id)
    db.add(models.AuditLog(
        event_id=ev.id, user_id=target.id,
        action="update_event", detail="עדכון פרטי אירוע",
    ))
    db.commit()

    # לפני התיקון: השורה הבאה זרקה PendingRollbackError.
    _delete_user_impl(db, admin, target, "user_and_events")
    db.commit()

    assert db.get(models.User, target.id) is None
    assert db.get(models.Event, ev.id) is None
    # השורה נמחקה (יחד עם האירוע) — לא נשארה עם user_id=None כ"יתומה".
    assert db.query(models.AuditLog).count() == 0
    print("✓ 13: audit_logs עם event_id+user_id יחד — נמחק אחת, בלי התנגשות flush")


def test_14_already_deleted_target_reports_404_not_crash() -> None:
    """נעילת שורת המשתמש (with_for_update, ראו admin.py:_delete_user_impl)
    שולפת אותה מחדש בתחילת הפונקציה. אם מישהו אחר כבר מחק את אותו משתמש
    בדיוק (לדוגמה שתי בקשות מחיקה מקבילות) — היא לא אמורה למצוא שורה, ואז
    הפונקציה חייבת לדווח 404 נקי ולא להמשיך ולנסות לנקות/למחוק משתמש
    שכבר לא קיים (SQLite לא אוכף נעילות ברמת שורה בעצמו, אבל הענף הזה —
    'לא נמצאה שורה' — בדיוק אותה התנהגות שReal race על Postgres מייצר,
    ובמכוון ניתן לבדיקה בלי Postgres אמיתי)."""
    db = _fresh_session_no_autoflush()
    admin = _make_user(db, "admin@veya.test", is_admin=True)
    target = _make_user(db, "couple@veya.test")
    target_id = target.id

    # מדמים "בקשה אחרת שכבר מחקה אותו" ע"י מחיקה ישירה מה-DB, בלי לעדכן את
    # אובייקט ה-Python של target שעדיין מוחזק (בדיוק כמו שהיה קורה אם
    # session אחר עשה commit על מחיקה בין הרגע שtarget נטען כאן לרגע
    # שהפונקציה מנסה לנעול אותו).
    db.execute(delete(models.User).where(models.User.id == target_id))
    db.commit()

    try:
        _delete_user_impl(db, admin, target, "user_and_events")
        raise AssertionError("הייתה אמורה להיזרק שגיאת 404")
    except HTTPException as exc:
        assert exc.status_code == 404
    db.rollback()
    print("✓ 14: משתמש שכבר נמחק ע\"י בקשה אחרת מדווח 404 נקי, לא קורס")


if __name__ == "__main__":
    test_1_user_only_keeps_event_and_guests_intact()
    test_2_user_only_owner_becomes_holder_not_null()
    test_3_user_only_holder_reused_across_deletions()
    test_4_user_only_no_events_no_holder_created()
    test_5_user_and_events_deletes_everything()
    test_6_user_and_events_with_invitation_does_not_break()
    test_7_user_and_events_does_not_touch_other_users_event()
    test_8_cannot_delete_self()
    test_9_cannot_delete_last_admin()
    test_10_cannot_delete_orphaned_events_holder()
    test_11_invalid_mode_rejected()
    test_12_user_level_relations_cleaned_correctly()
    test_13_audit_log_with_both_event_and_user_no_conflict()
    test_14_already_deleted_target_reports_404_not_crash()
    print()
    print("=== כל 14 תרחישי מחיקת משתמש (אדמין) עברו ===")
