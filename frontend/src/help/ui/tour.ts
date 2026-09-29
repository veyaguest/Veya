/**
 * עזרי DOM להדרכה ("תראו לי") — איתור יעד, בדיקת נראות, סימון.
 *
 * כלל ברזל (החלטת המייסד 2026-09-29): ההדרכה **לא לוחצת, לא ממלאת ולא
 * שולחת**. הקוד כאן רק מוצא אלמנט, בודק שהוא באמת גלוי, ומסמן אותו.
 */
import type { TargetId } from '../targets'

/**
 * גלוי באמת — לא רק קיים ב-DOM. באשף ההזמנה הראשונה כל השלבים קיימים
 * בדף, והשלבים שלא הגיעו אליהם מוסתרים עם ``hidden`` (נמצא בשלב 1). יעד
 * כזה לא נחשב.
 */
export function isVisible(el: HTMLElement): boolean {
  if (!el.isConnected) return false
  if (el.closest('[hidden]')) return false
  const style = window.getComputedStyle(el)
  if (style.display === 'none' || style.visibility === 'hidden') return false
  const r = el.getBoundingClientRect()
  return r.width > 0 && r.height > 0
}

/** היעד הגלוי הראשון עם ה-``data-help`` הזה, או ``null``. */
export function findVisibleTarget(id: TargetId): HTMLElement | null {
  const els = document.querySelectorAll<HTMLElement>(`[data-help="${id}"]`)
  for (const el of Array.from(els)) if (isVisible(el)) return el
  return null
}

export const HIGHLIGHT_CLASS = 'help-target-active'

/** כמה זמן מחכים שיעד יופיע (אחרי מעבר מסך / פתיחת תפריט) לפני שעוצרים. */
export const FIND_TIMEOUT_MS = 4000

export function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** שדה קלט (שכדאי להעביר אליו פוקוס כדי שאפשר יהיה להקליד מיד). */
export function isTextField(el: HTMLElement): el is HTMLInputElement | HTMLTextAreaElement {
  return el instanceof HTMLTextAreaElement || (el instanceof HTMLInputElement && el.type !== 'checkbox')
}
