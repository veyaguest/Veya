import { useCallback, useEffect, useState } from 'react'
import {
  adminBackfillMessageDefaults,
  adminCreateAccount,
  adminCreateMessageDefaultOption,
  adminDeleteMessageDefaultOption,
  adminListMessageDefaultOptions,
  adminListMessageDefaults,
  adminMessageStats,
  adminUpdateMessageDefault,
  adminUpdateMessageDefaultOption,
} from '../api'
import type { AdminMessageStats, MessageDefault, MessageDefaultOption, MessageType } from '../types'
import { MESSAGE_TYPES } from '../types'
import { strings } from '../strings/he'

/** תוויות סוגי האירוע לקיבוץ ברשימת ברירות המחדל (מקור: event_type בשרת). */
const EVENT_TYPE_LABELS: Record<string, string> = {
  wedding: 'חתונה',
  bar_mitzvah: 'בר מצווה',
  bat_mitzvah: 'בת מצווה',
  henna: 'חינה',
  brit: 'ברית',
  brita: 'בריתה',
  business: 'אירוע עסקי',
}
const EVENT_TYPE_ORDER = Object.keys(EVENT_TYPE_LABELS)

/** תוויות שלבי ההודעה (תואם ל-backend/app/communication.py: MESSAGE_TYPE_LABELS). */
const MESSAGE_TYPE_LABELS_HE: Record<string, string> = {
  invitation: 'הזמנה',
  reminder_1: 'תזכורת ראשונה',
  reminder_2: 'תזכורת שנייה',
  final_reminder: 'תזכורת אחרונה',
  event_day: 'יום האירוע',
  thank_you: 'תודה',
}

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

/** כרטיס עריכה לנוסח אחד מתוך ספריית הבחירה (עד 12 לכל event_type×message_type).
 * כולל מחיקה — בניגוד ל-48 ברירות המחדל הקבועות, כאן אפשר גם להוסיף וגם להסיר. */
function MessageDefaultOptionCard({
  option,
  onSaved,
  onDeleted,
}: {
  option: MessageDefaultOption
  onSaved: (o: MessageDefaultOption) => void
  onDeleted: (id: number) => void
}) {
  const [tone, setTone] = useState(option.tone)
  const [content, setContent] = useState(option.content)
  const [active, setActive] = useState(option.is_active)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const dirty = tone !== option.tone || content !== option.content || active !== option.is_active

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const updated = await adminUpdateMessageDefaultOption(option.id, {
        tone, content, is_active: active,
      })
      onSaved(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.adminSaveFailedRetry)
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    setBusy(true)
    setError(null)
    try {
      await adminDeleteMessageDefaultOption(option.id)
      onDeleted(option.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.adminSaveFailedRetry)
      setBusy(false)
    }
  }

  return (
    <div className={`veya-tpl-card ${active ? '' : 'inactive'}`}>
      <div className="veya-tpl-head">
        <span className="file-name">אופציה {option.option_number}</span>
        <input
          className="veya-tpl-name"
          value={tone}
          onChange={(e) => setTone(e.target.value)}
          placeholder="תיאור קצר של הטון (למשל: חם ותמציתי)"
        />
      </div>
      <textarea
        className="veya-tpl-body"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={6}
        dir="rtl"
        placeholder="עדיין אין תוכן — הזינו כאן נוסח"
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
          <button type="button" className="btn-ghost btn-sm" onClick={remove} disabled={busy}>
            מחיקה
          </button>
        </span>
      </div>
      {error && <div className="auth-error">{error}</div>}
    </div>
  )
}

/** ניהול ספריית הנוסחים לבחירה (עד 12 לכל event_type×message_type) —
 * הזוג בוחר וריאציה מתוכה במקום נוסח קבוע יחיד (decisions.md 2026-08-06).
 * כאן האדמין גם עורך וגם מוסיף/מוחק נוסחים — לא טקסט קשיח בקוד. */
export function MessageDefaultOptionsManager() {
  const [eventType, setEventType] = useState('wedding')
  const [options, setOptions] = useState<MessageDefaultOption[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [addingType, setAddingType] = useState<MessageType | null>(null)

  // כל 6 השלבים של סוג האירוע הנבחר, בבקשה אחת — לא מסונן לשלב יחיד, כדי
  // שהאדמין יראה מיד את כל מה שכבר הוזן ולא רק את השלב הראשון (הזמנה).
  const load = useCallback(() => {
    setOptions(null)
    adminListMessageDefaultOptions(eventType)
      .then(setOptions)
      .catch((err) =>
        setError(err instanceof Error ? err.message : strings.errors.adminDefaultsLoadFailed),
      )
  }, [eventType])

  useEffect(() => {
    load()
  }, [load])

  async function addOption(messageType: MessageType) {
    setAddingType(messageType)
    setError(null)
    try {
      const created = await adminCreateMessageDefaultOption({ event_type: eventType, message_type: messageType })
      setOptions((prev) => [...(prev ?? []), created])
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.adminSaveFailedRetry)
    } finally {
      setAddingType(null)
    }
  }

  return (
    <div className="veya-defaults">
      <h2 className="admin-section-title">ספריית נוסחים לבחירה (עד 12 לכל שלב)</h2>
      <p className="file-name">
        כאן הזוג בוחר וריאציה במקום נוסח קבוע — בנוסף ל"ברירת המחדל" שמוקצית
        אוטומטית לאירוע חדש (למעלה). כל 6 השלבים של סוג האירוע מוצגים כאן יחד.
      </p>

      <div className="event-new-grid" style={{ marginBottom: 16 }}>
        <select value={eventType} onChange={(e) => setEventType(e.target.value)}>
          {EVENT_TYPE_ORDER.map((t) => (
            <option key={t} value={t}>{EVENT_TYPE_LABELS[t]}</option>
          ))}
        </select>
      </div>

      {error && <div className="admin-error">{error}</div>}
      {!error && options === null && <div className="admin-loading">טוען נוסחים…</div>}

      {options && MESSAGE_TYPES.map((mt) => {
        const rows = options
          .filter((o) => o.message_type === mt)
          .sort((a, b) => a.option_number - b.option_number)
        return (
          <div key={mt} className="veya-tpl-list">
            <h3 className="admin-section-title" style={{ fontSize: 16 }}>
              {MESSAGE_TYPE_LABELS_HE[mt]}
            </h3>
            {rows.length === 0 && (
              <p className="file-name">אין עדיין נוסחים לשלב הזה.</p>
            )}
            {rows.map((opt) => (
              <MessageDefaultOptionCard
                key={opt.id}
                option={opt}
                onSaved={(u) => setOptions((prev) => prev!.map((x) => (x.id === u.id ? u : x)))}
                onDeleted={(id) => setOptions((prev) => prev!.filter((x) => x.id !== id))}
              />
            ))}
            {rows.length < 12 && (
              <button
                type="button"
                className="btn-ghost btn-sm"
                onClick={() => addOption(mt)}
                disabled={addingType === mt}
              >
                {addingType === mt ? 'מוסיף…' : `הוספת נוסח (${rows.length}/12)`}
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}

