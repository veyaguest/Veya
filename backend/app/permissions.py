"""מקור אמת יחיד להרשאות חבר-אירוע (מפיק/אולם) ברמת פעולה/טבלה.

הרשימות כאן חייבות להישאר זהות (כקבוצה, סדר לא משנה) לרשימות ה-ARRAY[...]
המקבילות ב-``backend/rls/02_policies.sql`` — הן שתי אכיפות עצמאיות של אותו
כלל: השכבה הזו נבדקת ב-API (``app/deps.py::EventAccess``) והשנייה נאכפת
בפועל ב-Postgres דרך ``app_has_any_event_permission``. יש טסט אוטומטי
(``tests/test_permission_alignment.py``) שמוודא שהן לא סוטות זו מזו.

כל קבוצה כאן = "איזו הרשאה (אחת לפחות) פותחת את הפעולה הזו לחבר-אירוע".
לבעלים/אדמין תמיד יש גישה מלאה בלי קשר לרשימות — זה נבדק בנפרד
(``event.owner_id == user.id or user.is_admin``), לא דרך הרשימות האלה.
"""
from app.schemas import PLANNER_PERMISSIONS, VENUE_PERMISSIONS  # noqa: F401 (re-export לנוחות)

# ── guests (טבלת המוזמנים) ───────────────────────────────────────────────
# קריאה: גם צופה-הושבה-בלבד (view_seating/edit_seating) צריך לראות שמות.
GUESTS_VIEW = ["view_guests", "edit_guests", "manage_seating", "view_seating", "edit_seating"]
# כתיבה (יצירה/עדכון/מחיקה/ייבוא): עריכת מוזמנים או ניהול הושבה בפועל.
GUESTS_WRITE = ["edit_guests", "manage_seating", "edit_seating"]

# ── הושבה (seating.py — קביעת/שינוי guests.table_number) ─────────────────
# תת-קבוצה של GUESTS_WRITE במכוון: שיבוץ לשולחן הוא פעולת-הושבה, לא עריכת
# פרטי מוזמן, אז edit_guests לבדו לא אמור לספיק (גם שאם ה-RLS עצמו, שהוא
# ברמת-שורה ולא ברמת-עמודה, כן מרשה — האפליקציה מדייקת יותר).
SEATING_WRITE = ["manage_seating", "edit_seating"]

# ── מפת האולם (hall.py — events.table_positions/hall_elements) ───────────
HALL_VIEW = ["view_seating", "edit_seating", "manage_seating", "manage_venue_data"]
HALL_WRITE = ["edit_seating", "manage_seating", "manage_venue_data"]

# ── clarifications (+ guests.constraints_parsed) ─────────────────────────
CLARIFICATIONS = ["edit_guests", "manage_seating"]

# ── messages (RSVP/תקשורת עם מוזמנים) ─────────────────────────────────────
# קריאה: גם מי שרק צריך לדעת "מה קרה" (view_reports/view_event).
MESSAGES_VIEW = ["send_messages", "view_reports", "view_event"]
# כתיבה (שליחה בפועל): send_messages בלבד — לא קיימת אצל אולמות.
MESSAGES_WRITE = ["send_messages"]

# ── automation_rules / message_templates (+ כל מה שנגזר מהן: due/track) ──
# כל endpoint באוטומציה נוגע בטבלאות האלה (ישירות או דרך _rules()/_templates()
# הפנימיים), אז דורש send_messages בלבד לכל הפעולות (קריאה וכתיבה כאחד).
AUTOMATION = ["send_messages"]

# ── events (SELECT) — איחוד כל ההרשאות המוכרות; מי שיש לו ולו אחת מהן ────
# רואה את פרטי האירוע הבסיסיים (שם, תאריך, אולם וכו').
EVENTS_VIEW = [
    "view_event", "view_guests", "view_seating", "view_reports",
    "edit_guests", "manage_seating", "send_messages",
    "edit_seating", "manage_venue_data",
]

# ── events (UPDATE) — איחוד ההרשאות שדרכן endpoint כלשהו (לא event.py עצמו,
# ראו owner_only שם) כותב שדה כלשהו על שורת האירוע: hall.py (הושבה/אולם),
# automation.py+messaging.py (rsvp_track_*/message_template), guests.py
# (group_notes). ה-RLS ברמת-שורה, אז הרשימה היא איחוד ולא צומת.
EVENTS_UPDATE = [
    "manage_seating", "edit_seating", "manage_venue_data",
    "send_messages", "edit_guests",
]
