import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  callCenterGuest,
  callCenterOverview,
  callCenterQueue,
  callCenterRecordOutcome,
} from '../api'
import type {
  CallCenterEventRow,
  CallCenterGuestDetail,
  CallCenterGuestRow,
  CallCenterOverview,
  CallOutcome,
  Side,
} from '../types'
import { getEventTerms, sidePhrase } from '../strings/eventTypes'
import './AdminCallCenter.css'

/**
 * Call Center — מסך השיחות של האדמין.
 *
 * המסך לא מנהל תאריכים משלו: הוא מציג בדיוק את מה שה-Backend גוזר מ-Workflow
 * אישורי ההגעה (backend/app/call_center.py). אירוע שסבב השיחות הבא שלו עוד
 * לא הגיע פשוט לא מופיע כאן, ומוזמן שכבר אישר או ביטל יורד מהתור מיד — בין
 * אם דרך WhatsApp, דרך בעל/ת האירוע, או דרך המסך הזה.
 */

const PAGE_SIZE = 50

/** תוצאות השיחה, בסדר שבו הן מוצגות למוקדן. */
const OUTCOME_BUTTONS: {
  key: CallOutcome
  icon: string
  label: string
  tone: 'good' | 'bad' | 'neutral'
}[] = [
  { key: 'confirmed', icon: '✅', label: 'אישר הגעה', tone: 'good' },
  { key: 'declined', icon: '❌', label: 'לא מגיע', tone: 'bad' },
  { key: 'no_answer', icon: '📞', label: 'לא ענה', tone: 'neutral' },
  { key: 'callback', icon: '📅', label: 'לחזור מאוחר יותר', tone: 'neutral' },
  { key: 'busy', icon: '☎️', label: 'תפוס', tone: 'neutral' },
  { key: 'wrong_number', icon: '❗', label: 'מספר שגוי', tone: 'neutral' },
]

const RSVP_LABELS: Record<string, string> = {
  pending: 'טרם השיב',
  maybe: 'מתלבט',
  confirmed: 'מגיע',
  declined: 'לא מגיע',
}

/**
 * צד המוזמן, בשפה של סוג האירוע שלו (חתן/כלה בחתונה, צד האב/האם בבר מצווה).
 * במסך הזה מוצגים מוזמנים מכמה אירועים במקביל, ולכן מעבירים את סוג האירוע
 * במפורש ולא נשענים על "האירוע הפעיל".
 */
function sideText(side: string, eventType: string): string {
  return sidePhrase(side as Side, getEventTerms(eventType))
}

function formatDateTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleString('he-IL', {
    day: 'numeric',
    month: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** מספר טלפון לחיוג — הדפדפן/הטלפון פותח את החייגן. */
function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, '')}`
}

export function AdminCallCenter() {
  const [overview, setOverview] = useState<CallCenterOverview | null>(null)
  const [rows, setRows] = useState<CallCenterGuestRow[] | null>(null)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState<string | null>(null)

  // סינונים — תצוגתיים בלבד, לא משנים מי צריך שיחה לפי ה-Workflow.
  const [eventId, setEventId] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [roundNumber, setRoundNumber] = useState<number | null>(null)
  const [offset, setOffset] = useState(0)

  const [openGuestId, setOpenGuestId] = useState<number | null>(null)

  const loadOverview = useCallback(() => {
    callCenterOverview()
      .then(setOverview)
      .catch((err) => setError(err instanceof Error ? err.message : 'טעינת מסך השיחות נכשלה'))
  }, [])

  const loadQueue = useCallback(() => {
    callCenterQueue({ eventId, q: query, status, roundNumber, limit: PAGE_SIZE, offset })
      .then((page) => {
        setRows(page.items)
        setTotal(page.total)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'טעינת רשימת השיחות נכשלה'))
  }, [eventId, query, status, roundNumber, offset])

  useEffect(() => {
    loadOverview()
  }, [loadOverview])

  // השהיית חיפוש קלה, כדי לא לירות בקשה על כל תו שנכתב.
  useEffect(() => {
    const timer = window.setTimeout(loadQueue, query ? 250 : 0)
    return () => window.clearTimeout(timer)
  }, [loadQueue, query])

  /** אחרי תיעוד שיחה — רענון התור והמונים, כדי שהמסך תמיד יראה את האמת. */
  function afterOutcome() {
    setOpenGuestId(null)
    loadOverview()
    loadQueue()
  }

  const selectedEvent = useMemo(
    () => overview?.events.find((e) => e.event_id === eventId) ?? null,
    [overview, eventId],
  )

  const availableRounds = useMemo(() => {
    const set = new Set<number>()
    overview?.events.forEach((e) => set.add(e.round_number))
    return [...set].sort((a, b) => a - b)
  }, [overview])

  if (error && !overview) return <div className="admin-error">{error}</div>
  if (!overview) return <div className="admin-loading">טוען…</div>

  return (
    <div className="admin-page cc-page">
      <div className="cc-stats">
        <StatCard label="שיחות בסבב הנוכחי" value={overview.total} />
        <StatCard label="הושלמו" value={overview.done} tone="good" />
        <StatCard label="ממתינות" value={overview.waiting} tone="warn" />
        <StatCard label="אירועים לטיפול" value={overview.events_needing_attention} />
      </div>

      {overview.events.length === 0 ? (
        <div className="cc-empty">
          <div className="cc-empty-icon">☕</div>
          <h3>אין שיחות היום</h3>
          <p>
            אין כרגע אירוע שסבב השיחות שלו הגיע לפי מסלול אישורי ההגעה.
            כשיגיע מועד הסבב הבא, המוזמנים יופיעו כאן אוטומטית.
          </p>
        </div>
      ) : (
        <>
          <h2 className="admin-section-title">אירועים עם שיחות</h2>
          <div className="cc-events">
            {overview.events.map((ev) => (
              <EventCard
                key={ev.event_id}
                event={ev}
                active={eventId === ev.event_id}
                onSelect={() => {
                  setEventId(eventId === ev.event_id ? null : ev.event_id)
                  setOffset(0)
                }}
              />
            ))}
          </div>

          <div className="cc-list-head">
            <h2 className="admin-section-title">
              {selectedEvent ? `שיחות · ${selectedEvent.hosts}` : 'כל השיחות'} ({total})
            </h2>
            <div className="cc-filters">
              <input
                type="search"
                className="adm-search"
                placeholder="חיפוש לפי שם או טלפון…"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value)
                  setOffset(0)
                }}
              />
              <select
                className="cc-select"
                value={eventId ?? ''}
                onChange={(e) => {
                  setEventId(e.target.value ? Number(e.target.value) : null)
                  setOffset(0)
                }}
                aria-label="סינון לפי אירוע"
              >
                <option value="">כל האירועים</option>
                {overview.events.map((ev) => (
                  <option key={ev.event_id} value={ev.event_id}>
                    {ev.hosts}
                  </option>
                ))}
              </select>
              <select
                className="cc-select"
                value={status}
                onChange={(e) => {
                  setStatus(e.target.value)
                  setOffset(0)
                }}
                aria-label="סינון לפי סטטוס"
              >
                <option value="">כל הסטטוסים</option>
                <option value="pending">טרם השיב</option>
                <option value="maybe">מתלבט</option>
              </select>
              <select
                className="cc-select"
                value={roundNumber ?? ''}
                onChange={(e) => {
                  setRoundNumber(e.target.value ? Number(e.target.value) : null)
                  setOffset(0)
                }}
                aria-label="סינון לפי סבב שיחות"
              >
                <option value="">כל הסבבים</option>
                {availableRounds.map((r) => (
                  <option key={r} value={r}>
                    סבב {r}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {error && <div className="admin-error">{error}</div>}

          {rows === null ? (
            <div className="admin-loading">טוען…</div>
          ) : rows.length === 0 ? (
            <div className="cc-empty-inline">אין שיחות שממתינות לפי הסינון הזה.</div>
          ) : (
            <>
              <div className="cc-guests">
                {rows.map((row) => (
                  <GuestRow key={row.guest_id} row={row} onOpen={() => setOpenGuestId(row.guest_id)} />
                ))}
              </div>
              {total > PAGE_SIZE && (
                <div className="cc-pager">
                  <button
                    type="button"
                    className="btn-ghost"
                    disabled={offset === 0}
                    onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  >
                    הקודם
                  </button>
                  <span className="cc-pager-info">
                    {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} מתוך {total}
                  </span>
                  <button
                    type="button"
                    className="btn-ghost"
                    disabled={offset + PAGE_SIZE >= total}
                    onClick={() => setOffset(offset + PAGE_SIZE)}
                  >
                    הבא
                  </button>
                </div>
              )}
            </>
          )}
        </>
      )}

      {openGuestId !== null && (
        <CallDialog
          guestId={openGuestId}
          onClose={() => setOpenGuestId(null)}
          onSaved={afterOutcome}
        />
      )}
    </div>
  )
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone?: 'good' | 'warn'
}) {
  return (
    <div className={`cc-stat ${tone ? `cc-stat-${tone}` : ''}`}>
      <div className="cc-stat-value">{value}</div>
      <div className="cc-stat-label">{label}</div>
    </div>
  )
}

function EventCard({
  event,
  active,
  onSelect,
}: {
  event: CallCenterEventRow
  active: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      className={`cc-event ${active ? 'active' : ''}`}
      onClick={onSelect}
      aria-pressed={active}
    >
      <div className="cc-event-top">
        <span className="cc-event-hosts">{event.hosts}</span>
        <span className="cc-event-count">{event.waiting}</span>
      </div>
      <div className="cc-event-meta">
        <span>{event.round_label}</span>
        <span className="cc-dot">·</span>
        <span>נפתח ב-{event.round_date}</span>
      </div>
      <div className="cc-event-meta cc-event-sub">
        {event.venue_name && <span>{event.venue_name}</span>}
        {event.days_until != null && (
          <>
            {event.venue_name && <span className="cc-dot">·</span>}
            <span>
              {event.days_until === 0
                ? 'האירוע היום'
                : event.days_until > 0
                  ? `עוד ${event.days_until} ימים`
                  : 'האירוע עבר'}
            </span>
          </>
        )}
        {event.done > 0 && (
          <>
            <span className="cc-dot">·</span>
            <span>{event.done} טופלו</span>
          </>
        )}
      </div>
    </button>
  )
}

function GuestRow({ row, onOpen }: { row: CallCenterGuestRow; onOpen: () => void }) {
  return (
    <div className="cc-guest">
      <button type="button" className="cc-guest-main" onClick={onOpen}>
        <div className="cc-guest-name">
          {row.full_name}
          <span className={`cc-chip cc-chip-${row.rsvp_status}`}>
            {RSVP_LABELS[row.rsvp_status] ?? row.rsvp_status}
          </span>
        </div>
        <div className="cc-guest-meta">
          <span dir="ltr">{row.phone}</span>
          <span className="cc-dot">·</span>
          <span>{row.party_size} מוזמנים</span>
          <span className="cc-dot">·</span>
          <span>{sideText(row.side, row.event_type)}</span>
          <span className="cc-dot">·</span>
          <span>{row.event_hosts}</span>
        </div>
        <div className="cc-guest-meta cc-guest-sub">
          <span>סבב {row.round_number}</span>
          <span className="cc-dot">·</span>
          <span>מ-{row.round_date}</span>
          {row.last_outcome_label && (
            <>
              <span className="cc-dot">·</span>
              <span className="cc-last">אחרון: {row.last_outcome_label}</span>
            </>
          )}
          {row.callback_at && (
            <>
              <span className="cc-dot">·</span>
              <span className="cc-last">לחזור ב-{formatDateTime(row.callback_at)}</span>
            </>
          )}
        </div>
      </button>
      <a className="cc-call-btn" href={telHref(row.phone)} aria-label={`חיוג ל${row.full_name}`}>
        📞
      </a>
    </div>
  )
}

/** חלון ביצוע שיחה: פרטי האירוע והמוזמן, פעולות מהירות ויומן פעילות. */
function CallDialog({
  guestId,
  onClose,
  onSaved,
}: {
  guestId: number
  onClose: () => void
  onSaved: () => void
}) {
  const [detail, setDetail] = useState<CallCenterGuestDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<CallOutcome | null>(null)
  const [count, setCount] = useState(1)
  const [guestNote, setGuestNote] = useState('')
  const [callNote, setCallNote] = useState('')
  const [callbackAt, setCallbackAt] = useState('')

  useEffect(() => {
    callCenterGuest(guestId)
      .then((d) => {
        setDetail(d)
        setCount(d.confirmed_count ?? d.party_size)
        setGuestNote(d.guest_note ?? '')
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'טעינת פרטי המוזמן נכשלה'))
  }, [guestId])

  async function save(outcome: CallOutcome) {
    setBusy(true)
    setError(null)
    try {
      await callCenterRecordOutcome(guestId, {
        outcome,
        count: outcome === 'confirmed' ? count : null,
        guest_note: outcome === 'confirmed' || outcome === 'declined' ? guestNote : null,
        note: callNote,
        callback_at:
          outcome === 'callback' && callbackAt ? new Date(callbackAt).toISOString() : null,
      })
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שמירת תוצאת השיחה נכשלה')
      setBusy(false)
    }
  }

  /** תוצאה שדורשת פרטים נוספים נפתחת לטופס; השאר נשמרות בלחיצה אחת. */
  function pick(outcome: CallOutcome) {
    if (outcome === 'confirmed' || outcome === 'callback') {
      setPending(pending === outcome ? null : outcome)
      return
    }
    void save(outcome)
  }

  /** קיצורי "לחזור אליו" — היום / מחר / מותאם אישית. */
  function setCallbackPreset(which: 'today' | 'tomorrow') {
    const d = new Date()
    if (which === 'today') {
      d.setHours(d.getHours() + 3, 0, 0, 0)
    } else {
      d.setDate(d.getDate() + 1)
      d.setHours(10, 0, 0, 0)
    }
    // הפורמט ש-datetime-local מצפה לו, בשעון המקומי.
    const pad = (n: number) => String(n).padStart(2, '0')
    setCallbackAt(
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`,
    )
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog cc-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h3>{detail ? detail.full_name : 'ביצוע שיחה'}</h3>
          <button type="button" className="x" onClick={onClose} aria-label="סגירה">
            ×
          </button>
        </div>

        {!detail ? (
          <div className="dialog-body">
            {error ? <div className="admin-error">{error}</div> : <div className="admin-loading">טוען…</div>}
          </div>
        ) : (
          <div className="dialog-body cc-dialog-body">
            <section className="cc-card">
              <h4 className="cc-card-title">האירוע</h4>
              <dl className="cc-facts">
                <div>
                  <dt>בעלי האירוע</dt>
                  <dd>{detail.hosts}</dd>
                </div>
                <div>
                  <dt>תאריך</dt>
                  <dd>
                    {detail.event_date || '—'}
                    {detail.event_time ? ` · ${detail.event_time}` : ''}
                  </dd>
                </div>
                <div>
                  <dt>אולם</dt>
                  <dd>{detail.venue_name || '—'}</dd>
                </div>
              </dl>
            </section>

            <section className="cc-card">
              <h4 className="cc-card-title">המוזמן</h4>
              <dl className="cc-facts">
                <div>
                  <dt>טלפון</dt>
                  <dd>
                    <a href={telHref(detail.phone)} dir="ltr">
                      {detail.phone || '—'}
                    </a>
                  </dd>
                </div>
                <div>
                  <dt>צד</dt>
                  <dd>{sideText(detail.side, detail.event_type)}</dd>
                </div>
                <div>
                  <dt>מוזמנים</dt>
                  <dd>{detail.party_size}</dd>
                </div>
                <div>
                  <dt>סטטוס</dt>
                  <dd>{RSVP_LABELS[detail.rsvp_status] ?? detail.rsvp_status}</dd>
                </div>
              </dl>
              {(detail.guest_note || detail.notes_raw) && (
                <div className="cc-notes">
                  {detail.guest_note && <p>הערת המוזמן: {detail.guest_note}</p>}
                  {detail.notes_raw && <p>הערה פנימית: {detail.notes_raw}</p>}
                </div>
              )}
            </section>

            <section className="cc-card">
              <h4 className="cc-card-title">תוצאת השיחה</h4>
              <div className="cc-outcomes">
                {OUTCOME_BUTTONS.map((b) => (
                  <button
                    key={b.key}
                    type="button"
                    className={`cc-outcome cc-outcome-${b.tone} ${pending === b.key ? 'open' : ''}`}
                    onClick={() => pick(b.key)}
                    disabled={busy}
                  >
                    <span aria-hidden>{b.icon}</span> {b.label}
                  </button>
                ))}
              </div>

              {pending === 'confirmed' && (
                <div className="cc-extra">
                  <label className="adm-field">
                    <span className="adm-field-label">כמה מגיעים</span>
                    <input
                      className="adm-field-input"
                      type="number"
                      min={1}
                      max={30}
                      value={count}
                      onChange={(e) => setCount(Number(e.target.value))}
                    />
                  </label>
                  <label className="adm-field">
                    <span className="adm-field-label">הערה שהמוזמן מסר</span>
                    <input
                      className="adm-field-input"
                      value={guestNote}
                      onChange={(e) => setGuestNote(e.target.value)}
                      placeholder="נגישות, צמחוני, מגיע עם תינוק…"
                    />
                  </label>
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={busy}
                    onClick={() => save('confirmed')}
                  >
                    {busy ? 'רגע…' : 'שמירת אישור הגעה'}
                  </button>
                </div>
              )}

              {pending === 'callback' && (
                <div className="cc-extra">
                  <div className="cc-presets">
                    <button type="button" className="btn-ghost" onClick={() => setCallbackPreset('today')}>
                      היום
                    </button>
                    <button type="button" className="btn-ghost" onClick={() => setCallbackPreset('tomorrow')}>
                      מחר
                    </button>
                  </div>
                  <label className="adm-field">
                    <span className="adm-field-label">מתי לחזור אליו</span>
                    <input
                      className="adm-field-input"
                      type="datetime-local"
                      value={callbackAt}
                      onChange={(e) => setCallbackAt(e.target.value)}
                    />
                  </label>
                  <button
                    type="button"
                    className="btn-primary"
                    disabled={busy || !callbackAt}
                    onClick={() => save('callback')}
                  >
                    {busy ? 'רגע…' : 'שמירה'}
                  </button>
                </div>
              )}

              <label className="adm-field cc-call-note">
                <span className="adm-field-label">הערה על השיחה (לא נשלחת למוזמן)</span>
                <input
                  className="adm-field-input"
                  value={callNote}
                  onChange={(e) => setCallNote(e.target.value)}
                  placeholder="למשל: ענתה אשתו, ביקשה שנתקשר בערב"
                />
              </label>

              {error && <div className="admin-error">{error}</div>}
            </section>

            <section className="cc-card">
              <h4 className="cc-card-title">היסטוריית פעילות</h4>
              {detail.timeline.length === 0 ? (
                <p className="cc-empty-inline">עוד לא נרשמה פעילות למוזמן הזה.</p>
              ) : (
                <ol className="cc-timeline">
                  {detail.timeline.map((item, i) => (
                    <li key={i} className={`cc-tl-item cc-tl-${item.channel}`}>
                      <span className="cc-tl-icon" aria-hidden>
                        {item.channel === 'phone' ? '📞' : item.channel === 'web' ? '🔗' : '💬'}
                      </span>
                      <div className="cc-tl-body">
                        <div className="cc-tl-label">{item.label}</div>
                        {item.text && <div className="cc-tl-text">{item.text}</div>}
                        <div className="cc-tl-meta">
                          {formatDateTime(item.created_at)}
                          {item.actor ? ` · ${item.actor}` : ''}
                        </div>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  )
}
