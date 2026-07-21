import { useState } from 'react'
import { login, register } from '../api'
import { setToken } from '../authStore'
import type { User } from '../types'

/** מסך התחברות / הרשמה — פריסת split-screen: פאנל שיווקי + טופס כניסה. */
export function AuthPage({ onAuth }: { onAuth: (user: User) => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [phone, setPhone] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setNote(null)
    setBusy(true)
    try {
      const res =
        mode === 'login'
          ? await login(email, password)
          : await register(email, password, displayName, phone)
      setToken(res.access_token)
      onAuth(res.user)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו להתחבר. בדקו את הפרטים ונסו שוב.')
    } finally {
      setBusy(false)
    }
  }

  function switchMode(next: 'login' | 'register') {
    setMode(next)
    setError(null)
    setNote(null)
  }

  const isLogin = mode === 'login'

  return (
    <div className="auth-split" dir="rtl">
      {/* ===== פאנל שיווקי ===== */}
      <aside className="auth-marketing">
        <span className="auth-ring auth-ring-1" aria-hidden="true" />
        <span className="auth-ring auth-ring-2" aria-hidden="true" />

        <div className="auth-logo-lockup" dir="ltr">
          <span className="auth-monogram">
            <span className="auth-monogram-diamond" />
            <span className="auth-monogram-v">V</span>
          </span>
          <span className="auth-logo-divider" />
          <span className="auth-wordmark">
            <span className="auth-wordmark-name">VEYA</span>
            <span className="auth-wordmark-tag" dir="rtl">
              הדרך הפשוטה לארגן חתונה, ובעצם כל אירוע
            </span>
          </span>
        </div>

        <div className="auth-hero">
          <div className="auth-hero-text">
            <h1 className="auth-hero-title">החתונה שלכם, מאורגנת אחת ולתמיד</h1>
            <p className="auth-hero-sub">
              רשימת מוזמנים, אישורי הגעה וסידורי הושבה — במקום אחד נקי ופשוט,
              בלי גיליונות אקסל ובלי בלגן.
            </p>
          </div>
          <ul className="auth-features">
            <li>
              <span className="auth-bullet" />
              רשימת מוזמנים חכמה שמתעדכנת בזמן אמת
            </li>
            <li>
              <span className="auth-bullet" />
              אישורי הגעה דיגיטליים שהאורחים באמת ממלאים
            </li>
            <li>
              <span className="auth-bullet" />
              סידורי הושבה בגרירה ושחרור, בלי כאב ראש
            </li>
          </ul>
        </div>

        <div className="auth-copyright">
          © 2026 VEYA · מלווים אתכם עד היום הגדול
        </div>
      </aside>

      {/* ===== פאנל התחברות ===== */}
      <section className="auth-panel">
        <div className="auth-panel-inner">
          {/* לוגו VEYA — מוצג בטלפון, שם הפאנל השיווקי (עם הלוגו הגדול) מוסתר */}
          <div className="auth-panel-logo" dir="ltr" aria-label="VEYA">
            <span className="auth-monogram">
              <span className="auth-monogram-diamond" />
              <span className="auth-monogram-v">V</span>
            </span>
            <span className="auth-panel-logo-name">VEYA</span>
          </div>

          <div className="auth-panel-head">
            <h2 className="auth-panel-title">
              {isLogin ? 'ברוכים השבים' : 'הרשמה ל-VEYA'}
            </h2>
            <p className="auth-panel-sub">
              {isLogin
                ? 'התחברו כדי להמשיך לנהל את האירוע שלכם'
                : 'פתחו חשבון חדש ותתחילו לנהל את האירוע שלכם'}
            </p>
          </div>

          <form className="auth-form" onSubmit={submit}>
            {!isLogin && (
              <div className="auth-field">
                <label htmlFor="auth-name">שם מלא</label>
                <input
                  id="auth-name"
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="דנה ויוסי"
                  autoComplete="name"
                />
              </div>
            )}

            {!isLogin && (
              <div className="auth-field">
                <label htmlFor="auth-phone">טלפון</label>
                <input
                  id="auth-phone"
                  type="tel"
                  dir="ltr"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="050-123-4567"
                  autoComplete="tel"
                  required
                />
              </div>
            )}

            <div className="auth-field">
              <label htmlFor="auth-email">אימייל</label>
              <input
                id="auth-email"
                type="email"
                dir="ltr"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                autoComplete="email"
                required
              />
            </div>

            <div className="auth-field">
              <label htmlFor="auth-pass">סיסמה</label>
              <input
                id="auth-pass"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={isLogin ? '••••••••' : 'לפחות 8 תווים, אות וספרה'}
                autoComplete={isLogin ? 'current-password' : 'new-password'}
                required
              />
            </div>

            {isLogin && (
              <div className="auth-row">
                <label className="auth-remember">
                  <input type="checkbox" defaultChecked />
                  זכור אותי
                </label>
                <button
                  type="button"
                  className="auth-link-btn"
                  onClick={() =>
                    setNote('איפוס סיסמה עצמאי בדרך — בינתיים כתבו לנו ונעזור.')
                  }
                >
                  שכחתם סיסמה?
                </button>
              </div>
            )}

            {error && <div className="auth-error">{error}</div>}
            {note && <div className="auth-note">{note}</div>}

            <button type="submit" className="auth-submit" disabled={busy}>
              {busy ? 'רגע…' : isLogin ? 'התחברות' : 'יצירת חשבון'}
            </button>

            {isLogin && (
              <>
                <div className="auth-divider">
                  <span className="auth-divider-line" />
                  <span className="auth-divider-word">או</span>
                  <span className="auth-divider-line" />
                </div>
                <button
                  type="button"
                  className="auth-secondary"
                  onClick={() =>
                    setNote('כניסה עם קוד לנייד תגיע בקרוב.')
                  }
                >
                  כניסה עם קוד חד-פעמי לנייד
                </button>
              </>
            )}
          </form>

          <div className="auth-switch">
            {isLogin ? (
              <>
                אין לכם חשבון עדיין?{' '}
                <button
                  type="button"
                  className="auth-link-btn"
                  onClick={() => switchMode('register')}
                >
                  הרשמה ל-VEYA
                </button>
              </>
            ) : (
              <>
                כבר יש לכם חשבון?{' '}
                <button
                  type="button"
                  className="auth-link-btn"
                  onClick={() => switchMode('login')}
                >
                  להתחברות
                </button>
              </>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}
