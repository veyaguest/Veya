"""WhatsApp מול Postgres + RLS אמיתי — עוטף את ``_whatsapp_pg_worker.py``.

Postgres זמני (``pgserver``, בלי Docker), תפקיד ``veya_app`` כפוף ל-RLS, בדיוק
כמו ``test_full_rls_regression.py``. מכסה את מה ש-SQLite לא יכול להוכיח:
נעילה לפי אירוע, שליחות מקבילות, commit-ים באמצע בקשה תחת RLS, "נכשלה" מול
"נמסרה", נעילת שורה, webhook כפול במקביל, ומצב ``meta_test`` תחת RLS.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("pgserver", reason="pip install pgserver כדי להריץ מול Postgres אמיתי")

from tests.rls_pg_harness import start_ephemeral_postgres  # noqa: E402

WORKER = Path(__file__).resolve().parent / "_whatsapp_pg_worker.py"
BACKEND_DIR = Path(__file__).resolve().parent.parent

SCENARIOS = [
    "01_event_lock",
    "02_concurrent_invitations_once",
    "03_external_provider_commits_under_rls",
    "04_failed_does_not_override",
    "05_row_lock_no_regression",
    "06_webhook_reply_and_duplicates",
    "07_webhook_concurrent_duplicates",
    "08_meta_test_allowlist_under_rls",
    "09_meta_template_unknown_then_reconciled",
]


@pytest.fixture(scope="module")
def results():
    pg = start_ephemeral_postgres()
    try:
        env = dict(os.environ)
        env["DATABASE_URL"] = pg.veya_app_dsn
        env["MIGRATIONS_DATABASE_URL"] = pg.admin_dsn
        env["JWT_SECRET"] = "test-secret-not-for-production-usage"
        env.pop("VEYA_ENV", None)
        env.pop("WHATSAPP_MODE", None)
        proc = subprocess.run(
            [sys.executable, str(WORKER)], cwd=str(BACKEND_DIR), env=env,
            capture_output=True, text=True, timeout=240,
        )
        assert proc.returncode == 0, f"stdout={proc.stdout[-3000:]!r} stderr={proc.stderr[-6000:]!r}"
        yield json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        pg.cleanup()


@pytest.mark.parametrize("name", SCENARIOS)
def test_whatsapp_on_postgres(results, name):
    assert name in results, f"התרחיש לא רץ: {sorted(results)}"
    assert results[name]["ok"], f"{name}: {results[name]}"
