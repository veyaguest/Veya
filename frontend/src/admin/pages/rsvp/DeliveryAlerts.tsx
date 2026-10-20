import { useState } from 'react'
import { adminHttp } from '../../adminApi'
import { routeHref } from '../../route'
import { ConfirmAction, EmptyState, ErrorState, Loading, fmtDate, fmtDateTime, useAsync, useCan, useToast } from '../../ui'

/** מוזמן שההודעה האחרונה אליו לא הגיעה (``backend/app/delivery_issues.py``). */
interface DeliveryAlert {
  event_id: number
  event_label: string
  event_date: string
  guest_id: number
  guest_name: string
  phone: string
  message_type: string
  message_label: string
  failed_at: string | null
  code: number | null
  raw_reason: string
  reason: 'marketing_cap' | 'marketing_opt_out' | 'undeliverable' | 'failed_other'
  title: string
  detail: string
  /** guest = משהו אצל המוזמן; veya = אצלנו (תבנית/חשבון) — משפיע על כולם. */
  side: 'guest' | 'veya'
  attempts: number
  resend_at: string | null
  has_open_call: boolean
  /** הצוות העביר לבעלי האירוע לשלוח מה-WhatsApp האישי. */
  handed_off_at: string | null
  /** בעלי האירוע פתחו את WhatsApp לשליחה. */
  couple_opened_at: string | null
  can_hand_off: boolean
}

interface ResendResult {
  sent: number
  failed: number
  unknown: number
  not_sent: number
  outcome: string
  detail: string
}

/**
 * "הודעות שלא הגיעו" — לכל מוזמן: למה (בעברית, לפי קוד Meta), האם זה אצלו או
 * אצלנו, מה VEYA כבר עושה (ניסיון אוטומטי / תור שיחות), וכפתור "לשלוח שוב".
 * השרת בודק הכול שוב לפני שליחה — לחיצה כפולה לא שולחת פעמיים.
 */
