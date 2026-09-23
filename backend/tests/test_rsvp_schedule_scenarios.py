"""בדיקות לוח אישורי ההגעה: תאריך אירוע → מועד סגירה → כמה סבבים → פריסה.

נועל את הכללים (החלטת המייסד 2026-09-23):
- העוגן הוא מועד הסגירה. המסלול המלא מתחיל 14 ימים לפניו ומסתיים בו.
- המסלול המלא: WhatsApp → WhatsApp → שיחות → WhatsApp → שיחות → WhatsApp → שיחות.
- חלון קצר → **פחות סבבים** (סבב לכל יומיים), מתחלפים W/P — לא מסלול דחוס.
- אף פעם שתי פעולות באותו יום, אף פעם אחרי מועד הסגירה, הסדר לא מתהפך.
- שישי/שבת: אין פעולות. → חמישי שלפני; אם הוא תפוס → ראשון שאחרי.
- אירוע רחוק בלי בחירה → אין לוח; אירוע קרוב בלי בחירה → יום לפני (לתצוגה).
- ברית/בריתה/חתונה עוברות אותו חישוב — ההבדל נובע רק מתאריך האירוע.

כל תרחיש רץ על כל 7 ימי השבוע כיום "היום", כי שישי/שבת משנים את התוצאה.

הרצה: ``venv/bin/python tests/test_rsvp_schedule_scenarios.py`` (עצמאי, או pytest).
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


def _kinds(schedule: rt.Schedule) -> str:
    return "".join("P" if p.step["type"] == "call_round" else "W" for p in schedule.placements)


def _assert_sane(schedule: rt.Schedule, now: datetime, days_out: int, where: str) -> None:
    today = now.date()
    event_date = today + timedelta(days=days_out)
    dates = [p.date for p in schedule.placements]
    assert schedule.commitment_date < event_date, f"{where}: מועד סגירה {schedule.commitment_date}"
    assert all(d >= today for d in dates), f"{where}: תאריך בעבר {dates}"
    assert all(d <= schedule.commitment_date for d in dates), f"{where}: סבב אחרי הסגירה {dates}"
    assert len(set(dates)) == len(dates), f"{where}: שני סבבים באותו יום {dates}"
    assert dates == sorted(dates), f"{where}: סבבים לא בסדר {dates}"
    assert not any(rt.is_weekend(d) for d in dates), f"{where}: סבב בשישי/שבת {dates}"
    if dates:
        n = len(dates)
        assert _kinds(schedule) == "".join(rt.SEQUENCES[n]), f"{where}: רצף {_kinds(schedule)}"
        start = max(schedule.commitment_date - timedelta(days=rt.MAX_WINDOW_DAYS), today)
        window = (schedule.commitment_date - start).days
        assert n <= rt.rounds_for_window(window), f"{where}: {n} סבבים בחלון של {window} ימים"
        assert (schedule.commitment_date - dates[0]).days <= rt.MAX_WINDOW_DAYS, f"{where}: חלון מעל 14"
        assert schedule.placements[0].step["type"] == "whatsapp_first", f"{where}: בלי בקשה ראשונה"
        if n > 1:
            assert dates[-1] == schedule.commitment_date, f"{where}: הסבב האחרון לא ביום הסגירה"


# (שם, ימים עד האירוע, בחירה ידנית, סוג אירוע, ברירת מחדל צפויה, מסלול מלא צפוי)
SCENARIOS = [
    ("חתונה בעוד 30 יום", 30, 5, "wedding", False, True),
    ("חתונה בעוד 21 יום", 21, 5, "wedding", False, True),
    ("חתונה בעוד 14 יום (בחירה)", 14, 1, "wedding", False, None),
    ("חתונה בעוד 10 ימים", 10, None, "wedding", True, False),
    ("חתונה בעוד 7 ימים", 7, None, "wedding", True, False),
    ("ברית בעוד 21 יום", 21, 3, "brit", False, True),
    ("ברית בעוד 7 ימים", 7, None, "brit", True, False),
    ("בריתה בעוד 10 ימים", 10, None, "brita", True, False),
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
                assert _kinds(s) == "WWPWPWP" and not s.compressed, f"{where}: {_kinds(s)}"
            if want_full is False:
                assert s.compressed and len(s.placements) < 7, f"{where}: {_kinds(s)}"
    print("✓ 11 תרחישי החובה תקינים בכל 7 ימי השבוע")


def test_full_14_day_track_exact_dates() -> None:
    """(1) מסלול מלא של 14 ימים — הסדר והתאריכים המדויקים."""
    now = MONDAY  # שני 14/9
    s = rt.compute_schedule(_event(16, now, commit=2), now)  # סגירה: שני 28/9
    got = [(k, p.date.day) for k, p in zip(_kinds(s), s.placements)]
    assert got == [("W", 14), ("W", 15), ("P", 17), ("W", 20), ("P", 23), ("W", 24), ("P", 28)], got
    assert not s.compressed
    print("✓ (1) מסלול מלא: W W P W P W P, 14 ימים, מסתיים ביום הסגירה")


def test_less_than_14_days_gets_fewer_rounds() -> None:
    """(2) פחות מ-14 ימים — פחות סבבים, מתחלפים, לא דחוס."""
    now = MONDAY
    s = rt.compute_schedule(_event(12, now, commit=2), now)  # סגירה חמישי 24/9 → 10 ימים
    assert _kinds(s) == "WPWPW", _kinds(s)
    gaps = [(b.date - a.date).days for a, b in zip(s.placements, s.placements[1:])]
    assert min(gaps) >= 1 and sum(gaps) == 10, gaps
    print("✓ (2) 10 ימים → 5 סבבים W P W P W")


def test_very_short_window() -> None:
    """(3) חלון קצר מאוד — סבב אחד או שניים, בלי לדחוס."""
    now = MONDAY
    one = rt.compute_schedule(_event(3, now, commit=1), now)   # סגירה רביעי → 2 ימים
    assert _kinds(one) == "W" and one.placements[0].date == now.date(), (
        "סבב יחיד יוצא בתחילת החלון, לא ביום הסגירה"
    )
    two = rt.compute_schedule(_event(5, now, commit=1), now)   # סגירה שישי→חמישי: 3 ימים
    assert _kinds(two) == "WP", _kinds(two)
    today_close = rt.compute_schedule(_event(1, now), now)     # אירוע מחר → סוגרים היום
    assert _kinds(today_close) == "W"
    print("✓ (3) חלון קצר מאוד: 1–2 סבבים, סבב יחיד בתחילת החלון")


def test_every_round_count_has_the_right_sequence() -> None:
    """(4) 7/6/5/4/3/2/1 סבבים — כל מספר עם הרצף שנקבע."""
    expected = {7: "WWPWPWP", 6: "WPWPWP", 5: "WPWPW", 4: "WPWP", 3: "WPW", 2: "WP", 1: "W"}
    for n, seq in expected.items():
        assert "".join(rt.SEQUENCES[n]) == seq
    # מספר הסבבים לפי אורך החלון: סבב לכל יומיים.
    assert [rt.rounds_for_window(d) for d in (14, 13, 12, 10, 8, 6, 4, 2, 1, 0)] == [7, 7, 6, 5, 4, 3, 2, 1, 1, 1]
    assert rt.rounds_for_window(-1) == 0
    # כל מספר סבבים מופיע בפועל בלוח אמיתי, עם הרצף הנכון.
    seen: set[int] = set()
    for now in WEEK:
        for days_out in range(1, 20):
            s = rt.compute_schedule(_event(days_out, now, commit=1), now)
            if s and s.placements:
                seen.add(len(s.placements))
                assert _kinds(s) == expected[len(s.placements)]
    assert seen == set(expected), seen
    # תקרת אדמין — בוחרת שורה מאותה טבלה (לא מספר סבבים שרירותי).
    policy = rt.Policy(max_rounds=3)
    assert rt.rounds_for_window(14, policy) == 3
    print("✓ (4) 7/6/5/4/3/2/1 סבבים — הרצף הנכון לכל מספר")


def _natural_weekend_moves():
    """מאתר בכל הלוחות האפשריים סבבים שהתאריך הטבעי שלהם נפל בסופ\"ש."""
    moves = []
    for now in WEEK:
        for days_out in range(2, 40):
            for commit in (None, 1, 2, 3, 5):
                ev = _event(days_out, now, commit)
                s = rt.compute_schedule(ev, now)
                if not s or len(s.placements) < 2:
                    continue
                start = max(s.commitment_date - timedelta(days=rt.MAX_WINDOW_DAYS), now.date())
                span = (s.commitment_date - start).days
                kinds = rt.SEQUENCES[len(s.placements)]
                positions = rt._spread(kinds)
                for k, p in enumerate(s.placements[:-1]):
                    natural = start + timedelta(days=round(positions[k] * span))
                    if rt.is_weekend(natural):
                        prev = s.placements[k - 1].date if k else None
                        moves.append((natural, p.date, prev, kinds[k], start))
    return moves


