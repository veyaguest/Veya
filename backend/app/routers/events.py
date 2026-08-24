"""Router לניהול אירועים של המשתמש (שלב 8): רשימה, יצירה, מחיקה.

**אירוע אחד למשתמש.** לזוג יש אירוע אחד שהוא מנהל — בבעלותו, או כבן/בת זוג
שהצטרפו לאירוע קיים. ניסיון ליצור אירוע שני נחסם כאן (409). מי שרוצה לנהל
את האירוע יחד עם בן/בת הזוג לא יוצר אירוע נוסף אלא מוזמן לאותו אירוע —
ראו ``app/partners.py`` ו-``app/routers/partner.py``.

מפיק/אולם הם סיפור אחר: אין להם אירוע בבעלות, והם רואים אירועים ששותפו
איתם כחברי-אירוע. הרשימה כאן משרתת גם אותם.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import auth as auth_module
from app import communication, models, partners, schemas
from app.account import delete_event_cascade
from app.auth import get_current_owner
from app.database import IS_POSTGRES, get_db

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[schemas.EventSummary])
def list_events(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_owner),
):
    """אירועים בבעלות המשתמש + אירועים ששותפו איתו כחבר-אירוע פעיל, מהחדש לישן."""
    owned = set(
        db.scalars(
            select(models.Event.id).where(models.Event.owner_id == user.id)
        ).all()
    )
    shared = set(
        db.scalars(
            select(models.EventMember.event_id).where(
                models.EventMember.user_id == user.id,
                models.EventMember.status == "active",
            )
        ).all()
    )
    event_ids = owned | shared
    if not event_ids:
        return []
    return db.scalars(
        select(models.Event)
        .where(models.Event.id.in_(event_ids))
        .order_by(models.Event.id.desc())
    ).all()


@router.post("", response_model=schemas.EventSummary, status_code=201)
def create_event(
    payload: schemas.EventCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_owner),
):
    """יוצר אירוע חדש בבעלות המשתמש — אחד בלבד, ורק לחשבון שהושלם ואומת.

    שלוש הבדיקות שלפני היצירה, לפי הסדר:
    1. **אירוע אחד למשתמש** — אם המשתמש כבר מנהל אירוע (בבעלות או כבן/בת
       זוג), אין ליצור עוד אחד.
    2. **פרטים מלאים** — שם מלא וטלפון תקין. משתמשים ותיקים שנרשמו לפני
       שהשדות האלה היו חובה לא נשברים: הם מתבקשים להשלים פרטים כאן.
    3. **מייל מאומת** — כדי שנוכל להגיע לזוג, ושמי שהזמינו אותו יידע שהוא
       אכן בעל הכתובת.

    ב-Postgres דרך app_create_event (SECURITY DEFINER): INSERT ...RETURNING
    (ברירת המחדל של SQLAlchemy) דורש שהשורה תעבור גם את events_select, לא
    רק את ה-WITH CHECK של events_insert — עוקפים זאת כמו בשאר מקומות ה-
    INSERT הרגישים (ראו app/auth.py::register_user_row להסבר המלא).
    """
    existing = partners.my_event(db, user)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="כבר יש לך אירוע. אפשר לנהל אירוע אחד בכל חשבון",
        )
    if not auth_module.profile_complete(user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="לפני שיוצרים אירוע צריך להשלים שם מלא ומספר טלפון",
        )
    if not auth_module.is_email_verified(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="צריך לאמת את כתובת המייל לפני יצירת האירוע",
        )

    if IS_POSTGRES:
        row = db.execute(
            text("SELECT * FROM app_create_event(:owner_id, :event_type, :groom_name, :bride_name, :venue_name)"),
            {
                "owner_id": user.id, "event_type": payload.event_type,
                "groom_name": payload.groom_name.strip(),
                "bride_name": payload.bride_name.strip(),
                "venue_name": payload.venue_name.strip(),
            },
        ).mappings().first()
        db.commit()
        # app_create_event עושה RETURNING * — כלומר השורה כוללת כל עמודה
        # שקיימת היום בפועל בטבלת events ב-DB, גם אם היא נוספה ישירות ל-DB
        # ועדיין לא קיימת במודל ה-ORM כאן (כפי שקרה בפועל: עמודה event_subtype
        # שגרמה ל-TypeError בקונסטרוקטור וקרסה את הבקשה **אחרי** שהשורה כבר
        # נשמרה ב-commit למעלה). מסננים לפי מה שה-ORM באמת ממפה, כדי שפער
        # עתידי בין סכימת ה-DB בפועל למודל לא יפיל את הבקשה שוב.
        known_columns = {c.name for c in models.Event.__table__.columns}
        event = models.Event(**{k: v for k, v in dict(row).items() if k in known_columns})
    else:
        event = models.Event(
            owner_id=user.id,
            event_type=payload.event_type,
            groom_name=payload.groom_name.strip(),
            bride_name=payload.bride_name.strip(),
            venue_name=payload.venue_name.strip(),
        )
        db.add(event)
        db.commit()

    # מקצה אוטומטית את רצף "תקשורת עם אורחים" (6 ההודעות) לפי סוג האירוע.
    communication.provision_event_messages(db, event)
    db.commit()
    return event


@router.delete("/{event_id}", status_code=204)
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_owner),
):
    """מוחק אירוע (רק אם הוא בבעלות המשתמש) — כולל כל המוזמנים שלו."""
    event = db.get(models.Event, event_id)
    if event is None or event.owner_id != user.id:
        raise HTTPException(status_code=404, detail="האירוע לא נמצא")
    delete_event_cascade(db, event)
    db.commit()
