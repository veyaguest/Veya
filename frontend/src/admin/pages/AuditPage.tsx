import { useEffect, useState } from 'react'
import { fetchAudit, type AuditEntry, type AuditQuery } from '../adminApi'
import { navigate, type AdminRoute } from '../route'
import { EmptyState, ErrorState, Loading, PageHeader, fmtDateTime, useAsync } from '../ui'

const PAGE = 50

export function AuditPage({ route }: { route: AdminRoute }) {
  const [q, setQ] = useState(route.params.get('q') ?? '')
  const [domain, setDomain] = useState(route.params.get('domain') ?? '')
  const [actor, setActor] = useState(route.params.get('actor') ?? '')
  const [from, setFrom] = useState(route.params.get('from') ?? '')
  const [to, setTo] = useState(route.params.get('to') ?? '')
  const [offset, setOffset] = useState(0)
  const [debounced, setDebounced] = useState(q)
  const [filtersOpen, setFiltersOpen] = useState(false)

  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(q), 250)
    return () => window.clearTimeout(t)
  }, [q])

  useEffect(() => {
    setOffset(0)
  }, [debounced, domain, actor, from, to])

  const query: AuditQuery = {
    q: debounced,
    domain,
    actor_id: actor ? Number(actor) : null,
    date_from: from,
    date_to: to,
    target_type: route.params.get('target_type') ?? '',
    target_id: route.params.get('target_id') ?? '',
    limit: PAGE,
    offset,
  }
  const { data, error, loading, reload } = useAsync(
    () => fetchAudit(query),
    [debounced, domain, actor, from, to, offset, route.params.toString()],
  )

  const activeFilters = [domain, actor, from, to].filter(Boolean).length

  return (
    <div className="adm-page">
      <PageHeader title="יומן פעילות" subtitle="פעולות אדמין בלבד — מי, מה, מתי ומה השתנה" />

      <div className="adm-toolbar">
        <input
          type="search"
          className="adm-input adm-toolbar-search"
          placeholder="חיפוש ביומן…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="חיפוש ביומן"
        />
        <button
          type="button"
          className="adm-btn adm-filters-toggle"
          onClick={() => setFiltersOpen((v) => !v)}
          aria-expanded={filtersOpen}
        >
          סינון{activeFilters ? ` (${activeFilters})` : ''}
        </button>
        <div className={`adm-filters${filtersOpen ? ' is-open' : ''}`}>
          <select className="adm-input" value={domain} onChange={(e) => setDomain(e.target.value)} aria-label="תחום">
            <option value="">כל התחומים</option>
            {data &&
              Object.entries(data.domains).map(([k, label]) => (
                <option key={k} value={k}>{label}</option>
              ))}
          </select>
          <select className="adm-input" value={actor} onChange={(e) => setActor(e.target.value)} aria-label="אדמין">
            <option value="">כל האדמינים</option>
            {data?.actors.map((a) => (
              <option key={a.id} value={a.id}>{a.label}</option>
            ))}
          </select>
          <label className="adm-inline-field">
            <span>מתאריך</span>
            <input type="date" className="adm-input" value={from} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className="adm-inline-field">
            <span>עד</span>
            <input type="date" className="adm-input" value={to} onChange={(e) => setTo(e.target.value)} />
          </label>
          {(activeFilters > 0 || route.params.get('target_id')) && (
            <button
              type="button"
              className="adm-link-btn"
              onClick={() => {
                setDomain('')
                setActor('')
                setFrom('')
                setTo('')
                navigate('audit', null, { q }, { replace: true })
              }}
            >
              ניקוי
            </button>
          )}
        </div>
      </div>

      {loading && !data ? (
        <Loading />
      ) : error && !data ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          title="אין פעולות להצגה"
          text={debounced || activeFilters ? 'נסו לשנות את החיפוש או הסינון.' : 'פעולות אדמין יופיעו כאן מרגע שיבוצעו.'}
        />
      ) : (
        <>
          <ol className="adm-audit">
            {data.items.map((row) => (
              <AuditRow key={row.id} row={row} />
            ))}
          </ol>
          <Pager total={data.total} offset={offset} limit={PAGE} onChange={setOffset} />
        </>
      )}
    </div>
  )
}

function AuditRow({ row }: { row: AuditEntry }) {
  return (
    <li className="adm-audit-row">
      <div className="adm-audit-meta">
        <span className="adm-audit-actor">{row.actor_label || 'אדמין שנמחק'}</span>
        <span className="adm-audit-time">{fmtDateTime(row.created_at)}</span>
      </div>
      <div className="adm-audit-body">
        <div className="adm-audit-summary">
          {row.summary}
          <span className="adm-audit-domain">{row.domain_label}</span>
        </div>
        {row.changes.length > 0 && (
          <ul className="adm-audit-changes">
            {row.changes.map((c, i) => (
              <li key={i}>
                <span className="adm-muted">{c.label}:</span>{' '}
                <span className="adm-before">{c.before}</span>
                <span aria-hidden="true"> ← </span>
                <span className="adm-after">{c.after}</span>
              </li>
            ))}
          </ul>
        )}
        {row.reason && <p className="adm-audit-reason">סיבה: {row.reason}</p>}
      </div>
    </li>
  )
}

export function Pager({
  total,
  offset,
  limit,
  onChange,
}: {
  total: number
  offset: number
  limit: number
  onChange: (offset: number) => void
}) {
  if (total <= limit) return null
  const from = offset + 1
  const to = Math.min(offset + limit, total)
  return (
    <div className="adm-pager">
      <span className="adm-muted">
        {from}–{to} מתוך {total}
      </span>
      <div className="adm-pager-btns">
        <button type="button" className="adm-btn" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          הקודם
        </button>
        <button type="button" className="adm-btn" disabled={to >= total} onClick={() => onChange(offset + limit)}>
          הבא
        </button>
      </div>
    </div>
  )
}
