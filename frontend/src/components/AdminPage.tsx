import { useEffect, useState } from 'react'
import {
  adminCreateAccount,
  adminCreateVeyaTemplate,
  adminDeleteVeyaTemplate,
  adminListVeyaTemplates,
  adminListVeyaWorkflow,
  adminMessageStats,
  adminUpdateVeyaTemplate,
  adminUpdateVeyaWorkflowStep,
} from '../api'
import type {
  AdminMessageStats,
  VeyaStage,
  VeyaTemplate,
  VeyaWorkflowStep,
} from '../types'

/** שמות ידידותיים לשלבי המסלול (לא מציגים לאדמין קודים טכניים). */
const STAGE_LABELS: Record<VeyaStage, string> = {
  invitation: 'הזמנה',
  first_reminder: 'תזכורת ראשונה',
  second_reminder: 'תזכורת שנייה',
  thank_you: 'תודה (למי שאישר)',
  before_event: 'לפני האירוע',
}

const STAGE_ORDER: VeyaStage[] = [
  'invitation',
  'first_reminder',
  'second_reminder',
  'thank_you',
  'before_event',
]

const ACTION_LABELS: Record<string, string> = {
  send: 'שליחת הודעה',
  phone_followup: 'מעקב טלפוני',
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
      setError(err instanceof Error ? err.message : 'לא הצלחנו ליצור את החשבון, נסו שוב')
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

/** כרטיס עריכה לתבנית VEYA אחת — עריכה מקומית + שמירה/מחיקה. */
function VeyaTemplateCard({
  tpl,
  onSaved,
  onDeleted,
}: {
  tpl: VeyaTemplate
  onSaved: (t: VeyaTemplate) => void
  onDeleted: (id: number) => void
}) {
  const [name, setName] = useState(tpl.name)
  const [stage, setStage] = useState<VeyaStage>(tpl.stage)
  const [body, setBody] = useState(tpl.body)
  const [isDefault, setIsDefault] = useState(tpl.is_default)
  const [active, setActive] = useState(tpl.active)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const dirty =
    name !== tpl.name ||
    stage !== tpl.stage ||
    body !== tpl.body ||
    isDefault !== tpl.is_default ||
    active !== tpl.active

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const updated = await adminUpdateVeyaTemplate(tpl.id, {
        name,
        stage,
        body,
        is_default: isDefault,
        active,
      })
      onSaved(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'השמירה נכשלה, נסו שוב')
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!confirm(`למחוק את התבנית "${tpl.name}"?`)) return
    setBusy(true)
    setError(null)
    try {
      await adminDeleteVeyaTemplate(tpl.id)
      onDeleted(tpl.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'המחיקה נכשלה, נסו שוב')
      setBusy(false)
    }
  }

  return (
    <div className={`veya-tpl-card ${active ? '' : 'inactive'}`}>
      <div className="veya-tpl-head">
        <input
          className="veya-tpl-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="שם התבנית"
        />
        <select value={stage} onChange={(e) => setStage(e.target.value as VeyaStage)}>
          {STAGE_ORDER.map((s) => (
            <option key={s} value={s}>
              {STAGE_LABELS[s]}
            </option>
          ))}
        </select>
      </div>
      <textarea
        className="veya-tpl-body"
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={4}
        dir="rtl"
        placeholder="נוסח ההודעה (אפשר להשתמש בכינויים כמו [שם אורח])"
      />
      <div className="veya-tpl-foot">
        <label className="veya-chk">
          <input
            type="checkbox"
            checked={isDefault}
            onChange={(e) => setIsDefault(e.target.checked)}
          />
          ברירת מחדל לשלב זה
        </label>
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
          <button type="button" className="btn-ghost btn-sm danger" onClick={remove} disabled={busy}>
            מחיקה
          </button>
        </span>
      </div>
      {error && <div className="auth-error">{error}</div>}
    </div>
  )
}

/** טופס הוספת תבנית VEYA חדשה. */
function AddVeyaTemplate({ onAdded }: { onAdded: (t: VeyaTemplate) => void }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [stage, setStage] = useState<VeyaStage>('invitation')
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const created = await adminCreateVeyaTemplate({ name, stage, body, active: true })
      onAdded(created)
      setName('')
      setBody('')
      setStage('invitation')
      setOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'ההוספה נכשלה, נסו שוב')
    } finally {
      setBusy(false)
    }
  }

  if (!open) {
    return (
      <button type="button" className="btn-ghost veya-add-btn" onClick={() => setOpen(true)}>
        + הוספת תבנית
      </button>
    )
  }

  return (
    <form className="veya-tpl-card veya-add-form" onSubmit={submit}>
      <div className="veya-tpl-head">
        <input
          className="veya-tpl-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="שם התבנית"
          required
        />
        <select value={stage} onChange={(e) => setStage(e.target.value as VeyaStage)}>
          {STAGE_ORDER.map((s) => (
            <option key={s} value={s}>
              {STAGE_LABELS[s]}
            </option>
          ))}
        </select>
      </div>
      <textarea
        className="veya-tpl-body"
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={4}
        dir="rtl"
        placeholder="נוסח ההודעה (אפשר להשתמש בכינויים כמו [שם אורח])"
        required
      />
      <div className="veya-tpl-foot">
        <span className="veya-tpl-actions">
          <button type="submit" className="btn-primary btn-sm" disabled={busy}>
            {busy ? 'רגע…' : 'הוספה'}
          </button>
          <button
            type="button"
            className="btn-ghost btn-sm"
            onClick={() => setOpen(false)}
            disabled={busy}
          >
            ביטול
          </button>
        </span>
      </div>
      {error && <div className="auth-error">{error}</div>}
    </form>
  )
}

