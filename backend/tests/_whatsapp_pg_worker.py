"""בדיקות WhatsApp מול Postgres + RLS אמיתי (לא Production) — תהליך-בת.

מה שלא ניתן להוכיח מול SQLite (שם אין RLS, אין נעילות שורה ואין נעילות
advisory):
1. ``outbound.lock_event_sends`` — שליחה שנייה לאותו אירוע מחכה; אירוע אחר לא.
2. שתי שליחות הזמנות **במקביל** לאותו אירוע (``activate_track`` תחת זהות
   משתמש ו-RLS) — כל מוזמן מקבל הזמנה אחת בלבד.
3. ``outbound.send_batch`` מול ספק "אמיתי" (commit אחרי כל הודעה) בתוך בקשה
   תחת RLS — הזהות שורדת את ה-commit-ים באמצע.
4. "נכשלה" לא דורסת "נמסרה"/"נקראה" — ב-Postgres (שם הבאג היה, בפונקציית SQL).
5. ``FOR UPDATE`` — "נמסרה" ו"נקראה" במקביל לאותה הודעה: התוצאה "נקראה".
6. ה-webhook (עיבוד הפריטים, על חיבור המערכת): תשובה מוחלת, כפילות נקלטת
   פעם אחת — גם כששתי קריאות זהות מגיעות **במקביל**.
7. מצב ``meta_test`` תחת RLS — רק הנמען המורשה נשלח ונרשם.
8. Meta (מזויפת) תחת RLS: Template נשלח, timeout נשאר "לא ידוע", ועדכון
   webhook עם המזהה הפנימי סוגר אותו.

אותה שיטה כמו ``_rls_full_regression_worker.py``: DATABASE_URL = תפקיד
``veya_app`` (כפוף ל-RLS), MIGRATIONS_DATABASE_URL = superuser. מדפיס JSON
יחיד בשורה האחרונה: ``{name: {"ok": bool, ...}}``.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._rls_full_regression_worker import RLS_SQL_FILES, _FakeRequest  # noqa: E402

RESULTS: dict = {}

# מזהה המספר שאירועי ה-webhook כאן שייכים אליו (``WHATSAPP_WEBHOOK_PHONE_NUMBER_ID``).
_PNID = "100000000000003"
os.environ["WHATSAPP_WEBHOOK_PHONE_NUMBER_ID"] = _PNID


def _ok(name: str, **kw) -> None:
    RESULTS[name] = {"ok": True, **kw}


def _fail(name: str, **kw) -> None:
    RESULTS[name] = {"ok": False, **kw}


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


async def main() -> None:
    import psycopg2
    from sqlalchemy import func, select, text
    from starlette.concurrency import run_in_threadpool

    from app import (
        auth, database, guest_journey, message_status, messaging, models, outbound,
        schemas,
    )
    from app.main import _ensure_unique_indexes
    from app.routers import automation as automation_router
    from app.routers import messaging as messaging_router

    # ── סכימה + RLS (כמו ה-worker הקיים) + האינדקס הייחודי על מזהה הספק ──
    database.Base.metadata.create_all(bind=database.migrations_engine)
    rls_dir = Path(__file__).resolve().parent.parent / "rls"
    admin_conn = psycopg2.connect(os.environ["MIGRATIONS_DATABASE_URL"])
    admin_conn.autocommit = True
    cur = admin_conn.cursor()
    for fname in RLS_SQL_FILES:
        cur.execute((rls_dir / fname).read_text())
    admin_conn.close()
    _ensure_unique_indexes()

    def gt():
        return database.MigrationSessionLocal()

    # ── נתוני בסיס: משתמש, שני אירועים (אחד עם חלון אישורים פתוח), מוזמנים ──
    today = guest_journey.today_in_israel()
    ev_date = today + timedelta(days=30)
    commit_days = (ev_date - (today - timedelta(days=21))).days
    g = gt()
    try:
        user = models.User(
            email=f"wa-pg-{os.getpid()}@veya.test", password_hash=auth.hash_password("Test12345!"),
            display_name="זוג בדיקה", phone="0501234567",
            email_verified_at=datetime.utcnow(), token_version=1,
        )
        g.add(user)
        g.flush()
        ev = models.Event(
            owner_id=user.id, event_type="wedding", groom_name="יואב", bride_name="דנה",
            event_date=ev_date.isoformat(), rsvp_track_active=True,
            rsvp_track_started_at=datetime.utcnow() - timedelta(days=40),
            venue_commit_days_before=max(commit_days, 1),
        )
        ev2 = models.Event(owner_id=user.id, event_type="wedding", groom_name="א", bride_name="ב")
        g.add_all([ev, ev2])
        g.flush()
        g.add(models.EventMessage(event_id=ev.id, message_type="invitation", title="הזמנה",
                                  content="שלום {{guest_name}}", is_active=True))
        guests = [
            models.Guest(event_id=ev.id, full_name=f"מוזמן {i}", phone=f"05290000{i:02d}",
                         party_size=2)
            for i in range(6)
        ]
        g.add_all(guests)
        g.commit()
        uid, ev_id, ev2_id = user.id, ev.id, ev2.id
        guest_ids = [x.id for x in guests]
    finally:
        g.close()

    async def as_user(fn):
        """זהות בקריאה אחת וגוף ה-endpoint בקריאה אחרת — כמו FastAPI בפועל."""
        db = database.SessionLocal()
        try:
            def _identify():
                database.set_request_identity(uid, db)
                db.execute(text("SELECT 1"))

            await run_in_threadpool(_identify)
            return await run_in_threadpool(lambda: fn(db))
        finally:
            db.close()
            database.clear_request_identity()

    # =====================================================================
    # 1) נעילה לפי אירוע
    # =====================================================================
    try:
        holder = gt()
        outbound.lock_event_sends(holder, ev_id)  # מחזיק, בלי commit
        timings: dict = {}

        def _waiter(event_id, key):
            s = gt()
            try:
                t0 = time.monotonic()
                outbound.lock_event_sends(s, event_id)
                timings[key] = time.monotonic() - t0
                s.commit()
            finally:
                s.close()

        same = threading.Thread(target=_waiter, args=(ev_id, "same"))
        other = threading.Thread(target=_waiter, args=(ev2_id, "other"))
        same.start()
        other.start()
        other.join(5)
        time.sleep(1.0)
        same_blocked = same.is_alive()
        holder.commit()  # משחרר
        holder.close()
        same.join(5)
        if same_blocked and timings.get("other", 9) < 0.5 and timings.get("same", 0) >= 0.9:
            _ok("01_event_lock", same_event_waited_s=round(timings["same"], 2),
                other_event_waited_s=round(timings["other"], 2))
        else:
            _fail("01_event_lock", same_blocked=same_blocked, timings=timings)
    except Exception as exc:
        _fail("01_event_lock", error=_err(exc))

    # =====================================================================
    # 2) שתי שליחות הזמנות במקביל לאותו אירוע — הזמנה אחת לכל מוזמן
    # =====================================================================
    class _SlowMock(messaging.MockProvider):
        def send_invitation(self, phone, text_):
            time.sleep(0.05)
            return super().send_invitation(phone, text_)

    orig_provider = messaging.get_provider
    messaging.get_provider = lambda: _SlowMock()
    try:
        def _activate(db):
            event = db.get(models.Event, ev_id)
            u = db.get(models.User, uid)
            return automation_router.activate_track(
                request=_FakeRequest(), payload=schemas.RsvpTrackActivateRequest(),
                db=db, event=event, user=u,
            )

        r1, r2 = await asyncio.gather(as_user(_activate), as_user(_activate))
        g = gt()
        try:
            per_guest = dict(g.execute(
                select(models.Message.guest_id, func.count())
                .where(models.Message.event_id == ev_id, models.Message.kind == "invitation")
                .group_by(models.Message.guest_id)
            ).all())
            statuses = sorted(g.scalars(
                select(models.Message.status)
                .where(models.Message.event_id == ev_id, models.Message.kind == "invitation")
            ).all())
        finally:
            g.close()
        total = r1.invitations_sent + r2.invitations_sent
        if (total == len(guest_ids) and sorted(per_guest.values()) == [1] * len(guest_ids)
                and statuses == ["sent"] * len(guest_ids)):
            _ok("02_concurrent_invitations_once", sent_by_request=[r1.invitations_sent, r2.invitations_sent])
        else:
            _fail("02_concurrent_invitations_once", total=total, per_guest=per_guest, statuses=statuses)
    except Exception as exc:
        _fail("02_concurrent_invitations_once", error=_err(exc))
    finally:
        messaging.get_provider = orig_provider

    # =====================================================================
    # 3) ספק "אמיתי" (commit אחרי כל הודעה) בתוך בקשה תחת RLS
    # =====================================================================
    class _External(messaging.MockProvider):
        name = "fake-external"
        external = True

    try:
        def _batch(db):
            event = db.get(models.Event, ev_id)
            gs = [db.get(models.Guest, gid) for gid in guest_ids[:3]]
            res = outbound.send_batch(db, event, [
                outbound.OutboundItem(guest=x, phone=x.phone, text="תזכורת", kind="reminder_1")
                for x in gs
            ], provider=_External())
            db.commit()
            # אחרי כמה commit-ים — הזהות עדיין תקפה: SELECT תחת RLS רואה את השורות.
            visible = db.scalar(
                select(func.count()).select_from(models.Message)
                .where(models.Message.event_id == ev_id, models.Message.kind == "reminder_1")
            )
            return res, visible

        res, visible = await as_user(_batch)
        if res.sent == 3 and visible == 3:
            _ok("03_external_provider_commits_under_rls", sent=res.sent, visible_after=visible)
        else:
            _fail("03_external_provider_commits_under_rls", sent=res.sent, visible=visible)
    except Exception as exc:
        _fail("03_external_provider_commits_under_rls", error=_err(exc))

    # =====================================================================
    # 4) "נכשלה" לא דורסת "נמסרה"/"נקראה"
    # =====================================================================
    def _out(status, wamid):
        s = gt()
        try:
            s.add(models.Message(event_id=ev_id, guest_id=guest_ids[0], direction="outbound",
                                 kind="invitation", body="x", status=status, provider="meta",
                                 provider_message_id=wamid))
            s.commit()
        finally:
            s.close()

    def _status_of(wamid):
        s = gt()
        try:
            return s.scalar(select(models.Message.status)
                            .where(models.Message.provider_message_id == wamid))
        finally:
            s.close()

    try:
        outcomes = {}
        for start in ("delivered", "read"):
            wamid = f"wamid-pg-{start}"
            _out(start, wamid)
            s = gt()
            try:
                message_status.apply_status_update(
                    s, provider_message_id=wamid, status=message_status.FAILED,
                    reason="late", failure_code=131026)
                s.commit()
            finally:
                s.close()
            outcomes[start] = _status_of(wamid)
        if outcomes == {"delivered": "delivered", "read": "read"}:
            _ok("04_failed_does_not_override", outcomes=outcomes)
        else:
            _fail("04_failed_does_not_override", outcomes=outcomes)
    except Exception as exc:
        _fail("04_failed_does_not_override", error=_err(exc))

    # =====================================================================
    # 5) FOR UPDATE — "נקראה" ו"נמסרה" במקביל
    # =====================================================================
    try:
        wamid = "wamid-pg-race"
        _out("sent", wamid)
        first = gt()
        message_status.apply_status_update(first, provider_message_id=wamid,
                                           status=message_status.READ)  # נועל, בלי commit
        done = {}

        def _second():
            s = gt()
            try:
                message_status.apply_status_update(s, provider_message_id=wamid,
                                                   status=message_status.DELIVERED)
                s.commit()
                done["at"] = time.monotonic()
            finally:
                s.close()

        t = threading.Thread(target=_second)
        t.start()
        time.sleep(1.0)
        blocked = t.is_alive()
        first.commit()
        first.close()
        t.join(5)
        final = _status_of(wamid)
        if blocked and final == "read":
            _ok("05_row_lock_no_regression", second_waited=True, final=final)
        else:
            _fail("05_row_lock_no_regression", blocked=blocked, final=final)
    except Exception as exc:
        _fail("05_row_lock_no_regression", error=_err(exc))

    # =====================================================================
    # 6) webhook — תשובה, כפילות רציפה, כפילות במקביל
    # =====================================================================
    def _items(wamid, phone):
        return messaging_router._webhook_items({"entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": _PNID}, "messages": [{
            "from": "972" + phone[1:], "id": wamid, "type": "interactive",
            "interactive": {"button_reply": {"id": "rsvp_yes"}},
        }]}}]}]})

    def _guest_and_counts(gid, wamid):
        s = gt()
        try:
            guest = s.get(models.Guest, gid)
            inbound = s.scalar(select(func.count()).select_from(models.Message)
                               .where(models.Message.provider_message_id == wamid))
            audits = s.scalar(select(func.count()).select_from(models.AuditLog)
                              .where(models.AuditLog.event_id == ev_id,
                                     models.AuditLog.action == "confirm_submit",
                                     models.AuditLog.detail.like(f"{guest.full_name}:%")))
            return guest.rsvp_status, guest.confirmed_count, inbound, audits
        finally:
            s.close()

    # תרחישים 6–7 בודקים עיבוד הודעות נכנסות ועדכון RSVP מלחיצת כפתור —
    # שניהם כבויים כברירת מחדל.
    os.environ["WHATSAPP_WEBHOOK_INBOUND"] = "1"
    os.environ["WHATSAPP_INBOUND_RSVP"] = "1"
    try:
        gid = guest_ids[1]
        g = gt()
        try:
            phone = g.get(models.Guest, gid).phone
        finally:
            g.close()
        items = _items("wamid-pg-in-1", phone)
        flags = [messaging_router._process_webhook_items(items) for _ in range(3)]
        st, cnt, inbound, audits = _guest_and_counts(gid, "wamid-pg-in-1")
        if flags == [False] * 3 and (st, cnt, inbound, audits) == ("confirmed", 2, 1, 1):
            _ok("06_webhook_reply_and_duplicates", rsvp=st, confirmed_count=cnt,
                inbound_rows=inbound, audit_rows=audits)
        else:
            _fail("06_webhook_reply_and_duplicates", flags=flags, rsvp=st, count=cnt,
                  inbound=inbound, audits=audits)
    except Exception as exc:
        _fail("06_webhook_reply_and_duplicates", error=_err(exc))

    try:
        gid = guest_ids[2]
        g = gt()
        try:
            phone = g.get(models.Guest, gid).phone
        finally:
            g.close()
        items = _items("wamid-pg-in-2", phone)
        barrier = threading.Barrier(4)
        flags: list = []

        def _hit():
            barrier.wait()
            flags.append(messaging_router._process_webhook_items(items))

        threads = [threading.Thread(target=_hit) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
        st, cnt, inbound, audits = _guest_and_counts(gid, "wamid-pg-in-2")
        if not any(flags) and len(flags) == 4 and (st, inbound, audits) == ("confirmed", 1, 1):
            _ok("07_webhook_concurrent_duplicates", inbound_rows=inbound, audit_rows=audits)
        else:
            _fail("07_webhook_concurrent_duplicates", flags=flags, rsvp=st,
                  inbound=inbound, audits=audits)
    except Exception as exc:
        _fail("07_webhook_concurrent_duplicates", error=_err(exc))
    finally:
        os.environ["WHATSAPP_WEBHOOK_INBOUND"] = ""
        os.environ["WHATSAPP_INBOUND_RSVP"] = ""

    # =====================================================================
    # 8) meta_test תחת RLS — רק הנמען המורשה נשלח ונרשם; לאחרים אין שורה
    # =====================================================================
    class _FakeMeta(messaging.MockProvider):
        name = "meta"
        external = True
        calls: list = []

        def send_invitation(self, phone, text_):
            _FakeMeta.calls.append(phone)
            return super().send_invitation(phone, text_)

    real_meta = messaging.MetaProvider
    try:
        g = gt()
        try:
            allowed_phone = g.get(models.Guest, guest_ids[3]).phone
        finally:
            g.close()
        os.environ["WHATSAPP_MODE"] = "meta_test"
        os.environ["WHATSAPP_TEST_RECIPIENTS"] = allowed_phone
        messaging.MetaProvider = _FakeMeta

        def _batch_all(db):
            event = db.get(models.Event, ev_id)
            gs = [db.get(models.Guest, gid) for gid in guest_ids]
            res = outbound.send_batch(db, event, [
                outbound.OutboundItem(guest=x, phone=x.phone, text="בדיקה", kind="reminder_2")
                for x in gs
            ])
            db.commit()
            return res

        res = await as_user(_batch_all)
        g = gt()
        try:
            rows = g.scalars(select(models.Message.guest_id).where(
                models.Message.event_id == ev_id, models.Message.kind == "reminder_2")).all()
        finally:
            g.close()
        if (res.sent, res.blocked) == (1, len(guest_ids) - 1) and rows == [guest_ids[3]] \
                and _FakeMeta.calls == [allowed_phone]:
            _ok("08_meta_test_allowlist_under_rls", sent=res.sent, blocked=res.blocked)
        else:
            _fail("08_meta_test_allowlist_under_rls", sent=res.sent, blocked=res.blocked,
                  rows=rows, calls=len(_FakeMeta.calls))
    except Exception as exc:
        _fail("08_meta_test_allowlist_under_rls", error=_err(exc))
    finally:
        messaging.MetaProvider = real_meta
        os.environ.pop("WHATSAPP_MODE", None)
        os.environ.pop("WHATSAPP_TEST_RECIPIENTS", None)

    # =====================================================================
    # 9) Meta (מזויפת, בלי רשת) תחת RLS: Template נשלח; timeout נשאר "לא ידוע";
    #    webhook עם המזהה הפנימי סוגר אותו — על Postgres, עם נעילת שורה
    # =====================================================================
    import httpx

    from app import whatsapp_meta, whatsapp_templates

    replies = [
        httpx.Response(200, json={"messages": [{"id": "wamid.pg-tpl-1", "message_status": "accepted"}]}),
        "timeout",
    ]

    def _fake_meta(request):
        nxt = replies.pop(0)
        if nxt == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        return nxt

    real_transport = whatsapp_meta._transport
    saved_templates = dict(whatsapp_templates.TEMPLATES)
    try:
        os.environ["WHATSAPP_MODE"] = "meta"
        os.environ["WHATSAPP_ACCESS_TOKEN"] = "pg-test-token"
        os.environ["WHATSAPP_PHONE_NUMBER_ID"] = "999"
        whatsapp_meta._transport = httpx.MockTransport(_fake_meta)
        whatsapp_templates.TEMPLATES["reminder_3_pg"] = whatsapp_templates.TemplateSpec(
            name="veya_pg_tpl", body_params=("guest_name",), url_button=True)
        g = gt()
        try:
            for gid in guest_ids[4:6]:
                g.get(models.Guest, gid).guest_token = f"tok-pg-{gid}"
            g.commit()
        finally:
            g.close()

        def _send(db):
            event = db.get(models.Event, ev_id)
            gs = [db.get(models.Guest, gid) for gid in guest_ids[4:6]]
            res = outbound.send_batch(db, event, [
                outbound.OutboundItem(guest=x, phone=x.phone, text="x", kind="reminder_3_pg")
                for x in gs
            ])
            db.commit()
            return res

        res = await as_user(_send)
        g = gt()
        try:
            rows = g.scalars(select(models.Message).where(
                models.Message.kind == "reminder_3_pg").order_by(models.Message.id)).all()
            sent_row, unknown_row = rows
            unknown_id, unknown_gid = unknown_row.id, unknown_row.guest_id
            unknown_phone = g.get(models.Guest, unknown_gid).phone
            states = [(r.status, r.provider_message_id) for r in rows]
        finally:
            g.close()
        ref = f"veya:m{unknown_id}:e{ev_id}:g{unknown_gid}"
        items = messaging_router._webhook_items({"entry": [{"changes": [{"value": {
            "metadata": {"phone_number_id": _PNID}, "statuses": [{
            "id": "wamid.pg-late", "status": "delivered", "timestamp": "1790000000",
            "recipient_id": "972" + unknown_phone[1:], "biz_opaque_callback_data": ref,
        }]}}]}]})
        transient = messaging_router._process_webhook_items(items)
        g = gt()
        try:
            after = g.get(models.Message, unknown_id)
            final = (after.status, after.provider_message_id)
        finally:
            g.close()
        if ((res.sent, res.unknown) == (1, 1)
                and states == [("sent", "wamid.pg-tpl-1"), ("pending", None)]
                and not transient and final == ("delivered", "wamid.pg-late")):
            _ok("09_meta_template_unknown_then_reconciled", states=states, final=final)
        else:
            _fail("09_meta_template_unknown_then_reconciled", sent=res.sent, unknown=res.unknown,
                  states=states, transient=transient, final=final)
    except Exception as exc:
        _fail("09_meta_template_unknown_then_reconciled", error=_err(exc))
    finally:
        whatsapp_meta._transport = real_transport
        whatsapp_templates.TEMPLATES.clear()
        whatsapp_templates.TEMPLATES.update(saved_templates)
        for k in ("WHATSAPP_MODE", "WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID"):
            os.environ.pop(k, None)

    print(json.dumps(RESULTS, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
