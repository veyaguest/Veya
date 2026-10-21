"""בחירת נוסח בלבד, ונוסח קבוע ליום האירוע (החלטות הבעלים 2026-10-20) — דרך ה-API.

1. אירוע חדש מקבל את הנוסח הראשון מהספרייה — ויש לו תבנית WhatsApp.
2. אפשר לבחור נוסח אחר מהרשימה; עריכה חופשית נחסמת עם הסבר.
3. יום האירוע — נוסח קבוע, לא נערך; ``wording_source = fixed``.
4. נוסח ישן שנערך — מסומן ``edited`` (לא יישלח ב-WhatsApp עד שבוחרים מהרשימה).
5. שעת שליחה עדיין ניתנת לשינוי (הנעילה היא רק על הנוסח).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, make_client  # noqa: E402


REMINDERS = [
    "היי {{guest_name}},\n\nרק מזכירים שהחתונה מתקרבת 😊\n\nלאישור הגעה:\n{{rsvp_link}}",
    "היי {{guest_name}},\n\nרצינו לוודא שההזמנה הגיעה אליכם.\n\nלאישור הגעה:\n{{rsvp_link}}",
    "היי {{guest_name}},\n\nנשמח לדעת אם תגיעו.\n\n{{rsvp_link}}",
]


def _seed_reminder_options() -> None:
    """במסד הבדיקה אין נוסחי תזכורת (בייצור הם מגיעים מפאנל האדמין)."""
    from sqlalchemy import select

    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        for i, content in enumerate(REMINDERS, 1):
            exists = db.scalar(select(models.MessageDefaultOption).where(
                models.MessageDefaultOption.event_type == "wedding",
                models.MessageDefaultOption.message_type == "reminder_1",
                models.MessageDefaultOption.option_number == i))
            if exists is None:
                db.add(models.MessageDefaultOption(event_type="wedding", message_type="reminder_1",
                                                   option_number=i, title=f"נוסח {i}", content=content))
            elif not exists.content:
                # הזריעה בעלייה יוצרת שורות ריקות (בייצור ממלאים בפאנל האדמין).
                exists.content = content
        db.commit()
    finally:
        db.close()


def bootstrap_with_options():
    # קודם השרת (שקובע את מסד הבדיקה ומריץ את העלייה), ורק אחר כך הנוסחים —
    # אחרת הם נכתבים למסד אחר.
    make_client()
    _seed_reminder_options()
    return bootstrap()


def _seq(api) -> dict:
    return {m["message_type"]: m for m in
            api.client.get("/communication/sequence", headers=api.headers).json()}


def _options(api, mt):
    return api.client.get(f"/communication/sequence/{mt}/options", headers=api.headers).json()


def test_new_event_starts_with_first_library_wording() -> None:
    api, _ = bootstrap_with_options()
    seq = _seq(api)
    rem = seq["reminder_1"]
    opts = _options(api, "reminder_1")
    assert opts and rem["content"] == opts[0]["content"]
    assert rem["wording_source"] == "library" and rem["template_name"] == "veya_wed_rem1_01"
    inv = seq["invitation"]
    assert inv["template_name"] == "veya_wed_inv_01"
    print("✓ 1: אירוע חדש — הנוסח הראשון, עם תבנית")


def test_choose_from_list_only() -> None:
    from app import message_wording

    api, _ = bootstrap_with_options()
    opts = _options(api, "reminder_1")
    r = api.client.put("/communication/sequence/reminder_1", headers=api.headers,
                       json={"content": opts[2]["content"]})
    assert r.status_code == 200 and r.json()["template_name"] == "veya_wed_rem1_03", r.text
    r = api.client.put("/communication/sequence/reminder_1", headers=api.headers,
                       json={"content": opts[2]["content"] + "\nתוספת"})
    assert r.status_code == 400 and r.json()["detail"] == message_wording.CHOOSE_FROM_LIST
    assert _seq(api)["reminder_1"]["content"] == opts[2]["content"]
    print("✓ 2: בחירה מהרשימה — כן; עריכה חופשית — לא")


def test_event_day_is_fixed() -> None:
    from app import message_wording

    api, _ = bootstrap_with_options()
    ed = _seq(api)["event_day"]
    assert ed["content"] == message_wording.FIXED_CONTENT["event_day"]
    assert ed["wording_source"] == "fixed" and ed["template_name"] == "veya_event_day"
    r = api.client.put("/communication/sequence/event_day", headers=api.headers,
                       json={"content": "נוסח אחר"})
    assert r.status_code == 400 and r.json()["detail"] == message_wording.FIXED_WORDING
    print("✓ 3: יום האירוע — נוסח קבוע")


def test_old_edited_wording_is_marked() -> None:
    from sqlalchemy import select

    from app import models
    from app.database import SessionLocal

    api, _ = bootstrap_with_options()
    db = SessionLocal()
    try:
        em = db.scalar(select(models.EventMessage).where(
            models.EventMessage.event_id == api.event_id,
            models.EventMessage.message_type == "thank_you"))
        em.content = "נוסח שנכתב ביד לפני ההחלטה"
        db.commit()
    finally:
        db.close()
    thx = _seq(api)["thank_you"]
    assert thx["wording_source"] == "edited" and thx["template_name"] is None
    print("✓ 4: נוסח ישן שנערך — מסומן")


def test_send_time_still_editable() -> None:
    api, _ = bootstrap_with_options()
    r = api.client.put("/communication/sequence/reminder_1", headers=api.headers,
                       json={"send_time": "13:00"})
    assert r.status_code == 200 and r.json()["send_time"] == "13:00", r.text
    print("✓ 5: שעת שליחה — עדיין ניתנת לשינוי")


def test_auto_message_audience_is_fixed() -> None:
    """(2026-10-21) למי הודעה אוטומטית נשלחת — קבוע: תזכורת למי שלא ענה, יום
    האירוע למי שאישר. ניסיון לשנות ל-all נדחה; אותו ערך — עובר."""
    api, _ = bootstrap_with_options()
    r = api.client.put("/communication/sequence/reminder_1", headers=api.headers,
                       json={"target_audience": "all"})
    assert r.status_code == 400, r.text
    r = api.client.put("/communication/sequence/event_day", headers=api.headers,
                       json={"target_audience": "declined"})
    assert r.status_code == 400, r.text
    r = api.client.put("/communication/sequence/reminder_1", headers=api.headers,
                       json={"target_audience": "pending"})
    assert r.status_code == 200 and r.json()["target_audience"] == "pending", r.text
    print("✓ 6: קהל היעד של הודעה אוטומטית — קבוע")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("OK — בחירת נוסח ונוסח קבוע")
