import { fetchAdminOverview, type AdminOverview } from '../adminApi'
import { routeHref, type AdminPageKey } from '../route'
import { ErrorState, Loading, ModulePill, PageHeader, fmtDate, fmtNumber, useAsync } from '../ui'

const SEVERITY_LABEL = { critical: 'דחוף', warning: 'לטיפול', info: 'לידיעה' } as const

export function DashboardPage({ onLoaded }: { onLoaded?: (o: AdminOverview) => void }) {
  const { data, error, loading, reload } = useAsync(async () => {
    const o = await fetchAdminOverview()
    onLoaded?.(o)
    return o
  }, [])

  if (loading && !data) return <Loading />
  if (error && !data) return <ErrorState message={error} onRetry={reload} />
  if (!data) return null

  const p = data.pulse
  const stats: { label: string; value: number; hint?: string; tone?: 'warn' }[] = [
    { label: 'משתמשים פעילים', value: p.active_users, hint: `התחברו ב-${p.active_users_days} ימים` },
    { label: 'אירועים קרובים', value: p.upcoming_events, hint: 'מהיום והלאה' },
    { label: 'אירועים חדשים', value: p.new_events, hint: `ב-${p.new_events_days} ימים` },
    { label: 'אירועים שדורשים טיפול', value: p.events_needing_attention, tone: p.events_needing_attention ? 'warn' : undefined },
    { label: 'בקשות ממתינות', value: p.pending_requests, tone: p.pending_requests ? 'warn' : undefined },
    { label: 'אזהרות מערכת', value: p.warnings, tone: p.warnings ? 'warn' : undefined },
  ]

  return (
    <div className="adm-page">
      <PageHeader
        title="ראשי"
        subtitle={`היום · ${fmtDate(data.today)}`}
        actions={
          <button type="button" className="adm-btn" onClick={reload} disabled={loading}>
            {loading ? 'מרענן…' : 'רענון'}
          </button>
        }
      />

      <section aria-label="מצב VEYA" className="adm-stats">
        {stats.map((s) => (
          <div key={s.label} className={`adm-stat${s.tone === 'warn' ? ' is-warn' : ''}`}>
            <span className="adm-stat-value">{fmtNumber(s.value)}</span>
            <span className="adm-stat-label">{s.label}</span>
            {s.hint && <span className="adm-stat-hint">{s.hint}</span>}
          </div>
        ))}
      </section>

      <section className="adm-section" aria-labelledby="adm-attention-title">
        <div className="adm-section-head">
          <h2 className="adm-section-title" id="adm-attention-title">דורש תשומת לב</h2>
        </div>
        {data.attention.length === 0 ? (
          <p className="adm-quiet">אין כרגע משהו שדורש פעולה.</p>
        ) : (
          <ul className="adm-list">
            {data.attention.map((item) => (
              <li key={item.key}>
                <a className="adm-list-row" href={routeHref(item.page as AdminPageKey)}>
                  <span className={`adm-sev adm-sev-${item.severity}`}>{SEVERITY_LABEL[item.severity]}</span>
                  <span className="adm-list-main">
                    <span className="adm-list-title">{item.title}</span>
                    <span className="adm-list-sub">{item.detail}</span>
                  </span>
                  <span className="adm-list-count">{fmtNumber(item.count)}</span>
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="adm-section" aria-labelledby="adm-modules-title">
        <div className="adm-section-head">
          <h2 className="adm-section-title" id="adm-modules-title">מצב המערכת</h2>
        </div>
        <table className="adm-table adm-table-plain">
          <tbody>
            {data.modules.map((m) => (
              <tr key={m.key}>
                <th scope="row">{m.label}</th>
                <td className="adm-col-status"><ModulePill state={m.status} /></td>
                <td className="adm-muted">{m.detail}</td>
                <td className="adm-col-action">
                  {m.page && (
                    <a className="adm-link" href={routeHref(m.page as AdminPageKey)}>
                      ניהול
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  )
}
