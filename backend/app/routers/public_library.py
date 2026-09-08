"""ספריית הנוסחים הציבורית — קריאה בלבד מאותן שורות שהמוצר משתמש בהן.

## מקור אמת אחד

הנוסחים חיים ב-``models.MessageDefaultOption`` ומנוהלים במסך האדמין. הנתיב
כאן **לא מחזיק עותק שלהם** ולא מגדיר תוכן משלו — הוא שולף את אותן שורות
שהזוג רואה בתוך המערכת (``GET /communication/sequence/{type}/options``),
רק בלי אימות ובלי הקשר של אירוע. כשהבעלים עורך נוסח באדמין, האתר הציבורי
משתנה איתו.

## מה **לא** נחשף כאן

``postponement`` — נוסחי "אירוע נדחה". במסלול המחובר הם נפתחים רק אחרי
שנוהל דחייה אושר (ראו ``routers/communication.get_message_options``), וזה
תוכן שנשלח למשפחה ברגע רגיש. אין סיבה שהוא ישב בדף שיווקי, ולכן הוא מסונן
כאן במפורש ולא "במקרה" — ראו ``PUBLIC_MESSAGE_TYPES``.

שורות ריקות (``content == ""``) ושורות לא פעילות אינן מוחזרות: המוצר עדיין
לא מילא את כל השילובים, וקטגוריה ריקה בדף ציבורי היא הבטחה לתוכן שאינו קיים.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import Depends

from app import communication, event_terms, models
from app.database import get_db
from app.ratelimit import RateLimiter, client_ip

router = APIRouter(prefix="/public/library", tags=["public-library"])

#: סוגי ההודעה שמותר לחשוף בדף ציבורי — הרצף הקבוע בלבד.
#: ``postponement`` אינו כאן במכוון (ראו ההסבר בראש הקובץ).
PUBLIC_MESSAGE_TYPES: tuple[str, ...] = tuple(communication.MESSAGE_TYPES)

#: ביטויים שפוסלים נוסח מהאתר הציבורי.
#:
#: **למה זה קיים:** חלק מנוסחי "יום האירוע" מזכירים מתנה באשראי וכוללים את
#: המשתנה ``{{gift_link}}``. הפיצ'ר אינו משוחרר (``VEYA_GIFT_ENABLED`` כבוי),
#: ויש כלל מוצרי נעול שאין להציג אותו בשיווק — גם לא כרמז. בלי הסינון הזה,
#: ברגע שהבעלים ימלא את הקטגוריה הזו באדמין, ה-build הבא היה מפרסם את
#: ההזכרה הזו לאתר הציבורי **בלי שאף אחד יבחין**.
#:
#: הסינון חל על האתר הציבורי בלבד. במסלול המחובר הנוסחים נשארים כפי שהם.
BLOCKED_PHRASES: tuple[str, ...] = (
    "gift_link",
    "מתנה באשראי",
    "מתנות באשראי",
)


def _is_publishable(content: str) -> bool:
    """האם מותר להציג את הנוסח הזה בדף ציבורי."""
    lowered = content.lower()
    return not any(p.lower() in lowered for p in BLOCKED_PHRASES)


#: קיבוץ סוגי ההודעה לקטגוריות תצוגה. שלוש התזכורות הן קטגוריה אחת: הן
#: אותו סוג טקסט בשלושה תזמונים, ושלושה עמודים נפרדים היו מפצלים את אותו
#: תוכן בלי שום ערך לקורא.
CATEGORIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("invitations", "נוסחי הזמנה", ("invitation",)),
    ("rsvp", "נוסחי בקשת אישור הגעה", ("rsvp_request",)),
    ("reminders", "נוסחי תזכורת", ("reminder_1", "reminder_2", "final_reminder")),
    ("event-day", "נוסחי יום האירוע", ("event_day",)),
    ("thanks", "נוסחי תודה", ("thank_you",)),
)

library_limiter = RateLimiter(
    max_hits=60,
    window=60.0,
    message="בוצעו יותר מדי בקשות מהכתובת הזו. אפשר לנסות שוב בעוד דקה.",
)


class WordingOut(BaseModel):
    event_type: str
    event_type_label: str
    message_type: str
    message_type_label: str
    category: str
    option_number: int
    tone: str
    title: str
    content: str


class LibraryOut(BaseModel):
    #: קטגוריות שיש בהן תוכן בפועל, לפי הסדר של ``CATEGORIES``.
    categories: list["CategoryOut"]
    total: int


class CategoryOut(BaseModel):
    key: str
    label: str
    message_types: list[str]
    #: סוגי האירוע שיש להם נוסחים בקטגוריה הזו — לבניית הפילטר.
    event_types: list["EventTypeOut"]
    wordings: list[WordingOut]


class EventTypeOut(BaseModel):
    key: str
    label: str
    count: int


LibraryOut.model_rebuild()
CategoryOut.model_rebuild()


def _category_of(message_type: str) -> Optional[str]:
    for key, _label, types in CATEGORIES:
        if message_type in types:
            return key
    return None


def _event_label(event_type: str) -> str:
    """תווית סוג האירוע מהלקסיקון — לא מחרוזת שנכתבת כאן."""
    terms = event_terms.EVENT_TERMS.get(event_type)
    if terms is None:
        return event_type
    return getattr(terms, "label", None) or (
        terms.get("label") if isinstance(terms, dict) else event_type
    )


@router.get("", response_model=LibraryOut)
def get_public_library(request: Request, db: Session = Depends(get_db)) -> LibraryOut:
    """כל הנוסחים הפעילים, מקובצים לקטגוריות.

    מוחזרות **רק** קטגוריות שיש בהן תוכן. אם הבעלים עדיין לא מילא נוסחי
    תודה, למשל, הקטגוריה פשוט לא מופיעה — במקום להציג מדף ריק.
    """
    ip = client_ip(request)
    library_limiter.check(ip)
    library_limiter.record_fail(ip)

    rows = db.scalars(
        select(models.MessageDefaultOption)
        .where(models.MessageDefaultOption.is_active == True)  # noqa: E712
        .where(models.MessageDefaultOption.content != "")
        .where(models.MessageDefaultOption.message_type.in_(PUBLIC_MESSAGE_TYPES))
        .order_by(
            models.MessageDefaultOption.event_type,
            models.MessageDefaultOption.message_type,
            models.MessageDefaultOption.option_number,
        )
    ).all()

    by_category: dict[str, list[WordingOut]] = {}
    for row in rows:
        cat = _category_of(row.message_type)
        if cat is None:  # pragma: no cover — נחסם כבר ב-in_() למעלה
            continue
        if not _is_publishable(row.content):
            continue
        by_category.setdefault(cat, []).append(
            WordingOut(
                event_type=row.event_type,
                event_type_label=_event_label(row.event_type),
                message_type=row.message_type,
                message_type_label=communication.MESSAGE_TYPE_LABELS.get(
                    row.message_type, row.message_type
                ),
                category=cat,
                option_number=row.option_number,
                tone=row.tone or "",
                title=row.title or "",
                content=row.content,
            )
        )

    categories: list[CategoryOut] = []
    for key, label, types in CATEGORIES:
        items = by_category.get(key, [])
        if not items:
            continue
        counts: dict[str, int] = {}
        labels: dict[str, str] = {}
        for w in items:
            counts[w.event_type] = counts.get(w.event_type, 0) + 1
            labels[w.event_type] = w.event_type_label
        categories.append(
            CategoryOut(
                key=key,
                label=label,
                message_types=list(types),
                event_types=[
                    EventTypeOut(key=k, label=labels[k], count=c)
                    for k, c in sorted(counts.items(), key=lambda kv: -kv[1])
                ],
                wordings=items,
            )
        )

    return LibraryOut(categories=categories, total=sum(len(c.wordings) for c in categories))
