"""זכאות לשירות "מתנות באשראי" — מקור אמת אחד, וכל הצרכנים שלו.

הקובץ שומר על שלושה דברים:

1. **מקור אמת אחד.** כל מי ששואל "האם האירוע זכאי" מקבל את התשובה מאותה
   פונקציה. אין תנאי זכאות מקביל בשום קובץ אחר.
2. **הארכיטקטורה באמת ניתנת להרחבה.** רישום פותר בקדימות גבוהה יותר —
   כפי שתעשה מערכת חבילות בעתיד — משנה את התשובה בכל הצרכנים, **בלי
   לגעת באף אחד מהם**. זו לא הצהרה בתיעוד; זה נבדק כאן בפועל.
3. **זכאות ≠ שירות פעיל.** אירוע זכאי שחשבונו לא אומת אינו "פעיל".

הרצה: ``venv/bin/python tests/test_gift_eligibility.py``
"""
from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import (  # noqa: E402
    communication, gift_eligibility, guest_journey, models,
)
from app.database import SessionLocal, set_request_identity  # noqa: E402
from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


#: ערך המתג כפי שהיה כשהקובץ הזה נטען.
#:
#: ‼️ המתג הוא משתנה סביבה — **מצב גלובלי לתהליך כולו**. קובצי בדיקה
#: אחרים (``test_gift.py``, ``test_gifts_owner_view.py`` ועוד) מדליקים
#: אותו פעם אחת ברמת המודול, בזמן הייבוא. הקובץ הזה הוא היחיד שמכבה
#: ומדליק אותו תוך כדי ריצה — ולכן הוא חייב להחזיר את המצב הקודם בסוף,
#: אחרת כל קובץ שירוץ אחריו ב-pytest יקבל מתג כבוי ויישבר.
_ORIGINAL_SWITCH = os.environ.get("VEYA_GIFT_ENABLED")


def _set_switch(on: bool) -> None:
    """מדליק/מכבה את מתג השירות — המקור הזמני של היום."""
    if on:
        os.environ["VEYA_GIFT_ENABLED"] = "1"
    else:
        os.environ.pop("VEYA_GIFT_ENABLED", None)


def _restore_switch() -> None:
    """מחזיר את המתג למצב שבו היה לפני הקובץ הזה."""
    if _ORIGINAL_SWITCH is None:
        os.environ.pop("VEYA_GIFT_ENABLED", None)
    else:
        os.environ["VEYA_GIFT_ENABLED"] = _ORIGINAL_SWITCH


@pytest.fixture(autouse=True)
def _switch_isolation():
    """מבודד כל בדיקה: מה שהיא שינתה במתג לא דולף לבדיקה — או לקובץ — הבא.

    ``autouse`` ולא קריאה ידנית, כדי שבדיקה חדשה שתתווסף כאן תקבל את
    הבידוד מאליה ולא תזכיר את הבאג הזה מחדש.
    """
    yield
    _restore_switch()


def _event_row(event_id: int) -> models.Event:
    set_request_identity(None)
    db = SessionLocal()
    try:
        row = db.get(models.Event, event_id)
        db.expunge(row)
        return row
    finally:
        db.close()


def _ready_event(days: int = 1):
    """אירוע עם תאריך וכתובת — כלומר אירוע שחלון המתנה פתוח בו."""
    api, _ = bootstrap()
    r = api.client.patch("/event", headers=api.headers, json={
        "event_date": (guest_journey.today_in_israel() + timedelta(days=days)).isoformat(),
        "event_time": "19:30", "venue_address": "הרצל 5, תל אביב",
    })
    assert r.status_code == 200, r.text
    return api


def _guest_token(api, name: str, phone: str) -> str:
    g = api.add_guest(name, phone)
    set_request_identity(None)
    db = SessionLocal()
    try:
        return db.get(models.Guest, g["id"]).guest_token
    finally:
        db.close()


# ── 1. המודול עצמו ───────────────────────────────────────────────────────


def test_the_switch_is_the_source_of_truth_today() -> None:
    _set_switch(False)
    d = gift_eligibility.resolve(None)
    assert d.eligible is False and d.source == "global_switch"

    _set_switch(True)
    d = gift_eligibility.resolve(None)
    assert d.eligible is True and d.source == "global_switch"
    print("✓ מתג השירות הוא מקור האמת של היום, והמקור מדווח על עצמו")


def test_default_is_closed_when_nothing_can_answer() -> None:
    """בלי אף פותר — סגור. שירות שנוגע בכסף לא נפתח בגלל תקלת הגדרה."""
    gift_eligibility.unregister_resolver("global_switch")
    try:
        d = gift_eligibility.resolve(None)
        assert d.eligible is False and d.source == "default_closed"
    finally:
        gift_eligibility.register_resolver(
            "global_switch", gift_eligibility._from_global_switch, precedence=100
        )
    assert "global_switch" in gift_eligibility.registered_resolvers()
    print("✓ ברירת המחדל היא סגור כשאין מי שיכריע")


