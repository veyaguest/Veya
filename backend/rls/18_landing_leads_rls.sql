-- ============================================================================
-- VEYA · Row Level Security · קובץ 18: פניות מדף הנחיתה (landing_leads)
-- ============================================================================
-- מריצים אחרי קבצים 1–17. idempotent (DROP + CREATE), אפשר להריץ שוב בבטחה.
-- נטען אוטומטית בעליית השרת יחד עם 15–17 (ראו ``_RLS_MIGRATION_FILES``).
--
-- ‼️ תלות: ``app_is_admin`` מוגדרת ב-**קובץ 01**.
--
-- ── מודל ההרשאות ────────────────────────────────────────────────────────
--
--   INSERT — פתוח. זו הנקודה היחידה במערכת שבה כותב מי שאינו משתמש:
--            מבקר בדף הנחיתה שהשאיר שם וטלפון. אין לו ``user_id`` ואין
--            לו אירוע, ולכן אין למדיניות במה להיאחז מלבד "מותר להוסיף".
--            ההגנה כאן היא הגבלת קצב ב-API (``lead_limiter``), לא RLS.
--
--   SELECT — אדמין בלבד. ליד הוא שם + טלפון של אדם אמיתי: אין שום סיבה
--            שזוג, מפיק או אולם יוכלו לקרוא את רשימת הפניות.
--
--   UPDATE/DELETE — אין מדיניות בכלל, כלומר אסור לכולם דרך ה-API. פנייה
--            היא רישום היסטורי; מחיקה (בקשת אדם להסרת פרטיו) נעשית
--            ידנית מול ה-DB ובמודע, לא דרך הרשאה שפתוחה כל הזמן.
-- ============================================================================

ALTER TABLE landing_leads ENABLE ROW LEVEL SECURITY;
ALTER TABLE landing_leads FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS landing_leads_insert ON landing_leads;
CREATE POLICY landing_leads_insert ON landing_leads FOR INSERT
  WITH CHECK (true);

DROP POLICY IF EXISTS landing_leads_select ON landing_leads;
CREATE POLICY landing_leads_select ON landing_leads FOR SELECT
  USING (app_is_admin());

GRANT SELECT, INSERT ON landing_leads TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE landing_leads_id_seq TO veya_app;
