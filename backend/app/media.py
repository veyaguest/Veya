"""אחסון קבוע של תמונות (הזמנה/סקיצת אולם) בתוך מסד הנתונים.

למה: קודם שמרנו את התמונות כקבצים תחת ``backend/uploads/``. הבעיה — הדיסק
של Render (וגם של רוב שירותי הענן החינמיים) הוא **זמני**: בכל אתחול/שינה של
השרת הקבצים נמחקים, בדיוק כמו שקרה עם ה-SQLite הישן. לכן תמונת ההזמנה הייתה
נעלמת. הפתרון: שומרים את בייטים של התמונה בטבלה נפרדת (``media_blobs``) במסד
הנתונים (Postgres) שהוא קבוע, ובשורת האירוע נשמר רק נתיב קצר (``/media/<id>``).
הבייטים נשלפים רק כשמבקשים את ה-URL בפועל (endpoint ``/media/<id>``), כך
ששאילתת האירוע נשארת קלה.

כלל הכתיבה (זהה לקודם, רק היעד השתנה מדיסק ל-DB):
- ערך שהוא ``data:`` (base64) → נשמר כרשומת בלוב חדשה, מוחזר נתיב ``/media/<id>``.
- ערך ריק ("") → מחיקת התמונה (None) + מחיקת הבלוב.
- כל ערך אחר (URL קיים שחזר מקריאה) → אין שינוי, שומרים את מה שכבר יש.

תאימות לאחור: ערכים ישנים בסגנון ``/uploads/<file>`` או ``data:`` עדיין
מטופלים ב-``to_url`` כדי לא לשבור נתונים קיימים.
"""
from __future__ import annotations

import base64
import io
import secrets
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from PIL import Image, ImageOps
from sqlalchemy.orm import Session

from app import cache, models

# תיקיית uploads הישנה — נשמרת רק לתאימות לאחור (הגשת קבצים ישנים שכבר קיימים
# מקומית). כתיבה חדשה כבר לא מגיעה לכאן.
UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads"

_MIME_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/svg+xml": "svg",
}

# תמונת ההזמנה: תקרת גודל קובץ מקור (לפני אופטימיזציה, הגנה כללית מפני קבצי
# ענק) + תקרת גודל תוצאה (אחרי אופטימיזציה — ההגנה שבאמת קובעת מה נשמר) +
# פרמטרי הדחיסה. הצלע הארוכה מוגבלת ל-2500px כדי לשמור על חדות מקסימלית
# לטקסט קטן בהזמנה תוך צמצום משמעותי של גודל הקובץ שנשמר במסד.
#
# הסדר חשוב: בודקים גודל מקור מול תקרה **גבוהה ורפויה** (50MB) רק כדי לחסום
# קבצי ענק לא סבירים — לא כדי לדחות תמונות "גדולות אבל תקינות" לפני שהן קיבלו
# הזדמנות להידחס. תמונת מצלמה מודרנית של 20-30MB אמורה לעבור את הבדיקה הזו,
# להיכנס לעיבוד, ולצאת ממנו כקובץ WebP קטן בהרבה. הבדיקה המשמעותית האמיתית
# היא MAX_OPTIMIZED_BYTES, שרצה **אחרי** העיבוד על מה שבאמת ייכתב למסד.
MAX_SOURCE_BYTES = 50 * 1024 * 1024  # 50MB — תקרת קובץ מקור, לפני עיבוד
MAX_OPTIMIZED_BYTES = 8 * 1024 * 1024  # 8MB — תקרת התוצאה הסופית שנשמרת בפועל
MAX_IMAGE_DIMENSION = 2500
IMAGE_QUALITY = 90

_RASTER_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/bmp", "image/tiff"}


class _ImageProcessingError(Exception):
    """נזרקת כשעיבוד תמונה נכשל בפועל (קובץ פגום/פורמט לא נתמך/כשל קידוד).

    בכוונה **לא** נבלעת בשקט בתוך ``_optimize_image`` — אם העיבוד נכשל, אסור
    לשמור את הבייטים הגולמיים (לא-מעובדים) במקומו, כי הדרישה היא לשמור רק את
    הגרסה האופטימלית. הקריאה ל-``_write_data_url`` היא זו שהופכת את זה
    ל-HTTPException ברור למשתמש.
    """


def _optimize_image(raw: bytes, content_type: str) -> tuple[bytes, str]:
    """מקטין ודוחס תמונה: צלע ארוכה עד 2500px, WebP באיכות 90 (JPEG כגיבוי).

    SVG (וקטורי) נשמר כפי שהוא — אין מה לדחוס בווקטור. GIF (גם מונפש) נשמר
    כפי שהוא — לא כלול ב-``_RASTER_CONTENT_TYPES`` כי עיבוד היה עלול להרוס
    אנימציה. WebP נבחר כברירת מחדל כי כל הדפדפנים המודרניים תומכים בו ונותן
    איכות גבוהה יותר בגודל קטן יותר מ-JPEG; אם הקידוד נכשל, נופלים ל-JPEG.
    כשל אמיתי בפענוח/עיבוד (קובץ פגום, לא ניתן לפתיחה) זורק
    ``_ImageProcessingError`` — לא חוזר בשקט לבייטים המקוריים.
    """
    if content_type not in _RASTER_CONTENT_TYPES:
        return raw, content_type
    try:
        img = Image.open(io.BytesIO(raw))
        if getattr(img, "is_animated", False):
            return raw, content_type
        img = ImageOps.exif_transpose(img)  # מתקן סיבוב שמצלמות טלפון שומרות ב-EXIF
        has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
        img = img.convert("RGBA" if has_alpha else "RGB")
        if max(img.size) > MAX_IMAGE_DIMENSION:
            img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)
    except Exception as exc:
        raise _ImageProcessingError("קובץ התמונה פגום או בפורמט לא נתמך") from exc

    try:
        buf = io.BytesIO()
        img.save(buf, format="WEBP", quality=IMAGE_QUALITY, method=6)
        return buf.getvalue(), "image/webp"
    except Exception:
        pass  # ניפול ל-JPEG למטה

    try:
        if has_alpha:
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=IMAGE_QUALITY, optimize=True)
        return buf.getvalue(), "image/jpeg"
    except Exception as exc:
        raise _ImageProcessingError("שמירת התמונה הדחוסה נכשלה") from exc


