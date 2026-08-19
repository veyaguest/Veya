import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  callCenterGuest,
  callCenterOverview,
  callCenterQueue,
  callCenterRecordOutcome,
} from '../api'
import type {
  CallCenterGuestDetail,
  CallCenterGuestRow,
  CallOutcome,
  User,
} from '../types'
import { ProfileDialog } from './ProfileDialog'
import './PhoneAgentApp.css'

/**
 * מסך הטלפן — "שיחות להיום".
 *
 * זה **כל** הממשק שמשתמש עם תפקיד ``phone_agent`` רואה: אין סרגל אדמין, אין
 * ניהול מוזמנים, אין הושבה ואין הגדרות. הוא מדבר עם אותן ארבע נקודות קצה
 * שמסך ה-Call Center של האדמין משתמש בהן (``/admin/call-center``), כי הלוגיקה
 * זהה — רק התצוגה שונה: פשוטה, מובייל-פירסט, ובנויה לרצף שיחות ארוך.
 *
 * חשוב: ההסתרה כאן היא **נוחות, לא אבטחה**. ההרשאה עצמה נאכפת בשרת
 * (backend/app/roles.py, EventAccess, get_current_caller) — גם קריאה ישירה
 * ל-API מחוץ למסך הזה תיחסם.
 */

const PAGE_SIZE = 200

/** חמש הפעולות שהטלפן מבצע אחרי שיחה (§3 באפיון). */
const AGENT_OUTCOMES: {
  key: CallOutcome
  icon: string
  label: string
  tone: 'good' | 'bad' | 'neutral'
}[] = [
  { key: 'confirmed', icon: '✅', label: 'הגיע', tone: 'good' },
  { key: 'declined', icon: '❌', label: 'לא מגיע', tone: 'bad' },
  { key: 'no_answer', icon: '📞', label: 'לא ענה', tone: 'neutral' },
  { key: 'wrong_number', icon: '📵', label: 'מספר שגוי', tone: 'neutral' },
  { key: 'callback', icon: '📅', label: 'לחזור מאוחר יותר', tone: 'neutral' },
]

/** כמה אנשים מגיעים — בחירה מהירה, בלי מקלדת. */
const PARTY_CHOICES = [1, 2, 3, 4, 5, 6, 7, 8]

