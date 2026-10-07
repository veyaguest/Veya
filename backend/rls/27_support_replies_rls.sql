-- ============================================================================
-- VEYA · Row Level Security · קובץ 27: תשובות הצוות לפניות (support_replies)
-- ============================================================================
-- מריצים אחרי קבצים 1–26. idempotent (DROP + CREATE), אפשר להריץ שוב בבטחה.
-- נטען אוטומטית בעליית השרת (ראו ``_RLS_MIGRATION_FILES`` ב-main.py).
--
-- ‼️ תלות: ``app_current_user_id``, ``app_is_admin`` — קובץ 01.
--          ``support_requests`` ומדיניות שלה — קובץ 25.
--
-- ── מודל ההרשאות ────────────────────────────────────────────────────────
--
--   INSERT / UPDATE — אדמין בלבד (מסך "פניות תמיכה"; ה-API גם דורש
--            ``support.handle``).
--
--   SELECT — אדמין, ומי שכתב את הפנייה: אלה התשובות שנשלחו אליו במייל, והן
--            נכללות בייצוא המידע האישי שלו. ב-Postgres גם DELETE דורש
--            שהשורה תהיה גלויה ב-SELECT — ולכן זה תנאי למחיקת החשבון.
--
--   DELETE — אדמין, ומי שכתב את הפנייה (מחיקת החשבון / האירוע שלו —
--            account.py). אין endpoint שמוחק תשובה בודדת.
--
--   הבדיקה "מי כתב את הפנייה" רצה על support_requests עצמה, ולכן כפופה
--   למדיניות של קובץ 25 — אותה ראות בדיוק, לא רחבה ממנה.
-- ============================================================================

ALTER TABLE support_replies ENABLE ROW LEVEL SECURITY;
ALTER TABLE support_replies FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS support_replies_select ON support_replies;
CREATE POLICY support_replies_select ON support_replies FOR SELECT
  USING (
    app_is_admin()
    OR EXISTS (
      SELECT 1 FROM support_requests r
      WHERE r.id = support_replies.request_id AND r.user_id = app_current_user_id()
    )
  );

DROP POLICY IF EXISTS support_replies_insert ON support_replies;
CREATE POLICY support_replies_insert ON support_replies FOR INSERT
  WITH CHECK (app_is_admin());

DROP POLICY IF EXISTS support_replies_update ON support_replies;
CREATE POLICY support_replies_update ON support_replies FOR UPDATE
  USING (app_is_admin())
  WITH CHECK (app_is_admin());

DROP POLICY IF EXISTS support_replies_delete ON support_replies;
CREATE POLICY support_replies_delete ON support_replies FOR DELETE
  USING (
    app_is_admin()
    OR EXISTS (
      SELECT 1 FROM support_requests r
      WHERE r.id = support_replies.request_id AND r.user_id = app_current_user_id()
    )
  );

GRANT SELECT, INSERT, UPDATE, DELETE ON support_replies TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE support_replies_id_seq TO veya_app;
