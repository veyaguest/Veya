import { useState } from 'react'
import { createMyEvent } from '../api'
import type { EventSummary } from '../types'

/** שדות יצירת אירוע חדש (חתן / כלה / אולם) — משמש גם במסך הראשון וגם בפופאובר. */
function NewEventFields({
  onCreated,
  onCancel,
  submitLabel = 'יצירת אירוע',
}: {
  onCreated: (ev: EventSummary) => void
  onCancel?: () => void
  submitLabel?: string
}) {
  const [groom, setGroom] = useState('')
  const [bride, setBride] = useState('')
  const [venue, setVenue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const ev = await createMyEvent({
        groom_name: groom,
        bride_name: bride,
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
      <div className="event-new-grid">
        <input
          type="text"
          value={groom}
          onChange={(e) => setGroom(e.target.value)}
          placeholder="שם החתן"
        />
        <input
          type="text"
          value={bride}
          onChange={(e) => setBride(e.target.value)}
          placeholder="שם הכלה"
        />
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

/** בוחר האירוע בסרגל העליון — החלפת אירוע פעיל + יצירת אירוע חדש. */
export function EventPicker({
  events,
  activeEventId,
  onSwitch,
  onCreated,
}: {
  events: EventSummary[]
  activeEventId: number | null
  onSwitch: (id: number) => void
  onCreated: (ev: EventSummary) => void
}) {
  const [creating, setCreating] = useState(false)

  function labelFor(ev: EventSummary): string {
    const names = [ev.groom_name, ev.bride_name].filter(Boolean).join(' · ')
    return names || ev.venue_name || `אירוע #${ev.id}`
  }

  return (
    <div className="event-picker">
      <select
        className="event-select"
        value={activeEventId ?? ''}
        onChange={(e) => onSwitch(Number(e.target.value))}
      >
        {events.map((ev) => (
          <option key={ev.id} value={ev.id}>
            {labelFor(ev)}
          </option>
        ))}
      </select>
      <button
        type="button"
        className="event-add-btn"
        title="אירוע חדש"
        onClick={() => setCreating((v) => !v)}
      >
        +
      </button>

      {creating && (
        <div className="event-popover">
          <div className="event-popover-title">אירוע חדש</div>
          <NewEventFields
            submitLabel="יצירה"
            onCancel={() => setCreating(false)}
            onCreated={(ev) => {
              setCreating(false)
              onCreated(ev)
            }}
          />
        </div>
      )}
    </div>
  )
}
