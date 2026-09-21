"""מסחר — מסלולים (עם גרסאות), תוספים, עמלות, קופונים, ורכישות לאירועים.

מודל עסקי נעול: תשלום חד-פעמי לאירוע. אין סליקה מחוברת: כל פעולה כאן היא
נתון ניהולי אמיתי (מסלול שנקבע לאירוע פותח פיצ'רים), לא חיוב.
- מחיר מסלול לא נדרס: שינוי = גרסה חדשה; רכישות קיימות נשארות על הגרסה שלהן.
- עמלה: היסטוריה נשמרת; הכיוון (מתווספת על הנותן) נעול.
- קופון: נשמר ומנוהל; מימוש בקופה — כשתחובר סליקה (מוצג כך במסך).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import admin_audit, admin_rbac, commerce, event_terms, features, gift, local_time, models
from app.database import get_db

router = APIRouter(prefix="/admin/commerce", tags=["admin"])
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
PLAN_STATUS = {"active": "פעיל", "hidden": "מוסתר", "draft": "טיוטה", "archived": "בארכיון"}
ENT_STATUS = {"active": "פעיל", "trial": "ניסיון", "paused": "מושהה", "cancelled": "בוטל", "expired": "הסתיים"}


def _ils(agorot: Optional[int]) -> str:
    return "—" if agorot is None else gift.format_shekels(agorot)


def _feature_options(db: Session) -> list[dict]:
    """רק פיצ'רים שמסלול באמת יכול לפתוח: מובנים שנשלטים בקוד + דגלים שנוצרו באדמין."""
    opts = [{"key": k, "label": f.label} for k, f in features.BUILTIN.items() if f.controllable]
    opts += [{"key": f.key, "label": f.label or f.key} for f in db.scalars(select(models.FeatureFlag)).all()
             if f.key not in features.BUILTIN]
    return opts


def _feature_keys(db: Session) -> set[str]:
    return {o["key"] for o in _feature_options(db)}


# ── מסלולים ────────────────────────────────────────────────────────────────

def _version_dict(v: models.PlanVersion) -> dict:
    return {
        "id": v.id, "version": v.version, "price_agorot": v.price_agorot, "guest_limit": v.guest_limit,
        "event_limit": v.event_limit, "trial_days": v.trial_days, "features": v.features or [],
        "included_addons": v.included_addons or [], "available_addons": v.available_addons or [],
        "change_note": v.change_note or "", "created_at": v.created_at,
    }


def _plan_dict(db: Session, p: models.Plan, with_history: bool = False) -> dict:
    versions = db.scalars(select(models.PlanVersion).where(models.PlanVersion.plan_id == p.id)
                          .order_by(models.PlanVersion.version.desc())).all()
    current = next((v for v in versions if v.id == p.current_version_id), versions[0] if versions else None)
    usage = dict(db.execute(
        select(models.EventEntitlement.plan_version_id, func.count(models.EventEntitlement.id))
        .where(models.EventEntitlement.plan_version_id.in_([v.id for v in versions] or [0]))
        .group_by(models.EventEntitlement.plan_version_id)
    ).all())
    out = {
        "id": p.id, "key": p.key, "name": p.name, "description": p.description or "", "status": p.status,
        "status_label": PLAN_STATUS.get(p.status, p.status), "sort_order": p.sort_order,
        "current": _version_dict(current) if current else None,
        "events_count": sum(usage.values()),
    }
    if with_history:
        out["versions"] = [{**_version_dict(v), "events_count": usage.get(v.id, 0)} for v in versions]
    return out


@router.get("/plans")
def list_plans(db: Session = Depends(get_db), admin: models.User = Depends(admin_rbac.require("commerce.view"))):
    plans = db.scalars(select(models.Plan).order_by(models.Plan.sort_order, models.Plan.id)).all()
    return {
        "plans": [_plan_dict(db, p) for p in plans],
        "features": _feature_options(db),
        "addons": [{"key": a.key, "name": a.name} for a in db.scalars(select(models.Addon)).all()],
        "can_edit": admin_rbac.has_permission(admin, "commerce.edit"),
    }


@router.get("/plans/{plan_id}")
def get_plan(plan_id: int, db: Session = Depends(get_db), admin: models.User = Depends(admin_rbac.require("commerce.view"))):
    p = db.get(models.Plan, plan_id)
    if p is None:
        raise HTTPException(status_code=404, detail="המסלול לא נמצא")
    return _plan_dict(db, p, with_history=True)


