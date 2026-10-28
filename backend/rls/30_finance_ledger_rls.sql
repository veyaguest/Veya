-- ============================================================================
-- VEYA · Row Level Security · קובץ 30: רישום חשבונאי של אירועים שנמחקו
-- ============================================================================
-- מריצים אחרי 01, 08, 13 ו-23. idempotent (DROP + CREATE / OR REPLACE).
--
-- החלטת המייסד (2026-10-28): כשמוחקים אירוע, עסקאות המתנה ורכישות המסלול
-- נשמרות כרישום חשבונאי **בלי פרטים אישיים** (gift_ledger / entitlement_ledger),
-- וכל השאר נמחק. ראו models.GiftLedger ו-app/account.py::archive_event_finance.
--
-- למה פונקציה מבוקרת: טבלת gifts חסומה לכתיבה ישירה לגמרי (קובץ 13 — אין
-- מדיניות INSERT/UPDATE/DELETE, גם לא לבעלים). העברת המתנות לרישום ומחיקתן
-- חייבות לעבור דרך פונקציה SECURITY DEFINER, שבודקת בעצמה שהמבקש מנהל את
-- האירוע (בעלים / בן-בת זוג / אדמין — app_manages_event).
--
-- הרשאות הרישום: קריאה — אדמין בלבד. כתיבה ישירה — אף אחד (רק הפונקציה).
-- ============================================================================

ALTER TABLE gift_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE gift_ledger FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS gift_ledger_admin_select ON gift_ledger;
CREATE POLICY gift_ledger_admin_select ON gift_ledger FOR SELECT USING (app_is_admin());
GRANT SELECT, INSERT ON gift_ledger TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE gift_ledger_id_seq TO veya_app;

ALTER TABLE entitlement_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE entitlement_ledger FORCE  ROW LEVEL SECURITY;
DROP POLICY IF EXISTS entitlement_ledger_admin_select ON entitlement_ledger;
CREATE POLICY entitlement_ledger_admin_select ON entitlement_ledger FOR SELECT USING (app_is_admin());
GRANT SELECT, INSERT ON entitlement_ledger TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE entitlement_ledger_id_seq TO veya_app;

CREATE OR REPLACE FUNCTION app_archive_event_finance(p_event_id bigint)
RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  v_gifts integer;
BEGIN
  IF NOT app_manages_event(p_event_id) THEN
    RAISE EXCEPTION 'archive: אין הרשאה לאירוע הזה';
  END IF;

  -- מתנות: רק השדות החשבונאיים. לא sender_name, לא message, לא guest_id.
  INSERT INTO gift_ledger (
    original_gift_id, event_ref, gift_amount_agorot, fee_agorot, total_agorot, currency,
    status, provider, provider_transaction_id, gift_created_at, gift_updated_at, archived_at, reason
  )
  SELECT id, event_id, gift_amount_agorot, fee_agorot, total_agorot, currency,
         status, provider, provider_transaction_id, created_at, updated_at, now(), 'event_deleted'
  FROM gifts WHERE event_id = p_event_id;
  GET DIAGNOSTICS v_gifts = ROW_COUNT;
  DELETE FROM gifts WHERE event_id = p_event_id;

  -- רכישות מסלול: בלי note (טקסט חופשי) ובלי created_by_id.
  INSERT INTO entitlement_ledger (
    original_entitlement_id, event_ref, plan_version_id, status, price_agorot, addons, coupon_code,
    source, starts_on, trial_ends_on, renews_on, cancelled_at, entitlement_created_at, archived_at, reason
  )
  SELECT id, event_id, plan_version_id, status, price_agorot, addons, coupon_code,
         source, starts_on, trial_ends_on, renews_on, cancelled_at, created_at, now(), 'event_deleted'
  FROM event_entitlements WHERE event_id = p_event_id;
  DELETE FROM event_entitlements WHERE event_id = p_event_id;

  RETURN v_gifts;
END $$;

REVOKE ALL ON FUNCTION app_archive_event_finance(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app_archive_event_finance(bigint) TO veya_app;
