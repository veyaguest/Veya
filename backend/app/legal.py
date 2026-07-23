"""גרסאות המסמכים המשפטיים + ניהול ההסכמות (ConsentRecord).

מקור האמת היחיד לגרסה הנוכחית של כל מסמך — כל שינוי מהותי במסמך ב-``legal/``
מחייב עדכון התאריך כאן, וזה מה שמפעיל את דגל ``needs_reconsent`` למשתמשים
שאישרו גרסה ישנה (ראו legal/11-dev-compliance-tasklist.md, Backend #2).

בכוונה **בלי** מנגנון Versioning מורכב (טבלת גרסאות/דיפים) — מחרוזת תאריך
קבועה מספיקה בשלב הזה, בהתאם לעקרון "פשוט וזול על פני מושלם".
"""
from typing import Literal, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models

ConsentType = Literal["terms", "privacy", "marketing"]

# עדכנו את התאריך כאן בכל שינוי מהותי במסמך המתאים ב-legal/. משתמשים שאישרו
# תאריך קודם יסומנו needs_reconsent=True (GET /auth/me) עד שיאשרו מחדש.
LEGAL_DOCS_VERSION: dict[ConsentType, str] = {
    "terms": "2026-07-23",
    "privacy": "2026-07-23",
    "marketing": "2026-07-23",
}

# הסכמות חובה לפני יצירת חשבון (התיבה היחידה בהרשמה מכסה את שתיהן יחד —
# ראו legal/README.md §11). "marketing" נפרד ואופציונלי, לא כאן.
REQUIRED_CONSENT_TYPES: tuple[ConsentType, ...] = ("terms", "privacy")


def record_consent(
    db: Session,
    user_id: int,
    consent_type: ConsentType,
    *,
    source: str = "signup_form",
    ip: Optional[str] = None,
) -> None:
    """מוסיף שורת הסכמה חדשה (לא עדכון-במקום — היסטוריה מלאה נשמרת).

    אינו מבצע commit — הקורא אחראי לכך יחד עם שאר העבודה (עקבי עם audit.record).
    """
    db.add(models.ConsentRecord(
        user_id=user_id,
        consent_type=consent_type,
        document_version=LEGAL_DOCS_VERSION[consent_type],
        source=source,
        ip=ip,
    ))


def needs_reconsent(db: Session, user_id: int) -> bool:
    """True אם למשתמש חסרה הסכמה לגרסה הנוכחית של אחד ממסמכי החובה.

    בודק רק את ההסכמה *האחרונה* שנרשמה לכל סוג (לא כל ההיסטוריה) — משתמש
    שאישר גרסה ישנה ואז אישר שוב את הגרסה החדשה נחשב עדכני.
    """
    for consent_type in REQUIRED_CONSENT_TYPES:
        latest = db.scalars(
            select(models.ConsentRecord)
            .where(
                models.ConsentRecord.user_id == user_id,
                models.ConsentRecord.consent_type == consent_type,
            )
            .order_by(models.ConsentRecord.accepted_at.desc())
        ).first()
        if latest is None or latest.document_version != LEGAL_DOCS_VERSION[consent_type]:
            return True
    return False
