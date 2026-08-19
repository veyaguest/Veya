import { useState } from 'react'
import { GoogleLogin, type CredentialResponse } from '@react-oauth/google'
import { googleExchange, login, register } from '../api'
import { setToken } from '../authStore'
import { getSupabase, isGoogleAuthConfigured } from '../lib/supabase'
import { Footer } from './Footer'
import type { User } from '../types'
import { strings } from '../strings/he'

/** מסך התחברות / הרשמה — פריסת split-screen: פאנל שיווקי + טופס כניסה. */
export function AuthPage({
  onAuth,
  initialMode,
  lockedEmail,
}: {
  onAuth: (user: User) => void
  /** פותח ישר בטופס הנכון — למשל כשמגיעים מהזמנה לאירוע. */
  initialMode?: 'login' | 'register'
  /** כשמגיעים מהזמנה: הכתובת שאליה נשלחה, ממולאת מראש (אפשר לשנות). */
  lockedEmail?: string
}) {
  // דף הנחיתה מקשר לכאן עם ?auth=register עבור כפתורי "התחילו/בואו נתחיל",
  // כדי לפתוח ישר בטופס הרשמה במקום בהתחברות.
  const [mode, setMode] = useState<'login' | 'register'>(() => {
    if (initialMode) return initialMode
    return new URLSearchParams(window.location.search).get('auth') === 'register'
      ? 'register'
      : 'login'
  })
  const [email, setEmail] = useState(lockedEmail ?? '')
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
  // busy נפרד לגוגל — הכפתור עצמו של Google Identity Services מנוהל אצלנו,
  // אבל בזמן ההמרה (signInWithIdToken + /auth/google/exchange) מציגים
  // סטטוס "מתחבר עם גוגל..." במקום הכפתור.
  const [googleBusy, setGoogleBusy] = useState(false)
  const googleEnabled = isGoogleAuthConfigured()

  /** מטפל בתשובה של Google Identity Services: מקבל id_token, מאמת אותו מול
   * Supabase דרך signInWithIdToken (בלי redirect — הכל בפרונט), ואז ממיר את
   * ה-session של Supabase לטוקן פנימי שלנו דרך /auth/google/exchange. */
  async function handleGoogleCredential(response: CredentialResponse) {
    setError(null)
    setNote(null)
    const idToken = response.credential
    if (!idToken) {
      setError(strings.errors.authGoogleNoToken)
      return
    }
    const client = getSupabase()
    if (!client) {
      setError(strings.errors.authGoogleNotConfigured)
      return
    }
    setGoogleBusy(true)
    try {
      const { data, error: sbErr } = await client.auth.signInWithIdToken({
        provider: 'google',
        token: idToken,
      })
      if (sbErr || !data.session) {
        throw new Error(sbErr?.message || strings.errors.authGoogleSupabase)
      }
      const res = await googleExchange(data.session.access_token)
      setToken(res.access_token)
      // מנתקים מיד מ-Supabase — הפכנו כבר את הטוקן שלה לטוקן פנימי.
      // persistSession=false ממילא לא שומרת, אבל signOut מנקה מצב בזיכרון.
      await client.auth.signOut()
      onAuth(res.user)
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.authGoogleFailed)
    } finally {
      setGoogleBusy(false)
    }
  }

  /** ולידציה בצד הלקוח לפני שליחה — משוב מיידי בלי סיבוב לשרת.
   * זו **אינה** שכבת האכיפה: אותם כללים בדיוק נאכפים ב-schemas.UserCreate
   * בשרת, כך שגם קריאת API ישירה נחסמת. */
  function localValidationError(): string | null {
    if (mode === 'login') return null
    if (!displayName.trim()) return 'צריך למלא שם מלא'
    if (displayName.trim().length < 2) return 'השם קצר מדי — אפשר למלא שם מלא'
    if (!phone.trim()) return 'צריך למלא מספר טלפון'
    // אותה בדיקה כמו normalize_israeli_phone בשרת: 9-10 ספרות שמתחילות ב-0
    // (או +972 שמומר לזה). הודעה בשפה טבעית, לא "פורמט לא תקין".
    const digits = phone.replace(/\D/g, '').replace(/^972/, '0')
    if (!/^0\d{8,9}$/.test(digits)) {
      return 'מספר הטלפון לא נראה תקין. אפשר לכתוב אותו כך: 050-1234567'
    }
    return null
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setNote(null)
    const localError = localValidationError()
    if (localError) {
      setError(localError)
      return
    }
    setBusy(true)
    try {
      const res =
        mode === 'login'
          ? await login(email, password)
          : await register(email, password, displayName, phone, acceptedTerms, acceptedMarketing)
      setToken(res.access_token)
      onAuth(res.user)
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.authLoginFailed)
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
            <h1 className="auth-hero-title">האירוע שלכם, סוף־סוף מסודר</h1>
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
              אישורי הגעה דיגיטליים שהמוזמנים באמת ממלאים
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
                  required
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
                    setNote(strings.toasts.passwordResetNote)
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
                    {strings.legal.authAgreePrefix}{' '}
                    <a href="/legal/terms.html" target="_blank" rel="noopener noreferrer">
                      {strings.legal.authTermsLink}
                    </a>{' '}
                    {strings.legal.authAgreeAnd}{' '}
                    <a href="/legal/privacy.html" target="_blank" rel="noopener noreferrer">
                      {strings.legal.authPrivacyLink}
                    </a>
                  </span>
                </label>
                <label className="auth-consent-row auth-consent-optional">
                  <input
                    type="checkbox"
                    checked={acceptedMarketing}
                    onChange={(e) => setAcceptedMarketing(e.target.checked)}
                  />
                  <span>{strings.legal.authMarketingOptIn}</span>
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
                {/* Google Identity Services רנדר את הכפתור בעצמו (iframe).
                    בזמן העיבוד (signInWithIdToken + exchange) מציגים "מתחבר…"
                    במקום הכפתור, כדי למנוע לחיצה כפולה. */}
                <div className="auth-google-slot">
                  {googleBusy ? (
                    <div className="auth-google-busy">מתחבר עם גוגל…</div>
                  ) : (
                    <GoogleLogin
                      onSuccess={handleGoogleCredential}
                      onError={() => setError(strings.errors.authGoogleFailed)}
                      locale="he_IL"
                      text={isLogin ? 'signin_with' : 'signup_with'}
                      shape="rectangular"
                      theme="filled_black"
                      size="large"
                      width="320"
                      // Safari חוסם cookies של צד-שלישי (ITP) — בלי הדגל הזה גוגל
                      // עלולה "לברוח" ל-navigation מלא בעמוד במקום popup/FedCM,
                      // מה שגרם בפועל להפניה שגויה על iPhone. זו ההמלצה הרשמית
                      // של גוגל לטיפול ב-ITP.
                      itp_support
                    />
                  )}
                </div>
                <p className="auth-google-consent">
                  {strings.legal.authGoogleAgreePrefix}{' '}
                  <a href="/legal/terms.html" target="_blank" rel="noopener noreferrer">
                    {strings.legal.authTermsLink}
                  </a>{' '}
                  {strings.legal.authAgreeAnd}{' '}
                  <a href="/legal/privacy.html" target="_blank" rel="noopener noreferrer">
                    {strings.legal.authPrivacyLink}
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
