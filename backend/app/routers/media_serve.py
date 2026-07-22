"""הגשת תמונות ששמורות כרשומות בלוב במסד הנתונים (``/media/<id>``).

תמונת ההזמנה/סקיצת האולם נשמרות ב-``media_blobs`` (ראה ``app/media.py``).
נקודה זו מחזירה את בייטים של התמונה עם ה-content-type הנכון, כדי שהדפדפן
(כולל דף אישור ההגעה הציבורי) יטען אותה ישירות. התמונות אינן סודיות
(הזמנה שממילא נשלחת לכל המוזמנים), לכן אין דרישת הרשאה — רק מזהה בלתי-ניתן-לניחוש.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import cache, models
from app.database import get_db

router = APIRouter(prefix="/media", tags=["media"])

# בלוב עם אותו id הוא בלתי-משתנה לחלוטין (העלאה חדשה מקבלת id חדש — ראה
# app/media.py), אז אין סכנת "תוכן ישן" מה-TTL — הוא רק חוסך פנייה חוזרת
# ל-DB לאותה תמונה (למשל דף RSVP שכמה מוזמנים פותחים באותו יום). TTL ארוך
# יחסית כי אין באמת מה "לרענן". גודל מוגבל (MAX_CACHEABLE_BYTES) כדי לא
# להעמיס זיכרון בתהליך יחיד עם תמונות גדולות.
MEDIA_CACHE_TTL_SECONDS = 1800  # 30 דקות
MAX_CACHEABLE_BYTES = 1_000_000  # ~1MB; מעל זה מוגש ישירות מה-DB בלי מטמון


@router.get("/{blob_id}")
def get_media(blob_id: str, db: Session = Depends(get_db)) -> Response:
    key = f"media:{blob_id}"
    cached = cache.get(key)
    if cached is not None:
        content, content_type = cached
    else:
        blob = db.get(models.MediaBlob, blob_id)
        if blob is None:
            raise HTTPException(status_code=404, detail="התמונה לא נמצאה")
        content, content_type = blob.data, blob.content_type
        # לא ממטמנים בלובים גדולים מדי (תמונות כבדות) כדי לא לנפח את זיכרון
        # התהליך היחיד — הם פשוט נטענים מה-DB בכל בקשה, כמו קודם.
        if len(content) <= MAX_CACHEABLE_BYTES:
            cache.set(key, (content, content_type), MEDIA_CACHE_TTL_SECONDS)
    return Response(
        content=content,
        media_type=content_type or "application/octet-stream",
        # התמונה בלתי-משתנה (מזהה חדש לכל העלאה), אז אפשר לאחסן במטמון לאורך זמן.
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
