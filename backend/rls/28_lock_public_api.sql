-- ============================================================================
-- VEYA · Row Level Security · קובץ 28: נעילת הגישה הציבורית (Supabase Data API)
-- ============================================================================
-- למה (2026-10-14): ב-Supabase, כל טבלה ופונקציה בסכמה public נחשפת דרך
-- /rest/v1 לתפקידים anon / authenticated — והמפתח הציבורי (anon) נמצא בקוד
-- האתר. בייצור נמצא ש-anon ו-authenticated יכלו להריץ את כל פונקציות
-- ה-SECURITY DEFINER (כולל app_register_user עם p_is_admin), ושלחלק מהטבלאות
-- אין RLS. הוסר public מ-"Exposed schemas" בדשבורד — הקובץ הזה מוודא שגם אם
-- הסכמה תיחשף שוב בטעות, אין לתפקידים האלה שום הרשאה בתוך ה-DB.
--
-- מה הקובץ עושה:
--   1. מסיר מ-anon ומ-authenticated כל הרשאה על טבלאות, רצפים ופונקציות
--      ב-public — גם לקיימות וגם לעתידיות (ALTER DEFAULT PRIVILEGES).
--   2. מסיר את הרשאת ההרצה הכללית (PUBLIC) מכל הפונקציות ב-public. ב-Postgres
--      כל פונקציה חדשה ניתנת להרצה ע"י כולם כברירת מחדל — זה המקור לחשיפה.
--   3. נותן ל-veya_app (התפקיד שהאפליקציה מתחברת איתו) הרשאת הרצה מפורשת על
--      כל הפונקציות — כך שהאפליקציה ממשיכה לעבוד בדיוק כמו קודם.
--
-- מה הקובץ **לא** עושה: לא מפעיל RLS על טבלאות ולא משנה מדיניות. זה שלב נפרד
-- (קבצים 06/07/13/20–27), כי הוא משנה את התנהגות האפליקציה תחת veya_app.
--
-- האפליקציה לא משתמשת ב-anon/authenticated לגישה לנתונים: הצד הקדמי משתמש
-- ב-Supabase להתחברות בלבד (supabase.auth), והשרת מתחבר ישירות ל-Postgres.
--
-- להריץ ב-Supabase → SQL Editor כ-postgres. idempotent — אפשר להריץ שוב.
-- נבדק מקומית: tests/test_rls_lock_public_api.py.
-- ============================================================================

-- ── 1. anon / authenticated: בלי שום הרשאה ב-public ─────────────────────────
-- התפקידים קיימים רק ב-Supabase; בסביבה בלעדיהם (Postgres מקומי) — מדלגים.
DO $$
DECLARE
  r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA public FROM %I', r);
      EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', r);
      EXECUTE format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM %I', r);
      EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON TABLES FROM %I', r);
      EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', r);
      EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM %I', r);
      -- גם ברמה הגלובלית (בלי IN SCHEMA): ברירת מחדל שהוגדרה גלובלית לא
      -- מוסרת ע"י REVOKE פר-סכמה.
      EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE postgres REVOKE ALL ON TABLES FROM %I', r);
      EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE postgres REVOKE ALL ON SEQUENCES FROM %I', r);
      EXECUTE format('ALTER DEFAULT PRIVILEGES FOR ROLE postgres REVOKE ALL ON FUNCTIONS FROM %I', r);
    END IF;
  END LOOP;
END
$$;

-- ── 2. פונקציות: לא "כולם" כברירת מחדל ──────────────────────────────────────
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
-- **גלובלי, בכוונה (בלי IN SCHEMA):** ההרשאה של PUBLIC להריץ כל פונקציה היא
-- ברירת מחדל מובנית של Postgres, וברירות מחדל פר-סכמה יכולות רק *להוסיף*
-- הרשאות — לא להסיר מובנות. בלי השורה הזו, כל פונקציה חדשה שתיווצר ב-public
-- (קובץ RLS עתידי) תהיה שוב פתוחה ל-anon. חל על פונקציות ש-postgres יוצר.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres
  REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- ── 3. האפליקציה (veya_app) ממשיכה להריץ את כל הפונקציות ─────────────────────
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO veya_app;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO veya_app;
