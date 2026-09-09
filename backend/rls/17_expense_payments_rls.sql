-- ============================================================================
-- VEYA · Row Level Security · קובץ 17: יומן התשלומים (expense_payments)
-- ============================================================================
-- מריצים אחרי קבצים 1–16. idempotent (DROP + CREATE), אפשר להריץ שוב בבטחה.
--
-- ‼️ תלות: משתמש ב-``app_manages_event`` שמוגדרת ב-**קובץ 08** (ניהול משותף
--    עם בן/בת זוג). אם 08 לא הורץ, ה-CREATE POLICY כאן ייכשל בקול — וזה
--    מכוון: עדיף כישלון גלוי ממדיניות שנוצרה עם סמנטיקה אחרת מהכוונה.
--
-- למה קובץ נפרד ולא הוספה ל-16: קובץ 16 כבר הורץ בייצור. הוספת טבלה
-- לתוכו הייתה משנה קובץ שכבר רץ, ומקשה על התשובה לשאלה "מה בדיוק הורץ
-- ומתי". קובץ חדש לטבלה חדשה — אותה קונבנציה כמו 13, 14 ו-16.
--
-- ── מודל ההרשאות: זהה בדיוק ל-``event_expenses`` ─────────────────────────
--
--   קריאה וכתיבה — בעלים / בן-זוג / אדמין בלבד (``app_manages_event``).
--
-- **אין כאן שום הרשאת חבר-אירוע**, ומאותה סיבה בדיוק שמפורטת בקובץ 16:
-- יומן התשלומים הוא מי קיבל מהזוג כמה כסף ומתי. מפיק או אולם שרואים
-- שהצלם קיבל מקדמה של 4,000 ₪ ב-12/8 הוא בדיוק מה שאסור שיקרה — וכאן
-- זה חמור אף יותר מ-``event_expenses``, כי כאן יש גם שם מקבל ותאריך.
--
-- אותו כלל נאכף גם בשכבת ה-API דרך ``EventAccess(owner_only=True)``
-- ב-``app/routers/finance.py`` — שתי אכיפות עצמאיות, כמו בשאר המערכת.
--
-- ── למה המדיניות על ``event_id`` ולא דרך ``expense_id`` ─────────────────
--
-- לטבלה יש ``event_id`` משלה למרות שהוא נגזר מ-``expense_id``. בלעדיו
-- כל מדיניות כאן הייתה דורשת תת-שאילתה ל-``event_expenses`` בכל שורה:
-- איטי, וגם שביר — מדיניות שנשענת על מדיניות של טבלה אחרת היא בדיוק סוג
-- הקישור שנשבר בשקט. העמודה נכתבת בשרת מתוך ההוצאה ולא מגיעה מהלקוח.
-- ============================================================================

ALTER TABLE expense_payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE expense_payments FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS expense_payments_select ON expense_payments;
CREATE POLICY expense_payments_select ON expense_payments FOR SELECT
  USING (app_manages_event(event_id));

DROP POLICY IF EXISTS expense_payments_insert ON expense_payments;
CREATE POLICY expense_payments_insert ON expense_payments FOR INSERT
  WITH CHECK (app_manages_event(event_id));

-- USING = אילו שורות מותר לגעת בהן; WITH CHECK = איך מותר שהן ייראו אחרי.
-- שניהם נדרשים, אחרת אפשר היה לעדכן שורה קיימת ולהצמיד אותה ל-event_id אחר.
DROP POLICY IF EXISTS expense_payments_update ON expense_payments;
CREATE POLICY expense_payments_update ON expense_payments FOR UPDATE
  USING (app_manages_event(event_id))
  WITH CHECK (app_manages_event(event_id));

DROP POLICY IF EXISTS expense_payments_delete ON expense_payments;
CREATE POLICY expense_payments_delete ON expense_payments FOR DELETE
  USING (app_manages_event(event_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON expense_payments TO veya_app;
