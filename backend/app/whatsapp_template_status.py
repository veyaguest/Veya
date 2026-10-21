"""האם תבנית WhatsApp מאושרת ב-Meta — לפני ששולחים אותה.

למה: תבנית שעוד ממתינה לאישור (PENDING) או נדחתה — Meta מחזירה עליה שגיאה,
וההודעה נרשמת כנכשלה ("נשרפת"). כאן בודקים קודם: תבנית שידוע שאינה מאושרת
לא נשלחת ולא נרשמת (``whatsapp_templates.NOT_APPROVED``), והסבב יוצא כשתאושר
— כל עוד החלון שלו פתוח.

רשימת התבניות נקראת מ-Meta (``GET /{waba}/message_templates``) ונשמרת בזיכרון
ל-``CACHE_SECONDS``. בלי מזהה חשבון (``WHATSAPP_BUSINESS_ACCOUNT_ID``) או כשהקריאה
נכשלת — לא חוסמים: Meta עצמה דוחה תבנית לא מאושרת. הבדיקה כאן היא שכבת
זהירות, לא תנאי לשליחה.

מאותה קריאה נשמר גם **הסיווג** של כל תבנית (``UTILITY`` / ``MARKETING``) — הזוג
בוחר בבקשת האישור ובתזכורות רק נוסחים ש-Meta סיווגה כשירות (``message_wording``,
2026-10-21). לא ידוע (אין חיבור) — לא מסננים.
"""
from __future__ import annotations

import time
from typing import Optional

CACHE_SECONDS = 600
# קריאה ל-Meta שנכשלה — לא מנסים שוב לפני כן. בלי זה, כש-Meta לא עונה, כל
# שאלה על תבנית (עשרות בפתיחת מסך ההודעות, אחת לכל הודעה במנה) הייתה מחכה
# ל-timeout מחדש (נמצא בבדיקה 2026-10-21).
RETRY_AFTER_FAILURE_SECONDS = 60
APPROVED = "APPROVED"
UTILITY = "UTILITY"
MARKETING = "MARKETING"

# (name, language) → (status, category). ``None`` = לא נטען / לא זמין.
_cache: Optional[dict[tuple[str, str], tuple[str, str]]] = None
_loaded_at = 0.0
_failed_at: Optional[float] = None
# נקודות החלפה לבדיקות: dict קבוע במקום קריאה ל-Meta.
_override: Optional[dict[tuple[str, str], str]] = None
_category_override: Optional[dict[tuple[str, str], str]] = None


def _fetch() -> Optional[dict[tuple[str, str], tuple[str, str]]]:
    import httpx

    from app import whatsapp_meta

    config = whatsapp_meta.load_config()
    if not config.access_token or not config.business_account_id:
        return None
    url = (f"https://graph.facebook.com/{config.graph_version}/"
           f"{config.business_account_id}/message_templates")
    params: dict = {"limit": 200, "fields": "name,language,status,category"}
    out: dict[tuple[str, str], tuple[str, str]] = {}
    try:
        with whatsapp_meta._client() as client:
            for _ in range(20):
                resp = client.get(url, params=params,
                                  headers={"Authorization": f"Bearer {config.access_token}"})
                if resp.status_code >= 300:
                    print(f"[veya:whatsapp] template status http={resp.status_code}", flush=True)
                    return None
                body = resp.json()
                for t in body.get("data", []):
                    out[(t.get("name"), t.get("language"))] = (t.get("status"), t.get("category"))
                after = (body.get("paging") or {}).get("cursors", {}).get("after")
                if not after or not (body.get("paging") or {}).get("next"):
                    break
                params = dict(params, after=after)
    except (httpx.HTTPError, ValueError) as exc:
        print(f"[veya:whatsapp] template status error={type(exc).__name__}", flush=True)
        return None
    return out


def _templates(force: bool = False) -> Optional[dict[tuple[str, str], tuple[str, str]]]:
    global _cache, _loaded_at, _failed_at
    now = time.monotonic()
    stale = _cache is None or now - _loaded_at > CACHE_SECONDS
    recently_failed = _failed_at is not None and now - _failed_at < RETRY_AFTER_FAILURE_SECONDS
    if force or (stale and not recently_failed):
        fetched = _fetch()
        if fetched is not None:
            _cache, _loaded_at, _failed_at = fetched, time.monotonic(), None
        else:
            _failed_at = time.monotonic()
    return _cache


def statuses(force: bool = False) -> Optional[dict[tuple[str, str], str]]:
    if _override is not None:
        return _override
    known = _templates(force)
    return None if known is None else {k: v[0] for k, v in known.items()}


def category_of(name: str, language: str = "he") -> Optional[str]:
    """הסיווג ב-Meta (``UTILITY`` / ``MARKETING`` …), או ``None`` אם אין תבנית
    כזו או שלא ידוע (אין חיבור)."""
    if _category_override is not None:
        return _category_override.get((name, language))
    known = _templates()
    if known is None:
        return None
    entry = known.get((name, language))
    return entry[1] if entry else None


def status_of(name: str, language: str = "he") -> Optional[str]:
    """הסטטוס ב-Meta (APPROVED / PENDING / REJECTED…), ``"MISSING"`` אם אין תבנית
    כזו, או ``None`` אם לא ידוע (אין חיבור)."""
    known = statuses()
    if known is None:
        return None
    return known.get((name, language), "MISSING")


def is_sendable(name: str, language: str = "he") -> bool:
    """שולחים אם התבנית מאושרת, או אם אי אפשר לדעת (Meta תחליט)."""
    status = status_of(name, language)
    return status is None or status == APPROVED


def reset() -> None:
    global _cache, _loaded_at, _failed_at
    _cache, _loaded_at, _failed_at = None, 0.0, None
