"""AI Vision — ניתוח סקיצת אולם והצעת אלמנטים (בניית אולם אוטומטית מ-AI).

עקרון-על (ai-guidelines.md, decisions.md): ה-LLM אחראי לפרשנות/הצעה בלבד,
בדיוק כמו פרסור הערות ההושבה (constraints.py). הרשימה שמוחזרת כאן היא הצעה
בלבד — נבדקת ומאושרת ע"י המשתמש במסך Review, ולעולם לא נכתבת ל-Event
ישירות מהמודול הזה. כל אלמנט מאומת מול טווחים/טיפוסים נוקשים לפני שהוא חוזר
ללקוח (_validate_elements) — אין אמון עיוור בפלט המודל.

זו אינטגרציית ה-LLM הראשונה בפרויקט. קריאה ל-Claude Messages API דרך httpx
גולמי (בדיוק כמו MetaProvider ב-messaging.py) — בלי SDK חדש כתלות.
"""
from __future__ import annotations

import base64
import io
import os

from PIL import Image

_ANTHROPIC_MODEL = "claude-opus-5"
_ANTHROPIC_VERSION = "2023-06-01"
_MAX_VISION_DIMENSION = 1568  # יעד עלות/דיוק מומלץ לניתוח Vision

_ELEMENT_TYPES = [
    "round_table", "square_table", "rectangle_table", "knights_table",
    "bar", "dance_floor", "stage", "entrance", "pillar", "wall", "obstacle", "other_area",
]

_TOOL_SCHEMA = {
    "name": "report_hall_elements",
    "description": "דיווח רשימת האלמנטים (שולחנות/אזורים) שזוהו בסקיצת האולם.",
    "input_schema": {
        "type": "object",
        "properties": {
            "elements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": _ELEMENT_TYPES,
                            "description": "round_table=עגול, square_table=ריבועי (width≈height ממש), rectangle_table=מלבני ארוך (width≠height)",
                        },
                        "x": {"type": "number", "description": "מרכז האלמנט, 0-1, יחסית לרוחב התמונה"},
                        "y": {"type": "number", "description": "מרכז האלמנט, 0-1, יחסית לגובה התמונה"},
                        "width": {"type": "number", "description": "רוחב האלמנט כפי שהוא נראה בסקיצה (הציר האופקי של האובייקט, לפני סיבוב), 0-1, יחסית לרוחב התמונה"},
                        "height": {"type": "number", "description": "גובה האלמנט כפי שהוא נראה בסקיצה (הציר האנכי של האובייקט, לפני סיבוב), 0-1, יחסית לגובה התמונה"},
                        "rotation": {"type": "number", "description": "זווית הסיבוב של האובייקט במעלות, לפי הכיוון הנראה בפועל בסקיצה — 0 אם האובייקט ניצב ישר (לא מוטה), חובה לתת ערך תמיד (0 אם אין סיבוב)"},
                        "capacity": {"type": "integer", "description": "מספר מקומות, רק לשולחנות, אם ניתן להסיק בבירור"},
                        "table_number": {
                            "type": "integer",
                            "description": "מספר השולחן **כפי שהוא כתוב בסקיצה עצמה** (בתוך השולחן או צמוד לו), רק לשולחנות. השמט את השדה לגמרי אם אין מספר כתוב או שאינך קורא אותו בוודאות — אל תנחש ואל תמציא מספר סידורי משלך",
                        },
                        "confidence": {"type": "number", "description": "0 עד 1 — עד כמה בטוח הזיהוי"},
                        "label": {"type": "string", "description": "תיאור קצר אופציונלי"},
                    },
                    "required": ["type", "x", "y", "width", "height", "rotation", "confidence"],
                },
            },
        },
        "required": ["elements"],
    },
}

_SYSTEM_PROMPT = """אתה מנתח סקיצות/שרטוטים של אולמות אירועים. המטרה: לזהות שולחנות \
ואזורים פונקציונליים כדי לבנות מפת הושבה דיגיטלית אוטומטית.

זהה רק אובייקטים שרלוונטיים לסידור הושבה: שולחנות (עגול/ריבועי/מלבני/אבירים), \
בר, רחבת ריקודים, במה, כניסה, עמודים, מכשולים משמעותיים, מחיצות/קירות. \
אל תהפוך כל פרט קטן בסקיצה לאובייקט — התמקד באובייקטים שימושיים בלבד.

חשוב להבדיל נכון בין שולחן ריבועי (square_table, width≈height) לבין שולחן \
מלבני ארוך (rectangle_table, width שונה משמעותית מ-height) — אל תסווג שולחן \
ריבועי כמלבני רק כי הוא לא עגול.

לכל אובייקט תן קואורדינטות מנורמלות [0,1] של המרכז (x,y) וגודל (width,height) \
יחסית למידות התמונה כולה, וכן confidence כן ואמיתי (לא תמיד גבוה) — 0.9+ רק \
כשאתה בטוח מאוד, נמוך יותר כשיש עמימות. אל תמציא ודאות שאין לך.

תן rotation אמיתי לפי הכיוון הנראה של כל אובייקט בסקיצה (0 אם הוא ניצב ישר, \
ללא הטיה) — אל תשאיר rotation ריק, ואל תניח שכל השולחנות המלבניים באותו כיוון: \
שולחן אחד יכול להיות אופקי ואחר אנכי או מוטה, גם באותה סקיצה.

אם בסקיצה כתובים מספרי שולחנות (בתוך השולחן, לידו, או בתווית קטנה) — קרא כל \
מספר ודווח אותו ב-table_number של אותו שולחן בדיוק. זהו המספר של המשתמש והוא \
מנצח כל מספור אחר. שני כללים נוקשים: (1) שייך כל מספר לשולחן הקרוב אליו ממש, \
לא לשולחן שכן; (2) אם אין מספר כתוב, או שהוא מטושטש/חתוך/לא ברור — השמט את \
table_number לגמרי. עדיף בלי מספר מאשר מספר שגוי, ואל תמציא מספור סידורי משלך \
לפי סדר הסריקה שלך.

דווח דרך הכלי report_hall_elements בלבד."""


