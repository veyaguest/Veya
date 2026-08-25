"""בדיקות למנוע מסע האורח — מתי כל פעולה נפתחת בקישור של המוזמן.

הקישור ``/confirm/{token}`` קבוע לכל אורך חיי האירוע; מה שמשתנה זה אילו
פעולות פתוחות בו. הקובץ הזה נועל את ההתנהגות הזו, ובמיוחד את שני הדברים
שהכי קל לשבור בלי לשים לב:

1. **גבולות חלון המתנה** — פתיחה ב-00:00 שלושה ימים לפני, סגירה ב-10:00
   בבוקר שאחרי. שניהם בשעון ישראל, ושניהם נבדקים משני צדיהם *לדקה*.
2. **``?action=gift`` הוא ניתוב, לא הרשאה** — מוזמן שינחש את הפרמטר מחוץ
   לחלון לא יקבל כלום, כי הזמינות מחושבת בשרת ולא בדפדפן.

הרצה: ``venv/bin/python tests/test_guest_journey.py`` (עצמאי, בלי pytest).
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# מדליקים את מתג הפיצ'ר לכל הקובץ: כאן בודקים את *החלון*, לא את שאלת
# השחרור. הגדרה לפני הייבוא, כי הבדיקה של המתג עצמה קוראת אותו בזמן ריצה.
os.environ["VEYA_GIFT_ENABLED"] = "1"

from app import guest_journey as gj  # noqa: E402
from fastapi import HTTPException  # noqa: E402

EVENT_DAY = date(2026, 11, 12)      # יום חמישי, חורף (שעון ישראל = UTC+2)


class FakeEvent:
    """מינימום השדות שמנוע המסע נוגע בהם."""

    def __init__(self, event_date="2026-11-12", invite_image=None, venue_address=""):
        self.event_date = event_date
        self.invite_image = invite_image
        self.venue_address = venue_address


def il(day: date, hour: int = 12, minute: int = 0) -> datetime:
    """רגע בשעון *ישראל*.

    בדיקות הגבול נכתבות בשעון המקומי ולא ב-UTC בכוונה: ההחלטה המוצרית
    מנוסחת בשעון ישראל ("10:00 בבוקר"), וכל תרגום ידני ל-UTC היה מכניס
    לבדיקה את אותה טעות שהיא אמורה לתפוס.
    """
    tz = gj._israel_tz()
    stamp = datetime(day.year, day.month, day.day, hour, minute)
    return stamp.replace(tzinfo=tz) if tz is not None else stamp


def _open_at(moment: datetime) -> bool:
    return gj.gift_window_is_open(FakeEvent(), now=moment)


def _open_days_before(days: int, hour: int = 12) -> bool:
    return _open_at(il(EVENT_DAY - timedelta(days=days), hour))


# ---- גבולות החלון: יום אחר יום -------------------------------------------

def test_gift_window_day_by_day() -> None:
    assert _open_days_before(30) is False, "חודש לפני — סגור"
    assert _open_days_before(5) is False, "5 ימים לפני — סגור"
    assert _open_days_before(4) is False, "4 ימים לפני — עדיין סגור"
    assert _open_days_before(3) is True, "3 ימים לפני — פתוח"
    assert _open_days_before(2) is True, "יומיים לפני — פתוח"
    assert _open_days_before(1) is True, "יום לפני — פתוח"
    assert _open_days_before(0) is True, "יום האירוע — פתוח"
    print("✓ חלון המתנה יום-אחר-יום: סגור עד 4 ימים לפני, פתוח מ-3 ועד יום האירוע")


# ---- רגע הפתיחה: 00:00, שלושה ימים לפני ---------------------------------

def test_opening_moment_is_midnight_three_days_before() -> None:
    open_day = EVENT_DAY - timedelta(days=3)          # 09/11
    day_before_open = open_day - timedelta(days=1)    # 08/11

    assert _open_at(il(day_before_open, 12, 0)) is False, "08/11 בצהריים — סגור"
    assert _open_at(il(day_before_open, 23, 59)) is False, "08/11 ב-23:59 — עדיין סגור"
    assert _open_at(il(open_day, 0, 0)) is True, "09/11 ב-00:00 — רגע הפתיחה"
    assert _open_at(il(open_day, 0, 1)) is True, "09/11 ב-00:01 — פתוח"

    opens, _ = gj.gift_window_bounds(FakeEvent())
    assert opens == il(open_day, 0, 0), f"גבול הפתיחה שגוי: {opens}"
    print("✓ רגע הפתיחה: 09/11 בדיוק ב-00:00 שעון ישראל, ולא דקה לפני")


# ---- יום האירוע ----------------------------------------------------------

def test_event_day_is_open_all_day() -> None:
    for hour, minute in ((0, 0), (9, 0), (19, 30), (23, 59)):
        assert _open_at(il(EVENT_DAY, hour, minute)) is True, (
            f"יום האירוע ב-{hour:02d}:{minute:02d} חייב להיות פתוח"
        )
    print("✓ יום האירוע: פתוח מחצות ועד 23:59, כולל בזמן האירוע עצמו")


# ---- הבוקר שאחרי: 09:59 פתוח, 10:00 סגור --------------------------------

def test_morning_after_closes_at_ten() -> None:
    after = EVENT_DAY + timedelta(days=1)   # 13/11

    assert _open_at(il(after, 0, 0)) is True, "13/11 בחצות — עדיין פתוח"
    assert _open_at(il(after, 9, 0)) is True, "13/11 ב-09:00 — פתוח"
    assert _open_at(il(after, 9, 59)) is True, "13/11 ב-09:59 — פתוח (הדקה האחרונה)"
    assert _open_at(il(after, 10, 0)) is False, "13/11 ב-10:00 — נסגר בדיוק"
    assert _open_at(il(after, 10, 1)) is False, "13/11 ב-10:01 — סגור"
    assert _open_at(il(after, 18, 0)) is False, "13/11 בערב — סגור"

    _, closes = gj.gift_window_bounds(FakeEvent())
    assert closes == il(after, 10, 0), f"גבול הסגירה שגוי: {closes}"
    print("✓ הבוקר שאחרי: פתוח עד 09:59, נסגר ב-10:00 בדיוק (טווח חצי-פתוח)")


def test_later_days_stay_closed() -> None:
    for days in (2, 3, 7, 30):
        assert _open_at(il(EVENT_DAY + timedelta(days=days), 9, 0)) is False, (
            f"{days} ימים אחרי האירוע — חייב להיות סגור, גם בבוקר"
        )
    print("✓ יומיים ואילך אחרי האירוע: סגור לצמיתות, גם לפני 10:00")


# ---- אין תאריך / פורמטים ------------------------------------------------

def test_no_date_keeps_gift_closed() -> None:
    assert gj.gift_window_is_open(FakeEvent(event_date=""), now=il(EVENT_DAY)) is False
    assert gj.gift_window_is_open(FakeEvent(event_date="שיבוש"), now=il(EVENT_DAY)) is False
    assert gj.gift_window_bounds(FakeEvent(event_date="")) is None
    assert gj.days_until_event(FakeEvent(event_date="")) is None
    print("✓ אירוע בלי תאריך תקין: המתנה סגורה (אי אפשר לדעת — ולכן לא פותחים)")


def test_supports_both_stored_date_formats() -> None:
    """``parse_event_date`` הקיים תומך גם ב-DD/MM/YYYY — החלון חייב לכבד את זה."""
    iso = FakeEvent(event_date="2026-11-12")
    slash = FakeEvent(event_date="12/11/2026")
    assert gj.gift_window_bounds(iso) == gj.gift_window_bounds(slash)
    for moment in (il(EVENT_DAY - timedelta(days=3)), il(EVENT_DAY + timedelta(days=1), 9, 59)):
        assert gj.gift_window_is_open(iso, now=moment) == gj.gift_window_is_open(slash, now=moment)
    print("✓ שני פורמטי התאריך השמורים ב-DB מתנהגים זהה")


# ---- אזור הזמן של ישראל --------------------------------------------------

def test_israel_timezone_conversion() -> None:
    """הרגע נקבע לפי שעון ישראל — לא לפי UTC, ובשני עונות השנה."""
    # חורף (UTC+2): 21:59Z = 23:59 בישראל (עדיין 12/11), 22:00Z = 00:00 ב-13/11.
    assert gj.today_in_israel(datetime(2026, 11, 12, 21, 59)) == date(2026, 11, 12)
    assert gj.today_in_israel(datetime(2026, 11, 12, 22, 0)) == date(2026, 11, 13)
    # קיץ (UTC+3): המעבר קורה שעה מוקדם יותר ב-UTC.
    assert gj.today_in_israel(datetime(2026, 7, 1, 20, 59)) == date(2026, 7, 1)
    assert gj.today_in_israel(datetime(2026, 7, 1, 21, 0)) == date(2026, 7, 2)

    # שעת הסגירה נמדדת בשעון המקומי בשתי העונות. 10:00 בישראל =
    # 08:00Z בחורף אבל 07:00Z בקיץ — בדיוק הבאג שהמרה ל-UTC הייתה יוצרת.
    winter = FakeEvent(event_date="2026-11-12")
    assert gj.gift_window_is_open(winter, now=datetime(2026, 11, 13, 7, 59)) is True
    assert gj.gift_window_is_open(winter, now=datetime(2026, 11, 13, 8, 0)) is False

    summer = FakeEvent(event_date="2026-07-01")
    assert gj.gift_window_is_open(summer, now=datetime(2026, 7, 2, 6, 59)) is True
    assert gj.gift_window_is_open(summer, now=datetime(2026, 7, 2, 7, 0)) is False
    print("✓ אזור זמן: 10:00 נמדדת בשעון ישראל — 08:00Z בחורף, 07:00Z בקיץ")


# ---- ?action=gift — ניתוב, לא הרשאה --------------------------------------

def test_action_gift_is_not_authorization() -> None:
    ev = FakeEvent(venue_address="הרצל 5, תל אביב")
    early = il(EVENT_DAY - timedelta(days=10))
    inside = il(EVENT_DAY - timedelta(days=2))
    too_late = il(EVENT_DAY + timedelta(days=1), 10, 0)

    # מחוץ לחלון (משני הכיוונים): לא זמין, והשער חוסם — גם אם ה-URL מבקש.
    for moment, label in ((early, "מוקדם מדי"), (too_late, "אחרי 10:00 בבוקר שאחרי")):
        assert gj.compute_actions(ev, has_calendar=True, now=moment).gift is False
        try:
            gj.assert_action_allowed(ev, "gift", has_calendar=True, now=moment)
            raise AssertionError(f"?action=gift {label} היה אמור להיחסם ב-403")
        except HTTPException as exc:
            assert exc.status_code == 403, f"ציפינו ל-403, קיבלנו {exc.status_code}"

    # בתוך החלון: זמינה, והשער מאשר.
    assert gj.compute_actions(ev, has_calendar=True, now=inside).gift is True
    gj.assert_action_allowed(ev, "gift", has_calendar=True, now=inside)

    # פעולה שאינה ברשימת הניתוב כלל.
    try:
        gj.assert_action_allowed(ev, "admin", has_calendar=True, now=inside)
        raise AssertionError("פעולה לא מוכרת הייתה אמורה להידחות")
    except HTTPException as exc:
        assert exc.status_code == 404

    # פעולה שאין לה נתונים לא נפתחת גם היא (אירוע בלי כתובת → ניווט).
    try:
        gj.assert_action_allowed(FakeEvent(venue_address=""), "navigation",
                                 has_calendar=True, now=inside)
        raise AssertionError("ניווט בלי כתובת היה אמור להיחסם")
    except HTTPException as exc:
        assert exc.status_code == 403
    print("✓ ?action= הוא ניתוב בלבד: מחוץ לחלון → 403 משני הכיוונים")


# ---- מתג הפיצ'ר ----------------------------------------------------------

def test_feature_flag_gates_release_not_window() -> None:
    """המתג שולט על *שחרור* הפיצ'ר, לא על נכונות החלון."""
    ev = FakeEvent()
    inside = il(EVENT_DAY - timedelta(days=1))
    previous = os.environ.get("VEYA_GIFT_ENABLED", "")
    try:
        os.environ["VEYA_GIFT_ENABLED"] = ""
        assert gj.gift_is_open(ev, now=inside) is False, "מתג כבוי → המתנה לא נפתחת"
        assert gj.gift_window_is_open(ev, now=inside) is True, "אבל החלון עצמו עדיין נכון"
        assert gj.compute_actions(ev, has_calendar=True, now=inside).gift is False
        os.environ["VEYA_GIFT_ENABLED"] = "1"
        assert gj.gift_is_open(ev, now=inside) is True, "מתג דלוק → נפתחת"
    finally:
        os.environ["VEYA_GIFT_ENABLED"] = previous
    print("✓ מתג הפיצ'ר: חוסם שחרור, בלי לגעת בנכונות החלון")


