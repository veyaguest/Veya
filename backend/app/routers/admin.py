"""Router לפאנל האדמין (הבעלים) — שלב 8.

מאפשר לבעלים (משתמש עם ``is_admin``) לראות את *כל* המשתמשים ו*כל* האירועים
במערכת, כולל ספירת מוזמנים לכל אחד. מוגן ב-``get_current_admin`` — משתמש רגיל
יקבל 403.
"""
import secrets
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit, auth, messaging, models, schemas, venues
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
    guests_by_event = dict(
        db.execute(
            select(models.Guest.event_id, func.count(models.Guest.id)).group_by(
                models.Guest.event_id
            )
        ).all()
    )
    emails = {u.id: u.email for u in db.scalars(select(models.User)).all()}
    recent = db.scalars(
        select(models.Event).order_by(models.Event.id.desc()).limit(8)
    ).all()
    recent_events = []
    for e in recent:
        couple = " · ".join([n for n in (e.groom_name, e.bride_name) if n]) or "—"
        ed = _parse_event_date(e.event_date)
        days_until = (ed - today).days if ed and ed >= today else None
        recent_events.append(
            schemas.AdminDashboardEvent(
                id=e.id,
                couple=couple,
                venue_name=e.venue_name or "",
                owner_email=emails.get(e.owner_id) if e.owner_id else None,
                event_date=e.event_date or "",
                guests_count=guests_by_event.get(e.id, 0),
                days_until=days_until,
            )
        )

    # --- גרף הרשמות ל-14 הימים האחרונים ---
    window_days = 14
    start = today - timedelta(days=window_days - 1)
    counts: dict[date, int] = {}
    users = db.scalars(
        select(models.User).where(models.User.created_at >= datetime(start.year, start.month, start.day))
    ).all()
    for u in users:
        if u.created_at:
            d = u.created_at.date()
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
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """כל האירועים במערכת (מכל המשתמשים), עם בעלים וספירת מוזמנים."""
    guests_by_event = dict(
        db.execute(
            select(models.Guest.event_id, func.count(models.Guest.id))
            .group_by(models.Guest.event_id)
        ).all()
    )
    emails = {u.id: u.email for u in db.scalars(select(models.User)).all()}

    events = db.scalars(select(models.Event).order_by(models.Event.id.desc())).all()
    return [
        schemas.AdminEventRow(
            id=e.id,
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

    if changes:
        audit.record(
            db, "admin_update_user",
            user_id=admin.id,
            detail=f"עדכון משתמש {target.email} (#{target.id}): {', '.join(changes)}",
            ip=request.client.host if request.client else None,
        )
    db.commit()
    db.refresh(target)

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


@router.delete("/users/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """מחיקת משתמש — פעולה בלתי-הפיכה, עם שמירות בטיחות מחמירות.

    חסום אם: זה החשבון שלך, זה האדמין האחרון, או שיש למשתמש אירועים משויכים
    (כדי לא ליצור אירועים יתומים ולא למחוק נתונים בטעות).
    """
    target = db.get(models.User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="המשתמש לא נמצא")
    if target.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="אי אפשר למחוק את החשבון שלך",
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
    owned_events = db.scalar(
        select(func.count()).select_from(models.Event).where(models.Event.owner_id == user_id)
    ) or 0
    if owned_events:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"למשתמש יש {owned_events} אירועים. יש להעביר בעלות או למחוק אותם קודם",
        )

    # ניקוי הפניות לפני המחיקה כדי לא להפר מפתחות זרים.
    for lg in db.scalars(
        select(models.LoginEvent).where(models.LoginEvent.user_id == user_id)
    ).all():
        db.delete(lg)
    for al in db.scalars(
        select(models.AuditLog).where(models.AuditLog.user_id == user_id)
    ).all():
        al.user_id = None

    email = target.email
    audit.record(
        db, "admin_delete_user",
        user_id=admin.id,
        detail=f"מחיקת משתמש {email} (#{user_id})",
        ip=request.client.host if request.client else None,
    )
    db.delete(target)
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
    היעד, כך שכל נקודות הקצה של הזוג ממילא מסננות לפי המשתמש הזה. הפרונט שומר
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
    db.refresh(user)
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


# --- ניהול ברירות המחדל הגלובליות של VEYA (ספריית תבניות + מסלול קבוע) ---
# רק אדמין. אלה הברירות שמוחלות אוטומטית על כל זוג חדש; הזוג מקבל עותק לעריכה.


@router.get("/veya/templates", response_model=list[schemas.VeyaTemplateRead])
def list_veya_templates(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """כל תבניות ברירת המחדל הגלובליות, מסודרות לפי שלב ומיקום."""
    return db.scalars(
        select(models.VeyaTemplate).order_by(
            models.VeyaTemplate.sort_order, models.VeyaTemplate.id
        )
    ).all()


@router.post("/veya/templates", response_model=schemas.VeyaTemplateRead, status_code=201)
def create_veya_template(
    payload: schemas.VeyaTemplateCreate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    tpl = models.VeyaTemplate(
        stage=payload.stage,
        name=payload.name,
        body=payload.body,
        is_default=payload.is_default,
        active=payload.active,
        sort_order=payload.sort_order,
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.patch("/veya/templates/{template_id}", response_model=schemas.VeyaTemplateRead)
def update_veya_template(
    template_id: int,
    payload: schemas.VeyaTemplateUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    tpl = db.get(models.VeyaTemplate, template_id)
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="התבנית לא נמצאה")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(tpl, field, value)
    db.commit()
    db.refresh(tpl)
    return tpl


@router.delete("/veya/templates/{template_id}", status_code=204)
def delete_veya_template(
    template_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    tpl = db.get(models.VeyaTemplate, template_id)
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="התבנית לא נמצאה")
    db.delete(tpl)
    db.commit()


@router.get("/veya/workflow", response_model=list[schemas.VeyaWorkflowStepRead])
def list_veya_workflow(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    """שלבי המסלול הקבוע של VEYA, לפי סדר."""
    return db.scalars(
        select(models.VeyaWorkflowStep).order_by(models.VeyaWorkflowStep.step_order)
    ).all()


@router.patch("/veya/workflow/{step_id}", response_model=schemas.VeyaWorkflowStepRead)
def update_veya_workflow_step(
    step_id: int,
    payload: schemas.VeyaWorkflowStepUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_current_admin),
):
    step = db.get(models.VeyaWorkflowStep, step_id)
    if step is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="השלב לא נמצא")
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(step, field, value)
    db.commit()
    db.refresh(step)
    return step


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
    rows = db.scalars(
        select(models.Venue).order_by(
            models.Venue.usage_count.desc(), models.Venue.name
        )
    ).all()
    return [_venue_to_row(v) for v in rows]


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
    db.refresh(venue)
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
    db.refresh(target)
    return _venue_to_row(target)
