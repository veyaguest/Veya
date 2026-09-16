import { useState } from 'react'
import type { CallOutcome } from '../../../types'
import { callOps, israelToday, type CallerRow, type GuestCard } from '../../callOpsApi'
import { Drawer, ErrorState, Loading, StatusPill, fmtDate, fmtDateTime, useAsync, useCan, useToast } from '../../ui'

const RSVP_LABELS: Record<string, string> = {
  pending: 'טרם השיב/ה',
  maybe: 'אולי',
  confirmed: 'מגיע/ה',
  declined: 'לא מגיע/ה',
}

const OUTCOMES: { key: CallOutcome; label: string }[] = [
  { key: 'confirmed', label: 'אישר/ה הגעה' },
  { key: 'declined', label: 'לא מגיע/ה' },
  { key: 'no_answer', label: 'לא ענה/תה' },
  { key: 'busy', label: 'לא ניתן להשיג' },
  { key: 'callback', label: 'שיחה חוזרת' },
  { key: 'wrong_number', label: 'מספר לא תקין' },
]

export function GuestCallDrawer({
  guestId,
  callers,
  onClose,
  onChanged,
}: {
  guestId: number | null
  callers: CallerRow[]
  onClose: () => void
  onChanged: () => void
}) {
  const card = useAsync<GuestCard | null>(
    () => (guestId ? callOps.guest(guestId) : Promise.resolve(null)),
    [guestId],
  )
  const data = card.data
  return (
    <Drawer
      open={guestId !== null}
      onClose={onClose}
      title={data?.guest_name ?? 'אורח'}
      subtitle={data ? `${data.event_label} · ${fmtDate(data.event_date)}` : undefined}
      wide
    >
      {card.loading && !data ? (
        <Loading />
      ) : card.error ? (
        <ErrorState message={card.error} onRetry={card.reload} />
      ) : data ? (
        <GuestBody
          data={data}
          callers={callers}
          onChanged={() => {
            card.reload()
            onChanged()
          }}
        />
      ) : null}
    </Drawer>
  )
}