class VersionFields(BaseModel):
    price_agorot: int = Field(ge=0, le=100_000_00)
    guest_limit: Optional[int] = Field(default=None, ge=1, le=100000)
    event_limit: int = Field(default=1, ge=1, le=100)
    trial_days: int = Field(default=0, ge=0, le=365)
    features: list[str] = Field(default_factory=list)
    included_addons: list[str] = Field(default_factory=list)
    available_addons: list[str] = Field(default_factory=list)
    change_note: str = Field(default="", max_length=500)


class PlanCreate(VersionFields):
    key: str
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=1000)


def _check_version(db: Session, data: VersionFields) -> None:
    bad = set(data.features) - _feature_keys(db)
    if bad:
        raise HTTPException(status_code=400, detail=f"פיצ'ר לא מוכר: {', '.join(sorted(bad))}")
    addon_keys = set(db.scalars(select(models.Addon.key)).all())
    bad = (set(data.included_addons) | set(data.available_addons)) - addon_keys
    if bad:
        raise HTTPException(status_code=400, detail=f"תוסף לא מוכר: {', '.join(sorted(bad))}")


def _new_version(db: Session, plan: models.Plan, data: VersionFields, admin: models.User) -> models.PlanVersion:
    last = db.scalar(select(func.max(models.PlanVersion.version)).where(models.PlanVersion.plan_id == plan.id)) or 0
    v = models.PlanVersion(
        plan_id=plan.id, version=last + 1, price_agorot=data.price_agorot, guest_limit=data.guest_limit,
        event_limit=data.event_limit, trial_days=data.trial_days, features=sorted(set(data.features)),
        included_addons=sorted(set(data.included_addons)), available_addons=sorted(set(data.available_addons)),
        change_note=data.change_note, created_by_id=admin.id,
    )
    db.add(v)
    db.flush()
    plan.current_version_id = v.id
    plan.updated_at = datetime.utcnow()
    return v


@router.post("/plans", status_code=201)
def create_plan(payload: PlanCreate, request: Request, db: Session = Depends(get_db),
                admin: models.User = Depends(admin_rbac.require("commerce.edit"))):
    key = payload.key.strip().lower()
    if not KEY_RE.match(key):
        raise HTTPException(status_code=400, detail="מפתח: אותיות אנגליות קטנות, ספרות וקו תחתון")
    if db.scalar(select(models.Plan).where(models.Plan.key == key)):
        raise HTTPException(status_code=400, detail="כבר קיים מסלול עם המפתח הזה")
    _check_version(db, payload)
    p = models.Plan(key=key, name=payload.name.strip(), description=payload.description.strip(), status="draft")
    db.add(p)
    db.flush()
    _new_version(db, p, payload, admin)
    admin_audit.record(db, admin, domain="commerce", action="plan.create", summary=f"יצר/ה מסלול: {p.name}",
                       target_type="plan", target_id=p.id, target_label=p.name,
                       changes=[admin_audit.change("price", "מחיר", "", _ils(payload.price_agorot))], request=request)
    db.commit()
    return _plan_dict(db, p, with_history=True)


