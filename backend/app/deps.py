"""Dependencies משותפים ל-routers."""
from typing import Optional, Union

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
    עובר. (3) ``owner_only=True`` — אף חבר-אירוע לא עובר, בלי קשר להרשאות
    (למשל עריכת פרטי הליבה של האירוע — שם/תאריך/סוג — נשארת רק לבעלים).
    (4) חבר-אירוע פעיל (``EventMember`` עם ``status='active'``) — עובר רק אם
    ``permission`` לא התבקש, או שיש חפיפה בינו לבין רשימת ההרשאות שלו. אחרת
    404 (לא חושפים למשתמש שאירוע כלשהו קיים) או 403 (האירוע קיים אך חסרה
    הרשאה).

    ``permission`` יכול להיות מחרוזת בודדת, או רשימה — ואז מספיקה הרשאה
    *אחת* מתוכה (בדיוק הסמנטיקה של ``app_has_any_event_permission`` ב-RLS,
    ראו ``backend/rls/01_helpers_and_grants.sql``). כשבודקים כמה endpoint-ים
    צריכים אותה קבוצת הרשאות, יש להשתמש בקבועים מ-``app/permissions.py`` —
    לא לכתוב רשימות מפוזרות ב-routers, כדי שה-API וה-RLS לא יסטו זה מזה.

    שימוש: ``Depends(EventAccess())`` לגישה בסיסית — זהה ל-``get_current_event``
    ההיסטורי. ``Depends(EventAccess(permissions.GUESTS_WRITE))`` כשנדרשת
    הרשאה ספציפית.
    """

    def __init__(
        self,
        permission: Optional[Union[str, list[str]]] = None,
        owner_only: bool = False,
    ) -> None:
        self.permission = permission
        self.owner_only = owner_only

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
            if self.owner_only:
                # פעולה ששמורה לבעלים/אדמין בלבד — חבר-אירוע לא עובר, בלי
                # קשר לאילו הרשאות הוענקו לו (למשל שינוי שם בני הזוג/תאריך).
                raise not_found
            member = db.scalars(
                select(models.EventMember).where(
                    models.EventMember.event_id == event.id,
                    models.EventMember.user_id == user.id,
                    models.EventMember.status == "active",
                )
            ).first()
            if member is None:
                raise not_found
            if self.permission:
                required = (
                    [self.permission] if isinstance(self.permission, str)
                    else self.permission
                )
                granted = set(member.permissions or [])
                if not granted.intersection(required):
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
