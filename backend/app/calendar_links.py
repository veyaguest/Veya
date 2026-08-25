"""הוספת האירוע ליומן של המוזמן — ICS תקני + קישורים ל-Google/Outlook.

למה מודול נפרד ולמה בצד השרת:
  1. **ICS חייב להיות URL אמיתי.** ב-iOS Safari, קובץ .ics שמוגש עם
     ``Content-Type: text/calendar`` נפתח ישירות במסך "הוספה ליומן" של אפל.
     blob:/data: URL שנוצר ב-Frontend פשוט לא עובד שם — ולכן זו לא בחירה
     טכנית אלא בחירת UX.
  2. **מקור אמת אחד.** גם ה-ICS, גם קישור Google וגם קישור Outlook נגזרים
     מאותו חישוב חלון-זמן, כך שלא ייתכן שאחד מהם יראה שעה אחרת.

אזור הזמן: כל האירועים ב-VEYA הם בישראל, ולכן ``event_time`` נקרא כשעת קיר
ישראלית ומומר ל-UTC. כך מוזמן שנמצא בחו"ל רואה את השעה הנכונה *שלו*, ולא
19:00 מקומית בטעות.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date as _date, datetime, time as _time, timedelta, timezone
from urllib.parse import quote, urlencode

# tzdata נמצא ב-requirements כרשת ביטחון, אבל אם משום מה אין מסד אזורי זמן
# בסביבה — לא מפילים את הדף. נופלים ל"שעה צפה" (ICS בלי אזור זמן), שמוצגת
# בשעון המקומי של המכשיר. לרוב המוחלט של המוזמנים (בישראל) זה זהה.
try:  # pragma: no cover - תלוי סביבה
    from zoneinfo import ZoneInfo

    ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")
except Exception:  # pragma: no cover
    ISRAEL_TZ = None

# משך ברירת מחדל לאירוע. VEYA שומרת שעת התחלה בלבד — אין שדה "שעת סיום"
# ואנחנו לא מבקשים מהזוג עוד שדה רק בשביל היומן. 4 שעות זה החסם שמכסה
# אירוע ישראלי טיפוסי בלי "לתפוס" למוזמן את כל הלילה ביומן.
DEFAULT_DURATION_HOURS = 4

PRODID = "-//VEYA//Guest Hub//HE"


@dataclass(frozen=True)
class EventWindow:
    """חלון הזמן של האירוע, מוכן לכל הפורמטים."""

    start: datetime            # מודע-אזור-זמן אם יש tzdata, אחרת נאיבי
    end: datetime
    all_day: bool              # אין שעה לאירוע → אירוע יום שלם ביומן
    aware: bool                # האם הצלחנו לשייך אזור זמן אמיתי


def parse_window(event_date: str, event_time: str) -> EventWindow | None:
    """בונה חלון זמן מ-``YYYY-MM-DD`` + ``HH:MM`` (שניהם טקסט ב-DB).

    מחזיר ``None`` כשאין תאריך תקין — ואז פעולת "הוספה ליומן" פשוט לא מוצעת
    למוזמן. עדיף להסתיר כפתור מלהציע כפתור שמייצר אירוע ריק ביומן.
    """
    raw_date = (event_date or "").strip()
    if not raw_date:
        return None
    try:
        day = _date.fromisoformat(raw_date)
    except ValueError:
        return None

    raw_time = (event_time or "").strip()
    if not raw_time:
        # אירוע יום שלם: DTEND ב-ICS הוא בלעדי, ולכן היום שאחרי.
        start = datetime.combine(day, _time(0, 0))
        return EventWindow(start=start, end=start + timedelta(days=1), all_day=True, aware=False)

    try:
        hh, mm = raw_time.split(":")[:2]
        clock = _time(int(hh), int(mm))
    except (ValueError, IndexError):
        start = datetime.combine(day, _time(0, 0))
        return EventWindow(start=start, end=start + timedelta(days=1), all_day=True, aware=False)

    start = datetime.combine(day, clock)
    if ISRAEL_TZ is not None:
        start = start.replace(tzinfo=ISRAEL_TZ)
    return EventWindow(
        start=start,
        end=start + timedelta(hours=DEFAULT_DURATION_HOURS),
        all_day=False,
        aware=ISRAEL_TZ is not None,
    )


# ---- עזרי פורמט ----------------------------------------------------------

def _utc_stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _floating_stamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%dT%H%M%S")


def _date_stamp(moment: datetime) -> str:
    return moment.strftime("%Y%m%d")


def _escape(value: str) -> str:
    """הברחת תווים לפי RFC 5545 — אחרת פסיק בכתובת שובר את הקובץ."""
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _fold(line: str) -> str:
    """קיפול שורות ל-75 *אוקטטים* (לא תווים) לפי RFC 5545.

    קריטי בעברית: כל אות היא 2 בתים ב-UTF-8, ולכן ספירה לפי תווים הייתה
    מייצרת שורות ארוכות מדי — ויומנים מחמירים (Outlook) פוסלים את הקובץ.
    הקיפול נעשה על גבול תו שלם, כדי לא לחתוך אות באמצע.
    """
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out: list[str] = []
    chunk = b""
    limit = 75
    for ch in line:
        enc = ch.encode("utf-8")
        if len(chunk) + len(enc) > limit:
            out.append(chunk.decode("utf-8"))
            chunk = b""
            limit = 74  # שורות המשך מתחילות ברווח, שנספר גם הוא
        chunk += enc
    if chunk:
        out.append(chunk.decode("utf-8"))
    return "\r\n ".join(out)


def _location(venue_name: str, venue_address: str) -> str:
    parts = [p.strip() for p in (venue_name, venue_address) if (p or "").strip()]
    # שם האולם והכתובת יכולים לחזור על עצמם ("אולמי X, רחוב Y" בשני השדות)
    if len(parts) == 2 and parts[0] in parts[1]:
        return parts[1]
    return ", ".join(parts)


# ---- ICS -----------------------------------------------------------------

def build_ics(
    *,
    title: str,
    event_id: int,
    venue_name: str = "",
    venue_address: str = "",
    description: str = "",
    window: EventWindow,
) -> str:
    """מייצר קובץ ICS לאירוע אחד.

    ``UID`` יציב פר-אירוע: מוזמן שילחץ "הוספה ליומן" פעמיים לא יקבל שני
    עותקים — היומן יזהה שזה אותו אירוע ויעדכן אותו.
    """
    now = datetime.now(timezone.utc)
    location = _location(venue_name, venue_address)

    if window.all_day:
        dtstart = f"DTSTART;VALUE=DATE:{_date_stamp(window.start)}"
        dtend = f"DTEND;VALUE=DATE:{_date_stamp(window.end)}"
    elif window.aware:
        dtstart = f"DTSTART:{_utc_stamp(window.start)}"
        dtend = f"DTEND:{_utc_stamp(window.end)}"
    else:
        # "שעה צפה" — נקראת בשעון המקומי של המכשיר.
        dtstart = f"DTSTART:{_floating_stamp(window.start)}"
        dtend = f"DTEND:{_floating_stamp(window.end)}"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:veya-event-{event_id}@veya.co.il",
        f"DTSTAMP:{_utc_stamp(now)}",
        dtstart,
        dtend,
        f"SUMMARY:{_escape(title)}",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
    ]
    if location:
        lines.append(f"LOCATION:{_escape(location)}")
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    # תזכורת יום לפני — הסיבה שבגללה מוזמן מוסיף ליומן מלכתחילה.
    lines += [
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        "TRIGGER:-P1D",
        f"DESCRIPTION:{_escape(title)}",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def ics_filename(title: str) -> str:
    """שם קובץ ה-ICS. ASCII בלבד ב-``filename`` + גרסת UTF-8 ב-``filename*``
    מטופלים ב-router; כאן רק הכותרת הנקייה."""
    clean = "".join(ch for ch in (title or "event") if ch not in '\\/:*?"<>|\r\n').strip()
    return f"{clean or 'event'}.ics"


# ---- קישורי יומן ווב ------------------------------------------------------

def google_link(
    *,
    title: str,
    venue_name: str = "",
    venue_address: str = "",
    description: str = "",
    window: EventWindow,
) -> str:
    """קישור "הוספה ליומן Google" (טופס מוכן — המוזמן רק מאשר)."""
    if window.all_day:
        dates = f"{_date_stamp(window.start)}/{_date_stamp(window.end)}"
    elif window.aware:
        dates = f"{_utc_stamp(window.start)}/{_utc_stamp(window.end)}"
    else:
        dates = f"{_floating_stamp(window.start)}/{_floating_stamp(window.end)}"

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": dates,
    }
    location = _location(venue_name, venue_address)
    if location:
        params["location"] = location
    if description:
        params["details"] = description
    if window.aware:
        params["ctz"] = "Asia/Jerusalem"
    return "https://calendar.google.com/calendar/render?" + urlencode(params, quote_via=quote)


def outlook_link(
    *,
    title: str,
    venue_name: str = "",
    venue_address: str = "",
    description: str = "",
    window: EventWindow,
) -> str:
    """קישור "הוספה ליומן Outlook" (outlook.com / Microsoft 365 בדפדפן).

    Outlook מצפה ל-ISO 8601. באירוע יום שלם מוסיפים ``allday=true``.
    """
    if window.all_day:
        start = window.start.strftime("%Y-%m-%d")
        end = window.end.strftime("%Y-%m-%d")
    elif window.aware:
        start = window.start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = window.end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        start = window.start.strftime("%Y-%m-%dT%H:%M:%S")
        end = window.end.strftime("%Y-%m-%dT%H:%M:%S")

    params = {
        "path": "/calendar/action/compose",
        "rru": "addevent",
        "subject": title,
        "startdt": start,
        "enddt": end,
    }
    if window.all_day:
        params["allday"] = "true"
    location = _location(venue_name, venue_address)
    if location:
        params["location"] = location
    if description:
        params["body"] = description
    return "https://outlook.live.com/calendar/0/deeplink/compose?" + urlencode(params, quote_via=quote)
