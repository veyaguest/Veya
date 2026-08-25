"""אימות נוהל הדחייה מול Postgres אמיתי עם RLS מותקן.

בדיקות ה-SQLite (``test_postponement.py``) מוכיחות את הלוגיקה. הקובץ הזה
מוכיח משהו אחר, שאי אפשר להוכיח ב-SQLite: **שמדיניות ה-RLS של
``rls/15_postponement_rls.sql`` לא שוברת את הזרימה, ושהיא באמת חוסמת עקיפה
ישירה ב-DB.** RLS הוא no-op גמור ב-SQLite.

לא רץ כחלק מהסוויטה הרגילה. דורש שרת VEYA חי שמחובר ל-Postgres שכבר הורצו
עליו קובצי ה-RLS. בלי משתני הסביבה — מדפיס הסבר ויוצא בהצלחה, כדי שהרצה
בטעות לא תיראה ככישלון.

משתני סביבה:
  RLS_BASE_URL      — כתובת ה-API של השרת (למשל http://127.0.0.1:8101).
  RLS_ADMIN_DB_URL  — connection string כ-superuser. משמש את ה-harness בלבד
                      (יצירת משתמשי בדיקה ואימות ישיר של שורות) — עוקף RLS
                      בכוונה, זו התשתית ולא הבדיקה.
  RLS_APP_DB_URL    — אופציונלי: connection string כ-``veya_app``. כשהוא
                      קיים נבדקת גם עקיפה ישירה ב-DB (הבדיקה החשובה ביותר
                      כאן). בלעדיו הבדיקה מדולגת.

**איך מקימים Postgres מקומי לבדיקה** (בלי Docker, בלי התקנה על המערכת):

    pip install pgserver
    python -c "import pgserver; s=pgserver.get_server('/tmp/pgdata'); print(s.get_uri())"

ואז יוצרים סכימה (``create_all``), מריצים את ``rls/01``–``rls/15``, ומרימים
uvicorn עם ``DATABASE_URL`` מוצבע לשם. הפירוט המלא ב-``rls/POSTPONEMENT_ROLLOUT.md``.

הרצה:
    RLS_BASE_URL=http://127.0.0.1:8101 RLS_ADMIN_DB_URL=... \
        venv/bin/python tests/test_postponement_rls_postgres.py
"""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if not (os.getenv("RLS_BASE_URL") and os.getenv("RLS_ADMIN_DB_URL")):
    print(
        "חסרים RLS_BASE_URL / RLS_ADMIN_DB_URL — ראו את הדוקסטרינג בראש הקובץ. "
        "מדלג (לא נכשל)."
    )
    raise SystemExit(0)

B = os.environ["RLS_BASE_URL"]
SU = os.environ["RLS_ADMIN_DB_URL"]
ok = fail = 0
def check(name, cond, detail=""):
    global ok, fail
    if cond: ok += 1; print(f"  ✓ {name}")
    else: fail += 1; print(f"  ✗ {name} — {detail}")

def call(m, p, h=None, b=None):
    d = json.dumps(b).encode() if b is not None else None
    r = urllib.request.Request(B+p, data=d, method=m,
        headers={"Content-Type": "application/json", **(h or {})})
    try:
        with urllib.request.urlopen(r) as x:
            return x.status, json.loads(x.read().decode() or "null")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try: body = json.loads(body)
        except Exception: pass
        return e.code, body

def su(sql, *a):
    c = psycopg2.connect(SU); cur = c.cursor()
    cur.execute(sql, a or None)
    rows = cur.fetchall() if cur.description else None
    c.commit(); c.close(); return rows

def mkuser(name, admin=False):
    """יוצר משתמש דרך ה-ORM (כ-superuser) ואז מתחבר דרך ה-API האמיתי.

    לא דרך ``POST /auth/register`` במכוון: על סכימה טרייה שנוצרה ב-
    ``create_all`` כמה עמודות ב-``users`` הן NOT NULL, ואילו
    ``app_register_user`` (rls/01) אינה מציבה להן ערך — ולכן ההרשמה נופלת
    שם. זהו באג קיים ולא-קשור לנוהל הדחייה; ה-harness עוקף אותו כדי לבדוק
    את מה שהוא בא לבדוק, ו-``POST /auth/login`` עדיין נבדק לאמיתו.
    """
    from datetime import datetime as _dt
    from sqlalchemy import create_engine as _ce
    from sqlalchemy.orm import Session as _S
    from app import models as _m
    from app.auth import hash_password as _hp
    email = f"rls-{uuid.uuid4().hex[:8]}@veya.test"
    eng = _ce(SU)
    with _S(eng) as db:
        db.add(_m.User(email=email, password_hash=_hp("Test12345!"), display_name=name,
                       phone="0501234567", email_verified_at=_dt.utcnow(), is_admin=admin))
        db.commit()
    eng.dispose()
    st, res = call("POST", "/auth/login", b={"email": email, "password": "Test12345!"})
    assert st == 200, (st, res)
    return res["access_token"], email