function GuestBody({
  data,
  callers,
  onChanged,
}: {
  data: GuestCard
  callers: CallerRow[]
  onChanged: () => void
}) {
  const can = useCan()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [outcome, setOutcome] = useState<CallOutcome | null>(null)
  const [note, setNote] = useState('')
  const [count, setCount] = useState<number>(data.party_size || 1)
  const [callbackAt, setCallbackAt] = useState('')
  const [followupDate, setFollowupDate] = useState(israelToday())
  const current = data.current
  const open = data.rsvp_status === 'pending' || data.rsvp_status === 'maybe'

  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true)
    setError(null)
    try {
      await action()
      toast(success)
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'הפעולה נכשלה')
    } finally {
      setBusy(false)
    }
  }

  async function saveOutcome() {
    if (!outcome) return
    await run(
      () =>
        callOps.recordOutcome(data.guest_id, {
          outcome,
          note,
          count: outcome === 'confirmed' ? count : null,
          callback_at: outcome === 'callback' && callbackAt ? new Date(callbackAt).toISOString() : null,
        }),
      'תוצאת השיחה נשמרה',
    )
    setOutcome(null)
    setNote('')
  }

  const assignable = callers.filter((c) => c.available_today)

  return (
    <div className="adm-guest">
      <dl className="adm-facts">
        <div>
          <dt>טלפון</dt>
          <dd>
            {data.phone ? (
              <a className="adm-link adm-mono" href={`tel:${data.phone}`}>{data.phone}</a>
            ) : (
              'אין מספר'
            )}
          </dd>
        </div>
        <div>
          <dt>סטטוס הגעה</dt>
          <dd>
            {RSVP_LABELS[data.rsvp_status] ?? data.rsvp_status}
            {data.rsvp_status === 'confirmed' && data.confirmed_count ? ` · ${data.confirmed_count}` : ''}
          </dd>
        </div>
        <div>
          <dt>סבב</dt>
          <dd>{current?.round_label ?? '—'}</dd>
        </div>
        <div>
          <dt>טלפן</dt>
          <dd>{current?.assignee_name || '—'}</dd>
        </div>
      </dl>

      <div className="adm-next">
        <span className="adm-muted">הפעולה הבאה</span>
        <strong>{data.next_action}</strong>
        {current && <span className="adm-muted">למה: {current.reason_label}</span>}
      </div>

      {error && <p className="adm-inline-error" role="alert">{error}</p>}

      {open && current && (
        <section className="adm-section">
          <h3 className="adm-section-title">תיעוד שיחה</h3>
          <div className="adm-chips" role="group" aria-label="תוצאת השיחה">
            {OUTCOMES.map((o) => (
              <button
                key={o.key}
                type="button"
                className={`adm-chip${outcome === o.key ? ' is-on' : ''}`}
                aria-pressed={outcome === o.key}
                onClick={() => setOutcome(o.key)}
              >
                {o.label}
              </button>
            ))}
          </div>
          {outcome === 'confirmed' && (
            <label className="adm-formfield">
              <span className="adm-label">כמה מגיעים</span>
              <input
                type="number"
                min={1}
                className="adm-input adm-input-num"
                value={count}
                onChange={(e) => setCount(Math.max(1, Number(e.target.value) || 1))}
              />
            </label>
          )}
          {outcome === 'callback' && (
            <label className="adm-formfield">
              <span className="adm-label">מתי לחזור</span>
              <input
                type="datetime-local"
                className="adm-input"
                value={callbackAt}
                onChange={(e) => setCallbackAt(e.target.value)}
              />
            </label>
          )}
          {outcome && (
            <>
              <label className="adm-formfield">
                <span className="adm-label">הערה (לא נשלחת לאורח)</span>
                <textarea className="adm-input" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
              <div className="adm-row-actions">
                <button
                  type="button"
                  className="adm-btn adm-btn-primary"
                  disabled={busy || (outcome === 'callback' && !callbackAt)}
                  onClick={saveOutcome}
                >
                  שמירת תוצאה
                </button>
                <button type="button" className="adm-btn" onClick={() => setOutcome(null)} disabled={busy}>
                  ביטול
                </button>
              </div>
            </>
          )}
        </section>
      )}

      {open && current?.task_id && (
        <section className="adm-section">
          <h3 className="adm-section-title">הקצאה</h3>
          <div className="adm-row-actions">
            <select
              className="adm-input"
              value={current.assignee_id ?? ''}
              disabled={busy}
              aria-label="טלפן"
              onChange={(e) => {
                const id = e.target.value ? Number(e.target.value) : null
                run(() => callOps.assign([current.task_id as number], id), id ? 'המשימה הוקצתה' : 'ההקצאה הוסרה')
              }}
            >
              <option value="">ללא טלפן</option>
              {assignable.map((c) => (
                <option key={c.id} value={c.id}>{c.display_name || c.email}</option>
              ))}
              {current.assignee_id && !assignable.some((c) => c.id === current.assignee_id) && (
                <option value={current.assignee_id}>{current.assignee_name} (לא זמין)</option>
              )}
            </select>
          </div>
        </section>
      )}

      {open && can('calls.operate') && !current && (
        <section className="adm-section">
          <h3 className="adm-section-title">קביעת שיחה ידנית</h3>
          <div className="adm-row-actions">
            <input
              type="date"
              className="adm-input"
              min={israelToday()}
              value={followupDate}
              onChange={(e) => setFollowupDate(e.target.value)}
              aria-label="תאריך"
            />
            <button
              type="button"
              className="adm-btn"
              disabled={busy || !data.phone}
              onClick={() => run(() => callOps.manual(data.guest_id, followupDate, '', null), 'השיחה נקבעה')}
            >
              קביעה
            </button>
          </div>
        </section>
      )}

      <section className="adm-section">
        <h3 className="adm-section-title">היסטוריה</h3>
        {data.history.length === 0 ? (
          <p className="adm-quiet">עדיין לא היה קשר עם האורח.</p>
        ) : (
          <ol className="adm-history">
            {data.history.map((h, i) => (
              <li key={i} className="adm-history-item">
                <span className="adm-history-when">{fmtDateTime(h.at)}</span>
                <div>
                  <div className="adm-history-title">
                    {h.title}
                    {h.actor && <span className="adm-muted"> · {h.actor}</span>}
                  </div>
                  {h.detail && <div className="adm-history-detail">{h.detail}</div>}
                </div>
                {h.tone !== 'neutral' && <StatusPill tone={h.tone}>{h.channel === 'phone' ? 'טלפון' : 'WhatsApp'}</StatusPill>}
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  )
}
