"""שעון קבוע לבדיקות — כדי שהתוצאה לא תלויה ביום שבו מריצים אותן.

בדיקות רבות (שיחות, טלפנים, לוח הזמנים) בונות תרחיש סביב "היום": "סבב
שיחות שמגיע היום", "מסלול שהתחיל לפני 12 ימים". בשישי/שבת אין סבבים, ולכן
אותן בדיקות נכשלו בסוף השבוע בלי שום שינוי בקוד.

``install()`` מחליף את ``datetime.date`` / ``datetime.datetime`` בגרסה ששעונה
מתחיל ב-``ANCHOR`` (רביעי 23/9/2026, 10:00 בישראל) ומתקדם מכאן בקצב אמיתי —
כך סדר הזמנים בין פעולות נשמר. חייב לרוץ **לפני** ש-``app`` נטען (``from
datetime import datetime`` קושר את המחלקה ברגע הטעינה) — ולכן הוא ב-
``conftest.py`` וב-``e2e_seating.py``.

בדיקות שבודקות סוף שבוע (שאין שליחה/שיחה בשישי/שבת) מעבירות תאריך מפורש —
הן לא תלויות בשעון הזה.

``VEYA_REAL_CLOCK=1`` — ריצה על השעון האמיתי (לבדיקה ידנית בלבד).
"""
from __future__ import annotations

import datetime as _dt
import os

# רביעי 23/9/2026 07:00 UTC = 10:00 בישראל (שעון קיץ). יום חול באמצע השבוע.
ANCHOR = _dt.datetime(2026, 9, 23, 7, 0, 0)

_RealDate = _dt.date
_RealDateTime = _dt.datetime
_installed = False
_offset = _dt.timedelta(0)


class _DateMeta(type):
    # מופעים "אמיתיים" (מ-pydantic, SQLAlchemy וכו') עדיין נחשבים date.
    def __instancecheck__(cls, obj):
        return isinstance(obj, _RealDate)


class _DateTimeMeta(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, _RealDateTime)


class FixedDate(_RealDate, metaclass=_DateMeta):
    @classmethod
    def today(cls):
        d = FixedDateTime.now()
        return cls(d.year, d.month, d.day)


class FixedDateTime(_RealDateTime, metaclass=_DateTimeMeta):
    @classmethod
    def _wrap(cls, v):
        return cls(v.year, v.month, v.day, v.hour, v.minute, v.second, v.microsecond, v.tzinfo)

    @classmethod
    def utcnow(cls):
        return cls._wrap(_RealDateTime.utcnow() + _offset)

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls._wrap(_RealDateTime.now() + _offset)
        return cls._wrap(_RealDateTime.now(tz) + _offset)

    @classmethod
    def today(cls):
        return cls.now()


def install() -> None:
    """מפעיל את השעון הקבוע (פעם אחת; קריאה חוזרת לא עושה כלום)."""
    global _installed, _offset
    if _installed or os.environ.get("VEYA_REAL_CLOCK") == "1":
        return
    _offset = ANCHOR - _RealDateTime.utcnow()
    _dt.date = FixedDate
    _dt.datetime = FixedDateTime
    _installed = True
