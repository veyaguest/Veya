-- ============================================================================
-- VEYA · Row Level Security · קובץ 6: טבלת call_logs (Call Center של האדמין)
-- ============================================================================
-- מריצים אחרי קבצים 1–5. idempotent (DROP POLICY IF EXISTS לפני כל CREATE),
-- אז אפשר להריץ שוב בבטחה.
--
-- מה הטבלה: תיעוד ניסיונות שיחת הטלפון שמבצע צוות VEYA מול מוזמנים, כחלק
-- מסבבי השיחות של Workflow אישורי ההגעה (ראו backend/app/call_center.py).
-- הטבלה נוצרת אוטומטית ע"י ``Base.metadata.create_all`` בעליית השרת, ולכן —
-- כמו event_messages בקובץ 5 — היא נולדת **בלי RLS ובלי מדיניות**. הקובץ
-- הזה סוגר את הפער.
--
-- מי אמור לגשת: ה-API עצמו מגביל את כל נקודות הקצה ל-``get_current_admin``,
-- כלומר אדמין בלבד. המדיניות כאן רחבה במעט יותר בכוונה — היא מיושרת ל-
-- ``messages`` (אותה משפחת נתונים: "מה נאמר למוזמן ומתי"), כדי שאם בעתיד
-- ייחשף מסך "היסטוריית שיחות" גם לבעל/ת האירוע, ה-RLS לא יהיה החסם השקט.
-- ההגבלה בפועל היום נאכפת בשכבת ה-API, וזו שכבת ההגנה העדינה.
--
-- בטוח להריץ על ייצור עם נתונים קיימים: כן. ENABLE/FORCE אינם נוגעים
-- בנתונים, ו-CREATE POLICY משפיע רק על תפקיד veya_app שאינו מחובר עדיין
-- בייצור (ראו RLS_REPORT.md).
--
-- ============================================================================
-- ‼️ סטטוס: PENDING — הקובץ מוכן להרצה, אך **טרם הורץ ולא נבדק מול DB חי**.
-- ============================================================================
-- החלטת בעלים (2026-08-19): לא מריצים DDL על Production
-- (פרויקט lcpvsbvfyoitklikwpwm), ולא מעבירים את המערכת ל-veya_app בשלב הזה.
--
-- למה לא נבדק: פרויקט ה-Staging שמוגדר ב-backend/.env.staging
-- (fxzsmekweranxhgumsif) **אינו קיים יותר** — ניסיון חיבור מחזיר
-- "FATAL: (ENOTFOUND) tenant/user ... not found". הרשת תקינה וה-pooler של
-- Supabase עונה; הפרויקט עצמו נמחק/מושהה. אין סביבת Postgres חלופית
-- (אין psql, אין Docker, אין supabase CLI בסביבת הפיתוח).
--
-- מה כן אומת, סטטית, ונאכף אוטומטית ב-tests/test_permission_alignment.py:
--   • רשימות ההרשאות בכל מדיניות זהות ל-app/permissions.py.
--   • ארבע המדיניויות קיימות, עם ENABLE + FORCE.
--   • כל פונקציית app_*() שהקובץ קורא לה מוגדרת ב-01_helpers_and_grants.sql.
--
-- מה לעשות כשיוקם Staging חדש (התסריט המלא כבר כתוב ומחכה):
--   1. psql "$STAGING_SUPERUSER_DATABASE_URL" -f backend/rls/06_call_logs_rls.sql
--   2. STAGING_BASE_URL=... STAGING_ADMIN_DB_URL=... \
--        python backend/tests/test_staging_rls.py
--      (סעיף "9b. Call Center + call_logs RLS" מכסה: קיום הטבלה, ENABLE/FORCE,
--       ארבע המדיניויות, אדמין קורא, בעל אירוע/מפיק/אנונימי חסומים,
--       אירוע A מול B, וניקוי בלי רשומות יתומות.)
--
-- הערכת סיכון בינתיים: בייצור ה-DATABASE_URL מחובר כ-postgres (superuser),
-- ו-superuser **עוקף RLS לחלוטין בכל הטבלאות** — לא רק כאן (ראו RLS_REPORT.md).
-- כלומר call_logs אינו חריג ואינו מוסיף חשיפה חדשה יחסית למצב הקיים. ההגנה
-- בפועל היום היא שכבת ה-API: כל נקודות הקצה של /admin/call-center מוגנות
-- ב-get_current_admin, ויש לכך כיסוי בדיקות מלא
-- (tests/test_call_center_isolation.py).
-- ============================================================================

ALTER TABLE call_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_logs FORCE  ROW LEVEL SECURITY;

-- SELECT — זהה ל-messages_select: מי שיכול "לדעת מה קרה מול המוזמנים".
DROP POLICY IF EXISTS call_logs_select ON call_logs;
CREATE POLICY call_logs_select ON call_logs FOR SELECT
  USING (app_has_any_event_permission(event_id, ARRAY['send_messages','view_reports','view_event']));

-- INSERT/UPDATE — תיעוד שיחה הוא פעולת תקשורת מול המוזמן, ולכן send_messages
-- בלבד (אדמין ובעלים תמיד עוברים דרך app_has_any_event_permission).
-- WITH CHECK על אותו event_id מונע "העברת" שורה לאירוע אחר.
DROP POLICY IF EXISTS call_logs_insert ON call_logs;
CREATE POLICY call_logs_insert ON call_logs FOR INSERT
  WITH CHECK (app_has_any_event_permission(event_id, ARRAY['send_messages']));

DROP POLICY IF EXISTS call_logs_update ON call_logs;
CREATE POLICY call_logs_update ON call_logs FOR UPDATE
  USING (app_has_any_event_permission(event_id, ARRAY['send_messages']))
  WITH CHECK (app_has_any_event_permission(event_id, ARRAY['send_messages']));

-- DELETE — נדרש בפועל בשני מסלולים קיימים:
--   • מחיקת אירוע/חשבון (app/account.py::delete_event_cascade)
--   • מחיקת מוזמן בודד (app/routers/guests.py::delete_guest)
-- הבעלים תמיד עובר (app_owns_event בתוך ההלפר), כך ששני המסלולים ממשיכים
-- לעבוד בלי שינוי.
DROP POLICY IF EXISTS call_logs_delete ON call_logs;
CREATE POLICY call_logs_delete ON call_logs FOR DELETE
  USING (app_has_any_event_permission(event_id, ARRAY['send_messages','edit_guests']));
