"""Router התחברות (שלב 8): הרשמה, כניסה, ופרטי המשתמש המחובר."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.database import get_db
from app.ratelimit import auth_limiter, client_ip

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.TokenResponse, status_code=201)
def register(payload: schemas.UserCreate, request: Request, db: Session = Depends(get_db)):
    """יוצר משתמש חדש ומחזיר טוקן התחברות.

    המשתמש הראשון שנרשם "מאמץ" את האירוע הקיים (owner_id ריק) כדי שהנתונים
    שכבר הוזנו לא יאבדו.
    """
    ip = client_ip(request)
    auth_limiter.check(ip)
    exists = db.scalars(
        select(models.User).where(models.User.email == payload.email)
    ).first()
    if exists is not None:
        auth_limiter.record_fail(ip)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="כתובת האימייל כבר רשומה במערכת",
        )

    # הבעלים = המשתמש הראשון שנרשם (או אימייל שהוגדר ב-ADMIN_EMAIL) → אדמין.
    user_count = db.scalar(select(func.count()).select_from(models.User)) or 0
    is_admin = user_count == 0 or (
        auth.ADMIN_EMAIL != "" and payload.email == auth.ADMIN_EMAIL
    )

    user = models.User(
        email=payload.email,
        password_hash=auth.hash_password(payload.password),
        display_name=payload.display_name.strip(),
        is_admin=is_admin,
    )
    db.add(user)
    db.flush()  # מקבל id לפני שיוך אירועים

    # אימוץ אירועים "יתומים" (בלי בעלים) — מיגרציה מהמצב הישן של אירוע יחיד.
    orphans = db.scalars(
        select(models.Event).where(models.Event.owner_id.is_(None))
    ).all()
    for ev in orphans:
        ev.owner_id = user.id

    db.commit()
    db.refresh(user)
    token = auth.create_access_token(user)
    return schemas.TokenResponse(access_token=token, user=user)


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    """מאמת אימייל+סיסמה ומחזיר טוקן."""
    ip = client_ip(request)
    auth_limiter.check(ip)
    user = db.scalars(
        select(models.User).where(models.User.email == payload.email)
    ).first()
    if user is None or not auth.verify_password(payload.password, user.password_hash):
        auth_limiter.record_fail(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="אימייל או סיסמה שגויים",
        )
    token = auth.create_access_token(user)
    return schemas.TokenResponse(access_token=token, user=user)


@router.get("/me", response_model=schemas.UserRead)
def me(user: models.User = Depends(auth.get_current_user)):
    """מחזיר את פרטי המשתמש המחובר (בדיקת תקינות טוקן)."""
    return user


@router.post("/logout-all", status_code=204)
def logout_all(
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    """יציאה מכל המכשירים: מעלה את גרסת הטוקן ובכך פוסל את כל הטוקנים הקיימים.

    אחרי הקריאה גם הטוקן הנוכחי בטל — הצד-לקוח יימחק אותו ויחזיר למסך הכניסה.
    """
    user.token_version = (user.token_version or 1) + 1
    db.commit()


@router.patch("/me", response_model=schemas.UserRead)
def update_profile(
    payload: schemas.ProfileUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    """עדכון פרטי הפרופיל של המשתמש המחובר (שם תצוגה)."""
    user.display_name = payload.display_name.strip()
    db.commit()
    db.refresh(user)
    return user


@router.post("/change-password", response_model=schemas.TokenResponse)
def change_password(
    payload: schemas.PasswordChange,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    """שינוי סיסמה: מאמת את הנוכחית, מחליף, ופוסל את כל הטוקנים הישנים.

    מחזיר טוקן חדש כדי שהמכשיר הנוכחי יישאר מחובר, בעוד שאר המכשירים נדרשים
    להתחבר מחדש עם הסיסמה החדשה.
    """
    if not auth.verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="הסיסמה הנוכחית שגויה",
        )
    user.password_hash = auth.hash_password(payload.new_password)
    user.token_version = (user.token_version or 1) + 1
    db.commit()
    db.refresh(user)
    token = auth.create_access_token(user)
    return schemas.TokenResponse(access_token=token, user=user)
