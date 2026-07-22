"""אימות משתמשים (שלב 8): גיבוב סיסמאות + טוקני JWT.

- סיסמאות נשמרות מגובבות עם bcrypt (לעולם לא בטקסט גלוי).
- אחרי התחברות מקבל המשתמש טוקן JWT חתום, שנשלח בכל בקשה בכותרת
  Authorization: Bearer <token>.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import models
from app.database import IS_POSTGRES, get_db, set_request_identity

# מפתח חתימת הטוקנים. בפרודקשן חובה להגדיר JWT_SECRET אמיתי במשתני הסביבה;
# בפיתוח יש ברירת-מחדל כדי שהמערכת תרוץ מיד.
_DEV_JWT_SECRET = "veya-dev-secret-change-me"
JWT_SECRET = os.getenv("JWT_SECRET", _DEV_JWT_SECRET)
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30

# בסביבת ייצור (VEYA_ENV=production) אסור לרוץ עם מפתח ברירת המחדל — כל מי
# שיודע אותו יכול לזייף התחברות. במקרה כזה מפילים את עליית השרת במפורש.
if os.getenv("VEYA_ENV", "").strip().lower() == "production" and JWT_SECRET == _DEV_JWT_SECRET:
    raise RuntimeError(
        "JWT_SECRET חייב להיות מוגדר (ולא ברירת המחדל) כאשר VEYA_ENV=production. "
        "הגדירו משתנה סביבה JWT_SECRET עם מחרוזת אקראית וסודית."
    )

# אימייל שיקבל הרשאת אדמין אוטומטית בהרשמה (אופציונלי).
ADMIN_EMAIL = (os.getenv("ADMIN_EMAIL", "") or "").strip().lower()

_bearer = HTTPBearer(auto_error=False)


def find_user_by_email(db: Session, email: str) -> Optional["models.User"]:
    """שולף משתמש לפי אימייל מדויק — לשימוש ב-register/login, *לפני* שיש
    זהות מחוברת (עדיין אין ``app.current_user_id``).

    ב-Postgres עם RLS, מדיניות ``users_select`` הרגילה ("אני רואה רק את
    עצמי") הייתה חוסמת שאילתה כזו לגמרי. לכן על Postgres קוראים לפונקציית
    ה-DB ``app_user_by_email`` (SECURITY DEFINER, ראו backend/rls/) שעוקפת
    RLS בכוונה, ומחזירה שורה בודדת בלבד לפי אימייל מדויק — לא חשיפה כללית.
    ב-SQLite (פיתוח, בלי RLS) פשוט שאילתת ORM רגילה.
    """
    if not IS_POSTGRES:
        return db.scalars(select(models.User).where(models.User.email == email)).first()

    row = db.execute(
        text("SELECT * FROM app_user_by_email(:email)"), {"email": email}
    ).mappings().first()
    if row is None or row.get("id") is None:
        return None
    return models.User(**dict(row))


def count_users(db: Session) -> int:
    """סופר את כלל המשתמשים — לשימוש ב-register() כדי לקבוע "האם זה המשתמש
    הראשון" (ואז הוא הופך לאדמין-על). ב-Postgres, ``SELECT COUNT(*) FROM
    users`` רגיל תמיד מסונן ע"י ``users_select`` ("אני רואה רק את עצמי") —
    ובלי זהות מחוברת (המצב לפני הרשמה), זה מחזיר 0 *תמיד*, גם כשיש כבר
    עשרות משתמשים — מה שהיה הופך כל הרשמה חדשה לאדמין-על בטעות. לכן, על
    Postgres, עוברים דרך ``app_count_users`` (SECURITY DEFINER).
    """
    if not IS_POSTGRES:
        return db.scalar(select(func.count()).select_from(models.User)) or 0
    return db.execute(text("SELECT app_count_users()")).scalar() or 0


def register_user_row(
    db: Session,
    *,
    email: str,
    password_hash: str,
    display_name: str,
    phone: str,
    is_admin: bool,
    account_type: str,
) -> "models.User":
    """יוצר שורת משתמש חדשה ומחזיר אותה.

    ב-Postgres עם RLS: SQLAlchemy מבצע כל INSERT עם ``RETURNING`` (כדי לקבל
    ``id``/``created_at``), ו-Postgres דורש שהשורה המוחזרת תעבור גם את
    מדיניות ה-SELECT — לא רק את ה-WITH CHECK של מדיניות ה-INSERT. בהרשמה
    עדיין אין זהות מחוברת (``app_current_user_id()`` הוא NULL), אז
    ``users_select`` ("אני רואה רק את עצמי") נכשל וה-INSERT כולו נדחה, גם
    ש-``users_insert`` עצמה פתוחה לגמרי (``WITH CHECK (true)``). לכן
    עוברים דרך ``app_register_user`` (SECURITY DEFINER) שעוקפת את זה.
    התגלה בבדיקת Staging אמיתית מול Postgres — לא ניתן היה לגלות מול
    SQLite, ששם RLS הוא no-op לגמרי.
    """
    if not IS_POSTGRES:
        user = models.User(
            email=email, password_hash=password_hash, display_name=display_name,
            phone=phone, is_admin=is_admin, account_type=account_type,
        )
        db.add(user)
        db.flush()
        return user

    row = db.execute(
        text("SELECT * FROM app_register_user(:email, :password_hash, :display_name, :phone, :is_admin, :account_type)"),
        {
            "email": email, "password_hash": password_hash, "display_name": display_name,
            "phone": phone, "is_admin": is_admin, "account_type": account_type,
        },
    ).mappings().first()
    return models.User(**dict(row))


def record_login_event(db: Session, user_id: int, ip: Optional[str], user_agent: Optional[str]) -> None:
    """רושם רשומת התחברות (היסטוריית כניסות). ב-Postgres דרך פונקציית DB
    ייעודית — אותה סיבה בדיוק כמו ``register_user_row``: בזמן ה-login עדיין
    אין ``set_request_identity`` (הוא נקרא רק אחרי בדיקת הסיסמה/הנפקת
    הטוקן), ומדיניות ``login_events_select`` הייתה חוסמת את ה-RETURNING.
    """
    if IS_POSTGRES:
        db.execute(
            text("SELECT app_record_login_event(:uid, :ip, :ua)"),
            {"uid": user_id, "ip": ip, "ua": user_agent},
        )
        return
    db.add(models.LoginEvent(user_id=user_id, ip=ip, user_agent=user_agent))


def adopt_orphan_events(db: Session, user_id: int) -> None:
    """משייך אירועים "יתומים" (בלי owner_id) למשתמש שנרשם — מיגרציה חד-פעמית
    מהמצב הישן של אירוע יחיד. ב-Postgres דרך פונקציית DB ייעודית כי RLS
    היה חוסם למשתמש חדש (לא-אדמין) לראות/לעדכן שורות בלי owner_id משלו.
    """
    if IS_POSTGRES:
        db.execute(text("SELECT app_adopt_orphan_events(:uid)"), {"uid": user_id})
        return
    orphans = db.scalars(select(models.Event).where(models.Event.owner_id.is_(None))).all()
    for ev in orphans:
        ev.owner_id = user_id


def hash_password(password: str) -> str:
    """מגבב סיסמה עם bcrypt ומחזיר מחרוזת לשמירה ב-DB."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """בודק אם הסיסמה תואמת לגיבוב השמור."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(user: "models.User") -> str:
    """יוצר טוקן JWT חתום עבור המשתמש, כולל גרסת הטוקן הנוכחית (``tv``)."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "tv": user.token_version,
        "iat": now,
        "exp": now + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> Optional[dict]:
    """מפענח טוקן ומחזיר את תוכנו (sub + tv), או None אם לא תקין."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.User:
    """Dependency: מחזיר את המשתמש המחובר לפי טוקן ה-Bearer, או 401."""
    err = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="נדרשת התחברות",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None or not creds.credentials:
        raise err
    payload = _decode_token(creds.credentials)
    if payload is None:
        raise err
    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise err
    # קובעים את זהות הבקשה מתוך הטוקן *לפני* השאילתה הראשונה, כדי שגם שליפת
    # רשומת המשתמש עצמה תרוץ תחת RLS (מדיניות "כל אחד רואה רק את עצמו").
    set_request_identity(user_id)
    user = db.get(models.User, user_id)
    if user is None:
        raise err
    # בדיקת גרסת הטוקן: אם המשתמש העלה גרסה (יציאה/שינוי סיסמה), טוקן ישן נפסל.
    if payload.get("tv") != user.token_version:
        raise err
    # חשבון שהושבת ע"י אדמין — הטוקן בטל (הפעלת ההשבתה מעלה גם את גרסת הטוקן,
    # אבל בודקים גם כאן במפורש כדי לא להסתמך רק על כך).
    if user.disabled:
        raise err
    return user


def get_current_admin(
    user: models.User = Depends(get_current_user),
) -> models.User:
    """Dependency: מוודא שהמשתמש המחובר הוא אדמין (הבעלים), אחרת 403."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="נדרשת הרשאת מנהל",
        )
    return user
