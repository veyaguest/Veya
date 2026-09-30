/**
 * פניות תמיכה — פניות של בעלי אירועים מתוך "עזרה" (HELP_CENTER_PLAN.md §10.4, שלב 7).
 *
 * רשימה (פתוחות / טופלו / הכול) → פנייה אחת: מה נכתב, מה העזרה כבר בדקה,
 * שינוי סטטוס (נרשם ביומן), "כניסה לאירוע לתמיכה" (הקיים) ומייל לחזרה.
 * הצוות עונה במייל, מחוץ ל-VEYA (החלטת המייסד — ערוץ מייל בלבד).
 * הטקסט של הלקוח מוצג כטקסט בלבד (בלי HTML).
 */
import { useState } from 'react'
import {
  fetchSupportRequest, fetchSupportRequests, setSupportStatus,
  type SupportRequestDetail, type SupportRequestRow, type SupportStatus,
} from '../../adminApi'
import { navigate, routeHref, type AdminRoute } from '../../route'
import {
  ConfirmAction, EmptyState, ErrorState, Loading, PageHeader, StatusPill, Tabs,
  fmtDateTime, useAsync, useCan, useToast, type Tone,
} from '../../ui'

type Filter = 'open' | 'resolved' | 'all'

const STATUS_LABEL: Record<SupportStatus, string> = { new: 'חדשה', in_progress: 'בטיפול', resolved: 'טופלה' }
const STATUS_TONE: Record<SupportStatus, Tone> = { new: 'warn', in_progress: 'info', resolved: 'ok' }
const PLATFORM_LABEL: Record<string, string> = { desktop: 'מחשב', mobile: 'טלפון' }
const ROLE_LABEL: Record<string, string> = { owner: 'בעלים', partner: 'בן/בת זוג' }

export function SupportPage({
  route,
  onImpersonate,
}: {
  route: AdminRoute
  onImpersonate: (userId: number, eventId?: number) => Promise<void>
}) {
  if (route.id) return <SupportDetail id={Number(route.id)} onImpersonate={onImpersonate} />
  return <SupportList route={route} />
}

