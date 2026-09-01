"""תבניות ההוצאות — **תבנית משלה לכל סוג אירוע.**

VEYA אינה מחשבון תקציב גנרי. זוג שיוצר חתונה וזוג שיוצר ברית לא אמורים
לקבל את אותה רשימה: לברית יש מוהל ואין חופה, לאירוע עסקי יש מרצה ותגי
שם ואין שמלה. לכן אין כאן קטלוג אחד שמסונן — יש **תבנית לכל סוג**.

## מקור האמת: 7 סוגי אירוע, ולא אחד יותר

הרשימה כאן חייבת להישאר זהה ל-``event_terms.EVENT_TERMS``, ל-
``schemas.EventType`` ול-``frontend/src/strings/eventTypes.ts``. **אין
ליצור כאן סוג אירוע שלא קיים שם** — תבנית לסוג שלא ניתן ליצור היא קוד
מת שמטעה את מי שיקרא אותו אחר כך:

    wedding · henna · bar_mitzvah · bat_mitzvah · brit · brita · business

יש בדיקה שנועלת בדיוק את זה (``tests/test_finance_engine.py``).

## התבנית היא ברירת מחדל חכמה, לא רשימה סגורה

הזוג תמיד יכול להוסיף, למחוק, לערוך, לשנות סכום/כמות/ספק, להחליף שיטת
חישוב, ולסמן משוער/סוכם ושולם/לא שולם. ``EventExpense.category`` ו-
``item_key`` הם מחרוזות חופשיות ב-DB בדיוק כדי שזה יהיה אפשרי בלי
מיגרציה.

## ``is_default`` — למה המסך לא מציף

המיפוי כאן עשיר (עשרות פריטים לכל סוג), אבל מסך תקציב עם 60 שורות
פתוחות הוא מסך שסוגרים. לכן לכל פריט יש ``is_default``:

    is_default=True    מוצע מיד — "רוב האירועים מסוג הזה משלמים על זה"
    is_default=False   קיים בקטלוג, נמצא תחת "הוספת הוצאה"

כך התבנית יכולה להיות מקיפה מאוד בלי שהמסך ייראה עמוס.

## מבנה הקובץ

``ITEMS`` הוא מאגר שטוח של כל הפריטים במערכת (מפתח ← הגדרה), ו-
``TEMPLATES`` מרכיב מהם קטגוריות לכל סוג. כך תווית של פריט משותף
("DJ", "צילום סטילס") מוגדרת **פעם אחת** ולא שבע, ותיקון ניסוח לא
דורש שבע עריכות.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ── שיטות חישוב ─────────────────────────────────────────────────────────
# מוגדרות כאן ולא ב-``finance.py`` כדי שהתבניות יוכלו להצהיר עליהן בלי
# לייבא את מנוע החישוב. ``finance.py`` מייבא מכאן — כיוון אחד בלבד.

#: סכום קבוע. לא מוכפל בכלום — וגם "הזנה ידנית" נופלת לכאן: הזוג מקליד
#: את הסכום הסופי והמערכת לא מחשבת אותו.
FIXED = "fixed"
#: מחיר לאדם שמגיע בפועל (מנה, אלכוהול, מתנה לאורח).
#: **כאן חיה גם ההתחייבות לספק**: שורה כזו יכולה לשאת ``committed_quantity``
#: ו-``min_total_agorot``, ואז החיוב הוא
#: ``MAX(MAX(מגיעים, התחייבות) × מחיר, מינימום כספי)``.
PER_ATTENDEE = "per_attendee"
#: מחיר למוזמן שהוזמן (הזמנה מודפסת, מעטפה, משלוח) — כמות אחרת לגמרי.
PER_GUEST = "per_guest"
#: מחיר ליחידה × כמות שהזוג מזין (מספרי שולחן, אלבומים, הסעות).
PER_UNIT = "per_unit"
#: אחוז מסך שאר ההוצאות — לטיפים ולדמי הפקה שנקובים באחוזים.
PERCENT = "percent"

CALC_METHODS = (FIXED, PER_ATTENDEE, PER_GUEST, PER_UNIT, PERCENT)

#: שבעת סוגי האירוע שקיימים בפועל במערכת. ראו ההסבר בראש הקובץ.
EVENT_TYPES = (
    "wedding", "henna", "bar_mitzvah", "bat_mitzvah", "brit", "brita", "business",
)


@dataclass(frozen=True)
class ExpenseItem:
    """פריט מוצע — הצעה למילוי, לא שדה חובה."""

    key: str
    label: str
    #: שיטת החישוב שהפריט **נפתח** איתה. הזוג רשאי לשנות אותה מיד. "מנה"
    #: נפתחת כמחיר-לאדם כי כך היא נמכרת בישראל; "הזמנה מודפסת" נפתחת
    #: כמחיר-למוזמן מאותה סיבה.
    calc_method: str = FIXED
    #: האם להציג לפריט את שדות ההתחייבות (כמות מובטחת + מינימום כספי).
    #: נכון לשורות שנמכרות בהתקשרות עם מינימום — קודם כול המנה באולם.
    supports_commitment: bool = False
    #: כמות פתיחה ל-``per_unit`` / ``percent`` (באחוזים שלמים).
    default_quantity: Optional[int] = None


@dataclass(frozen=True)
class TemplateItem:
    """פריט **בתוך תבנית של סוג אירוע** — עם הסדר וההצעה שלו שם.

    אותו פריט יכול להיות ברירת מחדל בסוג אחד ובקטלוג בלבד באחר: DJ הוא
    ברירת מחדל בחתונה ובבר מצווה, אבל בברית רוב האירועים מסתדרים בלי.
    """

    key: str
    label: str
    calc_method: str
    supports_commitment: bool
    default_quantity: Optional[int]
    is_default: bool
    sort_order: int


@dataclass(frozen=True)
class ExpenseCategory:
    key: str
    label: str
    items: tuple[TemplateItem, ...]


def _i(
    key: str,
    label: str,
    method: str = FIXED,
    *,
    commitment: bool = False,
    quantity: Optional[int] = None,
) -> ExpenseItem:
    return ExpenseItem(key, label, method, commitment, quantity)


# ════════════════════════════════════════════════════════════════════════
#  מאגר הפריטים — כל פריט מוגדר **פעם אחת**
# ════════════════════════════════════════════════════════════════════════
# פריט משותף ("DJ", "צילום סטילס", "הסעות") מוגדר כאן פעם אחת ומשמש בכל
# התבניות שצריכות אותו. תיקון ניסוח = עריכה אחת, לא שבע.

ITEMS: dict[str, ExpenseItem] = {i.key: i for i in (
    # ── מקום ואירוח ──────────────────────────────────────────────────
    _i("hall", "אולם / גן"),
    _i("venue_rental", "השכרת המקום"),
    _i("venue_equipment", "ציוד המקום"),
    _i("meal_price", "מחיר מנה", PER_ATTENDEE, commitment=True),
    _i("venue_extras", "תוספות לאולם"),
    _i("suite", "חדר לבעלי האירוע"),
    _i("waiters", "מלצרים ותוספות שירות"),
    _i("overtime", "שעות נוספות"),

    # ── אוכל ומשקאות ─────────────────────────────────────────────────
    _i("catering", "קייטרינג"),
    _i("meals", "מנות", PER_ATTENDEE, commitment=True),
    _i("refreshments", "כיבוד"),
    _i("bar", "בר"),
    _i("alcohol", "אלכוהול", PER_ATTENDEE),
    _i("wine", "יין"),
    _i("cocktails", "קוקטיילים"),
    _i("coffee", "קפה"),
    _i("drinks", "שתייה", PER_ATTENDEE),
    _i("desserts", "קינוחים"),
    _i("sweets", "מתוקים"),
    _i("cake", "עוגה"),
    _i("food_extras", "תוספות מזון"),
    _i("food_vendors", "ספקי אוכל נוספים"),
    _i("food_stations", "תחנות אוכל"),

    # ── מוזיקה והפקה ─────────────────────────────────────────────────
    _i("dj", "DJ"),
    _i("band", "להקה / מוזיקה חיה"),
    _i("singer", "זמר/אמן"),
    _i("music", "מוזיקה"),
    _i("sound", "הגברה"),
    _i("lighting", "תאורה"),
    _i("screens", "מסכים"),
    _i("stage", "במה"),
    _i("tech_gear", "ציוד טכני"),
    _i("projectors", "מקרנים"),
    _i("streaming", "סטרימינג"),
    _i("wifi", "Wi-Fi וציוד רשת"),
    _i("effects", "אפקטים"),

    # ── צילום ────────────────────────────────────────────────────────
    _i("photo_stills", "צילום סטילס"),
    _i("photo", "צילום"),
    _i("video", "וידאו"),
    _i("drone", "רחפן"),
    _i("magnets", "מגנטים"),
    _i("albums", "אלבומים", PER_UNIT, quantity=1),
    _i("parent_albums", "אלבומי הורים", PER_UNIT, quantity=2),
    _i("pre_shoot", "צילומי זוגיות"),
    _i("kid_shoot", "צילומי הכנה"),
    _i("clip", "קליפ"),
    _i("second_shooter", "צלם נוסף"),
    _i("photo_booth", "עמדת צילום"),

    # ── עיצוב ────────────────────────────────────────────────────────
    _i("venue_design", "עיצוב המקום"),
    _i("chuppah", "חופה"),
    _i("flowers", "פרחים"),
    _i("balloons", "בלונים"),
    _i("table_design", "עיצוב שולחנות"),
    _i("centerpieces", "מרכזי שולחן", PER_UNIT, quantity=10),
    _i("signage", "שילוט"),
    _i("reception_design", "עיצוב קבלת פנים"),
    _i("entrance_design", "עיצוב הכניסה"),
    _i("concept_design", "עיצוב לפי קונספט"),
    _i("bar_design", "עיצוב בר"),

    # ── לבוש והופעה ──────────────────────────────────────────────────
    _i("dress", "שמלה"),
    _i("second_dress", "שמלה נוספת"),
    _i("suit", "חליפה"),
    _i("outfit", "לבוש"),
    _i("extra_outfit", "לבוש נוסף"),
    _i("baby_outfit", "לבוש לתינוק"),
    # פריט נפרד ולא "לבוש לתינוק/ת": VEYA לא כותבת לוכסנים.
    _i("baby_outfit_f", "לבוש לתינוקת"),
    _i("shoes", "נעליים"),
    _i("jewelry", "תכשיטים"),
    _i("accessories", "אביזרים"),
    _i("makeup", "איפור"),
    _i("hair", "שיער"),
    _i("alterations", "תיקונים"),
    _i("rings", "טבעות"),
    _i("costumes", "תלבושות"),

    # ── טקס ──────────────────────────────────────────────────────────
    _i("rabbi", "רב"),
    _i("cantor", "חזן"),
    _i("mohel", "מוהל"),
    _i("ketubah", "כתובה"),
    _i("tallit", "טלית"),
    _i("tefillin", "תפילין"),
    _i("ceremony_items", "אביזרי טקס"),
    _i("ceremony_venue", "מקום לטקס"),
    _i("file_opening", "פתיחת תיק"),
    _i("fees", "אגרות"),
    _i("lessons", "לימוד והכנה"),
    _i("religious_service", "שירות דתי"),
    _i("henna_ceremony_gear", "ציוד לטקס החינה"),
    _i("henna_station", "עמדת חינה"),
    _i("henna_tent", "אוהל / מבנה חינה"),
    _i("henna_design", "עיצוב חינה"),
    _i("henna_decor", "תפאורה"),

    # ── אורחים וניירת ────────────────────────────────────────────────
    _i("invitations", "הזמנות", PER_GUEST),
    _i("digital_invite", "הזמנה דיגיטלית"),
    _i("branding", "מיתוג"),
    _i("table_numbers", "מספרי שולחן", PER_UNIT, quantity=10),
    _i("seating_cards", "פתקי הושבה", PER_ATTENDEE),
    _i("guest_gifts", "מתנות לאורחים", PER_ATTENDEE),
    _i("keepsakes", "מזכרות", PER_ATTENDEE),
    _i("attractions", "אטרקציות"),
    _i("games", "משחקים"),
    _i("activity_stations", "עמדות הפעלה"),
    _i("show", "מופע"),
    _i("name_tags", "תגי שם", PER_ATTENDEE),
    _i("printing", "הדפסות"),
    _i("conference_kit", "חומרי כנס", PER_ATTENDEE),

    # ── תוכן (עסקי) ──────────────────────────────────────────────────
    _i("speaker", "מרצה"),
    _i("host", "מנחה"),
    _i("content", "תוכן"),
    _i("content_vendors", "ספקי תוכן"),

    # ── לוגיסטיקה ────────────────────────────────────────────────────
    _i("shuttles", "הסעות", PER_UNIT, quantity=1),
    _i("parking", "חניה"),
    _i("lodging", "לינה"),
    _i("travel", "נסיעות"),
    _i("security", "אבטחה"),
    _i("event_manager", "מנהל אירוע"),
    _i("production", "הפקה"),
    _i("staff", "עובדים נוספים"),
    _i("cleaning", "ניקיון"),
    _i("external_vendors", "ספקים חיצוניים"),
    _i("insurance", "ביטוח ואישורים"),
    _i("car", "רכב לבעלי האירוע"),
    # טיפים באחוזים: כך הם מתעדכנים מאליהם כשהתקציב גדל, במקום להישאר
    # מספר שנקבע כשהאירוע היה קטן יותר.
    _i("tips", "טיפים", PERCENT, quantity=10),
    _i("misc", "הוצאות בלתי צפויות", PERCENT, quantity=5),
    _i("other", "הוצאות נוספות"),
)}


# ════════════════════════════════════════════════════════════════════════
#  התבניות
# ════════════════════════════════════════════════════════════════════════
#
# כל שורה: ``("category_key", "תווית", [ברירות מחדל], [בקטלוג בלבד])``.
# הפריטים ברשימה הראשונה מוצעים מיד; אלה שבשנייה קיימים תחת "הוספת
# הוצאה". החלוקה נקבעה לפי מה שרוב האירועים מהסוג הזה באמת משלמים —
# לא לפי מה שאפשרי.

_Cat = tuple[str, str, list[str], list[str]]

_TEMPLATE_SPECS: dict[str, tuple[_Cat, ...]] = {
    # ── חתונה ────────────────────────────────────────────────────────
    "wedding": (
        ("venue", "מקום ואירוח",
         ["hall", "meal_price"],
         ["venue_extras", "suite", "waiters", "overtime"]),
        ("food", "אוכל ומשקאות",
         ["bar", "alcohol"],
         ["wine", "cocktails", "cake", "desserts", "food_extras", "food_vendors",
          "food_stations"]),
        ("music", "מוזיקה והפקה",
         ["dj", "sound", "lighting"],
         ["band", "singer", "screens", "stage", "tech_gear", "effects"]),
        ("photo", "צילום",
         ["photo_stills", "video"],
         ["drone", "magnets", "albums", "parent_albums", "pre_shoot", "clip",
          "second_shooter", "photo_booth"]),
        ("design", "עיצוב",
         ["chuppah", "flowers", "venue_design"],
         ["table_design", "centerpieces", "signage", "reception_design", "bar_design"]),
        ("attire", "כלה וחתן",
         ["dress", "suit", "makeup", "hair"],
         ["second_dress", "shoes", "jewelry", "accessories", "alterations",
          "extra_outfit"]),
        ("ceremony", "טקס",
         ["rabbi", "rings"],
         ["ketubah", "tallit", "ceremony_items", "file_opening", "fees"]),
        ("guests", "אורחים וניירת",
         ["invitations"],
         ["digital_invite", "branding", "table_numbers", "seating_cards",
          "guest_gifts", "attractions"]),
        ("logistics", "לוגיסטיקה",
         ["tips"],
         ["shuttles", "parking", "lodging", "security", "event_manager", "staff",
          "car", "misc", "other"]),
    ),

    # ── חינה ─────────────────────────────────────────────────────────
    "henna": (
        ("venue", "מקום ואוכל",
         ["hall", "catering", "meals"],
         ["bar", "alcohol", "desserts", "sweets", "waiters"]),
        ("henna", "חינה ומסורת",
         ["henna_design", "costumes", "henna_station"],
         ["henna_decor", "henna_tent", "jewelry", "accessories",
          "henna_ceremony_gear"]),
        ("music", "מוזיקה והפקה",
         ["dj", "sound"],
         ["band", "lighting", "stage", "screens"]),
        ("photo", "צילום",
         ["photo", "video"],
         ["magnets", "albums"]),
        ("design", "עיצוב",
         ["table_design", "flowers"],
         ["entrance_design", "signage", "branding"]),
        ("guests", "אורחים",
         ["invitations"],
         ["guest_gifts", "keepsakes", "attractions"]),
        ("logistics", "לוגיסטיקה",
         ["tips"],
         ["shuttles", "staff", "misc", "other"]),
    ),

    # ── בר מצווה ─────────────────────────────────────────────────────
    "bar_mitzvah": (
        ("venue", "מקום ואוכל",
         ["hall", "meals"],
         ["catering", "bar", "desserts", "waiters"]),
        ("music", "מוזיקה והפקה",
         ["dj", "sound"],
         ["lighting", "screens", "stage"]),
        ("photo", "צילום",
         ["photo", "video", "magnets"],
         ["albums", "kid_shoot"]),
        ("attractions", "אטרקציות",
         ["attractions"],
         ["games", "activity_stations", "show"]),
        ("design", "עיצוב",
         ["concept_design", "balloons"],
         ["flowers", "table_design", "signage", "branding"]),
        ("celebrant", "החוגג והמשפחה",
         ["suit", "tefillin", "lessons"],
         ["shoes", "accessories", "tallit", "rabbi", "cantor"]),
        ("guests", "אורחים",
         ["invitations"],
         ["keepsakes", "guest_gifts", "photo_booth"]),
        ("logistics", "לוגיסטיקה",
         ["tips"],
         ["shuttles", "parking", "staff", "misc", "other"]),
    ),

    # ── בת מצווה ─────────────────────────────────────────────────────
    "bat_mitzvah": (
        ("venue", "מקום ואוכל",
         ["hall", "meals"],
         ["catering", "bar", "desserts", "waiters"]),
        ("music", "מוזיקה והפקה",
         ["dj", "sound"],
         ["lighting", "stage", "screens"]),
        ("photo", "צילום",
         ["photo", "video", "magnets"],
         ["albums", "kid_shoot"]),
        ("attractions", "אטרקציות",
         ["activity_stations"],
         ["attractions", "show", "games"]),
        ("design", "עיצוב",
         ["concept_design", "balloons"],
         ["flowers", "table_design", "signage", "branding"]),
        ("celebrant", "החוגגת",
         ["dress", "makeup", "hair"],
         ["shoes", "jewelry", "accessories", "kid_shoot"]),
        ("guests", "אורחים",
         ["invitations"],
         ["keepsakes", "guest_gifts"]),
        ("logistics", "לוגיסטיקה",
         ["tips"],
         ["shuttles", "parking", "staff", "misc", "other"]),
    ),

    # ── ברית ─────────────────────────────────────────────────────────
    "brit": (
        ("venue", "מקום ואוכל",
         ["hall", "catering"],
         ["meals", "drinks", "bar", "desserts", "waiters"]),
        ("ceremony", "טקס",
         ["mohel"],
         ["rabbi", "cantor", "ceremony_venue", "ceremony_items"]),
        ("photo", "צילום",
         ["photo"],
         ["video", "magnets"]),
        ("design", "עיצוב",
         ["flowers", "balloons"],
         ["venue_design", "table_design", "branding"]),
        ("baby", "התינוק",
         ["baby_outfit"],
         ["accessories", "ceremony_items"]),
        ("guests", "אורחים",
         ["invitations"],
         ["keepsakes", "guest_gifts"]),
        ("music", "מוזיקה",
         [],
         ["music", "dj", "sound"]),
        ("logistics", "לוגיסטיקה",
         ["tips"],
         ["shuttles", "staff", "misc", "other"]),
    ),

    # ── בריתה ────────────────────────────────────────────────────────
    "brita": (
        ("venue", "מקום ואוכל",
         ["hall", "catering"],
         ["meals", "drinks", "bar", "desserts", "waiters"]),
        ("ceremony", "טקס",
         [],
         ["rabbi", "religious_service", "ceremony_venue", "ceremony_items"]),
        ("photo", "צילום",
         ["photo"],
         ["video", "magnets"]),
        ("design", "עיצוב",
         ["flowers", "balloons"],
         ["venue_design", "table_design", "branding"]),
        ("baby", "התינוקת",
         ["baby_outfit_f"],
         ["accessories"]),
        ("guests", "אורחים",
         ["invitations"],
         ["keepsakes", "guest_gifts"]),
        ("music", "מוזיקה",
         [],
         ["music", "dj", "sound"]),
        ("logistics", "לוגיסטיקה",
         ["tips"],
         ["shuttles", "staff", "misc", "other"]),
    ),

    # ── אירוע עסקי ───────────────────────────────────────────────────
    "business": (
        ("venue", "מקום",
         ["venue_rental"],
         ["hall", "venue_equipment", "overtime"]),
        ("food", "אוכל",
         ["catering", "refreshments"],
         ["meals", "coffee", "drinks", "alcohol", "bar"]),
        ("production", "הפקה וטכנולוגיה",
         ["sound", "screens", "projectors"],
         ["lighting", "stage", "streaming", "wifi", "tech_gear"]),
        ("content", "תוכן",
         ["speaker"],
         ["host", "show", "content", "content_vendors"]),
        ("photo", "צילום",
         ["photo"],
         ["video", "streaming"]),
        ("branding", "מיתוג",
         ["signage", "name_tags"],
         ["printing", "conference_kit", "branding", "guest_gifts"]),
        ("logistics", "לוגיסטיקה",
         [],
         ["shuttles", "parking", "security", "staff", "cleaning", "lodging",
          "travel"]),
        ("management", "ניהול",
         ["production"],
         ["external_vendors", "insurance", "misc", "other"]),
    ),
}


def _build(spec: tuple[_Cat, ...]) -> tuple[ExpenseCategory, ...]:
    """מרכיב תבנית מהמאגר, ומקצה ``sort_order`` רץ על פני כל התבנית.

    הסדר הוא **סדר התצוגה בתבנית**, ולא סדר אלפביתי: קטגוריית המקום
    ראשונה כי שם נמצא רוב הכסף, והלוגיסטיקה אחרונה.
    """
    categories: list[ExpenseCategory] = []
    order = 0
    for key, label, defaults, extras in spec:
        items: list[TemplateItem] = []
        for item_key in [*defaults, *extras]:
            base = ITEMS[item_key]
            order += 1
            items.append(
                TemplateItem(
                    key=base.key,
                    label=base.label,
                    calc_method=base.calc_method,
                    supports_commitment=base.supports_commitment,
                    default_quantity=base.default_quantity,
                    is_default=item_key in defaults,
                    sort_order=order,
                )
            )
        categories.append(ExpenseCategory(key=key, label=label, items=tuple(items)))
    return tuple(categories)


TEMPLATES: dict[str, tuple[ExpenseCategory, ...]] = {
    event_type: _build(spec) for event_type, spec in _TEMPLATE_SPECS.items()
}


# ════════════════════════════════════════════════════════════════════════
#  API של המודול
# ════════════════════════════════════════════════════════════════════════

def catalog_for(event_type: str) -> list[ExpenseCategory]:
    """הקטלוג המלא של סוג האירוע — ברירות המחדל **וגם** מה שתחת "הוספה".

    סוג שאינו מוכר נופל לתבנית החתונה: היא העשירה ביותר, וזו נפילה
    שמורידה דיוק ולא שוברת מסך. אין כאן "תבנית גנרית" נפרדת — היא
    הייתה סוג אירוע שמיני שלא קיים במערכת.
    """
    return list(TEMPLATES.get(event_type) or TEMPLATES["wedding"])


def default_items_for(event_type: str) -> list[tuple[str, TemplateItem]]:
    """רק ברירות המחדל, כזוגות ``(category_key, item)``.

    זו התבנית שנוצרת בפועל כשהזוג בוחר "להתחיל מהתבנית" — ולכן היא
    מוגבלת ל-``is_default``: תקציב פותח עם 15 שורות רלוונטיות, לא עם 60.
    """
    return [
        (category.key, item)
        for category in catalog_for(event_type)
        for item in category.items
        if item.is_default
    ]


#: תווית הקטגוריה **לכל סוג אירוע בנפרד**.
#:
#: מפתח קטגוריה משותף יכול לשאת תווית שונה בכל סוג, וזה לא ניואנס: אותו
#: ``baby`` הוא "התינוק" בברית ו"התינוקת" בבריתה, ואותו ``venue`` הוא
#: "מקום ואירוח" בחתונה ו"מקום" באירוע עסקי. מילון שטוח אחד היה נותן
#: לסוג האחרון שנטען לדרוס את כל השאר — ואב לתינוק היה רואה "התינוקת".
_LABELS: dict[str, dict[str, str]] = {
    event_type: {key: label for key, label, _, _ in spec}
    for event_type, spec in _TEMPLATE_SPECS.items()
}


#: מפתחות קטגוריה שכבר אינם בתבניות, ועדיין עשויים לשבת על שורות
#: קיימות ב-DB.
#:
#: **למה זה קיים:** ``EventExpense.category`` נשמר כמחרוזת בשורה, ולא
#: כמפתח זר. זו החלטה נכונה (היא מאפשרת לתבניות להשתנות בלי מיגרציה),
#: אבל היא אומרת ששינוי שם קטגוריה משאיר שורות ישנות מצביעות למפתח
#: שנעלם. בלי המפה הזו הזוג היה רואה "venue_food" ככותרת קבוצה —
#: מפתח פנימי שדלף למסך.
#:
#: כשמשנים או מסירים מפתח קטגוריה, מוסיפים אותו לכאן. זה הזול שבין
#: השניים: החלופה היא מיגרציה שנוגעת בכל שורות ההוצאה בייצור.
_LEGACY_LABELS: dict[str, str] = {
    "venue_food": "אולם ואוכל",
    "bride": "כלה",
    "groom": "חתן",
    "rings": "טבעות ותכשיטים",
    "invitations": "הזמנות ומיתוג",
    "transport": "הסעות וחניה",
    "tips": "טיפים",
    "other": "הוצאות נוספות",
}


def category_label(key: str, event_type: str = "wedding") -> str:
    """תווית הקטגוריה לתצוגה, בניסוח של סוג האירוע.

    שתי נפילות רכות, ובכוונה: סוג לא מוכר נופל לחתונה, ומפתח לא מוכר
    חוזר כמו שהוא. שורה ישנה שהקטגוריה שלה שונתה עדיין צריכה להופיע
    בסיכום — ולא להעלים ממנו כסף.
    """
    labels = _LABELS.get(event_type) or _LABELS["wedding"]
    if key in labels:
        return labels[key]
    # הקטגוריה לא קיימת בסוג הזה (שורה שנוצרה לפני שינוי סוג האירוע) —
    # מחפשים תווית בכל סוג אחר לפני שנופלים למפתח הגולמי.
    for other in _LABELS.values():
        if key in other:
            return other[key]
    return _LEGACY_LABELS.get(key, key)


def is_known_calc_method(method: str) -> bool:
    return method in CALC_METHODS
