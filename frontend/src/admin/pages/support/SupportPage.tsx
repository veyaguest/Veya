/**
 * פניות תמיכה — פניות של בעלי אירועים מתוך "עזרה" (HELP_CENTER_PLAN.md §10.4, שלב 7).
 *
 * רשימה (פתוחות / טופלו / הכול) → פנייה אחת: מה נכתב, מה העזרה כבר בדקה,
 * "השב לפונה" (מייל לפונה מתוך המסך, 2026-10-07) והיסטוריית המענה, שינוי
 * סטטוס (נרשם ביומן) ו"כניסה לאירוע לתמיכה" (הקיים).
 *
 * **"נענתה" ≠ "טופלה":** שליחת תשובה לא משנה את הסטטוס. רק סימון "טופלה".
 * הטקסט של הלקוח ושל הצוות מוצג כטקסט בלבד (בלי HTML).
 */
import { useRef, useState } from 'react'
import {
  fetchSupportRequest, fetchSupportRequests, sendSupportReply, setSupportStatus,
  type SupportReply, type SupportRequestDetail, type SupportRequestRow, type SupportStatus,
} from '../../adminApi'
import { navigate, routeHref, type AdminRoute } from '../../route'
import {
  ConfirmAction, Drawer, EmptyState, ErrorState, Loading, PageHeader, StatusPill, Tabs,
  fmtDateTime, useAsync, useCan, useToast, type Tone,
} from '../../ui'

type Filter = 'open' | 'resolved' | 'all'

const STATUS_LABEL: Record<SupportStatus, string> = { new: 'חדשה', in_progress: 'בטיפול', resolved: 'טופלה' }
const STATUS_TONE: Record<SupportStatus, Tone> = { new: 'warn', in_progress: 'info', resolved: 'ok' }
const PLATFORM_LABEL: Record<string, string> = { desktop: 'מחשב', mobile: 'טלפון' }
const ROLE_LABEL: Record<string, string> = { owner: 'בעלים', partner: 'בן/בת זוג' }

export function SupportPage({
  route,
  onImpersonate,
}: {
  route: AdminRoute
  onImpersonate: (userId: number, eventId?: number) => Promise<void>
}) {
  if (route.id) return <SupportDetail id={Number(route.id)} onImpersonate={onImpersonate} />
  return <SupportList route={route} />
}

