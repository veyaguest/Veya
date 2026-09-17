-- 22 — תמונות אולמות. תוכן קטלוג (כמו venues ו-media_blobs): קריאה פתוחה,
-- כתיבה לאדמין בלבד — גם ברמת המסד, לא רק ב-API.
ALTER TABLE venue_images ENABLE ROW LEVEL SECURITY;
ALTER TABLE venue_images FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS venue_images_select ON venue_images;
CREATE POLICY venue_images_select ON venue_images FOR SELECT USING (true);
DROP POLICY IF EXISTS venue_images_write ON venue_images;
CREATE POLICY venue_images_write ON venue_images FOR ALL
  USING (app_is_admin()) WITH CHECK (app_is_admin());
GRANT SELECT, INSERT, UPDATE, DELETE ON venue_images TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE venue_images_id_seq TO veya_app;
