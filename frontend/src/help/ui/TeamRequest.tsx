/**
 * "לדבר עם צוות VEYA" — הפנייה עצמה (HELP_CENTER_PLAN.md §10, שלב 7).
 *
 * החלטות המייסד (2026-09-29): ערוץ מייל בלבד; לא שואלים מה שכבר ידוע — השם
 * והמייל של החשבון מוצגים, לא נשאלים. השאלה היחידה: "במה אפשר לעזור?".
 *
 * נשלח **רק** כשהמשתמש לוחץ בעצמו "שליחה לצוות VEYA" (``submit`` — הקריאה
 * היחידה לשרת שכותבת משהו מתוך העזרה; נאכף ב-helpSafety.test.ts). יחד עם
 * הטקסט נשלחת תמונת מצב קבועה (מסך, נושא, בדיקה, שגיאות אחרונות אחרי ניקוי) —
 * בלי פרטי מוזמנים. השרת מחשב בעצמו את שאר העובדות.
 */
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { strings } from '../../strings/he'
import { sendHelpSupportRequest } from '../../api'
import type { HelpSupportRequest, HelpSupportRequestBody } from '../../api'

const t = strings.help.team
const MAX = 1000

/** "עוד לא הסתדר? לדבר עם צוות VEYA" — קישור קטן, או כפתור כשהאירוע קרוב. */
export function TeamEntry({
  prominent, withQuestion = false, onClick,
}: {
  prominent: boolean
  withQuestion?: boolean
  onClick: () => void
}) {
  return (
    <p className={`help-team-entry${prominent ? ' is-prominent' : ''}`}>
      {withQuestion && <span>{t.notSolved} </span>}
      <button
        type="button"
        className={prominent ? 'btn-ghost help-btn-sm' : 'btn-text help-inline-btn'}
        onClick={onClick}
      >
        {t.cta}
      </button>
    </p>
  )
}

export function TeamForm({
  account, checked, context, onSent,
}: {
  account: { name: string; email: string }
  /** שורות "מה כבר בדקנו כאן" — כותרות הנושא/הבדיקה, כמו שהמשתמש ראה אותן. */
  checked: string[]
  context: Omit<HelpSupportRequestBody, 'message'>
  onSent: (r: HelpSupportRequest) => void
}) {
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const areaRef = useRef<HTMLTextAreaElement | null>(null)
  useEffect(() => {
    areaRef.current?.focus({ preventScroll: true })
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    if (message.trim().length < 3) {
      setError(t.tooShort)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const r = await sendHelpSupportRequest({ ...context, message: message.trim() })
      setSent(true)
      onSent(r)
    } catch (err) {
      setError(err instanceof Error && err.message ? err.message : t.sendError)
    } finally {
      setBusy(false)
    }
  }

  if (sent) {
    return (
      <div className="help-section" role="status">
        <h3 className="help-h3">{t.sentTitle}</h3>
        <p className="help-answer">{t.sentBody(account.email)}</p>
      </div>
    )
  }

  return (
    <form className="help-section help-team-form" onSubmit={submit} noValidate>
      <h3 className="help-h3">{t.title}</h3>
      {checked.length > 0 && (
        <div className="help-team-checked">
          <p className="help-small-title">{t.checkedTitle}</p>
          <ul>
            {checked.map((line, i) => (
              <li key={i}>{line}</li>
            ))}
          </ul>
        </div>
      )}
      <label className="help-team-label" htmlFor="help-team-message">{t.messageLabel}</label>
      <p className="help-muted help-team-hint" id="help-team-hint">{t.messageHint}</p>
      <textarea
        id="help-team-message"
        ref={areaRef}
        className="help-team-textarea"
        rows={4}
        maxLength={MAX}
        value={message}
        onChange={(e) => {
          setMessage(e.target.value)
          if (error) setError(null)
        }}
        aria-describedby="help-team-hint help-team-counter"
        aria-invalid={error ? true : undefined}
      />
      <p className="help-muted help-team-counter" id="help-team-counter" aria-live="polite">{t.counter(message.length)}</p>
      <p className="help-answer help-team-reply">{t.replyTo(account.name.trim(), account.email)}</p>
      <p className="help-muted help-team-privacy">{t.privacy}</p>
      {error && <p className="help-note help-team-error" role="alert">{error}</p>}
      <button type="submit" className="btn-primary help-primary" disabled={busy}>
        {busy ? t.sending : t.submit}
      </button>
    </form>
  )
}

export function MyRequests({ items }: { items: HelpSupportRequest[] }) {
  if (items.length === 0) return null
  return (
    <div className="help-section help-team-mine">
      <p className="help-small-title">{t.mineTitle}</p>
      <ul className="help-list">
        {items.map((r) => (
          <li key={r.id} className="help-team-mine-row">
            <span>{t.mineItem(r.id, r.created_at ? new Date(r.created_at).toLocaleDateString('he-IL') : '')}</span>
            <span className={`help-team-status is-${r.status}`}>{t.status[r.status]}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
