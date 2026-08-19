import { useEffect, useState } from 'react'
import { acceptInvitation, previewInvitation } from '../api'
import { getToken } from '../authStore'
import type { InvitationPreview } from '../types'
import { Footer } from './Footer'
import './JoinEventPage.css'

/**
 * דף ההצטרפות לאירוע — מה שנפתח בלחיצה על הקישור במייל ההזמנה (``/join``).
 *
 * הדף לא מניח שום דבר על המשתמש: הוא עשוי להיות מחובר, מחובר עם החשבון
 * הלא-נכון, רשום אך מנותק, או לא רשום בכלל. השרת מחזיר ``state`` אחד מכל
 * המקרים האלה (ראו schemas.InvitationPreview), וכאן כל מצב מקבל מסך משלו.
 *
 * העיקרון החשוב: בשום מצב לא נוצר כאן אירוע חדש — ההצטרפות תמיד מחברת את
 * החשבון לאירוע שכבר קיים.
 */
export function JoinEventPage({
  token,
  onJoined,
  onNeedAuth,
}: {
  token: string
  /** ההצטרפות הושלמה — האפליקציה תטען מחדש את המשתמש ותיכנס לאירוע. */
  onJoined: () => void
  /** צריך להתחבר/להירשם קודם; ההזמנה נשמרת ונחזור אליה מיד אחרי. */
  onNeedAuth: (mode: 'login' | 'register', email: string) => void
}) {
  const [preview, setPreview] = useState<InvitationPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [joining, setJoining] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    previewInvitation(token)
      .then((p) => alive && setPreview(p))
      .catch((err) =>
        alive && setError(err instanceof Error ? err.message : 'לא הצלחנו לטעון את ההזמנה'),
      )
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [token])

  async function join() {
    setError(null)
    setJoining(true)
    try {
      await acceptInvitation(token)
      onJoined()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לצרף אתכם לאירוע')
      setJoining(false)
    }
  }

  function Shell({ children }: { children: React.ReactNode }) {
    return (
      <>
        <div className="join-page" dir="rtl">
          <div className="join-card">
            <div className="join-logo" dir="ltr" aria-label="VEYA">
              VEYA
            </div>
            {children}
          </div>
        </div>
        <Footer />
      </>
    )
  }

  if (loading) {
    return (
      <Shell>
        <p className="join-loading">טוען את ההזמנה…</p>
      </Shell>
    )
  }

  if (!preview) {
    return (
      <Shell>
        <h1 className="join-title">לא הצלחנו לפתוח את ההזמנה</h1>
        <p className="join-text">{error || 'הקישור הזה לא תקין.'}</p>
      </Shell>
    )
  }

  const { state, event_title, inviter_name, invited_email } = preview

  // מסכי "אי אפשר להשתמש בהזמנה" — נוסח אנושי, בלי שפה טכנית.
  const deadEnd: Partial<Record<string, { title: string; text: string }>> = {
    expired: {
      title: 'ההזמנה כבר לא בתוקף',
      text: 'הקישור הזה פג. אפשר לבקש מבן/בת הזוג לשלוח הזמנה חדשה.',
    },
    used: {
      title: 'ההזמנה כבר נוצלה',
      text: 'הקישור הזה כבר שימש להצטרפות. אם זה לא הייתם אתם, כדאי לבדוק מול בן/בת הזוג.',
    },
    cancelled: {
      title: 'ההזמנה בוטלה',
      text: 'אפשר לבקש מבן/בת הזוג לשלוח הזמנה חדשה.',
    },
    invalid: {
      title: 'הקישור הזה לא תקין',
      text: 'ייתכן שהוא נחתך בהעתקה. כדאי לפתוח את הקישור ישירות מהמייל.',
    },
  }

  const dead = deadEnd[state]
  if (dead) {
    return (
      <Shell>
        <h1 className="join-title">{dead.title}</h1>
        <p className="join-text">{dead.text}</p>
      </Shell>
    )
  }

  if (state === 'wrong_account') {
    return (
      <Shell>
        <h1 className="join-title">ההזמנה נשלחה לכתובת אחרת</h1>
        <p className="join-text">
          ההזמנה נשלחה ל-<span dir="ltr" className="join-email">{invited_email}</span>,
          ואתם מחוברים עם חשבון אחר.
        </p>
        <p className="join-text join-text-muted">
          כדי להצטרף, התחברו עם החשבון שאליו נשלחה ההזמנה.
        </p>
        <button
          type="button"
          className="join-btn join-btn-secondary"
          onClick={() => onNeedAuth('login', invited_email)}
        >
          התחברות עם חשבון אחר
        </button>
      </Shell>
    )
  }

  if (state === 'needs_login') {
    return (
      <Shell>
        <p className="join-kicker">
          {inviter_name ? `${inviter_name} הזמין אתכם` : 'הוזמנתם'} לנהל יחד את האירוע
        </p>
        <h1 className="join-title">{event_title}</h1>
        <p className="join-text">
          ההזמנה נשלחה ל-<span dir="ltr" className="join-email">{invited_email}</span>.
          התחברו או פתחו חשבון עם הכתובת הזו כדי להצטרף.
        </p>
        <div className="join-actions">
          <button
            type="button"
            className="join-btn join-btn-primary"
            onClick={() => onNeedAuth('register', invited_email)}
          >
            פתיחת חשבון והצטרפות
          </button>
          <button
            type="button"
            className="join-btn join-btn-secondary"
            onClick={() => onNeedAuth('login', invited_email)}
          >
            כבר יש לי חשבון
          </button>
        </div>
      </Shell>
    )
  }

  if (state === 'already_member' || state === 'joined') {
    return (
      <Shell>
        <div className="join-check" aria-hidden="true">✓</div>
        <h1 className="join-title">אתם בפנים</h1>
        <p className="join-text">
          אתם מנהלים את {event_title || 'האירוע'} יחד.
        </p>
        <button type="button" className="join-btn join-btn-primary" onClick={onJoined}>
          מעבר לאירוע
        </button>
      </Shell>
    )
  }

  // state === 'ready'
  return (
    <Shell>
      <p className="join-kicker">
        {inviter_name ? `${inviter_name} הזמין אתכם` : 'הוזמנתם'} לנהל יחד את האירוע 💍
      </p>
      <h1 className="join-title">{event_title}</h1>
      <p className="join-text">
        ב-VEYA תנהלו יחד את המוזמנים, אישורי ההגעה, סידור ההושבה וכל פרטי האירוע —
        שניכם רואים את אותו מידע.
      </p>
      {error && <p className="join-error">{error}</p>}
      <button
        type="button"
        className="join-btn join-btn-primary"
        onClick={join}
        disabled={joining}
      >
        {joining ? 'מצרף…' : 'הצטרפות לאירוע'}
      </button>
      {!getToken() && (
        <p className="join-text join-text-muted">צריך להיות מחוברים כדי להצטרף.</p>
      )}
    </Shell>
  )
}
