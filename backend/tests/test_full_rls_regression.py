"""שלב 3: ולידציה מלאה של המערכת תחת ``veya_app`` + RLS אמיתי (לא Production).

מריץ את ``_rls_full_regression_worker.py`` — כל 9 המקומות שזוהו בחקירה
(create_event, communication/sequence, guests/set_group_note,
constraints/analyze+resolve_clarification, automation/advance_track,
admin/create_account+update_user+set_caller_assignments) + רגרסיה על
auth/RSVP/partners/seating/postponement/gifts-payout/guest-management,
כולל מטריצת הרשאות בין שני משתמשים (A/B).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.rls_pg_harness import start_ephemeral_postgres

WORKER = Path(__file__).resolve().parent / "_rls_full_regression_worker.py"
BACKEND_DIR = Path(__file__).resolve().parent.parent


def _run_worker(veya_app_dsn: str, admin_dsn: str, *, legacy: bool) -> dict:
    env = dict(os.environ)
    env["DATABASE_URL"] = veya_app_dsn
    env["MIGRATIONS_DATABASE_URL"] = admin_dsn
    env["JWT_SECRET"] = "test-secret-not-for-production-usage"
    env.pop("VEYA_ENV", None)
    args = [sys.executable, str(WORKER)]
    if legacy:
        args.append("--legacy")
    proc = subprocess.run(
        args, cwd=str(BACKEND_DIR), env=env,
        capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, (
        f"worker (legacy={legacy}) נכשל בריצה עצמה — "
        f"stdout={proc.stdout!r} stderr={proc.stderr[-6000:]!r}"
    )
    last_line = proc.stdout.strip().splitlines()[-1]
    return json.loads(last_line)


@pytest.fixture(scope="module")
def pg():
    harness = start_ephemeral_postgres()
    yield harness
    harness.cleanup()


@pytest.fixture(scope="module")
def fixed_result(pg):
    return _run_worker(pg.veya_app_dsn, pg.admin_dsn, legacy=False)


SCENARIO_NAMES = [
    "01_create_event",
    "02_communication_sequence",
    "03_guests_set_group_note",
    "04_constraints_analyze",
    "05_constraints_resolve_clarification",
    "06_automation_advance_track",
    "07_admin_create_account",
    "08_admin_update_user",
    "09_admin_set_caller_assignments",
    "reg_auth",
    "reg_rsvp_confirm",
    "reg_partners",
    "reg_seating",
    "reg_postponement",
    "reg_gifts_payout",
    "reg_guest_management",
]


@pytest.mark.parametrize("name", SCENARIO_NAMES)
def test_scenario_ok_under_fixed_mechanism(fixed_result, name):
    entry = fixed_result.get(name)
    assert entry is not None, f"תרחיש {name} לא רץ בכלל"
    assert entry.get("ok") is True, f"{name} נכשל: {entry}"


def test_01_create_event_full_message_sequence(fixed_result):
    e = fixed_result["01_create_event"]
    assert e["event_messages_count"] == 6, e


def test_02_sequence_read_after_commit_and_isolation(fixed_result):
    e = fixed_result["02_communication_sequence"]
    assert e["rows_returned"] == 6, e
    assert e.get("other_user_denied") is True, e


def test_03_guests_write_and_cross_user_denied(fixed_result):
    e = fixed_result["03_guests_set_group_note"]
    assert e.get("other_user_read_denied") is True, e
    assert e.get("other_user_write_denied") is True, e


def test_04_and_05_clarification_lifecycle(fixed_result):
    a = fixed_result["04_constraints_analyze"]
    assert a["ambiguity_detected"] is True, (
        "פרסור ה'דני' העמום לא זוהה — לא בעיית RLS, תלוי בלוגיקת הפרסור"
    )
    assert a["pending_clarifications_reported"] == a["pending_clarifications_ground_truth"]
    r = fixed_result["05_constraints_resolve_clarification"]
    assert r["pending_after_ground_truth"] == 0, r


def test_06_advance_track_reads_after_commit(fixed_result):
    e = fixed_result["06_automation_advance_track"]
    assert e["sent"] == 1, e


def test_07_admin_create_account_audit_survives_commit(fixed_result):
    e = fixed_result["07_admin_create_account"]
    assert e["audit_log_written"] is True, e


def test_08_admin_update_user_counts_after_commit(fixed_result):
    e = fixed_result["08_admin_update_user"]
    assert e["events_count_reported"] == e["events_count_ground_truth"], e
    assert e["guests_count_reported"] == e["guests_count_ground_truth"], e
    assert e["events_count_ground_truth"] >= 1, e


def test_09_admin_caller_assignments_persist_after_commit(fixed_result):
    e = fixed_result["09_admin_set_caller_assignments"]
    assert e["assignment_persisted"] is True, e


def test_partners_full_vs_limited_permission(fixed_result):
    e = fixed_result["reg_partners"]
    assert e["partner_full_access_read"] is True, e
    assert e["partner_full_access_write"] is True, e
    assert e["planner_limited_read"] is True, e
    assert e["planner_write_denied"] is True, e


def test_seating_persists_and_isolated(fixed_result):
    e = fixed_result["reg_seating"]
    assert e["persisted"] is True, e
    assert e["seated_ground_truth"] == 2, e
    assert e["other_user_sees_seating"] is False, e


def test_gifts_payout_isolated(fixed_result):
    e = fixed_result["reg_gifts_payout"]
    assert e["owner_sees_gift"] is True, e
    assert e["owner_sees_payout_account"] is True, e
    assert e["other_user_gift_denied"] is True, e
    assert e["other_user_payout_denied"] is True, e


def test_guest_management_full_permission_matrix(fixed_result):
    e = fixed_result["reg_guest_management"]
    assert e["other_user_read_denied"] is True, e
    assert e["other_user_update_denied"] is True, e
    assert e["other_user_delete_denied"] is True, e
    assert e["guest_still_exists_after_attacks"] is True, e


# ── השוואה מול המנגנון הישן: מוכיח שהתיקון הוא מה שעושה את ההבדל ───────────
#
# כל assertion כאן אומת בפועל מול ריצה אמיתית (legacy=True) לפני שנכתב —
# לא ניחוש. שני ממצאים מעניינים שהריצה בפועל תיקנה מול ההשערה הראשונית
# (חקירת שלב 1, שהתבססה על ניתוח סטטי בלבד):
#   * admin/create_account כן עובד גם תחת המנגנון הישן — מדיניות ה-INSERT
#     של audit_logs היא ``WITH CHECK (true)`` (פתוחה בכוונה, כדי שגם נתיבים
#     ציבוריים-לגמרי יוכלו לרשום יומן) — אז "שני commits עם audit באמצע"
#     לא באמת חושף לסיכון RLS כאן. ניתוח סטטי לבדו לא יכול היה לגלות זאת.
#   * admin/set_caller_assignments כן עובד גם תחת הישן — ``assigned_event_ids``
#     בתשובה נבנה ישירות מ-``payload.event_ids`` (קלט הבקשה), לא משאילתת DB
#     אחרי ה-commit, ולכן אינו רגיש לזהות. השדות שכן היו רגישים
#     (``calls_made``/``waiting_tasks``) יצאו 0 בשני המצבים בהרכב הבדיקה
#     הזה (אין באמת שיחות/תור בהתקנה) — לא מפלים בין המנגנונים כאן.


@pytest.fixture(scope="module")
def legacy_result(pg):
    return _run_worker(pg.veya_app_dsn, pg.admin_dsn, legacy=True)


def test_legacy_01_create_event_orphans_the_event(legacy_result):
    e = legacy_result["01_create_event"]
    assert e["ok"] is False, e
    assert e["ground_truth"]["event_row_exists"] is True, e
    assert e["ground_truth"]["event_messages_count"] == 0, e


def test_legacy_02_sequence_read_returns_empty(legacy_result):
    e = legacy_result["02_communication_sequence"]
    assert e["rows_returned"] == 0, e  # אמיתי: 6


def test_legacy_03_guests_group_note_count_wrong(legacy_result):
    e = legacy_result["03_guests_set_group_note"]
    assert e["groups_count"] == 0, e  # אמיתי: 2


def test_legacy_04_clarification_count_wrong(legacy_result):
    e = legacy_result["04_constraints_analyze"]
    assert e["pending_clarifications_reported"] == 0, e
    assert e["pending_clarifications_ground_truth"] == 1, e  # השורה כן נוצרה — רק הקריאה חוזרת שגויה


def test_legacy_06_advance_track_crashes(legacy_result):
    e = legacy_result["06_automation_advance_track"]
    assert e["ok"] is False, e


def test_legacy_08_admin_update_user_counts_wrong(legacy_result):
    e = legacy_result["08_admin_update_user"]
    assert e["events_count_reported"] == 0, e
    assert e["events_count_ground_truth"] == 2, e  # השדה בתשובה שגוי, לא הנתון עצמו


def test_legacy_rsvp_guest_token_lost_after_commit(legacy_result):
    e = legacy_result["reg_rsvp_confirm"]
    assert e["guest_token_survives_commit"] is False, e
