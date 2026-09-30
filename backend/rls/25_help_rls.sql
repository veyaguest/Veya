-- ============================================================================
-- VEYA · Row Level Security · קובץ 25: פניות לצוות מתוך "עזרה" (support_requests)
-- ============================================================================
-- מריצים אחרי קבצים 1–24. idempotent (DROP + CREATE), אפשר להריץ שוב בבטחה.
-- נטען אוטומטית בעליית השרת (ראו ``_RLS_MIGRATION_FILES`` ב-main.py).
-- HELP_CENTER_PLAN.md §13.3 / שלב 7.
--
-- ‼️ תלות: ``app_current_user_id``, ``app_is_admin``, ``app_owns_event``
--          מוגדרות ב-**קובץ 01**.
--
-- ── מודל ההרשאות ────────────────────────────────────────────────────────
--
--   SELECT — מי שכתב את הפנייה ("הפניות שלי"), ואדמין (מסך "פניות תמיכה").
--            בן/בת הזוג לא רואים פניות אחד של השני — כל אחד כתב בשמו.
--
--   INSERT — רק בשם עצמך (user_id = המשתמש הנוכחי). ה-API גם מוודא שאתם
--            מנהלי האירוע ושהעזרה פתוחה לו.
--
--   UPDATE — אדמין בלבד (שינוי סטטוס בידי הצוות).
--
--   DELETE — מי שכתב, בעל/ת האירוע (מחיקת אירוע מוחקת גם פניות של בן/בת
--            הזוג עליו — account.py::delete_event_cascade), ואדמין (מחיקת
--            משתמש). אין endpoint שמוחק פנייה בודדת.
-- ============================================================================

ALTER TABLE support_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_requests FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS support_requests_select ON support_requests;
CREATE POLICY support_requests_select ON support_requests FOR SELECT
  USING (user_id = app_current_user_id() OR app_is_admin());

DROP POLICY IF EXISTS support_requests_insert ON support_requests;
CREATE POLICY support_requests_insert ON support_requests FOR INSERT
  WITH CHECK (user_id = app_current_user_id());

DROP POLICY IF EXISTS support_requests_update ON support_requests;
CREATE POLICY support_requests_update ON support_requests FOR UPDATE
  USING (app_is_admin())
  WITH CHECK (app_is_admin());

DROP POLICY IF EXISTS support_requests_delete ON support_requests;
CREATE POLICY support_requests_delete ON support_requests FOR DELETE
  USING (
    user_id = app_current_user_id()
    OR app_is_admin()
    OR (event_id IS NOT NULL AND app_owns_event(event_id))
  );

GRANT SELECT, INSERT, UPDATE, DELETE ON support_requests TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE support_requests_id_seq TO veya_app;
