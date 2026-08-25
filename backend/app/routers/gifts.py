"""מסך "מתנות באשראי" לבעלי האירוע — קריאה בלבד, על גבי טבלת ``gifts`` הקיימת.

**אין כאן שום נתיב כתיבה.** יצירת עסקאות ועדכון סטטוס קורים אך ורק דרך
המסלול הציבורי (``routers/confirm.py`` + ``gift_service``), בדיוק כמו
שה-RLS כבר אוכף (``rls/13_gifts_rls.sql`` — אין מדיניות INSERT/UPDATE
בכלל, רק שתי פונקציות SECURITY DEFINER מבוקרות). המסך הזה רק מציג.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import gift as gift_money
from app import gift_status, models, permissions, schemas
from app.database import get_db
from app.deps import EventAccess

_view = EventAccess(permissions.GIFTS_VIEW)

router = APIRouter(prefix="/gifts", tags=["gifts"])


def _row_read(row: models.Gift) -> schemas.OwnerGiftRead:
    """ממפה שורת עסקה לתצוגת בעלי האירוע.

    המיפוי מפורש שדה-שדה (ולא ``from_attributes``) בכוונה: כך עמודה חדשה
    שתתווסף לטבלת ``gifts`` בעתיד — למשל פרטי ספק סליקה — לא תזלוג
    אוטומטית לתשובת ה-API. מה שלא נכתב כאן, לא נשלח.
    """
    return schemas.OwnerGiftRead(
        id=row.id,
        # "מוזמן" ולא "אורח" — מונח המערכת ל"מי שקיבל הזמנה" (לקסיקון,
        # frontend/src/strings/he.ts:14). המקרה הזה נדיר: sender_name תמיד
        # נופל בשירות היצירה לשם המוזמן עצמו כשלא ניתן שם מפורש (ראו
        # gift_service.create_gift) — הערך הזה חסר רק אם השורה נערכה ישירות.
        sender_name=row.sender_name or "מוזמן",
        message=row.message,
        gift_amount_agorot=row.gift_amount_agorot,
        status=row.status,
        created_at=row.created_at,
    )


@router.get("", response_model=schemas.GiftsSummary)
def list_gifts(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_view),
):
    """כל המתנות של האירוע + סיכום.

    **הסיכום נספר רק מ-``paid``** — עסקה שנכשלה, בוטלה, עדיין ממתינה, או
    אפילו הוחזרה (``refunded``) אינה "מתנה שהתקבלה". זה נאכף כאן, בשרת —
    לא משהו שה-Frontend מסנן, כדי שהמספר בראש המסך תמיד יהיה נכון.

    התשובה מכילה **רק** את מה שבעלי האירוע צריכים לראות (ראו
    ``schemas.OwnerGiftRead``): שם, סכום, ברכה, תאריך וסטטוס. עמלת
    השירות והסכום ששילם המוזמן אינם חלק מהתשובה כלל.
    """
    rows = list(
        db.scalars(
            select(models.Gift)
            .where(models.Gift.event_id == event.id)
            # id כשובר-שוויון: שתי מתנות שנוצרו באותה שנייה (שכיח בבדיקות,
            # ואפשרי גם בייצור) עדיין חייבות להופיע בסדר יצירה עקבי.
            .order_by(models.Gift.created_at.desc(), models.Gift.id.desc())
        ).all()
    )

    paid = [r for r in rows if r.status == gift_status.PAID]
    # רק מה שהאירוע קיבל. סכום העמלות שנגבו **לא** מחושב ולא מוחזר —
    # כמה VEYA גבתה אינו מידע של בעלי האירוע.
    total_received_agorot = sum(r.gift_amount_agorot for r in paid)

    return schemas.GiftsSummary(
        total_received_agorot=total_received_agorot,
        total_received_display=gift_money.format_shekels(total_received_agorot),
        paid_count=len(paid),
        total_count=len(rows),
        gifts=[_row_read(r) for r in rows],
    )
