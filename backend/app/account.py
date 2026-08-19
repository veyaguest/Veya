"""ניקוי מידע בעת מחיקת אירוע/חשבון — משותף בין routers/events.py (מחיקת
אירוע בודד) לבין routers/auth.py (מחיקת חשבון מלאה, שמוחקת את כל האירועים
של המשתמש). מרוכז כאן כדי שלא לשכפל את לוגיקת ה-cascade בשני מקומות.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models


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
    db.delete(event)
