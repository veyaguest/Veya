-- ============================================================================
-- VEYA · Row Level Security · קובץ 29: תיבת WhatsApp לשירות לקוחות
--   (whatsapp_threads, whatsapp_thread_messages)
-- ============================================================================
-- מריצים אחרי קבצים 1–28. idempotent (DROP + CREATE), אפשר להריץ שוב בבטחה.
-- נטען אוטומטית בעליית השרת (ראו ``_RLS_MIGRATION_FILES`` ב-main.py).
--
-- ‼️ תלות: ``app_current_user_id``, ``app_is_admin`` — קובץ 01.
--          ``app_is_phone_agent`` — קובץ 07.
--
-- ── מודל ההרשאות ────────────────────────────────────────────────────────
--
--   קריאה / כתיבה — צוות VEYA: אדמין, וגם טלפן (החלטת המייסד 2026-10-19:
--            גם הטלפנים עונים בתיבה). ה-API מצמצם עוד: אדמין צריך
--            ``inbox.view`` / ``inbox.handle`` (routers/admin_inbox.py).
--
--   מי שכתב (``whatsapp_threads.user_id``) — קריאה ומחיקה בלבד: מחיקת החשבון
--            שלו מוחקת את השיחות שלו (account.py → whatsapp_inbox.delete_for_user).
--            אין endpoint שמציג לו אותן.
--
--   הודעה נכנסת נכתבת מה-webhook — על חיבור המערכת (עוקף RLS), לא כאן.
-- ============================================================================

ALTER TABLE whatsapp_threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE whatsapp_threads FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS whatsapp_threads_select ON whatsapp_threads;
CREATE POLICY whatsapp_threads_select ON whatsapp_threads FOR SELECT
  USING (app_is_admin() OR app_is_phone_agent() OR user_id = app_current_user_id());

DROP POLICY IF EXISTS whatsapp_threads_insert ON whatsapp_threads;
CREATE POLICY whatsapp_threads_insert ON whatsapp_threads FOR INSERT
  WITH CHECK (app_is_admin() OR app_is_phone_agent());

DROP POLICY IF EXISTS whatsapp_threads_update ON whatsapp_threads;
CREATE POLICY whatsapp_threads_update ON whatsapp_threads FOR UPDATE
  USING (app_is_admin() OR app_is_phone_agent())
  WITH CHECK (app_is_admin() OR app_is_phone_agent());

DROP POLICY IF EXISTS whatsapp_threads_delete ON whatsapp_threads;
CREATE POLICY whatsapp_threads_delete ON whatsapp_threads FOR DELETE
  USING (app_is_admin() OR user_id = app_current_user_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON whatsapp_threads TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE whatsapp_threads_id_seq TO veya_app;


ALTER TABLE whatsapp_thread_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE whatsapp_thread_messages FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS whatsapp_thread_messages_select ON whatsapp_thread_messages;
CREATE POLICY whatsapp_thread_messages_select ON whatsapp_thread_messages FOR SELECT
  USING (
    app_is_admin() OR app_is_phone_agent()
    OR EXISTS (
      SELECT 1 FROM whatsapp_threads t
      WHERE t.id = whatsapp_thread_messages.thread_id AND t.user_id = app_current_user_id()
    )
  );

DROP POLICY IF EXISTS whatsapp_thread_messages_insert ON whatsapp_thread_messages;
CREATE POLICY whatsapp_thread_messages_insert ON whatsapp_thread_messages FOR INSERT
  WITH CHECK (app_is_admin() OR app_is_phone_agent());

DROP POLICY IF EXISTS whatsapp_thread_messages_update ON whatsapp_thread_messages;
CREATE POLICY whatsapp_thread_messages_update ON whatsapp_thread_messages FOR UPDATE
  USING (app_is_admin() OR app_is_phone_agent())
  WITH CHECK (app_is_admin() OR app_is_phone_agent());

DROP POLICY IF EXISTS whatsapp_thread_messages_delete ON whatsapp_thread_messages;
CREATE POLICY whatsapp_thread_messages_delete ON whatsapp_thread_messages FOR DELETE
  USING (
    app_is_admin()
    OR EXISTS (
      SELECT 1 FROM whatsapp_threads t
      WHERE t.id = whatsapp_thread_messages.thread_id AND t.user_id = app_current_user_id()
    )
  );

GRANT SELECT, INSERT, UPDATE, DELETE ON whatsapp_thread_messages TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE whatsapp_thread_messages_id_seq TO veya_app;