class HallVisionError(Exception):
    """כשל בניתוח AI — הראוטר הופך אותה ל-HTTPException עם הודעה בעברית, לא 500 גולמי."""


def _downscale_image(raw: bytes) -> bytes:
    try:
        img = Image.open(io.BytesIO(raw))
        img = img.convert("RGB")
        if max(img.size) > _MAX_VISION_DIMENSION:
            img.thumbnail((_MAX_VISION_DIMENSION, _MAX_VISION_DIMENSION), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()
    except Exception as exc:
        raise HallVisionError("קובץ התמונה פגום או בפורמט לא נתמך") from exc


def analyze_sketch(raw: bytes, content_type: str) -> list[dict]:
    """שולח את הסקיצה ל-Claude Vision ומחזיר רשימת אלמנטים מוצעים (תצוגה מקדימה בלבד).

    ``content_type`` — image/* או application/pdf. PDF נשלח כ-document block ישירות
    ל-Claude (תומך בפורמט הזה מובנה) — בלי המרה מקומית. בקובץ מרובה-עמודים
    מנותח רק העמוד הראשון (מגבלה ידועה).
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HallVisionError("ניתוח AI אינו מוגדר בשרת (חסר מפתח API)")

    if content_type == "application/pdf":
        block = {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(raw).decode()},
        }
    else:
        optimized = _downscale_image(raw)
        block = {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(optimized).decode()},
        }

    payload = {
        "model": _ANTHROPIC_MODEL,
        "max_tokens": 4096,
        "system": _SYSTEM_PROMPT,
        # חשיבה כבויה בכוונה: קריאה יחידה למבנה קבוע (forced tool_choice), לא
        # משימת נימוק פתוחה — וזה גם מה שמאפשר לוודא שהתשובה תמיד tool_use אחד.
        "thinking": {"type": "disabled"},
        "tools": [_TOOL_SCHEMA],
        "tool_choice": {"type": "tool", "name": "report_hall_elements"},
        "messages": [
            {
                "role": "user",
                "content": [
                    block,
                    {"type": "text", "text": "נתח את סקיצת האולם המצורפת וזהה את האלמנטים לפי ההנחיות."},
                ],
            }
        ],
    }

    try:
        import httpx  # נטען רק כשצריך — תואם לדפוס MetaProvider ב-messaging.py

        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            json=payload,
            headers={
                "x-api-key": api_key,
                "anthropic-version": _ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            timeout=60.0,
        )
    except Exception as exc:
        raise HallVisionError("לא הצלחנו להתחבר לשירות הניתוח — נסו שוב") from exc

    if resp.status_code != 200:
        raise HallVisionError(f"שירות הניתוח החזיר שגיאה ({resp.status_code}) — נסו שוב")

    data = resp.json()
    if data.get("stop_reason") == "refusal":
        raise HallVisionError("לא הצלחנו לנתח את הסקיצה הזו — נסו תמונה אחרת")

    tool_input: dict | None = None
    for content_block in data.get("content", []):
        if content_block.get("type") == "tool_use" and content_block.get("name") == "report_hall_elements":
            tool_input = content_block.get("input")
            break
    if tool_input is None:
        raise HallVisionError("הניתוח לא החזיר תוצאה תקינה — נסו שוב")

    return _validate_elements(tool_input.get("elements") or [])


def _clean_table_number(raw, etype: str) -> int | None:
    """מספר שולחן שהמודל קרא מהסקיצה — או None.

    זה מספר שהמשתמש כתב בעצמו בסקיצה, ולכן הוא מנצח את המספור המרחבי בצד
    הלקוח (ראה assignTableNumbers). בדיוק בגלל זה הסינון כאן קפדני: רק
    שולחנות, רק שלם בטווח סביר. כל דבר אחר → None ("אין מספר"), כי בלי מספר
    יש fallback דטרמיניסטי, ואילו מספר שגוי היה מדביק תווית לא נכונה לשולחן.
    """
    if not etype.endswith("_table") or raw is None:
        return None
    try:
        num = int(raw)
    except (TypeError, ValueError):
        return None
    return num if 1 <= num <= 999 else None


def _validate_elements(raw_elements: list) -> list[dict]:
    """מוודא שכל אלמנט תקין (טווחים/טיפוס) לפני שהוא חוזר ללקוח — לא סומכים עיוורות על המודל."""
    out: list[dict] = []
    for el in raw_elements:
        if not isinstance(el, dict):
            continue
        try:
            etype = str(el["type"])
            if etype not in _ELEMENT_TYPES:
                continue
            x, y = float(el["x"]), float(el["y"])
            w, h = float(el["width"]), float(el["height"])
            conf = float(el.get("confidence", 0.5))
            if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1 and 0 <= conf <= 1):
                continue
            out.append({
                "type": etype,
                "x": x, "y": y, "width": w, "height": h,
                "rotation": float(el.get("rotation") or 0),
                "capacity": int(el["capacity"]) if el.get("capacity") else None,
                "table_number": _clean_table_number(el.get("table_number"), etype),
                "confidence": conf,
                "label": str(el.get("label") or ""),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return out
