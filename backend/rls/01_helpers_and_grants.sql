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

-- ── 4. פונקציות עזר לתהליכי אימות (login/register) ─────────────────────────
-- למה צריך את זה: register/login מחפשים משתמש לפי אימייל *לפני* שיש זהות
-- מחוברת (app.current_user_id עדיין ריק) — מדיניות users_select הרגילה
-- ("אני רואה רק את עצמי") הייתה חוסמת את זה לגמרי ומונעת התחברות/הרשמה.
-- הפונקציות האלה SECURITY DEFINER — עוקפות RLS בכוונה, ומוגבלות בתפקיד
-- למה שממש צריך: שליפת שורת המשתמש לפי אימייל מדויק, לא שאילתה חופשית.
CREATE OR REPLACE FUNCTION app_user_by_email(p_email text)
RETURNS users
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT * FROM users WHERE email = p_email
$$;

-- אימוץ אירועים "יתומים" (בלי owner_id) בהרשמה — מיגרציה חד-פעמית מהמצב
-- הישן של אירוע יחיד בלי בעלים. משתמש חדש (לא-אדמין) לא יכול לראות/לעדכן
-- שורות כאלה תחת RLS רגיל (owner_id הוא NULL, לא שלו), אז זו פעולת מערכת
-- מפורשת ולא הסתמכות על UPDATE רגיל.
CREATE OR REPLACE FUNCTION app_adopt_orphan_events(p_user_id bigint)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public
AS $$
  UPDATE events SET owner_id = p_user_id WHERE owner_id IS NULL
$$;

-- ── 5. פונקציות עזר להרשאות מדויקות של חבר-אירוע (Producer/Venue) ──────────
-- למה צריך את זה מעבר ל-app_is_event_member: כדי שה-RLS יאכוף גם *אילו*
-- הרשאות ספציפיות ניתנו לחבר (permissions), לא רק "הוא חבר פעיל" — עקרון
-- least-privilege. שימו לב למגבלה: RLS הוא ברמת-שורה, לא ברמת-עמודה, אז
-- הרשאה ל-event_id נתון פותחת את כל השורה/הטבלה עבורו; בקרה עדינה יותר
-- (איזה שדה ספציפי מותר לערוך) נשארת באחריות שכבת ה-API (routers), כמו היום.
CREATE OR REPLACE FUNCTION app_member_permissions(p_event_id bigint)
RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT COALESCE(m.permissions::jsonb, '[]'::jsonb)
  FROM event_members m
  WHERE m.event_id = p_event_id
    AND m.user_id = app_current_user_id()
    AND m.status = 'active'
  LIMIT 1
$$;

-- האם למשתמש הנוכחי יש לפחות אחת מההרשאות המבוקשות על האירוע (או שהוא
-- אדמין/בעלים — להם תמיד גישה מלאה בלי קשר לרשימת ההרשאות).
CREATE OR REPLACE FUNCTION app_has_any_event_permission(p_event_id bigint, p_permissions text[])
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT app_is_admin()
      OR app_owns_event(p_event_id)
      OR app_member_permissions(p_event_id) ?| p_permissions
$$;

-- ── 6. פונקציות עזר ל-webhook ה-WhatsApp הנכנס (Meta) ───────────────────────
-- למה צריך את זה: ה-webhook הציבורי (messaging.py::receive_webhook) מקבל
-- קריאה ישירה מ-Meta, בלי משתמש מחובר ובלי guest_token (המזהה היחיד שיש לו
-- הוא מספר הטלפון של השולח). בלי הפונקציות האלה, תחת RLS: השאילתה שמנסה
-- לאתר מוזמן לפי טלפון תחזיר תמיד 0 שורות (app_current_user_id() ו-
-- app_current_guest_token() שניהם NULL), ותשובת ה-RSVP האמיתית מוואטסאפ
-- הייתה נעלמת בשקט (ה-webhook עוטף הכול ב-try/except כדי לא להחזיר שגיאה
-- ל-Meta) — כלומר אישורי הגעה אמיתיים דרך WhatsApp פשוט לא היו נרשמים.
-- SECURITY DEFINER מוגבל בכוונה: רק חיפוש-לפי-טלפון-מדויק ורק עדכון סטטוס
-- RSVP + רישום הודעה נכנסת — לא חשיפה/כתיבה כלליים.
CREATE OR REPLACE FUNCTION app_find_guest_by_phone(p_tail text)
RETURNS guests
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT * FROM guests
  WHERE p_tail <> ''
    AND right(regexp_replace(COALESCE(phone, ''), '\D', '', 'g'), 9) = p_tail
  LIMIT 1
$$;

CREATE OR REPLACE FUNCTION app_record_guest_rsvp_reply(
  p_guest_id bigint, p_status text, p_label text, p_provider text
)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public
AS $$
  WITH updated AS (
    UPDATE guests SET rsvp_status = p_status WHERE id = p_guest_id RETURNING event_id, id
  )
  INSERT INTO messages (event_id, guest_id, direction, kind, body, status, provider)
  SELECT event_id, id, 'inbound', 'reply', p_label, 'received', p_provider FROM updated
$$;

-- פונקציות העזר צריכות להיות זמינות להרצה ע"י תפקיד האפליקציה.
GRANT EXECUTE ON FUNCTION
  app_current_user_id(),
  app_current_guest_token(),
  app_is_admin(),
  app_owns_event(bigint),
  app_is_event_member(bigint),
  app_can_access_event(bigint),
  app_token_matches_event(bigint),
  app_user_by_email(text),
  app_adopt_orphan_events(bigint),
  app_member_permissions(bigint),
  app_has_any_event_permission(bigint, text[]),
  app_find_guest_by_phone(text),
  app_record_guest_rsvp_reply(bigint, text, text, text)
TO veya_app;
