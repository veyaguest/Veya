"""Router התחברות (שלב 8): הרשמה, כניסה, ופרטי המשתמש המחובר."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, auth, emailer, legal, models, partners, schemas
from app.account import delete_event_cascade
from app.database import get_db, set_request_identity
from app.ratelimit import auth_limiter, client_ip

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_read(db: Session, user: models.User) -> schemas.UserRead:
    """``UserRead`` מלא — כולל שלושת השדות המחושבים שאינם על ה-ORM.

    מרוכז כאן כדי שכל מסלול שמחזיר משתמש (הרשמה, כניסה, גוגל, /me, עדכון
    פרופיל) יחזיר בדיוק את אותה תמונת מצב — אחרת הפרונט היה מקבל
    ``email_verified`` נכון במסך אחד ושגוי באחר.
    """
    data = schemas.UserRead.model_validate(user)
    data.needs_reconsent = legal.needs_reconsent(db, user.id)
    data.email_verified = auth.is_email_verified(user)
    data.profile_complete = auth.profile_complete(user)
    return data


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
    # קובעים את זהות הבקשה מיד אחרי שיש id, אבל זה מעדכן רק את ה-ContextVar
    # בפייתון — לא את הזהות שכבר הוזרקה לטרנזקציה הפתוחה (ראו commit מיד
    # למטה + ההערה המורחבת ב-google_exchange לעיל).
    set_request_identity(user.id)

    # קודם מוודאים שהמשתמש עצמו נשמר — *לפני* כל כתיבה תלוית-RLS אחרת
    # (הסכמות, אימוץ אירועים). קריטי: הטרנזקציה הנוכחית כבר הוזרקה עם זהות
    # ריקה (ב-after_begin, לפני שהמשתמש נוצר, בשאילתת find_user_by_email
    # למעלה) — INSERT ל-consent_records בתוכה היה נדחה ע"י RLS
    # (WITH CHECK user_id = app_current_user_id() כשזה עדיין ''), בדיוק כמו
    # הבאג שתוקן ב-google_exchange (ראו שם התיעוד המלא). ה-commit כאן סוגר
    # את הטרנזקציה הראשונה; הפעולות הבאות פותחות טרנזקציה חדשה שמוזרקת עם
    # הזהות הנכונה (current_user_id כבר עודכן ע"י set_request_identity).
    db.commit()

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

    # מנפיק טוקן אימות ושולח את מייל האימות. נשמר באותה טרנזקציה עם
    # ההסכמות, ולכן ה-commit שלמטה מכסה גם אותו.
    emailer.debug_log(f"ENDPOINT /auth/register reached | new user_id={user.id}")
    _sent_ok = auth.send_verification_email(db, user)
    # עד עכשיו ערך ההחזרה נזרק בשקט — כישלון שליחה לא הותיר שום עקבה.
    if not _sent_ok:
        emailer.debug_log("⚠️ register: verification email did NOT go out (result ok=False)")

    db.commit()
    # אין צורך ב-refresh: expire_on_commit=False (ראו app/database.py) — האובייקט
    # כבר מכיל את כל הערכים מה-INSERT (id/created_at), בלי שאילתה נוספת אחרי commit.
    token = auth.create_access_token(user)
    return schemas.TokenResponse(access_token=token, user=_user_read(db, user))


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
            detail="לא הצלחנו לזהות את הפרטים — בדקו את האימייל והסיסמה ונסו שוב",
        )
    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="החשבון הזה הושבת. אפשר לפנות אלינו כדי לברר למה",
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
    return schemas.TokenResponse(access_token=token, user=_user_read(db, user))


@router.post("/google/exchange", response_model=schemas.TokenResponse)
def google_exchange(
    payload: schemas.GoogleExchangeRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """מקבל טוקן Supabase (אחרי OAuth של גוגל בצד-לקוח) ומחזיר טוקן פנימי שלנו.

    המסלול:
    1. מאמת את הטוקן מול ה-JWKS הציבורי של Supabase (ES256, aud='authenticated').
    2. שולף email + display_name מה-payload.
    3. מוצא משתמש קיים לפי email, או יוצר חדש (הופך לאדמין רק אם ראשון /
       תואם ADMIN_EMAIL — בדיוק כמו register רגיל).
    4. משתמש חדש → רושם הסכמות terms+privacy אוטומטית (מקבילה למקרה
       שבו המשתמש סימן וי בטופס הרשמה; ה-Frontend חייב להציג את התנאים
       ליד כפתור "התחבר עם גוגל").
    5. מחזיר TokenResponse עם טוקן פנימי — משם המשך זהה ל-login רגיל.
    """
    ip = client_ip(request)
    auth_limiter.check(ip)

    supabase_payload = auth.verify_supabase_token(payload.supabase_access_token)

    email = (supabase_payload.get("email") or "").strip().lower()
    if not email:
        auth_limiter.record_fail(ip)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="לא נמצאה כתובת אימייל בטוקן של גוגל",
        )

    user_metadata = supabase_payload.get("user_metadata") or {}
    display_name = (
        user_metadata.get("full_name")
        or user_metadata.get("name")
        or ""
    )
    avatar_url = user_metadata.get("avatar_url") or user_metadata.get("picture") or ""

    user, is_new = auth.find_or_create_google_user(
        db, email=email, display_name=display_name, avatar_url=avatar_url,
    )

    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="החשבון הזה הושבת. אפשר לפנות אלינו כדי לברר למה",
        )

    # קודם מוודאים שהמשתמש עצמו נשמר בהצלחה — *לפני* כל כתיבה תלוית-RLS
    # אחרת (הסכמות, אירוע התחברות). קריטי: register_user_row לא עושה commit
    # בעצמה (ה-INSERT חי בטרנזקציה הנוכחית), ו-user.id כבר מאוכלס בזיכרון
    # מיד אחרי ה-INSERT (RETURNING), גם *לפני* commit. אם ה-commit הזה נכשל,
    # זו שגיאה אמיתית שצריכה 500 מפורש: בלי המשתמש הזה שמור בפועל, אסור
    # להנפיק לו טוקן (היה מייצר טוקן תקף-למראה למשתמש שלא קיים ב-DB —
    # הבקשה המאומתת הבאה הייתה נכשלת ב-401 ומחזירה למסך ההתחברות, למרות
    # שההתחברות "הצליחה").
    db.commit()

    # רישום ההסכמות *אחרי* ה-commit למעלה, לא לפניו — בכוונה. הזרקת הזהות
    # ל-RLS של Postgres (app.current_user_id) קורית פעם אחת בלבד לכל
    # טרנזקציה, ב-after_begin (ראו database.py), ונקראת מתוך current_user_id
    # (ContextVar) *באותו רגע*. set_request_identity(user.id) לעיל קורה
    # *באמצע* הטרנזקציה הראשונה (אחרי ה-INSERT של המשתמש) — כלומר הטרנזקציה
    # ההיא כבר הוזרקה עם זהות ריקה (לפני שהמשתמש בכלל נוצר). INSERT ל-
    # consent_records בתוך אותה טרנזקציה היה נכשל על WITH CHECK (user_id =
    # app_current_user_id()) כי app_current_user_id() עדיין '' — נתפס בפועל:
    # משתמש גוגל *חדש* קיבל שגיאת RLS לא-מטופלת ב-commit, בזמן שמשתמש קיים
    # (מדלג על הבלוק הזה לגמרי) תמיד עבד. ה-commit למעלה סוגר את הטרנזקציה
    # הראשונה; הפעולות הבאות פותחות טרנזקציה חדשה, ש-after_begin מזריק לה
    # את הזהות הנכונה (כי current_user_id כבר מעודכן מ-set_request_identity).
    if is_new:
        legal.record_consent(db, user.id, "terms", source="google_signup", ip=ip)
        legal.record_consent(db, user.id, "privacy", source="google_signup", ip=ip)
        audit.record(
            db, "consent_accepted", user_id=user.id,
            detail="terms+privacy בהרשמה דרך גוגל", ip=ip,
        )
        db.commit()

    # רישום ההתחברות להיסטוריה (מטא-דאטה בלבד) — best-effort: המשתמש כבר
    # שמור מהשלב הקודם, אז rollback כאן פוגע רק ברישום הזה, לא במשתמש עצמו
    # (בדיוק כמו login() הרגיל, ראו למטה).
    try:
        auth.record_login_event(
            db, user.id, ip, (request.headers.get("user-agent") or "")[:300] or None,
        )
        db.commit()
    except Exception:
        db.rollback()

    token = auth.create_access_token(user)
    return schemas.TokenResponse(access_token=token, user=_user_read(db, user))


@router.get("/me", response_model=schemas.UserRead)
def me(
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    """פרטי המשתמש המחובר + מצב ההסכמות, אימות המייל ושלמות הפרטים."""
    return _user_read(db, user)


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


# ---------------------------------------------------------------------------
# אימות כתובת המייל
# ---------------------------------------------------------------------------


@router.post("/verify-email/resend", status_code=200)
def resend_verification(
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    """שולח מחדש את מייל האימות למשתמש המחובר."""
    emailer.debug_log(
        f"ENDPOINT /auth/verify-email/resend reached | user_id={user.id} | "
        f"already_verified={auth.is_email_verified(user)}"
    )
    if auth.is_email_verified(user):
        # ⚠️ נקודת כשל אפשרית #4: המשתמש כבר מסומן כמאומת, ולכן **לא נקרא
        # בכלל** שירות המייל. כל 15 המשתמשים הקיימים סומנו כמאומתים
        # במיגרציה החד-פעמית — אז חשבון ותיק לעולם לא ישלח מייל אימות.
        emailer.debug_log("resend SKIPPED — user already verified; emailer NOT called")
        return {"already_verified": True, "sent": False}
    sent = auth.send_verification_email(db, user)
    db.commit()
    if not sent:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="לא הצלחנו לשלוח את המייל כרגע. אפשר לנסות שוב עוד רגע",
        )
    return {"already_verified": False, "sent": True}


@router.post("/verify-email/verify-code", response_model=schemas.UserRead)
def verify_email_code(
    payload: schemas.VerifyEmailCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    """מאמת את כתובת המייל לפי קוד 6 הספרות שהוקלד במסך האימות.

    בניגוד ל-``verify-email/confirm`` (הקישור, נתיב ציבורי), כאן המשתמש כבר
    מחובר — הטוקן שהתקבל בהרשמה מספיק, אין צורך בעקיפת RLS: העדכון עובר
    תחת מדיניות "כל אחד מעדכן רק את עצמו" הרגילה.
    """
    ip = client_ip(request)
    auth_limiter.check(ip)
    if auth.is_email_verified(user):
        # כבר אומת (למשל דרך הקישור, בטאב אחר) — לא שגיאה, פשוט no-op.
        return _user_read(db, user)

    result = auth.consume_email_verification_code(db, user, payload.code)
    if result == "ok":
        audit.record(
            db, "email_verified", user_id=user.id,
            detail=f"אימות כתובת מייל בקוד: {user.email}", ip=ip,
        )
        db.commit()
        return _user_read(db, user)

    db.commit()  # שומר את מונה הניסיונות שהתעדכן (אם עודכן)
    if result == "wrong":
        auth_limiter.record_fail(ip)
        raise HTTPException(status_code=400, detail="הקוד שהזנתם שגוי. אפשר לנסות שוב")
    if result == "expired":
        raise HTTPException(status_code=400, detail="הקוד פג תוקף. אפשר לבקש קוד חדש")
    if result == "locked":
        raise HTTPException(
            status_code=429, detail="יותר מדי ניסיונות שגויים. אפשר לבקש קוד חדש",
        )
    raise HTTPException(status_code=400, detail="לא נמצא קוד פעיל. אפשר לבקש קוד חדש")


@router.post("/verify-email/change", response_model=schemas.UserRead)
def change_unverified_email(
    payload: schemas.EmailChangeRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_user),
):
    """מתקן כתובת מייל שגויה **לפני** שאומתה, ושולח אליה אימות חדש.

    מוגבל בכוונה לחשבון שטרם אומת: אחרי שהכתובת אומתה, החלפתה היא פעולה
    רגישה יותר (היא מזהה הכניסה לחשבון) ודורשת תהליך משלה — לא נפתח כאן
    דלת אחורית לשינוי כתובת מאומתת.
    """
    if auth.is_email_verified(user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="כתובת המייל הזו כבר מאומתת",
        )
    if payload.email == user.email:
        # אותה כתובת — פשוט שולחים שוב, בלי להיכשל.
        auth.send_verification_email(db, user)
        db.commit()
        return _user_read(db, user)

    taken = auth.find_user_by_email(db, payload.email)
    if taken is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="כתובת האימייל כבר רשומה במערכת",
        )

    tracked = db.get(models.User, user.id) or user
    tracked.email = payload.email
    auth.send_verification_email(db, tracked)
    audit.record(
        db, "email_changed", user_id=tracked.id,
        detail=f"החלפת כתובת מייל לפני אימות ל-{payload.email}",
        ip=client_ip(request),
    )
    db.commit()
    return _user_read(db, tracked)


@router.post("/verify-email/confirm", response_model=schemas.TokenResponse)
def confirm_verification(
    payload: schemas.VerifyEmailRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """מאמת את כתובת המייל לפי הטוקן מהקישור, ומחזיר טוקן התחברות.

    נתיב **ציבורי** במכוון (בלי ``get_current_user``): המשתמש עשוי ללחוץ על
    הקישור בדפדפן אחר או במכשיר אחר, שבו הוא לא מחובר. הטוקן החד-פעמי הוא
    ההוכחה, ולכן הוא גם מספיק כדי להנפיק כניסה — בדיוק כמו קישור אימות
    בכל מוצר אחר. ראו ``auth.consume_email_verification``: הטוקן נמחק
    ברגע המימוש, כך שאי אפשר להשתמש בו שוב.
    """
    user = auth.consume_email_verification(db, payload.token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="הקישור לאימות כבר לא תקף. אפשר לבקש קישור חדש",
        )
    if user.disabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="החשבון הזה הושבת. אפשר לפנות אלינו כדי לברר למה",
        )
    set_request_identity(user.id)
    # מנקה גם קוד אימות שעדיין ממתין (אם קיים) — אותה "סשן אימות", שני
    # הערוצים מובילים לאותה תוצאה. ב-SQLite consume_email_verification כבר
    # עשה זאת; ב-Postgres הפונקציה הציבורית (SECURITY DEFINER) לא נוגעת
    # בעמודות הקוד, אז משלימים כאן — תחת RLS רגיל, כי הזהות כבר הוזרקה
    # לשורה למעלה (בלי לגעת ב-RLS/SQL עצמם).
    tracked = db.get(models.User, user.id)
    if tracked is not None:
        tracked.email_verification_code_hash = None
        tracked.email_verification_code_expires_at = None
        tracked.email_verification_code_attempts = 0
    audit.record(
        db, "email_verified", user_id=user.id,
        detail=f"אימות כתובת מייל: {user.email}", ip=client_ip(request),
    )
    db.commit()
    return schemas.TokenResponse(
        access_token=auth.create_access_token(user), user=_user_read(db, user)
    )


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
            "seating_notes": g.seating_notes,
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

    השורה נרשמת עם ``user_id=None`` מלכתחילה (לא ננסה לנתק אותה בהמשך): מזהה
    המשתמש נשמר בטקסט ה-``detail`` בלבד. הסיבה: ``SessionLocal`` פועל עם
    ``autoflush=False`` (ראו database.py), ולכן שורה חדשה שנוספה עם user_id
    תקין לא הייתה נראית לשאילתת ה-SELECT שמנתקת שורות קיימות בהמשך (היא לא
    נשלחת ל-DB לפני ה-commit) — והייתה נשארת עם FK חי לרגע לפני המחיקה,
    וגורמת ל-IntegrityError על ה-DELETE FROM users (נתפס ידנית בבדיקה מקומית
    מול SQLite, לפני שהגיע לייצור).
    """
    ip = client_ip(request)
    audit.record(
        db, "account_delete_requested",
        detail=f"מחיקת חשבון עצמית: {user.email} (#{user.id})", ip=ip,
    )

    owned_events = db.scalars(
        select(models.Event).where(models.Event.owner_id == user.id)
    ).all()
    for event in owned_events:
        # אירוע בניהול משותף לא נמחק כשאחד המנהלים עוזב — הוא עובר לבעלות
        # המנהל/ת שנשאר/ת. אחרת מחיקת חשבון אחד הייתה מוחקת לבן/בת הזוג את
        # כל המוזמנים, אישורי ההגעה וההושבה, בלי שהוא/היא ביקשו דבר.
        remaining = [
            m for m in partners.managers_of(db, event) if m.id != user.id
        ]
        if remaining:
            heir = remaining[0]
            # קריטי: מעבירים בעלות דרך ה-relationship ולא ע"י השמה ישירה
            # ל-owner_id. ל-``User.events`` יש relationship, ולכן מחיקת
            # המשתמש למטה גורמת ל-SQLAlchemy לאפס (NULL) את ה-FK של כל
            # אירוע שעדיין נמצא באוסף שלו בזיכרון — וזה היה דורס את ההשמה
            # הישירה ומשאיר את האירוע בלי בעלים בכלל (נתפס בבדיקה 20).
            # השמה דרך ``event.owner`` מעדכנת את שני צדדי הקשר, כך שהאירוע
            # יוצא מהאוסף של הנמחק ונכנס לזה של היורש.
            event.owner = db.get(models.User, heir.id)
            # שורת החברות של היורש מיותרת עכשיו — הוא הבעלים, והבעלים לעולם
            # אינו מיוצג ב-event_members (ראו models.EventMember).
            leftover = partners.partner_member(db, event.id, heir.id)
            if leftover is not None:
                db.delete(leftover)
            audit.record(
                db, "event_ownership_transferred", event_id=event.id,
                detail=f"האירוע עבר לניהול {heir.display_name or heir.email} "
                       f"לאחר מחיקת חשבון של {user.email}",
                ip=ip,
            )
            continue
        delete_event_cascade(db, event)

    # הזמנות ששלח/קיבל — נמחקות איתו. הן נושאות FK למשתמש, ואין להן ערך
    # אחרי שהחשבון נעלם (אפשר תמיד לשלוח הזמנה חדשה).
    for invitation in db.scalars(
        select(models.EventInvitation).where(
            (models.EventInvitation.invited_by == user.id)
            | (models.EventInvitation.accepted_by == user.id)
        )
    ).all():
        db.delete(invitation)

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
    # .with_for_update(): מגן מפני race עם טרנזקציה נפרדת שמוחקת במקביל
    # שורת audit_logs זהה דרך event_id (delete_event_cascade של אירוע-של-
    # מישהו-אחר ש-user שיתף עליו פעולה) — ראו הסבר מלא ב-admin.py::
    # _delete_user_impl (אותה תבנית פגיעות בדיוק, שוחזרה ותועדה שם).
    for log in db.scalars(
        select(models.AuditLog).where(models.AuditLog.user_id == user.id).with_for_update()
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
    return _user_read(db, user)


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
    return schemas.TokenResponse(access_token=token, user=_user_read(db, user))
