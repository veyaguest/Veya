"""בדיקת אימות מלאה של RLS על סביבת Staging אמיתית (Postgres + Supabase).

לא רץ אוטומטית כחלק מ-CI/מ-SQLite — זה סקריפט עצמאי שרץ מול שרת VEYA אמיתי
שכבר מחובר ל-staging DB דרך תפקיד ``veya_app`` (לא superuser), אחרי הרצת
``backend/rls/01_helpers_and_grants.sql`` + ``02_policies.sql``. ראו את
הוראות ההרצה המלאות ב-``backend/rls/STAGING_PLAN.md``.

משתני סביבה נדרשים:
  STAGING_BASE_URL     — כתובת ה-API של השרת שרץ מול ה-staging (למשל
                         http://localhost:8000 אם מריצים uvicorn מקומית
                         עם DATABASE_URL מוצבע ל-staging).
  STAGING_ADMIN_DB_URL — connection string ל-staging *כ-postgres* (superuser).
                         משמש רק להכנת/ניקוי נתוני-בדיקה (עוקף RLS בכוונה —
                         זה ה-harness, לא חלק מהבדיקה עצמה) ולאימות ישיר של
                         תוצאות (למשל בדיקת ה-webhook, שהוא endpoint ציבורי
                         בלי תשובת HTTP שחושפת את הסטטוס הפנימי).

בלי שני המשתנים — הסקריפט מדפיס הסבר ויוצא (exit code 0, לא נכשל), כדי
שהרצה בטעות בסביבה בלי staging לא תיראה כמו כישלון.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import psycopg2
import psycopg2.extras

REPORT_PATH = Path(__file__).resolve().parent.parent / "rls" / "STAGING_TEST_REPORT.md"


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""
    critical: bool = True


RESULTS: list[Result] = []


def check(name: str, condition: bool, detail: str = "", critical: bool = True) -> None:
    RESULTS.append(Result(name, condition, detail, critical))
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))


def check_status(name: str, resp, expected: int, critical: bool = True) -> None:
    """כמו check(), אבל תמיד מדפיס status+body בכשלון — לצורך אבחון מהיר."""
    ok = resp.status_code == expected
    detail = f"expected={expected} got={resp.status_code}"
    if not ok:
        detail += f" body={resp.text[:200]}"
    check(name, ok, detail, critical)


def main() -> int:
    base_url = os.getenv("STAGING_BASE_URL")
    admin_db_url = os.getenv("STAGING_ADMIN_DB_URL")
    if not base_url or not admin_db_url:
        print(
            "חסרים משתני סביבה STAGING_BASE_URL / STAGING_ADMIN_DB_URL — "
            "ראו backend/rls/STAGING_PLAN.md. מדלג (לא נכשל)."
        )
        return 0

    suffix = uuid.uuid4().hex[:8]  # מבודד כל הרצה — אין התנגשות עם הרצות קודמות
    conn = psycopg2.connect(admin_db_url)
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    created_user_ids: list[int] = []
    created_event_ids: list[int] = []

    def emails(*names: str) -> dict[str, str]:
        return {n: f"{n}.{suffix}@staging-test.veya" for n in names}

    e = emails(
        "owner_a", "owner_b", "admin", "planner_full", "planner_partial",
        "venue_full", "venue_partial",
    )

    with httpx.Client(base_url=base_url, timeout=15.0) as http:
        # ── הרשמה (כל המשתמשים נרשמים כ-"couple" — זה מה שה-API הציבורי
        # תומך בו; planner/venue הופכים לכאלה ישירות ב-DB, בדיוק כמו
        # שהיה קורה בעולם האמיתי דרך תהליך onboarding נפרד/אדמין, שאינו
        # חלק מהיקף בדיקת ה-RLS הזו) ──
        tokens: dict[str, str] = {}
        for key, email in e.items():
            r = http.post(
                "/auth/register",
                json={"email": email, "password": "StagingTest123!", "display_name": key},
            )
            check(f"setup: register {key}", r.status_code == 201, f"status={r.status_code}")
            if r.status_code == 201:
                tokens[key] = r.json()["access_token"]

        # שולפים user_id-ים לשימוש בהכנת EventMember/is_admin ישירות ב-DB.
        cur.execute("select id, email from users where email = any(%s)", (list(e.values()),))
        user_id_by_email = {row["email"]: row["id"] for row in cur.fetchall()}
        created_user_ids = list(user_id_by_email.values())

        # owner_a/owner_b חייבים להיות אדמין-על=false במפורש: אם השרשור הזה
        # רץ על טבלה ריקה, owner_a (שנרשם ראשון) היה הופך "בטעות" לאדמין
        # אמיתי לפי הכלל "המשתמש הראשון = אדמין" — ואז בדיקת "owner isolation"
        # למטה הייתה נכשלת כי אדמין רואה הכול, כמצופה, לא בגלל פרצת RLS.
        cur.execute(
            "update users set is_admin=false where id in (%s, %s)",
            (user_id_by_email[e["owner_a"]], user_id_by_email[e["owner_b"]]),
        )
        cur.execute(
            "update users set account_type='planner' where id in (%s, %s)",
            (user_id_by_email[e["planner_full"]], user_id_by_email[e["planner_partial"]]),
        )
        cur.execute(
            "update users set account_type='venue' where id in (%s, %s)",
            (user_id_by_email[e["venue_full"]], user_id_by_email[e["venue_partial"]]),
        )
        cur.execute("update users set is_admin=true where id=%s", (user_id_by_email[e["admin"]],))

        # ── אירוע A (owner_a) + אירוע B (owner_b, לבדיקת בידוד בין אירועים) ──
        oh_a = {"Authorization": f"Bearer {tokens['owner_a']}"}
        oh_b = {"Authorization": f"Bearer {tokens['owner_b']}"}
        ah = {"Authorization": f"Bearer {tokens['admin']}"}

        ev_a = http.post("/events", json={
            "event_type": "wedding", "groom_name": "דני", "bride_name": "מיכל", "venue_name": "אולם A",
        }, headers=oh_a)
        check("setup: create event A", ev_a.status_code == 201, f"status={ev_a.status_code}")
        event_a = ev_a.json()["id"]

        ev_b = http.post("/events", json={
            "event_type": "wedding", "groom_name": "יוסי", "bride_name": "שרה", "venue_name": "אולם B",
        }, headers=oh_b)
        check("setup: create event B", ev_b.status_code == 201, f"status={ev_b.status_code}")
        event_b = ev_b.json()["id"]
        created_event_ids = [event_a, event_b]

        # חברי-אירוע על אירוע A בלבד — עם הרשאות מלאות/חלקיות.
        cur.execute(
            """insert into event_members (event_id, user_id, role, permissions, status, invited_by_id)
               values (%s,%s,'planner',%s,'active',%s)""",
            (event_a, user_id_by_email[e["planner_full"]],
             psycopg2.extras.Json(["view_guests", "edit_guests", "manage_seating", "send_messages", "view_reports"]),
             user_id_by_email[e["owner_a"]]),
        )
        cur.execute(
            """insert into event_members (event_id, user_id, role, permissions, status, invited_by_id)
               values (%s,%s,'planner',%s,'active',%s)""",
            (event_a, user_id_by_email[e["planner_partial"]],
             psycopg2.extras.Json(["view_guests"]), user_id_by_email[e["owner_a"]]),
        )
        cur.execute(
            """insert into event_members (event_id, user_id, role, permissions, status, invited_by_id)
               values (%s,%s,'venue',%s,'active',%s)""",
            (event_a, user_id_by_email[e["venue_full"]],
             psycopg2.extras.Json(["view_event", "view_seating", "edit_seating", "manage_venue_data"]),
             user_id_by_email[e["owner_a"]]),
        )
        cur.execute(
            """insert into event_members (event_id, user_id, role, permissions, status, invited_by_id)
               values (%s,%s,'venue',%s,'active',%s)""",
            (event_a, user_id_by_email[e["venue_partial"]],
             psycopg2.extras.Json(["view_event"]), user_id_by_email[e["owner_a"]]),
        )

        pf_h = {"Authorization": f"Bearer {tokens['planner_full']}", "X-Event-Id": str(event_a)}
        pp_h = {"Authorization": f"Bearer {tokens['planner_partial']}", "X-Event-Id": str(event_a)}
        vf_h = {"Authorization": f"Bearer {tokens['venue_full']}", "X-Event-Id": str(event_a)}
        vp_h = {"Authorization": f"Bearer {tokens['venue_partial']}", "X-Event-Id": str(event_a)}

        guest = http.post("/guests", json={
            "full_name": "מוזמן בדיקה", "phone": "0501234567", "party_size": 2,
        }, headers=oh_a)
        check("setup: owner creates guest", guest.status_code == 201, f"status={guest.status_code}")
        guest_id = guest.json()["id"]
        guest_token = guest.json()["guest_token"]

        # ============================================================
        # 1. Owner access
        # ============================================================
        check_status("owner: list own guests", http.get("/guests", headers=oh_a), 200)
        check_status("owner: read own event", http.get("/event", headers=oh_a), 200)
        check_status(
            "owner: update own event core fields",
            http.patch("/event", json={"groom_name": "דני 2"}, headers=oh_a), 200,
        )
        check_status(
            "owner isolation: cannot see event B via X-Event-Id",
            http.get("/guests", headers={**oh_a, "X-Event-Id": str(event_b)}), 404,
        )

        # ============================================================
        # 2. Admin access
        # ============================================================
        check_status(
            "admin: list all events (cross-tenant)",
            http.get("/admin/events", headers=ah), 200, critical=False,
        )
        check_status(
            "admin: can act on event A guests via header",
            http.get("/guests", headers={**ah, "X-Event-Id": str(event_a)}), 200,
        )
        check_status(
            "admin: can act on event B guests via header",
            http.get("/guests", headers={**ah, "X-Event-Id": str(event_b)}), 200,
        )

        # ============================================================
        # 3. Producer (planner) access — full vs. partial permissions
        # ============================================================
        check_status("planner full: view guests", http.get("/guests", headers=pf_h), 200)
        check_status(
            "planner full: edit guests",
            http.post("/guests", json={"full_name": "X", "phone": "0500000001", "party_size": 1}, headers=pf_h), 201,
        )
        check_status(
            "planner full: manage seating",
            http.post("/seating/assign", json={"guest_id": guest_id, "table_number": 3}, headers=pf_h), 200,
        )
        check_status(
            "planner full: send messages permission recognized",
            http.get("/automation/templates", headers=pf_h), 200,
        )
        check_status(
            "planner full: cannot edit core event settings (owner-only)",
            http.patch("/event", json={"groom_name": "Hacked"}, headers=pf_h), 404,
        )
        check_status(
            "planner partial (view_guests only): can view guests",
            http.get("/guests", headers=pp_h), 200,
        )
        check_status(
            "planner partial: CANNOT create guests",
            http.post("/guests", json={"full_name": "Y", "phone": "0500000002", "party_size": 1}, headers=pp_h), 403,
        )
        check_status(
            "planner partial: CANNOT access automation/messaging",
            http.get("/automation/templates", headers=pp_h), 403,
        )
        check_status(
            "planner: isolated from event B",
            http.get("/guests", headers={**pf_h, "X-Event-Id": str(event_b)}), 404,
        )

        # ============================================================
        # 4. Venue access — full vs. partial permissions
        # ============================================================
        check_status("venue full: view hall", http.get("/hall", headers=vf_h), 200)
        check_status(
            "venue full: edit hall/seating",
            http.post("/seating/assign", json={"guest_id": guest_id, "table_number": 5}, headers=vf_h), 200,
        )
        # הערה: venue_full כולל את ההרשאה view_event, וזו נמצאת ב-MESSAGES_VIEW
        # במכוון (מי שרק צריך "לדעת מה קרה" — ראו app/permissions.py) — אז אולם
        # *כן* יכול לצפות בסיכום RSVP, גם בלי send_messages. זה תקין, לא פרצה.
        check_status(
            "venue full: CAN view messages summary (view_event grants read)",
            http.get("/messaging/summary", headers=vf_h), 200,
        )
        check_status(
            "venue full: CANNOT send messages (no send_messages)",
            http.post("/messaging/invitations/send", json={"only_pending": False}, headers=vf_h), 403,
        )
        check_status(
            "venue partial (view_event only): can read event",
            http.get("/event", headers=vp_h), 200,
        )
        check_status(
            "venue partial: CANNOT edit hall",
            http.put("/hall", json={"tables": [], "elements": []}, headers=vp_h), 403, critical=False,
        )

        # ============================================================
        # 5. Guest RSVP access
        # ============================================================
        conf = http.get(f"/confirm/{guest_token}")
        check_status("guest: read own RSVP via token", conf, 200)
        rsvp = http.post(f"/confirm/{guest_token}", json={"coming": True, "count": 2})
        check_status("guest: submit RSVP", rsvp, 200)
        check_status(
            "guest: wrong/random token rejected",
            http.get("/confirm/not-a-real-token-000"), 404,
        )

        # ============================================================
        # 6. WhatsApp webhook flow (unauthenticated, phone-matched)
        # ============================================================
        webhook_payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "972501234567",
                            "button": {"payload": "CONFIRM"},
                        }]
                    }
                }]
            }]
        }
        wh = http.post("/messaging/webhook", json=webhook_payload)
        check_status("webhook: accepted (never errors to Meta)", wh, 200)
        time.sleep(0.3)
        cur.execute("select rsvp_status from guests where id=%s", (guest_id,))
        row = cur.fetchone()
        check(
            "webhook: RSVP actually updated via SECURITY DEFINER path",
            row is not None and row["rsvp_status"] == "confirmed",
            f"rsvp_status={row['rsvp_status'] if row else None}",
        )

        # ============================================================
        # 7. Seating system
        # ============================================================
        seat_gen = http.post("/seating/generate", json={
            "seats_per_table": 10, "num_tables": 2, "persist": True,
        }, headers=oh_a)
        check_status("seating: owner can generate+persist", seat_gen, 200)

        # ============================================================
        # 8. Invitations
        # ============================================================
        inv = http.post("/messaging/invitations/send", json={"only_pending": False}, headers=oh_a)
        check_status("invitations: owner can send", inv, 200)
        inv_blocked = http.post("/messaging/invitations/send", json={"only_pending": False}, headers=pp_h)
        check_status("invitations: view-only planner blocked", inv_blocked, 403)

        # ============================================================
        # 9. Messages
        # ============================================================
        check_status("messages: owner reads summary", http.get("/messaging/summary", headers=oh_a), 200)
        check_status("messages: planner-full reads summary", http.get("/messaging/summary", headers=pf_h), 200)

        # ============================================================
        # 10. Media access
        # ============================================================
        tiny_png_data_uri = (
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        upd = http.patch("/event", json={"invite_image": tiny_png_data_uri}, headers=oh_a)
        check_status("media: owner uploads invite image", upd, 200)
        if upd.status_code == 200:
            img_url = upd.json().get("invite_image") or ""
            blob_path = img_url.split("/media/")[-1] if "/media/" in img_url else None
            if blob_path:
                media_resp = http.get(f"/media/{blob_path}")
                check_status("media: public unauthenticated fetch works", media_resp, 200)
            else:
                check("media: could not resolve blob path", False, f"invite_image={img_url}", critical=False)

        # ── ניקוי — מוחקים את כל נתוני הבדיקה שיצרנו (staging נשאר נקי).
        # סדר חשוב: ילדים לפני הורים (אין ON DELETE CASCADE ברוב הטבלאות).
        # מרחיבים את "אירועי הבדיקה" גם לפי owner_id, לא רק created_event_ids —
        # כדי שריצה קודמת שנכשלה באמצע (ולא ניקתה הכול) לא תשבור את הניקוי
        # הנוכחי עם FK violation (events עדיין מצביע על users שמנסים למחוק).
        cur.execute("select id from events where id = any(%s) or owner_id = any(%s)",
                    (created_event_ids, created_user_ids))
        all_event_ids = [r["id"] for r in cur.fetchall()] or created_event_ids
        cur.execute("delete from messages where event_id = any(%s)", (all_event_ids,))
        cur.execute("delete from clarifications where event_id = any(%s)", (all_event_ids,))
        cur.execute("delete from audit_logs where event_id = any(%s)", (all_event_ids,))
        cur.execute("delete from automation_rules where event_id = any(%s)", (all_event_ids,))
        cur.execute("delete from message_templates where event_id = any(%s)", (all_event_ids,))
        cur.execute("delete from event_members where event_id = any(%s)", (all_event_ids,))
        cur.execute("delete from guests where event_id = any(%s)", (all_event_ids,))
        cur.execute("delete from login_events where user_id = any(%s)", (created_user_ids,))
        cur.execute("delete from events where id = any(%s)", (all_event_ids,))
        cur.execute("delete from users where id = any(%s)", (created_user_ids,))

    cur.close()
    conn.close()

    write_report()
    n_fail_critical = sum(1 for r in RESULTS if not r.ok and r.critical)
    n_fail_noncrit = sum(1 for r in RESULTS if not r.ok and not r.critical)
    print(f"\n{'='*60}\n{len(RESULTS)} checks, {n_fail_critical} critical failures, {n_fail_noncrit} non-critical failures.")
    return 1 if n_fail_critical else 0


def write_report() -> None:
    lines = [
        "# VEYA · דוח בדיקת RLS על Staging",
        "",
        "נוצר אוטומטית ע\"י `tests/test_staging_rls.py`. כל שורה = תרחיש בדיקה אחד.",
        "",
        "| תרחיש | תוצאה | קריטי | פרטים |",
        "|---|---|---|---|",
    ]
    for r in RESULTS:
        mark = "✅ PASS" if r.ok else "❌ FAIL"
        lines.append(f"| {r.name} | {mark} | {'כן' if r.critical else 'לא'} | {r.detail} |")
    n_fail_critical = sum(1 for r in RESULTS if not r.ok and r.critical)
    lines += [
        "",
        f"**סיכום: {len(RESULTS)} בדיקות, {n_fail_critical} כשלים קריטיים.**",
        "",
        (
            "✅ **0 כשלים קריטיים — אפשר לעבור לתוכנית ההפעלה בייצור.**"
            if n_fail_critical == 0
            else "❌ **יש כשלים קריטיים — אין לעבור לייצור לפני שהם נבדקים ומתוקנים.**"
        ),
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nדוח נכתב ל-{REPORT_PATH}")


if __name__ == "__main__":
    sys.exit(main())
