-- ============================================================================
-- VEYA · Row Level Security · קובץ 7: תפקיד "טלפן" (phone_agent)
-- ============================================================================
-- מריצים אחרי קבצים 1–6. idempotent (DROP ... IF EXISTS לפני כל CREATE),
-- אז אפשר להריץ שוב בבטחה.
--
-- מה הקובץ עושה:
--   1. מוסיף שתי פונקציות עזר: "האם המשתמש המחובר הוא טלפן" ו"האם הוקצה לו
--      האירוע הזה".
--   2. מפעיל RLS על הטבלה החדשה call_assignments (הקצאת אירוע לטלפן).
--   3. **מרחיב** את מדיניות call_logs מקובץ 6 כך שטלפן יוכל לקרוא ולכתוב
--      את יומן השיחות של האירועים שהוקצו לו — ורק אותם.
--
-- למה נדרש: טלפן אינו בעלים של האירוע ואינו ``event_member``, ולכן
-- ``app_has_any_event_permission`` מחזירה עבורו false בכל אירוע. תחת RLS חי,
-- בלי הקובץ הזה, כל תיעוד שיחה של טלפן היה נדחה ע"י ה-DB — למרות שה-API
-- מאשר אותו. זה הפער היחיד שהתפקיד החדש פותח בשכבת ה-DB.
--
-- ============================================================================
-- ‼️ סטטוס: PENDING — הקובץ מוכן להרצה, אך **טרם הורץ ולא נבדק מול DB חי**.
-- ============================================================================
-- אותה סיבה בדיוק כמו קובץ 6, ובהמשך ישיר להחלטת הבעלים (2026-08-19):
-- לא מריצים DDL על Production (פרויקט lcpvsbvfyoitklikwpwm), ופרויקט ה-
-- Staging שהיה מוגדר ב-backend/.env.staging אינו קיים יותר.
--
-- מה כן אומת סטטית:
--   • כל פונקציה שהקובץ קורא לה (app_current_user_id, app_is_admin,
--     app_has_any_event_permission) מוגדרת ב-01_helpers_and_grants.sql.
--   • המדיניות כאן **מרחיבה בלבד** ולא מצמצמת: כל מי שעבר קודם ממשיך לעבור
--     (התנאי הישן נשאר, נוסף OR).
--   • שכבת ה-API כבר אוכפת בדיוק את אותו כלל, עם כיסוי בדיקות מלא:
--     tests/test_phone_agent_permissions.py (10 בדיקות),
--     tests/test_phone_agent_scope.py (7 בדיקות).
--
-- מה לעשות כשיוקם Staging חדש:
--   1. psql "$STAGING_SUPERUSER_DATABASE_URL" -f backend/rls/07_phone_agent_rls.sql
--   2. STAGING_BASE_URL=... STAGING_ADMIN_DB_URL=... \
--        python backend/tests/test_staging_rls.py
--
-- הערכת סיכון בינתיים: בייצור ה-DATABASE_URL מחובר כ-postgres (superuser),
-- ו-superuser עוקף RLS לחלוטין בכל הטבלאות. כלומר הפער הזה אינו פעיל היום
-- ואינו מוסיף חשיפה — ההגנה בפועל היא שכבת ה-API (app/roles.py + EventAccess).
-- ============================================================================


-- ── 1. פונקציות עזר ─────────────────────────────────────────────────────────

-- האם המשתמש המחובר הוא טלפן. SECURITY DEFINER כי היא קוראת מטבלת users,
-- שמדיניות users_select מגבילה ל"אני רואה רק את עצמי" — כאן זו בדיוק אותה
-- שורה (המשתמש עצמו), אבל בהקשר שבו הקורא הוא מדיניות ולא שאילתת משתמש.
CREATE OR REPLACE FUNCTION app_is_phone_agent() RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT COALESCE(
    (SELECT account_type = 'phone_agent' FROM users WHERE id = app_current_user_id()),
    false
  );
$$;

-- האם האירוע הזה הוקצה לטלפן המחובר.
-- שימו לב לענף השני: טלפן **בלי אף הקצאה** מקבל גישה לכל האירועים — זה התור
-- המשותף של שלב א', בדיוק אותה סמנטיקה כמו app/call_center.py::visible_event_ids.
-- שתי האכיפות חייבות להישאר זהות; אם משנים אחת, משנים גם את השנייה.
CREATE OR REPLACE FUNCTION app_agent_assigned_to_event(target_event_id bigint)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT app_is_phone_agent() AND (
    EXISTS (
      SELECT 1 FROM call_assignments
      WHERE user_id = app_current_user_id() AND event_id = target_event_id
    )
    OR NOT EXISTS (
      SELECT 1 FROM call_assignments WHERE user_id = app_current_user_id()
    )
  );
