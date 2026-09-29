/**
 * גשר קטן בין העזרה למדריכים שכבר קיימים במסכים (help/guides.ts).
 *
 * העזרה לא נוגעת ב-state של HallPage: היא רק מבקשת "לפתוח את המדריך", והמסך
 * פותח אותו בעצמו. בקשה שנשלחה לפני שהמסך נטען (עוברים אליו מתוך העזרה)
 * נשמרת, והמסך מממש אותה כשהוא עולה.
 */
import type { GuideId } from './guides'

const EVENT = 'veya:help-open-guide'
const pending = new Set<GuideId>()

/** נקרא מהעזרה. */
export function requestGuide(id: GuideId): void {
  pending.add(id)
  window.dispatchEvent(new CustomEvent(EVENT, { detail: id }))
}

/** נקרא מהמסך שמחזיק את המדריך (useEffect). מחזיר פונקציית ניקוי. */
export function onGuideRequest(id: GuideId, open: () => void): () => void {
  if (pending.delete(id)) open()
  const handler = (e: Event) => {
    if ((e as CustomEvent<GuideId>).detail === id && pending.delete(id)) open()
  }
  window.addEventListener(EVENT, handler)
  return () => window.removeEventListener(EVENT, handler)
}
