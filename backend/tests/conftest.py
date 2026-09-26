"""הגדרות משותפות לבדיקות: שעון קבוע (``tests/fixed_clock.py``) לפני כל טעינה של ``app``."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests import fixed_clock  # noqa: E402

fixed_clock.install()
