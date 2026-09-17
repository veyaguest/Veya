import { useState } from 'react'
import { adminDeleteEvent } from '../../../api'
import { fetchAudit } from '../../adminApi'
import { EVENT_ACTIVITY_LABELS, people } from '../../peopleApi'
import { navigate, routeHref, type AdminPageKey } from '../../route'
import {
  Advanced,
  ConfirmAction,
  EmptyState,
  ErrorState,
  Loading,
  StatusPill,
  fmtDate,
  fmtDateTime,
  useAsync,
  useCan,
  useToast,
} from '../../ui'
import { EventOverrides } from '../rules/EventOverrides'

export function EventControlPage({
  eventId,
  onImpersonate,
}: {
  eventId: number
  onImpersonate: (userId: number, eventId?: number) => Promise<void>
}) {
  const can = useCan()
  const toast = useToast()
  const data = useAsync(() => people.event(eventId), [eventId])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [confirmEnter, setConfirmEnter] = useState(false)

  if (data.loading && !data.data) return <Loading />
  if (data.error && !data.data) return <ErrorState message={data.error} onRetry={data.reload} />
  const e = data.data
  if (!e) return null

  async function enter() {
    if (!e?.owner) return
    setBusy(true)
    setError(null)
    try {
      await onImpersonate(e.owner.id, e.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'הכניסה נכשלה')
      setBusy(false)
    }
  }

  async function remove() {
    if (!e) return
    setBusy(true)
    setError(null)
    try {
      await adminDeleteEvent(e.id)
      toast('האירוע נמחק')
      navigate('people', null, { tab: 'events' })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'המחיקה נכשלה')
      setBusy(false)
    }
  }

  return (
    <div className="adm-page">
      <nav className="adm-crumbs" aria-label="מיקום">
        <a href={routeHref('people', null, { tab: 'events' })}>אירועים</a>
        <span aria-hidden="true"> / </span>
        <span>#{e.id}</span>
      </nav>
      <header className="adm-page-head">
        <div>
          <h1 className="adm-page-title">{e.label}</h1>
          <p className="adm-page-sub">
            {e.event_type_label} · {fmtDate(e.event_date)}
            {e.event_time ? ` ${e.event_time}` : ''}
            {e.venue_name ? ` · ${e.venue_name}` : ''}
            {e.cycle_number > 1 ? ` · מחזור ${e.cycle_number} (נדחה)` : ''}
          </p>
        </div>
        <div className="adm-page-actions">
          {e.owner && can('users.impersonate') && (
            <button type="button" className="adm-btn adm-btn-primary" onClick={() => setConfirmEnter(true)} disabled={busy || e.owner.disabled}>
              כניסה לאירוע לתמיכה
            </button>
          )}
        </div>
      </header>
      {error && <p className="adm-inline-error" role="alert">{error}</p>}

      <section className="adm-people-row" aria-label="אנשים">
        <div>
          <span className="adm-muted">בעלים</span>
          {e.owner ? (
            <a className="adm-link" href={routeHref('people', `u${e.owner.id}`)}>
              {e.owner.name || e.owner.email}
            </a>
          ) : (
            <span>—</span>
          )}
          {e.owner?.disabled && <StatusPill tone="bad">חסום</StatusPill>}
        </div>
        <div>
          <span className="adm-muted">מנהלים נוספים</span>
          {e.members.length === 0 ? (
            <span>אין</span>
          ) : (
            e.members.map((m) => (
              <a key={m.id} className="adm-link" href={routeHref('people', `u${m.id}`)}>
                {m.name || m.email}
                <span className="adm-muted"> ({m.role === 'partner' ? 'שותף' : m.role === 'planner' ? 'מפיק' : m.role === 'venue' ? 'אולם' : m.role})</span>
              </a>
            ))
          )}
        </div>
      </section>

      <div className="adm-control-grid">
        {e.sections.map((s) => (
          <section key={s.key} className="adm-control" aria-labelledby={`sec-${s.key}`}>
            <header className="adm-control-head">
              <h2 id={`sec-${s.key}`} className="adm-section-title">{s.title}</h2>
              <StatusPill tone={s.status}>{s.status_label}</StatusPill>
            </header>
            <dl className="adm-kv">
              {s.facts.map((f) => (
                <div key={f.label}>
                  <dt>{f.label}</dt>
                  <dd className={f.tone === 'bad' ? 'adm-danger-text' : f.tone === 'warn' ? 'adm-warn-text' : undefined}>
                    {f.value}
                  </dd>
                </div>
              ))}
            </dl>
            {s.link && (
              <a className="adm-link adm-control-link" href={`#/admin/${s.link.split('?')[0]}${s.link.includes('?') ? '?' + s.link.split('?')[1] : ''}`}>
                ניהול {s.title}
              </a>
            )}
          </section>
        ))}
      </div>

      <EventOverrides eventId={e.id} />

      <Advanced title="היסטוריית אדמין לאירוע">
        <AdminHistory eventId={e.id} />
      </Advanced>
      <Advanced title="פעילות אחרונה באירוע">
        <EventActivity eventId={e.id} />
      </Advanced>

      {can('events.delete') && (
        <div className="adm-danger-zone">
          <div>
            <strong>מחיקת האירוע</strong>
            <p className="adm-muted">מוחק לצמיתות את האירוע, המוזמנים, ההודעות, ההושבה והשיחות. אי אפשר לשחזר.</p>
          </div>
          <button type="button" className="adm-btn adm-danger-text" onClick={() => setConfirmDelete(true)} disabled={busy}>
            מחיקה
          </button>
        </div>
      )}

      <ConfirmAction
        open={confirmEnter}
        title="כניסה לאירוע לצורך תמיכה"
        body={
          <p>
            תיכנסו לממשק בדיוק כמו {e.owner?.name || e.owner?.email}. כל פעולה שתבצעו שם היא פעולה אמיתית באירוע. הכניסה נרשמת ביומן.
          </p>
        }
        confirmLabel="כניסה"
        busy={busy}
        error={error}
        onConfirm={enter}
        onCancel={() => setConfirmEnter(false)}
      />
      <ConfirmAction
        open={confirmDelete}
        title="מחיקת אירוע לצמיתות"
        body={<p>כל הנתונים של "{e.label}" יימחקו. הפעולה לא הפיכה ונרשמת ביומן.</p>}
        confirmLabel="מחיקה לצמיתות"
        danger
        typeToConfirm={e.label}
        busy={busy}
        error={error}
        onConfirm={remove}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  )
}