class PlanMetaWrite(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    description: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[Literal["active", "hidden", "draft", "archived"]] = None
    sort_order: Optional[int] = Field(default=None, ge=0, le=1000)


@router.patch("/plans/{plan_id}")
def update_plan_meta(plan_id: int, payload: PlanMetaWrite, request: Request, db: Session = Depends(get_db),
                     admin: models.User = Depends(admin_rbac.require("commerce.edit"))):
    p = db.get(models.Plan, plan_id)
    if p is None:
        raise HTTPException(status_code=404, detail="המסלול לא נמצא")
    changes = []
    labels = {"name": "שם", "description": "תיאור", "status": "סטטוס", "sort_order": "סדר"}
    for k, v in payload.model_dump(exclude_unset=True).items():
        before = getattr(p, k)
        if before != v:
            setattr(p, k, v.strip() if isinstance(v, str) and k != "status" else v)
            show = (lambda x: PLAN_STATUS.get(x, x)) if k == "status" else (lambda x: x)
            changes.append(admin_audit.change(k, labels[k], show(before), show(v)))
    if changes:
        p.updated_at = datetime.utcnow()
        admin_audit.record(db, admin, domain="commerce", action="plan.update", summary=f"עדכן/ה את המסלול {p.name}",
                           target_type="plan", target_id=p.id, target_label=p.name, changes=changes, request=request)
    db.commit()
    return _plan_dict(db, p, with_history=True)


@router.post("/plans/{plan_id}/versions", status_code=201)
def add_plan_version(plan_id: int, payload: VersionFields, request: Request, db: Session = Depends(get_db),
                     admin: models.User = Depends(admin_rbac.require("commerce.edit"))):
    """שינוי מחיר/תכולה = גרסה חדשה. אירועים קיימים נשארים על הגרסה שלהם."""
    p = db.get(models.Plan, plan_id)
    if p is None:
        raise HTTPException(status_code=404, detail="המסלול לא נמצא")
    _check_version(db, payload)
    before = db.get(models.PlanVersion, p.current_version_id) if p.current_version_id else None
    v = _new_version(db, p, payload, admin)
    changes = []
    if before is not None:
        changes.append(admin_audit.change("price", "מחיר", f"{_ils(before.price_agorot)} (v{before.version})",
                                          f"{_ils(v.price_agorot)} (v{v.version})"))
        added = set(v.features or []) - set(before.features or [])
        removed = set(before.features or []) - set(v.features or [])
        if added or removed:
            changes.append(admin_audit.change("features", "פיצ'רים",
                                              ", ".join(sorted(before.features or [])) or "—",
                                              ", ".join(sorted(v.features or [])) or "—"))
        if before.guest_limit != v.guest_limit:
            changes.append(admin_audit.change("guest_limit", "מגבלת מוזמנים", before.guest_limit, v.guest_limit))
    admin_audit.record(db, admin, domain="commerce", action="plan.version",
                       summary=f"יצר/ה גרסה {v.version} למסלול {p.name}", target_type="plan", target_id=p.id,
                       target_label=p.name, changes=changes, reason=payload.change_note, request=request)
    db.commit()
    commerce.invalidate()
    return _plan_dict(db, p, with_history=True)


# ── תוספים ────────────────────────────────────────────────────────────────

def _addon_dict(db: Session, a: models.Addon) -> dict:
    plans_with = []
    for p in db.scalars(select(models.Plan)).all():
        v = db.get(models.PlanVersion, p.current_version_id) if p.current_version_id else None
        if v is None:
            continue
        if a.key in (v.included_addons or []):
            plans_with.append({"plan": p.name, "mode": "included"})
        elif a.key in (v.available_addons or []):
            plans_with.append({"plan": p.name, "mode": "available"})
    return {"id": a.id, "key": a.key, "name": a.name, "description": a.description or "",
            "price_agorot": a.price_agorot, "status": a.status, "status_label": PLAN_STATUS.get(a.status, a.status),
            "standalone": a.standalone, "feature_key": a.feature_key or "", "plans": plans_with}


@router.get("/addons")
def list_addons(db: Session = Depends(get_db), admin: models.User = Depends(admin_rbac.require("commerce.view"))):
    return {"addons": [_addon_dict(db, a) for a in db.scalars(select(models.Addon).order_by(models.Addon.id)).all()],
            "features": _feature_options(db),
            "can_edit": admin_rbac.has_permission(admin, "commerce.edit")}


class AddonWrite(BaseModel):
    key: Optional[str] = None
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    description: Optional[str] = Field(default=None, max_length=1000)
    price_agorot: Optional[int] = Field(default=None, ge=0, le=100_000_00)
    status: Optional[Literal["active", "hidden", "draft"]] = None
    standalone: Optional[bool] = None
    feature_key: Optional[str] = None


@router.post("/addons", status_code=201)
def create_addon(payload: AddonWrite, request: Request, db: Session = Depends(get_db),
                 admin: models.User = Depends(admin_rbac.require("commerce.edit"))):
    key = (payload.key or "").strip().lower()
    if not KEY_RE.match(key) or not payload.name:
        raise HTTPException(status_code=400, detail="צריך שם ומפתח תקין")
    if db.scalar(select(models.Addon).where(models.Addon.key == key)):
        raise HTTPException(status_code=400, detail="כבר קיים תוסף עם המפתח הזה")
    if payload.feature_key and payload.feature_key not in _feature_keys(db):
        raise HTTPException(status_code=400, detail="פיצ'ר לא מוכר")
    a = models.Addon(key=key, name=payload.name.strip(), description=(payload.description or "").strip(),
                     price_agorot=payload.price_agorot or 0, status=payload.status or "draft",
                     standalone=True if payload.standalone is None else payload.standalone,
                     feature_key=payload.feature_key or "", updated_at=datetime.utcnow())
    db.add(a)
    db.flush()
    admin_audit.record(db, admin, domain="commerce", action="addon.create", summary=f"יצר/ה תוסף: {a.name}",
                       target_type="addon", target_id=a.id, target_label=a.name, request=request)
    db.commit()
    commerce.invalidate()
    return _addon_dict(db, a)


@router.patch("/addons/{addon_id}")
def update_addon(addon_id: int, payload: AddonWrite, request: Request, db: Session = Depends(get_db),
                 admin: models.User = Depends(admin_rbac.require("commerce.edit"))):
    a = db.get(models.Addon, addon_id)
    if a is None:
        raise HTTPException(status_code=404, detail="התוסף לא נמצא")
    data = payload.model_dump(exclude_unset=True)
    data.pop("key", None)
    if data.get("feature_key") and data["feature_key"] not in _feature_keys(db):
        raise HTTPException(status_code=400, detail="פיצ'ר לא מוכר")
    labels = {"name": "שם", "description": "תיאור", "price_agorot": "מחיר", "status": "סטטוס",
              "standalone": "ניתן לרכישה בנפרד", "feature_key": "פיצ'ר"}
    changes = []
    for k, v in data.items():
        before = getattr(a, k)
        if before != v:
            setattr(a, k, v)
            fmt = _ils if k == "price_agorot" else ((lambda x: PLAN_STATUS.get(x, x)) if k == "status" else (lambda x: x))
            changes.append(admin_audit.change(k, labels[k], fmt(before), fmt(v)))
    if changes:
        a.updated_at = datetime.utcnow()
        admin_audit.record(db, admin, domain="commerce", action="addon.update", summary=f"עדכן/ה את התוסף {a.name}",
                           target_type="addon", target_id=a.id, target_label=a.name, changes=changes, request=request)
    db.commit()
    commerce.invalidate()
    return _addon_dict(db, a)


# ── עמלות ─────────────────────────────────────────────────────────────────

def _fee_dict(r: models.FeeRule) -> dict:
    return {"id": r.id, "percent_bp": r.percent_bp, "percent": commerce.percent_display(r.percent_bp),
            "fixed_agorot": r.fixed_agorot, "min_agorot": r.min_agorot, "max_agorot": r.max_agorot,
            "direction": r.direction, "active": r.active, "note": r.note or "", "created_at": r.created_at,
            "created_by_id": r.created_by_id}


@router.get("/fees")
def get_fees(db: Session = Depends(get_db), admin: models.User = Depends(admin_rbac.require("commerce.view"))):
    commerce.invalidate()
    policy = commerce.gift_fee_policy()
    history = db.scalars(select(models.FeeRule).where(models.FeeRule.kind == "gift_card")
                         .order_by(models.FeeRule.id.desc()).limit(30)).all()
    examples = [10000, 50000, 100000, 200000]
    return {
        "current": {"percent_bp": policy.percent_bp, "percent": commerce.percent_display(policy.percent_bp),
                    "fixed_agorot": policy.fixed_agorot, "min_agorot": policy.min_agorot,
                    "max_agorot": policy.max_agorot, "source": policy.source, "direction": "added"},
        "examples": [{"gift": a, "fee": gift.fee_for(a), "total": a + gift.fee_for(a)} for a in examples],
        "history": [_fee_dict(r) for r in history],
        "can_edit": admin_rbac.has_permission(admin, "commerce.edit"),
    }


class FeeWrite(BaseModel):
    percent_bp: int = Field(ge=0, le=2000)
    fixed_agorot: int = Field(default=0, ge=0, le=10000)
    min_agorot: Optional[int] = Field(default=None, ge=0, le=100000)
    max_agorot: Optional[int] = Field(default=None, ge=0, le=1000000)
    reason: str = Field(min_length=3, max_length=500)


@router.put("/fees/gift")
def set_gift_fee(payload: FeeWrite, request: Request, db: Session = Depends(get_db),
                 admin: models.User = Depends(admin_rbac.require("commerce.edit"))):
    if payload.min_agorot is not None and payload.max_agorot is not None and payload.min_agorot > payload.max_agorot:
        raise HTTPException(status_code=400, detail="המינימום גדול מהמקסימום")
    commerce.invalidate()
    before = commerce.gift_fee_policy()
    for old in db.scalars(select(models.FeeRule).where(models.FeeRule.kind == "gift_card",
                                                       models.FeeRule.active.is_(True))).all():
        old.active = False
    db.add(models.FeeRule(kind="gift_card", scope_type="system", percent_bp=payload.percent_bp,
                          fixed_agorot=payload.fixed_agorot, min_agorot=payload.min_agorot,
                          max_agorot=payload.max_agorot, direction="added", active=True, note=payload.reason,
                          created_by_id=admin.id))

    def desc(bp, fixed, mn, mx) -> str:
        parts = [f"{commerce.percent_display(bp)}%"]
        if fixed:
            parts.append(f"+ {_ils(fixed)}")
        if mn is not None:
            parts.append(f"מינ' {_ils(mn)}")
        if mx is not None:
            parts.append(f"מקס' {_ils(mx)}")
        return " ".join(parts)

    admin_audit.record(
        db, admin, domain="commerce", action="fee.update", summary="שינה/תה את עמלת המתנות באשראי",
        target_type="fee", target_label="עמלת אשראי",
        changes=[admin_audit.change("gift_fee", "עמלת אשראי",
                                    desc(before.percent_bp, before.fixed_agorot, before.min_agorot, before.max_agorot),
                                    desc(payload.percent_bp, payload.fixed_agorot, payload.min_agorot, payload.max_agorot))],
        reason=payload.reason, request=request,
    )
    db.commit()
    commerce.invalidate()
    return get_fees(db, admin)


# ── קופונים ───────────────────────────────────────────────────────────────

def _coupon_dict(c: models.Coupon) -> dict:
    today = local_time.israel_date().isoformat()
    if not c.active:
        state = "כבוי"
    elif c.ends_on and c.ends_on < today:
        state = "פג תוקף"
    elif c.starts_on and c.starts_on > today:
        state = "עתידי"
    elif c.max_uses is not None and c.uses_count >= c.max_uses:
        state = "נוצל במלואו"
    else:
        state = "פעיל"
    return {"id": c.id, "code": c.code, "description": c.description or "", "kind": c.kind, "value": c.value,
            "starts_on": c.starts_on, "ends_on": c.ends_on, "max_uses": c.max_uses, "uses_count": c.uses_count,
            "plan_keys": c.plan_keys or [], "addon_keys": c.addon_keys or [], "audience": c.audience or "",
            "active": c.active, "state": state}


@router.get("/coupons")
def list_coupons(db: Session = Depends(get_db), admin: models.User = Depends(admin_rbac.require("commerce.view"))):
    return {"coupons": [_coupon_dict(c) for c in db.scalars(select(models.Coupon).order_by(models.Coupon.id.desc())).all()],
            "plans": [{"key": p.key, "name": p.name} for p in db.scalars(select(models.Plan)).all()],
            "addons": [{"key": a.key, "name": a.name} for a in db.scalars(select(models.Addon)).all()],
            "can_edit": admin_rbac.has_permission(admin, "commerce.edit")}


class CouponWrite(BaseModel):
    code: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=300)
    kind: Optional[Literal["percent", "amount"]] = None
    value: Optional[int] = Field(default=None, ge=1, le=100_000_00)
    starts_on: Optional[str] = None
    ends_on: Optional[str] = None
    max_uses: Optional[int] = Field(default=None, ge=1, le=1_000_000)
    plan_keys: Optional[list[str]] = None
    addon_keys: Optional[list[str]] = None
    audience: Optional[str] = Field(default=None, max_length=200)
    active: Optional[bool] = None


