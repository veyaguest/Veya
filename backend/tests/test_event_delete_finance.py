"""מחיקת אירוע/חשבון כשיש כסף באירוע — החלטת המייסד 2026-10-28.

עד עכשיו מחיקת אירוע שקיבל מתנה באשראי נכשלה (מפתח זר מ-gifts), בכל שלושת
המסלולים: מחיקת אירוע, מחיקת חשבון עצמית, ומחיקת משתמש ע"י אדמין. מה נבדק:

1. מתנות ורכישות מסלול עוברות לרישום חשבונאי (GiftLedger / EntitlementLedger)
   **בלי שום פרט אישי** — לא שם הנותן, לא ההודעה, לא מוזמן, לא בעלים.
2. כל השאר נמחק: מעטפות, הוצאות ותשלומים, פרטי חשבון הבנק.
3. לא נשאר שום נתון יתום (בדיקת המפתחות הזרים של SQLite).
4. שלושת מסלולי המחיקה עובדים, גם דרך ה-API.
5. מי שרשם מעטפה/תשלום באירוע של בן/בת הזוג — מחיקת החשבון שלו לא נכשלת,
   והרשומה נשארת לבן/בת הזוג (רק מתנתקת ממנו).
6. שמירה מפני שכחה: כל טבלה עם מפתח זר לאירוע/מוזמן מטופלת במחיקה.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, event as sa_event, func, select, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import models  # noqa: E402
from app.account import delete_event_cascade, detach_user_finance  # noqa: E402
from app.database import Base  # noqa: E402
from app.routers.admin import _delete_user_impl  # noqa: E402

SENDER = "דנה כהן מהבדיקה"
MESSAGE = "מזל טוב, הודעה אישית מהבדיקה"
NOTE = "הערה פנימית עם שם של לקוח"


def _session() -> Session:
    engine = create_engine("sqlite://")

    @sa_event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _rec):  # noqa: ANN001 — כמו app/database.py: בלי זה SQLite לא אוכף FK
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(bind=engine)
    return Session(engine, autoflush=False, expire_on_commit=False)


def _user(db, is_admin=False) -> models.User:
    u = models.User(email=f"fin-{uuid.uuid4().hex[:8]}@veya.test", password_hash="x", display_name="בדיקה",
                    is_admin=is_admin)
    db.add(u)
    db.flush()
    return u


def _event_with_money(db, owner: models.User, recorder: models.User | None = None) -> dict:
    """אירוע עם כל סוגי הכסף: מתנה באשראי, רכישת מסלול, מעטפה, הוצאה+תשלום, חשבון בנק."""
    ev = models.Event(owner_id=owner.id, groom_name="יואב", bride_name="דנה", event_type="wedding")
    db.add(ev)
    db.flush()
    guest = models.Guest(event_id=ev.id, full_name="מוזמן", phone="0501234567", side="groom")
    db.add(guest)
    db.flush()
    gift = models.Gift(event_id=ev.id, guest_id=guest.id, gift_amount_agorot=50000, fee_agorot=2000,
                       total_agorot=52000, status="paid", provider="mock", provider_transaction_id="tx-123",
                       idempotency_key=uuid.uuid4().hex, sender_name=SENDER, message=MESSAGE)
    plan = models.Plan(key=f"p-{uuid.uuid4().hex[:6]}", name="מסלול")
    db.add_all([gift, plan])
    db.flush()
    pv = models.PlanVersion(plan_id=plan.id, version=1)
    db.add(pv)
    db.flush()
    ent = models.EventEntitlement(event_id=ev.id, plan_version_id=pv.id, price_agorot=39000,
                                  coupon_code="WELCOME", note=NOTE, created_by_id=owner.id)
    env = models.GiftEnvelope(event_id=ev.id, envelope_number=1, amount_agorot=36000, guest_id=guest.id,
                              recorded_by_user_id=(recorder or owner).id)
    exp = models.EventExpense(event_id=ev.id)
    db.add_all([ent, env, exp])
    db.flush()
    pay = models.ExpensePayment(expense_id=exp.id, event_id=ev.id, amount_agorot=10000,
                                recorded_by_user_id=(recorder or owner).id)
    acct = models.PayoutAccount(event_id=ev.id, bank_code=12, branch_number="600", account_number="123456")
    db.add_all([pay, acct])
    db.commit()
    return {"event": ev.id, "guest": guest.id, "gift": gift.id, "ent": ent.id, "pv": pv.id}


def _event_rows(db, event_id) -> dict:
    out = {}
    for m in (models.Gift, models.EventEntitlement, models.GiftEnvelope, models.EventExpense,
              models.ExpensePayment, models.PayoutAccount, models.Guest):
        out[m.__tablename__] = db.scalar(select(func.count()).select_from(m).where(m.event_id == event_id))
    return out


def _no_orphans(db) -> list:
    return db.execute(text("PRAGMA foreign_key_check")).all()


# ── 1–3. מחיקת אירוע ─────────────────────────────────────────────────────

def test_event_delete_keeps_anonymous_ledger_and_removes_everything_else() -> None:
    db = _session()
    owner = _user(db)
    ids = _event_with_money(db, owner)
    delete_event_cascade(db, db.get(models.Event, ids["event"]))
    db.commit()

    assert db.get(models.Event, ids["event"]) is None
    assert all(n == 0 for n in _event_rows(db, ids["event"]).values()), _event_rows(db, ids["event"])
    assert _no_orphans(db) == []

    gl = db.scalars(select(models.GiftLedger)).all()
    assert len(gl) == 1
    g = gl[0]
    assert (g.original_gift_id, g.event_ref, g.gift_amount_agorot, g.fee_agorot, g.total_agorot) == \
        (ids["gift"], ids["event"], 50000, 2000, 52000)
    assert (g.status, g.provider, g.provider_transaction_id, g.reason) == ("paid", "mock", "tx-123", "event_deleted")

    el = db.scalars(select(models.EntitlementLedger)).all()
    assert len(el) == 1
    assert (el[0].original_entitlement_id, el[0].event_ref, el[0].plan_version_id, el[0].price_agorot,
            el[0].coupon_code) == (ids["ent"], ids["event"], ids["pv"], 39000, "WELCOME")


def test_ledger_tables_hold_no_personal_data() -> None:
    """מבני — אין בכלל עמודות לשם, הודעה, מוזמן, בעלים או הערה; ואין מפתח זר."""
    personal = {"sender_name", "message", "guest_id", "owner_id", "user_id", "note", "created_by_id",
                "phone", "email", "full_name"}
    for model in (models.GiftLedger, models.EntitlementLedger):
        cols = {c.name for c in model.__table__.columns}
        assert not cols & personal, (model.__tablename__, cols & personal)
        assert not model.__table__.foreign_keys, model.__tablename__
    db = _session()
    owner = _user(db)
    ids = _event_with_money(db, owner)
    delete_event_cascade(db, db.get(models.Event, ids["event"]))
    db.commit()
    dump = " ".join(str(v) for r in db.execute(text("SELECT * FROM gift_ledger")).all() for v in r)
    dump += " ".join(str(v) for r in db.execute(text("SELECT * FROM entitlement_ledger")).all() for v in r)
    for secret in (SENDER, MESSAGE, NOTE):
        assert secret not in dump


def test_event_without_money_still_deletes_cleanly() -> None:
    db = _session()
    owner = _user(db)
    ev = models.Event(owner_id=owner.id, groom_name="א", bride_name="ב", event_type="brit")
    db.add(ev)
    db.commit()
    delete_event_cascade(db, ev)
    db.commit()
    assert db.get(models.Event, ev.id) is None
    assert db.scalar(select(func.count()).select_from(models.GiftLedger)) == 0
    assert _no_orphans(db) == []


# ── 4. מחיקת משתמש ע"י אדמין / מחיקה עצמית ────────────────────────────────

def test_admin_deletes_user_with_gifts() -> None:
    db = _session()
    admin = _user(db, is_admin=True)
    owner = _user(db)
    ids = _event_with_money(db, owner)
    _delete_user_impl(db, admin, owner, "user_and_events")
    db.commit()
    assert db.get(models.User, owner.id) is None
    assert db.get(models.Event, ids["event"]) is None
    assert db.scalar(select(func.count()).select_from(models.GiftLedger)) == 1
    assert _no_orphans(db) == []


# ── 5. רשם מעטפה באירוע של בן/בת הזוג ──────────────────────────────────────

def test_partner_who_recorded_money_can_delete_account() -> None:
    db = _session()
    admin = _user(db, is_admin=True)
    owner, partner = _user(db), _user(db)
    ids = _event_with_money(db, owner, recorder=partner)
    _delete_user_impl(db, admin, partner, "user_and_events")
    db.commit()
    assert db.get(models.User, partner.id) is None
    rows = _event_rows(db, ids["event"])
    assert rows["gift_envelopes"] == 1 and rows["expense_payments"] == 1  # נשארו לבעלים
    env = db.scalar(select(models.GiftEnvelope).where(models.GiftEnvelope.event_id == ids["event"]))
    assert env.recorded_by_user_id is None
    assert _no_orphans(db) == []


def test_detach_user_finance_is_harmless_without_rows() -> None:
    db = _session()
    u = _user(db)
    detach_user_finance(db, u.id)
    db.commit()


# ── 6. שמירה מפני שכחה ──────────────────────────────────────────────────

# כל טבלה שיש לה מפתח זר לאירוע או למוזמן, ואיך מחיקת אירוע מטפלת בה. טבלה
# חדשה שלא ברשימה מכשילה את הבדיקה — כדי שמחיקת אירוע לא תישבר שוב בשקט
# (כמו שקרה עם event_messages, event_invitations, ועכשיו gifts).
HANDLED = {
    "audit_logs", "automation_rules", "call_assignments", "call_logs", "call_round_controls", "call_tasks",
    "clarifications", "event_cycles", "event_entitlements", "event_expenses", "event_invitations",
    "event_members", "event_messages", "expense_payments", "gift_envelopes", "gifts", "guest_cycle_rsvp",
    "guests", "message_templates", "messages", "payout_accounts", "postponement_requests", "support_requests",
}


def test_every_event_dependent_table_is_handled_by_event_delete() -> None:
    dependent = {
        t.name for t in Base.metadata.tables.values()
        for fk in t.foreign_keys if fk.column.table.name in ("events", "guests")
    }
    missing = dependent - HANDLED
    assert not missing, f"טבלאות חדשות שתלויות באירוע ולא מטופלות ב-delete_event_cascade: {sorted(missing)}"


# ── דרך ה-API: מחיקת אירוע ומחיקת חשבון עצמית ──────────────────────────────

def _api_event_with_gift():
    from app.database import SessionLocal
    from tests.e2e_seating import bootstrap

    api, _ = bootstrap()
    db = SessionLocal()
    try:
        owner = db.get(models.Event, api.event_id).owner_id
        guest = models.Guest(event_id=api.event_id, full_name="מוזמן", phone="0507654321", side="groom")
        db.add(guest)
        db.flush()
        db.add(models.Gift(event_id=api.event_id, guest_id=guest.id, gift_amount_agorot=30000, fee_agorot=1200,
                           total_agorot=31200, status="paid", idempotency_key=uuid.uuid4().hex,
                           sender_name=SENDER, message=MESSAGE))
        db.add(models.GiftEnvelope(event_id=api.event_id, envelope_number=7, amount_agorot=18000,
                                   recorded_by_user_id=owner))
        db.commit()
    finally:
        db.close()
    return api


def _ledger_for(event_id) -> int:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        return db.scalar(select(func.count()).select_from(models.GiftLedger)
                         .where(models.GiftLedger.event_ref == event_id))
    finally:
        db.close()


# סופרים שינוי ולא סך: ב-SQLite מספר של אירוע שנמחק חוזר לאירוע הבא (ב-Postgres
# לא), כך שהרישום יכול להכיל כבר שורה עם אותו event_ref מבדיקה קודמת.
def test_api_delete_event_with_gift() -> None:
    api = _api_event_with_gift()
    before = _ledger_for(api.event_id)
    r = api.client.delete(f"/events/{api.event_id}", headers=api.headers)
    assert r.status_code == 204, r.text
    assert _ledger_for(api.event_id) == before + 1


def test_api_delete_own_account_with_gift() -> None:
    api = _api_event_with_gift()
    before = _ledger_for(api.event_id)
    r = api.client.delete("/auth/me", headers=api.headers)
    assert r.status_code == 204, r.text
    assert _ledger_for(api.event_id) == before + 1


def teardown_module(module) -> None:  # noqa: ARG001
    from tests.e2e_seating import shutdown

    shutdown()

