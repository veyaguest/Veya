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

# שני כפתורי Quick Reply — עד 3 מותר בוואטסאפ (החלטה טכנית 2).
RSVP_YES_ID = "rsvp_yes"
RSVP_NO_ID = "rsvp_no"
RSVP_YES_LABEL = "מגיע/ה ✅"
RSVP_NO_LABEL = "לא מגיע/ה ❌"


def current_mode() -> str:
    """מצב הערוץ מתוך משתנה סביבה. ברירת מחדל בטוחה: mock (בלי שליחה אמיתית)."""
    return os.getenv("WHATSAPP_MODE", "mock").strip().lower()


def build_invitation_text(guest_name: str, groom: str, bride: str, venue: str) -> str:
    """נוסח ההזמנה שנשלח למוזמן (טקסט תבנית, לפני הכפתורים)."""
    couple = " ו".join([n for n in (groom, bride) if n]) or "בני הזוג"
    where = f" ב{venue}" if venue else ""
    hi = guest_name.split()[0] if guest_name else "שלום"
    return (
        f"היי {hi}! 💍\n"
        f"{couple} שמחים להזמין אותך לחתונה{where}.\n"
        f"נשמח לדעת אם תגיע/י — לחיצה על אחד הכפתורים למטה:"
    )


# ---- תבניות הודעה עם משתנים (שלב RSVP 2) ----

# תבנית ברירת המחדל. הבעלים יכול לערוך אותה ולשמור אחת משלו.
DEFAULT_TEMPLATE = (
    "שלום {name}! 💍\n"
    "{event_name} שמחים להזמין אתכם לחתונה{venue}.\n"
    "נשמח לאישור הגעה בקישור האישי:\n"
    "{personal_link}"
)

# קידומת עדינה שנוספת בראש הודעת תזכורת (למי שעדיין לא ענה).
REMINDER_PREFIX = "תזכורת קטנה 🙂 עדיין לא קיבלנו את אישורכם —"

# המשתנים הנתמכים — כל אחד עם כמה כינויים (אנגלית + עברית) לנוחות.
PLACEHOLDERS = [
    {"key": "{name}", "aliases": ["{name}", "{שם}"], "desc": "שם המוזמן"},
    {"key": "{event_name}", "aliases": ["{event_name}", "{שמות}"], "desc": "שמות בני הזוג"},
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
) -> str:
    """ממלא את המשתנים בתבנית בערכים של מוזמן ואירוע ספציפיים.

    תומך גם בכינויים בעברית ({שם}, {שמות}, {תאריך}, {מקום}, {קישור_אישי}).
    """
    couple = " ו".join([n for n in (groom, bride) if n]) or "בני הזוג"
    where = f" ב{venue}" if venue else ""
    values = {
        "name": guest_name.split()[0] if guest_name else "שלום",
        "event_name": couple,
        "date": date or "",
        "venue": where,
        "personal_link": link,
    }
    text = template or DEFAULT_TEMPLATE
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
    {"key": "{{guest_name}}", "token": "[שם אורח]", "desc": "שם המוזמן"},
    {"key": "{{couple_names}}", "token": "[שמות בני הזוג]", "desc": "שמות בני הזוג"},
    {"key": "{{event_date}}", "token": "[תאריך האירוע]", "desc": "תאריך האירוע"},
    {"key": "{{event_time}}", "token": "[שעה]", "desc": "שעת האירוע"},
    {"key": "{{venue_name}}", "token": "[שם האולם]", "desc": "שם האולם"},
    {"key": "{{venue_address}}", "token": "[כתובת]", "desc": "כתובת האולם"},
    {"key": "{{maps_link}}", "token": "[קישור ניווט]", "desc": "קישור לניווט בגוגל מפות"},
    {"key": "{{waze_link}}", "token": "[קישור וייז]", "desc": "קישור לניווט ב-Waze"},
    {"key": "{{rsvp_link}}", "token": "[קישור אישור]", "desc": "הקישור האישי לאישור הגעה"},
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
) -> str:
    """ממלא תבנית אוטומציה במשתני {{...}} של מוזמן ואירוע ספציפיים.

    תומך גם במשתנים הישנים בסגנון {...} דרך ``render_template`` (תאימות לאחור),
    כך שתבנית שנכתבה פעם עדיין תעבוד.
    """
    couple = " ו".join([n for n in (groom, bride) if n]) or "בני הזוג"
    values = {
        "{{guest_name}}": guest_name.split()[0] if guest_name else "שלום",
        "{{couple_names}}": couple,
        "{{event_date}}": date or "",
        "{{event_time}}": time or "",
        "{{venue_name}}": venue or "",
        "{{venue_address}}": venue_address or "",
        "{{maps_link}}": maps_link(venue_address),
        "{{waze_link}}": waze_link(venue_address),
        "{{rsvp_link}}": link or "",
    }
    text = body or DEFAULT_TEMPLATE
    # קודם ממירים את הכינויים הידידותיים ([שם אורח]) לערכים — זה מה שהזוג
    # מקליד בעורך הפשוט. ממופה לאותם ערכים כמו המשתנים הטכניים.
    friendly = {p["token"]: values.get(p["key"], "") for p in AUTOMATION_PLACEHOLDERS if p.get("token")}
    for token, val in friendly.items():
        text = text.replace(token, val)
    for key, val in values.items():
        text = text.replace(key, val)
    # תאימות לאחור: אם התבנית משתמשת עדיין במשתנים הישנים {...}, נמלא גם אותם.
    text = render_template(
        text,
        guest_name=guest_name,
        groom=groom,
        bride=bride,
        venue=venue,
        link=link,
        date=date,
    )
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
