"""בדיקות לסדר החישוב של לוח אישורי ההגעה: תאריך אירוע → מועד סגירה → סבבים.

נועל את הכללים:
- אירוע רחוק → בעל האירוע בוחר מועד סגירה (אין ברירת מחדל כפויה).
- אירוע קרוב (פחות מ-``MAX_WINDOW_DAYS``) בלי בחירה → יום לפני האירוע.
  אירוע מחר → הרשימה נסגרת היום.
- 14 יום = מקסימום. כשיש פחות — התהליך נדחס; כשאין מספיק ימים פעילים לכל
  השלבים — נבחרים החשובים ביותר (``STEP_PRIORITY``), בלי להישבר.
- תמיד: אין תאריך בעבר, אין שלב אחרי מועד הסגירה, אין שני שלבים באותו יום
  (ולכן אף פעם לא WhatsApp וטלפון יחד), אין שישי/שבת.
- ברית/בריתה/חתונה עוברות אותו חישוב — ההבדל נובע רק מתאריך האירוע.

כל תרחיש רץ על כל 7 ימי השבוע כיום "היום", כי שישי/שבת משנים את התוצאה.

הרצה: ``venv/bin/python tests/test_rsvp_schedule_scenarios.py`` (עצמאי, בלי pytest).
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import models, rsvp_timeline as rt  # noqa: E402

MONDAY = datetime(2026, 9, 14, 9, 0)
WEEK = [MONDAY + timedelta(days=i) for i in range(7)]


def _event(days_out: int, now: datetime, commit=None, event_type="wedding", started=None):
    return models.Event(
        event_type=event_type,
        event_date=(now.date() + timedelta(days=days_out)).isoformat(),
        venue_commit_days_before=commit,
        rsvp_track_started_at=started,
    )


def _assert_sane(schedule: rt.Schedule, now: datetime, days_out: int, where: str) -> None:
    today = now.date()
    event_date = today + timedelta(days=days_out)
    dates = [p.date for p in schedule.placements]
    assert today <= schedule.commitment_date < event_date, f"{where}: מועד סגירה {schedule.commitment_date}"
    assert all(d >= today for d in dates), f"{where}: תאריך בעבר {dates}"
    assert all(d <= schedule.commitment_date for d in dates), f"{where}: שלב אחרי הסגירה {dates}"
    assert len(set(dates)) == len(dates), f"{where}: שני שלבים באותו יום {dates}"
    assert dates == sorted(dates), f"{where}: שלבים לא בסדר {dates}"
    assert not any(rt.is_weekend(d) for d in dates), f"{where}: שלב בשישי/שבת {dates}"
    if dates:
        assert (schedule.commitment_date - dates[0]).days <= rt.MAX_WINDOW_DAYS, f"{where}: חלון מעל 14"
        assert schedule.placements[0].step["type"] == "whatsapp_first", f"{where}: בלי בקשה ראשונה"


# (שם, ימים עד האירוע, בחירה ידנית, סוג אירוע, ברירת מחדל צפויה, תהליך מלא צפוי)
SCENARIOS = [
    ("חתונה בעוד 30 יום", 30, 5, "wedding", False, True),
    ("חתונה בעוד 21 יום", 21, 5, "wedding", False, True),
    ("חתונה בעוד 14 יום (בחירה)", 14, 1, "wedding", False, None),
    ("חתונה בעוד 10 ימים", 10, None, "wedding", True, None),
    ("חתונה בעוד 7 ימים", 7, None, "wedding", True, False),
    ("ברית בעוד 21 יום", 21, 3, "brit", False, True),
    ("ברית בעוד 7 ימים", 7, None, "brit", True, False),
    ("בריתה בעוד 10 ימים", 10, None, "brita", True, None),
    ("בריתה בעוד 3 ימים", 3, None, "brita", True, False),
    ("אירוע מחר", 1, None, "wedding", True, False),
    ("אירוע רחוק, בחירה ידנית", 60, 10, "wedding", False, True),
]


def test_required_scenarios_every_weekday() -> None:
    for now in WEEK:
        for name, days_out, commit, event_type, want_default, want_full in SCENARIOS:
            where = f"{name} (היום {now.date()})"
            s = rt.compute_schedule(_event(days_out, now, commit, event_type), now)
            assert s is not None, f"{where}: אין לוח זמנים"
            _assert_sane(s, now, days_out, where)
            assert s.commit_is_default is want_default, where
            if want_default:
                assert s.commit_days == 1, where
            if want_full is True:
                assert len(s.placements) == 7 and not s.compressed, f"{where}: {len(s.placements)} שלבים"
                calls = [p for p in s.placements if p.round_number]
                assert calls[-1].date == s.commitment_date, where
            if want_full is False:
                assert s.compressed, f"{where}: היה אמור להידחס"
    print("✓ 11 תרחישי החובה תקינים בכל 7 ימי השבוע")


def test_far_event_without_choice_waits_for_the_user() -> None:
    """אירוע רחוק (14 יום ומעלה) בלי בחירה — לא כופים מועד סגירה."""
    for now in WEEK:
        for days_out in (14, 21, 30, 90):
            assert rt.compute_schedule(_event(days_out, now), now) is None, days_out
            assert rt.resolve_commit_days(_event(days_out, now), now) == (None, False)
    print("✓ אירוע רחוק בלי בחירה — ממתינים לבחירת בעל האירוע")


def test_near_event_defaults_to_day_before() -> None:
    now = MONDAY  # שני
    s = rt.compute_schedule(_event(3, now, event_type="brita"), now)  # חמישי
    assert s.commitment_date == now.date() + timedelta(days=2)  # רביעי = יום לפני
    tomorrow = rt.compute_schedule(_event(1, now), now)
    assert tomorrow.commitment_date == now.date(), "אירוע מחר → הרשימה נסגרת היום"
    assert [p.step["type"] for p in tomorrow.placements] == ["whatsapp_first"]
    print("✓ אירוע קרוב → יום לפני האירוע; אירוע מחר → היום")


def test_event_type_does_not_change_the_schedule() -> None:
    for now in WEEK:
        for days_out, commit in ((21, 3), (7, None), (3, None)):
            results = {
                et: [(p.step["type"], p.date) for p in rt.compute_schedule(_event(days_out, now, commit, et), now).placements]
                for et in ("wedding", "brit", "brita", "bar_mitzvah")
            }
            assert len({tuple(v) for v in results.values()}) == 1, results
    print("✓ סוג האירוע לא משנה את החישוב — רק התאריך")


def test_window_is_a_maximum_not_a_requirement() -> None:
    """ימים עד הסגירה → אורך החלון = min(14, ימים)."""
    now = MONDAY
    for days_to_close in (20, 14, 10, 7, 3, 1):
        ev = _event(days_to_close + 1, now, commit=1)
        s = rt.compute_schedule(ev, now)
        span = (s.commitment_date - s.start_date).days
        assert span <= min(14, days_to_close), (days_to_close, span)
    print("✓ 14 יום הם מקסימום — החלון לא חורג מהזמן הקיים")


def test_priority_when_days_are_short() -> None:
    """סדר העדיפות: בקשה → שיחה ביום הסגירה → תזכורת/שיחה לסירוגין."""
    expected = {
        1: ["whatsapp_first"],
        2: ["whatsapp_first", "call_round"],
        3: ["whatsapp_first", "reminder", "call_round"],
        4: ["whatsapp_first", "reminder", "call_round", "call_round"],
        5: ["whatsapp_first", "reminder", "call_round", "reminder", "call_round"],
        6: ["whatsapp_first", "reminder", "call_round", "reminder", "call_round", "call_round"],
        7: ["whatsapp_first", "reminder", "call_round", "reminder", "call_round", "reminder", "call_round"],
    }
    for n, types in expected.items():
        assert [rt.CYCLE[i]["type"] for i in rt._choose_steps(n)] == types, n
    # התוויות מתמספרות מחדש: שני סבבי שיחות = "ראשון" ו"אחרון".
    s = rt.compute_schedule(_event(5, MONDAY), MONDAY)  # שבת; סגירה שישי→חמישי: ב-ה = 4 ימים
    labels = [p.step["label"] for p in s.placements]
    assert labels == ["בקשת אישור ראשונה ב-WhatsApp", "תזכורת ראשונה", "סבב שיחות ראשון", "סבב שיחות אחרון"], labels
    assert [p.reminder_number for p in s.placements if p.reminder_number] == [1]
    print("✓ דחיסה בוחרת את הסבבים החשובים ומתמספרת מחדש")


def test_started_track_is_stable_and_never_before_start() -> None:
    """אחרי הפעלת המסלול התאריכים לא זזים מיום ליום."""
    for start in WEEK:
        for days_out, commit in ((30, 5), (9, None), (4, 2)):
            ev = _event(days_out, start, commit, started=start)
            first = rt.compute_schedule(ev, start)
            for later in range(1, 4):
                again = rt.compute_schedule(ev, start + timedelta(days=later))
                assert [p.date for p in again.placements] == [p.date for p in first.placements], (start, days_out)
            assert all(p.date >= start.date() for p in first.placements)
    # מסלול שהופעל כשהאירוע היה רחוק ובלי בחירה: ברירת המחדל לא יוצרת שלבים
    # לפני היום שבו האירוע נעשה קרוב.
    started = MONDAY - timedelta(days=20)
    ev = _event(10, MONDAY, started=started)
    s = rt.compute_schedule(ev, MONDAY)
    became_near = MONDAY.date() + timedelta(days=10 - (rt.MAX_WINDOW_DAYS - 1))
    assert s.commit_is_default and all(p.date >= became_near for p in s.placements)
    print("✓ מסלול שהופעל — תאריכים יציבים ולא לפני תחילת המסלול")


def test_brute_force_invariants() -> None:
    count = 0
    for now in WEEK:
        for days_out in range(1, 70):
            for commit in [None] + list(range(1, min(10, days_out) + 1)):
                s = rt.compute_schedule(_event(days_out, now, commit), now)
                if s is None:
                    continue
                _assert_sane(s, now, days_out, f"{now.date()} +{days_out} commit={commit}")
                count += 1
    print(f"✓ {count} צירופים (יום בשבוע × מרחק × בחירה) — אף הפרה")


def test_reminder_dates_follow_the_schedule() -> None:
    now = MONDAY
    ev = _event(30, now, commit=5)
    s = rt.compute_schedule(ev, now)
    reminders = [p for p in s.placements if p.step["type"] == "reminder"]
    for n, p in enumerate(reminders, start=1):
        assert rt.reminder_date(ev, n, now) == p.date
    short = _event(3, now, event_type="brita")
    assert rt.reminder_date(short, 1, now) is not None
    assert rt.reminder_date(short, 2, now) is None, "תזכורת שנחתכה בדחיסה — אין תאריך"
    print("✓ תאריכי התזכורות נגזרים מהלוח")


if __name__ == "__main__":
    test_required_scenarios_every_weekday()
    test_far_event_without_choice_waits_for_the_user()
    test_near_event_defaults_to_day_before()
    test_event_type_does_not_change_the_schedule()
    test_window_is_a_maximum_not_a_requirement()
    test_priority_when_days_are_short()
    test_started_track_is_stable_and_never_before_start()
    test_brute_force_invariants()
    test_reminder_dates_follow_the_schedule()
    print("\nכל בדיקות לוח אישורי ההגעה עברו ✓")
