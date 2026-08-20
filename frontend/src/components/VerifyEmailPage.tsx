import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent, ClipboardEvent } from 'react'
import { changeUnverifiedEmail, resendVerificationEmail, verifyEmailCode } from '../api'
import type { User } from '../types'
import { Footer } from './Footer'
import './VerifyEmailPage.css'

const CODE_LENGTH = 6
const RESEND_COOLDOWN_SECONDS = 30

/**
 * לוגו VEYA — קובץ המותג הרשמי ``frontend/public/logo.png`` (אותו קובץ שדף
 * הנחיתה מציג ב-hero ושמשמש כ-apple-touch-icon). בכוונה תמונה ולא שחזור
 * ב-CSS ולא ה-SVG: ה-SVG מרנדר את המילה VEYA כ-<text> בגופן Cormorant
 * Garamond, ובתוך <img> גופן חיצוני לא נטען — כלומר הלוגו היה נופל לגופן
 * ברירת מחדל. ה-PNG הוא הלוגו האמיתי כפי שעוצב, בלי תלות בגופנים.
 */
function VeyaLogo() {
  return <img className="verify-logo" src="/logo.png" alt="VEYA" width={152} height={133} />
}

/**
 * "אימות כתובת המייל" — המסך שמוצג מיד אחרי ההרשמה, לפני יצירת האירוע.
 *
 * הזרימה: הרשמה → קוד 6 ספרות מהמייל → אימות מוצלח → חזרה אוטומטית ליצירת
 * האירוע (App.tsx ממשיך משם לפי user.email_verified/user.profile_complete —
 * אין כאן שום ניווט ידני). הקישור במייל ממשיך לעבוד במקביל לקוד (מטופל
 * בנפרד ב-App.tsx דרך /app/verify-email) — המסך הזה לא נוגע בו, רק מזכיר
 * שהוא קיים כברירת מחדל כשהקוד לא נוח.
 */
