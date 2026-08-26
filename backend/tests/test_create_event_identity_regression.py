"""בדיקת רגרסיה: זהות RLS ששורדת ``commit()`` באמצע הבקשה, מול Postgres אמיתי
עם כל קובצי ה-RLS מותקנים ותפקיד ``veya_app`` (לא superuser) — בדיוק כמו
בפריסת ייצור אמיתית. RLS הוא no-op מוחלט ב-SQLite, ולכן אי אפשר להוכיח את
הבדיקות האלה בסוויטה הרגילה.

זו הבדיקה שמוכיחה את הממצא: ``routers/events.py::create_event`` עושה
``db.commit()`` ואז ממשיך ל-``communication.provision_event_messages`` (INSERT
רגיל, לא SECURITY DEFINER) — לפני התיקון זה נכשל בשקט תחת RLS אמיתי (האירוע
נוצר, רצף ההודעות לא). ראו ``app/database.py::set_request_identity`` להסבר
המלא של המנגנון (ContextVar לא שורד בין קריאות ``run_in_threadpool``,
``session.info`` כן).

מריץ Postgres זמני (``pgserver`` — מוטמע, בלי Docker/התקנה), מקים עליו את
הסכימה המלאה + את כל קובצי ``backend/rls/*.sql`` דרך תהליך-בת נפרד
(``_rls_identity_worker.py``) — פעם עם המנגנון הישן (``--legacy``) ופעם עם
הנוכחי — ומשווה. אין תלות בשום דבר חיצוני (לא Docker, לא Staging, לא משתני
סביבה ידניים) — רץ כחלק מהסוויטה הרגילה.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.rls_pg_harness import start_ephemeral_postgres

WORKER = Path(__file__).resolve().parent / "_rls_identity_worker.py"
BACKEND_DIR = Path(__file__).resolve().parent.parent


def _run_worker(veya_app_dsn: str, admin_dsn: str, *, legacy: bool) -> dict:
    env = dict(os.environ)
    env["DATABASE_URL"] = veya_app_dsn
    env["MIGRATIONS_DATABASE_URL"] = admin_dsn
    env["JWT_SECRET"] = "test-secret-not-for-production-usage"
    env.pop("VEYA_ENV", None)
    args = [sys.executable, str(WORKER)]
    if legacy:
        args.append("--legacy")
    proc = subprocess.run(
        args, cwd=str(BACKEND_DIR), env=env,
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, (
        f"worker (legacy={legacy}) נכשל בריצה עצמה — "
        f"stdout={proc.stdout!r} stderr={proc.stderr[-4000:]!r}"
    )
    # השורה האחרונה היא ה-JSON; הכול מעליה (אם יש) הוא פלט לוג רגיל.
    last_line = proc.stdout.strip().splitlines()[-1]
    return json.loads(last_line)


@pytest.fixture(scope="module")
def pg():
    harness = start_ephemeral_postgres()
    yield harness
    harness.cleanup()


def test_legacy_mechanism_reproduces_the_original_bug(pg):
    """מוכיח שהבאג המקורי אמיתי: עם מנגנון ה-ContextVar-בלבד (המצב לפני
    התיקון), הזהות אובדת אחרי commit(), ויצירת אירוע יוצרת אירוע "יתום"
    בלי רצף הודעות — בדיוק התרחיש שתועד בחקירה."""
    result = _run_worker(pg.veya_app_dsn, pg.admin_dsn, legacy=True)

    assert result["mechanism"] == "legacy_contextvar_only"

    # הזהות לא שורדת commit() תחת המנגנון הישן.
    assert result["identity_survives_commit"]["ok"] is False, result["identity_survives_commit"]

    # create_event: ה-API עצמו נכשל (חריגת RLS ב-provision_event_messages)...
    assert result["create_event_api"]["ok"] is False, result["create_event_api"]
    # ...אבל שורת האירוע כן נוצרה (ה-commit הראשון הצליח) — "אירוע יתום".
    gt = result["create_event_ground_truth"]
    assert gt["event_row_exists"] is True, gt
    assert gt["event_messages_count"] == 0, gt

    # guest_token גם הוא לא שורד commit() תחת המנגנון הישן.
    assert result["guest_token_survives_commit"]["ok"] is False, result["guest_token_survives_commit"]


def test_fixed_mechanism_survives_commit_and_enforces_rls(pg):
    """אותו תרחיש בדיוק, עם המנגנון הנוכחי (session.info) — הכול אמור לעבוד,
    כולל אכיפת RLS אמיתית (משתמש אחר לא רואה, הרשאה נדרשת לכתיבה)."""
    result = _run_worker(pg.veya_app_dsn, pg.admin_dsn, legacy=False)

    assert result["mechanism"] == "fixed_session_info"

    # 1. זהות שורדת commit() + טרנזקציה חדשה.
    assert result["identity_survives_commit"]["ok"] is True, result["identity_survives_commit"]

    # 2. רגרסיית create_event: ה-API מצליח, ורצף 6 ההודעות נוצר בפועל ב-DB.
    assert result["create_event_api"]["ok"] is True, result["create_event_api"]
    gt = result["create_event_ground_truth"]
    assert gt["event_row_exists"] is True, gt
    assert gt["event_messages_count"] == 6, gt

    # 3. SELECT מחזיר את הנתונים של הבעלים בלבד — משתמש אחר לא רואה.
    assert result["select_owner_sees_own_event"]["ok"] is True, result["select_owner_sees_own_event"]
    assert result["select_other_user_denied"]["ok"] is True, result["select_other_user_denied"]

    # 4. UPDATE מצליח כשלמשתמש יש הרשאה (בעלים על האירוע שלו).
    assert result["update_with_permission_succeeds"]["ok"] is True, result["update_with_permission_succeeds"]

    # 5. guest_token / RSVP: שורד commit(), ומוזמן בלי הטוקן לא נחשף.
    assert result["guest_token_survives_commit"]["ok"] is True, result["guest_token_survives_commit"]
    assert result["guest_without_token_denied"]["ok"] is True, result["guest_without_token_denied"]
