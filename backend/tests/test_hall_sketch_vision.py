"""בדיקות ל-AI Vision לסקיצת אולם — דרך ה-API האמיתי, בלי לפנות ל-Claude בפועל.

הרצה: ``python tests/test_hall_sketch_vision.py``
(עובד גם בלי pytest מותקן — סקריפט עצמאי עם ``assert``, בדיוק כמו test_seating_flow.py).

מה נבדק כאן:
- ``_validate_elements`` דוחה אלמנטים עם קואורדינטות/טיפוס לא תקינים ולעולם
  לא סומך עיוורות על מה שהמודל מחזיר (ai-guidelines.md).
- ``POST /hall/sketch/analyze`` הוא **תצוגה מקדימה בלבד** — שום דבר לא נכתב
  ל-Event, בדיוק כמו ``/guests/import/preview``.
- חסר ``ANTHROPIC_API_KEY`` נכשל בהודעת שגיאה ברורה בעברית, לא קריסה.
- מגביל הקצב (``hall_sketch_limiter``) חוסם אחרי יותר מדי ניסיונות לאותו אירוע.

קריאת ה-HTTP האמיתית ל-Claude (``hall_vision.analyze_sketch``) מוחלפת ידנית
(שמירה/שחזור של הפונקציה על המודול) — שום קריאת רשת אמיתית ושום עלות API כאן.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402

from app import hall_vision  # noqa: E402
from app.ratelimit import hall_sketch_limiter  # noqa: E402

_TINY_PNG_DATA_URL = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgAAI"
    "AAAUAAen63NgAAAAASUVORK5CYII="
)


def test_validate_elements_rejects_garbage() -> None:
    """קואורדינטות מחוץ לטווח / טיפוס לא מוכר / שדות חסרים — נופלים בשקט, לא קורסים."""
    raw = [
        {"type": "round_table", "x": 0.3, "y": 0.4, "width": 0.1, "height": 0.1, "confidence": 0.9},
        {"type": "round_table", "x": 1.5, "y": 0.4, "width": 0.1, "height": 0.1, "confidence": 0.9},  # x מחוץ לטווח
        {"type": "flying_unicorn", "x": 0.1, "y": 0.1, "width": 0.1, "height": 0.1, "confidence": 0.9},  # טיפוס לא מוכר
        {"type": "bar", "x": 0.2, "y": 0.2, "width": 0.1, "height": 0.1, "confidence": 5.0},  # confidence מחוץ לטווח
        {"type": "bar", "x": 0.2, "y": 0.2},  # שדות חובה חסרים
        "not even a dict",
    ]
    out = hall_vision._validate_elements(raw)
    assert len(out) == 1, f"ציפינו לאלמנט תקין יחיד, קיבלנו {out}"
    assert out[0]["type"] == "round_table"
    print("✓ _validate_elements דוחה קלט לא תקין בלי לקרוס")


def test_analyze_missing_api_key_gives_clean_error() -> None:
    old = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        try:
            hall_vision.analyze_sketch(b"fake-bytes", "image/png")
            assert False, "היה אמור לזרוק HallVisionError"
        except hall_vision.HallVisionError as exc:
            assert "API" in str(exc) or "מפתח" in str(exc)
        print("✓ חסר ANTHROPIC_API_KEY נכשל בהודעה ברורה, לא בקריסה")
    finally:
        if old is not None:
            os.environ["ANTHROPIC_API_KEY"] = old


def test_analyze_endpoint_is_preview_only() -> None:
    """הראוטר לא כותב שום דבר ל-Event — רק מחזיר את מה ש-analyze_sketch מחזיר."""
    fake_elements = [
        {"type": "round_table", "x": 0.2, "y": 0.3, "width": 0.08, "height": 0.08,
         "rotation": 0.0, "capacity": 12, "confidence": 0.95, "label": ""},
        {"type": "dance_floor", "x": 0.5, "y": 0.6, "width": 0.2, "height": 0.15,
         "rotation": 0.0, "capacity": None, "confidence": 0.7, "label": ""},
    ]
    original = hall_vision.analyze_sketch
    hall_vision.analyze_sketch = lambda raw, ct: fake_elements
    api, teardown = bootstrap()
    try:
        hall_before = api.get_hall()
        r = api.client.post(
            "/hall/sketch/analyze",
            headers=api.headers,
            json={"image": _TINY_PNG_DATA_URL},
        )
        assert r.status_code == 200, r.text
        elements = r.json()["elements"]
        assert len(elements) == 2
        assert elements[0]["type"] == "round_table"
        assert elements[1]["type"] == "dance_floor"

        hall_after = api.get_hall()
        assert hall_after["tables"] == hall_before["tables"] == [], (
            "sketch/analyze לא אמור לכתוב שולחנות ל-Event"
        )
        assert hall_after["elements"] == hall_before["elements"] == [], (
            "sketch/analyze לא אמור לכתוב אלמנטים ל-Event"
        )
        print("✓ POST /hall/sketch/analyze הוא תצוגה מקדימה בלבד — שום דבר לא נשמר")
    finally:
        hall_vision.analyze_sketch = original
        teardown()


def test_analyze_endpoint_rate_limited() -> None:
    original = hall_vision.analyze_sketch
    hall_vision.analyze_sketch = lambda raw, ct: []
    api, teardown = bootstrap()
    try:
        key = str(api.event_id)
        # מרוקנים את המכסה ידנית במקום לשלוח 15 בקשות אמיתיות.
        for _ in range(15):
            hall_sketch_limiter.record_fail(key)
        r = api.client.post(
            "/hall/sketch/analyze",
            headers=api.headers,
            json={"image": _TINY_PNG_DATA_URL},
        )
        assert r.status_code == 429, f"ציפינו לחסימת קצב, קיבלנו {r.status_code}: {r.text}"
        print("✓ hall_sketch_limiter חוסם אחרי יותר מדי ניסיונות לאותו אירוע")
    finally:
        hall_vision.analyze_sketch = original
        teardown()


if __name__ == "__main__":
    try:
        test_validate_elements_rejects_garbage()
        test_analyze_missing_api_key_gives_clean_error()
        test_analyze_endpoint_is_preview_only()
        test_analyze_endpoint_rate_limited()
        print("OK — בדיקות AI Vision לסקיצת אולם עוברות.")
    finally:
        shutdown()
