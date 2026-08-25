-- ============================================================================
-- VEYA · Row Level Security · קובץ 14: פרטי קבלת מתנות (payout_accounts)
-- ============================================================================
-- מריצים אחרי קבצים 1–13. idempotent (DROP + CREATE), אפשר להריץ שוב בבטחה.
--
-- ‼️ תלות: הקובץ הזה משתמש ב-``app_manages_event`` שמוגדרת ב-**קובץ 08**
--    (ניהול משותף עם בן/בת זוג). אם 08 לא הורץ, ה-CREATE POLICY כאן ייכשל
--    בקול — וזה מכוון: עדיף כישלון גלוי מאשר מדיניות שנוצרה עם סמנטיקה
--    אחרת ממה שהתכוונו לה.
--
-- למה בקובץ נפרד: הטבלה נוצרת ע"י ``create_all`` בעליית השרת ולכן נולדת
-- **בלי** RLS — בדיוק כמו gifts (קובץ 13).
--
-- מודל ההרשאות — הצר ביותר במערכת:
--   קריאה וכתיבה — בעלים / בן-זוג / אדמין בלבד (``app_manages_event``).
--
-- **אין כאן שום הרשאת חבר-אירוע.** לא view_reports, לא view_event, לא
-- כלום. מפיק או אולם שמנהלים את האירוע יכולים לראות שהתקבלו מתנות
-- (מדיניות gifts_select), אבל חשבון הבנק של הזוג אינו מידע שלהם — הוא
-- המידע הפיננסי הרגיש ביותר שהמערכת מחזיקה. זו הסיבה שהמדיניות כאן אינה
-- נגזרת מ-app/permissions.py כמו האחרות: אין הרשאה שפותחת אותה.
--
-- אותו כלל בדיוק נאכף גם בשכבת ה-API דרך ``EventAccess(owner_only=True)``
-- ב-``app/routers/payout.py`` — שתי אכיפות עצמאיות, כמו בשאר המערכת.
--
-- **מה אין בטבלה:** אין בה נתוני אשראי כלשהם. אישור ניהול החשבון נשמר
-- בעמודה בתוך הטבלה הזו ולא ב-``media_blobs``, כדי שלא יהיה לו נתיב
-- הגשה ציבורי (``GET /media/<id>`` הוא ללא אימות במכוון).
-- ============================================================================

ALTER TABLE payout_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE payout_accounts FORCE  ROW LEVEL SECURITY;

-- ── קריאה ───────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS payout_accounts_select ON payout_accounts;
CREATE POLICY payout_accounts_select ON payout_accounts FOR SELECT
  USING (app_manages_event(event_id));

-- ── יצירה ───────────────────────────────────────────────────────────────
DROP POLICY IF EXISTS payout_accounts_insert ON payout_accounts;
CREATE POLICY payout_accounts_insert ON payout_accounts FOR INSERT
  WITH CHECK (app_manages_event(event_id));

-- ── עדכון ───────────────────────────────────────────────────────────────
-- USING = אילו שורות מותר לגעת בהן; WITH CHECK = איך מותר שהן ייראו אחרי.
-- שניהם נדרשים, אחרת אפשר היה לעדכן שורה קיימת ולהצמיד אותה ל-event_id אחר.
DROP POLICY IF EXISTS payout_accounts_update ON payout_accounts;
CREATE POLICY payout_accounts_update ON payout_accounts FOR UPDATE
  USING (app_manages_event(event_id))
  WITH CHECK (app_manages_event(event_id));

-- ── מחיקה ───────────────────────────────────────────────────────────────
-- מחיקת האירוע גוררת מחיקת השורה (ON DELETE CASCADE ברמת ה-FK), אבל
-- המדיניות נדרשת גם כדי שמחיקה יזומה של בעלים לא תיחסם.
DROP POLICY IF EXISTS payout_accounts_delete ON payout_accounts;
CREATE POLICY payout_accounts_delete ON payout_accounts FOR DELETE
  USING (app_manages_event(event_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON payout_accounts TO veya_app;
