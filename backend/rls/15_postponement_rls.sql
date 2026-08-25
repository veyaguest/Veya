-- ============================================================================
-- VEYA · Row Level Security · קובץ 15: נוהל דחייה
--   postponement_requests · event_cycles · guest_cycle_rsvp
-- ============================================================================
-- מריצים אחרי קבצים 1–14. idempotent (DROP + CREATE), אפשר להריץ שוב בבטחה.
--
-- ‼️ תלות: הקובץ הזה משתמש ב-``app_manages_event`` שמוגדרת ב-**קובץ 08**
--    (ניהול משותף עם בן/בת זוג) וב-``app_is_admin`` מקובץ 01. אם הם לא
--    הורצו, ה-CREATE POLICY כאן ייכשל בקול — וזה מכוון: עדיף כישלון גלוי
--    מאשר מדיניות שנוצרה עם סמנטיקה אחרת ממה שהתכוונו לה.
--
-- למה בקובץ נפרד: שלוש הטבלאות נוצרות ע"י ``create_all`` בעליית השרת ולכן
-- נולדות **בלי** RLS — בדיוק כמו gifts (13) ו-payout_accounts (14).
--
-- מודל ההרשאות:
--   קריאה  — בעלים / בן-זוג / אדמין (``app_manages_event``).
--   כתיבה  — אותו דבר, **חוץ מהכרעת הבקשה** (ראו למטה).
--
-- **אין כאן שום הרשאת חבר-אירוע.** מפיק או אולם שמנהלים אירוע אינם פותחים
-- נוהל דחייה, אינם מאשרים אותו ואינם רואים את ארכיון התשובות. אותו כלל
-- בדיוק נאכף גם בשכבת ה-API דרך ``EventAccess(owner_only=True)`` ב-
-- ``app/routers/postpone.py`` — שתי אכיפות עצמאיות, כמו בשאר המערכת.
--
-- ## הכלל שמגן על האירוע
--
-- מי שמבקש לדחות את האירוע אינו מי שמאשר את הדחייה. ב-API זה נאכף בכך
-- שנתיבי האישור יושבים בקובץ נפרד מאחורי ``get_current_admin``. ברמת ה-DB
-- זה נאכף במדיניות ה-UPDATE למטה, והיא מדויקת:
--
--   אדמין        — רשאי לכל מעבר (אישור, דחייה).
--   בעלי האירוע  — רשאים למעבר **אחד בלבד**: ``approved → completed``,
--                  כלומר "סיימנו לעדכן, פתחו לנו מחזור חדש".
--
-- זה עובד כי ב-UPDATE, ``USING`` נבדק מול השורה **לפני** השינוי ו-
-- ``WITH CHECK`` מול השורה **אחרי**. בעלי אירוע שינסו לכתוב ישירות ל-DB
-- ולסמן לעצמם ``approved`` ייחסמו — גם אם עקפו את ה-API לגמרי.
--
-- שאר המעברים (מי מותר אחרי מי) נשארים ב-``app/postponement_status.py``
-- (``TRANSITIONS``). ה-RLS אינו משכפל את מכונת המצבים — הוא אוכף את הגבול
-- היחיד שחייב להחזיק בשתי השכבות: **הכרעה היא של אדמין בלבד.**
-- ============================================================================

-- ── postponement_requests ───────────────────────────────────────────────
ALTER TABLE postponement_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE postponement_requests FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS postponement_requests_select ON postponement_requests;
CREATE POLICY postponement_requests_select ON postponement_requests FOR SELECT
  USING (app_manages_event(event_id));

-- פתיחת בקשה — בעלי האירוע. זו הפעולה שכל המנגנון קיים בשבילה.
DROP POLICY IF EXISTS postponement_requests_insert ON postponement_requests;
CREATE POLICY postponement_requests_insert ON postponement_requests FOR INSERT
  WITH CHECK (app_manages_event(event_id));

