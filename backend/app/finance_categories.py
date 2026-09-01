"""קטלוג קטגוריות ההוצאה — מקור האמת היחיד לרשימת "מה בדרך כלל משלמים".

הקטלוג הוא **הצעה, לא סכימה**. הוא קיים כדי שזוג שנכנס למסך ריק לא יצטרך
להמציא מאפס את רשימת ההוצאות של אירוע — לא כדי לכלוא אותו ברשימה סגורה.
לכן ``EventExpense.category``/``item_key`` הם מחרוזות חופשיות ב-DB: אפשר
תמיד להוסיף שורה משלך, והקטלוג יכול לגדול בלי מיגרציה.

## למה הקטלוג יושב בשרת ולא ב-Frontend

הוא מוגש דרך ``GET /finance/categories``. מקור אחד, שני צרכנים — המסך
והחישוב — ואין דרך שהם יסטו זה מזה. קטלוג שהיה משוכפל ל-TypeScript היה
מתחיל להיסדק בעדכון הראשון.

## Event-first — קטגוריה יודעת לאיזה אירוע היא שייכת

"כלה", "חתן" ו"טבעות" הן קטגוריות **חתונתיות**. הצגתן בברית או באירוע
עסקי אינה טעות ניסוח אלא מוצר שבור. לכן לכל קטגוריה יש ``event_types``,
ו-``catalog_for(event_type)`` מחזיר רק את מה שרלוונטי. הסוגים שאין להם
קטגוריות לבוש חתונתיות מקבלים במקומן קטגוריה אחת — "לבוש והופעה".

זו בדיוק שכבת ההתאמה שהארכיטקטורה דורשת (``event_type`` + לקסיקון), ולא
הסתעפות קוד במסך. הוספת סוג אירוע חדש לא מצריכה נגיעה בקובץ הזה — הוא
פשוט מקבל את קבוצת ברירת המחדל.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ── שיטות חישוב ─────────────────────────────────────────────────────────
# מוגדרות כאן ולא ב-``finance.py`` כדי שהקטלוג יוכל להצהיר עליהן בלי
# לייבא את מנוע החישוב. ``finance.py`` מייבא אותן מכאן — כיוון אחד בלבד.

#: סכום קבוע. לא מוכפל בכלום.
FIXED = "fixed"
#: מחיר לאורח שמגיע בפועל (מנה, אלכוהול, מתנה לאורח).
PER_ATTENDEE = "per_attendee"
#: מחיר למוזמן שהוזמן (הזמנה מודפסת, מעטפה, משלוח) — כמות אחרת לגמרי.
PER_GUEST = "per_guest"
#: מחיר ליחידה × כמות שהזוג מזין (מספרי שולחן, אלבומים).
PER_UNIT = "per_unit"

CALC_METHODS = (FIXED, PER_ATTENDEE, PER_GUEST, PER_UNIT)

#: סוגי אירוע שבהם קטגוריות הלבוש החתונתיות ("כלה"/"חתן"/"טבעות") רלוונטיות.
_WEDDING_LIKE = ("wedding", "henna")


@dataclass(frozen=True)
class ExpenseItem:
    """פריט מוצע בתוך קטגוריה."""

    key: str
    label: str
    #: שיטת החישוב שהפריט **נפתח** איתה. הזוג רשאי לשנות אותה בכל רגע —
    #: זו ברירת מחדל חכמה, לא כלל. "מנה" נפתחת כמחיר-לאורח כי כך היא
    #: נמכרת בישראל; "הזמנה מודפסת" נפתחת כמחיר-למוזמן מאותה סיבה.
    calc_method: str = FIXED
    #: האם להציג לפריט הזה את שדות ההתחייבות (כמות מובטחת + מינימום כספי).
    #: נכון לשורות שנמכרות בהתקשרות עם מינימום — קודם כול המנה באולם.
    supports_commitment: bool = False


@dataclass(frozen=True)
class ExpenseCategory:
    """קטגוריה — כותרת אחת ורשימת פריטים מוצעים."""

    key: str
    label: str
    items: tuple[ExpenseItem, ...]
    #: לאילו סוגי אירוע הקטגוריה שייכת. ``None`` = כולם.
    event_types: Optional[tuple[str, ...]] = None
    #: לאילו סוגי אירוע הקטגוריה **לא** שייכת. שימושי כשקל יותר לתאר
    #: את החריג מאשר את הרשימה המלאה.
    excluded_event_types: tuple[str, ...] = ()


def _item(key: str, label: str, method: str = FIXED, *, commitment: bool = False) -> ExpenseItem:
    return ExpenseItem(key=key, label=label, calc_method=method, supports_commitment=commitment)


# ════════════════════════════════════════════════════════════════════════
#  הקטלוג
# ════════════════════════════════════════════════════════════════════════

CATALOG: tuple[ExpenseCategory, ...] = (
    ExpenseCategory(
        key="venue_food",
        label="אולם ואוכל",
        items=(
            # שורת המנה היא הלב הכספי של האירוע הישראלי, ולכן היא היחידה
            # שנפתחת עם שדות ההתחייבות פתוחים. "מינימום התחייבות" **אינו**
            # פריט נפרד בקטלוג בכוונה: הוא שדה על שורת המנה. פריט נפרד
            # היה נספר פעמיים בסיכום — פעם כמנות ופעם כמינימום.
            _item("meal_price", "מחיר מנה", PER_ATTENDEE, commitment=True),
            _item("alcohol", "אלכוהול", PER_ATTENDEE),
            _item("menu_upgrade", "שדרוג תפריט", PER_ATTENDEE),
            _item("special_meals", "מנות מיוחדות", PER_UNIT),
            _item("cake", "עוגה"),
            _item("desserts", "קינוחים"),
            _item("extras", "תוספות"),
            _item("overtime", "שעות נוספות"),
            _item("parking", "חניה"),
            _item("security", "אבטחה"),
            _item("venue_other", "הוצאות נוספות של האולם"),
        ),
    ),
    ExpenseCategory(
        key="photo",
        label="צילום",
        items=(
            _item("stills", "צילום סטילס"),
            _item("video", "וידאו"),
            _item("second_shooter", "צלם נוסף"),
            _item("family_photographer", "צלם משפחות"),
            _item("drone", "רחפן"),
            _item("albums", "אלבומים", PER_UNIT),
            _item("parent_albums", "אלבומי הורים", PER_UNIT),
            _item("clip", "קליפ"),
            _item("photo_overtime", "שעות נוספות"),
        ),
    ),
    ExpenseCategory(
        key="music",
        label="מוזיקה, סאונד ותאורה",
        items=(
            _item("dj", "DJ"),
            _item("band", "להקה"),
            _item("singer", "זמר/אמן"),
            _item("sound", "סאונד"),
            _item("lighting", "תאורה"),
            _item("screens", "מסכים"),
            _item("led", "LED"),
            _item("effects", "אפקטים"),
            _item("smoke", "עשן"),
            _item("confetti", "קונפטי"),
            _item("special_acts", "אטרקציות מיוחדות"),
        ),
    ),
    ExpenseCategory(
        key="design",
        label="עיצוב",
        items=(
            # "חופה" היא מבנה הטקס. בברית/בר מצווה אין חופה, ולכן היא
            # מסוננת החוצה יחד עם שאר הקטגוריות החתונתיות — ראו
            # ``_CEREMONY_ONLY_ITEMS`` למטה.
            _item("chuppah", "חופה"),
            _item("table_design", "עיצוב שולחנות", PER_UNIT),
            _item("flowers", "פרחים"),
            _item("centerpieces", "מרכזי שולחן", PER_UNIT),
            _item("reception_design", "עיצוב קבלת פנים"),
            _item("bar_design", "עיצוב בר"),
            _item("signage", "שילוט"),
            _item("table_numbers", "מספרי שולחן", PER_UNIT),
            _item("special_design", "עיצוב מיוחד"),
        ),
    ),
    ExpenseCategory(
        key="bride",
        label="כלה",
        event_types=_WEDDING_LIKE,
        items=(
            _item("dress_1", "שמלה ראשונה"),
            _item("dress_2", "שמלה שנייה"),
            _item("dress_3", "שמלה שלישית"),
            _item("veil", "הינומה"),
            _item("bolero", "עליונית/בולרו"),
            _item("alterations", "תיקונים"),
            _item("shoes", "נעליים"),
            _item("jewelry", "תכשיטים"),
            _item("accessories", "אביזרים"),
            _item("makeup", "איפור"),
            _item("makeup_trial", "ניסיון איפור"),
            _item("hair", "שיער"),
            _item("hair_trial", "ניסיון שיער"),
            _item("nails", "ציפורניים"),
            _item("day_of_styling", "ליווי ביום האירוע"),
        ),
    ),
    ExpenseCategory(
        key="groom",
        label="חתן",
        event_types=_WEDDING_LIKE,
        items=(
            _item("suit", "חליפה"),
            _item("shirt", "חולצה"),
            _item("vest", "וסט"),
            _item("tie", "עניבה/פפיון"),
            _item("belt", "חגורה"),
            _item("groom_shoes", "נעליים"),
            _item("extra_clothes", "בגדים נוספים"),
            _item("groom_alterations", "תיקונים"),
            _item("groom_hair", "שיער"),
            _item("tallit", "טלית"),
            _item("kippah", "כיפה"),
        ),
    ),
    # התחליף לשתי הקטגוריות שמעל בכל סוג אירוע שאינו חתונה/חינה. קטגוריה
    # אחת ולא שתיים: בבר מצווה או באירוע עסקי אין שני "צדדים" של לבוש.
    ExpenseCategory(
        key="attire",
        label="לבוש והופעה",
        excluded_event_types=_WEDDING_LIKE,
        items=(
            _item("outfit", "לבוש"),
            _item("extra_outfit", "לבוש נוסף"),
            _item("attire_alterations", "תיקונים"),
            _item("attire_shoes", "נעליים"),
            _item("attire_jewelry", "תכשיטים"),
            _item("attire_accessories", "אביזרים"),
            _item("attire_makeup", "איפור"),
            _item("attire_hair", "שיער"),
            _item("attire_day_of", "ליווי ביום האירוע"),
        ),
    ),
    ExpenseCategory(
        key="rings",
        label="טבעות ותכשיטים",
        event_types=_WEDDING_LIKE,
        items=(
            _item("bride_ring", "טבעת כלה"),
            _item("groom_ring", "טבעת חתן"),
            _item("engraving", "חריטה"),
            _item("extra_jewelry", "תכשיטים נוספים"),
        ),
    ),
    ExpenseCategory(
        key="ceremony",
        label="רבנות וטקס",
        # אירוע עסקי ואירוע משפחתי אינם טקס דתי. שאר הסוגים — כן.
        excluded_event_types=("business", "family", "other"),
        items=(
            _item("file_opening", "פתיחת תיק"),
            _item("rabbi", "רב"),
            _item("fees", "אגרות"),
            _item("documents", "מסמכים"),
            _item("ceremony_other", "הוצאות טקס נוספות"),
        ),
    ),
    ExpenseCategory(
        key="invitations",
        label="הזמנות ומיתוג",
        items=(
            _item("digital_invite", "הזמנה דיגיטלית"),
            # שלוש השורות האלה נפתחות כמחיר **למוזמן** ולא לאורח: מדפיסים
            # ושולחים לפי מי שהוזמן, לא לפי מי שבסוף הגיע.
            _item("printed_invite", "הזמנה מודפסת", PER_GUEST),
            _item("invite_design", "עיצוב"),
            _item("printing", "הדפסה", PER_GUEST),
            _item("envelopes", "מעטפות", PER_GUEST),
            _item("shipping", "משלוח", PER_GUEST),
            _item("menus", "תפריטים", PER_ATTENDEE),
            _item("seating_cards", "פתקי הושבה", PER_ATTENDEE),
            _item("invite_table_numbers", "מספרי שולחן", PER_UNIT),
            _item("branding", "מיתוג"),
        ),
    ),
    ExpenseCategory(
        key="attractions",
        label="אטרקציות",
        items=(
            _item("magnets", "מגנטים"),
            _item("photo_booth", "עמדת צילום"),
            _item("booth_360", "עמדת 360"),
            _item("polaroid", "פולארויד"),
            _item("balloons", "בלונים"),
            _item("props", "אביזרים"),
            _item("attraction_smoke", "עשן"),
            _item("attraction_confetti", "קונפטי"),
            _item("fireworks", "זיקוקים"),
            _item("guest_gifts", "מתנות לאורחים", PER_ATTENDEE),
            _item("food_stations", "תחנות אוכל/ממתקים"),
        ),
    ),
    ExpenseCategory(
        key="transport",
        label="הסעות וחניה",
        items=(
            # "רכב לזוג" מנוסח בלקסיקון (``label_for``) — בברית או באירוע
            # עסקי "הזוג" אינו הניסוח הנכון.
            _item("hosts_car", "רכב לבעלי האירוע"),
            _item("car_decoration", "קישוט רכב"),
            _item("shuttles", "הסעות", PER_UNIT),
            _item("driver", "נהג"),
            _item("transport_parking", "חניה"),
            _item("parking_rental", "השכרת חניה"),
        ),
    ),
    ExpenseCategory(
        key="production",
        label="ניהול והפקה",
        items=(
            _item("event_manager", "מנהל אירוע"),
            _item("producer", "מפיק"),
            _item("assistant", "עוזר"),
            _item("vendor_coordination", "תיאום ספקים"),
            _item("day_of_management", "ניהול ביום האירוע"),
        ),
    ),
    ExpenseCategory(
        key="tips",
        label="טיפים",
        items=(
            _item("waiters_tip", "מלצרים"),
            _item("bartenders_tip", "ברמנים"),
            _item("manager_tip", "מנהל אירוע"),
            _item("dj_tip", "DJ"),
            _item("photo_tip", "צילום"),
            _item("drivers_tip", "נהגים"),
            _item("other_tips", "אחרים"),
        ),
    ),
    ExpenseCategory(
        key="other",
        label="הוצאות נוספות",
        # אין פריטים מוצעים — זו הקטגוריה שבה הזוג כותב מה שהוא רוצה.
        # קיימת בקטלוג ולא כמקרה קצה בקוד, כדי ש"הוצאה חופשית" תהיה
        # אזרחית שוות-זכויות בכל מסך ובכל סיכום.
        items=(),
    ),
)

#: פריטים שהם חתונתיים בתוך קטגוריה שאינה חתונתית. מסוננים בנפרד כדי
#: שלא נצטרך לשכפל קטגוריה שלמה בגלל שורה אחת.
_WEDDING_ONLY_ITEMS = frozenset({"chuppah"})

_BY_KEY = {c.key: c for c in CATALOG}


def _applies(category: ExpenseCategory, event_type: str) -> bool:
    if category.event_types is not None and event_type not in category.event_types:
        return False
    return event_type not in category.excluded_event_types


def catalog_for(event_type: str) -> list[ExpenseCategory]:
    """הקטגוריות והפריטים הרלוונטיים לסוג האירוע הזה.

    סוג שאינו מוכר מקבל את ברירת המחדל הרחבה (בלי הקטגוריות החתונתיות),
    ולא רשימה ריקה — מוצר שבור עדיף שלא ייווצר מטעות הקלדה בשם סוג.
    """
    wedding_like = event_type in _WEDDING_LIKE
    result: list[ExpenseCategory] = []
    for category in CATALOG:
        if not _applies(category, event_type):
            continue
        if wedding_like:
            result.append(category)
            continue
        items = tuple(i for i in category.items if i.key not in _WEDDING_ONLY_ITEMS)
        result.append(ExpenseCategory(
            key=category.key,
            label=category.label,
            items=items,
            event_types=category.event_types,
            excluded_event_types=category.excluded_event_types,
        ))
    return result


def category_label(key: str) -> str:
    """תווית הקטגוריה לתצוגה. מפתח לא מוכר חוזר כמו שהוא ולא מפיל דבר —
    שורה ישנה שקטגוריה שלה הוסרה מהקטלוג עדיין צריכה להופיע בסיכום."""
    category = _BY_KEY.get(key)
    return category.label if category else key


def is_known_calc_method(method: str) -> bool:
    return method in CALC_METHODS
