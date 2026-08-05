import { useEffect, useState } from 'react'
import {
  adminBackfillMessageDefaults,
  adminCreateAccount,
  adminListMessageDefaults,
  adminMessageStats,
  adminUpdateMessageDefault,
} from '../api'
import type { AdminMessageStats, MessageDefault } from '../types'
import { MESSAGE_TYPES } from '../types'
import { strings } from '../strings/he'

/** תוויות סוגי האירוע לקיבוץ ברשימת ברירות המחדל (מקור: event_type בשרת). */
const EVENT_TYPE_LABELS: Record<string, string> = {
  wedding: 'חתונה',
  bar_mitzvah: 'בר מצווה',
  bat_mitzvah: 'בת מצווה',
  henna: 'חינה',
  brit: 'ברית / בריתה',
  family: 'אירוע משפחתי',
  business: 'אירוע עסקי',
  other: 'אירוע אחר',
}
const EVENT_TYPE_ORDER = Object.keys(EVENT_TYPE_LABELS)

const MESSAGE_KIND_LABELS: Record<string, string> = {
  invitation: 'הזמנות',
  reminder: 'תזכורות',
  pre_event: 'לפני האירוע',
  thank_you: 'תודה',
  reply: 'תשובות',
  custom: 'מותאם',
}

/** טופס יצירת חשבון מפיק/אולם — לתפקידים אלו אין הרשמה עצמאית. */
export function CreateAccountForm({ onCreated }: { onCreated: () => void }) {
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [accountType, setAccountType] = useState<'planner' | 'venue'>('planner')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ email: string; temporary_password: string } | null>(
    null,
  )

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setResult(null)
    setBusy(true)
    try {
      const res = await adminCreateAccount({
        email,
        display_name: displayName,
        account_type: accountType,
      })
      setResult({ email: res.email, temporary_password: res.temporary_password })
      setEmail('')
      setDisplayName('')
      onCreated()
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.adminAccountCreateFailed)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="admin-create-account">
      <h2 className="admin-section-title">יצירת חשבון מפיק / אולם</h2>
      <p className="file-name">
        למפיקים ואולמות אין הרשמה עצמאית — יוצרים להם כאן חשבון עם סיסמה זמנית,
        ומוסרים להם אותה כדי שיתחברו וישנו אותה בעצמם.
      </p>
      <form className="auth-form event-new-form" onSubmit={submit}>
        <div className="event-new-grid">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="אימייל"
            dir="ltr"
            required
          />
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="שם תצוגה"
            required
          />
          <select
            value={accountType}
            onChange={(e) => setAccountType(e.target.value as 'planner' | 'venue')}
          >
            <option value="planner">מפיק</option>
            <option value="venue">אולם</option>
          </select>
        </div>
        {error && <div className="auth-error">{error}</div>}
        {result && (
          <div className="auth-note">
            החשבון נוצר עבור {result.email}. סיסמה זמנית (למסירה חד-פעמית):{' '}
            <strong dir="ltr">{result.temporary_password}</strong>
          </div>
        )}
        <div className="event-new-actions">
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? 'רגע…' : 'יצירת חשבון'}
          </button>
        </div>
      </form>
    </div>
  )
}

/** כרטיס עריכה לברירת מחדל אחת (event_type × message_type) — עריכת
 * title/content/is_active + שמירה. אין יצירה/מחיקה — 48 השורות קבועות. */
function MessageDefaultCard({
  d,
  onSaved,
}: {
  d: MessageDefault
  onSaved: (d: MessageDefault) => void
}) {
  const [title, setTitle] = useState(d.title)
  const [content, setContent] = useState(d.content)
  const [active, setActive] = useState(d.is_active)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const dirty = title !== d.title || content !== d.content || active !== d.is_active

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const updated = await adminUpdateMessageDefault(d.id, { title, content, is_active: active })
      onSaved(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.adminSaveFailedRetry)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`veya-tpl-card ${active ? '' : 'inactive'}`}>
      <div className="veya-tpl-head">
        <input
          className="veya-tpl-name"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="כותרת ההודעה"
        />
      </div>
      <textarea
        className="veya-tpl-body"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={4}
        dir="rtl"
        placeholder="עדיין אין תוכן — הזינו כאן את הנוסח הסופי"
      />
      <div className="veya-tpl-foot">
        <label className="veya-chk">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          פעילה
        </label>
        <span className="veya-tpl-actions">
          <button
            type="button"
            className="btn-primary btn-sm"
            onClick={save}
            disabled={busy || !dirty}
          >
            {busy ? 'רגע…' : dirty ? 'שמירה' : 'נשמר'}
          </button>
        </span>
      </div>
      {error && <div className="auth-error">{error}</div>}
    </div>
  )
}

