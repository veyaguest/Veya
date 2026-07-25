-- ============================================================================
-- VEYA · RLS fix: consent_records (missing from Production — found by audit
-- 2026-07-25). Standalone, idempotent, touches ONLY consent_records.
-- ============================================================================
-- Root cause: the table was auto-created by SQLAlchemy's create_all() when
-- the ConsentRecord model shipped, but the RLS section already written for
-- it in 02_policies.sql (lines 231-255) was never actually run against a
-- live database. This file is that same, unmodified section, extracted so
-- it can be applied on its own without re-running 02_policies.sql in full.
--
-- Verified against the live production schema (information_schema.columns)
-- on 2026-07-25: user_id integer/nullable, consent_type/document_version/
-- source varchar not-null, ip varchar/nullable, accepted_at timestamp
-- not-null — matches app/models.py::ConsentRecord exactly. No column names
-- referenced here need to change.
--
-- Requires: app_current_user_id() and app_is_admin() (from
-- 01_helpers_and_grants.sql) — already present in production, proven by the
-- 24 existing policies on other tables that depend on the same functions.
--
-- Safe to run on Production with existing data: yes.
--   - ENABLE/FORCE ROW LEVEL SECURITY do not touch any row's data.
--   - CREATE POLICY only takes effect for non-superuser roles going forward;
--     it cannot delete, lock, or lose any existing row.
--   - DROP POLICY IF EXISTS before each CREATE POLICY makes re-running this
--     file safe (idempotent) even if partially applied before.
--   - The only behavior change: the `veya_app` role (used by the running
--     API) will now be restricted on this table exactly like every other
--     per-user table. The superuser role used for migrations is unaffected
--     (superuser always bypasses RLS, by Postgres design).
-- ============================================================================

ALTER TABLE consent_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE consent_records FORCE  ROW LEVEL SECURITY;

-- SELECT: a user reads only their own consent history, or an admin reads all.
-- Needed because /auth/me/export and any future "my consents" UI must not
-- leak one user's consent timestamps/versions to another user.
DROP POLICY IF EXISTS consent_records_select ON consent_records;
CREATE POLICY consent_records_select ON consent_records FOR SELECT
  USING (user_id = app_current_user_id() OR app_is_admin());

-- INSERT: a user may only insert a consent row under their own user_id.
-- No SECURITY DEFINER needed (unlike users_insert) because consent rows are
-- always written *after* the user already exists and is authenticated —
-- there is no anonymous/pre-identity insert path here.
DROP POLICY IF EXISTS consent_records_insert ON consent_records;
CREATE POLICY consent_records_insert ON consent_records FOR INSERT
  WITH CHECK (user_id = app_current_user_id());

-- UPDATE: only used by auth.py::delete_my_account to null out user_id on a
-- user's own rows during self-deletion (or by an admin). WITH CHECK (true)
-- because the post-update value (user_id=NULL) can no longer equal
-- app_current_user_id() — the USING clause is what gates who may start the
-- update; WITH CHECK must allow the resulting NULL.
DROP POLICY IF EXISTS consent_records_update ON consent_records;
CREATE POLICY consent_records_update ON consent_records FOR UPDATE
  USING (user_id = app_current_user_id() OR app_is_admin())
  WITH CHECK (true);

-- DELETE: admin only. Consent records are an append-only audit trail (proof
-- of what was accepted, when) — a user must never be able to erase their own
-- consent history, even after account deletion (that's why UPDATE anonymizes
-- instead of DELETE in delete_my_account).
DROP POLICY IF EXISTS consent_records_delete ON consent_records;
CREATE POLICY consent_records_delete ON consent_records FOR DELETE
  USING (app_is_admin());
