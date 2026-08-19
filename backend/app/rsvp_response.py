"""תשובת אישור-הגעה של מוזמן — מקור אמת יחיד להחלת התשובה על השורה שלו.

למה מודול נפרד: אותה תשובה בדיוק יכולה להגיע משני ערוצים —
- המוזמן לוחץ בעצמו בקישור האישי (``routers/confirm.py``, WhatsApp), ו-
- האדמין מסמן במקומו בשיחת טלפון (``routers/call_center.py``).

שניהם קוראים ל-``apply_response`` כאן, כך שאין שתי לוגיקות שיכולות לסטות
זו מזו. הפונקציה טהורה: היא רק מעדכנת את אובייקט המוזמן ומחזירה תווית
עברית לתיעוד — בלי commit, בלי כתיבה ליומן, בלי שליחת הודעות.
"""
from __future__ import annotations

from typing import Optional

from app import models

# תקרה סבירה לכמות מאשרים בתשובה אחת — הגנה מפני שימוש לרעה/טעות הקלדה.
MAX_CONFIRMED_COUNT = 30

DECISIONS = ("confirmed", "declined", "maybe")


def apply_response(
    guest: models.Guest,
    decision: str,
    *,
    count: Optional[int] = None,
    note: Optional[str] = None,
) -> str:
    """מחיל תשובת אישור-הגעה על המוזמן ומחזיר תווית עברית לתיעוד.

    ``decision`` — אחד מ-``DECISIONS``.
    ``count``    — כמה אנשים מגיעים בפועל (רלוונטי רק ל-``confirmed``).
                   ``None`` => כמה שהוזמנו (``party_size``).
    ``note``     — הערת המוזמן. ``None`` = לא לגעת בהערה הקיימת;
                   מחרוזת ריקה = לנקות אותה.
    """
    if decision == "maybe":
        guest.rsvp_status = "maybe"
        guest.confirmed_count = None
        label = "סימן/ה 'אולי'"
    elif decision == "confirmed":
        # ברירת מחדל = כמה שהוזמנו. אפשר גם מעבר לזה (משפחה שגדלה), עד תקרה.
        value = count if count is not None else guest.party_size
        value = max(1, min(value, MAX_CONFIRMED_COUNT))
        guest.rsvp_status = "confirmed"
        guest.confirmed_count = value
        label = f"אישר/ה הגעה ({value})"
    elif decision == "declined":
        guest.rsvp_status = "declined"
        guest.confirmed_count = 0
        label = "ביטל/ה הגעה"
    else:
        raise ValueError(f"תשובת אישור הגעה לא מוכרת: {decision}")

    if note is not None:
        cleaned = note.strip()
        guest.guest_note = cleaned or None

    return label
