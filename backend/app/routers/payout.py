"""פרטי קבלת מתנות — חשבון הבנק שאליו יועברו המתנות שהתקבלו.

**גישה: בעלי האירוע בלבד.** לא נפתחה כאן שום הרשאת חבר-אירוע, גם לא
``view_reports``. מפיק או אולם שמנהלים אירוע יכולים לראות שהתקבלו מתנות
(``routers/gifts.py``), אבל חשבון הבנק של הזוג אינו מידע שלהם. אותו כלל
בדיוק נאכף שוב ברמת ה-DB ב-``rls/14_payout_accounts_rls.sql``.

**מה הקובץ הזה לא עושה:** הוא לא מעביר כסף, לא מדבר עם ספק סליקה ולא מייצר
Payout. הוא שומר את הפרטים בלבד — כדי שיהיו מוכנים כשתיבנה ההעברה בפועל.

**ואין כאן שום נתיב שמאשר.** בעלי האירוע יכולים לשמור ולהגיש, ותו לא.
האישור נעשה בנתיבי האדמין (``routers/payout_admin.py``), ותשובת הספק
נרשמת שם גם היא — מי שמזין את פרטי החשבון אינו מי שמאשר אותם.

**ואחרי שאושר — אין כאן גם נתיב ששומר.** ``payout_service.assert_unlocked``
חוסם כל כתיבה לחשבון מאושר, ולכן ההגנה אינה תלויה בכך שהמסך יסתיר כפתור.
פתיחה מחדש היא פעולת אדמין (``POST /admin/payout/{event_id}/reopen``).
"""
from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, undefer

from app import banks, models, payout_service, payout_status, schemas
from app.auth import get_current_owner
from app.database import get_db
from app.deps import EventAccess

# בעלים/בן-זוג/אדמין בלבד — ראו EventAccess: ``owner_only`` חוסם כל חבר-אירוע
# אחר, בלי קשר להרשאות שניתנו לו.
_owner_only = EventAccess(owner_only=True)

router = APIRouter(prefix="/payout", tags=["payout"])

# אישור ניהול חשבון מגיע מהבנק כ-PDF, או כצילום/סריקה. אין כאן SVG במכוון
# (SVG הוא מסמך שיכול להריץ סקריפט), ואין פורמטים אקזוטיים.
ALLOWED_CERTIFICATE_TYPES = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/heic": "heic",
}
MAX_CERTIFICATE_BYTES = 10 * 1024 * 1024  # 10MB — אישור בנק סרוק לא מגיע לזה


def _mask(account_number: str) -> str:
    """מחזיר את מספר החשבון מוסתר, למעט ארבע הספרות האחרונות.

    ארבע ספרות מספיקות לזוג כדי לזהות שזה החשבון הנכון, ולא מספיקות כדי
    להעביר אליו כסף. חשבון קצר במיוחד מוסתר במלואו.
    """
    tail = account_number[-4:] if len(account_number) > 4 else ""
    return "•" * (len(account_number) - len(tail)) + tail


