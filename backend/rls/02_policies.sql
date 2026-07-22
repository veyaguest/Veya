-- ============================================================================
-- VEYA · Row Level Security · קובץ 2/3: הפעלת RLS + מדיניות לכל טבלה
-- ============================================================================
-- מריצים *אחרי* קובץ 1. כל הפקודות idempotent (DROP POLICY IF EXISTS לפני כל
-- CREATE POLICY), אז אפשר להריץ שוב בבטחה.
--
-- חשוב להבנה: כל עוד השרת מחובר כ-postgres (superuser) — RLS *לא ישפיע*,
-- כי superuser עוקף אותו. ההגנה מופעלת בפועל רק כשמחליפים את DATABASE_URL
-- לחיבור veya_app. לכן אפשר להריץ את הקובץ הזה על הייצור בבטחה, ורק אז,
-- אחרי בדיקה, להחליף את החיבור. rollback = קובץ 3 / החזרת DATABASE_URL.
--
-- מוסכמות:
--   * ENABLE ROW LEVEL SECURITY  → מפעיל RLS על הטבלה (חל על תפקידים רגילים).
--   * FORCE  ROW LEVEL SECURITY  → מחיל אותו גם על בעל הטבלה (הגנה נוספת).
--   * טבלה עם RLS מופעל ובלי מדיניות תואמת = 0 שורות. לכן כל טבלה מוגנת
--     מקבלת מדיניות מפורשת.
-- ============================================================================

-- ── events ─────────────────────────────────────────────────────────────────
-- הערה על "כל ההרשאות הידועות": הרשימה למטה = כל המחרוזות מ-PLANNER_PERMISSIONS
-- ו-VENUE_PERMISSIONS (schemas.py). המשמעות: חבר-אירוע עם *לפחות הרשאה אחת*
-- שהוענקה לו רואה את פרטי האירוע הבסיסיים; חבר בלי אף הרשאה (permissions=[])
-- לא רואה כלום — עקרון least-privilege במקום "חבר פעיל" גורף. אם מוסיפים
-- הרשאה חדשה ב-schemas.py, יש לעדכן גם כאן.
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE events FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS events_select ON events;
CREATE POLICY events_select ON events FOR SELECT
  USING (
    app_has_any_event_permission(id, ARRAY[
      'view_event','view_guests','view_seating','view_reports',
      'edit_guests','manage_seating','send_messages',
      'edit_seating','manage_venue_data'
    ])
    OR app_token_matches_event(id)           -- נתיב אישור הגעה ציבורי
  );

DROP POLICY IF EXISTS events_insert ON events;
CREATE POLICY events_insert ON events FOR INSERT
  WITH CHECK (owner_id = app_current_user_id() OR app_is_admin());

