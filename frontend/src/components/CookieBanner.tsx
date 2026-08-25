import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { getCookieConsent, setCookieConsent } from '../cookieConsent'
import { strings } from '../strings/he'

/**
 * שם המשתנה שהבאנר מפרסם לשאר המערכת: הגובה האמיתי שהוא תופס בתחתית המסך.
 *
 * הבאנר הוא ``position: fixed`` ולכן הוא **מרחף מעל** התוכן ולא דוחף אותו.
 * בלי המשתנה הזה אף פריסה לא יודעת שהוא שם — וכל מה שיושב בתחתית המסך
 * (הניווט התחתון במובייל, כפתור "שליחת אישור" בעמוד המוזמן) נעלם מתחתיו.
 * זו הייתה התקלה בפועל: מוזמן במובייל לא הצליח להגיע לכפתור אישור ההגעה.
 *
 * כל מי שצריך לפנות מקום בתחתית קורא ``var(--cookie-banner-height)``,
 * שערכו ``0px`` כשאין באנר — כך שברגע שהמוזמן בוחר, הפריסה חוזרת לעצמה
 * מעצמה, בלי שאף קומפוננטה תצטרך לדעת על כך.
 */
const HEIGHT_VAR = '--cookie-banner-height'

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
  const bannerRef = useRef<HTMLDivElement>(null)

  // מפרסמים את הגובה בפועל ל-CSS — לא מדידה חד-פעמית, כי הגובה זז:
  // מעבר ל"הגדרות מותאמות" מחליף את התוכן, סיבוב המכשיר משנה את מספר
  // שורות הטקסט, וטעינת הפונט מזיזה הכול בכמה פיקסלים.
  //
  // שני מקורות עדכון, כי הם מכסים דברים שונים:
  //   ResizeObserver — שינוי *תוכן* (טקסט אחר, פונט שנטען) בלי שהחלון זז.
  //   resize/orientationchange — שינוי *חלון* (סיבוב מכשיר, פתיחת מקלדת).
  // הם חופפים חלקית בכוונה: מספיק שאחד מהם יעבוד כדי שלא ייווצר "חור"
  // בתחתית המסך. ה-RO גם עטוף בבדיקת קיום — בלעדיו העמוד עדיין תקין.
  useLayoutEffect(() => {
    const el = bannerRef.current
    const root = document.documentElement
    if (dismissed || !el) {
      root.style.setProperty(HEIGHT_VAR, '0px')
      return
    }
    let frame = 0
    const publish = () => {
      root.style.setProperty(HEIGHT_VAR, `${Math.ceil(el.getBoundingClientRect().height)}px`)
    }
    // מודדים פעמיים בכוונה: מיד (הערך הנוכחי, נכון ברוב המקרים), ושוב
    // בפריים הבא אחרי שהדפדפן סיים לפרוס מחדש (שם התוצאה מדויקת).
    // המדידה המיידית היא לא ייתור — כשהלשונית ברקע הדפדפן מקפיא
    // requestAnimationFrame, וסיבוב מכשיר במצב הזה היה משאיר מידה ישנה.
    const publishNextFrame = () => {
      publish()
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(publish)
    }

    publish()
    window.addEventListener('resize', publishNextFrame)
    window.addEventListener('orientationchange', publishNextFrame)

    const observer =
      typeof ResizeObserver !== 'undefined' ? new ResizeObserver(publish) : null
    observer?.observe(el)

    return () => {
      cancelAnimationFrame(frame)
      window.removeEventListener('resize', publishNextFrame)
      window.removeEventListener('orientationchange', publishNextFrame)
      observer?.disconnect()
    }
  }, [dismissed, customizing])

  // ניקוי אחרון: אם הבאנר יורד מהמסך לגמרי, אסור שיישאר "חור" שמור בתחתית.
  useEffect(() => {
    return () => document.documentElement.style.setProperty(HEIGHT_VAR, '0px')
  }, [])

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
    <div
      className="cookie-banner"
      dir="rtl"
      role="region"
      aria-label={strings.legal.cookieAriaLabel}
      ref={bannerRef}
    >
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
