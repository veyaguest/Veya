"""בדיקות לתשתית "פרטי קבלת מתנות" — סטטוסים, הגשה, יומן ושכבת הספק.

הבדיקות על הטופס עצמו (ולידציה, רשימת הבנקים, הרשאות, אחסון האישור)
נמצאות ב-``test_payout_account.py``. הקובץ הזה מכסה את השכבה שנוספה מעליו:

1. **מכונת המצבים** — missing → submitted → under_review → verified/rejected,
   וכל מה שאסור.
2. **``verified`` אינו נגיש לבעלי האירוע** — אין נתיב API שמוביל אליו.
3. **עריכת פרטים מבטלת אימות** — חשבון שאומת והוחלף אינו מאומת.
4. **יומן** — כל שינוי נרשם, ובלי מספר החשבון.
5. **שכבת הספק** — קיימת, אינרטית, ולא שולחת דבר.

הרצה: ``venv/bin/python tests/test_payout_infrastructure.py``
"""
from __future__ import annotations

import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app import models, payout_provider, payout_service, payout_status  # noqa: E402
from app.database import SessionLocal, set_request_identity  # noqa: E402
from tests.e2e_seating import bootstrap, shutdown  # noqa: E402

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
PDF_URL = "data:application/pdf;base64," + base64.b64encode(PDF).decode()


def _body(**over):
    b = {"bank_code": 12, "branch_number": "045",
         "account_number": "123456", "certificate": PDF_URL}
    b.update(over)
    return b


def _save(api, **over):
    return api.client.put("/payout", headers=api.headers, json=_body(**over))


def _get(api):
    return api.client.get("/payout", headers=api.headers).json()


def _review(api, target, reason=""):
    """מעבר מצד הבודק — דרך השירות, כי אין לו נתיב API במכוון."""
    set_request_identity(None)
    db = SessionLocal()
    try:
        payout_service.set_status(db, api.event_id, target, reason=reason)
        db.commit()
    finally:
        db.close()


# ── 1. מכונת המצבים ──────────────────────────────────────────────────────

def test_status_machine_allows_the_documented_path() -> None:
    s = payout_status
    for a, b in [(s.MISSING, s.SUBMITTED), (s.SUBMITTED, s.UNDER_REVIEW),
                 (s.UNDER_REVIEW, s.VERIFIED), (s.UNDER_REVIEW, s.REJECTED),
                 (s.REJECTED, s.SUBMITTED), (s.VERIFIED, s.MISSING)]:
        assert s.can_transition(a, b), f"מעבר חוקי נחסם: {a} → {b}"
    print("✓ המסלול המתועד מותר במלואו")


def test_status_machine_blocks_shortcuts() -> None:
    s = payout_status
    forbidden = [
        (s.MISSING, s.VERIFIED),        # אי אפשר לאמת מה שלא הוגש
        (s.MISSING, s.UNDER_REVIEW),
        (s.SUBMITTED, s.VERIFIED),      # אימות עובר תמיד דרך בדיקה מפורשת
        (s.REJECTED, s.VERIFIED),
        (s.VERIFIED, s.UNDER_REVIEW),
    ]
    for a, b in forbidden:
        assert not s.can_transition(a, b), f"קיצור דרך אסור התאפשר: {a} → {b}"
        try:
            s.assert_transition(a, b)
            raise AssertionError(f"assert_transition לא זרק על {a} → {b}")
        except s.InvalidStatusTransition:
            pass
    try:
        s.assert_transition(s.MISSING, "banana")
        raise AssertionError("סטטוס מומצא התקבל")
    except s.InvalidStatusTransition:
        pass
    print("✓ קיצורי דרך וסטטוסים מומצאים נחסמים")


# ── 2. מסלול מקצה לקצה דרך ה-API ─────────────────────────────────────────

def test_new_event_starts_missing() -> None:
    api, _ = bootstrap()
    body = _get(api)
    assert body["status"] == payout_status.MISSING and body["configured"] is False, body
    assert body["can_submit"] is False
    print("✓ אירוע חדש מתחיל ב-missing ולא ניתן להגשה")


def test_save_does_not_submit() -> None:
    """שמירה אינה הגשה — אחרת כל שמירת ביניים הייתה פותחת בדיקה."""
    api, _ = bootstrap()
    body = _save(api).json()
    assert body["status"] == payout_status.MISSING, body
    assert body["can_submit"] is True, "יש פרטים ואישור — אמור להיות ניתן להגשה"
    print("✓ שמירה משאירה missing, ומסמנת שאפשר להגיש")


