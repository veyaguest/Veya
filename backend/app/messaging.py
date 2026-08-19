"""ערוץ WhatsApp למוזמנים (שלב 5).

עיקרון: המערכת שולחת הזמנה עם שני כפתורי Quick Reply — "מגיע/ה" ו"לא מגיע/ה".
המוזמן לוחץ כפתור, ותשובת ה-RSVP נרשמת אוטומטית. (PRD חלק 5 + החלטה טכנית 3.)

מצבי עבודה (WHATSAPP_MODE):
- "mock" (ברירת מחדל) — לא נשלחת הודעה אמיתית. ההודעה נרשמת ביומן בלבד, כדי
  שהבעלים יוכל לבדוק את כל הזרימה בלי חשבון Meta ובלי עלות. אפשר "לדמות" תשובת
  מוזמן דרך המסך.
- "live" — שליחה אמיתית מול Meta WhatsApp Cloud API. דורש טוקן + מזהה מספר
  ששמורים במשתני סביבה. (הקוד מוכן; הבעלים צריך להשלים אישור תבנית מול Meta.)

הפרדה מכוונת: כל התלות ב-Meta מרוכזת כאן, כדי שאפשר יהיה להחליף/לכבות בקלות.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from app import event_terms

# שני כפתורי Quick Reply — עד 3 מותר בוואטסאפ (החלטה טכנית 2).
RSVP_YES_ID = "rsvp_yes"
RSVP_NO_ID = "rsvp_no"
RSVP_YES_LABEL = "מגיע/ה ✅"
RSVP_NO_LABEL = "לא מגיע/ה ❌"


def current_mode() -> str:
    """מצב הערוץ מתוך משתנה סביבה. ברירת מחדל בטוחה: mock (בלי שליחה אמיתית)."""
    return os.getenv("WHATSAPP_MODE", "mock").strip().lower()


def build_invitation_text(
    guest_name: str, groom: str, bride: str, venue: str, event_type: str = "wedding"
) -> str:
    """נוסח ההזמנה שנשלח למוזמן (טקסט תבנית, לפני הכפתורים). מתאים את עצמו לסוג האירוע."""
    terms = event_terms.get_event_terms(event_type)
    couple = event_terms.hosts_names(event_type, groom, bride)
    where = f" ב{venue}" if venue else ""
    hi = guest_name.split()[0] if guest_name else "שלום"
    return (
        f"היי {hi}! {terms.emoji}\n"
        f"{couple} שמחים להזמין אותך ל{terms.celebration}{where}.\n"
        f"נשמח לדעת אם תגיע/י — לחיצה על אחד הכפתורים למטה:"
    )


# ---- תבניות הודעה עם משתנים (שלב RSVP 2) ----

# תבנית ברירת המחדל. הבעלים יכול לערוך אותה ולשמור אחת משלו.
# משתמשת בטוקן {{celebration}} ("החתונה"/"אירוע בר המצווה"/"האירוע") כדי
# להתאים את עצמה לסוג האירוע — לחתונה היא נקראת בדיוק כמו קודם.
DEFAULT_TEMPLATE = (
    "שלום {name}!\n"
    "{event_name} שמחים להזמין אתכם ל{{celebration}}{venue}.\n"
    "נשמח לאישור הגעה בקישור האישי:\n"
    "{personal_link}"
)

def default_template_for(event_type: str | None) -> str:
    """DEPRECATED — נתיב ה"תבנית הישנה" (``event.message_template``) הוחלף
    בהודעת ה-invitation ברצף "תקשורת עם אורחים" (``EventMessage``, ראו
    ``communication.py``), שהוא היום מקור-האמת לשליחה בפועל. הפונקציה נשארת
    (מוחזרת רק רשת הביטחון הגנרית) כדי ש-``routers/messaging.py`` הישן —
    שאין לו יותר קורא ב-Frontend — לא ייפול אם מישהו עדיין קורא לו ישירות.
    """
    return DEFAULT_TEMPLATE


# קידומת עדינה שנוספת בראש הודעת תזכורת (למי שעדיין לא ענה). מנוסחת כך
# שהסיבה לפנייה היא *שלנו* ("אנחנו סוגרים רשימה") ולא כישלון של המוזמן
# ("לא עניתם") — זה קו המותג של VEYA מול הסטנדרט בשוק.
REMINDER_PREFIX = "תזכורת קטנה 🙂 אנחנו סוגרים את הרשימה —"

# המשתנים הנתמכים — כל אחד עם כמה כינויים (אנגלית + עברית) לנוחות.
PLACEHOLDERS = [
    {"key": "{name}", "aliases": ["{name}", "{שם}"], "desc": "שם המוזמן"},
    {"key": "{event_name}", "aliases": ["{event_name}", "{שמות}"], "desc": "שמות בעלי האירוע"},
    {"key": "{date}", "aliases": ["{date}", "{תאריך}"], "desc": "תאריך האירוע"},
    {"key": "{venue}", "aliases": ["{venue}", "{מקום}"], "desc": "שם האולם"},
    {"key": "{personal_link}", "aliases": ["{personal_link}", "{קישור_אישי}"], "desc": "הקישור האישי לאישור"},
]


# מקור אמת יחיד ל-public_base_url הוא app/emailer.py — לא לשכפל כאן. זה בדיוק
# מה שהיה לפני התיקון: שני עותקים זהים של אותה פונקציה, ושניהם נפלו בשקט
# ל-localhost בייצור כי אף אחד מהם לא הכיר את VEYA_ENV.
from app.emailer import public_base_url


def confirm_link(token: str | None) -> str:
    """הקישור האישי המלא לדף אישור ההגעה של מוזמן."""
    return f"{public_base_url()}/confirm/{token}" if token else ""


def render_template(
    template: str,
    *,
    guest_name: str,
    groom: str,
    bride: str,
    venue: str,
    link: str,
    date: str = "",
    event_type: str = "wedding",
) -> str:
    """ממלא את המשתנים בתבנית בערכים של מוזמן ואירוע ספציפיים.

    תומך גם בכינויים בעברית ({שם}, {שמות}, {תאריך}, {מקום}, {קישור_אישי}),
    ובטוקן {{celebration}} שמתאים את שם האירוע לסוגו.
    """
    terms = event_terms.get_event_terms(event_type)
    couple = event_terms.hosts_names(event_type, groom, bride)
    where = f" ב{venue}" if venue else ""
    values = {
        "name": guest_name.split()[0] if guest_name else "שלום",
        "event_name": couple,
        "date": date or "",
        "venue": where,
        "personal_link": link,
    }
    text = template or DEFAULT_TEMPLATE
    # טוקן שם האירוע לפי הסוג (למשל בתבנית ברירת המחדל).
    text = text.replace("{{celebration}}", terms.celebration)
    # מיפוי כל הכינויים לערך
    for ph in PLACEHOLDERS:
        canonical = ph["key"].strip("{}")
        for alias in ph["aliases"]:
            text = text.replace(alias, values.get(canonical, ""))
    return text


# ---- מנוע האוטומציות: משתנים דינמיים בסגנון {{...}} (שלב RSVP Automation) ----

# רשימת המשתנים הנתמכים בתבניות האוטומציה — כל אחד עם הסבר קצר בעברית.
# משתמשים בסוגריים כפולים ({{...}}) כדי להבדיל מהמשתנים הישנים ({...}) ולא
# לשבור תבניות קיימות. שני הסגנונות עובדים יחד.
# לכל משתנה גם כינוי ידידותי בעברית ("token") שהזוג רואה ומכניס במקום
# המשתנה הטכני — למשל "[שם אורח]" במקום "{{guest_name}}". שני הסגנונות
# ממופים לאותו ערך, כך שהזוג לא נחשף לקוד אבל הכול נשאר תואם לאחור.
# קטגוריות הטוקנים לתצוגה מקובצת בעורך ההודעות (מקור-אמת משותף לשרת ולפרונט).
# הסדר כאן הוא סדר הקבוצות שהזוג רואה.
TOKEN_CAT_GUEST = "guest"          # מי מקבל את ההודעה
TOKEN_CAT_EVENT = "event"          # מי מארח ומה חוגגים
TOKEN_CAT_WHEN_WHERE = "when_where"  # מתי ואיפה
TOKEN_CAT_LINKS = "links"          # קישורים
TOKEN_CAT_EXTRA = "extra"          # תוספות

TOKEN_CATEGORY_LABELS: dict[str, str] = {
    TOKEN_CAT_GUEST: "המוזמן",
    TOKEN_CAT_EVENT: "האירוע",
    TOKEN_CAT_WHEN_WHERE: "מתי ואיפה",
    TOKEN_CAT_LINKS: "קישורים",
    TOKEN_CAT_EXTRA: "תוספות",
}

AUTOMATION_PLACEHOLDERS = [
    {"key": "{{first_name}}", "token": "[שם פרטי]", "cat": TOKEN_CAT_GUEST,
     "desc": "השם הפרטי של המוזמן. אין שם — שורת הפנייה כולה נעלמת מההודעה."},
    {"key": "{{table_number}}", "token": "[מספר שולחן]", "cat": TOKEN_CAT_GUEST,
     "desc": "מספר השולחן של המוזמן. עוד לא שובץ — השורה נעלמת."},
    {"key": "{{guest_count}}", "token": "[כמות מקומות]", "cat": TOKEN_CAT_GUEST,
     "desc": "כמה מקומות שמורים למוזמן"},

    {"key": "{{event_name}}", "token": "[שמות בעלי האירוע]", "cat": TOKEN_CAT_EVENT,
     "desc": "שמות בעלי האירוע — מה שמילאתם בפרטי האירוע"},
    {"key": "{{groom_name}}", "token": "[שם החתן]", "cat": TOKEN_CAT_EVENT,
     "desc": "שם החתן בלבד"},
    {"key": "{{bride_name}}", "token": "[שם הכלה]", "cat": TOKEN_CAT_EVENT,
     "desc": "שם הכלה בלבד"},
    {"key": "{{celebration_of}}", "token": "[שמחת]", "cat": TOKEN_CAT_EVENT,
     "desc": "פתיח לפני השמות: \"חתונת דנה ויואב\" / \"בר המצווה של יונתן\""},
    {"key": "{{celebration}}", "token": "[האירוע]", "cat": TOKEN_CAT_EVENT,
     "desc": "שם האירוע אחרי ל/ב: \"לחתונה\" / \"לאירוע בר המצווה\""},
    {"key": "{{groom_parents_line}}", "token": "[הורי החתן]", "cat": TOKEN_CAT_EVENT,
     "desc": "שורת הורי החתן בהזמנה דתית (\"משפחת כהן\" / \"יצחק ורבקה כהן\"). לא מילאתם — השורה נעלמת."},
    {"key": "{{bride_parents_line}}", "token": "[הורי הכלה]", "cat": TOKEN_CAT_EVENT,
     "desc": "שורת הורי הכלה בהזמנה דתית. לא מילאתם — השורה נעלמת."},

    {"key": "{{event_date}}", "token": "[תאריך]", "cat": TOKEN_CAT_WHEN_WHERE,
     "desc": "תאריך האירוע, בפורמט ישראלי (10.09.2026)"},
    {"key": "{{event_time}}", "token": "[שעה]", "cat": TOKEN_CAT_WHEN_WHERE,
     "desc": "שעת האירוע (20:00)"},
    {"key": "{{venue_name}}", "token": "[שם האולם]", "cat": TOKEN_CAT_WHEN_WHERE,
     "desc": "שם האולם"},
    {"key": "{{venue_address}}", "token": "[כתובת]", "cat": TOKEN_CAT_WHEN_WHERE,
     "desc": "כתובת האולם המלאה"},

    {"key": "{{confirmation_link}}", "token": "[קישור אישור]", "cat": TOKEN_CAT_LINKS,
     "desc": "הקישור האישי של המוזמן לאישור הגעה"},
    {"key": "{{navigation_link}}", "token": "[קישור ניווט]", "cat": TOKEN_CAT_LINKS,
     "desc": "ניווט ב-Google Maps. נגזר מכתובת האולם."},
    {"key": "{{waze_link}}", "token": "[קישור וייז]", "cat": TOKEN_CAT_LINKS,
     "desc": "ניווט ב-Waze. נגזר מכתובת האולם."},

    {"key": "{{update_details}}", "token": "[פרטי שינוי]", "cat": TOKEN_CAT_EXTRA,
     "desc": "פרטי העדכון שתכתבו בשליחת הודעת שינוי (שעה חדשה, מקום חדש). ריק — השורה נעלמת."},
]

# טוקנים שהיו בבורר ואינם עוד: אין להם מקור נתונים באירוע (אין שדה מתנה או
# גלריה במערכת), ולכן הם היו נשארים ריקים תמיד ומוחקים את השורה שבה נכתבו.
# הם ממשיכים *להתפרש* (ראו ``build_automation_values``) כדי שתבנית שמורה
# ישנה שכוללת אותם לא תישבר — הם פשוט לא מוצעים יותר לבחירה.
RETIRED_TOKENS = ["[קישור מתנה]", "[גלריית תמונות]", "[גלריית וידאו]"]

# ============================================================================
#  אוצר המילים של הטוקנים לפי סוג אירוע
# ============================================================================
# הבעיה שזה פותר: גוף התבנית בספרייה הוא מחרוזת אחת המשותפת לכמה סוגי אירוע
# (``MITZVAH_LIBRARY`` משרתת גם בר וגם בת מצווה), ולכן הוא כתוב בטוקן קנוני
# אחד — ``[שמות בעלי האירוע]``. השליחה בפועל תמיד הייתה נכונה, כי כל הטוקנים
# כאן הם כינויים לאותו ערך; אבל *הטקסט שהחוגג רואה בעורך* אמר "שמות בעלי
# האירוע" — ניסוח זוגי באירוע שיש לו מארח אחד.
#
# הפתרון: תרגום הטוקן בגבול שבו הטקסט מגיע לעיני המשתמש (ספרייה, הקצאת
# תבנית, בורר הטוקנים). הספריות נשארות DRY, בר ובת מצווה מקבלות ניסוח שונה
# מאותה תבנית, וכל תבנית שמורה — ישנה או חדשה — ממשיכה להתפרש, כי כל
# הווריאציות ממופות לאותו ``{{event_name}}`` / ``{{groom_parents_line}}``.
#
# מפתח = הטוקן הקנוני שכתוב בגוף התבנית; ערך = מה שהמשתמש רואה.
TOKEN_VOCABULARY: dict[str, dict[str, str]] = {
    # חתונה וחינה = שני בני זוג. הספרייה החתונתית כבר כתובה ב-[שמות בני הזוג],
    # והמיפוי כאן מוודא שגם בורר הטוקנים יציע בדיוק את אותה מחרוזת.
    "wedding": {"[שמות בעלי האירוע]": "[שמות בני הזוג]"},
    "henna": {"[שמות בעלי האירוע]": "[שמות בני הזוג]"},
    "bar_mitzvah": {
        "[שמות בעלי האירוע]": "[שם החוגג]",
        "[הורי החתן]": "[משפחת החוגג]",
    },
    # ``MITZVAH_LIBRARY`` משרתת גם בר וגם בת מצווה, והנוסחים הדתיים בה כתובים
    # בלשון זכר ("זיכנו בכניסת בננו לעול המצוות"). בת מצווה קיבלה עד עכשיו
    # הזמנה שמדברת על "בננו". ההטיות מתורגמות כאן יחד עם הטוקנים — אותו
    # מנגנון, אותו גבול תצוגה — במקום לשכפל ספרייה שלמה בשביל שלוש מילים.
    "bat_mitzvah": {
        "[שמות בעלי האירוע]": "[שם החוגגת]",
        "[הורי החתן]": "[משפחת החוגגת]",
        "בננו היקר": "בתנו היקרה",
        "בכניסת בננו": "בכניסת בתנו",
        "בכניסתו לעול המצוות": "בכניסתה לעול המצוות",
    },
    # לשלושת אלה אין נוסח שמזמין דרך ההורים, ולכן אין להם תרגום ל-[הורי החתן]:
    # מיפוי מת היה יוצר כינוי ("[שם המחלקה]") שאיש לא רואה ולא משתמש בו.
    #
    # ברית: המזמינה היא *המשפחה*, ושם התינוק אינו נמסר בהזמנה — לרוב הוא עוד
    # לא ניתן. לכן השדה היחיד בטופס נקרא "שם המשפחה", והטוקן נקרא בדיוק כמוהו.
    "brit": {"[שמות בעלי האירוע]": "[שם המשפחה]"},
    "family": {"[שמות בעלי האירוע]": "[שם בעל השמחה]"},
    "business": {"[שמות בעלי האירוע]": "[שם החברה]"},
    "other": {"[שמות בעלי האירוע]": "[שם האירוע]"},
}


def vocabulary_for(event_type: str | None) -> dict[str, str]:
    """מפת התרגום מהטוקן הקנוני לטוקן שהמשתמש רואה, לסוג אירוע נתון."""
    return TOKEN_VOCABULARY.get(event_type or "wedding", {})


def localize_tokens(body: str, event_type: str | None) -> str:
    """מתרגם את גוף התבנית לשפה של סוג האירוע — טוקנים והטיות מגדר.

    מופעל בכל מקום שבו טקסט תבנית מגיע לעיני המשתמש — ספריית הנוסחים,
    הקצאת תבניות לאירוע חדש ותבנית ברירת המחדל. *לא* מופעל בשליחה: שם כל
    הווריאציות ממילא מתפרשות לאותו ערך, וכפל תרגום היה מיותר.

    ההחלפה מהארוך לקצר, כדי שביטוי מורכב ("בננו היקר") יטופל לפני החלק
    שמוכל בו ולא ייחתך לחצי ("בתנו היקר").
    """
    vocab = vocabulary_for(event_type)
    for canonical in sorted(vocab, key=len, reverse=True):
        if canonical in body:
            body = body.replace(canonical, vocab[canonical])
    return body



# מפת כינויים לתאימות-לאחור: משתנים/טוקנים ישנים שכבר נשמרו בתבניות קיימות,
# ממופים לאותם ערכים כמו המשתנים החדשים. כך תבנית שנכתבה פעם עדיין עובדת,
# בלי שהם יופיעו יותר בבורר-המשתנים של הזוג.
AUTOMATION_ALIASES = [
    {"key": "{{guest_name}}", "same_as": "{{first_name}}"},
    {"key": "{{couple_names}}", "same_as": "{{event_name}}"},
    {"key": "{{rsvp_link}}", "same_as": "{{confirmation_link}}"},
    {"key": "{{maps_link}}", "same_as": "{{navigation_link}}"},
    {"key": "[שם אורח]", "same_as": "{{first_name}}"},
    {"key": "[תאריך האירוע]", "same_as": "{{event_date}}"},
    # תאימות לאחור: הטוקן הישן "[שמות בני הזוג]" (שמופיע בספריית ההודעות
    # ובתבניות שכבר נשמרו) ממשיך לעבוד וממופה לאותו ערך כמו [שמות בעלי האירוע].
    {"key": "[שמות בני הזוג]", "same_as": "{{event_name}}"},
    # כינויים ותיקים — נשמרים כדי שתבנית שנשמרה איתם תמשיך לעבוד, גם אם הם
    # כבר לא מוצעים בבורר ולא מופיעים באף נוסח.
    {"key": "[הורי החוגג]", "same_as": "{{groom_parents_line}}"},
    # בברית אין שם לתינוק בהזמנה (לרוב הוא עוד לא ניתן), ולכן הטוקן נקרא
    # היום "[שם המשפחה]" — כמו השדה בטופס. הכינוי הישן נשאר מתפרש.
    {"key": "[משפחת התינוק]", "same_as": "{{event_name}}"},
]

# כל טוקן מקומי מ-``TOKEN_VOCABULARY`` הוא כינוי לטוקן הקנוני שהוא מחליף.
# נגזר אוטומטית ולא נכתב ביד: הוספת סוג אירוע או שינוי ניסוח ב-vocabulary
# מוסיפים את הכינוי מעצמם, ואי אפשר שייווצר טוקן שמוצג למשתמש אך אינו
# מתפרש בשליחה (הבאג שהיה קורה אילו היינו מתחזקים שתי רשימות במקביל).
_CANONICAL_KEY = {
    "[שמות בעלי האירוע]": "{{event_name}}",
    "[הורי החתן]": "{{groom_parents_line}}",
    "[הורי הכלה]": "{{bride_parents_line}}",
}
for _vocab in TOKEN_VOCABULARY.values():
    for _canonical, _localized in _vocab.items():
        _key = _CANONICAL_KEY.get(_canonical)
        if _key and not any(a["key"] == _localized for a in AUTOMATION_ALIASES):
            AUTOMATION_ALIASES.append({"key": _localized, "same_as": _key})


def maps_link(address: str) -> str:
    """קישור ניווט לגוגל מפות מתוך כתובת חופשית (ריק אם אין כתובת)."""
    address = (address or "").strip()
    if not address:
        return ""
    from urllib.parse import quote_plus

    return f"https://www.google.com/maps/search/?api=1&query={quote_plus(address)}"


def waze_link(address: str) -> str:
    """קישור ניווט ל-Waze מתוך כתובת חופשית (ריק אם אין כתובת).

    Waze פותח חיפוש לפי טקסט הכתובת; אין צורך בקואורדינטות/geocoding — הכתובת
    עצמה מספיקה, כך שאין תלות ב-API בתשלום.
    """
    address = (address or "").strip()
    if not address:
        return ""
    from urllib.parse import quote_plus

    return f"https://waze.com/ul?q={quote_plus(address)}&navigate=yes"


def event_values(event) -> dict:
    """כל ערכי ה*אירוע* המוזנים ל-``render_automation_template``, במקום אחד.

    קיים כדי שלא יקרה שוב מה שקרה עד עכשיו: שדות ``groom_parents_line`` /
    ``bride_parents_line`` היו קיימים במודל ובטוקנים, אבל אף אחד מארבעת מקומות
    השליחה לא העביר אותם — ולכן ההזמנות בסגנון דתי/חב"ד/חרדי איבדו את שורת
    ההורים תמיד, גם כשהיא מולאה. מכאן והלאה, הוספת שדה אירוע לתבנית = שינוי
    בפונקציה אחת, וכל מסלולי השליחה מקבלים אותו יחד.

    השימוש: ``render_automation_template(body, guest_name=..., link=...,
    **messaging.event_values(event))``.
    """
    # ייבוא lazy — ``automation`` מייבא את המודול הזה בראש הקובץ.
    from app import automation

    return {
        "groom": event.groom_name or "",
        "bride": event.bride_name or "",
        "venue": event.venue_name or "",
        "venue_address": event.venue_address or "",
        "date": automation.event_date_display(event),
        "time": event.event_time or "",
        "event_type": event.event_type or "wedding",
        "groom_parents_line": event.groom_parents_line or "",
        "bride_parents_line": event.bride_parents_line or "",
    }


def build_automation_values(
    *,
    guest_name: str,
    groom: str,
    bride: str,
    venue: str,
    venue_address: str = "",
    date: str = "",
    time: str = "",
    link: str = "",
    table_number: int | None = None,
    guest_count: int | None = None,
    gift_link: str = "",
    photo_gallery: str = "",
    video_gallery: str = "",
    event_type: str = "wedding",
    groom_parents_line: str = "",
    bride_parents_line: str = "",
    update_details: str = "",
) -> dict[str, str]:
    """בונה מפה מלאה של כל טוקן (טכני וידידותי, חדש וישן) → הערך שלו.

    זהו מקור-האמת היחיד לערכי המשתנים. מפריד את חישוב הערכים מהחלפתם, כדי
    ש-``render_automation_template`` יוכל גם *להסתיר שורות* שכל המשתנים בהן ריקים.
    מונחי האירוע (שם החגיגה, כינוי בעלי האירוע) נגזרים מ-``event_type``.
    """
    terms = event_terms.get_event_terms(event_type)
    couple = event_terms.hosts_names(event_type, groom, bride)
    first = guest_name.split()[0] if guest_name else ""
    nav = maps_link(venue_address)
    tbl = str(table_number) if table_number else ""
    cnt = str(guest_count) if (guest_count and guest_count > 0) else ""

    # ערך קנוני לכל משתנה מהרשימה הרשמית.
    canonical = {
        "{{first_name}}": first,
        "{{bride_name}}": bride or "",
        "{{groom_name}}": groom or "",
        "{{event_name}}": couple,
        "{{celebration}}": terms.celebration,
        "{{celebration_of}}": terms.celebration_construct,
        "{{event_date}}": date or "",
        "{{event_time}}": time or "",
        "{{venue_name}}": venue or "",
        "{{venue_address}}": venue_address or "",
        "{{confirmation_link}}": link or "",
        "{{navigation_link}}": nav,
        "{{waze_link}}": waze_link(venue_address),
        "{{table_number}}": tbl,
        "{{guest_count}}": cnt,
        "{{gift_link}}": gift_link or "",
        "{{photo_gallery}}": photo_gallery or "",
        "{{video_gallery}}": video_gallery or "",
        "{{groom_parents_line}}": groom_parents_line or "",
        "{{bride_parents_line}}": bride_parents_line or "",
        "{{update_details}}": update_details or "",
    }
    values: dict[str, str] = dict(canonical)
    # הטוקנים הידידותיים ([שם פרטי] וכו') מקבלים את אותו ערך.
    for p in AUTOMATION_PLACEHOLDERS:
        if p.get("token"):
            values[p["token"]] = canonical.get(p["key"], "")
    # טוקנים שהוצאו מהבורר אך עדיין עשויים להופיע בתבנית שמורה — חייבים
    # להישאר במפה. בלעדיהם הם היו נכתבים למוזמן כטקסט גולמי ("[קישור מתנה]")
    # במקום להיעלם בשקט יחד עם השורה שלהם.
    values["[קישור מתנה]"] = canonical["{{gift_link}}"]
    values["[גלריית תמונות]"] = canonical["{{photo_gallery}}"]
    values["[גלריית וידאו]"] = canonical["{{video_gallery}}"]
    # כינויים ישנים לתאימות-לאחור.
    for a in AUTOMATION_ALIASES:
        values[a["key"]] = canonical.get(a["same_as"], "")
    return values


_MULTI_SPACE = re.compile(r"[ \t]{2,}")
# תווי הפרדה שמחברים שני ערכים באותה שורה ("[תאריך] · [שעה]", "[אולם], [כתובת]").
_SEPARATORS = r"[,·|–—]"


def _drop_separator_around(line: str, token: str) -> str:
    """מוחק מפריד שנשען על ``token`` ריק, יחד עם הטוקן עצמו.

    למה נקודתי ולא "לחתוך פיסוק בסוף שורה": שורה כמו "[שם פרטי] שלום,"
    מסתיימת בפסיק *לגמרי בכוונה*, וחיתוך גורף היה הופך אותה ל"דנה שלום".
    כאן נמחק רק פסיק או נקודה-אמצעית שהצמוד להם הוא ערך שנעלם — למשל
    "[שמות בני הזוג] · [תאריך]" באירוע שעדיין אין לו תאריך, או
    "📍 [שם האולם], [כתובת]" בלי כתובת.
    """
    tok = re.escape(token)
    # מפריד שלפני הטוקן ("… · [תאריך]") ומפריד שאחריו ("[תאריך] · …").
    line = re.sub(rf"[ \t]*{_SEPARATORS}[ \t]*{tok}", "", line)
    line = re.sub(rf"{tok}[ \t]*{_SEPARATORS}[ \t]*", "", line)
    return line


def render_automation_template(
    body: str,
    *,
    guest_name: str,
    groom: str,
    bride: str,
    venue: str,
    venue_address: str = "",
    date: str = "",
    time: str = "",
    link: str = "",
    table_number: int | None = None,
    guest_count: int | None = None,
    gift_link: str = "",
    photo_gallery: str = "",
    video_gallery: str = "",
    event_type: str = "wedding",
    groom_parents_line: str = "",
    bride_parents_line: str = "",
    update_details: str = "",
) -> str:
    """ממלא תבנית אוטומציה במשתני {{...}} של מוזמן ואירוע ספציפיים.

    שלושה שדרוגים חשובים:
    1. *תוכן חכם* — שורה שכל המשתנים שבה ריקים (למשל "מספר השולחן שלך:
       {{table_number}}" כשעדיין אין שיבוץ) נמחקת לגמרי, כדי לא להשאיר שורה
       קטועה או משתנה "שבור" מול המוזמן. שורת ברכה בלי שם ("שלום {{first_name}}")
       נעלמת גם היא במקום להציג ברכה ריקה.
    2. *ניקוי שאריות* — שורה שרק *חלק* מהמשתנים בה התרוקנו לא נמחקת, אבל
       הסימנים שנשארו תלויים בגללם כן ("דנה ויואב · " ← "דנה ויואב"), וכך גם
       רווחים כפולים ונקודתיים שהבטיחו רשימה שכל שורותיה נמחקו.
    3. *תאימות לאחור* — משתנים ישנים בסגנון {{guest_name}} / [שם אורח] וגם
       {...} הישנים ממשיכים לעבוד.
    """
    values = build_automation_values(
        guest_name=guest_name,
        groom=groom,
        bride=bride,
        venue=venue,
        venue_address=venue_address,
        date=date,
        time=time,
        link=link,
        table_number=table_number,
        guest_count=guest_count,
        gift_link=gift_link,
        photo_gallery=photo_gallery,
        video_gallery=video_gallery,
        event_type=event_type,
        groom_parents_line=groom_parents_line,
        bride_parents_line=bride_parents_line,
        update_details=update_details,
    )
    # מחליפים טוקנים ארוכים לפני קצרים, כדי ש-"[תאריך האירוע]" לא ייחתך ל-"[תאריך]".
    tokens_by_len = sorted(values.keys(), key=len, reverse=True)

    text = body or DEFAULT_TEMPLATE
    out_lines: list[str] = []
    dropped_any = False
    for line in text.split("\n"):
        present = [tok for tok in values if tok in line]
        # תוכן חכם: אם בשורה יש משתנים והם *כולם* ריקים — מוחקים את השורה.
        if present and all(values[tok] == "" for tok in present):
            dropped_any = True
            continue
        # שורה מעורבת (חלק מהערכים קיימים וחלק ריקים): מוחקים כל טוקן ריק
        # *יחד עם המפריד שנשען עליו*, לפני ההחלפה הרגילה. בלי זה נשארות
        # שאריות שהזוג לא כתב — "דנה ויואב · " או "📍 אולמי הגן,".
        for tok in tokens_by_len:
            if values[tok] == "" and tok in line:
                line = _drop_separator_around(line, tok)
        for tok in tokens_by_len:
            if tok in line:
                line = line.replace(tok, values[tok])
        # רווח כפול נוצר כשטוקן ריק ישב בין שתי מילים. נוגעים רק בשורות
        # שבאמת עברו החלפה — שורת טקסט קבוע נשארת בדיוק כפי שנכתבה.
        if present:
            line = _MULTI_SPACE.sub(" ", line).rstrip()
        out_lines.append(line)
    text = "\n".join(out_lines)

    # אם התוכן החכם מחק את כל השורות — מחזירים ריק (בלי ליפול לתבנית ברירת המחדל).
    if not text.strip():
        return ""

    # תאימות לאחור: אם התבנית משתמשת עדיין במשתנים הישנים {...}, נמלא גם אותם.
    text = render_template(
        text,
        guest_name=guest_name,
        groom=groom,
        bride=bride,
        venue=venue,
        link=link,
        date=date,
        event_type=event_type,
    )
    # איחוד רווחים מיותרים שנוצרו ממחיקת שורות: 3+ שורות ריקות → אחת.
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    # נקודתיים יתומות: "כמה פרטים להגעה נוחה:" שכל השורות שהיא הבטיחה נמחקו
    # (אין עדיין אולם או כתובת). מסירים רק כשבאמת נמחקו שורות, כדי לא לגעת
    # בתבנית שמסתיימת בנקודתיים בכוונת הזוג.
    if dropped_any:
        text = re.sub(r"\s*:\s*$", "", text)
    return text


@dataclass
class SendResult:
    ok: bool
    provider: str
    status: str          # sent / failed — ראו app/message_status.py לאוצר המלים המלא
    detail: str = ""
    # מזהה ההודעה אצל הספק (wamid ב-Meta) — ריק כשאין (mock/כשל לפני שליחה).
    # נשמר על Message.provider_message_id כדי ש-webhook עתידי ידע לעדכן
    # בדיוק את השורה הנכונה (ראו app/message_status.py: outbound_fields).
    provider_message_id: str = ""
    # קוד השגיאה הגולמי מתגובת Meta (error.code), כשהשליחה נכשלת באופן
    # סינכרוני (למשל טוקן לא תקין, תבנית לא מאושרת). None כשאין כשל, או
    # כשלא הצלחנו לפרסר את גוף התגובה. נשמר גולמי על Message.failure_code
    # — לא מפורש כאן, ראו app/message_status.py למיפוי.
    error_code: Optional[int] = None


class MockProvider:
    """מצב בדיקה — לא שולח כלום החוצה, רק מדווח הצלחה כדי לרשום ביומן."""

    name = "mock"

    def send_invitation(self, phone: str, text: str) -> SendResult:
        # מזהה מדומה (לא אמיתי) — כדי שזרימת ה-provider_message_id תיבדק
        # גם במצב mock, בלי לחכות לחיבור Meta אמיתי.
        return SendResult(
            ok=True, provider=self.name, status="sent",
            provider_message_id=f"mock-{uuid4().hex[:16]}",
        )


class MetaProvider:
    """שליחה אמיתית מול WhatsApp Cloud API (Meta). פעיל רק ב-WHATSAPP_MODE=live.

    דורש משתני סביבה:
      WHATSAPP_TOKEN         — טוקן גישה קבוע
      WHATSAPP_PHONE_ID      — מזהה מספר השולח (Phone Number ID)
    ההודעה נשלחת עם שני כפתורי Quick Reply (interactive) ל-RSVP.
    """

    name = "meta"

    def __init__(self) -> None:
        self.token = os.getenv("WHATSAPP_TOKEN", "")
        self.phone_id = os.getenv("WHATSAPP_PHONE_ID", "")

    def send_invitation(self, phone: str, text: str) -> SendResult:
        if not self.token or not self.phone_id:
            return SendResult(
                ok=False,
                provider=self.name,
                status="failed",
                detail="חסר WHATSAPP_TOKEN או WHATSAPP_PHONE_ID",
            )
        try:
            import httpx  # נטען רק כשצריך — לא נדרש במצב mock

            url = f"https://graph.facebook.com/v20.0/{self.phone_id}/messages"
            payload = {
                "messaging_product": "whatsapp",
                "to": _to_e164(phone),
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": text},
                    "action": {
                        "buttons": [
                            {"type": "reply", "reply": {"id": RSVP_YES_ID, "title": RSVP_YES_LABEL}},
                            {"type": "reply", "reply": {"id": RSVP_NO_ID, "title": RSVP_NO_LABEL}},
                        ]
                    },
                },
            }
            headers = {"Authorization": f"Bearer {self.token}"}
            resp = httpx.post(url, json=payload, headers=headers, timeout=15.0)
            if resp.status_code // 100 == 2:
                # תגובת Meta כוללת messages: [{"id": "wamid...."}] — המזהה
                # שדרכו יגיע webhook עתידי עם עדכון נמסרה/נקראה/נכשלה.
                wamid = ""
                try:
                    wamid = (resp.json().get("messages") or [{}])[0].get("id", "")
                except Exception:
                    wamid = ""
                return SendResult(
                    ok=True, provider=self.name, status="sent",
                    provider_message_id=wamid,
                )
            # תגובת שגיאה של Meta היא {"error": {"message":..., "code":..., ...}}
            # (מתועד ב-Cloud API). מפרסרים בעדינות — כשל בפרסור לא אמור
            # להפיל את הטיפול בשגיאה המקורית.
            error_code = None
            try:
                error_code = resp.json().get("error", {}).get("code")
                error_code = int(error_code) if error_code is not None else None
            except Exception:
                error_code = None
            return SendResult(
                ok=False, provider=self.name, status="failed",
                detail=f"Meta {resp.status_code}: {resp.text[:200]}",
                error_code=error_code,
            )
        except Exception as exc:  # רשת/תלות חסרה — לא מפילים את הבקשה
            return SendResult(ok=False, provider=self.name, status="failed", detail=str(exc))


def _to_e164(phone: str) -> str:
    """המרה גסה למספר בינלאומי ישראלי (0501234567 -> 972501234567)."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("0"):
        digits = "972" + digits[1:]
    return digits


def get_provider():
    """בוחר ספק לפי המצב הנוכחי."""
    return MetaProvider() if current_mode() == "live" else MockProvider()


def rsvp_from_button(button_id: str) -> str | None:
    """ממפה מזהה כפתור שהמוזמן לחץ לסטטוס RSVP. None אם לא מזוהה."""
    if button_id == RSVP_YES_ID:
        return "confirmed"
    if button_id == RSVP_NO_ID:
        return "declined"
    return None
