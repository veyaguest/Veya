"""נוסח מספריית הנוסחים → תבנית ה-WhatsApp שלו ב-Meta. מקור האמת היחיד להמרה.

החלטת הבעלים (2026-10-19): כל תבנית זהה אחד-לאחד לנוסח שבדף הנוסחים באתר
(``frontend/scripts/build-nuschim.mjs``), ולכל נוסח בספרייה (``MessageDefaultOption``)
יש תבנית אחת בשם קבוע. משתמשים בזה גם הקוד ששולח (``whatsapp_templates``) וגם
הכלי שיוצר את התבניות ב-Meta (``tools/meta-templates-mcp/library_sync.py``) —
כך ששם, סדר המשתנים והכפתורים לא יכולים להיפרד.

## ההמרה
- ``{{guest_name}}`` וחבריו → ``{{1}}``, ``{{2}}``… לפי סדר ההופעה הראשונה.
- שורת ``{{rsvp_link}}`` → כפתור קישור אישי (``/confirm/{{1}}``), ושורת התווית שלפניה
  ("לצפייה בהזמנה:") יוצאת מהגוף — כמו בדף. בהזמנה הכפתור "לצפייה בהזמנה" (אישור
  ההגעה נפתח רק מהיום הראשון של אישורי ההגעה), בשאר "אישור הגעה".
- ``{{navigation_link}}`` → כפתור "ניווט למקום" (Google Maps לכתובת האולם).
- הזמנה: גם גרסה עם תמונת ההזמנה כ-Header (``…_img``) — לא שולחים הזמנה בלי
  התמונה כשיש לאירוע תמונה (החלטה 2026-10-15, אושרה שוב 2026-10-20).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

EVENT_CODES = {"wedding": "wed", "henna": "henna", "bar_mitzvah": "barm", "bat_mitzvah": "batm",
               "brit": "brit", "brita": "brita", "business": "biz"}
MESSAGE_CODES = {"invitation": "inv", "rsvp_request": "rsvp", "reminder_1": "rem1",
                 "reminder_2": "rem2", "final_reminder": "rem3", "thank_you": "thx"}
#: סוגי ההודעה שהזוג בוחר להם נוסח מהספרייה (ושמופיעים בדף הנוסחים).
LIBRARY_TYPES = frozenset(MESSAGE_CODES)

LINK_BUTTON = "אישור הגעה"
INVITATION_LINK_BUTTON = "לצפייה בהזמנה"
NAVIGATION_BUTTON = "ניווט למקום"
IMAGE_SUFFIX = "_img"

LINK_TOKENS = ("rsvp_link", "navigation_link", "maps_link", "gift_link")
_LINK_RE = re.compile(r"\{\{(%s)\}\}" % "|".join(LINK_TOKENS))
_LABEL_RE = re.compile(r"^.{0,32}:\s*$")
_TOKEN_RE = re.compile(r"\{\{(\w+)\}\}")
_ENDS_VAR = re.compile(r"\{\{\s*\w+\s*\}\}\s*$")


@dataclass(frozen=True)
class LibraryTemplate:
    name: str
    body: str                          # הגוף עם {{1}}, {{2}}… — בדיוק מה שנשמר ב-Meta
    params: tuple[str, ...]            # המפתחות (communication_values) של {{1}}, {{2}}…
    link_button: Optional[str] = None  # טקסט כפתור הקישור האישי (כפתור ראשון), או None
    navigation_button: bool = False    # כפתור ניווט (כפתור שני)
    links: tuple[str, ...] = field(default_factory=tuple)

    @property
    def exact(self) -> bool:
        """Meta דוחה גוף שנגמר במשתנה — נוסח כזה לא יכול להיות תבנית זהה."""
        return not _ENDS_VAR.search(self.body)


def template_name(event_type: str, message_type: str, option_number: int) -> Optional[str]:
    ev, mt = EVENT_CODES.get(event_type), MESSAGE_CODES.get(message_type)
    if not ev or not mt:
        return None
    return f"veya_{ev}_{mt}_{int(option_number):02d}"


def split_links(content: str) -> tuple[str, list[str]]:
    """כמו ``render`` ב-build-nuschim.mjs: שורת קישור ושורת התווית שלפניה יוצאות."""
    links, kept = [], []
    for line in (content or "").split("\n"):
        found = _LINK_RE.findall(line)
        if found:
            links += found
            if kept and kept[-1].strip() and _LABEL_RE.match(kept[-1].strip()):
                kept.pop()
            rest = _LINK_RE.sub("", line).strip()
            if rest and not _LABEL_RE.match(rest):
                kept.append(rest)
            continue
        kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip(), links


def library_template(event_type: str, message_type: str, option_number: int,
                     content: str) -> Optional[LibraryTemplate]:
    """התבנית של נוסח מהספרייה, או ``None`` לסוג שאין לו תבניות ספרייה."""
    name = template_name(event_type, message_type, option_number)
    if name is None:
        return None
    body, links = split_links(content)
    order: list[str] = []
    for t in _TOKEN_RE.findall(body):
        if t not in order:
            order.append(t)
    positional = body
    for i, t in enumerate(order, 1):
        positional = positional.replace("{{%s}}" % t, "{{%d}}" % i)
    link_button = None
    if "rsvp_link" in links:
        link_button = INVITATION_LINK_BUTTON if message_type == "invitation" else LINK_BUTTON
    return LibraryTemplate(
        name=name, body=positional, params=tuple(order), link_button=link_button,
        navigation_button="navigation_link" in links, links=tuple(dict.fromkeys(links)),
    )


def image_variant(name: str) -> str:
    return name + IMAGE_SUFFIX
