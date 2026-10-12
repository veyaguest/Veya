"""הבדיקות האוטומטיות תמיד רצות עם WhatsApp במצב ``mock`` ובלי טוקן אמיתי —
גם כש-``backend/.env`` (או הטרמינל) מוגדרים ל-``meta_test`` עם טוקן אמיתי.

ראו ``tests/safe_env.py``. כאן נבדק:
1. בתוך הרצת pytest: כל משתני ה-WhatsApp בטוחים, והמערכת עצמה רואה ``mock``.
2. קובץ ``.env`` עם ``meta_test`` וטוקן — לא דורס (כמו ``app/database.py``).
3. הרצת pytest בתהליך נפרד, כשהטרמינל מגדיר ``meta_test`` וטוקן — עדיין ``mock``.
4. בדיקת האינטגרציה האמיתית לא רצה בהרצה רגילה, גם עם ``VEYA_META_INTEGRATION=1``.

אף בדיקה כאן לא מדפיסה ערך של משתנה.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BACKEND = Path(__file__).resolve().parent.parent


def _assert_safe() -> None:
    from app import messaging, whatsapp_meta
    from tests.safe_env import WHATSAPP_SAFE_ENV

    for key, safe in WHATSAPP_SAFE_ENV.items():
        assert os.environ.get(key) == safe, f"{key} אינו בערך הבטוח"
    assert messaging.whatsapp_mode() == messaging.MODE_MOCK
    assert isinstance(messaging.get_provider(), (messaging.MockProvider, messaging.StoppedProvider))
    assert messaging.test_recipients() == frozenset()
    assert whatsapp_meta.load_config().missing() == ["WHATSAPP_ACCESS_TOKEN", "WHATSAPP_PHONE_NUMBER_ID"]


def test_regular_tests_run_in_mock_without_real_token() -> None:
    import app.database  # noqa: F401 — ה-load_dotenv של המערכת כבר רץ

    _assert_safe()
    # ואם בקובץ האמיתי יש טוקן — הוא לא הגיע לסביבת הבדיקות.
    env_file = BACKEND / ".env"
    if env_file.exists():
        from dotenv import dotenv_values

        real = dotenv_values(env_file)
        for key in ("WHATSAPP_ACCESS_TOKEN", "WHATSAPP_TOKEN", "WHATSAPP_APP_SECRET"):
            if real.get(key):
                assert os.environ.get(key) != real[key], f"{key} מהקובץ האמיתי דלף לבדיקות"
    print("✓ 1: בבדיקות — mock, בלי טוקן, בלי נמענים, גם אחרי טעינת .env של המערכת")


def test_env_file_with_meta_test_cannot_override() -> None:
    from dotenv import load_dotenv

    with tempfile.TemporaryDirectory() as tmp:
        hostile = Path(tmp) / ".env"
        hostile.write_text(
            "WHATSAPP_MODE=meta_test\n"
            "WHATSAPP_ACCESS_TOKEN=EAAfake-hostile-token-0000000000\n"
            "WHATSAPP_PHONE_NUMBER_ID=1234567890\n"
            "WHATSAPP_TEST_RECIPIENTS=0501112233\n"
            "WHATSAPP_APP_SECRET=hostile-secret\n",
            encoding="utf-8",
        )
        load_dotenv(hostile, override=False)  # בדיוק כמו app/database.py
    _assert_safe()
    print("✓ 2: קובץ .env עם meta_test וטוקן — לא דורס את ההגדרות הבטוחות")


def test_shell_env_with_meta_test_is_overridden_in_fresh_pytest() -> None:
    """pytest חדש, שהטרמינל שלו מוגדר ל-meta_test עם טוקן — conftest דורס הכול
    לפני ש-``app`` נטען, והבדיקה 1 עוברת בתוכו."""
    if os.environ.get("_VEYA_ISOLATION_CHILD") == "1":
        return  # לא להריץ את עצמנו שוב בתוך תהליך-הבת
    env = dict(os.environ)
    env.update({
        "WHATSAPP_MODE": "meta_test",
        "WHATSAPP_ACCESS_TOKEN": "EAAfake-shell-token-0000000000",
        "WHATSAPP_PHONE_NUMBER_ID": "1234567890",
        "WHATSAPP_TEST_RECIPIENTS": "0501112233",
        "_VEYA_ISOLATION_CHILD": "1",
    })
    env.pop("VEYA_META_INTEGRATION", None)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_test_env_isolation.py::test_regular_tests_run_in_mock_without_real_token"],
        cwd=str(BACKEND), env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout[-2000:]
    assert "1 passed" in proc.stdout
    assert "EAAfake-shell-token" not in proc.stdout + proc.stderr
    print("✓ 3: pytest חדש עם meta_test וטוקן בטרמינל — עדיין mock")


def test_integration_runs_only_when_requested_by_name() -> None:
    from tests.test_whatsapp_meta_integration import explicitly_requested

    for args in ([], ["tests"], ["tests/"], ["."], [str(BACKEND / "tests")],
                 ["tests/test_whatsapp_safety.py"], ["-k", "hello_world"]):
        assert not explicitly_requested(args), args
    for args in (["tests/test_whatsapp_meta_integration.py"],
                 ["tests/test_whatsapp_meta_integration.py::test_hello_world_reaches_meta"],
                 [str(BACKEND / "tests" / "test_whatsapp_meta_integration.py")]):
        assert explicitly_requested(args), args
    print("✓ 4: בדיקת האינטגרציה — רק כשהקובץ נקרא בשמו (ועם VEYA_META_INTEGRATION=1)")


if __name__ == "__main__":
    from tests import safe_env

    safe_env.apply()
    test_regular_tests_run_in_mock_without_real_token()
    test_env_file_with_meta_test_cannot_override()
    test_shell_env_with_meta_test_is_overridden_in_fresh_pytest()
    test_integration_runs_only_when_requested_by_name()
    print("\n=== בידוד סביבת הבדיקות — עבר ===")
