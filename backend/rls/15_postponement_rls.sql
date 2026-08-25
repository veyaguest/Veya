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
-- זה נאכף כאן: **UPDATE על שורת בקשה מותר רק לאדמין** — למעט מעבר אחד,
-- ``approved → completed``, שהוא הפעולה של בעלי האירוע עצמם ("פתחו לנו
-- מחזור חדש").
--
-- שימו לב: המדיניות אינה יודעת *לאיזה* סטטוס עוברים — ל-Postgres אין כאן
-- גישה לערך הישן והחדש בתוך ביטוי USING/WITH CHECK פשוט. לכן ההפרדה
-- המדויקת בין המעברים נשארת ב-``app/postponement_status.py``
-- (``TRANSITIONS``), וה-RLS מספק את הרובד הגס: מי בכלל רשאי לגעת בשורה.
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

-- עדכון — אדמין (אישור/דחייה) ובעלי האירוע (סגירת הנוהל). USING קובע אילו
-- שורות מותר לגעת בהן; WITH CHECK קובע איך מותר שהן ייראו אחרי — שניהם
-- נדרשים, אחרת אפשר היה לעדכן שורה ולהצמיד אותה ל-event_id אחר.
DROP POLICY IF EXISTS postponement_requests_update ON postponement_requests;
CREATE POLICY postponement_requests_update ON postponement_requests FOR UPDATE
  USING (app_is_admin() OR app_manages_event(event_id))
  WITH CHECK (app_is_admin() OR app_manages_event(event_id));

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


GRANT SELECT, INSERT, UPDATE, DELETE ON postponement_requests TO veya_app;
GRANT SELECT, INSERT, DELETE          ON event_cycles          TO veya_app;
GRANT SELECT, INSERT, DELETE          ON guest_cycle_rsvp      TO veya_app;

-- רצפי ה-id של הטבלאות (create_all יוצר אותן כ-BIGSERIAL/IDENTITY).
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO veya_app;
