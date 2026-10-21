"""בבקשת האישור ובתזכורות — רק נוסחי שירות (החלטת הבעלים 2026-10-21).

הסיווג מגיע מ-Meta (``whatsapp_template_status.category_of``); כאן מוחלף ב-
``_category_override``. נועלים:
1. רשימת הבחירה של הזוג — רק נוסחים שהתבנית שלהם ``UTILITY``.
2. שמירת נוסח שיווקי נחסמת; נוסח שירות — עובר.
3. אירוע חדש מתחיל מנוסח השירות הראשון.
4. אירוע קיים שבחר נוסח שיווקי עובר לנוסח השירות הראשון; נוסח שנערך — לא נוגעים.
5. אין מידע על סיווג (אין חיבור ל-Meta) — לא מסננים.
6. דף הנוסחים הציבורי מסמן ``choosable`` וסופר רק אותם; הנוסחים האחרים עדיין
   מוחזרים (כלי התבניות משווה מולם).

הרצה: backend/venv/bin/python -m pytest backend/tests/test_utility_only_wordings.py
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_message_wording import REMINDERS, _options, _seq, bootstrap_with_options  # noqa: E402

CATEGORIES = {
    ("veya_wed_rem1_01", "he"): "MARKETING",
    ("veya_wed_rem1_02", "he"): "UTILITY",
    ("veya_wed_rem1_03", "he"): "MARKETING",
}


@contextmanager
def categories(mapping):
    from app import whatsapp_template_status as status

    status._category_override = mapping
    try:
        yield
    finally:
        status._category_override = None


def _set_content(api, mt: str, content: str) -> None:
    from sqlalchemy import select

    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        em = db.scalar(select(models.EventMessage).where(
            models.EventMessage.event_id == api.event_id, models.EventMessage.message_type == mt))
        em.content = content
        db.commit()
    finally:
        db.close()


def test_only_utility_wordings_can_be_chosen() -> None:
    with categories(CATEGORIES):
        api, _ = bootstrap_with_options()
        assert [o["content"] for o in _options(api, "reminder_1")] == [REMINDERS[1]]
        r = api.client.put("/communication/sequence/reminder_1", headers=api.headers,
                           json={"content": REMINDERS[0]})
        assert r.status_code == 400, r.text
        r = api.client.put("/communication/sequence/reminder_1", headers=api.headers,
                           json={"content": REMINDERS[1]})
        assert r.status_code == 200, r.text


def test_new_event_starts_from_the_first_utility_wording() -> None:
    with categories(CATEGORIES):
        api, _ = bootstrap_with_options()
        assert _seq(api)["reminder_1"]["content"] == REMINDERS[1]


def test_existing_marketing_choice_switches_edited_stays() -> None:
    with categories(CATEGORIES):
        api, _ = bootstrap_with_options()
        _seq(api)
        _set_content(api, "reminder_1", REMINDERS[2])
        assert _seq(api)["reminder_1"]["content"] == REMINDERS[1]

        edited = REMINDERS[2] + "\nנוסח שנערך"
        _set_content(api, "reminder_1", edited)
        assert _seq(api)["reminder_1"]["content"] == edited


def test_unknown_categories_do_not_filter() -> None:
    with categories({}):
        api, _ = bootstrap_with_options()
        contents = [o["content"] for o in _options(api, "reminder_1")]
        assert all(c in contents for c in REMINDERS), contents


def test_public_library_marks_choosable() -> None:
    with categories(CATEGORIES):
        api, _ = bootstrap_with_options()
        d = api.client.get("/public/library").json()
    wordings = [w for c in d["categories"] for w in c["wordings"]]
    rem1 = {w["option_number"]: w["choosable"] for w in wordings
            if w["event_type"] == "wedding" and w["message_type"] == "reminder_1"}
    assert rem1[1] is False and rem1[2] is True and rem1[3] is False, rem1
    assert d["total"] == sum(1 for w in wordings if w["choosable"])
    assert all(w["choosable"] for w in wordings if w["message_type"] == "invitation")
