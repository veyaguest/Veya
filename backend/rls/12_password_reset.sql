-- ============================================================================
-- VEYA · Row Level Security · קובץ 12: איפוס סיסמה עצמאי (public endpoint)
-- ============================================================================
-- מריצים אחרי קבצים 1–11. idempotent (CREATE OR REPLACE), אפשר להריץ שוב בבטחה.
--
-- אותה סיבה בדיוק כמו app_consume_email_verification (קובץ 9): ה-endpoint
-- ``POST /auth/reset-password`` הוא ציבורי במכוון (המשתמש לוחץ על קישור
-- שהתקבל במייל בלי להיות מחובר) — SELECT ישיר דרך ה-ORM לפי
-- password_reset_hash היה נחסם ע"י מדיניות users_select ("אני רואה רק את
-- עצמי"), כי אין עדיין זהות מחוברת (app_current_user_id() הוא NULL).
--
-- לפני שמריצים את הקובץ הזה: העמודות password_reset_hash (TEXT) ו-
-- password_reset_expires_at (TIMESTAMP) חייבות כבר להתווסף לטבלת users —
-- זה קורה אוטומטית בעליית השרת דרך app/main.py::_ensure_columns (ראו שם
-- _EXTRA_COLUMNS["users"]), בלי צורך בפעולה ידנית נוספת.
-- ============================================================================

-- מאתרת לפי hash של הטוקן, בודקת תוקף, ומבטלת אותו (חד-פעמי) — אטומית
-- (FOR UPDATE), כך שאי אפשר לממש את אותו טוקן פעמיים בבת-אחת מרוץ בין שתי
-- בקשות. מחזירה NULL אם הטוקן לא נמצא או פג. **לא** קובעת סיסמה חדשה —
-- זו אחריות ה-Python (routers/auth.py::reset_password), אחרי שהטוקן אומת.
CREATE OR REPLACE FUNCTION app_consume_password_reset(p_token_hash text)
RETURNS users
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  v_user users;
BEGIN
  SELECT * INTO v_user FROM users
   WHERE password_reset_hash = p_token_hash
   FOR UPDATE;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;
  IF v_user.password_reset_expires_at IS NOT NULL
     AND v_user.password_reset_expires_at <= now() THEN
    RETURN NULL;
  END IF;

  UPDATE users
     SET password_reset_hash = NULL,
         password_reset_expires_at = NULL
   WHERE id = v_user.id
   RETURNING * INTO v_user;

  RETURN v_user;
END;
$$;

GRANT EXECUTE ON FUNCTION app_consume_password_reset(text) TO veya_app;