-- עדכון — ראו "הכלל שמגן על האירוע" בראש הקובץ.
--
--   USING       מול השורה לפני השינוי: אדמין תמיד; בעלי אירוע רק כשהנוהל
--               כבר אושר — כלומר אין להם דרך לגעת בבקשה שממתינה להכרעה.
--   WITH CHECK  מול השורה אחרי: אדמין תמיד; בעלי אירוע רק אם התוצאה היא
--               ``completed`` — המעבר היחיד שלהם הוא סגירת הנוהל.
--
-- ``event_id`` נבדק בשני הצדדים, אחרת אפשר היה לעדכן שורה ולהצמיד אותה
-- לאירוע אחר.
DROP POLICY IF EXISTS postponement_requests_update ON postponement_requests;
CREATE POLICY postponement_requests_update ON postponement_requests FOR UPDATE
  USING (
    app_is_admin()
    OR (app_manages_event(event_id) AND status = 'approved')
  )
  WITH CHECK (
    app_is_admin()
    OR (app_manages_event(event_id) AND status = 'completed')
  );

-- מחיקת האירוע גוררת מחיקת השורות (ON DELETE CASCADE ברמת ה-FK), אבל
-- המדיניות נדרשת גם כדי שמחיקה יזומה של בעלים לא תיחסם.
DROP POLICY IF EXISTS postponement_requests_delete ON postponement_requests;
CREATE POLICY postponement_requests_delete ON postponement_requests FOR DELETE
  USING (app_manages_event(event_id));


-- ── event_cycles ────────────────────────────────────────────────────────
-- צילום של מחזור שנסגר. נכתב פעם אחת ולעולם לא מתעדכן — ולכן **אין כאן
-- מדיניות UPDATE**, בכוונה: היסטוריה שאפשר לערוך אינה היסטוריה.
ALTER TABLE event_cycles ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_cycles FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS event_cycles_select ON event_cycles;
CREATE POLICY event_cycles_select ON event_cycles FOR SELECT
  USING (app_manages_event(event_id));

DROP POLICY IF EXISTS event_cycles_insert ON event_cycles;
CREATE POLICY event_cycles_insert ON event_cycles FOR INSERT
  WITH CHECK (app_manages_event(event_id));

DROP POLICY IF EXISTS event_cycles_delete ON event_cycles;
CREATE POLICY event_cycles_delete ON event_cycles FOR DELETE
  USING (app_manages_event(event_id));


-- ── guest_cycle_rsvp ────────────────────────────────────────────────────
-- ארכיון תשובות ההגעה של מחזור שנסגר. זו הטבלה שמאפשרת "לאפס" אישורי הגעה
-- בלי למחוק דבר, ולכן גם כאן **אין מדיניות UPDATE**: השורה נכתבת ברגע
-- הארכוב ונשארת כפי שהיא.
--
-- הערה על פרטיות: השורות כאן הן מידע אישי של מוזמנים (מי אישר, כמה, ומה
-- כתב). הן נשארות באותו מעגל הרשאות בדיוק כמו ``guests`` עצמה מבחינת
-- הבעלים, ונמחקות יחד עם האירוע או עם המוזמן (ON DELETE CASCADE) — כדי
-- שבקשת מחיקת נתונים לא תשאיר עותק שקט מאחור.
ALTER TABLE guest_cycle_rsvp ENABLE ROW LEVEL SECURITY;
ALTER TABLE guest_cycle_rsvp FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS guest_cycle_rsvp_select ON guest_cycle_rsvp;
CREATE POLICY guest_cycle_rsvp_select ON guest_cycle_rsvp FOR SELECT
  USING (app_manages_event(event_id));

DROP POLICY IF EXISTS guest_cycle_rsvp_insert ON guest_cycle_rsvp;
CREATE POLICY guest_cycle_rsvp_insert ON guest_cycle_rsvp FOR INSERT
  WITH CHECK (app_manages_event(event_id));

DROP POLICY IF EXISTS guest_cycle_rsvp_delete ON guest_cycle_rsvp;
CREATE POLICY guest_cycle_rsvp_delete ON guest_cycle_rsvp FOR DELETE
  USING (app_manages_event(event_id));


