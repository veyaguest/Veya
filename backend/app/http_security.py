"""שכבת אבטחת HTTP של השרת — כתובת IP אמיתית, כותרות אבטחה ותיעוד API.

1. ``TrustedProxyMiddleware`` — ב-Render השרת יושב מאחורי proxy, ולכן
   ``request.client.host`` הוא כתובת ה-proxy ולא של המשתמש: כל הגבלות הקצב
   ("10 ניסיונות התחברות לדקה ל-IP") הופכות למונה אחד משותף לכל העולם —
   תוקף אחד חוסם את כולם, ויומן הכניסות רושם את כתובת ה-proxy. uvicorn לא
   קורא את X-Forwarded-For כשהפונה אינו localhost (``--forwarded-allow-ips``),
   ו-"*" היה מקבל את הערך השמאלי — שהלקוח עצמו יכול לזייף.
   לכן לוקחים את הערך ה-``hops``-י מימין: אותו ערך שה-proxy שלנו הוסיף, ולא
   משהו שהלקוח שלח. ``VEYA_TRUSTED_PROXY_HOPS`` (ברירת מחדל: 1 בייצור, 0 בפיתוח).

2. ``SecurityHeadersMiddleware`` — כותרות אבטחה על כל תשובה: nosniff, איסור
   הטמעה ב-iframe, בלי Referrer, HSTS בייצור. תשובות JSON מקבלות CSP שחוסם
   הכול; מדיה שהמשתמשים העלו (``/media``, ``/uploads``) מקבלת CSP ``sandbox``,
   כך שגם SVG/HTML שהגיע לשם לא מריץ סקריפט כשפותחים אותו ישירות.

3. ``docs_settings`` — דפי התיעוד האוטומטיים (/docs, /openapi.json) מפרטים
   את כל ~240 הנתיבים, כולל האדמין. בייצור הם כבויים.
"""
from __future__ import annotations

import ipaddress
import os

_JSON_CSP = b"default-src 'none'; frame-ancestors 'none'"
_MEDIA_CSP = b"default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; sandbox"
_MEDIA_PREFIXES = ("/media/", "/uploads/")


def is_production() -> bool:
    return os.getenv("VEYA_ENV", "").strip().lower() == "production"


def trusted_proxy_hops() -> int:
    raw = os.getenv("VEYA_TRUSTED_PROXY_HOPS", "").strip()
    if raw.isdigit():
        return int(raw)
    return 1 if is_production() else 0


def docs_settings(*, production: bool) -> dict:
    if production:
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {}


def _valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


class TrustedProxyMiddleware:
    """מחליף את ``scope["client"]`` בכתובת שה-proxy המהימן דיווח עליה."""

    def __init__(self, app, hops: int) -> None:
        self.app = app
        self.hops = hops

    async def __call__(self, scope, receive, send):
        if self.hops > 0 and scope.get("type") in ("http", "websocket"):
            values = [v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"x-forwarded-for"]
            hosts = [h.strip() for h in ",".join(values).split(",") if h.strip()]
            if len(hosts) >= self.hops:
                host = hosts[-self.hops]
                if _valid_ip(host):
                    port = (scope.get("client") or (None, 0))[1]
                    scope = dict(scope)
                    scope["client"] = (host, port)
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    """מוסיף כותרות אבטחה לכל תשובה (בלי לדרוס כותרת שה-endpoint כבר קבע)."""

    def __init__(self, app, *, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        is_media = scope.get("path", "").startswith(_MEDIA_PREFIXES)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}

                def add(name: bytes, value: bytes) -> None:
                    if name not in present:
                        headers.append((name, value))
                        present.add(name)

                add(b"x-content-type-options", b"nosniff")
                add(b"x-frame-options", b"DENY")
                add(b"referrer-policy", b"no-referrer")
                if self.hsts:
                    add(b"strict-transport-security", b"max-age=31536000; includeSubDomains")
                content_type = next((v for k, v in headers if k.lower() == b"content-type"), b"")
                if is_media:
                    add(b"content-security-policy", _MEDIA_CSP)
                elif content_type.startswith(b"application/json"):
                    add(b"content-security-policy", _JSON_CSP)
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