def test_eligibility_is_not_the_same_as_active() -> None:
    _set_switch(True)
    assert gift_eligibility.is_eligible(None) is True
    assert gift_eligibility.is_active(None, account_verified=False) is False, (
        "אירוע זכאי בלי חשבון מאומת סומן כשירות פעיל"
    )
    assert gift_eligibility.is_active(None, account_verified=True) is True

    _set_switch(False)
    assert gift_eligibility.is_active(None, account_verified=True) is False, (
        "חשבון מאומת פתח שירות לאירוע שאינו זכאי"
    )
    print("✓ זכאות ואימות הם שני תנאים נפרדים, ושניהם נדרשים ל'פעיל'")


# ── 2. נקודת החיבור למערכת החבילות ───────────────────────────────────────


def test_a_higher_precedence_resolver_overrides_everything(monkeypatch=None) -> None:
    """**הבדיקה שמוכיחה את הארכיטקטורה.**

    רושמים פותר בקדימות גבוהה — בדיוק מה שמערכת חבילות תעשה — ומראים
    שהתשובה משתנה בכל הצרכנים בלי לגעת באף אחד מהם.
    """
    _set_switch(False)                     # המתג אומר "לא זכאי"
    api = _ready_event()
    event = _event_row(api.event_id)
    assert gift_eligibility.is_eligible(event) is False

    # "החבילה של האירוע כוללת את השירות."
    gift_eligibility.register_resolver(
        "fake_plan", lambda ev: True, precedence=10
    )
    try:
        assert gift_eligibility.registered_resolvers() == ("fake_plan", "global_switch")
        d = gift_eligibility.resolve(event)
        assert d.eligible is True and d.source == "fake_plan"
        # והצרכן — מסע האורח — התעדכן מאליו.
        assert guest_journey.gift_is_open(event) is True, (
            "הצרכן לא קיבל את התשובה החדשה — הזכאות משוכפלת אצלו"
        )
    finally:
        gift_eligibility.unregister_resolver("fake_plan")

    assert gift_eligibility.is_eligible(event) is False
    print("✓ פותר בקדימות גבוהה עוקף את המתג, וכל הצרכנים מתעדכנים מאליהם")


def test_a_resolver_with_no_opinion_falls_through() -> None:
    """``None`` = "אין לי דעה" — לא "לא זכאי". זה מה שיאפשר לאירוע בלי
    חבילה להמשיך להיות מוכרע ע"י המתג."""
    _set_switch(True)
    gift_eligibility.register_resolver("no_opinion", lambda ev: None, precedence=5)
    try:
        d = gift_eligibility.resolve(None)
        assert d.eligible is True and d.source == "global_switch"
    finally:
        gift_eligibility.unregister_resolver("no_opinion")
    print("✓ פותר בלי דעה מעביר את ההכרעה הלאה ולא חוסם")


# ── 3. Guest Hub ─────────────────────────────────────────────────────────


def test_guest_hub_hides_the_gift_action_when_not_eligible() -> None:
    api = _ready_event()
    token = _guest_token(api, "מוזמן", "0504440001")

    _set_switch(False)
    r = api.client.get(f"/confirm/{token}")
    assert r.status_code == 200, r.text
    assert r.json()["actions"]["gift"] is False, "מוזמן ראה 'להעניק מתנה' באירוע לא זכאי"

    # וגם ניסיון ישיר לפעולה נחסם — ההסתרה אינה ההגנה.
    blocked = api.client.get(f"/confirm/{token}?action=gift")
    assert blocked.status_code in (403, 200)
    if blocked.status_code == 200:
        assert blocked.json()["actions"]["gift"] is False

    _set_switch(True)
    r = api.client.get(f"/confirm/{token}")
    assert r.json()["actions"]["gift"] is True, "אירוע זכאי בתוך החלון לא הציג מתנה"
    print("✓ Guest Hub: 'להעניק מתנה' מוצג רק לאירוע זכאי")


def test_gift_window_is_independent_of_eligibility() -> None:
    """זכאות וחלון הזמן הם שני תנאים נפרדים — אירוע זכאי מחוץ לחלון סגור."""
    _set_switch(True)
    far = _ready_event(days=60)
    event = _event_row(far.event_id)
    assert gift_eligibility.is_eligible(event) is True
    assert guest_journey.gift_window_is_open(event) is False
    assert guest_journey.gift_is_open(event) is False
    print("✓ אירוע זכאי מחוץ לחלון הזמן — עדיין סגור")


# ── 4. מסך "מתנות באשראי" ────────────────────────────────────────────────


def test_gifts_screen_is_hidden_for_an_ineligible_event() -> None:
    api = _ready_event()

    _set_switch(False)
    r = api.client.get("/gifts", headers=api.headers)
    assert r.status_code == 404, f"מסך המתנות נגיש לאירוע לא זכאי ({r.status_code})"

    _set_switch(True)
    r = api.client.get("/gifts", headers=api.headers)
    assert r.status_code == 200, r.text
    print("✓ מסך המתנות: 404 לאירוע לא זכאי, 200 לזכאי")


