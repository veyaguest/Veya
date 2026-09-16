-- 20 — מרכז שליטה בטלפנים: משימות שיחה, זמינות טלפנים, שליטה בסבבים.
--
-- call_tasks: אדמין הכול. טלפן — משימות שהוקצו לו, או משימות פנויות באירועים
-- שלו (אותו כלל של call_logs, app_agent_assigned_to_event). בעלי האירוע —
-- קריאה ומחיקה בלבד (מחיקת מוזמן/אירוע מנקה את המשימות שלו).

ALTER TABLE call_tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_tasks FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS call_tasks_select ON call_tasks;
CREATE POLICY call_tasks_select ON call_tasks FOR SELECT
  USING (
    app_is_admin()
    OR assignee_id = app_current_user_id()
    OR app_agent_assigned_to_event(event_id)
    OR app_has_any_event_permission(event_id, ARRAY['send_messages','edit_guests','view_reports','view_event'])
  );

DROP POLICY IF EXISTS call_tasks_insert ON call_tasks;
CREATE POLICY call_tasks_insert ON call_tasks FOR INSERT
  WITH CHECK (app_is_admin() OR app_agent_assigned_to_event(event_id));

DROP POLICY IF EXISTS call_tasks_update ON call_tasks;
CREATE POLICY call_tasks_update ON call_tasks FOR UPDATE
  USING (app_is_admin() OR assignee_id = app_current_user_id() OR app_agent_assigned_to_event(event_id))
  WITH CHECK (app_is_admin() OR assignee_id = app_current_user_id() OR app_agent_assigned_to_event(event_id));

DROP POLICY IF EXISTS call_tasks_delete ON call_tasks;
CREATE POLICY call_tasks_delete ON call_tasks FOR DELETE
  USING (app_is_admin() OR app_has_any_event_permission(event_id, ARRAY['send_messages','edit_guests']));

GRANT SELECT, INSERT, UPDATE, DELETE ON call_tasks TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE call_tasks_id_seq TO veya_app;

-- caller_profiles: אדמין הכול; טלפן רואה את השורה של עצמו בלבד.
ALTER TABLE caller_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE caller_profiles FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS caller_profiles_select ON caller_profiles;
CREATE POLICY caller_profiles_select ON caller_profiles FOR SELECT
  USING (app_is_admin() OR user_id = app_current_user_id());

DROP POLICY IF EXISTS caller_profiles_write ON caller_profiles;
CREATE POLICY caller_profiles_write ON caller_profiles FOR ALL
  USING (app_is_admin()) WITH CHECK (app_is_admin());

GRANT SELECT, INSERT, UPDATE, DELETE ON caller_profiles TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE caller_profiles_id_seq TO veya_app;

-- call_round_controls: כתיבה לאדמין; קריאה גם לטלפן של האירוע ולבעלי האירוע.
ALTER TABLE call_round_controls ENABLE ROW LEVEL SECURITY;
ALTER TABLE call_round_controls FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS call_round_controls_select ON call_round_controls;
CREATE POLICY call_round_controls_select ON call_round_controls FOR SELECT
  USING (
    app_is_admin() OR app_agent_assigned_to_event(event_id)
    OR app_has_any_event_permission(event_id, ARRAY['send_messages','edit_guests','view_reports','view_event'])
  );

DROP POLICY IF EXISTS call_round_controls_admin ON call_round_controls;
CREATE POLICY call_round_controls_admin ON call_round_controls FOR ALL
  USING (app_is_admin()) WITH CHECK (app_is_admin());

DROP POLICY IF EXISTS call_round_controls_owner_delete ON call_round_controls;
CREATE POLICY call_round_controls_owner_delete ON call_round_controls FOR DELETE
  USING (app_has_any_event_permission(event_id, ARRAY['send_messages','edit_guests']));

GRANT SELECT, INSERT, UPDATE, DELETE ON call_round_controls TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE call_round_controls_id_seq TO veya_app;
