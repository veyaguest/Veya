"""ניקוי מידע בעת מחיקת אירוע/חשבון — משותף בין routers/events.py (מחיקת
אירוע בודד) לבין routers/auth.py (מחיקת חשבון מלאה, שמוחקת את כל האירועים
של המשתמש). מרוכז כאן כדי שלא לשכפל את לוגיקת ה-cascade בשני מקומות.
"""
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import models
from app.database import IS_POSTGRES

# האם במסד קיימות הפונקציות המבוקרות של ``rls/30_finance_ledger_rls.sql``.
# נבדק פעם אחת לתהליך. בייצור הקובץ מוחל רק יחד עם שאר קובצי ה-RLS (ראו
# main.py::_ensure_rls_policies); כל עוד לא הוחל, אין RLS על טבלאות המתנות
# והמחיקה הישירה (למטה) עובדת — כך שהקוד נכון בשני המצבים.
_LEDGER_FUNCTIONS: dict = {}


def _has_db_function(db: Session, name: str) -> bool:
    if not IS_POSTGRES:
        return False
    if name not in _LEDGER_FUNCTIONS:
        _LEDGER_FUNCTIONS[name] = bool(db.execute(text(
            "SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.proname = :n"
        ), {"n": name}).first())
    return _LEDGER_FUNCTIONS[name]


def archive_event_finance(db: Session, event_id: int) -> None:
    """לפני מחיקת אירוע: מתנות ורכישות מסלול עוברות לרישום חשבונאי בלי פרטים
    אישיים (``GiftLedger`` / ``EntitlementLedger``), ונמחקות מהטבלאות שלהן.

    החלטת המייסד 2026-10-28. ב-Postgres עם RLS טבלת ``gifts`` חסומה לכתיבה
    ישירה לגמרי, ולכן שם זה רץ דרך הפונקציה המבוקרת ``app_archive_event_finance``
    (בודקת שהמבקש מנהל את האירוע או אדמין). בלי commit.
    """
    if _has_db_function(db, "app_archive_event_finance"):
        db.execute(text("SELECT app_archive_event_finance(:e)"), {"e": event_id})
        return
    now = datetime.utcnow()
    for g in db.scalars(select(models.Gift).where(models.Gift.event_id == event_id)).all():
        db.add(models.GiftLedger(
            original_gift_id=g.id, event_ref=event_id, gift_amount_agorot=g.gift_amount_agorot,
            fee_agorot=g.fee_agorot, total_agorot=g.total_agorot, currency=g.currency, status=g.status,
            provider=g.provider, provider_transaction_id=g.provider_transaction_id,
            gift_created_at=g.created_at, gift_updated_at=g.updated_at, archived_at=now,
        ))
        db.delete(g)
    for e in db.scalars(
        select(models.EventEntitlement).where(models.EventEntitlement.event_id == event_id)
    ).all():
        db.add(models.EntitlementLedger(
            original_entitlement_id=e.id, event_ref=event_id, plan_version_id=e.plan_version_id,
            status=e.status, price_agorot=e.price_agorot, addons=e.addons, coupon_code=e.coupon_code,
            source=e.source, starts_on=e.starts_on, trial_ends_on=e.trial_ends_on, renews_on=e.renews_on,
            cancelled_at=e.cancelled_at, entitlement_created_at=e.created_at, archived_at=now,
        ))
        db.delete(e)
    db.flush()


