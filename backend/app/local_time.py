"""שעון ישראל — מקור אמת יחיד ל"איזה יום זה עכשיו" בחישובי תפעול.

כל הזמנים במסד נשמרים כ-UTC נאיבי (``datetime.utcnow``). אבל "היום", "מחר"
ו"אתמול" של טלפן, של סבב שיחות ושל אדמין הם ימים **בישראל**: בלי ההמרה, בין
חצות לשלוש לפנות בוקר המערכת עדיין חושבת שזה אתמול.

מודול עלה (בלי תלות במודולי VEYA אחרים) כדי שגם ``rsvp_timeline`` וגם
``call_center`` יוכלו לייבא אותו בלי ייבוא מעגלי.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

ISRAEL_TIMEZONE = "Asia/Jerusalem"


def _tz():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo(ISRAEL_TIMEZONE)
    except Exception:  # noqa: BLE001 — בלי מסד אזורי זמן נשארים ב-UTC
        return None


def to_israel(moment: datetime) -> datetime:
    """UTC נאיבי (או aware) → שעון ישראל, **נאיבי** (להשוואות פשוטות)."""
    tz = _tz()
    if tz is None:
        return moment.replace(tzinfo=None)
    aware = moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment
    return aware.astimezone(tz).replace(tzinfo=None)


def israel_date(now: Optional[datetime] = None) -> date:
    """התאריך בישראל ברגע ``now`` (UTC). ברירת מחדל: עכשיו."""
    return to_israel(now or datetime.utcnow()).date()


def israel_day_start_utc(day: date) -> datetime:
    """חצות של יום ישראלי, כ-UTC נאיבי — לסינון עמודות ``created_at``."""
    tz = _tz()
    local_midnight = datetime.combine(day, time.min)
    if tz is None:
        return local_midnight
    return local_midnight.replace(tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)


def israel_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    """[תחילת היום, תחילת היום הבא) בישראל, כ-UTC נאיבי."""
    return israel_day_start_utc(day), israel_day_start_utc(day + timedelta(days=1))
