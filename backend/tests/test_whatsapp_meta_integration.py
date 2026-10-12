"""בדיקת אינטגרציה אמיתית מול Meta — **מדולגת תמיד**, אלא אם מפעילים אותה במפורש.

שולחת את תבנית ``hello_world`` של Meta לנמען הראשון ב-``WHATSAPP_TEST_RECIPIENTS``
— דרך אותו כלי בדיקה ידני (``whatsapp_meta.send_hello_world``), עם כל תנאי
הבטיחות שלו: ``meta_test`` בלבד, לא production, עצירת חירום כבויה, נמען מורשה.
לא נוגעת במסד ולא באף אורח.

הרצה (רק עם פרטי חשבון הבדיקה של Meta ב-``backend/.env``):
    VEYA_META_INTEGRATION=1 venv/bin/python -m pytest -q tests/test_whatsapp_meta_integration.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

pytestmark = pytest.mark.skipif(
    os.getenv("VEYA_META_INTEGRATION") != "1",
    reason="בדיקה אמיתית מול Meta — רק עם VEYA_META_INTEGRATION=1",
)


def test_hello_world_reaches_meta() -> None:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    from app import messaging, whatsapp_meta

    recipients = sorted(messaging.test_recipients())
    assert recipients, "WHATSAPP_TEST_RECIPIENTS ריק"
    check, result = whatsapp_meta.send_hello_world(recipients[0])
    assert check.ok, f"תנאי בטיחות לא מתקיימים: {check.reasons}"
    assert result.ok, f"Meta לא קיבלה את ההודעה: {result.detail}"
    assert result.provider_message_id.startswith("wamid.")