function AdminHistory({ eventId }: { eventId: number }) {
  const data = useAsync(() => fetchAudit({ event_id: eventId, limit: 30 }), [eventId])
  if (data.loading && !data.data) return <Loading />
  if (data.error && !data.data) return <ErrorState message={data.error} onRetry={data.reload} />
  if (!data.data || data.data.items.length === 0) return <EmptyState title="לא בוצעו פעולות אדמין באירוע הזה" />
  return (
    <ol className="adm-history">
      {data.data.items.map((r) => (
        <li key={r.id} className="adm-history-item">
          <span className="adm-history-when">{fmtDateTime(r.created_at)}</span>
          <div>
            <div className="adm-history-title">{r.summary}</div>
            <div className="adm-history-detail">
              {r.actor_label}
              {r.changes.map((c) => ` · ${c.label}: ${c.before} ← ${c.after}`).join('')}
            </div>
          </div>
          <span />
        </li>
      ))}
    </ol>
  )
}

function EventActivity({ eventId }: { eventId: number }) {
  const data = useAsync(() => people.activity(eventId), [eventId])
  if (data.loading && !data.data) return <Loading />
  if (data.error && !data.data) return <ErrorState message={data.error} onRetry={data.reload} />
  if (!data.data || data.data.length === 0) return <EmptyState title="אין פעילות מתועדת" />
  return (
    <ol className="adm-history">
      {data.data.map((r) => (
        <li key={r.id} className="adm-history-item">
          <span className="adm-history-when">{fmtDateTime(r.created_at)}</span>
          <div>
            <div className="adm-history-title">{EVENT_ACTIVITY_LABELS[r.action] ?? r.action}</div>
            {r.detail && <div className="adm-history-detail">{r.detail}</div>}
          </div>
          <span className="adm-muted">{r.actor}</span>
        </li>
      ))}
    </ol>
  )
}

export type { AdminPageKey }