def test_submit_moves_to_submitted() -> None:
    api, _ = bootstrap()
    _save(api)
    r = api.client.post("/payout/submit", headers=api.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == payout_status.SUBMITTED, body
    assert body["submitted_at"] and body["can_submit"] is False
    print("✓ הגשה מעבירה ל-submitted ומתעדת מועד")


def test_cannot_submit_twice_or_without_details() -> None:
    api, _ = bootstrap()
    assert api.client.post("/payout/submit", headers=api.headers).status_code == 409
    _save(api)
    assert api.client.post("/payout/submit", headers=api.headers).status_code == 200
    r = api.client.post("/payout/submit", headers=api.headers)
    assert r.status_code == 409 and "כבר" in r.json()["detail"], r.json()
    print("✓ אי אפשר להגיש פעמיים או בלי פרטים")


def test_full_review_path_to_verified() -> None:
    api, _ = bootstrap()
    _save(api)
    api.client.post("/payout/submit", headers=api.headers)
    _review(api, payout_status.UNDER_REVIEW)
    assert _get(api)["status"] == payout_status.UNDER_REVIEW
    _review(api, payout_status.VERIFIED)
    body = _get(api)
    assert body["status"] == payout_status.VERIFIED and body["can_submit"] is False
    print("✓ המסלול המלא עד verified עובד")


def test_rejection_carries_reason_and_allows_resubmit() -> None:
    api, _ = bootstrap()
    _save(api)
    api.client.post("/payout/submit", headers=api.headers)
    _review(api, payout_status.UNDER_REVIEW)
    _review(api, payout_status.REJECTED, reason="אישור ניהול החשבון לא קריא")
    body = _get(api)
    assert body["status"] == payout_status.REJECTED
    assert body["rejection_reason"] == "אישור ניהול החשבון לא קריא", body
    assert body["can_submit"] is True, "אחרי דחייה אמור להיות אפשר להגיש שוב"
    assert api.client.post("/payout/submit", headers=api.headers).status_code == 200
    print("✓ דחייה נושאת סיבה ומאפשרת הגשה חוזרת")


# ── 3. הכלל שמגן על הכסף ─────────────────────────────────────────────────

def test_owner_has_no_api_path_to_verified() -> None:
    """אין נתיב שבו בעלי האירוע מאשרים את עצמם."""
    api, _ = bootstrap()
    _save(api)
    for path in ("/payout/verify", "/payout/status", "/payout/approve"):
        assert api.client.post(path, headers=api.headers).status_code in (404, 405), path
    # גם ניסיון להזריק סטטוס דרך גוף השמירה לא משנה דבר.
    api.client.put("/payout", headers=api.headers,
                   json=_body() | {"status": "verified"})
    assert _get(api)["status"] == payout_status.MISSING
    print("✓ אין דרך לבעלי האירוע להגיע ל-verified")


def test_editing_details_cancels_verification() -> None:
    api, _ = bootstrap()
    _save(api)
    api.client.post("/payout/submit", headers=api.headers)
    _review(api, payout_status.UNDER_REVIEW)
    _review(api, payout_status.VERIFIED)
    assert _get(api)["status"] == payout_status.VERIFIED

    # מחליפים את מספר החשבון — האימות חייב להתבטל.
    _save(api, account_number="99887766", certificate=None)
    body = _get(api)
    assert body["status"] == payout_status.MISSING, \
        "חשבון שאומת והוחלף נשאר מאומת — פרצה"
    assert body["can_submit"] is True
    print("✓ שינוי זהות החשבון מבטל אימות קיים")


def test_resaving_same_details_keeps_status() -> None:
    """שמירה חוזרת של אותם פרטים בדיוק לא מאפסת בדיקה שבתהליך."""
    api, _ = bootstrap()
    _save(api)
    api.client.post("/payout/submit", headers=api.headers)
    _review(api, payout_status.UNDER_REVIEW)
    _save(api, certificate=None)          # אותם ערכים בדיוק
    assert _get(api)["status"] == payout_status.UNDER_REVIEW
    print("✓ שמירה ללא שינוי אינה מאפסת את הבדיקה")


def test_replacing_certificate_keeps_status() -> None:
    api, _ = bootstrap()
    _save(api)
    api.client.post("/payout/submit", headers=api.headers)
    png = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 40).decode()
    _save(api, certificate=png)
    assert _get(api)["status"] == payout_status.SUBMITTED, \
        "החלפת האישור בלבד לא אמורה לאפס את ההגשה"
    print("✓ החלפת אישור בלבד שומרת על הסטטוס")


# ── 4. יומן ──────────────────────────────────────────────────────────────

