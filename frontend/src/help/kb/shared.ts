/**
 * קבועים משותפים לכל קבצי הידע.
 */
import type { Condition } from '../types'

/** מתי אומת התוכן מול הקוד. */
export const VERIFIED = '2026-09-29'

/**
 * רק מי שמנהל את האירוע (בעלים / בן-בת זוג). מפיק/אולם לא מקבלים פעולות
 * והדרכות בשלב הזה (החלטת המייסד 2026-09-29).
 */
export const MANAGER = { fact: 'user.role', op: 'in', value: ['owner', 'partner'] } as const satisfies Condition

/**
 * מוצג ליד כל נושא/הדרכה/עץ שמסומנים ``sendsMessages`` כשהעובדה
 * ``messaging.mode`` היא ``mock``. הניסוח של המייסד (2026-09-29), מילה במילה.
 */
export const MOCK_NOTICE =
  'כרגע WhatsApp עדיין במצב הדגמה, ולכן ההודעות לא נשלחות בפועל. אנחנו עובדים על הפעלה של השליחה.'

/** "מסלול אישורי ההגעה פועל או יפעל" — יש תאריך ונבחר מועד סגירה. */
export const TRACK_PHASES_ACTIVE = ['before', 'running', 'ended'] as const
