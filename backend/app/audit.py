"""עזר קטן לכתיבת רשומות ליומן האבטחה (audit log).

מטרה: לתעד פעולות רגישות (שליחת הודעות, עדכון פרטי אירוע, גישה לקישור אישי,
ניסיונות גישה חריגים) כדי לאפשר מעקב ואיתור חריגות — בלי לשמור מידע רגיש.
"""
from typing import Optional

from sqlalchemy.orm import Session

from app import models


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
    """
    try:
        db.add(models.AuditLog(
            event_id=event_id,
            user_id=user_id,
            action=action,
            detail=detail[:500],
            ip=ip,
        ))
    except Exception:
        pass