def _read(row: models.PayoutAccount | None) -> schemas.PayoutAccountRead:
    """בונה את התשובה למסך. מספר החשבון המלא לעולם לא חוזר מכאן.

    השדות ``provider``/``provider_account_id`` אינם מועתקים לתשובה
    במכוון — ראו ``schemas.PayoutAccountRead``. המיפוי כאן מפורש
    שדה-שדה, כך שעמודה חדשה בטבלה לא תזלוג אוטומטית ל-API.
    """
    if row is None:
        # אין פרטים כלל: שתי הבדיקות ``pending`` וברור שאין אימות מלא.
        return schemas.PayoutAccountRead(
            configured=False,
            status=payout_status.MISSING,
            veya_status=payout_status.REVIEW_PENDING,
            provider_status=payout_status.REVIEW_PENDING,
            fully_verified=False,
        )
    bank = banks.BY_CODE.get(row.bank_code)
    cert = None
    if row.certificate_filename or row.certificate_size:
        cert = schemas.PayoutCertificateRead(
            filename=row.certificate_filename,
            content_type=row.certificate_content_type,
            size=row.certificate_size,
            uploaded_at=row.certificate_uploaded_at,
        )
    status = payout_service.current_status(row)
    return schemas.PayoutAccountRead(
        configured=True,
        status=status,
        # שלושת השדות האלה **נגזרים בשרת** ואינם מתקבלים בשום קלט:
        # ``PayoutAccountWrite`` מכיל פרטי בנק בלבד, וכל שדה נוסף שיישלח
        # בגוף הבקשה נזרק ע"י Pydantic ולא מגיע לשום מקום.
        veya_status=payout_service.veya_status(row),
        provider_status=payout_service.provider_status(row),
        fully_verified=payout_service.is_fully_verified(row),
        # נעילה: מרגע ש-VEYA אישרה אין יותר עריכה. השדה מוחזר כדי שהמסך
        # לא יצטרך להסיק אותו מהסטטוס — ההסקה הזו היא בדיוק המקום שבו
        # UI ושרת מתחילים לסטות זה מזה.
        locked=payout_service.is_locked(row),
        # אפשר להגיש רק כשיש אישור, ורק מסטטוס שממנו ההגשה חוקית
        # (``missing`` או ``rejected``) — אותו כלל שהשירות אוכף בפועל.
        can_submit=bool(row.certificate_size)
        and status in (payout_status.MISSING, payout_status.REJECTED),
        # הערה: אחרי דחיית ספק החשבון עדיין ``verified`` אצלנו, ולכן
        # ``can_submit`` שקר — וזה נכון: אין מה להגיש מחדש בלי לשנות משהו.
        # הזוג עורך את הפרטים, השמירה מחזירה את הסטטוס ל-``missing``,
        # ורק אז ההגשה נפתחת.
        rejection_reason=row.rejection_reason,
        provider_rejection_reason=row.provider_rejection_reason,
        submitted_at=row.submitted_at,
        bank_code=row.bank_code,
        # אם קוד הבנק כבר לא ברשימה (בנק שהתמזג אחרי שהפרטים נשמרו) עדיין
        # מציגים את הקוד עצמו, ולא "לא ידוע" — הנתון תקף, רק השם חסר.
        bank_name=bank.name if bank else f"קוד בנק {row.bank_code}",
        branch_number=row.branch_number,
        account_number_masked=_mask(row.account_number),
        certificate=cert,
        updated_at=row.updated_at or row.created_at,
    )


def _parse_certificate(data_url: str) -> tuple[bytes, str]:
    """מפרק data URL של אישור ניהול חשבון, ומאמת סוג וגודל.

    הבדיקות כאן הן על מה שבאמת ייכתב למסד — לא על מה שהדפדפן הצהיר עליו.
    """
    header, _, b64 = data_url.partition(",")
    if not header.startswith("data:") or not b64:
        raise HTTPException(status_code=422, detail="הקובץ לא נקרא כראוי — נסו להעלות שוב")
    content_type = header[5:].split(";")[0].strip().lower()
    if content_type not in ALLOWED_CERTIFICATE_TYPES:
        raise HTTPException(
            status_code=422,
            detail="אפשר להעלות קובץ PDF או תמונה (JPG, PNG)",
        )
    try:
        raw = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=422, detail="הקובץ לא נקרא כראוי — נסו להעלות שוב") from None
    if not raw:
        raise HTTPException(status_code=422, detail="הקובץ ריק — נסו להעלות שוב")
    if len(raw) > MAX_CERTIFICATE_BYTES:
        raise HTTPException(status_code=413, detail="הקובץ גדול מדי — עד 10MB")
    return raw, content_type


def _certificate_filename(content_type: str) -> str:
    """שם הקובץ לתצוגה ולהורדה.

    בכוונה **לא** משתמשים בשם שהמשתמש העלה: "IMG_4821.pdf" לא אומר כלום
    כשרואים אותו חצי שנה אחרי, ושם קובץ שמגיע מהלקוח הוא גם טקסט לא-מהימן
    שנכנס לכותרת ``Content-Disposition``. שם קבוע ומתאר פותר את שניהם.
    """
    return f"אישור ניהול חשבון.{ALLOWED_CERTIFICATE_TYPES[content_type]}"


@router.get("", response_model=schemas.PayoutAccountRead)
def get_payout_account(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_owner_only),
):
    """פרטי החשבון השמורים. מספר החשבון חוזר מוסתר בלבד."""
    return _read(payout_service.get(db, event.id))


