import { useState } from 'react'
import { updateProfile } from '../api'
import type { User } from '../types'
import { Footer } from './Footer'
import './JoinEventPage.css'

/**
 * "השלמת פרטים" — מוצג למשתמש קיים שחסרים לו שם מלא או טלפון, לפני שהוא
 * יכול ליצור אירוע.
 *
 * למי זה קורה: מי שנרשם לפני ששני השדות הפכו לחובה, ומי שנכנס דרך גוגל
 * (שם אין שדה טלפון בכלל). הם לא נשברים ולא מאבדים כלום — רק מתבקשים
 * להשלים פעם אחת. מי שנרשם היום ממילא מילא הכול בהרשמה ולא יראה את המסך.
 */
export function CompleteProfilePage({
  user,
  onUpdated,
  onLogout,
}: {
  user: User
  onUpdated: (user: User) => void
  onLogout: () => void
}) {
  const [displayName, setDisplayName] = useState(user.display_name || '')
  const [phone, setPhone] = useState(user.phone || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      onUpdated(await updateProfile(displayName, phone))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לשמור את הפרטים')
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

          <h1 className="join-title">עוד שני פרטים ואפשר להתחיל</h1>
          <p className="join-text">
            כדי שנוכל ללוות אתכם באירוע, נשמח לדעת איך קוראים לכם ואיך אפשר
            להשיג אתכם.
          </p>

          {error && <p className="join-error">{error}</p>}

          <form onSubmit={submit}>
            <div className="join-field">
              <label htmlFor="cp-name">שם מלא</label>
              <input
                id="cp-name"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder="דנה כהן"
                autoComplete="name"
                required
              />
            </div>
            <div className="join-field">
              <label htmlFor="cp-phone">טלפון</label>
              <input
                id="cp-phone"
                type="tel"
                dir="ltr"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="050-123-4567"
                autoComplete="tel"
                required
              />
            </div>
            <button type="submit" className="join-btn join-btn-primary" disabled={busy}>
              {busy ? 'שומר…' : 'שמירה והמשך'}
            </button>
          </form>

          <button type="button" className="join-linkbtn" onClick={onLogout}>
            יציאה מהחשבון
          </button>
        </div>
      </div>
      <Footer />
    </>
  )
}
