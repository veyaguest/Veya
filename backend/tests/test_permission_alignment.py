"""בודק שהרשימות ב-app/permissions.py זהות (כקבוצה) ל-ARRAY[...] המקביל
ב-backend/rls/02_policies.sql, לכל מדיניות שמבוססת על
app_has_any_event_permission(...).

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

SQL_PATH = Path(__file__).resolve().parent.parent / "rls" / "02_policies.sql"

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


def _extract_array(sql: str, policy_name: str) -> list[str]:
    """מוצא את ה-ARRAY[...] הראשון אחרי ``CREATE POLICY <policy_name>``."""
    marker = re.search(rf"CREATE POLICY {re.escape(policy_name)}\b", sql)
    assert marker, f"לא נמצאה מדיניות {policy_name} ב-02_policies.sql"
    start = sql.index("ARRAY[", marker.end())
    end = sql.index("]", start)
    body = sql[start + len("ARRAY[") : end]
    return [tok.strip().strip("'") for tok in body.split(",") if tok.strip()]


def main() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    failures = []
    for policy_name, expected in POLICY_TO_CONSTANT.items():
        actual = set(_extract_array(sql, policy_name))
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

    print(f"OK — {len(POLICY_TO_CONSTANT)} policies aligned, {len(containments)} containments verified.")


if __name__ == "__main__":
    main()
