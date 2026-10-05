/**
 * תובנות עזרה — על מה המשתמשים נתקעים (HELP_CENTER_PLAN.md §12.3, שלב 8).
 *
 * ספירות בלבד ל-7/30 הימים האחרונים. אין כאן אף משתמש, אף אירוע ואף טקסט:
 * הטבלה ``help_events`` לא מחזיקה זהות, ורק משתמשים שאישרו "סטטיסטיקה ושיפור"
 * נספרים. בלי גרפים ב-MVP.
 */
import { fetchHelpInsights, type HelpInsights } from '../../adminApi'
import { navigate, type AdminRoute } from '../../route'
import { EmptyState, ErrorState, Loading, PageHeader, Tabs, fmtNumber, useAsync } from '../../ui'

const ENTRY_LABEL: Record<string, string> = {
  launcher: 'כפתור "עזרה"',
  error_hint: '"צריכים עזרה עם זה?" ליד שגיאה',
  tour_back: 'חזרה מהדרכה',
}

export function HelpInsightsPage({ route }: { route: AdminRoute }) {
  const days: 7 | 30 = route.params.get('days') === '30' ? 30 : 7
  const { data, error, loading, reload } = useAsync(() => fetchHelpInsights(days), [days])
  return (
    <div className="adm-page">
      <PageHeader
        title="תובנות עזרה"
        subtitle="ספירות בלבד, בלי זהות · נספרים רק משתמשים שאישרו סטטיסטיקה ושיפור"
      />
      <Tabs<'7' | '30'>
        label="תקופה"
        active={String(days) as '7' | '30'}
        onChange={(v) => navigate('insights', null, { days: v === '7' ? null : v }, { replace: true })}
        tabs={[
          { key: '7', label: '7 ימים' },
          { key: '30', label: '30 ימים' },
        ]}
      />
      {loading && !data ? (
        <Loading />
      ) : error && !data ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data || data.events === 0 ? (
        <EmptyState title="אין עדיין נתונים לתקופה הזו" text="כשמשתמשים יפתחו את העזרה, הספירות יופיעו כאן." />
      ) : (
        <InsightsBody data={data} />
      )}
    </div>
  )
}

function n(v: unknown): string {
  return fmtNumber(typeof v === 'number' ? v : 0)
}

function InsightsBody({ data }: { data: HelpInsights }) {
  return (
    <>
      <section className="adm-section" aria-labelledby="hi-summary">
        <h2 className="adm-section-title" id="hi-summary">בקצרה</h2>
        <table className="adm-table adm-table-plain">
          <tbody>
            <tr><th scope="row">פתיחות של העזרה</th><td>{n(data.sessions)}</td></tr>
            <tr><th scope="row">התחילו פנייה לצוות</th><td>{n(data.escalations.started)}</td></tr>
            <tr><th scope="row">שלחו פנייה לצוות</th><td>{n(data.escalations.submitted)}</td></tr>
          </tbody>
        </table>
        {data.entries.length > 0 && (
          <p className="adm-quiet">
            {data.entries.map((e) => `${ENTRY_LABEL[e.entry] ?? e.entry}: ${n(e.count)}`).join(' · ')}
          </p>
        )}
      </section>

      <InsightsTable
        title="איפה פותחים את העזרה"
        head={['מסך', 'פתיחות']}
        rows={data.opened_by_screen.map((r) => [r.screen, n(r.count)])}
      />
      <InsightsTable
        title="נושאים"
        head={['נושא', 'נבחר', 'עזר', 'לא עזר']}
        rows={data.topics.map((r) => [r.topic_id, n(r.selected), n(r.helped), n(r.not_helped)])}
      />
      <InsightsTable
        title="הדרכות"
        head={['הדרכה', 'התחילו', 'הסתיימו', 'נעצרו', 'כפתור לא נמצא', 'שגיאה']}
        rows={data.tours.map((r) => [r.flow_id, n(r.started), n(r.completed), n(r.abandoned), n(r.target_missing), n(r.error)])}
        note={'"כפתור לא נמצא" = המסך השתנה וההדרכה לא עודכנה — לבדוק.'}
      />
      <InsightsTable
        title="בדיקות תקלה"
        head={['בדיקה', 'התחילו', 'לא זוהה', 'לא עזר', 'פנו לצוות']}
        rows={data.trees.map((r) => [r.tree_id, n(r.started), n(r.resolution_unknown), n(r.not_helped), n(r.escalated)])}
      />
      <InsightsTable
        title="חיפושים בלי תוצאות"
        head={['מסך', 'פעמים']}
        rows={data.no_results.map((r) => [r.screen, n(r.count)])}
        note="הטקסט שחיפשו לא נשמר — רק שהיה חיפוש כזה, ובאיזה מסך."
      />
    </>
  )
}

function InsightsTable({ title, head, rows, note }: { title: string; head: string[]; rows: string[][]; note?: string }) {
  if (rows.length === 0) return null
  return (
    <section className="adm-section">
      <h2 className="adm-section-title">{title}</h2>
      <div className="adm-table-wrap">
        <table className="adm-table">
          <thead>
            <tr>{head.map((h) => <th key={h} scope="col">{h}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>{r.map((c, j) => <td key={j}>{j === 0 ? <code>{c}</code> : c}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
      {note && <p className="adm-quiet">{note}</p>}
    </section>
  )
}
