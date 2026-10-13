"""בדיקת webhook חתום ומדומה מול שרת VEYA — אירוע סטטוס ``delivered`` אחד.

מה זה בודק: ששרת ה-webhook החי מקבל אירוע שחתום ב-``WHATSAPP_APP_SECRET``,
שהאירוע עובר את הסינון לפי ``WHATSAPP_WEBHOOK_PHONE_NUMBER_ID``, ושסטטוס
מפוענח ומעובד. **לא** בודק עדכון הודעה במסד: ה-``wamid`` כאן מדומה וייחודי,
ואין לו שורה בשום מסד — בלוג של Render הצפי הוא ``status delivered known=no``.

מה זה לא עושה: לא שולח הודעת WhatsApp, לא פונה ל-Meta, לא נוגע במסד מקומי
ולא משנה שום הגדרה. הבקשה היחידה היא POST אחד לכתובת ה-webhook שלנו.

סודות: ``WHATSAPP_APP_SECRET`` ו-``WHATSAPP_WEBHOOK_PHONE_NUMBER_ID`` נקראים
מ-``backend/.env`` (או מהסביבה), ורק אם קיימים — אין ערך ברירת מחדל. הסוד לא
מודפס ולא נשמר; מזהה המספר מודפס מצונזר. אין שום הנחה שהם תואמים ל-Render —
התוצאה היא מה שבודק את זה:
    403                       → הסוד המקומי ≠ זה שב-Render (או שהוא לא מוגדר שם)
    200 + בלוג "known=no"     → חתימה וסינון עברו, הסטטוס עובד
    200 + "rejected ... reason=phone_number_id_mismatch / not_configured"
                              → מזהה המספר לא תואם / לא מוגדר ב-Render

שימוש (מתוך backend/):
    venv/bin/python scripts/whatsapp_webhook_probe.py          # מציג בלבד, לא שולח
    venv/bin/python scripts/whatsapp_webhook_probe.py --send   # POST אחד
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import time
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# כתובת היעד — קבועה בקוד. אין ארגומנט ואין משתנה סביבה שמשנים אותה, וגם
# הגדרות proxy מהסביבה לא חלות על הבקשה (``trust_env=False``).
TARGET_URL = "https://veya-backend-u41w.onrender.com/messaging/webhook"
# מזהה הודעה מדומה: ``wamid.VEYA-PROBE-<uuid>`` — אמיתיים הם base64 (``wamid.HBg…``),
# כך שאין התנגשות אפשרית עם הודעה אמיתית, וכל הרצה ייחודית.
PROBE_PREFIX = "wamid.VEYA-PROBE-"
# "נמען" מדומה — לא מספר טלפון של אף אחד, ולא בשימוש בעיבוד (אין callback).
DUMMY_RECIPIENT = "000000000000"


def _load_env(env_file: Path) -> bool:
    from dotenv import load_dotenv

    return load_dotenv(env_file, override=False)


def _mask(value: str) -> str:
    return f"***{value[-4:]}" if len(value) > 4 else "***"


def new_probe_wamid() -> str:
    return PROBE_PREFIX + uuid.uuid4().hex


def build_payload(phone_number_id: str, wamid: str, timestamp: int) -> dict:
    """אירוע סטטוס ``delivered`` אחד, במבנה של Meta (``entry → changes → value``)."""
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "veya-webhook-probe",
            "changes": [{
                "field": "messages",
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {"display_phone_number": "0", "phone_number_id": phone_number_id},
                    "statuses": [{
                        "id": wamid,
                        "status": "delivered",
                        "timestamp": str(timestamp),
                        "recipient_id": DUMMY_RECIPIENT,
                    }],
                },
            }],
        }],
    }


def encode(payload: dict) -> bytes:
    """הבייטים בדיוק כפי שנחתמים ונשלחים."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign(body: bytes, app_secret: str) -> str:
    """``X-Hub-Signature-256`` כפי ש-Meta שולחת: HMAC-SHA256 על הגוף הגולמי, hex."""
    return "sha256=" + hmac.new(app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def redacted_view(payload: dict) -> dict:
    """אותו payload להצגה — מזהה המספר מצונזר."""
    shown = json.loads(json.dumps(payload))
    meta = shown["entry"][0]["changes"][0]["value"]["metadata"]
    meta["phone_number_id"] = _mask(meta["phone_number_id"])
    return shown


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="אירוע סטטוס delivered חתום ומדומה ל-webhook", allow_abbrev=False,
    )
    parser.add_argument("--send", action="store_true", help="לשלוח בפועל (בלי זה — הצגה בלבד)")
    # לבדיקות בלבד: מאיזה קובץ לקרוא את הסוד ואת מזהה המספר. לא משפיע על היעד.
    parser.add_argument("--env-file", default=str(BACKEND / ".env"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    import os

    loaded = _load_env(Path(args.env_file))
    secret = (os.getenv("WHATSAPP_APP_SECRET") or "").strip()
    pnid_raw = (os.getenv("WHATSAPP_WEBHOOK_PHONE_NUMBER_ID") or "").strip()
    pnid = next((p.strip() for p in pnid_raw.split(",") if p.strip()), "")
    print(f"קובץ הגדרות: {'נטען' if loaded else 'לא נמצא'}")
    print(f"  WHATSAPP_APP_SECRET: {'מוגדר' if secret else 'חסר'}")
    print(f"  WHATSAPP_WEBHOOK_PHONE_NUMBER_ID: {'מוגדר (' + _mask(pnid) + ')' if pnid else 'חסר'}")
    if not secret or not pnid:
        print("✗ לא נשלח: חסר משתנה מקומי. לא משתמשים בערך ברירת מחדל.")
        return 2

    wamid = new_probe_wamid()
    payload = build_payload(pnid, wamid, int(time.time()))
    body = encode(payload)
    signature = sign(body, secret)

    print(f"\nכתובת: POST {TARGET_URL}")
    print("כותרות: Content-Type: application/json · X-Hub-Signature-256: sha256=<64 תווי hex — לא מוצג>")
    print(f"גודל הגוף: {len(body)} בייטים")
    print("payload (מזהה המספר מצונזר):")
    print(json.dumps(redacted_view(payload), ensure_ascii=False, indent=2))

    if not args.send:
        print("\nהצגה בלבד — לא נשלח. להוסיף --send כדי לשלוח POST אחד.")
        return 0

    import httpx

    started = time.time()
    try:
        resp = httpx.post(
            TARGET_URL, content=body, timeout=httpx.Timeout(120.0, connect=30.0),
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
            follow_redirects=False, trust_env=False,
        )
    except httpx.HTTPError as exc:
        print(f"\n✗ אין תשובה מהשרת: {type(exc).__name__}")
        return 3
    took = time.time() - started
    print(f"\nתשובה: {resp.status_code} ({took:.1f}s) {resp.text[:120]}")
    print(f"זמן שליחה (UTC): {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(started))}")
    if resp.status_code == 200:
        print("בלוג של Render, באותו זמן, לחפש אחת מאלה:")
        print('  "[veya:whatsapp] status delivered known=no"  → עבר חתימה וסינון; הסטטוס עובד')
        print('  "webhook rejected items=1 reason=..."       → נדחה בסינון (הסיבה בשורה)')
        print("ה-wamid מדומה — שום הודעה במסד לא עודכנה.")
        return 0
    if resp.status_code == 403:
        print("403: החתימה נדחתה — הסוד המקומי לא תואם לזה שב-Render, או שהוא לא מוגדר שם.")
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
