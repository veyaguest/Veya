"""הגשת תמונות ששמורות כרשומות בלוב במסד הנתונים (``/media/<id>``).

תמונת ההזמנה/סקיצת האולם נשמרות ב-``media_blobs`` (ראה ``app/media.py``).
נקודה זו מחזירה את בייטים של התמונה עם ה-content-type הנכון, כדי שהדפדפן
(כולל דף אישור ההגעה הציבורי) יטען אותה ישירות. התמונות אינן סודיות
(הזמנה שממילא נשלחת לכל המוזמנים), לכן אין דרישת הרשאה — רק מזהה בלתי-ניתן-לניחוש.
"""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/{blob_id}")
def get_media(blob_id: str, db: Session = Depends(get_db)) -> Response:
    blob = db.get(models.MediaBlob, blob_id)
    if blob is None:
        raise HTTPException(status_code=404, detail="התמונה לא נמצאה")
    return Response(
        content=blob.data,
        media_type=blob.content_type or "application/octet-stream",
        # התמונה בלתי-משתנה (מזהה חדש לכל העלאה), אז אפשר לאחסן במטמון לאורך זמן.
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
