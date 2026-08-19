"""תפקידי משתמש — מקור אמת יחיד לציר ``User.account_type``.

במערכת יש **שני צירים נפרדים** של הרשאה, ואין ליצור ציר שלישי:

1. ``User.is_admin``      — אדמין-על. רואה ומנהל הכול, בכל אירוע.
2. ``User.account_type``  — *מי* המשתמש. ``couple`` (ברירת מחדל) / ``planner``
   (מפיק) / ``venue`` (אולם) / ``phone_agent`` (טלפן).

``phone_agent`` הוא תפקיד **מגביל**, לא מרחיב: הוא לא מוסיף שום הרשאה לצד
מה שכבר קיים, אלא מסמן משתמש שכל הגישה שלו מצטמצמת למסך השיחות בלבד. לכן
האכיפה שלו היא שלילית ומרוכזת בשתי נקודות-צוואר קיימות:

- ``app/deps.py::EventAccess``    — כל endpoint שתלוי-אירוע (מוזמנים, הושבה,
  אולם, הודעות, אוטומציה, סטטיסטיקות) עובר דרכה. טלפן נדחה שם *לפני* בדיקת
  הבעלות, כך שגם אם במקרה יש לו אירוע משלו — הוא לא מגיע לממשק הבעלים.
- ``app/auth.py::get_current_owner`` — מעט ה-endpoints שאינם תלויי-אירוע
  (יצירת אירוע, חיפוש אולמות, ספריית ההודעות, ניהול חברי-אירוע).

ההיפך — מה שטלפן כן רשאי — נאכף ב-``app/auth.py::get_current_caller``,
שמשמש **רק** את ה-router של ``/admin/call-center``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover — לייבוא טיפוסים בלבד
    from app import models

# ── ערכי account_type ────────────────────────────────────────────────────
COUPLE = "couple"
PLANNER = "planner"
VENUE = "venue"
PHONE_AGENT = "phone_agent"

ACCOUNT_TYPES = (COUPLE, PLANNER, VENUE, PHONE_AGENT)

# תוויות בעברית — לתצוגה בפאנל האדמין. מקור אמת יחיד; ה-Frontend מחזיק את
# אותן מחרוזות בקובץ אחד (frontend/src/types.ts + AdminPage).
ACCOUNT_TYPE_LABELS = {
    COUPLE: "זוג",
    PLANNER: "מפיק",
    VENUE: "אולם",
    PHONE_AGENT: "טלפן",
}


def is_phone_agent(user: "models.User") -> bool:
    """האם המשתמש הוא טלפן (איש צוות שמבצע שיחות אישורי הגעה בלבד)."""
    return (getattr(user, "account_type", "") or "") == PHONE_AGENT


def can_make_calls(user: "models.User") -> bool:
    """מי רשאי לעבוד במסך השיחות: אדמין-על, או טלפן.

    אדמין נשאר בפנים כי מסך ה-Call Center נבנה במקור עבורו והוא לא נלקח ממנו.
    """
    return bool(getattr(user, "is_admin", False)) or is_phone_agent(user)
