"""ייצוא רשימת המוזמנים לפורמט של אייפלן (iPlan) — להושבה באולמות שעובדים איתו.

שכבת התאמה בלבד: קוראת את המוזמנים כפי שהם ב-VEYA ומתרגמת אותם לתבנית של
אייפלן. **לא משנה שום נתון**, ולא מחשבת כמויות מחדש.

מקור הפורמט — קובץ התבנית הרשמי של אייפלן (wedding_invitations_template_he-IL.xls):

- Excel 97–2003 (``.xls``, BIFF8). לא ``.xlsx`` ולא CSV — לכן ``xlwt``.
- גיליון יחיד ``הזמנות``, מימין לשמאל.
- שורה 1: כותרות-על ממוזגות (שיוך / פרטי התקשרות / כתובת).
- שורה 2: 12 כותרות העמודות, בסדר קבוע (``COLUMNS``).
- משורה 3: שורה לכל הזמנה. טלפון כטקסט עם מקף ("050-1234567"), נייד וקווי
  בעמודות נפרדות. מספר האורחים — מספר שלם.

מי נכנס (החלטת בעלים 2026-09-28): רק מי שאישר הגעה, עם ``Guest.effective_seats``
— אותו מקור בדיוק כמו מנוע ההושבה ומפת האולם. מי שלא אישר נספר בסיכום אבל
לא נכנס לקובץ. מוזמן ב"צד משותף" — תא "צד" ריק (בתבנית יש רק חתן/כלה).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import xlwt

from app import models
from app.event_terms import get_event_terms, hosts_names
from app.validators import normalize_israeli_phone

SHEET_NAME = "הזמנות"

# 12 העמודות — שמות וסדר זהים לתבנית של אייפלן. אין להוסיף/לשנות סדר.
COLUMNS = [
    "הזמנה לכבוד",
    "מס' אורחים שהוזמנו",
    "צד",
    "קבוצה",
    "סלולרי",
    "טלפון רגיל",
    "אימייל",
    "עיר",
    "רחוב",
    "מיקוד",
    "תא דואר",
    "צ'ק צפוי",
]

# כותרות-העל הממוזגות בשורה 1: (טקסט, עמודה ראשונה, עמודה אחרונה) — כמו בתבנית.
GROUP_HEADERS = [
    ("שיוך", 2, 3),
    ("פרטי התקשרות", 4, 6),
    ("כתובת", 7, 10),
]

# רוחב העמודות מהתבנית (יחידות של 1/256 תו). ויזואלי בלבד, אבל זול לשמר.
_COLUMN_WIDTHS = [4954, 4864, 2138, 3930, 3162, 3162, 5932, 2220, 3884, 1708, 2176, 2266]
_HEADER_ROW_HEIGHT = 332
_DATA_ROW_HEIGHT = 292

# ``xlwt`` כותב גרסת BIFF8 שמוגבלת ל-65,536 שורות. גבול תיאורטי בלבד לאירוע.
MAX_ROWS = 65_536 - 2


@dataclass
class ExportIssue:
    """בעיה בנתונים שהמשתמש צריך לדעת עליה לפני ההורדה."""

    guest_id: int
    full_name: str
    kind: str  # missing_name / zero_seats / bad_phone
    #: True — המוזמן לא נכנס לקובץ. False — נכנס, אבל שדה אחד נשאר ריק.
    excluded: bool


@dataclass
class ExportRow:
    guest_id: int
    name: str
    seats: int
    side: str
    group: str
    mobile: str
    landline: str


@dataclass
class ExportPlan:
    """מה ייכנס לקובץ, מה לא, ולמה — מחושב פעם אחת ומשמש גם לתצוגה וגם לקובץ."""

    rows: list[ExportRow] = field(default_factory=list)
    issues: list[ExportIssue] = field(default_factory=list)
    #: מוזמנים שעוד לא אישרו ("טרם השיב" / "אולי") — לא בקובץ.
    not_confirmed: int = 0
    #: מוזמנים שביטלו — לא בקובץ.
    declined: int = 0

    @property
    def total_seats(self) -> int:
        return sum(r.seats for r in self.rows)


def format_phone(raw: str | None) -> tuple[str, str] | None:
    """(סלולרי, טלפון רגיל) בפורמט של התבנית — או None אם המספר חסר/לא תקין.

    נייד (05X, 10 ספרות) → "050-1234567" בעמודת הסלולרי. כל מספר תקין אחר
    (קווי 0X בן 9 ספרות, או 07X בן 10) → "03-1234567" / "077-1234567"
    בעמודת הטלפון הרגיל. אותו כלל תקינות כמו השליחה (``normalize_israeli_phone``).
    """
    if not (raw or "").strip():
        return None
    try:
        digits = normalize_israeli_phone(raw)
    except ValueError:
        return None
    if len(digits) == 10:
        formatted = f"{digits[:3]}-{digits[3:]}"
        return (formatted, "") if digits.startswith("05") else ("", formatted)
    return ("", f"{digits[:2]}-{digits[2:]}")


def _side_label(side: str, terms) -> str:
    # "משותף" אינו ערך בתבנית (רק חתן/כלה) — משאירים ריק.
    if side == "groom":
        return terms.side_groom
    if side == "bride":
        return terms.side_bride
    return ""


def _group_label(group_type: str, terms) -> str:
    # קבוצה מוכרת → השם העברי שלה; קבוצה שהמשתמש יצר נשמרת כטקסט עצמו.
    labels = dict(terms.group_options)
    key = (group_type or "").strip()
    return labels.get(key, key)


def build_plan(event: models.Event, guests: list[models.Guest]) -> ExportPlan:
    """מסווג את המוזמנים: מי נכנס, עם אילו ערכים, ואילו בעיות יש בנתונים."""
    terms = get_event_terms(event.event_type)
    plan = ExportPlan()
    for g in sorted(guests, key=lambda g: ((g.full_name or "").strip(), g.id)):
        if g.rsvp_status == "declined":
            plan.declined += 1
            continue
        if g.rsvp_status != "confirmed":
            plan.not_confirmed += 1
            continue

        name = (g.full_name or "").strip()
        seats = g.effective_seats
        if not name:
            plan.issues.append(ExportIssue(g.id, "", "missing_name", excluded=True))
            continue
        if seats <= 0:
            plan.issues.append(ExportIssue(g.id, name, "zero_seats", excluded=True))
            continue

        phone = format_phone(g.phone)
        if phone is None:
            plan.issues.append(ExportIssue(g.id, name, "bad_phone", excluded=False))
            phone = ("", "")

        plan.rows.append(ExportRow(
            guest_id=g.id,
            name=name,
            seats=seats,
            side=_side_label(g.side, terms),
            group=_group_label(g.group_type, terms),
            mobile=phone[0],
            landline=phone[1],
        ))
    return plan


def _styles():
    """סגנונות התבנית: כותרת כחולה-כהה עם טקסט לבן (Arial 12), נתונים Arial 10."""
    header = xlwt.easyxf(
        "font: name Arial, height 240, colour white;"
        "pattern: pattern solid, fore_colour dark_blue_ega;"
        "borders: left thin, right thin, top thin, bottom thin;"
        "align: horiz center, vert center;",
        num_format_str="@",
    )
    text = xlwt.easyxf(
        "font: name Arial, height 200;"
        "borders: left thin, right thin, top thin, bottom thin;"
        "align: horiz right, vert center;",
        num_format_str="@",
    )
    number = xlwt.easyxf(
        "font: name Arial, height 200;"
        "borders: left thin, right thin, top thin, bottom thin;"
        "align: horiz right, vert center;",
        num_format_str="0",
    )
    return header, text, number


def build_workbook(plan: ExportPlan) -> bytes:
    """בונה את קובץ ה-``.xls`` לפי מבנה התבנית ומחזיר אותו כבייטים."""
    if len(plan.rows) > MAX_ROWS:
        raise ValueError("too many rows for .xls")

    wb = xlwt.Workbook(encoding="utf-8")
    # הכחול של התבנית (51,51,153) — מחליף את הגוון שבפלטה הסטנדרטית.
    wb.set_colour_RGB(xlwt.Style.colour_map["dark_blue_ega"], 51, 51, 153)
    ws = wb.add_sheet(SHEET_NAME)
    ws.cols_right_to_left = True

    header, text, number = _styles()

    for idx, width in enumerate(_COLUMN_WIDTHS):
        ws.col(idx).width = width

    # שורה 1 — כותרות-העל. תאים שלא בתוך מיזוג מקבלים את אותו רקע, כמו בתבנית.
    merged_cols = set()
    for label, first, last in GROUP_HEADERS:
        ws.write_merge(0, 0, first, last, label, header)
        merged_cols.update(range(first, last + 1))
    for col in range(len(COLUMNS)):
        if col not in merged_cols:
            ws.write(0, col, "", header)

    # שורה 2 — כותרות העמודות.
    for col, label in enumerate(COLUMNS):
        ws.write(1, col, label, header)
    for r in (0, 1):
        ws.row(r).height_mismatch = True
        ws.row(r).height = _HEADER_ROW_HEIGHT

    # משורה 3 — הנתונים. כל ערך טקסט נכתב כתא טקסט (לא נוסחה), כך ששם שמתחיל
    # ב-"=" נשאר שם. עמודות שאין להן מקור ב-VEYA נשארות ריקות אך ממוסגרות.
    for i, row in enumerate(plan.rows, start=2):
        values = [
            row.name, row.seats, row.side, row.group, row.mobile, row.landline,
            "", "", "", "", "", None,
        ]
        for col, value in enumerate(values):
            if col in (1, 11):
                ws.write(i, col, value if value is not None else "", number)
            else:
                ws.write(i, col, value, text)
        ws.row(i).height_mismatch = True
        ws.row(i).height = _DATA_ROW_HEIGHT

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def export_filename(event: models.Event) -> str:
    """``VEYA_iPlan_<שם האירוע>.xls`` — השם שמוצג למשתמש בהורדה."""
    name = hosts_names(event.event_type, event.groom_name, event.bride_name)
    name = _UNSAFE_FILENAME.sub(" ", name).strip() or "event"
    name = re.sub(r"\s+", "_", name)[:60]
    return f"VEYA_iPlan_{name}.xls"
