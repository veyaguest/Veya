"""אימות משתמשים (שלב 8): גיבוב סיסמאות + טוקני JWT.

- סיסמאות נשמרות מגובבות עם bcrypt (לעולם לא בטקסט גלוי).
- אחרי התחברות מקבל המשתמש טוקן JWT חתום, שנשלח בכל בקשה בכותרת
  Authorization: Bearer <token>.
- התחברות עם גוגל (Supabase OAuth) — verify_supabase_token מאמת טוקן Supabase
  ו-find_or_create_google_user מוצא/יוצר את שורת המשתמש הפנימית. שאר המערכת
  ממשיכה לעבוד עם הטוקן הפנימי הרגיל (create_access_token) כרגיל — RLS,
  token_version, disabled וכו' לא משתנים.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
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

# כתובת פרויקט ה-Supabase — דרושה לאימות טוקני OAuth (התחברות עם גוגל).
# מגיע מ-Supabase Dashboard → Project Settings → API → Project URL
# (למשל https://xxxx.supabase.co, בלי / בסוף).
#
# חשוב: הפרויקט הזה עבר ל"JWT Signing Keys" של Supabase — טוקנים חתומים
# ב-ES256 (א-סימטרי) דרך מפתח פרטי שרק Supabase מחזיקה, לא ב-HS256 עם סוד
# משותף (כמו שהיה בעבר, ואיך שהקוד כאן עבד במקור — זה בדיוק מה שגרם ל-
# "טוקן התחברות לא תקין": jwt.decode עם algorithms=["HS256"] דוחה כל טוקן
# עם alg=ES256 מיידית, לפני שבכלל מנסה לאמת חתימה). האימות הנכון: שולפים
# את המפתח הציבורי המתאים (לפי kid בכותרת הטוקן) מ-JWKS הציבורי של
# Supabase (/.well-known/jwks.json) ומאמתים מולו — בדיוק כמו שכל ספריית
# JWT-verification סטנדרטית עושה מול idP חיצוני. אומת בפועל: הרצנו
# curl ישיר מול ה-JWKS endpoint וראינו {"alg":"ES256","kty":"EC",...}.
#
# אם ריק, /auth/google/exchange יחזיר 503 (התחברות גוגל כבויה) — כל שאר
# האימות (אימייל+סיסמה) ממשיך לעבוד ללא שינוי.
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_JWT_ALGORITHM = "ES256"
SUPABASE_JWT_AUDIENCE = "authenticated"

_supabase_jwks_client: Optional[PyJWKClient] = None


def _get_supabase_jwks_client() -> Optional[PyJWKClient]:
    """מחזיר PyJWKClient לפרויקט ה-Supabase (עצל, נבנה פעם אחת). ה-client
    שומר cache פנימי של המפתחות (ברירת מחדל: 300 שניות) כדי לא לפנות
    ל-Supabase בכל בקשה."""
    global _supabase_jwks_client
    if _supabase_jwks_client is None and SUPABASE_URL:
        _supabase_jwks_client = PyJWKClient(
            f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        )
    return _supabase_jwks_client

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


# ---------------------------------------------------------------------------
# התחברות עם גוגל דרך Supabase OAuth
# ---------------------------------------------------------------------------

def verify_supabase_token(token: str) -> dict:
    """מאמת טוקן Supabase דרך JWKS (ES256 א-סימטרי, aud='authenticated')
    ומחזיר את ה-payload.

    זורק HTTPException(401) על כל טוקן לא-תקין/פגוע/פג-תוקף — הודעה כללית
    בכוונה, כדי לא לחשוף פרטים על סיבת הכשל. גם כשל בשליפת ה-JWKS עצמו
    (רשת/Supabase לא זמין) מטופל כ-401 באותה הודעה — לא 500, כי מבחינת
    הקורא זו עדיין "לא הצלחנו לאמת את הזהות שלך", לא תקלת שרת פנימית.
    """
    client = _get_supabase_jwks_client()
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="התחברות עם גוגל אינה מוגדרת בשרת",
        )
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=[SUPABASE_JWT_ALGORITHM],
            audience=SUPABASE_JWT_AUDIENCE,
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="טוקן התחברות לא תקין",
        )


def _unusable_password_hash() -> str:
    """מייצר bcrypt hash של סוד אקראי (32 בייטים) — לשימוש במשתמש שנרשם דרך
    גוגל בלבד ואין לו סיסמה. אף אחד לא יכול להתחבר איתו (הסוד לא נשמר בשום
    מקום), אבל השדה password_hash הוא NOT NULL אז חייבים ערך כלשהו.
    """
    random_secret = secrets.token_urlsafe(32)
    return hash_password(random_secret)


def find_or_create_google_user(
    db: Session,
    *,
    email: str,
    display_name: str,
    avatar_url: str = "",
) -> tuple["models.User", bool]:
    """מוצא משתמש קיים לפי email, או יוצר חדש אם לא קיים. מחזיר (user, is_new).

    - אם המשתמש קיים: מחזיר אותו, ומעדכן avatar_url אם התקבל ערך חדש מגוגל
      (התמונה יכולה להתעדכן — נשמור אותה טרייה בכל כניסה). גם אם נרשם במקור
      בסיסמה — הוא יכול עכשיו להתחבר גם דרך גוגל (אותו email).
    - אם לא קיים: יוצר משתמש חדש עם password_hash לא-שמיש (ראו למעלה), display_name
      מגוגל, טלפון ריק, account_type=couple. הופך לאדמין רק אם זה המשתמש הראשון
      *או* אם ה-email תואם ל-ADMIN_EMAIL — בדיוק כמו register רגיל.
    - אימוץ אירועים יתומים (adopt_orphan_events) נעשה גם כאן, כדי לשמור על
      התנהגות זהה ל-register.

    avatar_url מוגדר דרך UPDATE נפרד אחרי היצירה (לא כפרמטר ל-register_user_row)
    כדי לא לגעת בפונקציית ה-DB app_register_user (SECURITY DEFINER) ב-Postgres —
    זה היה דורש מיגרציית SQL ידנית. עדכון self על עמודה רגילה עובר תחת RLS
    הרגיל (מדיניות users_update: "אני רואה/מעדכן רק את עצמי").

    הערה טכנית חשובה: ב-Postgres, find_user_by_email/register_user_row
    מחזירות אובייקט "transient" (נבנה ידנית מ-dict של תוצאת RPC, לא דרך
    session.query) — מוטציה עליו *לא* נתפסת ב-db.commit() כי הוא לא מחובר
    ל-unit-of-work של SQLAlchemy. לכן, כשצריך לשנות avatar_url, טוענים
    מחדש דרך db.get() (אותה שורה, בתוך אותה טרנזקציה — לא שאילתה חיצונית)
    כדי לקבל מופע שה-ORM באמת עוקב אחריו, ומחזירים אותו במקום המקורי.
    """
    existing = find_user_by_email(db, email)
    if existing is not None:
        set_request_identity(existing.id)
        if avatar_url and existing.avatar_url != avatar_url:
            tracked = db.get(models.User, existing.id)
            if tracked is not None:
                tracked.avatar_url = avatar_url
                existing = tracked
        return existing, False

    user_count = count_users(db)
    is_admin = user_count == 0 or (ADMIN_EMAIL != "" and email == ADMIN_EMAIL)

    user = register_user_row(
        db,
        email=email,
        password_hash=_unusable_password_hash(),
        display_name=display_name.strip() or email.split("@")[0],
        phone="",
        is_admin=is_admin,
        account_type="couple",
    )
    set_request_identity(user.id)
    if avatar_url:
        tracked = db.get(models.User, user.id)
        if tracked is not None:
            tracked.avatar_url = avatar_url
            user = tracked
    adopt_orphan_events(db, user.id)
    return user, True
