/**
 * מתי מציעים את צוות VEYA (HELP_CENTER_PLAN.md §10 + החלטות המייסד 2026-09-29).
 *
 * הסדר קבוע: תשובה מהירה → "תראו לי" → בדיקה → ניסיון נוסף → צוות VEYA.
 * הצוות **לא** מוצע לפני שניסינו לפתור. אחרי ניסיון אחד לפחות הוא זמין
 * בשקט; והוא בולט יותר רק כשזה באמת דחוף — האירוע בעוד יומיים או פחות, או
 * שהבדיקה מצאה שהבעיה אצלנו ולא אצל המשתמש. גם אז הוא לא הדרך הראשונה.
 */
import type { Resolution } from '../types'
import type { Facts } from '../facts'

export interface HelpAttempts {
  /** כמה פעמים נלחץ "עדיין לא" על תשובה/הדרכה/בדיקה. */
  notHelped: number
  /** איך נגמרה ההדרכה האחרונה. */
  tour: 'none' | 'completed' | 'abandoned' | 'failed'
  /** תוצאת עץ התקלות האחרון, אם הגיע לתוצאה. */
  diagnosis: Resolution | 'cant-check' | null
}

export const NO_ATTEMPTS: HelpAttempts = { notHelped: 0, tour: 'none', diagnosis: null }

/** יומיים או פחות לאירוע = דחוף. */
export const URGENT_DAYS = 2

export type TeamOption = 'hidden' | 'available' | 'prominent'

export function teamOption(a: HelpAttempts, facts: Facts): TeamOption {
  const tried =
    a.notHelped > 0 ||
    a.tour === 'abandoned' ||
    a.tour === 'failed' ||
    a.diagnosis !== null
  if (!tried) return 'hidden'
  const days = facts['event.days_to_event']
  const eventSoon = typeof days === 'number' && days >= 0 && days <= URGENT_DAYS
  const ourSide = a.diagnosis === 'veya_side'
  return eventSoon || ourSide ? 'prominent' : 'available'
}
