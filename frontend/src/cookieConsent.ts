/**
 * העדפת המשתמש לגבי Cookies שאינם הכרחיים (סטטיסטיקה ושיפור).
 *
 * כיום יש שימוש אחד בלבד בסטטיסטיקה: מדידה אנונימית של השימוש במסך "עזרה"
 * (help/analytics.ts, legal/03-cookie-policy.md §2.3). אין כלי Analytics של
 * צד שלישי. כל מדידה — עכשיו ובעתיד — בודקת `analyticsAllowed()` לפני שהיא
 * רושמת משהו.
 *
 * **אישור מחדש:** עד שלב 8 הבאנר אמר שהסטטיסטיקה "כרגע אינה בשימוש בפועל".
 * אישור שניתן אז לא מכסה את המדידה בעזרה — ולכן הוא לא נחשב, ומבקשים בחירה
 * מחדש פעם אחת (`needsAnalyticsReconsent`). "לא" ישן נשאר "לא", ושום דבר אחר
 * בבחירה לא נמחק.
 */
const STORAGE_KEY = 'veya_cookie_consent'

/**
 * על מה האישור לסטטיסטיקה חל. 1 = מדידה אנונימית של השימוש בעזרה.
 * אם השימוש ישתנה שוב — מעלים את המספר, וכל מי שאישר לפני כן יישאל מחדש.
 */
export const ANALYTICS_PURPOSE = 1

export interface CookieConsent {
  analytics: boolean
  decidedAt: string
  /** חסר = הבחירה נעשתה לפני שהסטטיסטיקה הייתה בשימוש (או בבאנר של דף הנחיתה). */
  analyticsPurpose?: number
}

export function getCookieConsent(): CookieConsent | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as CookieConsent) : null
  } catch {
    return null
  }
}

export function setCookieConsent(analytics: boolean): void {
  const value: CookieConsent = { analytics, decidedAt: new Date().toISOString(), analyticsPurpose: ANALYTICS_PURPOSE }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
}

/** מותר למדוד רק אם אישרו סטטיסטיקה אחרי שנאמר להם על מה היא חלה. */
export function analyticsAllowed(): boolean {
  const c = getCookieConsent()
  return c?.analytics === true && c.analyticsPurpose === ANALYTICS_PURPOSE
}

/** אישרו סטטיסטיקה לפני שהשימוש השתנה → שואלים פעם אחת מחדש. */
export function needsAnalyticsReconsent(): boolean {
  const c = getCookieConsent()
  return c?.analytics === true && c.analyticsPurpose !== ANALYTICS_PURPOSE
}
