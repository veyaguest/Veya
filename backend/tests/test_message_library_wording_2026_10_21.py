"""עדכון הניסוח בספריית הנוסחים (2026-10-21): 18 נוסחים שנשארו בלשון זכר או עם לוכסן.

נועלים: שאין "אתה" או לוכסן בנוסחים שעודכנו, שהמשתנים לא השתנו, שכל נוסח
עדיין יכול להיות תבנית זהה לדף הנוסחים באתר, ושהודעה של אירוע קיים שבחר את
הנוסח הישן מתעדכנת (אחרת היא לא תואמת לאף תבנית ולא נשלחת), ונוסח שנערך — לא.

הרצה: backend/venv/bin/python -m pytest backend/tests/test_message_library_wording_2026_10_21.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "tools" / "meta-templates-mcp"))
import library_sync as ls  # noqa: E402

CHANGES = json.loads((ROOT / "backend" / "app" / "message_library_wording_2026_10_21.json")
                     .read_text(encoding="utf-8"))
TOKEN = re.compile(r"\{\{[a-z_]+\}\}")
H = "֐-׿"
SLASH = re.compile(rf"[{H}]/[{H}]")
MASCULINE = re.compile(rf"(?<![{H}])(אתה|מצטרף|מגיע לחגוג|שקיבלת)(?![{H}])")


def test_no_gender_slash_or_masculine():
    assert len(CHANGES) == 18
    for c in CHANGES:
        key = (c["event_type"], c["message_type"], c["option_number"])
        assert not SLASH.search(c["new"]) and not MASCULINE.search(c["new"]), key
        assert "אתם" in c["new"], key


def test_same_variables():
    for c in CHANGES:
        assert sorted(TOKEN.findall(c["old"])) == sorted(TOKEN.findall(c["new"]))


def test_still_an_exact_template():
    for c in CHANGES:
        d = ls.to_draft({"event_type": c["event_type"], "message_type": c["message_type"],
                         "option_number": c["option_number"], "tone": "", "content": c["new"]})
        assert d["state"] == "ok", (d["name"], d["problems_he"])


def test_existing_event_message_follows_the_library() -> None:
    from sqlalchemy import select

    from app import main, models
    from app.database import SessionLocal
    from tests.e2e_seating import bootstrap

    c = next(c for c in CHANGES if c["event_type"] == "wedding" and c["message_type"] == "reminder_1")
    api, _ = bootstrap()
    db = SessionLocal()
    try:
        opt = db.scalars(select(models.MessageDefaultOption).where(
            models.MessageDefaultOption.event_type == "wedding",
            models.MessageDefaultOption.message_type == "reminder_1",
            models.MessageDefaultOption.option_number == c["option_number"])).first()
        if opt is None:
            opt = models.MessageDefaultOption(event_type="wedding", message_type="reminder_1",
                                              option_number=c["option_number"], title="t", content="")
            db.add(opt)
        opt.content = c["old"]
        ev = db.get(models.Event, api.event_id)
        ev.event_type = "wedding"
        msgs = {m.message_type: m for m in db.scalars(
            select(models.EventMessage).where(models.EventMessage.event_id == ev.id))}
        for kind, content in (("reminder_1", c["old"]), ("reminder_2", c["old"] + "\nנערך")):
            m = msgs.get(kind) or models.EventMessage(event_id=ev.id, message_type=kind, is_active=True,
                                                       trigger_offset_days=0, target_audience="all")
            m.content = content
            db.add(m)
        db.commit()
    finally:
        db.close()

    main._migrate_message_library_wording()

    db = SessionLocal()
    try:
        msgs = {m.message_type: m.content for m in db.scalars(
            select(models.EventMessage).where(models.EventMessage.event_id == api.event_id))}
        assert msgs["reminder_1"] == c["new"]
        assert msgs["reminder_2"] == c["old"] + "\nנערך"
    finally:
        db.close()
