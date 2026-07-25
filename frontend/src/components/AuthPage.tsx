import { useEffect, useState } from 'react'
import { googleExchange, login, register } from '../api'
import { setToken } from '../authStore'
import { getSupabase, isGoogleAuthConfigured } from '../lib/supabase'
import { Footer } from './Footer'
import type { User } from '../types'

/** מסך התחברות / הרשמה — פריסת split-screen: פאנל שיווקי + טופס כניסה. */
export function AuthPage({ onAuth }: { onAuth: (user: User) => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [phone, setPhone] = useState('')
  // חובה: תיבת אישור תנאי שימוש+פרטיות בהרשמה. לא מסומנת מראש (בניגוד ל"זכור
  // אותי" של ההתחברות) — ראו legal/11-dev-compliance-tasklist.md, Frontend #2.
  const [acceptedTerms, setAcceptedTerms] = useState(false)
  const [acceptedMarketing, setAcceptedMarketing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  // גוגל בנפרד: busy נפרד כדי שהמצב יישאר "מתחבר עם גוגל..." גם בזמן שהדפדפן
  // חוזר מ-OAuth callback וממיר את הטוקן ב-Backend.
  const [googleBusy, setGoogleBusy] = useState(false)
  const googleEnabled = isGoogleAuthConfigured()

  // טיפול ב-callback של גוגל: אחרי ש-Supabase שולחת את המשתמש בחזרה,
  // ה-URL מכיל #access_token=... . הלקוח (עם detectSessionInUrl:true)
  // מפענח את זה אוטומטית ושומר session. אנחנו קוראים getSession(),
  // ואם יש טוקן — ממירים אותו לטוקן פנימי של VEYA דרך /auth/google/exchange.
  // חשוב: נכנסים לזה רק אם ה-URL מכיל את החתימה של OAuth (#access_token=)
  // כדי לא לרוץ לחינם כל טעינה של דף הכניסה.
  useEffect(() => {
    const client = getSupabase()
    if (!client) return
    const hash = window.location.hash || ''
    if (!hash.includes('access_token=')) return

    setGoogleBusy(true)
    setError(null)
    ;(async () => {
      try {
        const { data, error: sessionErr } = await client.auth.getSession()
        if (sessionErr || !data.session) {
          throw new Error(sessionErr?.message || 'לא הצלחנו לקבל את פרטי הכניסה מגוגל')
        }
        const res = await googleExchange(data.session.access_token)
        setToken(res.access_token)
        // מנקים את ה-hash מה-URL כדי שריענון לא ינסה להריץ שוב את החילוף.
        // Supabase לא נוגעת ב-hash אחרי getSession — צריך לנקות ידנית.
        window.history.replaceState(null, '', window.location.pathname + window.location.search)
        // מנתקים מ-Supabase — הטוקן שלה כבר לא נחוץ (הפכנו אותו לטוקן פנימי).
        // בלי זה session נשאר ב-localStorage וניסיון התחברות עתידי היה חוזר לאותו משתמש.
        await client.auth.signOut()
        onAuth(res.user)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'התחברות עם גוגל נכשלה')
      } finally {
        setGoogleBusy(false)
      }
    })()
  }, [onAuth])

  async function handleGoogleLogin() {
    setError(null)
    setNote(null)
    const client = getSupabase()
    if (!client) {
      setError('התחברות עם גוגל אינה מוגדרת כרגע')
      return
    }
    setGoogleBusy(true)
    try {
      const { error: oauthErr } = await client.auth.signInWithOAuth({
        provider: 'google',
        options: { redirectTo: window.location.origin },
      })
      if (oauthErr) throw new Error(oauthErr.message)
      // הצלחה = הדפדפן מנווט לגוגל. הקוד מכאן והלאה כבר לא ירוץ.
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לפתוח את התחברות גוגל')
      setGoogleBusy(false)
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setNote(null)
    setBusy(true)
    try {
      const res =
        mode === 'login'
          ? await login(email, password)
          : await register(email, password, displayName, phone, acceptedTerms, acceptedMarketing)
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
    <>
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
            <h1 className="auth-hero-title">האירוע שלכם, מאורגן אחת ולתמיד</h1>
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
          © 2026 VEYA · מלווים אתכם עד היום שלכם
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
                  placeholder="דנה כהן"
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

            {!isLogin && (
              <div className="auth-consent">
                <label className="auth-consent-row">
                  <input
                    type="checkbox"
                    checked={acceptedTerms}
                    onChange={(e) => setAcceptedTerms(e.target.checked)}
                    required
                  />
                  <span>
                    אני מאשר/ת את{' '}
                    <a href="/legal/terms.html" target="_blank" rel="noopener noreferrer">
                      תנאי השימוש
                    </a>{' '}
                    ואת{' '}
                    <a href="/legal/privacy.html" target="_blank" rel="noopener noreferrer">
                      מדיניות הפרטיות
                    </a>
                  </span>
                </label>
                <label className="auth-consent-row auth-consent-optional">
                  <input
                    type="checkbox"
                    checked={acceptedMarketing}
                    onChange={(e) => setAcceptedMarketing(e.target.checked)}
                  />
                  <span>אני מעוניין/ת לקבל עדכונים מ-VEYA</span>
                </label>
              </div>
            )}

            {error && <div className="auth-error">{error}</div>}
            {note && <div className="auth-note">{note}</div>}

            <button
              type="submit"
              className="auth-submit"
              disabled={busy || (!isLogin && !acceptedTerms)}
            >
              {busy ? 'רגע…' : isLogin ? 'התחברות' : 'יצירת חשבון'}
            </button>

            {googleEnabled && (
              <>
                <div className="auth-divider">
                  <span className="auth-divider-line" />
                  <span className="auth-divider-word">או</span>
                  <span className="auth-divider-line" />
                </div>
                <button
                  type="button"
                  className="auth-secondary auth-google"
                  onClick={handleGoogleLogin}
                  disabled={googleBusy || busy}
                >
                  <svg
                    width="18"
                    height="18"
                    viewBox="0 0 18 18"
                    aria-hidden="true"
                    style={{ marginInlineEnd: 8, verticalAlign: 'middle' }}
                  >
                    <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"/>
                    <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.83.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.32A9 9 0 0 0 9 18z"/>
                    <path fill="#FBBC05" d="M3.97 10.72A5.4 5.4 0 0 1 3.68 9c0-.6.1-1.18.29-1.72V4.96H.96A9 9 0 0 0 0 9c0 1.45.35 2.82.96 4.04l3.01-2.32z"/>
                    <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.47.9 11.43 0 9 0A9 9 0 0 0 .96 4.96l3.01 2.32C4.68 5.16 6.66 3.58 9 3.58z"/>
                  </svg>
                  {googleBusy ? 'מתחבר עם גוגל…' : 'התחברות עם גוגל'}
                </button>
                <p className="auth-google-consent">
                  בהתחברות עם גוגל אני מאשר/ת את{' '}
                  <a href="/legal/terms.html" target="_blank" rel="noopener noreferrer">
                    תנאי השימוש
                  </a>{' '}
                  ואת{' '}
                  <a href="/legal/privacy.html" target="_blank" rel="noopener noreferrer">
                    מדיניות הפרטיות
                  </a>
                </p>
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
    <Footer />
    </>
  )
}
