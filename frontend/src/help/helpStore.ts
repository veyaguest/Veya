/**
 * האם חלונית העזרה פתוחה — מצב אחד, משותף לכפתור (בסרגל/בפס העליון) ולחלונית.
 *
 * מודול קטן ונפרד בכוונה: הכפתור יושב בחבילה הראשית, והחלונית נטענת רק
 * בפתיחה הראשונה (React.lazy). כך העזרה כמעט לא מוסיפה משקל לטעינת האפליקציה.
 */
import { useSyncExternalStore } from 'react'

let open = false
const listeners = new Set<() => void>()

function set(next: boolean): void {
  if (open === next) return
  open = next
  for (const fn of listeners) fn()
}

export const openHelp = (): void => set(true)
export const closeHelp = (): void => set(false)
export const toggleHelp = (): void => set(!open)

function subscribe(fn: () => void): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}

export function useHelpOpen(): boolean {
  return useSyncExternalStore(subscribe, () => open)
}

// ── האם העזרה פתוחה לאירוע הנוכחי (App.tsx קובע, מ-EventSummary.help_enabled) ──
// רכיבים קטנים במסכים (HelpErrorHint) צריכים לדעת את זה בלי לקבל props.
let enabled = false
const enabledListeners = new Set<() => void>()

export function setHelpEnabled(next: boolean): void {
  if (enabled === next) return
  enabled = next
  for (const fn of enabledListeners) fn()
}

export function useHelpEnabled(): boolean {
  return useSyncExternalStore(
    (fn) => {
      enabledListeners.add(fn)
      return () => {
        enabledListeners.delete(fn)
      }
    },
    () => enabled,
  )
}

// ── בקשה לפתוח את העזרה ישר על בדיקת תקלה (מ"צריכים עזרה עם זה?") ──
export interface HelpRequest {
  tree: string
  /** הרגע שבו נרשמה השגיאה שנלחצה — העץ ייבדק מולה בלבד. */
  errorAt: number
}
let request: HelpRequest | null = null
let requestVersion = 0
const requestListeners = new Set<() => void>()

export function openHelpFor(req: HelpRequest): void {
  request = req
  requestVersion++
  for (const fn of requestListeners) fn()
  set(true)
}

/** משתנה בכל בקשה חדשה — כך החלונית קולטת אותה גם כשהיא כבר פתוחה. */
export function useHelpRequestVersion(): number {
  return useSyncExternalStore(
    (fn) => {
      requestListeners.add(fn)
      return () => {
        requestListeners.delete(fn)
      }
    },
    () => requestVersion,
  )
}

export function takeHelpRequest(): HelpRequest | null {
  const r = request
  request = null
  return r
}