function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, '')}`
}

/** תאריך האירוע לתצוגה: YYYY-MM-DD → DD/MM/YYYY. */
function eventDateText(iso: string): string {
  if (!iso) return ''
  const [y, m, d] = iso.slice(0, 10).split('-')
  return y && m && d ? `${d}/${m}/${y}` : iso
}

function formatDateTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleString('he-IL', {
    day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export function PhoneAgentApp({
  user,
  onLogout,
  onUserUpdated,
}: {
  user: User
  onLogout: () => void
  onUserUpdated: (user: User) => void
}) {
  const [rows, setRows] = useState<CallCenterGuestRow[] | null>(null)
  const [done, setDone] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [openGuestId, setOpenGuestId] = useState<number | null>(null)
  // מצב עבודה רציף: אחרי שמירה עוברים אוטומטית למוזמן הבא, בלי לחזור לרשימה.
  const [streak, setStreak] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)

  const load = useCallback(async () => {
    try {
      const [overview, page] = await Promise.all([
        callCenterOverview(),
        callCenterQueue({ q: query, limit: PAGE_SIZE, offset: 0 }),
      ])
      setDone(overview.done)
      setRows(page.items)
      setError(null)
      return page.items
    } catch (err) {
      setError(err instanceof Error ? err.message : 'טעינת רשימת השיחות נכשלה')
      return null
    }
  }, [query])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), query ? 250 : 0)
    return () => window.clearTimeout(timer)
  }, [load, query])

  const followups = useMemo(
    () => (rows ?? []).filter((r) => r.is_followup).length,
    [rows],
  )

  /** אחרי תיעוד שיחה: רענון, ואם אנחנו ברצף — קפיצה למוזמן הבא. */
  async function afterOutcome(savedGuestId: number) {
    const fresh = await load()
    if (!streak || !fresh) {
      setOpenGuestId(null)
      return
    }
    const next = fresh.find((r) => r.guest_id !== savedGuestId)
    setOpenGuestId(next ? next.guest_id : null)
    if (!next) setStreak(false)
  }

  function startStreak() {
    const first = rows?.[0]
    if (!first) return
    setStreak(true)
    setOpenGuestId(first.guest_id)
  }

  const waiting = rows?.length ?? 0

  return (
    <div className="pa-app" dir="rtl">
      <header className="pa-top">
        <div className="pa-brand">
          <span className="pa-brand-mark" aria-hidden>
            ☎️
          </span>
          <span className="pa-brand-name">VEYA · שיחות</span>
        </div>
        <div className="pa-top-actions">
          <button type="button" className="pa-top-btn" onClick={() => setProfileOpen(true)}>
            <span aria-hidden>👤</span> החשבון שלי
          </button>
          <button type="button" className="pa-top-btn" onClick={onLogout}>
            יציאה
          </button>
        </div>
      </header>

      <main className="pa-main">
        <div className="pa-head">
          <h1 className="pa-title">שיחות להיום</h1>
          <p className="pa-sub">
            שלום {user.display_name || 'לך'} — {waiting + done} שיחות היום
          </p>
        </div>

        <div className="pa-stats">
          <Stat value={waiting} label="ממתינות" tone="warn" />
          <Stat value={done} label="טופלו" tone="good" />
          <Stat value={followups} label="שיחות המשך" />
        </div>

        {error && <div className="pa-error">{error}</div>}

        {rows === null ? (
          <div className="pa-loading">טוען…</div>
        ) : rows.length === 0 ? (
          <div className="pa-empty">
            <div className="pa-empty-icon">☕</div>
            <h2>אין שיחות ממתינות</h2>
            <p>
              {query
                ? 'אין מוזמן שמתאים לחיפוש הזה.'
                : 'כל השיחות שהיו מוכנות להיום טופלו. כשייפתח סבב חדש, המוזמנים יופיעו כאן אוטומטית.'}
            </p>
          </div>
        ) : (
          <>
            <div className="pa-toolbar">
              <button type="button" className="pa-start" onClick={startStreak}>
                ▶ התחל שיחות
              </button>
              <input
                type="search"
                className="pa-search"
                placeholder="חיפוש לפי שם או טלפון…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>

            <ul className="pa-list">
              {rows.map((row) => (
                <li key={row.guest_id}>
                  <TaskCard row={row} onOpen={() => setOpenGuestId(row.guest_id)} />
                </li>
              ))}
            </ul>
          </>
        )}
      </main>

      {openGuestId !== null && (
        <CallSheet
          guestId={openGuestId}
          streak={streak}
          onClose={() => {
            setOpenGuestId(null)
            setStreak(false)
          }}
          onSaved={() => afterOutcome(openGuestId)}
        />
      )}

      {profileOpen && (
        <ProfileDialog
          user={user}
          onClose={() => setProfileOpen(false)}
          onUpdated={onUserUpdated}
          onLogout={onLogout}
        />
      )}
    </div>
  )
}

function Stat({
  value,
  label,
  tone,
}: {
  value: number
  label: string
  tone?: 'good' | 'warn'
}) {
  return (
    <div className={`pa-stat ${tone ? `pa-stat-${tone}` : ''}`}>
      <span className="pa-stat-value">{value}</span>
      <span className="pa-stat-label">{label}</span>
    </div>
  )
}

/** כרטיס משימה אחת — כל מה שצריך כדי להתחיל לחייג. */
function TaskCard({ row, onOpen }: { row: CallCenterGuestRow; onOpen: () => void }) {
  return (
    <div className={`pa-card ${row.is_followup ? 'pa-card-followup' : ''}`}>
      <button type="button" className="pa-card-main" onClick={onOpen}>
        <div className="pa-card-name">
          {row.full_name}
          {row.is_followup && <span className="pa-badge">שיחת המשך</span>}
        </div>
        <div className="pa-card-phone" dir="ltr">
          {row.phone}
        </div>
        <div className="pa-card-meta">
          <span>{row.event_hosts}</span>
          {row.event_date && (
            <>
              <span className="pa-dot">·</span>
              <span>{eventDateText(row.event_date)}</span>
            </>
          )}
        </div>
        <div className="pa-card-meta pa-card-sub">
          <span>סבב טלפונים {row.round_number}</span>
          <span className="pa-dot">·</span>
          <span>{row.party_size} מוזמנים</span>
          {row.callback_at && (
            <>
              <span className="pa-dot">·</span>
              <span>לחזור ב-{formatDateTime(row.callback_at)}</span>
            </>
          )}
        </div>
      </button>
      <div className="pa-card-actions">
        <a className="pa-dial" href={telHref(row.phone)} aria-label={`חיוג ל${row.full_name}`}>
          📞 חייג
        </a>
        <button type="button" className="pa-open" onClick={onOpen}>
          התקשר
        </button>
      </div>
    </div>
  )
}

/**
 * גיליון ביצוע השיחה. במובייל הוא נפתח מלמטה כמעט על כל המסך — כי זו העבודה
 * עצמה, לא חלון צדדי.
 */
function CallSheet({
  guestId,
  streak,
  onClose,
  onSaved,
}: {
  guestId: number
  streak: boolean
  onClose: () => void
  onSaved: () => void
}) {
  const [detail, setDetail] = useState<CallCenterGuestDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<CallOutcome | null>(null)
  const [count, setCount] = useState(1)
  const [callbackAt, setCallbackAt] = useState('')

  useEffect(() => {
    setDetail(null)
    setPending(null)
    setCallbackAt('')
    setError(null)
    callCenterGuest(guestId)
      .then((d) => {
        setDetail(d)
        setCount(d.confirmed_count ?? d.party_size ?? 1)
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'טעינת פרטי המוזמן נכשלה'),
      )
  }, [guestId])

  async function save(outcome: CallOutcome, people?: number) {
    setBusy(true)
    setError(null)
    try {
      await callCenterRecordOutcome(guestId, {
        outcome,
        count: outcome === 'confirmed' ? (people ?? count) : null,
        guest_note: null,
        note: '',
        callback_at:
          outcome === 'callback' && callbackAt
            ? new Date(callbackAt).toISOString()
            : null,
      })
      onSaved()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שמירת תוצאת השיחה נכשלה')
    } finally {
      setBusy(false)
    }
  }

  /** תוצאה שדורשת פרט נוסף נפתחת; השאר נשמרות בלחיצה אחת. */
  function pick(outcome: CallOutcome) {
    if (outcome === 'confirmed' || outcome === 'callback') {
      setPending(pending === outcome ? null : outcome)
      return
    }
    void save(outcome)
  }

  function setCallbackPreset(which: 'today' | 'tomorrow') {
    const d = new Date()
    if (which === 'today') d.setHours(d.getHours() + 3, 0, 0, 0)
    else {
      d.setDate(d.getDate() + 1)
      d.setHours(10, 0, 0, 0)
    }
    const pad = (n: number) => String(n).padStart(2, '0')
    setCallbackAt(
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`,
    )
  }

  return (
    <div className="pa-overlay" onClick={onClose}>
      <div className="pa-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="pa-sheet-head">
          <div>
            <h2 className="pa-sheet-title">{detail?.full_name ?? 'ביצוע שיחה'}</h2>
            {streak && <span className="pa-streak">מצב רצף — עובר אוטומטית לבא</span>}
          </div>
          <button type="button" className="pa-x" onClick={onClose} aria-label="סגירה">
            ×
          </button>
        </div>

        {!detail ? (
          <div className="pa-sheet-body">
            {error ? <div className="pa-error">{error}</div> : <div className="pa-loading">טוען…</div>}
          </div>
        ) : (
          <div className="pa-sheet-body">
            <a className="pa-dial pa-dial-big" href={telHref(detail.phone)} dir="ltr">
              📞 {detail.phone || '—'}
            </a>

            <dl className="pa-facts">
              <div>
                <dt>האירוע</dt>
                <dd>{detail.hosts}</dd>
              </div>
              <div>
                <dt>תאריך</dt>
                <dd>
                  {eventDateText(detail.event_date) || '—'}
                  {detail.event_time ? ` · ${detail.event_time}` : ''}
                </dd>
              </div>
              <div>
                <dt>אולם</dt>
                <dd>{detail.venue_name || '—'}</dd>
              </div>
              <div>
                <dt>מוזמנים</dt>
                <dd>{detail.party_size}</dd>
              </div>
            </dl>

            {(detail.guest_note || detail.notes_raw) && (
              <div className="pa-notes">
                {detail.guest_note && <p>{detail.guest_note}</p>}
                {detail.notes_raw && <p>{detail.notes_raw}</p>}
              </div>
            )}

            <h3 className="pa-section">תוצאת השיחה</h3>
            <div className="pa-outcomes">
              {AGENT_OUTCOMES.map((b) => (
                <button
                  key={b.key}
                  type="button"
                  className={`pa-outcome pa-outcome-${b.tone} ${pending === b.key ? 'open' : ''}`}
                  onClick={() => pick(b.key)}
                  disabled={busy}
                >
                  <span aria-hidden>{b.icon}</span> {b.label}
                </button>
              ))}
            </div>

            {pending === 'confirmed' && (
              <div className="pa-extra">
                <span className="pa-extra-label">כמה אנשים מגיעים?</span>
                <div className="pa-counts">
                  {PARTY_CHOICES.map((n) => (
                    <button
                      key={n}
                      type="button"
                      className={`pa-count ${count === n ? 'active' : ''}`}
                      onClick={() => setCount(n)}
                      disabled={busy}
                    >
                      {n}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  className="pa-save"
                  onClick={() => save('confirmed')}
                  disabled={busy}
                >
                  {busy ? 'רגע…' : `שמירה — ${count} מגיעים`}
                </button>
              </div>
            )}

            {pending === 'callback' && (
              <div className="pa-extra">
                <span className="pa-extra-label">מתי לחזור אליו?</span>
                <div className="pa-presets">
                  <button type="button" className="pa-preset" onClick={() => setCallbackPreset('today')}>
                    היום
                  </button>
                  <button type="button" className="pa-preset" onClick={() => setCallbackPreset('tomorrow')}>
                    מחר
                  </button>
                </div>
                <input
                  className="pa-input"
                  type="datetime-local"
                  value={callbackAt}
                  onChange={(e) => setCallbackAt(e.target.value)}
                  aria-label="מועד לחזור אל המוזמן"
                />
                <button
                  type="button"
                  className="pa-save"
                  onClick={() => save('callback')}
                  disabled={busy || !callbackAt}
                >
                  {busy ? 'רגע…' : 'שמירה'}
                </button>
              </div>
            )}

            {error && <div className="pa-error">{error}</div>}
          </div>
        )}
      </div>
    </div>
  )
}