def _delete_event_money_rows(db: Session, event_id: int) -> None:
    """הנתונים הכספיים הפרטיים של בעלי האירוע — נמחקים איתו (לא נשמרים):
    מעטפות שנספרו, הוצאות ותשלומיהן, ופרטי חשבון הבנק לקבלת המתנות.

    לחלקן יש ON DELETE CASCADE ברמת ה-FK, אבל נמחקות כאן במפורש מאותה סיבה
    שכל השאר נמחק כאן (ראו ההערה ב-``delete_event_cascade``). תשלומים לפני
    הוצאות (מפתח זר), והכול לפני המוזמנים (מעטפה מצביעה על מוזמן).
    """
    for row in db.scalars(
        select(models.ExpensePayment).where(models.ExpensePayment.event_id == event_id)
    ).all():
        db.delete(row)
    db.flush()
    for model in (models.EventExpense, models.GiftEnvelope, models.PayoutAccount):
        for row in db.scalars(select(model).where(model.event_id == event_id)).all():
            db.delete(row)
    db.flush()


def detach_user_finance(db: Session, user_id: int) -> None:
    """לפני מחיקת משתמש: מעטפות ותשלומי הוצאה שהוא רשם (גם באירוע של
    בן/בת הזוג, שנשאר) — נשארים, רק מתנתקים ממנו. בלי זה מחיקת החשבון
    נכשלת על מפתח זר. בלי commit.
    """
    for row in db.scalars(
        select(models.GiftEnvelope).where(models.GiftEnvelope.recorded_by_user_id == user_id)
    ).all():
        row.recorded_by_user_id = None
    for row in db.scalars(
        select(models.ExpensePayment).where(models.ExpensePayment.recorded_by_user_id == user_id)
    ).all():
        row.recorded_by_user_id = None


