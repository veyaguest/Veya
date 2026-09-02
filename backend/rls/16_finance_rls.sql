-- ============================================================================
-- VEYA · Row Level Security · קובץ 16: כספי האירוע
--                            (event_expenses, gift_envelopes)
-- ============================================================================
-- מריצים אחרי קבצים 1–15. idempotent (DROP + CREATE), אפשר להריץ שוב בבטחה.
--
-- ‼️ תלות: משתמש ב-``app_manages_event`` שמוגדרת ב-**קובץ 08** (ניהול משותף
--    עם בן/בת זוג). אם 08 לא הורץ, ה-CREATE POLICY כאן ייכשל בקול — וזה
--    מכוון: עדיף כישלון גלוי ממדיניות שנוצרה עם סמנטיקה אחרת מהכוונה.
--
-- למה בקובץ נפרד: שתי הטבלאות נוצרות ע"י ``create_all`` בעליית השרת ולכן
-- נולדות **בלי** RLS — בדיוק כמו gifts (13) ו-payout_accounts (14).
--
-- ── מודל ההרשאות: הצר ביותר במערכת, יחד עם payout_accounts ─────────────
--
--   קריאה וכתיבה — בעלים / בן-זוג / אדמין בלבד (``app_manages_event``).
--
-- **אין כאן שום הרשאת חבר-אירוע.** לא view_reports, לא view_event, לא
-- כלום — ולכן, בשונה מרוב הקבצים כאן, המדיניות הזו **אינה** נגזרת
-- מרשימה ב-``app/permissions.py``: אין הרשאה שפותחת אותה, ואין מה
-- ליישר מולה ב-``tests/test_permission_alignment.py``.
--
-- הסיבה מוצרית ולא טכנית. מפיק או אולם שמנהלים את האירוע רשאים לראות
-- שהתקבלו מתנות (``gifts_select``), אבל:
--
--   * ``event_expenses`` הוא מה שהזוג משלם לכל **ספק אחר** — כולל,
--     לעיתים, לספק שיושב באותו רגע מול המסך. אולם שרואה כמה שולם ל-DJ
--     ולצלם הוא בדיוק מה שאסור שיקרה.
--   * ``gift_envelopes`` הוא ספירת הכסף הפיזי שקיבל הזוג בערב האירוע.
--     זה המידע הפרטי ביותר שהמערכת מחזיקה על משק בית.
--
-- אותו כלל בדיוק נאכף גם בשכבת ה-API דרך ``EventAccess(owner_only=True)``
-- ב-``app/routers/finance.py`` — שתי אכיפות עצמאיות, כמו בשאר המערכת.
--
-- **מה אין בטבלאות:** אין בהן שום נתון אשראי. מעטפה היא רישום ידני של
-- מזומן/צ'ק שכבר בידי הזוג; עסקאות הסליקה חיות ב-``gifts`` תחת קובץ 13,
-- ואינן נכתבות מכאן לעולם.
-- ============================================================================

-- ════════════════════════════════════════════════════════════════════════
--  event_expenses — שורות עלות האירוע
-- ════════════════════════════════════════════════════════════════════════

ALTER TABLE event_expenses ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_expenses FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS event_expenses_select ON event_expenses;
CREATE POLICY event_expenses_select ON event_expenses FOR SELECT
  USING (app_manages_event(event_id));

DROP POLICY IF EXISTS event_expenses_insert ON event_expenses;
CREATE POLICY event_expenses_insert ON event_expenses FOR INSERT
  WITH CHECK (app_manages_event(event_id));

-- USING = אילו שורות מותר לגעת בהן; WITH CHECK = איך מותר שהן ייראו אחרי.
-- שניהם נדרשים, אחרת אפשר היה לעדכן שורה קיימת ולהצמיד אותה ל-event_id אחר.
DROP POLICY IF EXISTS event_expenses_update ON event_expenses;
CREATE POLICY event_expenses_update ON event_expenses FOR UPDATE
  USING (app_manages_event(event_id))
  WITH CHECK (app_manages_event(event_id));

DROP POLICY IF EXISTS event_expenses_delete ON event_expenses;
CREATE POLICY event_expenses_delete ON event_expenses FOR DELETE
  USING (app_manages_event(event_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON event_expenses TO veya_app;

-- ════════════════════════════════════════════════════════════════════════
--  gift_envelopes — המעטפות שנספרו אחרי האירוע
-- ════════════════════════════════════════════════════════════════════════
--
-- שימו לב להבדל מ-``gifts`` (קובץ 13): שם **אין** מדיניות INSERT/UPDATE
-- בכלל, כי עסקת סליקה נכתבת רק דרך פונקציות SECURITY DEFINER מבוקרות.
-- כאן יש מדיניות כתיבה מלאה — ובכוונה: מעטפה היא רישום ידני של הבעלים,
-- ומותר לו לערוך ולמחוק אותה. זה בדיוק ההבדל שבגללו אלה שתי טבלאות
-- ולא עמודה אחת (ראו ``models.GiftEnvelope``).

ALTER TABLE gift_envelopes ENABLE ROW LEVEL SECURITY;
ALTER TABLE gift_envelopes FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS gift_envelopes_select ON gift_envelopes;
CREATE POLICY gift_envelopes_select ON gift_envelopes FOR SELECT
  USING (app_manages_event(event_id));

DROP POLICY IF EXISTS gift_envelopes_insert ON gift_envelopes;
CREATE POLICY gift_envelopes_insert ON gift_envelopes FOR INSERT
  WITH CHECK (app_manages_event(event_id));

DROP POLICY IF EXISTS gift_envelopes_update ON gift_envelopes;
CREATE POLICY gift_envelopes_update ON gift_envelopes FOR UPDATE
  USING (app_manages_event(event_id))
  WITH CHECK (app_manages_event(event_id));

DROP POLICY IF EXISTS gift_envelopes_delete ON gift_envelopes;
CREATE POLICY gift_envelopes_delete ON gift_envelopes FOR DELETE
  USING (app_manages_event(event_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON gift_envelopes TO veya_app;