-- ── הרשאות ל-veya_app ───────────────────────────────────────────────────
--
-- ברוב המקרים אלה כבר ניתנו מאליהן: קובץ 01 מריץ
-- ``ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ... TO veya_app``,
-- וכל טבלה חדשה ש-``create_all`` יוצר (כ-postgres) יורשת אותן אוטומטית.
-- **זו הסיבה שהאפליקציה בייצור עובדת גם לפני שהקובץ הזה הורץ** — מה שחסר
-- שם הוא שכבת ה-RLS, לא ההרשאות.
--
-- הן נכתבות כאן במפורש בכל זאת, כרשת ביטחון לכל DB שבו ברירות המחדל לא
-- חלו (למשל טבלה שנוצרה בידי תפקיד אחר). ה-GRANT מוגבל לשלוש הטבלאות
-- האלה ולרצפים שלהן בלבד — הוא **אינו** נוגע בשאר הסכימה.
--
-- הכול עטוף בבדיקת קיום התפקיד: קובץ שרץ על DB שבו ``veya_app`` עוד לא
-- נוצר (כלומר קובץ 01 לא הורץ) לא ייפול על GRANT לתפקיד שאינו קיים —
-- מדיניות ה-RLS למעלה כבר נוצרה, וזה מה שחשוב.
DO $$
DECLARE
  seq text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'veya_app') THEN
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON postponement_requests TO veya_app';
    EXECUTE 'GRANT SELECT, INSERT, DELETE ON event_cycles TO veya_app';
    EXECUTE 'GRANT SELECT, INSERT, DELETE ON guest_cycle_rsvp TO veya_app';
    -- הרצפים של עמודות ה-id (create_all יוצר אותן כ-SERIAL/IDENTITY).
    -- ``pg_get_serial_sequence`` מחזיר NULL אם אין רצף — ואז מדלגים.
    -- שרשור ב-|| ולא ב-format(): ל-format יש placeholder בסימן אחוז, וכל
    -- מריץ שמעביר את הקובץ דרך ספריית DB של פייתון (psycopg2) יפרש אותו
    -- כפרמטר bind ויפיל את ההרצה. הקובץ הזה נשאר **נקי מסימני אחוז**
    -- בכוונה, כדי שיהיה אפשר להריץ אותו גם מה-SQL Editor וגם מהקוד.
    FOR seq IN
      SELECT s FROM (VALUES
        (pg_get_serial_sequence('postponement_requests', 'id')),
        (pg_get_serial_sequence('event_cycles', 'id')),
        (pg_get_serial_sequence('guest_cycle_rsvp', 'id'))
      ) AS t(s) WHERE s IS NOT NULL
    LOOP
      EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE ' || seq || ' TO veya_app';
    END LOOP;
  ELSE
    RAISE NOTICE 'התפקיד veya_app אינו קיים — דילגנו על ה-GRANT. המדיניות נוצרה.';
  END IF;
END
$$;


-- ============================================================================
-- בדיקת אימות — להריץ אחרי הקובץ, קריאה בלבד.
-- ============================================================================
-- שלוש שורות, כולן true:
--
--   select relname, relrowsecurity, relforcerowsecurity
--     from pg_class
--    where relnamespace = 'public'::regnamespace
--      and relname in ('postponement_requests','event_cycles','guest_cycle_rsvp')
--    order by 1;
--
-- עשר מדיניות (4 לבקשות, 3 לכל אחת מטבלאות ההיסטוריה):
--
--   select tablename, policyname, cmd
--     from pg_policies
--    where schemaname = 'public'
--      and tablename in ('postponement_requests','event_cycles','guest_cycle_rsvp')
--    order by tablename, policyname;
--
-- ואין UPDATE על טבלאות ההיסטוריה — זו הבדיקה החשובה מכולן:
--
--   select count(*) = 0 as history_is_immutable
--     from pg_policies
--    where schemaname = 'public'
--      and tablename in ('event_cycles','guest_cycle_rsvp')
--      and cmd = 'UPDATE';
-- ============================================================================
