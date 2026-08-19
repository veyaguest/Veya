"""Regression: RSVP → מועמדות להושבה אוטומטית (Audit RSVP↔הושבה, 2026-08-19).

נועל את התיקון ב-``routers/seating.py::generate``: רק מוזמן עם
``rsvp_status == "confirmed"`` יכול להיכנס כמועמד **חדש** להושבה אוטומטית
(``POST /seating/generate``) — בכל מצב (כולל ``only_unassigned``), ובלי
תלות בדגל ``only_confirmed`` שהלקוח שולח (או לא שולח). מוזמן שכבר משובץ
ואינו "מגיע" לעולם לא נמחק מהשולחן שלו על ידי ה-endpoint הזה — הושבה ידנית
(``/seating/assign``, ``PUT /hall``) לא עוברת דרכו וממשיכה לעבוד בלי שינוי.

הרצה: ``pytest tests/test_seating_rsvp_filter.py`` או
``python tests/test_seating_rsvp_filter.py``.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


def _table_of(hall: dict, guest_name: str):
    """מספר השולחן שבו יושב מוזמן לפי שם, או None אם אינו משובץ."""
    for t in hall["tables"]:
        for g in t["guests"]:
            if g["full_name"] == guest_name:
                return t["table_number"]
    return None


def _mark(api, guest_id: int, status: str) -> None:
    r = api.client.patch(f"/guests/{guest_id}", headers=api.headers,
                          json={"rsvp_status": status})
    assert r.status_code == 200, r.text


# ---- A: מי כן נכנס ----

def test_confirmed_is_seated_by_one_click() -> None:
    """A. מגיע נכנס להושבה בקליק."""
    api, teardown = bootstrap()
    try:
        g = api.add_guest("מגיע אחד", "0501111111", party_size=2)
        api.confirm(g["id"])
        r = api.generate(persist=True)
        assert r.status_code == 200, r.text
        hall = api.get_hall()
        assert _table_of(hall, "מגיע אחד") is not None, "מגיע לא שובץ"
        print("✓ A: מגיע נכנס להושבה בקליק")
    finally:
        teardown()


# ---- B/C/D: מי לא נכנס (ריצה מלאה, לא only_unassigned) ----

def _assert_status_excluded_from_full_run(status: str, label: str) -> None:
    api, teardown = bootstrap()
    try:
        confirmed = api.add_guest("מגיע", "0501000000")
        api.confirm(confirmed["id"])
        g = api.add_guest(f"אורח {label}", "0502000000")
        _mark(api, g["id"], status)

        r = api.generate(persist=True)
        assert r.status_code == 200, r.text
        hall = api.get_hall()
        assert _table_of(hall, f"אורח {label}") is None, (
            f"{label} שובץ בהושבה בקליק — הבאג חזר"
        )
        assert f"אורח {label}" in {u["full_name"] for u in hall["unassigned"]}
        assert _table_of(hall, "מגיע") is not None
        print(f"✓ {label} לא נכנס להושבה בקליק (ריצה מלאה)")
    finally:
        teardown()


def test_pending_is_not_seated_by_one_click() -> None:
    """B. טרם השיב לא נכנס להושבה בקליק."""
    _assert_status_excluded_from_full_run("pending", "טרם-השיב")


def test_maybe_is_not_seated_by_one_click() -> None:
    """C. מתלבט לא נכנס להושבה בקליק."""
    _assert_status_excluded_from_full_run("maybe", "מתלבט")


def test_declined_is_not_seated_by_one_click() -> None:
    """D. לא מגיע לא נכנס להושבה בקליק."""
    _assert_status_excluded_from_full_run("declined", "לא-מגיע")


# ---- E/F/G: אותו דבר, במצב "השלמת מקומות" (only_unassigned) ----

def _assert_status_excluded_from_only_unassigned(status: str, label: str) -> None:
    api, teardown = bootstrap()
    try:
        # מישהו כבר משובץ, כדי שיהיה הבדל אמיתי בין "מלא" ל"רק לא-משובצים".
        seated = api.add_guest("כבר משובץ", "0503000000")
        api.confirm(seated["id"])
        r = api.generate(persist=True)
        assert r.status_code == 200, r.text

        g = api.add_guest(f"חדש {label}", "0504000000")
        _mark(api, g["id"], status)

        r = api.generate(persist=True, only_unassigned=True)
        assert r.status_code == 200, r.text
        hall = api.get_hall()
        assert _table_of(hall, f"חדש {label}") is None, (
            f"{label} שובץ ב-only_unassigned — הבאג חזר"
        )
        assert _table_of(hall, "כבר משובץ") is not None, "המשובץ הקודם נמחק"
        print(f"✓ {label} לא נכנס גם ב-only_unassigned")
    finally:
        teardown()


def test_only_unassigned_excludes_pending() -> None:
    """E. only_unassigned=True + טרם השיב → עדיין לא נכנס."""
    _assert_status_excluded_from_only_unassigned("pending", "טרם-השיב")


def test_only_unassigned_excludes_maybe() -> None:
    """F. only_unassigned=True + מתלבט → עדיין לא נכנס."""
    _assert_status_excluded_from_only_unassigned("maybe", "מתלבט")


def test_only_unassigned_excludes_declined() -> None:
    """G. only_unassigned=True + לא מגיע → עדיין לא נכנס."""
    _assert_status_excluded_from_only_unassigned("declined", "לא-מגיע")


# ---- H/I: מי שכבר משובץ (הושבה ידנית) לא נמחק כשה-RSVP שלו לא "מגיע" ----

def _assert_already_seated_is_not_unseated(status: str, label: str) -> None:
    api, teardown = bootstrap()
    try:
        g = api.add_guest(f"כבר יושב ({label})", "0505000000")
        _mark(api, g["id"], status)
        # הושבה ידנית — לא דרך generate בכלל, כמו שהבעלים היה עושה בגרירה.
        api.save_hall([
            {"table_number": 1, "x": 100, "y": 100, "guest_ids": [g["id"]],
             "table_type": "round", "capacity": 12, "rotation": 0,
             "name": "", "color": "", "notes": "", "locked": False,
             "is_reserve": False},
        ])

        confirmed = api.add_guest("מגיע", "0506000000")
        api.confirm(confirmed["id"])

        # ריצה מלאה (לא only_unassigned) — הכי תובענית: זו שהייתה עלולה
        # "לשכוח" אותו כי הוא לא ברשימת המועמדים החדשים.
        r = api.generate(persist=True)
        assert r.status_code == 200, r.text
        hall = api.get_hall()
        assert _table_of(hall, f"כבר יושב ({label})") == 1, (
            f"{label} שכבר היה משובץ נמחק מהשולחן — אסור!"
        )
        print(f"✓ {label} שכבר משובץ לא נמחק מהשולחן")
    finally:
        teardown()


def test_already_seated_pending_guest_is_not_unseated() -> None:
    """H. מוזמן pending שכבר משובץ לא נמחק."""
    _assert_already_seated_is_not_unseated("pending", "טרם השיב")


def test_already_seated_declined_guest_is_not_unseated() -> None:
    """I. מוזמן declined שכבר משובץ לא נמחק."""
    _assert_already_seated_is_not_unseated("declined", "לא מגיע")


# ---- J/K: כמות ----

def test_confirmed_party_of_four_takes_four_seats() -> None:
    """J. מגיע עם 4 אנשים תופס 4 מקומות בפועל."""
    api, teardown = bootstrap()
    try:
        g = api.add_guest("משפחה", "0507000000", party_size=4)
        api.confirm(g["id"], count=4)
        r = api.generate(persist=True, seats_per_table=6)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total_people"] == 4, body
        hall = api.get_hall()
        tnum = _table_of(hall, "משפחה")
        table = next(t for t in hall["tables"] if t["table_number"] == tnum)
        assert table["seats_used"] == 4, table
        print("✓ J: מגיע עם 4 אנשים תופס 4 מקומות")
    finally:
        teardown()


def test_pending_large_party_is_not_clamped_to_one() -> None:
    """K. pending עם party_size=4 לא הופך ל"אדם אחד" ולא נכנס בכלל — המוקש
    ``max(1, ...)`` ב-``app/seating.py`` אף פעם לא נוגע בו, כי הוא לא
    מגיע לשם."""
    api, teardown = bootstrap()
    try:
        confirmed = api.add_guest("מגיע", "0508000000")
        api.confirm(confirmed["id"])
        api.add_guest("משפחה גדולה שלא ענתה", "0509000000", party_size=4)

        r = api.generate(persist=True)
        assert r.status_code == 200, r.text
        body = r.json()
        # רק המגיע האחד נספר — לא 1 (המוקש) ולא 4 (התעלמות מהסינון).
        assert body["total_people"] == 1, body
        hall = api.get_hall()
        assert _table_of(hall, "משפחה גדולה שלא ענתה") is None
        print("✓ K: pending עם party_size גדול לא נכנס בכלל למנוע")
    finally:
        teardown()


# ---- R: אי אפשר לעקוף את הסינון דרך הפרמטרים של ה-API ----

def test_only_confirmed_flag_cannot_bypass_the_filter() -> None:
    """R. התוצאה זהה בין only_confirmed=True, only_confirmed=False, ובלי
    לשלוח את הדגל בכלל — הסינון תמיד חל, לא משנה מה הלקוח שולח."""
    for flag_kwargs in ({"only_confirmed": True}, {"only_confirmed": False}, {}):
        api, teardown = bootstrap()
        try:
            confirmed = api.add_guest("מגיע", "0510000000")
            api.confirm(confirmed["id"])
            api.add_guest("טרם השיב", "0511000000")

            r = api.generate(persist=True, **flag_kwargs)
            assert r.status_code == 200, r.text
            hall = api.get_hall()
            assert _table_of(hall, "טרם השיב") is None, (
                f"עם {flag_kwargs}: pending שובץ — אפשר לעקוף את הסינון"
            )
            assert _table_of(hall, "מגיע") is not None
        finally:
            teardown()
    print("✓ R: אי אפשר לעקוף את הסינון דרך only_confirmed")


if __name__ == "__main__":
    try:
        test_confirmed_is_seated_by_one_click()
        test_pending_is_not_seated_by_one_click()
        test_maybe_is_not_seated_by_one_click()
        test_declined_is_not_seated_by_one_click()
        test_only_unassigned_excludes_pending()
        test_only_unassigned_excludes_maybe()
        test_only_unassigned_excludes_declined()
        test_already_seated_pending_guest_is_not_unseated()
        test_already_seated_declined_guest_is_not_unseated()
        test_confirmed_party_of_four_takes_four_seats()
        test_pending_large_party_is_not_clamped_to_one()
        test_only_confirmed_flag_cannot_bypass_the_filter()
        print("OK — הסינון RSVP→הושבה אוטומטית עובד כמפרט.")
    finally:
        shutdown()
