"""Router לפאנל האדמין (הבעלים) — שלב 8.

מאפשר לבעלים (משתמש עם ``is_admin``) לראות את *כל* המשתמשים ו*כל* האירועים
במערכת, כולל ספירת מוזמנים לכל אחד. מוגן ב-``get_current_admin`` — משתמש רגיל
יקבל 403.
"""
import secrets
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import (
    audit, auth, cache, call_center, communication, event_terms, messaging, models, roles,
    schemas, venues,
)
from app.account import delete_event_cascade
from app.auth import get_current_admin
from app.database import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


def _parse_event_date(value: str) -> Optional[date]:
    """מנסה לפרש 'YYYY-MM-DD'; מחזיר None אם ריק/לא תקין (לא מפיל את הבקשה)."""
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


@router.get("/dashboard", response_model=schemas.AdminDashboard)
def admin_dashboard(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """סקירת מערכת ללוח הבקרה של האדמין — מונים אמיתיים, אירועים אחרונים,
    גרף הרשמות לפי יום, והתראות נגזרות. נתונים בלבד; שום פעולה משנה.
    """
    today = date.today()
    today_str = today.isoformat()

    total_events = db.scalar(select(func.count(models.Event.id))) or 0
    total_users = db.scalar(select(func.count(models.User.id))) or 0
    total_venues = db.scalar(select(func.count(models.Venue.id))) or 0
    total_guests = db.scalar(select(func.count(models.Guest.id))) or 0
    whatsapp_sent = (
        db.scalar(
            select(func.count(models.Message.id)).where(
                models.Message.direction == "outbound",
                models.Message.channel == "whatsapp",
            )
        )
        or 0
    )
    # אירועים עתידיים — תאריך לא ריק וגדול/שווה להיום (השוואת מחרוזות ISO תקינה).
    upcoming_events = (
        db.scalar(
            select(func.count(models.Event.id)).where(
                models.Event.event_date >= today_str,
                models.Event.event_date != "",
            )
        )
        or 0
    )

    # --- האירועים האחרונים (8) עם בעלים וספירת מוזמנים ---
    # שלב 2: קודם שולפים את 8 האירועים, ורק אז את ספירת המוזמנים/המיילים
    # *עבורם בלבד* — לפני זה זה היה סורק את כל טבלת guests ואת כל טבלת users
    # במערכת כדי להציג בסוף רק 8 שורות. אותה תוצאה, הרבה פחות דאטה שנטען.
    recent = db.scalars(
        select(models.Event).order_by(models.Event.id.desc()).limit(8)
    ).all()
    recent_ids = [e.id for e in recent]
    recent_owner_ids = {e.owner_id for e in recent if e.owner_id}
    guests_by_event = dict(
        db.execute(
            select(models.Guest.event_id, func.count(models.Guest.id))
            .where(models.Guest.event_id.in_(recent_ids))
            .group_by(models.Guest.event_id)
        ).all()
    ) if recent_ids else {}
    emails = {
        u.id: u.email
        for u in db.scalars(
            select(models.User).where(models.User.id.in_(recent_owner_ids))
        ).all()
    } if recent_owner_ids else {}
    recent_events = []
    for e in recent:
        couple = event_terms.hosts_names(e.event_type, e.groom_name, e.bride_name)
        ed = _parse_event_date(e.event_date)
        days_until = (ed - today).days if ed and ed >= today else None
        recent_events.append(
            schemas.AdminDashboardEvent(
                id=e.id,
                event_type=e.event_type,
                couple=couple,
                venue_name=e.venue_name or "",
                owner_email=emails.get(e.owner_id) if e.owner_id else None,
                event_date=e.event_date or "",
                guests_count=guests_by_event.get(e.id, 0),
                days_until=days_until,
            )
        )

    # --- פילוח אירועים לפי event_type — לסטטיסטיקות/דוחות באדמין ---
    type_counts = dict(
        db.execute(
            select(models.Event.event_type, func.count(models.Event.id)).group_by(
                models.Event.event_type
            )
        ).all()
    )
    events_by_type = [
        schemas.AdminEventTypeCount(
            event_type=et, label=event_terms.get_event_terms(et).label, count=count
        )
        for et, count in sorted(type_counts.items(), key=lambda kv: -kv[1])
    ]

    # --- גרף הרשמות ל-14 הימים האחרונים ---
    window_days = 14
    start = today - timedelta(days=window_days - 1)
    counts: dict[date, int] = {}
    # שלב 2: שולפים רק את עמודת created_at (לא את כל השורה — email/password וכו')
    # כי זה כל מה שנחוץ פה; אותה ספירה בדיוק, פחות דאטה מועבר מה-DB.
    signup_dates = db.scalars(
        select(models.User.created_at).where(
            models.User.created_at >= datetime(start.year, start.month, start.day)
        )
    ).all()
    for created_at in signup_dates:
        if created_at:
            d = created_at.date()
            counts[d] = counts.get(d, 0) + 1
    signups = [
        schemas.AdminDashboardPoint(
            label=(start + timedelta(days=i)).strftime("%d/%m"),
            count=counts.get(start + timedelta(days=i), 0),
        )
        for i in range(window_days)
    ]

    # --- התראות נגזרות ---
    alerts: list[schemas.AdminDashboardAlert] = []
    events_no_date = (
        db.scalar(
            select(func.count(models.Event.id)).where(models.Event.event_date == "")
        )
        or 0
    )
    if events_no_date:
        alerts.append(
            schemas.AdminDashboardAlert(
                level="warn",
                text=f"{events_no_date} אירועים בלי תאריך שנקבע",
            )
        )
    # אירועים בשבוע הקרוב.
    soon_str = (today + timedelta(days=7)).isoformat()
    events_this_week = (
        db.scalar(
            select(func.count(models.Event.id)).where(
                models.Event.event_date >= today_str,
                models.Event.event_date <= soon_str,
                models.Event.event_date != "",
            )
        )
        or 0
    )
    if events_this_week:
        alerts.append(
            schemas.AdminDashboardAlert(
                level="info",
                text=f"{events_this_week} אירועים בשבוע הקרוב",
            )
        )
    if not alerts:
        alerts.append(
            schemas.AdminDashboardAlert(level="info", text="הכול תקין — אין התראות פתוחות")
        )

    return schemas.AdminDashboard(
        total_events=total_events,
        upcoming_events=upcoming_events,
        total_users=total_users,
        total_venues=total_venues,
        total_guests=total_guests,
        whatsapp_sent=whatsapp_sent,
        recent_events=recent_events,
        signups=signups,
        alerts=alerts,
        events_by_type=events_by_type,
    )


@router.get("/users", response_model=list[schemas.AdminUserRow])
def list_users(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """כל המשתמשים במערכת, עם מספר האירועים והמוזמנים של כל אחד."""
    # ספירת אירועים לכל בעלים.
    events_by_owner = dict(
        db.execute(
            select(models.Event.owner_id, func.count(models.Event.id))
            .group_by(models.Event.owner_id)
        ).all()
    )
    # ספירת מוזמנים לכל בעלים (דרך האירועים שלו).
    guests_by_owner = dict(
        db.execute(
            select(models.Event.owner_id, func.count(models.Guest.id))
            .join(models.Guest, models.Guest.event_id == models.Event.id)
            .group_by(models.Event.owner_id)
        ).all()
    )

    users = db.scalars(select(models.User).order_by(models.User.id)).all()
    return [
        schemas.AdminUserRow(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            is_admin=u.is_admin,
            account_type=u.account_type,
            disabled=u.disabled,
            events_count=events_by_owner.get(u.id, 0),
            guests_count=guests_by_owner.get(u.id, 0),
            created_at=u.created_at,
        )
        for u in users
    ]


@router.get("/events", response_model=list[schemas.AdminEventRow])
def list_all_events(
    event_type: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """כל האירועים במערכת (מכל המשתמשים), עם בעלים וספירת מוזמנים.

    ``event_type`` — סינון אופציונלי בצד השרת (בנוסף לחיפוש בצד הלקוח).
    """
    query = select(models.Event).order_by(models.Event.id.desc())
    if event_type:
        query = query.where(models.Event.event_type == event_type)
    events = db.scalars(query).all()

    # שלב 2: מסננים לפי האירועים שבאמת הוחזרו (בפרט כש-event_type מסונן) —
    # במקום לטעון את כל טבלת guests/users בכל קריאה. אותה תוצאה, פחות דאטה.
    event_ids = [e.id for e in events]
    owner_ids = {e.owner_id for e in events if e.owner_id}
    guests_by_event = dict(
        db.execute(
            select(models.Guest.event_id, func.count(models.Guest.id))
            .where(models.Guest.event_id.in_(event_ids))
            .group_by(models.Guest.event_id)
        ).all()
    ) if event_ids else {}
    emails = {
        u.id: u.email
        for u in db.scalars(
            select(models.User).where(models.User.id.in_(owner_ids))
        ).all()
    } if owner_ids else {}

    return [
        schemas.AdminEventRow(
            id=e.id,
            event_type=e.event_type,
            hosts=event_terms.hosts_names(e.event_type, e.groom_name, e.bride_name),
            groom_name=e.groom_name,
            bride_name=e.bride_name,
            venue_name=e.venue_name,
            owner_id=e.owner_id,
            owner_email=emails.get(e.owner_id) if e.owner_id else None,
            guests_count=guests_by_event.get(e.id, 0),
        )
        for e in events
    ]


@router.post(
    "/users/{user_id}/reset-password",
    response_model=schemas.AdminPasswordResetResult,
)
def reset_user_password(
    user_id: int,
    payload: schemas.AdminPasswordReset,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """איפוס סיסמה ע"י אדמין (פתרון ביניים עד שיהיה ערוץ מייל ל"שכחתי סיסמה").

    האדמין מגדיר סיסמה זמנית (או שהמערכת מייצרת אחת), והמשתמש מתחבר איתה ואז
    משנה אותה בעצמו. האיפוס פוסל את כל הטוקנים הישנים של אותו משתמש.
    """
    target = db.get(models.User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="המשתמש לא נמצא")

    temp_password = payload.new_password or secrets.token_urlsafe(9)
    target.password_hash = auth.hash_password(temp_password)
    target.token_version = (target.token_version or 1) + 1
    audit.record(
        db, "admin_reset_password",
        user_id=admin.id,
        detail=f"איפוס סיסמה למשתמש {target.email} (#{target.id})",
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return schemas.AdminPasswordResetResult(
        user_id=target.id,
        email=target.email,
        temporary_password=temp_password,
    )


@router.get("/users/{user_id}", response_model=schemas.AdminUserDetail)
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """כרטיס משתמש מלא: פרופיל, האירועים שלו, ו-10 ההתחברויות האחרונות."""
    target = db.get(models.User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="המשתמש לא נמצא")

    events = db.scalars(
        select(models.Event)
        .where(models.Event.owner_id == user_id)
        .order_by(models.Event.id.desc())
    ).all()
    guests_by_event = dict(
        db.execute(
            select(models.Guest.event_id, func.count(models.Guest.id))
            .where(models.Guest.event_id.in_([e.id for e in events] or [0]))
            .group_by(models.Guest.event_id)
        ).all()
    )
    event_rows = [
        schemas.AdminEventRow(
            id=e.id,
            event_type=e.event_type,
            hosts=event_terms.hosts_names(e.event_type, e.groom_name, e.bride_name),
            groom_name=e.groom_name,
            bride_name=e.bride_name,
            venue_name=e.venue_name,
            owner_id=e.owner_id,
            owner_email=target.email,
            guests_count=guests_by_event.get(e.id, 0),
        )
        for e in events
    ]

    login_count = db.scalar(
        select(func.count())
        .select_from(models.LoginEvent)
        .where(models.LoginEvent.user_id == user_id)
    ) or 0
    logins = db.scalars(
        select(models.LoginEvent)
        .where(models.LoginEvent.user_id == user_id)
        .order_by(models.LoginEvent.id.desc())
        .limit(10)
    ).all()
    login_rows = [
        schemas.AdminLoginRow(
            id=lg.id,
            ip=lg.ip,
            user_agent=lg.user_agent,
            created_at=lg.created_at,
        )
        for lg in logins
    ]

    return schemas.AdminUserDetail(
        id=target.id,
        email=target.email,
        display_name=target.display_name,
        phone=target.phone or "",
        is_admin=target.is_admin,
        account_type=target.account_type,
        disabled=target.disabled,
        created_at=target.created_at,
        events=event_rows,
        recent_logins=login_rows,
        login_count=login_count,
    )


@router.patch("/users/{user_id}", response_model=schemas.AdminUserRow)
def update_user(
    user_id: int,
    payload: schemas.AdminUserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """עריכת פרטי משתמש ע"י אדמין: שם תצוגה, טלפון, סוג חשבון, והרשאת אדמין."""
    target = db.get(models.User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="המשתמש לא נמצא")

    changes = []
    if payload.display_name is not None:
        new_name = payload.display_name.strip()
        if new_name and new_name != target.display_name:
            changes.append(f"שם: {target.display_name}→{new_name}")
            target.display_name = new_name
    if payload.phone is not None and payload.phone != target.phone:
        target.phone = payload.phone
        changes.append("טלפון עודכן")
    if payload.account_type is not None and payload.account_type != target.account_type:
        changes.append(f"סוג: {target.account_type}→{payload.account_type}")
        target.account_type = payload.account_type
    if payload.is_admin is not None and payload.is_admin != target.is_admin:
        # שמירה: אסור להסיר את הרשאת האדמין האחרונה במערכת.
        if target.is_admin and not payload.is_admin:
            admin_count = db.scalar(
                select(func.count()).select_from(models.User).where(models.User.is_admin.is_(True))
            ) or 0
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="לא ניתן להסיר את הרשאת האדמין האחרונה במערכת",
                )
        changes.append(f"אדמין: {target.is_admin}→{payload.is_admin}")
        target.is_admin = payload.is_admin

    # "טלפן" הוא תפקיד מגביל (גישה למסך השיחות בלבד) ו"אדמין" הוא גישה מלאה
    # — השילוב חסר משמעות ומסוכן. נחסם כאן, ולא רק ב-UI, כדי שגם קריאת API
    # ישירה לא תיצור משתמש-כלאיים. הבדיקה על המצב *הסופי*, כך שאין חשיבות
    # לסדר שבו נשלחו שני השדות באותה בקשה.
    if target.is_admin and roles.is_phone_agent(target):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="לא ניתן להגדיר משתמש גם כאדמין וגם כטלפן",
        )

    if changes:
        audit.record(
            db, "admin_update_user",
            user_id=admin.id,
            detail=f"עדכון משתמש {target.email} (#{target.id}): {', '.join(changes)}",
            ip=request.client.host if request.client else None,
        )
    db.commit()

    events_count = db.scalar(
        select(func.count()).select_from(models.Event).where(models.Event.owner_id == user_id)
    ) or 0
    guests_count = db.scalar(
        select(func.count())
        .select_from(models.Guest)
        .join(models.Event, models.Guest.event_id == models.Event.id)
        .where(models.Event.owner_id == user_id)
    ) or 0
    return schemas.AdminUserRow(
        id=target.id,
        email=target.email,
        display_name=target.display_name,
        is_admin=target.is_admin,
        account_type=target.account_type,
        disabled=target.disabled,
        events_count=events_count,
        guests_count=guests_count,
        created_at=target.created_at,
    )


@router.post("/users/{user_id}/disable", status_code=204)
def disable_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """השבתת חשבון: המשתמש לא יוכל להתחבר, וכל הטוקנים הקיימים נפסלים."""
    target = db.get(models.User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="המשתמש לא נמצא")
    if target.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="אי אפשר להשבית את החשבון שלך",
        )
    if not target.disabled:
        target.disabled = True
        target.token_version = (target.token_version or 1) + 1
        audit.record(
            db, "admin_disable_user",
            user_id=admin.id,
            detail=f"השבתת משתמש {target.email} (#{target.id})",
            ip=request.client.host if request.client else None,
        )
        db.commit()


@router.post("/users/{user_id}/enable", status_code=204)
def enable_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """הפעלה מחדש של חשבון מושבת."""
    target = db.get(models.User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="המשתמש לא נמצא")
    if target.disabled:
        target.disabled = False
        audit.record(
            db, "admin_enable_user",
            user_id=admin.id,
            detail=f"הפעלת משתמש {target.email} (#{target.id})",
            ip=request.client.host if request.client else None,
        )
        db.commit()


# מחיקת משתמש בפאנל האדמין: שני מצבים אפשריים (ראו delete_user למטה).
_DELETE_USER_MODES = {"user_only", "user_and_events"}

# חשבון-מערכת קבוע שמחזיק בעלות על אירועים של משתמשים שנמחקו במצב
# "user_only". למה לא owner_id=NULL: ``auth.adopt_orphan_events`` (נקרא בכל
# הרשמה חדשה — מיגרציה חד-פעמית מהמצב הישן החד-משתמשי, ראו
# app/auth.py) מאמצת אוטומטית *כל* אירוע עם owner_id=NULL למי שנרשם הבא.
# NULL כאן היה גורם לנתוני החתונה (מוזמנים, טלפונים, הודעות) "לקפוץ" בטעות
# לחשבון זר הבא שנרשם — דליפת מידע, לא רק באג. חשבון ייעודי ונעול (disabled,
# בלי סיסמה שאף אחד מכיר) שומר על FK תקין בלי הסיכון הזה.
_ORPHANED_EVENTS_HOLDER_EMAIL = "system.deleted-users@veya.internal"


def _get_or_create_orphaned_events_holder(db: Session) -> models.User:
    """מחזיר את חשבון-המערכת שמחזיק אירועים של משתמשים שנמחקו (יוצר בפעם הראשונה)."""
    holder = db.scalar(
        select(models.User).where(models.User.email == _ORPHANED_EVENTS_HOLDER_EMAIL)
    )
    if holder is not None:
        return holder
    holder = models.User(
        email=_ORPHANED_EVENTS_HOLDER_EMAIL,
        # סיסמה אקראית שאף אחד לא מכיר ולעולם לא נמסרת — יחד עם disabled=True
        # (הגנה כפולה: גם מי שיידע את הגיבוב לא יתחבר, כי disabled חוסם login).
        password_hash=auth.hash_password(secrets.token_urlsafe(32)),
        display_name="⚠️ אירועים ממשתמשים שנמחקו (חשבון מערכת)",
        is_admin=False,
        account_type="couple",
        disabled=True,
    )
    db.add(holder)
    db.flush()  # צריך holder.id לפני שמשייכים אליו אירועים
    return holder


def _delete_user_impl(db: Session, admin: models.User, target: models.User, mode: str) -> int:
    """הלוגיקה המלאה של מחיקת משתמש — ללא HTTP, כדי לאפשר בדיקה ישירה
    (tests/test_admin_delete_user.py) בלי לעבור דרך FastAPI.

    לא עושה commit — הקורא (delete_user למטה) אחראי לכך יחד עם רישום
    audit.record, בדיוק כמו delete_event_cascade: אם שלב כלשהו נכשל (למשל
    HTTPException על שמירת בטיחות), שום דבר לא נשמר. מחזירה כמה אירועים היו
    בבעלות המשתמש (לפירוט ביומן האבטחה).
    """
    if mode not in _DELETE_USER_MODES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="מצב מחיקה לא תקין")
    if target.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="אי אפשר למחוק את החשבון שלך",
        )
    if target.email == _ORPHANED_EVENTS_HOLDER_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="זהו חשבון מערכת שמחזיק אירועים של משתמשים שנמחקו — אי אפשר למחוק אותו",
        )
    if target.is_admin:
        admin_count = db.scalar(
            select(func.count()).select_from(models.User).where(models.User.is_admin.is_(True))
        ) or 0
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="לא ניתן למחוק את האדמין האחרון במערכת",
            )

    user_id = target.id
    owned_events = db.scalars(select(models.Event).where(models.Event.owner_id == user_id)).all()

    if mode == "user_and_events":
        # מצב 2: מוחקים גם את כל האירועים בבעלותו וכל הנתונים התלויים בהם
        # (מוזמנים/RSVP, הודעות, הבהרות, יומן שיחות...) — אותו cascade
        # שמשמש למחיקת חשבון עצמית (routers/auth.py::delete_my_account).
        for event in owned_events:
            delete_event_cascade(db, event)
    else:
        # מצב 1 ("user_only"): האירועים נשארים בשלמותם — רק הבעלות עוברת
        # לחשבון-המערכת (לא ל-NULL, ראו הסבר ב-_ORPHANED_EVENTS_HOLDER_EMAIL).
        if owned_events:
            holder = _get_or_create_orphaned_events_holder(db)
            for event in owned_events:
                event.owner_id = holder.id

    # ── ניקוי משותף לשני המצבים: כל מה שקושר את *המשתמש עצמו* (לא את
    # האירועים בבעלותו, שכבר טופלו למעלה) ────────────────────────────────
    # חברות שלו באירועים של אחרים (מפיק/אולם/שותף שהוזמן) — נמחקת, אין יותר
    # גישה (המשתמש כבר לא קיים).
    for member in db.scalars(
        select(models.EventMember).where(models.EventMember.user_id == user_id)
    ).all():
        db.delete(member)
    # חברות של *אחרים* שהוא הזמין נשארת פעילה — רק מתנתקת ממנו. לא מוחקים
    # גישה תקינה של מישהו אחר רק כי מי שהזמין אותו נמחק.
    for member in db.scalars(
        select(models.EventMember).where(models.EventMember.invited_by_id == user_id)
    ).all():
        member.invited_by_id = None
    # הזמנות שיתוף-אירוע ששלח/קיבל (event_invitations) — נשארות לתיעוד, רק
    # מתנתקות ממנו.
    for inv in db.scalars(
        select(models.EventInvitation).where(
            (models.EventInvitation.invited_by == user_id)
            | (models.EventInvitation.accepted_by == user_id)
        )
    ).all():
        if inv.invited_by == user_id:
            inv.invited_by = None
        if inv.accepted_by == user_id:
            inv.accepted_by = None
    # אישורי הסכמה (תנאי שימוש/פרטיות) — נשארים לצורך שקיפות/רגולציה, רק
    # מתנתקים מהמשתמש שנמחק (כמו ב-routers/auth.py::delete_my_account).
    for consent in db.scalars(
        select(models.ConsentRecord).where(models.ConsentRecord.user_id == user_id)
    ).all():
        consent.user_id = None
    # היסטוריית התחברות — נמחקת (אין טעם לשמר בלי המשתמש עצמו).
    for lg in db.scalars(
        select(models.LoginEvent).where(models.LoginEvent.user_id == user_id)
    ).all():
        db.delete(lg)
    # יומן אבטחה — נשאר לצורך שקיפות/תיעוד, רק מתנתק מהמשתמש שנמחק.
    for al in db.scalars(
        select(models.AuditLog).where(models.AuditLog.user_id == user_id)
    ).all():
        al.user_id = None
    # יומן שיחות ה-Call Center נשאר (הוא מתעד מה קרה מול המוזמן), רק מנותק
    # מהמשתמש שנמחק — כמו יומן האבטחה.
    for cl in db.scalars(
        select(models.CallLog).where(models.CallLog.created_by_id == user_id)
    ).all():
        cl.created_by_id = None
    # הקצאות שיחה: אלה *שלו* נמחקות (הוא כבר לא עובד כאן), ואלה שהוא הקצה
    # לאחרים נשארות ורק מתנתקות ממנו — כדי שמחיקת אדמין לא תבטל את העבודה
    # של הטלפנים שהוא שיבץ.
    for ca in db.scalars(
        select(models.CallAssignment).where(models.CallAssignment.user_id == user_id)
    ).all():
        db.delete(ca)
    for ca in db.scalars(
        select(models.CallAssignment).where(models.CallAssignment.assigned_by_id == user_id)
    ).all():
        ca.assigned_by_id = None

    db.delete(target)
    return len(owned_events)


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    request: Request,
    mode: str = Query(
        "user_only",
        description=(
            "user_only = מחיקת החשבון בלבד, האירועים נשארים · "
            "user_and_events = מחיקת החשבון וכל האירועים בבעלותו"
        ),
    ),
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """מחיקת משתמש — פעולה בלתי-הפיכה, בשני מצבים אפשריים (ראו ``mode``):

    - ``user_only`` (ברירת מחדל): מוחק רק את החשבון. האירועים בבעלותו וכל
      הנתונים שלהם (מוזמנים, הודעות, סידורי הושבה...) נשארים בשלמותם.
    - ``user_and_events``: מוחק את החשבון **וגם** את כל האירועים בבעלותו,
      כולל כל הנתונים התלויים בהם — בלתי הפיך.

    בשני המצבים: חסום אם זה החשבון שלך או האדמין האחרון במערכת. כל הלוגיקה
    בפועל ב-``_delete_user_impl`` — טרנזקציה אחת, בלי commit ביניים, כך
    שכשל בכל שלב מבטל את הכול (אטומי, אין מצב "חצי מחוק").
    """
    target = db.get(models.User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="המשתמש לא נמצא")

    email = target.email
    events_count = _delete_user_impl(db, admin, target, mode)

    audit.record(
        db, "admin_delete_user",
        user_id=admin.id,
        detail=(
            f"מחיקת משתמש {email} (#{user_id}), מצב: {mode}"
            + (f", {events_count} אירועים" if events_count else "")
        ),
        ip=request.client.host if request.client else None,
    )
    db.commit()


