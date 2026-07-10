"""Router התחברות (שלב 8): הרשמה, כניסה, ופרטי המשתמש המחובר."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth, models, schemas
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.TokenResponse, status_code=201)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    """יוצר משתמש חדש ומחזיר טוקן התחברות.

    המשתמש הראשון שנרשם "מאמץ" את האירוע הקיים (owner_id ריק) כדי שהנתונים
    שכבר הוזנו לא יאבדו.
    """
    exists = db.scalars(
        select(models.User).where(models.User.email == payload.email)
    ).first()
    if exists is not None:
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
    token = auth.create_access_token(user.id)
    return schemas.TokenResponse(access_token=token, user=user)


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    """מאמת אימייל+סיסמה ומחזיר טוקן."""
    user = db.scalars(
        select(models.User).where(models.User.email == payload.email)
    ).first()
    if user is None or not auth.verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="אימייל או סיסמה שגויים",
        )
    token = auth.create_access_token(user.id)
    return schemas.TokenResponse(access_token=token, user=user)


@router.get("/me", response_model=schemas.UserRead)
def me(user: models.User = Depends(auth.get_current_user)):
    """מחזיר את פרטי המשתמש המחובר (בדיקת תקינות טוקן)."""
    return user
