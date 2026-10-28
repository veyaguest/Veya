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


def test_meta_failure_is_not_retried_on_every_question() -> None:
    """(2026-10-21) Meta לא עונה — לא מנסים שוב בכל שאלה על תבנית (עשרות בפתיחת
    מסך ההודעות, אחת לכל הודעה במנה), אלא לכל היותר פעם בדקה."""
    from app import whatsapp_template_status as status

    calls = []
    real = status._fetch
    status._fetch = lambda: calls.append(1)
    status.reset()
    try:
        for _ in range(30):
            status.category_of("veya_wed_rem1_02")
            status.is_sendable("veya_wed_rem1_02")
        assert len(calls) == 1, len(calls)
    finally:
        status._fetch = real
        status.reset()


def test_view_only_screen_load_survives_a_failed_switch() -> None:
    """מסך ההודעות נטען גם כשההחלפה לנוסח שירות נכשלת (למשל RLS לצופה בלבד)."""
    from unittest import mock

    from app import message_wording

    with categories(CATEGORIES):
        api, _ = bootstrap_with_options()
        with mock.patch.object(message_wording, "switch_to_utility", side_effect=RuntimeError("rls")):
            r = api.client.get("/communication/sequence", headers=api.headers)
    assert r.status_code == 200, r.text


def test_retired_wording_is_hidden_and_events_move_off_it(tmp_path) -> None:
    """(2026-10-28) נוסח שהוסר מהספרייה: לא מוצג לבחירה, ואירוע שבחר אותו עובר
    לנוסח השירות הראשון — גם בלי שום מידע מ-Meta (אחרי מחיקת התבנית אין לה סיווג).
    נוסח שנערך בפאנל האדמין (תוכן אחר) לא מכובה."""
    import json

    from sqlalchemy import select

    from app import main, message_wording, models
    from app.database import SessionLocal

    retired = tmp_path / "retired.json"
    retired.write_text(json.dumps([
        {"event_type": "wedding", "message_type": "reminder_1", "option_number": 1, "content": REMINDERS[0]},
        {"event_type": "wedding", "message_type": "reminder_1", "option_number": 3, "content": "נוסח אחר"},
    ], ensure_ascii=False), encoding="utf-8")
    real_file = message_wording.RETIRED_FILE
    message_wording.RETIRED_FILE = retired
    with categories({}):
        api, _ = bootstrap_with_options()
        _seq(api)
        _set_content(api, "reminder_1", REMINDERS[0])

        def option(n):
            db = SessionLocal()
            try:
                return db.scalar(select(models.MessageDefaultOption).where(
                    models.MessageDefaultOption.event_type == "wedding",
                    models.MessageDefaultOption.message_type == "reminder_1",
                    models.MessageDefaultOption.option_number == n))
            finally:
                db.close()

        try:
            main._retire_library_options()
            assert option(1).is_active is False and option(3).is_active is True
            contents = [o["content"] for o in _options(api, "reminder_1")]
            assert REMINDERS[0] not in contents and REMINDERS[1] in contents
            moved_to = _seq(api)["reminder_1"]["content"]
            assert moved_to != REMINDERS[0] and moved_to in contents, moved_to
        finally:
            message_wording.RETIRED_FILE = real_file
            db = SessionLocal()
            try:
                db.get(models.MessageDefaultOption, option(1).id).is_active = True
                db.commit()
            finally:
                db.close()
