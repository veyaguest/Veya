"""Worker שרץ בתהליך נפרד, עם ``DATABASE_URL``/``MIGRATIONS_DATABASE_URL``
מוצבעים ל-Postgres זמני (ראו ``test_create_event_identity_regression.py``),
ומדמה בדיוק את הרצף שה-FastAPI האמיתי מריץ: dependency אחד (``get_current_user``)
ואז גוף ה-endpoint (``create_event``) — **כל אחד בקריאת ``run_in_threadpool``
נפרדת משלו**, בדיוק כמו ש-FastAPI עושה בפועל (ראו ``starlette.concurrency
.run_in_threadpool`` → ``anyio.to_thread.run_sync``, וההסבר המלא ב-
``app/database.py::set_request_identity``).

למה תהליך נפרד ולא חלק מ-pytest הרגיל: ``app.database`` קובע את ה-engine
לפי ``DATABASE_URL`` **בזמן הייבוא** — ברגע שקובץ בדיקה אחר בסוויטה כבר ייבא
את ``app.database`` (רובם עושים זאת, מול SQLite), אי אפשר "להחליף" DB
בתוך אותו תהליך. תהליך פייתון נפרד = ייבוא נקי, מקובע ל-Postgres הזמני.

דגל ``--legacy``: מחליף את ``_apply_rls_identity`` (ה-listener על
``after_begin``) חזרה למנגנון **הישן** — קריאה מ-ContextVar בלבד, בלי
``session.info`` — כדי להוכיח בפועל שהתרחיש נכשל עם המנגנון הישן ועובר עם
החדש, על אותו קוד אמיתי (``app.auth``, ``app.routers.events``,
``app.communication``) בשני המקרים.

מדפיס JSON יחיד ל-stdout עם תוצאות כל התרחישים.
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

RESULTS: dict = {}


def _err(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


RLS_SQL_FILES = [
    "01_helpers_and_grants.sql", "02_policies.sql", "04_consent_records_rls_fix.sql",
    "05_event_messages_rls.sql", "06_call_logs_rls.sql", "07_phone_agent_rls.sql",
    "08_partner_comanagement.sql", "09_email_verification_rls_fix.sql",
    "11_event_messages_delete_rls_fix.sql", "12_password_reset.sql",
    "13_gifts_rls.sql", "14_payout_accounts_rls.sql", "15_postponement_rls.sql",
]  # הכול חוץ מ-03_rollback.sql (זה rollback, לא חלק מהקמה) — אותו סדר בדיוק
   # כמו שמתועד ב-backend/rls/PRODUCTION_ROLLOUT.md.


async def main(legacy: bool) -> None:
    import psycopg2
    import jwt
    from fastapi.security import HTTPAuthorizationCredentials
    from sqlalchemy import event as sa_event, select, text
    from starlette.concurrency import run_in_threadpool

    from app import auth, database, models, partners, schemas
    from app.routers import events as events_router

    # ── הקמת סכימה + כל קובצי ה-RLS, דרך MIGRATIONS_DATABASE_URL (superuser) ──
    # אותו בדיוק split בין DATABASE_URL (veya_app) ל-MIGRATIONS_DATABASE_URL
    # (superuser) שכבר קיים בקוד הייצור (ראו database.py) — ה-DDL כאן חייב
    # superuser (בעל הטבלאות), בדיוק כמו שהיה קורה בפריסה אמיתית.
    database.Base.metadata.create_all(bind=database.migrations_engine)

    # תיקון פער ידוע ולא-קשור לזהות/RLS (מתועד גם ב-tests/test_postponement_rls_postgres.py):
    # ``create_all()`` על סכימה טרייה יוצר עמודות NOT NULL בלי DEFAULT ברמת
    # ה-DB (``default=""`` ב-SQLAlchemy הוא ערך צד-פייתון בלבד, מוחל רק
    # ב-INSERT דרך ה-ORM). ב-DB ייצור אמיתי יש להן DEFAULT אמיתי (הצטבר
    # דרך ALTER TABLE ADD COLUMN ... DEFAULT בכל מיגרציה היסטורית). פונקציות
    # ה-SECURITY DEFINER (כמו app_create_event/app_register_user) עושות
    # INSERT עם רשימת עמודות חלקית ומסתמכות בדיוק על ה-DEFAULT הזה. משלימים
    # אותו כאן כדי שהסכימה הזמנית תתנהג כמו ייצור אמיתי.
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
        # מנגנון "ישן": ContextVar בלבד, מתעלם לגמרי מ-session.info. זהה
        # ל-_apply_rls_identity לפני התיקון (ראו database.py::set_request_identity
        # להסבר המלא של למה זה שובר commit-והמשך).
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

    RESULTS["mechanism"] = "legacy_contextvar_only" if legacy else "fixed_session_info"

    # ── הכנת נתוני בדיקה (superuser — עוקף RLS בכוונה, זה ה-harness) ─────────
    admin_session = database.MigrationSessionLocal()
    try:
        user_a = models.User(
            email=f"rls-a-{os.getpid()}@veya.test",
            password_hash=auth.hash_password("Test12345!"),
            display_name="זוג בדיקה א",
            phone="0501234567",
            email_verified_at=datetime.utcnow(),
            token_version=1,
        )
        user_b = models.User(
            email=f"rls-b-{os.getpid()}@veya.test",
            password_hash=auth.hash_password("Test12345!"),
            display_name="זוג בדיקה ב",
            phone="0507654321",
            email_verified_at=datetime.utcnow(),
            token_version=1,
        )
        admin_session.add_all([user_a, user_b])
        admin_session.commit()
        user_a_id, user_b_id = user_a.id, user_b.id
    finally:
        admin_session.close()

    def _token_for(user_id: int) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id), "tv": 1, "iat": now,
            "exp": now + timedelta(days=1),
        }
        return jwt.encode(payload, auth.JWT_SECRET, algorithm=auth.JWT_ALGORITHM)

    # ── תרחיש 1: הזהות שורדת commit() ותחילת טרנזקציה חדשה ───────────────────
    # התרחיש הכי מינימלי מכל הבקשה: זיהוי → commit → טרנזקציה חדשה → הזהות
    # עדיין קיימת. שתי הפאזות רצות ב-run_in_threadpool נפרדות, בדיוק כמו
    # dependency נפרד וגוף endpoint נפרד ב-FastAPI אמיתי.
    db1 = database.SessionLocal()
    try:
        def _phase1_identify():
            database.set_request_identity(user_a_id, db1)
            db1.execute(text("SELECT 1"))  # פותח טרנזקציה #1 — מוזרקת נכון

        await run_in_threadpool(_phase1_identify)

        def _phase2_after_commit():
            db1.commit()  # סוגר טרנזקציה #1
            return db1.execute(text("SELECT app_current_user_id()")).scalar()

        uid_after_commit = await run_in_threadpool(_phase2_after_commit)
        RESULTS["identity_survives_commit"] = {
            "ok": uid_after_commit == user_a_id,
            "expected": user_a_id,
            "got": uid_after_commit,
        }
    except Exception as exc:
        RESULTS["identity_survives_commit"] = {"ok": False, "error": _err(exc)}
    finally:
        db1.close()
        database.clear_request_identity()

    # ── תרחיש 2: רגרסיית create_event המדויקת ────────────────────────────────
    # פעולה ראשונה (app_create_event) → commit → provision_event_messages
    # (INSERT רגיל דרך ה-ORM, לא SECURITY DEFINER) → אמור להיכשל עם המנגנון
    # הישן ולעבוד עם החדש. שני dependency-calls נפרדים (get_current_user,
    # ואז גוף create_event) — בדיוק כמו FastAPI אמיתי.
    db2 = database.SessionLocal()
    event_a_id = None
    try:
        token_a = _token_for(user_a_id)

        def _phase_get_current_user():
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token_a)
            return auth.get_current_user(creds=creds, db=db2)

        user_obj = await run_in_threadpool(_phase_get_current_user)

        def _phase_create_event():
            payload = schemas.EventCreate(
                event_type="wedding", groom_name="איתי", bride_name="דנה",
                venue_name="אולם הבדיקה",
            )
            return events_router.create_event(payload=payload, db=db2, user=user_obj)

        summary = await run_in_threadpool(_phase_create_event)
        RESULTS["create_event_api"] = {"ok": True, "event_id": summary.id}
        event_a_id = summary.id
    except Exception as exc:
        RESULTS["create_event_api"] = {"ok": False, "error": _err(exc)}
    finally:
        db2.close()
        database.clear_request_identity()

    # אם ה-API נכשל אחרי שה-event עצמו כבר נוצר (הטרנזקציה הראשונה הצליחה,
    # רק ה-provisioning שנכשל) — עדיין נצטרך את המזהה כדי לבדוק ground-truth.
    if event_a_id is None:
        verify_session = database.MigrationSessionLocal()
        try:
            row = verify_session.scalars(
                select(models.Event).where(models.Event.owner_id == user_a_id)
            ).first()
            event_a_id = row.id if row is not None else None
        finally:
            verify_session.close()

    # ground truth: כמה שורות event_messages נוצרו בפועל — נבדק דרך superuser,
    # בלי תלות ב-RLS, כדי לדעת מה *באמת* קרה ב-DB (לא רק מה ה-API החזיר).
    verify_session = database.MigrationSessionLocal()
    try:
        if event_a_id is not None:
            from sqlalchemy import func
            count = verify_session.scalar(
                select(func.count()).select_from(models.EventMessage)
                .where(models.EventMessage.event_id == event_a_id)
            )
        else:
            count = 0
        RESULTS["create_event_ground_truth"] = {
            "event_row_exists": event_a_id is not None,
            "event_messages_count": count,
        }
    finally:
        verify_session.close()

    # ── תרחיש 3: SELECT מחזיר רק את הנתונים של המשתמש הנכון ──────────────────
    if event_a_id is not None:
        db3 = database.SessionLocal()
        try:
            def _select_as_a():
                database.set_request_identity(user_a_id, db3)
                return db3.scalars(
                    select(models.Event).where(models.Event.id == event_a_id)
                ).first()

            seen_by_a = await run_in_threadpool(_select_as_a)
            RESULTS["select_owner_sees_own_event"] = {"ok": seen_by_a is not None}
        except Exception as exc:
            RESULTS["select_owner_sees_own_event"] = {"ok": False, "error": _err(exc)}
        finally:
            db3.close()
            database.clear_request_identity()

        db4 = database.SessionLocal()
        try:
            def _select_as_b():
                database.set_request_identity(user_b_id, db4)
                return db4.scalars(
                    select(models.Event).where(models.Event.id == event_a_id)
                ).first()

            seen_by_b = await run_in_threadpool(_select_as_b)
            RESULTS["select_other_user_denied"] = {"ok": seen_by_b is None}
        except Exception as exc:
            RESULTS["select_other_user_denied"] = {"ok": False, "error": _err(exc)}
        finally:
            db4.close()
            database.clear_request_identity()

        # ── תרחיש 4: UPDATE מצליח כשלמשתמש יש הרשאה (הבעלים על האירוע שלו) ──
        db5 = database.SessionLocal()
        try:
            def _update_as_owner():
                database.set_request_identity(user_a_id, db5)
                ev = db5.get(models.Event, event_a_id)
                ev.venue_name = "אולם עודכן"
                db5.commit()

            await run_in_threadpool(_update_as_owner)
            verify_session = database.MigrationSessionLocal()
            try:
                updated = verify_session.get(models.Event, event_a_id)
                RESULTS["update_with_permission_succeeds"] = {
                    "ok": updated.venue_name == "אולם עודכן",
                }
            finally:
                verify_session.close()
        except Exception as exc:
            RESULTS["update_with_permission_succeeds"] = {"ok": False, "error": _err(exc)}
        finally:
            db5.close()
            database.clear_request_identity()

    # ── תרחיש 5: guest_token שורד commit() (RSVP) ────────────────────────────
    if event_a_id is not None:
        admin_session = database.MigrationSessionLocal()
        try:
            guest = models.Guest(
                event_id=event_a_id, full_name="מוזמן בדיקה", phone="0509999999",
                guest_token=f"rls-guest-token-{os.getpid()}",
            )
            admin_session.add(guest)
            admin_session.commit()
            guest_token_value = guest.guest_token
        finally:
            admin_session.close()

        db6 = database.SessionLocal()
        try:
            def _phase_set_guest_token():
                database.set_guest_token(guest_token_value, db6)
                db6.execute(text("SELECT 1"))  # פותח טרנזקציה #1 עם זהות-אורח נכונה

            await run_in_threadpool(_phase_set_guest_token)

            def _phase_after_commit_guest():
                db6.commit()  # סוגר טרנזקציה #1 — בדיוק כמו submit_confirm שממשיך אחרי כתיבה
                return db6.scalars(
                    select(models.Guest).where(models.Guest.guest_token == guest_token_value)
                ).first()

            row = await run_in_threadpool(_phase_after_commit_guest)
            RESULTS["guest_token_survives_commit"] = {"ok": row is not None}
        except Exception as exc:
            RESULTS["guest_token_survives_commit"] = {"ok": False, "error": _err(exc)}
        finally:
            db6.close()

        # בידוד: session חדש, בלי guest_token בכלל — לא אמור לראות את המוזמן.
        db7 = database.SessionLocal()
        try:
            def _select_without_token():
                return db7.scalars(
                    select(models.Guest).where(models.Guest.guest_token == guest_token_value)
                ).first()

            row2 = await run_in_threadpool(_select_without_token)
            RESULTS["guest_without_token_denied"] = {"ok": row2 is None}
        except Exception as exc:
            RESULTS["guest_without_token_denied"] = {"ok": False, "error": _err(exc)}
        finally:
            db7.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.legacy))
    print(json.dumps(RESULTS, ensure_ascii=False))
