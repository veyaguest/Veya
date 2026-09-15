"""בדיקות API למועד סגירת הרשימה: ברירת מחדל לאירוע קרוב וחסימת מועד שכבר עבר.

- ``GET /event`` מחזיר ``commit_default_days`` = 1 לאירוע קרוב שלא נבחר לו
  מועד, ו-``None`` לאירוע רחוק או כשכבר נבחר מועד.
- ``PATCH /event`` דוחה בחירה שהייתה סוגרת את הרשימה בתאריך שכבר עבר
  (למשל 5 ימים לפני אירוע שמתקיים בעוד 3 ימים).
- ``GET /automation/timeline`` מציג לוח זמנים לאירוע קרוב גם בלי בחירה.

הרצה: ``venv/bin/python tests/test_event_commit_default.py``
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


def _set_event_date(api, days_out: int) -> None:
    from app import models
    from app.database import SessionLocal, set_request_identity

    set_request_identity(None)
    db = SessionLocal()
    try:
        event = db.get(models.Event, api.event_id)
        event.event_date = (date.today() + timedelta(days=days_out)).isoformat()
        event.venue_commit_days_before = None
        db.commit()
    finally:
        db.close()


def _get(api) -> dict:
    r = api.client.get("/event", headers=api.headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_default_only_for_near_event_without_choice() -> None:
    api, _ = bootstrap("brit")
    _set_event_date(api, 7)
    assert _get(api)["commit_default_days"] == 1
    _set_event_date(api, 30)
    assert _get(api)["commit_default_days"] is None, "אירוע רחוק — בעל האירוע בוחר"
    _set_event_date(api, 7)
    r = api.client.patch("/event", headers=api.headers, json={"venue_commit_days_before": 3})
    assert r.status_code == 200, r.text
    assert _get(api)["commit_default_days"] is None, "כבר נבחר מועד — אין ברירת מחדל"
    print("✓ ברירת מחדל רק לאירוע קרוב בלי בחירה")


def test_commit_in_the_past_is_rejected() -> None:
    api, _ = bootstrap("brita")
    _set_event_date(api, 3)
    r = api.client.patch("/event", headers=api.headers, json={"venue_commit_days_before": 5})
    assert r.status_code == 400, r.text
    assert "כבר הייתה סגורה" in r.json()["detail"]
    assert _get(api)["venue_commit_days_before"] is None, "הבחירה נשמרה למרות הדחייה"
    r = api.client.patch("/event", headers=api.headers, json={"venue_commit_days_before": 3})
    assert r.status_code == 200, "סגירה היום (3 ימים לפני אירוע בעוד 3 ימים) מותרת"
    print("✓ מועד סגירה שכבר עבר נדחה, סגירה היום מותרת")


def test_timeline_shows_default_schedule() -> None:
    api, _ = bootstrap()
    _set_event_date(api, 10)
    r = api.client.get("/automation/timeline", headers=api.headers)
    assert r.status_code == 200, r.text
    view = r.json()
    assert view["configured"] is True and view["commit_is_default"] is True, view
    assert view["commit_days_before"] == 1
    print("✓ לוח הזמנים מוצג לאירוע קרוב גם בלי בחירה")


if __name__ == "__main__":
    try:
        test_default_only_for_near_event_without_choice()
        test_commit_in_the_past_is_rejected()
        test_timeline_shows_default_schedule()
        print("\nכל בדיקות ברירת המחדל של מועד הסגירה עברו ✓")
    finally:
        shutdown()
