"""מועד הסגירה כש"היום" הוא שישי או שבת.

הבאג (נמצא 2026-09-28): המנוע לא מאפשר מועד סגירה מוקדם מהיום. כשהיום הוא
שישי/שבת ומועד הסגירה הטבעי כבר עבר, הסגירה "הוצמדה" להיום — ואז כל חלון
המסלול נפל על שישי–שבת, בלי אף יום פעיל, והמסלול יצא עם 0 שלבים: לא נשלחה
אף הודעה ולא תוכננה אף שיחה.

הכלל: במקרה כזה הסגירה עוברת ליום הפעילות הבא (ראשון), כל עוד הוא עדיין
לפני האירוע. אם אין אף יום פעיל לפני האירוע — אין מסלול, וזה תקין.

כל שאר ההחלטות (7 שלבים ובאותו סדר, בלי שישי/שבת, דחיסה בחלון קצר) נבדקות
ב-``test_rsvp_schedule_scenarios.py`` ולא משתנות כאן.

הרצה: ``venv/bin/python tests/test_rsvp_weekend_today.py`` (עצמאי, או pytest).
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import models, rsvp_timeline as rt  # noqa: E402

MONDAY = datetime(2026, 9, 14, 9, 0)
WEEK = [MONDAY + timedelta(days=i) for i in range(7)]  # ב׳ 14/9 … א׳ 20/9
FRIDAY, SATURDAY, SUNDAY = WEEK[4], WEEK[5], WEEK[6]
FULL = "WWPWPWP"


def _event(event_date: date, commit=None) -> models.Event:
    return models.Event(
        event_type="wedding",
        event_date=event_date.isoformat(),
        venue_commit_days_before=commit,
    )


def _kinds(s: rt.Schedule) -> str:
    return "".join("P" if p.step["type"] == "call_round" else "W" for p in s.placements)


def _prev_active(d: date) -> date:
    while rt.is_weekend(d):
        d -= timedelta(days=1)
    return d


def _has_workday(start: date, end_exclusive: date) -> bool:
    d = start
    while d < end_exclusive:
        if not rt.is_weekend(d):
            return True
        d += timedelta(days=1)
    return False


def test_friday_closing_already_passed_moves_to_sunday() -> None:
    """היום שישי 18/9, אירוע בשלישי 22/9, סגירה 4 ימים לפני = שישי 18/9 →
    הוקדם לחמישי 17/9 שכבר עבר. לפני התיקון: סגירה בשישי ו-0 שלבים."""
    s = rt.compute_schedule(_event(date(2026, 9, 22), commit=4), FRIDAY)
    assert s is not None
    assert s.commitment_date == date(2026, 9, 20), s.commitment_date
    assert len(s.placements) == 7, f"מסלול ריק/חסר: {len(s.placements)} שלבים"
    assert _kinds(s) == FULL, _kinds(s)
    # יום פעיל אחד בלבד לפני הסגירה (ראשון) — כל השלבים בו, בסדר הקבוע.
    assert {p.date for p in s.placements} == {date(2026, 9, 20)}
    print("✓ שישי, הסגירה הטבעית עברה → ראשון, 7 שלבים")


def test_saturday_closing_already_passed_moves_to_sunday() -> None:
    """היום שבת 19/9, אירוע בשלישי 22/9, סגירה 3 ימים לפני = שבת → חמישי
    שעבר. לפני התיקון: סגירה בשבת ו-0 שלבים."""
    s = rt.compute_schedule(_event(date(2026, 9, 22), commit=3), SATURDAY)
    assert s is not None
    assert s.commitment_date == date(2026, 9, 20), s.commitment_date
    assert _kinds(s) == FULL, _kinds(s)
    print("✓ שבת, הסגירה הטבעית עברה → ראשון, 7 שלבים")


def test_sunday_already_the_natural_closing_is_unchanged() -> None:
    """היום שישי, והסגירה הטבעית היא ראשון — המצב שכבר עבד. לא משתנה."""
    s = rt.compute_schedule(_event(date(2026, 9, 21), commit=1), FRIDAY)
    assert s is not None and s.commitment_date == date(2026, 9, 20)
    assert _kinds(s) == FULL
    print("✓ סגירה טבעית בראשון — ללא שינוי")


def test_no_workday_before_the_event_has_no_track() -> None:
    """היום שישי והאירוע בשבת או בראשון: אין אף יום פעיל לפני האירוע.
    הסגירה לא עוברת לראשון (זה יום האירוע או אחריו), ואין שלבים — תקין."""
    for event_day in (date(2026, 9, 19), date(2026, 9, 20)):
        for now in (FRIDAY, SATURDAY):
            if now.date() >= event_day:
                continue
            for commit in (None, 1, 2, 3):
                s = rt.compute_schedule(_event(event_day, commit=commit), now)
                if s is None:
                    continue
                assert s.commitment_date < event_day, f"{now.date()}→{event_day}: {s.commitment_date}"
                assert s.placements == [], f"{now.date()}→{event_day}: {len(s.placements)} שלבים"
    print("✓ בלי יום פעיל לפני האירוע — אין מסלול, והסגירה לא אחרי האירוע")


def test_stable_from_friday_to_sunday() -> None:
    """מה שמוצג בשישי הוא מה שקורה בפועל בראשון (כשהמשימה המתוזמנת מתחילה
    את המסלול): אותו מועד סגירה ואותם תאריכים."""
    ev_date = date(2026, 9, 23)
    for commit in (3, 4, 5):
        seen = set()
        for now in (FRIDAY, SATURDAY, SUNDAY):
            s = rt.compute_schedule(_event(ev_date, commit=commit), now)
            seen.add((s.commitment_date, tuple(p.date for p in s.placements)))
        assert len(seen) == 1, f"commit={commit}: {seen}"
    print("✓ שישי, שבת וראשון רואים אותו לוח")


def test_every_weekday_never_empty_when_a_workday_exists() -> None:
    """כל 7 ימי השבוע × מרחק × בחירה: אם יש יום פעיל בין היום לאירוע —
    המסלול מלא (7 שלבים) והסגירה לא בשישי/שבת. בימים א׳–ה׳ הכלל הישן בדיוק."""
    count = 0
    for now in WEEK:
        today = now.date()
        for days_out in range(1, 40):
            ev_date = today + timedelta(days=days_out)
            for commit in [None] + list(range(1, min(10, days_out) + 1)):
                s = rt.compute_schedule(_event(ev_date, commit=commit), now)
                if s is None:
                    continue
                where = f"היום {today} ({rt.hebrew_weekday(today)}) +{days_out} commit={commit}"
                assert s.commitment_date < ev_date, f"{where}: סגירה {s.commitment_date}"
                if _has_workday(today, ev_date):
                    assert _kinds(s) == FULL, f"{where}: {len(s.placements)} שלבים"
                    assert not rt.is_weekend(s.commitment_date), f"{where}: סגירה {s.commitment_date}"
                # הנוסחה המלאה: קודם כמו תמיד, ורק אם נפל על סוף שבוע — ראשון.
                raw = ev_date - timedelta(days=s.commit_days)
                want = max(_prev_active(raw), today)
                if rt.is_weekend(want) and rt.next_active_day(want) < ev_date:
                    want = rt.next_active_day(want)
                assert s.commitment_date == want, f"{where}: {s.commitment_date} ≠ {want}"
                if not rt.is_weekend(today):
                    # בימים א׳–ה׳ התיקון לא משנה כלום.
                    assert s.commitment_date == max(_prev_active(raw), today), where
                count += 1
    print(f"✓ {count} צירופים בכל 7 ימי השבוע — אין מסלול ריק כשיש יום פעיל")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
