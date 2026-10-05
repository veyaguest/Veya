-- ============================================================================
-- VEYA · Row Level Security · קובץ 26: מדידת שימוש בעזרה (help_events)
-- ============================================================================
-- מריצים אחרי קבצים 1–25. idempotent (DROP + CREATE), אפשר להריץ שוב בבטחה.
-- נטען אוטומטית בעליית השרת (ראו ``_RLS_MIGRATION_FILES`` ב-main.py).
-- HELP_CENTER_PLAN.md §12–13.3 / שלב 8.
--
-- ‼️ תלות: ``app_current_user_id``, ``app_is_admin`` מוגדרות ב-**קובץ 01**.
--
-- ── מודל ההרשאות ────────────────────────────────────────────────────────
--
--   אין בטבלה זהות (בלי user_id ובלי event_id) — לכן אין "שורה של מישהו".
--
--   INSERT — כל משתמש מחובר (דרך ה-API בלבד, שמאמת אוצר מילים סגור, הרשאת
--            אירוע ודגל העזרה, ומגביל קצב).
--   SELECT — אדמין בלבד (מסך "תובנות עזרה").
--   DELETE — אדמין בלבד: מחיקת אירועים ישנים מ-180 יום רצה כשצוות פותח את
--            "תובנות עזרה" (help_analytics.purge_old, בזהות האדמין).
--   UPDATE — אין מדיניות: אירוע שנרשם לא משתנה.
-- ============================================================================

ALTER TABLE help_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE help_events FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS help_events_insert ON help_events;
CREATE POLICY help_events_insert ON help_events FOR INSERT
  WITH CHECK (app_current_user_id() IS NOT NULL);

DROP POLICY IF EXISTS help_events_select ON help_events;
CREATE POLICY help_events_select ON help_events FOR SELECT
  USING (app_is_admin());

DROP POLICY IF EXISTS help_events_delete ON help_events;
CREATE POLICY help_events_delete ON help_events FOR DELETE
  USING (app_is_admin());

GRANT SELECT, INSERT, DELETE ON help_events TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE help_events_id_seq TO veya_app;
