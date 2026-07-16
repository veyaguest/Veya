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

from app import audit, auth, models, schemas
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
