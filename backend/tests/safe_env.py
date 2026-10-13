"""בידוד הבדיקות מהגדרות WhatsApp אמיתיות.

הבעיה (2026-10-12): ``app/database.py`` טוען את ``backend/.env`` בעלייה. ברגע
שבעלי המערכת הגדירו שם ``WHATSAPP_MODE=meta_test`` וטוקן אמיתי לבדיקה ידנית,
גם הבדיקות האוטומטיות רצו במצב הזה — עם הטוקן האמיתי. שום דבר לא יצא ל-Meta
(הטלפונים בבדיקות לא ברשימה המורשית), אבל לבדיקות אסור לתלות בזה.

הפתרון: לפני שמשהו מ-``app`` נטען, כל משתני ה-WhatsApp מקבלים ערך בטוח —
``mock`` וערכים ריקים. ``load_dotenv`` (בלי ``override``) לא דורס משתנה שכבר
קיים בסביבה, *גם אם הוא ריק* — ולכן הקובץ לא יכול "למלא" אותם. ההחלה
דורסת גם ערכים שהגיעו מהטרמינל.

נקרא מ-``tests/conftest.py`` (כל הרצה של pytest) ומ-``tests/e2e_seating.py``
(הרצה עצמאית של קובץ בדיקה). בדיקת האינטגרציה האמיתית
(``test_whatsapp_meta_integration.py``) קוראת את ``.env`` בעצמה, ורק כשמפעילים
אותה במפורש.
"""
from __future__ import annotations

import os

WHATSAPP_SAFE_ENV: dict[str, str] = {
    "WHATSAPP_MODE": "mock",
    "WHATSAPP_ACCESS_TOKEN": "",
    "WHATSAPP_TOKEN": "",
    "WHATSAPP_PHONE_NUMBER_ID": "",
    "WHATSAPP_PHONE_ID": "",
    "WHATSAPP_BUSINESS_ACCOUNT_ID": "",
    "WHATSAPP_TEST_RECIPIENTS": "",
    "WHATSAPP_APP_SECRET": "",
    "WHATSAPP_VERIFY_TOKEN": "",
    "WHATSAPP_GRAPH_API_VERSION": "",
    # עיבוד הודעות נכנסות ועדכון RSVP מהן — כבויים (בדיקות שבודקות אותם מדליקות במפורש).
    "WHATSAPP_WEBHOOK_INBOUND": "",
    "WHATSAPP_INBOUND_RSVP": "",
}


def apply() -> None:
    """דורס את כל משתני ה-WhatsApp בערכים בטוחים. idempotent."""
    os.environ.update(WHATSAPP_SAFE_ENV)
