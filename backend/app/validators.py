"""ולידציה ונרמול של מספרי טלפון ישראליים."""
import re


def normalize_israeli_phone(raw: str) -> str:
    """מחזיר מספר מנורמל (ספרות בלבד, מתחיל ב-0) או זורק ValueError.

    מקבל פורמטים נפוצים: 050-123-4567, +972 50 1234567, 0501234567.
    """
    digits = re.sub(r"\D", "", raw or "")

    # +972 / 972 -> 0
    if digits.startswith("972"):
        digits = "0" + digits[3:]

    if not digits.startswith("0"):
        raise ValueError(f"מספר טלפון לא תקין: '{raw}'")

    # נייד = 10 ספרות (05X), קווי = 9 ספרות (0X)
    if len(digits) not in (9, 10):
        raise ValueError(f"מספר טלפון לא תקין: '{raw}'")

    return digits
