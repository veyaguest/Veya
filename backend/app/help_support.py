"""פנייה לצוות VEYA מתוך "עזרה" (HELP_CENTER_PLAN.md §10, שלב 7).

שלושה דברים, וכולם כאן כדי שה-router יישאר דק:

1. **תמונת מצב בפורמט קבוע** (``build_context``): רשימה לבנה של שדות. מה
   שהדפדפן שולח עובר אימות (``SupportRequestCreate`` ב-routers/help.py, בלי
   שדות נוספים), הודעות השגיאה מנוקות **שוב** כאן (גם אם הדפדפן כבר ניקה —
   לא סומכים על הלקוח), והעובדות של המסך מחושבות מחדש **בשרת** —
   ספירות ודגלים בלבד, בדיוק מה ש-``/help/context`` מחזיר.
2. **דחיפות** (``urgency_for``): נקבעת בשרת — עד יומיים לאירוע = ``high``
   (החלטת המייסד 2026-09-29: הצוות בולט יותר קרוב לאירוע).
3. **התראה לצוות** (``notify_team``): מייל לכתובת ב-``VEYA_SUPPORT_EMAIL``.
   הכתובת **לעולם** לא בקוד. אין כתובת → לא נשלח כלום (ומודפסת שורת יומן).
   במייל: מספר הפנייה, דחיפות, נושא וקישור למסך האדמין — **בלי** הטקסט
   שנכתב ובלי פרטי הלקוח (פחות מידע אישי בתיבות דואר; הכול במסך האדמין).
"""
from __future__ import annotations

import html
import os
import re
from typing import Optional

from sqlalchemy.orm import Session

from app import emailer, guest_journey, help_context, models

URGENT_DAYS = 2
STATUSES = ("new", "in_progress", "resolved")
STATUS_LABELS = {"new": "התקבלה", "in_progress": "בטיפול", "resolved": "טופלה"}


def redact_message(message: str) -> str:
    """אותו ניקוי של ``frontend/src/help/errorBus.ts::redactMessage``: מה
    שאחרי נקודתיים (שמות), מה שהוקלד בשדה הטלפון, מיילים ורצפי ספרות."""
    m = message or ""
    colon = m.find(":")
    if colon >= 0:
        m = m[:colon]
    m = re.sub(r"המספר\s+.*?\s+לא תקין", "המספר # לא תקין", m)
    m = re.sub(r"\S+@\S+", "@", m)
    m = re.sub(r"\+?\d[\d\s\-()]*\d", "#", m)
    return m.strip()[:160]


def days_to_event(event: Optional[models.Event]) -> Optional[int]:
    return guest_journey.days_until_event(event) if event is not None else None


def urgency_for(event: Optional[models.Event]) -> str:
    days = days_to_event(event)
    return "high" if days is not None and 0 <= days <= URGENT_DAYS else "normal"


def build_context(
    db: Session,
    event: models.Event,
    user: models.User,
    *,
    screen: Optional[str],
    topic_id: Optional[str],
    tree_id: Optional[str],
    outcome: Optional[str],
    tour_flow: Optional[str],
    recent_errors: list[dict],
    platform: str,
) -> dict:
    """תמונת המצב שנשמרת עם הפנייה — רק השדות האלה, תמיד."""
    role = "owner" if event.owner_id == user.id else "partner"
    facts = help_context.screen_facts(db, event, screen) if screen in help_context.SCREENS else {}
    return {
        "event_type": event.event_type,
        "role": role,
        "screen": screen,
        "topic_id": topic_id,
        "tree_id": tree_id,
        "outcome": outcome,
        "tour_flow": tour_flow,
        "days_to_event": days_to_event(event),
        "platform": platform,
        "recent_errors": [
            {
                "method": e["method"],
                # מזהה שנשאר בנתיב (/guests/123) — כמו pathTemplate בדפדפן.
                "path": re.sub(r"/\d+(?=/|$)", "/{id}", e["path"]),
                "status": e["status"],
                **({"message": redact_message(e["message"])} if e.get("message") else {}),
            }
            for e in recent_errors[:5]
        ],
        "facts": facts,
    }


def support_email() -> str:
    """כתובת ההתראות של הצוות — מהסביבה בלבד (החלטת המייסד 2026-09-29)."""
    return (os.getenv("VEYA_SUPPORT_EMAIL", "") or "").strip()


def notify_team(request: models.SupportRequest) -> Optional[emailer.SendResult]:
    """מייל קצר לצוות על פנייה חדשה. לא זורק חריגה; בלי כתובת — ``None``."""
    to = support_email()
    if not to:
        print(f"[veya:support] פנייה #{request.id} נשמרה — VEYA_SUPPORT_EMAIL לא מוגדר, לא נשלחה התראה", flush=True)
        return None
    urgent = request.urgency == "high"
    ctx = request.context or {}
    about = request.tree_id or request.topic_id or "כללי"
    days = ctx.get("days_to_event")
    link = f"{emailer.public_base_url()}/app#/admin/support/{request.id}"
    subject = f"{'דחוף — ' if urgent else ''}פנייה חדשה לצוות VEYA #{request.id}"
    lines = [
        f"פנייה #{request.id}{' · דחוף' if urgent else ''}",
        f"נושא: {about}",
        *( [f"ימים עד האירוע: {days}"] if isinstance(days, int) else [] ),
    ]
    body_html = (
        "".join(f"<p style=\"margin:0 0 8px\">{html.escape(line)}</p>" for line in lines)
        + f"<p style=\"margin:16px 0 0\"><a href=\"{html.escape(link)}\">לפנייה במסך הניהול</a></p>"
    )
    text = "\n".join(lines) + f"\n\nלפנייה במסך הניהול: {link}"
    return emailer.send_email(to=to, subject=subject, html_body=body_html, text_body=text)
