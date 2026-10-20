/**
 * תיבת WhatsApp — מי שכתב למספר של VEYA, ומענה מכאן.
 *
 * המספר מחובר ל-Cloud API של Meta, ולכן אי אפשר לפתוח אותו באפליקציית
 * WhatsApp — כל מענה יוצא מהמסך הזה. אותו רכיב במרכז השליטה (``InboxPage``,
 * ניווט ב-hash) ובמסך הטלפן (``InboxView`` עם מצב פנימי).
 *
 * - רשימה: פתוחות / נענו / סגורות / הכול, ו"רק שלי". מתרעננת כל 30 שניות.
 * - שיחה: כל ההודעות, שיוך, סטטוס, ומענה — **רק בתוך 24 שעות** מההודעה
 *   האחרונה של הפונה (השרת אוכף; כאן רק מסבירים).
 * - שאלות של מוזמנים מזוהים לא מגיעות לכאן: הן עוברות לבעלי האירוע.
 *
 * הטקסט של הפונה ושל הצוות מוצג כטקסט בלבד.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  assignInboxThread, fetchInboxSummary, fetchInboxThread, fetchInboxThreads, sendInboxFollowup, sendInboxReply,
  setInboxStatus,
  type InboxFilter, type InboxMessage, type InboxSenderKind, type InboxStatus, type InboxThreadDetail,
  type InboxThreadRow,
} from '../../inboxApi'
import { navigate, routeHref, type AdminRoute } from '../../route'
import { EmptyState, ErrorState, Loading, PageHeader, StatusPill, Tabs, fmtDateTime, type Tone } from '../../ui'
import './inbox.css'

// ── טקסטים (מסך צוות פנימי) ───────────────────────────────────────────────
const T = {
  title: 'WhatsApp',
  subtitle: 'מי שכתב למספר של VEYA. עונים מכאן — רק בתוך 24 שעות מההודעה האחרונה של הפונה.',
  filterLabel: 'סינון שיחות',
  tabs: { open: 'פתוחות', answered: 'נענו', closed: 'סגורות', all: 'הכול' } as Record<InboxFilter, string>,
  mineOnly: 'רק שלי',
  emptyOpen: 'אין שיחות שמחכות למענה',
  empty: 'אין שיחות להצגה',
  emptyText: 'כשמישהו יכתוב למספר של VEYA, השיחה תופיע כאן. שאלות של מוזמנים עוברות לבעלי האירוע.',
  back: '→ לכל השיחות',
  unknownName: 'בלי שם',
  ourPrefix: 'אנחנו: ',
  assignedTo: (name: string) => `אצל ${name}`,
  unassigned: 'לא משויכת',
  status: { open: 'מחכה למענה', answered: 'נענתה', closed: 'סגורה' } as Record<InboxStatus, string>,
  sender: {
    account: 'יש חשבון ב-VEYA',
    unknown: 'מספר לא מוכר',
    guest: 'מוזמן — לא זוהה בוודאות',
  } as Record<InboxSenderKind, string>,
  whoTitle: 'מי כתב',
  whatsappName: (n: string) => `השם ב-WhatsApp: ${n}`,
  events: 'אירועים',
  guestHint:
    'המספר הזה רשום כמוזמן ביותר מאירוע אחד (או שהמספר של המוזמן השתנה), ולכן ההודעה לא הועברה אוטומטית לבעלי אירוע.',
  conversation: 'השיחה',
  autoReply: 'תשובה אוטומטית',
  outStatus: {
    pending: 'בשליחה',
    sent: 'נשלחה',
    delivered: 'נמסרה',
    read: 'נקראה',
    failed: 'לא נשלחה',
    blocked: 'לא נשלחה',
    mock: 'נשמרה, לא נשלחה (מצב הדגמה)',
    received: '',
  } as Record<InboxMessage['status'], string>,
  replyLabel: 'התשובה',
  replyPlaceholder: 'כותבים כאן. הפונה יקבל את זה בוואטסאפ מ-VEYA.',
  send: 'שליחה',
  sending: 'שולחים…',
  sent: 'נשלחה',
  savedMock: 'נשמרה — בסביבה הזו WhatsApp במצב הדגמה, ולכן לא נשלחה בפועל',
  notSent: (reason: string) => `לא נשלחה${reason ? `: ${reason}` : ''}`,
  sendError: 'השליחה לא הצליחה, והתשובה לא יצאה. אפשר לנסות שוב.',
  windowLeft: (until: string, hours: number) =>
    hours >= 1 ? `אפשר לענות עד ${until} (עוד ${hours} ${hours === 1 ? 'שעה' : 'שעות'}).` : `אפשר לענות עד ${until} (פחות משעה).`,
  windowClosed:
    'עברו 24 שעות מההודעה האחרונה של הפונה, ולכן WhatsApp לא מאפשר לכתוב לו טקסט חופשי. אפשר לשלוח לו הודעת חזרה קבועה: כשהוא יענה או ילחץ "נמשיך כאן", אפשר יהיה לכתוב לו את התשובה.',
  followupPreviewLabel: 'מה הפונה יקבל:',
  followupText:
    'היי, כאן VEYA.\nקיבלנו את ההודעה ששלחתם לנו כאן ב-WhatsApp, ויש לנו תשובה בשבילכם.\nכדי שנוכל לענות, השיבו להודעה הזו או לחצו על הכפתור.\n[ נמשיך כאן ]',
  followupSend: 'שליחת הודעת חזרה',
  followupSending: 'שולחים…',
  followupHint: 'שלחו אותה רק כשהתשובה כבר מוכנה אצלכם.',
  followupWaiting: 'נשלחה הודעת חזרה. כשהפונה יענה, אפשר יהיה לכתוב לו כאן.',
  followupSent: 'הודעת החזרה נשלחה.',
  followupMock: 'נשמר — מצב הדגמה, שום הודעה לא יצאה.',
  followupLabel: 'הודעת חזרה',
  manage: 'טיפול',
  take: 'לקחת אליי',
  assignLabel: 'שיוך',
  nobody: 'בלי שיוך',
  close: 'סימון כסגורה',
  reopen: 'פתיחה מחדש',
  markAnswered: 'סימון כנענתה',
  actionError: 'העדכון לא הצליח. אפשר לנסות שוב.',
}

const STATUS_TONE: Record<InboxStatus, Tone> = { open: 'warn', answered: 'info', closed: 'ok' }

function newToken(): string {
  const c = globalThis.crypto
  if (typeof c.randomUUID === 'function') return c.randomUUID()
  return Array.from(c.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('')
}

/** רענון תקופתי — רק כשהלשונית גלויה. */
function usePolling(fn: () => void, ms: number) {
  const saved = useRef(fn)
  saved.current = fn
  useEffect(() => {
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') saved.current()
    }, ms)
    return () => window.clearInterval(id)
  }, [ms])
}

