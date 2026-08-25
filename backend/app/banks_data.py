"""רשימת הבנקים נוצרה אוטומטית מנתוני בנק ישראל — אין לערוך ידנית.

מקור: בנק ישראל דרך data.gov.il —
  · "סניפים לסליקה"                  https://data.gov.il/dataset/branches_for_payments
  · "רשימת תאגידים בנקאיים בישראל"   https://data.gov.il/dataset/375

נוצר: 2026-08-25 · לרענון: ``python3 tools/fetch_israeli_banks.py``
הכללים שלפיהם נבחרו הבנקים מתועדים בסקריפט עצמו.
"""
from __future__ import annotations

from typing import NamedTuple


class Bank(NamedTuple):
    code: int
    name: str
    legal_name: str


#: מקור הנתונים, לתצוגה ולתיעוד.
SOURCE = "בנק ישראל · data.gov.il"
SOURCE_UPDATED = "2026-08-25"

BANKS: tuple[Bank, ...] = (
    Bank(code=10, name='בנק לאומי לישראל', legal_name='בנק לאומי לישראל בע"מ'),
    Bank(code=12, name='בנק הפועלים', legal_name='בנק הפועלים בע"מ'),
    Bank(code=20, name='בנק מזרחי טפחות', legal_name='בנק מזרחי טפחות בע"מ'),
    Bank(code=31, name='בנק הבינלאומי הראשון לישראל', legal_name='בנק הבינלאומי הראשון לישראל בע"מ'),
    Bank(code=11, name='בנק דיסקונט לישראל', legal_name='בנק דיסקונט לישראל בע"מ'),
    Bank(code=17, name='בנק מרכנתיל דיסקונט', legal_name='בנק מרכנתיל דיסקונט בע"מ'),
    Bank(code=4, name='בנק יהב לעובדי המדינה', legal_name='בנק יהב לעובדי המדינה בע"מ'),
    Bank(code=14, name='בנק אוצר החייל', legal_name='בנק אוצר החייל בע"מ'),
    Bank(code=54, name='בנק ירושלים', legal_name='בנק ירושלים בע"מ'),
    Bank(code=46, name='בנק מסד', legal_name='בנק מסד בע"מ'),
    Bank(code=52, name='בנק פועלי אגודת ישראל', legal_name='בנק פועלי אגודת ישראל בע"מ'),
    Bank(code=26, name='יו-בנק', legal_name='יו-בנק בע"מ'),
    Bank(code=18, name='וואן זירו הבנק הדיגיטלי', legal_name='וואן זירו הבנק הדיגיטלי בע"מ'),
    Bank(code=22, name='Citibank', legal_name='Citibank'),
    Bank(code=9, name='בנק הדואר', legal_name='בנק הדואר'),
    Bank(code=23, name='HSBC', legal_name='HSBC'),
    Bank(code=39, name='SBI State Bank of India', legal_name='SBI State Bank of India'),
    Bank(code=3, name='בנק אש ישראל', legal_name='בנק אש ישראל בע"מ'),
)

BY_CODE: dict[int, Bank] = {b.code: b for b in BANKS}
