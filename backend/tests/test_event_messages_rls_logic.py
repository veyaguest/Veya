"""סימולציה לוגית של מדיניות ה-RLS ל-event_messages (rls/05_event_messages_rls.sql).

**מגבלה חשובה, בכוונה לא מוסתרת:** זו *לא* בדיקה מול Postgres/Supabase חי —
אין Docker/psql/פרטי Supabase staging בסביבת הפיתוח הזו (ראו ההערה בראש
05_event_messages_rls.sql). מה שכן נבדק כאן: תרגום מדויק ל-Python של הביטוי
הבוליאני שכל policy מריצה בפועל —
``app_has_any_event_permission(event_id, perms) = is_admin OR owns_event
OR (member_permissions ∩ perms ≠ ∅)`` — מול בדיוק התרחישים שהתבקשו: בעלים,
חבר מורשה, חבר לא-מורשה, ומשתמש מאירוע אחר (cross-tenant). זה מוודא
שהלוגיקה שתכננתי נכונה; זה לא מחליף בדיקה חיה מול Postgres אמיתי לפני
הפעלה בייצור (ראו STAGING_PLAN.md).

הרצה: ``venv/bin/python tests/test_event_messages_rls_logic.py``
"""
from dataclasses import dataclass, field


# ---- תרגום מדויק של app_has_any_event_permission (01_helpers_and_grants.sql) ----

@dataclass
class FakeDB:
    """גרף קטן: מי הבעלים של כל אירוע, ואיזה הרשאות יש לכל (user, event)."""

    owners: dict[int, int] = field(default_factory=dict)          # event_id -> owner_user_id
    admins: set[int] = field(default_factory=set)                 # user_id
    member_perms: dict[tuple[int, int], set[str]] = field(default_factory=dict)  # (user_id, event_id) -> perms

    def owns_event(self, user_id: int, event_id: int) -> bool:
        return self.owners.get(event_id) == user_id

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admins

    def has_any_event_permission(self, user_id: int, event_id: int, perms: set[str]) -> bool:
        if self.is_admin(user_id):
            return True
        if self.owns_event(user_id, event_id):
            return True
        return bool(self.member_perms.get((user_id, event_id), set()) & perms)


MESSAGES_VIEW = {"send_messages", "view_reports", "view_event"}
MESSAGES_WRITE = {"send_messages"}


# ---- ארבעת ה-policies מ-05_event_messages_rls.sql, כביטוי בוליאני ----

def can_select(db: FakeDB, user_id: int, row_event_id: int) -> bool:
    return db.has_any_event_permission(user_id, row_event_id, MESSAGES_VIEW)


def can_insert(db: FakeDB, user_id: int, new_event_id: int) -> bool:
    return db.has_any_event_permission(user_id, new_event_id, MESSAGES_VIEW)


def can_update(db: FakeDB, user_id: int, row_event_id: int, new_event_id: int) -> bool:
    # USING על השורה הישנה, WITH CHECK על השורה החדשה — שתיהן חייבות לעבור.
    return (
        db.has_any_event_permission(user_id, row_event_id, MESSAGES_WRITE)
        and db.has_any_event_permission(user_id, new_event_id, MESSAGES_WRITE)
    )


def can_delete(db: FakeDB, user_id: int, row_event_id: int) -> bool:
    return db.has_any_event_permission(user_id, row_event_id, MESSAGES_WRITE)


def _fixture() -> FakeDB:
    db = FakeDB()
    db.owners = {100: 1, 200: 2}          # אירוע 100 בבעלות משתמש 1, אירוע 200 בבעלות משתמש 2
    db.admins = {99}
    db.member_perms = {
        (10, 100): {"send_messages"},      # חבר מורשה מלא (מפיק) באירוע 100
        (20, 100): {"view_event"},         # חבר צופה-בלבד (אולם) באירוע 100
        (30, 100): set(),                  # חבר "פעיל" בלי אף הרשאה
    }
    return db


def test_owner_full_access() -> None:
    db = _fixture()
    assert can_select(db, 1, 100)
    assert can_insert(db, 1, 100)
    assert can_update(db, 1, 100, 100)
    assert can_delete(db, 1, 100)
    print("✓ בעלים: SELECT/INSERT/UPDATE/DELETE מלא על האירוע שלו")


def test_admin_full_access() -> None:
    db = _fixture()
    assert can_select(db, 99, 100)
    assert can_insert(db, 99, 100)
    assert can_update(db, 99, 100, 100)
    assert can_delete(db, 99, 100)
    print("✓ אדמין: SELECT/INSERT/UPDATE/DELETE מלא, על כל אירוע")


