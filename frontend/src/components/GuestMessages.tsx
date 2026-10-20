/**
 * "מוזמנים כתבו לכם בוואטסאפ" — במסך אישורי ההגעה, ליד "צריכים אתכם".
 *
 * מוזמן שכותב שאלה למספר של VEYA — ההודעה מגיעה לכאן, ו-VEYA לא עונה לו
 * בשמכם (החלטת המייסד 2026-10-19). עונים מה-WhatsApp האישי (קישור wa.me
 * שנפתח באפליקציה שלכם) ומסמנים "טופל". כשאין הודעות שמחכות — לא מוצג כלום.
 */
import { useState } from 'react'
import { markGuestMessageHandled, type GuestMessageItem } from '../api'
import { announce } from '../lib/announce'
import { strings } from '../strings/he'
import './GuestMessages.css'

const t = strings.messages.guestMessages

function whenText(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString('he-IL', {
    timeZone: 'Asia/Jerusalem', day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

/** ``05XXXXXXXX`` → קישור שפותח שיחה ב-WhatsApp של מי שלוחץ. */
function waHref(phone: string): string {
  return `https://wa.me/972${phone.replace(/\D/g, '').replace(/^0/, '')}`
}

export function GuestMessages({
  items,
  guestsLabel,
  onChange,
}: {
  items: GuestMessageItem[]
  guestsLabel: string
  onChange: (items: GuestMessageItem[]) => void
}) {
  const [busyId, setBusyId] = useState<number | null>(null)
  const [error, setError] = useState('')
  const waiting = items.filter((m) => !m.handled)
  if (waiting.length === 0) return null

  async function handled(id: number) {
    setBusyId(id)
    setError('')
    try {
      await markGuestMessageHandled(id)
      onChange(items.filter((m) => m.id !== id))
      announce(t.handled)
    } catch {
      setError(t.handledError)
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="dash-stack dash-actions rsvp-needs guest-msgs" aria-labelledby="guest-msgs-title">
      <h2 className="rsvp-needs-title" id="guest-msgs-title">
        {t.title(guestsLabel)} <span className="guest-msgs-count">({waiting.length})</span>
      </h2>
      <p className="guest-msgs-desc">{t.desc}</p>
      <ul className="guest-msgs-list">
        {waiting.map((m) => (
          <li key={m.id} className="guest-msgs-item">
            <p className="guest-msgs-who">
              <strong>{m.guest_name || t.sharedPhone(guestsLabel)}</strong>
              {m.created_at && <span className="guest-msgs-when"> · {whenText(m.created_at)}</span>}
            </p>
            <p className="guest-msgs-body">{m.body}</p>
            <div className="guest-msgs-actions">
              {m.phone && (
                <a className="btn-primary guest-msgs-btn" href={waHref(m.phone)} target="_blank" rel="noopener noreferrer">
                  {t.reply}
                </a>
              )}
              <button
                type="button"
                className="btn-ghost guest-msgs-btn"
                disabled={busyId === m.id}
                onClick={() => void handled(m.id)}
              >
                {t.handled}
              </button>
            </div>
          </li>
        ))}
      </ul>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}