def test_friday_saturday_move_to_thursday_or_sunday() -> None:
    """(5)(6)(7) שישי/שבת → חמישי שלפני; אם חמישי תפוס (או מחוץ לחלון) →
    ראשון שאחרי. אותו כלל ל-WhatsApp ולשיחות, והסדר לא מתהפך."""
    moves = _natural_weekend_moves()
    cases = set()
    for natural, actual, prev, kind, start in moves:
        thursday = natural - timedelta(days=natural.weekday() - 3)
        sunday = rt.next_active_day(natural)
        thursday_ok = thursday >= start and (prev is None or thursday > prev)
        day = "fri" if natural.weekday() == 4 else "sat"
        if thursday_ok:
            assert actual == thursday, f"חמישי היה פנוי: {natural} → {actual}"
            cases.add((day, "thu", kind))
        else:
            assert actual >= sunday, f"חמישי תפוס/מחוץ לחלון → ראשון או אחריו: {natural} → {actual}"
            if actual == sunday:
                cases.add((day, "sun", kind))
    for want in (("fri", "thu", "W"), ("sat", "thu", "W"), ("fri", "sun", "W"), ("sat", "sun", "W"),
                 ("fri", "thu", "P"), ("sat", "thu", "P")):
        assert want in cases, f"לא נמצא מקרה {want}: {sorted(cases)}"
    # דוגמה מפורשת: חמישי תפוס ע"י הסבב הקודם → הסבב עובר לראשון.
    thursday = WEEK[3]  # חמישי 17/9
    s = rt.compute_schedule(_event(16, thursday, commit=2), thursday)
    assert [p.date.day for p in s.placements[:2]] == [17, 20], "שישי→חמישי תפוס→ראשון"
    print(f"✓ (5)(6)(7) שישי/שבת → חמישי, ואם תפוס → ראשון ({len(moves)} מקרים)")


