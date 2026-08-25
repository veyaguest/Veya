/**
 * מצב פרטי קבלת המתנות — **סיווג אחד, לכל המסכים**.
 *
 * החשבון עובר שתי בדיקות בלתי תלויות (VEYA וחברת הסליקה), ולכן "מה
 * המצב?" היא תמיד שאלה על *צירוף* של שני סטטוסים ולא על אחד מהם. הפונקציה
 * כאן עושה את הצירוף פעם אחת, כדי שמסך המתנות ותמונת המצב לא יגיעו לשתי
 * מסקנות שונות מאותם נתונים.
 *
 * **זה סיווג לתצוגה, לא הרשאה.** מי שמחליט אם מותר להחזיר סכומים הוא
 * השרת בלבד (``payout_status.is_fully_verified``); כאן רק נקבע איזה משפט
 * הזוג רואה. שינוי בקוד הזה לא חושף שקל אחד.
 */
import type { PayoutAccount } from './types'

export type PayoutStage =
  /** אין פרטים, או שנשמרו ולא הוגשו — בשני המקרים הכדור אצל הזוג. */
  | 'missing'
  /** הוגש, VEYA בודקת. */
  | 'pending'
  /** VEYA אישרה, חברת הסליקה עוד לא. */
  | 'providerPending'
  /** VEYA דחתה — נדרש תיקון. */
  | 'rejected'
  /** חברת הסליקה דחתה. */
  | 'providerRejected'
  /** שתי הבדיקות אושרו. */
  | 'verified'

export function payoutStage(account: PayoutAccount | null): PayoutStage {
  // אין שורה, או שיש פרטים שמעולם לא הוגשו: מבחינת הזוג שניהם "לא
  // הושלם" — פרטים ששוכבים בטיוטה אינם שונים מפרטים שלא הוזנו.
  if (!account || !account.configured || account.status === 'missing') return 'missing'

  // דחייה קודמת לכל השאר: היא המצב היחיד שדורש פעולה, וצריכה להופיע גם
  // כשהמסלול השני כבר אושר.
  if (account.veya_status === 'rejected') return 'rejected'
  if (account.provider_status === 'rejected') return 'providerRejected'

  // ``fully_verified`` מגיע מהשרת ואינו מחושב כאן מחדש — הוא מקור האמת.
  if (account.fully_verified) return 'verified'
  if (account.veya_status === 'approved') return 'providerPending'
  return 'pending'
}

/** האם השלב הזה דורש פעולה מהזוג (ולא רק המתנה). */
export function needsOwnerAction(stage: PayoutStage): boolean {
  return stage === 'missing' || stage === 'rejected' || stage === 'providerRejected'
}

/**
 * מה שבעלי האירוע רואים — **ארבעה מצבים, לא שישה.**
 *
 * ``PayoutStage`` מבחין בין "VEYA עוד לא בדקה" ל"VEYA אישרה והספק לא",
 * ובין דחייה שלנו לדחייה של הספק. ההבחנות האלה נכונות ונחוצות — בשרת
 * ובמסך האדמין. הן פשוט **לא עניינם של בעלי האירוע**: לזוג לא משנה מי
 * מבין שני הגורמים עדיין בודק, או מי מהם ביקש תיקון. משנה לו רק מה המצב
 * ומה נדרש ממנו.
 *
 * לכן שישה שלבים מתקפלים לארבעה מצבים, וכל אזכור של "VEYA" או "חברת
 * הסליקה" יורד מהמסך של הזוג.
 */
export type PayoutDisplayStatus =
  /** חסרים פרטים — הכדור אצל הזוג. */
  | 'missing'
  /** הפרטים בבדיקה — אין מה לעשות. כולל המצב שבו בדיקה אחת כבר הושלמה. */
  | 'review'
  /** הפרטים אושרו — הכול מוכן. */
  | 'approved'
  /** נדרש תיקון — לא משנה מי ביקש אותו. */
  | 'fix'

export function payoutDisplayStatus(stage: PayoutStage): PayoutDisplayStatus {
  switch (stage) {
    case 'missing':
      return 'missing'
    case 'rejected':
    case 'providerRejected':
      return 'fix'
    case 'verified':
      return 'approved'
    case 'pending':
    case 'providerPending':
      return 'review'
  }
}
