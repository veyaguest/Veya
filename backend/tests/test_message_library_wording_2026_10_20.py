"""עדכון הניסוח בספריית הנוסחים (2026-10-20): כל נוסח זהה לתבנית ה-WhatsApp שלו.

נועלים: שכל נוסח בקובץ, אחרי השינוי, יכול להיות תבנית זהה לדף הנוסחים באתר
(לא נגמר במשתנה, אחרי שהקישור הופך לכפתור); שבהזמנות הקישור הוא "לצפייה
בהזמנה" ולא אישור הגעה; ושלא נוספו ולא נעלמו משתנים, חוץ מהעברת שמות בעלי
האירוע מהחתימה לשורה שאחרי הפתיחה.

הרצה: backend/venv/bin/python -m pytest backend/tests/test_message_library_wording_2026_10_20.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "meta-templates-mcp"))
import library_sync as ls  # noqa: E402

CHANGES = json.loads((ROOT / "backend" / "app" / "message_library_wording_2026_10_20.json")
                     .read_text(encoding="utf-8"))
TOKEN = re.compile(r"\{\{[a-z_]+\}\}")


def _wording(c, key):
    return {"event_type": c["event_type"], "message_type": c["message_type"],
            "option_number": c["option_number"], "tone": "", "content": c[key]}


def test_every_new_wording_can_be_an_exact_template():
    for c in CHANGES:
        d = ls.to_draft(_wording(c, "new"))
        assert d["state"] == "ok", (d["name"], d["problems_he"])


def test_same_variables():
    for c in CHANGES:
        assert sorted(TOKEN.findall(c["old"])) == sorted(TOKEN.findall(c["new"])), c


def test_invitation_link_is_view_not_rsvp():
    for c in CHANGES:
        if c["message_type"] != "invitation":
            continue
        assert "לאישור הגעה:" not in c["new"] and "\nאישור הגעה:" not in c["new"], c["option_number"]
        assert "לצפייה בהזמנה:" in c["new"] or "ההזמנה המלאה והניווט בקישור האישי." in c["new"]


def test_names_move_to_the_top_when_they_ended_the_message():
    for c in CHANGES:
        if c["message_type"] == "invitation":
            continue
        lines = [l for l in c["new"].split("\n") if l.strip()]
        assert lines[1] == "כאן {{groom_name}} ו{{bride_name}}.", c
        assert "{{groom_name}} & {{bride_name}}" not in c["new"]


def test_no_new_exclamation_or_party_emoji():
    for c in CHANGES:
        for mark in ("!", "🥳", "🎉"):
            assert c["new"].count(mark) <= c["old"].count(mark), (c["option_number"], mark)
