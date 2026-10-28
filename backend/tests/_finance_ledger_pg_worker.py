"""מחיקת אירוע עם כסף מול Postgres + RLS אמיתי (pgserver) — תהליך-בת, JSON בשורה האחרונה.

טבלת gifts חסומה לכתיבה ישירה (rls/13) — לכן כאן נבדק המסלול האמיתי של
הייצור: הפונקציה המבוקרת app_archive_event_finance (rls/30), דרך ה-API, כשהאפליקציה
רצה בתפקיד המוגבל veya_app. שלושה מסלולים: מחיקת אירוע, מחיקת חשבון עצמית,
ומחיקת משתמש ע"י אדמין.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RLS_FILES = [
    "01_helpers_and_grants.sql", "02_policies.sql", "04_consent_records_rls_fix.sql",
    "05_event_messages_rls.sql", "06_call_logs_rls.sql", "07_phone_agent_rls.sql",
    "08_partner_comanagement.sql", "09_email_verification_rls_fix.sql",
    "11_event_messages_delete_rls_fix.sql", "12_password_reset.sql", "13_gifts_rls.sql",
    "14_payout_accounts_rls.sql", "16_finance_rls.sql", "17_expense_payments_rls.sql",
    "23_commerce_rls.sql", "30_finance_ledger_rls.sql",
]


def main() -> None:
    import psycopg2
    from fastapi.testclient import TestClient

    from app import auth, database, legal, models

    database.Base.metadata.create_all(bind=database.migrations_engine)
    admin = psycopg2.connect(os.environ["MIGRATIONS_DATABASE_URL"])
    admin.autocommit = True
    cur = admin.cursor()
    rls = Path(__file__).resolve().parent.parent / "rls"
    for f in RLS_FILES:
        cur.execute((rls / f).read_text())

    s = database.MigrationSessionLocal()

    def user(is_admin=False, consents=True):
        u = models.User(email=f"pg-{uuid.uuid4().hex[:8]}@veya.test", password_hash="x", display_name="בדיקה",
                        is_admin=is_admin, admin_role="super_admin" if is_admin else None,
                        email_verified_at=datetime.utcnow(), token_version=1, phone="0501234567")
        s.add(u)
        s.flush()
        if consents:
            for t in legal.REQUIRED_CONSENT_TYPES:
                legal.record_consent(s, u.id, t, source="test")
        return u

    plan = models.Plan(key=f"p-{uuid.uuid4().hex[:6]}", name="מסלול")
    s.add(plan)
    s.flush()
    pv = models.PlanVersion(plan_id=plan.id, version=1)
    s.add(pv)
    s.flush()

    def event_with_money(owner):
        ev = models.Event(owner_id=owner.id, groom_name="יואב", bride_name="דנה", event_type="wedding")
        s.add(ev)
        s.flush()
        g = models.Guest(event_id=ev.id, full_name="מוזמן", phone="0507654321", side="groom")
        s.add(g)
        s.flush()
        exp = models.EventExpense(event_id=ev.id)
        s.add_all([
            models.Gift(event_id=ev.id, guest_id=g.id, gift_amount_agorot=50000, fee_agorot=2000,
                        total_agorot=52000, status="paid", provider_transaction_id="tx-pg",
                        idempotency_key=uuid.uuid4().hex, sender_name="שם אישי", message="הודעה אישית"),
            models.EventEntitlement(event_id=ev.id, plan_version_id=pv.id, price_agorot=39000, note="הערה"),
            models.GiftEnvelope(event_id=ev.id, envelope_number=1, amount_agorot=36000, guest_id=g.id,
                                recorded_by_user_id=owner.id),
            models.PayoutAccount(event_id=ev.id, bank_code=12, branch_number="600", account_number="123456"),
            exp,
        ])
        s.flush()
        s.add(models.ExpensePayment(expense_id=exp.id, event_id=ev.id, amount_agorot=10000,
                                    recorded_by_user_id=owner.id))
        return ev.id

    # b: בלי אישורי הסכמה — כדי שהבדיקה תבדוק את חלק הכסף במחיקה העצמית.
    # d: עם אישורי הסכמה ובלי כסף — מתעד תקלה קיימת (ניתוק consent_records
    # במחיקה עצמית נחסם ב-RLS), ראו test_finance_ledger_postgres.
    a, b, c, boss = user(), user(consents=False), user(), user(is_admin=True)
    d = user()
    ev_a, ev_b, ev_c = event_with_money(a), event_with_money(b), event_with_money(c)
    s.commit()
    tokens = {u.id: auth.create_access_token(u) for u in (a, b, c, boss, d)}
    s.close()

    out: dict = {}
    with TestClient(database_app()) as client:
        def h(uid):
            return {"Authorization": f"Bearer {tokens[uid]}"}

        out["delete_event"] = client.delete(f"/events/{ev_a}", headers=h(a.id)).status_code
        out["delete_me"] = client.delete("/auth/me", headers=h(b.id)).status_code
        out["admin_delete"] = client.delete(f"/admin/users/{c.id}?mode=user_and_events",
                                            headers=h(boss.id)).status_code
        out["delete_me_with_consents"] = client.delete("/auth/me", headers=h(d.id)).status_code

    def q(sql, args=()):
        cur.execute(sql, args)
        return cur.fetchall()

    ids = (ev_a, ev_b, ev_c)
    out["gifts_left"] = q("SELECT count(*) FROM gifts WHERE event_id = ANY(%s)", (list(ids),))[0][0]
    out["events_left"] = q("SELECT count(*) FROM events WHERE id = ANY(%s)", (list(ids),))[0][0]
    out["ledger_rows"] = q("SELECT count(*) FROM gift_ledger WHERE event_ref = ANY(%s)", (list(ids),))[0][0]
    out["ent_ledger_rows"] = q("SELECT count(*) FROM entitlement_ledger WHERE event_ref = ANY(%s)",
                               (list(ids),))[0][0]
    out["money_left"] = sum(q(f"SELECT count(*) FROM {t} WHERE event_id = ANY(%s)", (list(ids),))[0][0]
                            for t in ("gift_envelopes", "event_expenses", "expense_payments",
                                      "payout_accounts", "event_entitlements"))
    out["ledger_amounts"] = q("SELECT DISTINCT gift_amount_agorot, fee_agorot, status, provider_transaction_id "
                              "FROM gift_ledger WHERE event_ref = ANY(%s)", (list(ids),))
    out["ledger_columns"] = [r[0] for r in q(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'gift_ledger'")]

    # מי רואה את הרישום: veya_app בזהות בעלים רגיל — כלום; בזהות אדמין — הכול.
    app_conn = psycopg2.connect(os.environ["DATABASE_URL"])
    ac = app_conn.cursor()
    seen = {}
    for label, uid in (("owner", a.id), ("admin", boss.id)):
        ac.execute("BEGIN")
        ac.execute("SELECT set_config('app.current_user_id', %s, true)", (str(uid),))
        ac.execute("SELECT count(*) FROM gift_ledger")
        seen[label] = ac.fetchone()[0]
        try:
            ac.execute("INSERT INTO gift_ledger (original_gift_id, event_ref, gift_amount_agorot, fee_agorot, "
                       "total_agorot, status) VALUES (1, 1, 1, 0, 1, 'paid')")
            seen[label + "_direct_insert"] = "allowed"
        except Exception:  # noqa: BLE001
            seen[label + "_direct_insert"] = "blocked"
        ac.execute("ROLLBACK")
    out["visibility"] = seen
    app_conn.close()
    admin.close()
    print(json.dumps(out, ensure_ascii=False, default=str))


def database_app():
    from app.main import app

    return app


if __name__ == "__main__":
    main()