def _validate_optimized(raw: bytes, content_type: str) -> None:
    """בודק שהקובץ הסופי (מה שבאמת עומד להישמר במסד) תקין וסביר בגודלו.

    זו ההגנה המשמעותית נגד קבצים חריגים — רצה **אחרי** העיבוד, על התוצאה
    שבאמת נכתבת ל-DB (ולא על קובץ המקור, שיכול להיות גדול אבל ידחס יפה).
    """
    if not raw or len(raw) > MAX_OPTIMIZED_BYTES:
        raise HTTPException(
            status_code=413, detail="התמונה גדולה מדי גם אחרי דחיסה — נסו קובץ אחר"
        )
    if content_type in _RASTER_CONTENT_TYPES:
        try:
            Image.open(io.BytesIO(raw)).load()
        except Exception as exc:
            raise HTTPException(status_code=422, detail="קובץ התמונה פגום — נסו קובץ אחר") from exc


def _parse_data_url(data_url: str) -> tuple[str, bytes]:
    """מפרק data URL ל-(content_type, bytes)."""
    header, _, b64 = data_url.partition(",")
    mime = header[5:].split(";")[0] if header.startswith("data:") else ""
    content_type = mime.lower() if mime else "application/octet-stream"
    raw = base64.b64decode(b64, validate=False)
    return content_type, raw


def _write_data_url(db: Session, data_url: str, prefix: str, optimize: bool = False) -> str:
    """שומר data URL כרשומת בלוב במסד ומחזיר נתיב יחסי (/media/<id>).

    ``optimize=True`` מריץ דחיסה אוטומטית (ראה ``_optimize_image``) לפני
    השמירה — נשמרת רק הגרסה הדחוסה, כדי לא לכפול אחסון עם המקור. סדר הבדיקות
    בכוונה: קודם תקרה רפויה על המקור (50MB, רק נגד קבצי ענק) → עיבוד → ואז
    הבדיקה המשמעותית על התוצאה הסופית (``_validate_optimized``). כך תמונה
    "כבדה אבל תקינה" מקבלת הזדמנות להידחס לפני שנשקל לדחות אותה.
    """
    content_type, raw = _parse_data_url(data_url)
    if len(raw) > MAX_SOURCE_BYTES:
        raise HTTPException(status_code=413, detail="התמונה גדולה מדי — עד 50MB")
    if optimize:
        try:
            raw, content_type = _optimize_image(raw, content_type)
        except _ImageProcessingError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _validate_optimized(raw, content_type)
    blob_id = f"{prefix}-{secrets.token_hex(8)}"
    db.add(models.MediaBlob(id=blob_id, content_type=content_type, data=raw))
    db.flush()  # מוודא שהרשומה נכתבת יחד עם שאר השינויים של הבקשה.
    return f"/media/{blob_id}"


def delete_stored(db: Session, stored: Optional[str]) -> None:
    """מוחק את התמונה השמורה — רשומת בלוב במסד או קובץ ישן על הדיסק."""
    if not stored:
        return
    if stored.startswith("/media/"):
        blob_id = stored.rsplit("/", 1)[-1]
        blob = db.get(models.MediaBlob, blob_id)
        if blob is not None:
            db.delete(blob)
        # מנקים גם מטמון (אם הבלוב הזה נטען קודם ב-GET /media/<id>), כדי
        # שלא יוגש תוכן ישן לכתובת שנמחקה תוך כדי ה-TTL.
        cache.invalidate_key(f"media:{blob_id}")
    elif stored.startswith("/uploads/"):
        try:
            (UPLOADS_DIR / Path(stored).name).unlink()
        except OSError:
            pass


def resolve_incoming(
    db: Session,
    new_value: Optional[str],
    current: Optional[str],
    prefix: str,
    optimize: bool = False,
) -> Optional[str]:
    """מחזיר את הערך שיש לשמור ב-DB לפי כלל הכתיבה שלמעלה."""
    if new_value is None:
        return current
    v = new_value.strip()
    if not v:
        delete_stored(db, current)
        return None
    if v.startswith("data:"):
        delete_stored(db, current)
        return _write_data_url(db, v, prefix, optimize=optimize)
    # URL קיים שחזר מקריאה → אין שינוי.
    return current


def to_url(stored: Optional[str]) -> Optional[str]:
    """מחזיר את הנתיב לתצוגה כפי שהוא (יחסי), בלי לקבע כתובת שרת.

    למה יחסי ולא מוחלט: קידום עם host קשיח (למשל ``API_PUBLIC_URL``) היה שביר —
    אם המשתנה לא הוגדר בייצור, כל תמונה קיבלה כתובת ``http://localhost:8000/...``
    שהדפדפן של המשתמש לא יכול להגיע אליה, והתמונה נשברה. במקום זה מחזירים את
    הנתיב היחסי (``/media/<id>`` או ``/uploads/<file>``), והפרונטאנד מרכיב את
    הכתובת המלאה מול ה-API שהוא כבר יודע (ראה ``mediaUrl`` ב-``frontend/api.ts``).
    ערכי ``data:`` ישנים או URL חיצוני מוחזרים כמו שהם.
    """
    return stored or None
