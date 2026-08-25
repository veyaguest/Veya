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
  - ``has_two_hosts``        — האם לסוג יש *שני* בעלי אירוע (חתן+כלה) או אחד בלבד.
                               התאום של ``hasTwoHosts`` ב-``eventTypes.ts``: מסך יצירת
                               האירוע מציג שדה שם אחד לסוגים חד-מארחים, ולכן
                               ``bride_name`` שם ריק תמיד. הדגל מונע ניסוח "יונתן ושרה"
                               באירוע עם חוגג יחיד (למשל אחרי שינוי סוג אירוע).
  - ``host_field_label``     — תווית שדה השם במסך יצירת האירוע ("שם החתן" / "שם החוגג").
                               תאום של ``hostAField``. משמשת גם כתווית הטוקן
                               ``[שמות בעלי האירוע]`` בבורר הטוקנים, כדי שמה שהזוג רואה
                               בעורך ההודעות יתאים בדיוק למה שהוא מילא ביצירת האירוע.
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
    has_two_hosts: bool = True  # שני בעלי אירוע (חתן+כלה) — תואם ל-hasTwoHosts ב-eventTypes.ts
    host_field_label: str = "שם החתן"      # תווית שדה השם הראשון — תואם ל-hostAField
    host_b_field_label: str = "שם הכלה"    # תווית שדה השם השני — תואם ל-hostBField
    side_groom: str = "חתן"     # תווית צד groom (תואם ל-sideLabels ב-eventTypes.ts)
    side_bride: str = "כלה"     # תווית צד bride
    guests_label: str = "מוזמנים"  # תואם ל-guestsLabel ב-eventTypes.ts
    # תווית פעולת המתנה. אחיד בכל סוגי האירוע במכוון (החלטת בעלים
    # 2026-08-24) — "להעניק מתנה" בלי קשר לסוג האירוע, בניגוד לשאר
    # השדות כאן. תואם ל-giftLabel ב-eventTypes.ts.
    gift_label: str = "להעניק מתנה"
    # כותרת האירוע לתצוגה ("החתונה של אביב ודנה"). ``{hosts}`` מוחלף בשמות
    # בעלי האירוע. ברירת המחדל גנרית בכוונה — סוג שלא הוגדר לו ניסוח משלו
    # יקבל "האירוע של ..." ולא ניסוח שבור.
    display_title: str = "האירוע של {hosts}"
    group_options: list[tuple[str, str]] = field(default_factory=lambda: WEDDING_GROUP_OPTIONS)


# מקור-אמת יחיד לכל סוגי האירועים. הוספת סוג חדש = רשומה אחת כאן בלבד.
EVENT_TERMS: dict[str, EventTerms] = {
    "wedding": EventTerms(
        type="wedding",
        label="חתונה",
        celebration="חתונה",
        celebration_construct="חתונת",
        hosts="בני הזוג",
        display_title="החתונה של {hosts}",
        emoji="💍",
    ),
    "bar_mitzvah": EventTerms(
        type="bar_mitzvah",
        label="בר מצווה",
        celebration="אירוע בר המצווה",
        celebration_construct="בר המצווה של",
        hosts="החוגג",
        display_title="בר המצווה של {hosts}",
        emoji="🕯️",
        has_two_hosts=False,
        host_field_label="שם החוגג",
        host_b_field_label="",
        side_groom="צד משפחת האב",
        side_bride="צד משפחת האם",
        gift_label="להעניק מתנה",
        group_options=MITZVAH_GROUP_OPTIONS,
    ),
    "bat_mitzvah": EventTerms(
        type="bat_mitzvah",
        label="בת מצווה",
        celebration="אירוע בת המצווה",
        celebration_construct="בת המצווה של",
        hosts="החוגגת",
        display_title="בת המצווה של {hosts}",
        emoji="🕯️",
        has_two_hosts=False,
        host_field_label="שם החוגגת",
        host_b_field_label="",
        side_groom="צד משפחת האב",
        side_bride="צד משפחת האם",
        gift_label="להעניק מתנה",
        group_options=MITZVAH_GROUP_OPTIONS,
    ),
    "henna": EventTerms(
        type="henna",
        label="חינה",
        celebration="חינה",
        celebration_construct="חינת",
        hosts="בני הזוג",
        display_title="החינה של {hosts}",
        emoji="🌿",
        group_options=HENNA_GROUP_OPTIONS,
    ),
    "brit": EventTerms(
        type="brit",
        label="ברית",
        celebration="אירוע ברית",
        celebration_construct="ברית של",
        hosts="המשפחה",
        display_title="הברית של {hosts}",
        emoji="🍼",
        has_two_hosts=False,
        host_field_label="שם המשפחה",
        host_b_field_label="",
        side_groom="צד משפחת האב",
        side_bride="צד משפחת האם",
        gift_label="להעניק מתנה",
        group_options=FAMILY_EVENT_GROUP_OPTIONS,
    ),
    "brita": EventTerms(
        type="brita",
        label="בריתה",
        celebration="אירוע בריתה",
        celebration_construct="בריתה של",
        hosts="המשפחה",
        display_title="הבריתה של {hosts}",
        emoji="🎀",
        has_two_hosts=False,
        host_field_label="שם המשפחה",
        host_b_field_label="",
        side_groom="צד משפחת האב",
        side_bride="צד משפחת האם",
        gift_label="להעניק מתנה",
        group_options=FAMILY_EVENT_GROUP_OPTIONS,
    ),
    "business": EventTerms(
        type="business",
        label="אירוע עסקי",
        celebration="אירוע",
        celebration_construct="אירוע של",
        hosts="המארגנים",
        display_title="האירוע של {hosts}",
        emoji="✨",
        has_two_hosts=False,
        host_field_label="שם האירוע / החברה",
        host_b_field_label="",
        side_groom="צד א׳",
        side_bride="צד ב׳",
        guests_label="משתתפים",
        gift_label="להעניק מתנה",
        group_options=BUSINESS_GROUP_OPTIONS,
    ),
}


