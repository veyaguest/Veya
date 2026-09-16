"""דרגות אדמין (RBAC) — מקור אמת יחיד למי מבין האדמינים רשאי לעשות מה.

שכבה **מעל** ``User.is_admin``, לא במקומו: ``get_current_admin`` ממשיך להיות
השער הראשון (משתמש שאינו אדמין — או טלפן — נדחה שם), והמודול הזה מוסיף רק
את השאלה "איזה אדמין". כך אף endpoint קיים לא נפתח בטעות למשתמש רגיל.

שלוש דרגות, בסדר עולה:

- ``support``     — תמיכה: משתמשים ואירועים, מרכז הטלפנים, כניסה לאירוע לתמיכה.
                    בלי מחיקות, בלי מסחר, בלי הגדרות מערכת.
- ``admin``       — ניהול שוטף: + הגדרות, אולמות, הודעות, טלפנים, יומן.
- ``super_admin`` — הכול: + מחיקות, כסף (מחירים/עמלות/Payout), עצירת חירום,
                    ניהול אדמינים.

תאימות לאחור: ``admin_role`` ריק אצל אדמין = ``super_admin``. כל האדמינים שהיו
לפני שהדרגות נולדו ממשיכים עם בדיוק אותה גישה מלאה שהייתה להם.
"""
from __future__ import annotations

from typing import Callable, Optional

from fastapi import Depends, HTTPException, status

from app import models
from app.auth import get_current_admin

SUPER_ADMIN = "super_admin"
ADMIN = "admin"
SUPPORT = "support"

ROLES = (SUPER_ADMIN, ADMIN, SUPPORT)
ROLE_RANK = {SUPPORT: 1, ADMIN: 2, SUPER_ADMIN: 3}
ROLE_LABELS = {
    SUPER_ADMIN: "Super Admin",
    ADMIN: "Admin",
    SUPPORT: "Support",
}

# הרשאה → הדרגה המינימלית. מפתח חדש שלא מופיע כאן נדחה (fail closed).
PERMISSIONS: dict[str, str] = {
    # ראשי
    "dashboard.view": SUPPORT,
    "search.use": SUPPORT,
    # משתמשים ואירועים
    "users.view": SUPPORT,
    "users.edit": SUPPORT,            # שם, טלפון
    "users.reset_password": SUPPORT,
    "users.impersonate": SUPPORT,     # כניסה לאירוע לצורך תמיכה — תמיד נרשם ביומן
    "users.account_type": ADMIN,      # שינוי סוג חשבון (כולל הפיכה לטלפן)
    "users.create": ADMIN,
    "users.disable": ADMIN,
    "users.delete": SUPER_ADMIN,
    "events.view": SUPPORT,
    "events.delete": SUPER_ADMIN,
    "admins.manage": SUPER_ADMIN,     # is_admin / admin_role — מניעת הסלמת הרשאות
    # טלפנים
    "calls.operate": SUPPORT,         # עבודה בתור, תיעוד תוצאה, הקצאת משימות
    "calls.manage": ADMIN,            # טלפנים, זמינות, הקצאה לאירוע
    # תוכן ותפעול
    "venues.view": SUPPORT,
    "venues.edit": ADMIN,
    "venues.delete": SUPER_ADMIN,
    "messages.edit": ADMIN,           # ספריית ההודעות וברירות המחדל
    "postponements.review": ADMIN,
    "audit.view": ADMIN,
    # שליטה ב-VEYA
    "settings.view": SUPPORT,
    "settings.edit": ADMIN,
    "settings.critical": SUPER_ADMIN,  # עצירת חירום, מצב WhatsApp
    "features.edit": ADMIN,
    "overrides.edit": ADMIN,
    # מסחר
    "commerce.view": ADMIN,
    "commerce.edit": SUPER_ADMIN,      # מחירים, עמלות, מסלולים, קופונים
    "payouts.review": SUPER_ADMIN,     # כסף אמיתי של בעלי אירועים
}


def role_of(user: Optional[models.User]) -> Optional[str]:
    """הדרגה האפקטיבית של המשתמש, או ``None`` אם הוא לא אדמין בכלל."""
    if user is None or not getattr(user, "is_admin", False):
        return None
    role = (getattr(user, "admin_role", None) or "").strip()
    return role if role in ROLE_RANK else SUPER_ADMIN


def has_permission(user: Optional[models.User], permission: str) -> bool:
    role = role_of(user)
    needed = PERMISSIONS.get(permission)
    if role is None or needed is None:
        return False
    return ROLE_RANK[role] >= ROLE_RANK[needed]


def permissions_for(user: models.User) -> list[str]:
    return sorted(p for p in PERMISSIONS if has_permission(user, p))


def can_grant(actor: models.User, role: Optional[str]) -> bool:
    """אדמין לעולם לא מעניק דרגה גבוהה משלו."""
    actor_role = role_of(actor)
    if actor_role is None:
        return False
    if role is None:
        return True
    return role in ROLE_RANK and ROLE_RANK[actor_role] >= ROLE_RANK[role]


def require(permission: str) -> Callable[..., models.User]:
    """Dependency: אדמין עם ההרשאה הזו, אחרת 403.

    ``get_current_admin`` רץ קודם — לא-אדמין נדחה שם כמו תמיד.
    """
    if permission not in PERMISSIONS:  # טעות מפתח נתפסת בעליית השרת, לא בייצור
        raise ValueError(f"הרשאת אדמין לא מוכרת: {permission}")

    def dependency(admin: models.User = Depends(get_current_admin)) -> models.User:
        if not has_permission(admin, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="אין לך הרשאה לפעולה הזו",
            )
        return admin

    return dependency


def ensure(user: models.User, permission: str) -> None:
    """בדיקה בתוך endpoint — לשדות רגישים בבקשה משולבת (למשל PATCH משתמש)."""
    if not has_permission(user, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="אין לך הרשאה לפעולה הזו",
        )
