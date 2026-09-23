"""משימות מערכת מתוזמנות — בלי משתמש מחובר.

``POST /internal/jobs/call-sync`` מריץ את ``call_ops.sync`` המלא, כדי שתכנון
השיחות של היום יישמר גם אם אף אדמין לא נכנס. מופעל פעמיים ביום ע"י GitHub
Actions (``.github/workflows/call-sync.yml``).

``POST /internal/jobs/rsvp-tick`` מריץ את מסלול אישורי ההגעה (``rsvp_scheduler``)
— שליחת סבבי ה-WhatsApp, הודעת יום האירוע והתודה — בלי תלות בכניסה של מישהו
למסך. מופעל כל 15 דקות בשעות השליחה (``.github/workflows/rsvp-tick.yml``).

אבטחה:
- מופעל רק כשמוגדר ``VEYA_JOB_SECRET`` בשרת. בלעדיו — 404 (כאילו לא קיים).
- חובה כותרת ``X-Veya-Job-Secret`` זהה (השוואה בזמן קבוע). אחרת — 404.
- לא מקבל שום פרמטר מבחוץ: אין מה "לכוון". תוצאה = מספרים בלבד, בלי מידע אישי.
- idempotent: ריצה חוזרת/מקבילה לא יוצרת כפילויות (ראו ``call_ops._insert_tasks``
  ו-``_try_sync_lock``).

החיבור למסד: ``MigrationSessionLocal`` — אותו חיבור מערכת שמשמש את תחזוקת
העלייה, כי אין כאן זהות משתמש שה-RLS יכול לסנן לפיה.
"""
from __future__ import annotations

import hmac
import os
import time
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from app import call_ops, rsvp_scheduler
from app.database import MigrationSessionLocal

router = APIRouter(prefix="/internal/jobs", tags=["internal"], include_in_schema=False)


def _authorized(given: Optional[str]) -> bool:
    secret = os.getenv("VEYA_JOB_SECRET", "").strip()
    if len(secret) < 24 or not given:
        return False
    return hmac.compare_digest(secret.encode(), given.strip().encode())


@router.post("/call-sync")
def run_call_sync(x_veya_job_secret: Optional[str] = Header(default=None)):
    if not _authorized(x_veya_job_secret):
        raise HTTPException(status_code=404, detail="Not Found")
    started = time.monotonic()
    with MigrationSessionLocal() as db:
        try:
            stats = call_ops.sync(db, force=True)
            db.commit()
        except Exception as exc:  # noqa: BLE001 — מדווחים ל-Actions, לא מפילים את השרת
            db.rollback()
            print(f"[veya:jobs] call-sync נכשל: {exc!r}", flush=True)
            raise HTTPException(status_code=500, detail="call-sync failed") from exc
    result = {"ok": True, "seconds": round(time.monotonic() - started, 2), **asdict(stats)}
    print(f"[veya:jobs] call-sync {result}", flush=True)
    return result


@router.post("/rsvp-tick")
def run_rsvp_tick(x_veya_job_secret: Optional[str] = Header(default=None)):
    if not _authorized(x_veya_job_secret):
        raise HTTPException(status_code=404, detail="Not Found")
    started = time.monotonic()
    with MigrationSessionLocal() as db:
        try:
            stats = rsvp_scheduler.run(db)
        except Exception as exc:  # noqa: BLE001 — מדווחים ל-Actions, לא מפילים את השרת
            db.rollback()
            print(f"[veya:jobs] rsvp-tick נכשל: {exc!r}", flush=True)
            raise HTTPException(status_code=500, detail="rsvp-tick failed") from exc
    result = {"ok": True, "seconds": round(time.monotonic() - started, 2), **asdict(stats)}
    print(f"[veya:jobs] rsvp-tick {result}", flush=True)
    return result
