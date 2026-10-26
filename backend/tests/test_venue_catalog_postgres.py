"""מאגר האולמות מול Postgres אמיתי: מיגרציה על טבלה קיימת + ייבוא כ-veya_app.

ראו ``_venue_catalog_pg_worker.py``. דורש pgserver (כמו שאר בדיקות ה-RLS).
"""
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

WORKER = Path(__file__).resolve().parent / "_venue_catalog_pg_worker.py"


@pytest.fixture(scope="module")
def result():
    pg = start_ephemeral_postgres()
    try:
        env = dict(os.environ, DATABASE_URL=pg.veya_app_dsn, MIGRATIONS_DATABASE_URL=pg.admin_dsn,
                   JWT_SECRET="test-secret-not-for-production-usage")
        env.pop("VEYA_ENV", None)
        proc = subprocess.run([sys.executable, str(WORKER)], cwd=str(WORKER.parent.parent), env=env,
                              capture_output=True, text=True, timeout=300)
        assert proc.returncode == 0, proc.stderr[-4000:]
        yield json.loads(proc.stdout.strip().splitlines()[-1])
    finally:
        pg.cleanup()


def test_migration_adds_columns_and_unique_index(result):
    assert set(result["columns_added"]) >= {"import_key", "aliases", "region", "verification"}, result
    assert result["unique_index"] is True


def test_import_runs_as_app_role_and_is_idempotent(result):
    assert result["role"] == "veya_app", result
    assert result["first"]["created"] > 500 and result["first"]["invalid_count"] == 0, result
    assert result["second"]["created"] == 0 and result["second"]["updated"] == 0, result
    assert result["imported_rows"] == result["first"]["created"]


def test_existing_rows_untouched_and_db_blocks_duplicates(result):
    assert result["old_row_untouched"] is True, result
    assert result["first"]["matched_existing_count"] >= 1, "השורה הישנה 'אגדת דשא' הייתה צריכה להיחשב קיימת"
    assert result["db_blocks_duplicate_key"] is True
    assert result["search_hit"], result
