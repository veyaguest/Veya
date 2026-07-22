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
from dataclasses import dataclass

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

# קידומת עדינה שנוספת בראש הודעת תזכורת (למי שעדיין לא ענה).
REMINDER_PREFIX = "תזכורת קטנה 🙂 עדיין לא קיבלנו את אישורכם —"

# המשתנים הנתמכים — כל אחד עם כמה כינויים (אנגלית + עברית) לנוחות.
PLACEHOLDERS = [
    {"key": "{name}", "aliases": ["{name}", "{שם}"], "desc": "שם המוזמן"},
    {"key": "{event_name}", "aliases": ["{event_name}", "{שמות}"], "desc": "שמות בעלי האירוע"},
    {"key": "{date}", "aliases": ["{date}", "{תאריך}"], "desc": "תאריך האירוע"},
    {"key": "{venue}", "aliases": ["{venue}", "{מקום}"], "desc": "שם האולם"},
    {"key": "{personal_link}", "aliases": ["{personal_link}", "{קישור_אישי}"], "desc": "הקישור האישי לאישור"},
]


def public_base_url() -> str:
    """כתובת הבסיס של דף האישור הציבורי (ניתן לקבוע דרך משתנה סביבה)."""
    return os.getenv("PUBLIC_BASE_URL", "http://localhost:5173").rstrip("/")


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
AUTOMATION_PLACEHOLDERS = [
    {"key": "{{first_name}}", "token": "[שם פרטי]", "desc": "שם פרטי של המוזמן"},
    {"key": "{{bride_name}}", "token": "[שם הכלה]", "desc": "שם בעל/ת האירוע השני/ה (בחתונה — הכלה)"},
    {"key": "{{groom_name}}", "token": "[שם החתן]", "desc": "שם בעל/ת האירוע הראשי/ת (בחתונה — החתן)"},
    {"key": "{{event_name}}", "token": "[שמות בעלי האירוע]", "desc": "שמות בעלי האירוע (בחתונה — בני הזוג)"},
    {"key": "{{celebration}}", "token": "[האירוע]", "desc": "שם האירוע לפי סוגו, לשימוש אחרי ל/ב (חתונה / אירוע בר המצווה / אירוע)"},
    {"key": "{{celebration_of}}", "token": "[שמחת]", "desc": "שם האירוע לפני שמות בעלי האירוע (חתונת… / בר המצווה של…)"},
    {"key": "{{event_date}}", "token": "[תאריך]", "desc": "תאריך האירוע"},
    {"key": "{{event_time}}", "token": "[שעה]", "desc": "שעת האירוע"},
    {"key": "{{venue_name}}", "token": "[שם האולם]", "desc": "שם האולם"},
    {"key": "{{venue_address}}", "token": "[כתובת]", "desc": "כתובת האולם"},
    {"key": "{{confirmation_link}}", "token": "[קישור אישור]", "desc": "קישור אישי לאישור הגעה"},
    {"key": "{{navigation_link}}", "token": "[קישור ניווט]", "desc": "קישור לניווט (Google Maps)"},
    {"key": "{{waze_link}}", "token": "[קישור וייז]", "desc": "קישור לניווט ב-Waze"},
    {"key": "{{table_number}}", "token": "[מספר שולחן]", "desc": "מספר השולחן של המוזמן"},
    {"key": "{{guest_count}}", "token": "[כמות מקומות]", "desc": "כמות המקומות השמורים למוזמן"},
    {"key": "{{gift_link}}", "token": "[קישור מתנה]", "desc": "קישור למתנה / העברה כספית"},
    {"key": "{{photo_gallery}}", "token": "[גלריית תמונות]", "desc": "קישור לגלריית התמונות"},
    {"key": "{{video_gallery}}", "token": "[גלריית וידאו]", "desc": "קישור לגלריית הווידאו"},
]

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
]


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
    }
    values: dict[str, str] = dict(canonical)
    # הטוקנים הידידותיים ([שם פרטי] וכו') מקבלים את אותו ערך.
    for p in AUTOMATION_PLACEHOLDERS:
        if p.get("token"):
            values[p["token"]] = canonical.get(p["key"], "")
    # כינויים ישנים לתאימות-לאחור.
    for a in AUTOMATION_ALIASES:
        values[a["key"]] = canonical.get(a["same_as"], "")
    return values


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
) -> str:
    """ממלא תבנית אוטומציה במשתני {{...}} של מוזמן ואירוע ספציפיים.

    שני שדרוגים חשובים:
    1. *תוכן חכם* — שורה שכל המשתנים שבה ריקים (למשל "מספר השולחן שלך:
       {{table_number}}" כשעדיין אין שיבוץ) נמחקת לגמרי, כדי לא להשאיר שורה
       קטועה או משתנה "שבור" מול המוזמן. שורת ברכה בלי שם ("שלום {{first_name}}")
       נעלמת גם היא במקום להציג ברכה ריקה.
    2. *תאימות לאחור* — משתנים ישנים בסגנון {{guest_name}} / [שם אורח] וגם
       {...} הישנים ממשיכים לעבוד.
    """
    import re

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
    )
    # מחליפים טוקנים ארוכים לפני קצרים, כדי ש-"[תאריך האירוע]" לא ייחתך ל-"[תאריך]".
    tokens_by_len = sorted(values.keys(), key=len, reverse=True)

    text = body or DEFAULT_TEMPLATE
    out_lines: list[str] = []
    for line in text.split("\n"):
        present = [tok for tok in values if tok in line]
        # תוכן חכם: אם בשורה יש משתנים והם *כולם* ריקים — מוחקים את השורה.
        if present and all(values[tok] == "" for tok in present):
            continue
        for tok in tokens_by_len:
            if tok in line:
                line = line.replace(tok, values[tok])
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
    return text


@dataclass
class SendResult:
    ok: bool
    provider: str
    status: str          # sent / failed
    detail: str = ""


class MockProvider:
    """מצב בדיקה — לא שולח כלום החוצה, רק מדווח הצלחה כדי לרשום ביומן."""

    name = "mock"

    def send_invitation(self, phone: str, text: str) -> SendResult:
        return SendResult(ok=True, provider=self.name, status="sent")


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
                return SendResult(ok=True, provider=self.name, status="sent")
            return SendResult(
                ok=False, provider=self.name, status="failed",
                detail=f"Meta {resp.status_code}: {resp.text[:200]}",
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
