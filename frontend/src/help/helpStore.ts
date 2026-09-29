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
