"""כללי המערכת ופיצ'רים והרשאות — API.

- ``/admin/rules``                 ערכי מערכת (שמירה מרוכזת: שינויים → בדיקה → שמירה).
- ``/admin/rules/events/{id}``     Overrides לאירוע, עם מקור כל ערך.
- ``/admin/features``              סטטוס פיצ'רים, כללים למשתמש/אירוע, פיצ'ר חדש.

כל שינוי נרשם ביומן האדמין עם לפני/אחרי. הגדרה קריטית (עצירת חירום)
דורשת ``settings.critical``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import admin_audit, admin_rbac, call_ops, event_terms, features, messaging, models
from app import settings_registry as sr
from app.database import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


def _show(setting: sr.Setting, value: Any) -> str:
    if setting.type == "bool":
        return "כן" if value else "לא"
    return f"{value}{' ' + setting.unit if setting.unit else ''}"


def _setting_row(s: sr.Setting, event_id: Optional[int] = None) -> dict:
    r = sr.resolve(s.key, event_id)
    value = r.value
    if s.key == "whatsapp.mode":
        value = messaging.current_mode()
    return {
        "key": s.key, "domain": s.domain, "label": s.label, "help": s.help, "type": s.type,
        "min": s.min, "max": s.max, "choices": list(s.choices), "unit": s.unit, "live": s.live,
        "critical": s.critical, "readonly_reason": s.readonly_reason, "event_override": s.event_override,
        "default": s.default, "value": value, "source": r.source if s.key != "whatsapp.mode" else "env",
        "system_value": r.system_value,
    }


@router.get("/rules")
def get_rules(admin: models.User = Depends(admin_rbac.require("settings.view"))):
    sr.invalidate()
    return {
        "domains": sr.DOMAINS,
        "settings": [_setting_row(s) for s in sr.SETTINGS.values()],
        "can_edit": admin_rbac.has_permission(admin, "settings.edit"),
        "can_edit_critical": admin_rbac.has_permission(admin, "settings.critical"),
    }


class RulesWrite(BaseModel):
    changes: dict[str, Any] = Field(min_length=1)
    reason: str = Field(default="", max_length=500)


@router.put("/rules")
def save_rules(
    payload: RulesWrite,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("settings.edit")),
):
    """שמירה מרוכזת. ערך ששווה לברירת המחדל בקוד — מוחק את השורה (חזרה לברירת מחדל)."""
    now = datetime.utcnow()
    audit_changes = []
    validated: dict[str, Any] = {}
    for key, raw in payload.changes.items():
        s = sr.SETTINGS.get(key)
        if s is None:
            raise HTTPException(status_code=400, detail=f"הגדרה לא מוכרת: {key}")
        if not s.live:
            raise HTTPException(status_code=400, detail=f"'{s.label}' לא ניתנת לשינוי מכאן: {s.readonly_reason}")
        if s.critical:
            admin_rbac.ensure(admin, "settings.critical")
        try:
            validated[key] = sr.validate(s, raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{s.label}: {exc}")
    for key, value in validated.items():
        s = sr.SETTINGS[key]
        row = db.scalar(select(models.SystemSetting).where(models.SystemSetting.key == key))
        before = row.value if row is not None else s.default
        if before == value:
            continue
        if value == s.default:
            if row is not None:
                db.delete(row)
        else:
            if row is None:
                row = models.SystemSetting(key=key)
                db.add(row)
            row.value, row.updated_by_id, row.updated_at = value, admin.id, now
        audit_changes.append(admin_audit.change(key, s.label, _show(s, before), _show(s, value)))
    if audit_changes:
        critical = any(sr.SETTINGS[c["field"]].critical for c in audit_changes)
        admin_audit.record(
            db, admin, domain="settings", action="settings.update",
            summary=(
                "שינה/תה את מצב עצירת החירום של WhatsApp" if critical
                else f"עדכן/ה {len(audit_changes)} כללי מערכת"
            ),
            target_type="system_settings", changes=audit_changes, reason=payload.reason, request=request,
        )
    db.commit()
    sr.invalidate()
    call_ops.invalidate_sync_cache()
    return {"updated": len(audit_changes), "settings": [_setting_row(s) for s in sr.SETTINGS.values()]}


# ── Overrides לאירוע ──────────────────────────────────────────────────────

def _feature_row_for_event(key: str, event: models.Event) -> dict:
    f = features.BUILTIN[key]
    d = features.decide(key, event)
    effective = d.enabled
    if key == "gifts" and effective is None:
        from app import gift_eligibility

        effective = gift_eligibility.is_eligible(event)
    return {
        "key": key, "label": f.label, "enabled": bool(effective) if effective is not None else True,
        "source": d.source, "controllable": f.controllable and "event" in f.rule_scopes,
    }


@router.get("/rules/events/{event_id}")
def event_overrides(
    event_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("settings.view")),
):
    event = db.get(models.Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="האירוע לא נמצא")
    sr.invalidate()
    features.invalidate()
    return {
        "event_id": event_id,
        "track_active": bool(event.rsvp_track_active),
        "settings": [_setting_row(s, event_id) for s in sr.SETTINGS.values() if s.event_override and s.live],
        "features": [_feature_row_for_event(k, event) for k in ("calls", "gifts")],
        "can_edit": admin_rbac.has_permission(admin, "overrides.edit"),
    }


class OverridesWrite(BaseModel):
    changes: dict[str, Any] = Field(min_length=1)       # None = איפוס לברירת המערכת
    reason: str = Field(default="", max_length=500)


@router.put("/rules/events/{event_id}")
def save_event_overrides(
    event_id: int,
    payload: OverridesWrite,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("overrides.edit")),
):
    event = db.get(models.Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="האירוע לא נמצא")
    label = event_terms.hosts_names(event.event_type, event.groom_name, event.bride_name) or f"#{event_id}"
    now = datetime.utcnow()
    O = models.SettingOverride
    audit_changes = []
    for key, raw in payload.changes.items():
        s = sr.SETTINGS.get(key)
        if s is None or not s.event_override or not s.live:
            raise HTTPException(status_code=400, detail=f"אי אפשר לקבוע Override ל-{key}")
        row = db.scalar(select(O).where(O.scope_type == "event", O.scope_id == event_id, O.key == key))
        system_value = sr.resolve(key).value
        before = row.value if row is not None else system_value
        if raw is None:
            if row is not None:
                db.delete(row)
                audit_changes.append(admin_audit.change(
                    key, s.label, f"{_show(s, before)} (Override)", f"{_show(s, system_value)} (ברירת המערכת)",
                ))
            continue
        try:
            value = sr.validate(s, raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{s.label}: {exc}")
        if row is None:
            if value == system_value:
                continue
            row = O(scope_type="event", scope_id=event_id, key=key, created_by_id=admin.id, created_at=now)
            db.add(row)
        if row.value == value:
            continue
        row.value, row.reason, row.updated_at = value, payload.reason, now
        audit_changes.append(admin_audit.change(key, s.label, _show(s, before), f"{_show(s, value)} (Override)"))
    if audit_changes:
        admin_audit.record(
            db, admin, domain="overrides", action="event_override.update",
            summary=f"עדכן/ה Overrides לאירוע {label}", target_type="event", target_id=event_id,
            target_label=label, event_id=event_id, changes=audit_changes, reason=payload.reason, request=request,
        )
    db.commit()
    sr.invalidate()
    call_ops.invalidate_sync_cache()
    return event_overrides(event_id, db, admin)


# ── פיצ'רים ───────────────────────────────────────────────────────────────

STATUS_LABELS = {"active": "פעיל", "beta": "בטא", "off": "כבוי"}


def _scope_label(db: Session, scope_type: str, scope_id: int) -> str:
    if scope_type == "event":
        e = db.get(models.Event, scope_id)
        return (event_terms.hosts_names(e.event_type, e.groom_name, e.bride_name) or f"אירוע #{scope_id}") if e else f"אירוע #{scope_id} (נמחק)"
    if scope_type == "user":
        u = db.get(models.User, scope_id)
        return (u.display_name or u.email) if u else f"משתמש #{scope_id} (נמחק)"
    return f"{scope_type} #{scope_id}"


def _feature_rows(db: Session) -> list[dict]:
    features.invalidate()
    flags = {f.key: f for f in db.scalars(select(models.FeatureFlag)).all()}
    rules_by_key: dict[str, list[dict]] = {}
    for r in db.scalars(select(models.FeatureRule).order_by(models.FeatureRule.id)).all():
        rules_by_key.setdefault(r.feature_key, []).append({
            "id": r.id, "scope_type": r.scope_type, "scope_id": r.scope_id,
            "scope_label": _scope_label(db, r.scope_type, r.scope_id), "enabled": r.enabled, "note": r.note or "",
        })
    rows = []
    for key, f in features.BUILTIN.items():
        flag = flags.get(key)
        if flag is not None:
            status, source = flag.status, "admin"
        elif key == "gifts":
            from app import gift_eligibility

            status, source = ("active" if gift_eligibility.service_switch_on() else "off"), "env"
        else:
            status, source = ("active" if f.default_enabled else "off"), "default"
        rows.append({
            "key": key, "label": f.label, "description": f.description, "builtin": True,
            "controllable": f.controllable, "reason": f.reason, "rule_scopes": list(f.rule_scopes),
            "status": status, "status_label": STATUS_LABELS.get(status, status), "source": source,
            "rules": rules_by_key.get(key, []), "consumed": True,
        })
    for key, flag in flags.items():
        if key in features.BUILTIN:
            continue
        rows.append({
            "key": key, "label": flag.label or key, "description": flag.description or "", "builtin": False,
            "controllable": True, "reason": "", "rule_scopes": ["event", "user"], "status": flag.status,
            "status_label": STATUS_LABELS.get(flag.status, flag.status), "source": "admin",
            "rules": rules_by_key.get(key, []), "consumed": False,
        })
    return rows


@router.get("/features")
def list_features(
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("settings.view")),
):
    return {"features": _feature_rows(db), "can_edit": admin_rbac.has_permission(admin, "features.edit")}


class FeatureStatusWrite(BaseModel):
    status: Literal["active", "beta", "off"]
    reason: str = Field(default="", max_length=500)


@router.put("/features/{key}")
def set_feature_status(
    key: str,
    payload: FeatureStatusWrite,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("features.edit")),
):
    builtin = features.BUILTIN.get(key)
    flag = db.scalar(select(models.FeatureFlag).where(models.FeatureFlag.key == key))
    if builtin is None and flag is None:
        raise HTTPException(status_code=404, detail="הפיצ'ר לא נמצא")
    if builtin is not None and not builtin.controllable:
        raise HTTPException(status_code=400, detail=builtin.reason or "את הפיצ'ר הזה אי אפשר לכבות מהאדמין")
    if key == "gifts" and payload.status == "active":
        admin_rbac.ensure(admin, "commerce.edit")   # פתיחת שירות כסף לכולם — Super Admin בלבד
    before = next((r for r in _feature_rows(db) if r["key"] == key), None)
    if flag is None:
        flag = models.FeatureFlag(key=key, label=builtin.label if builtin else key, created_by_id=admin.id)
        db.add(flag)
    flag.status, flag.updated_at = payload.status, datetime.utcnow()
    admin_audit.record(
        db, admin, domain="features", action="feature.status",
        summary=f"שינה/תה את סטטוס הפיצ'ר '{flag.label}'", target_type="feature", target_id=key,
        target_label=flag.label,
        changes=[admin_audit.change("status", "סטטוס", before["status_label"] if before else "—", STATUS_LABELS[payload.status])],
        reason=payload.reason, request=request,
    )
    db.commit()
    features.invalidate()
    call_ops.invalidate_sync_cache()
    return {"features": _feature_rows(db)}


class FeatureCreate(BaseModel):
    key: str
    label: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=500)
    status: Literal["active", "beta", "off"] = "off"


@router.post("/features", status_code=201)
def create_feature(
    payload: FeatureCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("features.edit")),
):
    """פיצ'ר חדש = דגל. הוא נכנס לתוקף ברגע שקוד כלשהו ישאל עליו
    (``features.enabled(key, event)``) — עד אז הוא רק מתועד כאן."""
    key = payload.key.strip().lower()
    if not features.KEY_RE.match(key):
        raise HTTPException(status_code=400, detail="מפתח: אותיות אנגליות קטנות, ספרות וקו תחתון (3–40)")
    if key in features.BUILTIN or db.scalar(select(models.FeatureFlag).where(models.FeatureFlag.key == key)):
        raise HTTPException(status_code=400, detail="כבר קיים פיצ'ר עם המפתח הזה")
    db.add(models.FeatureFlag(
        key=key, label=payload.label.strip(), description=payload.description.strip(), status=payload.status,
        created_by_id=admin.id, updated_at=datetime.utcnow(),
    ))
    admin_audit.record(
        db, admin, domain="features", action="feature.create", summary=f"הוסיף/ה פיצ'ר: {payload.label}",
        target_type="feature", target_id=key, target_label=payload.label, request=request,
    )
    db.commit()
    features.invalidate()
    return {"features": _feature_rows(db)}


class RuleWrite(BaseModel):
    scope_type: Literal["event", "user"]
    scope_id: int
    enabled: bool
    note: str = Field(default="", max_length=300)


@router.post("/features/{key}/rules", status_code=201)
def add_feature_rule(
    key: str,
    payload: RuleWrite,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("overrides.edit")),
):
    builtin = features.BUILTIN.get(key)
    if builtin is None and db.scalar(select(models.FeatureFlag).where(models.FeatureFlag.key == key)) is None:
        raise HTTPException(status_code=404, detail="הפיצ'ר לא נמצא")
    if builtin is not None and payload.scope_type not in builtin.rule_scopes:
        raise HTTPException(status_code=400, detail="לפיצ'ר הזה אין עדיין חריגה ברמה הזו")
    target = db.get(models.Event if payload.scope_type == "event" else models.User, payload.scope_id)
    if target is None:
        raise HTTPException(status_code=404, detail="היעד לא נמצא")
    if key == "gifts" and payload.enabled:
        admin_rbac.ensure(admin, "commerce.edit")
    R = models.FeatureRule
    rule = db.scalar(select(R).where(R.feature_key == key, R.scope_type == payload.scope_type, R.scope_id == payload.scope_id))
    before = ("פתוח" if rule.enabled else "סגור") if rule else "לפי ברירת המחדל"
    if rule is None:
        rule = R(feature_key=key, scope_type=payload.scope_type, scope_id=payload.scope_id, created_by_id=admin.id)
        db.add(rule)
    rule.enabled, rule.note = payload.enabled, payload.note
    label = _scope_label(db, payload.scope_type, payload.scope_id)
    flabel = builtin.label if builtin else key
    admin_audit.record(
        db, admin, domain="features", action="feature.rule",
        summary=f"{'פתח/ה' if payload.enabled else 'סגר/ה'} את '{flabel}' ל{label}",
        target_type=payload.scope_type, target_id=payload.scope_id, target_label=label,
        event_id=payload.scope_id if payload.scope_type == "event" else None,
        changes=[admin_audit.change("rule", flabel, before, "פתוח" if payload.enabled else "סגור")],
        reason=payload.note, request=request,
    )
    db.commit()
    features.invalidate()
    call_ops.invalidate_sync_cache()
    return {"features": _feature_rows(db)}


@router.delete("/features/{key}/rules/{rule_id}")
def delete_feature_rule(
    key: str,
    rule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: models.User = Depends(admin_rbac.require("overrides.edit")),
):
    rule = db.get(models.FeatureRule, rule_id)
    if rule is None or rule.feature_key != key:
        raise HTTPException(status_code=404, detail="הכלל לא נמצא")
    label = _scope_label(db, rule.scope_type, rule.scope_id)
    flabel = features.BUILTIN[key].label if key in features.BUILTIN else key
    admin_audit.record(
        db, admin, domain="features", action="feature.rule_delete",
        summary=f"הסיר/ה חריגה של '{flabel}' עבור {label}", target_type=rule.scope_type, target_id=rule.scope_id,
        target_label=label, event_id=rule.scope_id if rule.scope_type == "event" else None,
        changes=[admin_audit.change("rule", flabel, "פתוח" if rule.enabled else "סגור", "לפי ברירת המחדל")],
        request=request,
    )
    db.delete(rule)
    db.commit()
    features.invalidate()
    call_ops.invalidate_sync_cache()
    return {"features": _feature_rows(db)}
