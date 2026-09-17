-- 21 — כללי המערכת ופיצ'רים: system_settings, setting_overrides, feature_flags, feature_rules.
--
-- קריאה פתוחה: הערכים נטענים למטמון מחיבור שאין לו זהות משתמש (חישוב לוח
-- זמנים, שליחה), והם אינם מידע אישי. כתיבה — אדמין בלבד. מחיקת Override/כלל
-- של אירוע מותרת גם למי שמנהל את האירוע (ניקוי במחיקת אירוע).

ALTER TABLE system_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_settings FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS system_settings_select ON system_settings;
CREATE POLICY system_settings_select ON system_settings FOR SELECT USING (true);
DROP POLICY IF EXISTS system_settings_write ON system_settings;
CREATE POLICY system_settings_write ON system_settings FOR ALL
  USING (app_is_admin()) WITH CHECK (app_is_admin());
GRANT SELECT, INSERT, UPDATE, DELETE ON system_settings TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE system_settings_id_seq TO veya_app;

ALTER TABLE setting_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE setting_overrides FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS setting_overrides_select ON setting_overrides;
CREATE POLICY setting_overrides_select ON setting_overrides FOR SELECT USING (true);
DROP POLICY IF EXISTS setting_overrides_write ON setting_overrides;
CREATE POLICY setting_overrides_write ON setting_overrides FOR ALL
  USING (app_is_admin()) WITH CHECK (app_is_admin());
DROP POLICY IF EXISTS setting_overrides_owner_delete ON setting_overrides;
CREATE POLICY setting_overrides_owner_delete ON setting_overrides FOR DELETE
  USING (scope_type = 'event' AND app_manages_event(scope_id));
GRANT SELECT, INSERT, UPDATE, DELETE ON setting_overrides TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE setting_overrides_id_seq TO veya_app;

ALTER TABLE feature_flags ENABLE ROW LEVEL SECURITY;
ALTER TABLE feature_flags FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS feature_flags_select ON feature_flags;
CREATE POLICY feature_flags_select ON feature_flags FOR SELECT USING (true);
DROP POLICY IF EXISTS feature_flags_write ON feature_flags;
CREATE POLICY feature_flags_write ON feature_flags FOR ALL
  USING (app_is_admin()) WITH CHECK (app_is_admin());
GRANT SELECT, INSERT, UPDATE, DELETE ON feature_flags TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE feature_flags_id_seq TO veya_app;

ALTER TABLE feature_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE feature_rules FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS feature_rules_select ON feature_rules;
CREATE POLICY feature_rules_select ON feature_rules FOR SELECT USING (true);
DROP POLICY IF EXISTS feature_rules_write ON feature_rules;
CREATE POLICY feature_rules_write ON feature_rules FOR ALL
  USING (app_is_admin()) WITH CHECK (app_is_admin());
DROP POLICY IF EXISTS feature_rules_owner_delete ON feature_rules;
CREATE POLICY feature_rules_owner_delete ON feature_rules FOR DELETE
  USING (scope_type = 'event' AND app_manages_event(scope_id));
GRANT SELECT, INSERT, UPDATE, DELETE ON feature_rules TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE feature_rules_id_seq TO veya_app;
