"""חישובי כסף למתנה — אגורות בלבד, מספרים שלמים בלבד.

**למה אין כאן שום ``float``:** 0.1 + 0.2 אינו 0.35 בבינארי, ותשלום שנופל
באגורה אחת הוא תקלה שמתגלה רק אחרי שכסף אמיתי כבר זז. כל סכום במודול הזה
הוא ``int`` של אגורות (₪1 = 100 אגורות), וכל החישוב הוא חשבון שלמים.

**חלוקת התפקידים (החלטת בעלים):** העמלה היא **על נותן המתנה בלבד**. בעלי
האירוע מקבלים את מלוא הסכום שהאורח הזין, בלי שום ניכוי:

    הזוג מקבל   = gift_amount_agorot   (מה שהאורח הקליד)
    עמלת שירות  = 4% מהסכום            (מתווספת מעל)
    האורח משלם  = gift_amount + fee

זו הסיבה שהעמלה **מתווספת** ולא **מנוכה**. כל שינוי בכיוון הזה הוא שינוי
מהותי בהבטחה ללקוח, לא אופטימיזציה.

המודול הזה הוא מקור-האמת היחיד לחישוב. ה-Frontend לא מחשב כסף — הוא שואל
את השרת ומציג את מה שקיבל (ראו ``routers/confirm.py``).
"""
from __future__ import annotations

from dataclasses import dataclass

# שיעור עמלת השירות באחוזים. מוגדר כשלם כדי שכל החשבון יישאר בשלמים.
GIFT_FEE_PERCENT = 4

AGOROT_PER_SHEKEL = 100

# הסכום המינימלי שאפשר לשלוח: אגורה אחת. אין כאן "מינימום עסקי" מומצא —
# מגבלת מינימום/מקסימום אמיתית תיקבע ע"י ספק הסליקה כשייבחר, ולא כאן.
MIN_GIFT_AGOROT = 1


class GiftAmountError(ValueError):
    """סכום מתנה לא תקין. ההודעה מנוסחת למוזמן, לא למפתח."""


@dataclass(frozen=True)
class GiftQuote:
    """פירוט התשלום — שלושת המספרים שהאורח רואה לפני שהוא ממשיך."""

    gift_amount_agorot: int   # מה שהזוג יקבל
    fee_agorot: int           # עמלת השירות, על האורח
    total_agorot: int         # מה שהאורח משלם בפועל
    fee_percent: int = GIFT_FEE_PERCENT


def parse_amount_agorot(raw: object) -> int:
    """ממיר קלט חופשי לאגורות, או זורק ``GiftAmountError`` מנוסחת בעברית.

    הקלט מגיע ממוזמן אנונימי ברשת הפתוחה, ולכן הוא נחשב עוין עד שהוכח
    אחרת: ``bool``, ``NaN``, ``Infinity``, מחרוזת ריקה, טקסט, ``None``
    ומספרים שליליים — כולם נדחים כאן, לפני שנוגעים בהם בחשבון.
    """
    # ``bool`` הוא תת-מחלקה של ``int`` בפייתון — ``True`` היה הופך ל-1 אגורה.
    if isinstance(raw, bool) or raw is None:
        raise GiftAmountError("נשמח שתזינו סכום מתנה.")

    if isinstance(raw, int):
        agorot = raw
    elif isinstance(raw, float):
        # float נדחה כאן ולא "מעוגל בנימוס": ערך שהגיע כ-float כבר עלול
        # לשאת שגיאת ייצוג, ואנחנו לא מנחשים מה המוזמן התכוון.
        raise GiftAmountError("הסכום צריך להיות מספר שלם של אגורות.")
    elif isinstance(raw, str):
        text = raw.strip()
        if not text or not text.lstrip("-").isdigit():
            raise GiftAmountError("נשמח שתזינו סכום בשקלים.")
        agorot = int(text)
    else:
        raise GiftAmountError("נשמח שתזינו סכום בשקלים.")

    if agorot < MIN_GIFT_AGOROT:
        raise GiftAmountError("הסכום צריך להיות גדול מאפס.")
    return agorot


def fee_for(gift_amount_agorot: int) -> int:
    """עמלת השירות באגורות — חשבון שלמים בלבד, עיגול חצי-כלפי-מעלה.

    ``(סכום × 4 + 50) // 100`` הוא בדיוק ``round(סכום × 0.04)`` בלי לגעת
    ב-float: מוסיפים חצי-אגורה לפני החלוקה השלמה. דטרמיניסטי לחלוטין —
    אותו קלט תמיד ייתן אותה תוצאה, בכל מכונה ובכל גרסת פייתון.
    """
    return (gift_amount_agorot * GIFT_FEE_PERCENT + 50) // 100


def quote(gift_amount_agorot: int) -> GiftQuote:
    """מחשב את הפירוט המלא מהסכום שהזוג אמור לקבל."""
    fee = fee_for(gift_amount_agorot)
    return GiftQuote(
        gift_amount_agorot=gift_amount_agorot,
        fee_agorot=fee,
        total_agorot=gift_amount_agorot + fee,
    )


def quote_from_input(raw: object) -> GiftQuote:
    """ולידציה + חישוב במכה אחת — הכניסה היחידה שנתיבי ה-API משתמשים בה."""
    return quote(parse_amount_agorot(raw))


def format_shekels(agorot: int) -> str:
    """הצגה לבני אדם: 52000 → "₪520", 10450 → "₪104.50".

    משמש ליומן הפעילות של הזוג ולהודעות. אין כאן float — האגורות
    מופרדות בחשבון שלמים.
    """
    whole, remainder = divmod(abs(agorot), AGOROT_PER_SHEKEL)
    sign = "-" if agorot < 0 else ""
    if remainder:
        return f"{sign}₪{whole:,}.{remainder:02d}"
    return f"{sign}₪{whole:,}"