export function VerifyEmailPage({
  user,
  onUpdated,
  onRefresh,
  onLogout,
}: {
  user: User
  onUpdated: (user: User) => void
  /** בודק מחדש מול השרת אם הכתובת כבר אומתה (למשל דרך הקישור, בטאב אחר). */
  onRefresh: () => void
  onLogout: () => void
}) {
  const [digits, setDigits] = useState<string[]>(() => Array(CODE_LENGTH).fill(''))
  const [editing, setEditing] = useState(false)
  const [email, setEmail] = useState(user.email)
  const [busy, setBusy] = useState(false)
  const [resending, setResending] = useState(false)
  const [note, setNote] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)
  const [cooldown, setCooldown] = useState(RESEND_COOLDOWN_SECONDS)
  const inputsRef = useRef<Array<HTMLInputElement | null>>([])

  // countdown לשליחה חוזרת — רץ פעם אחת בטעינה (קוד כבר נשלח בהרשמה),
  // ומתאפס שוב בכל שליחה חוזרת מוצלחת.
  useEffect(() => {
    if (cooldown <= 0) return
    const t = window.setInterval(() => setCooldown((c) => Math.max(0, c - 1)), 1000)
    return () => window.clearInterval(t)
  }, [cooldown])

  function focusBox(index: number) {
    inputsRef.current[index]?.focus()
    inputsRef.current[index]?.select()
  }

  // פוקוס ראשוני על התיבה הראשונה. ``preventScroll`` — בלי זה הדפדפן גולל
  // את העמוד כדי "להביא" את השדה, והלוגו בראש הכרטיס נחתך בטעינה. מחליף את
  // autoFocus שהיה על ה-input עצמו (שם אי אפשר לבטל את הגלילה).
  useEffect(() => {
    if (!editing && !success) inputsRef.current[0]?.focus({ preventScroll: true })
  }, [editing, success])

  // מאמת אוטומטית ברגע שכל 6 התיבות התמלאו. עובר דרך useEffect (ולא נקרא
  // ישירות בתוך handleChange) כדי לא להסתמך על תזמון לא-מובטח של updater
  // ל-setState — קריאת ה-state מיד אחרי setDigits() לא מובטחת להיות מעודכנת.
  useEffect(() => {
    const joined = digits.join('')
    if (joined.length === CODE_LENGTH) submit(joined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [digits])

  async function submit(code: string) {
    if (code.length !== CODE_LENGTH || busy) return
    setError(null)
    setBusy(true)
    try {
      const updated = await verifyEmailCode(code)
      setSuccess(true)
      // רגע קטן להראות את הודעת ההצלחה לפני שהאפליקציה ממשיכה לשלב הבא.
      window.setTimeout(() => onUpdated(updated), 450)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לאמת את הקוד')
      setDigits(Array(CODE_LENGTH).fill(''))
      focusBox(0)
      setBusy(false)
    }
  }

  function handleChange(index: number, raw: string) {
    // ברגע שמתחילים להקליד קוד חדש, השגיאה הקודמת כבר לא רלוונטית — היא
    // נעלמת מיד (יחד עם המסגרת האדומה על התיבות) במקום להישאר עד השליחה.
    if (error) setError(null)
    const value = raw.replace(/\D/g, '')
    if (!value) {
      setDigits((prev) => {
        const next = [...prev]
        next[index] = ''
        return next
      })
      return
    }
    // תמיכה בהדבקה/הקלדה מהירה שנוחתת כמה ספרות בתיבה אחת (למשל autofill).
    // חשוב: הזזת הפוקוס מחושבת רק מ-index/chars.length (לא מ-prev בתוך
    // ה-updater) — updater של setState חייב להישאר טהור בלי תופעות-לוואי;
    // React (StrictMode) מריץ אותו פעמיים לבדיקת טוהר, ו-focus() בתוכו היה
    // "קופץ" פעמיים ומאבד ספרות (נתפס בבדיקה ידנית).
    const chars = value.split('')
    setDigits((prev) => {
      const next = [...prev]
      let i = index
      for (const ch of chars) {
        if (i >= CODE_LENGTH) break
        next[i] = ch
        i += 1
      }
      return next
    })
    focusBox(Math.min(index + chars.length, CODE_LENGTH - 1))
  }

  function handleKeyDown(index: number, e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Backspace') {
      if (digits[index]) {
        handleChange(index, '')
        return
      }
      if (index > 0) {
        e.preventDefault()
        focusBox(index - 1)
        handleChange(index - 1, '')
      }
      return
    }
    if (e.key === 'ArrowLeft' && index < CODE_LENGTH - 1) focusBox(index + 1)
    if (e.key === 'ArrowRight' && index > 0) focusBox(index - 1)
    if (e.key === 'Enter') submit(digits.join(''))
  }

  function handlePaste(e: ClipboardEvent<HTMLInputElement>) {
    const text = e.clipboardData.getData('text')
    if (!text) return
    e.preventDefault()
    handleChange(0, text)
  }

  async function resend() {
    setError(null)
    setNote(null)
    setResending(true)
    try {
      await resendVerificationEmail()
      // "לכתובת" ולא "ל-": מקף לפני כתובת לטינית בתוך משפט עברי נשבר ב-bidi.
      setNote(`שלחנו קוד חדש לכתובת ${user.email}`)
      setDigits(Array(CODE_LENGTH).fill(''))
      setCooldown(RESEND_COOLDOWN_SECONDS)
      focusBox(0)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לשלוח את הקוד')
    } finally {
      setResending(false)
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
      setDigits(Array(CODE_LENGTH).fill(''))
      setCooldown(RESEND_COOLDOWN_SECONDS)
      setNote(`שלחנו קוד אימות חדש לכתובת ${updated.email}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לעדכן את הכתובת')
    } finally {
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
              <h1 className="verify-title">האימות הצליח</h1>
              <p className="verify-sub">רגע, ממשיכים…</p>
            </>
          ) : !editing ? (
            <>
              <h1 className="verify-title">אימות כתובת המייל</h1>
              {/* "לכתובת" ולא "ל־[מייל]": מקף מחבר שנצמד לכתובת לטינית בתוך
                  פסקה בעברית נשבר ויזואלית בדפדפנים (ה-bidi מזיז אותו לקצה
                  השורה). ככה הניסוח גם פשוט יותר לקריאה. */}
              <p className="verify-sub">
                שלחנו קוד אימות לכתובת
                <br />
                <span dir="ltr" className="verify-email">{user.email}</span>
              </p>

              <p className="verify-hint">הזינו את הקוד כדי להמשיך</p>

              <div className="verify-code-row" dir="ltr" onPaste={handlePaste}>
                {digits.map((digit, i) => (
                  <input
                    key={i}
                    ref={(el) => { inputsRef.current[i] = el }}
                    className={
                      'verify-code-box' +
                      (digit ? ' is-filled' : '') +
                      (error ? ' has-error' : '')
                    }
                    type="text"
                    inputMode="numeric"
                    autoComplete={i === 0 ? 'one-time-code' : 'off'}
                    pattern="[0-9]*"
                    maxLength={1}
                    value={digit}
                    disabled={busy}
                    aria-label={`ספרה ${i + 1} מתוך ${CODE_LENGTH}`}
                    onChange={(e) => handleChange(i, e.target.value)}
                    onKeyDown={(e) => handleKeyDown(i, e)}
                    onFocus={(e) => e.target.select()}
                  />
                ))}
              </div>

              {error && (
                <p className="auth-error verify-msg" role="alert">{error}</p>
              )}
              {note && <p className="auth-note verify-msg">{note}</p>}

              <button
                type="button"
                className="auth-submit verify-submit"
                onClick={() => submit(digits.join(''))}
                disabled={busy || digits.join('').length !== CODE_LENGTH}
              >
                {busy ? 'מאמתים…' : 'אימות מייל'}
              </button>

              <p className="verify-resend">
                <span>לא קיבלתם את הקוד?</span>
                <button
                  type="button"
                  className="auth-link-btn"
                  onClick={resend}
                  disabled={resending || cooldown > 0}
                >
                  {resending ? 'שולחים…' : 'שלחו לי קוד חדש'}
                </button>
              </p>
              {cooldown > 0 && (
                <p className="verify-countdown">
                  אפשר לבקש קוד חדש בעוד {cooldown} שניות
                </p>
              )}

              <div className="verify-secondary">
                <button
                  type="button"
                  className="auth-link-btn"
                  onClick={() => {
                    setEditing(true)
                    setNote(null)
                    setError(null)
                  }}
                >
                  הכתובת שגויה? אפשר לשנות אותה
                </button>
                <button type="button" className="auth-link-btn" onClick={onRefresh}>
                  כבר אימתתם דרך הקישור במייל? לרענון
                </button>
                <button type="button" className="auth-link-btn" onClick={onLogout}>
                  יציאה מהחשבון
                </button>
              </div>
            </>
          ) : (
            <>
              <h1 className="verify-title">עדכון כתובת המייל</h1>
              <p className="verify-sub">נשלח קוד אימות חדש לכתובת שתזינו.</p>
              {error && (
                <p className="auth-error verify-msg" role="alert">{error}</p>
              )}
              <form className="verify-form" onSubmit={saveEmail}>
                <div className="auth-field">
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
                  className="auth-submit verify-submit"
                  disabled={busy}
                >
                  {busy ? 'שומרים…' : 'שמירה ושליחת קוד חדש'}
                </button>
                <button
                  type="button"
                  className="verify-cancel"
                  onClick={() => {
                    setEditing(false)
                    setEmail(user.email)
                    setError(null)
                  }}
                  disabled={busy}
                >
                  ביטול
                </button>
              </form>
            </>
          )}
        </div>
      </div>
      <Footer />
    </>
  )
}
