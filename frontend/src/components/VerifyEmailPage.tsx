import { useState } from 'react'
import { changeUnverifiedEmail, resendVerificationEmail } from '../api'
import type { User } from '../types'
import { Footer } from './Footer'
import './JoinEventPage.css'

/**
 * "אימות כתובת המייל" — המסך שמוצג אחרי ההרשמה, לפני יצירת האירוע.
 *
 * הזרימה: הרשמה → אימות מייל → חשבון מאומת → יצירת אירוע. המסך חוסם את
 * ההמשך, אבל אף פעם לא מוביל למבוי סתום: אפשר לשלוח את המייל מחדש, ואפשר
 * לתקן כתובת שהוקלדה בטעות (וזה המקרה הנפוץ באמת).
 */
export function VerifyEmailPage({
  user,
  onUpdated,
  onRefresh,
  onLogout,
}: {
  user: User
  onUpdated: (user: User) => void
  /** בודק מחדש מול השרת אם הכתובת כבר אומתה (אחרי לחיצה על הקישור). */
  onRefresh: () => void
  onLogout: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [email, setEmail] = useState(user.email)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function resend() {
    setError(null)
    setNote(null)
    setBusy(true)
    try {
      await resendVerificationEmail()
      setNote(`שלחנו שוב קישור אימות ל-${user.email}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לשלוח את המייל')
    } finally {
      setBusy(false)
    }
  }

  async function saveEmail(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setNote(null)
    setBusy(true)
    try {
      const updated = await changeUnverifiedEmail(email)
      onUpdated(updated)
      setEditing(false)
      setNote(`שלחנו קישור אימות ל-${updated.email}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לעדכן את הכתובת')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="join-page" dir="rtl">
        <div className="join-card">
          <div className="join-logo" dir="ltr" aria-label="VEYA">
            VEYA
          </div>

          <h1 className="join-title">אימות כתובת המייל</h1>
          <p className="join-text">
            שלחנו קישור אימות ל-
            <span dir="ltr" className="join-email">{user.email}</span>.
            <br />
            פתחו את המייל ולחצו על הקישור כדי להמשיך.
          </p>

          {error && <p className="join-error">{error}</p>}
          {note && <p className="join-note">{note}</p>}

          {!editing ? (
            <>
              <button
                type="button"
                className="join-btn join-btn-primary"
                onClick={onRefresh}
                disabled={busy}
              >
                כבר אימתתי — להמשיך
              </button>
              <button
                type="button"
                className="join-btn join-btn-secondary"
                onClick={resend}
                disabled={busy}
              >
                {busy ? 'שולח…' : 'שליחת הקישור מחדש'}
              </button>
              <button
                type="button"
                className="join-linkbtn"
                onClick={() => {
                  setEditing(true)
                  setNote(null)
                  setError(null)
                }}
              >
                הכתובת שגויה? אפשר לשנות אותה
              </button>
            </>
          ) : (
            <form onSubmit={saveEmail}>
              <div className="join-field">
                <label htmlFor="verify-email">כתובת המייל שלכם</label>
                <input
                  id="verify-email"
                  type="email"
                  dir="ltr"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="email"
                  required
                />
              </div>
              <button
                type="submit"
                className="join-btn join-btn-primary"
                disabled={busy}
              >
                {busy ? 'שומר…' : 'שמירה ושליחת אימות'}
              </button>
              <button
                type="button"
                className="join-btn join-btn-secondary"
                onClick={() => {
                  setEditing(false)
                  setEmail(user.email)
                }}
                disabled={busy}
              >
                ביטול
              </button>
            </form>
          )}

          <button type="button" className="join-linkbtn" onClick={onLogout}>
            יציאה מהחשבון
          </button>
        </div>
      </div>
      <Footer />
    </>
  )
}
