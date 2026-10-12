"""הגדרות משותפות לבדיקות, לפני כל טעינה של ``app``:

- שעון קבוע (``tests/fixed_clock.py``).
- WhatsApp במצב ``mock`` ובלי טוקן אמיתי, גם אם ``backend/.env`` מוגדר אחרת
  (``tests/safe_env.py``).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests import safe_env  # noqa: E402

safe_env.apply()

from tests import fixed_clock  # noqa: E402

fixed_clock.install()