def delete_event_cascade(db: Session, event: "models.Event") -> None:
    """מוחק אירוע וכל הרשומות התלויות בו שאין להן cascade אוטומטי ב-DB.

    ``guests`` נמחקים ע"י ה-relationship cascade של SQLAlchemy (ראו
    ``Event.guests`` ב-models.py) — לא נוגעים בהם כאן. שאר הטבלאות התלויות
    (הודעות, רצף "תקשורת עם אורחים", הבהרות, יומן אבטחה, חוקי אוטומציה,
    תבניות הודעה, חברי-אירוע) אין להן ON DELETE CASCADE ברמת ה-DB, ולכן
    דורשות ניקוי ידני מפורש — אחרת הן נשארות "מידע יתום" (או גורמות לשגיאת
    foreign-key גם ב-SQLite וגם ב-Postgres, כמו שקרה בפועל עם event_messages
    לפני שהתווסף לכאן: כל אירוע שהופעל בו מסלול אישורי הגעה יצר שורות
    event_messages, וללא הניקוי הזה מחיקת האירוע/החשבון נכשלה).

    כל המחיקות כאן פועלות בתוך הטרנזקציה של הקורא (אין ``db.commit()``
    בפונקציה הזו) — אם שלב כלשהו נכשל, שום דבר לא נשמר: ``get_db`` (ראו
    database.py) סוגר את ה-session ללא commit, וה-DB מבטל את כל הטרנזקציה
    הפתוחה. לא נשאר מצב "חצי מחוק".

    שים לב: זו מחיקת הרשומה שלנו ב-DB בלבד. אין כאן (ולא צריכה להיות) שום
    קריאה לספק WhatsApp כדי "לבטל" הודעה שכבר נשלחה בפועל — Meta לא חושפת
    פעולה כזו, וגם אם הייתה חושפת, מחיקת האירוע אצלנו לא אמורה לגעת בהודעה
    שכבר הגיעה למכשיר של מוזמן.
    """
    event_id = event.id
    # יומן השיחות (Call Center) — קודם כול: הוא מצביע גם על guests, שנמחקים
    # בסוף דרך ה-relationship cascade של Event.guests.
    for call in db.scalars(
        select(models.CallLog).where(models.CallLog.event_id == event_id)
    ).all():
        db.delete(call)
    # משימות השיחה ושליטת הסבבים (מרכז הטלפנים) — מצביעות על guests ו-events.
    from app import call_ops

    call_ops.delete_for_event(db, event_id)
    # כסף: מתנות ורכישות מסלול → רישום חשבונאי בלי פרטים אישיים; נתוני הכסף
    # הפרטיים של בעלי האירוע → נמחקים. לפני המוזמנים — מתנה ומעטפה מצביעות
    # על מוזמן (החלטת המייסד 2026-10-28; לפני כן מחיקת אירוע עם מתנה נכשלה).
    archive_event_finance(db, event_id)
    _delete_event_money_rows(db, event_id)
    # הקצאות הטלפנים לאירוע — נמחקות איתו (אין אירוע, אין למי להתקשר).
    for assignment in db.scalars(
        select(models.CallAssignment).where(models.CallAssignment.event_id == event_id)
    ).all():
        db.delete(assignment)
    for msg in db.scalars(
        select(models.Message).where(models.Message.event_id == event_id)
    ).all():
        db.delete(msg)
    # flush מפורש: Message.event_message_id הוא FK רגיל (בלי relationship()
    # ל-EventMessage), ולכן ה-unit-of-work של SQLAlchemy לא בהכרח מזהה את
    # תלות ה-FK בין שתי המחיקות ועלול לשלוח את ה-DELETE-ים בסדר ההפוך (נבדק
    # בפועל: בלי ה-flush הזה, DELETE FROM event_messages רץ *לפני* שה-
    # messages שמצביעות אליו נמחקו, ונכשל עם FOREIGN KEY constraint failed).
    # flush (לא commit) — עדיין באותה טרנזקציה, עדיין מתבטל כולו יחד אם
    # שלב מאוחר יותר נכשל.
    db.flush()
    # event_messages (רצף "תקשורת עם אורחים") — נמחק אחרי messages בכוונה:
    # Message.event_message_id מצביע לכאן, אז ה-children (ההודעות שנשלחו
    # בפועל) חייבים להיעלם קודם. זו הרשומה שהייתה חסרה כאן עד עכשיו וגרמה
    # ל-IntegrityError במחיקת אירוע/חשבון ברגע שכבר הופעל מסלול אישורי הגעה
    # (provision_event_messages יוצר שורות event_messages בהפעלה הראשונה).
    for event_msg in db.scalars(
        select(models.EventMessage).where(models.EventMessage.event_id == event_id)
    ).all():
        db.delete(event_msg)
    # flush מפורש נוסף: Event אין לו relationship() ל-EventMessage (בדיוק כמו
    # Message->EventMessage למעלה) — ה-unit-of-work לא מובטח באופן פורמלי
    # לשמור על הסדר בין שני mapper-ים בלי תלות מפורשת, אז הופך אותו כאן
    # לוודאי במקום מוסתר. הערה לגבי מה זה כן/לא מוכיח: הסרתי את השורה הזו
    # זמנית והרצתי את tests/test_account_delete.py (כולל test_15, שמבודד
    # event_messages בלי אף Message) — כל הבדיקות עברו גם בלעדיה. כלומר סדר
    # ה-DELETE ב-SQLite כבר תקין גם בלי ה-flush הזה, ובדיקות ה-SQLite כאן
    # *לא* מסוגלות להוכיח שזה תיקן את שגיאת הפרודקשן האמיתית (ForeignKeyViolation
    # על event_messages_event_id_fkey, admin.py::delete_single_event #23) —
    # RLS הוא no-op לגמרי ב-SQLite, וזו הסיבה הסבירה ביותר לשגיאה עצמה (ראו
    # rls/11_event_messages_delete_rls_fix.sql). נשאר כאן כהקשחה מפורשת
    # וזולה, לא כ"התיקון המוכח".
    db.flush()
    for clar in db.scalars(
        select(models.Clarification).where(models.Clarification.event_id == event_id)
    ).all():
        db.delete(clar)
    for log in db.scalars(
        select(models.AuditLog).where(models.AuditLog.event_id == event_id)
    ).all():
        db.delete(log)
    for rule in db.scalars(
        select(models.AutomationRule).where(models.AutomationRule.event_id == event_id)
    ).all():
        db.delete(rule)
    for tmpl in db.scalars(
        select(models.MessageTemplate).where(models.MessageTemplate.event_id == event_id)
    ).all():
        db.delete(tmpl)
    for member in db.scalars(
        select(models.EventMember).where(models.EventMember.event_id == event_id)
    ).all():
        db.delete(member)
    # הזמנות שיתוף-אירוע (event_invitations, שלב "מנהלים ביחד") — לא היו כאן
    # עד עכשיו כי הטבלה נוספה אחרי delete_event_cascade. FK רגיל בלי cascade,
    # אותה בעיה בדיוק כמו event_messages בזמנו: בלי הניקוי הזה, מחיקת אירוע
    # שנשלחה בו הזמנת שיתוף נכשלת עם IntegrityError.
    for invite in db.scalars(
        select(models.EventInvitation).where(models.EventInvitation.event_id == event_id)
    ).all():
        db.delete(invite)
    # ---- נוהל דחייה ----
    # שלוש הטבלאות מוגדרות עם ON DELETE CASCADE ברמת ה-FK, אבל הן נמחקות
    # כאן במפורש מאותה סיבה שכל השאר נמחק כאן: ההסתמכות על cascade ברמת ה-DB
    # שברירה (SQLite אוכף FK רק כש-PRAGMA foreign_keys דלוק), והקובץ הזה הוא
    # המקום היחיד שיודע מה נמחק יחד עם אירוע.
    #
    # ``guest_cycle_rsvp`` ראשון: הוא מצביע גם על ``guests``, שנמחקים בסוף
    # דרך ה-relationship cascade של ``Event.guests``.
    for row in db.scalars(
        select(models.GuestCycleRsvp).where(models.GuestCycleRsvp.event_id == event_id)
    ).all():
        db.delete(row)
    db.flush()
    for row in db.scalars(
        select(models.EventCycle).where(models.EventCycle.event_id == event_id)
    ).all():
        db.delete(row)
    for row in db.scalars(
        select(models.PostponementRequest)
        .where(models.PostponementRequest.event_id == event_id)
    ).all():
        db.delete(row)
    # פניות לצוות VEYA על האירוע (עזרה, שלב 7) — אין אירוע, אין על מה לענות.
    for row in db.scalars(
        select(models.SupportRequest).where(models.SupportRequest.event_id == event_id)
    ).all():
        _delete_support_replies(db, row.id)
        db.delete(row)
    db.delete(event)


