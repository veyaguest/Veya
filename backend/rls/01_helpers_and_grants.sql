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
  INSERT INTO messages (event_id, guest_id, direction, kind, body, status, provider, channel)
  SELECT event_id, id, 'inbound', 'reply', p_label, 'received', p_provider, 'whatsapp' FROM updated
$$;

-- ── 7. פונקציות עזר ל-INSERT ...RETURNING לפני/בלי זהות מספיקה ──────────────
-- התגלה בבדיקת Staging אמיתית (לא ניתן היה לגלות מול SQLite): Postgres
-- דורש, בכל INSERT עם RETURNING (וזה מה שכל ORM INSERT של SQLAlchemy עושה
-- כברירת מחדל כדי לקבל id/created_at) — שהשורה החדשה תעבור גם את מדיניות
-- ה-SELECT של הטבלה, לא רק את ה-WITH CHECK של מדיניות ה-INSERT. כשהזהות
-- הנוכחית (app_current_user_id) היא NULL (הרשמה, כניסה) או guest_token
-- בלבד (מוזמן אנונימי בדף האישור) — מדיניות ה-SELECT (שדורשת admin/owner/
-- חבר-אירוע עם הרשאה) נכשלת, וה-INSERT כולו נדחה עם השגיאה "new row
-- violates row-level security policy", גם אם ה-INSERT-policy עצמה (WITH
-- CHECK) הייתה מרשה זאת. הפונקציות הבאות עוקפות את זה באותה דרך כמו
-- הפונקציות למעלה: SECURITY DEFINER, בעלות scope מוגבל בכוונה.
CREATE OR REPLACE FUNCTION app_register_user(
  p_email text, p_password_hash text, p_display_name text, p_phone text,
  p_is_admin boolean, p_account_type text
)
RETURNS users
LANGUAGE sql SECURITY DEFINER SET search_path = public
AS $$
  INSERT INTO users (email, password_hash, display_name, phone, is_admin, account_type, disabled, token_version)
  VALUES (p_email, p_password_hash, p_display_name, p_phone, p_is_admin, p_account_type, false, 1)
  RETURNING *
$$;

-- יצירת אירוע חדש (events.py::create_event) — INSERT ...RETURNING תחת RLS
-- דורש שהשורה תעבור גם את events_select, לא רק את events_insert (WITH
-- CHECK owner_id=app_current_user_id()). ל-owner/admin אמיתי זה עובד כי
-- app_owns_event/app_is_admin בתוך events_select מזהים אותם — אבל זו עדיין
-- שאילתה נפרדת שרצה כחלק מבדיקת ה-RETURNING, ולכן עדיף לעקוף לגמרי דרך
-- SECURITY DEFINER, עקבי עם שאר תיקוני ה-INSERT...RETURNING במסמך הזה.
CREATE OR REPLACE FUNCTION app_create_event(
  p_owner_id bigint, p_event_type text, p_groom_name text, p_bride_name text, p_venue_name text
)
RETURNS events
LANGUAGE sql SECURITY DEFINER SET search_path = public
AS $$
  INSERT INTO events (
    owner_id, event_type, groom_name, bride_name, venue_name,
    venue_address, event_date, event_time, seats_per_table, reserve_seats, rsvp_track_active
  )
  VALUES (p_owner_id, p_event_type, p_groom_name, p_bride_name, p_venue_name, '', '', '', 12, 0, false)
  RETURNING *
$$;

-- ספירת משתמשים לצורך "המשתמש הראשון = אדמין": register() (routers/auth.py)
-- בודק user_count == 0 *לפני* שיש זהות מחוברת. תחת RLS, ``SELECT COUNT(*)
-- FROM users`` רגיל היה מסונן ע"י users_select ("אני רואה רק את עצמי") —
-- ובלי זהות, זה 0 שורות *תמיד*, גם כשכבר יש עשרות משתמשים במערכת. התוצאה:
-- כל הרשמה חדשה הייתה הופכת את המשתמש לאדמין-על בטעות. התגלה בבדיקת
-- Staging אמיתית — בעיה חמורה יותר מדליפת מידע (הענקת הרשאת-על לכולם).
CREATE OR REPLACE FUNCTION app_count_users()
RETURNS bigint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT count(*) FROM users
$$;

CREATE OR REPLACE FUNCTION app_record_login_event(
  p_user_id bigint, p_ip text, p_user_agent text
)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public
AS $$
  INSERT INTO login_events (user_id, ip, user_agent) VALUES (p_user_id, p_ip, p_user_agent)
$$;

-- הודעת RSVP נכנסת שהמוזמן האנונימי כותב *דרך דף האישור עצמו* (לא webhook —
-- ראו app_record_guest_rsvp_reply למעלה לזרימת ה-webhook). guest_token לבדו
-- לא מספיק כדי לעבור את מדיניות messages_select (שדורשת הרשאת משתמש), אז
-- ה-INSERT הרגיל מ-confirm.py נחסם ללא הפונקציה הזו.
CREATE OR REPLACE FUNCTION app_record_confirm_message(p_guest_id bigint, p_body text)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public
AS $$
  INSERT INTO messages (event_id, guest_id, direction, kind, body, status, provider, channel)
  SELECT event_id, id, 'inbound', 'reply', p_body, 'received', 'web', 'web' FROM guests WHERE id = p_guest_id
$$;

-- יומן אבטחה (audit_logs): נקרא גם מנתיבים ציבוריים/אנונימיים לגמרי (למשל
-- ניסיון גישה לטוקן לא תקין ב-confirm.py, לפני שידוע בכלל איזה אירוע/מוזמן
-- מדובר) — אין שום זהות שתעבור את מדיניות audit_logs_select. מדיניות ה-
-- INSERT כבר הייתה WITH CHECK(true) (יומן פתוח-לכתיבה בכוונה), אז זו רק
-- עקיפת בעיית ה-RETURNING, לא הרחבת הרשאה.
CREATE OR REPLACE FUNCTION app_record_audit_log(
  p_action text, p_event_id bigint, p_user_id bigint, p_detail text, p_ip text
)
RETURNS void
LANGUAGE sql SECURITY DEFINER SET search_path = public
AS $$
  INSERT INTO audit_logs (event_id, user_id, action, detail, ip)
  VALUES (p_event_id, p_user_id, p_action, p_detail, p_ip)
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
  app_record_guest_rsvp_reply(bigint, text, text, text),
  app_register_user(text, text, text, text, boolean, text),
  app_create_event(bigint, text, text, text, text),
  app_count_users(),
  app_record_login_event(bigint, text, text),
  app_record_confirm_message(bigint, text),
  app_record_audit_log(text, bigint, bigint, text, text)
TO veya_app;
