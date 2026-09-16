-- 19 — מרכז השליטה של האדמין: יומן פעולות אדמין.
--
-- admin_audit_logs: קריאה וכתיבה לאדמין בלבד. אין מדיניות UPDATE/DELETE —
-- היומן הוא טבלת הוספה בלבד גם ברמת המסד, לא רק כי אין endpoint שמוחק.
-- (דרגות Support/Admin/Super Admin נאכפות ב-API: app/admin_rbac.py.)

ALTER TABLE admin_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_audit_logs FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS admin_audit_logs_select ON admin_audit_logs;
CREATE POLICY admin_audit_logs_select ON admin_audit_logs FOR SELECT
  USING (app_is_admin());

DROP POLICY IF EXISTS admin_audit_logs_insert ON admin_audit_logs;
CREATE POLICY admin_audit_logs_insert ON admin_audit_logs FOR INSERT
  WITH CHECK (app_is_admin());

GRANT SELECT, INSERT ON admin_audit_logs TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE admin_audit_logs_id_seq TO veya_app;