def _validate_coupon(c: models.Coupon) -> None:
    if c.kind == "percent" and not (1 <= c.value <= 100):
        raise HTTPException(status_code=400, detail="הנחה באחוזים: בין 1 ל-100")
    for d in (c.starts_on, c.ends_on):
        if d:
            try:
                datetime.strptime(d, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="תאריך לא תקין")
    if c.starts_on and c.ends_on and c.starts_on > c.ends_on:
        raise HTTPException(status_code=400, detail="תאריך הסיום לפני תאריך ההתחלה")


@router.post("/coupons", status_code=201)
def create_coupon(payload: CouponWrite, request: Request, db: Session = Depends(get_db),
                  admin: models.User = Depends(admin_rbac.require("commerce.edit"))):
    code = (payload.code or "").strip().upper()
    if not re.match(r"^[A-Z0-9_-]{3,30}$", code):
        raise HTTPException(status_code=400, detail="קוד: 3–30 תווים באנגלית, ספרות, מקף או קו תחתון")
    if db.scalar(select(models.Coupon).where(models.Coupon.code == code)):
        raise HTTPException(status_code=400, detail="הקוד כבר קיים")
    c = models.Coupon(code=code, description=payload.description or "", kind=payload.kind or "percent",
                      value=payload.value or 0, starts_on=payload.starts_on or "", ends_on=payload.ends_on or "",
                      max_uses=payload.max_uses, plan_keys=payload.plan_keys or [], addon_keys=payload.addon_keys or [],
                      audience=payload.audience or "", active=True if payload.active is None else payload.active,
                      created_by_id=admin.id, updated_at=datetime.utcnow())
    _validate_coupon(c)
    db.add(c)
    db.flush()
    admin_audit.record(db, admin, domain="commerce", action="coupon.create", summary=f"יצר/ה קופון {c.code}",
                       target_type="coupon", target_id=c.id, target_label=c.code, request=request)
    db.commit()
    return _coupon_dict(c)


