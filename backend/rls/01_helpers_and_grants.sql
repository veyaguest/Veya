-- ============================================================================
-- VEYA · Row Level Security · קובץ 1/3: תפקיד האפליקציה, הרשאות ופונקציות עזר
-- ============================================================================
-- מה הקובץ הזה עושה (בעברית פשוטה):
--   1. יוצר תפקיד DB חדש (veya_app) שאיננו superuser. זה קריטי: החיבור
--      הנוכחי כ-postgres הוא superuser, ו-superuser *עוקף* RLS לחלוטין. רק
--      תפקיד רגיל כפוף למדיניות. אחרי שמריצים את הקובץ הזה, מחליפים את
--      DATABASE_URL בשרת לחיבור עם veya_app (ראו הוראות בקובץ הריצה/הצ'אט).
--   2. נותן ל-veya_app הרשאות עבודה רגילות על הטבלאות (SELECT/INSERT/UPDATE/
--      DELETE) — בלי זה התפקיד לא יכול לעשות כלום. ה-RLS הוא זה שמצמצם *אילו
--      שורות* הוא רואה, לא *אם* יש לו גישה בכלל.
--   3. יוצר פונקציות עזר שהמדיניות (קובץ 2) משתמשת בהן. הן מוגדרות
--      SECURITY DEFINER ובבעלות postgres — כלומר הן רצות בהרשאות-על ועוקפות
--      RLS *בתוך הפונקציה בלבד*. זה מונע "recursion" (מדיניות שקוראת לטבלה
--      שיש עליה מדיניות שקוראת שוב לאותה טבלה...) ושומר על המדיניות פשוטה.
--
-- להריץ ב-Supabase → SQL Editor, כשמחוברים כ-postgres. אפשר להריץ שוב ושוב
-- (idempotent): הכול כתוב עם IF NOT EXISTS / CREATE OR REPLACE.
--
-- אזהרה: אל תריצו את זה על ה-DB של הייצור לפני שקראתם את מדריך הריצה
-- ואישרתם. הפעלת RLS בפועל מתרחשת בקובץ 2 + החלפת DATABASE_URL.
-- ============================================================================

-- ── 1. תפקיד האפליקציה (לא-superuser) ───────────────────────────────────────
-- החליפו 'CHANGE_ME_STRONG_PASSWORD' בסיסמה חזקה ואקראית לפני ההרצה, ושמרו
-- אותה — היא תיכנס ל-DATABASE_URL של השרת.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'veya_app') THEN
    CREATE ROLE veya_app LOGIN PASSWORD 'CHANGE_ME_STRONG_PASSWORD';
  END IF;
END
$$;

-- הרשאות עבודה בסיסיות. veya_app אינו בעל הטבלאות (postgres הוא הבעלים),
-- לכן RLS ייאכף עליו אוטומטית ברגע שנפעיל אותו בקובץ 2.
GRANT USAGE ON SCHEMA public TO veya_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO veya_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO veya_app;

-- טבלאות/רצפים עתידיים יקבלו את אותן הרשאות אוטומטית.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO veya_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO veya_app;

-- ── 2. פונקציות עזר לזהות הבקשה ─────────────────────────────────────────────
-- מזהה המשתמש המחובר, נשלף ממשתנה ה-session שהאפליקציה מזריקה בכל טרנזקציה
-- (ראו backend/app/database.py). מחזיר NULL כשאין משתמש (למשל נתיב ציבורי).
CREATE OR REPLACE FUNCTION app_current_user_id()
RETURNS bigint
LANGUAGE sql STABLE
AS $$
  SELECT NULLIF(current_setting('app.current_user_id', true), '')::bigint
$$;

-- טוקן המוזמן בנתיב אישור ההגעה הציבורי (/confirm/{token}). מוזרק ע"י
-- confirm.py. מחזיר NULL כשלא הוגדר.
CREATE OR REPLACE FUNCTION app_current_guest_token()
RETURNS text
LANGUAGE sql STABLE
AS $$
  SELECT NULLIF(current_setting('app.guest_token', true), '')
$$;

-- ── 3. פונקציות עזר להרשאות (SECURITY DEFINER = עוקפות RLS פנימית) ──────────
-- האם המשתמש הנוכחי הוא אדמין-על.
CREATE OR REPLACE FUNCTION app_is_admin()
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM users u
    WHERE u.id = app_current_user_id() AND u.is_admin
  )
$$;

-- האם המשתמש הנוכחי הוא הבעלים של האירוע.
CREATE OR REPLACE FUNCTION app_owns_event(p_event_id bigint)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM events e
    WHERE e.id = p_event_id AND e.owner_id = app_current_user_id()
  )
$$;

-- האם המשתמש הנוכחי הוא חבר-אירוע פעיל (מפיק/אולם שהוזמן לאירוע).
CREATE OR REPLACE FUNCTION app_is_event_member(p_event_id bigint)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM event_members m
    WHERE m.event_id = p_event_id
      AND m.user_id = app_current_user_id()
      AND m.status = 'active'
  )
$$;

-- הרשאת גישה כללית לאירוע: אדמין, או בעלים, או חבר פעיל. זו הבדיקה
-- המרכזית שכל הטבלאות התלויות-באירוע (guests, messages וכו') משתמשות בה.
CREATE OR REPLACE FUNCTION app_can_access_event(p_event_id bigint)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT app_is_admin()
      OR app_owns_event(p_event_id)
      OR app_is_event_member(p_event_id)
$$;

-- האם קיים באירוע מוזמן שהטוקן הציבורי הנוכחי שייך לו. משמש כדי לאפשר
-- לנתיב אישור ההגעה הציבורי לקרוא את פרטי האירוע ולכתוב הודעת RSVP.
CREATE OR REPLACE FUNCTION app_token_matches_event(p_event_id bigint)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT app_current_guest_token() IS NOT NULL
     AND EXISTS (
       SELECT 1 FROM guests g
       WHERE g.event_id = p_event_id
         AND g.guest_token = app_current_guest_token()
     )
$$;

-- פונקציות העזר צריכות להיות זמינות להרצה ע"י תפקיד האפליקציה.
GRANT EXECUTE ON FUNCTION
  app_current_user_id(),
  app_current_guest_token(),
  app_is_admin(),
  app_owns_event(bigint),
  app_is_event_member(bigint),
  app_can_access_event(bigint),
  app_token_matches_event(bigint)
TO veya_app;
