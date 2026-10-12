"""בדיקת אינטגרציה אמיתית מול Meta — **כבויה תמיד**, אלא אם מפעילים אותה במפורש.

רצה רק כששני התנאים מתקיימים:
1. ``VEYA_META_INTEGRATION=1``, **וגם**
2. הקובץ הזה נקרא בשמו בפקודת pytest — הרצה רגילה של כל הבדיקות (``pytest`` /
   ``pytest tests``) מדלגת עליה גם כשהדגל מוגדר.

הבדיקות הרגילות רצות עם WhatsApp במצב ``mock`` ובלי טוקן (``tests/safe_env.py``),
ולכן הבדיקה הזו קוראת את משתני ה-WhatsApp מ-``backend/.env`` בעצמה, לזמן
הבדיקה בלבד, ומחזירה אחריה את הערכים הבטוחים. היא שולחת את תבנית
``hello_world`` של Meta לנמען הראשון ב-``WHATSAPP_TEST_RECIPIENTS``, דרך כלי
הבדיקה הידני (``whatsapp_meta.send_hello_world``) — כלומר רק אם: ``meta_test``,
לא production, עצירת חירום כבויה, נמען מורשה. לא נוגעת במסד ולא באף אורח.

הרצה:
    VEYA_META_INTEGRATION=1 venv/bin/python -m pytest -q tests/test_whatsapp_meta_integration.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BACKEND = Path(__file__).resolve().parent.parent
_THIS_FILE = Path(__file__).name

pytestmark = pytest.mark.skipif(
    os.getenv("VEYA_META_INTEGRATION") != "1",
    reason="בדיקה אמיתית מול Meta — רק עם VEYA_META_INTEGRATION=1",
)


def explicitly_requested(args) -> bool:
    """האם הקובץ הזה נקרא בשמו בפקודת pytest (ולא נאסף כחלק מתיקייה)."""
    return any(_THIS_FILE in str(arg) for arg in args)


@pytest.fixture
def real_whatsapp_env(request):
    if not explicitly_requested(request.config.args):
        pytest.skip("בדיקה אמיתית מול Meta — רק כשמריצים את הקובץ הזה בשמו")
    from dotenv import dotenv_values

    real = {
        k: v for k, v in dotenv_values(BACKEND / ".env").items()
        if k.startswith("WHATSAPP_") and v is not None
    }
    saved = {k: os.environ.get(k) for k in real}
    os.environ.update(real)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_hello_world_reaches_meta(real_whatsapp_env) -> None:  # noqa: ARG001
    from app import messaging, whatsapp_meta

    assert messaging.whatsapp_mode() == messaging.MODE_META_TEST, "נדרש WHATSAPP_MODE=meta_test"
    recipients = sorted(messaging.test_recipients())
    assert recipients, "WHATSAPP_TEST_RECIPIENTS ריק"
    check, result = whatsapp_meta.send_hello_world(recipients[0])
    assert check.ok, f"תנאי בטיחות לא מתקיימים: {check.reasons}"
    assert result.ok, f"Meta לא קיבלה את ההודעה (קוד {result.error_code})"
    assert result.provider_message_id.startswith("wamid.")
