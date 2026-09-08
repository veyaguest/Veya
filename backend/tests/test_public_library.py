"""ספריית הנוסחים הציבורית — מקור אמת אחד, בלי דליפת תוכן רגיש.

הלוגיקה החדשה היחידה כאן היא **קיבוץ לקטגוריות וסינון**. הבדיקות נועדו
לנעול בדיוק את שני אלה: שנוסחי "אירוע נדחה" לא ידלפו לדף ציבורי, ושקטגוריה
בלי תוכן לא תוחזר בכלל (כדי שהאתר לא יבטיח נוסחים שלא קיימים).

הרצה: python3 backend/tests/test_public_library.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("VEYA_DB_URL", "sqlite://")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import communication, models  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.routers import public_library  # noqa: E402

client = TestClient(app)


def fetch():
    public_library.library_limiter._hits.clear()
    r = client.get("/public/library")
    assert r.status_code == 200, r.text
    return r.json()


def test_postponement_wordings_never_leak():
    """נוסחי 'אירוע נדחה' לא מופיעים בדף ציבורי בשום צורה."""
    assert "postponement" not in public_library.PUBLIC_MESSAGE_TYPES
    d = fetch()
    for c in d["categories"]:
        for w in c["wordings"]:
            assert w["message_type"] != "postponement", w
            assert "postponement" not in c["message_types"], c["key"]


def test_only_categories_with_content_are_returned():
    """קטגוריה בלי נוסחים לא מוחזרת — לא מבטיחים תוכן שלא קיים."""
    d = fetch()
    for c in d["categories"]:
        assert c["wordings"], c["key"]
        assert c["event_types"], c["key"]


def test_no_empty_or_inactive_wordings():
    d = fetch()
    for c in d["categories"]:
        for w in c["wordings"]:
            assert w["content"].strip(), w


def test_matches_the_database_rows():
    """**הבדיקה המרכזית:** אותן שורות שהמוצר משתמש בהן, בלי עותק מקביל."""
    d = fetch()
    with SessionLocal() as db:
        rows = db.scalars(
            select(models.MessageDefaultOption)
            .where(models.MessageDefaultOption.is_active == True)  # noqa: E712
            .where(models.MessageDefaultOption.content != "")
            .where(
                models.MessageDefaultOption.message_type.in_(
                    public_library.PUBLIC_MESSAGE_TYPES
                )
            )
        ).all()
    assert d["total"] == len(rows), (d["total"], len(rows))

    api_contents = {
        (w["event_type"], w["message_type"], w["option_number"]): w["content"]
        for c in d["categories"]
        for w in c["wordings"]
    }
    for row in rows:
        key = (row.event_type, row.message_type, row.option_number)
        assert key in api_contents, key
        assert api_contents[key] == row.content, key


def test_labels_come_from_the_lexicon():
    """התוויות נשאבות מהלקסיקון ולא נכתבות בנתיב הציבורי."""
    d = fetch()
    for c in d["categories"]:
        for w in c["wordings"]:
            assert w["message_type_label"] == communication.MESSAGE_TYPE_LABELS[w["message_type"]]
            assert w["event_type_label"] and w["event_type_label"] != w["event_type"]


def test_every_category_key_is_covered_by_the_message_sequence():
    """כל סוג הודעה ברצף הקבוע שייך לקטגוריה אחת בדיוק."""
    seen = {}
    for key, _label, types in public_library.CATEGORIES:
        for t in types:
            assert t not in seen, "סוג הודעה בשתי קטגוריות: %s" % t
            seen[t] = key
    for t in communication.MESSAGE_TYPES:
        assert t in seen, "סוג הודעה בלי קטגוריה: %s" % t


def test_rate_limited():
    public_library.library_limiter._hits.clear()
    codes = {client.get("/public/library").status_code for _ in range(65)}
    assert 429 in codes, codes


def test_gift_references_never_reach_the_public_page():
    """נוסח שמזכיר מתנה באשראי לא מתפרסם — גם אם הבעלים ימלא אותו באדמין.

    הפיצ'ר אינו משוחרר, ויש כלל נעול שאין להזכיר אותו בשיווק. בלי החסימה
    הזו, מילוי קטגוריית "יום האירוע" באדמין היה מפרסם את ההזכרה בשקט.
    """
    assert public_library._is_publishable("היי, נשמח לראותכם") is True
    assert public_library._is_publishable("אפשר גם להעניק מתנה באשראי") is False
    assert public_library._is_publishable("קישור: {{gift_link}}") is False
    assert public_library._is_publishable("{{GIFT_LINK}}") is False

    d = fetch()
    for c in d["categories"]:
        for w in c["wordings"]:
            low = w["content"].lower()
            assert "gift_link" not in low, w
            assert "מתנה באשראי" not in w["content"], w
            assert "מתנות באשראי" not in w["content"], w


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("✓", t.__name__)
    print("\n%d בדיקות עברו." % len(tests))
