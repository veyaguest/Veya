"""כותרת בהודעה ("לניווט:") שכל מה שמתחתיה נמחק — נמחקת גם היא.

בלי זה, אירוע בלי כתובת שלח למוזמן "לניווט:" ואחריו כלום. כותרת שיש
מתחתיה לפחות שורה אחת שנשארה — נשארת.

הרצה: ``venv/bin/pytest -q tests/test_render_orphan_label.py``
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.messaging import render_automation_template  # noqa: E402

BODY = (
    "היי {{first_name}}\n\n"
    "לאישור הגעה:\n{{confirmation_link}}\n\n"
    "לניווט:\n{{navigation_link}}\n\n"
    "כמה פרטים:\n📍 {{venue_name}}\n⏰ {{event_time}}"
)


def _render(**kw) -> str:
    base = dict(guest_name="דנה לוי", groom="יואב", bride="מיכל", venue="", link="http://x/c")
    base.update(kw)
    return render_automation_template(BODY, **base)


def test_label_without_content_is_removed() -> None:
    text = _render(time="20:00")
    assert "לניווט" not in text, text
    assert "לאישור הגעה:" in text and "http://x/c" in text
    assert "כמה פרטים:\n⏰ 20:00" in text, "כותרת עם שורה שנשארה — נשארת"


def test_label_with_content_stays() -> None:
    text = _render(venue="אולם", venue_address="הרצל 1 תל אביב")
    assert "לניווט:\nhttps://" in text, text
    assert "כמה פרטים:\n📍 אולם" in text