function useLoad<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const seq = useRef(0)
  const reload = useCallback(() => {
    const n = ++seq.current
    setLoading(true)
    load()
      .then((d) => {
        if (n === seq.current) {
          setData(d)
          setError(null)
        }
      })
      .catch((e: unknown) => {
        if (n === seq.current) setError(e instanceof Error ? e.message : 'הטעינה לא הצליחה')
      })
      .finally(() => {
        if (n === seq.current) setLoading(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(reload, [reload])
  return { data, setData, error, loading, reload }
}

function displayName(t: { name: string; phone: string }): string {
  return t.name || t.phone
}

// ── מרכז השליטה ─────────────────────────────────────────────────────────

export function InboxPage({ route, meId }: { route: AdminRoute; meId: number }) {
  const filter = (route.params.get('status') as InboxFilter) || 'open'
  const mine = route.params.get('mine') === '1'
  return (
    <InboxView
      selectedId={route.id ? Number(route.id) : null}
      filter={filter}
      mine={mine}
      meId={meId}
      onSelect={(id) => navigate('inbox', id, { status: filter === 'open' ? null : filter, mine: mine ? 1 : null })}
      onFilter={(f, m) => navigate('inbox', null, { status: f === 'open' ? null : f, mine: m ? 1 : null }, { replace: true })}
      eventHref={(id) => routeHref('people', `e${id}`)}
    />
  )
}

/** מספר השיחות שמחכות למענה — לתפריט של מרכז השליטה. */
export function InboxNavBadge() {
  const [open, setOpen] = useState(0)
  const load = useCallback(() => {
    fetchInboxSummary().then((s) => setOpen(s.open)).catch(() => undefined)
  }, [])
  useEffect(load, [load])
  usePolling(load, 60_000)
  if (open <= 0) return null
  return (
    <span className="adm-nav-badge" aria-label={`${open} שיחות WhatsApp מחכות למענה`}>
      {open}
    </span>
  )
}

// ── התצוגה עצמה (גם במסך הטלפן) ──────────────────────────────────────────

export function InboxView({
  selectedId,
  filter,
  mine,
  meId,
  onSelect,
  onFilter,
  eventHref,
}: {
  selectedId: number | null
  filter: InboxFilter
  mine: boolean
  meId: number
  onSelect: (id: number | null) => void
  onFilter: (filter: InboxFilter, mine: boolean) => void
  eventHref?: (eventId: number) => string
}) {
  if (selectedId) {
    return <ThreadView id={selectedId} meId={meId} onBack={() => onSelect(null)} eventHref={eventHref} />
  }
  return <ThreadList filter={filter} mine={mine} onSelect={onSelect} onFilter={onFilter} />
}

function ThreadList({
  filter,
  mine,
  onSelect,
  onFilter,
}: {
  filter: InboxFilter
  mine: boolean
  onSelect: (id: number) => void
  onFilter: (filter: InboxFilter, mine: boolean) => void
}) {
  const { data, error, loading, reload } = useLoad(() => fetchInboxThreads(filter, mine), [filter, mine])
  usePolling(reload, 30_000)
  return (
    <div className="adm-page wa-inbox">
      <PageHeader title={T.title} subtitle={T.subtitle} />
      <div className="wa-inbox-filters">
        <Tabs<InboxFilter>
          label={T.filterLabel}
          active={filter}
          onChange={(f) => onFilter(f, mine)}
          tabs={(['open', 'answered', 'closed', 'all'] as InboxFilter[]).map((k) => ({ key: k, label: T.tabs[k] }))}
        />
        <label className="wa-inbox-mine">
          <input type="checkbox" checked={mine} onChange={(e) => onFilter(filter, e.target.checked)} />
          {T.mineOnly}
        </label>
      </div>
      {loading && !data ? (
        <Loading />
      ) : error && !data ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data || data.length === 0 ? (
        <EmptyState title={filter === 'open' ? T.emptyOpen : T.empty} text={T.emptyText} />
      ) : (
        <ul className="adm-list">
          {data.map((t) => (
            <li key={t.id}>
              <ThreadRow t={t} onSelect={onSelect} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ThreadRow({ t, onSelect }: { t: InboxThreadRow; onSelect: (id: number) => void }) {
  return (
    <button type="button" className="adm-list-row wa-inbox-row" onClick={() => onSelect(t.id)}>
      <span className={`wa-inbox-dot${t.status === 'open' ? ' is-open' : ''}`} aria-hidden="true" />
      <span className="adm-list-main">
        <span className="adm-list-title">{displayName(t)}</span>
        <span className="adm-list-sub wa-inbox-preview">
          {t.preview_direction === 'outbound' ? T.ourPrefix : ''}
          {t.preview}
        </span>
        <span className="adm-list-sub">
          {t.name && (
            <>
              <bdi dir="ltr">{t.phone}</bdi> ·{' '}
            </>
          )}
          {T.sender[t.sender_kind]} · {fmtDateTime(t.last_message_at)} ·{' '}
          {t.assigned_to ? T.assignedTo(t.assigned_to.name) : T.unassigned}
        </span>
      </span>
      <StatusPill tone={STATUS_TONE[t.status]}>{T.status[t.status]}</StatusPill>
    </button>
  )
}

function ThreadView({
  id,
  meId,
  onBack,
  eventHref,
}: {
  id: number
  meId: number
  onBack: () => void
  eventHref?: (eventId: number) => string
}) {
  const { data, setData, error, loading, reload } = useLoad(() => fetchInboxThread(id), [id])
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  usePolling(() => {
    if (!busy) reload()
  }, 20_000)

  if (loading && !data) return <Loading />
  if (error && !data) return <ErrorState message={error} onRetry={reload} />
  if (!data) return null
  const t = data

  async function act(fn: () => Promise<InboxThreadDetail>) {
    setBusy(true)
    setActionError(null)
    try {
      setData(await fn())
    } catch {
      setActionError(T.actionError)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="adm-page wa-inbox">
      <p className="adm-quiet">
        <button type="button" className="adm-link-btn" onClick={onBack}>
          {T.back}
        </button>
      </p>
      <header className="adm-page-head">
        <div>
          <h1 className="adm-page-title">{displayName(t)}</h1>
          <p className="adm-page-sub">
            <span dir="ltr">{t.phone}</span> · {T.sender[t.sender_kind]}
          </p>
        </div>
        <div className="adm-page-actions">
          <StatusPill tone={STATUS_TONE[t.status]}>{T.status[t.status]}</StatusPill>
        </div>
      </header>

      <section className="adm-section" aria-labelledby="wa-who">
        <h2 className="adm-section-title" id="wa-who">
          {T.whoTitle}
        </h2>
        {t.account ? (
          <p>
            {t.account.name || '—'}
            {t.account.email && (
              <>
                {' · '}
                <a href={`mailto:${t.account.email}`} dir="ltr">
                  {t.account.email}
                </a>
              </>
            )}
          </p>
        ) : null}
        {t.profile_name && <p className="adm-quiet">{T.whatsappName(t.profile_name)}</p>}
        {t.account && t.account.events.length > 0 && (
          <p>
            {T.events}:{' '}
            {t.account.events.map((e, i) => (
              <span key={e.id}>
                {i > 0 && ' · '}
                {eventHref ? <a href={eventHref(e.id)}>{e.title}</a> : e.title}
              </span>
            ))}
          </p>
        )}
        {t.sender_kind === 'guest' && <p className="adm-quiet">{T.guestHint}</p>}
      </section>

      <section className="adm-section" aria-labelledby="wa-conv">
        <h2 className="adm-section-title" id="wa-conv">
          {T.conversation}
        </h2>
        <ol className="wa-inbox-thread">
          {t.messages.map((m) => (
            <MessageBubble key={m.id} m={m} />
          ))}
        </ol>
        <Composer thread={t} onSent={setData} />
      </section>

      <section className="adm-section" aria-labelledby="wa-manage">
        <h2 className="adm-section-title" id="wa-manage">
          {T.manage}
        </h2>
        <div className="adm-page-actions wa-inbox-actions">
          {t.assigned_to?.id !== meId && (
            <button type="button" className="adm-btn" disabled={busy} onClick={() => void act(() => assignInboxThread(t.id, meId))}>
              {T.take}
            </button>
          )}
          <label className="adm-formfield wa-inbox-assign">
            <span className="adm-label">{T.assignLabel}</span>
            <select
              className="adm-input adm-input-sm"
              value={t.assigned_to?.id ?? ''}
              disabled={busy}
              onChange={(e) => {
                const v = e.target.value ? Number(e.target.value) : null
                void act(() => assignInboxThread(t.id, v))
              }}
            >
              <option value="">{T.nobody}</option>
              {t.agents.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </label>
          {t.status === 'open' && (
            <button type="button" className="adm-btn" disabled={busy} onClick={() => void act(() => setInboxStatus(t.id, 'answered'))}>
              {T.markAnswered}
            </button>
          )}
          {t.status !== 'closed' ? (
            <button type="button" className="adm-btn adm-btn-primary" disabled={busy} onClick={() => void act(() => setInboxStatus(t.id, 'closed'))}>
              {T.close}
            </button>
          ) : (
            <button type="button" className="adm-btn" disabled={busy} onClick={() => void act(() => setInboxStatus(t.id, 'open'))}>
              {T.reopen}
            </button>
          )}
        </div>
        {actionError && (
          <p className="adm-inline-error" role="alert">
            {actionError}
          </p>
        )}
      </section>
    </div>
  )
}

function MessageBubble({ m }: { m: InboxMessage }) {
  const out = m.direction === 'outbound'
  const failed = m.status === 'failed' || m.status === 'blocked'
  const who = out
    ? m.kind === 'auto_reply' ? T.autoReply
      : m.kind === 'followup' ? `${T.followupLabel}${m.sent_by?.name ? ` · ${m.sent_by.name}` : ''}`
        : m.sent_by?.name ?? ''
    : ''
  return (
    <li className={`wa-inbox-msg ${out ? 'is-out' : 'is-in'}${failed ? ' is-failed' : ''}`}>
      <p className="wa-inbox-body">{m.body}</p>
      <p className="wa-inbox-meta">
        {fmtDateTime(m.created_at)}
        {who && ` · ${who}`}
        {out && T.outStatus[m.status] && ` · ${T.outStatus[m.status]}`}
        {out && failed && m.failure_reason && ` — ${m.failure_reason}`}
      </p>
    </li>
  )
}

function hoursLeft(iso: string | null): number {
  if (!iso) return 0
  const withZone = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`
  return Math.floor((new Date(withZone).getTime() - Date.now()) / 3_600_000)
}

/** החלון סגור: הודעת חזרה בתבנית מאושרת (`veya_support_followup`), פעם אחת עד שהפונה עונה. */
function FollowupPanel({ thread, onSent }: { thread: InboxThreadDetail; onSent: (t: InboxThreadDetail) => void }) {
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'ok' | 'bad'; text: string } | null>(null)

  if (thread.followup_waiting) {
    return <p className="wa-inbox-closed">{T.followupWaiting}</p>
  }

  async function send() {
    setBusy(true)
    setNotice(null)
    try {
      const next = await sendInboxFollowup(thread.id)
      const mine = [...next.messages].reverse().find((m) => m.direction === 'outbound' && m.kind === 'followup')
      onSent(next)
      if (mine && (mine.status === 'failed' || mine.status === 'blocked')) {
        setNotice({ tone: 'bad', text: T.notSent(mine.failure_reason) })
      } else {
        setNotice({ tone: 'ok', text: mine?.status === 'mock' ? T.followupMock : T.followupSent })
      }
    } catch (e) {
      setNotice({ tone: 'bad', text: e instanceof Error && e.message ? e.message : T.sendError })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="wa-inbox-composer">
      <p className="wa-inbox-closed">{T.windowClosed}</p>
      <p className="adm-label">{T.followupPreviewLabel}</p>
      <p className="wa-inbox-followup-preview">{T.followupText}</p>
      <div className="wa-inbox-composer-row">
        <button
          type="button"
          className="adm-btn adm-btn-primary"
          onClick={() => void send()}
          disabled={busy}
          aria-busy={busy}
        >
          {busy ? T.followupSending : T.followupSend}
        </button>
        <span className="adm-quiet">{T.followupHint}</span>
      </div>
      {notice && (
        <p className={notice.tone === 'bad' ? 'adm-inline-error' : 'wa-inbox-ok'} role={notice.tone === 'bad' ? 'alert' : 'status'}>
          {notice.text}
        </p>
      )}
    </div>
  )
}

function Composer({ thread, onSent }: { thread: InboxThreadDetail; onSent: (t: InboxThreadDetail) => void }) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<{ tone: 'ok' | 'bad'; text: string } | null>(null)
  // מזהה אחד לכל טיוטה: ניסיון חוזר אחרי כשל — אותו מזהה; אחרי שליחה — חדש.
  const [token, setToken] = useState(newToken)
  const inFlight = useRef(false)

  if (!thread.window_open) {
    return <FollowupPanel thread={thread} onSent={onSent} />
  }

  async function send() {
    if (inFlight.current || !text.trim()) return
    inFlight.current = true
    setBusy(true)
    setNotice(null)
    try {
      const next = await sendInboxReply(thread.id, text, token)
      const mine = [...next.messages].reverse().find((m) => m.direction === 'outbound' && m.kind === 'reply')
      onSent(next)
      if (mine && (mine.status === 'failed' || mine.status === 'blocked')) {
        setNotice({ tone: 'bad', text: T.notSent(mine.failure_reason) })
      } else {
        setText('')
        setToken(newToken())
        setNotice({ tone: 'ok', text: mine?.status === 'mock' ? T.savedMock : T.sent })
      }
    } catch (e) {
      setNotice({ tone: 'bad', text: e instanceof Error && e.message ? e.message : T.sendError })
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  const left = hoursLeft(thread.window_closes_at)
  return (
    <div className="wa-inbox-composer">
      <label className="adm-formfield">
        <span className="adm-label">{T.replyLabel}</span>
        <textarea
          className="adm-input"
          rows={4}
          maxLength={4096}
          value={text}
          disabled={busy}
          placeholder={T.replyPlaceholder}
          onChange={(e) => {
            setText(e.target.value)
            setNotice(null)
          }}
        />
      </label>
      <div className="wa-inbox-composer-row">
        <button
          type="button"
          className="adm-btn adm-btn-primary"
          onClick={() => void send()}
          disabled={busy || !text.trim()}
          aria-busy={busy}
        >
          {busy ? T.sending : T.send}
        </button>
        <span className="adm-quiet">{T.windowLeft(fmtDateTime(thread.window_closes_at), left)}</span>
      </div>
      {notice && (
        <p className={notice.tone === 'bad' ? 'adm-inline-error' : 'wa-inbox-ok'} role={notice.tone === 'bad' ? 'alert' : 'status'}>
          {notice.text}
        </p>
      )}
    </div>
  )
}
