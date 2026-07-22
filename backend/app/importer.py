"""ייבוא מוזמנים מקובץ Excel/CSV: קריאה, זיהוי עמודות חכם וולידציה.

זיהוי העמודות מבוסס על מילות-מפתח בכותרות (עברית/אנגלית), כדי לתמוך
בקבצים שהמשתמשים מביאים בפורמטים שונים.

בנוסף, `parse_freeform_text` מפענח רשימת טקסט חופשי (הדבקה מ-WhatsApp/אקסל/
כל מקום) שורה-שורה: מזהה טלפון, כמות אנשים, רמז "משפחת…", ומשאיר את השם.
הפענוח דטרמיניסטי לגמרי (regex/היוריסטיקה) — אין קריאות LLM.
"""
import csv
import io
import re
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
    # ערכי "צד" לחתונה/חינה (חתן/כלה) ולסוגי אירוע אחרים (אב/אם, א׳/ב׳) —
    # פנימית כולם נשמרים כ-groom/bride/shared, והתווית המוצגת נשאבת מ-
    # eventTypes.ts לפי event_type (ראה sideLabel/sidePhrase).
    "חתן": "groom",
    "groom": "groom",
    "אב": "groom",
    "א׳": "groom",
    "כלה": "bride",
    "bride": "bride",
    "אמא": "bride",
    "אם": "bride",
    "ב׳": "bride",
    "משותף": "shared",
    "שני": "shared",
    "shared": "shared",
}