$$;

GRANT EXECUTE ON FUNCTION app_is_phone_agent() TO veya_app;
GRANT EXECUTE ON FUNCTION app_agent_assigned_to_event(bigint) TO veya_app;


-- ── 2. call_assignments ─────────────────────────────────────────────────────

ALTER TABLE call_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_assignments FORCE  ROW LEVEL SECURITY;

-- קריאה: אדמין רואה הכול; טלפן רואה **רק את ההקצאות של עצמו** (הוא לא אמור
-- לדעת מי עוד עובד ועל מה). בעל אירוע אינו נוגע בטבלה הזו בכלל.
DROP POLICY IF EXISTS call_assignments_select ON call_assignments;
CREATE POLICY call_assignments_select ON call_assignments FOR SELECT
  USING (app_is_admin() OR user_id = app_current_user_id());

-- כתיבה/מחיקה: אדמין בלבד. ההקצאה היא החלטה ניהולית — טלפן לא מקצה לעצמו.
DROP POLICY IF EXISTS call_assignments_write ON call_assignments;
CREATE POLICY call_assignments_write ON call_assignments FOR ALL
  USING (app_is_admin())
  WITH CHECK (app_is_admin());


-- ── 3. הרחבת call_logs לטלפן ────────────────────────────────────────────────
-- כל התנאים הישנים מקובץ 6 נשארים מילה במילה; נוסף רק ``OR`` לטלפן מוקצה.
-- DELETE **לא** הורחב במכוון: טלפן מתעד שיחות, לא מוחק היסטוריה.

DROP POLICY IF EXISTS call_logs_select ON call_logs;
CREATE POLICY call_logs_select ON call_logs FOR SELECT
  USING (
    app_has_any_event_permission(event_id, ARRAY['send_messages','view_reports','view_event'])
    OR app_agent_assigned_to_event(event_id)
  );

DROP POLICY IF EXISTS call_logs_insert ON call_logs;
CREATE POLICY call_logs_insert ON call_logs FOR INSERT
  WITH CHECK (
    app_has_any_event_permission(event_id, ARRAY['send_messages'])
    OR app_agent_assigned_to_event(event_id)
  );

DROP POLICY IF EXISTS call_logs_update ON call_logs;
CREATE POLICY call_logs_update ON call_logs FOR UPDATE
  USING (
    app_has_any_event_permission(event_id, ARRAY['send_messages'])
    OR app_agent_assigned_to_event(event_id)
  )
  WITH CHECK (
    app_has_any_event_permission(event_id, ARRAY['send_messages'])
    OR app_agent_assigned_to_event(event_id)
  );


-- ── 4. guests / events — קריאה לטלפן ────────────────────────────────────────
-- מסך השיחות שולף שורות guests ו-events (שם, טלפון, כמות, תאריך האירוע).
-- תחת RLS חי, בלי ההרחבה הזו התור של הטלפן היה חוזר ריק תמיד.
-- ההרחבה היא **קריאה בלבד**: אין UPDATE ואין DELETE לטלפן על אף אחת מהן —
-- זה מה שאוכף ברמת ה-DB את הכלל "טלפן לא עורך מוזמן ולא משנה מספר טלפון".

DROP POLICY IF EXISTS guests_agent_select ON guests;
CREATE POLICY guests_agent_select ON guests FOR SELECT
  USING (app_agent_assigned_to_event(event_id));

DROP POLICY IF EXISTS events_agent_select ON events;
CREATE POLICY events_agent_select ON events FOR SELECT
  USING (app_agent_assigned_to_event(id));

-- מסך השיחות מציג גם את היסטוריית ההודעות של המוזמן (Timeline) — קריאה בלבד.
DROP POLICY IF EXISTS messages_agent_select ON messages;
CREATE POLICY messages_agent_select ON messages FOR SELECT
  USING (app_agent_assigned_to_event(event_id));

-- audit_logs: הטלפן **כותב** ליומן הפעילות של בעל/ת האירוע (המשפט בעברית
-- שמופיע ב-Feed), אך אינו קורא ממנו.
DROP POLICY IF EXISTS audit_logs_agent_insert ON audit_logs;
CREATE POLICY audit_logs_agent_insert ON audit_logs FOR INSERT
  WITH CHECK (event_id IS NOT NULL AND app_agent_assigned_to_event(event_id));
