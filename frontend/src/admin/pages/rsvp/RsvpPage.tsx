import { MessageDefaultOptionsManager, MessageDefaultsManager } from '../../../components/AdminPage'
import { adminHttp, qs } from '../../adminApi'
import { addDays, israelToday, weekday } from '../../callOpsApi'
import { navigate, routeHref, type AdminRoute } from '../../route'
import { DeliveryAlerts } from './DeliveryAlerts'
import { PhoneAlerts } from './PhoneAlerts'
import {
  Advanced,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  StatusPill,
  fmtDate,
  fmtDateTime,
  fmtNumber,
  useAsync,
} from '../../ui'

interface Overview {
  /** האם עדכוני המסירה מ-Meta מגיעים (``admin_rsvp._webhook_health``). */
  webhook: { relevant: boolean; last_update: string | null; recent_real_sends: number; stale: boolean }
  date: string
  today: string
  whatsapp_mode: string
  emergency_stop: boolean
  active_tracks: number
  totals: Partial<Record<'whatsapp' | 'calls', { events: number; guests: number }>>
  steps: { event_id: number; event_label: string; event_date: string; type: string; label: string; audience: number; send_time: string }[]
  sent_today: { total: number; failed: number }
  not_started: { event_id: number; event_label: string; event_date: string; guests: number }[]
}

