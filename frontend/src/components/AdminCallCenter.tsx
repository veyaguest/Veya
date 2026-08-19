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
  CallCenterScope,
  CallOutcome,
  Side,
} from '../types'
import { getEventTerms, sidePhrase } from '../strings/eventTypes'
import './AdminCallCenter.css'

/**
 * Call Center — מסך השיחות של האדמין.
 *
 * המסך לא מנהל תאריכים משלו: הוא מציג בדיוק את מה שה-Backend גוזר מ-Workflow
 * אישורי ההגעה (backend/app/call_center.py). ברירת המחדל היא "היום" — רק
 * שיחות שצריך לבצע עכשיו. "מחר"/"בהמשך" הם תצוגה מקדימה בלבד, לתכנון.
 * מוזמן שכבר אישר או ביטל יורד מהתור מיד — בין אם דרך WhatsApp, דרך בעל/ת
 * האירוע, או דרך המסך הזה.
 */

// גדול מספיק כדי לכסות יום עבודה שלם על פני כמה אירועים בלי לקטוע אירוע
// באמצע (ה-Backend מגביל ל-200 בכל מקרה, ראו MAX_PAGE_LIMIT ב-router).
const PAGE_SIZE = 200

// "לא טופל" ראשון בכוונה: שיחות שכבר איחרו דורשות תשומת לב לפני שיחות
// "טריות" של היום. אירוע שכבר הסתיים לא מופיע כאן ולא בשום טאב אחר —
// ראו event_has_ended ב-Backend.
const SCOPE_TABS: { key: CallCenterScope; label: string }[] = [
  { key: 'not_handled', label: 'לא טופל' },
  { key: 'today', label: 'היום' },
  { key: 'tomorrow', label: 'מחר' },
  { key: 'later', label: 'בהמשך' },
]

const SCOPE_NOUN: Record<CallCenterScope, string> = {
  today: 'שיחות להיום',
  tomorrow: 'שיחות למחר',
  later: 'שיחות בהמשך',
  not_handled: 'שיחות שלא טופלו',
}

const SCOPE_EMPTY_TITLE: Record<CallCenterScope, string> = {
  today: 'אין שיחות היום',
  tomorrow: 'אין שיחות צפויות למחר',
  later: 'אין שיחות צפויות בהמשך',
  not_handled: 'אין שיחות שלא טופלו',
}

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

// VEYA היא מערכת ישראלית — מועדים תמיד מוצגים בשעון ישראל, לא בשעון
// הדפדפן/המכשיר (ששניהם עשויים להיות שונים, למשל למוקדן שעובד מחו"ל).
const LOCAL_TIMEZONE = 'Asia/Jerusalem'

/** מפרש ISO string שמגיע מה-Backend כ-UTC נאיבי (בלי Z/offset — ראו
 * ``call_center.py``: כל הזמנים במערכת נשמרים ``datetime.utcnow()``).
 * בלי הסימון המפורש כאן, ``new Date()`` היה מפרש את המחרוזת כזמן *מקומי
 * של המכשיר* במקום UTC — טעות שכבר תוקנה פעם אחת בצד ה-Backend
 * (``_callback_phrase``); זו אותה טעות בדיוק, בצד ה-Frontend. */
function parseNaiveUtc(iso: string): Date {
  const hasZone = /[Zz]|[+-]\d{2}:?\d{2}$/.test(iso)
  return new Date(hasZone ? iso : `${iso}Z`)
}

