"""מחיקת אירוע עם כסף מול Postgres + RLS — ראו ``_finance_ledger_pg_worker.py``."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("pgserver", reason="pip install pgserver כדי להריץ מול Postgres אמיתי")
pytest.importorskip("psycopg2")

from tests.rls_pg_harness import start_ephemeral_postgres  # noqa: E402

WORKER = Path(__file__).resolve().parent / "_finance_ledger_pg_worker.py"


@pytest.fixture(scope="module")
def result():
    pg = start_ephemeral_postgres()
    try:
        env = dict(os.environ, DATABASE_URL=pg.veya_app_dsn, MIGRATIONS_DATABASE_URL=pg.admin_dsn,
                   JWT_SECRET="test-secret-not-for-production-usage")
        env.pop("VEYA_ENV", None)
        proc = subprocess.run([sys.executable, str(WORKER)], cwd=str(WORKER.parent.parent), env=env,
                              capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr[-5000:]
        yield json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        pg.cleanup()


def test_all_three_delete_paths_succeed_under_rls(result):
    assert (result["delete_event"], result["delete_me"], result["admin_delete"]) == (204, 204, 204), result


def test_money_moved_to_anonymous_ledger(result):
    assert result["events_left"] == 0 and result["gifts_left"] == 0 and result["money_left"] == 0, result
    assert result["ledger_rows"] == 3 and result["ent_ledger_rows"] == 3, result
    assert result["ledger_amounts"] == [[50000, 2000, "paid", "tx-pg"]], result
    assert not {"sender_name", "message", "guest_id"} & set(result["ledger_columns"]), result


def test_only_admin_reads_ledger_and_nobody_writes_directly(result):
    v = result["visibility"]
    assert v["owner"] == 0 and v["admin"] >= 3, v
    assert v["owner_direct_insert"] == "blocked" and v["admin_direct_insert"] == "blocked", v


@pytest.mark.xfail(strict=True, reason=(
    "תקלה קיימת (נמצאה 2026-10-28, לא קשורה לכסף): במחיקת חשבון עצמית, ניתוק "
    "consent_records (user_id=NULL) נחסם ב-RLS — מדיניות ה-SELECT של rls/04 לא "
    "מתירה את השורה החדשה. מחיקה ע\"י אדמין עובדת. כשהתקלה תתוקן הבדיקה תעבור "
    "ו-strict יחייב להסיר את הסימון."))
def test_self_delete_with_consent_records_known_bug(result):
    assert result["delete_me_with_consents"] == 204