export function RsvpPage({ route }: { route: AdminRoute }) {
  const today = israelToday()
  const date = route.params.get('date') || today
  const data = useAsync(() => adminHttp.getJson<Overview>(`/admin/rsvp/overview${qs({ date })}`), [date])
  const d = data.data
  const setDate = (v: string) => navigate('rsvp', null, v === today ? {} : { date: v }, { replace: true })

  return (
    <div className="adm-page">
      <PageHeader
        title="אישורי הגעה"
        subtitle="מה יוצא לפי לוח הזמנים של כל אירוע. הכללים עצמם — ב'כללי המערכת'."
        actions={<a className="adm-btn" href={routeHref('rules')}>כללי המערכת</a>}
      />

      <div className="adm-datebar">
        <div className="adm-datebar-current">
          <span className="adm-datebar-label">{date === today ? 'היום' : `יום ${weekday(date)}`}</span>
          <span className="adm-datebar-date">{fmtDate(date)}</span>
        </div>
        <div className="adm-datebar-nav">
          <button type="button" className="adm-btn adm-btn-sm" onClick={() => setDate(addDays(date, -1))} aria-label="יום קודם">→</button>
          <button type="button" className={`adm-seg${date === today ? ' is-on' : ''}`} onClick={() => setDate(today)}>היום</button>
          <button type="button" className={`adm-seg${date === addDays(today, 1) ? ' is-on' : ''}`} onClick={() => setDate(addDays(today, 1))}>מחר</button>
          <button type="button" className="adm-btn adm-btn-sm" onClick={() => setDate(addDays(date, 1))} aria-label="יום הבא">←</button>
          <input type="date" className="adm-input adm-input-sm" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} aria-label="בחירת תאריך" />
        </div>
      </div>

      {data.loading && !d ? (
        <Loading />
      ) : data.error && !d ? (
        <ErrorState message={data.error} onRetry={data.reload} />
      ) : d ? (
        <>
          {d.emergency_stop && (
            <div className="adm-banner adm-banner-bad" role="alert">
              <strong>עצירת חירום פעילה</strong> — ההודעות שמתוכננות כאן לא ייצאו.
              <a className="adm-link" href={routeHref('rules', null, { domain: 'whatsapp' })}>ניהול</a>
            </div>
          )}
          <section className="adm-stats adm-stats-5" aria-label="מצב">
            <div className="adm-stat"><span className="adm-stat-value">{fmtNumber(d.active_tracks)}</span><span className="adm-stat-label">מסלולים פעילים</span></div>
            <div className="adm-stat"><span className="adm-stat-value">{fmtNumber(d.totals.whatsapp?.events ?? 0)}</span><span className="adm-stat-label">אירועים עם WhatsApp ביום הזה</span></div>
            <div className="adm-stat"><span className="adm-stat-value">{fmtNumber(d.totals.calls?.events ?? 0)}</span><span className="adm-stat-label">אירועים עם סבב שיחות</span></div>
            <div className="adm-stat"><span className="adm-stat-value">{fmtNumber(d.sent_today.total)}</span><span className="adm-stat-label">הודעות שיצאו היום</span></div>
            <div className={`adm-stat${d.sent_today.failed ? ' is-bad' : ''}`}><span className="adm-stat-value">{fmtNumber(d.sent_today.failed)}</span><span className="adm-stat-label">נכשלו היום</span></div>
          </section>
          {d.webhook.stale && (
            <div className="adm-banner adm-banner-bad" role="alert">
              <strong>עדכוני המסירה מ-WhatsApp לא מגיעים.</strong> ב-24 השעות האחרונות יצאו{' '}
              {fmtNumber(d.webhook.recent_real_sends)} הודעות ואף אחת לא קיבלה עדכון מ-Meta. עד שזה יתוקן,
              הסטטוס בעמוד אישורי ההגעה של הזוג נשאר "נשלחה", והודעות שלא הגיעו לא יופיעו כאן. כדאי לבדוק
              את חיבור ה-webhook ב-Meta ואת ההגדרות בשרת.
            </div>
          )}
          <p className="adm-quiet">
            מצב WhatsApp: {d.whatsapp_mode === 'live' ? 'שליחה אמיתית' : d.whatsapp_mode === 'meta_test' ? 'בדיקה — רק למספרים המורשים' : 'הדגמה — ההודעות לא מגיעות למוזמנים'}
            {d.webhook.relevant && (
              <> · עדכון מסירה אחרון מ-WhatsApp: {d.webhook.last_update ? fmtDateTime(d.webhook.last_update) : 'עוד לא התקבל'}</>
            )}
          </p>

          <DeliveryAlerts />
          <PhoneAlerts />

          <section className="adm-section">
            <div className="adm-section-head"><h2 className="adm-section-title">מה מתוכנן ביום הזה</h2></div>
            {d.steps.length === 0 ? (
              <EmptyState title="אין שלבים מתוכננים ליום הזה" />
            ) : (
              <div className="adm-table-wrap">
                <table className="adm-table">
                  <thead>
                    <tr><th>אירוע</th><th>שלב</th><th className="adm-num">מי שעדיין לא אישר</th><th className="adm-hide-md">שעה</th></tr>
                  </thead>
                  <tbody>
                    {d.steps.map((s, i) => (
                      <tr key={i} className="is-clickable" tabIndex={0} onClick={() => navigate('people', `e${s.event_id}`)} onKeyDown={(e) => e.key === 'Enter' && navigate('people', `e${s.event_id}`)}>
                        <td><div className="adm-cell-title">{s.event_label}</div><div className="adm-cell-sub">{fmtDate(s.event_date)}</div></td>
                        <td>
                          <StatusPill tone={s.type === 'call_round' ? 'info' : 'neutral'}>{s.type === 'call_round' ? 'טלפון' : 'WhatsApp'}</StatusPill>{' '}
                          {s.label}
                        </td>
                        <td className="adm-num">{s.audience}</td>
                        <td className="adm-hide-md adm-muted">{s.send_time || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {d.not_started.length > 0 && (
            <Advanced title={`אירועים ב-45 הימים הקרובים שעוד לא הפעילו אישורי הגעה (${d.not_started.length})`}>
              <ul className="adm-plain-list">
                {d.not_started.map((e) => (
                  <li key={e.event_id}>
                    <a className="adm-link" href={routeHref('people', `e${e.event_id}`)}>{e.event_label}</a>
                    <span className="adm-muted"> · {fmtDate(e.event_date)} · {e.guests} מוזמנים</span>
                  </li>
                ))}
              </ul>
            </Advanced>
          )}
        </>
      ) : null}

      <Advanced title="ספריית ההודעות וברירות המחדל">
        <div className="adm-legacy">
          <MessageDefaultsManager />
          <MessageDefaultOptionsManager />
        </div>
      </Advanced>
    </div>
  )
}