function formatDateTime(iso: string | null): string {
  if (!iso) return ''
  const d = parseNaiveUtc(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleString('he-IL', {
    day: 'numeric',
    month: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: LOCAL_TIMEZONE,
  })
}

/** "לחזור היום ב-10:00" / "לחזור ב-20/08 ב-10:00" — לפי אם המועד היום. */
function followupPhrase(iso: string | null): string {
  if (!iso) return ''
  const d = parseNaiveUtc(iso)
  if (isNaN(d.getTime())) return ''
  const todayStr = new Date().toLocaleDateString('en-CA', { timeZone: LOCAL_TIMEZONE })
  const dStr = d.toLocaleDateString('en-CA', { timeZone: LOCAL_TIMEZONE })
  const time = d.toLocaleTimeString('he-IL', {
    hour: '2-digit', minute: '2-digit', timeZone: LOCAL_TIMEZONE,
  })
  if (dStr === todayStr) return `לחזור היום ב-${time}`
  const date = d.toLocaleDateString('he-IL', {
    day: 'numeric', month: 'numeric', timeZone: LOCAL_TIMEZONE,
  })
  return `לחזור ב-${date} ב-${time}`
}

/** מספר טלפון לחיוג — הדפדפן/הטלפון פותח את החייגן. */
function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, '')}`
}

export function AdminCallCenter() {
  const [scope, setScope] = useState<CallCenterScope>('today')
  const [overview, setOverview] = useState<CallCenterOverview | null>(null)
  const [rows, setRows] = useState<CallCenterGuestRow[] | null>(null)
  const [total, setTotal] = useState(0)
  const [error, setError] = useState<string | null>(null)

  // סינונים — תצוגתיים בלבד, לא משנים מי צריך שיחה לפי ה-Workflow. החיפוש
  // (query) עובר ל-Backend ומסונן שם *בתוך הטווח הנבחר בלבד*.
  const [eventId, setEventId] = useState<number | null>(null)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)

  const [openGuestId, setOpenGuestId] = useState<number | null>(null)

  const loadOverview = useCallback(() => {
    callCenterOverview(scope)
      .then(setOverview)
      .catch((err) => setError(err instanceof Error ? err.message : 'טעינת מסך השיחות נכשלה'))
  }, [scope])

  const loadQueue = useCallback(() => {
    callCenterQueue({ scope, eventId, q: query, status, limit: PAGE_SIZE, offset })
      .then((page) => {
        setRows(page.items)
        setTotal(page.total)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'טעינת רשימת השיחות נכשלה'))
  }, [scope, eventId, query, status, offset])

  // מעבר טווח: מאפסים סינונים תלויי-מסך (אירוע/עמוד) כדי לא "לגרור" בחירה
  // מ"היום" לתוך "מחר" בטעות, אבל משאירים את החיפוש (נוח, וממילא מסונן
  // מחדש בתוך הטווח החדש).
  function selectScope(next: CallCenterScope) {
    setScope(next)
    setEventId(null)
    setOffset(0)
  }

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

  // קיבוץ המוזמנים לפי אירוע — סדר האירועים נקבע ב-Backend (הכי הרבה שיחות
  // קודם, ובשוויון האירוע הקרוב יותר; ראו call_center.py::_event_sort_key),
  // וסדר האורחים בתוך כל אירוע כבר מגיע ממוין (Follow-up קודם, ואז א-ב).
  const groups = useMemo(() => {
    if (!overview || !rows) return []
    const byEvent = new Map<number, CallCenterGuestRow[]>()
    for (const row of rows) {
      const list = byEvent.get(row.event_id)
      if (list) list.push(row)
      else byEvent.set(row.event_id, [row])
    }
    return overview.events
      .filter((ev) => byEvent.has(ev.event_id))
      .map((ev) => ({ event: ev, guests: byEvent.get(ev.event_id) ?? [] }))
  }, [overview, rows])

  if (error && !overview) return <div className="admin-error">{error}</div>
  if (!overview) return <div className="admin-loading">טוען…</div>

  return (
    <div className="admin-page cc-page">
      <div className="cc-scope-tabs" role="tablist" aria-label="טווח תצוגה">
        {SCOPE_TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={scope === tab.key}
            className={`cc-scope-tab ${scope === tab.key ? 'active' : ''}`}
            onClick={() => selectScope(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="cc-stats">
        <StatCard label={SCOPE_NOUN[scope]} value={overview.total} />
        <StatCard label="הושלמו" value={overview.done} tone="good" />
        <StatCard label="ממתינות" value={overview.waiting} tone="warn" />
        <StatCard label="אירועים" value={overview.events_needing_attention} />
      </div>

      {overview.events.length === 0 ? (
        <div className="cc-empty">
          <div className="cc-empty-icon">☕</div>
          <h3>{SCOPE_EMPTY_TITLE[scope]}</h3>
          <p>
            {scope === 'today'
              ? 'אין כרגע אירוע שצריך שיחה היום לפי מסלול אישורי ההגעה. כשיגיע מועד הסבב הבא, המוזמנים יופיעו כאן אוטומטית.'
              : 'אין כרגע אירוע עם שיחה צפויה בטווח הזה.'}
          </p>
        </div>
      ) : (
        <>
          <div className="cc-list-head">
            <h2 className="admin-section-title">{SCOPE_NOUN[scope]} ({total})</h2>
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
            </div>
          </div>

          {error && <div className="admin-error">{error}</div>}

          {rows === null ? (
            <div className="admin-loading">טוען…</div>
          ) : groups.length === 0 ? (
            <div className="cc-empty-inline">אין שיחות שתואמות לסינון הזה.</div>
          ) : (
            <>
              <div className="cc-groups">
                {groups.map(({ event, guests }) => (
                  <EventGroup
                    key={event.event_id}
                    event={event}
                    guests={guests}
                    scope={scope}
                    onOpen={setOpenGuestId}
                  />
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

/** תאריך האירוע לתצוגת כותרת קבוצה — "19.09.2026" (YYYY-MM-DD → D.M.YYYY). */
function eventDateDots(iso: string): string {
  if (!iso) return ''
  const [y, m, d] = iso.slice(0, 10).split('-')
  return y && m && d ? `${d}.${m}.${y}` : iso
}

/** כותרת אירוע + רשימת המוזמנים שלו לטווח הנבחר (§2: קיבוץ לפי אירוע). */
function EventGroup({
  event,
  guests,
  scope,
  onOpen,
}: {
  event: CallCenterEventRow
  guests: CallCenterGuestRow[]
  scope: CallCenterScope
  onOpen: (guestId: number) => void
}) {
  return (
    <section className="cc-group">
      <header className="cc-group-head">
        <span className="cc-group-hosts">{event.hosts}</span>
        <span className="cc-group-meta">
          {event.event_date && (
            <>
              <span>{eventDateDots(event.event_date)}</span>
              <span className="cc-dot">·</span>
            </>
          )}
          <span>{guests.length} {SCOPE_NOUN[scope]}</span>
        </span>
      </header>
      <div className="cc-guests">
        {guests.map((row) => (
          <GuestRow key={row.guest_id} row={row} onOpen={() => onOpen(row.guest_id)} />
        ))}
      </div>
    </section>
  )
}

function GuestRow({ row, onOpen }: { row: CallCenterGuestRow; onOpen: () => void }) {
  return (
    <div className={`cc-guest ${row.is_followup ? 'cc-guest-followup' : ''}`}>
      <button type="button" className="cc-guest-main" onClick={onOpen}>
        {row.is_followup && (
          <div className="cc-followup-badge">
            <span aria-hidden>🔁</span> חזרה למוזמן
          </div>
        )}
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
        </div>
        <div className="cc-guest-meta cc-guest-sub">
          <span>סבב {row.round_number}</span>
          <span className="cc-dot">·</span>
          <span>מ-{row.round_date}</span>
          {row.last_outcome_label && !row.is_followup && (
            <>
              <span className="cc-dot">·</span>
              <span className="cc-last">אחרון: {row.last_outcome_label}</span>
            </>
          )}
        </div>
        {row.is_followup && row.callback_at && (
          <div className="cc-followup-time">{followupPhrase(row.callback_at)}</div>
        )}
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
