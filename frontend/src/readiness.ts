import type { DashboardStats } from './types'

// יעד ניווט של שלב במדד המוכנות — מסך קיים באפליקציה.
export type ReadinessPage = 'guests' | 'hall'

export interface ReadinessStep {
  key: 'guests' | 'groups' | 'preferences' | 'hall' | 'seating'
  label: string
  desc: string
  done: boolean
  progress: number // 0..1 — התקדמות השלב (לחישוב האחוז הכולל)
  page: ReadinessPage
  cta: string
}

export interface Readiness {
  percent: number
  steps: ReadinessStep[]
  nextIndex: number // השלב הראשון שעוד לא הושלם (-1 אם הכול מוכן)
  message: string
}

/**
 * מחשב את "מדד המוכנות להושבה" מתוך נתוני הדשבורד — ממליץ, לא חוסם.
 * חמישה שלבים, כל אחד תורם עד 20% (עם התקדמות חלקית בשלבים המדידים),
 * כדי לתת מספר חלק ומעודד ("מוכנים ל-85%").
 */
export function computeReadiness(stats: DashboardStats | null): Readiness {
  const total = stats?.total_guests ?? 0
  const other = (stats?.by_group?.['other'] as number | undefined) ?? 0
  const grouped = Math.max(0, total - other)
  const groupRatio = total > 0 ? grouped / total : 0
  const seatRatio = total > 0 ? Math.min(1, (stats?.seated_guests ?? 0) / total) : 0
  const hasPrefs =
    (stats?.guests_with_notes ?? 0) > 0 || (stats?.group_notes_count ?? 0) > 0

  const steps: ReadinessStep[] = [
    {
      key: 'guests',
      label: 'הוספת מוזמנים',
      desc: 'ייבוא או הדבקת רשימת המוזמנים',
      done: total > 0,
      progress: total > 0 ? 1 : 0,
      page: 'guests',
      cta: 'להוספת מוזמנים',
    },
    {
      key: 'groups',
      label: 'חלוקה לקבוצות',
      desc: 'שיוך משפחות וחברים לקבוצות',
      done: total > 0 && groupRatio >= 0.8,
      progress: groupRatio,
      page: 'guests',
      cta: 'לחלוקה לקבוצות',
    },
    {
      key: 'preferences',
      label: 'העדפות ישיבה',
      desc: 'מי לשבת לידו, ומי להרחיק',
      done: hasPrefs,
      progress: hasPrefs ? 1 : 0,
      page: 'guests',
      cta: 'להוספת העדפות',
    },
    {
      key: 'hall',
      label: 'מפת אולם',
      desc: 'הגדרת שולחנות ומיקומם',
      done: (stats?.tables_assigned ?? 0) > 0,
      progress: (stats?.tables_assigned ?? 0) > 0 ? 1 : 0,
      page: 'hall',
      cta: 'למפת האולם',
    },
    {
      key: 'seating',
      label: 'סידור הושבה',
      desc: 'יצירת ההושבה לפי הקשרים וההעדפות',
      done: (stats?.seated_guests ?? 0) > 0,
      progress: seatRatio,
      page: 'hall',
      cta: 'ליצירת ההושבה',
    },
  ]

  const percent = Math.round(
    (steps.reduce((s, st) => s + Math.min(1, Math.max(0, st.progress)), 0) /
      steps.length) *
      100,
  )
  const nextIndex = steps.findIndex((s) => !s.done)

  let message: string
  if (percent >= 100) message = 'הכול מוכן! אפשר לסדר את ההושבה בביטחון.'
  else if (percent >= 70) message = 'אתם ממש קרובים — עוד כמה צעדים וסיימנו.'
  else if (percent >= 30) message = 'התחלה מצוינת. בואו נמשיך צעד אחר צעד.'
  else message = 'נתחיל להכין את הכול יחד — זה פשוט יותר ממה שנדמה.'

  return { percent, steps, nextIndex, message }
}
