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
    assert dates == sorted(dates), f"{where}: סבבים לא בסדר {dates}"
    assert not any(rt.is_weekend(d) for d in dates), f"{where}: סבב בשישי/שבת {dates}"
    _assert_same_day_rule(schedule, where)
    if dates:
        kinds = _kinds(schedule)
        # הסדר לעולם לא משתנה: תמיד תחילת המסלול המלא.
        assert FULL.startswith(kinds), f"{where}: רצף {kinds}"
        start = max(schedule.commitment_date - timedelta(days=rt.MAX_WINDOW_DAYS), today)
        # יש לפחות 4 ימים פעילים — כל 7 השלבים נשמרים (דחוס).
        if len(_active_days(start, schedule.commitment_date)) >= 4:
            assert kinds == FULL, f"{where}: חסרים שלבים {kinds}"
        assert (schedule.commitment_date - dates[0]).days <= rt.MAX_WINDOW_DAYS, f"{where}: חלון מעל 14"
        assert schedule.placements[0].step["type"] == "whatsapp_first", f"{where}: בלי בקשה ראשונה"
        if len(dates) > 1:
            assert dates[-1] == schedule.commitment_date, f"{where}: הסבב האחרון לא ביום הסגירה"


FULL = "WWPWPWP"


def _active_days(start, end) -> list:
    days, cur = [], start
    while cur <= end:
        if not rt.is_weekend(cur):
            days.append(cur)
        cur += timedelta(days=1)
    return days


def _assert_same_day_rule(schedule: rt.Schedule, where: str) -> None:
    """שני שלבים באותו יום — רק תזכורת ואחריה שיחה. אף פעם שתי הודעות
    WhatsApp או שתי שיחות, ואף פעם בקשת האישור הראשונה עם עוד שלב."""
    by_day: dict = {}
    for p in schedule.placements:
        by_day.setdefault(p.date, []).append(p.step["type"])
    for day, types in by_day.items():
        assert len(types) <= 2, f"{where}: {types} ב-{day}"
        if len(types) == 2:
            assert types == ["reminder", "call_round"], f"{where}: {types} ב-{day}"


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
                # פחות מ-14 יום: דחוס — אבל לא מקוצר (נבדק ב-_assert_sane).
                assert s.compressed, f"{where}: {_kinds(s)}"
    print("✓ 11 תרחישי החובה תקינים בכל 7 ימי השבוע")


def test_full_14_day_track_exact_dates() -> None:
    """(1) מסלול מלא של 14 ימים — הסדר והתאריכים המדויקים."""
    now = MONDAY  # שני 14/9
    s = rt.compute_schedule(_event(16, now, commit=2), now)  # סגירה: שני 28/9
    got = [(k, p.date.day) for k, p in zip(_kinds(s), s.placements)]
    assert got == [("W", 14), ("W", 15), ("P", 17), ("W", 20), ("P", 23), ("W", 24), ("P", 28)], got
    assert not s.compressed
    print("✓ (1) מסלול מלא: W W P W P W P, 14 ימים, מסתיים ביום הסגירה")


def test_less_than_14_days_keeps_all_seven() -> None:
    """(2) פחות מ-14 ימים — כל 7 השלבים, באותו סדר, דחוסים לחלון (2026-09-25)."""
    now = MONDAY
    s = rt.compute_schedule(_event(12, now, commit=2), now)  # סגירה חמישי 24/9 → 10 ימים
    got = [(k, p.date.day) for k, p in zip(_kinds(s), s.placements)]
    assert got == [("W", 14), ("W", 15), ("P", 17), ("W", 20), ("P", 21), ("W", 22), ("P", 24)], got
    assert s.compressed
    print("✓ (2) 10 ימים → כל 7 השלבים, כל אחד ביום משלו")


def test_short_window_puts_reminder_and_call_on_the_same_day() -> None:
    """(2ב) חלון קצר מדי ליום לכל שלב — תזכורת והשיחה שאחריה באותו יום,
    קודם התזכורת. שישי/שבת לא נבחרים, והסדר נשמר."""
    now = MONDAY
    s = rt.compute_schedule(_event(7, now, commit=1), now)  # סגירה ראשון 20/9 → 5 ימים פעילים
    got = [(k, p.date.day) for k, p in zip(_kinds(s), s.placements)]
    assert got == [("W", 14), ("W", 15), ("P", 16), ("W", 17), ("P", 17), ("W", 20), ("P", 20)], got
    assert [p.step["type"] for p in s.placements if p.date.day == 17] == ["reminder", "call_round"]
    # 4 ימים פעילים (שני–חמישי) — עדיין כל 7: בקשה, ואז 3 ימים של תזכורת+שיחה.
    four = rt.compute_schedule(_event(4, now, commit=1), now)  # סגירה חמישי 17/9
    assert [(k, p.date.day) for k, p in zip(_kinds(four), four.placements)] == [
        ("W", 14), ("W", 15), ("P", 15), ("W", 16), ("P", 16), ("W", 17), ("P", 17),
    ]
    print("✓ (2ב) חלון קצר: תזכורת ושיחה באותו יום, כל 7 השלבים")


