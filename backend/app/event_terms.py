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

from dataclasses import dataclass


@dataclass(frozen=True)
class EventTerms:
    type: str
    celebration: str            # "חתונה" (סתמי — בטוח אחרי ל/ב)
    celebration_construct: str  # "חתונת" / "בר המצווה של"
    hosts: str                  # "בני הזוג"
    emoji: str


# מקור-אמת יחיד לכל סוגי האירועים. הוספת סוג חדש = רשומה אחת כאן בלבד.
EVENT_TERMS: dict[str, EventTerms] = {
    "wedding": EventTerms(
        type="wedding",
        celebration="חתונה",
        celebration_construct="חתונת",
        hosts="בני הזוג",
        emoji="💍",
    ),
    "bar_mitzvah": EventTerms(
        type="bar_mitzvah",
        celebration="אירוע בר המצווה",
        celebration_construct="בר המצווה של",
        hosts="המשפחה",
        emoji="🕯️",
    ),
    "bat_mitzvah": EventTerms(
        type="bat_mitzvah",
        celebration="אירוע בת המצווה",
        celebration_construct="בת המצווה של",
        hosts="המשפחה",
        emoji="🕯️",
    ),
    "henna": EventTerms(
        type="henna",
        celebration="חינה",
        celebration_construct="חינת",
        hosts="בני הזוג",
        emoji="🌿",
    ),
    "brit": EventTerms(
        type="brit",
        celebration="אירוע ברית",
        celebration_construct="ברית של",
        hosts="המשפחה",
        emoji="🍼",
    ),
    "family": EventTerms(
        type="family",
        celebration="אירוע משפחתי",
        celebration_construct="אירוע של",
        hosts="המשפחה",
        emoji="🎉",
    ),
    "business": EventTerms(
        type="business",
        celebration="אירוע",
        celebration_construct="אירוע של",
        hosts="המארגנים",
        emoji="✨",
    ),
    "other": EventTerms(
        type="other",
        celebration="אירוע",
        celebration_construct="אירוע של",
        hosts="המארגנים",
        emoji="✨",
    ),
}


def get_event_terms(event_type: str | None) -> EventTerms:
    """מונחי הסוג המבוקש — נופל בעדינות לחתונה אם הסוג ריק/לא מוכר."""
    return EVENT_TERMS.get((event_type or "wedding"), EVENT_TERMS["wedding"])


def hosts_names(event_type: str | None, groom: str, bride: str) -> str:
    """שמות בעלי האירוע ("דניאל ושירה") או כינוי ברירת מחדל לפי הסוג."""
    joined = " ו".join([n for n in (groom, bride) if n])
    return joined or get_event_terms(event_type).hosts