@router.patch("/coupons/{coupon_id}")
def update_coupon(coupon_id: int, payload: CouponWrite, request: Request, db: Session = Depends(get_db),
                  admin: models.User = Depends(admin_rbac.require("commerce.edit"))):
    c = db.get(models.Coupon, coupon_id)
    if c is None:
        raise HTTPException(status_code=404, detail="הקופון לא נמצא")
    data = payload.model_dump(exclude_unset=True)
    data.pop("code", None)
    changes = []
    for k, v in data.items():
        before = getattr(c, k)
        if before != v:
            setattr(c, k, v if v is not None or k == "max_uses" else "")
            changes.append(admin_audit.change(k, k, before, v))
    _validate_coupon(c)
    if changes:
        c.updated_at = datetime.utcnow()
        admin_audit.record(db, admin, domain="commerce", action="coupon.update", summary=f"עדכן/ה את הקופון {c.code}",
                           target_type="coupon", target_id=c.id, target_label=c.code, changes=changes, request=request)
    db.commit()
    return _coupon_dict(c)


# ── רכישות לאירועים ("מנויים") ────────────────────────────────────────────

def _ent_dict(db: Session, ent: models.EventEntitlement) -> dict:
    v = db.get(models.PlanVersion, ent.plan_version_id)
    p = db.get(models.Plan, v.plan_id) if v else None
    e = db.get(models.Event, ent.event_id)
    current = db.get(models.PlanVersion, p.current_version_id) if p and p.current_version_id else None
    return {
        "id": ent.id, "event_id": ent.event_id,
        "event_label": (event_terms.hosts_names(e.event_type, e.groom_name, e.bride_name) or f"#{e.id}") if e else f"#{ent.event_id}",
        "event_date": e.event_date if e else "", "plan_id": p.id if p else None, "plan_name": p.name if p else "?",
        "version": v.version if v else None, "list_price_agorot": v.price_agorot if v else 0,
        "current_price_agorot": current.price_agorot if current else None,
        "on_old_version": bool(current and v and current.id != v.id),
        "price_agorot": ent.price_agorot, "addons": ent.addons or [], "coupon_code": ent.coupon_code or "",
        "status": ent.status, "status_label": ENT_STATUS.get(ent.status, ent.status), "source": ent.source,
        "starts_on": ent.starts_on, "trial_ends_on": ent.trial_ends_on, "renews_on": ent.renews_on,
        "note": ent.note or "", "created_at": ent.created_at,
    }


