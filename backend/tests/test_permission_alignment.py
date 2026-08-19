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
# call_logs (Call Center) קיבל RLS בקובץ נפרד משלו, מאותה סיבה: הטבלה נוצרת
# ע"י create_all ולכן נולדת בלי RLS. ראו 06_call_logs_rls.sql.
CALL_LOGS_SQL_PATH = RLS_DIR / "06_call_logs_rls.sql"
# תפקיד "טלפן" (phone_agent) מרחיב שלוש ממדיניויות call_logs בקובץ 7, כדי
# שטלפן יוכל לתעד שיחה באירוע שהוקצה לו. ההרחבה היא ``OR`` בלבד — רשימות
# ההרשאות עצמן חייבות להישאר זהות לאלה שבקובץ 6, אחרת שני הקבצים יסתרו זה
# את זה בהתאם לסדר ההרצה. הבדיקה למטה נועלת בדיוק את זה.
PHONE_AGENT_SQL_PATH = RLS_DIR / "07_phone_agent_rls.sql"

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

# call_logs: SELECT תחת MESSAGES_VIEW (מי שרשאי "לדעת מה קרה מול המוזמנים"),
# INSERT/UPDATE תחת MESSAGES_WRITE (תיעוד שיחה = פעולת תקשורת). ל-DELETE אין
# קבוע יחיד ב-permissions.py: הוא נדרש בשני מסלולי מחיקה שונים — מחיקת אירוע/
# חשבון (send_messages, דרך הבעלים) ומחיקת מוזמן בודד (edit_guests), ולכן
# נבדק בנפרד למטה מול איחוד השניים.
CALL_LOGS_POLICY_TO_CONSTANT = {
    "call_logs_select": permissions.MESSAGES_VIEW,
    "call_logs_insert": permissions.MESSAGES_WRITE,
    "call_logs_update": permissions.MESSAGES_WRITE,
}

# כל הפונקציות שקובץ ה-RLS של call_logs מסתמך עליהן — חייבות להיות מוגדרות
# ב-01_helpers_and_grants.sql, אחרת ההרצה על Postgres תיכשל.
HELPERS_SQL_PATH = RLS_DIR / "01_helpers_and_grants.sql"


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

    call_logs_sql = CALL_LOGS_SQL_PATH.read_text(encoding="utf-8")
    for policy_name, expected in CALL_LOGS_POLICY_TO_CONSTANT.items():
        actual = set(_extract_array(call_logs_sql, policy_name))
        if actual != set(expected):
            failures.append(
                f"{policy_name}: SQL={sorted(actual)} != permissions.py={sorted(expected)}"
            )
    # DELETE של call_logs מכסה את שני מסלולי המחיקה בקוד (account.py ו-
    # guests.py), ולכן הוא איחוד של שתי ההרשאות ולא קבוע יחיד.
    delete_actual = set(_extract_array(call_logs_sql, "call_logs_delete"))
    delete_expected = set(permissions.MESSAGES_WRITE) | {"edit_guests"}
    if delete_actual != delete_expected:
        failures.append(
            f"call_logs_delete: SQL={sorted(delete_actual)} != {sorted(delete_expected)}"
        )

    # קובץ 7 (טלפן) כותב מחדש שלוש ממדיניויות call_logs עם ``OR`` נוסף —
    # רשימות ההרשאות בתוכן חייבות להישאר זהות לקובץ 6.
    agent_sql = PHONE_AGENT_SQL_PATH.read_text(encoding="utf-8")
    for policy_name, expected in CALL_LOGS_POLICY_TO_CONSTANT.items():
        actual = set(_extract_array(agent_sql, policy_name))
        if actual != set(expected):
            failures.append(
                f"07/{policy_name}: SQL={sorted(actual)} != permissions.py={sorted(expected)}"
            )
        if "app_agent_assigned_to_event" not in agent_sql:
            failures.append(f"07/{policy_name}: ההרחבה לטלפן חסרה")

    # כל טבלה שמוגנת ב-RLS חייבת גם ENABLE וגם FORCE — אחרת בעל הטבלה עוקף.
    for table, sql_text in (
        ("call_logs", call_logs_sql),
        ("event_messages", event_messages_sql),
        ("call_assignments", agent_sql),
    ):
        for clause in ("ENABLE ROW LEVEL SECURITY", "FORCE  ROW LEVEL SECURITY"):
            if f"ALTER TABLE {table} {clause}" not in sql_text:
                failures.append(f"{table}: חסר '{clause}'")

    # כל פונקציית עזר שנקראת בקובץ RLS חייבת להיות מוגדרת בקובץ ההלפרים.
    helpers_sql = HELPERS_SQL_PATH.read_text(encoding="utf-8")
    defined = set(re.findall(r"CREATE OR REPLACE FUNCTION (\w+)", helpers_sql))
    used = set(re.findall(r"\b(app_\w+)\s*\(", call_logs_sql))
    missing = sorted(used - defined)
    if missing:
        failures.append(f"call_logs RLS משתמש בפונקציות שלא מוגדרות: {missing}")
    # קובץ 7 מגדיר שתי פונקציות עזר משלו — אלה מותרות; כל השאר חייב לבוא
    # מקובץ ההלפרים.
    agent_defined = set(re.findall(r"CREATE OR REPLACE FUNCTION (\w+)", agent_sql))
    agent_missing = sorted(
        set(re.findall(r"\b(app_\w+)\s*\(", agent_sql)) - defined - agent_defined
    )
    if agent_missing:
        failures.append(f"07 RLS משתמש בפונקציות שלא מוגדרות: {agent_missing}")

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

    total_policies = (
        len(POLICY_TO_CONSTANT)
        + len(EVENT_MESSAGES_POLICY_TO_CONSTANT)
        + len(CALL_LOGS_POLICY_TO_CONSTANT)
        + 1  # call_logs_delete (נבדק בנפרד — איחוד שתי הרשאות)
    )
    print(f"OK — {total_policies} policies aligned, {len(containments)} containments verified.")


if __name__ == "__main__":
    main()
