"""בדיקות לייצוא רשימת המוזמנים לאייפלן (GET /guests/iplan-export[/summary]).

החלטת בעלים (2026-09-28): קובץ ``.xls`` במבנה של אייפלן — כמו קובץ אייפלן של
אירוע חי אחרי אישורי הגעה והושבה: כל המוזמנים, עם "אישרו שיגיעו"
(``Guest.effective_seats``), "מתלבטים" ו"מספר שולחן". עמודות A–K והמיזוגים
מושווים לתבנית האמיתית (``tests/fixtures/iplan_template.xls``); ארבע העמודות
הנוספות — לקובץ החי שהבעלים מסר (לא נשמר כאן, יש בו פרטי מוזמנים אמיתיים).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import xlrd  # noqa: E402

from tests.e2e_seating import bootstrap, create_event, register  # noqa: E402

TEMPLATE = Path(__file__).resolve().parent / "fixtures" / "iplan_template.xls"

# שורת הכותרות בקובץ החי של אייפלן, כפי שהיא (עמודה L — כותרת ריקה).
LIVE_HEADERS = [
    "הזמנה לכבוד", "מס' אורחים שהוזמנו", "צד", "קבוצה", "סלולרי", "טלפון רגיל",
    "אימייל", "עיר", "רחוב", "מיקוד", "תא דואר", "",
    "אישרו שיגיעו", "מתלבטים", "מספר שולחן", "הגיעו",
]
NAME, INVITED, SIDE, GROUP, MOBILE, LANDLINE = 0, 1, 2, 3, 4, 5
CONFIRMED, MAYBE, TABLE, ARRIVED = 12, 13, 14, 15


def _db_update(guest_id: int, **fields) -> None:
    """שדות שהבעלים לא עורך ישירות (כמות שהמוזמן אישר, שם ריק מייבוא)."""
    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        g = db.get(models.Guest, guest_id)
        for k, v in fields.items():
            setattr(g, k, v)
        db.commit()
    finally:
        db.close()


def _set_status(api, guest_id: int, status: str) -> None:
    r = api.client.patch(f"/guests/{guest_id}", headers=api.headers, json={"rsvp_status": status})
    assert r.status_code == 200, r.text


def _table(number: int, guest_ids: list[int]) -> dict:
    return {"table_number": number, "x": 0, "y": 0, "guest_ids": guest_ids,
            "table_type": "round", "capacity": 12, "rotation": 0, "name": "",
            "color": "", "notes": "", "locked": False, "is_reserve": False}


def _download(api):
    r = api.client.get("/guests/iplan-export", headers=api.headers)
    assert r.status_code == 200, r.text
    return r


def _sheet(content: bytes):
    return xlrd.open_workbook(file_contents=content, formatting_info=True).sheet_by_index(0)


def _rows(api) -> dict[str, list]:
    s = _sheet(_download(api).content)
    return {s.cell_value(r, 0): s.row_values(r) for r in range(2, s.nrows)}


def _summary(api) -> dict:
    r = api.client.get("/guests/iplan-export/summary", headers=api.headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_file_matches_iplan_structure() -> None:
    api, teardown = bootstrap()
    try:
        g = api.add_guest("אבי כהן", "0501234567", party_size=2, side="groom", group_type="friends")
        api.confirm(g["id"])
        r = _download(api)
        assert r.headers["content-type"] == "application/vnd.ms-excel"
        disposition = r.headers["content-disposition"]
        assert "attachment" in disposition and ".xls" in disposition
        # שם הקובץ במבנה של iPlan: "<בעלי האירוע> - הזמנות.xls".
        assert _summary(api)["filename"] == "דני ורותי - הזמנות.xls"
        assert "%D7%94%D7%96%D7%9E%D7%A0%D7%95%D7%AA.xls" in disposition

        # קובץ Excel 97–2003 אמיתי (חתימת OLE2), לא xlsx/csv.
        assert r.content[:8] == bytes.fromhex("d0cf11e0a1b11ae1")

        out = xlrd.open_workbook(file_contents=r.content, formatting_info=True)
        tpl = xlrd.open_workbook(str(TEMPLATE), formatting_info=True)
        assert out.biff_version == tpl.biff_version == 80
        assert out.sheet_names() == tpl.sheet_names() == ["הזמנות"]
        s, t = out.sheet_by_index(0), tpl.sheet_by_index(0)

        # שורת כותרות-העל והמיזוגים — זהים לתבנית.
        assert s.row_values(0)[:12] == t.row_values(0)
        assert sorted(s.merged_cells) == sorted(t.merged_cells)
        # עמודות A–K זהות לתבנית; כל 16 העמודות — כמו בקובץ החי.
        assert s.row_values(1)[:11] == t.row_values(1)[:11]
        assert s.row_values(1) == LIVE_HEADERS

        # סוגי הנתונים: מספרים בכמויות, טקסט בטלפון ובשולחן.
        assert s.cell(2, INVITED).ctype == xlrd.XL_CELL_NUMBER
        assert s.cell(2, CONFIRMED).ctype == xlrd.XL_CELL_NUMBER
        assert s.cell(2, MOBILE).ctype == xlrd.XL_CELL_TEXT
        print("✓ מבנה הקובץ תואם לאייפלן")
    finally:
        teardown()


def test_mapping_of_names_sides_groups_and_phones() -> None:
    api, teardown = bootstrap()
    try:
        api.add_guest("אבי כהן", "0542163535", party_size=2, side="groom", group_type="friends")
        api.add_guest("ישראל לוי", "031234567", side="bride", group_type="close_family")
        api.add_guest("משפחת ישראלי", "0521111111", party_size=3, group_type="עבודה נרי")

        rows = _rows(api)
        assert rows["אבי כהן"][:6] == ["אבי כהן", 2.0, "חתן", "חברים", "054-216-3535", ""]
        # קווי → עמודת טלפון רגיל, לא סלולרי.
        assert rows["ישראל לוי"][:6] == ["ישראל לוי", 1.0, "כלה", "משפחה קרובה", "", "03-123-4567"]
        # צד משותף → "חתן וכלה" כמו באייפלן; קבוצה שהמשתמש יצר → כמו שהיא.
        assert rows["משפחת ישראלי"][SIDE:GROUP + 1] == ["חתן וכלה", "עבודה נרי"]
        # עמודות שאין להן מקור ב-VEYA — ריקות.
        for row in rows.values():
            assert row[6:12] == ["", "", "", "", "", ""]
            assert row[ARRIVED] == ""
        print("✓ מיפוי שם/צד/קבוצה/טלפון")
    finally:
        teardown()


def test_all_guests_exported_with_rsvp_state() -> None:
    api, teardown = bootstrap()
    try:
        yes = api.add_guest("מגיע", "0500000001", party_size=2)
        no = api.add_guest("לא מגיע", "0500000002", party_size=2)
        maybe = api.add_guest("מתלבט", "0500000003", party_size=2)
        api.add_guest("טרם השיב", "0500000004", party_size=2)
        api.confirm(yes["id"])
        _set_status(api, no["id"], "declined")
        _set_status(api, maybe["id"], "maybe")

        rows = _rows(api)
        assert set(rows) == {"מגיע", "לא מגיע", "מתלבט", "טרם השיב"}
        # (הוזמנו, אישרו שיגיעו, מתלבטים) — כמו בקובץ של אייפלן.
        got = {n: (r[INVITED], r[CONFIRMED], r[MAYBE]) for n, r in rows.items()}
        assert got == {
            "מגיע": (2.0, 2.0, ""),
            "לא מגיע": (2.0, 0.0, ""),
            "מתלבט": (2.0, 0.0, 2.0),
            "טרם השיב": (2.0, "", ""),
        }

        summary = _summary(api)
        assert (summary["invitations"], summary["invited_people"], summary["confirmed_people"]) == (4, 8, 2)
        assert (summary["confirmed"], summary["pending"], summary["maybe"], summary["declined"]) == (1, 1, 1, 1)
        print("✓ כל המוזמנים בקובץ, עם מצב אישור ההגעה")
    finally:
        teardown()


def test_confirmed_seats_come_from_effective_seats() -> None:
    api, teardown = bootstrap()
    try:
        # הוזמנו 5, אישרו 3 → "אישרו שיגיעו" 3, "הוזמנו" נשאר 5.
        g = api.add_guest("משפחת כהן", "0501111111", party_size=5)
        api.confirm(g["id"])
        _db_update(g["id"], confirmed_count=3)
        # הוזמן 1, אישר 2 (קורה באייפלן ובחיים).
        h = api.add_guest("זוג לוי", "0502222222", party_size=1)
        api.confirm(h["id"])
        _db_update(h["id"], confirmed_count=2)
        # אישר בלי לציין כמות → נופלים לכמות שהוזמנה.
        k = api.add_guest("יחיד", "0503333333", party_size=1)
        api.confirm(k["id"])

        rows = _rows(api)
        got = {n: (r[INVITED], r[CONFIRMED]) for n, r in rows.items()}
        assert got == {"משפחת כהן": (5.0, 3.0), "זוג לוי": (1.0, 2.0), "יחיד": (1.0, 1.0)}
        assert _summary(api)["confirmed_people"] == 6
        print("✓ 'אישרו שיגיעו' = effective_seats")
    finally:
        teardown()


def test_table_number_only_for_confirmed_seated_guests() -> None:
    api, teardown = bootstrap()
    try:
        a = api.add_guest("משובץ", "0501111111", party_size=2)
        b = api.add_guest("לא משובץ", "0502222222")
        c = api.add_guest("ביטל אחרי שיבוץ", "0503333333")
        for g in (a, b, c):
            api.confirm(g["id"])
        api.save_hall([_table(7, [a["id"]]), _table(12, [c["id"]])])
        _set_status(api, c["id"], "declined")

        rows = _rows(api)
        assert rows["משובץ"][TABLE] == "7"
        assert rows["לא משובץ"][TABLE] == ""
        # השיבוץ נשמר ב-VEYA, אבל מי שביטל לא תופס מקום — ולכן בלי שולחן בקובץ.
        assert rows["ביטל אחרי שיבוץ"][TABLE] == ""
        s = _sheet(_download(api).content)
        cells = [s.cell(r, TABLE) for r in range(2, s.nrows) if s.cell_value(r, TABLE)]
        assert all(cell.ctype == xlrd.XL_CELL_TEXT for cell in cells)
        assert _summary(api)["seated"] == 1
        print("✓ מספר שולחן — רק למי שאישר ושובץ, כטקסט")
    finally:
        teardown()


def test_guest_without_phone_is_exported_with_warning() -> None:
    api, teardown = bootstrap()
    try:
        g = api.add_guest("בלי טלפון", "0501111111")
        _db_update(g["id"], phone="")  # בייבוא אפשר להגיע למוזמן בלי מספר

        summary = _summary(api)
        assert summary["invitations"] == 1
        assert summary["issues"] == [
            {"guest_id": g["id"], "full_name": "בלי טלפון", "kind": "bad_phone", "excluded": False}
        ]
        assert _rows(api)["בלי טלפון"][MOBILE:LANDLINE + 1] == ["", ""]
        print("✓ מוזמן בלי טלפון נכנס, עם אזהרה")
    finally:
        teardown()


def test_hebrew_and_special_characters_kept_as_text() -> None:
    api, teardown = bootstrap()
    try:
        names = ['רס"ן יוסי בן-דוד', "אביבה ואביב אביבי (ילדים)", "=SUM(A1:A2)", "O'Brien & שות'"]
        for i, n in enumerate(names):
            api.add_guest(n, f"05000000{i:02d}")
        sheet = _sheet(_download(api).content)
        got = [sheet.cell(r, NAME) for r in range(2, sheet.nrows)]
        assert sorted(c.value for c in got) == sorted(names)
        # "=..." נשאר טקסט — לא הופך לנוסחה ב-Excel.
        assert all(c.ctype == xlrd.XL_CELL_TEXT for c in got)
        print("✓ עברית ותווים מיוחדים נשמרים כטקסט")
    finally:
        teardown()


def test_empty_list_returns_message_not_file() -> None:
    api, teardown = bootstrap()
    try:
        summary = _summary(api)
        assert summary["invitations"] == 0 and summary["issues"] == []
        r = api.client.get("/guests/iplan-export", headers=api.headers)
        assert r.status_code == 422
        assert "אין מוזמנים" in r.json()["detail"]
        print("✓ רשימה ריקה — הודעה ולא קובץ ריק")
    finally:
        teardown()


def test_missing_name_is_reported_and_excluded() -> None:
    api, teardown = bootstrap()
    try:
        api.add_guest("תקין", "0501111111")
        noname = api.add_guest("זמני", "0503333333")
        _db_update(noname["id"], full_name="   ")

        summary = _summary(api)
        assert summary["issues"] == [
            {"guest_id": noname["id"], "full_name": "", "kind": "missing_name", "excluded": True}
        ]
        assert summary["invitations"] == 1
        assert list(_rows(api)) == ["תקין"]
        print("✓ מוזמן בלי שם — מדווח ולא נכנס לקובץ")
    finally:
        teardown()


def test_large_event() -> None:
    api, teardown = bootstrap()
    try:
        from app import models
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            db.add_all([
                models.Guest(
                    event_id=api.event_id, full_name=f"אורח {i:04d}",
                    phone=f"05{i:08d}", party_size=2,
                    rsvp_status="confirmed" if i % 2 else "pending",
                )
                for i in range(1500)
            ])
            db.commit()
        finally:
            db.close()

        sheet = _sheet(_download(api).content)
        assert sheet.nrows == 1500 + 2
        summary = _summary(api)
        assert (summary["invited_people"], summary["confirmed_people"]) == (3000, 1500)
        print("✓ 1,500 מוזמנים")
    finally:
        teardown()


def test_other_user_cannot_export_event() -> None:
    api, teardown = bootstrap()
    try:
        api.add_guest("פרטי", "0501111111")

        stranger = register(api.client)
        create_event(api.client, stranger)
        headers = {"Authorization": f"Bearer {stranger}", "X-Event-Id": str(api.event_id)}
        for path in ("/guests/iplan-export", "/guests/iplan-export/summary"):
            r = api.client.get(path, headers=headers)
            assert r.status_code == 404, (path, r.status_code, r.text)
            assert "פרטי" not in r.text
        # בלי התחברות בכלל.
        assert api.client.get("/guests/iplan-export",
                              headers={"X-Event-Id": str(api.event_id)}).status_code == 401
        print("✓ משתמש אחר לא יכול לייצא את האירוע")
    finally:
        teardown()


def test_non_wedding_event_uses_its_own_side_terms() -> None:
    api, teardown = bootstrap("bar_mitzvah")
    try:
        api.add_guest("דוד", "0501111111", side="groom", group_type="class")
        api.add_guest("רחל", "0502222222", group_type="friends")
        rows = _rows(api)
        assert rows["דוד"][SIDE:GROUP + 1] == ["צד משפחת האב", "כיתה"]
        assert rows["רחל"][SIDE] == "צד משפחת האב וצד משפחת האם"
        print("✓ בר מצווה — מונחי הצד והקבוצה של סוג האירוע")
    finally:
        teardown()