@router.post("/users/{user_id}/impersonate", response_model=schemas.AdminImpersonateResult)
def impersonate_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """מנפיק טוקן זמני שמאפשר לאדמין לראות את המערכת בדיוק כמו המשתמש.

    זהו ה"התחבר כמשתמש" — בלי לדעת את סיסמת המשתמש. הטוקן מונפק עבור המשתמש
    היעד, כך שכל נקודות הקצה של בעל האירוע ממילא מסננות לפי המשתמש הזה. הפרונט שומר
    את טוקן האדמין בצד, מציג באנר קבוע, ומאפשר לחזור לאדמין בכל רגע.
    """
    target = db.get(models.User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="המשתמש לא נמצא")
    if target.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="אתה כבר מחובר כאדמין הזה",
        )
    if target.is_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="אי אפשר להתחזות לאדמין אחר",
        )
    if target.disabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="החשבון מושבת. יש להפעיל אותו לפני התחזות",
        )

    token = auth.create_access_token(target)
    audit.record(
        db, "admin_impersonate",
        user_id=admin.id,
        detail=f"התחזות למשתמש {target.email} (#{target.id})",
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return schemas.AdminImpersonateResult(
        token=token,
        user_id=target.id,
        email=target.email,
        display_name=target.display_name,
    )


@router.post("/accounts", response_model=schemas.AdminAccountCreateResult, status_code=201)
def create_account(
    payload: schemas.AdminAccountCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """יצירת חשבון מפיק/אולם ע"י אדמין.

    למפיקים ואולמות אין הרשמה עצמאית — רק האדמין יוצר עבורם חשבון, עם סיסמה
    זמנית (מפורשת או מיוצרת). המשתמש מתחבר איתה ומחליף אותה בעצמו.
    """
    existing = db.scalars(
        select(models.User).where(models.User.email == payload.email)
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="כבר קיים משתמש עם האימייל הזה",
        )

    temp_password = payload.new_password or secrets.token_urlsafe(9)
    user = models.User(
        email=payload.email,
        display_name=payload.display_name,
        password_hash=auth.hash_password(temp_password),
        account_type=payload.account_type,
    )
    db.add(user)
    db.commit()
    audit.record(
        db, "admin_create_account",
        user_id=admin.id,
        detail=f"יצירת חשבון {payload.account_type} עבור {user.email} (#{user.id})",
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return schemas.AdminAccountCreateResult(
        user_id=user.id,
        email=user.email,
        account_type=user.account_type,
        temporary_password=temp_password,
    )


# --- ניהול טלפנים (phone_agent) ---
# שני endpoints בלבד, שניהם ``get_current_admin``. אין כאן מנגנון חדש:
# היצירה עוברת ב-``create_account`` שכבר קיים, ההשבתה/הפעלה ב-``disable_user``/
# ``enable_user`` שכבר קיימים (ומאפסים טוקנים בעצמם), וההקצאה נשמרת בטבלת
# ``call_assignments`` שנבנתה בשלב הקודם.


@router.get("/callers", response_model=schemas.AdminCallersPage)
def list_callers(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """מסך ניהול הטלפנים: כל משתמשי ``phone_agent`` + האירועים להקצאה.

    המונים אינם מטבלת סטטיסטיקות חדשה — "שיחות שביצע" נספר ישירות מ-
    ``call_logs``, ו"משימות ממתינות" מגיע מאותו ``build_queues`` שמזין את מסך
    השיחות עצמו. התור נבנה **פעם אחת** (בהיקף אדמין = כל האירועים), ומחולק
    לטלפנים לפי ההקצאות שלהם — כדי לא להריץ את החישוב מחדש לכל טלפן.
    """
    callers = db.scalars(
        select(models.User)
        .where(models.User.account_type == roles.PHONE_AGENT)
        .order_by(models.User.display_name, models.User.id)
    ).all()
    caller_ids = [c.id for c in callers]

    calls_by_user = dict(
        db.execute(
            select(models.CallLog.created_by_id, func.count(models.CallLog.id))
            .where(models.CallLog.created_by_id.in_(caller_ids))
            .group_by(models.CallLog.created_by_id)
        ).all()
    ) if caller_ids else {}

    assigned_by_user: dict[int, list[int]] = {cid: [] for cid in caller_ids}
    if caller_ids:
        for user_id, event_id in db.execute(
            select(models.CallAssignment.user_id, models.CallAssignment.event_id)
            .where(models.CallAssignment.user_id.in_(caller_ids))
        ).all():
            assigned_by_user[user_id].append(event_id)

    queues = call_center.build_queues(db)
    waiting_by_event = {q.event.id: len(q.guests) for q in queues}
    shared_total = sum(waiting_by_event.values())

    rows = []
    for c in callers:
        assigned = sorted(assigned_by_user.get(c.id, []))
        # בדיוק הסמנטיקה של call_center.visible_event_ids: בלי הקצאות —
        # התור המשותף המלא; עם הקצאות — רק מה שהוקצה.
        waiting = (
            sum(waiting_by_event.get(eid, 0) for eid in assigned)
            if assigned else shared_total
        )
        rows.append(schemas.AdminCallerRow(
            id=c.id,
            email=c.email,
            display_name=c.display_name or "",
            phone=c.phone or "",
            disabled=bool(c.disabled),
            calls_made=calls_by_user.get(c.id, 0),
            waiting_tasks=waiting,
            assigned_event_ids=assigned,
            created_at=c.created_at,
        ))

    events = db.scalars(select(models.Event).order_by(models.Event.id.desc())).all()
    options = [
        schemas.AdminCallerEventOption(
            event_id=e.id,
            event_type=e.event_type,
            hosts=event_terms.hosts_names(e.event_type, e.groom_name, e.bride_name),
            venue_name=e.venue_name or "",
            event_date=e.event_date or "",
            waiting=waiting_by_event.get(e.id, 0),
        )
        for e in events
    ]
    return schemas.AdminCallersPage(callers=rows, events=options)


@router.put("/callers/{user_id}/assignments", response_model=schemas.AdminCallerRow)
def set_caller_assignments(
    user_id: int,
    payload: schemas.AdminCallerAssignmentUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """מחליף את רשימת האירועים המוקצים לטלפן.

    רשימה ריקה = הסרת כל ההקצאות, כלומר חזרה לתור המשותף (זו ההתנהגות
    המוגדרת של שלב א', ראו ``models.CallAssignment``). ההקצאה משנה **רק** מה
    הטלפן רואה — היא לא נוגעת בחישוב סבבי השיחות ולא בסטטוס אף מוזמן.
    """
    target = db.get(models.User, user_id)
    if target is None or not roles.is_phone_agent(target):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="הטלפן לא נמצא"
        )

    wanted = set(payload.event_ids)
    if wanted:
        found = set(db.scalars(
            select(models.Event.id).where(models.Event.id.in_(wanted))
        ).all())
        missing = wanted - found
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="אחד האירועים שנבחרו לא קיים",
            )

    current = {
        a.event_id: a for a in db.scalars(
            select(models.CallAssignment).where(
                models.CallAssignment.user_id == user_id
            )
        ).all()
    }
    for event_id, row in current.items():
        if event_id not in wanted:
            db.delete(row)
    for event_id in wanted - set(current):
        db.add(models.CallAssignment(
            event_id=event_id, user_id=user_id, assigned_by_id=admin.id,
        ))

    audit.record(
        db, "admin_caller_assignments",
        user_id=admin.id,
        detail=(
            f"הקצאת אירועים לטלפן {target.email} (#{target.id}): "
            + (", ".join(f"#{e}" for e in sorted(wanted)) if wanted else "תור משותף")
        ),
        ip=request.client.host if request.client else None,
    )
    db.commit()

    calls_made = db.scalar(
        select(func.count(models.CallLog.id)).where(
            models.CallLog.created_by_id == user_id
        )
    ) or 0
    queues = call_center.build_queues(
        db, allowed_event_ids=call_center.visible_event_ids(db, target)
    )
    return schemas.AdminCallerRow(
        id=target.id,
        email=target.email,
        display_name=target.display_name or "",
        phone=target.phone or "",
        disabled=bool(target.disabled),
        calls_made=calls_made,
        waiting_tasks=sum(len(q.guests) for q in queues),
        assigned_event_ids=sorted(wanted),
        created_at=target.created_at,
    )


# --- ניהול ברירות המחדל הגלובליות לרצף "תקשורת עם אורחים" ---
# רק אדמין. כאן הבעלים מזין את הטקסטים הסופיים לכל event_type × message_type
# (48 שורות); כל אירוע חדש מעתיק מכאן את השורה המתאימה לו (idempotent).

MESSAGE_DEFAULTS_CACHE_TTL_SECONDS = 300  # 5 דקות — עריכה נדירה, invalidate מיידי בכתיבה


@router.get("/message-defaults", response_model=list[schemas.MessageDefaultRead])
def list_message_defaults(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """כל 48 ברירות המחדל (8 סוגי אירוע × 6 סוגי הודעה), לפי סוג אירוע וסדר קבוע."""

    def _load():
        rows = db.scalars(
            select(models.MessageDefault).order_by(
                models.MessageDefault.event_type, models.MessageDefault.id
            )
        ).all()
        return cache.snapshot_all(rows)

    order = {mt: i for i, mt in enumerate(communication.MESSAGE_TYPES)}
    rows = cache.get_or_set(
        "message_defaults:admin_all", MESSAGE_DEFAULTS_CACHE_TTL_SECONDS, _load
    )
    return sorted(rows, key=lambda r: (r.event_type, order.get(r.message_type, 99)))


@router.patch("/message-defaults/{default_id}", response_model=schemas.MessageDefaultRead)
def update_message_default(
    default_id: int,
    payload: schemas.MessageDefaultUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    d = db.get(models.MessageDefault, default_id)
    if d is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ברירת המחדל לא נמצאה")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(d, field, value)
    db.commit()
    cache.invalidate_prefix("message_defaults:")
    return d


@router.post("/message-defaults/backfill", response_model=schemas.MessageDefaultsBackfillResult)
def backfill_message_defaults(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """מקצה את רצף "תקשורת עם אורחים" לכל אירוע קיים שעדיין חסר לו (idempotent —
    לא נוגע באירוע שכבר קיבל את השורות, אפילו אם עדיין ריקות)."""
    events = db.scalars(select(models.Event)).all()
    created = 0
    for ev in events:
        created += communication.provision_event_messages(db, ev)
    db.commit()
    return schemas.MessageDefaultsBackfillResult(
        events_processed=len(events), messages_created=created,
    )


# ---- ספריית נוסחים לבחירה (MessageDefaultOption) — עד 12 וריאציות לכל
#      event_type×message_type, שהזוג בוחר מתוכן (decisions.md 2026-08-06).
#      האדמין הוא מקור האמת: עריכה + הוספה כאן, לא טקסט קשיח בקוד. ----

@router.get("/message-default-options", response_model=list[schemas.MessageDefaultOptionRead])
def list_message_default_options(
    event_type: Optional[str] = None,
    message_type: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    stmt = select(models.MessageDefaultOption)
    if event_type:
        stmt = stmt.where(models.MessageDefaultOption.event_type == event_type)
    if message_type:
        stmt = stmt.where(models.MessageDefaultOption.message_type == message_type)
    rows = db.scalars(stmt).all()
    return sorted(rows, key=lambda r: (r.event_type, r.message_type, r.option_number))


@router.post(
    "/message-default-options",
    response_model=schemas.MessageDefaultOptionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_message_default_option(
    payload: schemas.MessageDefaultOptionCreate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """מוסיף וריאציה חדשה — ממספר אוטומטית את המספר הפנוי הבא (1–12)."""
    taken = set(db.scalars(
        select(models.MessageDefaultOption.option_number)
        .where(models.MessageDefaultOption.event_type == payload.event_type)
        .where(models.MessageDefaultOption.message_type == payload.message_type)
    ).all())
    next_number = next((n for n in range(1, 13) if n not in taken), None)
    if next_number is None:
        raise HTTPException(status_code=400, detail="כבר יש 12 נוסחים לשילוב הזה — המקסימום המותר")
    option = models.MessageDefaultOption(
        event_type=payload.event_type,
        message_type=payload.message_type,
        option_number=next_number,
        tone=payload.tone,
        title=payload.title,
        content=payload.content,
        variables_supported=payload.variables_supported,
    )
    db.add(option)
    db.commit()
    return option


@router.patch("/message-default-options/{option_id}", response_model=schemas.MessageDefaultOptionRead)
def update_message_default_option(
    option_id: int,
    payload: schemas.MessageDefaultOptionUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    option = db.get(models.MessageDefaultOption, option_id)
    if option is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="הנוסח לא נמצא")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(option, field, value)
    db.commit()
    return option


@router.delete("/message-default-options/{option_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_message_default_option(
    option_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    option = db.get(models.MessageDefaultOption, option_id)
    if option is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="הנוסח לא נמצא")
    db.delete(option)
    db.commit()


@router.get("/veya/message-stats", response_model=schemas.AdminMessageStats)
def veya_message_stats(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """נפח ההודעות במערכת: יוצאות ב-WhatsApp לפי סוג, ונכנסות."""
    rows = db.execute(
        select(models.Message.kind, func.count(models.Message.id))
        .where(
            models.Message.direction == "outbound",
            models.Message.channel == "whatsapp",
        )
        .group_by(models.Message.kind)
        .order_by(func.count(models.Message.id).desc())
    ).all()
    by_kind = [schemas.AdminMessageStat(kind=k or "custom", count=c) for k, c in rows]
    total_outbound = sum(s.count for s in by_kind)
    total_inbound = (
        db.scalar(
            select(func.count(models.Message.id)).where(
                models.Message.direction == "inbound"
            )
        )
        or 0
    )
    return schemas.AdminMessageStats(
        total_outbound=total_outbound,
        total_inbound=total_inbound,
        by_kind=by_kind,
    )


# ---------------------------------------------------------------------------
# יומן פעולות האדמין (שלב אדמין 6)
# ---------------------------------------------------------------------------

@router.get("/audit-log", response_model=list[schemas.AdminAuditRow])
def list_audit_log(
    limit: int = 150,
    action: Optional[str] = None,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """יומן הפעולות האחרונות במערכת — החדשות קודם. סינון אופציונלי לפי סוג פעולה."""
    limit = max(1, min(limit, 500))
    stmt = (
        select(models.AuditLog, models.User)
        .outerjoin(models.User, models.AuditLog.user_id == models.User.id)
        .order_by(models.AuditLog.created_at.desc(), models.AuditLog.id.desc())
        .limit(limit)
    )
    if action:
        stmt = stmt.where(models.AuditLog.action == action)
    rows = db.execute(stmt).all()
    result = []
    for log, user in rows:
        result.append(
            schemas.AdminAuditRow(
                id=log.id,
                action=log.action,
                detail=log.detail or "",
                ip=log.ip,
                event_id=log.event_id,
                user_id=log.user_id,
                actor_email=user.email if user else None,
                actor_name=user.display_name if user else None,
                created_at=log.created_at,
            )
        )
    return result


# ---------------------------------------------------------------------------
# ניהול מאגר האולמות (שלב אדמין 4)
# ---------------------------------------------------------------------------

def _venue_to_row(v: models.Venue) -> schemas.AdminVenueRow:
    """ממיר רשומת אולם לשורת תצוגה באדמין, כולל קישורי ניווט מחושבים מהכתובת."""
    address = v.address or ""
    return schemas.AdminVenueRow(
        id=v.id,
        name=v.name,
        address=address,
        city=v.city or "",
        usage_count=v.usage_count,
        maps_link=messaging.maps_link(address) if address else "",
        waze_link=messaging.waze_link(address) if address else "",
        created_at=v.created_at,
    )


@router.get("/venues", response_model=list[schemas.AdminVenueRow])
def list_venues(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """כל האולמות במאגר, הפופולריים קודם."""

    def _load():
        rows = db.scalars(
            select(models.Venue).order_by(
                models.Venue.usage_count.desc(), models.Venue.name
            )
        ).all()
        return [_venue_to_row(v) for v in rows]

    return cache.get_or_set(
        "venues:admin_list", venues.VENUE_CACHE_TTL_SECONDS, _load
    )


@router.patch("/venues/{venue_id}", response_model=schemas.AdminVenueRow)
def update_venue(
    venue_id: int,
    payload: schemas.AdminVenueUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """עדכון שם/כתובת/עיר של אולם. שינוי שם מעדכן גם את מפתח הדדופ."""
    venue = db.get(models.Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="האולם לא נמצא")
    data = payload.model_dump(exclude_unset=True)
    before = f"{venue.name} / {venue.address} / {venue.city}"

    new_name = data.get("name")
    if new_name is not None:
        new_name = new_name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="שם האולם לא יכול להיות ריק")
        new_key = venues._dedup_key(new_name)
        if new_key != venue.dedup_key:
            clash = db.scalar(
                select(models.Venue).where(
                    models.Venue.dedup_key == new_key, models.Venue.id != venue.id
                )
            )
            if clash is not None:
                raise HTTPException(
                    status_code=400,
                    detail="כבר קיים אולם עם שם זהה. אפשר למזג ביניהם במקום לשנות שם.",
                )
            venue.dedup_key = new_key
        venue.name = new_name

    if "address" in data and data["address"] is not None:
        venue.address = data["address"].strip()
    if "city" in data and data["city"] is not None:
        venue.city = data["city"].strip()

    after = f"{venue.name} / {venue.address} / {venue.city}"
    audit.record(
        db, "admin_update_venue",
        user_id=admin.id,
        detail=f"עדכון אולם #{venue.id}: [{before}] ← [{after}]",
        ip=request.client.host if request.client else None,
    )
    db.commit()
    cache.invalidate_prefix("venues:")
    return _venue_to_row(venue)


@router.delete("/venues/{venue_id}", status_code=204)
def delete_venue(
    venue_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """מחיקת אולם מהמאגר. לא משפיע על אירועים קיימים (הם שומרים את שם האולם אצלם)."""
    venue = db.get(models.Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="האולם לא נמצא")
    audit.record(
        db, "admin_delete_venue",
        user_id=admin.id,
        detail=f"מחיקת אולם #{venue.id} ({venue.name})",
        ip=request.client.host if request.client else None,
    )
    db.delete(venue)
    db.commit()
    cache.invalidate_prefix("venues:")
    return None


@router.post("/venues/{venue_id}/merge", response_model=schemas.AdminVenueRow)
def merge_venue(
    venue_id: int,
    payload: schemas.AdminVenueMerge,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """מיזוג אולם כפול לתוך אולם יעד: מחבר את מונה השימושים ומוחק את המקור."""
    source = db.get(models.Venue, venue_id)
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="האולם למיזוג לא נמצא")
    target = db.get(models.Venue, payload.target_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="אולם היעד לא נמצא")
    if source.id == target.id:
        raise HTTPException(status_code=400, detail="אי אפשר למזג אולם לתוך עצמו")

    target.usage_count += source.usage_count
    audit.record(
        db, "admin_merge_venue",
        user_id=admin.id,
        detail=f"מיזוג אולם #{source.id} ({source.name}) → #{target.id} ({target.name})",
        ip=request.client.host if request.client else None,
    )
    db.delete(source)
    db.commit()
    cache.invalidate_prefix("venues:")
    return _venue_to_row(target)
