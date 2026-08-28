"""בדיקות אבטחה ל-webhook של WhatsApp (routers/messaging.py::receive_webhook).

Security Audit שלב 6 גילה ש-``_verify_signature`` דילגה על אימות החתימה
כש-``WHATSAPP_APP_SECRET`` לא מוגדר/ריק — מה שהפך את ה-endpoint הציבורי
הזה (בלי טוקן, בלי guest_token) לפתוח לגמרי: כל אחד יכול היה לזייף
אישור/ביטול הגעה לכל מוזמן במערכת, בכל אירוע, רק לפי סיומת מספר הטלפון
שלו (``app_find_guest_by_phone`` לא מסונן לפי אירוע — ראו backend/rls/
01_helpers_and_grants.sql). שלב 6.1: התיקון עצמו הוא דחייה תמיד כשאין
סוד מוגדר, במקום "לדלג על האימות".

שלב 6.2: אותו Audit הראה ש-``json.loads(raw_body)`` ב-``receive_webhook``
ישב **מחוץ** ל-try/except — payload עם חתימה תקינה אבל גוף לא-JSON תקין
היה גורם ל-500 גולמי במקום דחייה מבוקרת. התיקון: json.loads עטוף ב-
try/except צר משלו שמחזיר 400 (בלי traceback), בלי לגעת בבדיקת החתימה
או בעיבוד העסקי הקיים.

נבנה על ``tests/e2e_seating.py`` (TestClient אמיתי מול SQLite זמני — כמו
כל בדיקות ה-E2E האחרות בתיקייה הזו). ``WHATSAPP_APP_SECRET`` נקרא מ-
``os.getenv`` בזמן הקריאה עצמה (לא בזמן import), כך שאפשר להחליף אותו
בבטחה בין בדיקות עם ``_secret()`` (context manager קטן למטה) בלי לגעת
ב-DB/client המשותפים.

הרצה עצמאית: ``venv/bin/python tests/test_webhook_signature.py``
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.e2e_seating import bootstrap, shutdown  # noqa: E402

WEBHOOK_URL = "/messaging/webhook"
_SECRET_ENV = "WHATSAPP_APP_SECRET"
_REAL_SECRET = "test-whatsapp-app-secret-not-real"


@contextmanager
def _secret(value):
    """מגדיר/מנקה את WHATSAPP_APP_SECRET לזמן הבדיקה בלבד, ומחזיר למצב הקודם.

    ``value=None`` מדמה "לא מוגדר בכלל" (``del`` מה-environ, לא רק מחרוזת
    ריקה) — שני המצבים השונים שהדרישה מבקשת לבדוק בנפרד.
    """
    had = _SECRET_ENV in os.environ
    prev = os.environ.get(_SECRET_ENV)
    try:
        if value is None:
            os.environ.pop(_SECRET_ENV, None)
        else:
            os.environ[_SECRET_ENV] = value
        yield
    finally:
        if had:
            os.environ[_SECRET_ENV] = prev
        else:
            os.environ.pop(_SECRET_ENV, None)


def _sign(body: bytes, secret: str = _REAL_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _rsvp_payload(from_phone: str, coming: bool = True) -> bytes:
    """גוף webhook תקין בפורמט Meta — תגובת כפתור RSVP (ראו messaging.rsvp_from_button)."""
    button_id = "rsvp_yes" if coming else "rsvp_no"
    data = {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": from_phone,
                        "interactive": {"button_reply": {"id": button_id}},
                    }]
                }
            }]
        }]
    }
    # separators=(",", ":") — בלי רווחים מיותרים, אותו בייטים בדיוק שנחתמים
    # ושנשלחים (אין מקום לאי-התאמה בין מה שחתמנו למה שהשרת קיבל).
    return json.dumps(data, separators=(",", ":")).encode("utf-8")


def _status_payload(provider_message_id: str, status: str = "delivered") -> bytes:
    data = {
        "entry": [{
            "changes": [{
                "value": {
                    "statuses": [{
                        "id": provider_message_id,
                        "status": status,
                    }]
                }
            }]
        }]
    }
    return json.dumps(data, separators=(",", ":")).encode("utf-8")


def _fresh_phone() -> str:
    """מספר ישראלי מקומי אקראי-קריפטוגרפית (לא ספרתיים קבועות).

    ``tests/e2e_seating.py`` שומר על client/DB זמני ומבודד ל-*הרצה אחת*
    (temp SQLite חדש) — אבל אם קובץ בדיקה אחר, שנאסף (import) לפני זה
    ב-collection של pytest, מייבא ``app.models``/``app.guest_journey`` וכו'
    לפני ש-``e2e_seating.make_client()`` מספיק לקבוע ``DATABASE_URL``,
    ``app.database`` נקשר מוקדם ל-DB שמוגדר ב-``.env`` (מקומי, לא Production
    — לא production impact) ועלול לכלול נתוני-בדיקה ישנים שנצברו לאורך זמן.
    מספר טלפון קבוע (כמו ``0521112233``) יכול אז להתנגש עם מוזמן ישן
    ולגרום ל-``_match_guest_by_phone`` (שממילא לא מסונן לפי אירוע — ראו
    routers/messaging.py) להתאים לשורה הלא-נכונה. אקראיות פותרת את זה בלי
    לגעת בארכיטקטורת הבדיקות המשותפת.
    """
    return "05" + f"{secrets.randbelow(10 ** 8):08d}"


def _intl(local_phone: str) -> str:
    """'0521234567' → '972521234567' — הפורמט שמגיע בפועל מ-Meta ב-webhook."""
    return "972" + local_phone[1:]


def _fresh_wamid() -> str:
    return f"wamid-sig-test-{secrets.token_hex(8)}"


def _post(api, body: bytes, signature: str | None):
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    return api.client.post(WEBHOOK_URL, content=body, headers=headers)


def _rsvp_status(api, guest_id: int) -> str:
    from app.database import SessionLocal
    from app import models

    db = SessionLocal()
    try:
        return db.get(models.Guest, guest_id).rsvp_status
    finally:
        db.close()


def test_missing_secret_env_var_rejects_webhook() -> None:
    """WHATSAPP_APP_SECRET לא מוגדר בכלל (לא בעברית — לא קיים ב-environ)
    → הבקשה נדחית, גם אם היא נושאת חתימה 'תקינה' לפי סוד כלשהו."""
    api, teardown = bootstrap()
    try:
        phone = _fresh_phone()
        guest = api.add_guest("מוזמן א", phone)
        body = _rsvp_payload(_intl(phone))
        with _secret(None):
            r = _post(api, body, _sign(body))
        assert r.status_code == 403, f"ציפינו ל-403, קיבלנו {r.status_code}: {r.text}"
        assert "secret" not in r.text.lower(), "תשובת השגיאה לא אמורה להזכיר את הסוד"
        assert _rsvp_status(api, guest["id"]) == "pending", "ה-RSVP לא אמור להשתנות כשאין סוד"
        print("✓ WHATSAPP_APP_SECRET לא מוגדר בכלל → webhook נדחה (403), RSVP לא השתנה")
    finally:
        teardown()


def test_empty_secret_env_var_rejects_webhook() -> None:
    """WHATSAPP_APP_SECRET מוגדר כמחרוזת ריקה — אותה דחייה בדיוק כמו 'לא מוגדר'."""
    api, teardown = bootstrap()
    try:
        phone = _fresh_phone()
        guest = api.add_guest("מוזמן ב", phone)
        body = _rsvp_payload(_intl(phone))
        with _secret(""):
            r = _post(api, body, _sign(body))
        assert r.status_code == 403, f"ציפינו ל-403, קיבלנו {r.status_code}: {r.text}"
        assert _rsvp_status(api, guest["id"]) == "pending"
        print("✓ WHATSAPP_APP_SECRET ריק → webhook נדחה (403), RSVP לא השתנה")
    finally:
        teardown()


def test_missing_signature_header_rejected_when_secret_configured() -> None:
    """יש סוד מוגדר, אבל הבקשה לא נושאת X-Hub-Signature-256 בכלל → נדחית."""
    api, teardown = bootstrap()
    try:
        phone = _fresh_phone()
        guest = api.add_guest("מוזמן ג", phone)
        body = _rsvp_payload(_intl(phone))
        with _secret(_REAL_SECRET):
            r = _post(api, body, None)
        assert r.status_code == 403, f"ציפינו ל-403, קיבלנו {r.status_code}: {r.text}"
        assert _rsvp_status(api, guest["id"]) == "pending"
        print("✓ סוד מוגדר, אין כותרת חתימה → webhook נדחה (403)")
    finally:
        teardown()


def test_wrong_signature_rejected() -> None:
    """חתימה קיימת אבל שגויה (סוד/גוף לא תואם) → נדחית, ה-RSVP לא זז."""
    api, teardown = bootstrap()
    try:
        phone = _fresh_phone()
        guest = api.add_guest("מוזמן ד", phone)
        body = _rsvp_payload(_intl(phone))
        with _secret(_REAL_SECRET):
            # חתום עם סוד אחר — בדיוק התרחיש של תוקף שמנחש/מזייף בלי לדעת
            # את הסוד האמיתי.
            r = _post(api, body, _sign(body, secret="wrong-secret-guess"))
        assert r.status_code == 403, f"ציפינו ל-403, קיבלנו {r.status_code}: {r.text}"
        assert _rsvp_status(api, guest["id"]) == "pending"

        # גם חתימה בפורמט לא תקין (בלי prefix "sha256=") נדחית, לא רק ערך שגוי.
        with _secret(_REAL_SECRET):
            r2 = _post(api, body, "not-a-real-signature-format")
        assert r2.status_code == 403, r2.text
        print("✓ חתימה שגויה / בפורמט לא תקין → webhook נדחה (403), RSVP לא השתנה")
    finally:
        teardown()


def test_valid_signature_accepted_and_updates_rsvp() -> None:
    """חתימה תקינה → הבקשה מתקבלת וממשיכה למסלול הקיים בדיוק כמו קודם
    (המסלול העסקי לא נשבר ע"י התיקון)."""
    api, teardown = bootstrap()
    try:
        phone = _fresh_phone()
        guest = api.add_guest("מוזמן ה", phone)
        body = _rsvp_payload(_intl(phone), coming=True)
        with _secret(_REAL_SECRET):
            r = _post(api, body, _sign(body))
        assert r.status_code == 200, f"ציפינו ל-200, קיבלנו {r.status_code}: {r.text}"
        assert _rsvp_status(api, guest["id"]) == "confirmed", "RSVP היה אמור להתעדכן ל-confirmed"
        print("✓ חתימה תקינה → webhook מתקבל (200) ומעדכן RSVP כרגיל")
    finally:
        teardown()


def test_valid_signature_status_update_still_works() -> None:
    """המסלול השני של אותו webhook (עדכוני מסירה, statuses[]) גם ממשיך
    לעבוד תחת חתימה תקינה — לא רק תגובות RSVP."""
    from app.database import SessionLocal
    from app import models

    api, teardown = bootstrap()
    try:
        guest = api.add_guest("מוזמן ו", _fresh_phone())
        wamid = _fresh_wamid()
        db = SessionLocal()
        try:
            msg = models.Message(
                event_id=api.event_id, guest_id=guest["id"], direction="outbound",
                kind="invitation", body="hi", status="sent", provider="meta",
                provider_message_id=wamid,
            )
            db.add(msg)
            db.commit()
        finally:
            db.close()

        body = _status_payload(wamid, "delivered")
        with _secret(_REAL_SECRET):
            r = _post(api, body, _sign(body))
        assert r.status_code == 200, f"ציפינו ל-200, קיבלנו {r.status_code}: {r.text}"

        db = SessionLocal()
        try:
            updated = db.get(models.Message, msg.id)
            assert updated.status == "delivered", f"status={updated.status}"
        finally:
            db.close()
        print("✓ חתימה תקינה → עדכון סטטוס מסירה (statuses[]) ממשיך לעבוד")
    finally:
        teardown()


def test_cross_tenant_guest_not_reachable_without_valid_signature() -> None:
    """הבעיה המקורית שאותרה ב-Audit: התאמת מוזמן היא לפי סיומת טלפון
    בלבד, בלי סינון לפי אירוע (app_find_guest_by_phone/ _match_guest_by_phone
    — נשארים כך במכוון, ראו הדרישה לא לגעת ב-RLS/בהתנהגות העסקית).
    הביטחון היחיד מפני ניצול חוצה-אירועים הוא שהבקשה חייבת להיות חתומה
    ע"י Meta בפועל — בודקים כאן בדיוק את זה: בלי חתימה תקינה, מוזמן של
    אירוע ב' לא מגיע בכלל, לא משנה איזה טלפון ננחש.
    """
    api_a, teardown_a = bootstrap()
    api_b, teardown_b = bootstrap()
    try:
        # שני מוזמנים בשני אירועים שונים (בעלים שונים), טלפון ייחודי כל אחד.
        phone_a, phone_b = _fresh_phone(), _fresh_phone()
        guest_a = api_a.add_guest("מוזמן אירוע א", phone_a)
        guest_b = api_b.add_guest("מוזמן אירוע ב", phone_b)

        # תוקף שמנסה לזייף עדכון למוזמן של אירוע ב', בלי לדעת את הסוד האמיתי.
        body = _rsvp_payload(_intl(phone_b))
        with _secret(_REAL_SECRET):
            r = _post(api_b, body, _sign(body, secret="attacker-guess"))
        assert r.status_code == 403, r.text
        assert _rsvp_status(api_b, guest_b["id"]) == "pending", "מוזמן אירוע ב' לא אמור להיפגע"
        assert _rsvp_status(api_a, guest_a["id"]) == "pending", "מוזמן אירוע א' ודאי לא אמור להיפגע"
        print("✓ בלי חתימה תקינה — אין עדכון RSVP חוצה-אירועים, גם עם טלפון מדויק")
    finally:
        teardown_a()
        teardown_b()


def test_no_500_across_all_signature_scenarios() -> None:
    """סבב מרוכז: אף אחד מהתרחישים (חסר/ריק/חסרה/שגויה/תקינה) לא מחזיר 500."""
    api, teardown = bootstrap()
    try:
        body = _rsvp_payload(_intl(_fresh_phone()))
        codes = []
        with _secret(None):
            codes.append(_post(api, body, _sign(body)).status_code)
        with _secret(""):
            codes.append(_post(api, body, _sign(body)).status_code)
        with _secret(_REAL_SECRET):
            codes.append(_post(api, body, None).status_code)
            codes.append(_post(api, body, _sign(body, secret="nope")).status_code)
            codes.append(_post(api, body, _sign(body)).status_code)
        assert all(c != 500 for c in codes), f"נמצא 500 בסבב התרחישים: {codes}"
        assert codes == [403, 403, 403, 403, 200], codes
        print(f"✓ כל תרחישי החתימה — בלי אף 500 (קודים: {codes})")
    finally:
        teardown()


# ── שלב 6.2: טיפול ב-JSON פגום (json.loads מחוץ ל-try/except שנחשף ב-6.1) ──
# תרחיש #1 של הדרישה ("JSON תקין + חתימה תקינה → ממשיך כרגיל") כבר מכוסה
# במלואו ע"י test_valid_signature_accepted_and_updates_rsvp +
# test_valid_signature_status_update_still_works למעלה — לא כפלתי אותו כאן.


def test_malformed_json_with_valid_signature_rejected_cleanly() -> None:
    """גוף שאינו JSON תקין בכלל, אבל **חתום כדין** — בדיוק התרחיש שנחשף
    ב-Audit (שלב 6.1 כבר תיקן: אם הגוף לא-JSON, החתימה עצמה עדיין מחושבת
    ומאומתת נכון על ה-bytes הגולמיים, בלי שום קשר לתוכן). מצפים ל-400
    מבוקר, בלי traceback ובלי לחשוף את פרטי שגיאת הפענוח."""
    api, teardown = bootstrap()
    try:
        garbage = b'{"entry": [ this is not valid json !!'
        with _secret(_REAL_SECRET):
            r = _post(api, garbage, _sign(garbage))
        assert r.status_code == 400, f"ציפינו ל-400, קיבלנו {r.status_code}: {r.text}"
        assert r.status_code != 500
        text_lower = r.text.lower()
        assert "traceback" not in text_lower and "line " not in text_lower
        print("✓ JSON פגום + חתימה תקינה → 400 מבוקר, בלי traceback (לא 500)")
    finally:
        teardown()


def test_malformed_json_with_wrong_signature_rejected() -> None:
    """גוף פגום **וגם** חתימה שגויה — נדחה כבר בשלב אימות החתימה (403),
    עוד לפני שמנסים לפענח את הגוף בכלל. מוכיח שבדיקת החתימה מ-6.1 עדיין
    רצה ראשונה ולא השתנתה ע"י תיקון ה-JSON."""
    api, teardown = bootstrap()
    try:
        garbage = b"{not json at all"
        with _secret(_REAL_SECRET):
            r = _post(api, garbage, _sign(garbage, secret="wrong-secret"))
        assert r.status_code == 403, f"ציפינו ל-403, קיבלנו {r.status_code}: {r.text}"

        with _secret(_REAL_SECRET):
            r2 = _post(api, garbage, None)  # בלי כותרת חתימה בכלל
        assert r2.status_code == 403, r2.text
        print("✓ JSON פגום + חתימה שגויה/חסרה → 403 (נבדק לפני הפענוח, לא 500 ולא 400)")
    finally:
        teardown()


def test_empty_or_non_dict_json_with_valid_signature_no_500() -> None:
    """JSON ריק / לא בצורת webhook (מערך, מחרוזת, null, גוף ריק לגמרי) —
    כולם JSON *תקין-תחבירית*, אז לא נכנסים ל-except החדש (400) בכלל; הם
    כבר היו מטופלים בעדינות ע"י ה-except הפנימי הקיים (db.rollback + 200
    'received: true' — 'לעולם לא נכשלים ל-Meta' על עיבוד). כאן רק נועלים
    (regression-lock) שזה נשאר נכון ולא מחזיר 500 באף אחת מהצורות."""
    api, teardown = bootstrap()
    try:
        for label, body in [
            ("גוף ריק לגמרי", b""),
            ("אובייקט ריק", b"{}"),
            ("מערך במקום אובייקט", b"[]"),
            ("null", b"null"),
            ("מספר", b"42"),
            ("מחרוזת", b'"hello"'),
        ]:
            with _secret(_REAL_SECRET):
                r = _post(api, body, _sign(body))
            assert r.status_code != 500, f"{label}: קיבלנו 500! {r.text}"
            assert r.status_code == 200, f"{label}: ציפינו ל-200 (התנהגות קיימת), קיבלנו {r.status_code}: {r.text}"
            assert r.json() == {"received": True}, f"{label}: {r.text}"
        print("✓ JSON ריק/לא-בצורת-webhook (6 צורות) → 200 עדין, אף פעם לא 500")
    finally:
        teardown()


if __name__ == "__main__":
    try:
        test_missing_secret_env_var_rejects_webhook()
        test_empty_secret_env_var_rejects_webhook()
        test_missing_signature_header_rejected_when_secret_configured()
        test_wrong_signature_rejected()
        test_valid_signature_accepted_and_updates_rsvp()
        test_valid_signature_status_update_still_works()
        test_cross_tenant_guest_not_reachable_without_valid_signature()
        test_no_500_across_all_signature_scenarios()
        test_malformed_json_with_valid_signature_rejected_cleanly()
        test_malformed_json_with_wrong_signature_rejected()
        test_empty_or_non_dict_json_with_valid_signature_no_500()
        print()
        print("=== כל בדיקות אבטחת ה-webhook עברו ===")
    finally:
        shutdown()
