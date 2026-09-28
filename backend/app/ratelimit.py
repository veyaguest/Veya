"""הגבלת קצב פשוטה מבוססת-זיכרון (per-IP), נגד ניחוש/הצפה.

מונה כשלונות פר-IP בחלון זמן נע. כשעוברים את הסף — חוסמים זמנית (429).
מיועד להתקנה בשרת יחיד; אם בעתיד נעבור לכמה תהליכים/שרתים, נחליף במנגנון
משותף (למשל Redis). מרוכז כאן כדי שכל הנתיבים הרגישים ישתמשו באותו דפוס.
"""
from __future__ import annotations

import time

from fastapi import HTTPException, Request

# כל המגבילים שנוצרו בתהליך — לבדיקות (איפוס בין בדיקה לבדיקה).
_REGISTRY: list["RateLimiter"] = []

# תקרת מפתחות במעקב לכל מגביל. בלי תקרה, כל IP חדש (או כתובת מייל חדשה)
# נשאר במילון לתמיד — הצפה ממיליוני כתובות הייתה מנפחת את הזיכרון עד קריסה.
MAX_TRACKED_KEYS = 10_000


def all_limiters() -> list["RateLimiter"]:
    return list(_REGISTRY)


class RateLimiter:
    """מגביל קצב לפי IP: עד ``max_hits`` אירועים בחלון של ``window`` שניות."""

    def __init__(self, *, max_hits: int, window: float, message: str) -> None:
        self.max_hits = max_hits
        self.window = window
        self.message = message
        self._hits: dict[str, list[float]] = {}
        self._alerted: dict[str, float] = {}
        _REGISTRY.append(self)

    def reset(self) -> None:
        self._hits.clear()
        self._alerted.clear()

    def _recent(self, ip: str, now: float) -> list[float]:
        hits = [t for t in self._hits.get(ip, []) if now - t < self.window]
        self._hits[ip] = hits
        return hits

    def check(self, ip: str) -> None:
        """זורק 429 אם ה-IP חרג מהסף. יש לקרוא לפני הפעולה המוגנת."""
        now = time.time()
        if len(self._recent(ip, now)) >= self.max_hits:
            # שורת יומן אחת לכל חסימה (לא לכל בקשה חסומה) — כדי שניסיון
            # ניחוש/הצפה ייראה ביומני השרת בלי להציף אותם.
            if now - self._alerted.get(ip, 0.0) >= self.window:
                self._alerted[ip] = now
                print(f"[veya:security] rate_limited key={_mask_key(ip)} limit={self.max_hits}/{int(self.window)}s", flush=True)
            raise HTTPException(status_code=429, detail=self.message)

    def record_fail(self, ip: str) -> None:
        """רושם כשלון (למשל סיסמה שגויה) — נספר לצורך החסימה."""
        now = time.time()
        if ip not in self._hits and len(self._hits) >= MAX_TRACKED_KEYS:
            self._prune(now)
        self._hits.setdefault(ip, []).append(now)

    def _prune(self, now: float) -> None:
        """מוחק מפתחות שאין להם ניסיון בחלון הנוכחי; אם עדיין מלא — את הישנים."""
        for key in [k for k, hits in self._hits.items() if not hits or now - hits[-1] >= self.window]:
            del self._hits[key]
            self._alerted.pop(key, None)
        if len(self._hits) >= MAX_TRACKED_KEYS:
            oldest = sorted(self._hits, key=lambda k: self._hits[k][-1])
            for key in oldest[: len(self._hits) - MAX_TRACKED_KEYS + 1]:
                del self._hits[key]
                self._alerted.pop(key, None)


def _mask_key(key: str) -> str:
    """מפתח ליומן בלי מידע אישי מלא: מייל מוסתר חלקית, IP/מזהה כפי שהם."""
    if "@" not in key:
        return key
    head, _, domain = key.rpartition("@")
    prefix, _, local = head.rpartition(":")
    return f"{prefix + ':' if prefix else ''}{local[:1]}***@{domain}"


def client_ip(request: Request) -> str:
    """כתובת ה-IP של הפונה (או 'unknown' אם לא ידועה)."""
    return request.client.host if request.client else "unknown"


# מגביל להתחברות/הרשמה: עד 10 ניסיונות כושלים ל-IP בדקה.
auth_limiter = RateLimiter(
    max_hits=10,
    window=60.0,
    message="יותר מדי ניסיונות התחברות. נסו שוב בעוד דקה.",
)

# מגביל ניתוח סקיצה ב-AI Vision: עד 15 קריאות לאירוע בשעה — כל קריאה עולה
# כסף (ai-guidelines.md), אז חוסמים הצפה/ניסיונות חוזרים בלי לחסום שימוש סביר.
# המפתח כאן הוא event_id (str), לא IP — משתמשים ב-record_fail על כל ניסיון
# (לא רק כשלונות) כדי לספור קריאות בפועל, לא רק שגיאות.
hall_sketch_limiter = RateLimiter(
    max_hits=15,
    window=3600.0,
    message="יותר מדי ניסיונות ניתוח סקיצה לאירוע הזה. נסו שוב בעוד שעה.",
)

# מיילים שהמערכת שולחת לבקשת אנונימי/משתמש (איפוס סיסמה, אימות מייל, הרשמה).
# כל שליחה עולה כסף אצל ספק המייל, וזו גם דרך להציף תיבה של מישהו אחר
# ("שכחתי סיסמה" על כתובת של קורבן, שוב ושוב). לכן נספרת **כל** בקשה, לא רק
# כשלונות — בנפרד לפי IP ולפי תיבת היעד. אותה תשובה בדיוק עד החסימה, כך
# שההגבלה לא חושפת אם הכתובת רשומה.
EMAIL_PER_TARGET_MAX = 3
email_ip_limiter = RateLimiter(
    max_hits=10,
    window=15 * 60.0,
    message="נשלחו הרבה בקשות מהכתובת הזו. נסו שוב בעוד רבע שעה.",
)
email_target_limiter = RateLimiter(
    max_hits=EMAIL_PER_TARGET_MAX,
    window=60 * 60.0,
    message="כבר שלחנו כמה מיילים לכתובת הזו. בדקו את תיבת הדואר (גם בספאם) או נסו שוב בעוד שעה.",
)


def limit_email_send(ip: str, target: str) -> None:
    """בודק ורושם בקשה לשליחת מייל — זורק 429 אם חרגה לפי IP או לפי יעד."""
    target_key = f"to:{(target or '').strip().lower()}"
    email_ip_limiter.check(ip)
    email_target_limiter.check(target_key)
    email_ip_limiter.record_fail(ip)
    email_target_limiter.record_fail(target_key)
