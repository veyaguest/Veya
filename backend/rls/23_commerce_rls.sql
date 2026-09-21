-- 23 — מסחר: מסלולים, גרסאות, תוספים, עמלות, קופונים, רכישות לאירועים.
-- קריאה: פתוחה לקטלוג (מסלולים/תוספים/עמלה פעילה נטענים למטמון מחיבור בלי זהות,
-- למשל חישוב עמלה בדף האורח). קופונים ורכישות — אדמין ובעלי האירוע בלבד.
-- כתיבה — אדמין בלבד.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['plans','plan_versions','addons','fee_rules'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_select', t);
    EXECUTE format('CREATE POLICY %I ON %I FOR SELECT USING (true)', t || '_select', t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_write', t);
    EXECUTE format('CREATE POLICY %I ON %I FOR ALL USING (app_is_admin()) WITH CHECK (app_is_admin())', t || '_write', t);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO veya_app', t);
    EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %I TO veya_app', t || '_id_seq');
  END LOOP;
END $$;

ALTER TABLE coupons ENABLE ROW LEVEL SECURITY;
ALTER TABLE coupons FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS coupons_admin ON coupons;
CREATE POLICY coupons_admin ON coupons FOR ALL USING (app_is_admin()) WITH CHECK (app_is_admin());
GRANT SELECT, INSERT, UPDATE, DELETE ON coupons TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE coupons_id_seq TO veya_app;

-- event_entitlements: נטען גם למטמון הזכאויות (בלי זהות) — ולכן SELECT פתוח;
-- אין בו מידע אישי (מזהה אירוע, מסלול, מחיר). כתיבה/מחיקה: אדמין, ומחיקה גם
-- למי שמנהל את האירוע (ניקוי במחיקת אירוע).
ALTER TABLE event_entitlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_entitlements FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS event_entitlements_select ON event_entitlements;
CREATE POLICY event_entitlements_select ON event_entitlements FOR SELECT USING (true);
DROP POLICY IF EXISTS event_entitlements_write ON event_entitlements;
CREATE POLICY event_entitlements_write ON event_entitlements FOR ALL
  USING (app_is_admin()) WITH CHECK (app_is_admin());
DROP POLICY IF EXISTS event_entitlements_owner_delete ON event_entitlements;
CREATE POLICY event_entitlements_owner_delete ON event_entitlements FOR DELETE
  USING (app_manages_event(event_id));
GRANT SELECT, INSERT, UPDATE, DELETE ON event_entitlements TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE event_entitlements_id_seq TO veya_app;
