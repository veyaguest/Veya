"""רגרסיה — פעולות שיחה ביומן הפעילות של בעל/ת האירוע.

שני עקרונות נבדקים כאן:

1. **מנגנון קיים בלבד.** הפעולות נרשמות ל-``AuditLog`` הקיים ונקראות דרך
   ``GET /event/audit`` — אותו ערוץ שממנו כבר מגיע ה-Feed בתמונת המצב. לא
   נבנתה מערכת Activity שנייה.
2. **שפה אנושית.** בעל/ת האירוע לא רואה מונחים טכניים, שמות שדות, סטטוסים
   פנימיים או רמז לכך שקיים מודול בשם Call Center. הבדיקה האחרונה בקובץ
   סורקת את כל הטקסטים מול רשימת מונחים אסורים.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402
from tests.call_center_helpers import (  # noqa: E402
    configure_track,
    guest_of,
    shift_callback,
    standalone_admin,
)

# מונחים שאסור שיופיעו בטקסט שבעל/ת האירוע רואה.
FORBIDDEN_TERMS = [
    "Call Center", "call center", "call_center", "Call Result",
    "wrong_number", "no_answer", "busy", "callback", "follow-up", "Follow-up",
    "rsvp_status", "outcome", "admin", "אדמין", "מוקדן", "call_logs",
    "pending", "confirmed", "declined",
]


def _feed(api) -> list[dict]:
    """יומן הפעילות כפי שבעל/ת האירוע מקבל אותו."""
    r = api.client.get("/event/audit", headers=api.headers, params={"limit": 100})
    assert r.status_code == 200, r.text
    return r.json()


def _texts(api, action_prefix: str = "guest_call") -> list[str]:
    return [row["detail"] for row in _feed(api) if row["action"].startswith(action_prefix)]


def _record(api, admin, guest_id: int, **payload) -> dict:
    r = api.client.post(f"/admin/call-center/guests/{guest_id}/outcome",
                        headers=admin, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_confirmed_appears_in_the_feed() -> None:
    """(1) אישר הגעה — כולל מספר האנשים שעודכן בשיחה."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("ישראל כהן", "0561000001", party_size=5)

        _record(api, admin, guest["id"], outcome="confirmed", count=3)

        texts = _texts(api)
        assert "ישראל כהן אישר/ה הגעה – 3 אנשים" in texts, texts
        print("✓ אישור הגעה מופיע ב-Feed עם מספר האנשים")
    finally:
        teardown()


def test_declined_appears_in_the_feed() -> None:
    """(2) לא מגיע."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("ישראל כהן", "0561000002", party_size=2)

        _record(api, admin, guest["id"], outcome="declined")

        assert "ישראל כהן עדכן/ה שלא יגיע/ה" in _texts(api)
        print("✓ ביטול הגעה מופיע ב-Feed")
    finally:
        teardown()


def test_no_answer_appears_in_the_feed() -> None:
    """(3) לא ענה — בניסוח שלא מרמז על "ניסיון חיוג" טכני."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("ישראל כהן", "0561000003", party_size=1)

        _record(api, admin, guest["id"], outcome="no_answer")

        assert "לא התקבלה תשובה מישראל כהן" in _texts(api)
        # ולא נגעה בסטטוס — ה-Feed מדווח על שיחה, לא על שינוי אישור הגעה.
        assert guest_of(api, guest["id"]).rsvp_status == "pending"
        print("✓ 'לא ענה' מופיע ב-Feed בלי לשנות סטטוס")
    finally:
        teardown()


def test_busy_appears_in_the_feed() -> None:
    """(4) תפוס."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("ישראל כהן", "0561000004", party_size=1)

        _record(api, admin, guest["id"], outcome="busy")

        assert "לא ניתן היה להשיג את ישראל כהן" in _texts(api)
        print("✓ 'תפוס' מופיע ב-Feed")
    finally:
        teardown()


def test_wrong_number_appears_in_the_feed() -> None:
    """(5) מספר שגוי."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("ישראל כהן", "0561000005", party_size=1)

        _record(api, admin, guest["id"], outcome="wrong_number")

        assert "מספר הטלפון של ישראל כהן אינו תקין" in _texts(api)
        print("✓ 'מספר שגוי' מופיע ב-Feed")
    finally:
        teardown()


