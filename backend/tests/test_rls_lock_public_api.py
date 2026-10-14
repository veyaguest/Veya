"""``rls/28_lock_public_api.sql`` מול Postgres אמיתי (``pgserver``, בלי Docker).

מדמים את ברירת המחדל של Supabase — תפקידי ``anon``/``authenticated`` עם הרשאות
על כל טבלה ופונקציה חדשה ב-public, ופונקציות שכל אחד (PUBLIC) רשאי להריץ — ואז:

1. **לפני 28:** החשיפה באמת קיימת (כדי שהבדיקה תבדוק משהו אמיתי).
2. **אחרי 28:** ל-anon ול-authenticated אין שום הרשאה על טבלה, רצף או פונקציה;
   PUBLIC לא מריץ פונקציות; ``veya_app`` מריץ את כולן.
3. **ברירות מחדל לעתיד:** טבלה ופונקציה חדשות לא נחשפות, ו-``veya_app`` מריץ.
4. **האפליקציה לא נשברה:** כל תרחישי רגרסיית ה-RLS (``_rls_full_regression_worker``)
   עוברים שוב, על אותו מסד, אחרי 28.
5. **הקובץ idempotent:** הרצה שנייה לא נכשלת ולא פותחת כלום.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pgserver", reason="pip install pgserver כדי להריץ מול Postgres אמיתי")
psycopg2 = pytest.importorskip("psycopg2")

from tests.rls_pg_harness import start_ephemeral_postgres  # noqa: E402
from tests.test_full_rls_regression import SCENARIO_NAMES, _run_worker  # noqa: E402

RLS_28 = Path(__file__).resolve().parent.parent / "rls" / "28_lock_public_api.sql"

# ברירת המחדל של פרויקט Supabase, כפי שהיא בייצור לפני התיקון.
_SUPABASE_DEFAULTS = """
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon NOLOGIN; END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
END $$;
GRANT USAGE ON SCHEMA public TO anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO anon, authenticated;
"""

_EXPOSURE = """
SELECT
  (SELECT count(*) FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace
     AND (has_function_privilege('anon', p.oid, 'EXECUTE')
          OR has_function_privilege('authenticated', p.oid, 'EXECUTE'))),
  (SELECT count(*) FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r'
     AND (has_table_privilege('anon', c.oid, 'SELECT,INSERT,UPDATE,DELETE')
          OR has_table_privilege('authenticated', c.oid, 'SELECT,INSERT,UPDATE,DELETE'))),
  (SELECT count(*) FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'S'
     AND (has_sequence_privilege('anon', c.oid, 'USAGE,SELECT,UPDATE')
          OR has_sequence_privilege('authenticated', c.oid, 'USAGE,SELECT,UPDATE'))),
  (SELECT count(*) FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace
     AND NOT has_function_privilege('veya_app', p.oid, 'EXECUTE')),
  (SELECT count(*) FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace
     AND p.proacl IS NOT NULL AND EXISTS (
       SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE')),
  (SELECT count(*) FROM pg_proc p WHERE p.pronamespace = 'public'::regnamespace AND p.proname LIKE 'app\\_%')
"""


def _admin(dsn):
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    return conn


def _exposure(dsn) -> dict:
    with _admin(dsn) as conn, conn.cursor() as cur:
        cur.execute(_EXPOSURE)
        fn_anon, tables_anon, seq_anon, fn_not_app, fn_public, app_fns = cur.fetchone()
    return {"functions_exposed": fn_anon, "tables_exposed": tables_anon, "sequences_exposed": seq_anon,
            "functions_veya_app_cannot_run": fn_not_app, "functions_public_execute": fn_public,
            "app_functions": app_fns}


def _apply_28(dsn) -> None:
    with _admin(dsn) as conn, conn.cursor() as cur:
        cur.execute(RLS_28.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def lifecycle():
    pg = start_ephemeral_postgres()
    try:
        with _admin(pg.admin_dsn) as conn, conn.cursor() as cur:
            cur.execute(_SUPABASE_DEFAULTS)
        first = _run_worker(pg.veya_app_dsn, pg.admin_dsn, legacy=False)  # סכימה + RLS + נתונים
        before = _exposure(pg.admin_dsn)
        _apply_28(pg.admin_dsn)
        after = _exposure(pg.admin_dsn)
        _apply_28(pg.admin_dsn)  # idempotent
        after_twice = _exposure(pg.admin_dsn)

        # ברירות מחדל לעתיד: טבלה ופונקציה חדשות שנוצרות כ-postgres.
        with _admin(pg.admin_dsn) as conn, conn.cursor() as cur:
            cur.execute("CREATE TABLE public.zz_future_table (id serial PRIMARY KEY)")
            cur.execute("CREATE FUNCTION public.zz_future_fn() RETURNS int LANGUAGE sql AS 'SELECT 1'")
            cur.execute("""
                SELECT has_table_privilege('anon', 'public.zz_future_table', 'SELECT'),
                       has_table_privilege('authenticated', 'public.zz_future_table', 'SELECT'),
                       has_function_privilege('anon', 'public.zz_future_fn()', 'EXECUTE'),
                       has_function_privilege('authenticated', 'public.zz_future_fn()', 'EXECUTE'),
                       has_function_privilege('veya_app', 'public.zz_future_fn()', 'EXECUTE'),
                       has_table_privilege('veya_app', 'public.zz_future_table', 'SELECT')
            """)
            future = cur.fetchone()
            cur.execute("DROP FUNCTION public.zz_future_fn(); DROP TABLE public.zz_future_table")

        second = _run_worker(pg.veya_app_dsn, pg.admin_dsn, legacy=False)  # האפליקציה אחרי 28
        after_rerun = _exposure(pg.admin_dsn)
        yield {"first": first, "before": before, "after": after, "after_twice": after_twice,
               "future": future, "second": second, "after_rerun": after_rerun}
    finally:
        pg.cleanup()


def test_exposure_exists_before_28(lifecycle):
    b = lifecycle["before"]
    assert b["app_functions"] >= 20, b
    assert b["functions_exposed"] >= b["app_functions"], f"הסימולציה לא חשפה את הפונקציות: {b}"
    assert b["tables_exposed"] >= 40, f"הסימולציה לא חשפה את הטבלאות: {b}"


def test_after_28_nothing_is_exposed(lifecycle):
    for key in ("after", "after_twice"):
        a = lifecycle[key]
        assert a["functions_exposed"] == 0, (key, a)
        assert a["tables_exposed"] == 0, (key, a)
        assert a["sequences_exposed"] == 0, (key, a)
        assert a["functions_public_execute"] == 0, (key, a)
        assert a["functions_veya_app_cannot_run"] == 0, (key, a)


def test_future_objects_are_not_exposed(lifecycle):
    anon_t, auth_t, anon_f, auth_f, app_f, app_t = lifecycle["future"]
    assert (anon_t, auth_t, anon_f, auth_f) == (False, False, False, False)
    assert app_f is True and app_t is True


def test_reapplying_rls_files_does_not_reopen(lifecycle):
    """הרצה חוזרת של קובצי ה-RLS (CREATE OR REPLACE) — כמו בעליית שרת — לא מחזירה הרשאות."""
    a = lifecycle["after_rerun"]
    assert a["functions_exposed"] == 0 and a["tables_exposed"] == 0, a
    assert a["functions_public_execute"] == 0 and a["functions_veya_app_cannot_run"] == 0, a


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_app_scenarios_still_pass_after_28(lifecycle, name):
    for run in ("first", "second"):
        entry = lifecycle[run].get(name)
        assert entry is not None and entry.get("ok") is True, f"{run}: {name} נכשל: {entry}"
