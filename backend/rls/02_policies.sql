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
ALTER TABLE events ENABLE ROW LEVEL SECURITY;
ALTER TABLE events FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS events_select ON events;
CREATE POLICY events_select ON events FOR SELECT
  USING (
    app_can_access_event(id)                 -- אדמין / בעלים / חבר פעיל
    OR app_token_matches_event(id)           -- נתיב אישור הגעה ציבורי
  );

DROP POLICY IF EXISTS events_insert ON events;
CREATE POLICY events_insert ON events FOR INSERT
  WITH CHECK (owner_id = app_current_user_id() OR app_is_admin());

DROP POLICY IF EXISTS events_update ON events;
CREATE POLICY events_update ON events FOR UPDATE
  USING (app_owns_event(id) OR app_is_admin())
  WITH CHECK (app_owns_event(id) OR app_is_admin());

DROP POLICY IF EXISTS events_delete ON events;
CREATE POLICY events_delete ON events FOR DELETE
  USING (app_owns_event(id) OR app_is_admin());

-- ── guests ─────────────────────────────────────────────────────────────────
ALTER TABLE guests ENABLE ROW LEVEL SECURITY;
ALTER TABLE guests FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS guests_select ON guests;
CREATE POLICY guests_select ON guests FOR SELECT
  USING (
    app_can_access_event(event_id)
    OR guest_token = app_current_guest_token()  -- המוזמן רואה רק את השורה שלו
  );

-- כתיבה של בעלי-הרשאה על האירוע (הוספה/עריכה/מחיקה מהמערכת המנוהלת).
DROP POLICY IF EXISTS guests_write ON guests;
CREATE POLICY guests_write ON guests FOR ALL
  USING (app_can_access_event(event_id))
  WITH CHECK (app_can_access_event(event_id));

-- עדכון ציבורי דרך הטוקן (המוזמן מסמן הגעה/כמות/הערה על השורה שלו בלבד).
DROP POLICY IF EXISTS guests_public_update ON guests;
CREATE POLICY guests_public_update ON guests FOR UPDATE
  USING (guest_token = app_current_guest_token())
  WITH CHECK (guest_token = app_current_guest_token());

-- ── messages ───────────────────────────────────────────────────────────────
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS messages_rw ON messages;
CREATE POLICY messages_rw ON messages FOR ALL
  USING (app_can_access_event(event_id))
  WITH CHECK (app_can_access_event(event_id));

-- המוזמן הציבורי כותב הודעת RSVP נכנסת (inbound) לאירוע שלו.
DROP POLICY IF EXISTS messages_public_insert ON messages;
CREATE POLICY messages_public_insert ON messages FOR INSERT
  WITH CHECK (app_token_matches_event(event_id));

-- ── clarifications ─────────────────────────────────────────────────────────
ALTER TABLE clarifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE clarifications FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS clarifications_rw ON clarifications;
CREATE POLICY clarifications_rw ON clarifications FOR ALL
  USING (app_can_access_event(event_id))
  WITH CHECK (app_can_access_event(event_id));

-- ── automation_rules ───────────────────────────────────────────────────────
ALTER TABLE automation_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE automation_rules FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS automation_rules_rw ON automation_rules;
CREATE POLICY automation_rules_rw ON automation_rules FOR ALL
  USING (app_can_access_event(event_id))
  WITH CHECK (app_can_access_event(event_id));

-- ── message_templates ──────────────────────────────────────────────────────
ALTER TABLE message_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE message_templates FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS message_templates_rw ON message_templates;
CREATE POLICY message_templates_rw ON message_templates FOR ALL
  USING (app_can_access_event(event_id))
  WITH CHECK (app_can_access_event(event_id));

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
