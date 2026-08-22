import { useState } from 'react'
import { forgotPassword } from '../api'
import { Footer } from './Footer'
import './VerifyEmailPage.css'
import './ForgotPasswordPage.css'

/** אותו לוגו, באותו גודל בדיוק, כמו VerifyEmailPage — ראו ההערה שם. */
function VeyaLogo() {
  return <img className="verify-logo" src="/logo.png" alt="VEYA" width={152} height={133} />
}

/**
 * "שכחתי סיסמה" — ממשיך ישירות את מסך אימות המייל: אותו משטח כהה
 * (.verify-page/.verify-inner מ-VerifyEmailPage.css), אותו לוגו, אותה
 * כותרת/כפתור. ההבדל היחיד מכוון: שדה המייל עצמו לבן/שנהב (ForgotPasswordPage.css)
 * — ניגוד מודע לרקע הכהה, כדי שיהיה ברור וקל להקליד בו כתובת מייל.
 *
 * אבטחה: התגובה מהשרת זהה תמיד, בלי קשר אם הכתובת קיימת (email
 * enumeration) — ולכן מסך ההצלחה כאן לא אומר "שלחנו" אלא "אם קיימת כתובת".
 */
export function ForgotPasswordPage({ onBack }: { onBack: () => void }) {
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await forgotPassword(email)
      setSent(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לשלוח את הקישור')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="verify-page" dir="rtl">
        <div className="verify-inner">
          <VeyaLogo />

          {sent ? (
            <>
              <div className="verify-check" aria-hidden="true">✓</div>
              <h1 className="verify-title">בדקו את תיבת הדואר</h1>
              <p className="verify-sub">
                אם קיימת כתובת עם החשבון הזה, שלחנו אליה קישור לאיפוס הסיסמה.
              </p>
              <div className="verify-secondary">
                <button type="button" className="auth-link-btn" onClick={onBack}>
                  חזרה להתחברות
                </button>
              </div>
            </>
          ) : (
            <>
              <h1 className="verify-title">איפוס הסיסמה</h1>
              <p className="verify-sub">
                הזינו את כתובת המייל שאיתה נרשמתם, ונשלח אליכם קישור לאיפוס הסיסמה.
              </p>

              {error && (
                <p className="auth-error verify-msg" role="alert">{error}</p>
              )}

              <form className="verify-form" onSubmit={submit}>
                <div className="fp-field">
                  <label htmlFor="fp-email">כתובת המייל</label>
                  <input
                    id="fp-email"
                    type="email"
                    dir="ltr"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    autoComplete="email"
                    required
                  />
                </div>
                <button
                  type="submit"
                  className="auth-submit verify-submit"
                  disabled={busy}
                >
                  {busy ? 'שולחים…' : 'שלחו לי קישור לאיפוס'}
                </button>
              </form>

              <div className="verify-secondary">
                <button type="button" className="auth-link-btn" onClick={onBack}>
                  חזרה להתחברות
                </button>
              </div>
            </>
          )}
        </div>
      </div>
      <Footer />
    </>
  )
}
