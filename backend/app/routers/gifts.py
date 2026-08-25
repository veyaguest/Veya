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
from app import gift_status, models, payout_service, permissions, schemas
from app.database import get_db
from app.deps import EventAccess

_view = EventAccess(permissions.GIFTS_VIEW)

router = APIRouter(prefix="/gifts", tags=["gifts"])


def _row_read(row: models.Gift, *, amounts_visible: bool) -> schemas.OwnerGiftRead:
    """ממפה שורת עסקה לתצוגת בעלי האירוע.

    המיפוי מפורש שדה-שדה (ולא ``from_attributes``) בכוונה: כך עמודה חדשה
    שתתווסף לטבלת ``gifts`` בעתיד — למשל פרטי ספק סליקה — לא תזלוג
    אוטומטית לתשובת ה-API. מה שלא נכתב כאן, לא נשלח.

    ``amounts_visible=False`` ⇒ הסכום **לא נכתב לתשובה בכלל**. לא מאופס,
    לא מעוגל, לא מוסתר בכוכביות — פשוט לא קיים ב-JSON שיוצא.
    """
    return schemas.OwnerGiftRead(
        id=row.id,
        # "מוזמן" ולא "אורח" — מונח המערכת ל"מי שקיבל הזמנה" (לקסיקון,
        # frontend/src/strings/he.ts:14). המקרה הזה נדיר: sender_name תמיד
        # נופל בשירות היצירה לשם המוזמן עצמו כשלא ניתן שם מפורש (ראו
        # gift_service.create_gift) — הערך הזה חסר רק אם השורה נערכה ישירות.
        sender_name=row.sender_name or "מוזמן",
        message=row.message,
        gift_amount_agorot=row.gift_amount_agorot if amounts_visible else None,
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

    ## שער הסכומים

    **הסכומים מוחזרים רק כשחשבון קבלת המתנות עבר את שתי הבדיקות** — של
    VEYA ושל ספק הסליקה (``payout_service.is_fully_verified``). לפני כן
    כל שדה סכום בתשובה הוא ``None``.

    זו הגנת שרת, לא הסתרה במסך: אין מסלול — DevTools, שינוי כתובת,
    פרמטר, או בקשה ידנית — שמחזיר את הסכומים לפני האימות, כי הם פשוט לא
    נכתבים לתשובה. הנתונים עצמם נשארים בטבלה ללא שינוי; זו הגבלת החזרה.

    **מה כן חוזר תמיד:** מי בירך, מה כתב, מתי, ובאיזה סטטוס — ובכללם
    ``paid_count``. כמה מתנות התקבלו הוא נתון של האירוע ולא סכום כספי,
    ובעלי האירוע רשאים לדעת שמתנות מגיעות גם בזמן שהחשבון בבדיקה.
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

    # השאלה נשאלת **פעם אחת**, דרך הפונקציה המרכזית, ומכאן היא רק מסננת
    # מה נכתב לתשובה. אין כאן העתק של התנאי "שתי הבדיקות אושרו".
    #
    # ⚠️ הבדל ידוע בין SQLite לייצור: ב-Postgres, ``payout_accounts`` מוגנת
    # ב-RLS שפתוחה לבעלים/בן-זוג/אדמין בלבד (``rls/14``). לכן **חבר-אירוע
    # (מפיק/אולם) עם הרשאת צפייה במתנות לא יראה כאן שורה, והסכומים יישארו
    # חסומים אצלו גם אחרי שהאימות הושלם.** בפיתוח מול SQLite אין RLS והוא
    # כן יראה אותם.
    #
    # ההתנהגות **נכשלת לכיוון הסגור**, ולכן אינה פרצה — אבל היא כן פער
    # תפקודי למפיקים. הפתרון כשיידרש: פונקציית SQL ``SECURITY DEFINER``
    # שמחזירה את שני הסטטוסים בלבד (לא פרטי בנק), כך שהתנאי עצמו יישאר
    # במקום אחד ב-Python. לא נבנתה כאן כדי לא להוסיף migration ידני שאינו
    # נחוץ עדיין: פיצ'ר המתנות סגור בברירת מחדל (``VEYA_GIFT_ENABLED``).
    amounts_visible = payout_service.is_fully_verified(payout_service.get(db, event.id))

    total_received_agorot = None
    total_received_display = None
    if amounts_visible:
        # רק מה שהאירוע קיבל. סכום העמלות שנגבו **לא** מחושב ולא מוחזר —
        # כמה VEYA גבתה אינו מידע של בעלי האירוע.
        total_received_agorot = sum(r.gift_amount_agorot for r in paid)
        total_received_display = gift_money.format_shekels(total_received_agorot)

    return schemas.GiftsSummary(
        amounts_visible=amounts_visible,
        total_received_agorot=total_received_agorot,
        total_received_display=total_received_display,
        paid_count=len(paid),
        total_count=len(rows),
        gifts=[_row_read(r, amounts_visible=amounts_visible) for r in rows],
    )
