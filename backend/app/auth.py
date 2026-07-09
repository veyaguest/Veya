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
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

# מפתח חתימת הטוקנים. בפרודקשן חובה להגדיר JWT_SECRET במשתני הסביבה;
# בפיתוח יש ברירת-מחדל כדי שהמערכת תרוץ מיד.
JWT_SECRET = os.getenv("JWT_SECRET", "veya-dev-secret-change-me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = 30

_bearer = HTTPBearer(auto_error=False)


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


def create_access_token(user_id: int) -> str:
    """יוצר טוקן JWT חתום עבור המשתמש."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(days=JWT_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> Optional[int]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
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
    user_id = _decode_token(creds.credentials)
    if user_id is None:
        raise err
    user = db.get(models.User, user_id)
    if user is None:
        raise err
    return user
