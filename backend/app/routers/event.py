"""נקודת API לפרטי האירוע (שם החתן/כלה/אולם) — שלב 6.

בשלב הנוכחי יש אירוע יחיד. הפרטים משמשים לכותרת ההזמנה שנשלחת בוואטסאפ
ולכותרת הדשבורד.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import (
    audit, communication, media, models, postponement_service, schemas, venues,
)
from app.auth import get_current_owner
from app.database import get_db
from app.deps import EventAccess, get_current_event

# עדכון פרטי הליבה של האירוע (שם/תאריך/אולם/תמונה) נשאר בעלים/אדמין בלבד —
# אין הרשאת חבר-אירוע שפותחת את זה (בשונה מהושבה/הודעות/מוזמנים, שיש להן
# הרשאה ייעודית). ראו backend/rls/RLS_REPORT.md להסבר המלא של ההחלטה הזו.
_owner_only = EventAccess(owner_only=True)

router = APIRouter(prefix="/event", tags=["event"])


# ---- נעילת פרטי האירוע ----
#
# **זו נקודת האכיפה.** הסתרת שדות במסך אינה נעילה — כל אכיפה אמיתית קורית
# כאן, בשרת. ראו ``app/postponement_service.py`` לתהליך שפותח את הנעילה.
#
# הכלל: פרט מהותי של האירוע (תאריך, שמות, סוג) נכתב **פעם אחת**. אפשר למלא
# שדה שעדיין ריק — כך אשף ההקמה, שיוצר אירוע ואז משלים פרטים, ממשיך לעבוד,
# ואירועים קיימים עם שדות ריקים לא נתקעים. שינוי ערך שכבר קיים דורש נוהל
# דחייה מאושר. זו בדיוק התבנית שכבר קיימת כאן ל-``venue_commit_days_before``.

#: מה שמותר לשנות תמיד — פרטים שאינם משנים את זהות האירוע או את לוח הזמנים.
#: תמונה ואולם משתנים תוך כדי תכנון וזה תקין; שעות השליחה הן העדפה, לא פרט.
ALWAYS_EDITABLE = frozenset({
    "venue_name", "venue_address", "invite_image",
    "rsvp_send_time", "thank_you_send_time",
})

#: שדות עם כלל משלהם בגוף ``update_event`` — לא עוברים בבדיקה הגנרית.
_SELF_GUARDED = frozenset({"venue_commit_days_before"})


def _core_fields() -> frozenset[str]:
    """שדות הליבה הנעולים — **כל מה שלא הוכרז במפורש כפתוח**.

    נגזר מ-``EventUpdate`` ולא נכתב כרשימה, כדי ששדה חדש שמישהו יוסיף בעתיד
    ייפול לצד הבטוח (נעול) ולא ידלוף החוצה בשקט.
    """
    return frozenset(schemas.EventUpdate.model_fields) - ALWAYS_EDITABLE - _SELF_GUARDED


#: שם עברי לכל שדה נעול — כדי שההודעה תדבר על "תאריך האירוע", לא על event_date.
_FIELD_LABELS: dict[str, str] = {
    "event_type": "סוג האירוע",
    "groom_name": "שם בעל/ת האירוע",
    "bride_name": "שם בעל/ת האירוע",
    "groom_parents_line": "שמות ההורים בהזמנה",
    "bride_parents_line": "שמות ההורים בהזמנה",
    "event_date": "תאריך האירוע",
    "event_time": "שעת האירוע",
}


def _assert_core_unchanged(event: models.Event, changed: dict) -> None:
    """חוסם שינוי של פרט מהותי כשהאירוע נעול. שקט כשהכול תקין.

    שדה ריק — מותר למלא. ערך זהה לקיים — עובר בשקט, כדי שטופס ששולח את כל
    השדות בחזרה לא ייכשל סתם על שדה שאיש לא נגע בו.
    """
    for key in _core_fields():
        if key not in changed:
            continue
        current = (getattr(event, key, None) or "")
        if isinstance(current, str):
            current = current.strip()
        if not current:
            continue  # עדיין ריק — כתיבה ראשונה מותרת
        incoming = (changed[key] or "")
        if isinstance(incoming, str):
            incoming = incoming.strip()
        if incoming == current:
            continue
        label = _FIELD_LABELS.get(key, "הפרט הזה")
        raise HTTPException(
            status_code=409,
            detail=(
                f"{label} נעול לעריכה, כדי שאישורי ההגעה והתזכורות יישארו "
                "מסונכרנים. אם האירוע נדחה — אפשר לפתוח נוהל דחייה מפרטי "
                "האירוע, ואז לעדכן הכול."
            ),
        )


def _describe_changed_fields(changed: dict) -> str:
    """רשימת מה שהשתנה, בעברית קריאה — שורת המשנה ביומן הפעילות מתחת ל
    "עדכנתם את פרטי האירוע". מחרוזת ריקה = אין פירוט להציג.

    כך הזוג רואה "פרטי האולם ותמונת ההזמנה" ולא "groom_name, venue_name".
    """
    categories = [
        (("event_type",), "סוג האירוע"),
        (("groom_name", "bride_name"), "שמות בעלי האירוע"),
        (("groom_parents_line", "bride_parents_line"), "שמות ההורים בהזמנה"),
        (("venue_name", "venue_address"), "פרטי האולם"),
        (("event_date", "event_time"), "תאריך ושעת האירוע"),
        (("invite_image",), "תמונת ההזמנה"),
        (("venue_commit_days_before",), "מועד סגירת הרשימה"),
        (("rsvp_send_time", "thank_you_send_time"), "שעת שליחת ההודעות"),
    ]
    labels = [label for keys, label in categories if any(k in changed for k in keys)]
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + " ו" + labels[-1]


def _event_read(db: Session, event: models.Event) -> schemas.EventRead:
    """בונה תשובה עם URL מלא לתמונת ההזמנה (במקום הנתיב הגולמי שב-DB).

    כאן גם מגיע מצב נוהל הדחייה. הוא מחושב בשרת ולא ב-Frontend כדי שיהיה
    **מקור אמת אחד** לשאלה "באיזה שלב אנחנו ומה נעול" — המסך מציג את מה
    שהשרת אומר, ואינו מסיק מצב בעצמו.
    """
    unlocked = postponement_service.edit_unlocked(db, event)
    return schemas.EventRead(
        id=event.id,
        event_type=event.event_type or "wedding",
        groom_name=event.groom_name,
        bride_name=event.bride_name,
        groom_parents_line=event.groom_parents_line or "",
        bride_parents_line=event.bride_parents_line or "",
        venue_name=event.venue_name,
        venue_address=event.venue_address or "",
        event_date=event.event_date or "",
        event_time=event.event_time or "",
        invite_image=media.to_url(event.invite_image),
        venue_commit_days_before=event.venue_commit_days_before,
        # בזמן נוהל דחייה מאושר גם מועד סגירת הרשימה נפתח מחדש — התאריך החדש
        # מחייב לוח זמנים חדש, ולכן הבחירה שנעשתה למועד הישן כבר לא רלוונטית.
        venue_commit_locked=event.venue_commit_days_before is not None and not unlocked,
        rsvp_send_time=event.rsvp_send_time or communication.DEFAULT_SEND_TIME,
        thank_you_send_time=event.thank_you_send_time or communication.DEFAULT_SEND_TIME,
        cycle_number=event.cycle_number or 1,
        event_stage=postponement_service.event_stage(db, event),
        edit_locked=not unlocked,
        locked_fields=sorted(_core_fields()),
    )


@router.get("", response_model=schemas.EventRead)
def read_event(
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    return _event_read(db, event)


@router.patch("", response_model=schemas.EventRead)
def update_event(
    payload: schemas.EventUpdate,
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_owner_only),
    user: models.User = Depends(get_current_owner),
):
    changed = payload.model_dump(exclude_unset=True)
    unlocked = postponement_service.edit_unlocked(db, event)
    if not unlocked:
        _assert_core_unchanged(event, changed)
    for key, value in changed.items():
        if key == "invite_image":
            # תמונה: data URL → קובץ; ריק → מחיקה; URL קיים → ללא שינוי.
            event.invite_image = media.resolve_incoming(
                db, value, event.invite_image, prefix=f"invite-{event.id}", optimize=True
            )
        elif key == "venue_commit_days_before":
            # מועד סגירת הרשימה — בחירה חד-פעמית. אפשר להגדיר רק פעם אחת;
            # ניסיון לשנות ערך שכבר נקבע נדחה, כי כל לוח הזמנים של אישורי
            # ההגעה נבנה סביבו. None בגוף הבקשה => התעלמות (לא מאפס בטעות).
            #
            # החריג היחיד: נוהל דחייה מאושר. תאריך חדש מחייב לוח זמנים חדש,
            # ולכן שם הבחירה נפתחת מחדש (דרישת "מועד סגירת רשימה חדש").
            if value is None:
                continue
            if not isinstance(value, int) or not (1 <= value <= 10):
                raise HTTPException(
                    status_code=400,
                    detail="בחרו כמה ימים לפני האירוע צריך למסור לאולם (בין 1 ל-10).",
                )
            if event.venue_commit_days_before is not None and not unlocked:
                if event.venue_commit_days_before != value:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "מועד סגירת הרשימה כבר נקבע — כל לוח הזמנים "
                            "של אישורי ההגעה נבנה סביבו. אם האירוע נדחה, "
                            "אפשר לפתוח נוהל דחייה ואז לקבוע מועד חדש."
                        ),
                    )
                continue
            event.venue_commit_days_before = value
        elif key in ("rsvp_send_time", "thank_you_send_time"):
            # None בגוף הבקשה => התעלמות (לא מאפס בטעות) — כמו venue_commit_days_before.
            if value is None:
                continue
            try:
                setattr(event, key, communication.validate_send_time(value))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        else:
            setattr(event, key, (value or "").strip())
    # מאגר אולמות משותף: כל שם+כתובת שזוג שומר נרשם למאגר, כדי שזוגות אחרים
    # יקבלו הצעת השלמה עם הכתובת המוכנה. שם ריק => נדלג (record_venue מתעלם).
    if "venue_name" in changed or "venue_address" in changed:
        venues.record_venue(db, event.venue_name, event.venue_address or "")
    audit.record(
        db, "update_event",
        event_id=event.id, user_id=user.id,
        detail=_describe_changed_fields(changed),
        ip=request.client.host if request.client else None,
    )
    db.commit()
    return _event_read(db, event)


@router.get("/audit", response_model=list[schemas.AuditLogRow])
def read_audit(
    limit: int = 30,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_current_event),
):
    """יומן הפעילות של האירוע — מי עשה מה ומתי (למנהלי האירוע בלבד).

    שני המנהלים (בעלים ובן/בת זוג) רואים את אותו יומן בדיוק — הוא תלוי
    אירוע, לא משתמש.
    """
    stmt = (
        select(models.AuditLog)
        .where(models.AuditLog.event_id == event.id)
        .order_by(models.AuditLog.created_at.desc())
        .limit(max(1, min(limit, 100)))
    )
    rows = db.scalars(stmt).all()

    # שם המבצע בשאילתה אחת לכל השורות (ולא db.get בלולאה — N+1), באותה
    # תבנית שכבר קיימת ב-routers/event_members.py.
    actor_ids = {r.user_id for r in rows if r.user_id is not None}
    names: dict[int, str] = {}
    if actor_ids:
        for u in db.scalars(
            select(models.User).where(models.User.id.in_(actor_ids))
        ).all():
            names[u.id] = u.display_name or u.email.split("@")[0]

    result = []
    for row in rows:
        item = schemas.AuditLogRow.model_validate(row)
        item.actor_name = names.get(row.user_id, "") if row.user_id else ""
        item.actor_id = row.user_id
        result.append(item)
    return result
