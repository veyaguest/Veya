import { useState } from 'react'
import { getCookieConsent, setCookieConsent } from '../cookieConsent'

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
    <div className="cookie-banner" dir="rtl" role="region" aria-label="הסכמת Cookies">
      <div className="cookie-banner-inner">
        {!customizing ? (
          <>
            <p className="cookie-banner-text">
              אנחנו משתמשים בעוגיות הכרחיות לתפעול השירות (כמו שמירת החיבור
              שלך). עוגיות נוספות (סטטיסטיקה/שיפור) יופעלו רק באישורך המפורש.
              פרטים ב
              <a href="/legal/cookies.html" target="_blank" rel="noopener noreferrer">
                מדיניות ה-Cookies
              </a>
              .
            </p>
            <div className="cookie-banner-actions">
              <button type="button" className="btn-primary" onClick={acceptAll}>
                קבל הכל
              </button>
              <button type="button" className="btn-ghost" onClick={rejectNonEssential}>
                דחה לא-הכרחיים
              </button>
              <button type="button" className="btn-link" onClick={() => setCustomizing(true)}>
                הגדרות מותאמות
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="cookie-banner-custom-row">
              <label className="auth-consent-row">
                <input type="checkbox" checked disabled />
                <span>עוגיות הכרחיות (חובה לתפעול השירות)</span>
              </label>
              <label className="auth-consent-row">
                <input
                  type="checkbox"
                  checked={analyticsChecked}
                  onChange={(e) => setAnalyticsChecked(e.target.checked)}
                />
                <span>עוגיות סטטיסטיקה/שיפור (כרגע אינן בשימוש בפועל)</span>
              </label>
            </div>
            <div className="cookie-banner-actions">
              <button type="button" className="btn-primary" onClick={saveCustom}>
                שמירת ההעדפות
              </button>
              <button type="button" className="btn-ghost" onClick={() => setCustomizing(false)}>
                חזרה
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
