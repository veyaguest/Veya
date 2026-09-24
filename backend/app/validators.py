"""ולידציה ונרמול של מספרי טלפון ישראליים."""
import re


def _bad_phone(raw: str) -> str:
    """הודעה שאומרת מה לא בסדר ואיך מתקנים — בלי להאשים."""
    return (
        f"נראה שהמספר {raw.strip()} לא תקין. מספר נייד מתחיל ב-05 ויש בו 10 ספרות, "
        "למשל 050-1234567."
    )


def normalize_israeli_phone(raw: str) -> str:
    """מחזיר מספר מנורמל (ספרות בלבד, מתחיל ב-0) או זורק ValueError.

    מקבל פורמטים נפוצים: 050-123-4567, +972 50 1234567, 0501234567.
    """
    digits = re.sub(r"\D", "", raw or "")

    # +972 / 972 -> 0
    if digits.startswith("972"):
        digits = "0" + digits[3:]

    if not digits.startswith("0"):
        raise ValueError(_bad_phone(raw))

    # נייד = 10 ספרות (05X), קווי = 9 ספרות (0X)
    if len(digits) not in (9, 10):
        raise ValueError(_bad_phone(raw))

    return digits
