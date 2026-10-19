import { useState } from 'react'
import { adminHttp } from '../../adminApi'
import { routeHref } from '../../route'
import { Advanced, ErrorState, Loading, fmtDate, fmtDateTime, useAsync, useCan, useToast } from '../../ui'

type Problem = 'missing' | 'invalid' | 'whatsapp'

interface PhoneAlertGuest {
  guest_id: number
  guest_name: string
  phone: string
  problem: Problem
  alerted_at: string | null
}

interface PhoneAlertEvent {
  event_id: number
  event_label: string
  event_date: string
  guests: PhoneAlertGuest[]
}

const PROBLEM_LABELS: Record<Problem, string> = {
  missing: 'אין מספר',
  invalid: 'המספר לא תקין',
  whatsapp: 'WhatsApp לא מגיע למספר',
}

/**
 * "מספרים שצריך לתקן" — לכל אירוע: מי עוד לא ענה ואין לו מספר שאפשר לשלוח
 * אליו. "להתריע לזוג" מציג לבעלי האירוע את המוזמנים בהתראה במסך המוזמנים,
 * עם כפתור תיקון; ההתראה נסגרת מעצמה כשהמספר משתנה.
 */
export function PhoneAlerts() {
  const data = useAsync(
    () => adminHttp.getJson<{ events: PhoneAlertEvent[] }>('/admin/rsvp/phone-alerts'),
    [],
  )
  const can = useCan()
  const toast = useToast()
  const [busy, setBusy] = useState<string | null>(null)

  const alert = async (key: string, ids: number[]) => {
    setBusy(key)
    try {
      const r = await adminHttp.sendJson<{ alerted: number }>('/admin/rsvp/phone-alerts', 'POST', { guest_ids: ids })
      toast(r.alerted === 1 ? 'בעלי האירוע יראו התראה על המספר' : `בעלי האירוע יראו התראה על ${r.alerted} מספרים`)
      data.reload()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'ההתראה לא נשלחה', 'bad')
    } finally {
      setBusy(null)
    }
  }

  if (data.loading && !data.data) return <Loading />
  if (data.error && !data.data) return <ErrorState message={data.error} onRetry={data.reload} />
  const events = data.data?.events ?? []
  if (events.length === 0) return null
  const total = events.reduce((n, e) => n + e.guests.length, 0)
  const allowed = can('messages.alert')

  return (
    <Advanced title={`מספרים שצריך לתקן (${total})`}>
      <ul className="adm-list">
        {events.map((e) => {
          const pending = e.guests.filter((g) => !g.alerted_at)
          return (
            <li key={e.event_id} className="adm-phone-event">
              <div className="adm-list-row">
                <span className="adm-sev adm-sev-info">{e.guests.length}</span>
                <span className="adm-list-main">
                  <a className="adm-list-title adm-link" href={routeHref('people', `e${e.event_id}`)}>{e.event_label}</a>
                  <span className="adm-list-sub">
                    {fmtDate(e.event_date)}
                    {pending.length < e.guests.length ? ` · כבר התרענו על ${e.guests.length - pending.length}` : ''}
                  </span>
                </span>
                {allowed && pending.length > 0 && (
                  <button
                    type="button"
                    className="adm-btn adm-btn-sm"
                    disabled={busy !== null}
                    onClick={() => alert(`e${e.event_id}`, pending.map((g) => g.guest_id))}
                  >
                    {pending.length === 1 ? 'להתריע לזוג' : `להתריע לזוג על ${pending.length}`}
                  </button>
                )}
              </div>
              <ul className="adm-plain-list adm-phone-guests">
                {e.guests.map((g) => (
                  <li key={g.guest_id}>
                    <span>{g.guest_name}</span>
                    <span className="adm-muted">
                      {' · '}{PROBLEM_LABELS[g.problem]}
                      {g.phone ? <> · <span dir="ltr">{g.phone}</span></> : null}
                      {g.alerted_at ? ` · התראה נשלחה ${fmtDateTime(g.alerted_at)}` : ''}
                    </span>
                    {allowed && !g.alerted_at && (
                      <button
                        type="button"
                        className="adm-link adm-phone-one"
                        disabled={busy !== null}
                        onClick={() => alert(`g${g.guest_id}`, [g.guest_id])}
                      >
                        להתריע
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </li>
          )
        })}
      </ul>
    </Advanced>
  )
}
