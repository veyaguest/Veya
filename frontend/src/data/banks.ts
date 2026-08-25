/* רשימת הבנקים נוצרה אוטומטית מנתוני בנק ישראל — אין לערוך ידנית.
 *
 * מקור: בנק ישראל דרך data.gov.il —
 *   · "סניפים לסליקה"                https://data.gov.il/dataset/branches_for_payments
 *   · "רשימת תאגידים בנקאיים בישראל" https://data.gov.il/dataset/375
 *
 * נוצר: 2026-08-25 · לרענון: `python3 tools/fetch_israeli_banks.py`
 * הכללים שלפיהם נבחרו הבנקים מתועדים בסקריפט עצמו.
 */

export type Bank = {
  /** קוד הבנק כפי שבנק ישראל מגדיר אותו — 12 = הפועלים, 10 = לאומי. */
  code: number
  /** שם לתצוגה, בלי סיומת התאגיד. */
  name: string
  /** השם המשפטי המלא, כפי שמופיע במרשם. */
  legalName: string
}

/** מקור הנתונים — מוצג למשתמש מתחת לבורר הבנקים. */
export const BANKS_SOURCE = 'בנק ישראל'
export const BANKS_UPDATED = '2026-08-25'

/** מסודר לפי מספר הסניפים בפועל: הבנקים הגדולים בראש. */
export const BANKS: readonly Bank[] = [
  { code: 10, name: "בנק לאומי לישראל", legalName: "בנק לאומי לישראל בע\"מ" },
  { code: 12, name: "בנק הפועלים", legalName: "בנק הפועלים בע\"מ" },
  { code: 20, name: "בנק מזרחי טפחות", legalName: "בנק מזרחי טפחות בע\"מ" },
  { code: 31, name: "בנק הבינלאומי הראשון לישראל", legalName: "בנק הבינלאומי הראשון לישראל בע\"מ" },
  { code: 11, name: "בנק דיסקונט לישראל", legalName: "בנק דיסקונט לישראל בע\"מ" },
  { code: 17, name: "בנק מרכנתיל דיסקונט", legalName: "בנק מרכנתיל דיסקונט בע\"מ" },
  { code: 4, name: "בנק יהב לעובדי המדינה", legalName: "בנק יהב לעובדי המדינה בע\"מ" },
  { code: 14, name: "בנק אוצר החייל", legalName: "בנק אוצר החייל בע\"מ" },
  { code: 54, name: "בנק ירושלים", legalName: "בנק ירושלים בע\"מ" },
  { code: 46, name: "בנק מסד", legalName: "בנק מסד בע\"מ" },
  { code: 52, name: "בנק פועלי אגודת ישראל", legalName: "בנק פועלי אגודת ישראל בע\"מ" },
  { code: 26, name: "יו-בנק", legalName: "יו-בנק בע\"מ" },
  { code: 18, name: "וואן זירו הבנק הדיגיטלי", legalName: "וואן זירו הבנק הדיגיטלי בע\"מ" },
  { code: 22, name: "Citibank", legalName: "Citibank" },
  { code: 9, name: "בנק הדואר", legalName: "בנק הדואר" },
  { code: 23, name: "HSBC", legalName: "HSBC" },
  { code: 39, name: "SBI State Bank of India", legalName: "SBI State Bank of India" },
  { code: 3, name: "בנק אש ישראל", legalName: "בנק אש ישראל בע\"מ" },
]

export const BANK_BY_CODE: ReadonlyMap<number, Bank> = new Map(BANKS.map((b) => [b.code, b]))
