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
    (הודעות, הבהרות, יומן אבטחה, חוקי אוטומציה, תבניות הודעה, חברי-אירוע)
    אין להן ON DELETE CASCADE ברמת ה-DB, ולכן דורשות ניקוי ידני מפורש —
    אחרת הן נשארות "מידע יתום" (או גורמות לשגיאת foreign-key ב-Postgres).
    """
    event_id = event.id
    for msg in db.scalars(
        select(models.Message).where(models.Message.event_id == event_id)
    ).all():
        db.delete(msg)
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
    db.delete(event)
