"""בדיקות ל-Guest Hub — עמוד המוזמן הציבורי (/confirm/{token}).

ה-Hub נבנה **על גבי** מנגנון הקישור האישי הקיים ולא לצידו: אותו טוקן, אותו
Route, אותה הגנת RLS. הבדיקות כאן מוודאות שלוש משפחות של דברים:

1. **בידוד** — מוזמן לא רואה מוזמן אחר ולא אירוע אחר, וטוקן שהומצא נדחה
   באותה תשובה בדיוק (404 זהה) גם בעמוד וגם בקובץ היומן.
2. **פעולות מותנות נתונים** — אירוע בלי כתובת לא מציע ניווט, אירוע בלי
   תאריך לא מציע יומן, אירוע בלי שעה מייצר אירוע יום-שלם ולא 00:00.
3. **אי-רגרסיה** — אישור ההגעה הקיים ממשיך לעבוד בדיוק כמו קודם.

הרצה: ``venv/bin/python tests/test_guest_hub.py`` (עצמאי, בלי pytest).
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os  # noqa: E402

# מתג המתנה דלוק לאורך הקובץ — כאן בודקים את הזמינות דרך ה-API, לא את
# שאלת השחרור (זו נבדקת ב-tests/test_guest_journey.py).
os.environ["VEYA_GIFT_ENABLED"] = "1"

from app import calendar_links, guest_journey  # noqa: E402
from tests.e2e_seating import bootstrap, shutdown  # noqa: E402


def _set_event(api, **fields):
    """מזיז את פרטי האירוע ישירות ב-DB, ולא דרך ``PATCH /event``.

    תאריך האירוע נעול לעריכה מרגע שנקבע (ראו ``app/routers/postpone.py``:
    שינוי אמיתי עובר בנוהל דחייה מאושר). הבדיקות כאן אינן על עריכת אירוע
    אלא על **חלון הזמן** של המתנות, ולכן הן מזיזות את התאריך ישירות במסד —
    בדיוק כמו שהיו מזיזות שעון. הנעילה בייצור נשארת שלמה ונבדקת בקובץ
    ``tests/test_postponement.py``.
    """
    from app import models
    from app.database import SessionLocal, set_request_identity

    set_request_identity(None)
    db = SessionLocal()
    try:
        event = db.get(models.Event, api.event_id)
        for key, value in fields.items():
            setattr(event, key, value)
        db.commit()
    finally:
        db.close()
    r = api.client.get("/event", headers=api.headers)
    assert r.status_code == 200, f"קריאת אירוע נכשלה: {r.status_code} {r.text}"
    return r.json()


def _token(api, guest_id: int) -> str:
    """הטוקן האישי של מוזמן, כפי שהוא נשלח לו בהודעה."""
    from app import models
    from app.database import SessionLocal, set_request_identity

    set_request_identity(None)
    db = SessionLocal()
    try:
        return db.get(models.Guest, guest_id).guest_token
    finally:
        db.close()


# ---- 1. מוזמן תקין: מקבל את הפעולות שלו, ורק את שלו ----------------------

def test_valid_guest_sees_own_hub() -> None:
    api, _ = bootstrap()
    _set_event(
        api,
        venue_name="אולמי הבדיקה",
        venue_address="הרצל 5, תל אביב",
        event_date="2026-11-12",
        event_time="19:30",
    )
    g = api.add_guest("דנה כהן", "0501111111", party_size=3)
    tok = _token(api, g["id"])

    r = api.client.get(f"/confirm/{tok}")
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["full_name"] == "דנה כהן"
    assert data["party_size"] == 3
    ev = data["event"]
    assert ev["venue_name"] == "אולמי הבדיקה"
    assert ev["title"] == "החתונה של דני ורותי", ev["title"]

    acts = data["actions"]
    assert acts["navigation"] is True, "יש כתובת — ניווט חייב להיות זמין"
    assert acts["calendar"] is True, "יש תאריך — הוספה ליומן חייבת להיות זמינה"
    assert acts["rsvp"] is True, "אישור הגעה פתוח מרגע ההזמנה"
    assert acts["gift"] is False, "מתנה באשראי עוד לא נבנתה — חייבת להיות כבויה"
    assert acts["invitation"] is False, "לא הועלתה תמונת הזמנה"

    for key in ("maps_link", "waze_link", "apple_maps_link"):
        assert ev[key], f"{key} חסר למרות שיש כתובת"
    assert "waze.com" in ev["waze_link"]
    assert "maps.apple.com" in ev["apple_maps_link"]

    cal = ev["calendar"]
    assert cal["ics"] == f"/confirm/{tok}/calendar.ics"
    assert cal["google"].startswith("https://calendar.google.com/")
    assert cal["outlook"].startswith("https://outlook.live.com/")
    # 19:30 שעון ישראל בנובמבר (UTC+2) → 17:30Z
    dates = parse_qs(urlparse(cal["google"]).query)["dates"][0]
    assert dates.startswith("20261112T173000Z"), dates

    # שום נתון של מוזמן אחר לא נמצא בתשובה.
    assert "guests" not in data and "phone" not in data
    print("✓ מוזמן תקין: רואה את הפעולות שלו, עם הנתונים שלו בלבד")


# ---- 2-3. טוקן לא תקין / שהומצא ------------------------------------------

def test_invalid_token_is_rejected_everywhere() -> None:
    api, _ = bootstrap()
    for bad in ("לא-קיים", "abcdefghijkl", "../../etc/passwd", ""):
        r = api.client.get(f"/confirm/{bad}")
        assert r.status_code in (404, 405), f"טוקן '{bad}' לא נדחה: {r.status_code}"
        r = api.client.get(f"/confirm/{bad}/calendar.ics")
        assert r.status_code in (404, 405), f"יומן לטוקן '{bad}' לא נדחה: {r.status_code}"
    print("✓ טוקן לא תקין נדחה גם בעמוד וגם בקובץ היומן")
    # הערה: אין מנגנון תפוגה לטוקן ב-VEYA (הקישור קבוע לכל חיי האירוע) —
    # ולכן אין מה לבדוק ב"טוקן שפג תוקפו". זו החלטת מוצר, לא פער בבדיקה.


# ---- 4-5. בידוד בין מוזמנים ובין אירועים ---------------------------------

def test_guest_cannot_reach_another_guest_or_event() -> None:
    api_a, _ = bootstrap()
    ga1 = api_a.add_guest("מוזמן א׳", "0502222222")
    ga2 = api_a.add_guest("מוזמן ב׳", "0503333333")
    tok1 = _token(api_a, ga1["id"])
    tok2 = _token(api_a, ga2["id"])

    # אותו אירוע, שני מוזמנים — כל טוקן מחזיר רק את בעליו.
    assert api_a.client.get(f"/confirm/{tok1}").json()["full_name"] == "מוזמן א׳"
    assert api_a.client.get(f"/confirm/{tok2}").json()["full_name"] == "מוזמן ב׳"

    # אירוע אחר לגמרי, של בעלים אחר.
    api_b, _ = bootstrap()
    _set_event(api_b, venue_name="אולם אחר לגמרי")
    gb = api_b.add_guest("מוזמן של אירוע אחר", "0504444444")
    tok_b = _token(api_b, gb["id"])

    other = api_a.client.get(f"/confirm/{tok_b}").json()
    assert other["full_name"] == "מוזמן של אירוע אחר"
    assert other["event"]["venue_name"] == "אולם אחר לגמרי"
    mine = api_a.client.get(f"/confirm/{tok1}").json()
    assert mine["event"]["venue_name"] != "אולם אחר לגמרי", (
        "טוקן של אירוע אחד החזיר נתוני אירוע אחר"
    )

    # אין פרמטר זהות ניתן-לשינוי: guest_id/event_id ב-query לא משנים כלום.
    spoof = api_a.client.get(f"/confirm/{tok1}?guest_id={ga2['id']}&event_id=999").json()
    assert spoof["full_name"] == "מוזמן א׳", "פרמטר ב-URL הצליח להחליף זהות"
    print("✓ בידוד מלא: מוזמן↔מוזמן, אירוע↔אירוע, ואין זהות ב-query")


# ---- 6-8. אירוע בלי כתובת / בלי שעה / עם הכול ----------------------------

def test_missing_venue_hides_navigation() -> None:
    api, _ = bootstrap()
    _set_event(api, venue_name="", venue_address="", event_date="2026-11-12")
    g = api.add_guest("בלי כתובת", "0505555555")
    data = api.client.get(f"/confirm/{_token(api, g['id'])}").json()
    assert data["actions"]["navigation"] is False, "בלי כתובת אסור להציע ניווט"
    assert data["event"]["waze_link"] == "" and data["event"]["maps_link"] == ""
    assert data["actions"]["calendar"] is True, "יש תאריך — היומן עדיין זמין"
    print("✓ אירוע בלי כתובת: ניווט מוסתר, היומן ממשיך לעבוד")


def test_missing_date_hides_calendar() -> None:
    api, _ = bootstrap()
    _set_event(api, venue_address="הרצל 5, תל אביב", event_date="", event_time="")
    g = api.add_guest("בלי תאריך", "0506666666")
    tok = _token(api, g["id"])
    data = api.client.get(f"/confirm/{tok}").json()
    assert data["actions"]["calendar"] is False, "בלי תאריך אסור להציע יומן"
    assert data["event"]["calendar"]["ics"] == ""
    assert api.client.get(f"/confirm/{tok}/calendar.ics").status_code == 404
    assert data["actions"]["navigation"] is True, "יש כתובת — הניווט עדיין זמין"
    print("✓ אירוע בלי תאריך: יומן מוסתר, ניווט ממשיך לעבוד")


def test_missing_time_becomes_all_day() -> None:
    api, _ = bootstrap()
    _set_event(api, event_date="2026-11-12", event_time="")
    g = api.add_guest("בלי שעה", "0507777777")
    tok = _token(api, g["id"])
    assert api.client.get(f"/confirm/{tok}").json()["actions"]["calendar"] is True
    ics = api.client.get(f"/confirm/{tok}/calendar.ics").text
    assert "DTSTART;VALUE=DATE:20261112" in ics, ics
    assert "T000000" not in ics, "אירוע בלי שעה נרשם בטעות כ-00:00"
    print("✓ אירוע בלי שעה: נשמר ביומן כאירוע יום-שלם, לא כחצות")


# ---- 9-11. קובץ היומן עצמו -----------------------------------------------

def test_ics_is_valid_and_leaks_nothing() -> None:
    api, _ = bootstrap()
    _set_event(
        api,
        venue_name="אולמי הבדיקה",
        venue_address="הרצל 5, תל אביב",
        event_date="2026-11-12",
        event_time="19:30",
    )
    g = api.add_guest("דנה כהן", "0508888888", party_size=2)
    tok = _token(api, g["id"])
    r = api.client.get(f"/confirm/{tok}/calendar.ics")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/calendar")
    assert "attachment" in r.headers["content-disposition"]

    ics = r.text
    for required in ("BEGIN:VCALENDAR", "BEGIN:VEVENT", "UID:", "DTSTAMP:",
                     "DTSTART:", "DTEND:", "SUMMARY:", "END:VCALENDAR"):
        assert required in ics, f"חסר {required} בקובץ היומן"
    assert "DTSTART:20261112T173000Z" in ics, "השעה לא הומרה נכון מישראל ל-UTC"
    assert "\r\n" in ics, "ICS חייב שורות בסיום CRLF"
    assert all(len(l.encode()) <= 75 for l in ics.split("\r\n")), "שורה ארוכה מ-75 בתים"

    # שום מידע אישי בקובץ שנשמר במכשיר ועלול להישלח הלאה.
    assert "דנה כהן" not in ics and "0508888888" not in ics, "דלף מידע אישי ל-ICS"
    print("✓ ICS: תקני, בשעה הנכונה, ובלי שום נתון אישי")


def test_ics_stable_uid_prevents_duplicates() -> None:
    api, _ = bootstrap()
    _set_event(api, event_date="2026-11-12", event_time="19:30")
    g1 = api.add_guest("מוזמן א׳", "0509990001")
    g2 = api.add_guest("מוזמן ב׳", "0509990002")

    def uid(gid):
        text = api.client.get(f"/confirm/{_token(api, gid)}/calendar.ics").text
        return next(l for l in text.split("\r\n") if l.startswith("UID:"))

    assert uid(g1["id"]) == uid(g2["id"]), (
        "UID חייב להיות של האירוע, לא של המוזמן — אחרת הוספה חוזרת מייצרת כפילות"
    )
    print("✓ UID יציב פר-אירוע — אין אירועים כפולים ביומן")


# ---- 12-13. קישורי ניווט --------------------------------------------------

def test_navigation_links_use_real_address() -> None:
    from urllib.parse import unquote_plus

    api, _ = bootstrap()
    address = "שדרות רוטשילד 12, תל אביב"
    _set_event(api, venue_address=address)
    g = api.add_guest("מנווט", "0501230001")
    ev = api.client.get(f"/confirm/{_token(api, g['id'])}").json()["event"]
    for key in ("waze_link", "maps_link", "apple_maps_link"):
        assert address in unquote_plus(ev[key]), f"{key} לא מכיל את הכתובת האמיתית"
    print("✓ ניווט: שלושת הקישורים נבנים מהכתובת שבאירוע, בלי שום כתובת קבועה")


# ---- Event-first: הכותרת ביומן מתאימה לסוג האירוע ------------------------

def test_calendar_title_follows_event_type() -> None:
    api, _ = bootstrap(event_type="bar_mitzvah")
    _set_event(api, event_date="2026-11-12", event_time="19:30")
    g = api.add_guest("מוזמן", "0501230002")
    tok = _token(api, g["id"])
    title = api.client.get(f"/confirm/{tok}").json()["event"]["title"]
    assert "חתונה" not in title, f"שפה חתונתית דלפה לבר מצווה: {title}"
    assert "בר המצווה" in title, title
    assert f"SUMMARY:{title}" in api.client.get(f"/confirm/{tok}/calendar.ics").text
    print(f"✓ Event-first: הכותרת ביומן היא '{title}' ולא ברירת מחדל חתונתית")


# ---- 18-19. אי-רגרסיה: אישור ההגעה הקיים -----------------------------------

def test_existing_rsvp_still_works() -> None:
    api, _ = bootstrap()
    _set_event(api, event_date="2026-11-12", event_time="19:30",
               venue_address="הרצל 5, תל אביב")
    g = api.add_guest("מאשר הגעה", "0501230003", party_size=4)
    tok = _token(api, g["id"])

    r = api.client.post(f"/confirm/{tok}", json={
        "coming": True, "maybe": False, "count": 3, "note": "צריך נגישות",
    })
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["rsvp_status"] == "confirmed"
    assert out["confirmed_count"] == 3
    assert out["guest_note"] == "צריך נגישות"
    # התשובה אחרי שליחה היא אותו מבנה Hub — כולל הפעולות והיומן.
    assert out["actions"]["calendar"] is True and out["event"]["calendar"]["ics"]

    # שינוי תשובה, כמו בעמוד עצמו.
    again = api.client.post(f"/confirm/{tok}", json={"coming": False, "maybe": False}).json()
    assert again["rsvp_status"] == "declined"

    # והמערכת של הזוג רואה את זה — הקישור בין RSVP לתמונת המצב לא נשבר.
    hall = api.get_hall()
    row = {u["id"]: u for u in hall["unassigned"]}[g["id"]]
    assert row["rsvp_status"] == "declined" and row["seats"] == 0
    print("✓ אי-רגרסיה: אישור ההגעה הקיים עובד, כולל שינוי תשובה וסנכרון לזוג")


# ---- מסע האורח: זמינות המתנה דרך ה-API האמיתי ---------------------------

def _event_date_in(days: int) -> str:
    """תאריך אירוע שנמצא ``days`` ימים מהיום (לפי שעון ישראל)."""
    from datetime import timedelta

    return (guest_journey.today_in_israel() + timedelta(days=days)).isoformat()


def test_gift_availability_through_api() -> None:
    """אותו מוזמן, אותו קישור — רק תאריך האירוע זז, והמתנה נדלקת בהתאם."""
    api, _ = bootstrap()
    _set_event(api, venue_address="הרצל 5, תל אביב", event_time="19:30")
    g = api.add_guest("מוזמן מסע", "0507000001")
    tok = _token(api, g["id"])

    def gift_flag(days_away: int) -> bool:
        _set_event(api, event_date=_event_date_in(days_away))
        r = api.client.get(f"/confirm/{tok}")
        assert r.status_code == 200, r.text
        return r.json()["actions"]["gift"]

    assert gift_flag(10) is False, "10 ימים לפני — המתנה חייבת להיות סגורה"
    assert gift_flag(4) is False, "4 ימים לפני — עדיין סגורה"
    assert gift_flag(3) is True, "בדיוק 3 ימים לפני — נפתחת"
    assert gift_flag(1) is True, "יום לפני — פתוחה"
    assert gift_flag(0) is True, "יום האירוע — פתוחה"
    # −1 (הבוקר שאחרי) **לא** נבדק כאן בכוונה: החלון נסגר ב-10:00 שעון
    # ישראל, ולכן התוצאה תלויה בשעה שבה הסוויטה רצה — בדיקה כזו הייתה
    # עוברת אחר הצהריים ונכשלת בבוקר. הגבול לדקה נבדק ב-
    # tests/test_guest_journey.py, שם אפשר להזריק ``now`` מדויק.
    assert gift_flag(-2) is False, "יומיים אחרי האירוע — סגורה בכל שעה"
    print("✓ API: דגל המתנה נדלק ונכבה לפי חלון המתנה")


def test_other_actions_survive_the_whole_journey() -> None:
    """הפעולות הקיימות זמינות בכל שלב — גם אחרי שהמתנה נפתחה."""
    api, _ = bootstrap()
    _set_event(api, venue_address="הרצל 5, תל אביב", event_time="19:30")
    g = api.add_guest("מוזמן", "0507000002")
    tok = _token(api, g["id"])
    for days in (10, 3, 0):
        _set_event(api, event_date=_event_date_in(days))
        acts = api.client.get(f"/confirm/{tok}").json()["actions"]
        assert acts["calendar"] is True and acts["navigation"] is True
        assert acts["rsvp"] is True, "אישור הגעה נשאר פתוח לאורך כל המסע"
    print("✓ API: יומן/ניווט/אישור הגעה זמינים בכל שלבי המסע")


def test_gift_url_param_grants_nothing() -> None:
    """``?action=gift`` מוקדם לא משנה שום דבר בתשובת השרת.

    זה הלב של "action הוא ניתוב, לא הרשאה": ה-URL יכול לבקש מה שירצה,
    התשובה נקבעת אך ורק לפי תאריך האירוע.
    """
    api, _ = bootstrap()
    _set_event(api, event_date=_event_date_in(14), event_time="19:30",
               venue_address="הרצל 5, תל אביב")
    g = api.add_guest("מנחש", "0507000003")
    tok = _token(api, g["id"])

    plain = api.client.get(f"/confirm/{tok}").json()
    spoofed = api.client.get(f"/confirm/{tok}?action=gift").json()
    assert plain["actions"] == spoofed["actions"], "פרמטר ב-URL שינה את הזמינות"
    assert spoofed["actions"]["gift"] is False, "המתנה נפתחה מוקדם דרך ה-URL"

    # גם שילובים "יצירתיים" לא פותחים כלום.
    for q in ("?action=gift&gift=true", "?actions[gift]=1", "?action=GIFT", "?action=../gift"):
        acts = api.client.get(f"/confirm/{tok}{q}").json()["actions"]
        assert acts["gift"] is False, f"'{q}' הצליח לפתוח את המתנה"

    # ובתוך החלון — נפתח, בלי שנגענו ב-URL בכלל.
    _set_event(api, event_date=_event_date_in(2))
    assert api.client.get(f"/confirm/{tok}").json()["actions"]["gift"] is True
    print("✓ API: אי אפשר לפתוח את המתנה מוקדם דרך ה-URL, בשום וריאציה")


def test_gift_window_does_not_leak_across_guests_or_events() -> None:
    """המתנה נגזרת מהאירוע *של בעל הטוקן* — לא מאירוע אחר שנמצא בחלון."""
    api_a, _ = bootstrap()
    _set_event(api_a, event_date=_event_date_in(30))     # רחוק — סגור
    ga = api_a.add_guest("מוזמן רחוק", "0507000004")
    tok_a = _token(api_a, ga["id"])

    api_b, _ = bootstrap()
    _set_event(api_b, event_date=_event_date_in(1))      # קרוב — פתוח
    gb = api_b.add_guest("מוזמן קרוב", "0507000005")
    tok_b = _token(api_b, gb["id"])

    a = api_a.client.get(f"/confirm/{tok_a}").json()
    b = api_a.client.get(f"/confirm/{tok_b}").json()
    assert a["actions"]["gift"] is False, "אירוע רחוק קיבל מתנה פתוחה"
    assert b["actions"]["gift"] is True, "אירוע קרוב לא קיבל מתנה פתוחה"
    assert a["full_name"] == "מוזמן רחוק" and b["full_name"] == "מוזמן קרוב"

    # ניסיון להחליף זהות ב-query בזמן שמבקשים מתנה — לא עוזר.
    spoof = api_a.client.get(f"/confirm/{tok_a}?action=gift&guest_id={gb['id']}").json()
    assert spoof["full_name"] == "מוזמן רחוק" and spoof["actions"]["gift"] is False
    print("✓ API: חלון המתנה מבודד לחלוטין בין מוזמנים ובין אירועים")


# ---- יחידה: חלון הזמן ----------------------------------------------------

def test_window_parsing_edge_cases() -> None:
    assert calendar_links.parse_window("", "19:00") is None, "בלי תאריך אין חלון"
    assert calendar_links.parse_window("לא-תאריך", "19:00") is None, "תאריך שבור → אין חלון"
    assert calendar_links.parse_window("2026-11-12", "שעה").all_day, "שעה שבורה → יום שלם"
    w = calendar_links.parse_window("2026-11-12", "19:30")
    assert (w.end - w.start).total_seconds() == calendar_links.DEFAULT_DURATION_HOURS * 3600
    # קיץ מול חורף — הסטת אזור הזמן חייבת להשתנות לבד.
    summer = calendar_links.parse_window("2026-07-01", "19:30")
    assert summer.start.utcoffset().total_seconds() == 3 * 3600, "קיץ בישראל הוא UTC+3"
    assert w.start.utcoffset().total_seconds() == 2 * 3600, "חורף בישראל הוא UTC+2"
    print("✓ חלון זמן: קלט שבור לא מפיל, ושעון קיץ/חורף מטופל לבד")


if __name__ == "__main__":
    try:
        test_window_parsing_edge_cases()
        test_valid_guest_sees_own_hub()
        test_invalid_token_is_rejected_everywhere()
        test_guest_cannot_reach_another_guest_or_event()
        test_missing_venue_hides_navigation()
        test_missing_date_hides_calendar()
        test_missing_time_becomes_all_day()
        test_ics_is_valid_and_leaks_nothing()
        test_ics_stable_uid_prevents_duplicates()
        test_navigation_links_use_real_address()
        test_calendar_title_follows_event_type()
        test_existing_rsvp_still_works()
        test_gift_availability_through_api()
        test_other_actions_survive_the_whole_journey()
        test_gift_url_param_grants_nothing()
        test_gift_window_does_not_leak_across_guests_or_events()
        print("\nכל בדיקות ה-Guest Hub עברו ✓")
    finally:
        shutdown()
