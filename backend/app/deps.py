"""Dependencies משותפים ל-routers."""
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_user
from app.database import get_db


def get_default_event(db: Session = Depends(get_db)) -> models.Event:
    """מחזיר אירוע ברירת-מחדל (משמש רק באתחול המערכת / תאימות לאחור)."""
    event = db.scalars(select(models.Event)).first()
    if event is None:
        event = models.Event()
        db.add(event)
        db.commit()
        db.refresh(event)
    return event


class EventAccess:
    """דיפנדנסי גישה לאירוע — עם בדיקת הרשאה אופציונלית לחברי-אירוע.

    סדר הבדיקה: (1) בעלים — תמיד עובר. (2) אדמין-על (``is_admin``) — תמיד
    עובר. (3) חבר-אירוע פעיל (``EventMember`` עם ``status='active'``) — עובר
    רק אם ``permission`` לא התבקש, או שהוא מופיע ברשימת ההרשאות שלו. אחרת 404
    (לא חושפים למשתמש שאירוע כלשהו קיים) או 403 (האירוע קיים אך חסרה הרשאה).

    שימוש: ``Depends(EventAccess())`` לגישה בסיסית — זהה ל-``get_current_event``
    ההיסטורי. ``Depends(EventAccess("view_guests"))`` כשנדרשת הרשאה ספציפית
    (ישמש routers בשלב 3, כשתהיה דרך בפועל ליצור חברי-אירוע).
    """

    def __init__(self, permission: Optional[str] = None) -> None:
        self.permission = permission

    def __call__(
        self,
        x_event_id: Optional[int] = Header(default=None, alias="X-Event-Id"),
        user: models.User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> models.Event:
        not_found = HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="האירוע לא נמצא"
        )

        if x_event_id is not None:
            event = db.get(models.Event, x_event_id)
            if event is None:
                raise not_found
            if event.owner_id == user.id or user.is_admin:
                return event
            member = db.scalars(
                select(models.EventMember).where(
                    models.EventMember.event_id == event.id,
                    models.EventMember.user_id == user.id,
                    models.EventMember.status == "active",
                )
            ).first()
            if member is None:
                raise not_found
            if self.permission and self.permission not in (member.permissions or []):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="אין לך הרשאה לפעולה הזו",
                )
            return event

        # בלי כותרת אירוע: ברירת המחדל היא האירוע הראשון בבעלות המשתמש
        # (נוחות לזוג עם אירוע יחיד). למפיק/אולם אין אירוע בבעלות — הם
        # יידרשו לבחור אירוע מפורש דרך X-Event-Id, כמו שהפרונט כבר עושה
        # היום לכל אירוע פרט לראשון (ראו EventControls / App.tsx).
        event = db.scalars(
            select(models.Event)
            .where(models.Event.owner_id == user.id)
            .order_by(models.Event.id)
        ).first()
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="עדיין לא יצרת אירוע",
            )
        return event


# תאימות לאחור: כל ה-routers הקיימים משתמשים ב-Depends(get_current_event) —
# זה כינוי לגישה בסיסית (בלי דרישת הרשאה ספציפית), אותה התנהגות כמו קודם.
get_current_event = EventAccess()
