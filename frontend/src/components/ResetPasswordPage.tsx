import { useState } from 'react'
import { resetPassword } from '../api'
import { setToken } from '../authStore'
import { Footer } from './Footer'
import type { User } from '../types'
import './VerifyEmailPage.css'
import './ResetPasswordPage.css'

/** אותו לוגו, באותו גודל בדיוק, כמו VerifyEmailPage — ראו ההערה שם. */
function VeyaLogo() {
  return <img className="verify-logo" src="/logo.png" alt="VEYA" width={152} height={133} />
}

/**
 * "בחירת סיסמה חדשה" — נפתח מהקישור שבמייל איפוס הסיסמה
 * (``/app/reset-password?token=...``, ראו App.tsx). אותו משטח כהה בדיוק
 * כמו מסך אימות המייל: שדות הסיסמה הם .auth-field הרגיל (כהה), לא כמו
 * שדה המייל הלבן של ForgotPasswordPage — כאן אין את אותה סיבה לניגוד.
 *
 * אחרי הצלחה מתחברים אוטומטית (כמו verify-email/confirm ו-change-password
 * בשרת) — אין טעם להכריח שלב "התחברות" נוסף כשהטוקן כבר הוכיח בעלות.
 */
export function ResetPasswordPage({
  token,
  onDone,
  onBack,
}: {
  token: string
  onDone: (user: User) => void
  onBack: () => void
}) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError('הסיסמאות לא תואמות')
      return
    }
    setBusy(true)
    try {
      const res = await resetPassword(token, password)
      setToken(res.access_token)
      setSuccess(true)
      // רגע קטן להראות את הודעת ההצלחה לפני שהאפליקציה ממשיכה (כמו VerifyEmailPage).
      window.setTimeout(() => onDone(res.user), 450)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לעדכן את הסיסמה')
      setBusy(false)
    }
  }

  return (
    <>
      <div className="verify-page" dir="rtl">
        <div className="verify-inner">
          <VeyaLogo />

          {success ? (
            <>
              <div className="verify-check" aria-hidden="true">✓</div>
              <h1 className="verify-title">הסיסמה עודכנה</h1>
              <p className="verify-sub">רגע, ממשיכים…</p>
            </>
          ) : (
            <>
              <h1 className="verify-title">בחירת סיסמה חדשה</h1>
              <p className="verify-sub">בחרו סיסמה חדשה לחשבון שלכם ב-VEYA.</p>

              {error && (
                <p className="auth-error verify-msg" role="alert">{error}</p>
              )}

              <form className="verify-form rp-form" onSubmit={submit}>
                <div className="auth-field">
                  <label htmlFor="rp-pass">סיסמה חדשה</label>
                  <input
                    id="rp-pass"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="לפחות 8 תווים, אות וספרה"
                    autoComplete="new-password"
                    required
                  />
                </div>
                <div className="auth-field">
                  <label htmlFor="rp-pass-confirm">אימות סיסמה</label>
                  <input
                    id="rp-pass-confirm"
                    type="password"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    placeholder="הקלידו שוב את הסיסמה"
                    autoComplete="new-password"
                    required
                  />
                </div>
                <button
                  type="submit"
                  className="auth-submit verify-submit"
                  disabled={busy}
                >
                  {busy ? 'מעדכנים…' : 'עדכון הסיסמה'}
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
