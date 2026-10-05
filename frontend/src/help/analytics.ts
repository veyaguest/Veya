/**
 * מדידת שימוש בעזרה — תור קטן בדפדפן (HELP_CENTER_PLAN.md §12, שלב 8).
 *
 * - **בלי זהות:** מזהה סשן אקראי חדש בכל פתיחה של העזרה (``startHelpSession``).
 *   השרת גם לא שומר אותו כמו שהוא — רק טביעה חד-כיוונית שלו.
 * - **בלי טקסט חופשי:** כל אירוע עובר ``cleanEvent`` (אוצר מילים סגור). אירוע
 *   לא תקין פשוט לא נשלח. טקסט החיפוש לא נשלח לעולם.
 * - **רק באישור:** נשלח רק אם המשתמש אישר "סטטיסטיקה ושיפור" בבאנר ה-Cookies
 *   אחרי שנאמר לו שזו מדידה של העזרה (``analyticsAllowed`` — אישור ישן מהתקופה
 *   שבה הסטטיסטיקה לא הייתה בשימוש לא נחשב), רק כשהעזרה פתוחה לאירוע, ולא
 *   בכניסה לתמיכה (``setHelpAnalyticsEnabled``).
 * - שליחה במנות (עד 20, או כל 5 שניות), וביציאה מהדף — עם ``keepalive``.
 *   כשל בשליחה נבלע בשקט: מדידה לעולם לא מפריעה לעזרה.
 */
import { postHelpEvents } from '../api'
import type { HelpEventsBatch } from '../api'
import { analyticsAllowed } from '../cookieConsent'
import { KB_VERSION, cleanEvent, newSessionId } from './analyticsSpec'
import type { HelpEventName, HelpEventProps } from './analyticsSpec'

const FLUSH_MS = 5000
const MAX_BATCH = 20

let enabled = false
let sessionId = ''
let screen = ''
let platform: 'desktop' | 'mobile' = 'desktop'
let queue: HelpEventsBatch['events'] = []
let timer: number | null = null
/** אירועים "פעם אחת בסשן" שכבר נרשמו (נמחק בכל פתיחה חדשה). */
let once = new Set<string>()

/** נקבע מ-HelpApp: העזרה פתוחה לאירוע, ולא בכניסה לתמיכה. */
export function setHelpAnalyticsEnabled(on: boolean): void {
  enabled = on
  if (!on) queue = []
}

/** המסך והמכשיר הנוכחיים — מצורפים לכל אירוע. */
export function setHelpAnalyticsContext(nextScreen: string, nextPlatform: 'desktop' | 'mobile'): void {
  screen = nextScreen
  platform = nextPlatform
}

/** פתיחה חדשה של העזרה → מזהה סשן אקראי חדש. */
export function startHelpSession(): void {
  flush()
  sessionId = newSessionId((n) => crypto.getRandomValues(new Uint8Array(n)))
  once = new Set()
}

export function track(name: HelpEventName, props: HelpEventProps = {}): void {
  if (!enabled || !sessionId || !screen || !analyticsAllowed()) return
  const clean = cleanEvent(name, props)
  if (!clean) return
  queue.push({ name, screen, props: clean })
  if (queue.length >= MAX_BATCH) flush()
  else if (timer === null) timer = window.setTimeout(() => flush(), FLUSH_MS)
}

/**
 * כמו ``track``, אבל לכל היותר פעם אחת בסשן לכל ``key`` — למשל "נושא נפתח"
 * או "בדיקה הגיעה לתוצאה", גם אם המסך נבנה שוב (חזרה אחורה, StrictMode).
 */
export function trackOnce(key: string, name: HelpEventName, props: HelpEventProps = {}): void {
  if (!sessionId || once.has(key)) return
  once.add(key)
  track(name, props)
}

function flush(keepalive = false): void {
  if (timer !== null) {
    window.clearTimeout(timer)
    timer = null
  }
  if (queue.length === 0 || !sessionId) return
  const events = queue
  queue = []
  void postHelpEvents({ session_id: sessionId, platform, kb_version: KB_VERSION, events }, keepalive).catch(() => {
    /* מדידה לא מפריעה לעזרה — כשל נבלע */
  })
}

if (typeof window !== 'undefined') {
  window.addEventListener('pagehide', () => flush(true))
}

/** לבדיקות בלבד. */
export function flushHelpAnalytics(): void {
  flush()
}
