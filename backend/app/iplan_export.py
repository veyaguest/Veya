"""ייצוא רשימת המוזמנים לפורמט של אייפלן (iPlan) — להושבה באולמות שעובדים איתו.

שכבת התאמה בלבד: קוראת את המוזמנים כפי שהם ב-VEYA ומתרגמת אותם למבנה של
אייפלן. **לא משנה שום נתון**, ולא מחשבת כמויות מחדש.

מקור הפורמט — שני קבצים אמיתיים של אייפלן:

1. תבנית הייבוא הריקה (``tests/fixtures/iplan_template.xls``) — 12 עמודות.
2. קובץ אייפלן של אירוע חי, אחרי אישורי הגעה והושבה (נמסר ע"י הבעלים
   2026-09-28; לא נשמר בקוד כי יש בו פרטי מוזמנים אמיתיים). **זה המבנה
   שאנחנו מייצאים**, כי כך הקובץ צריך להיראות גם אחרי אישור הגעה והושבה:

- Excel 97–2003 (``.xls``, BIFF8) — לכן ``xlwt``. גיליון יחיד ``הזמנות``, RTL.
- שורה 1: כותרות-על ממוזגות (שיוך / פרטי התקשרות / כתובת).
- שורה 2: 16 כותרות (``COLUMNS``). עמודה L ("צ'ק צפוי" בתבנית) — כותרת ריקה.
- משורה 3: שורה לכל הזמנה — **כל** המוזמנים, לא רק מי שאישר:
  - "מס' אורחים שהוזמנו" = ``party_size``.
  - "אישרו שיגיעו" = ``Guest.effective_seats`` למי שאישר; 0 למי שלא מגיע
    או מתלבט; ריק למי שעוד לא ענה.
  - "מתלבטים" = ``party_size`` למי שסימן "אולי" (ב-VEYA אין כמות נפרדת
    למתלבטים); ריק לכל השאר.
  - "מספר שולחן" = ``table_number`` כטקסט — רק למי שאישר ותופס מקום
    (``effective_seats > 0``), כמו באייפלן. מוזמן שנשאר משובץ אחרי שביטל
    לא נספר בהושבה, ולכן גם לא מופיע כאן על שולחן.
  - "הגיעו" — ריק (נמדד ביום האירוע, לא ב-VEYA).
- טלפון כטקסט בפורמט "054-216-3535"; צד משותף = "חתן וכלה" (לפי מונחי הסוג).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Optional

import xlwt

from app import models
from app.event_terms import get_event_terms, hosts_names
from app.validators import normalize_israeli_phone

SHEET_NAME = "הזמנות"

# 16 העמודות — שמות וסדר זהים לקובץ של אייפלן. אין להוסיף/לשנות סדר.
COLUMNS = [
    "הזמנה לכבוד",          # A
    "מס' אורחים שהוזמנו",   # B
    "צד",                   # C
    "קבוצה",                # D
    "סלולרי",               # E
    "טלפון רגיל",           # F
    "אימייל",               # G
    "עיר",                  # H
    "רחוב",                 # I
    "מיקוד",                # J
    "תא דואר",              # K
    "",                     # L — "צ'ק צפוי" בתבנית; בקובץ החי הכותרת ריקה
    "אישרו שיגיעו",         # M
    "מתלבטים",              # N
    "מספר שולחן",           # O
    "הגיעו",                # P
]

# כותרות-העל הממוזגות בשורה 1: (טקסט, עמודה ראשונה, עמודה אחרונה).
GROUP_HEADERS = [
    ("שיוך", 2, 3),
    ("פרטי התקשרות", 4, 6),
    ("כתובת", 7, 10),
]

# רוחב העמודות ומידות השורות מהקובץ של אייפלן. ויזואלי בלבד, אבל זול לשמר.
_COLUMN_WIDTHS = [8106, 5674, 2346, 2773, 4608, 3242, 7722, 2432,
                  3200, 2517, 2688, 2688, 3456, 3072, 3712, 3840]
_HEADER_ROW_HEIGHT = 380
_DATA_ROW_HEIGHT = 242

_NUMBER_COLUMNS = {1, 12, 13}

# ``xlwt`` כותב BIFF8 שמוגבל ל-65,536 שורות. גבול תיאורטי בלבד לאירוע.
MAX_ROWS = 65_536 - 2


@dataclass
class ExportIssue:
    """בעיה בנתונים שהמשתמש צריך לדעת עליה לפני ההורדה."""

    guest_id: int
    full_name: str
    kind: str  # missing_name / bad_phone
    #: True — המוזמן לא נכנס לקובץ. False — נכנס, אבל שדה אחד נשאר ריק.
    excluded: bool


@dataclass
class ExportRow:
    guest_id: int
    name: str
    invited: int
    side: str
    group: str
    mobile: str
    landline: str
    confirmed: Optional[int]  # None = עוד לא ענה
    maybe: Optional[int]
    table: str


@dataclass
class ExportPlan:
    """מה ייכנס לקובץ ומה חסר — מחושב פעם אחת ומשמש גם לתצוגה וגם לקובץ."""

    rows: list[ExportRow] = field(default_factory=list)
    issues: list[ExportIssue] = field(default_factory=list)
    confirmed: int = 0  # הזמנות שאישרו
    pending: int = 0    # עוד לא ענו
    maybe: int = 0      # מתלבטים
    declined: int = 0   # לא מגיעים
    seated: int = 0     # הזמנות שאישרו ויש להן שולחן

    @property
    def invited_people(self) -> int:
        return sum(r.invited for r in self.rows)

    @property
    def confirmed_people(self) -> int:
        return sum(r.confirmed or 0 for r in self.rows)


def format_phone(raw: str | None) -> tuple[str, str] | None:
    """(סלולרי, טלפון רגיל) בפורמט של אייפלן — או None אם המספר חסר/לא תקין.

    נייד (05X, 10 ספרות) → "054-216-3535" בעמודת הסלולרי. כל מספר תקין אחר
    (קווי 0X בן 9 ספרות, או 07X בן 10) → "03-123-4567" / "077-123-4567"
    בעמודת הטלפון הרגיל. אותו כלל תקינות כמו השליחה (``normalize_israeli_phone``).
    """
    if not (raw or "").strip():
        return None
    try:
        digits = normalize_israeli_phone(raw)
    except ValueError:
        return None
    prefix = 3 if len(digits) == 10 else 2
    formatted = f"{digits[:prefix]}-{digits[prefix:prefix + 3]}-{digits[prefix + 3:]}"
    return (formatted, "") if digits.startswith("05") else ("", formatted)


def _side_label(side: str, terms) -> str:
    if side == "groom":
        return terms.side_groom
    if side == "bride":
        return terms.side_bride
    # צד משותף — כמו באייפלן ("חתן וכלה"), במונחי סוג האירוע.
    return f"{terms.side_groom} ו{terms.side_bride}"


def _group_label(group_type: str, terms) -> str:
    # קבוצה מוכרת → השם העברי שלה; קבוצה שהמשתמש יצר נשמרת כטקסט עצמו.
    labels = dict(terms.group_options)
    key = (group_type or "").strip()
    return labels.get(key, key)


def build_plan(event: models.Event, guests: list[models.Guest]) -> ExportPlan:
    """מתרגם את המוזמנים לשורות אייפלן ומאתר בעיות בנתונים."""
    terms = get_event_terms(event.event_type)
    plan = ExportPlan()
    for g in sorted(guests, key=lambda g: ((g.full_name or "").strip(), g.id)):
        name = (g.full_name or "").strip()
        if not name:
            plan.issues.append(ExportIssue(g.id, "", "missing_name", excluded=True))
            continue

        seats = g.effective_seats
        confirmed: Optional[int] = None
        maybe: Optional[int] = None
        if g.rsvp_status == "confirmed":
            plan.confirmed += 1
            confirmed = seats
        elif g.rsvp_status == "declined":
            plan.declined += 1
            confirmed = 0
        elif g.rsvp_status == "maybe":
            plan.maybe += 1
            confirmed = 0
            maybe = g.party_size
        else:
            plan.pending += 1

        table = ""
        if seats > 0 and g.table_number is not None:
            table = str(g.table_number)
            plan.seated += 1

        phone = format_phone(g.phone)
        if phone is None:
            plan.issues.append(ExportIssue(g.id, name, "bad_phone", excluded=False))
            phone = ("", "")

        plan.rows.append(ExportRow(
            guest_id=g.id,
            name=name,
            invited=g.party_size,
            side=_side_label(g.side, terms),
            group=_group_label(g.group_type, terms),
            mobile=phone[0],
            landline=phone[1],
            confirmed=confirmed,
            maybe=maybe,
            table=table,
        ))
    return plan


def _styles():
    """סגנונות הקובץ של אייפלן: כותרת כחולה-כהה עם טקסט לבן, נתונים Arial 12."""
    header = xlwt.easyxf(
        "font: name Arial, height 240, colour white;"
        "pattern: pattern solid, fore_colour dark_blue_ega;"
        "borders: left thin, right thin, top thin, bottom thin;"
        "align: horiz center, vert center;",
        num_format_str="@",
    )
    text = xlwt.easyxf("font: name Arial, height 240; align: vert center;", num_format_str="@")
    number = xlwt.easyxf("font: name Arial, height 240; align: vert center;")
    return header, text, number


def build_workbook(plan: ExportPlan) -> bytes:
    """בונה את קובץ ה-``.xls`` במבנה של אייפלן ומחזיר אותו כבייטים."""
    if len(plan.rows) > MAX_ROWS:
        raise ValueError("too many rows for .xls")

    wb = xlwt.Workbook(encoding="utf-8")
    # הכחול של אייפלן (51,51,153) — מחליף את הגוון שבפלטה הסטנדרטית.
    wb.set_colour_RGB(xlwt.Style.colour_map["dark_blue_ega"], 51, 51, 153)
    ws = wb.add_sheet(SHEET_NAME)
    ws.cols_right_to_left = True

    header, text, number = _styles()

    for idx, width in enumerate(_COLUMN_WIDTHS):
        ws.col(idx).width = width

    # שורה 1 — כותרות-העל. שאר התאים בשורה מקבלים את אותו רקע, כמו אצלם.
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

    # משורה 3 — הנתונים. טקסט נכתב כתא טקסט (לא נוסחה), כך ששם שמתחיל ב-"="
    # נשאר שם. ערך None = תא ריק (למשל "אישרו שיגיעו" למי שעוד לא ענה).
    for i, row in enumerate(plan.rows, start=2):
        values = [
            row.name, row.invited, row.side, row.group, row.mobile, row.landline,
            "", "", "", "", "", "",
            row.confirmed, row.maybe, row.table, "",
        ]
        for col, value in enumerate(values):
            if value is None or value == "":
                continue
            ws.write(i, col, value, number if col in _NUMBER_COLUMNS else text)
        ws.row(i).height_mismatch = True
        ws.row(i).height = _DATA_ROW_HEIGHT

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def export_filename(event: models.Event) -> str:
    """``<בעלי האירוע> - הזמנות.xls`` — אותו מבנה שם כמו בקובץ ש-iPlan מוציא
    ("נועה מנצור ואביב מנחם - הזמנות.xls"; החלטת בעלים 2026-09-28)."""
    name = hosts_names(event.event_type, event.groom_name, event.bride_name)
    name = re.sub(r"\s+", " ", _UNSAFE_FILENAME.sub(" ", name)).strip()[:60]
    return f"{name} - הזמנות.xls" if name else "הזמנות.xls"
