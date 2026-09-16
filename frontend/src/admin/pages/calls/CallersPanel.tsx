import { useState } from 'react'
import { adminDisableUser, adminEnableUser } from '../../../api'
import { callOps, type CallerRow } from '../../callOpsApi'
import { navigate } from '../../route'
import {
  ConfirmAction,
  Drawer,
  EmptyState,
  ErrorState,
  Loading,
  StatusPill,
  fmtDateTime,
  useCan,
  useToast,
} from '../../ui'

type CallersState = {
  data: CallerRow[] | null
  error: string | null
  loading: boolean
  reload: () => void
}

export function CallersPanel({ callers }: { callers: CallersState }) {
  const can = useCan()
  const [editing, setEditing] = useState<CallerRow | null>(null)
  const [creating, setCreating] = useState(false)

  if (callers.loading && !callers.data) return <Loading />
  if (callers.error && !callers.data) return <ErrorState message={callers.error} onRetry={callers.reload} />
  const rows = callers.data ?? []

  return (
    <section>
      <div className="adm-section-head">
        <p className="adm-section-desc">עומס היום ומחר לכל טלפן. טלפן לא זמין לא מקבל משימות חדשות.</p>
        {can('calls.manage') && (
          <button type="button" className="adm-btn adm-btn-primary" onClick={() => setCreating(true)}>
            + הוסף טלפן
          </button>
        )}
      </div>

      {rows.length === 0 ? (
        <EmptyState
          title="אין עדיין טלפנים"
          text="טלפן מקבל גישה רק למשימות השיחה שלו — לא לניהול."
          action={
            can('calls.manage') ? (
              <button type="button" className="adm-btn adm-btn-primary" onClick={() => setCreating(true)}>
                + הוסף טלפן
              </button>
            ) : undefined
          }
        />
      ) : (
        <div className="adm-table-wrap">
          <table className="adm-table">
            <thead>
              <tr>
                <th>טלפן</th>
                <th>זמינות</th>
                <th className="adm-num">היום</th>
                <th className="adm-num">טופלו</th>
                <th className="adm-num">ממתינות</th>
                <th className="adm-num adm-hide-md">מחר</th>
                <th className="adm-hide-md">פעילות אחרונה</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr
                  key={c.id}
                  className="is-clickable"
                  tabIndex={0}
                  onClick={() => setEditing(c)}
                  onKeyDown={(e) => e.key === 'Enter' && setEditing(c)}
                >
                  <td>
                    <div className="adm-cell-title">{c.display_name || c.email}</div>
                    <div className="adm-cell-sub">
                      {[c.group_name, c.phone].filter(Boolean).join(' · ') || c.email}
                    </div>
                  </td>
                  <td>
                    <StatusPill tone={c.disabled ? 'bad' : c.available_today ? 'ok' : 'neutral'}>
                      {c.availability_label}
                    </StatusPill>
                  </td>
                  <td className="adm-num">{c.today.tasks}</td>
                  <td className="adm-num">{c.today.handled}</td>
                  <td className="adm-num">
                    {c.today.pending}
                    {c.daily_capacity != null && <span className="adm-muted"> / {c.daily_capacity}</span>}
                  </td>
                  <td className="adm-num adm-hide-md">{c.tomorrow_tasks}</td>
                  <td className="adm-hide-md adm-muted">{c.last_activity_at ? fmtDateTime(c.last_activity_at) : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {creating && (
        <CreateCallerDrawer
          onClose={() => setCreating(false)}
          onCreated={() => callers.reload()}
        />
      )}
      {editing && (
        <CallerDrawer
          caller={editing}
          canManage={can('calls.manage')}
          canDisable={can('users.disable')}
          onClose={() => setEditing(null)}
          onSaved={(c) => {
            setEditing(c)
            callers.reload()
          }}
        />
      )}
    </section>
  )
}

function CreateCallerDrawer({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState({ display_name: '', email: '', phone: '', group_name: '', daily_capacity: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<{ email: string; password: string } | null>(null)

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const r = await callOps.createCaller({
        display_name: form.display_name.trim(),
        email: form.email.trim(),
        phone: form.phone.trim(),
        group_name: form.group_name.trim(),
        daily_capacity: form.daily_capacity ? Number(form.daily_capacity) : null,
      })
      setCreated({ email: r.caller.email, password: r.temporary_password })
      onCreated()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'יצירת הטלפן נכשלה')
    } finally {
      setBusy(false)
    }
  }

  const valid = form.display_name.trim().length >= 2 && form.email.includes('@')
  return (
    <Drawer
      open
      onClose={onClose}
      title="טלפן חדש"
      subtitle="החשבון נוצר עם תפקיד טלפן בלבד — בלי גישה לניהול"
      footer={
        created ? (
          <button type="button" className="adm-btn adm-btn-primary" onClick={onClose}>סגירה</button>
        ) : (
          <>
            <button type="button" className="adm-btn" onClick={onClose} disabled={busy}>ביטול</button>
            <button type="button" className="adm-btn adm-btn-primary" onClick={submit} disabled={busy || !valid}>
              {busy ? 'יוצר…' : 'יצירת טלפן'}
            </button>
          </>
        )
      }
    >
      {created ? (
        <div className="adm-created">
          <p>הטלפן נוצר. מסרו לו את פרטי הכניסה — הסיסמה מוצגת פעם אחת בלבד:</p>
          <dl className="adm-facts">
            <div><dt>אימייל</dt><dd className="adm-mono">{created.email}</dd></div>
            <div><dt>סיסמה זמנית</dt><dd className="adm-mono">{created.password}</dd></div>
          </dl>
        </div>
      ) : (
        <>
          {[
            ['display_name', 'שם', 'text'],
            ['email', 'אימייל (לכניסה)', 'email'],
            ['phone', 'טלפון', 'tel'],
            ['group_name', 'קבוצה / אזור (לא חובה)', 'text'],
            ['daily_capacity', 'מקסימום משימות ביום (לא חובה)', 'number'],
          ].map(([key, label, type]) => (
            <label key={key} className="adm-formfield">
              <span className="adm-label">{label}</span>
              <input
                className="adm-input"
                type={type}
                dir={type === 'email' || type === 'tel' ? 'ltr' : undefined}
                min={type === 'number' ? 1 : undefined}
                value={form[key as keyof typeof form]}
                onChange={(e) => setForm({ ...form, [key]: e.target.value })}
              />
            </label>
          ))}
          {error && <p className="adm-inline-error" role="alert">{error}</p>}
        </>
      )}
    </Drawer>
  )
}

function CallerDrawer({
  caller,
  canManage,
  canDisable,
  onClose,
  onSaved,
}: {
  caller: CallerRow
  canManage: boolean
  canDisable: boolean
  onClose: () => void
  onSaved: (c: CallerRow) => void
}) {
  const toast = useToast()
  const [form, setForm] = useState({
    display_name: caller.display_name,
    phone: caller.phone,
    availability: caller.availability,
    unavailable_from: caller.unavailable_from,
    unavailable_until: caller.unavailable_until,
    group_name: caller.group_name,
    daily_capacity: caller.daily_capacity == null ? '' : String(caller.daily_capacity),
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmBlock, setConfirmBlock] = useState(false)
  const dirty =
    form.display_name !== caller.display_name ||
    form.phone !== caller.phone ||
    form.availability !== caller.availability ||
    form.unavailable_from !== caller.unavailable_from ||
    form.unavailable_until !== caller.unavailable_until ||
    form.group_name !== caller.group_name ||
    form.daily_capacity !== (caller.daily_capacity == null ? '' : String(caller.daily_capacity))

  async function save() {
    setBusy(true)
    setError(null)
    try {
      const updated = await callOps.updateCaller(caller.id, {
        display_name: form.display_name,
        phone: form.phone,
        availability: form.availability,
        unavailable_from: form.availability === 'vacation' ? form.unavailable_from : '',
        unavailable_until: form.availability === 'vacation' ? form.unavailable_until : '',
        group_name: form.group_name,
        daily_capacity: form.daily_capacity ? Number(form.daily_capacity) : 0,
      })
      toast('השינויים נשמרו')
      onSaved(updated)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'השמירה נכשלה')
    } finally {
      setBusy(false)
    }
  }

  async function toggleBlock() {
    setBusy(true)
    setError(null)
    try {
      if (caller.disabled) await adminEnableUser(caller.id)
      else await adminDisableUser(caller.id)
      toast(caller.disabled ? 'הטלפן הופעל' : 'הטלפן נחסם')
      setConfirmBlock(false)
      onSaved({ ...caller, disabled: !caller.disabled })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'הפעולה נכשלה')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Drawer
      open
      onClose={onClose}
      title={caller.display_name || caller.email}
      subtitle={caller.email}
      footer={
        canManage ? (
          <>
            <button type="button" className="adm-btn" onClick={onClose} disabled={busy}>סגירה</button>
            <button type="button" className="adm-btn adm-btn-primary" onClick={save} disabled={busy || !dirty}>
              {busy ? 'שומר…' : 'שמירת שינויים'}
            </button>
          </>
        ) : undefined
      }
    >
      <section aria-label="עומס" className="adm-stats adm-stats-4 adm-stats-compact">
        <div className="adm-stat"><span className="adm-stat-value">{caller.today.tasks}</span><span className="adm-stat-label">היום</span></div>
        <div className="adm-stat"><span className="adm-stat-value">{caller.today.handled}</span><span className="adm-stat-label">טופלו</span></div>
        <div className="adm-stat"><span className="adm-stat-value">{caller.today.pending}</span><span className="adm-stat-label">ממתינות</span></div>
        <div className="adm-stat"><span className="adm-stat-value">{caller.tomorrow_tasks}</span><span className="adm-stat-label">מחר</span></div>
      </section>
      <div className="adm-row-actions adm-mt">
        <button type="button" className="adm-btn" onClick={() => navigate('calls', null, { assignee: caller.id })}>
          המשימות של {caller.display_name || 'הטלפן'}
        </button>
        <span className="adm-muted">{caller.calls_total} שיחות בסך הכול</span>
      </div>

      <fieldset className="adm-fieldset" disabled={!canManage || busy}>
        <legend className="adm-section-title">זמינות</legend>
        <div className="adm-chips" role="radiogroup" aria-label="זמינות">
          {(
            [
              ['active', 'פעיל'],
              ['vacation', 'חופשה / לא זמין'],
              ['inactive', 'לא פעיל'],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="radio"
              aria-checked={form.availability === value}
              className={`adm-chip${form.availability === value ? ' is-on' : ''}`}
              onClick={() => setForm({ ...form, availability: value })}
            >
              {label}
            </button>
          ))}
        </div>
        {form.availability === 'vacation' && (
          <div className="adm-row-actions adm-mt">
            <label className="adm-inline-field">
              <span>מ-</span>
              <input type="date" className="adm-input" value={form.unavailable_from} onChange={(e) => setForm({ ...form, unavailable_from: e.target.value })} />
            </label>
            <label className="adm-inline-field">
              <span>עד</span>
              <input type="date" className="adm-input" value={form.unavailable_until} onChange={(e) => setForm({ ...form, unavailable_until: e.target.value })} />
            </label>
          </div>
        )}
        <label className="adm-formfield">
          <span className="adm-label">מקסימום משימות ביום</span>
          <input type="number" min={0} className="adm-input adm-input-num" value={form.daily_capacity} placeholder="ללא הגבלה" onChange={(e) => setForm({ ...form, daily_capacity: e.target.value })} />
          <span className="adm-help">חלוקה אוטומטית לא תעבור את המספר הזה</span>
        </label>
      </fieldset>

      <fieldset className="adm-fieldset" disabled={!canManage || busy}>
        <legend className="adm-section-title">פרטים</legend>
        <label className="adm-formfield">
          <span className="adm-label">שם</span>
          <input className="adm-input" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
        </label>
        <label className="adm-formfield">
          <span className="adm-label">טלפון</span>
          <input className="adm-input" dir="ltr" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
        </label>
        <label className="adm-formfield">
          <span className="adm-label">קבוצה / אזור</span>
          <input className="adm-input" value={form.group_name} onChange={(e) => setForm({ ...form, group_name: e.target.value })} />
        </label>
      </fieldset>

      {error && <p className="adm-inline-error" role="alert">{error}</p>}

      {canDisable && (
        <div className="adm-danger-zone">
          <div>
            <strong>{caller.disabled ? 'החשבון חסום' : 'חסימת החשבון'}</strong>
            <p className="adm-muted">
              {caller.disabled ? 'הטלפן לא יכול להתחבר.' : 'הטלפן יתנתק מיד ולא יוכל להתחבר. ההיסטוריה נשמרת.'}
            </p>
          </div>
          <button
            type="button"
            className={`adm-btn ${caller.disabled ? '' : 'adm-danger-text'}`}
            onClick={() => (caller.disabled ? toggleBlock() : setConfirmBlock(true))}
            disabled={busy}
          >
            {caller.disabled ? 'הפעלה מחדש' : 'חסימה'}
          </button>
        </div>
      )}
      <ConfirmAction
        open={confirmBlock}
        title="חסימת טלפן"
        body={<p>{caller.display_name} יתנתק מכל המכשירים. משימות פתוחות שלו יופיעו ב"דורש בדיקה" להעברה.</p>}
        confirmLabel="חסימה"
        danger
        busy={busy}
        error={error}
        onConfirm={toggleBlock}
        onCancel={() => setConfirmBlock(false)}
      />
    </Drawer>
  )
}
