"""מרכז השליטה של האדמין — זהות ודרגות, ניהול אדמינים, ויומן פעולות האדמין.

נפרד מ-``routers/admin.py`` (שכבר ארוך) כדי שכל תחום חדש של מרכז השליטה
יקבל בית ברור. כל נתיב מוגן ב-``admin_rbac.require`` — כלומר עובר קודם את
``get_current_admin`` ואז בדיקת דרגה.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app import admin_audit, admin_rbac, local_time, models
from app.database import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# מי אני
# ---------------------------------------------------------------------------

class AdminMe(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    role_label: str
    permissions: list[str]


@router.get("/me", response_model=AdminMe)
def admin_me(admin: models.User = Depends(admin_rbac.require("dashboard.view"))):
    """הדרגה וההרשאות של האדמין המחובר — ה-UI מסתיר לפיהן, השרת אוכף בנפרד."""
    role = admin_rbac.role_of(admin) or ""
    return AdminMe(
        id=admin.id,
        email=admin.email,
        display_name=admin.display_name or "",
        role=role,
        role_label=admin_rbac.ROLE_LABELS.get(role, role),
        permissions=admin_rbac.permissions_for(admin),
    )


# ---------------------------------------------------------------------------
# הגדרות Admin — מי אדמין ובאיזו דרגה
# ---------------------------------------------------------------------------

class AdminAccountRow(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    role_label: str
    disabled: bool
    is_self: bool
    created_at: Optional[datetime] = None


class AdminRoleWrite(BaseModel):
    # None = הסרת הרשאת אדמין
    role: Optional[str] = None
    reason: str = Field(default="", max_length=500)


def _account_row(user: models.User, me: models.User) -> AdminAccountRow:
    role = admin_rbac.role_of(user) or ""
    return AdminAccountRow(
        id=user.id,
        email=user.email,
        display_name=user.display_name or "",
        role=role,
        role_label=admin_rbac.ROLE_LABELS.get(role, role),
        disabled=bool(user.disabled),
        is_self=user.id == me.id,
        created_at=user.created_at,
    )


@router.get("/admins", response_model=list[AdminAccountRow])
def list_admins(
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("admins.manage")),
):
    users = db.scalars(
        select(models.User).where(models.User.is_admin.is_(True)).order_by(models.User.id)
    ).all()
    return [_account_row(u, admin) for u in users]


def _super_admin_count(db: Session) -> int:
    users = db.scalars(select(models.User).where(models.User.is_admin.is_(True))).all()
    return sum(
        1 for u in users
        if admin_rbac.role_of(u) == admin_rbac.SUPER_ADMIN and not u.disabled
    )


@router.put("/admins/{user_id}/role", response_model=AdminAccountRow)
def set_admin_role(
    user_id: int,
    payload: AdminRoleWrite,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("admins.manage")),
):
    """קובע דרגת אדמין למשתמש קיים, או מסיר ממנו הרשאת אדמין (``role=None``).

    הגנות (בשרת, לא רק ב-UI):
    - אי אפשר לשנות את הדרגה של עצמך.
    - אי אפשר להעניק דרגה גבוהה מהדרגה שלך.
    - תמיד נשאר לפחות Super Admin פעיל אחד.
    - טלפן לא יכול להיות אדמין.
    """
    if payload.role is not None and payload.role not in admin_rbac.ROLES:
        raise HTTPException(status_code=400, detail="דרגה לא מוכרת")
    target = db.get(models.User, user_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="המשתמש לא נמצא")
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="אי אפשר לשנות את הדרגה של עצמך")
    if not admin_rbac.can_grant(admin, payload.role):
        raise HTTPException(status_code=403, detail="אי אפשר להעניק דרגה גבוהה מהדרגה שלך")
    if payload.role is not None and (target.account_type or "") == "phone_agent":
        raise HTTPException(status_code=400, detail="לא ניתן להגדיר טלפן כאדמין")

    before_role = admin_rbac.role_of(target)
    if before_role == payload.role:
        return _account_row(target, admin)

    if before_role == admin_rbac.SUPER_ADMIN and not target.disabled and _super_admin_count(db) <= 1:
        raise HTTPException(
            status_code=400, detail="חייב להישאר לפחות Super Admin פעיל אחד במערכת",
        )

    target.is_admin = payload.role is not None
    target.admin_role = payload.role
    # שינוי הרשאות פוסל טוקנים קיימים — הדרגה החדשה חלה מיד, לא בהתחברות הבאה.
    target.token_version = (target.token_version or 1) + 1

    def label(role: Optional[str]) -> str:
        return admin_rbac.ROLE_LABELS.get(role, role) if role else "לא אדמין"

    admin_audit.record(
        db, admin, domain="admins", action="admin.role_change",
        summary=f"שינה/תה הרשאת אדמין של {target.email}",
        target_type="user", target_id=target.id, target_label=target.email,
        changes=[admin_audit.change("admin_role", "דרגה", label(before_role), label(payload.role))],
        reason=payload.reason, request=request,
    )
    db.commit()
    db.refresh(target)
    return _account_row(target, admin)


# ---------------------------------------------------------------------------
# יומן פעילות — פעולות אדמין בלבד
# ---------------------------------------------------------------------------

class AdminAuditChange(BaseModel):
    field: str
    label: str
    before: str
    after: str


class AdminAuditEntry(BaseModel):
    id: int
    actor_id: Optional[int]
    actor_label: str
    actor_role: str
    domain: str
    domain_label: str
    action: str
    target_type: str
    target_id: str
    target_label: str
    summary: str
    changes: list[AdminAuditChange]
    reason: str
    event_id: Optional[int]
    created_at: Optional[datetime]


class AdminAuditPage(BaseModel):
    items: list[AdminAuditEntry]
    total: int
    limit: int
    offset: int
    domains: dict[str, str]
    actors: list[dict]


def _parse_day(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="תאריך לא תקין")


@router.get("/audit", response_model=AdminAuditPage)
def admin_audit_log(
    q: str = "",
    domain: str = "",
    actor_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    target_type: str = "",
    target_id: str = "",
    event_id: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("audit.view")),
):
    """יומן פעולות האדמין, החדש קודם. חיפוש + סינון לפי אדמין/תחום/תאריך/יעד.

    התאריכים הם ימים בשעון ישראל ("עד" כולל את כל היום).
    """
    M = models.AdminAuditLog
    filters = []
    if domain:
        filters.append(M.domain == domain)
    if actor_id is not None:
        filters.append(M.actor_id == actor_id)
    if target_type:
        filters.append(M.target_type == target_type)
    if target_id:
        filters.append(M.target_id == target_id)
    if event_id is not None:
        filters.append(or_(M.event_id == event_id, and_(M.target_type == "event", M.target_id == str(event_id))))
    d_from, d_to = _parse_day(date_from), _parse_day(date_to)
    if d_from:
        filters.append(M.created_at >= local_time.israel_day_start_utc(d_from))
    if d_to:
        filters.append(M.created_at < local_time.israel_day_bounds_utc(d_to)[1])
    if q.strip():
        like = f"%{q.strip()}%"
        filters.append(or_(
            M.summary.ilike(like), M.target_label.ilike(like),
            M.actor_label.ilike(like), M.reason.ilike(like),
        ))

    total = db.scalar(select(func.count(M.id)).where(*filters)) or 0
    rows = db.scalars(
        select(M).where(*filters).order_by(M.created_at.desc(), M.id.desc())
        .limit(limit).offset(offset)
    ).all()
    actors = db.execute(
        select(M.actor_id, func.max(M.actor_label)).where(M.actor_id.is_not(None)).group_by(M.actor_id)
    ).all()

    return AdminAuditPage(
        items=[
            AdminAuditEntry(
                id=r.id, actor_id=r.actor_id, actor_label=r.actor_label or "",
                actor_role=admin_rbac.ROLE_LABELS.get(r.actor_role, r.actor_role or ""),
                domain=r.domain,
                domain_label=admin_audit.DOMAIN_LABELS.get(r.domain, r.domain),
                action=r.action, target_type=r.target_type or "", target_id=r.target_id or "",
                target_label=r.target_label or "", summary=r.summary or "",
                changes=[AdminAuditChange(**c) for c in (r.changes or [])],
                reason=r.reason or "", event_id=r.event_id, created_at=r.created_at,
            )
            for r in rows
        ],
        total=total, limit=limit, offset=offset,
        domains=admin_audit.DOMAIN_LABELS,
        actors=[{"id": a, "label": label or ""} for a, label in actors],
    )


# ---------------------------------------------------------------------------
# דשבורד וחיפוש גלובלי
# ---------------------------------------------------------------------------

@router.get("/overview")
def admin_overview_endpoint(
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("dashboard.view")),
):
    """מצב VEYA · דורש תשומת לב · מצב המערכת — ראו ``app/admin_overview.py``."""
    from app import admin_overview

    return admin_overview.overview(db)


@router.get("/search")
def admin_search(
    q: str = Query("", max_length=100),
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("search.use")),
):
    from app import admin_overview

    return {"q": q, "groups": admin_overview.search(db, q)}
