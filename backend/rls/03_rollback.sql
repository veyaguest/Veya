-- ============================================================================
-- VEYA · Row Level Security · קובץ 3/3: Rollback — כיבוי RLS וחזרה למצב קודם
-- ============================================================================
-- מתי להריץ את זה: אם אחרי הפעלת RLS בפועל (החלפת DATABASE_URL לחיבור
-- veya_app) מתגלה תקלה בייצור שדורשת חזרה מיידית למצב הקודם.
--
-- שני שלבים לרול-בק מלא, לפי סדר החומרה:
--
-- שלב א' (מיידי, תוך שניות, בלי לגעת ב-DB בכלל):
--   מחזירים את DATABASE_URL בשרת (Render) לחיבור postgres (superuser) כמו
--   שהיה לפני ההפעלה, ומפעילים deploy מחדש. superuser עוקף RLS לגמרי, אז
--   ברגע שהחיבור חוזר, כל הבקשות חוזרות להתנהג בדיוק כמו לפני RLS — בלי
--   לשנות שום דבר במסד הנתונים עצמו. זה מספיק כרול-בק חירום ברוב המקרים.
--
-- שלב ב' (רק אם רוצים גם לכבות את מנגנון ה-RLS עצמו ב-DB, לא רק את החיבור):
--   מריצים את הפקודות למטה. גם הן idempotent (DISABLE-אם-מופעל).
-- ============================================================================

ALTER TABLE events            DISABLE ROW LEVEL SECURITY;
ALTER TABLE guests             DISABLE ROW LEVEL SECURITY;
ALTER TABLE messages            DISABLE ROW LEVEL SECURITY;
ALTER TABLE clarifications       DISABLE ROW LEVEL SECURITY;
ALTER TABLE automation_rules      DISABLE ROW LEVEL SECURITY;
ALTER TABLE message_templates      DISABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs              DISABLE ROW LEVEL SECURITY;
ALTER TABLE event_members             DISABLE ROW LEVEL SECURITY;
ALTER TABLE users                       DISABLE ROW LEVEL SECURITY;
ALTER TABLE login_events                  DISABLE ROW LEVEL SECURITY;

-- הערה: FORCE ROW LEVEL SECURITY לא צריך "ביטול" נפרד — ברגע ש-RLS עצמו
-- מבוטל (DISABLE), ה-FORCE לא משפיע (הוא רלוונטי רק כש-RLS מופעל).

-- שלב ג' (אופציונלי, רק אם רוצים למחוק גם את התשתית לגמרי — לא מומלץ בד"כ,
-- כי אין נזק מהשארת הפונקציות/המדיניות במצב DISABLE, וזה שומר את האפשרות
-- להפעיל שוב מהר בלי להריץ הכול מחדש):
--
-- DROP POLICY IF EXISTS events_select ON events; -- וכו' לכל מדיניות בקובץ 2
-- DROP FUNCTION IF EXISTS app_current_user_id(); -- וכו' לכל פונקציה בקובץ 1
-- DROP ROLE IF EXISTS veya_app; -- רק אחרי שמוודאים ששום חיבור לא משתמש בו יותר
