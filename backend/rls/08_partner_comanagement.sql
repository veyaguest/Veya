-- ============================================================================
-- VEYA · Row Level Security · קובץ 8: ניהול משותף של אירוע (בן/בת זוג)
-- ============================================================================
-- מריצים אחרי קבצים 1–7. idempotent (CREATE OR REPLACE / DROP ... IF EXISTS),
-- אז אפשר להריץ שוב בבטחה.
--
-- מה הקובץ עושה (בעברית פשוטה):
--   1. מוסיף פונקציית עזר "האם המשתמש המחובר הוא בן/בת הזוג של האירוע הזה"
--      (שורת event_members פעילה עם role='partner').
--   2. מוסיף פונקציית עזר app_manages_event() = אדמין / בעלים / בן-בת זוג.
--      זו התשובה ל"מותר לו הכול על האירוע הזה?".
--   3. **מרחיב** מדיניות קיימות שהיו כתובות עם app_owns_event בלבד, כך שגם
--      בן/בת הזוג יעברו אותן: מחיקת אירוע, מחיקת שורות יומן, וניהול
--      חברי-אירוע.
--   4. מרחיב את app_has_any_event_permission כך שבן/בת זוג יעברו כל בדיקת
--      הרשאה — בדיוק כמו הבעלים.
--   5. מפעיל RLS על הטבלה החדשה event_invitations.
--
-- למה נדרש: בלי זה, בן/בת הזוג היו עוברים את שכבת ה-API (app/deps.py::
-- EventAccess מזהה אותם) אבל נחסמים בשקט ע"י Postgres — כלומר "מנהלים
-- יחד" היה נשבר בייצור בלבד, ולא בפיתוח מול SQLite שבו RLS הוא no-op.
--
-- ============================================================================
-- ‼️ סטטוס: PENDING — הקובץ מוכן להרצה, אך **טרם הורץ ולא נבדק מול DB חי**.
-- להריץ ב-Supabase → SQL Editor כשמחוברים כ-postgres, יחד עם שאר הקבצים.
-- ============================================================================


-- ── 1. פונקציות עזר ─────────────────────────────────────────────────────────

-- האם המשתמש הנוכחי הוא בן/בת הזוג שמנהלים יחד את האירוע.
CREATE OR REPLACE FUNCTION app_is_event_partner(p_event_id bigint)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM event_members m
    WHERE m.event_id = p_event_id
      AND m.user_id = app_current_user_id()
      AND m.role = 'partner'
      AND m.status = 'active'
  )
$$;

-- "מנהל האירוע" במובן המלא: אדמין-על, הבעלים, או בן/בת הזוג. זו הבדיקה
-- שמחליפה app_owns_event בכל מקום שבו הכוונה הייתה "בעל הבית", ולא "מי
-- רשום כ-owner_id" באופן טכני.
CREATE OR REPLACE FUNCTION app_manages_event(p_event_id bigint)
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT app_is_admin()
      OR app_owns_event(p_event_id)
      OR app_is_event_partner(p_event_id)
$$;

-- הרחבה: בן/בת זוג עוברים כל בדיקת הרשאה, כמו הבעלים. שאר הלוגיקה
-- (חבר-אירוע מפיק/אולם עם רשימת permissions) נשארת בדיוק כפי שהייתה.
CREATE OR REPLACE FUNCTION app_has_any_event_permission(p_event_id bigint, p_permissions text[])
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT app_is_admin()
      OR app_owns_event(p_event_id)
      OR app_is_event_partner(p_event_id)
      OR app_member_permissions(p_event_id) ?| p_permissions
$$;


-- ── 2. הרחבת מדיניות קיימות ─────────────────────────────────────────────────

-- מחיקת אירוע: גם בן/בת הזוג רשאים (הם מנהלים שווים).
DROP POLICY IF EXISTS events_delete ON events;
CREATE POLICY events_delete ON events FOR DELETE
  USING (app_manages_event(id));

-- מחיקת שורות יומן פעילות של האירוע (נדרש כדי שמחיקת אירוע לא תישבר על FK).
DROP POLICY IF EXISTS audit_logs_delete ON audit_logs;
CREATE POLICY audit_logs_delete ON audit_logs FOR DELETE
  USING (app_is_admin() OR (event_id IS NOT NULL AND app_manages_event(event_id)));

-- ניהול חברי-אירוע: גם בן/בת הזוג יכולים לראות ולנהל מי מחובר לאירוע
-- (למשל להזמין מפיק/אולם) — אחרת "ניהול משותף" היה חלקי.
DROP POLICY IF EXISTS event_members_select ON event_members;
CREATE POLICY event_members_select ON event_members FOR SELECT
  USING (
    app_is_admin()
    OR app_manages_event(event_id)
    OR user_id = app_current_user_id()
  );

DROP POLICY IF EXISTS event_members_write ON event_members;
CREATE POLICY event_members_write ON event_members FOR ALL
  USING (app_manages_event(event_id))
  WITH CHECK (app_manages_event(event_id));