@router.get("/subscriptions")
def list_entitlements(
    status: str = "", q: str = Query("", max_length=100), limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0), db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("commerce.view")),
):
    E = models.EventEntitlement
    stmt = select(E)
    if status:
        stmt = stmt.where(E.status == status)
    if q.strip().isdigit():
        stmt = stmt.where(E.event_id == int(q.strip()))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(E.id.desc()).limit(limit).offset(offset)).all()
    plans = []
    for p in db.scalars(select(models.Plan).where(models.Plan.status != "archived")).all():
        v = db.get(models.PlanVersion, p.current_version_id) if p.current_version_id else None
        if v:
            plans.append({"id": p.id, "name": p.name, "version_id": v.id, "version": v.version,
                          "price_agorot": v.price_agorot, "trial_days": v.trial_days})
    return {"total": total, "limit": limit, "offset": offset, "items": [_ent_dict(db, r) for r in rows],
            "plans": plans, "can_edit": admin_rbac.has_permission(admin, "commerce.edit")}


class EntitlementCreate(BaseModel):
    event_id: int
    plan_version_id: int
    price_agorot: Optional[int] = Field(default=None, ge=0)
    addons: list[str] = Field(default_factory=list)
    trial: bool = False
    note: str = Field(default="", max_length=500)


