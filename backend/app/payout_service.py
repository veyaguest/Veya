"""שירות פרטי קבלת המתנות — שמירה, הגשה ושינוי סטטוס.

**זו נקודת הכתיבה היחידה** לטבלת ``payout_accounts``. הנתיבים
(``routers/payout.py``) לא נוגעים בשדות ישירות, כדי ששלושת הכללים
שלמטה ייאכפו בכל מסלול ולא ייתלו בזכירה של מי שיוסיף נתיב חדש:

1. **כל מעבר סטטוס עובר ``payout_status.assert_transition``** — אין השמה
   חופשית ל-``row.status``.
2. **עריכת פרטי בנק מבטלת אימות** — חשבון שאומת והוחלף אינו מאומת.
3. **כל שינוי נרשם ליומן, בלי הנתונים עצמם** — מספר חשבון לא נכתב ליומן.

4. **שתי הבדיקות נשארות בלתי תלויות** — בדיקת VEYA כותבת ל-``status``,
   תשובת הספק כותבת ל-``provider_status``, ואף אחת לא נוגעת בשנייה.

**מה שאין כאן:** העברת כספים, פנייה לספק סליקה, KYC ואימות בנק אמיתי.
``submit`` רק מסמן שהפרטים מוכנים לבדיקה. הבדיקה עצמה היא היום אדם
ב-VEYA; בעתיד תגיע דרך ``payout_provider`` בלי לשנות את הקובץ הזה.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit, banks, models, payout_status

#: השדות שהם "זהות החשבון". שינוי באחד מהם מבטל אימות קיים.
IDENTITY_FIELDS = ("bank_code", "branch_number", "account_number")


class PayoutError(ValueError):
    """שגיאת שימוש עם נוסח עברי מוכן להצגה."""


class PayoutLocked(PayoutError):
    """ניסיון לשנות חשבון שכבר אושר.

    נפרד מ-``PayoutError`` כדי שהנתיב יחזיר 409 (התנגשות מצב) ולא 422
    (קלט שגוי): הקלט היה תקין לגמרי, פשוט אסור לשנות עכשיו.
    """


def get(db: Session, event_id: int) -> Optional[models.PayoutAccount]:
    return db.scalars(
        select(models.PayoutAccount).where(models.PayoutAccount.event_id == event_id)
    ).first()


def current_status(row: Optional[models.PayoutAccount]) -> str:
    """הסטטוס של האירוע. אין שורה = ``missing`` (וכך גם שורה ישנה עם NULL)."""
    if row is None:
        return payout_status.MISSING
    return row.status or payout_status.MISSING


def veya_status(row: Optional[models.PayoutAccount]) -> str:
    """תשובת בדיקת VEYA: ``pending`` / ``approved`` / ``rejected``."""
    return payout_status.veya_review(current_status(row))


def provider_status(row: Optional[models.PayoutAccount]) -> str:
    """תשובת בדיקת ספק הסליקה. אין שורה, או שורה ישנה עם NULL = ``pending``."""
    if row is None:
        return payout_status.REVIEW_PENDING
    return payout_status.normalize_review(row.provider_status)


def is_locked(row: Optional[models.PayoutAccount]) -> bool:
    """האם החשבון נעול לשינוי.

    **הנעילה נכנסת לתוקף ברגע ש-VEYA אישרה** (``status == verified``) —
    לא כשהאימות המלא הושלם. זו הנקודה שבה אדם הסתכל על אישור ניהול
    החשבון והצהיר שהוא תקין; אילו הזוג היה יכול להחליף מספר חשבון אחריה,
    ההצהרה הזו הייתה חסרת ערך — אפשר היה לעבור בדיקה עם חשבון אחד
    ולהחליף אותו בחשבון אחר.

    זו הסיבה שהנעילה **אינה** מחכה לאישור ספק הסליקה: הסיכון קיים כבר
    מהרגע הראשון, ולא רק בסוף.

    **חריג אחד: דחייה של ספק הסליקה מבטלת את הנעילה.** אם הספק דחה את
    החשבון, הוא לא יוכל לקבל דרכו כסף לעולם — כלומר אין יותר מה להגן
    עליו, ויש מה לתקן. נעילה במצב הזה הייתה לוכדת את בעלי האירוע: המסך
    אומר להם "נדרש תיקון", וכל ניסיון לתקן היה נדחה. שתי הבדיקות נשארות
    בלתי תלויות — תשובת הספק לא משנה את ``status``, רק את השאלה אם יש
    בכלל מה לנעול.

    פתיחה מחדש (במצב מאושר רגיל) היא פעולת אדמין בלבד — ``veya_reopen``.
    """
    if current_status(row) != payout_status.VERIFIED:
        return False
    return provider_status(row) != payout_status.REVIEW_REJECTED


def assert_unlocked(row: Optional[models.PayoutAccount]) -> None:
    """שער הכתיבה. נקרא בכל מסלול שמשנה פרטי חשבון או מסמך."""
    if is_locked(row):
        raise PayoutLocked(
            "פרטי החשבון אושרו ונעולים לשינוי. לפתיחה מחדש יש לפנות לתמיכה."
        )


def is_fully_verified(row: Optional[models.PayoutAccount]) -> bool:
    """**הפונקציה שכל המערכת שואלת** — האם החשבון כשיר לקבל כסף.

    זו העטיפה היחידה מעל ``payout_status.is_fully_verified``: היא מקבלת
    שורה (או ``None``) ופותרת ממנה את שתי התשובות. התנאי עצמו — ששתי
    הבדיקות ``approved`` — כתוב במקום אחד בלבד, ב-``payout_status``.

    ``None`` (אין בכלל פרטי חשבון) מחזיר ``False`` באופן טבעי: אין מה
    לאמת. כך לקורא לא צריך להיות ענף מיוחד ל"אין חשבון".
    """
    return payout_status.is_fully_verified(veya_status(row), provider_status(row))


def _set_status(
    db: Session,
    row: models.PayoutAccount,
    target: str,
    *,
    event_id: int,
    user_id: Optional[int],
    reason: str = "",
    detail: str = "",
    ip: Optional[str] = None,
) -> None:
    """מעבר סטטוס יחיד — מאומת, מתוארך ומתועד. הפונקציה הפנימית היחידה
    שמותר לה לגעת ב-``row.status``."""
    before = current_status(row)
    payout_status.assert_transition(before, target)
    if before == target:
        return
    row.status = target
    row.status_changed_at = datetime.utcnow()
    row.rejection_reason = reason or None
    # המעבר עצמו (``לפני → אחרי``) **תמיד** נכתב, גם כשיש נוסח עברי משלו.
    # הנוסח קיים בשביל אדם שקורא את היומן; המעבר קיים כדי שיהיה אפשר
    # לשחזר מהיומן את מסלול החיים המלא של החשבון בלי לנחש מהמילים.
    audit.record(
        db,
        "payout_status_changed",
        event_id=event_id,
        user_id=user_id,
        detail=f"{detail or 'סטטוס פרטי קבלת המתנות'} · {before} → {target}",
        ip=ip,
    )


def _set_provider_status(
    db: Session,
    row: models.PayoutAccount,
    target: str,
    *,
    user_id: Optional[int] = None,
    reason: str = "",
    detail: str = "",
    ip: Optional[str] = None,
) -> None:
    """מעדכן את תשובת ספק הסליקה. **הפונקציה היחידה שנוגעת בעמודה הזו.**

    אין כאן מכונת מצבים כמו במסלול ה-VEYA, ובכוונה: הסטטוס הזה אינו שלנו.
    הוא שיקוף של מה שהספק אומר, והספק רשאי לשנות את דעתו לכל כיוון (לאשר,
    לדחות, ולהחזיר לבדיקה) בלי שנחסום אותו. מה שכן נאכף — שהערך הוא אחת
    משלוש המילים המוכרות.
    """
    before = provider_status(row)
    target = payout_status.normalize_review(target)
    if before == target:
        return
    row.provider_status = target
    row.provider_status_changed_at = datetime.utcnow()
    row.provider_rejection_reason = reason or None
    audit.record(
        db,
        "payout_provider_status_changed",
        event_id=row.event_id,
        user_id=user_id,
        detail=detail or f"בדיקת ספק הסליקה: {before} → {target}"
        + (f" · סיבה: {reason}" if reason else ""),
        ip=ip,
    )


def save_details(
    db: Session,
    event_id: int,
    *,
    bank_code,
    branch_number,
    account_number,
    user_id: Optional[int] = None,
    ip: Optional[str] = None,
) -> tuple[models.PayoutAccount, bool]:
    """שומר או מעדכן את פרטי הבנק. מחזיר ``(שורה, נוצרה_עכשיו)``.

    הנרמול והוולידציה עוברים דרך ``app/banks.py`` — מקור אמת אחד לכללים
    ולנוסח השגיאות, כך שאותה בדיקה חלה על כל נתיב שכותב פרטי חשבון.
    """
    row = get(db, event_id)

    # **לפני הנרמול, לא אחריו.** חשבון נעול לא אמור לקבל אפילו הודעת
    # ולידציה על הקלט — התשובה היחידה הנכונה לו היא "אי אפשר לשנות".
    assert_unlocked(row)

    try:
        code = banks.normalize_bank_code(bank_code)
        branch = banks.normalize_branch(branch_number)
        account = banks.normalize_account(account_number)
    except banks.BranchError as exc:
        raise PayoutError(str(exc)) from exc

    creating = row is None
    if row is None:
        row = models.PayoutAccount(event_id=event_id, status=payout_status.MISSING)
        db.add(row)

    changed = creating or any(
        getattr(row, f) != v
        for f, v in zip(IDENTITY_FIELDS, (code, branch, account))
    )
    row.bank_code, row.branch_number, row.account_number = code, branch, account

    # כלל 2: זהות החשבון השתנתה → **שתי** הבדיקות בטלות. גם זו של VEYA
    # וגם זו של הספק: שתיהן אישרו חשבון מסוים, וזה כבר לא אותו חשבון.
    if changed:
        if current_status(row) != payout_status.MISSING:
            _set_status(
                db, row, payout_status.MISSING,
                event_id=event_id, user_id=user_id, ip=ip,
                detail="פרטי החשבון שונו — האימות בוטל ונדרשת הגשה מחדש",
            )
        row.veya_reviewed_by_user_id = None
        row.veya_reviewed_at = None
        if provider_status(row) != payout_status.REVIEW_PENDING:
            _set_provider_status(
                db, row, payout_status.REVIEW_PENDING,
                user_id=user_id, ip=ip,
                detail="פרטי החשבון שונו — בדיקת ספק הסליקה אופסה",
            )

    audit.record(
        db,
        "payout_details_saved" if creating else "payout_details_updated",
        event_id=event_id,
        user_id=user_id,
        # בלי קוד בנק, סניף או מספר חשבון — היומן מתעד שינוי, לא נתונים.
        detail="נשמרו פרטי קבלת המתנות" if creating else "עודכנו פרטי קבלת המתנות",
        ip=ip,
    )
    return row, creating


def attach_certificate(
    db: Session,
    row: models.PayoutAccount,
    *,
    data: bytes,
    content_type: str,
    filename: str,
    user_id: Optional[int] = None,
    ip: Optional[str] = None,
) -> None:
    """מצרף אישור ניהול חשבון חדש (דורס קודם).

    החלפת האישור **אינה** מבטלת אימות: זהות החשבון לא השתנתה, ורק המסמך
    שמוכיח אותה הוחלף (למשל סריקה קריאה יותר אחרי דחייה).

    אבל **אחרי אישור אי אפשר להחליף גם אותו**: המסמך הוא הראיה שעליה
    האישור נשען. השער נבדק כאן שוב ולא רק ב-``save_details``, כי זה מסלול
    כתיבה נפרד — ומי שיוסיף בעתיד נתיב שמעלה מסמך בלבד יקבל את ההגנה
    מאליה.
    """
    assert_unlocked(row)
    row.certificate_data = data
    row.certificate_content_type = content_type
    row.certificate_filename = filename
    row.certificate_size = len(data)
    row.certificate_uploaded_at = datetime.utcnow()
    audit.record(
        db, "payout_certificate_uploaded",
        event_id=row.event_id, user_id=user_id,
        detail="הועלה אישור ניהול חשבון", ip=ip,
    )


def submit(
    db: Session,
    event_id: int,
    *,
    user_id: Optional[int] = None,
    ip: Optional[str] = None,
) -> models.PayoutAccount:
    """מגיש את הפרטים לבדיקה: ``missing``/``rejected`` → ``submitted``.

    **לא נשלח כאן מידע לאף גורם חיצוני.** ההגשה מסמנת שהפרטים מוכנים;
    הבדיקה עצמה ידנית היום (ראו ``payout_provider.ManualProvider``).
    """
    row = get(db, event_id)
    if row is None:
        raise PayoutError("אין פרטי חשבון להגשה")
    if not row.certificate_data and not row.certificate_size:
        raise PayoutError("צריך לצרף אישור ניהול חשבון לפני ההגשה")

    status = current_status(row)
    if status in payout_status.PENDING_REVIEW:
        raise PayoutError("הפרטים כבר הוגשו וממתינים לבדיקה")
    if status == payout_status.VERIFIED:
        raise PayoutError("הפרטים כבר אומתו")

    try:
        _set_status(
            db, row, payout_status.SUBMITTED,
            event_id=event_id, user_id=user_id, ip=ip,
            detail="פרטי קבלת המתנות הוגשו לבדיקה",
        )
    except payout_status.InvalidStatusTransition as exc:
        raise PayoutError(str(exc)) from exc
    row.submitted_at = datetime.utcnow()
    return row


def set_status(
    db: Session,
    event_id: int,
    target: str,
    *,
    reason: str = "",
    reviewer_user_id: Optional[int] = None,
    ip: Optional[str] = None,
) -> models.PayoutAccount:
    """מעבר במסלול ה-VEYA — ``under_review`` / ``verified`` / ``rejected``.

    **בכוונה אין לזה נתיב API של בעלי האירוע.** מי שמזין את פרטי החשבון
    אינו מי שמאשר אותם; הפונקציה הזו מיועדת לצד הבודק בלבד, ובפועל נקראת
    דרך ``veya_approve``/``veya_reject`` מנתיבי האדמין.

    היא **אינה** נוגעת ב-``provider_status`` — תשובת הספק היא מסלול נפרד.
    """
    row = get(db, event_id)
    if row is None:
        raise PayoutError("אין פרטי חשבון לאירוע הזה")
    try:
        _set_status(
            db, row, target,
            event_id=event_id, user_id=reviewer_user_id, reason=reason, ip=ip,
        )
    except payout_status.InvalidStatusTransition as exc:
        raise PayoutError(str(exc)) from exc
    return row


# ── בדיקה 1: VEYA ────────────────────────────────────────────────────────
# שתי הפעולות שאדם ב-VEYA מבצע. הן החוליה בין נתיבי האדמין למכונת המצבים,
# והן היחידות שכותבות ``veya_reviewed_by_user_id``.


def veya_approve(
    db: Session,
    event_id: int,
    *,
    reviewer_user_id: int,
    ip: Optional[str] = None,
) -> models.PayoutAccount:
    """VEYA מאשרת את פרטי החשבון.

    **האישור הזה לבדו אינו הופך את החשבון לכשיר.** ``provider_status``
    נשאר בדיוק כפי שהיה — ברירת המחדל ``pending`` — עד שספק אמיתי יאמר
    את דברו. זו בדיוק ההפרדה שכל המנגנון קיים בשבילה.

    חשבון שהוגש עובר בדרך דרך ``under_review``: מכונת המצבים אוסרת קפיצה
    ישירה מ-``submitted`` ל-``verified``, כדי שביומן תמיד יישאר תיעוד של
    "נפתחה בדיקה" ולא רק של תוצאתה. שני המעברים נרשמים.
    """
    row = get(db, event_id)
    if row is None:
        raise PayoutError("אין פרטי חשבון לאירוע הזה")
    status = current_status(row)
    if status == payout_status.MISSING:
        raise PayoutError("הפרטים טרם הוגשו לבדיקה")
    if status == payout_status.REJECTED:
        raise PayoutError("הפרטים נדחו — נדרשת הגשה מחדש לפני אישור")

    try:
        if status == payout_status.SUBMITTED:
            _set_status(
                db, row, payout_status.UNDER_REVIEW,
                event_id=event_id, user_id=reviewer_user_id, ip=ip,
                detail="נפתחה בדיקת VEYA לפרטי קבלת המתנות",
            )
        _set_status(
            db, row, payout_status.VERIFIED,
            event_id=event_id, user_id=reviewer_user_id, ip=ip,
            detail="בדיקת VEYA: פרטי קבלת המתנות אושרו",
        )
    except payout_status.InvalidStatusTransition as exc:
        raise PayoutError(str(exc)) from exc

    row.veya_reviewed_by_user_id = reviewer_user_id
    row.veya_reviewed_at = datetime.utcnow()
    return row


def veya_reject(
    db: Session,
    event_id: int,
    *,
    reason: str,
    reviewer_user_id: int,
    ip: Optional[str] = None,
) -> models.PayoutAccount:
    """VEYA דוחה את פרטי החשבון. **סיבת דחייה היא חובה.**

    בלי סיבה, בעלי האירוע מקבלים "נדחה" ולא יודעים מה לתקן — וזו דחייה
    שתחזור. הכלל נאכף כאן, בשירות, ולא רק בטופס האדמין.
    """
    reason = (reason or "").strip()
    if not reason:
        raise PayoutError("צריך להזין סיבת דחייה")

    row = get(db, event_id)
    if row is None:
        raise PayoutError("אין פרטי חשבון לאירוע הזה")
    if current_status(row) == payout_status.MISSING:
        raise PayoutError("הפרטים טרם הוגשו לבדיקה")

    try:
        _set_status(
            db, row, payout_status.REJECTED,
            event_id=event_id, user_id=reviewer_user_id, reason=reason, ip=ip,
            detail=f"בדיקת VEYA: פרטי קבלת המתנות נדחו · סיבה: {reason}",
        )
    except payout_status.InvalidStatusTransition as exc:
        raise PayoutError(str(exc)) from exc

    row.veya_reviewed_by_user_id = reviewer_user_id
    row.veya_reviewed_at = datetime.utcnow()
    return row


def veya_reopen(
    db: Session,
    event_id: int,
    *,
    reviewer_user_id: int,
    ip: Optional[str] = None,
) -> models.PayoutAccount:
    """פותח מחדש חשבון מאושר, כדי שבעלי האירוע יוכלו לתקן ולהגיש שוב.

    **זו הדרך היחידה לבטל את הנעילה**, והיא פעולת אדמין בלבד. החשבון חוזר
    ל-``missing``: לא ל"בבדיקה" ולא ל"נדחה", כי לא נמצאה בו בעיה — הוא
    פשוט אינו מאושר יותר עד שיוגש שוב.

    הפרטים עצמם (בנק, סניף, חשבון, אישור) **נשארים בטבלה** — הזוג לא
    צריך להקליד הכול מחדש, רק לתקן ולשלוח. וגם ``provider_status`` מתאפס:
    אישור ספק שניתן לחשבון שכבר אינו מאושר אצלנו אינו תקף.
    """
    row = get(db, event_id)
    if row is None:
        raise PayoutError("אין פרטי חשבון לאירוע הזה")
    if current_status(row) != payout_status.VERIFIED:
        raise PayoutError("הפרטים אינם מאושרים — אין מה לפתוח מחדש")

    try:
        _set_status(
            db, row, payout_status.MISSING,
            event_id=event_id, user_id=reviewer_user_id, ip=ip,
            detail="בדיקת VEYA: האישור בוטל והפרטים נפתחו לעריכה מחדש",
        )
    except payout_status.InvalidStatusTransition as exc:
        raise PayoutError(str(exc)) from exc

    row.veya_reviewed_by_user_id = None
    row.veya_reviewed_at = None
    if provider_status(row) != payout_status.REVIEW_PENDING:
        _set_provider_status(
            db, row, payout_status.REVIEW_PENDING,
            user_id=reviewer_user_id, ip=ip,
            detail="האישור נפתח מחדש — בדיקת ספק הסליקה אופסה",
        )
    return row


# ── בדיקה 2: ספק הסליקה ──────────────────────────────────────────────────


def set_provider_status(
    db: Session,
    event_id: int,
    target: str,
    *,
    reason: str = "",
    actor_user_id: Optional[int] = None,
    ip: Optional[str] = None,
) -> models.PayoutAccount:
    """רושם את תשובת ספק הסליקה.

    **זו רשומה, לא פנייה.** הפונקציה לא מדברת עם אף ספק ולא שולחת לשום
    מקום מידע — היא רק שומרת מה הספק ענה. היום אין ספק, ולכן היחיד שקורא
    לה הוא אדמין ב-VEYA שמזין ידנית את התשובה; כשיחובר ספק אמיתי, ה-adapter
    שלו יקרא לאותה פונקציה בדיוק עם מה שהחזיר ``PayoutProvider``.

    היא **אינה** נוגעת במסלול ה-VEYA: דחיית ספק לא הופכת חשבון ל-``rejected``
    אצלנו, ואישור ספק לא הופך אותו ל-``verified``.
    """
    row = get(db, event_id)
    if row is None:
        raise PayoutError("אין פרטי חשבון לאירוע הזה")
    try:
        _set_provider_status(
            db, row, target, user_id=actor_user_id, reason=reason, ip=ip,
        )
    except payout_status.InvalidStatusTransition as exc:
        raise PayoutError(str(exc)) from exc
    return row


def awaiting_veya_review(db: Session) -> list[models.PayoutAccount]:
    """כל החשבונות שממתינים להכרעת VEYA — ``submitted`` או ``under_review``.

    התור של מסך האדמין. הוותיק ביותר ראשון: מי שמחכה הכי הרבה זמן נבדק
    ראשון, ולא נדחק לתחתית הרשימה בכל הגשה חדשה.
    """
    return list(
        db.scalars(
            select(models.PayoutAccount)
            .where(models.PayoutAccount.status.in_(payout_status.PENDING_REVIEW))
            .order_by(
                models.PayoutAccount.submitted_at.asc(),
                models.PayoutAccount.id.asc(),
            )
        ).all()
    )


def approved_accounts(db: Session) -> list[models.PayoutAccount]:
    """חשבונות שכבר אושרו ולכן נעולים לבעלי האירוע.

    **בלי הרשימה הזו, "פתיחה מחדש" לא הייתה נגישה מהמסך בכלל**: חשבון
    שאושר יוצא מתור הבדיקה, ואז אין דרך להגיע אליו. החדש ביותר ראשון —
    בקשה לשינוי מגיעה בדרך כלל סמוך לאישור.
    """
    return list(
        db.scalars(
            select(models.PayoutAccount)
            .where(models.PayoutAccount.status == payout_status.VERIFIED)
            .order_by(
                models.PayoutAccount.veya_reviewed_at.desc(),
                models.PayoutAccount.id.desc(),
            )
        ).all()
    )
