"""בודק שהרשימות ב-app/permissions.py זהות (כקבוצה) ל-ARRAY[...] המקביל
ב-backend/rls/*.sql, לכל מדיניות שמבוססת על app_has_any_event_permission(...).

זו לא בדיקת אינטגרציה מול Postgres אמיתי (אין כזה בסביבת הפיתוח) — רק בדיקה
סטטית שמונעת מהשכבה האפליקטיבית (EventAccess) ומהמדיניות ב-DB לסטות זו מזו
בטעות בעריכה עתידית. הרצה: ``python tests/test_permission_alignment.py``
(עובד גם בלי pytest מותקן — סקריפט עצמאי עם ``assert``).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import permissions  # noqa: E402

RLS_DIR = Path(__file__).resolve().parent.parent / "rls"
SQL_PATH = RLS_DIR / "02_policies.sql"
# event_messages קיבל RLS בקובץ נפרד (05_event_messages_rls.sql) — נוסף אחרי
# 02_policies.sql המקורי, ראו שם את הסבר ה-root cause. נבדק כאן יחד עם השאר.
EVENT_MESSAGES_SQL_PATH = RLS_DIR / "05_event_messages_rls.sql"

# שם המדיניות ב-SQL -> הקבוע המקביל ב-app/permissions.py.
POLICY_TO_CONSTANT = {
    "events_select": permissions.EVENTS_VIEW,
    "events_update": permissions.EVENTS_UPDATE,
    "guests_select": permissions.GUESTS_VIEW,
    "guests_write": permissions.GUESTS_WRITE,
    "messages_select": permissions.MESSAGES_VIEW,
    "messages_write": permissions.MESSAGES_WRITE,
    "clarifications_rw": permissions.CLARIFICATIONS,
    "automation_rules_rw": permissions.AUTOMATION,
    "message_templates_rw": permissions.AUTOMATION,
}

# event_messages: SELECT/INSERT תחת MESSAGES_VIEW (ה-INSERT מכסה את ה-
# provisioning האוטומטי שקורה בתוך GET /communication/sequence — ראו
# 05_event_messages_rls.sql), UPDATE/DELETE תחת MESSAGES_WRITE (בדיוק כמו
# routers/communication.py: _view/_write).
EVENT_MESSAGES_POLICY_TO_CONSTANT = {
    "event_messages_select": permissions.MESSAGES_VIEW,
    "event_messages_insert": permissions.MESSAGES_VIEW,
    "event_messages_update": permissions.MESSAGES_WRITE,
    "event_messages_delete": permissions.MESSAGES_WRITE,
}


def _extract_array(sql: str, policy_name: str) -> list[str]:
    """מוצא את ה-ARRAY[...] הראשון אחרי ``CREATE POLICY <policy_name>``."""
    marker = re.search(rf"CREATE POLICY {re.escape(policy_name)}\b", sql)
    assert marker, f"לא נמצאה מדיניות {policy_name}"
    start = sql.index("ARRAY[", marker.end())
    end = sql.index("]", start)
    body = sql[start + len("ARRAY[") : end]
    return [tok.strip().strip("'") for tok in body.split(",") if tok.strip()]


def main() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    event_messages_sql = EVENT_MESSAGES_SQL_PATH.read_text(encoding="utf-8")
    failures = []
    for policy_name, expected in POLICY_TO_CONSTANT.items():
        actual = set(_extract_array(sql, policy_name))
        if actual != set(expected):
            failures.append(
                f"{policy_name}: SQL={sorted(actual)} != permissions.py={sorted(expected)}"
            )
    for policy_name, expected in EVENT_MESSAGES_POLICY_TO_CONSTANT.items():
        actual = set(_extract_array(event_messages_sql, policy_name))
        if actual != set(expected):
            failures.append(
                f"{policy_name}: SQL={sorted(actual)} != permissions.py={sorted(expected)}"
            )

    # בדיקת הכלה: כל קבוצת app-layer צריכה להיות תת-קבוצה של (או שווה ל)
    # מה שה-RLS מרשה בפועל — כדי שהאפליקציה לעולם לא תהיה *מתירנית יותר* מה-DB.
    containments = [
        ("HALL_VIEW", permissions.HALL_VIEW, "EVENTS_VIEW", permissions.EVENTS_VIEW),
        ("HALL_WRITE", permissions.HALL_WRITE, "EVENTS_UPDATE", permissions.EVENTS_UPDATE),
        ("SEATING_WRITE", permissions.SEATING_WRITE, "GUESTS_WRITE", permissions.GUESTS_WRITE),
    ]
    for name_a, a, name_b, b in containments:
        if not set(a) <= set(b):
            failures.append(f"{name_a} {a} is not a subset of {name_b} {b}")

    if failures:
        print("FAILED — permission alignment drift found:")
        for f in failures:
            print(" -", f)
        sys.exit(1)

    total_policies = len(POLICY_TO_CONSTANT) + len(EVENT_MESSAGES_POLICY_TO_CONSTANT)
    print(f"OK — {total_policies} policies aligned, {len(containments)} containments verified.")


if __name__ == "__main__":
    main()