def test_changes_are_audited_without_account_number() -> None:
    api, _ = bootstrap()
    _save(api, account_number="55446677")
    api.client.post("/payout/submit", headers=api.headers)
    _review(api, payout_status.UNDER_REVIEW)

    set_request_identity(None)
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(models.AuditLog).where(models.AuditLog.event_id == api.event_id)
        ).all()
    finally:
        db.close()
    actions = [r.action for r in rows]
    for expected in ("payout_details_saved", "payout_certificate_uploaded",
                     "payout_status_changed"):
        assert expected in actions, f"חסרה רשומת יומן: {expected} (יש: {actions})"
    blob = " ".join((r.detail or "") for r in rows)
    for secret in ("55446677", "123456", "045"):
        assert secret not in blob, f"נתון בנקאי דלף ליומן: {secret}"
    print("✓ כל שינוי נרשם ביומן — בלי מספר חשבון, סניף או קוד בנק")


# ── 5. שכבת הספק ─────────────────────────────────────────────────────────

def test_provider_layer_is_present_and_inert() -> None:
    assert payout_provider.DEFAULT_PROVIDER == "manual"
    prov = payout_provider.get_provider()
    reg = prov.register_recipient(
        event_id=1, bank_code=12, branch_number="045",
        account_number="123456", holder_name="בדיקה",
    )
    # ידני = אין גורם חיצוני: אין מזהה, והסטטוס "ממתין לבדיקה".
    assert reg.provider_account_id == ""
    assert reg.status == payout_provider.PROVIDER_PENDING
    assert payout_provider.PROVIDER_TO_PAYOUT_STATUS[reg.status] == payout_status.UNDER_REVIEW
    print("✓ שכבת הספק קיימת, ברירת המחדל ידנית ואינה שולחת דבר")


def test_unknown_provider_fails_loudly() -> None:
    try:
        payout_provider.get_provider("stripe")
        raise AssertionError("ספק לא מוכר התקבל בשקט")
    except ValueError:
        pass
    print("✓ ספק לא מוכר נופל בקול ולא חוזר בשקט לברירת מחדל")


def test_provider_fields_exist_but_unused() -> None:
    """השדות קיימים בטבלה, ואף קוד לא כותב אליהם היום."""
    cols = {c.name for c in models.PayoutAccount.__table__.columns}
    assert {"provider", "provider_account_id"} <= cols

    api, _ = bootstrap()
    _save(api)
    api.client.post("/payout/submit", headers=api.headers)
    set_request_identity(None)
    db = SessionLocal()
    try:
        row = db.scalars(select(models.PayoutAccount)
                         .where(models.PayoutAccount.event_id == api.event_id)).first()
        assert row.provider is None and row.provider_account_id is None, \
            "מישהו כותב לשדות הספק — הם אמורים להישאר ריקים עד חיבור ספק אמיתי"
    finally:
        db.close()

    # והם גם לא דולפים ל-API של בעלי האירוע.
    raw = api.client.get("/payout", headers=api.headers).text
    assert "provider" not in raw, "שדות הספק דלפו לתשובת ה-API"
    print("✓ שדות הספק קיימים, ריקים, ולא נחשפים ב-API")


# ── 6. בידוד ─────────────────────────────────────────────────────────────

def test_status_is_isolated_between_events() -> None:
    a, _ = bootstrap()
    _save(a)
    a.client.post("/payout/submit", headers=a.headers)
    _review(a, payout_status.UNDER_REVIEW)
    _review(a, payout_status.VERIFIED)

    b, _ = bootstrap()
    body = _get(b)
    assert body["status"] == payout_status.MISSING and body["configured"] is False, body
    assert b.client.post("/payout/submit", headers=b.headers).status_code == 409
    print("✓ סטטוס האימות מבודד לחלוטין בין אירועים")


if __name__ == "__main__":
    try:
        test_status_machine_allows_the_documented_path()
        test_status_machine_blocks_shortcuts()
        test_new_event_starts_missing()
        test_save_does_not_submit()
        test_submit_moves_to_submitted()
        test_cannot_submit_twice_or_without_details()
        test_full_review_path_to_verified()
        test_rejection_carries_reason_and_allows_resubmit()
        test_owner_has_no_api_path_to_verified()
        test_editing_details_cancels_verification()
        test_resaving_same_details_keeps_status()
        test_replacing_certificate_keeps_status()
        test_changes_are_audited_without_account_number()
        test_provider_layer_is_present_and_inert()
        test_unknown_provider_fails_loudly()
        test_provider_fields_exist_but_unused()
        test_status_is_isolated_between_events()
        print("\nכל בדיקות תשתית פרטי קבלת המתנות עברו ✓")
    finally:
        shutdown()
