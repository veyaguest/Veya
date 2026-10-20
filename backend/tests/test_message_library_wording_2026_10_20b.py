"""עדכון הניסוח בספריית הנוסחים (2026-10-20b): פנייה לשני המינים.

נועלים: שאין יותר לוכסן מגדרי או פנייה בלשון זכר בנוסחים שעודכנו, שהמשתנים
לא השתנו, ושכל נוסח עדיין יכול להיות תבנית זהה לדף הנוסחים באתר.

הרצה: backend/venv/bin/python -m pytest backend/tests/test_message_library_wording_2026_10_20b.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "meta-templates-mcp"))
import library_sync as ls  # noqa: E402

CHANGES = json.loads((ROOT / "backend" / "app" / "message_library_wording_2026_10_20b.json")
                     .read_text(encoding="utf-8"))
TOKEN = re.compile(r"\{\{[a-z_]+\}\}")
H = "֐-׿"
SLASH = re.compile(rf"[{H}]/[יה](?![{H}])")
MASCULINE = re.compile(rf"(?<![{H}])(ש?תהיה|ש?תגיע|ש?תוכל|ש?תבוא|ש?תצטרף|ש?תעדכן|אותך|איתך|אליך|ממך|לך)(?![{H}])")


def test_no_gender_slash_or_masculine_only():
    for c in CHANGES:
        assert not SLASH.search(c["new"]), (c["event_type"], c["message_type"], c["option_number"])
        assert not MASCULINE.search(c["new"]), (c["event_type"], c["message_type"], c["option_number"])


def test_same_variables():
    for c in CHANGES:
        assert sorted(TOKEN.findall(c["old"])) == sorted(TOKEN.findall(c["new"]))


def test_still_an_exact_template():
    for c in CHANGES:
        d = ls.to_draft({"event_type": c["event_type"], "message_type": c["message_type"],
                         "option_number": c["option_number"], "tone": "", "content": c["new"]})
        assert d["state"] == "ok", (d["name"], d["problems_he"])
