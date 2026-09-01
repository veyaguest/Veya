import { useEffect, useState } from 'react'
import { getAccountOverview, invitePartner } from '../api'
import './PartnerCta.css'

/** דגל דפדפן: הזוג בחר "לא עכשיו". מסתיר את הכרטיס לצמיתות במכשיר הזה —
 * זו הצעה, לא מצב אירוע, ואין סיבה להמשיך להציע אחרי שאמרו לא. */
const DISMISSED_KEY = 'veya_partner_cta_dismissed'

function readDismissed(): boolean {
  try {
    return localStorage.getItem(DISMISSED_KEY) === '1'
  } catch {
    return false
  }
}

/**
 * "מנהלים את האירוע יחד?" — כרטיס בדשבורד למי שעדיין לא צירף/ה את בן/בת הזוג.
 *
 * מוצג **רק** כשבאמת אין שותף/ה, אין הזמנה פתוחה, והזוג לא ביקש להסתיר.
 * ברגע שנשלחה הזמנה או שמישהו הצטרף, הכרטיס נעלם מעצמו — כדי שלא יהפוך
 * לרעש קבוע בדשבורד. זו התזכורת למי שדילג על ההזמנה בסיום יצירת האירוע.
 */
export function PartnerCta() {
  const [visible, setVisible] = useState(false)
  const [dismissed, setDismissed] = useState(readDismissed)
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  function dismiss() {
    try {
      localStorage.setItem(DISMISSED_KEY, '1')
    } catch {
      /* מצב פרטי / אחסון חסום — לפחות נסתיר לשארית הביקור */
    }
    setDismissed(true)
  }

  useEffect(() => {
    let alive = true
    getAccountOverview()
      .then((data) => {
        if (!alive) return
        setVisible(data.can_invite_partner && !data.pending_invite)
      })
      .catch(() => {
        /* הכרטיס הוא תוספת, לא ליבה — בכישלון פשוט לא מציגים אותו. */
      })
    return () => {
      alive = false
    }
  }, [])

  async function send(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const invite = await invitePartner(email)
      setSentTo(invite.invited_email)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לשלוח את ההזמנה')
    } finally {
      setBusy(false)
    }
  }

  if (!visible || dismissed) return null

  if (sentTo) {
    return (
      <div className="pcta pcta-done" role="status">
        <span className="pcta-check" aria-hidden="true">✓</span>
        <p className="pcta-done-text">
          שלחנו הזמנה ל-<span dir="ltr">{sentTo}</span>. ברגע שהיא תאושר, תנהלו
          את האירוע יחד.
        </p>
      </div>
    )
  }

  return (
    <div className="pcta">
      <div className="pcta-main">
        <h3 className="pcta-title">מנהלים את האירוע יחד?</h3>
        <p className="pcta-text">
          הזמינו את בן/בת הזוג כדי שתוכלו לעבוד יחד על אותו אירוע.
        </p>
      </div>

      {!open ? (
        <div className="pcta-actions">
          <button type="button" className="btn-primary pcta-btn" onClick={() => setOpen(true)}>
            הזמנת בן/בת זוג
          </button>
          <button type="button" className="btn-text pcta-dismiss" onClick={dismiss}>
            לא עכשיו
          </button>
        </div>
      ) : (
        <form className="pcta-form" onSubmit={send}>
          <label className="pcta-label" htmlFor="pcta-email">
            האימייל של בן/בת הזוג
          </label>
          <div className="pcta-row">
            <input
              id="pcta-email"
              type="email"
              dir="ltr"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="partner@example.com"
              required
            />
            <button type="submit" className="btn-primary pcta-btn" disabled={busy}>
              {busy ? 'שולח…' : 'שליחת הזמנה'}
            </button>
          </div>
          {error && <p className="pcta-error">{error}</p>}
        </form>
      )}
    </div>
  )
}
