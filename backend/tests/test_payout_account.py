"""בדיקות ל"פרטי קבלת מתנות" — חשבון הבנק של בעלי האירוע.

מה שהקובץ הזה שומר עליו:

1. **רשימת הבנקים אמיתית ונגזרת מבנק ישראל** — ובעיקר: אין בה סולקים
   (ישראכרט/מקס/כאל) ואין בה תשתיות שוק (בנק ישראל, שב"א, מס"ב).
2. **קוד הבנק הוא נתון נפרד** — נבדק מול רשימה סגורה בשרת, ולעולם לא
   נגזר מטקסט שהוקלד.
3. **ולידציה בשרת** — ספרות בלבד, אורכים סבירים, הודעות בעברית.
4. **הרשאות** — בעלים בלבד. גם חבר-אירוע עם ``view_reports`` (שכן רואה
   מתנות) לא רואה את חשבון הבנק.
5. **מספר החשבון המלא לא חוזר** ב-GET, ואישור ניהול החשבון אינו נגיש
   דרך הנתיב הציבורי ``/media``.

הרצה: ``venv/bin/python tests/test_payout_account.py`` (עצמאי, בלי pytest).
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# הבדיקה על ההרשאות כאן נשענת על כך שחבר-אירוע **כן** רואה מתנות (ורק
# חשבון הבנק חסום לו). מאז שמסך המתנות מגודר בזכאות לשירות
# (``gift_eligibility``), צריך להדליק את השירות כדי שההנחה הזו תתקיים.
import os  # noqa: E402

os.environ["VEYA_GIFT_ENABLED"] = "1"

from sqlalchemy import select  # noqa: E402

from app import banks, models  # noqa: E402
from app.database import SessionLocal, set_request_identity  # noqa: E402
from tests.e2e_seating import bootstrap, register, shutdown  # noqa: E402

# PDF מינימלי ותקין — מספיק כדי לעבור את בדיקת הסוג והגודל.
PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
PDF_DATA_URL = "data:application/pdf;base64," + base64.b64encode(PDF_BYTES).decode()
PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 40).decode()


def _valid(**over):
    body = {
        "bank_code": 12,          # בנק הפועלים
        "branch_number": "045",
        "account_number": "123456",
        "certificate": PDF_DATA_URL,
    }
    body.update(over)
    return body


def _save(api, **over):
    return api.client.put("/payout", headers=api.headers, json=_valid(**over))


# ── 1. רשימת הבנקים ──────────────────────────────────────────────────────

def test_bank_list_comes_from_bank_of_israel() -> None:
    assert "בנק ישראל" in banks.SOURCE
    assert len(banks.BANKS) >= 15, "הרשימה קטנה מדי — כנראה נכשלה ההפקה מהמאגר"
    codes = {b.code for b in banks.BANKS}
    # הבנקים הגדולים חייבים להיות שם, עם הקוד הרשמי שלהם.
    for code, expected in [(10, "לאומי"), (12, "הפועלים"), (20, "מזרחי"), (11, "דיסקונט")]:
        assert code in codes, f"חסר קוד בנק {code}"
        assert expected in banks.BY_CODE[code].name, banks.BY_CODE[code].name
    print("✓ רשימת הבנקים נגזרת מבנק ישראל וכוללת את הבנקים הגדולים")


def test_no_credit_card_acquirers_in_bank_list() -> None:
    """סולקים אינם בנקים — הם לא מקום שמנהלים בו חשבון עו"ש.

    ישראכרט ומקס **כן** מופיעים במאגר "סניפים לסליקה" של בנק ישראל, ולכן
    הבדיקה הזו היא ההגנה על כלל הסינון: אם מישהו יפשט אותו בעתיד, כאן זה
    ייפול.
    """
    names = " ".join(b.name + " " + b.legal_name for b in banks.BANKS)
    for forbidden in ("ישראכרט", "מקס", "כאל", "קארדקום", "Cardcom", "MAX"):
        assert forbidden not in names, f"סולק ברשימת הבנקים: {forbidden}"
    codes = {b.code for b in banks.BANKS}
    assert 1 not in codes and 6 not in codes, "קוד של סולק נשאר ברשימה"
    print("✓ אין סולקים ברשימת הבנקים (ישראכרט/מקס/כאל)")


def test_no_market_infrastructure_in_bank_list() -> None:
    codes = {b.code for b in banks.BANKS}
    for code, who in [(99, "בנק ישראל"), (59, 'שב"א'), (50, 'מס"ב')]:
        assert code not in codes, f"תשתית שוק ברשימת הבנקים: {who}"
    print("✓ אין תשתיות שוק ברשימה (בנק ישראל, שב״א, מס״ב)")


def test_backend_and_frontend_lists_match() -> None:
    """שני הקבצים נוצרים מאותו סקריפט — הבדיקה נועלת שלא ייווצר פער.

    אם מישהו יערוך אחד מהם ידנית, כאן זה יתגלה.
    """
    ts = (Path(__file__).resolve().parent.parent.parent
          / "frontend" / "src" / "data" / "banks.ts").read_text(encoding="utf-8")
    import re
    pairs = re.findall(r"\{ code: (\d+), name: '([^']*)'", ts) or \
        re.findall(r'\{ code: (\d+), name: "([^"]*)"', ts)
    assert pairs, "לא נמצאו בנקים בקובץ ה-TypeScript"
    assert [(int(c), n) for c, n in pairs] == [(b.code, b.name) for b in banks.BANKS], \
        "רשימת הבנקים בצד השרת ובצד הלקוח אינן זהות — יש להריץ tools/fetch_israeli_banks.py"
    print(f"✓ רשימות השרת והלקוח זהות ({len(pairs)} בנקים)")


# ── 2. ולידציה ───────────────────────────────────────────────────────────

def test_branch_and_account_accept_digits_only() -> None:
    api, _ = bootstrap()
    for bad in ("12a", "אב", "12.5", "-12", "12/3", ""):
        r = _save(api, branch_number=bad)
        assert r.status_code == 422, f"מספר סניף לא תקין התקבל: {bad!r}"
        assert any("֐" <= ch <= "ת" for ch in r.json()["detail"]), "השגיאה אינה בעברית"
    for bad in ("12a", "אבגד", "", "12 34x"):
        r = _save(api, account_number=bad)
        assert r.status_code == 422, f"מספר חשבון לא תקין התקבל: {bad!r}"
    print("✓ מספר סניף וחשבון מקבלים ספרות בלבד, והשגיאות בעברית")


def test_length_limits_enforced() -> None:
    api, _ = bootstrap()
    assert _save(api, branch_number="1234").status_code == 422, "סניף בן 4 ספרות התקבל"
    assert _save(api, account_number="123").status_code == 422, "חשבון קצר מדי התקבל"
    assert _save(api, account_number="1" * 14).status_code == 422, "חשבון ארוך מדי התקבל"
    assert _save(api, branch_number="45").status_code == 200, "סניף בן 2 ספרות נדחה בטעות"
    print("✓ נאכפים אורכים: סניף עד 3 ספרות, חשבון 4–13")


def test_branch_is_padded_to_three_digits() -> None:
    api, _ = bootstrap()
    r = _save(api, branch_number="45")
    assert r.json()["branch_number"] == "045", r.json()
    print("✓ מספר סניף מרופד לשלוש ספרות (45 → 045)")


def test_separators_are_cleaned_not_rejected() -> None:
    """אנשים מעתיקים "12-345" מאישור הבנק — מקף ורווח מנוקים, לא נפסלים."""
    api, _ = bootstrap()
    r = _save(api, account_number="12-345 67")
    assert r.status_code == 200 and r.json()["account_number_masked"].endswith("4567"), r.json()
    print("✓ מקפים ורווחים מנוקים ממספר החשבון")


def test_unknown_bank_code_rejected() -> None:
    api, _ = bootstrap()
    for bad in (7, 999, 0, -12, 1, 6):  # 1/6 = ישראכרט/מקס — הוחרגו במכוון
        assert _save(api, bank_code=bad).status_code == 422, f"קוד בנק לא תקין התקבל: {bad}"
    print("✓ קוד בנק שאינו ברשימת בנק ישראל נדחה (כולל קודי סולקים)")


def test_bank_code_is_not_derived_from_typed_text() -> None:
    """הדרישה: קוד הבנק הוא נתון נפרד, ולא נגזר ממה שהמשתמש הקליד."""
    api, _ = bootstrap()
    r = api.client.put("/payout", headers=api.headers,
                       json=_valid(bank_code=12) | {"bank_name": "בנק לאומי"})
    assert r.status_code == 200
    # שם הבנק בתשובה נגזר מהקוד (12 = הפועלים), לא מהטקסט שנשלח.
    assert "הפועלים" in r.json()["bank_name"], r.json()
    print("✓ שם הבנק נגזר מהקוד ולא מטקסט שנשלח מהלקוח")


# ── 3. אישור ניהול חשבון ─────────────────────────────────────────────────

def test_certificate_is_required_on_first_save() -> None:
    api, _ = bootstrap()
    r = api.client.put("/payout", headers=api.headers, json=_valid(certificate=None))
    assert r.status_code == 422 and "אישור" in r.json()["detail"], r.json()
    print("✓ אי אפשר לשמור לראשונה בלי אישור ניהול חשבון")


def test_certificate_type_and_size_enforced() -> None:
    api, _ = bootstrap()
    bad_type = "data:image/svg+xml;base64," + base64.b64encode(b"<svg/>").decode()
    assert _save(api, certificate=bad_type).status_code == 422, "SVG התקבל"
    huge = "data:application/pdf;base64," + base64.b64encode(b"x" * (11 * 1024 * 1024)).decode()
    assert _save(api, certificate=huge).status_code == 413, "קובץ ענק התקבל"
    assert _save(api, certificate=PNG_DATA_URL).status_code == 200, "PNG תקין נדחה"
    print("✓ נאכפים סוג הקובץ (PDF/תמונה, לא SVG) וגודל מקסימלי")


def test_certificate_served_only_to_owner_and_not_via_media() -> None:
    api, _ = bootstrap()
    _save(api)
    r = api.client.get("/payout/certificate", headers=api.headers)
    assert r.status_code == 200 and r.content == PDF_BYTES, r.status_code
    assert r.headers["content-type"].startswith("application/pdf")
    assert "no-store" in r.headers.get("cache-control", ""), "מסמך פיננסי נשמר במטמון"
    assert api.client.get("/payout/certificate").status_code in (401, 403), "הוגש בלי אימות"

    # הקובץ אינו בטבלת media_blobs, ולכן אין לו נתיב ציבורי כלל.
    set_request_identity(None)
    db = SessionLocal()
    try:
        blobs = db.scalars(select(models.MediaBlob)).all()
        assert not any(b.data == PDF_BYTES for b in blobs), "האישור נשמר ב-media_blobs הציבורי"
    finally:
        db.close()
    print("✓ האישור מוגש רק לבעלים, ואינו נגיש דרך /media הציבורי")


# ── 4. תצוגה והרשאות ─────────────────────────────────────────────────────

def test_full_account_number_never_returned() -> None:
    api, _ = bootstrap()
    _save(api, account_number="98765432")
    raw = api.client.get("/payout", headers=api.headers).text
    assert "98765432" not in raw, "מספר החשבון המלא חזר ב-GET"
    body = api.client.get("/payout", headers=api.headers).json()
    assert body["account_number_masked"] == "••••5432", body
    print("✓ מספר החשבון חוזר מוסתר (ארבע ספרות אחרונות בלבד)")


def test_unconfigured_event_returns_empty_state() -> None:
    api, _ = bootstrap()
    body = api.client.get("/payout", headers=api.headers).json()
    assert body["configured"] is False and body["bank_code"] is None, body
    print("✓ אירוע בלי פרטים מחזיר מצב ריק ולא שגיאה")


def test_requires_authentication() -> None:
    api, _ = bootstrap()
    assert api.client.get("/payout").status_code in (401, 403)
    assert api.client.put("/payout", json=_valid()).status_code in (401, 403)
    print("✓ הנתיב סגור ללא אימות")


def test_member_with_gift_permission_cannot_see_bank_details() -> None:
    """מפיק שרואה מתנות — לא רואה את חשבון הבנק. זו הבדיקה המרכזית כאן."""
    api, _ = bootstrap()
    _save(api)

    member_token = register(api.client)
    set_request_identity(None)
    db = SessionLocal()
    try:
        users = db.scalars(select(models.User)).all()
        member_user = [u for u in users if u.email.startswith("test-")][-1]
        db.add(models.EventMember(
            event_id=api.event_id, user_id=member_user.id,
            role="producer", status="active", permissions=["view_reports", "view_event"],
        ))
        db.commit()
    finally:
        db.close()

    # מפיק אינו "בעל" אירוע, ולכן חייב לציין במפורש באיזה אירוע מדובר
    # (בדיוק כמו שהפרונטאנד עושה — ראו deps.py::EventAccess).
    headers = {"Authorization": f"Bearer {member_token}",
               "X-Event-Id": str(api.event_id)}
    assert api.client.get("/gifts", headers=headers).status_code == 200, \
        "המפיק אמור לראות מתנות — אחרת הבדיקה לא מוכיחה כלום"
    for path in ("/payout", "/payout/certificate"):
        assert api.client.get(path, headers=headers).status_code in (403, 404), \
            f"חבר-אירוע ראה את {path}"
    assert api.client.put("/payout", headers=headers, json=_valid()).status_code in (403, 404)
    print("✓ חבר-אירוע שרואה מתנות אינו רואה (ואינו משנה) את חשבון הבנק")


def test_no_cross_event_access() -> None:
    api_a, _ = bootstrap()
    _save(api_a, account_number="11112222")
    api_b, _ = bootstrap()
    body = api_b.client.get("/payout", headers=api_b.headers).json()
    assert body["configured"] is False, "אירוע אחר ראה פרטי חשבון"
    assert api_b.client.get("/payout/certificate", headers=api_b.headers).status_code == 404
    print("✓ אין דליפה בין אירועים")


def test_update_keeps_certificate_and_overwrites_details() -> None:
    api, _ = bootstrap()
    _save(api)
    r = api.client.put("/payout", headers=api.headers,
                       json=_valid(bank_code=10, branch_number="800",
                                   account_number="55556666", certificate=None))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bank_code"] == 10 and "לאומי" in body["bank_name"]
    assert body["branch_number"] == "800"
    assert body["certificate"] is not None, "האישור הקיים נמחק בעדכון"
    # יש חשבון אחד לכל אירוע — עדכון דורס, לא מוסיף שורה.
    set_request_identity(None)
    db = SessionLocal()
    try:
        rows = db.scalars(select(models.PayoutAccount)
                          .where(models.PayoutAccount.event_id == api.event_id)).all()
        assert len(rows) == 1, f"נוצרו {len(rows)} שורות לאותו אירוע"
    finally:
        db.close()
    print("✓ עדכון דורס את הפרטים ושומר את האישור הקיים")


if __name__ == "__main__":
    try:
        test_bank_list_comes_from_bank_of_israel()
        test_no_credit_card_acquirers_in_bank_list()
        test_no_market_infrastructure_in_bank_list()
        test_backend_and_frontend_lists_match()
        test_branch_and_account_accept_digits_only()
        test_length_limits_enforced()
        test_branch_is_padded_to_three_digits()
        test_separators_are_cleaned_not_rejected()
        test_unknown_bank_code_rejected()
        test_bank_code_is_not_derived_from_typed_text()
        test_certificate_is_required_on_first_save()
        test_certificate_type_and_size_enforced()
        test_certificate_served_only_to_owner_and_not_via_media()
        test_full_account_number_never_returned()
        test_unconfigured_event_returns_empty_state()
        test_requires_authentication()
        test_member_with_gift_permission_cannot_see_bank_details()
        test_no_cross_event_access()
        test_update_keeps_certificate_and_overwrites_details()
        print("\nכל בדיקות פרטי קבלת המתנות עברו ✓")
    finally:
        shutdown()
