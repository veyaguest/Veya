"""אחסון תמונות כקבצים (במקום base64 בתוך שורת ה-DB).

למה: תמונת הזמנה/סקיצת אולם כ-base64 בתוך שורת האירוע מנפחת כל שאילתה
(מגה-בייטים בכל טעינת אירוע). כאן שומרים את הקובץ תחת ``backend/uploads/``
ובמסד נשמר רק נתיב קצר (``/uploads/<file>``). בקריאה מחזירים URL מלא כדי
שהדפדפן (גם דף האישור הציבורי) יטען את התמונה ישירות מהשרת.

כלל הכתיבה:
- ערך שהוא ``data:`` (base64) → נכתב לקובץ חדש, מוחזר נתיב ``/uploads/...``.
- ערך ריק ("") → מחיקת התמונה (None).
- כל ערך אחר (URL קיים שחזר מקריאה) → אין שינוי, שומרים את מה שכבר יש.
"""
from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path
from typing import Optional

# backend/uploads (app נמצא ב-backend/app → parent.parent = backend)
UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads"

_MIME_EXT = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/svg+xml": "svg",
}


def _api_base() -> str:
    """כתובת הבסיס הציבורית של ה-API (להרכבת URL מלא לתמונה)."""
    return os.getenv("API_PUBLIC_URL", "http://localhost:8000").rstrip("/")


def _write_data_url(data_url: str, prefix: str) -> str:
    """כותב data URL לקובץ ומחזיר נתיב יחסי (/uploads/<file>)."""
    header, _, b64 = data_url.partition(",")
    mime = header[5:].split(";")[0] if header.startswith("data:") else ""
    ext = _MIME_EXT.get(mime.lower(), "bin")
    raw = base64.b64decode(b64, validate=False)
    UPLOADS_DIR.mkdir(exist_ok=True)
    fname = f"{prefix}-{secrets.token_hex(8)}.{ext}"
    (UPLOADS_DIR / fname).write_bytes(raw)
    return f"/uploads/{fname}"


def delete_stored(stored: Optional[str]) -> None:
    """מוחק את קובץ התמונה אם הערך השמור מצביע על קובץ מקומי שלנו."""
    if stored and stored.startswith("/uploads/"):
        try:
            (UPLOADS_DIR / Path(stored).name).unlink()
        except OSError:
            pass


def resolve_incoming(
    new_value: Optional[str], current: Optional[str], prefix: str
) -> Optional[str]:
    """מחזיר את הערך שיש לשמור ב-DB לפי כלל הכתיבה שלמעלה."""
    if new_value is None:
        return current
    v = new_value.strip()
    if not v:
        delete_stored(current)
        return None
    if v.startswith("data:"):
        delete_stored(current)
        return _write_data_url(v, prefix)
    # URL קיים שחזר מקריאה → אין שינוי.
    return current


def to_url(stored: Optional[str]) -> Optional[str]:
    """ממיר נתיב שמור ל-URL מלא לתצוגה. ערכי base64 ישנים מוחזרים כמו שהם."""
    if not stored:
        return None
    if stored.startswith("/uploads/"):
        return _api_base() + stored
    return stored