/** ניהול ברירות המחדל הגלובליות לרצף "תקשורת עם אורחים" — 8 סוגי אירוע ×
 * 6 סוגי הודעה. כאן מוזנים הטקסטים הסופיים; כל אירוע חדש מעתיק מכאן. */
export function MessageDefaultsManager() {
  const [defaults, setDefaults] = useState<MessageDefault[] | null>(null)
  const [stats, setStats] = useState<AdminMessageStats | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [backfillNote, setBackfillNote] = useState('')
  const [backfilling, setBackfilling] = useState(false)

  useEffect(() => {
    adminListMessageDefaults()
      .then(setDefaults)
      .catch((err) =>
        setError(err instanceof Error ? err.message : strings.errors.adminDefaultsLoadFailed),
      )
    // נפח ההודעות — לא חוסם את המסך אם נכשל.
    adminMessageStats()
      .then(setStats)
      .catch(() => setStats(null))
  }, [])

  async function runBackfill() {
    setBackfilling(true)
    setBackfillNote('')
    try {
      const res = await adminBackfillMessageDefaults()
      setBackfillNote(
        `נבדקו ${res.events_processed} אירועים, נוצרו ${res.messages_created} הודעות חדשות`,
      )
    } catch (err) {
      setBackfillNote(err instanceof Error ? err.message : 'הרצת ה-Backfill נכשלה')
    } finally {
      setBackfilling(false)
    }
  }

  if (error) return <div className="admin-error">{error}</div>
  if (!defaults) return <div className="admin-loading">טוען ברירות מחדל…</div>

  const byType = new Map<string, MessageDefault[]>()
  for (const d of defaults) {
    const list = byType.get(d.event_type) ?? []
    list.push(d)
    byType.set(d.event_type, list)
  }
  const order = new Map(MESSAGE_TYPES.map((mt, i) => [mt, i]))

  return (
    <div className="veya-defaults">
      {stats && (
        <>
          <h2 className="admin-section-title">נפח ההודעות במערכת</h2>
          <div className="veya-msg-stats">
            <div className="veya-msg-stat total">
              <span className="veya-msg-num">{stats.total_outbound}</span>
              <span className="veya-msg-label">נשלחו בסה״כ</span>
            </div>
            {stats.by_kind.map((s) => (
              <div className="veya-msg-stat" key={s.kind}>
                <span className="veya-msg-num">{s.count}</span>
                <span className="veya-msg-label">
                  {MESSAGE_KIND_LABELS[s.kind] ?? s.kind}
                </span>
              </div>
            ))}
            <div className="veya-msg-stat">
              <span className="veya-msg-num">{stats.total_inbound}</span>
              <span className="veya-msg-label">תשובות שהתקבלו</span>
            </div>
          </div>
        </>
      )}

      <h2 className="admin-section-title">תקשורת עם אורחים — ברירות המחדל</h2>
      <p className="file-name">
        6 ההודעות הקבועות לכל סוג אירוע. כל אירוע חדש מקבל אוטומטית עותק
        לעריכה משלו; שינוי כאן משפיע רק על אירועים עתידיים.
      </p>
      <div className="veya-tpl-actions" style={{ marginBottom: 16 }}>
        <button
          type="button"
          className="btn-ghost btn-sm"
          onClick={runBackfill}
          disabled={backfilling}
        >
          {backfilling ? 'מריץ…' : 'הקצאה לכל האירועים הקיימים (Backfill)'}
        </button>
        {backfillNote && <span className="file-name">{backfillNote}</span>}
      </div>

      {EVENT_TYPE_ORDER.map((eventType) => {
        const rows = (byType.get(eventType) ?? []).slice().sort(
          (a, b) => (order.get(a.message_type) ?? 99) - (order.get(b.message_type) ?? 99),
        )
        if (rows.length === 0) return null
        return (
          <div key={eventType} className="veya-tpl-list">
            <h3 className="admin-section-title" style={{ fontSize: 16 }}>
              {EVENT_TYPE_LABELS[eventType] ?? eventType}
            </h3>
            {rows.map((d) => (
              <MessageDefaultCard
                key={d.id}
                d={d}
                onSaved={(u) => setDefaults((prev) => prev!.map((x) => (x.id === u.id ? u : x)))}
              />
            ))}
          </div>
        )
      })}
    </div>
  )
}

