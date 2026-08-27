"""שלב 3: ולידציה מלאה מול Postgres+RLS אמיתי (לא Production) — כל 9 המקומות
שזוהו בחקירה + רגרסיה על auth/RSVP/partners/seating/postponement/gifts-payout/
messaging/guest-management, כולל מטריצת הרשאות בין שני משתמשים (A/B).

אותה שיטה בדיוק כמו שלב 1 (``_rls_identity_worker.py``): תהליך-בת נפרד עם
DATABASE_URL/MIGRATIONS_DATABASE_URL מוצבעים ל-Postgres זמני (``pgserver``),
כל שלב "dependency" מול "גוף endpoint" רץ ב-``run_in_threadpool`` **נפרדת**
משלו כדי לשחזר נאמנה את גבול ה-thread-pool האמיתי של FastAPI, ודגל
``--legacy`` שמחליף את מנגנון הזהות בחזרה ל-ContextVar-בלבד (המצב לפני
התיקון) לצורך השוואה.

מדפיס JSON יחיד ל-stdout: ``{"mechanism": ..., "scenarios": {name: {...}}}``.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SCENARIOS: dict = {}


def _ok(name: str, **kw) -> None:
    SCENARIOS[name] = {"ok": True, **kw}


def _fail(name: str, **kw) -> None:
    SCENARIOS[name] = {"ok": False, **kw}


def _err(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


RLS_SQL_FILES = [
    "01_helpers_and_grants.sql", "02_policies.sql", "04_consent_records_rls_fix.sql",
    "05_event_messages_rls.sql", "06_call_logs_rls.sql", "07_phone_agent_rls.sql",
    "08_partner_comanagement.sql", "09_email_verification_rls_fix.sql",
    "11_event_messages_delete_rls_fix.sql", "12_password_reset.sql",
    "13_gifts_rls.sql", "14_payout_accounts_rls.sql", "15_postponement_rls.sql",
]


class _FakeClient:
    host = "127.0.0.1"


class _FakeRequest:
    """תחליף מינימלי ל-``Request`` — כל מה שה-routers כאן קוראים ממנו הוא
    ``request.client.host if request.client else None``."""

    client = _FakeClient()


async def main(legacy: bool) -> None:
    import psycopg2
    from fastapi.security import HTTPAuthorizationCredentials
    from sqlalchemy import event as sa_event, func, select, text
    from starlette.concurrency import run_in_threadpool

    from app import (
        auth, communication, database, models, partners, postponement_service,
        schemas,
    )
    from app.routers import (
        admin as admin_router,
        automation as automation_router,
        communication as communication_router,
        constraints as constraints_router,
        events as events_router,
        guests as guests_router,
        partner as partner_router,
        postpone as postpone_router,
        seating as seating_router,
    )

    # ── סכימה + כל קובצי ה-RLS (אותו הליך בדיוק כמו שלב 1) ──────────────────
    database.Base.metadata.create_all(bind=database.migrations_engine)
    with database.migrations_engine.begin() as conn:
        for table in database.Base.metadata.tables.values():
            for column in table.columns:
                default = getattr(column, "default", None)
                if default is None or getattr(default, "is_callable", False):
                    continue
                value = getattr(default, "arg", None)
                if isinstance(value, bool):
                    literal = "TRUE" if value else "FALSE"
                elif isinstance(value, (int, float)):
                    literal = str(value)
                elif isinstance(value, str):
                    literal = "'" + value.replace("'", "''") + "'"
                else:
                    continue
                conn.exec_driver_sql(
                    f'ALTER TABLE "{table.name}" ALTER COLUMN "{column.name}" '
                    f"SET DEFAULT {literal}"
                )
    rls_dir = Path(__file__).resolve().parent.parent / "rls"
    admin_conn = psycopg2.connect(os.environ["MIGRATIONS_DATABASE_URL"])
    admin_conn.autocommit = True
    admin_cur = admin_conn.cursor()
    for fname in RLS_SQL_FILES:
        admin_cur.execute((rls_dir / fname).read_text())
    admin_conn.close()

    if legacy:
        sa_event.remove(database.SessionLocal, "after_begin", database._apply_rls_identity)

        @sa_event.listens_for(database.SessionLocal, "after_begin")
        def _legacy_apply_rls_identity(session, transaction, connection):  # noqa: ANN001
            uid = database.current_user_id.get()
            connection.exec_driver_sql(
                "SELECT set_config('app.current_user_id', %s, true)",
                (str(uid) if uid is not None else "",),
            )
            token = database.current_guest_token.get()
            connection.exec_driver_sql(
                "SELECT set_config('app.guest_token', %s, true)",
                (token if token is not None else "",),
            )

    SCENARIOS["_mechanism"] = "legacy_contextvar_only" if legacy else "fixed_session_info"

    # ── משתמשי בדיקה (superuser — עוקף RLS בכוונה, זה ה-harness) ─────────────
    pid = os.getpid()
    admin_session = database.MigrationSessionLocal()
    try:
        user_a = models.User(
            email=f"rls-a-{pid}@veya.test", password_hash=auth.hash_password("Test12345!"),
            display_name="זוג בדיקה א", phone="0501234567",
            email_verified_at=datetime.utcnow(), token_version=1,
        )
        user_b = models.User(
            email=f"rls-b-{pid}@veya.test", password_hash=auth.hash_password("Test12345!"),
            display_name="זוג בדיקה ב", phone="0507654321",
            email_verified_at=datetime.utcnow(), token_version=1,
        )
        user_c = models.User(
            email=f"rls-c-{pid}@veya.test", password_hash=auth.hash_password("Test12345!"),
            display_name="מפיק בדיקה ג", phone="0501111111",
            email_verified_at=datetime.utcnow(), token_version=1,
        )
        admin_user = models.User(
            email=f"rls-admin-{pid}@veya.test", password_hash=auth.hash_password("Test12345!"),
            display_name="אדמין בדיקה", phone="0509999999",
            email_verified_at=datetime.utcnow(), token_version=1, is_admin=True,
        )
        # "זר" אמיתי — אף פעם לא מקבל שום חברות/הרשאה בשום אירוע. B ו-C
        # הופכים לחברי-אירוע לגיטימיים ב-reg_partners (בהמשך הריצה), ולכן
        # אינם מתאימים יותר לבדיקות "משתמש-אחר-נחסם" אחרי אותה נקודה —
        # לכך תמיד משתמשים ב-D.
        user_d = models.User(
            email=f"rls-d-outsider-{pid}@veya.test", password_hash=auth.hash_password("Test12345!"),
            display_name="זר בדיקה ד", phone="0502223344",
            email_verified_at=datetime.utcnow(), token_version=1,
        )
        admin_session.add_all([user_a, user_b, user_c, user_d, admin_user])
        admin_session.commit()
        uid_a, uid_b, uid_c, uid_d, uid_admin = (
            user_a.id, user_b.id, user_c.id, user_d.id, admin_user.id
        )
    finally:
        admin_session.close()

    def sess() -> "database.Session":
        return database.SessionLocal()

    async def as_user(user_id: int, fn):
        """מריץ fn(db) בזהות user_id — הזדהות וקריאת fn בשתי run_in_threadpool
        **נפרדות** (בדיוק כמו get_current_user מול גוף ה-endpoint האמיתי).
        מחזיר את התוצאה, וסוגר את ה-session."""
        db = sess()
        try:
            def _identify():
                database.set_request_identity(user_id, db)
                db.execute(text("SELECT 1"))

            await run_in_threadpool(_identify)
            return await run_in_threadpool(lambda: fn(db))
        finally:
            db.close()
            database.clear_request_identity()

    def gt() -> "database.Session":
        """session לבדיקות ground-truth (superuser, עוקף RLS בכוונה)."""
        return database.MigrationSessionLocal()

    # =========================================================================
    # 1) create_event — commit() ואז provision_event_messages (INSERT רגיל)
    # =========================================================================
    event_a_id = None
    try:
        def _create(db):
            payload = schemas.EventCreate(
                event_type="wedding", groom_name="איתי", bride_name="דנה",
                venue_name="אולם הבדיקה",
            )
            user_obj = db.get(models.User, uid_a)
            return events_router.create_event(payload=payload, db=db, user=user_obj)

        summary = await as_user(uid_a, _create)
        event_a_id = summary.id
        g = gt()
        try:
            count = g.scalar(
                select(func.count()).select_from(models.EventMessage)
                .where(models.EventMessage.event_id == event_a_id)
            )
        finally:
            g.close()
        _ok("01_create_event", event_id=event_a_id, event_messages_count=count)
    except Exception as exc:
        _fail("01_create_event", error=_err(exc))
        # ground truth בכל מקרה — כדי לדעת אם האירוע כן נוצר "יתום"
        g = gt()
        try:
            row = g.scalars(select(models.Event).where(models.Event.owner_id == uid_a)).first()
            if row is not None:
                event_a_id = row.id
                count = g.scalar(
                    select(func.count()).select_from(models.EventMessage)
                    .where(models.EventMessage.event_id == event_a_id)
                )
                SCENARIOS["01_create_event"]["ground_truth"] = {
                    "event_row_exists": True, "event_messages_count": count,
                }
        finally:
            g.close()

    if event_a_id is None:
        # בלי אירוע אין טעם להמשיך לשאר התרחישים — כולם תלויי-אירוע.
        print(json.dumps(SCENARIOS, ensure_ascii=False))
        return

    # תנאי-סף ליצירת אירוע: מייל מאומת + פרופיל מלא (כבר קיים ל-A). B צריך
    # את זה גם כדי לעבור בדיקות שדורשות get_current_owner (לא event משלו).

    # ── עוד אירוע ל-A, לא-מסופק (superuser, לצורך תרחיש #2 בלבד — עוקף את
    # כלל "אירוע אחד למשתמש" שהוא כלל ברמת אפליקציה, לא DB) ───────────────
    g = gt()
    try:
        event_a2 = models.Event(
            owner_id=uid_a, event_type="wedding", groom_name="איתי", bride_name="דנה",
            venue_name="אולם שני (בדיקה בלבד)",
        )
        g.add(event_a2)
        g.commit()
        event_a2_id = event_a2.id
    finally:
        g.close()

    # =========================================================================
    # 2) communication / sequence — _get_sequence: commit() (provisioning) ואז
    #    event_messages_by_type (SELECT)
    # =========================================================================
    try:
        def _get_seq(db):
            ev = db.get(models.Event, event_a2_id)
            return communication_router.get_sequence(db=db, event=ev)

        rows = await as_user(uid_a, _get_seq)
        _ok("02_communication_sequence", rows_returned=len(rows))
    except Exception as exc:
        _fail("02_communication_sequence", error=_err(exc))

    # B לא חבר באירוע — לא אמור לראות אף event_message של event_a2.
    try:
        def _select_as_b(db):
            return db.scalars(
                select(models.EventMessage).where(models.EventMessage.event_id == event_a2_id)
            ).all()

        rows_b = await as_user(uid_d, _select_as_b)
        SCENARIOS["02_communication_sequence"]["other_user_denied"] = len(rows_b) == 0
    except Exception as exc:
        SCENARIOS["02_communication_sequence"]["other_user_denied_error"] = _err(exc)

    # ── מוזמנים לאירוע הראשי (event_a) — בשימוש בכמה תרחישים הבאים ─────────
    g = gt()
    try:
        guest1 = models.Guest(event_id=event_a_id, full_name="שרה כהן", phone="0501112222",
                               group_type="family")
        guest2 = models.Guest(event_id=event_a_id, full_name="יוסי לוי", phone="0502223333",
                               group_type="friends")
        # שני מוזמנים בשם פרטי זהה, בלי שם משפחה מבדל — כדי לעורר עמימות
        # אמיתית בפרסור (ראו CLAUDE.md: "שם פרטי בלבד לא ניתן לשיוך חד-משמעי").
        guest_dani_1 = models.Guest(event_id=event_a_id, full_name="דני", phone="0503334444",
                                     group_type="friends")
        guest_dani_2 = models.Guest(event_id=event_a_id, full_name="דני", phone="0504445555",
                                     group_type="family")
        guest_asks = models.Guest(
            event_id=event_a_id, full_name="משה גורן", phone="0505556666",
            group_type="friends", seating_notes="לא לשבת ליד דני",
        )
        g.add_all([guest1, guest2, guest_dani_1, guest_dani_2, guest_asks])
        g.commit()
        guest1_id, guest2_id = guest1.id, guest2.id
        guest_asks_id = guest_asks.id
    finally:
        g.close()

    # =========================================================================
    # 3) guests / set_group_note — commit() ואז SELECT (ספירת קבוצות)
    # =========================================================================
    try:
        def _set_note(db):
            payload = constraints_group_note_payload = _GroupNotePayload(
                group_type="family", note="לשבת קרוב לבמה"
            )
            ev = db.get(models.Event, event_a_id)
            return guests_router.set_group_note(payload=payload, db=db, event=ev)

        result = await as_user(uid_a, _set_note)
        _ok(
            "03_guests_set_group_note",
            notes=result.notes, groups_count=len(result.groups),
        )
    except Exception as exc:
        _fail("03_guests_set_group_note", error=_err(exc))

    # B: SELECT מוזמנים של event_a → 0 שורות. UPDATE ישיר (מדמה כתיבה
    # ללא הרשאה) → נדחה ע"י RLS (שגיאה, לא שקט).
    try:
        def _select_guests_as_b(db):
            return db.scalars(
                select(models.Guest).where(models.Guest.event_id == event_a_id)
            ).all()

        guests_seen_by_d = await as_user(uid_d, _select_guests_as_b)
        SCENARIOS["03_guests_set_group_note"]["other_user_read_denied"] = (
            len(guests_seen_by_d) == 0
        )
    except Exception as exc:
        SCENARIOS["03_guests_set_group_note"]["other_user_read_error"] = _err(exc)

    try:
        def _update_guest_as_b(db):
            g_row = db.get(models.Guest, guest1_id)
            if g_row is None:
                return "not_visible"
            g_row.full_name = "נסיון חדירה"
            db.commit()
            return "write_succeeded"

        outcome = await as_user(uid_d, _update_guest_as_b)
        SCENARIOS["03_guests_set_group_note"]["other_user_write_denied"] = (
            outcome != "write_succeeded"
        )
        SCENARIOS["03_guests_set_group_note"]["other_user_write_outcome"] = outcome
    except Exception as exc:
        # RLS דוחה UPDATE עם שגיאה אמיתית — זו בדיוק ההתנהגות הרצויה.
        SCENARIOS["03_guests_set_group_note"]["other_user_write_denied"] = True
        SCENARIOS["03_guests_set_group_note"]["other_user_write_outcome"] = _err(exc)

    # =========================================================================
    # 4) constraints / analyze — commit() ואז SELECT (ספירת הבהרות ממתינות)
    # =========================================================================
    clar_id = None
    try:
        def _analyze(db):
            ev = db.get(models.Event, event_a_id)
            return constraints_router.analyze(db=db, event=ev)

        result = await as_user(uid_a, _analyze)
        g = gt()
        try:
            clar = g.scalars(
                select(models.Clarification)
                .where(models.Clarification.event_id == event_a_id)
                .where(models.Clarification.status == "pending")
            ).first()
            clar_id = clar.id if clar is not None else None
        finally:
            g.close()
        _ok(
            "04_constraints_analyze",
            pending_clarifications_reported=result.pending_clarifications,
            pending_clarifications_ground_truth=1 if clar_id else 0,
            ambiguity_detected=clar_id is not None,
        )
    except Exception as exc:
        _fail("04_constraints_analyze", error=_err(exc))

    # =========================================================================
    # 5) constraints / resolve_clarification — commit() ואז SELECT
    # =========================================================================
    if clar_id is not None:
        try:
            def _resolve(db):
                ev = db.get(models.Event, event_a_id)
                payload = _ResolveClarificationPayload(chosen_guest_id=None)  # "אף אחד מהם"
                return constraints_router.resolve_clarification(
                    clar_id=clar_id, payload=payload, db=db, event=ev,
                )

            result = await as_user(uid_a, _resolve)
            g = gt()
            try:
                still_pending = g.scalar(
                    select(func.count()).select_from(models.Clarification)
                    .where(models.Clarification.event_id == event_a_id)
                    .where(models.Clarification.status == "pending")
                )
            finally:
                g.close()
            _ok(
                "05_constraints_resolve_clarification",
                pending_after_reported=result.pending_clarifications,
                pending_after_ground_truth=still_pending,
            )
        except Exception as exc:
            _fail("05_constraints_resolve_clarification", error=_err(exc))
    else:
        _fail("05_constraints_resolve_clarification", error="skipped: תרחיש 4 לא יצר הבהרה עמומה")

    # =========================================================================
    # 6) automation / advance_track — commit() (רק כשיש actions) ואז
    #    _track_status (SELECT). ה"עמימות" של due-messages תלויה בלוח זמנים
    #    מורכב (event_cycle/timezone) — כדי לבודד בדיוק את מנגנון הזהות
    #    (ולא את לוגיקת ה"מתי הודעה נחשבת רלוונטית"), מדמים actions אמיתי
    #    ע"י monkeypatch חד-פעמי ל-compute_due_messages, שמחזיר פעולה אחת
    #    אמיתית (EventMessage+Guest קיימים) — send_due_messages/commit/
    #    _track_status רצים אחר כך במלואם, ללא שינוי.
    # =========================================================================
    try:
        g = gt()
        try:
            ev_row = g.get(models.Event, event_a_id)
            ev_row.rsvp_track_active = True
            em = g.scalars(
                select(models.EventMessage)
                .where(models.EventMessage.event_id == event_a_id)
                .where(models.EventMessage.message_type == "reminder_1")
            ).first()
            g.commit()
            em_id = em.id
        finally:
            g.close()

        _orig_compute = communication.compute_due_messages

        def _fake_compute(db, event, **kwargs):
            em_row = db.get(models.EventMessage, em_id)
            guest_row = db.get(models.Guest, guest1_id)
            return [communication.DueMessageAction(
                event_message=em_row, guest=guest_row, preview="תזכורת בדיקה",
            )]

        communication.compute_due_messages = _fake_compute
        try:
            def _advance(db):
                ev = db.get(models.Event, event_a_id)
                user_obj = db.get(models.User, uid_a)
                return automation_router.advance_track(
                    request=_FakeRequest(), db=db, event=ev, user=user_obj,
                )

            result = await as_user(uid_a, _advance)
            _ok(
                "06_automation_advance_track",
                sent=result.sent, failed=result.failed,
                confirmed=result.confirmed, pending=result.pending,
            )
        finally:
            communication.compute_due_messages = _orig_compute
    except Exception as exc:
        _fail("06_automation_advance_track", error=_err(exc))

    # =========================================================================
    # 7) admin / create_account — שני commits, audit.record ביניהם
    # =========================================================================
    try:
        def _create_account(db):
            admin_obj = db.get(models.User, uid_admin)
            payload = schemas.AdminAccountCreate(
                email=f"rls-planner-{pid}@veya.test", display_name="מפיק שנוצר ע\"י אדמין",
                account_type="planner",
            )
            return admin_router.create_account(payload=payload, request=_FakeRequest(),
                                                db=db, admin=admin_obj)

        result = await as_user(uid_admin, _create_account)
        g = gt()
        try:
            audit_row = g.scalars(
                select(models.AuditLog)
                .where(models.AuditLog.action == "admin_create_account")
                .where(models.AuditLog.user_id == uid_admin)
            ).first()
        finally:
            g.close()
        _ok(
            "07_admin_create_account",
            new_user_id=result.user_id,
            audit_log_written=audit_row is not None,
        )
    except Exception as exc:
        _fail("07_admin_create_account", error=_err(exc))

    # =========================================================================
    # 8) admin / update_user — commit() ואז SELECT (ספירות events/guests)
    # =========================================================================
    try:
        def _update_user(db):
            admin_obj = db.get(models.User, uid_admin)
            payload = schemas.AdminUserUpdate(display_name="זוג בדיקה א (עודכן)")
            return admin_router.update_user(
                user_id=uid_a, payload=payload, request=_FakeRequest(),
                db=db, admin=admin_obj,
            )

        result = await as_user(uid_admin, _update_user)
        g = gt()
        try:
            real_events_count = g.scalar(
                select(func.count()).select_from(models.Event).where(models.Event.owner_id == uid_a)
            )
            real_guests_count = g.scalar(
                select(func.count()).select_from(models.Guest)
                .join(models.Event, models.Guest.event_id == models.Event.id)
                .where(models.Event.owner_id == uid_a)
            )
        finally:
            g.close()
        _ok(
            "08_admin_update_user",
            display_name=result.display_name,
            events_count_reported=result.events_count,
            events_count_ground_truth=real_events_count,
            guests_count_reported=result.guests_count,
            guests_count_ground_truth=real_guests_count,
        )
    except Exception as exc:
        _fail("08_admin_update_user", error=_err(exc))

    # =========================================================================
    # 9) admin / set_caller_assignments — commit() ואז SELECT+queues
    # =========================================================================
    try:
        g = gt()
        try:
            caller = models.User(
                email=f"rls-caller-{pid}@veya.test", password_hash=auth.hash_password("Test12345!"),
                display_name="טלפן בדיקה", phone="0508887777",
                email_verified_at=datetime.utcnow(), token_version=1, account_type="phone_agent",
            )
            g.add(caller)
            g.commit()
            caller_id = caller.id
        finally:
            g.close()

        def _set_assignments(db):
            admin_obj = db.get(models.User, uid_admin)
            payload = schemas.AdminCallerAssignmentUpdate(event_ids=[event_a_id])
            return admin_router.set_caller_assignments(
                user_id=caller_id, payload=payload, request=_FakeRequest(),
                db=db, admin=admin_obj,
            )

        result = await as_user(uid_admin, _set_assignments)
        g = gt()
        try:
            real_assignment = g.scalars(
                select(models.CallAssignment)
                .where(models.CallAssignment.user_id == caller_id)
                .where(models.CallAssignment.event_id == event_a_id)
            ).first()
        finally:
            g.close()
        _ok(
            "09_admin_set_caller_assignments",
            assigned_event_ids=result.assigned_event_ids,
            assignment_persisted=real_assignment is not None,
        )
    except Exception as exc:
        _fail("09_admin_set_caller_assignments", error=_err(exc))

    # =========================================================================
    # רגרסיה: Auth (register/login תחת RLS אמיתי)
    # =========================================================================
    try:
        db = sess()
        try:
            def _register(db):
                return auth.register_user_row(
                    db, email=f"rls-reg-{pid}@veya.test",
                    password_hash=auth.hash_password("Test12345!"),
                    display_name="נרשם בדיקה", phone="0501231234",
                    is_admin=False, account_type="couple",
                )

            new_user = await run_in_threadpool(lambda: _register(db))
            await run_in_threadpool(lambda: database.set_request_identity(new_user.id, db))
            await run_in_threadpool(db.commit)
        finally:
            db.close()
            database.clear_request_identity()

        db2 = sess()
        try:
            fetched = await run_in_threadpool(lambda: auth.find_user_by_email(db2, f"rls-reg-{pid}@veya.test"))
        finally:
            db2.close()
        _ok("reg_auth", registered_and_findable=fetched is not None)
    except Exception as exc:
        _fail("reg_auth", error=_err(exc))

    # =========================================================================
    # רגרסיה: RSVP/confirm — guest_token שורד commit + בידוד בין מוזמנים
    # =========================================================================
    try:
        db3 = sess()
        try:
            def _set_token(db):
                database.set_guest_token(f"rls-tok-{guest_asks_id}", db)
                # שומרים על guest.guest_token אמיתי דרך superuser (ORM guest_token
                # מיוצר אוטומטית; דורסים לערך ידוע לבדיקה).
            g = gt()
            try:
                gu = g.get(models.Guest, guest_asks_id)
                gu.guest_token = f"rls-tok-{guest_asks_id}"
                g.commit()
            finally:
                g.close()

            await run_in_threadpool(lambda: (
                database.set_guest_token(f"rls-tok-{guest_asks_id}", db3),
                db3.execute(text("SELECT 1")),
            ))

            def _after_commit(db):
                db.commit()
                return db.scalars(
                    select(models.Guest).where(models.Guest.guest_token == f"rls-tok-{guest_asks_id}")
                ).first()

            row = await run_in_threadpool(lambda: _after_commit(db3))
            survives = row is not None
        finally:
            db3.close()

        db4 = sess()
        try:
            def _other_guest_denied(db):
                # session חדש, בלי אף guest_token — לא אמור לראות שום מוזמן.
                return db.scalars(select(models.Guest).where(models.Guest.id == guest1_id)).first()

            other = await run_in_threadpool(lambda: _other_guest_denied(db4))
        finally:
            db4.close()

        _ok(
            "reg_rsvp_confirm",
            guest_token_survives_commit=survives,
            other_guest_denied_without_token=other is None,
        )
    except Exception as exc:
        _fail("reg_rsvp_confirm", error=_err(exc))

    # =========================================================================
    # רגרסיה: Partners — חבר-אירוע (partner=גישה מלאה, planner=הרשאה חלקית)
    # =========================================================================
    try:
        g = gt()
        try:
            member_partner = models.EventMember(
                event_id=event_a_id, user_id=uid_b, role="partner",
                permissions=[], status="active",
            )
            member_planner = models.EventMember(
                event_id=event_a_id, user_id=uid_c, role="planner",
                permissions=["view_guests"], status="active",
            )
            g.add_all([member_partner, member_planner])
            g.commit()
        finally:
            g.close()

        # B (partner) — גישה מלאה כמו הבעלים: יכול לקרוא ולכתוב.
        def _partner_read(db):
            return db.scalars(
                select(models.Guest).where(models.Guest.event_id == event_a_id)
            ).all()

        b_guests = await as_user(uid_b, _partner_read)

        def _partner_write(db):
            ev = db.get(models.Event, event_a_id)
            ev.venue_name = "עודכן ע\"י בן/בת הזוג"
            db.commit()
            return True

        b_write_ok = await as_user(uid_b, _partner_write)

        # C (planner, view_guests בלבד) — קורא מוזמנים, אבל לא כותב.
        c_guests = await as_user(uid_c, _partner_read)

        def _planner_write_attempt(db):
            g_row = db.get(models.Guest, guest1_id)
            g_row.full_name = "נסיון כתיבה ע\"י מפיק"
            db.commit()
            return "write_succeeded"

        try:
            c_write_outcome = await as_user(uid_c, _planner_write_attempt)
        except Exception as exc:
            c_write_outcome = _err(exc)

        _ok(
            "reg_partners",
            partner_full_access_read=len(b_guests) == 5,
            partner_full_access_write=bool(b_write_ok),
            planner_limited_read=len(c_guests) == 5,
            planner_write_denied=(c_write_outcome != "write_succeeded"),
            planner_write_outcome=c_write_outcome,
        )
    except Exception as exc:
        _fail("reg_partners", error=_err(exc))

    # =========================================================================
    # רגרסיה: Seating — generate (commit() אחרון, persist) + בידוד B
    # =========================================================================
    try:
        g = gt()
        try:
            for gid in (guest1_id, guest2_id):
                gu = g.get(models.Guest, gid)
                gu.rsvp_status = "confirmed"
                gu.confirmed_count = 1
            g.commit()
        finally:
            g.close()

        def _generate(db):
            ev = db.get(models.Event, event_a_id)
            payload = schemas.SeatingRequest(seats_per_table=12, persist=True)
            return seating_router.generate(payload=payload, db=db, event=ev)

        result = await as_user(uid_a, _generate)

        g = gt()
        try:
            seated = g.scalar(
                select(func.count()).select_from(models.Guest)
                .where(models.Guest.event_id == event_a_id)
                .where(models.Guest.table_number.is_not(None))
            )
        finally:
            g.close()

        def _b_reads_hall(db):
            return db.scalars(
                select(models.Guest)
                .where(models.Guest.event_id == event_a_id)
                .where(models.Guest.table_number.is_not(None))
            ).all()

        d_seated_view = await as_user(uid_d, _b_reads_hall)

        _ok(
            "reg_seating",
            persisted=result.persisted,
            seated_ground_truth=seated,
            other_user_sees_seating=len(d_seated_view) > 0,  # אמור להיות False
        )
    except Exception as exc:
        _fail("reg_seating", error=_err(exc))

    # =========================================================================
    # רגרסיה: Postponement — open_request תחת RLS אמיתי (לא נוגעים בקוד עצמו)
    # =========================================================================
    try:
        def _open_request(db):
            ev = db.get(models.Event, event_a_id)
            user_obj = db.get(models.User, uid_a)
            return postpone_router.open_request(request=_FakeRequest(), db=db, event=ev, user=user_obj)

        result = await as_user(uid_a, _open_request)
        g = gt()
        try:
            req_row = g.scalars(
                select(models.PostponementRequest).where(models.PostponementRequest.event_id == event_a_id)
            ).first()
        finally:
            g.close()
        _ok("reg_postponement", request_created=req_row is not None, status=getattr(req_row, "status", None))
    except Exception as exc:
        # לא נוגעים בקוד/RLS של נוהל הדחייה — כל תוצאה (כולל דחייה עסקית
        # תקינה) מתועדת, לא מטופלת.
        _fail("reg_postponement", error=_err(exc))

    # =========================================================================
    # רגרסיה: Gifts/payout — בדיקת בידוד RLS בלבד (לא נוגעים בלוגיקה העסקית)
    # =========================================================================
    try:
        g = gt()
        try:
            gift_row = models.Gift(
                event_id=event_a_id, guest_id=guest1_id,
                gift_amount_agorot=10000, fee_agorot=400, total_agorot=10400,
                sender_name="בודק", status="paid",
                provider_transaction_id=f"rls-test-{pid}",
                idempotency_key=f"rls-idem-{pid}",
            )
            payout_row = models.PayoutAccount(
                event_id=event_a_id, bank_code=12, branch_number="123",
                account_number="456",
            )
            g.add_all([gift_row, payout_row])
            g.commit()
        finally:
            g.close()

        def _a_reads(db):
            gifts = db.scalars(select(models.Gift).where(models.Gift.event_id == event_a_id)).all()
            payout = db.scalars(
                select(models.PayoutAccount).where(models.PayoutAccount.event_id == event_a_id)
            ).first()
            return len(gifts), payout is not None

        a_gifts_count, a_payout_visible = await as_user(uid_a, _a_reads)

        def _b_reads(db):
            gifts = db.scalars(select(models.Gift).where(models.Gift.event_id == event_a_id)).all()
            payout = db.scalars(
                select(models.PayoutAccount).where(models.PayoutAccount.event_id == event_a_id)
            ).first()
            return len(gifts), payout is not None

        d_gifts_count, d_payout_visible = await as_user(uid_d, _b_reads)

        _ok(
            "reg_gifts_payout",
            owner_sees_gift=a_gifts_count > 0,
            owner_sees_payout_account=a_payout_visible,
            other_user_gift_denied=d_gifts_count == 0,
            other_user_payout_denied=(not d_payout_visible),
        )
    except Exception as exc:
        _fail("reg_gifts_payout", error=_err(exc))

    # =========================================================================
    # רגרסיה: Guest management — CRUD + מטריצת הרשאות מלאה (קריאה/עדכון/מחיקה)
    # =========================================================================
    try:
        def _create_guest(db):
            ev = db.get(models.Event, event_a_id)
            payload = schemas.GuestCreate(full_name="מוזמן חדש", phone="0509990000")
            return guests_router.create_guest(payload=payload, db=db, event=ev)

        new_guest = await as_user(uid_a, _create_guest)

        # B: לא רואה, לא יכול לעדכן, לא יכול למחוק.
        def _b_read_guest(db):
            return db.get(models.Guest, new_guest.id)

        d_sees = await as_user(uid_d, _b_read_guest)

        def _b_update_guest(db):
            row = db.get(models.Guest, new_guest.id)
            if row is None:
                return "not_visible"
            row.full_name = "השתלטות B"
            db.commit()
            return "write_succeeded"

        try:
            d_update_outcome = await as_user(uid_d, _b_update_guest)
        except Exception as exc:
            b_update_outcome = _err(exc)

        def _b_delete_guest(db):
            row = db.get(models.Guest, new_guest.id)
            if row is None:
                return "not_visible"
            db.delete(row)
            db.commit()
            return "delete_succeeded"

        try:
            d_delete_outcome = await as_user(uid_d, _b_delete_guest)
        except Exception as exc:
            b_delete_outcome = _err(exc)

        g = gt()
        try:
            still_exists = g.get(models.Guest, new_guest.id) is not None
        finally:
            g.close()

        _ok(
            "reg_guest_management",
            created_id=new_guest.id,
            other_user_read_denied=(d_sees is None),
            other_user_update_denied=(d_update_outcome != "write_succeeded"),
            other_user_delete_denied=(d_delete_outcome != "delete_succeeded"),
            guest_still_exists_after_attacks=still_exists,
        )
    except Exception as exc:
        _fail("reg_guest_management", error=_err(exc))

    print(json.dumps(SCENARIOS, ensure_ascii=False))


# ── עזרי payload קלים (מונע תלות ב-pydantic import סדר-גדול בראש הקובץ) ─────
def _GroupNotePayload(**kw):
    from app.routers.guests import GroupNoteUpdate
    return GroupNoteUpdate(**kw)


def _ResolveClarificationPayload(**kw):
    from app import schemas
    return schemas.ResolveClarification(**kw)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.legacy))