print("\n=== 1. הרשמה ויצירת אירוע תחת RLS ===")
tok, email = mkuser("זוג בדיקה")
H = {"Authorization": f"Bearer {tok}"}
st, ev = call("POST", "/events", H, {"groom_name": "איתי", "bride_name": "דנה",
              "event_type": "wedding", "venue_name": "אולם הבדיקה"})
check("יצירת אירוע", st == 201, f"{st} {ev}")
eid = ev["id"]; H["X-Event-Id"] = str(eid)
st, _ = call("PATCH", "/event", H, {"event_date": "2026-11-12", "event_time": "19:30",
                                    "venue_commit_days_before": 5})
check("מילוי ראשוני של פרטי האירוע", st == 200, str(_))
for n, p in [("שרה כהן", "0501111111"), ("יוסי לוי", "0502222222")]:
    call("POST", "/guests", H, {"full_name": n, "phone": p})
g = call("GET", "/guests", H)[1]["items"]
check("מוזמנים נוצרו", len(g) == 2, str(len(g)))
su("update guests set rsvp_status='confirmed', confirmed_count=2, table_number=3 where id=%s", g[0]["id"])

print("\n=== 2. נעילה נאכפת בשרת (RLS + API) ===")
st, r = call("PATCH", "/event", H, {"event_date": "2027-01-01"})
check("שינוי תאריך נחסם", st == 409, str(r))
st, r = call("PATCH", "/event", H, {"groom_name": "מישהו אחר"})
check("שינוי שם נחסם", st == 409, str(r))
st, r = call("PATCH", "/event", H, {"venue_name": "אולם אחר", "venue_address": "דיזנגוף 1"})
check("אולם וכתובת נשמרו", st == 200, str(r))

print("\n=== 3. בקשת דחייה ===")
st, r = call("POST", "/postpone", H)
check("בקשה נפתחה בלי תאריך", st == 201 and r["status"] == "pending", f"{st} {r}")
st, r = call("POST", "/postpone", H)
check("בקשה כפולה נחסמה", st == 409, str(r))

print("\n=== 4. הפרדת סמכויות תחת RLS ===")
st, r = call("GET", "/admin/postpone", H)
check("זוג לא רואה את תור האדמין", st in (401, 403), str(st))
st, r = call("POST", f"/admin/postpone/{eid}/approve", H)
check("זוג לא יכול לאשר לעצמו", st in (401, 403), str(st))
# ניסיון עקיפה ישיר ב-DB בזהות הזוג — זה מה שמדיניות ה-UPDATE אמורה לחסום
uid = su("select id from users where email=%s", email)[0][0]
app_uri = os.environ.get("RLS_APP_DB_URL", "")
if app_uri:
    c = psycopg2.connect(app_uri); cur = c.cursor()
    cur.execute("select set_config('app.current_user_id', %s, true)", (str(uid),))
    cur.execute("update postponement_requests set status='approved' where event_id=%s", (eid,))
    moved = cur.rowcount
    c.rollback(); c.close()
    check("עקיפה ישירה ב-DB נחסמה ע\"י RLS", moved == 0, f"עודכנו {moved} שורות")
else:
    print("  · דילוג על בדיקת העקיפה הישירה (אין RLS_APP_DB_URL)")

print("\n=== 5. אישור אדמין ===")
atok, _ = mkuser("מנהל", admin=True)
AH = {"Authorization": f"Bearer {atok}"}
rows = call("GET", "/admin/postpone", AH)[1]
check("הבקשה מופיעה לאדמין", any(x["event_id"] == eid for x in rows), str(len(rows)))
st, r = call("POST", f"/admin/postpone/{eid}/approve", AH)
check("אדמין אישר", st == 200 and r["status"] == "approved", f"{st} {r}")

print("\n=== 6. עריכה מלאה נפתחה ===")
st, e = call("GET", "/event", H)
check("edit_locked=false", e["edit_locked"] is False, str(e.get("edit_locked")))
check("שלב = open", e["event_stage"] == "open", e.get("event_stage"))
st, r = call("PATCH", "/event", H, {"event_date": "2027-05-20", "event_time": "20:00",
                                    "bride_name": "דנה כהן", "venue_commit_days_before": 8})
check("תאריך/שם/מועד סגירה עודכנו", st == 200 and r["event_date"] == "2027-05-20", str(r)[:160])
check("מועד סגירת רשימה חדש נשמר", r.get("venue_commit_days_before") == 8, str(r.get("venue_commit_days_before")))
check("שלב = new_date_set", r["event_stage"] == "new_date_set", r.get("event_stage"))
seq = call("GET", "/communication/sequence", H)[1]
check("קטגוריית 'אירוע נדחה' נפתחה", any(m["message_type"] == "postponement" for m in seq),
      str([m["message_type"] for m in seq]))