# ---- שאר הפעולות לא הושפעו ----------------------------------------------

def test_other_actions_unchanged_by_gift_logic() -> None:
    ev = FakeEvent(invite_image="/media/x", venue_address="הרצל 5")
    moments = [
        il(EVENT_DAY - timedelta(days=30)),
        il(EVENT_DAY - timedelta(days=3)),
        il(EVENT_DAY),
        il(EVENT_DAY + timedelta(days=1), 9, 59),
        il(EVENT_DAY + timedelta(days=1), 10, 0),
        il(EVENT_DAY + timedelta(days=30)),
    ]
    for moment in moments:
        a = gj.compute_actions(ev, has_calendar=True, now=moment)
        assert a.invitation is True, f"ההזמנה נעלמה ב-{moment}"
        assert a.calendar is True, f"היומן נעלם ב-{moment}"
        assert a.navigation is True, f"הניווט נעלם ב-{moment}"
        assert a.rsvp is True, f"אישור ההגעה נעלם ב-{moment}"
    print("✓ הזמנה/יומן/ניווט/אישור הגעה לא הושפעו משינוי חלון המתנה")


if __name__ == "__main__":
    test_gift_window_day_by_day()
    test_opening_moment_is_midnight_three_days_before()
    test_event_day_is_open_all_day()
    test_morning_after_closes_at_ten()
    test_later_days_stay_closed()
    test_no_date_keeps_gift_closed()
    test_supports_both_stored_date_formats()
    test_israel_timezone_conversion()
    test_action_gift_is_not_authorization()
    test_feature_flag_gates_release_not_window()
    test_other_actions_unchanged_by_gift_logic()
    print("\nכל בדיקות מסע האורח עברו ✓")