def _delete_support_replies(db: Session, request_id: int) -> None:
    """תשובות הצוות לפנייה — נמחקות יחד איתה (לפניה, בגלל המפתח הזר)."""
    for reply in db.scalars(
        select(models.SupportReply).where(models.SupportReply.request_id == request_id)
    ).all():
        db.delete(reply)
    db.flush()


def delete_support_requests_for_user(db: Session, user_id: int) -> None:
    """לפני מחיקת משתמש: הפניות **שלו** לצוות נמחקות (מידע אישי שלו), יחד עם
    תשובות הצוות אליהן. פניות שהוא טיפל בהן / תשובות שהוא שלח כאיש צוות
    נשארות — רק מנותקות ממנו. בלי commit.
    """
    for row in db.scalars(
        select(models.SupportRequest).where(models.SupportRequest.user_id == user_id)
    ).all():
        _delete_support_replies(db, row.id)
        db.delete(row)
    for row in db.scalars(
        select(models.SupportRequest).where(models.SupportRequest.handled_by_id == user_id)
    ).all():
        row.handled_by_id = None
    for reply in db.scalars(
        select(models.SupportReply).where(models.SupportReply.admin_id == user_id)
    ).all():
        reply.admin_id = None
    # אותו עיקרון בתיבת ה-WhatsApp: השיחות שלו נמחקות, מה שטיפל בו מנותק.
    from app import whatsapp_inbox

    whatsapp_inbox.delete_for_user(db, user_id)
