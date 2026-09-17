import { useState } from 'react'
import { rules, type FeatureRow } from '../../rulesApi'
import {
  ConfirmAction,
  Drawer,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  StatusPill,
  useAsync,
  useToast,
} from '../../ui'

const STATUS_TONE = { active: 'ok', beta: 'info', off: 'neutral' } as const
const SOURCE_LABEL = { admin: 'נקבע באדמין', env: 'מתג בשרת', default: 'ברירת מחדל' }

export function FeaturesPage() {
  const toast = useToast()
  const data = useAsync(rules.features, [])
  const [open, setOpen] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [pending, setPending] = useState<{ f: FeatureRow; status: FeatureRow['status'] } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(action: () => Promise<{ features: FeatureRow[] }>, msg: string) {
    setBusy(true)
    setError(null)
    try {
      const r = await action()
      data.setData(data.data ? { ...data.data, features: r.features } : null)
      toast(msg)
      return true
    } catch (e) {
      setError(e instanceof Error ? e.message : 'הפעולה נכשלה')
      return false
    } finally {
      setBusy(false)
    }
  }

  if (data.loading && !data.data) return <Loading />
  if (data.error && !data.data) return <ErrorState message={data.error} onRetry={data.reload} />
  const d = data.data
  if (!d) return null
  const current = d.features.find((f) => f.key === open) ?? null

  return (
    <div className="adm-page">
      <PageHeader
        title="פיצ'רים והרשאות"
        subtitle="מה פעיל ב-VEYA ולמי. חריגה למשתמש או לאירוע גוברת על הסטטוס הכללי."
        actions={
          d.can_edit && (
            <button type="button" className="adm-btn" onClick={() => setCreating(true)}>
              + פיצ'ר חדש
            </button>
          )
        }
      />
      <div className="adm-table-wrap">
        <table className="adm-table">
          <thead>
            <tr>
              <th>פיצ'ר</th>
              <th>סטטוס</th>
              <th className="adm-hide-md">נקבע</th>
              <th className="adm-num">חריגות</th>
            </tr>
          </thead>
          <tbody>
            {d.features.map((f) => (
              <tr key={f.key} className="is-clickable" tabIndex={0} onClick={() => setOpen(f.key)} onKeyDown={(e) => e.key === 'Enter' && setOpen(f.key)}>
                <td>
                  <div className="adm-cell-title">{f.label}</div>
                  <div className="adm-cell-sub">{f.description || f.key}</div>
                </td>
                <td>
                  <StatusPill tone={STATUS_TONE[f.status]}>{f.status_label}</StatusPill>
                  {!f.controllable && <div className="adm-cell-sub">קבוע</div>}
                  {!f.builtin && !f.consumed && <div className="adm-cell-sub">עוד לא בשימוש בקוד</div>}
                </td>
                <td className="adm-hide-md adm-muted">{SOURCE_LABEL[f.source]}</td>
                <td className="adm-num">{f.rules.length || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Drawer open={current !== null} onClose={() => setOpen(null)} title={current?.label ?? ''} subtitle={current?.description}>
        {current && (
          <FeatureDetail
            f={current}
            canEdit={d.can_edit}
            busy={busy}
            error={error}
            onStatus={(status) => setPending({ f: current, status })}
            onAddRule={(rule) => run(() => rules.addRule(current.key, rule), 'החריגה נשמרה')}
            onDeleteRule={(id) => run(() => rules.deleteRule(current.key, id), 'החריגה הוסרה')}
          />
        )}
      </Drawer>

      <ConfirmAction
        open={pending !== null}
        title={`שינוי סטטוס: ${pending?.f.label ?? ''}`}
        body={
          <p>
            {pending?.status === 'off'
              ? "הפיצ'ר ייסגר לכולם, חוץ ממי שיש לו חריגה פתוחה."
              : pending?.status === 'beta'
                ? "הפיצ'ר ייסגר לכולם ויישאר פתוח רק למשתמשים ולאירועים שיש להם חריגה פתוחה."
                : "הפיצ'ר ייפתח לכולם, חוץ ממי שיש לו חריגה סגורה."}
          </p>
        }
        confirmLabel="שמירה"
        danger={pending?.status !== 'active'}
        typeToConfirm={pending?.f.key === 'gifts' ? pending.f.label : undefined}
        requireReason
        busy={busy}
        error={error}
        onConfirm={async (reason) => {
          if (pending && (await run(() => rules.setStatus(pending.f.key, pending.status, reason), 'הסטטוס עודכן'))) setPending(null)
        }}
        onCancel={() => setPending(null)}
      />

      {creating && <CreateFeature onClose={() => setCreating(false)} onCreated={(features) => data.setData({ ...d, features })} />}
    </div>
  )
}

function FeatureDetail({
  f,
  canEdit,
  busy,
  error,
  onStatus,
  onAddRule,
  onDeleteRule,
}: {
  f: FeatureRow
  canEdit: boolean
  busy: boolean
  error: string | null
  onStatus: (s: FeatureRow['status']) => void
  onAddRule: (rule: { scope_type: 'event' | 'user'; scope_id: number; enabled: boolean; note: string }) => Promise<boolean>
  onDeleteRule: (id: number) => void
}) {
  const [scope, setScope] = useState<'event' | 'user'>(f.rule_scopes[0] ?? 'event')
  const [scopeId, setScopeId] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [note, setNote] = useState('')
  const statuses: FeatureRow['status'][] = ['active', 'beta', 'off']
  const labels = { active: 'פעיל', beta: 'בטא', off: 'כבוי' }

  return (
    <>
      <section>
        <h3 className="adm-section-title">סטטוס</h3>
        {f.controllable && canEdit ? (
          <div className="adm-chips" role="radiogroup" aria-label="סטטוס">
            {statuses.map((s) => (
              <button key={s} type="button" role="radio" aria-checked={f.status === s} className={`adm-chip${f.status === s ? ' is-on' : ''}`} disabled={busy} onClick={() => f.status !== s && onStatus(s)}>
                {labels[s]}
              </button>
            ))}
          </div>
        ) : (
          <p>
            <StatusPill tone={STATUS_TONE[f.status]}>{f.status_label}</StatusPill>
          </p>
        )}
        {f.reason && <p className="adm-muted">{f.reason}</p>}
        {!f.builtin && (
          <p className="adm-muted">
            פיצ'ר חדש נשמר כדגל. הוא ישפיע על המוצר מרגע שקוד כלשהו יבדוק אותו (מפתח: <span className="adm-mono">{f.key}</span>).
          </p>
        )}
      </section>

      {(f.rule_scopes.length > 0 || f.rules.length > 0) && (
        <section className="adm-section">
          <h3 className="adm-section-title">חריגות</h3>
          {f.rules.length === 0 ? (
            <EmptyState title="אין חריגות" text="כולם מקבלים את הסטטוס הכללי." />
          ) : (
            <ul className="adm-list">
              {f.rules.map((r) => (
                <li key={r.id} className="adm-list-row">
                  <StatusPill tone={r.enabled ? 'ok' : 'neutral'}>{r.enabled ? 'פתוח' : 'סגור'}</StatusPill>
                  <span className="adm-list-main">
                    <span className="adm-list-title">{r.scope_label}</span>
                    <span className="adm-list-sub">
                      {r.scope_type === 'event' ? `אירוע #${r.scope_id}` : `משתמש #${r.scope_id}`}
                      {r.note ? ` · ${r.note}` : ''}
                    </span>
                  </span>
                  {canEdit && (
                    <button type="button" className="adm-link-btn adm-danger-text" disabled={busy} onClick={() => onDeleteRule(r.id)}>
                      הסרה
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
          {canEdit && f.rule_scopes.length > 0 && (
            <div className="adm-rule-form">
              <select className="adm-input adm-input-sm" value={scope} onChange={(e) => setScope(e.target.value as 'event' | 'user')} aria-label="סוג">
                {f.rule_scopes.map((s) => (
                  <option key={s} value={s}>{s === 'event' ? 'אירוע' : 'משתמש'}</option>
                ))}
              </select>
              <input className="adm-input adm-input-sm" inputMode="numeric" placeholder={scope === 'event' ? 'מזהה אירוע' : 'מזהה משתמש'} value={scopeId} onChange={(e) => setScopeId(e.target.value.replace(/\D/g, ''))} aria-label="מזהה" />
              <select className="adm-input adm-input-sm" value={enabled ? '1' : '0'} onChange={(e) => setEnabled(e.target.value === '1')} aria-label="פתוח או סגור">
                <option value="1">פתוח</option>
                <option value="0">סגור</option>
              </select>
              <input className="adm-input adm-input-sm" placeholder="הערה" value={note} onChange={(e) => setNote(e.target.value)} aria-label="הערה" />
              <button
                type="button"
                className="adm-btn adm-btn-sm"
                disabled={busy || !scopeId}
                onClick={async () => {
                  if (await onAddRule({ scope_type: scope, scope_id: Number(scopeId), enabled, note })) {
                    setScopeId('')
                    setNote('')
                  }
                }}
              >
                הוספה
              </button>
            </div>
          )}
          {error && <p className="adm-inline-error" role="alert">{error}</p>}
        </section>
      )}
    </>
  )
}

function CreateFeature({ onClose, onCreated }: { onClose: () => void; onCreated: (f: FeatureRow[]) => void }) {
  const [form, setForm] = useState({ key: '', label: '', description: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  return (
    <Drawer
      open
      onClose={onClose}
      title="פיצ'ר חדש"
      subtitle="נוצר כבוי. מתאים להכנת פיצ'ר עתידי או לפתיחה הדרגתית."
      footer={
        <>
          <button type="button" className="adm-btn" onClick={onClose} disabled={busy}>ביטול</button>
          <button
            type="button"
            className="adm-btn adm-btn-primary"
            disabled={busy || form.label.trim().length < 2 || !/^[a-z][a-z0-9_]{2,40}$/.test(form.key)}
            onClick={async () => {
              setBusy(true)
              setError(null)
              try {
                const r = await rules.createFeature({ ...form, status: 'off' })
                onCreated(r.features)
                onClose()
              } catch (e) {
                setError(e instanceof Error ? e.message : 'היצירה נכשלה')
              } finally {
                setBusy(false)
              }
            }}
          >
            יצירה
          </button>
        </>
      }
    >
      <label className="adm-formfield">
        <span className="adm-label">שם</span>
        <input className="adm-input" value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} />
      </label>
      <label className="adm-formfield">
        <span className="adm-label">מפתח טכני</span>
        <input className="adm-input adm-mono" dir="ltr" placeholder="photo_album" value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value.toLowerCase() })} />
        <span className="adm-help">אותיות אנגליות קטנות, ספרות וקו תחתון. לא ניתן לשנות אחר כך.</span>
      </label>
      <label className="adm-formfield">
        <span className="adm-label">תיאור</span>
        <textarea className="adm-input" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
      </label>
      {error && <p className="adm-inline-error" role="alert">{error}</p>}
    </Drawer>
  )
}