def test_authorized_member_send_messages() -> None:
    """חבר עם send_messages (מפיק) — גישה מלאה, בדיוק כמו MESSAGES_WRITE."""
    db = _fixture()
    assert can_select(db, 10, 100)
    assert can_insert(db, 10, 100)
    assert can_update(db, 10, 100, 100)
    assert can_delete(db, 10, 100)
    print("✓ חבר עם send_messages: גישה מלאה (SELECT/INSERT/UPDATE/DELETE)")


def test_view_only_member_can_read_and_provision_but_not_write() -> None:
    """חבר צופה-בלבד (view_event, כמו אולם) — יכול SELECT ו-INSERT (ה-
    provisioning האוטומטי ב-GET /communication/sequence), אבל לא UPDATE/DELETE.
    זה בדיוק התרחיש שה-INSERT הרחב יותר נועד לשמר."""
    db = _fixture()
    assert can_select(db, 20, 100)
    assert can_insert(db, 20, 100), "INSERT חייב לעבוד לצופה-בלבד — אחרת GET הראשון על אירוע חדש נשבר"
    assert not can_update(db, 20, 100, 100)
    assert not can_delete(db, 20, 100)
    print("✓ חבר צופה-בלבד (view_event): SELECT+INSERT מותרים, UPDATE+DELETE חסומים")


def test_member_without_any_permission_fully_blocked() -> None:
    db = _fixture()
    assert not can_select(db, 30, 100)
    assert not can_insert(db, 30, 100)
    assert not can_update(db, 30, 100, 100)
    assert not can_delete(db, 30, 100)
    print("✓ חבר-אירוע בלי אף הרשאה: כל הפעולות חסומות")


def test_cross_tenant_user_from_other_event_fully_blocked() -> None:
    """משתמש 2 (בעלים של אירוע 200) מנסה לגעת בשורות של אירוע 100 — שלו
    בעצמו, לא חבר בו בכלל. זה בדיוק תרחיש ה-Cross-Tenant שהתבקש."""
    db = _fixture()
    assert not can_select(db, 2, 100)
    assert not can_insert(db, 2, 100)
    assert not can_update(db, 2, 100, 100)
    assert not can_delete(db, 2, 100)
    # ולוודא שהוא כן רואה את האירוע שלו — לא סתם "הכול חסום" גורף.
    assert can_select(db, 2, 200)
    print("✓ Cross-Tenant: משתמש מאירוע אחר חסום לגמרי מול אירוע 100, אך רואה את אירוע 200 שלו")


def test_cannot_reassign_event_id_to_unauthorized_event() -> None:
    """חבר מורשה (send_messages) באירוע 100 מנסה UPDATE שמעביר שורה לאירוע
    200 (שהוא לא מורשה אליו) — ה-WITH CHECK על השורה החדשה חייב לחסום."""
    db = _fixture()
    assert can_update(db, 10, 100, 100)          # עדכון רגיל בתוך האירוע שלו — מותר
    assert not can_update(db, 10, 100, 200)       # ניסיון "להעביר" לאירוע 200 — חסום
    print("✓ ניסיון לשנות event_id לאירוע לא-מורשה (200) חסום ע\"י WITH CHECK")


def test_owner_can_reassign_between_own_events() -> None:
    """בעלים ששני האירועים שלו (100 ו-חדש) — מותר, כי הוא מורשה בשניהם.
    לא סתירה: זה בדיוק המשמעות של 'אירוע שהוא מורשה אליו'."""
    db = _fixture()
    db.owners[300] = 1  # אותו בעלים (משתמש 1) גם באירוע 300
    assert can_update(db, 1, 100, 300)
    print("✓ בעלים יכול 'להעביר' שורה רק בין שני אירועים שהוא בעלים של שניהם")


if __name__ == "__main__":
    test_owner_full_access()
    test_admin_full_access()
    test_authorized_member_send_messages()
    test_view_only_member_can_read_and_provision_but_not_write()
    test_member_without_any_permission_fully_blocked()
    test_cross_tenant_user_from_other_event_fully_blocked()
    test_cannot_reassign_event_id_to_unauthorized_event()
    test_owner_can_reassign_between_own_events()
    print()
    print("=== כל תרחישי ה-RLS (סימולציה לוגית, לא DB חי) עברו ===")
