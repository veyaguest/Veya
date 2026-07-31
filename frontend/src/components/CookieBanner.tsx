import { useState } from 'react'
import { getCookieConsent, setCookieConsent } from '../cookieConsent'
import { strings } from '../strings/he'

/**
 * באנר הסכמת Cookies — מוצג בביקור ראשון (כל עוד אין העדפה שמורה), עם שלוש
 * אפשרויות ברורות לפי legal/03-cookie-policy.md §3: קבל הכל / דחה לא-הכרחיים /
 * הגדרות מותאמות. VEYA לא מפעילה כיום Cookies שאינם הכרחיים בפועל — הבאנר
 * קיים כדי לתעד את הבחירה מראש לקראת כלים עתידיים (ראו cookieConsent.ts),
 * ולתת גישה ברורה למדיניות.
 */
export function CookieBanner() {
  const [dismissed, setDismissed] = useState(() => getCookieConsent() != null)
  const [customizing, setCustomizing] = useState(false)
  const [analyticsChecked, setAnalyticsChecked] = useState(false)

  if (dismissed) return null

  function acceptAll() {
    setCookieConsent(true)
    setDismissed(true)
  }
  function rejectNonEssential() {
    setCookieConsent(false)
    setDismissed(true)
  }
  function saveCustom() {
    setCookieConsent(analyticsChecked)
    setDismissed(true)
  }

  return (
    <div className="cookie-banner" dir="rtl" role="region" aria-label={strings.legal.cookieAriaLabel}>
      <div className="cookie-banner-inner">
        {!customizing ? (
          <>
            <p className="cookie-banner-text">
              {strings.legal.cookieBody}
              {' '}
              <a href="/legal/cookies.html" target="_blank" rel="noopener noreferrer">
                {strings.legal.cookiePolicyLink}
              </a>
              .
            </p>
            <div className="cookie-banner-actions">
              <button type="button" className="btn-primary" onClick={acceptAll}>
                {strings.legal.cookieAcceptAll}
              </button>
              <button type="button" className="btn-ghost" onClick={rejectNonEssential}>
                {strings.legal.cookieRejectNonEssential}
              </button>
              <button type="button" className="btn-link" onClick={() => setCustomizing(true)}>
                {strings.legal.cookieCustomize}
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="cookie-banner-custom-row">
              <label className="auth-consent-row">
                <input type="checkbox" checked disabled />
                <span>{strings.legal.cookieEssentialLabel}</span>
              </label>
              <label className="auth-consent-row">
                <input
                  type="checkbox"
                  checked={analyticsChecked}
                  onChange={(e) => setAnalyticsChecked(e.target.checked)}
                />
                <span>{strings.legal.cookieAnalyticsLabel}</span>
              </label>
            </div>
            <div className="cookie-banner-actions">
              <button type="button" className="btn-primary" onClick={saveCustom}>
                {strings.legal.cookieSavePrefs}
              </button>
              <button type="button" className="btn-ghost" onClick={() => setCustomizing(false)}>
                {strings.legal.cookieBack}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
