"""נקודות API לייבוא מוזמנים מקובץ Excel/CSV."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, permissions, schemas
from app.database import get_db
from app.deps import EventAccess

_write = EventAccess(permissions.GUESTS_WRITE)

from app.importer import build_preview, detect_columns, parse_file, parse_freeform_text
from app.validators import normalize_israeli_phone

router = APIRouter(prefix="/guests/import", tags=["import"])

# תקרות הגנה מפני קבצים ענקיים שיכשילו את השרת (זיכרון/זמן).
MAX_IMPORT_BYTES = 5 * 1024 * 1024   # 5MB
MAX_IMPORT_ROWS = 5000               # מספר שורות מקסימלי בקובץ


@router.post("/preview")
async def preview_import(
    file: UploadFile = File(...),
    event: models.Event = Depends(_write),
):
    """שלב 1: מעלים קובץ, מקבלים תצוגה מקדימה עם זיהוי עמודות וולידציה.

    לא נשמר כלום למסד הנתונים בשלב הזה. דורש התחברות + הרשאת כתיבה על
    האירוע (כמו /paste ו-/commit) — לא endpoint פתוח.
    """
    content = await file.read()
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"הקובץ גדול מדי (מעל {MAX_IMPORT_BYTES // (1024 * 1024)}MB). "
            "נא לפצל לקובץ קטן יותר.",
        )
    try:
        headers, rows = parse_file(file.filename or "", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        # רשת ביטחון: כל תקלת קריאה לא-צפויה (קובץ פגום בצורה חריגה,
        # שגיאת ספרייה פנימית) — לא מותר שתיפול כ-500 גולמי למשתמש.
        raise HTTPException(
            status_code=400,
            detail="לא הצלחנו לקרוא את הקובץ. בדקו שהקובץ תקין ונסו שוב.",
        )

    if not headers:
        raise HTTPException(status_code=400, detail="הקובץ ריק או ללא כותרות")

    if len(rows) > MAX_IMPORT_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"הקובץ מכיל יותר מ-{MAX_IMPORT_ROWS} שורות. נא לפצל לקבצים קטנים יותר.",
        )

    mapping = detect_columns(headers)
    if mapping.get("full_name") is None or mapping.get("phone") is None:
        raise HTTPException(
            status_code=400,
            detail="לא זוהו עמודות חובה. ודא שיש עמודות 'שם' ו'טלפון' בקובץ.",
        )

    return build_preview(headers, rows, mapping)


class ImportPaste(BaseModel):
    text: str = ""


@router.post("/paste")
def paste_import(
    payload: ImportPaste,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_write),
):
    """ייבוא חכם: מקבלים רשימת טקסט חופשי (הדבקה מ-WhatsApp/אקסל/כל מקום),
    מחזירים תצוגה מקדימה במבנה זהה ל-`/preview`.

    לא נשמר כלום למסד הנתונים בשלב הזה — רק פענוח + ולידציה. הכפילות מסומנת
    גם מול המוזמנים שכבר קיימים באירוע.
    """
    if len(payload.text or "") > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=400,
            detail="הרשימה ארוכה מדי. נא לפצל להדבקות קטנות יותר.",
        )

    # מפתחות המוזמנים הקיימים באירוע — טלפון מנורמל, או שם (fallback) אם אין טלפון.
    keys: set[str] = set()
    for phone, name in db.execute(
        select(models.Guest.phone, models.Guest.full_name).where(
            models.Guest.event_id == event.id
        )
    ).all():
        if phone:
            keys.add(_phone_key(phone))
        elif name:
            keys.add(name.strip().lower())

    result = parse_freeform_text(payload.text, existing_keys=keys)
    if result["total"] > MAX_IMPORT_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"הרשימה מכילה יותר מ-{MAX_IMPORT_ROWS} שורות. נא לפצל.",
        )
    return result


class ImportCommit(BaseModel):
    rows: list[schemas.GuestCreate]


def _phone_key(phone: str) -> str:
    """מפתח השוואה לטלפון: מנרמל, ואם נכשל — נופל לספרות בלבד."""
    try:
        return normalize_israeli_phone(phone)
    except ValueError:
        return "".join(ch for ch in (phone or "") if ch.isdigit())


@router.post("/commit")
def commit_import(
    payload: ImportCommit,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_write),
):
    """שלב 2: מקבלים את השורות התקינות ושומרים אותן כמוזמנים.

    מדלגים על טלפונים כפולים — גם כאלה שכבר קיימים באירוע וגם כפילויות בתוך
    אותו קובץ — ומדווחים כמה שורות דולגו.
    """
    # טלפונים שכבר קיימים באירוע (כדי לא ליצור כפילויות).
    existing = db.scalars(
        select(models.Guest.phone).where(models.Guest.event_id == event.id)
    ).all()
    seen: set[str] = {_phone_key(p) for p in existing if p}

    created = 0
    skipped_duplicates = 0
    for row in payload.rows:
        key = _phone_key(row.phone)
        if key and key in seen:
            skipped_duplicates += 1
            continue
        if key:
            seen.add(key)
        db.add(models.Guest(event_id=event.id, **row.model_dump()))
        created += 1
    db.commit()
    return {"created": created, "skipped_duplicates": skipped_duplicates}
