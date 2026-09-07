"""המחשבונים הציבוריים — מוודא שהם **אותו מנוע** של המוצר, לא העתק שלו.

הבדיקה החשובה כאן היא לא "המספר יפה" אלא **"המספר זהה"**: אותו קלט
שעובר דרך ``finance.py``/``rsvp_timeline.py`` ישירות חייב לתת בדיוק את
מה שהנתיב הציבורי מחזיר. ברגע שמישהו ישכפל את הנוסחה לצד הלקוח או
יכתוב חישוב מקביל בשרת — הבדיקה הזו תיפול.

הרצה: python3 backend/tests/test_public_calc.py
"""
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("VEYA_DB_URL", "sqlite://")

from fastapi.testclient import TestClient  # noqa: E402

from app import finance, models, rsvp_timeline  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import public_calc  # noqa: E402

client = TestClient(app)
BASE = "/public/calculators"


def reset_limiter():
    """המגביל שומר מונה בזיכרון בין הבדיקות — מאפסים כדי שלא נקבל 429."""
    public_calc.calc_limiter._hits.clear()


def post(path, body):
    reset_limiter()
    return client.post(BASE + path, json=body)


# ════════════════════════════════════════════════════════════════════════
#  התחייבות לאולם
# ════════════════════════════════════════════════════════════════════════

