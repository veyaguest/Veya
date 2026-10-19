"""מחזור האירוע — התנאי היחיד שמפריד בין "מה שלחנו עכשיו" ל"מה כבר שלחנו".

אירוע שנדחה מקבל **מחזור חדש** (``Event.cycle_number``). ההודעות של המחזור
הקודם נשארות ב-DB במלואן, אבל אינן חלק מהתמונה שהזוג רואה: אחרי דחייה, מוזמן
שקיבל הזמנה למועד הישן צריך להיספר כ"טרם קיבל הזמנה" — אחרת לא תישלח אליו
ההזמנה החדשה, והוא פשוט לא יידע שהאירוע זז.

## הכלל: הצמצום חל על **הודעות יוצאות בלבד**

הודעה נכנסת (תשובת אורח) נכללת תמיד, בכל מחזור. שתי סיבות:

1. **זו לא "היסטוריה" — זה יומן.** מה שהזוג לא אמור לראות אחרי דחייה הוא
   *סטטוס* ההגעה הישן, והוא באמת מתאפס (``postponement_service.complete``).
   יומן ההודעות הכרונולוגי הוא דבר אחר, ואין סיבה לחתוך אותו.
2. **הודעות נכנסות נכתבות ב-Postgres דרך ``app_record_guest_rsvp_reply`` /
   ``app_record_confirm_message``** (SECURITY DEFINER, ``rls/01_helpers_and_grants.sql``)
   ולא דרך ה-ORM. הפונקציות האלה אינן מכירות את ``cycle_number``, ולכן שורה
   שנוצרת בהן מקבלת את ברירת המחדל 1. לו היינו מצמצמים גם נכנסות, תשובה
   אמיתית שהגיעה במחזור 2 הייתה **נעלמת מהמסך**. הכלל למעלה מונע את זה
   מראש, במקום להישען על כך שמישהו יזכור לסנכרן את ה-SQL.

**כל שאילתה שסופרת שליחות מסננת דרך ``current_sends``.** שאילתה שנוגעת בכל
ההיסטוריה (מחיקת אירוע, חקירה) לא מסננת — ובמכוון.

## רק שליחות אמיתיות (2026-10-19, החלטת הבעלים)

כש-WhatsApp יוצא באמת (``WHATSAPP_MODE`` = ``meta_test``/``meta``), שורות של מצב
ההדגמה (``provider == "mock"``) **אינן שליחות**: הן לא נספרות בסטטוס ("נשלחו/
נמסרו"), לא נחשבות "כבר קיבל הזמנה" ולא "כבר קיבל את התזכורת" — כך מוזמן שקיבל
רק הזמנת הדגמה מקבל הזמנה אמיתית. במצב mock הכול נשאר כמו שהיה (הדגמה מלאה).
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, or_

from app import models


def of(event: Optional[models.Event]) -> int:
    """מספר המחזור של האירוע. חסר/ישן => 1 (האירוע המקורי)."""
    if event is None:
        return 1
    return event.cycle_number or 1


def current_sends(event: Optional[models.Event]):
    """תנאי SQLAlchemy: שליחות של המחזור הנוכחי בלבד (נכנסות תמיד נכללות).

    במחזור 1 מתקבלות גם שורות עם ``NULL`` — רשת ביטחון לכל DB שבו העמודה
    נוספה בלי למלא ערך לשורות קיימות. במחזורים מתקדמים יותר ``NULL`` הוא
    בהכרח נתון ישן, ולכן אינו נכלל.
    """
    number = of(event)
    if number == 1:
        cycle = or_(
            models.Message.cycle_number == 1,
            models.Message.cycle_number.is_(None),
        )
    else:
        cycle = models.Message.cycle_number == number
    if counts_demo_sends():
        return or_(models.Message.direction != "outbound", cycle)
    return or_(
        models.Message.direction != "outbound",
        and_(cycle, models.Message.provider != MOCK_PROVIDER),
    )


MOCK_PROVIDER = "mock"


def counts_demo_sends() -> bool:
    """האם שורות של מצב ההדגמה נחשבות שליחות — רק כשאנחנו עצמנו במצב הדגמה."""
    from app import messaging

    return messaging.whatsapp_mode() == messaging.MODE_MOCK


def is_real_send(msg: "models.Message") -> bool:
    """אותו כלל כמו ``current_sends`` (בלי המחזור), לשורה שכבר נטענה."""
    return counts_demo_sends() or msg.provider != MOCK_PROVIDER