def test_event_summary_reports_eligibility_to_the_client() -> None:
    api = _ready_event()

    _set_switch(False)
    rows = api.client.get("/events", headers=api.headers).json()
    mine = [e for e in rows if e["id"] == api.event_id][0]
    assert mine["gift_service_eligible"] is False

    _set_switch(True)
    rows = api.client.get("/events", headers=api.headers).json()
    mine = [e for e in rows if e["id"] == api.event_id][0]
    assert mine["gift_service_eligible"] is True
    print("✓ רשימת האירועים מדווחת זכאות — כך הפרונט מסתיר ניווט ומסך")


# ── 5. הודעות WhatsApp ───────────────────────────────────────────────────


def test_messages_carry_no_gift_content_when_not_eligible() -> None:
    api = _ready_event()
    _guest_token(api, "מוזמן להודעה", "0504440002")

    set_request_identity(None)
    db = SessionLocal()
    try:
        event = db.get(models.Event, api.event_id)
        guest = db.scalars(
            select(models.Guest).where(models.Guest.event_id == api.event_id)
        ).first()

        _set_switch(False)
        values = communication.communication_values(event, guest)
        assert values["gift_link"] == "", "קישור מתנה נכנס להודעה של אירוע לא זכאי"
        for kind in communication.MESSAGE_TYPES:
            assert "gift_link" not in communication.variables_supported(event, kind), (
                f"gift_link מוצע בעורך לסוג {kind} באירוע לא זכאי"
            )

        # ושורה בתבנית שמכילה את הטוקן נמחקת לגמרי — לא נשלח "מתנה: ".
        rendered = communication.render_message(
            "שלום {{guest_name}}\nלהעניק מתנה: {{gift_link}}", values
        )
        assert "מתנה" not in rendered, f"תוכן מתנה נשלח בכל זאת: {rendered!r}"
        assert values["guest_name"] in rendered

        _set_switch(True)
        assert "gift_link" in communication.variables_supported(event, "thank_you"), (
            "gift_link לא מוצע גם לאירוע זכאי"
        )
    finally:
        db.close()
    print("✓ הודעות: אין תוכן או קישור מתנה לאירוע שאינו זכאי")


def test_event_day_message_has_no_gift_content_when_not_eligible() -> None:
    """הודעת יום האירוע — נבדקת במפורש, כי היא הרגישה ביותר."""
    api = _ready_event()
    _guest_token(api, "מוזמן יום אירוע", "0504440003")

    set_request_identity(None)
    db = SessionLocal()
    try:
        event = db.get(models.Event, api.event_id)
        guest = db.scalars(
            select(models.Guest).where(models.Guest.event_id == api.event_id)
        ).first()

        _set_switch(False)
        assert "gift_link" not in communication.variables_supported(event, "event_day")
        values = communication.communication_values(event, guest)
        rendered = communication.render_message(
            "מתראים היום ב-{{event_time}}\nמתנה: {{gift_link}}", values
        )
        assert "מתנה" not in rendered, rendered
        assert "19:30" in rendered, "שאר תוכן ההודעה נפגע"
    finally:
        db.close()
    print("✓ הודעת יום האירוע נקייה ממתנות באירוע לא זכאי, ושאר התוכן שלם")


def test_seeded_event_messages_exclude_the_gift_variable() -> None:
    """אירוע שנוצר כשאינו זכאי — ``gift_link`` לא נכנס לתבניות שלו."""
    _set_switch(False)
    api, _ = bootstrap()
    set_request_identity(None)
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(models.EventMessage)
            .where(models.EventMessage.event_id == api.event_id)
        ).all()
        assert rows, "לא נוצרו הודעות לאירוע"
        for row in rows:
            assert "gift_link" not in (row.variables_supported or []), (
                f"gift_link נשתל בתבנית {row.message_type} של אירוע לא זכאי"
            )
    finally:
        db.close()
    print("✓ תבניות ההודעות של אירוע לא זכאי נוצרות בלי משתנה המתנה")


def _run(test) -> None:
    """מריץ בדיקה בהרצה עצמאית, ומחזיר את המתג אחריה — כמו ה-fixture."""
    try:
        test()
    finally:
        _restore_switch()


if __name__ == "__main__":
    try:
        _run(test_the_switch_is_the_source_of_truth_today)
        _run(test_default_is_closed_when_nothing_can_answer)
        _run(test_eligibility_is_not_the_same_as_active)

        _run(test_a_higher_precedence_resolver_overrides_everything)
        _run(test_a_resolver_with_no_opinion_falls_through)

        _run(test_guest_hub_hides_the_gift_action_when_not_eligible)
        _run(test_gift_window_is_independent_of_eligibility)

        _run(test_gifts_screen_is_hidden_for_an_ineligible_event)
        _run(test_event_summary_reports_eligibility_to_the_client)

        _run(test_messages_carry_no_gift_content_when_not_eligible)
        _run(test_event_day_message_has_no_gift_content_when_not_eligible)
        _run(test_seeded_event_messages_exclude_the_gift_variable)
        print("\nכל בדיקות הזכאות עברו ✓")
    finally:
        _restore_switch()
        shutdown()
