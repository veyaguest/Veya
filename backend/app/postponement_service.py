"""שירות "נוהל דחייה" — פתיחת בקשה, הכרעת VEYA, ופתיחת מחזור חדש.

**זו נקודת הכתיבה היחידה** לטבלת ``postponement_requests`` ולמעבר בין מחזורי
אירוע. הנתיבים (``routers/postpone.py``, ``routers/postpone_admin.py``) לא
נוגעים בשדות ישירות, כדי שארבעת הכללים שלמטה ייאכפו בכל מסלול ולא ייתלו
בזכירה של מי שיוסיף נתיב חדש:

1. **כל מעבר סטטוס עובר ``postponement_status.assert_transition``.**
2. **בקשה אחת פתוחה לכל אירוע** — אין להגיש בקשה נוספת בזמן שקיימת בקשה חיה.
3. **אין מחיקה של נתוני RSVP.** ``complete`` מארכב כל מוזמן ל-
   ``guest_cycle_rsvp`` **לפני** שהוא מאתחל את התשובה. אין כאן ``DELETE``,
   ולא יהיה.
4. **פתיחת מחזור חדש מנתקת את האוטומציות מהתאריך הישן** — ``rsvp_track_active``
   ו-``rsvp_track_started_at`` מתאפסים, ולכן כל לוח הזמנים של אישורי-ההגעה
   נבנה מחדש מהתאריך החדש ולא ממשיך לפי הישן.

**מה שאין כאן:** קביעת תאריך חדש. הבקשה אינה מכילה תאריך, האישור אינו קובע
תאריך, והמערכת אינה מבקשת מהזוג לדעת מתי האירוע יתקיים כשהוא מבקש לדחות
אותו. התאריך החדש נכנס אחר כך, דרך עריכת האירוע הרגילה.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, models, postponement_status

# מצבי התצוגה של האירוע — מקור אמת יחיד לשאלה "באיזה שלב אנחנו?".
# ה-Frontend מקבל את הערך הזה מוכן ואינו מחשב אותו מחדש.
STAGE_NORMAL = "normal"              # אירוע פעיל, פרטי הליבה נעולים
STAGE_REQUESTED = "requested"        # בקשה נשלחה, ממתינה לאישור VEYA
STAGE_OPEN = "open"                  # נוהל דחייה פעיל, עדיין בלי תאריך חדש
STAGE_NEW_DATE = "new_date_set"      # נוהל דחייה פעיל, התאריך החדש כבר עודכן
STAGE_RSVP_REOPENED = "rsvp_reopened"  # מחזור חדש נפתח, טרם נשלחה הזמנה חדשה


class PostponementError(ValueError):
    """שגיאת שימוש עם נוסח עברי מוכן להצגה."""


# ── קריאה ────────────────────────────────────────────────────────────────

def open_request_of(db: Session, event_id: int) -> Optional[models.PostponementRequest]:
    """הבקשה החיה של האירוע (``pending`` או ``approved``), אם יש."""
    return db.scalars(
        select(models.PostponementRequest)
        .where(models.PostponementRequest.event_id == event_id)
        .where(models.PostponementRequest.status.in_(postponement_status.OPEN))
        .order_by(models.PostponementRequest.id.desc())
    ).first()


def latest(db: Session, event_id: int) -> Optional[models.PostponementRequest]:
    """הבקשה האחרונה של האירוע בכל סטטוס — כולל שהוכרעה, לצורך תצוגה."""
    return db.scalars(
        select(models.PostponementRequest)
        .where(models.PostponementRequest.event_id == event_id)
        .order_by(models.PostponementRequest.id.desc())
    ).first()


def edit_unlocked(db: Session, event: models.Event) -> bool:
    """האם פרטי הליבה של האירוע פתוחים כרגע לעריכה מלאה.

    זו השאלה שנעילת ``PATCH /event`` שואלת, ואין לה תשובה שנייה בקוד.
    """
    row = open_request_of(db, event.id)
    return row is not None and postponement_status.unlocks_editing(row.status)


def event_stage(db: Session, event: models.Event) -> str:
    """באיזה שלב האירוע נמצא — הערך שמזין את באנר המצב במסך.

    הסדר כאן חשוב: בקשה חיה גוברת תמיד על "מחזור חדש נפתח", כי אם נפתחה
    דחייה נוספת זה מה שהזוג צריך לראות.
    """
    row = open_request_of(db, event.id)
    if row is not None:
        if row.status == postponement_status.PENDING:
            return STAGE_REQUESTED
        # approved — פתוח לעריכה. האם כבר נקבע תאריך חדש?
        current = (event.event_date or "").strip()
        previous = (row.previous_event_date or "").strip()
        if current and current != previous:
            return STAGE_NEW_DATE
        return STAGE_OPEN
    # אין בקשה חיה. אירוע שעבר דחייה וטרם שלח הזמנה חדשה — מחזור פתוח מחדש.
    if (event.cycle_number or 1) > 1 and not event.rsvp_track_active:
        return STAGE_RSVP_REOPENED
    return STAGE_NORMAL


def pending_requests(db: Session) -> list[models.PostponementRequest]:
    """תור הבדיקה של האדמין — הוותיקה ביותר ראשונה."""
    return list(db.scalars(
        select(models.PostponementRequest)
        .where(models.PostponementRequest.status == postponement_status.PENDING)
        .order_by(models.PostponementRequest.requested_at.asc())
    ).all())


def approved_requests(db: Session) -> list[models.PostponementRequest]:
    """נהלים שאושרו ועדיין רצים — כדי שהאדמין יראה מה פתוח כרגע."""
    return list(db.scalars(
        select(models.PostponementRequest)
        .where(models.PostponementRequest.status == postponement_status.APPROVED)
        .order_by(models.PostponementRequest.reviewed_at.asc())
    ).all())


# ── כתיבה ────────────────────────────────────────────────────────────────

def _set_status(
    row: models.PostponementRequest,
    target: str,
) -> None:
    """המקום היחיד שמשנה ``row.status``. אוכף את מכונת המצבים."""
    postponement_status.assert_transition(row.status, target)
    row.status = target


def open_request(
    db: Session,
    event: models.Event,
    *,
    user_id: Optional[int],
    ip: Optional[str] = None,
) -> models.PostponementRequest:
    """בעלי האירוע מבקשים לפתוח נוהל דחייה. אין כאן תאריך, ובמכוון."""
    existing = open_request_of(db, event.id)
    if existing is not None:
        if existing.status == postponement_status.PENDING:
            raise PostponementError(
                "כבר יש בקשה שממתינה לאישור. נעדכן אתכם ברגע שהיא תאושר."
            )
        raise PostponementError(
            "נוהל הדחייה כבר פתוח — אפשר לעדכן את פרטי האירוע עכשיו."
        )

    row = models.PostponementRequest(
        event_id=event.id,
        cycle_number=event.cycle_number or 1,
        status=postponement_status.PENDING,
        requested_by_user_id=user_id,
        requested_at=datetime.utcnow(),
    )
    db.add(row)
    db.flush()
    audit.record(
        db, "postponement_request",
        event_id=event.id, user_id=user_id,
        detail="ביקשתם לפתוח נוהל דחייה",
        ip=ip,
    )
    return row


def approve(
    db: Session,
    event_id: int,
    *,
    reviewer_user_id: Optional[int],
    ip: Optional[str] = None,
) -> models.PostponementRequest:
    """מנהל VEYA מאשר. מכאן ואילך פרטי האירוע פתוחים לעריכה מלאה.

    מצלמים את התאריך והשעה **כפי שהם עכשיו**, לפני שהזוג משנה אותם. זה מה
    שמאפשר להציג אחר כך "התאריך החדש עודכן" בלי לנחש.

    כאן גם נפתחת קטגוריית ההודעות "אירוע נדחה" — היא מוקצית לאירוע רק ברגע
    הזה, ולא נולדת עם כל אירוע במערכת.
    """
    row = open_request_of(db, event_id)
    if row is None or row.status != postponement_status.PENDING:
        raise PostponementError("אין בקשת דחייה שממתינה לאישור באירוע הזה")

    event = db.get(models.Event, event_id)
    if event is None:
        raise PostponementError("האירוע לא נמצא")

    _set_status(row, postponement_status.APPROVED)
    row.reviewed_by_user_id = reviewer_user_id
    row.reviewed_at = datetime.utcnow()
    # צילום האירוע כפי שהוא **עכשיו**, לפני שהזוג נוגע בו. כל שדה שנשמר
    # בארכיון המחזור מצולם כאן, באותו רגע אחד — אחרת הארכיון היה מערבב
    # תאריך ישן עם אולם חדש ומתאר מחזור שמעולם לא התקיים.
    row.previous_event_date = event.event_date or ""
    row.previous_event_time = event.event_time or ""
    row.previous_venue_name = event.venue_name or ""
    row.previous_venue_address = event.venue_address or ""
    row.previous_venue_commit_days_before = event.venue_commit_days_before
    row.previous_snapshot_at = row.reviewed_at

    # ייבוא מקומי: ``communication`` הוא מודול כבד שמושך את שרשרת ההודעות
    # כולה, ואין סיבה שכל מי שמייבא את השירות הזה ישלם עליו.
    from app import communication

    communication.provision_postponement_message(db, event)

    audit.record(
        db, "postponement_approved",
        event_id=event_id, user_id=reviewer_user_id,
        detail="נוהל הדחייה אושר — פרטי האירוע נפתחו לעריכה",
        ip=ip,
    )
    return row


def reject(
    db: Session,
    event_id: int,
    *,
    reason: str,
    reviewer_user_id: Optional[int],
    ip: Optional[str] = None,
) -> models.PostponementRequest:
    """מנהל VEYA דוחה את הבקשה. הסיבה חובה, ומוצגת לבעלי האירוע."""
    text = (reason or "").strip()
    if not text:
        raise PostponementError("צריך לכתוב סיבה — בעלי האירוע רואים אותה")

    row = open_request_of(db, event_id)
    if row is None or row.status != postponement_status.PENDING:
        raise PostponementError("אין בקשת דחייה שממתינה לאישור באירוע הזה")

    _set_status(row, postponement_status.REJECTED)
    row.reviewed_by_user_id = reviewer_user_id
    row.reviewed_at = datetime.utcnow()
    row.rejection_reason = text[:500]

    audit.record(
        db, "postponement_rejected",
        event_id=event_id, user_id=reviewer_user_id,
        detail=f"בקשת הדחייה נדחתה: {text[:200]}",
        ip=ip,
    )
    return row


def complete(
    db: Session,
    event: models.Event,
    *,
    user_id: Optional[int],
    ip: Optional[str] = None,
) -> models.PostponementRequest:
    """בעלי האירוע מסיימים את הנוהל ופותחים מחזור אישורי-הגעה חדש.

    שישה צעדים, בסדר הזה בדיוק. הארכוב קודם לאיפוס — תמיד:

    1. שורת ``event_cycles`` עם ערכי המחזור **הישן** (מה היה התאריך, האולם).
    2. כל מוזמן מועתק ל-``guest_cycle_rsvp``.
    3. איפוס התשובה: ``rsvp_status`` → ``pending``, וכמות/הערת המוזמן מתנקות.
       ``table_number`` **לא נוגעים בו** — השיבוץ נשמר כבסיס עבודה לתאריך
       החדש (החלטת בעלים).
    4. ``event.cycle_number += 1`` — מכאן הודעות חדשות שייכות למחזור החדש,
       והישנות נשארות משויכות לקודם.
    5. ניתוק האוטומציות מהתאריך הישן.
    6. סגירת הבקשה. מכאן פרטי האירוע נעולים שוב.
    """
    row = open_request_of(db, event.id)
    if row is None or row.status != postponement_status.APPROVED:
        raise PostponementError("אין נוהל דחייה פעיל באירוע הזה")

    current_date = (event.event_date or "").strip()
    if not current_date:
        raise PostponementError(
            "לפני פתיחת מחזור חדש צריך לעדכן את תאריך האירוע"
        )
    if current_date == (row.previous_event_date or "").strip():
        raise PostponementError(
            "התאריך עדיין זהה לתאריך הקודם — עדכנו אותו ואז אפשר להמשיך"
        )

    old_cycle = event.cycle_number or 1
    now = datetime.utcnow()

    # 1 — צילום המחזור שנסגר, מתוך מה שנלכד ברגע האישור.
    #
    # ``previous_snapshot_at`` הוא סמן הקיום: בקשה שאושרה לפני שהצילום
    # המורחב נוסף למערכת נופלת בעדינות לערכי האירוע החיים — בדיוק ההתנהגות
    # שהייתה קודם — במקום לכתוב ארכיון ריק. אי אפשר להסיק זאת מהערכים
    # עצמם, כי ``previous_venue_commit_days_before = None`` הוא ערך לגיטימי.
    snapshotted = row.previous_snapshot_at is not None
    db.add(models.EventCycle(
        event_id=event.id,
        cycle_number=old_cycle,
        event_date=row.previous_event_date or "",
        event_time=row.previous_event_time or "",
        venue_name=(
            (row.previous_venue_name or "") if snapshotted else (event.venue_name or "")
        ),
        venue_address=(
            (row.previous_venue_address or "") if snapshotted
            else (event.venue_address or "")
        ),
        venue_commit_days_before=(
            row.previous_venue_commit_days_before if snapshotted
            else event.venue_commit_days_before
        ),
        # לא מצולם באישור בכוונה: ``rsvp_track_started_at`` נקבע פעם אחת
        # בהפעלת המסלול ואינו משתנה בין האישור לסגירה, ולכן הערך החי נכון
        # ממילא. ראו ``models.PostponementRequest``.
        started_at=event.rsvp_track_started_at,
        closed_at=now,
        close_reason="postponed",
    ))

    # 2 + 3 — ארכוב ואז איפוס. לעולם לא איפוס בלי ארכוב.
    guests = db.scalars(
        select(models.Guest).where(models.Guest.event_id == event.id)
    ).all()
    for g in guests:
        db.add(models.GuestCycleRsvp(
            event_id=event.id,
            guest_id=g.id,
            cycle_number=old_cycle,
            rsvp_status=g.rsvp_status,
            confirmed_count=g.confirmed_count,
            guest_note=g.guest_note,
            table_number=g.table_number,
            archived_at=now,
        ))
        g.rsvp_status = "pending"
        g.confirmed_count = None
        g.guest_note = None

    # 4 — המחזור החדש.
    event.cycle_number = old_cycle + 1

    # 5 — האוטומציות מתחילות מחדש מהתאריך החדש.
    event.rsvp_track_active = False
    event.rsvp_track_started_at = None

    # 6 — סגירת הנוהל. פרטי האירוע חוזרים להיות נעולים.
    _set_status(row, postponement_status.COMPLETED)
    row.completed_at = now

    audit.record(
        db, "postponement_completed",
        event_id=event.id, user_id=user_id,
        detail=(
            f"נפתח מחזור אישורי הגעה חדש (מחזור {event.cycle_number}); "
            f"{len(guests)} מוזמנים אופסו והתשובות הקודמות נשמרו בארכיון"
        ),
        ip=ip,
    )
    return row