def test_under_commitment_pays_for_commitment():
    """מתחת להתחייבות משלמים על ההתחייבות — לא על מי שהגיע."""
    r = post("/venue-commitment", {
        "attendees": 463,
        "meal_price_agorot": 32000,
        "committed_quantity": 500,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["billed_quantity"] == 500, d
    assert d["unused_quantity"] == 37, d
    assert d["over_commitment"] == 0, d
    assert d["total_agorot"] == 500 * 32000, d


def test_extra_guest_is_free_under_commitment():
    """אין הוצאות אחרות לאדם ⇒ האורח הבא לא מוסיף כלום מתחת להתחייבות."""
    d = post("/venue-commitment", {
        "attendees": 463, "meal_price_agorot": 32000, "committed_quantity": 500,
    }).json()
    assert d["next_attendee_agorot"] == 0, d


def test_extra_guest_costs_only_the_extras_under_commitment():
    """יש אלכוהול לאדם ⇒ מתחת להתחייבות מתווסף רק הוא, בלי המנה.

    זו בדיוק הנקודה שמחשבון שמכפיל מחירים מפספס.
    """
    d = post("/venue-commitment", {
        "attendees": 463, "meal_price_agorot": 32000, "committed_quantity": 500,
        "extra_per_attendee_agorot": 4500,
    }).json()
    assert d["next_attendee_agorot"] == 4500, d


def test_extra_guest_full_price_over_commitment():
    """מעל ההתחייבות כל אורח נספר במחיר מלא."""
    d = post("/venue-commitment", {
        "attendees": 512, "meal_price_agorot": 32000, "committed_quantity": 500,
        "extra_per_attendee_agorot": 4500,
    }).json()
    assert d["over_commitment"] == 12, d
    assert d["next_attendee_agorot"] == 32000 + 4500, d


def test_money_minimum_wins_when_higher():
    """מינימום כספי בחוזה גובר על המכפלה כשהוא גבוה ממנה."""
    d = post("/venue-commitment", {
        "attendees": 100, "meal_price_agorot": 30000,
        "committed_quantity": 100, "min_total_agorot": 5_000_000,
    }).json()
    assert d["min_total_applied"] is True, d
    assert d["meal_line"]["total_agorot"] == 5_000_000, d


def test_no_attendees_has_no_per_person_cost():
    """אין מגיעים ⇒ אין ממוצע לאדם. לא "0 ₪" — פשוט אין מספר."""
    d = post("/venue-commitment", {"attendees": 0, "meal_price_agorot": 32000}).json()
    assert d["cost_per_attendee_agorot"] is None, d
    assert d["cost_per_attendee_display"] is None, d


def test_matches_finance_engine_exactly():
    """**הבדיקה המרכזית:** אותו קלט דרך ``finance.py`` ישירות = אותו מספר."""
    payload = {
        "attendees": 463, "meal_price_agorot": 32000, "committed_quantity": 500,
        "min_total_agorot": 14_000_000, "extra_per_attendee_agorot": 4500,
        "fixed_agorot": 6_000_000,
    }
    api = post("/venue-commitment", payload).json()

    expenses = public_calc._build_expenses(public_calc.CommitmentIn(**payload))
    direct = finance.cost_breakdown(expenses, payload["attendees"], payload["attendees"])

    assert api["total_agorot"] == direct.total_agorot
    assert api["next_attendee_agorot"] == direct.next_attendee_agorot
    assert api["cost_per_attendee_agorot"] == direct.cost_per_attendee_agorot
    assert api["total_display"] == finance.format_shekels(direct.total_agorot)


def test_scenarios_include_commitment_and_current():
    d = post("/venue-commitment", {
        "attendees": 463, "meal_price_agorot": 32000, "committed_quantity": 500,
    }).json()
    points = [s["attendees"] for s in d["scenarios"]]
    assert 463 in points, points
    assert 500 in points, points
    assert any(s["is_current"] for s in d["scenarios"])
    assert any(s["is_commitment"] for s in d["scenarios"])


def test_rejects_negative_and_absurd_input():
    reset_limiter()
    assert client.post(BASE + "/venue-commitment",
                       json={"attendees": -1, "meal_price_agorot": 100}).status_code == 422
    reset_limiter()
    assert client.post(BASE + "/venue-commitment",
                       json={"attendees": 10, "meal_price_agorot": 10 ** 15}).status_code == 422


# ════════════════════════════════════════════════════════════════════════
#  לוח הזמנים
# ════════════════════════════════════════════════════════════════════════

def _future(days):
    return (date.today() + timedelta(days=days)).isoformat()


def test_timeline_has_seven_stages_ending_on_commitment_date():
    d = post("/rsvp-timeline", {"event_date": _future(90), "commit_days_before": 7}).json()
    assert len(d["placements"]) == 7, d
    calls = [p for p in d["placements"] if p["type"] == "call_round"]
    assert len(calls) == 3, calls
    # הסבב האחרון נופל בדיוק על מועד סגירת הרשימה — תאריך אחד ויחיד.
    assert calls[-1]["date"] == d["commitment_date"], d


def test_timeline_never_falls_on_weekend():
    d = post("/rsvp-timeline", {"event_date": _future(120), "commit_days_before": 5}).json()
    for p in d["placements"]:
        weekday = date.fromisoformat(p["date"]).weekday()
        assert weekday not in (4, 5), p  # שישי/שבת


def test_timeline_stages_are_strictly_ordered():
    d = post("/rsvp-timeline", {"event_date": _future(60), "commit_days_before": 10}).json()
    dates = [date.fromisoformat(p["date"]) for p in d["placements"]]
    assert dates == sorted(dates), dates
    assert len(set(dates)) == len(dates), "שני שלבים נפלו על אותו יום"


def test_timeline_compresses_when_time_is_short():
    d = post("/rsvp-timeline", {"event_date": _future(6), "commit_days_before": 2}).json()
    assert d["compressed"] is True, d
    assert len(d["placements"]) == 7, d


def test_timeline_matches_engine_exactly():
    """**הבדיקה המרכזית:** אותו אירוע דרך ``rsvp_timeline`` ישירות."""
    event_date = _future(75)
    api = post("/rsvp-timeline", {"event_date": event_date, "commit_days_before": 6}).json()

    event = models.Event(
        event_date=event_date, venue_commit_days_before=6, rsvp_track_started_at=None
    )
    direct = rsvp_timeline.compute_schedule(event)

    assert api["commitment_date"] == direct.commitment_date.isoformat()
    assert api["compressed"] == direct.compressed
    assert [p["date"] for p in api["placements"]] == [
        p.date.isoformat() for p in direct.placements
    ]


def test_timeline_rejects_past_and_broken_dates():
    reset_limiter()
    assert client.post(BASE + "/rsvp-timeline",
                       json={"event_date": "2020-01-01", "commit_days_before": 5}).status_code == 400
    reset_limiter()
    assert client.post(BASE + "/rsvp-timeline",
                       json={"event_date": "לא תאריך", "commit_days_before": 5}).status_code == 400
    reset_limiter()
    assert client.post(BASE + "/rsvp-timeline",
                       json={"event_date": _future(30), "commit_days_before": 99}).status_code == 422


def test_rate_limit_kicks_in():
    reset_limiter()
    body = {"attendees": 10, "meal_price_agorot": 30000}
    codes = {client.post(BASE + "/venue-commitment", json=body).status_code for _ in range(65)}
    assert 429 in codes, codes


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("✓", t.__name__)
    print("\n%d בדיקות עברו." % len(tests))