/** כרטיס עריכה לשלב אחד במסלול הקבוע — עריכת מרווח ימים/שם/הפעלה. */
function VeyaStepCard({
  step,
  onSaved,
}: {
  step: VeyaWorkflowStep
  onSaved: (s: VeyaWorkflowStep) => void
}) {
  const [name, setName] = useState(step.name)
  const [offset, setOffset] = useState(step.offset_days)
  const [active, setActive] = useState(step.active)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const dirty = name !== step.name || offset !== step.offset_days || active !== step.active

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const updated = await adminUpdateVeyaWorkflowStep(step.id, {
        name,
        offset_days: offset,
        active,
      })
      onSaved(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'השמירה נכשלה, נסו שוב')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={`veya-step-card ${active ? '' : 'inactive'}`}>
      <span className="veya-step-order">{step.step_order}</span>
      <div className="veya-step-main">
        <input
          className="veya-step-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="שם השלב"
        />
        <div className="veya-step-meta">
          <span className="badge">{ACTION_LABELS[step.action_kind] ?? step.action_kind}</span>
          <span className="badge">{STAGE_LABELS[step.template_stage as VeyaStage] ?? step.template_stage}</span>
        </div>
      </div>
      <label className="veya-step-offset">
        אחרי
        <input
          type="number"
          min={0}
          max={90}
          value={offset}
          onChange={(e) => setOffset(Number(e.target.value) || 0)}
        />
        ימים
      </label>
      <label className="veya-chk">
        <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
        פעיל
      </label>
      <button type="button" className="btn-primary btn-sm" onClick={save} disabled={busy || !dirty}>
        {busy ? 'רגע…' : dirty ? 'שמירה' : 'נשמר'}
      </button>
      {error && <div className="auth-error veya-step-error">{error}</div>}
    </div>
  )
}

/** ניהול ברירות המחדל הגלובליות של VEYA — ספריית תבניות + המסלול הקבוע. */
export function VeyaDefaultsManager() {
  const [templates, setTemplates] = useState<VeyaTemplate[] | null>(null)
  const [workflow, setWorkflow] = useState<VeyaWorkflowStep[] | null>(null)
  const [stats, setStats] = useState<AdminMessageStats | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([adminListVeyaTemplates(), adminListVeyaWorkflow()])
      .then(([t, w]) => {
        setTemplates(t)
        setWorkflow(w)
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'שגיאה בטעינת ברירות המחדל'),
      )
    // נפח ההודעות — לא חוסם את המסך אם נכשל.
    adminMessageStats()
      .then(setStats)
      .catch(() => setStats(null))
  }, [])

  if (error) return <div className="admin-error">{error}</div>
  if (!templates || !workflow) return <div className="admin-loading">טוען ברירות מחדל…</div>

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

      <h2 className="admin-section-title">מסלול אישורי ההגעה הקבוע</h2>
      <p className="file-name">
        השלבים רצים אוטומטית על כל אירוע חדש. אפשר לשנות את מרווחי הימים, לשנות שם
        או להשבית שלב — השינויים חלים על אירועים חדשים.
      </p>
      <div className="veya-steps">
        {workflow.map((s) => (
          <VeyaStepCard
            key={s.id}
            step={s}
            onSaved={(u) => setWorkflow((prev) => prev!.map((x) => (x.id === u.id ? u : x)))}
          />
        ))}
      </div>

      <h2 className="admin-section-title">ספריית תבניות ההודעות</h2>
      <p className="file-name">
        התבניות שכל אירוע חדש מקבל כברירת מחדל. אפשר לערוך נוסח, לסמן ברירת מחדל לכל שלב,
        להשבית או להוסיף תבניות חדשות.
      </p>
      <div className="veya-tpl-list">
        {templates.map((t) => (
          <VeyaTemplateCard
            key={t.id}
            tpl={t}
            onSaved={(u) => setTemplates((prev) => prev!.map((x) => (x.id === u.id ? u : x)))}
            onDeleted={(id) => setTemplates((prev) => prev!.filter((x) => x.id !== id))}
          />
        ))}
      </div>
      <AddVeyaTemplate onAdded={(t) => setTemplates((prev) => [...(prev ?? []), t])} />
    </div>
  )
}

