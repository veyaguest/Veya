import { useCallback, useEffect, useState } from 'react'
import { callOps, type MyDay, type TaskDetail, type TaskRow } from '../admin/callOpsApi'
import type { CallOutcome, User } from '../types'
import { AccountCenter } from './AccountCenter'
import './PhoneAgentApp.css'

/**
 * מסך הטלפן — "שיחות להיום".
 *
 * זה **כל** הממשק שמשתמש עם תפקיד ``phone_agent`` רואה: אין סרגל אדמין, אין
 * ניהול מוזמנים, אין הושבה ואין הגדרות.
 *
 * מקור האמת היחיד הוא פנקס המשימות (``call_tasks``, ``/admin/call-ops/my/*``):
 * הטלפן רואה **רק משימות שהוקצו לו**, והמסך לא מחשב תור בעצמו — הסדר, הסבב,
 * המחזור והשיחות החוזרות נקבעים בשרת. כל תוצאה נרשמת על המשימה עצמה.
 *
 * חשוב: ההסתרה כאן היא **נוחות, לא אבטחה**. ההרשאה נאכפת בשרת
 * (get_current_caller + סינון לפי assignee_id + RLS).
 */

/** תוצאות השיחה (§B באיחוד מרכז הטלפנים). */
const AGENT_OUTCOMES: {
  key: CallOutcome
  icon: string
  label: string
  tone: 'good' | 'bad' | 'neutral'
}[] = [
  { key: 'confirmed', icon: '✅', label: 'מגיע', tone: 'good' },
  { key: 'declined', icon: '❌', label: 'לא מגיע', tone: 'bad' },
  { key: 'maybe', icon: '🤔', label: 'עדיין לא בטוח', tone: 'neutral' },
  { key: 'answered', icon: '💬', label: 'ענה, בלי החלטה', tone: 'neutral' },
  { key: 'no_answer', icon: '📞', label: 'לא ענה', tone: 'neutral' },
  { key: 'busy', icon: '⏳', label: 'לא זמין / תפוס', tone: 'neutral' },
  { key: 'wrong_number', icon: '📵', label: 'מספר שגוי', tone: 'neutral' },
  { key: 'note', icon: '📝', label: 'הערה בלבד', tone: 'neutral' },
  { key: 'callback', icon: '📅', label: 'לחזור מאוחר יותר', tone: 'neutral' },
]

/** תוצאות שצריכות פרט נוסף לפני שמירה. השאר נשמרות בלחיצה אחת. */
const NEEDS_DETAIL: CallOutcome[] = ['confirmed', 'callback', 'note']

/** כמה אנשים מגיעים — בחירה מהירה, בלי מקלדת. */
const PARTY_CHOICES = [1, 2, 3, 4, 5, 6, 7, 8]

const RSVP_LABELS: Record<string, string> = {
  pending: 'טרם השיב',
  maybe: 'עדיין לא בטוח',
  confirmed: 'מגיע',
  declined: 'לא מגיע',
}