def get_event_terms(event_type: str | None) -> EventTerms:
    """מונחי הסוג המבוקש — נופל בעדינות לחתונה אם הסוג ריק/לא מוכר."""
    return EVENT_TERMS.get((event_type or "wedding"), EVENT_TERMS["wedding"])


def hosts_names(event_type: str | None, groom: str, bride: str) -> str:
    """שמות בעלי האירוע ("דניאל ושירה") או כינוי ברירת מחדל לפי הסוג.

    שלוש הקפדות שמונעות ניסוח שבור בהודעה למוזמן:

    1. *ניקוי רווחים* — שם שמכיל רווחים בלבד נחשב ריק, אחרת נוצרת הודעה עם
       "ו" מיותרת או רווח כפול ("יונתן ו").
    2. *בעל אירוע יחיד* — בסוגים שמסך יצירת האירוע מציג להם שדה שם אחד
       (בר/בת מצווה, ברית, משפחתי, עסקי, אחר) מוחזר רק השם הראשון. כך
       ``bride_name`` שנשאר מאירוע שהיה פעם חתונה לא מייצר "יונתן ושרה"
       בהזמנה לבר מצווה. אם השם הראשון ריק — נופלים לשני, כדי לא לאבד מידע.
    3. *נפילה רכה* — בלי שמות כלל מוחזר כינוי הסוג ("בני הזוג" / "החוגג").
    """
    a = (groom or "").strip()
    b = (bride or "").strip()
    terms = get_event_terms(event_type)
    if not terms.has_two_hosts:
        return a or b or terms.hosts
    joined = " ו".join([n for n in (a, b) if n])
    return joined or terms.hosts


def side_axis_label(event_type: str | None) -> str:
    """תווית כללית לציר ה'צד' לשימוש בסוגריים ("חתן/כלה", "האב/האם", "א׳/ב׳").

    לא מתייחס לצד ספציפי של מוזמן — רק מסביר מה "הצד המתאים" אומר עבור סוג
    האירוע הזה, בתוך הסבר שיבוץ כמו "יושבים בצד המתאים (חתן/כלה)".
    """
    terms = get_event_terms(event_type)

    def bare(raw: str) -> str:
        return raw[len("צד "):] if raw.startswith("צד ") else raw

    return f"{bare(terms.side_groom)}/{bare(terms.side_bride)}"


def event_display_title(event_type: str | None, groom: str, bride: str) -> str:
    """כותרת האירוע לתצוגה — "החתונה של אביב ודנה", "בר המצווה של יונתן".

    משמשת בכל מקום שבו מוצג "האירוע שלי" למשתמש: מסך החשבון, מייל ההזמנה
    לניהול משותף ומסך ההצטרפות. מרוכז כאן (ולא בכל קורא בנפרד) כדי שסוג
    אירוע חדש יקבל את הניסוח הנכון בכל המסכים בבת אחת.

    בלי שמות כלל מוחזרת כותרת הסוג בלבד ("חתונה") — לא "החתונה של בני הזוג",
    שנשמע כמו תקלה.
    """
    terms = get_event_terms(event_type)
    a = (groom or "").strip()
    b = (bride or "").strip()
    if not a and not b:
        return terms.celebration
    return terms.display_title.format(hosts=hosts_names(event_type, groom, bride))
