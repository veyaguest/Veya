-- ============================================================================
-- VEYA · Row Level Security · קובץ 13: עסקאות מתנה (gifts)
-- ============================================================================
-- מריצים אחרי קבצים 1–12. idempotent (DROP + CREATE), אפשר להריץ שוב בבטחה.
--
-- למה בקובץ נפרד ולא ב-02_policies.sql: הטבלה נוצרת ע"י ``create_all``
-- בעליית השרת ולכן היא נולדת **בלי** RLS — בדיוק כמו event_messages (קובץ 5)
-- ו-call_logs (קובץ 6). זו הסיבה שהקובץ הזה חייב לרוץ אחרי הפריסה שיוצרת
-- את הטבלה, ולא לפניה.
--
-- מודל ההרשאות:
--   קריאה  — בעלים/אדמין, חבר-אירוע עם הרשאת דיווח, **או המוזמן עצמו**
--            (רק את השורות שלו, לפי הטוקן הציבורי).
--   כתיבה  — אף אחד ישירות. יצירה ועדכון סטטוס עוברים דרך שתי פונקציות
--            SECURITY DEFINER בלבד (למטה). זה מכוון: סכומי כסף וסטטוס
--            תשלום לא אמורים להיות ניתנים לעריכה מה-API הרגיל.
--
-- **אין בטבלה שום נתון אשראי** — לא מספר כרטיס, לא CVV, לא תוקף. רק
-- provider_transaction_id להתאמה מול הספק.
-- ============================================================================

ALTER TABLE gifts ENABLE ROW LEVEL SECURITY;
ALTER TABLE gifts FORCE  ROW LEVEL SECURITY;

-- ── קריאה ───────────────────────────────────────────────────────────────
-- view_reports/view_event הן ההרשאות שכבר מסמנות "מי צריך לדעת מה קרה
-- באירוע" (זהה ל-MESSAGES_VIEW פחות send_messages — מפיק ששולח הודעות
-- לא אמור בהכרח לראות כספים). מיושר מול app/permissions.py::GIFTS_VIEW,
-- ויש טסט שנועל את ההתאמה (tests/test_permission_alignment.py).
DROP POLICY IF EXISTS gifts_select ON gifts;
CREATE POLICY gifts_select ON gifts FOR SELECT
  USING (
    app_has_any_event_permission(event_id, ARRAY['view_reports','view_event'])
    OR guest_id IN (
      SELECT id FROM guests WHERE guest_token = app_current_guest_token()
    )
  );

-- ── כתיבה ישירה: אסורה לחלוטין ──────────────────────────────────────────
-- אין CREATE POLICY ל-INSERT/UPDATE/DELETE. בהיעדר מדיניות, RLS חוסם הכל
-- (גם לבעלים) — וזה בדיוק מה שרוצים: הדרך היחידה לשנות שורת כסף היא דרך
-- שתי הפונקציות המבוקרות למטה.

-- ── יצירת עסקה (מוזמן אנונימי) ──────────────────────────────────────────
-- אותה סיבה בדיוק כמו app_record_confirm_message (קובץ 1): למוזמן יש רק
-- guest_token ולא זהות משתמש, ולכן INSERT רגיל (עם RETURNING שברירת המחדל
-- של SQLAlchemy) היה נדחה ע"י gifts_select.
--
-- הפונקציה **גוזרת בעצמה** את event_id מתוך שורת המוזמן ומוודאת שהטוקן
-- הנוכחי אכן שייך לאותו מוזמן — כך שגם אם קוד יישום עתידי ינסה להעביר
-- guest_id של מישהו אחר, ה-DB יסרב.
CREATE OR REPLACE FUNCTION app_record_gift(
  p_event_id bigint, p_guest_id bigint,
  p_gift_agorot integer, p_fee_agorot integer, p_total_agorot integer,
  p_currency text, p_status text, p_provider text,
  p_idempotency_key text, p_sender_name text, p_message text
)
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  v_event_id bigint;
  v_new_id   bigint;
BEGIN
  -- מקור האמת לזהות: שורת המוזמן שהטוקן הנוכחי פותח.
  SELECT g.event_id INTO v_event_id
  FROM guests g
  WHERE g.id = p_guest_id
    AND (
      g.guest_token = app_current_guest_token()
      OR app_has_any_event_permission(g.event_id, ARRAY['view_reports','view_event'])
    );

  IF v_event_id IS NULL THEN
    RAISE EXCEPTION 'gift: אין הרשאה ליצור עסקה למוזמן הזה';
  END IF;

  IF v_event_id <> p_event_id THEN
    RAISE EXCEPTION 'gift: המוזמן אינו שייך לאירוע שנשלח';
  END IF;

  INSERT INTO gifts (
    event_id, guest_id, gift_amount_agorot, fee_agorot, total_agorot,
    currency, status, provider, idempotency_key, sender_name, message
  ) VALUES (
    v_event_id, p_guest_id, p_gift_agorot, p_fee_agorot, p_total_agorot,
    p_currency, p_status, p_provider, p_idempotency_key, p_sender_name, p_message
  )
  RETURNING id INTO v_new_id;

  RETURN v_new_id;
END;
$$;

-- ── עדכון סטטוס (ספק הסליקה / webhook עתידי) ────────────────────────────
-- מגבילה את עצמה לסטטוסים המוכרים בלבד. מעברים חוקיים נאכפים בשכבת
-- ה-Python (app/gift_status.py) — כאן זו רשת ביטחון מפני ערך שרירותי.
-- **סכומי הכסף אינם ניתנים לעדכון כאן בכוונה:** עסקה שנוצרה לא משנה סכום.
CREATE OR REPLACE FUNCTION app_update_gift_status(
  p_gift_id bigint, p_status text, p_provider_transaction_id text
)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  IF p_status NOT IN ('pending','paid','failed','cancelled','refunded') THEN
    RAISE EXCEPTION 'gift: סטטוס לא מוכר %', p_status;
  END IF;

  UPDATE gifts
     SET status = p_status,
         provider_transaction_id =
           COALESCE(p_provider_transaction_id, provider_transaction_id),
         updated_at = now()
   WHERE id = p_gift_id;
END;
$$;

GRANT SELECT ON gifts TO veya_app;
GRANT EXECUTE ON FUNCTION
  app_record_gift(bigint, bigint, integer, integer, integer, text, text, text, text, text, text),
  app_update_gift_status(bigint, text, text)
TO veya_app;
