"""מייצר fixtures לבדיקת הזהות בין התצוגה המקדימה בדפדפן לשליחה בשרת.

הרצה (מתוך backend/):
    venv/bin/python ../frontend/src/lib/messagePreview.fixtures.py

לכל תבנית בספרייה, בכל סוג אירוע ובכמה מצבי נתונים, נשמרים:
  - ``body``     — גוף התבנית
  - ``sample``   — מפת טוקן→ערך *בדיוק* כפי שהדפדפן בונה אותה
  - ``expected`` — הפלט של ``render_automation_template`` בשרת

הבדיקה ב-``messagePreview.test.mjs`` מריצה את מנוע הדפדפן על אותם קלטים
ודורשת זהות מוחלטת. כך כלל רינדור שמשתנה רק בצד אחד נתפס מיד.
"""
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3] / "backend"
sys.path.insert(0, str(BACKEND))

from app import message_library as lib, messaging, event_terms  # noqa: E402


class FakeEvent:
    def __init__(self, **kw):
        self.groom_name = ""
        self.bride_name = ""
        self.venue_name = ""
        self.venue_address = ""
        self.event_date = ""
        self.event_time = ""
        self.event_type = "wedding"
        self.groom_parents_line = ""
        self.bride_parents_line = ""
        self.__dict__.update(kw)


GUEST = "דנה כהן"
# ערכי הדוגמה הקבועים של הדפדפן (המקבילים ל-buildSampleTokens).
RSVP = "https://veya.co.il/confirm/…"
NAV = "https://maps.google.com/…"
TABLE = "12"
SEATS = "2"


def browser_sample(ev: FakeEvent) -> dict:
    """מפת הטוקנים כפי שהדפדפן בונה אותה — התאום של ``buildSampleTokens``."""
    terms = event_terms.get_event_terms(ev.event_type)
    hosts = event_terms.hosts_names(ev.event_type, ev.groom_name, ev.bride_name)
    first = GUEST.split()[0]
    nav = NAV if ev.venue_address else ""
    gp, bp = ev.groom_parents_line, ev.bride_parents_line
    return {
        "{{first_name}}": first, "{{guest_name}}": first,
        "[שם פרטי]": first, "[שם אורח]": first,
        "{{event_name}}": hosts, "{{couple_names}}": hosts,
        "[שמות בעלי האירוע]": hosts, "[שמות בני הזוג]": hosts,
        "[שם החוגג]": hosts, "[שם החוגגת]": hosts, "[שם בעל השמחה]": hosts,
        "{{groom_name}}": ev.groom_name, "[שם החתן]": ev.groom_name,
        "{{bride_name}}": ev.bride_name, "[שם הכלה]": ev.bride_name,
        "{{groom_parents_line}}": gp, "[הורי החתן]": gp, "[הורי החוגג]": gp,
        "{{bride_parents_line}}": bp, "[הורי הכלה]": bp,
        "{{celebration}}": terms.celebration, "[האירוע]": terms.celebration,
        "{{celebration_of}}": terms.celebration_construct,
        "[שמחת]": terms.celebration_construct,
        "{{event_date}}": _date(ev), "[תאריך]": _date(ev), "[תאריך האירוע]": _date(ev),
        "{{event_time}}": ev.event_time, "[שעה]": ev.event_time,
        "{{venue_name}}": ev.venue_name, "[שם האולם]": ev.venue_name,
        "{{venue_address}}": ev.venue_address, "[כתובת]": ev.venue_address,
        "{{confirmation_link}}": RSVP, "{{rsvp_link}}": RSVP, "[קישור אישור]": RSVP,
        "{{navigation_link}}": nav, "{{maps_link}}": nav, "[קישור ניווט]": nav,
        "{{waze_link}}": nav, "[קישור וייז]": nav,
        "{{table_number}}": TABLE, "[מספר שולחן]": TABLE,
        "{{guest_count}}": SEATS, "[כמות מקומות]": SEATS,
        "{{update_details}}": "", "[פרטי שינוי]": "",
        "{{gift_link}}": "", "[קישור מתנה]": "",
        "{{photo_gallery}}": "", "[גלריית תמונות]": "",
        "{{video_gallery}}": "", "[גלריית וידאו]": "",
    }


def _date(ev: FakeEvent) -> str:
    from app import automation
    return automation.event_date_display(ev)


def _normalize_links(text: str, ev: FakeEvent) -> str:
    """מיישר את *ערכי* קישורי הניווט בין השרת לדפדפן לפני ההשוואה.

    השרת שולח קישור Google Maps/Waze מלא ומקודד; התצוגה המקדימה מציגה
    קישור קצר וקריא, כי אין טעם להראות לזוג מחרוזת של 200 תווים. ההבדל
    הזה מכוון — ומה שהבדיקה באמת אמורה לשמור עליו הוא *מבנה* ההודעה:
    אילו שורות נמחקות, אילו מפרידים יורדים ואיפה נשארות שורות ריקות.
    לכן משווים אחרי איחוד הערך, ולא מוותרים על התבניות שיש בהן ניווט.
    """
    for real in (messaging.maps_link(ev.venue_address),
                 messaging.waze_link(ev.venue_address)):
        if real:
            text = text.replace(real, NAV)
    return text


FULL = dict(venue_name="אולמי הגן", venue_address="הרצל 1, תל אביב",
            event_date="2026-09-10", event_time="20:00")

SCENARIOS = [
    ("זוג מלא", dict(groom_name="יואב", bride_name="דנה", **FULL)),
    ("חוגג יחיד", dict(groom_name="יונתן", **FULL)),
    ("עם הורים", dict(groom_name="יונתן", groom_parents_line="משפחת כהן",
                      bride_parents_line="משפחת לוי", **FULL)),
    ("בלי אולם", dict(groom_name="יואב", bride_name="דנה", event_date="2026-09-10")),
    ("אירוע חדש", dict(groom_name="יואב", bride_name="דנה")),
]


def main() -> None:
    # מפות הטוקנים זהות לכל התבניות באותו (סוג אירוע × תרחיש), ולכן נשמרות
    # פעם אחת ומקבלות מזהה. בלי זה הקובץ שוקל 2MB של כפילויות.
    samples: list[dict] = []
    out = []
    for etype in lib._LIBRARY_BY_TYPE:
        for sname, kw in SCENARIOS:
            ev = FakeEvent(event_type=etype, **kw)
            samples.append(browser_sample(ev))
            sample_id = len(samples) - 1
            values = messaging.event_values(ev)
            for entry in lib.entries_for(etype):
                expected = messaging.render_automation_template(
                    entry["body"], guest_name=GUEST,
                    link=RSVP, table_number=int(TABLE), guest_count=int(SEATS),
                    **values,
                )
                expected = _normalize_links(expected, ev)
                out.append({
                    "name": f"{etype}/{sname}/{entry['name']}",
                    "body": entry["body"],
                    "sample_id": sample_id,
                    "expected": expected,
                })

    target = Path(__file__).with_name("messagePreview.fixtures.json")
    target.write_text(
        json.dumps({"samples": samples, "cases": out}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"✓ נכתבו {len(out)} fixtures ({len(samples)} מפות טוקנים) ל-{target.name}")


if __name__ == "__main__":
    main()
