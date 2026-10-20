"""בחירת תבנית ה-WhatsApp לפי הנוסח שהזוג בחר (2026-10-20) — מול Meta מזויפת.

מכסה:
1. נוסח מהספרייה → התבנית שלו (``veya_wed_rem1_02``), משתנים לפי הסדר, כפתור אישי.
2. נוסח שנערך (לא בספרייה) → לא נשלח, לא נרשם, וההסבר בעברית.
3. הזמנה: לאירוע עם תמונה — גרסת ``_img``; בלי — הגרסה הרגילה; כפתור "לצפייה".
4. כפתור ניווט: כפתור שני עם הכתובת; בלי כתובת — לא נשלח (Meta דוחה ערך ריק).
5. יום האירוע: עם שולחן → ``veya_event_day_table``; בלי → ``veya_event_day``.
6. שינוי מועד: לפני שנקבע תאריך → ``veya_postponement_no_date``.
7. תבנית שעוד לא אושרה ב-Meta → לא נשלחת ולא "נשרפת".
8. הקוד והכלי שיוצר את התבניות משתמשים באותה המרה (שם וסדר משתנים זהים).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402,F401 — הטבלאות נרשמות לפני create_all

from tests.test_whatsapp_meta_api import FakeMeta, meta_env, ok  # noqa: E402
from tests.test_whatsapp_safety import _engine, _event, _guest, _phone  # noqa: E402

REM = "היי {{guest_name}},\n\nרק מזכירים שה{{host_names}} מתקרבים 😊\n\nלאישור הגעה:\n{{rsvp_link}}"
INV = ("היי {{guest_name}},\n\nשמחים להזמין אתכם לחתונה של {{host_names}}.\n\n📅 {{event_date}}\n"
       "📍 {{venue_name}}\n\nנשמח לראות אתכם.\n\nלצפייה בהזמנה:\n{{rsvp_link}}\n\nלניווט:\n{{navigation_link}}")


def _setup(db, *, kind="reminder_1", content=REM, option=2, chosen=None, **event_kw):
    from app import models

    ev = _event(db, **event_kw)
    db.add(models.MessageDefaultOption(event_type="wedding", message_type=kind,
                                       option_number=option, title="t", content=content))
    db.add(models.EventMessage(event_id=ev.id, message_type=kind, content=chosen or content,
                               is_active=True, trigger_offset_days=0, target_audience="all"))
    phone = _phone()
    g = _guest(db, ev.id, phone, name="דנה כהן")
    g.guest_token = "tok-abc123"
    db.commit()
    return ev, g


def _send(db, ev, g, kind, fake):
    from app import outbound

    with meta_env(mode="meta_test", recipients=g.phone, fake=fake):
        result = outbound.send_batch(db, ev, [outbound.OutboundItem(guest=g, phone=g.phone, text="x", kind=kind)])
        db.commit()
    return result, [json.loads(r.content) for r in fake.requests if r.url.path.endswith("/messages")]


def _buttons(body):
    return [(c["index"], c["parameters"][0]["text"])
            for c in body["template"].get("components", []) if c["type"] == "button"]


def _params(body):
    comps = [c for c in body["template"]["components"] if c["type"] == "body"]
    return [p["text"] for p in comps[0]["parameters"]] if comps else []


def test_library_wording_sends_its_own_template() -> None:
    db = Session(_engine())
    ev, g = _setup(db)
    result, bodies = _send(db, ev, g, "reminder_1", FakeMeta(ok("wamid.1")))
    assert result.sent == 1 and bodies[0]["template"]["name"] == "veya_wed_rem1_02"
    assert _params(bodies[0]) == ["דנה", "יואב ודנה"]
    assert _buttons(bodies[0]) == [("0", "tok-abc123")]
    print("✓ 1: נוסח מהספרייה → התבנית שלו, משתנים לפי הסדר")


def test_edited_wording_is_not_sent() -> None:
    from app import messaging, models, whatsapp_templates as wt
    from sqlalchemy import select

    db = Session(_engine())
    ev, g = _setup(db, chosen=REM + "\nנוסח שנערך")
    fake = FakeMeta()
    result, bodies = _send(db, ev, g, "reminder_1", fake)
    assert bodies == [] and result.sent == 0
    assert db.scalars(select(models.Message)).all() == []
    assert wt.resolve("reminder_1", ev, g) == (None, wt.NOT_LIBRARY_WORDING)
    assert "בחרו נוסח מהרשימה" in messaging._NOT_SENT_DETAIL[wt.NOT_LIBRARY_WORDING]
    print("✓ 2: נוסח שנערך — לא נשלח ולא נרשם")


def test_invitation_image_variant_and_view_button() -> None:
    from app import whatsapp_templates as wt

    db = Session(_engine())
    ev, g = _setup(db, kind="invitation", content=INV, option=1, venue_address="הזורע 12, רמת גן",
                   venue_name="גן האירועים")
    spec, _ = wt.resolve("invitation", ev, g)
    assert spec.name == "veya_wed_inv_01" and not spec.header_image
    ev.invite_image = "/media/x"
    spec, _ = wt.resolve("invitation", ev, g)
    assert spec.name == "veya_wed_inv_01_img" and spec.header_image
    print("✓ 3: הזמנה — עם תמונה _img, בלי תמונה הגרסה הרגילה")


def test_navigation_button_gets_the_address() -> None:
    db = Session(_engine())
    ev, g = _setup(db, kind="invitation", content=INV, option=1, venue_address="הזורע 12, רמת גן",
                   venue_name="גן האירועים")
    result, bodies = _send(db, ev, g, "invitation", FakeMeta(ok("wamid.2")))
    assert result.sent == 1
    assert _buttons(bodies[0]) == [("0", "tok-abc123"), ("1", "%D7%94%D7%96%D7%95%D7%A8%D7%A2+12%2C+%D7%A8%D7%9E%D7%AA+%D7%92%D7%9F")]
    db2 = Session(_engine())
    ev2, g2 = _setup(db2, kind="invitation", content=INV, option=1, venue_name="גן האירועים")
    result2, bodies2 = _send(db2, ev2, g2, "invitation", FakeMeta())
    assert bodies2 == [] and result2.sent == 0
    print("✓ 4: כפתור ניווט עם הכתובת; בלי כתובת — לא נשלח")


def test_event_day_table_and_postponement_fixed_templates() -> None:
    from app import whatsapp_templates as wt

    db = Session(_engine())
    ev, g = _setup(db)
    assert wt.resolve("event_day", ev, g)[0].name == "veya_event_day"
    g.table_number = 7
    assert wt.resolve("event_day", ev, g)[0].name == "veya_event_day_table"
    assert wt.resolve("postponement", ev, g)[0].name == "veya_postponement_no_date"
    print("✓ 5–6: יום האירוע ושינוי מועד — התבניות הקבועות")


def test_pending_template_is_not_sent_or_consumed() -> None:
    from app import whatsapp_template_status as status

    db = Session(_engine())
    ev, g = _setup(db)
    status._override = {("veya_wed_rem1_02", "he"): "PENDING"}
    try:
        result, bodies = _send(db, ev, g, "reminder_1", FakeMeta())
        assert bodies == [] and result.sent == 0 and result.failed == 0
        status._override = {("veya_wed_rem1_02", "he"): "APPROVED"}
        result, bodies = _send(db, ev, g, "reminder_1", FakeMeta(ok("wamid.3")))
        assert result.sent == 1
    finally:
        status._override = None
    print("✓ 7: תבנית שממתינה לאישור — לא נשלחת; אחרי אישור — כן")


def test_code_and_template_tool_agree() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "meta-templates-mcp"))
    import library_sync as ls

    from app import whatsapp_templates as wt

    w = {"event_type": "wedding", "message_type": "reminder_1", "option_number": 2, "content": REM}
    d = ls.to_draft(w)
    spec = wt.library_spec("wedding", "reminder_1", 2, REM)
    assert d["name"] == spec.name and tuple(d["params"]) == spec.body_params
    assert bool(d["draft"]["buttons"]) == spec.url_button
    print("✓ 8: הקוד והכלי — אותו שם ואותו סדר משתנים")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("OK — בחירת תבנית לפי הנוסח")


def test_invitations_screen_explains_pending_template() -> None:
    """(2026-10-20) במצב WhatsApp אמיתי, כשהתבנית של נוסח ההזמנה עוד לא אושרה —
    409 עם הסבר לזוג, שום בקשה ל-Meta ושום שורה (אפשר לשלוח שוב אחרי האישור)."""
    from sqlalchemy import select

    from app import models
    from app import whatsapp_template_status as status
    from app.database import SessionLocal
    from tests.e2e_seating import bootstrap

    api, _ = bootstrap()
    phone = _phone()
    g = api.add_guest("מורשה בדיקה", phone)
    db = SessionLocal()
    try:
        db.get(models.Event, api.event_id).event_date = "2026-12-01"
        db.commit()
        from app import whatsapp_templates as wt
        spec, _ = wt.resolve("invitation", db.get(models.Event, api.event_id))
        assert spec is not None, "אירוע חדש מתחיל עם נוסח הזמנה מהספרייה"
        wt_name = spec.name
    finally:
        db.close()
    status._override = {(wt_name, "he"): "PENDING"}
    try:
        with meta_env(mode="meta_test", recipients=phone) as fake:
            r = api.client.post("/automation/track/activate", headers=api.headers, json={})
    finally:
        status._override = None
    assert r.status_code == 409, r.text
    assert "ממתין לאישור של WhatsApp" in r.json()["detail"] and fake.requests == []
    db = SessionLocal()
    try:
        assert db.scalars(select(models.Message).where(models.Message.guest_id == g["id"])).all() == []
    finally:
        db.close()
    print("✓ 9: שליחת הזמנות כשהתבנית ממתינה — הסבר לזוג, שום שליחה")