def test_very_short_window() -> None:
    """(3) חלון קצר מאוד — סבב אחד או שניים, בלי לדחוס."""
    now = MONDAY
    # פחות מ-4 ימים פעילים — אין דרך לכל 7 בלי שתי הודעות WhatsApp (או
    # שתי שיחות) באותו יום, ולכן כמה שיותר מתחילת המסלול, באותו סדר.
    three = rt.compute_schedule(_event(3, now, commit=1), now)  # סגירה רביעי → 3 ימים פעילים
    assert _kinds(three) == "WWPWP", _kinds(three)
    two = rt.compute_schedule(_event(2, now, commit=1), now)    # סגירה שלישי → 2 ימים
    assert _kinds(two) == "WWP", _kinds(two)
    today_close = rt.compute_schedule(_event(1, now), now)      # אירוע מחר → סוגרים היום
    assert _kinds(today_close) == "W" and today_close.placements[0].date == now.date()
    five_days = rt.compute_schedule(_event(5, now, commit=1), now)  # סגירה שישי→חמישי: 4 ימים
    assert _kinds(five_days) == FULL, _kinds(five_days)
    print("✓ (3) חלון קצר מאוד: 4 ימים פעילים = כל 7; פחות מזה — תחילת המסלול")


def test_order_never_changes_and_short_windows_keep_seven() -> None:
    """(4) בכל לוח אמיתי הרצף הוא תחילת W W P W P W P — וכל 7 כשיש 4 ימים
    פעילים ומעלה. חלון קצר נדחס, לא מתקצר ולא מתחלף."""
    assert "".join(rt.SEQUENCES[7]) == FULL
    sevens = 0
    for now in WEEK:
        for days_out in range(1, 20):
            for commit in (1, 2, 3, 5):
                if commit >= days_out:
                    continue
                s = rt.compute_schedule(_event(days_out, now, commit=commit), now)
                if not s or not s.placements:
                    continue
                assert FULL.startswith(_kinds(s)), _kinds(s)
                start = max(s.commitment_date - timedelta(days=rt.MAX_WINDOW_DAYS), now.date())
                if len(_active_days(start, s.commitment_date)) >= 4:
                    assert _kinds(s) == FULL, (now, days_out, commit, _kinds(s))
                    sevens += 1
    assert sevens > 0
    # תקרת אדמין מפורשת לאירוע — שורה מאותה טבלה, גם היא נדחסת ולא מתקצרת.
    kinds, dates = rt._place_track(rt.SEQUENCES[3], MONDAY.date(), MONDAY.date() + timedelta(days=14))
    assert "".join(kinds) == "WPW" and len(dates) == 3
    print(f"✓ (4) הסדר לא משתנה; {sevens} לוחות קצרים עם כל 7 השלבים")


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
                # רק הפריסה הרגילה (יום לכל שלב) נשענת על "חמישי/ראשון";
                # מסלול דחוס פשוט לא בוחר שישי/שבת (נבדק ב-_assert_sane).
                regular = rt._place(kinds, start, s.commitment_date)
                if regular is None or [d for d, _ in regular] != [p.date for p in s.placements]:
                    continue
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
    """גם במסלול דחוס — אותן 7 תוויות ואותו מספור תזכורות."""
    s = rt.compute_schedule(_event(8, MONDAY, commit=1), MONDAY)  # דחוס, 5 ימים פעילים
    labels = [p.step["label"] for p in s.placements]
    assert labels == [
        "בקשת אישור ראשונה ב-WhatsApp", "תזכורת ראשונה", "סבב שיחות ראשון", "תזכורת שנייה",
        "סבב שיחות שני", "תזכורת שלישית", "סבב שיחות אחרון",
    ], labels
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
    # אירוע מחר — רק בקשת האישור נכנסת; לתזכורת אין תאריך.
    short = _event(1, now, event_type="brita")
    assert rt.reminder_date(short, 1, now) is None, "תזכורת שלא נכנסה ללוח — אין תאריך"
    # חלון קצר — התזכורות נשמרות (דחוס), עם תאריך.
    squeezed = _event(3, now, event_type="brita")  # סגירה רביעי → 3 ימים פעילים
    assert rt.reminder_date(squeezed, 1, now) is not None
    print("✓ תאריכי התזכורות נגזרים מהלוח")


if __name__ == "__main__":
    test_required_scenarios_every_weekday()
    test_full_14_day_track_exact_dates()
    test_less_than_14_days_keeps_all_seven()
    test_short_window_puts_reminder_and_call_on_the_same_day()
    test_very_short_window()
    test_order_never_changes_and_short_windows_keep_seven()
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
