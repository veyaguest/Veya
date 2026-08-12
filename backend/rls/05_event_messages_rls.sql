-- ============================================================================
-- VEYA · RLS fix: event_messages (רצף "תקשורת עם אורחים" — הזמנה/תזכורות/
-- יום-האירוע/תודה, ראו app/communication.py). נמצא ע"י ביקורת 2026-08-12:
-- הטבלה נוספה אחרי סבב ה-RLS המקורי (02_policies.sql) ומעולם לא קיבלה
-- ENABLE ROW LEVEL SECURITY או שום CREATE POLICY — בניגוד לכל שאר הטבלאות
-- התלויות-אירוע (events/guests/messages/clarifications/automation_rules/
-- message_templates/event_members). Standalone, idempotent, נוגע רק ב-
-- event_messages. אל תשנה קבצים קודמים (01-04) — זה הקובץ המצטבר החדש.
--
-- מודל ההרשאות: **לא הומצא כאן שום דבר חדש**. event_messages כבר מוגן
-- היום ברמת ה-API (routers/communication.py) בדיוק ע"י אותם קבועים
-- שמגינים על טבלת messages:
--   _view  = EventAccess(permissions.MESSAGES_VIEW)   -- GET /communication/sequence...
--   _write = EventAccess(permissions.MESSAGES_WRITE)  -- PUT /communication/sequence/{type}
-- כלומר MESSAGES_VIEW=['send_messages','view_reports','view_event'] ו-
-- MESSAGES_WRITE=['send_messages'] — בדיוק ה-ARRAY-ים של messages_select/
-- messages_write הקיימים. המדיניות כאן ממשיכה בדיוק את אותו מודל.
--
-- למה 4 מדיניות נפרדות (SELECT/INSERT/UPDATE/DELETE) ולא FOR ALL אחד כמו
-- ב-messages_write: routers/communication.py::_get_sequence מפעילה את
-- provision_event_messages (INSERT של עד 6 שורות ברירת-מחדל) *גם* בתוך
-- GET /communication/sequence — כלומר גם קריאה בהרשאת-צפייה-בלבד
-- (view_event/view_reports, למשל אולם) יכולה להפעיל INSERT לגיטימי. FOR
-- ALL עם WITH CHECK מבוסס-send_messages-בלבד היה שובר את הקריאה הזו
-- לחברי-אירוע צופים-בלבד (500 על ה-GET הראשון של אירוע חדש). לכן INSERT
-- מורשה תחת MESSAGES_VIEW (בדיוק כמו SELECT) — זו לא "פרצה": זו בדיוק
-- הפעולה שה-API כבר מבצע בפועל עבור אותו קהל בדיוק, רק שה-DB מיישר קו
-- איתה. UPDATE/DELETE נשארים תחת MESSAGES_WRITE (send_messages בלבד),
-- מדויק ל-PUT /communication/sequence/{type} ולניקוי ב-account.py.
--
-- event_id אינו שדה ניתן לעריכה ב-schemas.EventMessageUpdate (רק
-- title/content/is_active/trigger_offset_days/target_audience) — אי אפשר
-- להעביר event_message לאירוע אחר דרך ה-API כלל. ה-WITH CHECK על UPDATE
-- כאן הוא הגנת-עומק בלבד למקרה של גישה גולמית ל-DB שעוקפת את ה-API.
--
-- השפעה על delete_event_cascade (app/account.py) ומחיקת חשבון: הבעלים
-- תמיד עובר את app_has_any_event_permission (app_owns_event OR-clause,
-- ראו 01_helpers_and_grants.sql) בלי קשר לאיזו רשימת הרשאות נבחרה — כלומר
-- ה-DELETE FROM event_messages שם ימשיך לעבוד בדיוק כמו היום, לכל בעלים
-- ולכל אדמין. לא נדרש שינוי קוד Python בכלל.
--
-- בטוח להריץ על ייצור עם נתונים קיימים: כן — כמו כל קובץ RLS קודם כאן,
-- ENABLE/FORCE אינם נוגעים בנתונים, ו-CREATE POLICY משפיע רק על תפקיד
-- veya_app שאינו מחובר עדיין בייצור (ראו RLS_REPORT.md: RLS מוכן אך לא
-- מופעל — DATABASE_URL עדיין superuser). DROP POLICY IF EXISTS מבטיח
-- אידמפוטנטיות אם צריך להריץ שוב.
--
-- מגבלת בדיקה: נכתב ואומת סטטית מול הקוד (routers/communication.py,
-- app/permissions.py, app/schemas.py) ומול test_permission_alignment.py —
-- **לא נבדק מול Postgres/Supabase חי** (אין Docker/psql/Supabase staging
-- בסביבת הפיתוח הזו, אותה מגבלה שכבר תועדה ב-RLS_REPORT.md לסבב הקודם).
-- לפני הפעלה בייצור יש לעבור את אותו תהליך Staging המתועד ב-STAGING_PLAN.md
-- (כולל את שני התרחישים הקריטיים כאן: GET /communication/sequence ע"י חבר
-- צופה-בלבד על אירוע חדש, ומחיקת אירוע/חשבון עם event_messages קיימים).
-- ============================================================================

ALTER TABLE event_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_messages FORCE  ROW LEVEL SECURITY;

-- SELECT — זהה ל-messages_select: כל מי שיכול "לדעת מה קורה" (MESSAGES_VIEW).
DROP POLICY IF EXISTS event_messages_select ON event_messages;
CREATE POLICY event_messages_select ON event_messages FOR SELECT
  USING (app_has_any_event_permission(event_id, ARRAY['send_messages','view_reports','view_event']));

-- INSERT — במכוון רחב יותר מ-messages_write (ראו הסבר למעלה): מכסה את
-- ה-provisioning האוטומטי שקורה בתוך GET /communication/sequence, שזמין
-- לכל מי שיש לו MESSAGES_VIEW ולא רק MESSAGES_WRITE.
DROP POLICY IF EXISTS event_messages_insert ON event_messages;
CREATE POLICY event_messages_insert ON event_messages FOR INSERT
  WITH CHECK (app_has_any_event_permission(event_id, ARRAY['send_messages','view_reports','view_event']));

-- UPDATE — זהה ל-messages_write: רק send_messages בפועל (PUT /communication/
-- sequence/{type}). WITH CHECK על אותו event_id מונע "העברת" שורה לאירוע אחר.
DROP POLICY IF EXISTS event_messages_update ON event_messages;
CREATE POLICY event_messages_update ON event_messages FOR UPDATE
  USING (app_has_any_event_permission(event_id, ARRAY['send_messages']))
  WITH CHECK (app_has_any_event_permission(event_id, ARRAY['send_messages']));

-- DELETE — זהה ל-messages_write: send_messages בלבד. הבעלים תמיד עובר
-- (app_owns_event), כך שמחיקת אירוע/חשבון (account.py::delete_event_cascade)
-- ממשיכה לעבוד בלי שינוי.
DROP POLICY IF EXISTS event_messages_delete ON event_messages;
CREATE POLICY event_messages_delete ON event_messages FOR DELETE
  USING (app_has_any_event_permission(event_id, ARRAY['send_messages']));