def test_changing_the_closing_date_recomputes() -> None:
    """(15) שינוי מועד הסגירה: לפני שהמסלול התחיל — לוח חדש לגמרי; אחרי —
    אותו יום התחלה, והסבבים נפרסים מחדש עד מועד הסגירה החדש."""
    now = MONDAY
    before = rt.compute_schedule(_event(20, now, commit=3), now)
    after = rt.compute_schedule(_event(20, now, commit=6), now)
    assert after.commitment_date < before.commitment_date
    assert after.placements[-1].date == after.commitment_date
    started = _event(12, now, commit=2, started=now)
    s1 = rt.compute_schedule(started, now)
    started.venue_commit_days_before = 4
    s2 = rt.compute_schedule(started, now + timedelta(days=1))
    assert s2.placements[0].date == s1.placements[0].date, "יום ההתחלה זז"
    assert s2.commitment_date < s1.commitment_date and len(s2.placements) <= len(s1.placements)
    print("✓ (15) שינוי מועד הסגירה מחשב מחדש, בלי להזיז את תחילת המסלול")


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
    # ברירת המחדל מוצגת, אבל המסלול לא רשאי לשלוח עד שבוחרים.
    assert rt.track_enabled(_event(3, now)) is False
    assert rt.track_enabled(_event(3, now, commit=1)) is True
    print("✓ אירוע קרוב → יום לפני האירוע (לתצוגה); שליחה רק אחרי בחירה")


