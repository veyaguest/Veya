"""Router התחברות (שלב 8): הרשמה, כניסה, ופרטי המשתמש המחובר."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, auth, legal, models, schemas
from app.account import delete_event_cascade
from app.database import get_db, set_request_identity
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
    exists = auth.find_user_by_email(db, payload.email)
    if exists is not None:
        auth_limiter.record_fail(ip)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="כתובת האימייל כבר רשומה במערכת",
        )

    # הבעלים = המשתמש הראשון שנרשם (או אימייל שהוגדר ב-ADMIN_EMAIL) → אדמין.
    user_count = auth.count_users(db)
    is_admin = user_count == 0 or (
        auth.ADMIN_EMAIL != "" and payload.email == auth.ADMIN_EMAIL
    )

    user = auth.register_user_row(
        db,
        email=payload.email,
        password_hash=auth.hash_password(payload.password),
        display_name=payload.display_name.strip(),
        phone=payload.phone,
        is_admin=is_admin,
        account_type="couple",
    )
    # קובעים את זהות הבקשה מיד אחרי שיש id — כך גם שאילתות ה-RLS הבאות
    # (אימוץ אירועים יתומים) רצות תחת הזהות של המשתמש עצמו.
    set_request_identity(user.id)

    # אימוץ אירועים "יתומים" (בלי בעלים) — מיגרציה מהמצב הישן של אירוע יחיד.
    auth.adopt_orphan_events(db, user.id)

    # רישום ההסכמות שאושרו בטופס ההרשמה (חובה: terms+privacy — נאכף כבר
    # ב-schemas.UserCreate; אופציונלי: marketing אם המשתמש סימן זאת).
    legal.record_consent(db, user.id, "terms", source="signup_form", ip=ip)
    legal.record_consent(db, user.id, "privacy", source="signup_form", ip=ip)
    if payload.accepted_marketing:
        legal.record_consent(db, user.id, "marketing", source="signup_form", ip=ip)
    audit.record(
        db, "consent_accepted", user_id=user.id,
        detail="terms+privacy בהרשמה" + ("+marketing" if payload.accepted_marketing else ""),
        ip=ip,
    )

    db.commit()
    # אין צורך ב-refresh: expire_on_commit=False (ראו app/database.py) — האובייקט
    # כבר מכיל את כל הערכים מה-INSERT (id/created_at), בלי שאילתה נוספת אחרי commit.
    token = auth.create_access_token(user)
    return schemas.TokenResponse(access_token=token, user=user)


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, request: Request, db: Session = Depends(get_db)):
    """מאמת אימייל+סיסמה ומחזיר טוקן."""
    ip = client_ip(request)
    auth_limiter.check(ip)
    user = auth.find_user_by_email(db, payload.email)
    if user is None or not auth.verify_password(payload.password, user.password_hash):
        auth_limiter.record_fail(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="אימייל או סיסמה שגויים",
        )
    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="החשבון הושבת. יש לפנות למנהל המערכת",
        )
    # רישום ההתחברות להיסטוריה (מטא-דאטה בלבד). לא מפיל את הכניסה אם נכשל.
    try:
        auth.record_login_event(
            db, user.id, ip, (request.headers.get("user-agent") or "")[:300] or None,
        )
        db.commit()
    except Exception:
        db.rollback()
    token = auth.create_access_token(user)
    return schemas.TokenResponse(access_token=token, user=user)


@router.get("/me", response_model=schemas.UserRead)
def me(
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    """מחזיר את פרטי המשתמש המחובר (בדיקת תקינות טוקן) + needs_reconsent."""
    data = schemas.UserRead.model_validate(user)
    data.needs_reconsent = legal.needs_reconsent(db, user.id)
    return data


@router.post("/consent", status_code=204)
def accept_consent(
    payload: schemas.ConsentAccept,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    """אישור/אישור-מחדש מפורש של מסמך אחד או יותר (למשל אחרי עדכון תנאים).

    כל קריאה יוצרת שורת הסכמה חדשה בגרסה הנוכחית — לא דורסת היסטוריה.
    """
    ip = client_ip(request)
    for consent_type in payload.types:
        legal.record_consent(db, user.id, consent_type, source="reconsent_modal", ip=ip)
    audit.record(
        db, "consent_accepted", user_id=user.id,
        detail=f"אישור מחדש: {', '.join(payload.types)}", ip=ip,
    )
    db.commit()


@router.get("/me/export")
def export_my_data(
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    """מייצא את כל המידע האישי של המשתמש המחובר כ-JSON (זכות עיון/העתק —
    מדיניות פרטיות §7). לא כולל password_hash/token_version."""

    def guest_dict(g: models.Guest) -> dict:
        return {
            "id": g.id,
            "full_name": g.full_name,
            "phone": g.phone,
            "side": g.side,
            "group_type": g.group_type,
            "party_size": g.party_size,
            "notes_raw": g.notes_raw,
            "rsvp_status": g.rsvp_status,
            "table_number": g.table_number,
            "confirmed_count": g.confirmed_count,
            "guest_note": g.guest_note,
            "is_child": g.is_child,
            "created_at": g.created_at.isoformat() if g.created_at else None,
        }

    def event_dict(ev: models.Event) -> dict:
        guests = db.scalars(
            select(models.Guest).where(models.Guest.event_id == ev.id)
        ).all()
        return {
            "id": ev.id,
            "event_type": ev.event_type,
            "groom_name": ev.groom_name,
            "bride_name": ev.bride_name,
            "venue_name": ev.venue_name,
            "venue_address": ev.venue_address,
            "event_date": ev.event_date,
            "event_time": ev.event_time,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
            "guests": [guest_dict(g) for g in guests],
        }

    events = db.scalars(
        select(models.Event).where(models.Event.owner_id == user.id)
    ).all()
    consents = db.scalars(
        select(models.ConsentRecord).where(models.ConsentRecord.user_id == user.id)
    ).all()
    logins = db.scalars(
        select(models.LoginEvent).where(models.LoginEvent.user_id == user.id)
    ).all()

    audit.record(db, "data_export", user_id=user.id, detail="ייצוא מידע אישי (GET /auth/me/export)")
    db.commit()

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "phone": user.phone,
            "account_type": user.account_type,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "events": [event_dict(ev) for ev in events],
        "consents": [
            {
                "consent_type": c.consent_type,
                "document_version": c.document_version,
                "source": c.source,
                "accepted_at": c.accepted_at.isoformat() if c.accepted_at else None,
            }
            for c in consents
        ],
        "login_history": [
            {
                "created_at": lg.created_at.isoformat() if lg.created_at else None,
                "ip": lg.ip,
            }
            for lg in logins
        ],
    }


@router.delete("/me", status_code=204)
def delete_my_account(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    """מוחק לצמיתות את החשבון של המשתמש המחובר, כולל כל האירועים שבבעלותו.

    שונה במכוון מ-admin.delete_user (שם מחיקה חסומה אם יש למשתמש אירועים
    בבעלותו, כדי למנוע יתמות בטעות ע"י אדמין): כאן זו בקשת מחיקה עצמית —
    "אני רוצה שהחשבון והנתונים שלי יימחקו" כולל האירועים, לא רק לחסום אותה.
    מתעד ב-Audit Log *לפני* המחיקה (אחרי המחיקה אין user_id לקשר אליו).
    """
    ip = client_ip(request)
    audit.record(
        db, "account_delete_requested", user_id=user.id,
        detail=f"מחיקת חשבון עצמית: {user.email}", ip=ip,
    )

    owned_events = db.scalars(
        select(models.Event).where(models.Event.owner_id == user.id)
    ).all()
    for event in owned_events:
        delete_event_cascade(db, event)

    for member in db.scalars(
        select(models.EventMember).where(
            (models.EventMember.user_id == user.id)
            | (models.EventMember.invited_by_id == user.id)
        )
    ).all():
        db.delete(member)

    for login_event in db.scalars(
        select(models.LoginEvent).where(models.LoginEvent.user_id == user.id)
    ).all():
        db.delete(login_event)

    # יומן הסכמות/אבטחה נשארים לצורך שקיפות ותיעוד, אך מנותקים מהמשתמש
    # שנמחק (בדומה לתבנית הקיימת ב-admin.py::delete_user).
    for consent in db.scalars(
        select(models.ConsentRecord).where(models.ConsentRecord.user_id == user.id)
    ).all():
        consent.user_id = None
    for log in db.scalars(
        select(models.AuditLog).where(models.AuditLog.user_id == user.id)
    ).all():
        log.user_id = None

    db.delete(user)
    db.commit()


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
    """עדכון פרטי הפרופיל של המשתמש המחובר (שם תצוגה + טלפון)."""
    user.display_name = payload.display_name.strip()
    if payload.phone is not None:
        user.phone = payload.phone
    db.commit()
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
    token = auth.create_access_token(user)
    return schemas.TokenResponse(access_token=token, user=user)
