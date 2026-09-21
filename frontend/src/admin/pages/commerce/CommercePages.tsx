/**
 * מסחר: מסלולים, תוספים, עמלות, קופונים, רכישות לאירועים.
 *
 * מודל עסקי נעול — תשלום חד-פעמי לאירוע. אין סליקה מחוברת, ולכן כל מסך
 * אומר במפורש מה נשמר ומשפיע (למשל מסלול פותח פיצ'רים לאירוע) ומה עדיין
 * לא מחובר (חיוב, מימוש קופון בקופה).
 */
import { useState } from 'react'
import { AdminPayoutReview } from '../../../components/AdminPayoutReview'
import { adminHttp, qs } from '../../adminApi'
import { routeHref } from '../../route'
import {
  Advanced,
  ConfirmAction,
  Drawer,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  Section,
  StatusPill,
  Tabs,
  fmtDate,
  fmtDateTime,
  useAsync,
  useCan,
  useToast,
} from '../../ui'

const { getJson, sendJson } = adminHttp

const ils = (agorot: number | null | undefined) =>
  agorot == null ? '—' : `₪${(agorot / 100).toLocaleString('he-IL', { maximumFractionDigits: 2 })}`
const toAgorot = (shekels: string) => Math.round(Number(shekels || 0) * 100)
const STATUS_TONE: Record<string, 'ok' | 'neutral' | 'warn' | 'bad' | 'info'> = {
  active: 'ok', hidden: 'neutral', draft: 'warn', archived: 'neutral', trial: 'info', paused: 'warn', cancelled: 'neutral', expired: 'neutral',
}

function NotConnected({ children }: { children: React.ReactNode }) {
  return <p className="adm-notice">{children}</p>
}

function useRunner() {
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function run<T>(action: () => Promise<T>, msg: string): Promise<T | null> {
    setBusy(true)
    setError(null)
    try {
      const r = await action()
      toast(msg)
      return r
    } catch (e) {
      setError(e instanceof Error ? e.message : 'הפעולה נכשלה')
      return null
    } finally {
      setBusy(false)
    }
  }
  return { busy, error, setError, run }
}

// ── מסלולים ──────────────────────────────────────────────────────────────
interface Version {
  id: number
  version: number
  price_agorot: number
  guest_limit: number | null
  event_limit: number
  trial_days: number
  features: string[]
  included_addons: string[]
  available_addons: string[]
  change_note: string
  created_at: string | null
  events_count?: number
}
interface Plan {
  id: number
  key: string
  name: string
  description: string
  status: string
  status_label: string
  current: Version | null
  events_count: number
  versions?: Version[]
}
interface PlansResp {
  plans: Plan[]
  features: { key: string; label: string }[]
  addons: { key: string; name: string }[]
  can_edit: boolean
}