function SupportList({ route }: { route: AdminRoute }) {
  const filter = (route.params.get('status') as Filter) || 'open'
  const { data, error, loading, reload } = useAsync(() => fetchSupportRequests(filter), [filter])
  return (
    <div className="adm-page">
      <PageHeader title="פניות תמיכה" subtitle="פניות מתוך &quot;עזרה&quot; — עונים מכאן, במייל לפונה" />
      <Tabs<Filter>
        label="סינון פניות"
        active={filter}
        onChange={(v) => navigate('support', null, { status: v === 'open' ? null : v }, { replace: true })}
        tabs={[
          { key: 'open', label: 'פתוחות' },
          { key: 'resolved', label: 'טופלו' },
          { key: 'all', label: 'הכול' },
        ]}
      />
      {loading && !data ? (
        <Loading />
      ) : error && !data ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data || data.length === 0 ? (
        <EmptyState
          title={filter === 'open' ? 'אין פניות פתוחות' : 'אין פניות להצגה'}
          text="פניות חדשות מתוך העזרה יופיעו כאן."
        />
      ) : (
        <ul className="adm-list">
          {data.map((r) => (
            <li key={r.id}>
              <SupportListRow r={r} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function SupportListRow({ r }: { r: SupportRequestRow }) {
  return (
    <a className="adm-list-row" href={routeHref('support', r.id)}>
      {/* תמיד שלושה תאים (הגריד של adm-list-row) — גם כשאין תגית דחיפות. */}
      {r.urgency === 'high' ? <span className="adm-sev adm-sev-critical">דחוף</span> : <span aria-hidden="true" />}
      <span className="adm-list-main">
        <span className="adm-list-title">
          פנייה #{r.id} · {r.user?.name || r.user?.email || 'משתמש שנמחק'}
        </span>
        <span className="adm-list-sub">
          {r.about || 'כללי'}
          {r.event ? ` · ${r.event.title}` : ''}
          {r.event?.days_to_event != null ? ` · ${daysLabel(r.event.days_to_event)}` : ''}
          {' · '}
          {fmtDateTime(r.created_at)}
        </span>
      </span>
      <StatusPill tone={STATUS_TONE[r.status]}>{STATUS_LABEL[r.status]}</StatusPill>
    </a>
  )
}

function daysLabel(days: number): string {
  if (days < 0) return 'האירוע עבר'
  if (days === 0) return 'האירוע היום'
  if (days === 1) return 'מחר האירוע'
  return `עוד ${days} ימים לאירוע`
}

function SupportDetail({
  id,
  onImpersonate,
}: {
  id: number
  onImpersonate: (userId: number, eventId?: number) => Promise<void>
}) {
  const can = useCan()
  const toast = useToast()
  const { data, error, loading, reload } = useAsync(() => fetchSupportRequest(id), [id])
  const [current, setCurrent] = useState<SupportRequestDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [confirmEnter, setConfirmEnter] = useState(false)
  const [replyOpen, setReplyOpen] = useState(false)

  if (loading && !data) return <Loading />
  if (error && !data) return <ErrorState message={error} onRetry={reload} />
  const r = current && current.id === id ? current : data
  if (!r) return null

  async function changeStatus(status: SupportStatus) {
    setBusy(true)
    setActionError(null)
    try {
      setCurrent(await setSupportStatus(id, status))
      toast(`הסטטוס עודכן: ${STATUS_LABEL[status]}`)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'העדכון לא הצליח')
    } finally {
      setBusy(false)
    }
  }

  async function enter() {
    if (!r?.event?.owner_id) return
    setBusy(true)
    setActionError(null)
    try {
      await onImpersonate(r.event.owner_id, r.event.id)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'הכניסה נכשלה')
      setBusy(false)
    }
  }

  const ctx = r.context
  const facts = Object.entries(ctx.facts ?? {})
  return (
    <div className="adm-page">
      <p className="adm-quiet">
        <a href={routeHref('support')}>→ לכל הפניות</a>
      </p>
      <header className="adm-page-head">
        <div>
          <h1 className="adm-page-title">
            פנייה #{r.id} {r.urgency === 'high' && <span className="adm-sev adm-sev-critical">דחוף</span>}
          </h1>
          <p className="adm-page-sub">
            {fmtDateTime(r.created_at)}
            {r.handled_by ? ` · מטפל/ת: ${r.handled_by.name || r.handled_by.email}` : ''}
          </p>
        </div>
        <div className="adm-page-actions">
          <StatusPill tone={STATUS_TONE[r.status]}>{STATUS_LABEL[r.status]}</StatusPill>
          {r.event?.owner_id && can('users.impersonate') && (
            <button type="button" className="adm-btn adm-btn-primary" onClick={() => setConfirmEnter(true)} disabled={busy}>
              כניסה לאירוע לתמיכה
            </button>
          )}
        </div>
      </header>
      {actionError && <p className="adm-inline-error" role="alert">{actionError}</p>}

      <section className="adm-section" aria-labelledby="sup-who">
        <h2 className="adm-section-title" id="sup-who">מי פנה</h2>
        {r.user ? (
          <p>
            {r.user.name || '—'} ·{' '}
            <a href={`mailto:${r.user.email}?subject=${encodeURIComponent(`פנייה #${r.id} ל-VEYA`)}`}>{r.user.email}</a>
            {ctx.role ? ` · ${ROLE_LABEL[ctx.role] ?? ctx.role}` : ''}
          </p>
        ) : (
          <p className="adm-quiet">המשתמש נמחק</p>
        )}
        {r.event && (
          <p>
            <a href={routeHref('people', `e${r.event.id}`)}>{r.event.title}</a>
            {r.event.event_date ? ` · ${r.event.event_date}` : ''}
            {r.event.days_to_event != null ? ` · ${daysLabel(r.event.days_to_event)}` : ''}
          </p>
        )}
      </section>

      <section className="adm-section" aria-labelledby="sup-msg">
        <h2 className="adm-section-title" id="sup-msg">מה נכתב</h2>
        <p className="adm-support-message">{r.message}</p>
      </section>

      <ReplyHistory
        replies={r.replies ?? []}
        canReply={can('support.handle') && !!r.user?.email}
        onReply={() => setReplyOpen(true)}
      />

      <section className="adm-section" aria-labelledby="sup-ctx">
        <h2 className="adm-section-title" id="sup-ctx">מה העזרה כבר בדקה</h2>
        <table className="adm-table adm-table-plain">
          <tbody>
            <tr><th scope="row">מסך</th><td>{ctx.screen || '—'}</td></tr>
            <tr><th scope="row">נושא</th><td>{ctx.topic_id || '—'}</td></tr>
            <tr><th scope="row">בדיקה</th><td>{ctx.tree_id ? `${ctx.tree_id}${ctx.outcome ? ` → ${ctx.outcome}` : ''}` : '—'}</td></tr>
            <tr><th scope="row">מכשיר</th><td>{ctx.platform ? PLATFORM_LABEL[ctx.platform] ?? ctx.platform : '—'}</td></tr>
            <tr><th scope="row">סוג אירוע</th><td>{ctx.event_type || '—'}</td></tr>
          </tbody>
        </table>
        {(ctx.recent_errors ?? []).length > 0 && (
          <>
            <h3 className="adm-support-subtitle">שגיאות אחרונות (אחרי ניקוי)</h3>
            <ul className="adm-support-errors">
              {ctx.recent_errors!.map((e, i) => (
                <li key={i}>
                  <code>{e.method} {e.path} · {e.status}</code>
                  {e.message ? ` — ${e.message}` : ''}
                </li>
              ))}
            </ul>
          </>
        )}
        {facts.length > 0 && (
          <details className="adm-support-facts">
            <summary>עובדות המסך בזמן הפנייה ({facts.length})</summary>
            <table className="adm-table adm-table-plain">
              <tbody>
                {facts.map(([k, v]) => (
                  <tr key={k}>
                    <th scope="row"><code>{k}</code></th>
                    <td>{v === null ? 'לא ידוע' : String(v)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        )}
      </section>

      {can('support.handle') && (
        <section className="adm-section" aria-labelledby="sup-status">
          <h2 className="adm-section-title" id="sup-status">סטטוס</h2>
          <div className="adm-page-actions">
            {r.status !== 'in_progress' && (
              <button type="button" className="adm-btn" disabled={busy} onClick={() => void changeStatus('in_progress')}>
                סימון &quot;בטיפול&quot;
              </button>
            )}
            {r.status !== 'resolved' && (
              <button type="button" className="adm-btn adm-btn-primary" disabled={busy} onClick={() => void changeStatus('resolved')}>
                סימון &quot;טופלה&quot;
              </button>
            )}
            {r.status !== 'new' && (
              <button type="button" className="adm-link-btn" disabled={busy} onClick={() => void changeStatus('new')}>
                החזרה ל&quot;חדשה&quot;
              </button>
            )}
          </div>
          <p className="adm-quiet">
            הלקוח רואה את הסטטוס ב&quot;הפניות שלי&quot; בתוך העזרה. שליחת תשובה לא משנה את הסטטוס —
            רק סימון &quot;טופלה&quot;.
          </p>
        </section>
      )}

      {replyOpen && r.user && (
        <ReplyDrawer
          request={r}
          onClose={() => setReplyOpen(false)}
          onSent={(next) => {
            setCurrent(next)
            setReplyOpen(false)
            const last = next.replies[next.replies.length - 1]
            toast(last?.status === 'mock' ? 'התשובה נשמרה — בסביבה הזו אין חיבור למייל, ולכן לא נשלחה בפועל' : 'התשובה נשלחה לפונה')
          }}
        />
      )}

      <ConfirmAction
        open={confirmEnter}
        title="כניסה לאירוע לצורך תמיכה"
        body={
          <p>
            תיכנסו לממשק בדיוק כמו בעלי האירוע. כל פעולה שתבצעו שם היא פעולה אמיתית באירוע. הכניסה נרשמת ביומן.
          </p>
        }
        confirmLabel="כניסה"
        busy={busy}
        error={actionError}
        onConfirm={enter}
        onCancel={() => setConfirmEnter(false)}
      />
    </div>
  )
}

// ── מענה לפונה ───────────────────────────────────────────────────────────

const REPLY_MAX = 5000

/** מזהה חד-פעמי לחלון המענה — אותו מזהה = אותה תשובה בשרת (לחיצה כפולה /
 *  ניסיון חוזר אחרי כשל לא שולחים שתי תשובות שונות). */
function newReplyToken(): string {
  const c = globalThis.crypto
  if (typeof c.randomUUID === 'function') return c.randomUUID()
  return Array.from(c.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('')
}

function ReplyHistory({
  replies, canReply, onReply,
}: {
  replies: SupportReply[]
  canReply: boolean
  onReply: () => void
}) {
  // רק מה שבאמת יצא (או נשמר בסביבה בלי מייל). ניסיון שנכשל לא מוצג כתשובה.
  const shown = replies.filter((x) => x.status === 'sent' || x.status === 'mock')
  return (
    <section className="adm-section" aria-labelledby="sup-replies">
      <div className="adm-support-replies-head">
        <h2 className="adm-section-title" id="sup-replies">מענה לפונה</h2>
        {canReply && (
          <button type="button" className="adm-btn adm-btn-primary" onClick={onReply}>
            השב לפונה
          </button>
        )}
      </div>
      {shown.length === 0 ? (
        <p className="adm-quiet">עוד לא נשלחה תשובה מכאן.</p>
      ) : (
        <ul className="adm-support-replies">
          {shown.map((x) => (
            <li key={x.id}>
              <p className="adm-support-reply-meta">
                {x.status === 'sent'
                  ? `נשלחה ${fmtDateTime(x.sent_at)}`
                  : `נשמרה ${fmtDateTime(x.created_at)} · לא נשלחה בפועל (סביבה בלי מייל)`}
                {x.admin ? ` · ${x.admin.name || x.admin.email}` : ''}
              </p>
              <p className="adm-support-message">{x.body}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function ReplyDrawer({
  request, onClose, onSent,
}: {
  request: SupportRequestDetail
  onClose: () => void
  onSent: (next: SupportRequestDetail) => void
}) {
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // נוצר פעם אחת לכל פתיחה של החלון; ניסיון חוזר אחרי כשל — אותו מזהה.
  const [token] = useState(newReplyToken)
  // נעילה מיידית: שתי לחיצות באותו רגע לא מגיעות לשרת פעמיים (``busy`` מתעדכן
  // רק ברינדור הבא). גם אם כן — השרת מזהה את אותו token ושולח פעם אחת.
  const inFlight = useRef(false)
  const empty = text.trim().length === 0

  async function send() {
    if (inFlight.current || empty) return
    inFlight.current = true
    setBusy(true)
    setError(null)
    try {
      onSent(await sendSupportReply(request.id, text, token))
    } catch {
      inFlight.current = false
      setError('השליחה נכשלה — התשובה לא נשלחה לפונה. אפשר לנסות שוב.')
      setBusy(false)
    }
  }

  return (
    <Drawer
      open
      wide
      title="השב לפונה"
      subtitle={`פנייה #${request.id}`}
      onClose={() => !busy && onClose()}
      footer={
        <>
          <button type="button" className="adm-btn adm-btn-primary" onClick={() => void send()} disabled={busy || empty} aria-busy={busy}>
            {busy ? 'שולח…' : 'שלח תשובה'}
          </button>
          <button type="button" className="adm-btn" onClick={onClose} disabled={busy}>
            ביטול
          </button>
        </>
      }
    >
      <dl className="adm-support-reply-to">
        <dt>אל</dt>
        <dd>
          {request.user?.name ? `${request.user.name} · ` : ''}
          <span dir="ltr">{request.user?.email}</span>
        </dd>
      </dl>
      <h3 className="adm-support-subtitle">הפנייה המקורית</h3>
      <p className="adm-support-message">{request.message}</p>
      <label className="adm-formfield adm-support-reply-field">
        <span className="adm-label">התשובה</span>
        <textarea
          className="adm-input"
          rows={9}
          maxLength={REPLY_MAX}
          value={text}
          disabled={busy}
          onChange={(e) => setText(e.target.value)}
          autoFocus
        />
      </label>
      {error && <p className="adm-inline-error" role="alert">{error}</p>}
      <p className="adm-quiet">
        התשובה נשלחת כטקסט, במייל של VEYA עם החתימה של הצוות. אם הפונה יענה, התשובה תגיע אל{' '}
        <span dir="ltr">support@veyaguest.co.il</span>. שליחה לא משנה את הסטטוס של הפנייה.
      </p>
    </Drawer>
  )
}
