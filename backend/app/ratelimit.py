"""הגבלת קצב פשוטה מבוססת-זיכרון (per-IP), נגד ניחוש/הצפה.

מונה כשלונות פר-IP בחלון זמן נע. כשעוברים את הסף — חוסמים זמנית (429).
מיועד להתקנה בשרת יחיד; אם בעתיד נעבור לכמה תהליכים/שרתים, נחליף במנגנון
משותף (למשל Redis). מרוכז כאן כדי שכל הנתיבים הרגישים ישתמשו באותו דפוס.
"""
from __future__ import annotations

import time

from fastapi import HTTPException, Request


class RateLimiter:
    """מגביל קצב לפי IP: עד ``max_hits`` אירועים בחלון של ``window`` שניות."""

    def __init__(self, *, max_hits: int, window: float, message: str) -> None:
        self.max_hits = max_hits
        self.window = window
        self.message = message
        self._hits: dict[str, list[float]] = {}

    def _recent(self, ip: str, now: float) -> list[float]:
        hits = [t for t in self._hits.get(ip, []) if now - t < self.window]
        self._hits[ip] = hits
        return hits

    def check(self, ip: str) -> None:
        """זורק 429 אם ה-IP חרג מהסף. יש לקרוא לפני הפעולה המוגנת."""
        now = time.time()
        if len(self._recent(ip, now)) >= self.max_hits:
            raise HTTPException(status_code=429, detail=self.message)

    def record_fail(self, ip: str) -> None:
        """רושם כשלון (למשל סיסמה שגויה) — נספר לצורך החסימה."""
        self._hits.setdefault(ip, []).append(time.time())


def client_ip(request: Request) -> str:
    """כתובת ה-IP של הפונה (או 'unknown' אם לא ידועה)."""
    return request.client.host if request.client else "unknown"


# מגביל להתחברות/הרשמה: עד 10 ניסיונות כושלים ל-IP בדקה.
auth_limiter = RateLimiter(
    max_hits=10,
    window=60.0,
    message="יותר מדי ניסיונות התחברות. נסו שוב בעוד דקה.",
)
