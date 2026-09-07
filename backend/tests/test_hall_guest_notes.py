"""``GET /hall`` חושף את ההערות שרלוונטיות להושבה — ורק אותן.

מרחב העבודה של ההושבה (סרגל המוזמנים לצד סקיצת האולם) מציג ליד כל מוזמן
את מה שמשפיע על השיבוץ שלו. הבדיקה נועלת שני דברים:

1. ``seating_notes`` (מה שהבעלים כתב כהערת הושבה) ו-``guest_note`` (מה
   שהמוזמן עצמו מסר ב-RSVP) **כן** מגיעים ב-``HallGuest``.
2. ``notes_raw`` — ההערה הפנימית ("צריך לחזור אליו") — **לא** מגיע. מנוע
   ההושבה לעולם לא קורא אותו (ראו ``seating-engine.md``), ולכן גם מסך
   ההושבה לא מציג אותו. חשיפה שלו כאן הייתה הופכת הערה תפעולית לשיקול
   הושבה, וזה בדיוק מה שההפרדה הזו נועדה למנוע.

הרצה: ``python tests/test_hall_guest_notes.py``
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


def _guest_in_hall(hall: dict, full_name: str) -> dict:
    """המוזמן כפי שהוא מוחזר ב-``GET /hall`` — משובץ או ללא שולחן."""
    for t in hall["tables"]:
        for g in t["guests"]:
            if g["full_name"] == full_name:
                return g
    for g in hall["unassigned"]:
        if g["full_name"] == full_name:
            return g
    raise AssertionError(f"{full_name} לא נמצא ב-GET /hall")


def test_seating_notes_are_exposed() -> None:
    """הערת הושבה מגיעה למסך האולם."""
    api, teardown = bootstrap()
    try:
        api.add_guest(
            "אבי כהן", "0501111111", seating_notes="לשבת עם דנה כהן"
        )
        g = _guest_in_hall(api.get_hall(), "אבי כהן")
        assert g["seating_notes"] == "לשבת עם דנה כהן", g
        print("✓ seating_notes נחשף ב-GET /hall")
    finally:
        teardown()


def test_internal_note_is_not_exposed() -> None:
    """ההערה הפנימית לא נחשפת למסך ההושבה."""
    api, teardown = bootstrap()
    try:
        api.add_guest("דנה כהן", "0502222222", notes_raw="צריך לחזור אליה")
        g = _guest_in_hall(api.get_hall(), "דנה כהן")
        assert "notes_raw" not in g, f"ההערה הפנימית נחשפה למסך ההושבה: {g}"
        # ולא "דלפה" לשדה ההושבה בדרך.
        assert g["seating_notes"] is None, g
        print("✓ notes_raw לא נחשף ב-GET /hall")
    finally:
        teardown()


def test_guest_note_is_exposed() -> None:
    """הערה שהמוזמן עצמו מסר ב-RSVP מגיעה למסך האולם."""
    api, teardown = bootstrap()
    try:
        g = api.add_guest("רון לוי", "0503333333")
        r = api.client.patch(
            f"/guests/{g['id']}",
            headers=api.headers,
            json={"guest_note": "כיסא גלגלים"},
        )
        assert r.status_code == 200, r.text
        row = _guest_in_hall(api.get_hall(), "רון לוי")
        assert row["guest_note"] == "כיסא גלגלים", row
        print("✓ guest_note נחשף ב-GET /hall")
    finally:
        teardown()


def test_notes_are_optional() -> None:
    """מוזמן בלי הערות בכלל — שני השדות ריקים, בלי שגיאה."""
    api, teardown = bootstrap()
    try:
        api.add_guest("יעל שדה", "0504444444")
        g = _guest_in_hall(api.get_hall(), "יעל שדה")
        assert g["seating_notes"] is None and g["guest_note"] is None, g
        print("✓ מוזמן בלי הערות מוחזר תקין")
    finally:
        teardown()


if __name__ == "__main__":
    try:
        test_seating_notes_are_exposed()
        test_internal_note_is_not_exposed()
        test_guest_note_is_exposed()
        test_notes_are_optional()
        print("OK — הערות ההושבה נחשפות ב-GET /hall, וההערה הפנימית לא.")
    finally:
        shutdown()