def test_event_type_does_not_change_the_schedule() -> None:
    for now in WEEK:
        for days_out, commit in ((21, 3), (7, None), (3, None)):
            results = {
                et: [(p.step["type"], p.date) for p in rt.compute_schedule(_event(days_out, now, commit, et), now).placements]
                for et in ("wedding", "brit", "brita", "bar_mitzvah")
            }
            assert len({tuple(v) for v in results.values()}) == 1, results
    print("✓ סוג האירוע לא משנה את החישוב — רק התאריך")


def test_labels_are_renumbered() -> None:
    """התוויות מתמספרות לפי מה שנכנס: 4 סבבים = בקשה, שיחות ראשון, תזכורת ראשונה, שיחות אחרון."""
    s = rt.compute_schedule(_event(10, MONDAY, commit=2), MONDAY)  # סגירה חמישי 17/9? → בדיקה לפי הרצף
    labels = [p.step["label"] for p in s.placements]
    if _kinds(s) == "WPWP":
        assert labels == ["בקשת אישור ראשונה ב-WhatsApp", "סבב שיחות ראשון", "תזכורת ראשונה", "סבב שיחות אחרון"], labels
    assert [p.reminder_number for p in s.placements if p.reminder_number] == list(
        range(1, _kinds(s).count("W"))
    )
    print("✓ תוויות ומספור תזכורות לפי הסבבים שנכנסו")


def test_started_track_is_stable_and_never_before_start() -> None:
    """אחרי תחילת המסלול התאריכים לא זזים מיום ליום."""
    for start in WEEK:
        for days_out, commit in ((30, 5), (9, None), (4, 2)):
            ev = _event(days_out, start, commit, started=start)
            first = rt.compute_schedule(ev, start)
            for later in range(1, 4):
                again = rt.compute_schedule(ev, start + timedelta(days=later))
                assert [p.date for p in again.placements] == [p.date for p in first.placements], (start, days_out)
            assert all(p.date >= start.date() for p in first.placements)
    started = MONDAY - timedelta(days=20)
    ev = _event(10, MONDAY, started=started)
    s = rt.compute_schedule(ev, MONDAY)
    became_near = MONDAY.date() + timedelta(days=10 - (rt.MAX_WINDOW_DAYS - 1))
    assert s.commit_is_default and all(p.date >= became_near for p in s.placements)
    print("✓ מסלול שהתחיל — תאריכים יציבים ולא לפני תחילת המסלול")


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
    short = _event(3, now, event_type="brita")  # 2 ימים → סבב אחד
    assert rt.reminder_date(short, 1, now) is None, "תזכורת שלא נכנסה ללוח — אין תאריך"
    print("✓ תאריכי התזכורות נגזרים מהלוח")


if __name__ == "__main__":
    test_required_scenarios_every_weekday()
    test_full_14_day_track_exact_dates()
    test_less_than_14_days_gets_fewer_rounds()
    test_very_short_window()
    test_every_round_count_has_the_right_sequence()
    test_friday_saturday_move_to_thursday_or_sunday()
    test_changing_the_closing_date_recomputes()
    test_far_event_without_choice_waits_for_the_user()
    test_near_event_defaults_to_day_before()
    test_event_type_does_not_change_the_schedule()
    test_labels_are_renumbered()
    test_started_track_is_stable_and_never_before_start()
    test_brute_force_invariants()
    test_reminder_dates_follow_the_schedule()
    print("\nכל בדיקות לוח אישורי ההגעה עברו ✓")
