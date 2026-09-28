"""בדיקות לייצוא רשימת המוזמנים לאייפלן (GET /guests/iplan-export[/summary]).

החלטת בעלים (2026-09-28): קובץ ``.xls`` במבנה תבנית אייפלן, רק מי שאישר
הגעה, עם ``Guest.effective_seats``. הקובץ שנוצר נקרא בחזרה ומושווה לתבנית
האמיתית (``tests/fixtures/iplan_template.xls``) — לא לרשימה שהועתקה לבדיקה.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import xlrd  # noqa: E402

from tests.e2e_seating import bootstrap, create_event, register  # noqa: E402

TEMPLATE = Path(__file__).resolve().parent / "fixtures" / "iplan_template.xls"


def _set_confirmed_count(guest_id: int, count: int) -> None:
    """הכמות שהמוזמן מזין בדף האישור — לא נחשפת בעריכת הבעלים, לכן ישירות ב-DB."""
    from app import models
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        db.get(models.Guest, guest_id).confirmed_count = count
        db.commit()
    finally:
        db.close()


def _download(api):
    r = api.client.get("/guests/iplan-export", headers=api.headers)
    assert r.status_code == 200, r.text
    return r


def _sheet(content: bytes):
    return xlrd.open_workbook(file_contents=content, formatting_info=True).sheet_by_index(0)


def _data_rows(sheet) -> list[list]:
    return [sheet.row_values(r) for r in range(2, sheet.nrows)]


def _summary(api) -> dict:
    r = api.client.get("/guests/iplan-export/summary", headers=api.headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_file_matches_iplan_template_structure() -> None:
    api, teardown = bootstrap()
    try:
        g = api.add_guest("אבי כהן", "0501234567", party_size=2, side="groom", group_type="friends")
        api.confirm(g["id"])
        r = _download(api)
        assert r.headers["content-type"] == "application/vnd.ms-excel"
        disposition = r.headers["content-disposition"]
        assert "attachment" in disposition and ".xls" in disposition

        # קובץ Excel 97–2003 אמיתי (חתימת OLE2), לא xlsx/csv.
        assert r.content[:8] == bytes.fromhex("d0cf11e0a1b11ae1")

        out = xlrd.open_workbook(file_contents=r.content, formatting_info=True)
        tpl = xlrd.open_workbook(str(TEMPLATE), formatting_info=True)
        assert out.biff_version == tpl.biff_version == 80
        assert out.sheet_names() == tpl.sheet_names() == ["הזמנות"]
        s, t = out.sheet_by_index(0), tpl.sheet_by_index(0)

        # שתי שורות הכותרת — טקסט, סדר ומיזוגים זהים לתבנית.
        assert s.row_values(0) == t.row_values(0)
        assert s.row_values(1) == t.row_values(1)
        assert s.ncols == t.ncols == 12
        assert sorted(s.merged_cells) == sorted(t.merged_cells)

        # סוגי הנתונים בשורת הנתונים: מספר בעמודת האורחים, טקסט בטלפון.
        assert s.cell(2, 1).ctype == xlrd.XL_CELL_NUMBER
        assert s.cell(2, 4).ctype == xlrd.XL_CELL_TEXT
        print("✓ מבנה הקובץ תואם לתבנית של אייפלן")
    finally:
        teardown()


def test_confirmed_guests_exported_with_mapping() -> None:
    api, teardown = bootstrap()
    try:
        a = api.add_guest("אבי כהן", "0501234567", party_size=2, side="groom", group_type="friends")
        b = api.add_guest("ישראל לוי", "031234567", party_size=1, side="bride", group_type="close_family")
        c = api.add_guest("משפחת ישראלי", "0521111111", party_size=3, group_type="משפחת ישראלי")
        for g in (a, b, c):
            api.confirm(g["id"])

        rows = _data_rows(_sheet(_download(api).content))
        by_name = {row[0]: row for row in rows}
        assert by_name["אבי כהן"][:6] == ["אבי כהן", 2.0, "חתן", "חברים", "050-1234567", ""]
        # קווי → עמודת טלפון רגיל, לא סלולרי.
        assert by_name["ישראל לוי"][:6] == ["ישראל לוי", 1.0, "כלה", "משפחה קרובה", "", "03-1234567"]
        # צד משותף → ריק; קבוצה שהמשתמש יצר → כמו שהיא.
        assert by_name["משפחת ישראלי"][2:4] == ["", "משפחת ישראלי"]
        # עמודות שאין להן מקור ב-VEYA — ריקות.
        for row in rows:
            assert row[6:] == ["", "", "", "", "", ""]
        print("✓ מיפוי VEYA → אייפלן נכון")
    finally:
        teardown()


def test_not_confirmed_guests_are_excluded_and_counted() -> None:
    api, teardown = bootstrap()
    try:
        yes = api.add_guest("מגיע", "0500000001", party_size=2)
        no = api.add_guest("לא מגיע", "0500000002", party_size=2)
        maybe = api.add_guest("אולי", "0500000003", party_size=2)
        api.add_guest("טרם השיב", "0500000004", party_size=2)
        api.confirm(yes["id"])
        api.client.patch(f"/guests/{no['id']}", headers=api.headers, json={"rsvp_status": "declined"})
        api.client.patch(f"/guests/{maybe['id']}", headers=api.headers, json={"rsvp_status": "maybe"})

        summary = _summary(api)
        assert (summary["invitations"], summary["seats"]) == (1, 2)
        assert (summary["not_confirmed"], summary["declined"]) == (2, 1)
        assert [r[0] for r in _data_rows(_sheet(_download(api).content))] == ["מגיע"]
        print("✓ רק מי שאישר נכנס; השאר נספרים בסיכום")
    finally:
        teardown()


def test_seats_come_from_effective_seats() -> None:
    api, teardown = bootstrap()
    try:
        # הוזמנו 5, אישרו 3 → בקובץ 3 (לא הכמות שהוזמנה).
        g = api.add_guest("משפחת כהן", "0501111111", party_size=5)
        api.confirm(g["id"])
        _set_confirmed_count(g["id"], 3)
        # אישר בלי לציין כמות → נופלים לכמות שהוזמנה.
        h = api.add_guest("זוג לוי", "0502222222", party_size=2)
        api.confirm(h["id"])

        rows = {r[0]: r[1] for r in _data_rows(_sheet(_download(api).content))}
        assert rows == {"משפחת כהן": 3.0, "זוג לוי": 2.0}
        assert _summary(api)["seats"] == 5
        print("✓ הכמות = effective_seats")
    finally:
        teardown()


def test_guest_without_phone_is_exported_with_warning() -> None:
    api, teardown = bootstrap()
    try:
        g = api.add_guest("בלי טלפון", "0501111111")
        api.confirm(g["id"])
        # בייבוא אפשר להגיע למוזמן בלי מספר / עם מספר לא תקין.
        from app import models
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            db.get(models.Guest, g["id"]).phone = ""
            db.commit()
        finally:
            db.close()

        summary = _summary(api)
        assert summary["invitations"] == 1
        assert summary["issues"] == [
            {"guest_id": g["id"], "full_name": "בלי טלפון", "kind": "bad_phone", "excluded": False}
        ]
        row = _data_rows(_sheet(_download(api).content))[0]
        assert row[0] == "בלי טלפון" and row[4:6] == ["", ""]
        print("✓ מוזמן בלי טלפון נכנס, עם אזהרה")
    finally:
        teardown()


def test_hebrew_and_special_characters_kept_as_text() -> None:
    api, teardown = bootstrap()
    try:
        names = ['רס"ן יוסי בן-דוד', "אביבה ואביב אביבי (ילדים)", "=SUM(A1:A2)", "O'Brien & שות'"]
        for i, n in enumerate(names):
            g = api.add_guest(n, f"05000000{i:02d}")
            api.confirm(g["id"])
        sheet = _sheet(_download(api).content)
        got = [sheet.cell(r, 0) for r in range(2, sheet.nrows)]
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
        assert "אישרו" in r.json()["detail"]
        # גם כשיש מוזמנים אבל אף אחד לא אישר.
        api.add_guest("טרם השיב", "0501111111")
        assert api.client.get("/guests/iplan-export", headers=api.headers).status_code == 422
        print("✓ רשימה ריקה — הודעה ולא קובץ ריק")
    finally:
        teardown()


def test_required_field_problems_are_reported_and_excluded() -> None:
    api, teardown = bootstrap()
    try:
        ok = api.add_guest("תקין", "0501111111")
        zero = api.add_guest("אישר אפס", "0502222222", party_size=2)
        noname = api.add_guest("זמני", "0503333333")
        for g in (ok, zero, noname):
            api.confirm(g["id"])
        _set_confirmed_count(zero["id"], 0)
        from app import models
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            db.get(models.Guest, noname["id"]).full_name = "   "
            db.commit()
        finally:
            db.close()

        summary = _summary(api)
        kinds = {i["kind"]: i for i in summary["issues"]}
        assert kinds["zero_seats"]["excluded"] and kinds["zero_seats"]["full_name"] == "אישר אפס"
        assert kinds["missing_name"]["excluded"]
        assert summary["invitations"] == 1
        assert [r[0] for r in _data_rows(_sheet(_download(api).content))] == ["תקין"]
        print("✓ שם חסר / כמות 0 — מדווחים ולא נכנסים לקובץ")
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
                    phone=f"05{i:08d}", party_size=2, rsvp_status="confirmed",
                )
                for i in range(1500)
            ])
            db.commit()
        finally:
            db.close()

        sheet = _sheet(_download(api).content)
        assert sheet.nrows == 1500 + 2
        assert _summary(api)["seats"] == 3000
        print("✓ 1,500 מוזמנים")
    finally:
        teardown()


def test_other_user_cannot_export_event() -> None:
    api, teardown = bootstrap()
    try:
        g = api.add_guest("פרטי", "0501111111")
        api.confirm(g["id"])

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
        g = api.add_guest("דוד", "0501111111", side="groom", group_type="class")
        api.confirm(g["id"])
        row = _data_rows(_sheet(_download(api).content))[0]
        assert row[2:4] == ["צד משפחת האב", "כיתה"]
        print("✓ בר מצווה — מונחי הצד והקבוצה של סוג האירוע")
    finally:
        teardown()
