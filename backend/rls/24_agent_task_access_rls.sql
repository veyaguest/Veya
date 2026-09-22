-- 24 — גישת טלפן לפי משימה (call_tasks), לא רק לפי אירוע.
--
-- מאז שהטלפן עובד על משימות שהוקצו לו אישית, הוא צריך לקרוא את האורח, את
-- האירוע ואת ההודעות של האורחים שיש לו משימה עליהם, לעדכן את אישור ההגעה של
-- האורח הזה (תוצאת שיחה עוברת דרך rsvp_response), ולתעד שיחה. המדיניות כאן
-- **מתווספת** (PERMISSIVE — OR) לזו של 07; היא לא מרחיבה גישה למי שאין לו
-- משימה, ואינה נוגעת בבעלי אירוע/חברי אירוע.

CREATE OR REPLACE FUNCTION app_agent_has_task_for_event(target_event_id bigint)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT app_is_phone_agent() AND EXISTS (
    SELECT 1 FROM call_tasks
    WHERE event_id = target_event_id AND assignee_id = app_current_user_id()
  );
$$;

CREATE OR REPLACE FUNCTION app_agent_has_task_for_guest(target_guest_id bigint)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT app_is_phone_agent() AND EXISTS (
    SELECT 1 FROM call_tasks
    WHERE guest_id = target_guest_id AND assignee_id = app_current_user_id()
  );
$$;

GRANT EXECUTE ON FUNCTION app_agent_has_task_for_event(bigint) TO veya_app;
GRANT EXECUTE ON FUNCTION app_agent_has_task_for_guest(bigint) TO veya_app;

DROP POLICY IF EXISTS guests_agent_task_select ON guests;
CREATE POLICY guests_agent_task_select ON guests FOR SELECT
  USING (app_agent_has_task_for_guest(id));

DROP POLICY IF EXISTS guests_agent_task_update ON guests;
CREATE POLICY guests_agent_task_update ON guests FOR UPDATE
  USING (app_agent_has_task_for_guest(id))
  WITH CHECK (app_agent_has_task_for_guest(id));

DROP POLICY IF EXISTS events_agent_task_select ON events;
CREATE POLICY events_agent_task_select ON events FOR SELECT
  USING (app_agent_has_task_for_event(id));

DROP POLICY IF EXISTS messages_agent_task_select ON messages;
CREATE POLICY messages_agent_task_select ON messages FOR SELECT
  USING (guest_id IS NOT NULL AND app_agent_has_task_for_guest(guest_id));

DROP POLICY IF EXISTS call_logs_agent_task_select ON call_logs;
CREATE POLICY call_logs_agent_task_select ON call_logs FOR SELECT
  USING (app_agent_has_task_for_guest(guest_id));

DROP POLICY IF EXISTS call_logs_agent_task_insert ON call_logs;
CREATE POLICY call_logs_agent_task_insert ON call_logs FOR INSERT
  WITH CHECK (app_agent_has_task_for_guest(guest_id));

DROP POLICY IF EXISTS audit_logs_agent_task_insert ON audit_logs;
CREATE POLICY audit_logs_agent_task_insert ON audit_logs FOR INSERT
  WITH CHECK (event_id IS NOT NULL AND app_agent_has_task_for_event(event_id));

-- call_round_controls: הטלפן צריך לדעת אם הסבב של המשימה שלו מושהה.
DROP POLICY IF EXISTS call_round_controls_agent_task_select ON call_round_controls;
CREATE POLICY call_round_controls_agent_task_select ON call_round_controls FOR SELECT
  USING (app_agent_has_task_for_event(event_id));