-- ── 3. event_invitations (הזמנה לניהול משותף) ───────────────────────────────
-- קריאה/כתיבה: מנהלי האירוע בלבד. מי שקיבל את ההזמנה **אינו** קורא את
-- הטבלה ישירות — הוא מגיע דרך endpoint שמאתר את השורה לפי hash של הטוקן
-- (app/routers/partner.py), וזו הסיבה שאין כאן מדיניות "לפי אימייל":
-- הטוקן הוא ההרשאה, לא כתובת המייל ולא מזהה האירוע.
ALTER TABLE event_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE event_invitations FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS event_invitations_select ON event_invitations;
CREATE POLICY event_invitations_select ON event_invitations FOR SELECT
  USING (app_manages_event(event_id));

DROP POLICY IF EXISTS event_invitations_write ON event_invitations;
CREATE POLICY event_invitations_write ON event_invitations FOR ALL
  USING (app_manages_event(event_id))
  WITH CHECK (app_manages_event(event_id));


-- ── 4. פונקציות עזר לזרימת ההצטרפות (עוקפות RLS במכוון ובמדויק) ─────────────
-- הצטרפות לאירוע היא המקרה הקלאסי של "עוד אין לי גישה, ולכן אני לא יכול
-- לקרוא את השורה שתיתן לי גישה". שלוש הפונקציות האלה פותרות בדיוק את זה,
-- והן מוגבלות לחיפוש לפי hash-של-טוקן — לא שאילתה חופשית על הטבלה.

-- איתור הזמנה לפי ה-hash של הטוקן מהקישור.
CREATE OR REPLACE FUNCTION app_invitation_by_token_hash(p_token_hash text)
RETURNS event_invitations
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT * FROM event_invitations WHERE token_hash = p_token_hash LIMIT 1
$$;

-- מימוש ההזמנה: מסמן אותה כ"התקבלה" ומוסיף/מפעיל את שורת החברות כבן/בת זוג.
-- אטומי בכוונה — אחרת אפשר היה להישאר עם הזמנה מסומנת בלי חברות בפועל.
CREATE OR REPLACE FUNCTION app_accept_partner_invitation(
  p_token_hash text, p_user_id bigint, p_permissions jsonb
)
RETURNS event_members
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  v_inv event_invitations;
  v_member event_members;
BEGIN
  SELECT * INTO v_inv FROM event_invitations
   WHERE token_hash = p_token_hash AND status = 'pending'
   FOR UPDATE;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;
  IF v_inv.expires_at IS NOT NULL AND v_inv.expires_at <= now() THEN
    RETURN NULL;
  END IF;

  UPDATE event_invitations
     SET status = 'accepted', accepted_at = now(), accepted_by = p_user_id
   WHERE id = v_inv.id;

  SELECT * INTO v_member FROM event_members
   WHERE event_id = v_inv.event_id AND user_id = p_user_id;

  IF FOUND THEN
    UPDATE event_members
       SET role = 'partner', permissions = p_permissions, status = 'active'
     WHERE id = v_member.id
     RETURNING * INTO v_member;
  ELSE
    INSERT INTO event_members (event_id, user_id, role, permissions, invited_by_id, status)
    VALUES (v_inv.event_id, p_user_id, 'partner', p_permissions, v_inv.invited_by, 'active')
    RETURNING * INTO v_member;
  END IF;

  RETURN v_member;
END;
$$;

-- פרטי האירוע והמזמין להצגה בדף ההצטרפות, לפני שיש גישה בכלל.
-- מחזירה מידע מינימלי בכוונה: כותרת האירוע ושם המזמין — לא מוזמנים, לא
-- טלפונים, ולא שום דבר אחר.
CREATE OR REPLACE FUNCTION app_invitation_preview(p_token_hash text)
RETURNS TABLE (
  event_id bigint, event_type text, groom_name text, bride_name text,
  inviter_name text, invited_email text, status text, expires_at timestamptz
)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT e.id, e.event_type, e.groom_name, e.bride_name,
         COALESCE(u.display_name, ''), i.invited_email, i.status, i.expires_at
    FROM event_invitations i
    JOIN events e ON e.id = i.event_id
    LEFT JOIN users u ON u.id = i.invited_by
   WHERE i.token_hash = p_token_hash
   LIMIT 1
$$;


-- ── 5. הרשאות הרצה לתפקיד האפליקציה ─────────────────────────────────────────
GRANT EXECUTE ON FUNCTION
  app_is_event_partner(bigint),
  app_manages_event(bigint),
  app_invitation_by_token_hash(text),
  app_accept_partner_invitation(text, bigint, jsonb),
  app_invitation_preview(text)
TO veya_app;

-- הרשאות עבודה על הטבלה החדשה (RLS מצמצם *אילו שורות*, לא *אם יש גישה*).
GRANT SELECT, INSERT, UPDATE, DELETE ON event_invitations TO veya_app;
GRANT USAGE, SELECT ON SEQUENCE event_invitations_id_seq TO veya_app;