-- עדכון: הבעלים/אדמין תמיד; חבר-אירוע רק אם יש לו הרשאה שדרכה endpoint
-- ספציפי כלשהו (לא event.py::update_event עצמו — זה owner-only באפליקציה,
-- ראו app/routers/event.py::_owner_only) כותב שדה על שורת האירוע:
--   • manage_seating/edit_seating/manage_venue_data — hall.py (table_positions/hall_elements)
--   • send_messages — automation.py activate_track/advance_track (rsvp_track_*),
--     messaging.py save_template (message_template)
--   • edit_guests — guests.py set_group_note (group_notes)
-- הרשימה הזו חייבת להישאר זהה ל-EVENTS_UPDATE ב-backend/app/permissions.py
-- (טסט אוטומטי מוודא זאת — ראו tests/test_permission_alignment.py).
-- מגבלה חשובה: RLS הוא ברמת-שורה, לא ברמת-עמודה — הרשאה זו פותחת עדכון על
-- כל השורה (כולל שמות בני הזוג וכו'), לא רק על השדה הרלוונטי. ה-API בפועל
-- (routers, דרך EventAccess עם הרשאה מדויקת לכל endpoint) חושף לחברים רק
-- את הפעולה הספציפית שמתאימה — וזו נשארת שכבת ההגנה העדינה בפועל; ה-RLS
-- כאן הוא רשת ביטחון נוספת.
DROP POLICY IF EXISTS events_update ON events;
CREATE POLICY events_update ON events FOR UPDATE
  USING (app_has_any_event_permission(id, ARRAY['manage_seating','edit_seating','manage_venue_data','send_messages','edit_guests']))
  WITH CHECK (app_has_any_event_permission(id, ARRAY['manage_seating','edit_seating','manage_venue_data','send_messages','edit_guests']));

DROP POLICY IF EXISTS events_delete ON events;
CREATE POLICY events_delete ON events FOR DELETE
  USING (app_owns_event(id) OR app_is_admin());

-- ── guests ─────────────────────────────────────────────────────────────────
-- קריאה: בעלים/אדמין תמיד; חבר-אירוע רק עם הרשאה שקשורה למוזמנים/הושבה
-- (גם צופה-הושבה-בלבד של אולם צריך לראות שמות, כדי לדעת מי יושב איפה).
-- כתיבה: רק מי שיש לו הרשאת עריכה בפועל (מפיק edit_guests/manage_seating,
-- או אולם עם edit_seating) — לא כל חבר-אירוע פעיל כמו שהיה קודם.
ALTER TABLE guests ENABLE ROW LEVEL SECURITY;
ALTER TABLE guests FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS guests_select ON guests;
CREATE POLICY guests_select ON guests FOR SELECT
  USING (
    app_has_any_event_permission(event_id, ARRAY[
      'view_guests','edit_guests','manage_seating','view_seating','edit_seating'
    ])
    OR guest_token = app_current_guest_token()  -- המוזמן רואה רק את השורה שלו
  );

DROP POLICY IF EXISTS guests_write ON guests;
CREATE POLICY guests_write ON guests FOR ALL
  USING (app_has_any_event_permission(event_id, ARRAY['edit_guests','manage_seating','edit_seating']))
  WITH CHECK (app_has_any_event_permission(event_id, ARRAY['edit_guests','manage_seating','edit_seating']));

-- עדכון ציבורי דרך הטוקן (המוזמן מסמן הגעה/כמות/הערה על השורה שלו בלבד).
DROP POLICY IF EXISTS guests_public_update ON guests;
CREATE POLICY guests_public_update ON guests FOR UPDATE
  USING (guest_token = app_current_guest_token())
  WITH CHECK (guest_token = app_current_guest_token());

-- ── messages ───────────────────────────────────────────────────────────────
-- קריאה: מותרת גם למי שרק צריך "לדעת מה קרה" (view_reports/view_event),
-- לא רק למי ששולח בפועל. כתיבה (שליחה/עדכון סטטוס): רק send_messages —
-- הרשאה שקיימת אצל מפיקים, לא אצל אולמות (VENUE_PERMISSIONS לא כוללת אותה),
-- כך שאולם לעולם לא יכול לשלוח הודעות בשם הזוג, גם אם ינסה לעקוף את ה-API.
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS messages_rw ON messages;

DROP POLICY IF EXISTS messages_select ON messages;
CREATE POLICY messages_select ON messages FOR SELECT
  USING (app_has_any_event_permission(event_id, ARRAY['send_messages','view_reports','view_event']));

DROP POLICY IF EXISTS messages_write ON messages;
CREATE POLICY messages_write ON messages FOR ALL
  USING (app_has_any_event_permission(event_id, ARRAY['send_messages']))
  WITH CHECK (app_has_any_event_permission(event_id, ARRAY['send_messages']));

-- המוזמן הציבורי כותב הודעת RSVP נכנסת (inbound) לאירוע שלו.
DROP POLICY IF EXISTS messages_public_insert ON messages;
CREATE POLICY messages_public_insert ON messages FOR INSERT
  WITH CHECK (app_token_matches_event(event_id));

-- ── clarifications ─────────────────────────────────────────────────────────
-- הבהרות שם עמום שייכות לתהליך ניהול המוזמנים/הושבה — לא רלוונטי לאולם.
ALTER TABLE clarifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE clarifications FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS clarifications_rw ON clarifications;
CREATE POLICY clarifications_rw ON clarifications FOR ALL
  USING (app_has_any_event_permission(event_id, ARRAY['edit_guests','manage_seating']))
  WITH CHECK (app_has_any_event_permission(event_id, ARRAY['edit_guests','manage_seating']));

-- ── automation_rules ───────────────────────────────────────────────────────
-- ניהול אוטומציית ה-WhatsApp — הרשאת send_messages בלבד (מפיק, לא אולם).
ALTER TABLE automation_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE automation_rules FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS automation_rules_rw ON automation_rules;
CREATE POLICY automation_rules_rw ON automation_rules FOR ALL
  USING (app_has_any_event_permission(event_id, ARRAY['send_messages']))
  WITH CHECK (app_has_any_event_permission(event_id, ARRAY['send_messages']));

-- ── message_templates ──────────────────────────────────────────────────────
ALTER TABLE message_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE message_templates FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS message_templates_rw ON message_templates;
CREATE POLICY message_templates_rw ON message_templates FOR ALL
  USING (app_has_any_event_permission(event_id, ARRAY['send_messages']))
  WITH CHECK (app_has_any_event_permission(event_id, ARRAY['send_messages']));

-- ── audit_logs ─────────────────────────────────────────────────────────────
-- קריאה: אדמין, או מי שיש לו גישה לאירוע. שורות ללא event_id (למשל ניסיון
-- כניסה עם טוקן לא תקין) — אדמין בלבד.
-- כתיבה: מותרת תמיד (יומן append-only; מי שכתב לא בהכרח יכול לקרוא). כך גם
-- הנתיב הציבורי וגם זרימת ההתחברות יכולים לתעד בלי חריגים מיוחדים.
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS audit_logs_select ON audit_logs;
CREATE POLICY audit_logs_select ON audit_logs FOR SELECT
  USING (
    app_is_admin()
    OR (event_id IS NOT NULL AND app_can_access_event(event_id))
  );

DROP POLICY IF EXISTS audit_logs_insert ON audit_logs;
CREATE POLICY audit_logs_insert ON audit_logs FOR INSERT
  WITH CHECK (true);

-- מחיקה: חסרה קודם! events.py::delete_event מוחק ידנית שורות audit_logs
-- לפני מחיקת האירוע (אין ON DELETE CASCADE בין audit_logs.event_id ל-events).
-- בלי מדיניות DELETE מפורשת, RLS+FORCE היו חוסמים את המחיקה בשקט (0 שורות
-- נמחקות), ואז ה-DELETE על events היה נכשל עם שגיאת foreign-key — כלומר
-- מחיקת אירוע הייתה נשברת לגמרי לכל משתמש, כולל הבעלים.
DROP POLICY IF EXISTS audit_logs_delete ON audit_logs;
CREATE POLICY audit_logs_delete ON audit_logs FOR DELETE
  USING (app_is_admin() OR (event_id IS NOT NULL AND app_owns_event(event_id)));

-- ── event_members ──────────────────────────────────────────────────────────
-- קריאה: אדמין, בעל האירוע, או החבר עצמו (רואה את שורת החברות שלו).
-- שינוי: אדמין או בעל האירוע בלבד.
ALTER TABLE event_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_members FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS event_members_select ON event_members;
CREATE POLICY event_members_select ON event_members FOR SELECT
  USING (
    app_is_admin()
    OR app_owns_event(event_id)
    OR user_id = app_current_user_id()
  );

DROP POLICY IF EXISTS event_members_write ON event_members;
CREATE POLICY event_members_write ON event_members FOR ALL
  USING (app_is_admin() OR app_owns_event(event_id))
  WITH CHECK (app_is_admin() OR app_owns_event(event_id));

-- ── users ──────────────────────────────────────────────────────────────────
-- קריאה/עדכון: המשתמש עצמו, או אדמין. הוספה (הרשמה) מותרת — היא אנונימית
-- מעצם טבעה (עדיין אין משתמש מחובר). מחיקה: אדמין בלבד.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE users FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS users_select ON users;
CREATE POLICY users_select ON users FOR SELECT
  USING (id = app_current_user_id() OR app_is_admin());

DROP POLICY IF EXISTS users_insert ON users;
CREATE POLICY users_insert ON users FOR INSERT
  WITH CHECK (true);

DROP POLICY IF EXISTS users_update ON users;
CREATE POLICY users_update ON users FOR UPDATE
  USING (id = app_current_user_id() OR app_is_admin())
  WITH CHECK (id = app_current_user_id() OR app_is_admin());

DROP POLICY IF EXISTS users_delete ON users;
CREATE POLICY users_delete ON users FOR DELETE
  USING (app_is_admin());

-- ── login_events ───────────────────────────────────────────────────────────
-- קריאה: המשתמש שלו, או אדמין. כתיבה: מותרת (append-only; נכתב בזמן התחברות
-- לפני שזהות ה-session מוזרקת).
ALTER TABLE login_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE login_events FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS login_events_select ON login_events;
CREATE POLICY login_events_select ON login_events FOR SELECT
  USING (user_id = app_current_user_id() OR app_is_admin());

DROP POLICY IF EXISTS login_events_insert ON login_events;
CREATE POLICY login_events_insert ON login_events FOR INSERT
  WITH CHECK (true);

-- ── טבלאות משותפות/ציבוריות: venues, veya_templates, veya_workflow_steps,
--    media_blobs ───────────────────────────────────────────────────────────
-- אלה תוכן מערכת/קטלוג ותמונות — לא נתונים פרטיים פר-משתמש. לא מפעילים עליהן
-- RLS כדי לא לשבור את הקטלוג הציבורי ואת הגשת התמונות (/media/<id>). כתיבה
-- אליהן ממילא מוגנת בשכבת ה-API (אדמין). אם בעתיד תרצו להגן על תמונות פרטיות,
-- זה השלב שבו נוסיף כאן מדיניות ייעודית.