@router.post("/subscriptions", status_code=201)
def create_entitlement(payload: EntitlementCreate, request: Request, db: Session = Depends(get_db),
                       admin: models.User = Depends(admin_rbac.require("commerce.edit"))):
    """קביעת מסלול לאירוע ידנית (הטבה / ניסיון / רכישה מחוץ למערכת). לא מחייב כסף."""
    e = db.get(models.Event, payload.event_id)
    v = db.get(models.PlanVersion, payload.plan_version_id)
    if e is None or v is None:
        raise HTTPException(status_code=404, detail="האירוע או המסלול לא נמצאו")
    existing = db.scalar(select(models.EventEntitlement).where(
        models.EventEntitlement.event_id == e.id, models.EventEntitlement.status.in_(("active", "trial", "paused"))))
    if existing is not None:
        raise HTTPException(status_code=409, detail="לאירוע כבר יש מסלול פעיל — קודם לבטל אותו")
    today = local_time.israel_date()
    from datetime import timedelta

    ent = models.EventEntitlement(
        event_id=e.id, plan_version_id=v.id, status="trial" if payload.trial and v.trial_days else "active",
        price_agorot=v.price_agorot if payload.price_agorot is None else payload.price_agorot,
        addons=sorted(set(payload.addons)), source="admin", starts_on=today.isoformat(),
        trial_ends_on=(today + timedelta(days=v.trial_days)).isoformat() if payload.trial and v.trial_days else "",
        note=payload.note, created_by_id=admin.id, updated_at=datetime.utcnow(),
    )
    db.add(ent)
    db.flush()
    p = db.get(models.Plan, v.plan_id)
    label = event_terms.hosts_names(e.event_type, e.groom_name, e.bride_name) or f"#{e.id}"
    admin_audit.record(db, admin, domain="commerce", action="entitlement.create",
                       summary=f"קבע/ה מסלול {p.name} (v{v.version}) לאירוע {label}", target_type="event",
                       target_id=e.id, target_label=label, event_id=e.id,
                       changes=[admin_audit.change("price", "מחיר", _ils(v.price_agorot), _ils(ent.price_agorot))],
                       reason=payload.note, request=request)
    db.commit()
    commerce.invalidate()
    features.invalidate()
    return _ent_dict(db, ent)


class EntitlementStatus(BaseModel):
    status: Literal["active", "paused", "cancelled"]
    reason: str = Field(min_length=3, max_length=500)


@router.post("/subscriptions/{ent_id}/status")
def set_entitlement_status(ent_id: int, payload: EntitlementStatus, request: Request, db: Session = Depends(get_db),
                           admin: models.User = Depends(admin_rbac.require("commerce.edit"))):
    ent = db.get(models.EventEntitlement, ent_id)
    if ent is None:
        raise HTTPException(status_code=404, detail="הרכישה לא נמצאה")
    if ent.status == "cancelled":
        raise HTTPException(status_code=400, detail="רכישה שבוטלה לא נפתחת מחדש — יוצרים חדשה")
    before = ent.status
    ent.status, ent.updated_at = payload.status, datetime.utcnow()
    if payload.status == "cancelled":
        ent.cancelled_at = datetime.utcnow()
    admin_audit.record(db, admin, domain="commerce", action="entitlement.status",
                       summary=f"עדכן/ה סטטוס מסלול לאירוע #{ent.event_id}", target_type="event",
                       target_id=ent.event_id, event_id=ent.event_id,
                       changes=[admin_audit.change("status", "סטטוס", ENT_STATUS.get(before, before), ENT_STATUS[payload.status])],
                       reason=payload.reason, request=request)
    db.commit()
    commerce.invalidate()
    features.invalidate()
    return _ent_dict(db, ent)