export function DeliveryAlerts() {
  const data = useAsync(
    () => adminHttp.getJson<{ alerts: DeliveryAlert[] }>('/admin/rsvp/delivery-alerts'),
    [],
  )
  const can = useCan()
  const toast = useToast()
  const [target, setTarget] = useState<DeliveryAlert | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [handingOff, setHandingOff] = useState<number | null>(null)
  const handOff = async (a: DeliveryAlert) => {
    setHandingOff(a.guest_id)
    try {
      await adminHttp.sendJson(`/admin/rsvp/delivery-alerts/${a.guest_id}/handoff`, 'POST')
      toast(`${a.guest_name}: בעלי האירוע יראו כפתור לשליחה מה-WhatsApp שלהם`)
      data.reload()
    } catch (e) {
      toast(e instanceof Error ? e.message : 'ההעברה לא בוצעה', 'bad')
    } finally {
      setHandingOff(null)
    }
  }

  const resend = async () => {
    if (!target) return
    setBusy(true)
    setError(null)
    try {
      const r = await adminHttp.sendJson<ResendResult>(
        `/admin/rsvp/delivery-alerts/${target.guest_id}/resend`, 'POST',
      )
      toast(`${target.guest_name}: ${r.outcome}`, r.sent || r.unknown ? 'ok' : 'bad')
      setTarget(null)
      data.reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'השליחה לא בוצעה')
    } finally {
      setBusy(false)
    }
  }

  const alerts = data.data?.alerts ?? []
  return (
    <section className="adm-section" aria-labelledby="adm-delivery-title">
      <div className="adm-section-head">
        <h2 className="adm-section-title" id="adm-delivery-title">
          הודעות שלא הגיעו{alerts.length ? ` (${alerts.length})` : ''}
        </h2>
      </div>
      {data.loading && !data.data ? (
        <Loading />
      ) : data.error && !data.data ? (
        <ErrorState message={data.error} onRetry={data.reload} />
      ) : alerts.length === 0 ? (
        <EmptyState title="כל ההודעות האחרונות הגיעו" text="מוזמן שהודעה לא תגיע אליו יופיע כאן, עם הסיבה." />
      ) : (
        <ul className="adm-list">
          {alerts.map((a) => (
            <li key={a.guest_id}>
              <div className="adm-list-row">
                <span className={`adm-sev ${a.side === 'veya' ? 'adm-sev-critical' : 'adm-sev-warning'}`}>
                  {a.side === 'veya' ? 'אצלנו' : 'אצל המוזמן'}
                </span>
                <span className="adm-list-main">
                  <span className="adm-list-title">
                    {a.guest_name} · {a.message_label} — {a.title}
                  </span>
                  <span className="adm-list-sub">{a.detail}</span>
                  <span className="adm-list-sub">
                    <a className="adm-link" href={routeHref('people', `e${a.event_id}`)}>{a.event_label}</a>
                    {a.event_date ? ` · ${fmtDate(a.event_date)}` : ''}
                    {' · '}<span dir="ltr">{a.phone}</span>
                    {' · '}לא הגיעה {fmtDateTime(a.failed_at)}
                    {a.attempts > 1 ? ` · ${a.attempts} ניסיונות` : ''}
                  </span>
                  {(a.resend_at || a.has_open_call || a.handed_off_at) && (
                    <span className="adm-list-sub">
                      {[
                        a.resend_at ? `ניסיון אוטומטי נוסף: ${fmtDateTime(a.resend_at)}` : '',
                        a.has_open_call ? 'נמצא בתור השיחות' : '',
                        a.couple_opened_at
                          ? `בעלי האירוע פתחו WhatsApp לשליחה ${fmtDateTime(a.couple_opened_at)}`
                          : a.handed_off_at ? `הועבר לבעלי האירוע ${fmtDateTime(a.handed_off_at)}` : '',
                      ].filter(Boolean).join(' · ')}
                    </span>
                  )}
                  <span className="adm-list-sub adm-muted">
                    {a.code != null ? `קוד ${a.code}` : 'בלי קוד'}
                    {a.raw_reason ? ` · Meta: ${a.raw_reason}` : ''}
                  </span>
                </span>
                <span className="adm-alert-actions">
                  {can('messages.resend') && !a.couple_opened_at && (
                    <button type="button" className="adm-btn adm-btn-sm" onClick={() => { setError(null); setTarget(a) }}>
                      לשלוח שוב
                    </button>
                  )}
                  {/* כשהניסיון האוטומטי כבר לא יעזור — בעלי האירוע שולחים מה-WhatsApp האישי. */}
                  {can('messages.alert') && !a.resend_at && !a.handed_off_at && a.can_hand_off && (
                    <button
                      type="button"
                      className="adm-btn adm-btn-sm"
                      disabled={handingOff !== null}
                      onClick={() => handOff(a)}
                    >
                      להעביר לבעלי האירוע
                    </button>
                  )}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}

      <ConfirmAction
        open={target != null}
        title={target ? `לשלוח שוב ל${target.guest_name}?` : ''}
        body={
          target && (
            <>
              <p>{`${target.message_label} תישלח שוב, פעם אחת, למספר ${target.phone}.`}</p>
              {target.side === 'veya' && (
                <p><strong>הסיבה אצלנו:</strong> אם היא עוד לא תוקנה, גם הניסיון הזה לא יגיע.</p>
              )}
              {target.reason === 'marketing_opt_out' && (
                <p>המוזמן ויתר על הודעות פרסום ב-WhatsApp — סביר שגם הניסיון הזה לא יגיע.</p>
              )}
              {target.resend_at && <p>{`כבר מתוכנן ניסיון אוטומטי ב-${fmtDateTime(target.resend_at)}.`}</p>}
            </>
          )
        }
        confirmLabel="לשלוח שוב"
        busy={busy}
        error={error}
        onConfirm={resend}
        onCancel={() => setTarget(null)}
      />
    </section>
  )
}