print("\n=== 7. שליחת הודעת דחייה ===")
call("PUT", "/communication/sequence/postponement", H,
     {"content": "שלום {{guest_name}}, האירוע נדחה. נעדכן בקרוב."})
st, r = call("POST", "/communication/sequence/postponement/send", H, {"audience": "all"})
check("הודעת דחייה נשלחה", st == 200 and r["sent"] == 2, f"{st} {r}")

print("\n=== 8. מחזור חדש ===")
st, r = call("POST", "/postpone/complete", H)
check("מחזור חדש נפתח", st == 200 and r["status"] == "completed", f"{st} {r}")
gs = call("GET", "/guests", H)[1]["items"]
check("כל המוזמנים חזרו ל'טרם השיב'", all(x["rsvp_status"] == "pending" for x in gs), str(gs)[:120])
check("שיבוץ השולחן נשמר", any(x["table_number"] == 3 for x in gs), str([x["table_number"] for x in gs]))
arch = su("select rsvp_status, confirmed_count, table_number, cycle_number from guest_cycle_rsvp where event_id=%s", eid)
check("ארכיון RSVP נכתב", len(arch) == 2 and any(a[0] == "confirmed" and a[1] == 2 for a in arch), str(arch))
cyc = su("select cycle_number, event_date from event_cycles where event_id=%s", eid)
check("מחזור קודם נשמר עם התאריך הישן", cyc and cyc[0][1] == "2026-11-12", str(cyc))
st, e = call("GET", "/event", H)
check("מחזור = 2", e["cycle_number"] == 2, str(e.get("cycle_number")))
check("האירוע ננעל מחדש", e["edit_locked"] is True, str(e.get("edit_locked")))
st, r = call("PATCH", "/event", H, {"event_date": "2028-01-01"})
check("תאריך נעול שוב", st == 409, str(st))
prev = call("GET", "/automation/track/preview", H)[1]
check("הזמנה חדשה נפתחה לכל המוזמנים", prev["not_yet_sent"] == 2 and prev["already_sent"] == 0, str(prev))
seq = call("GET", "/communication/sequence", H)[1]
check("כרטיס הדחייה יצא מהתצוגה", not any(m["message_type"] == "postponement" for m in seq), "עדיין מוצג")
old = su("select count(*) from messages where event_id=%s and cycle_number=1", eid)[0][0]
check("הודעות המחזור הקודם לא נמחקו", old >= 2, str(old))

print("\n=== 9. RSVP של אורח במחזור החדש ===")
tokn = su("select guest_token from guests where id=%s", gs[0]["id"])[0][0]
st, r = call("POST", f"/confirm/{tokn}", None, {"coming": True, "count": 2})
check("אורח אישר הגעה במחזור החדש", st == 200, f"{st} {str(r)[:120]}")
st2 = su("select rsvp_status from guests where id=%s", gs[0]["id"])[0][0]
check("הסטטוס נשמר", st2 == "confirmed", st2)

print("\n=== 10. דחייה שנייה (מחזור 3) ===")
call("POST", "/postpone", H)
call("POST", f"/admin/postpone/{eid}/approve", AH)
call("PATCH", "/event", H, {"event_date": "2027-09-09"})
st, r = call("POST", "/postpone/complete", H)
check("מחזור 3 נפתח", st == 200, f"{st} {r}")
e = call("GET", "/event", H)[1]
check("מחזור = 3", e["cycle_number"] == 3, str(e.get("cycle_number")))
cycs = su("select cycle_number, event_date from event_cycles where event_id=%s order by cycle_number", eid)
check("היסטוריית שני המחזורים נשמרה", [c[0] for c in cycs] == [1, 2], str(cycs))

print("\n=== 11. דחיית בקשה ע\"י אדמין ===")
call("POST", "/postpone", H)
st, r = call("POST", f"/admin/postpone/{eid}/reject", AH, {"reason": ""})
check("דחייה בלי סיבה נחסמה", st == 409, str(st))
st, r = call("POST", f"/admin/postpone/{eid}/reject", AH, {"reason": "נפתח בטעות"})
check("אדמין דחה עם סיבה", st == 200, f"{st} {r}")
p = call("GET", "/postpone", H)[1]
check("הזוג רואה סיבת דחייה", p["rejection_reason"] == "נפתח בטעות", str(p))
check("אפשר לבקש שוב", p["can_request"] is True, str(p.get("can_request")))

print("\n=== 12. בידוד בין אירועים (RLS) ===")
tok2, _ = mkuser("זוג אחר")
H2 = {"Authorization": f"Bearer {tok2}", "X-Event-Id": str(eid)}
st, r = call("GET", "/postpone", H2)
check("זוג זר לא רואה נוהל של אירוע אחר", st in (403, 404), f"{st} {str(r)[:80]}")
st, r = call("GET", "/event", H2)
check("זוג זר לא רואה את האירוע", st in (403, 404), str(st))

print(f"\n{'='*46}\nעברו: {ok} | נכשלו: {fail}")
sys.exit(1 if fail else 0)
