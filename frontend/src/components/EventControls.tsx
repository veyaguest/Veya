import { useState } from 'react'
import { createMyEvent } from '../api'
import type { EventSummary, EventType } from '../types'
import { EVENT_TYPE_OPTIONS, getEventTerms } from '../strings/eventTypes'

/** שדות יצירת אירוע חדש (סוג אירוע + בעלי האירוע + אולם) — משמש במסך הראשון ובפופאובר. */
function NewEventFields({
  onCreated,
  onCancel,
  submitLabel = 'יצירת אירוע',
}: {
  onCreated: (ev: EventSummary) => void
  onCancel?: () => void
  submitLabel?: string
}) {
  const [eventType, setEventType] = useState<EventType>('wedding')
  const [groom, setGroom] = useState('')
  const [bride, setBride] = useState('')
  const [venue, setVenue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const terms = getEventTerms(eventType)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const ev = await createMyEvent({
        event_type: eventType,
        groom_name: groom,
        bride_name: terms.hasTwoHosts ? bride : '',
        venue_name: venue,
      })
      onCreated(ev)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו ליצור את האירוע, נסו שוב')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="event-new-form" onSubmit={submit}>
      <div className="event-type-field">
        <span className="field-label">סוג האירוע</span>
        <div className="event-type-grid" role="radiogroup" aria-label="סוג האירוע">
          {EVENT_TYPE_OPTIONS.map((opt) => (
            <button
              key={opt.type}
              type="button"
              role="radio"
              aria-checked={eventType === opt.type}
              className={`event-type-chip ${eventType === opt.type ? 'active' : ''}`}
              onClick={() => setEventType(opt.type)}
            >
              <span className="event-type-chip-icon" aria-hidden="true">
                {opt.icon}
              </span>
              <span className="event-type-chip-label">{opt.label}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="event-new-grid">
        <input
          type="text"
          value={groom}
          onChange={(e) => setGroom(e.target.value)}
          placeholder={terms.hostAField}
        />
        {terms.hasTwoHosts && (
          <input
            type="text"
            value={bride}
            onChange={(e) => setBride(e.target.value)}
            placeholder={terms.hostBField}
          />
        )}
        <input
          type="text"
          value={venue}
          onChange={(e) => setVenue(e.target.value)}
          placeholder="שם האולם"
        />
      </div>
      {error && <div className="auth-error">{error}</div>}
      <div className="event-new-actions">
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? 'רגע…' : submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="btn-ghost" onClick={onCancel}>
            ביטול
          </button>
        )}
      </div>
    </form>
  )
}

/** מסך פתיחה למשתמש חדש שאין לו עדיין אירוע. */
export function FirstEventScreen({
  onCreated,
}: {
  onCreated: (ev: EventSummary) => void
}) {
  return (
    <div className="auth-wrap">
      <div className="auth-card">
        <h1 className="first-event-title">ברוכים הבאים ל-VEYA</h1>
        <p className="auth-tagline">בואו ניצור את האירוע הראשון שלכם</p>
        <NewEventFields onCreated={onCreated} />
      </div>
    </div>
  )
}
