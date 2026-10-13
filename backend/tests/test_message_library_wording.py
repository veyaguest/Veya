"""עדכון הניסוח בספריית הנוסחים (2026-10-13).

נועלים שלושה דברים: שהנוסחים החדשים נכנסים במסד חדש, שנוסח שנערך בפאנל
האדמין לא נדרס, ושהנוסחים החדשים שומרים את אותם משתנים ועומדים בכללים
(פנייה ברבים בהזמנות, בלי ❤️, בלי "!" ובלי 🥳).

הרצה: python3 backend/tests/test_message_library_wording.py
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("VEYA_DB_URL", "sqlite://")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import _MESSAGE_LIBRARY_WORDING_FILE, _migrate_message_library_wording, app  # noqa: E402

with TestClient(app):
    pass

CHANGES = json.loads(_MESSAGE_LIBRARY_WORDING_FILE.read_text(encoding="utf-8"))
TOKEN = re.compile(r"\{\{[a-z_]+\}\}")


def _options():
    db = SessionLocal()
    try:
        return {
            (o.event_type, o.message_type, o.option_number): o
            for o in db.scalars(select(models.MessageDefaultOption))
        }
    finally:
        db.close()


def test_new_wording_after_startup():
    opts = _options()
    for c in CHANGES:
        row = opts[(c["event_type"], c["message_type"], c["option_number"])]
        assert row.content == c["new"], (c["event_type"], c["option_number"])


def test_default_message_follows_option_one():
    db = SessionLocal()
    try:
        olds = {(c["event_type"], c["old"]) for c in CHANGES if c["message_type"] == "rsvp_request"}
        for d in db.scalars(select(models.MessageDefault).where(models.MessageDefault.message_type == "rsvp_request")):
            assert (d.event_type, d.content) not in olds, d.event_type
    finally:
        db.close()


def test_admin_edit_is_not_overwritten():
    c = CHANGES[0]
    db = SessionLocal()
    try:
        row = db.scalars(select(models.MessageDefaultOption).where(
            models.MessageDefaultOption.event_type == c["event_type"],
            models.MessageDefaultOption.message_type == c["message_type"],
            models.MessageDefaultOption.option_number == c["option_number"],
        )).one()
        row.content = "נוסח שנכתב בפאנל"
        db.commit()
    finally:
        db.close()
    _migrate_message_library_wording()
    _migrate_message_library_wording()  # idempotent
    assert _options()[(c["event_type"], c["message_type"], c["option_number"])].content == "נוסח שנכתב בפאנל"


def test_same_variables_and_rules():
    for c in CHANGES:
        assert sorted(TOKEN.findall(c["old"])) == sorted(TOKEN.findall(c["new"])), c["option_number"]
        assert "❤️" not in c["new"] and "!" not in c["new"] and "🥳" not in c["new"]
        if c["message_type"] == "invitation":
            assert not re.search(r"אותך|איתך|שתהיה |שתגיע ", c["new"]), c["option_number"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("✓", name)
    print("OK — ניסוח ספריית הנוסחים")
