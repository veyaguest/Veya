/**
 * העדפת המשתמש לגבי Cookies שאינם הכרחיים (סטטיסטיקה/שיפור). VEYA לא
 * מפעילה כיום שום כלי Analytics/Tracking בפועל (ראו legal/03-cookie-policy.md
 * §2.3) — אבל התשתית כאן קיימת מראש כדי שכל כלי עתידי מהסוג הזה יבדוק את
 * ההעדפה השמורה לפני טעינה, ולא יופעל בשקט על משתמשים קיימים.
 *
 * שימוש עתידי: לפני טעינת סקריפט אנליטיקס כלשהו, יש לבדוק
 * `getCookieConsent()?.analytics === true`.
 */
const STORAGE_KEY = 'veya_cookie_consent'

export interface CookieConsent {
  analytics: boolean
  decidedAt: string
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
  const value: CookieConsent = { analytics, decidedAt: new Date().toISOString() }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
}
