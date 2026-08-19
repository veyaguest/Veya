"""ניהול משותף של אירוע — בן/בת זוג שמנהלים יחד את אותו אירוע.

המודל העסקי (מקור אמת יחיד לכל המערכת):

    User A ─┐
            ├──▶ Event X
    User B ─┘

לכל משתמש יש **אירוע אחד** שהוא מנהל, ולאירוע יכולים להיות שני מנהלים.
אין שכפול נתונים, אין אירוע נוסף לבן/בת הזוג, ואין "האירועים שלי": שני
החשבונות רואים ומשנים בדיוק את אותה שורת ``Event`` ואת כל מה שתלוי בה.

איך זה בנוי טכנית: הבעלים נשאר ``Event.owner_id``, ובן/בת הזוג נרשמים
כשורת ``EventMember`` עם ``role='partner'`` והרשאות מלאות. בחרנו להרחיב את
טבלת חברי-האירוע הקיימת (ולא ליצור טבלה מקבילה) כדי שלא יהיו שתי מערכות
גישה שצריך לסנכרן — ``partner`` הוא פשוט חבר-אירוע שההרשאות שלו מלאות
והוא נחשב מנהל לכל דבר, כולל בפעולות ששמורות לבעלים.

ההזמנה עצמה יושבת ב-``EventInvitation``: טוקן אקראי חד-פעמי שנשלח במייל,
כשב-DB נשמר רק ה-hash שלו.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import models
from app.database import IS_POSTGRES
from app.schemas import PLANNER_PERMISSIONS, VENUE_PERMISSIONS

# ── תפקיד וחברות ────────────────────────────────────────────────────────────
PARTNER_ROLE = "partner"

# בן/בת זוג = מנהל/ת שווה. ההרשאות המלאות כאן הן "חגורה ושלייקס": בפועל
# ``EventAccess`` מזהה partner עוד לפני שהוא בודק הרשאות ספציפיות (בדיוק כמו
# שהוא עושה לבעלים), אבל אם בעתיד ייבדקו ההרשאות בנפרד — הן שלמות ולא חסרות.
PARTNER_PERMISSIONS = sorted(set(PLANNER_PERMISSIONS) | set(VENUE_PERMISSIONS))

# תוקף הזמנה: 14 יום. מספיק זמן לבן/בת זוג לפתוח מייל בלי למהר, וקצר מספיק
# שקישור ישן שדלף מפוסטה לא יישאר תקף לנצח.
INVITE_TTL_DAYS = 14

# סטטוסי הזמנה.
STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_EXPIRED = "expired"
STATUS_CANCELLED = "cancelled"


def partner_member(
    db: Session, event_id: int, user_id: int
) -> Optional[models.EventMember]:
    """שורת החברות של המשתמש כבן/בת זוג באירוע, אם קיימת ופעילה."""
    return db.scalars(
        select(models.EventMember).where(
            models.EventMember.event_id == event_id,
            models.EventMember.user_id == user_id,
            models.EventMember.role == PARTNER_ROLE,
            models.EventMember.status == "active",
        )
    ).first()


def manages_event(db: Session, event: models.Event, user: models.User) -> bool:
    """האם המשתמש מנהל את האירוע — בעלים, בן/בת זוג, או אדמין-על.

    זו הבדיקה היחידה שצריך כדי לענות על "מותר לו לעשות כאן הכול?".
    """
    if user.is_admin or event.owner_id == user.id:
        return True
    return partner_member(db, event.id, user.id) is not None


def managers_of(db: Session, event: models.Event) -> list[models.User]:
    """שני המנהלים של האירוע (בעלים + בן/בת זוג), לפי הסדר הזה."""
    result: list[models.User] = []
    if event.owner_id:
        owner = db.get(models.User, event.owner_id)
        if owner is not None:
            result.append(owner)
    partner_rows = db.scalars(
        select(models.EventMember).where(
            models.EventMember.event_id == event.id,
            models.EventMember.role == PARTNER_ROLE,
            models.EventMember.status == "active",
        )
    ).all()
    for row in partner_rows:
        u = db.get(models.User, row.user_id)
        if u is not None:
            result.append(u)
    return result


def my_event(db: Session, user: models.User) -> Optional[models.Event]:
    """האירוע היחיד שהמשתמש מנהל — בבעלותו, או כבן/בת זוג. None אם אין.

    זהו המימוש של "אירוע אחד למשתמש": מעדיפים אירוע בבעלות, ואם אין —
    האירוע שהוא הצטרף אליו כבן/בת זוג.
    """
    owned = db.scalars(
        select(models.Event)
        .where(models.Event.owner_id == user.id)
        .order_by(models.Event.id)
    ).first()
    if owned is not None:
        return owned
    row = db.scalars(
        select(models.EventMember)
        .where(
            models.EventMember.user_id == user.id,
            models.EventMember.role == PARTNER_ROLE,
            models.EventMember.status == "active",
        )
        .order_by(models.EventMember.id)
    ).first()
    return db.get(models.Event, row.event_id) if row is not None else None


def event_title(event: models.Event) -> str:
    """שם האירוע לתצוגה ולמיילים, למשל "החתונה של אביב ודנה".

    נשען על מנוע המונחים (``event_terms``) כדי שאירוע שאינו חתונה יקבל את
    הכותרת הנכונה שלו, ולא ייקרא "חתונה" בכוח.
    """
    from app import event_terms

    return event_terms.event_display_title(
        event.event_type or "wedding", event.groom_name or "", event.bride_name or ""
    )


# ── טוקן ההזמנה ─────────────────────────────────────────────────────────────
def generate_token() -> str:
    """טוקן הזמנה אקראי, חד-פעמי ובלתי-ניתן-לניחוש (256 ביט אנטרופיה)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """ה-hash שנשמר ב-DB. הטוקן עצמו לעולם לא נשמר — רק נשלח במייל.

    SHA-256 (ולא bcrypt): הטוקן כבר אקראי ובעל אנטרופיה גבוהה, ולכן אין כאן
    מה "להאט" מול תקיפת מילון — בניגוד לסיסמה שבחר אדם. חיפוש לפי hash גם
    חייב להיות דטרמיניסטי כדי שנוכל למצוא את ההזמנה לפי הטוקן שבקישור.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def invite_url(token: str) -> str:
    """הקישור המלא שנשלח במייל. הטוקן הוא ההרשאה — לא מזהה האירוע.

    תחת ``/app`` (לא ברמה העליונה): אפליקציית ה-React מוגשת שם (ראו
    ``frontend/vite.config.ts``), וה-rewrite הקיים ב-``vercel.json``
    (``/app/(.*) → /app.html``) כבר מכסה את הנתיב הזה — אין צורך בכלל
    ייעודי נוסף.
    """
    from app import emailer

    return f"{emailer.public_base_url()}/app/join?token={token}"


# ── מחזור החיים של הזמנה ────────────────────────────────────────────────────
def is_expired(invitation: models.EventInvitation, now: Optional[datetime] = None) -> bool:
    now = now or datetime.utcnow()
    return invitation.expires_at is not None and invitation.expires_at <= now


@dataclass
class InvitationContext:
    """כל מה שצריך כדי להציג ולממש הזמנה — בלי לדרוש גישה לאירוע.

    למה טיפוס נפרד ולא ``models.EventInvitation`` ישירות: מי שמקבל הזמנה
    עדיין **אינו** חבר באירוע, ולכן תחת RLS ב-Postgres הוא לא יכול לקרוא
    לא את שורת ההזמנה, לא את האירוע ולא את המזמין. הנתונים נשלפים דרך
    פונקציית DB ייעודית (``app_invitation_preview``, SECURITY DEFINER),
    שמחזירה בכוונה מינימום מידע — כותרת האירוע ושם המזמין בלבד.
    """

    event_id: int
    event_title: str
    inviter_name: str
    invited_email: str
    status: str
    expires_at: Optional[datetime] = None


def _title_from_parts(event_type: str, groom: str, bride: str) -> str:
    from app import event_terms

    return event_terms.event_display_title(event_type or "wedding", groom or "", bride or "")


def load_invitation(db: Session, token: str) -> Optional[InvitationContext]:
    """טוען את הקשר ההזמנה לפי הטוקן מהקישור. ``None`` אם הטוקן לא מוכר."""
    if not (token or "").strip():
        return None
    token_hash = hash_token(token.strip())

    if IS_POSTGRES:
        row = db.execute(
            text("SELECT * FROM app_invitation_preview(:h)"), {"h": token_hash}
        ).mappings().first()
        if row is None:
            return None
        return InvitationContext(
            event_id=row["event_id"],
            event_title=_title_from_parts(
                row["event_type"], row["groom_name"], row["bride_name"]
            ),
            inviter_name=row["inviter_name"] or "",
            invited_email=row["invited_email"],
            status=row["status"],
            expires_at=row["expires_at"],
        )

    invitation = db.scalars(
        select(models.EventInvitation).where(
            models.EventInvitation.token_hash == token_hash
        )
    ).first()
    if invitation is None:
        return None
    event = db.get(models.Event, invitation.event_id)
    inviter = db.get(models.User, invitation.invited_by) if invitation.invited_by else None
    return InvitationContext(
        event_id=invitation.event_id,
        event_title=event_title(event) if event is not None else "",
        inviter_name=(inviter.display_name if inviter else "") or "",
        invited_email=invitation.invited_email,
        status=invitation.status,
        expires_at=invitation.expires_at,
    )


def context_is_expired(ctx: InvitationContext, now: Optional[datetime] = None) -> bool:
    if ctx.expires_at is None:
        return False
    now = now or datetime.utcnow()
    expires = ctx.expires_at
    # ``app_invitation_preview`` מחזיר timestamptz (מודע לאזור זמן), בעוד
    # ההשוואה שלנו נעשית ב-UTC נאיבי — משווים באותו מרחב כדי לא להתפוצץ.
    if expires.tzinfo is not None:
        expires = expires.replace(tzinfo=None)
    return expires <= now


def cancel_open_invitations(db: Session, event_id: int) -> None:
    """מבטל הזמנות פתוחות קודמות לאירוע — שליחה מחדש מבטלת את הקישור הישן.

    כך לא נשארים כמה קישורים תקפים במקביל: הקישור האחרון שנשלח הוא היחיד
    שעובד (מצמצם את חלון החשיפה אם מייל ישן דלף).
    """
    for row in db.scalars(
        select(models.EventInvitation).where(
            models.EventInvitation.event_id == event_id,
            models.EventInvitation.status == STATUS_PENDING,
        )
    ).all():
        row.status = STATUS_CANCELLED


def create_invitation(
    db: Session, *, event: models.Event, invited_email: str, invited_by: models.User
) -> tuple[models.EventInvitation, str]:
    """יוצר הזמנה חדשה ומחזיר אותה יחד עם הטוקן הגולמי (לשליחה במייל בלבד)."""
    cancel_open_invitations(db, event.id)
    token = generate_token()
    invitation = models.EventInvitation(
        event_id=event.id,
        invited_email=invited_email.strip().lower(),
        invited_by=invited_by.id,
        token_hash=hash_token(token),
        status=STATUS_PENDING,
        expires_at=datetime.utcnow() + timedelta(days=INVITE_TTL_DAYS),
    )
    db.add(invitation)
    return invitation, token


def accept_invitation(db: Session, token: str, user: models.User) -> bool:
    """מחבר את המשתמש לאירוע הקיים כבן/בת זוג. **לא** יוצר אירוע חדש.

    מניח שכל הבדיקות (תוקף, סטטוס, התאמת אימייל) כבר נעשו ע"י הקורא.
    אידמפוטנטי: שורת חברות קיימת מופעלת מחדש במקום שתיווצר כפילות.

    ב-Postgres דרך ``app_accept_partner_invitation`` (SECURITY DEFINER):
    המצטרף עדיין אינו מנהל האירוע, ולכן RLS היה חוסם גם את עדכון ההזמנה
    וגם את ה-INSERT ל-event_members — בדיוק אותה משפחת בעיה כמו
    ``app_register_user`` בהרשמה (ראו app/auth.py::register_user_row).
    הפונקציה גם אטומית, כך שאי אפשר להישאר עם הזמנה "מומשה" בלי חברות.
    """
    token_hash = hash_token(token.strip())

    if IS_POSTGRES:
        row = db.execute(
            text("SELECT * FROM app_accept_partner_invitation(:h, :uid, CAST(:perms AS jsonb))"),
            {
                "h": token_hash,
                "uid": user.id,
                "perms": json.dumps(list(PARTNER_PERMISSIONS)),
            },
        ).mappings().first()
        return row is not None and row.get("id") is not None

    invitation = db.scalars(
        select(models.EventInvitation).where(
            models.EventInvitation.token_hash == token_hash
        )
    ).first()
    if invitation is None:
        return False

    existing = db.scalars(
        select(models.EventMember).where(
            models.EventMember.event_id == invitation.event_id,
            models.EventMember.user_id == user.id,
        )
    ).first()
    if existing is not None:
        existing.role = PARTNER_ROLE
        existing.permissions = list(PARTNER_PERMISSIONS)
        existing.status = "active"
    else:
        db.add(models.EventMember(
            event_id=invitation.event_id,
            user_id=user.id,
            role=PARTNER_ROLE,
            permissions=list(PARTNER_PERMISSIONS),
            invited_by_id=invitation.invited_by,
            status="active",
        ))

    invitation.status = STATUS_ACCEPTED
    invitation.accepted_at = datetime.utcnow()
    invitation.accepted_by = user.id
    return True
