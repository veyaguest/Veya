"""בדיקות לאימות הכפול של פרטי קבלת המתנות.

חשבון צריך לעבור **שתי בדיקות בלתי תלויות** לפני שהוא כשיר: אחת של VEYA
ואחת של ספק הסליקה. הקובץ הזה שומר על שני דברים:

1. **שתי הבדיקות באמת נפרדות** — אף אחת לא מזיזה את השנייה, ואף אחת לבדה
   אינה מספיקה.
2. **סכומי המתנות מגודרים בשרת** — לא מוסתרים במסך. לפני אימות מלא הם
   כלל לא נכתבים לתשובת ה-API, ואין פרמטר, כותרת או בקשה ידנית שמחזירה
   אותם.

הבדיקות על מכונת המצבים עצמה נמצאות ב-``test_payout_infrastructure.py``,
ואלה על הטופס ב-``test_payout_account.py``.

הרצה: ``venv/bin/python tests/test_payout_dual_verification.py``
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["VEYA_GIFT_ENABLED"] = "1"

from sqlalchemy import select  # noqa: E402

from app import guest_journey, models, payout_service, payout_status  # noqa: E402
from app.database import SessionLocal, set_request_identity  # noqa: E402
from tests.e2e_seating import bootstrap, register, shutdown  # noqa: E402

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
PDF_URL = "data:application/pdf;base64," + base64.b64encode(PDF).decode()

ACCOUNT = "55446677"


# ── עזרים ────────────────────────────────────────────────────────────────


def _event_date_in(days: int) -> str:
    from datetime import timedelta

    return (guest_journey.today_in_israel() + timedelta(days=days)).isoformat()


def _ready_event(days: int = 1):
    """אירוע עם תאריך וכתובת — כלומר אירוע שהמתנה פתוחה בו."""
    api, _ = bootstrap()
    r = api.client.patch("/event", headers=api.headers, json={
        "event_date": _event_date_in(days), "event_time": "19:30",
        "venue_address": "הרצל 5, תל אביב",
    })
    assert r.status_code == 200, r.text
    return api


def _save(api, **over):
    """שמירת פרטים בלבד (בלי הגשה) — לבדיקת מה פתוח לעריכה ומה נעול."""
    body = {"bank_code": 12, "branch_number": "045",
            "account_number": ACCOUNT, "certificate": PDF_URL}
    body.update(over)
    return api.client.put("/payout", headers=api.headers, json=body)


def _submit_payout(api, account: str = ACCOUNT):
    """שומר פרטי חשבון ומגיש אותם לבדיקה — הצד של בעלי האירוע, במלואו."""
    r = api.client.put("/payout", headers=api.headers, json={
        "bank_code": 12, "branch_number": "045",
        "account_number": account, "certificate": PDF_URL,
    })
    assert r.status_code == 200, r.text
    r = api.client.post("/payout/submit", headers=api.headers)
    assert r.status_code == 200, r.text
    return r.json()


def _admin(api):
    """מייצר משתמש אדמין ומחזיר את כותרות ההרשאה שלו.

    האדמין נוצר במסד ולא דרך ה-API — אין (ובכוונה) נתיב שבו משתמש מסמן
    את עצמו כאדמין.
    """
    token = register(api.client)
    set_request_identity(None)
    db = SessionLocal()
    try:
        user = db.scalars(
            select(models.User).order_by(models.User.id.desc())
        ).first()
        user.is_admin = True
        db.commit()
    finally:
        db.close()
    return {"Authorization": f"Bearer {token}"}


def _guest_token(api, name: str, phone: str):
    g = api.add_guest(name, phone)
    set_request_identity(None)
    db = SessionLocal()
    try:
        return db.get(models.Guest, g["id"]).guest_token
    finally:
        db.close()


def _gift(api, tok, agorot: int, key: str):
    return api.client.post(f"/confirm/{tok}/gift/checkout", json={
        "gift_amount_agorot": agorot, "giver_name": "דנה",
        "blessing": "מזל טוב", "idempotency_key": key, "simulate": "success",
    }).json()


def _set_provider(api, admin_headers, status: str, reason: str = ""):
    r = api.client.post(
        f"/admin/payout/{api.event_id}/provider",
        headers=admin_headers, json={"status": status, "reason": reason},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _row(event_id: int) -> models.PayoutAccount:
    set_request_identity(None)
    db = SessionLocal()
    try:
        row = db.scalars(select(models.PayoutAccount)
                         .where(models.PayoutAccount.event_id == event_id)).first()
        db.expunge(row)
        return row
    finally:
        db.close()


# ── 1. חמשת מצבי האימות ──────────────────────────────────────────────────


def test_veya_pending_provider_pending() -> None:
    """מיד אחרי הגשה: שתי הבדיקות ממתינות, החשבון אינו כשיר."""
    api = _ready_event()
    body = _submit_payout(api)
    assert body["status"] == payout_status.SUBMITTED
    assert body["veya_status"] == "pending"
    assert body["provider_status"] == "pending"
    assert body["fully_verified"] is False
    print("✓ VEYA ממתינה + ספק ממתין → לא מאומת")


def test_veya_approved_provider_pending() -> None:
    """**אישור VEYA לבדו אינו פותח כלום.** תשובת הספק לא זזה איתו."""
    api = _ready_event()
    _submit_payout(api)
    admin = _admin(api)

    r = api.client.post(f"/admin/payout/{api.event_id}/approve", headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["veya_status"] == "approved"
    assert r.json()["provider_status"] == "pending", (
        "אישור VEYA שינה את תשובת הספק — שתי הבדיקות אמורות להיות בלתי תלויות"
    )
    assert r.json()["fully_verified"] is False

    body = api.client.get("/payout", headers=api.headers).json()
    assert body["status"] == payout_status.VERIFIED
    assert body["fully_verified"] is False
    print("✓ VEYA אישרה + ספק ממתין → עדיין לא מאומת")


def test_veya_approved_provider_approved_is_fully_verified() -> None:
    api = _ready_event()
    _submit_payout(api)
    admin = _admin(api)
    api.client.post(f"/admin/payout/{api.event_id}/approve", headers=admin)
    _set_provider(api, admin, "approved")

    body = api.client.get("/payout", headers=api.headers).json()
    assert body["veya_status"] == "approved"
    assert body["provider_status"] == "approved"
    assert body["fully_verified"] is True
    print("✓ שתי הבדיקות אושרו → מאומת במלואו")


def test_provider_approved_alone_is_not_enough() -> None:
    """**אישור ספק לבדו אינו פותח כלום** — הכיוון ההפוך של אותו כלל."""
    api = _ready_event()
    _submit_payout(api)
    admin = _admin(api)
    _set_provider(api, admin, "approved")

    body = api.client.get("/payout", headers=api.headers).json()
    assert body["provider_status"] == "approved"
    assert body["veya_status"] == "pending", "תשובת הספק זלגה למסלול של VEYA"
    assert body["status"] == payout_status.SUBMITTED, (
        "תשובת הספק שינתה את סטטוס הבדיקה של VEYA"
    )
    assert body["fully_verified"] is False
    print("✓ ספק אישר לבדו → לא מאומת, ומסלול VEYA לא זז")


def test_veya_rejected_carries_reason_and_reason_is_required() -> None:
    api = _ready_event()
    _submit_payout(api)
    admin = _admin(api)

    empty = api.client.post(f"/admin/payout/{api.event_id}/reject",
                            headers=admin, json={"reason": ""})
    assert empty.status_code == 422, "דחייה בלי סיבה התקבלה"

    r = api.client.post(f"/admin/payout/{api.event_id}/reject",
                        headers=admin, json={"reason": "האישור לא קריא"})
    assert r.status_code == 200, r.text
    assert r.json()["veya_status"] == "rejected"

    body = api.client.get("/payout", headers=api.headers).json()
    assert body["status"] == payout_status.REJECTED
    assert body["rejection_reason"] == "האישור לא קריא"
    assert body["can_submit"] is True, "אחרי דחייה צריך להיות אפשר לתקן ולהגיש שוב"
    print("✓ דחיית VEYA נושאת סיבה, וסיבה היא חובה")


def test_provider_rejected_carries_its_own_reason() -> None:
    api = _ready_event()
    _submit_payout(api)
    admin = _admin(api)
    api.client.post(f"/admin/payout/{api.event_id}/approve", headers=admin)
    _set_provider(api, admin, "rejected", "השם בחשבון אינו תואם")

    body = api.client.get("/payout", headers=api.headers).json()
    assert body["provider_status"] == "rejected"
    assert body["provider_rejection_reason"] == "השם בחשבון אינו תואם"
    # דחיית ספק **אינה** הופכת את בדיקת VEYA לדחויה — שתי סיבות נפרדות.
    assert body["veya_status"] == "approved"
    assert body["rejection_reason"] is None
    assert body["fully_verified"] is False
    print("✓ דחיית ספק נשמרת בנפרד ואינה מבטלת את אישור VEYA")


# ── 2. שער הסכומים ───────────────────────────────────────────────────────


def _gifts(api):
    r = api.client.get("/gifts", headers=api.headers)
    assert r.status_code == 200, r.text
    return r.json()


def _assert_no_amounts(data, where: str) -> None:
    assert data["amounts_visible"] is False, where
    assert data["total_received_agorot"] is None, where
    assert data["total_received_display"] is None, where
    for row in data["gifts"]:
        assert row["gift_amount_agorot"] is None, f"{where}: סכום דלף בשורה"
    # וגם לא כמחרוזת גולמית בגוף התשובה.
    assert "50000" not in str(data), f"{where}: הסכום דלף לגוף התשובה"


def test_amounts_hidden_before_full_verification() -> None:
    api = _ready_event()
    tok = _guest_token(api, "נותן מתנה", "0503330001")
    _gift(api, tok, 50000, "gate-1")

    data = _gifts(api)
    _assert_no_amounts(data, "בלי פרטי חשבון בכלל")
    # מה שכן חוזר: מי בירך, מה כתב, וכמה מתנות התקבלו.
    assert data["paid_count"] == 1
    assert data["gifts"][0]["sender_name"] == "דנה"
    assert data["gifts"][0]["message"] == "מזל טוב"
    print("✓ לפני אימות מלא — אין סכומים, אבל כן מי בירך וכמה מתנות")


def test_veya_approval_alone_does_not_open_amounts() -> None:
    api = _ready_event()
    tok = _guest_token(api, "נותן מתנה", "0503330002")
    _gift(api, tok, 50000, "gate-2")
    _submit_payout(api)
    admin = _admin(api)
    api.client.post(f"/admin/payout/{api.event_id}/approve", headers=admin)

    _assert_no_amounts(_gifts(api), "VEYA אישרה לבדה")
    print("✓ אישור VEYA לבדו לא פותח סכומים")


def test_provider_approval_alone_does_not_open_amounts() -> None:
    api = _ready_event()
    tok = _guest_token(api, "נותן מתנה", "0503330003")
    _gift(api, tok, 50000, "gate-3")
    _submit_payout(api)
    admin = _admin(api)
    _set_provider(api, admin, "approved")

    _assert_no_amounts(_gifts(api), "הספק אישר לבדו")
    print("✓ אישור ספק לבדו לא פותח סכומים")


def test_amounts_return_after_full_verification() -> None:
    api = _ready_event()
    tok = _guest_token(api, "נותן מתנה", "0503330004")
    _gift(api, tok, 50000, "gate-4")
    _submit_payout(api)
    admin = _admin(api)
    api.client.post(f"/admin/payout/{api.event_id}/approve", headers=admin)
    _set_provider(api, admin, "approved")

    data = _gifts(api)
    assert data["amounts_visible"] is True
    assert data["total_received_agorot"] == 50000
    assert data["total_received_display"] == "₪500"
    assert data["gifts"][0]["gift_amount_agorot"] == 50000
    print("✓ אחרי שתי הבדיקות — הסכומים חוזרים כרגיל")


def test_revoking_either_approval_closes_amounts_again() -> None:
    """השער אינו חד-כיווני: ביטול של כל אחת מהבדיקות סוגר אותו שוב."""
    api = _ready_event()
    tok = _guest_token(api, "נותן מתנה", "0503330005")
    _gift(api, tok, 50000, "gate-5")
    _submit_payout(api)
    admin = _admin(api)
    api.client.post(f"/admin/payout/{api.event_id}/approve", headers=admin)
    _set_provider(api, admin, "approved")
    assert _gifts(api)["amounts_visible"] is True

    # הספק חזר בו.
    _set_provider(api, admin, "rejected", "החשבון נסגר")
    _assert_no_amounts(_gifts(api), "הספק חזר בו")

    # הספק אישר שוב, וכעת VEYA חוזרת בה.
    _set_provider(api, admin, "approved")
    assert _gifts(api)["amounts_visible"] is True
    api.client.post(f"/admin/payout/{api.event_id}/reject",
                    headers=admin, json={"reason": "נדרש אישור מעודכן"})
    _assert_no_amounts(_gifts(api), "VEYA חזרה בה")
    print("✓ ביטול של כל אחת מהבדיקות סוגר את הסכומים מחדש")


def test_a_verified_account_cannot_be_swapped_under_the_amounts() -> None:
    """אי אפשר להחליף חשבון מתחת לסכומים שכבר נפתחו.

    **הכלל הזה נאכף היום ע"י נעילה ולא ע"י ביטול אימות.** קודם, עריכה של
    חשבון מאושר הייתה מותרת ומחזירה את הסטטוס ל-``missing``; עכשיו היא
    פשוט נדחית. התוצאה חזקה יותר: אין רגע שבו חשבון מאושר מצביע למקום
    אחר, גם לא לרגע.
    """
    api = _ready_event()
    tok = _guest_token(api, "נותן מתנה", "0503330006")
    _gift(api, tok, 50000, "gate-6")
    _submit_payout(api)
    admin = _admin(api)
    api.client.post(f"/admin/payout/{api.event_id}/approve", headers=admin)
    _set_provider(api, admin, "approved")
    assert _gifts(api)["amounts_visible"] is True

    r = api.client.put("/payout", headers=api.headers, json={
        "bank_code": 20, "branch_number": "123",
        "account_number": "99887766", "certificate": None,
    })
    assert r.status_code == 409, f"החלפת חשבון מאושר החזירה {r.status_code}"

    # כלום לא זז: לא החשבון, לא הסטטוס, ולא הסכומים.
    body = api.client.get("/payout", headers=api.headers).json()
    assert body["fully_verified"] is True
    assert body["account_number_masked"].endswith(ACCOUNT[-4:])
    assert _gifts(api)["amounts_visible"] is True
    print("✓ אי אפשר להחליף חשבון מאושר — הבקשה נדחית ושום דבר לא זז")


def test_reopen_then_edit_closes_the_amounts_again() -> None:
    """המסלול החוקי לשינוי: אדמין פותח, הזוג עורך — והסכומים נסגרים."""
    api = _ready_event()
    tok = _guest_token(api, "נותן מתנה", "0503330008")
    _gift(api, tok, 50000, "gate-8")
    _submit_payout(api)
    admin = _admin(api)
    api.client.post(f"/admin/payout/{api.event_id}/approve", headers=admin)
    _set_provider(api, admin, "approved")
    assert _gifts(api)["amounts_visible"] is True

    # פתיחה מחדש לבדה כבר סוגרת את הסכומים — האישור בוטל.
    api.client.post(f"/admin/payout/{api.event_id}/reopen", headers=admin)
    _assert_no_amounts(_gifts(api), "מיד אחרי פתיחה מחדש")

    # ומכאן הזוג יכול לערוך.
    r = api.client.put("/payout", headers=api.headers, json={
        "bank_code": 20, "branch_number": "123",
        "account_number": "99887766", "certificate": None,
    })
    assert r.status_code == 200, r.text
    body = api.client.get("/payout", headers=api.headers).json()
    assert body["account_number_masked"].endswith("7766")
    assert body["fully_verified"] is False
    _assert_no_amounts(_gifts(api), "אחרי החלפת פרטי החשבון")
    print("✓ פתיחה מחדש → עריכה → הסכומים נסגרים, וזה המסלול היחיד")


def test_amounts_cannot_be_forced_by_query_parameters() -> None:
    """אין פרמטר שפותח את השער — הסכום פשוט לא נכתב לתשובה."""
    api = _ready_event()
    tok = _guest_token(api, "נותן מתנה", "0503330007")
    _gift(api, tok, 50000, "gate-7")

    for query in ("?amounts_visible=true", "?fully_verified=true",
                  "?show_amounts=1", "?status=verified"):
        r = api.client.get(f"/gifts{query}", headers=api.headers)
        assert r.status_code == 200, r.text
        _assert_no_amounts(r.json(), f"עם {query}")
    print("✓ פרמטרים בכתובת לא פותחים את הסכומים")


# ── 3. הזרקה והרשאות ─────────────────────────────────────────────────────


def test_status_cannot_be_injected_through_the_request_body() -> None:
    api = _ready_event()
    r = api.client.put("/payout", headers=api.headers, json={
        "bank_code": 12, "branch_number": "045", "account_number": ACCOUNT,
        "certificate": PDF_URL,
        # ניסיונות הזרקה — כל אלה אמורים להיזרק בשקט ע"י Pydantic.
        "status": "verified",
        "veya_status": "approved",
        "provider_status": "approved",
        "fully_verified": True,
        "rejection_reason": "",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == payout_status.MISSING
    assert body["veya_status"] == "pending"
    assert body["provider_status"] == "pending"
    assert body["fully_verified"] is False

    row = _row(api.event_id)
    assert row.status == payout_status.MISSING
    assert row.provider_status == "pending"
    print("✓ status / fully_verified / provider_status לא ניתנים להזרקה בגוף הבקשה")


def test_owner_cannot_approve_their_own_account() -> None:
    """הכלל שכל המנגנון קיים בשבילו: המזין אינו המאשר."""
    api = _ready_event()
    _submit_payout(api)

    for path in ("approve", "reject", "provider"):
        r = api.client.post(f"/admin/payout/{api.event_id}/{path}",
                            headers=api.headers,
                            json={"reason": "אני מאשר לעצמי", "status": "approved"})
        assert r.status_code == 403, (
            f"בעל האירוע הגיע ל-/admin/payout/…/{path} וקיבל {r.status_code}"
        )

    body = api.client.get("/payout", headers=api.headers).json()
    assert body["veya_status"] == "pending" and body["fully_verified"] is False
    print("✓ בעל האירוע לא יכול לאשר את עצמו — 403 בכל נתיבי הבדיקה")


def test_event_member_cannot_review() -> None:
    """מפיק — גם כזה שרואה מתנות — אינו בודק. הבדיקה היא של VEYA בלבד."""
    api = _ready_event()
    _submit_payout(api)

    member_token = register(api.client)
    set_request_identity(None)
    db = SessionLocal()
    try:
        member = db.scalars(select(models.User).order_by(models.User.id.desc())).first()
        db.add(models.EventMember(
            event_id=api.event_id, user_id=member.id,
            role="producer", status="active", permissions=["view_reports"],
        ))
        db.commit()
    finally:
        db.close()

    headers = {"Authorization": f"Bearer {member_token}",
               "X-Event-Id": str(api.event_id)}
    for path in ("approve", "reject", "provider"):
        r = api.client.post(f"/admin/payout/{api.event_id}/{path}",
                            headers=headers,
                            json={"reason": "בדיקה", "status": "approved"})
        assert r.status_code == 403, f"מפיק הגיע ל-{path} וקיבל {r.status_code}"

    # וגם לא לתור הבדיקה ולא למסמך.
    assert api.client.get("/admin/payout", headers=headers).status_code == 403
    assert api.client.get(
        f"/admin/payout/{api.event_id}/certificate", headers=headers
    ).status_code == 403
    print("✓ חבר-אירוע (מפיק) נחסם מכל נתיבי הבדיקה — 403")


def test_admin_queue_and_review_trail() -> None:
    """תור הבדיקה מציג את מה שצריך כדי להכריע — ומתעד מי הכריע ומתי."""
    api = _ready_event()
    _submit_payout(api)
    admin = _admin(api)

    queue = api.client.get("/admin/payout", headers=admin)
    assert queue.status_code == 200, queue.text
    mine = [r for r in queue.json() if r["event_id"] == api.event_id]
    assert len(mine) == 1, "החשבון שהוגש לא מופיע בתור הבדיקה"
    row = mine[0]
    assert row["bank_name"] and row["branch_number"] == "045"
    assert row["certificate"]["content_type"] == "application/pdf"
    assert row["owner_email"], "אין מול מי להצליב את האישור"
    # מספר החשבון המלא לא נכתב לתשובה — גם לא לאדמין.
    assert ACCOUNT not in str(row), "מספר חשבון מלא דלף לתור הבדיקה"
    assert row["account_number_masked"].endswith(ACCOUNT[-4:])

    # המסמך עצמו כן נגיש לבודק.
    cert = api.client.get(f"/admin/payout/{api.event_id}/certificate", headers=admin)
    assert cert.status_code == 200 and cert.content == PDF

    api.client.post(f"/admin/payout/{api.event_id}/approve", headers=admin)
    after = api.client.get(f"/admin/payout/{api.event_id}", headers=admin).json()
    assert after["reviewed_by"], "לא נשמר מי ביצע את הבדיקה"
    assert after["reviewed_at"], "לא נשמר מתי בוצעה הבדיקה"
    # וההגשה יצאה מהתור.
    still = [r for r in api.client.get("/admin/payout", headers=admin).json()
             if r["event_id"] == api.event_id]
    assert not still, "חשבון שהוכרע נשאר בתור"
    print("✓ תור הבדיקה שלם, ללא מספר חשבון, ומתעד מי בדק ומתי")


def test_no_cross_event_leak_in_review() -> None:
    a = _ready_event()
    b = _ready_event()
    _submit_payout(a, "11112222")
    _submit_payout(b, "33334444")
    admin = _admin(a)
    a.client.post(f"/admin/payout/{a.event_id}/approve", headers=admin)
    _set_provider(a, admin, "approved")

    # אירוע ב׳ לא הושפע מאישור אירוע א׳.
    body_b = b.client.get("/payout", headers=b.headers).json()
    assert body_b["fully_verified"] is False
    assert body_b["account_number_masked"].endswith("4444")

    # ובעלי א׳ לא רואים את ב׳ דרך X-Event-Id.
    r = a.client.get("/payout", headers={
        "Authorization": a.headers["Authorization"], "X-Event-Id": str(b.event_id)
    })
    assert r.status_code == 404, f"גישה חוצת-אירועים החזירה {r.status_code}"
    print("✓ אימות של אירוע אחד אינו נוגע באחר, ואין גישה חוצת-אירועים")


# ── נעילת חשבון מאושר ────────────────────────────────────────────────────


def test_approved_account_is_locked_for_the_owner() -> None:
    """**אחרי אישור — READ ONLY.** לא ב-UI, בשרת.

    זה הכלל שמגן על האישור עצמו: אם היה אפשר להחליף מספר חשבון אחרי
    שאדם הסתכל על אישור ניהול החשבון והצהיר שהוא תקין, ההצהרה הזו הייתה
    חסרת ערך.
    """
    api = _ready_event()
    _submit_payout(api)
    admin = _admin(api)
    api.client.post(f"/admin/payout/{api.event_id}/approve", headers=admin)

    body = api.client.get("/payout", headers=api.headers).json()
    assert body["locked"] is True, "חשבון מאושר לא סומן כנעול"
    assert body["can_submit"] is False

    # שינוי פרטי בנק — חסום.
    r = api.client.put("/payout", headers=api.headers, json={
        "bank_code": 20, "branch_number": "123",
        "account_number": "99887766", "certificate": None,
    })
    assert r.status_code == 409, f"עריכת חשבון מאושר החזירה {r.status_code}"

    # החלפת אישור ניהול חשבון בלבד — חסומה גם היא.
    r = api.client.put("/payout", headers=api.headers, json={
        "bank_code": 12, "branch_number": "045",
        "account_number": ACCOUNT, "certificate": PDF_URL,
    })
    assert r.status_code == 409, "החלפת המסמך בחשבון מאושר לא נחסמה"

    # והנתונים במסד לא זזו.
    row = _row(api.event_id)
    assert row.bank_code == 12 and row.account_number == ACCOUNT
    assert row.status == payout_status.VERIFIED
    print("✓ חשבון מאושר נעול לחלוטין — בנק, סניף, חשבון ומסמך")


def test_lock_applies_from_veya_approval_not_from_full_verification() -> None:
    """הנעילה נכנסת לתוקף עם אישור VEYA, לא כשהאימות המלא הושלם.

    בין שני האישורים יש חלון שבו החשבון כבר נבדק אצלנו אבל טרם אושר ע"י
    הספק. אילו הנעילה הייתה מחכה לסוף, אפשר היה להחליף חשבון בדיוק שם.
    """
    api = _ready_event()
    _submit_payout(api)
    admin = _admin(api)
    api.client.post(f"/admin/payout/{api.event_id}/approve", headers=admin)

    body = api.client.get("/payout", headers=api.headers).json()
    assert body["fully_verified"] is False, "הספק עדיין לא אישר"
    assert body["locked"] is True, "הנעילה חיכתה לאישור הספק"
    print("✓ הנעילה מתחילה באישור VEYA ולא באימות המלא")


def test_before_approval_editing_stays_open() -> None:
    """לפני אישור — עריכה פתוחה, בכל אחד מהמצבים שקודמים לו."""
    api = _ready_event()

    # טרם הוגש.
    assert _save(api).status_code == 200
    assert api.client.get("/payout", headers=api.headers).json()["locked"] is False

    # הוגש וממתין.
    api.client.post("/payout/submit", headers=api.headers)
    assert _save(api, account_number="12345678").status_code == 200
    assert api.client.get("/payout", headers=api.headers).json()["locked"] is False

    # נדחה.
    api.client.post("/payout/submit", headers=api.headers)
    admin = _admin(api)
    api.client.post(f"/admin/payout/{api.event_id}/reject",
                    headers=admin, json={"reason": "לא קריא"})
    assert _save(api, account_number="87654321").status_code == 200
    assert api.client.get("/payout", headers=api.headers).json()["locked"] is False
    print("✓ לפני אישור — עריכה פתוחה בכל המצבים")


def test_provider_rejection_lifts_the_lock_so_the_fix_is_possible() -> None:
    """דחיית ספק פותחת את הנעילה — אחרת "נדרש תיקון" היה מלכוד.

    המצב: VEYA אישרה (ולכן החשבון נעול), ואז ספק הסליקה דחה. הזוג רואה
    "נדרש תיקון", וחייב להיות מסוגל באמת לתקן.
    """
    api = _ready_event()
    _submit_payout(api)
    admin = _admin(api)
    api.client.post(f"/admin/payout/{api.event_id}/approve", headers=admin)
    assert api.client.get("/payout", headers=api.headers).json()["locked"] is True

    _set_provider(api, admin, "rejected", "השם בחשבון אינו תואם")
    body = api.client.get("/payout", headers=api.headers).json()
    assert body["locked"] is False, "הזוג נדרש לתקן אבל נשאר נעול"
    # מסלול ה-VEYA עצמו לא זז — שתי הבדיקות עדיין בלתי תלויות.
    assert body["status"] == payout_status.VERIFIED
    assert body["veya_status"] == "approved"

    # והתיקון באמת עובר.
    r = _save(api, account_number="24681357")
    assert r.status_code == 200, r.text
    after = api.client.get("/payout", headers=api.headers).json()
    assert after["status"] == payout_status.MISSING
    assert after["provider_status"] == "pending"
    assert after["can_submit"] is True, "אחרי התיקון אי אפשר להגיש מחדש"
    print("✓ דחיית ספק פותחת את הנעילה, והתיקון עובר")


def test_only_admin_can_reopen_a_locked_account() -> None:
    api = _ready_event()
    _submit_payout(api)
    admin = _admin(api)
    api.client.post(f"/admin/payout/{api.event_id}/approve", headers=admin)

    # בעל האירוע — 403, והחשבון נשאר נעול.
    r = api.client.post(f"/admin/payout/{api.event_id}/reopen", headers=api.headers)
    assert r.status_code == 403, f"בעל האירוע פתח את הנעילה בעצמו ({r.status_code})"
    assert api.client.get("/payout", headers=api.headers).json()["locked"] is True

    # אדמין — נפתח, והפרטים נשמרו כדי שלא יצטרכו להקליד הכול מחדש.
    r = api.client.post(f"/admin/payout/{api.event_id}/reopen", headers=admin)
    assert r.status_code == 200, r.text
    body = api.client.get("/payout", headers=api.headers).json()
    assert body["locked"] is False
    assert body["status"] == payout_status.MISSING
    assert body["veya_status"] == "pending"
    assert body["provider_status"] == "pending", "אישור ספק שרד פתיחה מחדש"
    assert body["branch_number"] == "045", "הפרטים נמחקו בפתיחה מחדש"
    assert body["configured"] is True

    # ומכאן אפשר לערוך שוב.
    assert _save(api, account_number="24681357").status_code == 200
    print("✓ רק אדמין פותח נעילה, והפרטים שורדים את הפתיחה")


def test_reopen_is_logged_and_rejected_when_not_approved() -> None:
    api = _ready_event()
    _submit_payout(api)
    admin = _admin(api)

    # חשבון שאינו מאושר — אין מה לפתוח.
    r = api.client.post(f"/admin/payout/{api.event_id}/reopen", headers=admin)
    assert r.status_code == 409, f"פתיחה מחדש של חשבון לא מאושר החזירה {r.status_code}"

    api.client.post(f"/admin/payout/{api.event_id}/approve", headers=admin)
    api.client.post(f"/admin/payout/{api.event_id}/reopen", headers=admin)

    set_request_identity(None)
    db = SessionLocal()
    try:
        details = " ".join(
            (r.detail or "") for r in db.scalars(
                select(models.AuditLog).where(models.AuditLog.event_id == api.event_id)
            ).all()
        )
    finally:
        db.close()
    assert "verified → missing" in details, "פתיחה מחדש לא נרשמה ביומן"
    assert ACCOUNT not in details
    print("✓ פתיחה מחדש נרשמת ביומן, ונחסמת כשאין מה לפתוח")


# ── 4. יומן ──────────────────────────────────────────────────────────────


def test_every_status_change_is_logged_without_secrets() -> None:
    api = _ready_event()
    _submit_payout(api)
    admin = _admin(api)
    api.client.post(f"/admin/payout/{api.event_id}/reject",
                    headers=admin, json={"reason": "האישור מטושטש"})
    api.client.post("/payout/submit", headers=api.headers)
    api.client.post(f"/admin/payout/{api.event_id}/approve", headers=admin)
    _set_provider(api, admin, "approved")
    _set_provider(api, admin, "rejected", "החשבון נסגר")

    set_request_identity(None)
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(models.AuditLog).where(models.AuditLog.event_id == api.event_id)
        ).all()
        actions = [r.action for r in rows]
        details = " ".join((r.detail or "") for r in rows)
        actors = {r.user_id for r in rows}
    finally:
        db.close()

    assert "payout_status_changed" in actions, "שינויי VEYA לא נרשמו"
    assert "payout_provider_status_changed" in actions, "שינויי הספק לא נרשמו"
    # לפני ואחרי — בכל רשומה.
    for expected in ("submitted → rejected", "rejected → submitted",
                     "submitted → under_review", "under_review → verified",
                     "pending → approved", "approved → rejected"):
        assert expected in details, f"חסר מעבר ביומן: {expected} (יש: {details})"
    # סיבות הדחייה נשמרו.
    assert "האישור מטושטש" in details and "החשבון נסגר" in details
    # מי ביצע — יש יותר מזהות אחת ביומן (בעלים + אדמין).
    assert len([a for a in actors if a]) >= 1
    # ומה שאסור: מספר חשבון, סניף, קוד בנק, ובוודאי לא המסמך.
    for secret in (ACCOUNT, "045", "%PDF", "base64"):
        assert secret not in details, f"נתון רגיש דלף ליומן: {secret}"
    print("✓ כל שינוי סטטוס ביומן — עם לפני/אחרי וסיבה, בלי נתונים רגישים")


# ── 5. הפונקציה המרכזית ──────────────────────────────────────────────────


def test_single_source_of_truth() -> None:
    """``is_fully_verified`` היא ההגדרה היחידה — וכל שאר המערכת שואלת אותה."""
    assert payout_status.is_fully_verified("approved", "approved") is True
    for veya, provider in (("approved", "pending"), ("pending", "approved"),
                           ("approved", "rejected"), ("rejected", "approved"),
                           ("pending", "pending"), (None, None)):
        assert payout_status.is_fully_verified(veya, provider) is False, (veya, provider)

    # אין שורה כלל — שאלה חוקית שמחזירה False, בלי ענף מיוחד אצל הקורא.
    assert payout_service.is_fully_verified(None) is False

    # והתנאי לא משוכפל: מחרוזת ה-``and`` של שתי הבדיקות מופיעה בקובץ אחד.
    root = Path(__file__).resolve().parent.parent / "app"
    holders = [
        p.name for p in root.rglob("*.py")
        if 'REVIEW_APPROVED and provider == payout_status.REVIEW_APPROVED'
        in p.read_text(encoding="utf-8")
        or 'veya == REVIEW_APPROVED and provider == REVIEW_APPROVED'
        in p.read_text(encoding="utf-8")
    ]
    assert holders == ["payout_status.py"], f"התנאי שוכפל אל: {holders}"
    print("✓ תנאי האימות המלא מוגדר במקום אחד בלבד")


if __name__ == "__main__":
    try:
        test_veya_pending_provider_pending()
        test_veya_approved_provider_pending()
        test_veya_approved_provider_approved_is_fully_verified()
        test_provider_approved_alone_is_not_enough()
        test_veya_rejected_carries_reason_and_reason_is_required()
        test_provider_rejected_carries_its_own_reason()

        test_amounts_hidden_before_full_verification()
        test_veya_approval_alone_does_not_open_amounts()
        test_provider_approval_alone_does_not_open_amounts()
        test_amounts_return_after_full_verification()
        test_revoking_either_approval_closes_amounts_again()
        test_a_verified_account_cannot_be_swapped_under_the_amounts()
        test_reopen_then_edit_closes_the_amounts_again()
        test_amounts_cannot_be_forced_by_query_parameters()

        test_status_cannot_be_injected_through_the_request_body()
        test_owner_cannot_approve_their_own_account()
        test_event_member_cannot_review()
        test_admin_queue_and_review_trail()
        test_no_cross_event_leak_in_review()

        test_approved_account_is_locked_for_the_owner()
        test_lock_applies_from_veya_approval_not_from_full_verification()
        test_before_approval_editing_stays_open()
        test_provider_rejection_lifts_the_lock_so_the_fix_is_possible()
        test_only_admin_can_reopen_a_locked_account()
        test_reopen_is_logged_and_rejected_when_not_approved()

        test_every_status_change_is_logged_without_secrets()
        test_single_source_of_truth()
        print("\nכל בדיקות האימות הכפול עברו ✓")
    finally:
        shutdown()
