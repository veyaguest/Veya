"""מונחי אירוע דינמיים בצד השרת — התאום העברי של ``strings/eventTypes.ts`` בפרונט.

עיקרון VEYA: *Wedding-first, Event-ready*. חתונה נשארת קטגוריית הליבה, אבל אותה
מערכת מתאימה את עצמה גם לבר/בת מצווה, חינה, ברית, אירוע משפחתי או עסקי. במקום
לשכפל טקסטים לכל סוג — כל מקום שמזכיר "חתונה"/"בני הזוג" שואב את המילה הנכונה
מכאן, לפי ``event_type`` של האירוע.

לכל סוג מוגדרים:
  - ``celebration``          — שם האירוע כשם עצם *סתמי* ("חתונה", "אירוע בר המצווה",
                               "אירוע"). סתמי בכוונה כדי שיתלכד נכון אחרי ל/ב
                               ("לחתונה", "לאירוע") בלי כפל ה' הידיעה ("להחתונה").
  - ``celebration_construct``— צורת סמיכות לפני שם ("חתונת", "בר המצווה של", "אירוע של").
                               כך "חתונת דניאל ושירה" מול "בר המצווה של יונתן".
  - ``hosts``                — כינוי בעלי האירוע כברירת מחדל ("בני הזוג", "המשפחה", "המארגנים").
  - ``emoji``                — אמוג'י עדין המשויך לסוג (לא חובה בשימוש).

ברירת המחדל בכל מקום היא ``wedding`` — כך אירועים קיימים (וכל מי שלא בחר סוג)
מקבלים בדיוק את חוויית החתונה כמו קודם, בלי שום שינוי.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# אפשרויות קבוצה מוצעות לטופס/ייבוא מוזמנים, לפי סוג אירוע — תואם ל-
# groupOptions ב-eventTypes.ts. (מפתח, תווית). group_type מאוחסן כטקסט חופשי
# ב-DB, אז אלה רק ברירות מחדל מוצעות — לא אכיפה.
WEDDING_GROUP_OPTIONS: list[tuple[str, str]] = [
    ("close_family", "משפחה קרובה"),
    ("extended_family", "משפחה רחוקה"),
    ("friends", "חברים"),
    ("work", "עבודה"),
    ("army", "צבא"),
    ("studies", "מהלימודים"),
    ("childhood", "חברי ילדות"),
    ("neighbors", "שכנים"),
    ("other", "אחר"),
]
MITZVAH_GROUP_OPTIONS: list[tuple[str, str]] = [
    ("family_father", "משפחת האב"),
    ("family_mother", "משפחת האם"),
    ("friends", "חברים"),
    ("class", "כיתה"),
    ("staff_clubs", "צוות/חוגים"),
    ("other", "אחר"),
]
HENNA_GROUP_OPTIONS: list[tuple[str, str]] = [
    ("family", "משפחה"),
    ("extended_family", "צד משפחתי מורחב"),
    ("friends", "חברים"),
    ("other", "אחר"),
]
FAMILY_EVENT_GROUP_OPTIONS: list[tuple[str, str]] = [
    ("family", "משפחה"),
    ("friends", "חברים"),
    ("other", "אחר"),
]
BUSINESS_GROUP_OPTIONS: list[tuple[str, str]] = [
    ("employees", "עובדים"),
    ("clients", "לקוחות"),
    ("suppliers", "ספקים"),
    ("management", "הנהלה"),
    ("partners", "שותפים"),
    ("other", "אחר"),
]


@dataclass(frozen=True)
class EventTerms:
    type: str
    label: str                  # שם הסוג לתצוגה (בורר סוג אירוע, אדמין) — תואם ל-label ב-eventTypes.ts
    celebration: str            # "חתונה" (סתמי — בטוח אחרי ל/ב)
    celebration_construct: str  # "חתונת" / "בר המצווה של"
    hosts: str                  # "בני הזוג"
    emoji: str
    side_groom: str = "חתן"     # תווית צד groom (תואם ל-sideLabels ב-eventTypes.ts)
    side_bride: str = "כלה"     # תווית צד bride
    guests_label: str = "מוזמנים"  # תואם ל-guestsLabel ב-eventTypes.ts
    gift_label: str = "מתנה לזוג"  # תואם ל-giftLabel ב-eventTypes.ts
    group_options: list[tuple[str, str]] = field(default_factory=lambda: WEDDING_GROUP_OPTIONS)


# מקור-אמת יחיד לכל סוגי האירועים. הוספת סוג חדש = רשומה אחת כאן בלבד.
EVENT_TERMS: dict[str, EventTerms] = {
    "wedding": EventTerms(
        type="wedding",
        label="חתונה",
        celebration="חתונה",
        celebration_construct="חתונת",
        hosts="בני הזוג",
        emoji="💍",
    ),
    "bar_mitzvah": EventTerms(
        type="bar_mitzvah",
        label="בר מצווה",
        celebration="אירוע בר המצווה",
        celebration_construct="בר המצווה של",
        hosts="החוגג",
        emoji="🕯️",
        side_groom="צד משפחת האב",
        side_bride="צד משפחת האם",
        gift_label="מתנה לחוגג",
        group_options=MITZVAH_GROUP_OPTIONS,
    ),
    "bat_mitzvah": EventTerms(
        type="bat_mitzvah",
        label="בת מצווה",
        celebration="אירוע בת המצווה",
        celebration_construct="בת המצווה של",
        hosts="החוגגת",
        emoji="🕯️",
        side_groom="צד משפחת האב",
        side_bride="צד משפחת האם",
        gift_label="מתנה לחוגגת",
        group_options=MITZVAH_GROUP_OPTIONS,
    ),
    "henna": EventTerms(
        type="henna",
        label="חינה",
        celebration="חינה",
        celebration_construct="חינת",
        hosts="בני הזוג",
        emoji="🌿",
        group_options=HENNA_GROUP_OPTIONS,
    ),
    "brit": EventTerms(
        type="brit",
        label="ברית / בריתה",
        celebration="אירוע ברית",
        celebration_construct="ברית של",
        hosts="המשפחה",
        emoji="🍼",
        side_groom="צד משפחת האב",
        side_bride="צד משפחת האם",
        gift_label="מתנה למשפחה",
        group_options=FAMILY_EVENT_GROUP_OPTIONS,
    ),
    "family": EventTerms(
        type="family",
        label="אירוע משפחתי",
        celebration="אירוע משפחתי",
        celebration_construct="אירוע של",
        hosts="המשפחה",
        emoji="🎉",
        side_groom="צד א׳",
        side_bride="צד ב׳",
        gift_label="מתנה למשפחה",
        group_options=FAMILY_EVENT_GROUP_OPTIONS,
    ),
    "business": EventTerms(
        type="business",
        label="אירוע עסקי",
        celebration="אירוע",
        celebration_construct="אירוע של",
        hosts="המארגנים",
        emoji="✨",
        side_groom="צד א׳",
        side_bride="צד ב׳",
        guests_label="משתתפים",
        gift_label="מתנה לאירוע",
        group_options=BUSINESS_GROUP_OPTIONS,
    ),
    "other": EventTerms(
        type="other",
        label="אחר",
        celebration="אירוע",
        celebration_construct="אירוע של",
        hosts="המארגנים",
        emoji="✨",
        side_groom="צד א׳",
        side_bride="צד ב׳",
        gift_label="מתנה לאירוע",
        group_options=FAMILY_EVENT_GROUP_OPTIONS,
    ),
}


def get_event_terms(event_type: str | None) -> EventTerms:
    """מונחי הסוג המבוקש — נופל בעדינות לחתונה אם הסוג ריק/לא מוכר."""
    return EVENT_TERMS.get((event_type or "wedding"), EVENT_TERMS["wedding"])


def hosts_names(event_type: str | None, groom: str, bride: str) -> str:
    """שמות בעלי האירוע ("דניאל ושירה") או כינוי ברירת מחדל לפי הסוג."""
    joined = " ו".join([n for n in (groom, bride) if n])
    return joined or get_event_terms(event_type).hosts


def side_axis_label(event_type: str | None) -> str:
    """תווית כללית לציר ה'צד' לשימוש בסוגריים ("חתן/כלה", "האב/האם", "א׳/ב׳").

    לא מתייחס לצד ספציפי של מוזמן — רק מסביר מה "הצד המתאים" אומר עבור סוג
    האירוע הזה, בתוך הסבר שיבוץ כמו "יושבים בצד המתאים (חתן/כלה)".
    """
    terms = get_event_terms(event_type)

    def bare(raw: str) -> str:
        return raw[len("צד "):] if raw.startswith("צד ") else raw

    return f"{bare(terms.side_groom)}/{bare(terms.side_bride)}"
