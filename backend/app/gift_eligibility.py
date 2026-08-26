"""זכאות לשירות "מתנות באשראי" — **מקור האמת היחיד במערכת.**

כל מקום ששואל "האם מותר לאירוע הזה להשתמש במתנות באשראי?" עובר דרך כאן:
מסע האורח (``guest_journey``), מסך המתנות, תמונת המצב, ורינדור ההודעות.
אין בדיקה מקבילה בשום קובץ אחר — זו הנקודה שבה התשובה נקבעת.

## זכאות אינה "השירות פעיל"

שתי שאלות שונות, ובכוונה לא אותה פונקציה:

    is_eligible(event)   האם מותר לאירוע להשתמש בשירות.
    is_active(event, …)  האם השירות באמת פועל — כלומר גם מותר, וגם חשבון
                         קבלת המתנות עבר את האימות המלא.

אירוע יכול להיות זכאי לגמרי ועדיין לא לקבל שקל, כי בעלי האירוע טרם הזינו
או שטרם אושרו פרטי חשבון. הערבוב בין השניים הוא בדיוק סוג הבאג שגורם
להציג לזוג "השירות שלך פעיל" כשאין לאן להעביר את הכסף.

``is_active`` **מקבל את תוצאת האימות כפרמטר** ולא מחשב אותה: מקור האמת
לאימות הוא ``payout_service.is_fully_verified``, ואין סיבה ששני המודולים
יכירו זה את זה.

## איך זה בנוי, ולמה כך

התשובה מגיעה מ**שרשרת פותרים (resolvers) מסודרת לפי קדימות**. כל פותר
מחזיר ``True`` / ``False`` / ``None``, כאשר ``None`` פירושו "אין לי דעה,
תשאלו את הבא בתור". הראשון שיש לו דעה — קובע.

היום רשום פותר אחד בלבד:

    global_switch (קדימות 100)   מתג הסביבה ``VEYA_GIFT_ENABLED``.

זו התשובה הזמנית, והיא מספיקה: השירות עדיין לא שוחרר, ולכן "כל האירועים
או אף אחד" הוא תיאור נאמן של המציאות.

## איך תחובר מערכת החבילות בעתיד

בלי לגעת באף קובץ אחר במערכת — רק להוסיף פותר בקדימות גבוהה יותר:

    def _from_plan(event):
        plan = plans.for_event(event)          # כשתהיה מערכת חבילות
        if plan is None:
            return None                        # אין חבילה → תנו למתג להכריע
        return SERVICE in plan.included_services

    register_resolver("plan", _from_plan, precedence=10)

מרגע הרישום, כל הצרכנים — Guest Hub, מסך המתנות, תמונת המצב וההודעות —
מקבלים את התשובה החדשה מאליהם, כי כולם שואלים את אותה פונקציה.

**מה שבמפורש לא נבנה כאן:** אין מערכת חבילות, אין תמחור, ואין עמודת
זכאות בטבלת האירועים. הקובץ הזה מגדיר את *נקודת החיבור*, לא את החבילות.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional

from app import models

#: השירות היחיד שהמודול הזה עונה עליו היום. קבוע מפורש ולא מחרוזת חופשית,
#: כדי שכשיתווסף שירות שני יהיה ברור מה בדיוק צריך להתפצל.
SERVICE = "credit_gifts"

#: פותר: מקבל אירוע, מחזיר הכרעה או ``None`` ("אין לי דעה").
Resolver = Callable[[Optional[models.Event]], Optional[bool]]


@dataclass(frozen=True)
class Decision:
    """התשובה, יחד עם **מי** ענה אותה.

    ``source`` אינו קישוט: כשתהיה יותר משכבה אחת, "למה האירוע הזה לא
    זכאי?" היא שאלת תמיכה יומיומית, ובלי המקור התשובה היא ניחוש.
    """

    eligible: bool
    source: str


# ── שרשרת הפותרים ────────────────────────────────────────────────────────
# ממוינת לפי קדימות עולה — מספר נמוך = מכריע ראשון.
_RESOLVERS: list[tuple[int, str, Resolver]] = []


def register_resolver(name: str, resolver: Resolver, *, precedence: int) -> None:
    """רושם פותר. רישום חוזר של אותו שם **מחליף** את הקודם.

    ההחלפה מכוונת: בבדיקות רושמים פותר מזויף ומסירים אותו אחר כך, ובייצור
    אין תרחיש שבו רוצים שני פותרים באותו שם.
    """
    unregister_resolver(name)
    _RESOLVERS.append((precedence, name, resolver))
    _RESOLVERS.sort(key=lambda item: item[0])


def unregister_resolver(name: str) -> None:
    """מסיר פותר לפי שם. שם שאינו רשום — פעולה ריקה."""
    global _RESOLVERS
    _RESOLVERS = [item for item in _RESOLVERS if item[1] != name]


def registered_resolvers() -> tuple[str, ...]:
    """שמות הפותרים לפי סדר ההכרעה. לאבחון ולבדיקות."""
    return tuple(name for _, name, _ in _RESOLVERS)


# ── הפותר של היום ────────────────────────────────────────────────────────


def service_switch_on() -> bool:
    """מתג הסביבה ``VEYA_GIFT_ENABLED``.

    **ברירת המחדל היא כבוי.** מסך המתנה למוזמן הוא עדיין שלד ואין סליקה
    אמיתית; בלי המתג, כל מוזמן באירוע אמיתי בתוך חלון המתנה היה רואה
    כפתור שמוביל ל"נפתח בקרוב" — בדיוק בימים הרגישים ביותר של הזוג.

    נקרא בכל בקשה ולא נשמר במטמון, כדי שאפשר יהיה לשנות אותו בייצור בלי
    לפרוס מחדש.
    """
    return os.getenv("VEYA_GIFT_ENABLED", "").strip().lower() in ("1", "true", "yes")


def _from_global_switch(event: Optional[models.Event]) -> Optional[bool]:
    """הפותר האחרון בשרשרת — תמיד יש לו דעה, ולכן אף פעם אין "אין תשובה"."""
    return service_switch_on()


register_resolver("global_switch", _from_global_switch, precedence=100)


# ── ה-API של המודול ──────────────────────────────────────────────────────


def resolve(event: Optional[models.Event]) -> Decision:
    """מכריע זכאות, ומחזיר גם מי הכריע."""
    for _, name, resolver in _RESOLVERS:
        answer = resolver(event)
        if answer is not None:
            return Decision(eligible=bool(answer), source=name)
    # לא אמור לקרות כל עוד ``global_switch`` רשום, אבל אם מישהו יסיר את כל
    # הפותרים — ברירת המחדל היא **סגור**. שירות שנוגע בכסף לא נפתח בגלל
    # תקלת הגדרה.
    return Decision(eligible=False, source="default_closed")


def is_eligible(event: Optional[models.Event]) -> bool:
    """האם מותר לאירוע הזה להשתמש ב"מתנות באשראי".

    **זו הפונקציה שכל המערכת קוראת לה.** אין להעתיק את ההיגיון שמאחוריה.
    """
    return resolve(event).eligible


def is_active(event: Optional[models.Event], *, account_verified: bool) -> bool:
    """האם השירות באמת פועל — זכאי **וגם** חשבון קבלת המתנות מאומת.

    ``account_verified`` מגיע מ-``payout_service.is_fully_verified``.
    """
    return is_eligible(event) and account_verified
