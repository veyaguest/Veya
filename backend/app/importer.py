"""ייבוא מוזמנים מקובץ Excel/CSV: קריאה, זיהוי עמודות חכם וולידציה.

זיהוי העמודות מבוסס על מילות-מפתח בכותרות (עברית/אנגלית), כדי לתמוך
בקבצים שהמשתמשים מביאים בפורמטים שונים.
"""
import csv
import io
from typing import Optional

from openpyxl import load_workbook

from app.validators import normalize_israeli_phone

# מילות מפתח לזיהוי כל עמודה (בכותרת). הבדיקה: האם הכותרת מכילה אחת מהן.
COLUMN_KEYWORDS = {
    "full_name": ["שם מלא", "שם", "name", "מוזמן"],
    "phone": ["טלפון", "נייד", "פלאפון", "פלאפו", "phone", "mobile", "טל"],
    "side": ["צד", "side"],
    "group_type": ["קבוצה", "קבוצת", "group", "שיוך"],
    "party_size": ["כמות", "אנשים", "מוזמנים", "size", "count"],
    "notes_raw": ["הערה", "הערות", "notes", "מגבל"],
}

SIDE_VALUE_MAP = {
    "חתן": "groom",
    "groom": "groom",
    "כלה": "bride",
    "bride": "bride",
    "משותף": "shared",
    "שני": "shared",
    "shared": "shared",
}

GROUP_VALUE_MAP = {
    "משפחה קרובה": "close_family",
    "קרובה": "close_family",
    "משפחה רחוקה": "extended_family",
    "רחוקה": "extended_family",
    "חברים": "friends",
    "חבר": "friends",
    "עבודה": "work",
    "work": "work",
}


def parse_file(filename: str, content: bytes) -> tuple[list[str], list[list]]:
    """מחזיר (כותרות, שורות) מקובץ CSV או XLSX."""
    name = (filename or "").lower()
    if name.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        reader = list(csv.reader(io.StringIO(text)))
        if not reader:
            return [], []
        headers = [str(h).strip() for h in reader[0]]
        rows = [list(r) for r in reader[1:]]
        return headers, rows
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.active
        all_rows = list(ws.iter_rows(values_only=True))
        wb.close()
        if not all_rows:
            return [], []
        headers = [str(h).strip() if h is not None else "" for h in all_rows[0]]
        rows = [list(r) for r in all_rows[1:]]
        return headers, rows
    raise ValueError("פורמט קובץ לא נתמך. נא להעלות קובץ .xlsx או .csv")


def detect_columns(headers: list[str]) -> dict:
    """ממפה שדה -> אינדקס עמודה, לפי מילות מפתח בכותרת.

    עובד לפי סדר עדיפויות (השדות ב-COLUMN_KEYWORDS), ומוודא שכל עמודה
    משויכת לכל היותר לשדה אחד — כדי למנוע התנגשויות (למשל "מספר טלפון"
    שמכיל גם 'טלפון' וגם מספר).
    """
    mapping: dict[str, Optional[int]] = {field: None for field in COLUMN_KEYWORDS}
    used: set[int] = set()
    for field, keywords in COLUMN_KEYWORDS.items():
        for idx, header in enumerate(headers):
            if idx in used:
                continue
            h = (header or "").strip().lower()
            if not h:
                continue
            if any(kw.lower() in h for kw in keywords):
                mapping[field] = idx
                used.add(idx)
                break
    return mapping


def _cell(row: list, idx: Optional[int]) -> str:
    if idx is None or idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


def _map_side(raw: str) -> str:
    key = raw.strip().lower()
    for text, value in SIDE_VALUE_MAP.items():
        if text.lower() in key:
            return value
    return "shared"


def _map_group(raw: str) -> str:
    key = raw.strip().lower()
    for text, value in GROUP_VALUE_MAP.items():
        if text.lower() in key:
            return value
    return "other"


def build_preview(headers: list[str], rows: list[list], mapping: dict) -> dict:
    """מייצר תצוגה מקדימה עם ולידציה לכל שורה."""
    preview_rows = []
    valid_count = 0

    for i, row in enumerate(rows):
        # מדלגים על שורות ריקות לגמרי
        if not any(str(c).strip() for c in row if c is not None):
            continue

        full_name = _cell(row, mapping.get("full_name"))
        phone_raw = _cell(row, mapping.get("phone"))
        side = _map_side(_cell(row, mapping.get("side")))
        group_type = _map_group(_cell(row, mapping.get("group_type")))
        notes_raw = _cell(row, mapping.get("notes_raw")) or None

        party_raw = _cell(row, mapping.get("party_size"))
        try:
            party_size = int(float(party_raw)) if party_raw else 1
            if party_size < 1:
                party_size = 1
        except ValueError:
            party_size = 1

        errors = []
        if not full_name:
            errors.append("חסר שם")

        phone = phone_raw
        try:
            phone = normalize_israeli_phone(phone_raw)
        except ValueError:
            errors.append("טלפון לא תקין")

        is_valid = len(errors) == 0
        if is_valid:
            valid_count += 1

        preview_rows.append(
            {
                "row_number": i + 2,  # +2: שורה 1 = כותרות, אינדקס מ-0
                "full_name": full_name,
                "phone": phone,
                "side": side,
                "group_type": group_type,
                "party_size": party_size,
                "notes_raw": notes_raw,
                "valid": is_valid,
                "errors": errors,
            }
        )

    return {
        "detected_columns": {
            field: (headers[idx] if idx is not None and idx < len(headers) else None)
            for field, idx in mapping.items()
        },
        "rows": preview_rows,
        "total": len(preview_rows),
        "valid_count": valid_count,
        "invalid_count": len(preview_rows) - valid_count,
    }