export function PlansPage() {
  const data = useAsync(() => getJson<PlansResp>('/admin/commerce/plans'), [])
  const [open, setOpen] = useState<number | 'new' | null>(null)
  if (data.loading && !data.data) return <Loading />
  if (data.error && !data.data) return <ErrorState message={data.error} onRetry={data.reload} />
  const d = data.data!
  const fname = (k: string) => d.features.find((f) => f.key === k)?.label ?? k
  return (
    <div className="adm-page">
      <PageHeader
        title="מסלולים ומחירים"
        subtitle="מסלול נקנה פעם אחת לאירוע. שינוי מחיר יוצר גרסה חדשה — אירועים קיימים נשארים בתנאים שלהם."
        actions={d.can_edit && <button type="button" className="adm-btn adm-btn-primary" onClick={() => setOpen('new')}>+ מסלול חדש</button>}
      />
      <NotConnected>אין עדיין סליקה במוצר: מסלול משפיע על מה שפתוח לאירוע (פיצ'רים ותוספים). מגבלת מוזמנים נשמרת אבל עוד לא נאכפת.</NotConnected>
      {d.plans.length === 0 ? (
        <EmptyState title="אין עדיין מסלולים" action={d.can_edit ? <button type="button" className="adm-btn adm-btn-primary" onClick={() => setOpen('new')}>+ מסלול חדש</button> : undefined} />
      ) : (
        <div className="adm-table-wrap">
          <table className="adm-table">
            <thead>
              <tr><th>מסלול</th><th>מחיר</th><th className="adm-hide-md">כולל</th><th className="adm-num">אירועים</th><th>סטטוס</th></tr>
            </thead>
            <tbody>
              {d.plans.map((p) => (
                <tr key={p.id} className="is-clickable" tabIndex={0} onClick={() => setOpen(p.id)} onKeyDown={(e) => e.key === 'Enter' && setOpen(p.id)}>
                  <td><div className="adm-cell-title">{p.name}</div><div className="adm-cell-sub">{p.key} · גרסה {p.current?.version ?? '—'}</div></td>
                  <td>{ils(p.current?.price_agorot)}</td>
                  <td className="adm-hide-md adm-muted">{(p.current?.features ?? []).map(fname).join(', ') || '—'}</td>
                  <td className="adm-num">{p.events_count}</td>
                  <td><StatusPill tone={STATUS_TONE[p.status]}>{p.status_label}</StatusPill></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {open !== null && <PlanDrawer planId={open === 'new' ? null : open} meta={d} onClose={() => setOpen(null)} onSaved={data.reload} />}
    </div>
  )
}

function PlanDrawer({ planId, meta, onClose, onSaved }: { planId: number | null; meta: PlansResp; onClose: () => void; onSaved: () => void }) {
  const plan = useAsync(() => (planId ? getJson<Plan>(`/admin/commerce/plans/${planId}`) : Promise.resolve(null)), [planId])
  const { busy, error, run } = useRunner()
  const p = plan.data
  const cur = p?.current
  const [form, setForm] = useState<null | {
    key: string; name: string; description: string; price: string; guest_limit: string; trial_days: string
    features: string[]; included_addons: string[]; available_addons: string[]; change_note: string
  }>(null)
  const [confirm, setConfirm] = useState(false)
  const f = form ?? {
    key: p?.key ?? '', name: p?.name ?? '', description: p?.description ?? '',
    price: cur ? String(cur.price_agorot / 100) : '', guest_limit: cur?.guest_limit ? String(cur.guest_limit) : '',
    trial_days: cur ? String(cur.trial_days) : '0', features: cur?.features ?? [], included_addons: cur?.included_addons ?? [],
    available_addons: cur?.available_addons ?? [], change_note: '',
  }
  const set = (patch: Partial<typeof f>) => setForm({ ...f, ...patch })
  const versionChanged = !!cur && (
    toAgorot(f.price) !== cur.price_agorot || (f.guest_limit ? Number(f.guest_limit) : null) !== cur.guest_limit ||
    Number(f.trial_days) !== cur.trial_days || JSON.stringify([...f.features].sort()) !== JSON.stringify([...cur.features].sort()) ||
    JSON.stringify([...f.included_addons].sort()) !== JSON.stringify([...cur.included_addons].sort()) ||
    JSON.stringify([...f.available_addons].sort()) !== JSON.stringify([...cur.available_addons].sort())
  )
  const metaChanged = !!p && (f.name !== p.name || f.description !== p.description)
  const versionBody = {
    price_agorot: toAgorot(f.price), guest_limit: f.guest_limit ? Number(f.guest_limit) : null, trial_days: Number(f.trial_days || 0),
    features: f.features, included_addons: f.included_addons, available_addons: f.available_addons, change_note: f.change_note,
  }
  const toggle = (list: string[], k: string) => (list.includes(k) ? list.filter((x) => x !== k) : [...list, k])

  async function save() {
    if (!planId) {
      const r = await run(() => sendJson('/admin/commerce/plans', 'POST', { key: f.key, name: f.name, description: f.description, ...versionBody }), 'המסלול נוצר כטיוטה')
      if (r) { onSaved(); onClose() }
      return
    }
    if (metaChanged) await run(() => sendJson(`/admin/commerce/plans/${planId}`, 'PATCH', { name: f.name, description: f.description }), 'הפרטים נשמרו')
    if (versionChanged) await run(() => sendJson(`/admin/commerce/plans/${planId}/versions`, 'POST', versionBody), 'נוצרה גרסה חדשה')
    setConfirm(false)
    setForm(null)
    plan.reload()
    onSaved()
  }

  if (planId && plan.loading && !p) return <Drawer open onClose={onClose} title="מסלול"><Loading /></Drawer>
  const canEdit = meta.can_edit
  return (
    <Drawer
      open
      wide
      onClose={onClose}
      title={p ? p.name : 'מסלול חדש'}
      subtitle={p ? `גרסה נוכחית ${cur?.version} · ${p.events_count} אירועים` : 'נוצר כטיוטה — לא מוצג לאף אחד עד שמפעילים'}
      footer={canEdit && (
        <>
          <button type="button" className="adm-btn" onClick={onClose} disabled={busy}>סגירה</button>
          <button type="button" className="adm-btn adm-btn-primary" disabled={busy || (planId !== null && !versionChanged && !metaChanged) || !f.name}
            onClick={() => (versionChanged ? setConfirm(true) : save())}>
            {planId ? (versionChanged ? 'שמירה כגרסה חדשה' : 'שמירה') : 'יצירה'}
          </button>
        </>
      )}
    >
      {error && <p className="adm-inline-error" role="alert">{error}</p>}
      <fieldset className="adm-fieldset" disabled={!canEdit || busy}>
        {!planId && (
          <label className="adm-formfield"><span className="adm-label">מפתח טכני</span>
            <input className="adm-input adm-mono" dir="ltr" placeholder="plus" value={f.key} onChange={(e) => set({ key: e.target.value.toLowerCase() })} /></label>
        )}
        <label className="adm-formfield"><span className="adm-label">שם</span><input className="adm-input" value={f.name} onChange={(e) => set({ name: e.target.value })} /></label>
        <label className="adm-formfield"><span className="adm-label">תיאור</span><textarea className="adm-input" rows={2} value={f.description} onChange={(e) => set({ description: e.target.value })} /></label>
        <div className="adm-form-2">
          <label className="adm-formfield"><span className="adm-label">מחיר (₪)</span><input className="adm-input" type="number" min={0} step="1" value={f.price} onChange={(e) => set({ price: e.target.value })} /></label>
          <label className="adm-formfield"><span className="adm-label">מגבלת מוזמנים</span><input className="adm-input" type="number" min={1} placeholder="ללא הגבלה" value={f.guest_limit} onChange={(e) => set({ guest_limit: e.target.value })} /></label>
        </div>
        <label className="adm-formfield"><span className="adm-label">ימי ניסיון</span><input className="adm-input adm-input-num" type="number" min={0} value={f.trial_days} onChange={(e) => set({ trial_days: e.target.value })} /></label>
        <h3 className="adm-section-title adm-mt">פיצ'רים שהמסלול פותח</h3>
        <div className="adm-chips">{meta.features.map((x) => <button key={x.key} type="button" aria-pressed={f.features.includes(x.key)} className={`adm-chip${f.features.includes(x.key) ? ' is-on' : ''}`} onClick={() => set({ features: toggle(f.features, x.key) })}>{x.label}</button>)}</div>
        {meta.addons.length > 0 && (
          <>
            <h3 className="adm-section-title adm-mt">תוספים</h3>
            <table className="adm-table adm-table-plain">
              <thead><tr><th>תוסף</th><th>כלול</th><th>ניתן להוספה</th></tr></thead>
              <tbody>{meta.addons.map((a) => (
                <tr key={a.key}><td>{a.name}</td>
                  <td><input type="checkbox" checked={f.included_addons.includes(a.key)} onChange={() => set({ included_addons: toggle(f.included_addons, a.key) })} aria-label={`${a.name} כלול`} /></td>
                  <td><input type="checkbox" checked={f.available_addons.includes(a.key)} onChange={() => set({ available_addons: toggle(f.available_addons, a.key) })} aria-label={`${a.name} להוספה`} /></td></tr>
              ))}</tbody>
            </table>
          </>
        )}
      </fieldset>
      {p && canEdit && (
        <div className="adm-row-actions adm-mt">
          <span className="adm-muted">סטטוס:</span>
          {(['draft', 'active', 'hidden', 'archived'] as const).map((st) => (
            <button key={st} type="button" className={`adm-chip${p.status === st ? ' is-on' : ''}`} disabled={busy}
              onClick={() => run(() => sendJson(`/admin/commerce/plans/${p.id}`, 'PATCH', { status: st }), 'הסטטוס עודכן').then(() => { plan.reload(); onSaved() })}>
              {{ draft: 'טיוטה', active: 'פעיל', hidden: 'מוסתר', archived: 'ארכיון' }[st]}
            </button>
          ))}
        </div>
      )}
      {p?.versions && p.versions.length > 0 && (
        <Advanced title={`היסטוריית גרסאות (${p.versions.length})`}>
          <table className="adm-table adm-table-plain">
            <thead><tr><th>גרסה</th><th>מחיר</th><th className="adm-num">אירועים</th><th>נוצרה</th></tr></thead>
            <tbody>{p.versions.map((v) => (
              <tr key={v.id}><td>v{v.version}{v.id === cur?.id ? ' (נוכחית)' : ''}{v.change_note ? <div className="adm-cell-sub">{v.change_note}</div> : null}</td>
                <td>{ils(v.price_agorot)}</td><td className="adm-num">{v.events_count ?? 0}</td><td className="adm-muted">{fmtDateTime(v.created_at)}</td></tr>
            ))}</tbody>
          </table>
        </Advanced>
      )}
      <ConfirmAction
        open={confirm}
        title="שמירה כגרסה חדשה"
        body={<p>תיווצר גרסה {(cur?.version ?? 0) + 1} ({ils(toAgorot(f.price))}). {p?.events_count ? `${p.events_count} אירועים שכבר קיבלו את המסלול נשארים בתנאים הקודמים.` : ''}</p>}
        confirmLabel="יצירת גרסה"
        requireReason
        busy={busy}
        error={error}
        onConfirm={(reason) => { f.change_note = reason; void save() }}
        onCancel={() => setConfirm(false)}
      />
    </Drawer>
  )
}

// ── תוספים ───────────────────────────────────────────────────────────────
interface Addon { id: number; key: string; name: string; description: string; price_agorot: number; status: string; status_label: string; standalone: boolean; feature_key: string; plans: { plan: string; mode: string }[] }

export function AddonsPage() {
  const data = useAsync(() => getJson<{ addons: Addon[]; features: { key: string; label: string }[]; can_edit: boolean }>('/admin/commerce/addons'), [])
  const [open, setOpen] = useState<Addon | 'new' | null>(null)
  const { busy, error, run } = useRunner()
  const [form, setForm] = useState({ key: '', name: '', description: '', price: '', status: 'draft', standalone: true, feature_key: '' })
  if (data.loading && !data.data) return <Loading />
  if (data.error && !data.data) return <ErrorState message={data.error} onRetry={data.reload} />
  const d = data.data!
  function edit(a: Addon | 'new') {
    setOpen(a)
    setForm(a === 'new'
      ? { key: '', name: '', description: '', price: '', status: 'draft', standalone: true, feature_key: '' }
      : { key: a.key, name: a.name, description: a.description, price: String(a.price_agorot / 100), status: a.status, standalone: a.standalone, feature_key: a.feature_key })
  }
  async function save() {
    const body = { name: form.name, description: form.description, price_agorot: toAgorot(form.price), status: form.status, standalone: form.standalone, feature_key: form.feature_key }
    const r = open === 'new'
      ? await run(() => sendJson('/admin/commerce/addons', 'POST', { ...body, key: form.key }), 'התוסף נוצר')
      : await run(() => sendJson(`/admin/commerce/addons/${(open as Addon).id}`, 'PATCH', body), 'התוסף עודכן')
    if (r) { setOpen(null); data.reload() }
  }
  return (
    <div className="adm-page">
      <PageHeader title="תוספים" subtitle="יכולות שאפשר לכלול במסלול או למכור בנפרד. תוסף שמחובר לפיצ'ר פותח אותו לאירוע שקיבל אותו."
        actions={d.can_edit && <button type="button" className="adm-btn adm-btn-primary" onClick={() => edit('new')}>+ תוסף חדש</button>} />
      {d.addons.length === 0 ? <EmptyState title="אין עדיין תוספים" /> : (
        <div className="adm-table-wrap"><table className="adm-table">
          <thead><tr><th>תוסף</th><th>מחיר</th><th className="adm-hide-md">במסלולים</th><th>סטטוס</th></tr></thead>
          <tbody>{d.addons.map((a) => (
            <tr key={a.id} className="is-clickable" tabIndex={0} onClick={() => edit(a)} onKeyDown={(e) => e.key === 'Enter' && edit(a)}>
              <td><div className="adm-cell-title">{a.name}</div><div className="adm-cell-sub">{a.feature_key ? `פותח: ${d.features.find((f) => f.key === a.feature_key)?.label ?? a.feature_key}` : 'לא מחובר לפיצ\'ר'}{a.standalone ? ' · לרכישה בנפרד' : ''}</div></td>
              <td>{ils(a.price_agorot)}</td>
              <td className="adm-hide-md adm-muted">{a.plans.map((p) => `${p.plan} (${p.mode === 'included' ? 'כלול' : 'בתוספת'})`).join(', ') || '—'}</td>
              <td><StatusPill tone={STATUS_TONE[a.status]}>{a.status_label}</StatusPill></td>
            </tr>
          ))}</tbody></table></div>
      )}
      <Drawer open={open !== null} onClose={() => setOpen(null)} title={open === 'new' ? 'תוסף חדש' : (open as Addon | null)?.name ?? ''}
        footer={d.can_edit && <><button type="button" className="adm-btn" onClick={() => setOpen(null)}>ביטול</button><button type="button" className="adm-btn adm-btn-primary" disabled={busy || !form.name || (open === 'new' && !form.key)} onClick={save}>שמירה</button></>}>
        {error && <p className="adm-inline-error" role="alert">{error}</p>}
        <fieldset className="adm-fieldset" disabled={!d.can_edit || busy}>
          {open === 'new' && <label className="adm-formfield"><span className="adm-label">מפתח טכני</span><input className="adm-input adm-mono" dir="ltr" value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value.toLowerCase() })} /></label>}
          <label className="adm-formfield"><span className="adm-label">שם</span><input className="adm-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label className="adm-formfield"><span className="adm-label">תיאור</span><textarea className="adm-input" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
          <div className="adm-form-2">
            <label className="adm-formfield"><span className="adm-label">מחיר (₪)</span><input className="adm-input" type="number" min={0} value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} /></label>
            <label className="adm-formfield"><span className="adm-label">סטטוס</span><select className="adm-input" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}><option value="draft">טיוטה</option><option value="active">פעיל</option><option value="hidden">מוסתר</option></select></label>
          </div>
          <label className="adm-formfield"><span className="adm-label">הפיצ'ר שהתוסף פותח</span>
            <select className="adm-input" value={form.feature_key} onChange={(e) => setForm({ ...form, feature_key: e.target.value })}><option value="">— לא מחובר —</option>{d.features.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}</select></label>
          <label className="adm-check"><input type="checkbox" checked={form.standalone} onChange={(e) => setForm({ ...form, standalone: e.target.checked })} /><span>ניתן לרכישה בנפרד</span></label>
        </fieldset>
      </Drawer>
    </div>
  )
}

// ── עמלות ────────────────────────────────────────────────────────────────
interface FeesResp {
  current: { percent_bp: number; percent: number; fixed_agorot: number; min_agorot: number | null; max_agorot: number | null; source: string }
  examples: { gift: number; fee: number; total: number }[]
  history: { id: number; percent: number; fixed_agorot: number; min_agorot: number | null; max_agorot: number | null; active: boolean; note: string; created_at: string | null }[]
  can_edit: boolean
}

export function FeesPage() {
  const can = useCan()
  const [tab, setTab] = useState<'fee' | 'payouts'>('fee')
  return (
    <div className="adm-page">
      <PageHeader title="עמלות" subtitle="עמלת המתנות באשראי ואישור פרטי חשבון לקבלת כספים" />
      <Tabs label="עמלות" tabs={[{ key: 'fee', label: 'עמלת אשראי' }, ...(can('payouts.review') ? [{ key: 'payouts' as const, label: 'פרטי חשבון לאישור' }] : [])]} active={tab} onChange={(k) => setTab(k as 'fee' | 'payouts')} />
      {tab === 'fee' ? <GiftFee /> : <div className="adm-legacy"><AdminPayoutReview /></div>}
    </div>
  )
}

function GiftFee() {
  const data = useAsync(() => getJson<FeesResp>('/admin/commerce/fees'), [])
  const { busy, error, run } = useRunner()
  const [form, setForm] = useState<{ percent: string; fixed: string; min: string; max: string } | null>(null)
  const [confirm, setConfirm] = useState(false)
  if (data.loading && !data.data) return <Loading />
  if (data.error && !data.data) return <ErrorState message={data.error} onRetry={data.reload} />
  const d = data.data!
  const c = d.current
  const f = form ?? { percent: String(c.percent), fixed: String(c.fixed_agorot / 100), min: c.min_agorot == null ? '' : String(c.min_agorot / 100), max: c.max_agorot == null ? '' : String(c.max_agorot / 100) }
  const body = { percent_bp: Math.round(Number(f.percent || 0) * 100), fixed_agorot: toAgorot(f.fixed), min_agorot: f.min === '' ? null : toAgorot(f.min), max_agorot: f.max === '' ? null : toAgorot(f.max) }
  const dirty = body.percent_bp !== c.percent_bp || body.fixed_agorot !== c.fixed_agorot || body.min_agorot !== c.min_agorot || body.max_agorot !== c.max_agorot
  const preview = (amount: number) => {
    let fee = Math.floor((amount * body.percent_bp + 5000) / 10000) + body.fixed_agorot
    if (body.min_agorot != null) fee = Math.max(fee, body.min_agorot)
    if (body.max_agorot != null) fee = Math.min(fee, body.max_agorot)
    return fee
  }
  return (
    <>
      <Section title="עמלת מתנות באשראי" description="העמלה מתווספת לסכום שהאורח משלם — בעלי האירוע מקבלים את מלוא המתנה (החלטה נעולה).">
        <fieldset className="adm-fieldset adm-control" disabled={!d.can_edit || busy}>
          <div className="adm-form-2">
            <label className="adm-formfield"><span className="adm-label">אחוז</span><input className="adm-input" type="number" step="0.05" min={0} max={20} value={f.percent} onChange={(e) => setForm({ ...f, percent: e.target.value })} /></label>
            <label className="adm-formfield"><span className="adm-label">סכום קבוע (₪)</span><input className="adm-input" type="number" step="0.5" min={0} value={f.fixed} onChange={(e) => setForm({ ...f, fixed: e.target.value })} /></label>
            <label className="adm-formfield"><span className="adm-label">מינימום (₪)</span><input className="adm-input" type="number" min={0} placeholder="ללא" value={f.min} onChange={(e) => setForm({ ...f, min: e.target.value })} /></label>
            <label className="adm-formfield"><span className="adm-label">מקסימום (₪)</span><input className="adm-input" type="number" min={0} placeholder="ללא" value={f.max} onChange={(e) => setForm({ ...f, max: e.target.value })} /></label>
          </div>
          <table className="adm-table adm-table-plain adm-mt">
            <thead><tr><th>מתנה</th><th>עמלה {dirty ? '(חדש)' : ''}</th><th>האורח משלם</th></tr></thead>
            <tbody>{d.examples.map((x) => (
              <tr key={x.gift}><td>{ils(x.gift)}</td><td>{ils(preview(x.gift))}{dirty && <span className="adm-muted"> (היום {ils(x.fee)})</span>}</td><td>{ils(x.gift + preview(x.gift))}</td></tr>
            ))}</tbody>
          </table>
          <p className="adm-help">{c.source === 'code' ? 'ברירת המחדל בקוד: 4%.' : 'נקבע במסך הזה.'} עמלה לפי מסלול או סוג אירוע — עוד לא מחוברת.</p>
          {dirty && d.can_edit && <div className="adm-row-actions"><button type="button" className="adm-btn" onClick={() => setForm(null)}>ביטול</button><button type="button" className="adm-btn adm-btn-primary" onClick={() => setConfirm(true)}>שמירה</button></div>}
        </fieldset>
      </Section>
      {d.history.length > 0 && (
        <Advanced title="היסטוריית עמלות">
          <table className="adm-table adm-table-plain"><tbody>{d.history.map((h) => (
            <tr key={h.id}><td>{h.percent}%{h.fixed_agorot ? ` + ${ils(h.fixed_agorot)}` : ''}{h.min_agorot != null ? ` · מינ' ${ils(h.min_agorot)}` : ''}{h.max_agorot != null ? ` · מקס' ${ils(h.max_agorot)}` : ''}</td>
              <td>{h.active ? <StatusPill tone="ok">פעילה</StatusPill> : <span className="adm-muted">קודמת</span>}</td><td className="adm-muted">{h.note}</td><td className="adm-muted">{fmtDateTime(h.created_at)}</td></tr>
          ))}</tbody></table>
        </Advanced>
      )}
      <ConfirmAction open={confirm} title="שינוי עמלת האשראי" danger
        body={<p>{c.percent}% ← <strong>{Number(f.percent)}%</strong>. חל על כל מתנה חדשה מרגע השמירה. מתנות קודמות לא משתנות.</p>}
        confirmLabel="שמירת עמלה" typeToConfirm={`${Number(f.percent)}%`} requireReason busy={busy} error={error}
        onConfirm={async (reason) => { const r = await run(() => sendJson<FeesResp>('/admin/commerce/fees/gift', 'PUT', { ...body, reason }), 'העמלה עודכנה'); if (r) { data.setData(r); setForm(null); setConfirm(false) } }}
        onCancel={() => setConfirm(false)} />
    </>
  )
}

// ── קופונים ──────────────────────────────────────────────────────────────
interface Coupon { id: number; code: string; description: string; kind: 'percent' | 'amount'; value: number; starts_on: string; ends_on: string; max_uses: number | null; uses_count: number; plan_keys: string[]; addon_keys: string[]; audience: string; active: boolean; state: string }

export function CouponsPage() {
  const data = useAsync(() => getJson<{ coupons: Coupon[]; plans: { key: string; name: string }[]; addons: { key: string; name: string }[]; can_edit: boolean }>('/admin/commerce/coupons'), [])
  const [open, setOpen] = useState<Coupon | 'new' | null>(null)
  const { busy, error, run } = useRunner()
  const empty = { code: '', description: '', kind: 'percent' as 'percent' | 'amount', value: '', starts_on: '', ends_on: '', max_uses: '', plan_keys: [] as string[], audience: '', active: true }
  const [form, setForm] = useState(empty)
  if (data.loading && !data.data) return <Loading />
  if (data.error && !data.data) return <ErrorState message={data.error} onRetry={data.reload} />
  const d = data.data!
  function edit(c: Coupon | 'new') {
    setOpen(c)
    setForm(c === 'new' ? empty : { code: c.code, description: c.description, kind: c.kind, value: String(c.kind === 'amount' ? c.value / 100 : c.value), starts_on: c.starts_on, ends_on: c.ends_on, max_uses: c.max_uses == null ? '' : String(c.max_uses), plan_keys: c.plan_keys, audience: c.audience, active: c.active })
  }
  async function save() {
    const body = { description: form.description, kind: form.kind, value: form.kind === 'amount' ? toAgorot(form.value) : Number(form.value), starts_on: form.starts_on, ends_on: form.ends_on, max_uses: form.max_uses ? Number(form.max_uses) : null, plan_keys: form.plan_keys, audience: form.audience, active: form.active }
    const r = open === 'new' ? await run(() => sendJson('/admin/commerce/coupons', 'POST', { ...body, code: form.code }), 'הקופון נוצר') : await run(() => sendJson(`/admin/commerce/coupons/${(open as Coupon).id}`, 'PATCH', body), 'הקופון עודכן')
    if (r) { setOpen(null); data.reload() }
  }
  return (
    <div className="adm-page">
      <PageHeader title="קופונים והטבות" actions={d.can_edit && <button type="button" className="adm-btn adm-btn-primary" onClick={() => edit('new')}>+ קופון</button>} />
      <NotConnected>הקופונים נשמרים ומנוהלים כאן. מימוש קופון בקופה יתחבר יחד עם הסליקה — עד אז אפשר להחיל הטבה ידנית במסך המנויים (מחיר לאירוע).</NotConnected>
      {d.coupons.length === 0 ? <EmptyState title="אין עדיין קופונים" /> : (
        <div className="adm-table-wrap"><table className="adm-table">
          <thead><tr><th>קוד</th><th>הנחה</th><th className="adm-hide-md">תוקף</th><th className="adm-num">שימושים</th><th>מצב</th></tr></thead>
          <tbody>{d.coupons.map((c) => (
            <tr key={c.id} className="is-clickable" tabIndex={0} onClick={() => edit(c)} onKeyDown={(e) => e.key === 'Enter' && edit(c)}>
              <td><div className="adm-cell-title adm-mono">{c.code}</div><div className="adm-cell-sub">{c.description}</div></td>
              <td>{c.kind === 'percent' ? `${c.value}%` : ils(c.value)}</td>
              <td className="adm-hide-md adm-muted">{c.starts_on || c.ends_on ? `${fmtDate(c.starts_on) || '—'} – ${fmtDate(c.ends_on) || '—'}` : 'ללא הגבלה'}</td>
              <td className="adm-num">{c.uses_count}{c.max_uses ? ` / ${c.max_uses}` : ''}</td>
              <td><StatusPill tone={c.state === 'פעיל' ? 'ok' : 'neutral'}>{c.state}</StatusPill></td>
            </tr>
          ))}</tbody></table></div>
      )}
      <Drawer open={open !== null} onClose={() => setOpen(null)} title={open === 'new' ? 'קופון חדש' : (open as Coupon | null)?.code ?? ''}
        footer={d.can_edit && <><button type="button" className="adm-btn" onClick={() => setOpen(null)}>ביטול</button><button type="button" className="adm-btn adm-btn-primary" disabled={busy || !form.value || (open === 'new' && !form.code)} onClick={save}>שמירה</button></>}>
        {error && <p className="adm-inline-error" role="alert">{error}</p>}
        <fieldset className="adm-fieldset" disabled={!d.can_edit || busy}>
          {open === 'new' && <label className="adm-formfield"><span className="adm-label">קוד</span><input className="adm-input adm-mono" dir="ltr" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toUpperCase() })} /></label>}
          <label className="adm-formfield"><span className="adm-label">תיאור</span><input className="adm-input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
          <div className="adm-form-2">
            <label className="adm-formfield"><span className="adm-label">סוג</span><select className="adm-input" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as 'percent' | 'amount' })}><option value="percent">אחוז</option><option value="amount">סכום (₪)</option></select></label>
            <label className="adm-formfield"><span className="adm-label">ערך</span><input className="adm-input" type="number" min={1} value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} /></label>
            <label className="adm-formfield"><span className="adm-label">מתאריך</span><input className="adm-input" type="date" value={form.starts_on} onChange={(e) => setForm({ ...form, starts_on: e.target.value })} /></label>
            <label className="adm-formfield"><span className="adm-label">עד תאריך</span><input className="adm-input" type="date" value={form.ends_on} onChange={(e) => setForm({ ...form, ends_on: e.target.value })} /></label>
            <label className="adm-formfield"><span className="adm-label">שימושים מקסימליים</span><input className="adm-input" type="number" min={1} placeholder="ללא הגבלה" value={form.max_uses} onChange={(e) => setForm({ ...form, max_uses: e.target.value })} /></label>
            <label className="adm-formfield"><span className="adm-label">למי</span><input className="adm-input" placeholder="למשל: שותפי אולמות" value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })} /></label>
          </div>
          {d.plans.length > 0 && <><h3 className="adm-section-title adm-mt">חל על מסלולים</h3><div className="adm-chips">{d.plans.map((p) => { const on = form.plan_keys.includes(p.key); return <button key={p.key} type="button" aria-pressed={on} className={`adm-chip${on ? ' is-on' : ''}`} onClick={() => setForm({ ...form, plan_keys: on ? form.plan_keys.filter((k) => k !== p.key) : [...form.plan_keys, p.key] })}>{p.name}</button> })}</div><p className="adm-help">בלי בחירה — כל המסלולים.</p></>}
          <label className="adm-check"><input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /><span>פעיל</span></label>
        </fieldset>
      </Drawer>
    </div>
  )
}

