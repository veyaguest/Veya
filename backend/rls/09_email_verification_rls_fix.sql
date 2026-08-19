-- ============================================================================
-- VEYA · Row Level Security · קובץ 9: תיקון אימות כתובת מייל (public endpoint)
-- ============================================================================
-- מריצים אחרי קבצים 1–8. idempotent (CREATE OR REPLACE), אפשר להריץ שוב בבטחה.
--
-- התקלה שהתגלתה בייצור: לחיצה על קישור אימות תקין החזירה תמיד "הקישור לאימות
-- כבר לא תקף", גם עם טוקן תקף לגמרי. הסיבה: ``/auth/verify-email/confirm``
-- הוא endpoint **ציבורי במכוון** (המשתמש עשוי ללחוץ על הקישור בלי להיות
-- מחובר) — ``app/auth.py::consume_email_verification`` עשה SELECT ישיר דרך
-- ה-ORM על ``users`` לפי ``email_verification_hash``, בלי זהות מחוברת.
-- מדיניות ``users_select`` ("אני רואה רק את עצמי") סיננה 0 שורות תמיד, בלי
-- קשר אם הטוקן תקין — בדיוק אותה משפחת בעיה שכבר נפתרה עבור register/login
-- (``app_register_user``/``app_user_by_email``) ועבור הצטרפות לאירוע
-- (``app_accept_partner_invitation``, קובץ 8) — הפונקציה הזו פשוט לא קיבלה
-- את אותו טיפול כשנכתבה.
--
-- ============================================================================
-- ‼️ סטטוס: PENDING — הקובץ מוכן להרצה, אך **טרם הורץ ולא נבדק מול DB חי**.
-- להריץ ב-Supabase → SQL Editor כשמחוברים כ-postgres.
-- ============================================================================

-- מאתרת לפי hash של הטוקן, בודקת תוקף, ומסמנת כמאומת — אטומית (FOR UPDATE),
-- כך שאי אפשר לממש את אותו טוקן פעמיים בבת-אחת מרוץ בין שתי בקשות. מחזירה
-- NULL אם הטוקן לא נמצא או פג — הקורא ב-Python מבחין בין המקרים בעצמו.
CREATE OR REPLACE FUNCTION app_consume_email_verification(p_token_hash text)
RETURNS users
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  v_user users;
BEGIN
  SELECT * INTO v_user FROM users
   WHERE email_verification_hash = p_token_hash
   FOR UPDATE;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;
  IF v_user.email_verification_expires_at IS NOT NULL
     AND v_user.email_verification_expires_at <= now() THEN
    RETURN NULL;
  END IF;

  UPDATE users
     SET email_verified_at = now(),
         email_verification_hash = NULL,
         email_verification_expires_at = NULL
   WHERE id = v_user.id
   RETURNING * INTO v_user;

  RETURN v_user;
END;
$$;

GRANT EXECUTE ON FUNCTION app_consume_email_verification(text) TO veya_app;