function SupportList({ route }: { route: AdminRoute }) {
  const filter = (route.params.get('status') as Filter) || 'open'
  const { data, error, loading, reload } = useAsync(() => fetchSupportRequests(filter), [filter])
  return (
    <div className="adm-page">
      <PageHeader title="פניות תמיכה" subtitle="פניות מתוך &quot;עזרה&quot; — עונים במייל של החשבון" />
      <Tabs<Filter>
        label="סינון פניות"
        active={filter}
        onChange={(v) => navigate('support', null, { status: v === 'open' ? null : v }, { replace: true })}
        tabs={[
          { key: 'open', label: 'פתוחות' },
          { key: 'resolved', label: 'טופלו' },
          { key: 'all', label: 'הכול' },
        ]}
      />
      {loading && !data ? (
        <Loading />
      ) : error && !data ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data || data.length === 0 ? (
        <EmptyState
          title={filter === 'open' ? 'אין פניות פתוחות' : 'אין פניות להצגה'}
          text="פניות חדשות מתוך העזרה יופיעו כאן."
        />
      ) : (
        <ul className="adm-list">
          {data.map((r) => (
            <li key={r.id}>
              <SupportListRow r={r} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function SupportListRow({ r }: { r: SupportRequestRow }) {
  return (
    <a className="adm-list-row" href={routeHref('support', r.id)}>
      {/* תמיד שלושה תאים (הגריד של adm-list-row) — גם כשאין תגית דחיפות. */}
      {r.urgency === 'high' ? <span className="adm-sev adm-sev-critical">דחוף</span> : <span aria-hidden="true" />}
      <span className="adm-list-main">
        <span className="adm-list-title">
          פנייה #{r.id} · {r.user?.name || r.user?.email || 'משתמש שנמחק'}
        </span>
        <span className="adm-list-sub">
          {r.about || 'כללי'}
          {r.event ? ` · ${r.event.title}` : ''}
          {r.event?.days_to_event != null ? ` · ${daysLabel(r.event.days_to_event)}` : ''}
          {' · '}
          {fmtDateTime(r.created_at)}
        </span>
      </span>
      <StatusPill tone={STATUS_TONE[r.status]}>{STATUS_LABEL[r.status]}</StatusPill>
    </a>
  )
}

function daysLabel(days: number): string {
  if (days < 0) return 'האירוע עבר'
  if (days === 0) return 'האירוע היום'
  if (days === 1) return 'מחר האירוע'
  return `עוד ${days} ימים לאירוע`
}

function SupportDetail({
  id,
  onImpersonate,
}: {
  id: number
  onImpersonate: (userId: number, eventId?: number) => Promise<void>
}) {
  const can = useCan()
  const toast = useToast()
  const { data, error, loading, reload } = useAsync(() => fetchSupportRequest(id), [id])
  const [current, setCurrent] = useState<SupportRequestDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [confirmEnter, setConfirmEnter] = useState(false)

  if (loading && !data) return <Loading />
  if (error && !data) return <ErrorState message={error} onRetry={reload} />
  const r = current && current.id === id ? current : data
  if (!r) return null

  async function changeStatus(status: SupportStatus) {
    setBusy(true)
    setActionError(null)
    try {
      setCurrent(await setSupportStatus(id, status))
      toast(`הסטטוס עודכן: ${STATUS_LABEL[status]}`)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'העדכון לא הצליח')
    } finally {
      setBusy(false)
    }
  }

  async function enter() {
    if (!r?.event?.owner_id) return
    setBusy(true)
    setActionError(null)
    try {
      await onImpersonate(r.event.owner_id, r.event.id)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'הכניסה נכשלה')
      setBusy(false)
    }
  }

  const ctx = r.context
  const facts = Object.entries(ctx.facts ?? {})
  return (
    <div className="adm-page">
      <p className="adm-quiet">
        <a href={routeHref('support')}>→ לכל הפניות</a>
      </p>
      <header className="adm-page-head">
        <div>
          <h1 className="adm-page-title">
            פנייה #{r.id} {r.urgency === 'high' && <span className="adm-sev adm-sev-critical">דחוף</span>}
          </h1>
          <p className="adm-page-sub">
            {fmtDateTime(r.created_at)}
            {r.handled_by ? ` · מטפל/ת: ${r.handled_by.name || r.handled_by.email}` : ''}
          </p>
        </div>
        <div className="adm-page-actions">
          <StatusPill tone={STATUS_TONE[r.status]}>{STATUS_LABEL[r.status]}</StatusPill>
          {r.event?.owner_id && can('users.impersonate') && (
            <button type="button" className="adm-btn adm-btn-primary" onClick={() => setConfirmEnter(true)} disabled={busy}>
              כניסה לאירוע לתמיכה
            </button>
          )}
        </div>
      </header>
      {actionError && <p className="adm-inline-error" role="alert">{actionError}</p>}

      <section className="adm-section" aria-labelledby="sup-who">
        <h2 className="adm-section-title" id="sup-who">מי פנה</h2>
        {r.user ? (
          <p>
            {r.user.name || '—'} ·{' '}
            <a href={`mailto:${r.user.email}?subject=${encodeURIComponent(`פנייה #${r.id} ל-VEYA`)}`}>{r.user.email}</a>
            {ctx.role ? ` · ${ROLE_LABEL[ctx.role] ?? ctx.role}` : ''}
          </p>
        ) : (
          <p className="adm-quiet">המשתמש נמחק</p>
        )}
        {r.event && (
          <p>
            <a href={routeHref('people', `e${r.event.id}`)}>{r.event.title}</a>
            {r.event.event_date ? ` · ${r.event.event_date}` : ''}
            {r.event.days_to_event != null ? ` · ${daysLabel(r.event.days_to_event)}` : ''}
          </p>
        )}
      </section>

      <section className="adm-section" aria-labelledby="sup-msg">
        <h2 className="adm-section-title" id="sup-msg">מה נכתב</h2>
        <p className="adm-support-message">{r.message}</p>
      </section>

      <section className="adm-section" aria-labelledby="sup-ctx">
        <h2 className="adm-section-title" id="sup-ctx">מה העזרה כבר בדקה</h2>
        <table className="adm-table adm-table-plain">
          <tbody>
            <tr><th scope="row">מסך</th><td>{ctx.screen || '—'}</td></tr>
            <tr><th scope="row">נושא</th><td>{ctx.topic_id || '—'}</td></tr>
            <tr><th scope="row">בדיקה</th><td>{ctx.tree_id ? `${ctx.tree_id}${ctx.outcome ? ` → ${ctx.outcome}` : ''}` : '—'}</td></tr>
            <tr><th scope="row">מכשיר</th><td>{ctx.platform ? PLATFORM_LABEL[ctx.platform] ?? ctx.platform : '—'}</td></tr>
            <tr><th scope="row">סוג אירוע</th><td>{ctx.event_type || '—'}</td></tr>
          </tbody>
        </table>
        {(ctx.recent_errors ?? []).length > 0 && (
          <>
            <h3 className="adm-support-subtitle">שגיאות אחרונות (אחרי ניקוי)</h3>
            <ul className="adm-support-errors">
              {ctx.recent_errors!.map((e, i) => (
                <li key={i}>
                  <code>{e.method} {e.path} · {e.status}</code>
                  {e.message ? ` — ${e.message}` : ''}
                </li>
              ))}
            </ul>
          </>
        )}
        {facts.length > 0 && (
          <details className="adm-support-facts">
            <summary>עובדות המסך בזמן הפנייה ({facts.length})</summary>
            <table className="adm-table adm-table-plain">
              <tbody>
                {facts.map(([k, v]) => (
                  <tr key={k}>
                    <th scope="row"><code>{k}</code></th>
                    <td>{v === null ? 'לא ידוע' : String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        )}
      </section>

      {can('support.handle') && (
        <section className="adm-section" aria-labelledby="sup-status">
          <h2 className="adm-section-title" id="sup-status">סטטוס</h2>
          <div className="adm-page-actions">
            {r.status !== 'in_progress' && (
              <button type="button" className="adm-btn" disabled={busy} onClick={() => void changeStatus('in_progress')}>
                סימון &quot;בטיפול&quot;
              </button>
            )}
            {r.status !== 'resolved' && (
              <button type="button" className="adm-btn adm-btn-primary" disabled={busy} onClick={() => void changeStatus('resolved')}>
                סימון &quot;טופלה&quot;
              </button>
            )}
            {r.status !== 'new' && (
              <button type="button" className="adm-link-btn" disabled={busy} onClick={() => void changeStatus('new')}>
                החזרה ל&quot;חדשה&quot;
              </button>
            )}
          </div>
          <p className="adm-quiet">הלקוח רואה את הסטטוס ב&quot;הפניות שלי&quot; בתוך העזרה. התשובה עצמה — במייל.</p>
        </section>
      )}

      <ConfirmAction
        open={confirmEnter}
        title="כניסה לאירוע לצורך תמיכה"
        body={
          <p>
            תיכנסו לממשק בדיוק כמו בעלי האירוע. כל פעולה שתבצעו שם היא פעולה אמיתית באירוע. הכניסה נרשמת ביומן.
          </p>
        }
        confirmLabel="כניסה"
        busy={busy}
        error={actionError}
        onConfirm={enter}
        onCancel={() => setConfirmEnter(false)}
      />
    </div>
  )
}
