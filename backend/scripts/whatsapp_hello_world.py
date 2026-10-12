"""כלי בדיקה ידני: שולח את תבנית ``hello_world`` של Meta למספר הבדיקה שלכם.

לא קשור לשום אורח, לא נוגע במסד, ולא חלק ממסלול אישורי ההגעה. נועד לבדוק
את החיבור ל-Meta מקצה לקצה (שליחה → נמסרה → נקראה) לפני שיש Templates של VEYA.

שולח **רק** כשכל התנאים מתקיימים (``whatsapp_meta.hello_world_preflight``):
WHATSAPP_MODE=meta_test · לא VEYA_ENV=production · עצירת חירום כבויה ·
הנמען ב-WHATSAPP_TEST_RECIPIENTS · טוקן ומזהה מספר מוגדרים.

שימוש (מתוך backend/):
    venv/bin/python scripts/whatsapp_hello_world.py                 # בדיקת הגדרות בלבד
    venv/bin/python scripts/whatsapp_hello_world.py --to 05XXXXXXXX # בדיקת תנאים, בלי שליחה
    venv/bin/python scripts/whatsapp_hello_world.py --to 05XXXXXXXX --send

לא מדפיס טוקנים, סודות, מספרי טלפון מלאים או את מזהה ההודעה של Meta (``wamid``
מכיל את מספר הנמען בקידוד base64) — רק טביעה מצונזרת שלו.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


def _load_env(env_file: Path) -> bool:
    """טוען את ``backend/.env`` **לפני** שקוראים הגדרות כלשהן.

    ``app.messaging``/``app.whatsapp_meta`` לא טוענים את הקובץ בעצמם (רק
    ``app.database`` עושה זאת, וייבוא שלו קורה מאוחר מדי) — בלי זה הכלי היה
    מדווח "חסר" ומסרב לשלוח גם כשהכול מוגדר. משתנה שכבר מוגדר בסביבה גובר
    על הקובץ (``override=False``).
    """
    from dotenv import load_dotenv

    return load_dotenv(env_file, override=False)


def _mask(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    return f"***{digits[-3:]}" if len(digits) >= 3 else "***"


_WAMID_RE = re.compile(r"wamid\.[A-Za-z0-9+/=_-]+")
# רצף של 8 ספרות ומעלה (עם רווחים/מקפים) — טלפון. קודי שגיאה של Meta (עד 7 ספרות) נשארים.
_LONG_DIGITS_RE = re.compile(r"\+?\d[\d\s-]{6,}\d")


def _redact_wamid(wamid: str) -> str:
    """מזהה ההודעה של Meta מכיל בתוכו את מספר הנמען בקידוד base64 — ולכן לא
    מוצג. במקומו: טביעה קצרה שאי אפשר לשחזר ממנה דבר, אבל אפשר להשוות אותה
    (sha256 של המזהה המלא, 10 תווים)."""
    return "wamid#" + hashlib.sha256(wamid.encode("utf-8")).hexdigest()[:10]


def _safe(text: str) -> str:
    """כל טקסט שמגיע מבחוץ (תיאור שגיאה של Meta וכו') עובר כאן לפני הדפסה."""
    text = _WAMID_RE.sub(lambda m: _redact_wamid(m.group(0)), text or "")
    return _LONG_DIGITS_RE.sub("[מספר מוסתר]", text)


def main(argv: list[str] | None = None) -> int:
    """כמו ``_run``, אבל חריגה לא צפויה מודפסת רק כסוג — בלי traceback, שעלול
    להכיל כתובת בקשה, מזהה הודעה או ערכי הגדרות."""
    try:
        return _run(argv)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"✗ שגיאה לא צפויה: {type(exc).__name__}")
        return 4


def _run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="שליחת hello_world למספר בדיקה מורשה")
    parser.add_argument("--to", help="הטלפון שלכם (חייב להיות ב-WHATSAPP_TEST_RECIPIENTS)")
    parser.add_argument("--send", action="store_true", help="לשלוח בפועל (בלי זה — בדיקה בלבד)")
    parser.add_argument("--env-file", default=str(BACKEND / ".env"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    loaded = _load_env(Path(args.env_file))
    print(f"קובץ הגדרות: {'נטען' if loaded else 'לא נמצא'} ({Path(args.env_file).name})")

    from app import messaging, whatsapp_meta

    print("הגדרות WhatsApp:")
    for name, state in whatsapp_meta.config_report().items():
        print(f"  {name}: {state}")
    print(f"  מצב בפועל: {messaging.whatsapp_mode()}")
    print(f"  נמענים מורשים: {len(messaging.test_recipients())}")
    print(f"  גרסת API: {whatsapp_meta.load_config().graph_version}")

    if not args.to:
        return 0

    check = whatsapp_meta.hello_world_preflight(args.to)
    print(f"\nנמען: {_mask(args.to)}")
    if not check.ok:
        print("לא נשלח. תנאים שלא מתקיימים:")
        for reason in check.reasons:
            print(f"  ✗ {reason}")
        return 2
    print("כל תנאי הבטיחות מתקיימים.")
    if not args.send:
        print("בדיקה בלבד — לא נשלח. להוסיף --send כדי לשלוח.")
        return 0

    _, result = whatsapp_meta.send_hello_world(args.to)
    if result.ok:
        print(f"✓ Meta קיבלה את ההודעה (סטטוס: {_safe(result.provider_status or 'accepted')}).")
        print(f"  מזהה הודעה (מצונזר): {_redact_wamid(result.provider_message_id)}")
        return 0
    if result.status == "pending":
        print(f"? {_safe(result.detail)}")
        return 3
    print(f"✗ נכשל: {_safe(result.detail)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
