"""ניהול משותף של אירוע — הזמנת בן/בת זוג והצטרפות לאירוע קיים.

שני חצאים לזרימה אחת:

1. **הזמנה** (``/partner/invite``) — מנהל האירוע מזין את המייל של בן/בת
   הזוג. נוצרת שורת ``EventInvitation`` עם טוקן חד-פעמי, והקישור נשלח
   במייל דרך Resend.
2. **הצטרפות** (``/partner/invitations/{token}``) — מי שקיבל את המייל
   פותח את הקישור. ה-GET מתאר מה מצב ההזמנה (בלי לחשוף מידע למי שאינו
   הנמען), וה-POST מחבר אותו לאירוע **הקיים** כמנהל שווה.

כלל שאסור לשבור: בשום שלב כאן לא נוצר אירוע חדש. ההצטרפות תמיד מחברת את
החשבון השני לאותה שורת ``Event`` — זה כל העניין של "אירוע אחד, שני מנהלים"
(ראו app/partners.py).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, auth, emailer, models, partners, schemas
from app.database import get_db
from app.ratelimit import client_ip

router = APIRouter(prefix="/partner", tags=["partner"])


def _require_my_event(db: Session, user: models.User) -> models.Event:
    """האירוע שהמשתמש מנהל — או 404 אם עדיין אין לו אירוע."""
    event = partners.my_event(db, user)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="עדיין לא יצרת אירוע",
        )
    return event


def _invite_read(
    invitation: models.EventInvitation, *, email_sent: bool = True
) -> schemas.PartnerInviteRead:
    return schemas.PartnerInviteRead(
        id=invitation.id,
        invited_email=invitation.invited_email,
        status=invitation.status,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
        email_sent=email_sent,
    )


@router.post("/invite", response_model=schemas.PartnerInviteRead, status_code=201)
def invite_partner(
    payload: schemas.PartnerInviteCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_owner),
):
    """שולח לבן/בת הזוג הזמנה לנהל יחד את האירוע.

    שליחה חוזרת מותרת ומייצרת קישור חדש — הקישור הקודם מתבטל
    (``partners.cancel_open_invitations``), כדי שלא יישארו כמה קישורים
    תקפים במקביל.
    """
    event = _require_my_event(db, user)

    # אין להזמין את עצמך — מצב מבלבל שלא מוסיף כלום.
    if payload.email == (user.email or "").strip().lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="זו כתובת המייל שלך. צריך למלא את הכתובת של בן/בת הזוג",
        )

    # אירוע מנוהל ע"י שני אנשים לכל היותר — זה המודל העסקי, לא מגבלה טכנית.
    existing_managers = partners.managers_of(db, event)
    if len(existing_managers) >= 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="לאירוע הזה כבר יש שני מנהלים",
        )

    invitation, token = partners.create_invitation(
        db, event=event, invited_email=payload.email, invited_by=user
    )
    db.flush()  # מבטיח id ו-created_at לפני שמרכיבים את התשובה

    result = emailer.send_partner_invite(
        to=invitation.invited_email,
        inviter_name=user.display_name or "",
        event_title=partners.event_title(event),
        invite_url=partners.invite_url(token),
    )
    audit.record(
        db, "partner_invited", event_id=event.id, user_id=user.id,
        detail=f"הזמנה לניהול משותף נשלחה ל-{invitation.invited_email}",
        ip=client_ip(request),
    )
    db.commit()
    return _invite_read(invitation, email_sent=result.ok)


@router.get("/invite", response_model=schemas.PartnerInviteRead)
def current_invite(
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_owner),
):
    """ההזמנה הפתוחה הנוכחית לאירוע, אם יש — כדי להציג "נשלחה הזמנה ל..."."""
    event = _require_my_event(db, user)
    invitation = db.scalars(
        select(models.EventInvitation)
        .where(
            models.EventInvitation.event_id == event.id,
            models.EventInvitation.status == partners.STATUS_PENDING,
        )
        .order_by(models.EventInvitation.id.desc())
    ).first()
    if invitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="אין הזמנה פתוחה"
        )
    return _invite_read(invitation)


@router.delete("/invite", status_code=204)
def cancel_invite(
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_owner),
):
    """מבטל את ההזמנה הפתוחה — הקישור שנשלח מפסיק לעבוד."""
    event = _require_my_event(db, user)
    partners.cancel_open_invitations(db, event.id)
    audit.record(
        db, "partner_invite_cancelled", event_id=event.id, user_id=user.id,
        detail="הזמנה לניהול משותף בוטלה", ip=client_ip(request),
    )
    db.commit()


@router.get("/overview", response_model=schemas.AccountOverview)
def account_overview(
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_owner),
):
    """כל מה שמסך "החשבון שלי" צריך — בקריאה אחת.

    מרוכז ב-endpoint אחד (ולא שלוש קריאות נפרדות) כדי שהמסך ייטען בבת אחת
    ולא "יקפוץ" בזמן שהחלקים מגיעים בזה אחר זה.
    """
    from app import legal

    data = schemas.UserRead.model_validate(user)
    data.needs_reconsent = legal.needs_reconsent(db, user.id)
    data.email_verified = auth.is_email_verified(user)
    data.profile_complete = auth.profile_complete(user)

    event = partners.my_event(db, user)
    if event is None:
        return schemas.AccountOverview(user=data)

    managers = [
        schemas.EventManagerRead(
            user_id=m.id,
            display_name=m.display_name or m.email.split("@")[0],
            email=m.email,
            is_me=(m.id == user.id),
        )
        for m in partners.managers_of(db, event)
    ]
    pending = db.scalars(
        select(models.EventInvitation)
        .where(
            models.EventInvitation.event_id == event.id,
            models.EventInvitation.status == partners.STATUS_PENDING,
        )
        .order_by(models.EventInvitation.id.desc())
    ).first()
    # הזמנה שפג תוקפה לא מוצגת כ"ממתינה" — היא כבר לא תעבוד.
    if pending is not None and partners.is_expired(pending):
        pending = None

    return schemas.AccountOverview(
        user=data,
        event=schemas.MyEventRead(
            id=event.id,
            title=partners.event_title(event),
            event_type=event.event_type or "wedding",
            event_date=event.event_date or "",
            venue_name=event.venue_name or "",
        ),
        managers=managers,
        pending_invite=_invite_read(pending) if pending is not None else None,
        can_invite_partner=len(managers) < 2,
    )


# ── הצטרפות ─────────────────────────────────────────────────────────────────
# שני ה-endpoints הבאים מקבלים את הטוקן בגוף/בנתיב ולא דורשים בעלות על
# האירוע — הטוקן *הוא* ההרשאה. מזהה האירוע לעולם אינו משמש כהרשאה בפני עצמו.


def _preview_for(
    db: Session,
    ctx: partners.InvitationContext,
    viewer: Optional[models.User] = None,
) -> schemas.InvitationPreview:
    """גוזר את מצב ההזמנה עבור הצופה הנוכחי (מחובר או לא).

    סדר הבדיקות חשוב: מצב ההזמנה עצמה (מומשה/בוטלה/פגה) נבדק **לפני** זהות
    הצופה, כדי שלא נבקש ממישהו להתחבר רק כדי לגלות שהקישור כבר לא תקף.
    """
    base = dict(
        event_title=ctx.event_title,
        inviter_name=ctx.inviter_name,
        invited_email=ctx.invited_email,
    )

    if ctx.status == partners.STATUS_ACCEPTED:
        return schemas.InvitationPreview(
            state="used", message="ההזמנה הזו כבר מומשה", **base
        )
    if ctx.status == partners.STATUS_CANCELLED:
        return schemas.InvitationPreview(
            state="cancelled", message="ההזמנה בוטלה", **base
        )
    if ctx.status == partners.STATUS_EXPIRED or partners.context_is_expired(ctx):
        return schemas.InvitationPreview(
            state="expired", message="תוקף ההזמנה פג", **base
        )

    if viewer is None:
        return schemas.InvitationPreview(state="needs_login", **base)

    if (viewer.email or "").strip().lower() != ctx.invited_email:
        return schemas.InvitationPreview(
            state="wrong_account",
            message=(
                f"ההזמנה נשלחה לכתובת {ctx.invited_email}, "
                f"ואתם מחוברים עם {viewer.email}"
            ),
            **base,
        )
    if partners.partner_member(db, ctx.event_id, viewer.id) is not None:
        return schemas.InvitationPreview(
            state="already_member", message="כבר יש לכם גישה לאירוע הזה", **base
        )
    return schemas.InvitationPreview(state="ready", **base)


@router.get("/invitations/{token}", response_model=schemas.InvitationPreview)
def preview_invitation(
    token: str,
    db: Session = Depends(get_db),
    viewer: models.User = Depends(auth.get_optional_user),
):
    """מה מצב ההזמנה — לפני ההצטרפות. עובד גם כשלא מחוברים."""
    ctx = partners.load_invitation(db, token)
    if ctx is None:
        return schemas.InvitationPreview(
            state="invalid", message="הקישור הזה לא תקין"
        )
    return _preview_for(db, ctx, viewer)


@router.post("/invitations/{token}/accept", response_model=schemas.InvitationPreview)
def accept_invitation(
    token: str,
    request: Request,
    db: Session = Depends(get_db),
    user: models.User = Depends(auth.get_current_owner),
):
    """מצרף את המשתמש המחובר לאירוע הקיים כמנהל/ת שווה.

    לא נוצר כאן אירוע חדש בשום מצב — רק שורת חברות לאירוע שכבר קיים.
    """
    ctx = partners.load_invitation(db, token)
    if ctx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="הקישור הזה לא תקין"
        )

    preview = _preview_for(db, ctx, user)
    if preview.state == "already_member":
        return preview
    if preview.state != "ready":
        # אימייל לא תואם / פג תוקף / מומש / בוטל — לא מאפשרים שימוש חוזר.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=preview.message or "אי אפשר להשתמש בהזמנה הזו",
        )

    # מי שמצטרף חייב לאמת את המייל שלו קודם — אחרת אפשר היה להירשם עם
    # כתובת של מישהו אחר ולהיכנס לאירוע שלו.
    if not auth.is_email_verified(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="צריך לאמת את כתובת המייל לפני ההצטרפות לאירוע",
        )

    if not partners.accept_invitation(db, token, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="אי אפשר להשתמש בהזמנה הזו",
        )
    audit.record(
        db, "partner_joined", event_id=ctx.event_id, user_id=user.id,
        detail=f"{user.display_name or user.email} הצטרף/ה לניהול האירוע",
        ip=client_ip(request),
    )
    db.commit()
    return schemas.InvitationPreview(
        state="joined",
        event_title=ctx.event_title,
        inviter_name=ctx.inviter_name,
        invited_email=ctx.invited_email,
    )
