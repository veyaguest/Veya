import { useEffect, useState } from 'react'
import { shouldOfferInstall, snoozeInstallPrompt } from '../lib/pwa'
import { strings } from '../strings/he'
import './InstallPrompt.css'

/**
 * ההצעה להוסיף את VEYA למסך הבית של האייפון.
 *
 * למה זו קומפוננטה ולא באנר של הדפדפן: ב-iOS אין ``beforeinstallprompt``
 * ואין שום דרך תכנותית להתקין. ההתקנה היא פעולה ידנית של המשתמש בתפריט
 * השיתוף של Safari — ולכן כל מה שאנחנו יכולים (וצריכים) לעשות זה להראות
 * לו איפה זה נמצא, פעם אחת, יפה.
 *
 * מתי היא מופיעה: רק ב-Safari על אייפון, רק כשה-VEYA לא מותקנת, ורק אם
 * לא נסגרה לאחרונה (``shouldOfferInstall`` ב-lib/pwa.ts).
 * ומעל הכול — היא מרונדרת רק בתוך מעטפת האפליקציה, כלומר **אחרי**
 * שהמשתמש כבר נכנס וראה את האירוע שלו. להציע להתקין למישהו שעוד לא
 * התחבר זה לבקש התחייבות לפני שנתנו ערך.
 *
 * ההשהיה: 12 שניות אחרי הכניסה. לא כי זה "טריק המרה" — אלא כדי שההצעה
 * לא תקפוץ באמצע הטעינה ותחטוף מהמשתמש את המסך שהוא בא לראות.
 */
const APPEAR_DELAY_MS = 12000

export function InstallPrompt() {
  const [visible, setVisible] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [leaving, setLeaving] = useState(false)

  useEffect(() => {
    if (!shouldOfferInstall()) return
    const timer = window.setTimeout(() => setVisible(true), APPEAR_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [])

  if (!visible) return null

  // סגירה היא סגירה — **לא** סימון "הותקן". הדגל הקבוע נדלק רק כש-VEYA
  // באמת נפתחת כאפליקציה מותקנת (ראו lib/pwa.ts). ההבחנה הזו היא כל
  // ההבדל בין הצעה מכבדת לבין הצקה.
  // ``explained`` מבדיל בין "לא עכשיו" (שקט ל-30 יום) לבין סגירה אחרי
  // קריאת ההוראות (שקט לחצי שנה — כמעט תמיד מישהו שהתקין בפועל).
  function dismiss(explained = false) {
    setLeaving(true)
    snoozeInstallPrompt(explained)
    window.setTimeout(() => setVisible(false), 200)
  }

  return (
    <aside
      className={`install-card ${leaving ? 'is-leaving' : ''}`}
      dir="rtl"
      role="region"
      aria-label={strings.install.ariaLabel}
    >
      <button
        type="button"
        className="install-x"
        onClick={() => dismiss()}
        aria-label={strings.install.close}
      >
        ✕
      </button>

      <div className="install-head">
        <span className="install-mark" aria-hidden="true">
          V
        </span>
        <div className="install-copy">
          <h2 className="install-title">{strings.install.title}</h2>
          <p className="install-body">{strings.install.body}</p>
        </div>
      </div>

      {expanded && (
        <ol className="install-steps">
          <li>
            {strings.install.step1Prefix}{' '}
            <ShareGlyph /> {strings.install.step1Suffix}
          </li>
          <li>
            {strings.install.step2Prefix}{' '}
            <strong>{strings.install.step2Action}</strong>
          </li>
          <li>{strings.install.step3Prefix}</li>
        </ol>
      )}

      <div className="install-actions">
        {!expanded ? (
          <>
            <button type="button" className="install-cta" onClick={() => setExpanded(true)}>
              {strings.install.how}
            </button>
            <button type="button" className="install-ghost" onClick={() => dismiss()}>
              {strings.install.dismiss}
            </button>
          </>
        ) : (
          <button type="button" className="install-cta" onClick={() => dismiss(true)}>
            {strings.install.done}
          </button>
        )}
      </div>
    </aside>
  )
}

/** אייקון השיתוף של iOS — ריבוע עם חץ למעלה. מצויר ולא אמוג'י, כדי
 *  שייראה בדיוק כמו הכפתור שהמשתמש מחפש בסרגל של Safari. */
function ShareGlyph() {
  return (
    <svg
      className="install-share-glyph"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 3v12" />
      <path d="M8 7l4-4 4 4" />
      <path d="M6 12H5a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7a1 1 0 0 0-1-1h-1" />
    </svg>
  )
}