function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, '')}`
}

/** תאריך האירוע לתצוגה: YYYY-MM-DD → DD/MM/YYYY. */
function eventDateText(iso: string): string {
  if (!iso) return ''
  const [y, m, d] = iso.slice(0, 10).split('-')
  return y && m && d ? `${d}/${m}/${y}` : iso
}

// VEYA היא מערכת ישראלית — מועדים תמיד מוצגים בשעון ישראל, לא בשעון
// הדפדפן/המכשיר של הטלפן.
const LOCAL_TIMEZONE = 'Asia/Jerusalem'

/** מפרש ISO string שמגיע מה-Backend כ-UTC נאיבי (בלי Z/offset). בלי הסימון
 * המפורש הזה, ``new Date()`` היה מפרש את המחרוזת כזמן מקומי של המכשיר. */
function parseNaiveUtc(iso: string): Date {
  const hasZone = /[Zz]|[+-]\d{2}:?\d{2}$/.test(iso)
  return new Date(hasZone ? iso : `${iso}Z`)
}

function formatDateTime(iso: string | null): string {
  if (!iso) return ''
  const d = parseNaiveUtc(iso)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleString('he-IL', {
    day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit',
    timeZone: LOCAL_TIMEZONE,
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
  const [work, setWork] = useState<TaskRow[] | null>(null)
  const [later, setLater] = useState<TaskRow[]>([])
  const [day, setDay] = useState<MyDay | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [openTaskId, setOpenTaskId] = useState<number | null>(null)
  // מצב עבודה רציף: אחרי שמירה עוברים אוטומטית למשימה הבאה, בלי לחזור לרשימה.
  const [streak, setStreak] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)

  // השרת מחזיר את רשימת העבודה מוכנה: ``work`` = מה לחייג עכשיו (כולל
  // באיחור, בלי שיחות חוזרות שמועדן לא הגיע ובלי סבבים מושהים), ``later`` =
  // שיחות חוזרות שנקבעו לשעה מאוחרת יותר. אין כאן מיזוג או חישוב תור.
  const load = useCallback(async () => {
    try {
      const [summary, workPage, laterPage] = await Promise.all([
        callOps.myDay(),
        callOps.myTasks('work', query),
        callOps.myTasks('later', query),
      ])
      setDay(summary)
      setWork(workPage.items)
      setLater(laterPage.items)
      setError(null)
      return workPage.items
    } catch (err) {
      setError(err instanceof Error ? err.message : 'טעינת רשימת השיחות נכשלה')
      return null
    }
  }, [query])

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), query ? 250 : 0)
    return () => window.clearTimeout(timer)
  }, [load, query])

  /** אחרי תיעוד שיחה: רענון, ואם אנחנו ברצף — קפיצה למשימה הבאה. */
  async function afterOutcome(savedTaskId: number, keepOpen: boolean) {
    const fresh = await load()
    if (keepOpen) return
    if (!streak || !fresh) {
      setOpenTaskId(null)
      return
    }
    const next = fresh.find((r) => r.task_id !== null && r.task_id !== savedTaskId)
    setOpenTaskId(next?.task_id ?? null)
    if (!next) setStreak(false)
  }

  function startStreak() {
    const first = work?.find((r) => r.task_id !== null)
    if (!first?.task_id) return
    setStreak(true)
    setOpenTaskId(first.task_id)
  }

  const waiting = day?.counts.work ?? work?.length ?? 0
  const made = day?.counts.calls_made ?? 0
  const waitingLater = day?.counts.later ?? later.length

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
            שלום {user.display_name || 'לך'} — אלה השיחות שהוקצו לך
          </p>
        </div>

        <div className="pa-stats">
          <Stat value={waiting} label="לחייג עכשיו" tone="warn" />
          <Stat value={made} label="שיחות שביצעת היום" tone="good" />
          <Stat value={waitingLater} label="לחזור מאוחר יותר" />
        </div>

        {error && <div className="pa-error">{error}</div>}

        {work === null ? (
          <div className="pa-loading">טוען…</div>
        ) : (
          <>
            {(work.length > 0 || query) && (
              <div className="pa-toolbar">
                <button type="button" className="pa-start" onClick={startStreak} disabled={work.length === 0}>
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
            )}

            {work.length === 0 ? (
              <div className="pa-empty">
                <div className="pa-empty-icon">☕</div>
                <h2>אין שיחות ממתינות</h2>
                <p>
                  {query
                    ? 'אין מוזמן שמתאים לחיפוש הזה.'
                    : 'כל השיחות שהוקצו לך להיום טופלו. כשתוקצה לך משימה חדשה, היא תופיע כאן.'}
                </p>
              </div>
            ) : (
              <ul className="pa-list">
                {work.map((row) => (
                  <li key={row.task_id ?? `g${row.guest_id}`}>
                    <TaskCard row={row} onOpen={() => row.task_id && setOpenTaskId(row.task_id)} />
                  </li>
                ))}
              </ul>
            )}

            {later.length > 0 && (
              <>
                <h2 className="pa-section pa-later-title">שיחות חוזרות מאוחר יותר</h2>
                <ul className="pa-list">
                  {later.map((row) => (
                    <li key={row.task_id ?? `g${row.guest_id}`}>
                      <TaskCard row={row} onOpen={() => row.task_id && setOpenTaskId(row.task_id)} />
                    </li>
                  ))}
                </ul>
              </>
            )}
          </>
        )}
      </main>

      {openTaskId !== null && (
        <CallSheet
          taskId={openTaskId}
          streak={streak}
          onClose={() => {
            setOpenTaskId(null)
            setStreak(false)
          }}
          onSaved={(keepOpen) => afterOutcome(openTaskId, keepOpen)}
        />
      )}

      {profileOpen && (
        <AccountCenter
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
function TaskCard({ row, onOpen }: { row: TaskRow; onOpen: () => void }) {
  const followup = row.is_followup || row.reason === 'callback' || row.reason === 'manual'
  return (
    <div className={`pa-card ${followup ? 'pa-card-followup' : ''}`}>
      <button type="button" className="pa-card-main" onClick={onOpen}>
        <div className="pa-card-name">
          {row.guest_name}
          {followup && <span className="pa-badge">{row.reason_label}</span>}
        </div>
        <div className="pa-card-phone" dir="ltr">
          {row.phone}
        </div>
        <div className="pa-card-meta">
          <span>{row.event_label}</span>
          {row.event_date && (
            <>
              <span className="pa-dot">·</span>
              <span>{eventDateText(row.event_date)}</span>
            </>
          )}
        </div>
        <div className="pa-card-meta pa-card-sub">
          <span>{row.round_label}</span>
          <span className="pa-dot">·</span>
          <span>{row.party_size} מוזמנים</span>
          {row.attempts > 0 && (
            <>
              <span className="pa-dot">·</span>
              <span>ניסיון {row.attempts + 1}</span>
            </>
          )}
          {row.callback_at && (
            <>
              <span className="pa-dot">·</span>
              <span>לחזור ב-{formatDateTime(row.callback_at)}</span>
            </>
          )}
        </div>
      </button>
      <div className="pa-card-actions">
        <a className="pa-dial" href={telHref(row.phone)} aria-label={`חיוג ל${row.guest_name}`}>
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
 * גיליון ביצוע השיחה על משימה אחת. במובייל הוא נפתח מלמטה כמעט על כל המסך —
 * כי זו העבודה עצמה, לא חלון צדדי.
 */
function CallSheet({
  taskId,
  streak,
  onClose,
  onSaved,
}: {
  taskId: number
  streak: boolean
  onClose: () => void
  /** ``keepOpen`` — אחרי "הערה בלבד" המשימה עדיין פתוחה, נשארים בה. */
  onSaved: (keepOpen: boolean) => void
}) {
  const [detail, setDetail] = useState<TaskDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [pending, setPending] = useState<CallOutcome | null>(null)
  const [count, setCount] = useState(1)
  const [callbackAt, setCallbackAt] = useState('')
  const [note, setNote] = useState('')

  const fetchDetail = useCallback(() => {
    return callOps
      .myTask(taskId)
      .then((d) => {
        setDetail(d)
        setCount(d.card.confirmed_count ?? d.task.party_size ?? 1)
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'טעינת המשימה נכשלה'))
  }, [taskId])

  useEffect(() => {
    setDetail(null)
    setPending(null)
    setCallbackAt('')
    setNote('')
    setError(null)
    void fetchDetail()
  }, [fetchDetail])

  async function save(outcome: CallOutcome) {
    setBusy(true)
    setError(null)
    try {
      await callOps.myTaskOutcome(taskId, {
        outcome,
        count: outcome === 'confirmed' ? count : null,
        guest_note: null,
        note: note.trim(),
        callback_at:
          outcome === 'callback' && callbackAt ? new Date(callbackAt).toISOString() : null,
      })
      if (outcome === 'note') {
        setNote('')
        setPending(null)
        await fetchDetail()
        onSaved(true)
      } else {
        onSaved(false)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שמירת תוצאת השיחה נכשלה')
    } finally {
      setBusy(false)
    }
  }

  function pick(outcome: CallOutcome) {
    if (NEEDS_DETAIL.includes(outcome)) {
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

  const task = detail?.task
  const card = detail?.card
  const closed = task ? task.status !== 'open' : false

  return (
    <div className="pa-overlay" onClick={onClose}>
      <div className="pa-sheet" onClick={(e) => e.stopPropagation()}>
        <div className="pa-sheet-head">
          <div>
            <h2 className="pa-sheet-title">{task?.guest_name ?? 'ביצוע שיחה'}</h2>
            {streak && <span className="pa-streak">מצב רצף — עובר אוטומטית לבא</span>}
          </div>
          <button type="button" className="pa-x" onClick={onClose} aria-label="סגירה">
            ×
          </button>
        </div>

        {!task || !card ? (
          <div className="pa-sheet-body">
            {error ? <div className="pa-error">{error}</div> : <div className="pa-loading">טוען…</div>}
          </div>
        ) : (
          <div className="pa-sheet-body">
            <a className="pa-dial pa-dial-big" href={telHref(task.phone)} dir="ltr">
              📞 {task.phone || '—'}
            </a>

            <div className="pa-next">
              <span className="pa-next-label">מה עושים עכשיו</span>
              <strong>{card.next_action}</strong>
            </div>

            <dl className="pa-facts">
              <div>
                <dt>האירוע</dt>
                <dd>{task.event_label}</dd>
              </div>
              <div>
                <dt>תאריך</dt>
                <dd>
                  {eventDateText(task.event_date) || '—'}
                  {task.event_time ? ` · ${task.event_time}` : ''}
                </dd>
              </div>
              <div>
                <dt>אולם</dt>
                <dd>{task.venue_name || '—'}</dd>
              </div>
              <div>
                <dt>מוזמנים</dt>
                <dd>{task.party_size}</dd>
              </div>
              <div>
                <dt>סבב</dt>
                <dd>{task.round_label}</dd>
              </div>
              <div>
                <dt>למה מתקשרים</dt>
                <dd>{task.reason_label}</dd>
              </div>
              <div>
                <dt>מצב</dt>
                <dd>
                  {task.status_label}
                  {task.attempts > 0 ? ` · ${task.attempts} ניסיונות` : ''}
                </dd>
              </div>
              <div>
                <dt>תשובה עד עכשיו</dt>
                <dd>{RSVP_LABELS[card.rsvp_status] ?? card.rsvp_status}</dd>
              </div>
              {task.callback_at && (
                <div>
                  <dt>ביקש שנחזור</dt>
                  <dd>{formatDateTime(task.callback_at)}</dd>
                </div>
              )}
              <div>
                <dt>מספר משימה</dt>
                <dd dir="ltr">#{task.task_id}</dd>
              </div>
            </dl>

            {(card.guest_note || card.owner_notes || task.note) && (
              <div className="pa-notes">
                {card.guest_note && <p>המוזמן כתב: {card.guest_note}</p>}
                {card.owner_notes && <p>{card.owner_notes}</p>}
                {task.note && <p className="pa-pre">{task.note}</p>}
              </div>
            )}

            {closed ? (
              <div className="pa-notes">המשימה כבר טופלה ({task.status_label}).</div>
            ) : (
              <>
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
                    <button type="button" className="pa-save" onClick={() => save('confirmed')} disabled={busy}>
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

                <label className="pa-extra">
                  <span className="pa-extra-label">
                    {pending === 'note' ? 'מה לרשום?' : 'הערה לשיחה (לא נשלחת למוזמן)'}
                  </span>
                  <textarea
                    className="pa-input pa-textarea"
                    rows={2}
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                  />
                  {pending === 'note' && (
                    <button
                      type="button"
                      className="pa-save"
                      onClick={() => save('note')}
                      disabled={busy || !note.trim()}
                    >
                      {busy ? 'רגע…' : 'שמירת הערה'}
                    </button>
                  )}
                </label>
              </>
            )}

            {error && <div className="pa-error">{error}</div>}

            {card.history.length > 0 && (
              <>
                <h3 className="pa-section">היסטוריית קשר</h3>
                <ol className="pa-history">
                  {card.history.slice(0, 12).map((h, i) => (
                    <li key={i}>
                      <span className="pa-history-when">{formatDateTime(h.at)}</span>
                      <span className="pa-history-title">
                        {h.title}
                        {h.actor ? ` · ${h.actor}` : ''}
                      </span>
                      {h.detail && <span className="pa-history-detail">{h.detail}</span>}
                    </li>
                  ))}
                </ol>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
