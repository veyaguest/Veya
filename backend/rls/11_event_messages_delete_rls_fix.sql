-- ============================================================================
-- VEYA · RLS fix: event_messages_delete (תיקון ממוקד)
-- ============================================================================
-- נמצא ע"י שגיאת פרודקשן אמיתית (2026-08-21), דרך admin.py::delete_single_event
-- (DELETE /admin/events/23):
--
--   psycopg2.errors.ForeignKeyViolation: update or delete on table "events"
--   violates foreign key constraint "event_messages_event_id_fkey" on table
--   "event_messages" — DETAIL: Key is still referenced from table "event_messages".
--   SQL: DELETE FROM events WHERE events.id = %(id)s
--
-- app/account.py::delete_event_cascade **כן** מוחק את שורות event_messages
-- לפני שהוא מוחק את האירוע (נבדק ומאומת — ראו tests/test_account_delete.py,
-- וגם 05_event_messages_rls.sql שכבר מגדיר בדיוק את המדיניות הזו). אם למרות
-- זאת event_messages נשארות קיימות ברגע שה-DELETE FROM events רץ, ההסבר
-- הסביר ביותר הוא אותה מחלקת באג שכבר תוקנה פעמיים בסבב הזה (login_events,
-- audit_logs): מדיניות DELETE חסרה/לא-תואמת על event_messages ב-DB האמיתי
-- גורמת ל-DELETE FROM event_messages למחוק **0 שורות בשקט** (RLS+FORCE, בלי
-- שגיאה גלויה מ-Postgres) — וברגע שמגיעים ל-DELETE FROM events, השורות עדיין
-- שם ומפילות foreign-key violation. זו בדיוק התבנית שכבר אובחנה ותוקנה
-- ב-10_user_deletion_rls_fix.sql (login_events/audit_logs).
--
-- הקובץ הזה **לא ממציא מדיניות חדשה** — הוא רק מריץ מחדש (DROP+CREATE,
-- אידמפוטנטי) את אותה מדיניות ``event_messages_delete`` שכבר מוגדרת
-- ב-05_event_messages_rls.sql שורה 82-84, כדי לוודא שהיא באמת קיימת ותקינה
-- ב-DB האמיתי כרגע — בלי לגעת ב-3 המדיניות האחרות של הטבלה (select/insert/
-- update), שאין אינדיקציה שהן שבורות (מסך "תקשורת עם אורחים" עובד כרגיל).
--
-- USING (app_has_any_event_permission(event_id, ARRAY['send_messages'])):
-- מרחיב ל-app_is_admin() OR app_owns_event(event_id) OR הרשאת send_messages —
-- אדמין ובעל האירוע תמיד עוברים, בלי קשר לרשימת ההרשאות (ראו
-- 01_helpers_and_grants.sql: app_has_any_event_permission).
--
-- בטוח להריץ על ייצור עם נתונים קיימים: כן. DROP POLICY IF EXISTS לפני
-- CREATE — אידמפוטנטי, אפשר להריץ שוב בלי נזק. לא נוגע בנתונים, רק במדיניות.
-- ============================================================================

DROP POLICY IF EXISTS event_messages_delete ON event_messages;
CREATE POLICY event_messages_delete ON event_messages FOR DELETE
  USING (app_has_any_event_permission(event_id, ARRAY['send_messages']));