@router.put("", response_model=schemas.PayoutAccountRead)
def save_payout_account(
    payload: schemas.PayoutAccountWrite,
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_owner_only),
    user: models.User = Depends(get_current_owner),
):
    """שומר או מעדכן את פרטי החשבון.

    כל הכתיבה עוברת דרך ``payout_service`` — שם נאכפים הנרמול, ביטול
    האימות בעת שינוי זהות החשבון, וכתיבת היומן. הנתיב עצמו לא נוגע
    בשדות ישירות.

    **שמירה אינה הגשה.** הפרטים נשמרים בסטטוס ``missing`` עד שבעלי
    האירוע מגישים אותם במפורש (``POST /payout/submit``) — כך אפשר למלא
    את הטופס בכמה פעימות בלי שכל שמירה תפתח בדיקה חדשה.
    """
    ip = request.client.host if request.client else None
    try:
        row, creating = payout_service.save_details(
            db, event.id,
            bank_code=payload.bank_code,
            branch_number=payload.branch_number,
            account_number=payload.account_number,
            user_id=user.id, ip=ip,
        )
    except payout_service.PayoutLocked as exc:
        # קלט תקין, מצב שאינו מאפשר — 409 ולא 422.
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except payout_service.PayoutError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if payload.certificate:
        raw, content_type = _parse_certificate(payload.certificate)
        payout_service.attach_certificate(
            db, row,
            data=raw, content_type=content_type,
            filename=_certificate_filename(content_type),
            user_id=user.id, ip=ip,
        )
    elif creating:
        # אישור ניהול חשבון הוא שדה חובה בטופס. בעדכון של חשבון קיים אפשר
        # לשנות מספר בלי להעלות מחדש את אותו אישור — אבל שמירה ראשונה בלי
        # אישור כלל אינה תקינה.
        raise HTTPException(status_code=422, detail="צריך לצרף אישור ניהול חשבון")

    db.flush()
    db.commit()
    db.refresh(row)
    return _read(row)


@router.post("/submit", response_model=schemas.PayoutAccountRead)
def submit_payout_account(
    request: Request,
    db: Session = Depends(get_db),
    event: models.Event = Depends(_owner_only),
    user: models.User = Depends(get_current_owner),
):
    """מגיש את הפרטים לבדיקה: ``missing``/``rejected`` → ``submitted``.

    **לא נשלח כאן מידע לשום גורם חיצוני.** אין פנייה לספק סליקה, אין KYC
    ואין אימות בנק — ההגשה רק מסמנת שהפרטים מוכנים. הבדיקה עצמה ידנית
    היום; חיבור ספק עתידי ייכנס ב-``payout_service`` בלבד, בלי לשנות את
    הנתיב הזה.

    המעבר ל-``verified`` **אינו** נגיש מכאן ולא מאף נתיב של בעלי האירוע —
    מי שמזין את פרטי החשבון אינו מי שמאשר אותם.
    """
    try:
        row = payout_service.submit(
            db, event.id,
            user_id=user.id,
            ip=request.client.host if request.client else None,
        )
    except payout_service.PayoutError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(row)
    return _read(row)


@router.get("/certificate")
def get_certificate(
    db: Session = Depends(get_db),
    event: models.Event = Depends(_owner_only),
):
    """מגיש את אישור ניהול החשבון לבעלי האירוע בלבד.

    זו הדרך **היחידה** לקרוא את הקובץ. בכוונה לא נעשה שימוש ב-``media_blobs``
    ו-``GET /media/<id>``, שהם ללא אימות (ראו ``models.PayoutAccount``).
    """
    row = db.scalars(
        select(models.PayoutAccount)
        .where(models.PayoutAccount.event_id == event.id)
        .options(undefer(models.PayoutAccount.certificate_data))
    ).first()
    if row is None or not row.certificate_data:
        raise HTTPException(status_code=404, detail="לא נמצא אישור ניהול חשבון")
    filename = row.certificate_filename or "certificate"
    return Response(
        content=row.certificate_data,
        media_type=row.certificate_content_type or "application/octet-stream",
        headers={
            # RFC 5987 — שם הקובץ בעברית חייב להיות מקודד, אחרת הכותרת נשברת.
            "Content-Disposition": f"inline; filename*=UTF-8''{_quote(filename)}",
            # מסמך פיננסי: לא נשמר במטמון של דפדפן או פרוקסי.
            "Cache-Control": "private, no-store",
        },
    )


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")
