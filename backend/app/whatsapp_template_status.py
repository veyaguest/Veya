"""האם תבנית WhatsApp מאושרת ב-Meta — לפני ששולחים אותה.

למה: תבנית שעוד ממתינה לאישור (PENDING) או נדחתה — Meta מחזירה עליה שגיאה,
וההודעה נרשמת כנכשלה ("נשרפת"). כאן בודקים קודם: תבנית שידוע שאינה מאושרת
לא נשלחת ולא נרשמת (``whatsapp_templates.NOT_APPROVED``), והסבב יוצא כשתאושר
— כל עוד החלון שלו פתוח.

רשימת התבניות נקראת מ-Meta (``GET /{waba}/message_templates``) ונשמרת בזיכרון
ל-``CACHE_SECONDS``. בלי מזהה חשבון (``WHATSAPP_BUSINESS_ACCOUNT_ID``) או כשהקריאה
נכשלת — לא חוסמים: Meta עצמה דוחה תבנית לא מאושרת. הבדיקה כאן היא שכבת
זהירות, לא תנאי לשליחה.
"""
from __future__ import annotations

import time
from typing import Optional

CACHE_SECONDS = 600
APPROVED = "APPROVED"

# (name, language) → status. ``None`` = לא נטען / לא זמין.
_cache: Optional[dict[tuple[str, str], str]] = None
_loaded_at = 0.0
# נקודת החלפה לבדיקות: dict קבוע במקום קריאה ל-Meta.
_override: Optional[dict[tuple[str, str], str]] = None


def _fetch() -> Optional[dict[tuple[str, str], str]]:
    import httpx

    from app import whatsapp_meta

    config = whatsapp_meta.load_config()
    if not config.access_token or not config.business_account_id:
        return None
    url = (f"https://graph.facebook.com/{config.graph_version}/"
           f"{config.business_account_id}/message_templates")
    params: dict = {"limit": 200, "fields": "name,language,status"}
    out: dict[tuple[str, str], str] = {}
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
                    out[(t.get("name"), t.get("language"))] = t.get("status")
                after = (body.get("paging") or {}).get("cursors", {}).get("after")
                if not after or not (body.get("paging") or {}).get("next"):
                    break
                params = dict(params, after=after)
    except (httpx.HTTPError, ValueError) as exc:
        print(f"[veya:whatsapp] template status error={type(exc).__name__}", flush=True)
        return None
    return out


def statuses(force: bool = False) -> Optional[dict[tuple[str, str], str]]:
    global _cache, _loaded_at
    if _override is not None:
        return _override
    if force or _cache is None or time.monotonic() - _loaded_at > CACHE_SECONDS:
        fetched = _fetch()
        if fetched is not None:
            _cache, _loaded_at = fetched, time.monotonic()
    return _cache


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
    global _cache, _loaded_at
    _cache, _loaded_at = None, 0.0