GROUP_VALUE_MAP = {
    # חתונה/חינה — קטגוריות ספציפיות קודם, כדי שלא "יבלעו" ע"י ההתאמה הכללית
    # של "משפחה"/"אב"/"אם" למטה (הראשון שמתאים בסדר האיטרציה מנצח).
    "משפחה קרובה": "close_family",
    "קרובה": "close_family",
    "משפחה רחוקה": "extended_family",
    "רחוקה": "extended_family",
    "חברים": "friends",
    "חבר": "friends",
    "עבודה": "work",
    "work": "work",
    "צבא": "army",
    "לימודים": "studies",
    "ילדות": "childhood",
    "שכנים": "neighbors",
    # בר/בת מצווה
    "משפחת האב": "family_father",
    "משפחת אב": "family_father",
    "משפחת האם": "family_mother",
    "משפחת אם": "family_mother",
    "כיתה": "class",
    "חוגים": "staff_clubs",
    "צוות": "staff_clubs",
    # אב/אם עצמאיים (אחרי הצירופים הארוכים למעלה) — "אב"/"אבא" ו"אם"/"אמא"
    "אבא": "family_father",
    "אב": "family_father",
    "אמא": "family_mother",
    "אם": "family_mother",
    # ברית/משפחתי/חינה — כללי, אחרי כל הצירופים הספציפיים למעלה
    "משפחה": "family",
    # אירוע עסקי
    "עובדים": "employees",
    "עובד": "employees",
    "לקוחות": "clients",
    "לקוח": "clients",
    "ספקים": "suppliers",
    "ספק": "suppliers",
    "הנהלה": "management",
    "מנהל": "management",
    "שותפים": "partners",
    "שותף": "partners",
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


# ---------------------------------------------------------------------------
# פענוח טקסט חופשי (הדבקת רשימה מ-WhatsApp / אקסל / כל מקור)
# ---------------------------------------------------------------------------

# רצף שנראה כמו טלפון ישראלי: מתחיל ב-0 (מקומי) או +972/972 (בינ"ל), ואז
# ספרות/רווחים/מקפים, ומסתיים בספרה. העיגון ל-0/972 מונע תפיסה בטעות של מספרי
# כמות ("x2", "5 אנשים") שנמצאים לפני הטלפון באותה שורה.
_PHONE_RE = re.compile(r"(?:\+?972|0)[\d\s\-]{7,}\d")

# כמות מפורשת: "5 אנשים", "5 מוזמנים", "5 נפשות", "5 איש/אורחים"
_COUNT_WORD_RE = re.compile(r"(\d+)\s*(?:אנשים|מוזמנים|נפשות|איש|אורחים)")
# כמות בסוגריים: "(5)" או "[5]"
_COUNT_PAREN_RE = re.compile(r"[\(\[]\s*(\d+)\s*[\)\]]")
# כמות עם x/×/*: "x5", "X 5", "*5"
_COUNT_X_RE = re.compile(r"(?:^|\s)[xX*×]\s*(\d+)\b")
# מספר בודד בקצה השורה (אחרי שהוסר הטלפון): "דנה 2"
_COUNT_TRAIL_RE = re.compile(r"(?:^|\s)(\d+)\s*$")

# רמז "משפחת …" / "משפחה של …" → קבוצת משפחה קרובה + כמות ברירת מחדל ≥ 2
_FAMILY_RE = re.compile(r"^\s*משפח[הת]\b")


def _clean_name(text: str) -> str:
    """מנקה מהשם שאריות מפרידים (מקפים/פסיקים/נקודתיים) ורווחים כפולים."""
    text = re.sub(r"[\-–—,:;|]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -–—,:;|\t")


def parse_freeform_text(text: str, existing_keys: Optional[set] = None) -> dict:
    """מפענח רשימת טקסט חופשי לשורות מוזמנים — מבנה זהה ל-`build_preview`.

    לכל שורה לא-ריקה: מזהה טלפון ומסירו, מזהה כמות אנשים ומסירה, מזהה רמז
    "משפחת…", ומשאיר את השם. ולידציה רכה: `errors` חוסמים (חסר שם) לעומת
    `warnings` שלא חוסמים (חסר טלפון / טלפון לא תקין / כפילות). `duplicate`
    מסומן מול הרשימה המודבקת עצמה וגם מול מוזמני האירוע (`existing_keys`).
    """
    existing_keys = existing_keys or set()
    preview_rows = []
    valid_count = 0
    seen_keys: set[str] = set()
    row_no = 0

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        row_no += 1
        working = line

        # 1) טלפון — מזהים, מנרמלים, ומסירים מהשורה
        phone = ""
        phone_warn: Optional[str] = None
        m = _PHONE_RE.search(working)
        if m:
            candidate = m.group(0)
            working = working[: m.start()] + " " + working[m.end():]
            try:
                phone = normalize_israeli_phone(candidate)
            except ValueError:
                phone_warn = "טלפון לא תקין"

        # 2) כמות — סורקים לפי סדר עדיפויות ומסירים מהשורה
        party_size: Optional[int] = None
        for rx in (_COUNT_WORD_RE, _COUNT_PAREN_RE, _COUNT_X_RE):
            cm = rx.search(working)
            if cm:
                party_size = int(cm.group(1))
                working = working[: cm.start()] + " " + working[cm.end():]
                break
        if party_size is None:
            cm = _COUNT_TRAIL_RE.search(working)
            if cm:
                party_size = int(cm.group(1))
                working = working[: cm.start()] + " " + working[cm.end():]

        # 3) רמז משפחה
        is_family = bool(_FAMILY_RE.search(line))
        group_type = "close_family" if is_family else "other"

        # 4) שם — מה שנשאר
        full_name = _clean_name(working)

        if party_size is None:
            party_size = 2 if is_family else 1
        if party_size < 1:
            party_size = 1

        # ולידציה רכה
        errors: list[str] = []
        warnings: list[str] = []
        if not full_name:
            errors.append("חסר שם")
        if phone_warn:
            warnings.append(phone_warn)
        elif not phone:
            warnings.append("חסר טלפון")

        # כפילות — מפתח לפי טלפון (מדויק) או שם (fallback)
        key = phone or (full_name.lower() if full_name else "")
        duplicate = bool(key and (key in seen_keys or key in existing_keys))
        if duplicate:
            warnings.append("כפילות")
        if key:
            seen_keys.add(key)

        is_valid = len(errors) == 0
        if is_valid:
            valid_count += 1

        preview_rows.append(
            {
                "row_number": row_no,
                "full_name": full_name,
                "phone": phone,
                "side": "shared",
                "group_type": group_type,
                "party_size": party_size,
                "notes_raw": None,
                "valid": is_valid,
                "errors": errors,
                "warnings": warnings,
                "duplicate": duplicate,
            }
        )

    return {
        "detected_columns": {},
        "rows": preview_rows,
        "total": len(preview_rows),
        "valid_count": valid_count,
        "invalid_count": len(preview_rows) - valid_count,
    }
