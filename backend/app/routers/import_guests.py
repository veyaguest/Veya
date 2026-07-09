"""נקודות API לייבוא מוזמנים מקובץ Excel/CSV."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_default_event
from app.importer import build_preview, detect_columns, parse_file

router = APIRouter(prefix="/guests/import", tags=["import"])


@router.post("/preview")
async def preview_import(file: UploadFile = File(...)):
    """שלב 1: מעלים קובץ, מקבלים תצוגה מקדימה עם זיהוי עמודות וולידציה.

    לא נשמר כלום למסד הנתונים בשלב הזה.
    """
    content = await file.read()
    try:
        headers, rows = parse_file(file.filename or "", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not headers:
        raise HTTPException(status_code=400, detail="הקובץ ריק או ללא כותרות")

    mapping = detect_columns(headers)
    if mapping.get("full_name") is None or mapping.get("phone") is None:
        raise HTTPException(
            status_code=400,
            detail="לא זוהו עמודות חובה. ודא שיש עמודות 'שם' ו'טלפון' בקובץ.",
        )

    return build_preview(headers, rows, mapping)


class ImportCommit(BaseModel):
    rows: list[schemas.GuestCreate]


@router.post("/commit")
def commit_import(
    payload: ImportCommit,
    db: Session = Depends(get_db),
    event: models.Event = Depends(get_default_event),
):
    """שלב 2: מקבלים את השורות התקינות ושומרים אותן כמוזמנים."""
    created = 0
    for row in payload.rows:
        db.add(models.Guest(event_id=event.id, **row.model_dump()))
        created += 1
    db.commit()
    return {"created": created}
