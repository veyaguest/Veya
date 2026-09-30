/**
 * אילו שגיאות העזרה **מזהה** — ולכן רק לידן מופיע "צריכים עזרה עם זה?".
 * HELP_CENTER_PLAN.md שלב 5.
 *
 * שגיאה מזוהה = נתיב שיש לו עץ תקלות, **וגם** אחד מאלה:
 *  - ההודעה מכילה ניסוח שהעץ יודע לזהות (למשל "לא זוהו עמודות"), או
 *  - אין תשובה בכלל מהשרת (status 0), והעץ יודע לטפל בזה ("אין חיבור").
 * שגיאה אחרת (למשל "משהו השתבש" כללי) — **לא** מזוהה, ולא מוצעת לה עזרה:
 * אין לנו מה לומר עליה בלי לנחש.
 *
 * הרשימה קטנה ויושבת בחבילה הראשית (בלי לטעון את כל בסיס הידע). בדיקה
 * (helpErrors.test.ts) מוודאת שהיא **זהה** למה שעצי התקלות בבסיס הידע מזהים.
 */
import { recentErrors, redactMessage, succeededSince } from './errorBus'
import type { ApiEvent } from './errorBus'

/** שגיאה נחשבת "עכשיו" עד 5 דקות — כמו ב-engine/topics.ts. */
export const ERROR_WINDOW_MS = 5 * 60 * 1000

export interface ErrorHelpDef {
  tree: string
  /** "שיטה נתיב", כמו ב-errorBus: ``'POST /guests'``. */
  routes: readonly string[]
  /** קטעי ניסוח שהעץ מזהה בהודעה. */
  known: readonly string[]
  /** העץ יודע לטפל ב"אין תשובה מהשרת" (status 0). */
  offline: boolean
}

export const ERROR_HELP: readonly ErrorHelpDef[] = [
  {
    tree: 'guest-save-failed',
    routes: ['POST /guests', 'PATCH /guests/{id}'],
    known: ['לא תקין', 'שם מלא', 'כמות אנשים'],
    offline: true,
  },
  {
    tree: 'import-failed',
    routes: [
      'POST /guests/import/preview',
      'POST /guests/import/paste',
      'POST /guests/import/commit',
    ],
    known: ['לא זוהו עמודות', 'גדול מדי', 'ארוכה מדי', 'שורות', 'פורמט', 'ריק', 'לא הצלחנו לקרוא'],
    offline: true,
  },
  {
    tree: 'event-save-failed',
    routes: ['PATCH /event'],
    known: ['נעול לעריכה', 'מועד סגירת הרשימה כבר נקבע', 'כבר הייתה סגורה', 'שעת השליחה חייבת'],
    offline: true,
  },
  {
    tree: 'seating-failed',
    routes: ['POST /seating/generate'],
    known: ['אין מוזמנים לשיבוץ', 'אין מוזמנים שאישרו הגעה', 'חבורה גדולה', 'הרזרבה גדולה מדי'],
    offline: true,
  },
]

/** השגיאות האחרונות שעוד "פתוחות" — בלי אלה שכבר הצליחה אחריהן כתיבה לאותו נתיב. */
export function openErrors(): ApiEvent[] {
  return recentErrors().filter((e) => !succeededSince(e))
}

/** העץ שמזהה את השגיאה הזו, או ``null`` אם היא לא מזוהה. */
export function knownErrorTree(e: ApiEvent): string | null {
  if (e.ok) return null
  for (const def of ERROR_HELP) {
    if (!def.routes.includes(`${e.method} ${e.path}`)) continue
    if (e.status === 0 && def.offline) return def.tree
    if (e.message && def.known.some((k) => e.message!.includes(k))) return def.tree
  }
  return null
}

/**
 * השגיאה **שמוצגת עכשיו** על המסך, אם היא מזוהה: ההודעה שהרכיב מציג
 * חייבת להיות זהה (אחרי ניקוי) להודעה של השגיאה האחרונה עם אותו ניסוח,
 * מ-5 הדקות האחרונות, שעוד לא "תוקנה" (לא הצליחה אחריה כתיבה לאותו נתיב).
 * הודעה ישנה/אחרת/כללית/שכבר תוקנה → ``null``.
 */
export function currentKnownError(
  displayed: string,
  now: number = Date.now(),
): { tree: string; at: number } | null {
  const clean = redactMessage(displayed)
  const errors = recentErrors()
  for (let i = errors.length - 1; i >= 0; i--) {
    const e = errors[i]
    if (now - e.at > ERROR_WINDOW_MS) continue
    if (e.message !== clean) continue
    if (succeededSince(e)) return null
    const tree = knownErrorTree(e)
    return tree ? { tree, at: e.at } : null
  }
  return null
}

/** השגיאה המזוהה האחרונה (לבית של העזרה), מ-5 הדקות האחרונות, שעוד לא תוקנה. */
export function latestKnownError(now: number = Date.now()): { tree: string; at: number } | null {
  const errors = recentErrors()
  for (let i = errors.length - 1; i >= 0; i--) {
    const e = errors[i]
    if (now - e.at > ERROR_WINDOW_MS) return null
    if (succeededSince(e)) continue
    const tree = knownErrorTree(e)
    if (tree) return { tree, at: e.at }
  }
  return null
}

/** השגיאה עצמה לפי הרגע שבו נרשמה — כדי שעץ ייבדק מול השגיאה שנלחצה, לא מול אחרת. */
export function errorAt(at: number, now: number = Date.now()): ApiEvent | null {
  if (now - at > ERROR_WINDOW_MS) return null
  return recentErrors().find((e) => e.at === at) ?? null
}
