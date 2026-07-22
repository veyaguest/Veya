"""עזר קטן לכתיבת רשומות ליומן האבטחה (audit log).

מטרה: לתעד פעולות רגישות (שליחת הודעות, עדכון פרטי אירוע, גישה לקישור אישי,
ניסיונות גישה חריגים) כדי לאפשר מעקב ואיתור חריגות — בלי לשמור מידע רגיש.
"""
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models
from app.database import IS_POSTGRES


def record(
    db: Session,
    action: str,
    *,
    event_id: Optional[int] = None,
    user_id: Optional[int] = None,
    detail: str = "",
    ip: Optional[str] = None,
) -> None:
    """מוסיף שורת יומן. אינו מבצע commit — הקורא אחראי לכך יחד עם שאר העבודה.

    לעולם לא מפיל את הבקשה: אם הכתיבה נכשלת, מתעלמים (היומן משני לפעולה עצמה).

    ב-Postgres תמיד דרך ``app_record_audit_log`` (SECURITY DEFINER), לא
    ORM ישיר: audit.record נקרא גם מנתיבים ציבוריים/אנונימיים לגמרי (למשל
    confirm.py לפני שידוע מוזמן/אירוע כלשהו) — ובלי זהות שעוברת את מדיניות
    audit_logs_select, ה-INSERT (שמשתמש ב-RETURNING כברירת מחדל ב-SQLAlchemy)
    היה נדחה ע"י RLS גם כש-audit_logs_insert עצמה פתוחה לגמרי. התגלה בבדיקת
    Staging אמיתית מול Postgres.
    """
    try:
        if IS_POSTGRES:
            db.execute(
                text("SELECT app_record_audit_log(:action, :event_id, :user_id, :detail, :ip)"),
                {
                    "action": action, "event_id": event_id, "user_id": user_id,
                    "detail": detail[:500], "ip": ip,
                },
            )
            return
        db.add(models.AuditLog(
            event_id=event_id,
            user_id=user_id,
            action=action,
            detail=detail[:500],
            ip=ip,
        ))
    except Exception:
        pass