// ── רכישות לאירועים ("מנויים") ───────────────────────────────────────────
interface Ent { id: number; event_id: number; event_label: string; event_date: string; plan_name: string; version: number | null; list_price_agorot: number; current_price_agorot: number | null; on_old_version: boolean; price_agorot: number; addons: string[]; status: string; status_label: string; source: string; starts_on: string; trial_ends_on: string; renews_on: string; note: string }
interface EntResp { total: number; items: Ent[]; plans: { id: number; name: string; version_id: number; version: number; price_agorot: number; trial_days: number }[]; can_edit: boolean }

export function SubscriptionsPage() {
  const [status, setStatus] = useState('')
  const data = useAsync(() => getJson<EntResp>(`/admin/commerce/subscriptions${qs({ status })}`), [status])
  const { busy, error, run } = useRunner()
  const [creating, setCreating] = useState(false)
  const [form, setForm] = useState({ event_id: '', version_id: '', price: '', trial: false, note: '' })
  const [pending, setPending] = useState<{ ent: Ent; status: 'active' | 'paused' | 'cancelled' } | null>(null)
  if (data.loading && !data.data) return <Loading />
  if (data.error && !data.data) return <ErrorState message={data.error} onRetry={data.reload} />
  const d = data.data!
  const chosen = d.plans.find((p) => String(p.version_id) === form.version_id)
  return (
    <div className="adm-page">
      <PageHeader title="מנויים" subtitle="המסלול של כל אירוע — גרסה, מחיר ותוספים. רכישה חד-פעמית לאירוע."
        actions={d.can_edit && d.plans.length > 0 && <button type="button" className="adm-btn adm-btn-primary" onClick={() => setCreating(true)}>+ מסלול לאירוע</button>} />
      <NotConnected>אין עדיין רכישה עצמית ואין חיוב. כאן קובעים מסלול לאירוע ידנית (הטבה, פיילוט, תשלום מחוץ למערכת) — והוא פותח את הפיצ'רים שלו מיד.</NotConnected>
      <Tabs label="סטטוס" tabs={[{ key: '', label: 'הכול' }, { key: 'active', label: 'פעילים' }, { key: 'trial', label: 'ניסיון' }, { key: 'paused', label: 'מושהים' }, { key: 'cancelled', label: 'בוטלו' }]} active={status} onChange={setStatus} />
      {d.plans.length === 0 ? (
        <EmptyState title="אין עדיין מסלולים" text="קודם יוצרים מסלול במסך המסלולים." action={<a className="adm-btn" href={routeHref('plans')}>למסלולים</a>} />
      ) : d.items.length === 0 ? <EmptyState title="אין אירועים עם מסלול" /> : (
        <div className="adm-table-wrap"><table className="adm-table">
          <thead><tr><th>אירוע</th><th>מסלול</th><th>מחיר</th><th className="adm-hide-md">התחלה</th><th>סטטוס</th>{d.can_edit && <th />}</tr></thead>
          <tbody>{d.items.map((e) => (
            <tr key={e.id}>
              <td><a className="adm-link" href={routeHref('people', `e${e.event_id}`)}>{e.event_label}</a><div className="adm-cell-sub">{fmtDate(e.event_date)}</div></td>
              <td>{e.plan_name} v{e.version}{e.on_old_version && <div className="adm-cell-sub">גרסה קודמת · היום {ils(e.current_price_agorot)}</div>}</td>
              <td>{ils(e.price_agorot)}{e.price_agorot !== e.list_price_agorot && <div className="adm-cell-sub">מחירון {ils(e.list_price_agorot)}</div>}</td>
              <td className="adm-hide-md adm-muted">{fmtDate(e.starts_on)}{e.trial_ends_on ? ` · ניסיון עד ${fmtDate(e.trial_ends_on)}` : ''}</td>
              <td><StatusPill tone={STATUS_TONE[e.status]}>{e.status_label}</StatusPill></td>
              {d.can_edit && <td className="adm-col-action">{e.status !== 'cancelled' && (
                <span className="adm-inline-group">
                  {e.status === 'paused' ? <button type="button" className="adm-link-btn" onClick={() => setPending({ ent: e, status: 'active' })}>חידוש</button> : <button type="button" className="adm-link-btn" onClick={() => setPending({ ent: e, status: 'paused' })}>השהיה</button>}
                  <button type="button" className="adm-link-btn adm-danger-text" onClick={() => setPending({ ent: e, status: 'cancelled' })}>ביטול</button>
                </span>)}</td>}
            </tr>
          ))}</tbody></table></div>
      )}
      <Drawer open={creating} onClose={() => setCreating(false)} title="מסלול לאירוע"
        footer={<><button type="button" className="adm-btn" onClick={() => setCreating(false)}>ביטול</button><button type="button" className="adm-btn adm-btn-primary" disabled={busy || !form.event_id || !form.version_id}
          onClick={async () => { const r = await run(() => sendJson('/admin/commerce/subscriptions', 'POST', { event_id: Number(form.event_id), plan_version_id: Number(form.version_id), price_agorot: form.price === '' ? null : toAgorot(form.price), trial: form.trial, note: form.note }), 'המסלול נקבע לאירוע'); if (r) { setCreating(false); data.reload() } }}>שמירה</button></>}>
        {error && <p className="adm-inline-error" role="alert">{error}</p>}
        <label className="adm-formfield"><span className="adm-label">מזהה אירוע</span><input className="adm-input" inputMode="numeric" value={form.event_id} onChange={(e) => setForm({ ...form, event_id: e.target.value.replace(/\D/g, '') })} /><span className="adm-help">מופיע בכתובת של מרכז השליטה לאירוע (#123)</span></label>
        <label className="adm-formfield"><span className="adm-label">מסלול</span><select className="adm-input" value={form.version_id} onChange={(e) => setForm({ ...form, version_id: e.target.value })}><option value="">בחירה…</option>{d.plans.map((p) => <option key={p.version_id} value={p.version_id}>{p.name} v{p.version} · {ils(p.price_agorot)}</option>)}</select></label>
        <label className="adm-formfield"><span className="adm-label">מחיר לאירוע (₪)</span><input className="adm-input" type="number" min={0} placeholder={chosen ? String(chosen.price_agorot / 100) : ''} value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} /><span className="adm-help">ריק = מחיר המחירון. 0 = הטבה מלאה.</span></label>
        {chosen && chosen.trial_days > 0 && <label className="adm-check"><input type="checkbox" checked={form.trial} onChange={(e) => setForm({ ...form, trial: e.target.checked })} /><span>תקופת ניסיון ({chosen.trial_days} ימים)</span></label>}
        <label className="adm-formfield"><span className="adm-label">הערה</span><input className="adm-input" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
      </Drawer>
      <ConfirmAction open={pending !== null} title={pending?.status === 'cancelled' ? 'ביטול המסלול לאירוע' : pending?.status === 'paused' ? 'השהיית המסלול' : 'חידוש המסלול'}
        body={<p>{pending?.status === 'cancelled' ? 'הפיצ\'רים שהמסלול פתח ייסגרו לאירוע (אם הם לא פתוחים לו בדרך אחרת). ביטול לא נפתח מחדש.' : pending?.status === 'paused' ? 'הפיצ\'רים של המסלול ייסגרו לאירוע עד החידוש.' : 'הפיצ\'רים של המסלול ייפתחו שוב לאירוע.'}</p>}
        confirmLabel="אישור" danger={pending?.status === 'cancelled'} requireReason busy={busy} error={error}
        onConfirm={async (reason) => { if (!pending) return; const r = await run(() => sendJson(`/admin/commerce/subscriptions/${pending.ent.id}/status`, 'POST', { status: pending.status, reason }), 'עודכן'); if (r) { setPending(null); data.reload() } }}
        onCancel={() => setPending(null)} />
    </div>
  )
}