def test_callback_appears_in_the_feed_with_date_time_and_note() -> None:
    """(6) בקשה לחזור מאוחר יותר — עם תאריך, שעה, והערה בשורה נפרדת."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("ישראל כהן", "0561000006", party_size=1)

        when = datetime.utcnow() + timedelta(days=1)
        _record(api, admin, guest["id"], outcome="callback",
                callback_at=when.isoformat() + "Z",
                note="ביקש שנחזור אליו אחרי העבודה.")

        # המועד מוצג בשעון המקומי (ישראל), לא ב-UTC שבו הוא נשמר — אחרת
        # בעל/ת האירוע רואה שעה שאף אחד לא בחר.
        from zoneinfo import ZoneInfo

        from app import call_center

        local = when.replace(tzinfo=timezone.utc).astimezone(
            ZoneInfo(call_center.LOCAL_TIMEZONE)
        )
        text = next(t for t in _texts(api) if t.startswith("נקבע ליצור קשר"))
        assert f"בתאריך {local.strftime('%d/%m')}" in text, text
        assert f"בשעה {local.strftime('%H:%M')}" in text, text
        assert "ישראל כהן" in text
        # ההערה יורדת לשורה נפרדת מתחת למשפט.
        assert "\nהערה: ביקש שנחזור אליו אחרי העבודה." in text, text
        print("✓ בקשת חזרה מופיעה עם תאריך, שעה והערה")
    finally:
        teardown()


def test_followup_call_appears_in_the_feed() -> None:
    """(7) שיחת המשך — נרשמת בנוסף לתוצאה של אותה שיחה."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("ישראל כהן", "0561000007", party_size=2)

        # שיחה ראשונה: ביקש שנחזור אליו.
        _record(api, admin, guest["id"], outcome="callback",
                callback_at=(datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z")
        assert not any("שיחת המשך" in t for t in _texts(api)), "שיחת המשך נרשמה מוקדם מדי"

        # הגיע המועד, מתקשרים שוב — והפעם הוא מאשר.
        shift_callback(guest["id"], minutes_from_now=-1)
        _record(api, admin, guest["id"], outcome="confirmed", count=2)

        texts = _texts(api)
        assert "בוצעה שיחת המשך עם ישראל כהן" in texts, texts
        assert "ישראל כהן אישר/ה הגעה – 2 אנשים" in texts, texts
        print("✓ שיחת המשך והתוצאה שלה מופיעות שתיהן ב-Feed")
    finally:
        teardown()


def test_activity_belongs_to_the_right_event_and_guest() -> None:
    """(8) הפעילות משויכת לאירוע ולמוזמן הנכונים."""
    api, teardown = bootstrap()
    try:
        from app import models
        from app.database import SessionLocal

        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("ישראל כהן", "0561000008", party_size=1)

        _record(api, admin, guest["id"], outcome="no_answer")

        db = SessionLocal()
        try:
            row = (
                db.query(models.AuditLog)
                .filter(models.AuditLog.action == "guest_call_no_answer")
                .order_by(models.AuditLog.id.desc())
                .first()
            )
            assert row.event_id == api.event_id
            assert row.user_id is not None, "לא נשמר מי ביצע את הפעולה"
            assert "ישראל כהן" in row.detail
        finally:
            db.close()
        print("✓ הפעילות משויכת לאירוע ולמוזמן הנכונים")
    finally:
        teardown()


def test_no_activity_leaks_between_events() -> None:
    """(9) פעילות של אירוע אחד לא מופיעה ביומן של אירוע אחר."""
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        admin = standalone_admin(api_a)
        configure_track(api_a)
        configure_track(api_b)
        guest_a = api_a.add_guest("אורח של A", "0561000009", party_size=1)
        guest_b = api_b.add_guest("אורח של B", "0561000010", party_size=1)

        _record(api_a, admin, guest_a["id"], outcome="no_answer")
        _record(api_b, admin, guest_b["id"], outcome="busy")

        texts_a = " ".join(_texts(api_a))
        texts_b = " ".join(_texts(api_b))
        assert "אורח של A" in texts_a and "אורח של B" not in texts_a, texts_a
        assert "אורח של B" in texts_b and "אורח של A" not in texts_b, texts_b
        print("✓ אין דליפת פעילות בין אירועים")
    finally:
        teardown_a()
        teardown_b()


def test_feed_contains_no_technical_terms() -> None:
    """(10) אין שום מונח טכני בטקסט שבעל/ת האירוע רואה."""
    api, teardown = bootstrap()
    try:
        admin = standalone_admin(api)
        configure_track(api)
        names = ["דנה לוי", "יוסי מזרחי", "רותם ברק", "נועה שני", "עמית גל", "שיר אלון"]
        outcomes = [
            {"outcome": "confirmed", "count": 2},
            {"outcome": "declined"},
            {"outcome": "no_answer"},
            {"outcome": "busy"},
            {"outcome": "wrong_number"},
            {"outcome": "callback",
             "callback_at": (datetime.utcnow() + timedelta(hours=2)).isoformat() + "Z",
             "note": "לחזור בערב"},
        ]
        for i, (name, payload) in enumerate(zip(names, outcomes)):
            g = api.add_guest(name, f"05610001{i:02d}", party_size=2)
            _record(api, admin, g["id"], **payload)

        texts = _texts(api)
        assert len(texts) == len(outcomes), texts
        for text in texts:
            for term in FORBIDDEN_TERMS:
                assert term not in text, f"מונח טכני '{term}' דלף לטקסט: {text!r}"
            # אין אותיות לטיניות בכלל בטקסט שמוצג לבעל/ת האירוע.
            assert not any("a" <= c.lower() <= "z" for c in text), text
        print("✓ אין מונחים טכניים בתצוגה לבעל האירוע")
    finally:
        teardown()


def test_call_details_stay_available_internally() -> None:
    """המידע התפעולי המלא נשמר — רק לא מוצג לבעל/ת האירוע בניסוח טכני."""
    api, teardown = bootstrap()
    try:
        from tests.call_center_helpers import call_logs_of

        admin = standalone_admin(api)
        configure_track(api)
        guest = api.add_guest("ישראל כהן", "0561000200", party_size=1)

        _record(api, admin, guest["id"], outcome="wrong_number", note="מנותק")

        log = call_logs_of(api, guest["id"])[0]
        assert log.outcome == "wrong_number"     # סוג הפעולה
        assert log.created_by_id is not None     # מי ביצע
        assert log.created_at is not None        # תאריך ושעה
        assert log.event_id == api.event_id      # האירוע
        assert log.guest_id == guest["id"]       # האורח
        assert log.phone_at_call == "0561000200" # המספר שאליו חויג
        assert log.note == "מנותק"               # מה נאמר בשיחה
        print("✓ כל המידע התפעולי נשמר ב-call_logs לצורכי Audit")
    finally:
        teardown()


def test_phone_agent_actions_look_identical_in_the_feed() -> None:
    """שיחה של **טלפן** נראית לבעל/ת האירוע בדיוק כמו כל שיחה אחרת.

    §11 באפיון: הבעלים רואה "ישראל כהן אישר/ה הגעה – 3 אנשים", ולא "טלפן X
    עדכן…". שם המבצע נשמר ב-``call_logs`` בלבד, לצורכי Audit.
    """
    api, teardown = bootstrap()
    try:
        from tests.call_center_helpers import call_logs_of, phone_agent

        configure_track(api)
        guest = api.add_guest("ישראל כהן", "0561000300", party_size=4)
        agent_id, agent = phone_agent(api, display_name="דנה מוקד")

        _record(api, agent, guest["id"], outcome="confirmed", count=3)

        texts = _texts(api)
        assert texts == ["ישראל כהן אישר/ה הגעה – 3 אנשים"], texts
        for text in texts:
            assert "דנה מוקד" not in text, "שם הטלפן דלף ליומן של בעל האירוע"
            for term in FORBIDDEN_TERMS + ["טלפן", "מוקד"]:
                assert term not in text, f"מונח פנימי '{term}' דלף: {text!r}"

        # ומאחורי הקלעים — כן יודעים בדיוק מי ביצע.
        log = call_logs_of(api, guest["id"])[0]
        assert log.created_by_id == agent_id
        print("✓ פעולת טלפן מוצגת לבעל האירוע בניסוח אנושי, בלי לחשוף מי חייג")
    finally:
        teardown()


if __name__ == "__main__":
    try:
        test_confirmed_appears_in_the_feed()
        test_declined_appears_in_the_feed()
        test_no_answer_appears_in_the_feed()
        test_busy_appears_in_the_feed()
        test_wrong_number_appears_in_the_feed()
        test_callback_appears_in_the_feed_with_date_time_and_note()
        test_followup_call_appears_in_the_feed()
        test_activity_belongs_to_the_right_event_and_guest()
        test_no_activity_leaks_between_events()
        test_feed_contains_no_technical_terms()
        test_call_details_stay_available_internally()
        test_phone_agent_actions_look_identical_in_the_feed()
    finally:
        shutdown()
