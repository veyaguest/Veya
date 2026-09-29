/**
 * ידע: מאזן האירוע + מתנות באשראי (HELP_CENTER_PLAN.md — שלב 2, חלק 2).
 *
 * עובדות (אומתו ב-2026-09-29):
 * - "מאזן האירוע": שלוש לשוניות — עלות {האירוע}, ספירת מתנות, סיכום {האירוע}
 *   (FinancePage TABS + strings.finance).
 * - העלות משוערת לפי אישורי ההגעה, עד שמזינים כמה הגיעו בפועל
 *   (strings.finance.estimatedCostNote).
 * - הכרטיס "כמה אורחים הגיעו בפועל?" מופיע **מיום האירוע** (או כשאין תאריך) —
 *   finance_service.counting_open: days_until_event <= 0.
 * - מתנות באשראי: בנויות אבל לא פעילות; פריט הניווט מופיע רק לאירוע זכאי
 *   (App.tsx, gift_eligibility). העזרה לא מבטיחה דבר מעבר לזה (gifts-copy §7).
 */
import type { HelpTopic } from '../types'
import { VERIFIED } from './shared'

const SOURCES = ['components/FinancePage.tsx', 'strings/he.ts']

export const FINANCE_TOPICS: readonly HelpTopic[] = [
  {
    id: 'finance.what',
    area: 'finance',
    title: 'מה יש במאזן האירוע?',
    aliases: ['מאזן', 'כספים', 'תקציב', 'הוצאות'],
    scopes: [{ scope: 'finance', weight: 60 }],
    answer: [
      'שלוש לשוניות: עלות {event}, {ui:finance.countingTitle} וסיכום {event}.',
      'בעלות רושמים הוצאות ותשלומים; בספירת המתנות — מעטפות ומתנות.',
    ],
    sources: SOURCES,
    verifiedAt: VERIFIED,
  },
  {
    id: 'finance.cost-per-person',
    area: 'finance',
    title: 'איך מחושבת העלות לאדם?',
    aliases: ['עלות לאדם', 'ממוצע', 'עלות משוערת', 'מנה'],
    scopes: [
      { scope: 'finance.cost', weight: 90 },
      { scope: 'finance', weight: 40 },
    ],
    answer: [
      'לפי מי שאישרו הגעה עכשיו — ולכן עד האירוע היא משוערת.',
      'אחרי האירוע, כשמזינים כמה הגיעו בפועל, העלות מתעדכנת לסופית.',
    ],
    sources: SOURCES,
    verifiedAt: VERIFIED,
  },
  {
    id: 'finance.attendance',
    area: 'finance',
    title: 'איפה מזינים כמה הגיעו בפועל?',
    aliases: ['הגיעו בפועל', 'כמה הגיעו', 'מספר סופי'],
    scopes: [
      { scope: 'finance.cost', weight: 70 },
      { scope: 'finance.summary', weight: 50 },
    ],
    answer: [],
    variants: [
      {
        when: { fact: 'event.days_to_event', op: '<=', value: 0 },
        answer: ['בלשונית "עלות {event}", בכרטיס "{ui:finance.attendanceTitle}".'],
      },
      {
        when: { fact: 'event.days_to_event', op: '>', value: 0 },
        answer: ['מיום האירוע יופיע בלשונית "עלות {event}" כרטיס "{ui:finance.attendanceTitle}".'],
      },
    ],
    sources: [...SOURCES, '../../backend/app/finance_service.py'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'gifts.unavailable',
    area: 'gifts',
    title: 'איפה מתנות באשראי?',
    aliases: ['מתנות באשראי', 'מתנה באשראי', 'כרטיס אשראי', 'מתנות'],
    // רק בחיפוש (בלי scopes): לא מציעים את זה סתם בבית של העזרה.
    scopes: [],
    when: { fact: 'gifts.eligible', op: '==', value: false },
    answer: ['השירות עדיין לא זמין לאירוע שלכם.'],
    sources: ['App.tsx', '../../backend/app/gift_eligibility.py'],
    verifiedAt: VERIFIED,
  },
]
