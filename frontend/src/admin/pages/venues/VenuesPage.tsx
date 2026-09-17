import { useEffect, useState } from 'react'
import { mediaUrl } from '../../../api'
import { adminHttp, qs } from '../../adminApi'
import { navigate, routeHref, type AdminRoute } from '../../route'
import {
  ConfirmAction,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  StatusPill,
  Tabs,
  fmtDateTime,
  fmtNumber,
  useAsync,
  useCan,
  useToast,
} from '../../ui'
import { Pager } from '../AuditPage'

const { getJson, sendJson } = adminHttp
const PAGE = 40

export const EVENT_TYPES: [string, string][] = [
  ['wedding', 'חתונה'], ['henna', 'חינה'], ['bar_mitzvah', 'בר מצווה'], ['bat_mitzvah', 'בת מצווה'],
  ['brit', 'ברית'], ['brita', 'בריתה'], ['family', 'משפחתי'], ['business', 'עסקי'], ['other', 'אחר'],
]
const KINDS: [string, string][] = [['', '—'], ['hall', 'אולם'], ['garden', 'גן'], ['complex', 'מתחם'], ['restaurant', 'מסעדה'], ['other', 'אחר']]
const STATUS_TONE = { active: 'ok', hidden: 'neutral', draft: 'warn' } as const

interface VenueRow {
  id: number
  name: string
  city: string
  address: string
  status: 'active' | 'hidden' | 'draft'
  status_label: string
  verified: boolean
  priority: number
  usage_count: number
  venue_kind: string
  event_types: string[]
  capacity_min: number | null
  capacity_max: number | null
  main_image: string | null
  updated_at: string | null
}

export interface VenueDetail extends VenueRow {
  description: string
  phone: string
  website: string
  capacity_by_type: Record<string, number>
  kashrut: string
  parking: string
  accessibility: string
  is_open: boolean
  contact_name: string
  contact_phone: string
  source: string
  internal_notes: string
  partnership: string
  images: { id: number; url: string; caption: string; is_main: boolean; sort_order: number }[]
  navigation: { waze: string; google: string }
  events_using: number
}

export function VenuesPage({ route }: { route: AdminRoute }) {
  const id = route.id
  if (id === 'new' || (id && Number(id))) return <VenueEditor venueId={id === 'new' ? null : Number(id)} />
  return <VenueList route={route} />
}

function VenueList({ route }: { route: AdminRoute }) {
  const can = useCan()
  const status = route.params.get('status') ?? ''
  const [q, setQ] = useState('')
  const [dq, setDq] = useState('')
  const [eventType, setEventType] = useState('')
  const [verified, setVerified] = useState('')
  const [sort, setSort] = useState('usage')
  const [offset, setOffset] = useState(0)
  useEffect(() => {
    const t = window.setTimeout(() => setDq(q), 250)
    return () => window.clearTimeout(t)
  }, [q])
  useEffect(() => setOffset(0), [dq, status, eventType, verified, sort])
  const data = useAsync(
    () => getJson<{ total: number; items: VenueRow[]; counts: Record<string, number> }>(
      `/admin/venue-cms${qs({ q: dq, status, event_type: eventType, verified, sort, limit: PAGE, offset })}`,
    ),
    [dq, status, eventType, verified, sort, offset],
  )
  const counts = data.data?.counts

  return (
    <div className="adm-page">
      <PageHeader
        title="מאגר אולמות"
        subtitle="אולם פעיל מוצע לבעלי אירועים כשהם מקלידים שם אולם. מוסתר וטיוטה — לא מוצעים."
        actions={can('venues.edit') && <a className="adm-btn adm-btn-primary" href={routeHref('venues', 'new')}>+ הוסף אולם</a>}
      />
      <Tabs
        label="סטטוס"
        tabs={[
          { key: '', label: 'הכול' },
          { key: 'active', label: 'פעילים', count: counts?.active ?? null },
          { key: 'draft', label: 'טיוטות', count: counts?.draft ?? null },
          { key: 'hidden', label: 'מוסתרים', count: counts?.hidden ?? null },
        ]}
        active={status}
        onChange={(k) => navigate('venues', null, k ? { status: k } : {}, { replace: true })}
      />
      <div className="adm-toolbar">
        <input type="search" className="adm-input adm-toolbar-search" placeholder="שם, עיר או כתובת…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="חיפוש אולם" />
        <select className="adm-input" value={eventType} onChange={(e) => setEventType(e.target.value)} aria-label="סוג אירוע">
          <option value="">כל סוגי האירועים</option>
          {EVENT_TYPES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <select className="adm-input" value={verified} onChange={(e) => setVerified(e.target.value)} aria-label="אימות">
          <option value="">מאומתים ולא מאומתים</option>
          <option value="yes">מאומתים</option>
          <option value="no">לא מאומתים</option>
        </select>
        <select className="adm-input" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="מיון">
          <option value="usage">הכי בשימוש</option>
          <option value="priority">עדיפות להצגה</option>
          <option value="name">לפי שם</option>
          <option value="recent">נוספו לאחרונה</option>
        </select>
      </div>

      {data.loading && !data.data ? (
        <Loading />
      ) : data.error && !data.data ? (
        <ErrorState message={data.error} onRetry={data.reload} />
      ) : !data.data || data.data.items.length === 0 ? (
        <EmptyState
          title={dq || status || eventType || verified ? 'לא נמצאו אולמות' : 'אין עדיין אולמות'}
          action={can('venues.edit') ? <a className="adm-btn adm-btn-primary" href={routeHref('venues', 'new')}>+ הוסף אולם</a> : undefined}
        />
      ) : (
        <>
          <div className="adm-table-wrap">
            <table className="adm-table">
              <thead>
                <tr>
                  <th className="adm-col-thumb" />
                  <th>אולם</th>
                  <th className="adm-hide-md">קיבולת</th>
                  <th className="adm-num">אירועים</th>
                  <th>סטטוס</th>
                </tr>
              </thead>
              <tbody>
                {data.data.items.map((v) => (
                  <tr key={v.id} className="is-clickable" tabIndex={0} onClick={() => navigate('venues', v.id)} onKeyDown={(e) => e.key === 'Enter' && navigate('venues', v.id)}>
                    <td className="adm-col-thumb">
                      {v.main_image ? <img className="adm-thumb" src={mediaUrl(v.main_image)} alt="" loading="lazy" /> : <span className="adm-thumb adm-thumb-empty" />}
                    </td>
                    <td>
                      <div className="adm-cell-title">
                        {v.name}
                        {v.verified && <span className="adm-verified" title="מאומת">מאומת</span>}
                      </div>
                      <div className="adm-cell-sub">{[v.city, v.address].filter(Boolean).join(' · ') || 'בלי כתובת'}</div>
                    </td>
                    <td className="adm-hide-md">{v.capacity_max ? `${v.capacity_min ?? 0}–${v.capacity_max}` : '—'}</td>
                    <td className="adm-num">{fmtNumber(v.usage_count)}</td>
                    <td><StatusPill tone={STATUS_TONE[v.status]}>{v.status_label}</StatusPill></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager total={data.data.total} offset={offset} limit={PAGE} onChange={setOffset} />
        </>
      )}
    </div>
  )
}

type Form = Omit<VenueDetail, 'id' | 'status' | 'status_label' | 'usage_count' | 'main_image' | 'updated_at' | 'images' | 'navigation' | 'events_using' | 'source'> & { source: string }

const EMPTY: Form = {
  name: '', city: '', address: '', verified: false, priority: 0, venue_kind: '', event_types: [], capacity_min: null,
  capacity_max: null, description: '', phone: '', website: '', capacity_by_type: {}, kashrut: '', parking: '',
  accessibility: '', is_open: true, contact_name: '', contact_phone: '', source: 'admin', internal_notes: '', partnership: '',
}

function toForm(v: VenueDetail): Form {
  const f = { ...EMPTY }
  for (const k of Object.keys(EMPTY) as (keyof Form)[]) {
    ;(f as Record<string, unknown>)[k] = (v as unknown as Record<string, unknown>)[k] ?? (EMPTY as Record<string, unknown>)[k]
  }
  return f
}

function VenueEditor({ venueId }: { venueId: number | null }) {
  const can = useCan()
  const toast = useToast()
  const canEdit = can('venues.edit')
  const data = useAsync(() => (venueId ? getJson<VenueDetail>(`/admin/venue-cms/${venueId}`) : Promise.resolve(null)), [venueId])
  const [form, setForm] = useState<Form>(EMPTY)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<'delete' | 'hide' | null>(null)
  useEffect(() => {
    if (data.data) setForm(toForm(data.data))
  }, [data.data])

  if (venueId && data.loading && !data.data) return <Loading />
  if (venueId && data.error && !data.data) return <ErrorState message={data.error} onRetry={data.reload} />
  const v = data.data
  const original = v ? toForm(v) : EMPTY
  const dirty = JSON.stringify(form) !== JSON.stringify(original)
  const set = <K extends keyof Form>(k: K, val: Form[K]) => setForm((p) => ({ ...p, [k]: val }))

  async function run<T>(action: () => Promise<T>, msg: string, after?: (r: T) => void) {
    setBusy(true)
    setError(null)
    try {
      const r = await action()
      toast(msg)
      after?.(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'הפעולה נכשלה')
    } finally {
      setBusy(false)
    }
  }

  function save() {
    const changed: Partial<Form> = {}
    for (const k of Object.keys(form) as (keyof Form)[]) {
      if (JSON.stringify(form[k]) !== JSON.stringify(original[k])) (changed as Record<string, unknown>)[k] = form[k]
    }
    if (!venueId) {
      run(() => sendJson<VenueDetail>('/admin/venue-cms', 'POST', form), 'האולם נוצר כטיוטה', (r) => navigate('venues', r.id, {}, { replace: true }))
    } else {
      run(() => sendJson<VenueDetail>(`/admin/venue-cms/${venueId}`, 'PATCH', changed), 'השינויים נשמרו', (r) => data.setData(r))
    }
  }

  async function addImages(files: FileList | null) {
    if (!files || !venueId) return
    for (const file of Array.from(files)) {
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(String(reader.result))
        reader.onerror = () => reject(new Error('קריאת הקובץ נכשלה'))
        reader.readAsDataURL(file)
      })
      await run(() => sendJson<VenueDetail>(`/admin/venue-cms/${venueId}/images`, 'POST', { data_url: dataUrl, caption: '' }), 'התמונה נוספה', (r) => data.setData(r))
    }
  }

  function moveImage(index: number, delta: number) {
    if (!v) return
    const ids = v.images.map((i) => i.id)
    const j = index + delta
    if (j < 0 || j >= ids.length) return
    ;[ids[index], ids[j]] = [ids[j], ids[index]]
    run(() => sendJson<VenueDetail>(`/admin/venue-cms/${v.id}/images`, 'PUT', { order: ids }), 'הסדר עודכן', (r) => data.setData(r))
  }

  const text = (k: keyof Form, label: string, opts: { ltr?: boolean; area?: boolean; hint?: string } = {}) => (
    <label className="adm-formfield">
      <span className="adm-label">{label}</span>
      {opts.area ? (
        <textarea className="adm-input" rows={3} value={String(form[k] ?? '')} disabled={!canEdit} onChange={(e) => set(k, e.target.value as never)} />
      ) : (
        <input className="adm-input" dir={opts.ltr ? 'ltr' : undefined} value={String(form[k] ?? '')} disabled={!canEdit} onChange={(e) => set(k, e.target.value as never)} />
      )}
      {opts.hint && <span className="adm-help">{opts.hint}</span>}
    </label>
  )
  const num = (k: 'capacity_min' | 'capacity_max' | 'priority', label: string) => (
    <label className="adm-formfield">
      <span className="adm-label">{label}</span>
      <input className="adm-input" type="number" min={0} value={form[k] ?? ''} disabled={!canEdit} onChange={(e) => set(k, e.target.value === '' ? (k === 'priority' ? 0 : null) : Number(e.target.value))} />
    </label>
  )

  return (
    <div className="adm-page">
      <nav className="adm-crumbs" aria-label="מיקום">
        <a href={routeHref('venues')}>מאגר אולמות</a>
        <span aria-hidden="true"> / </span>
        <span>{v ? v.name : 'אולם חדש'}</span>
      </nav>
      <header className="adm-page-head">
        <div>
          <h1 className="adm-page-title">{v ? v.name : 'אולם חדש'}</h1>
          {v && (
            <p className="adm-page-sub">
              <StatusPill tone={STATUS_TONE[v.status]}>{v.status_label}</StatusPill> · נבחר ב-{v.usage_count} אירועים · עודכן {fmtDateTime(v.updated_at)}
            </p>
          )}
        </div>
        {v && canEdit && (
          <div className="adm-page-actions">
            {v.status !== 'active' && (
              <button type="button" className="adm-btn" disabled={busy || dirty} onClick={() => run(() => sendJson<VenueDetail>(`/admin/venue-cms/${v.id}/status`, 'POST', { status: 'active' }), 'האולם פעיל', (r) => data.setData(r))}>
                הפעלה
              </button>
            )}
            {v.status === 'active' && (
              <button type="button" className="adm-btn" disabled={busy} onClick={() => setConfirm('hide')}>הסתרה</button>
            )}
            <button type="button" className="adm-btn" disabled={busy} onClick={() => run(() => sendJson<VenueDetail>(`/admin/venue-cms/${v.id}/duplicate`, 'POST'), 'נוצר עותק כטיוטה', (r) => navigate('venues', r.id))}>
              שכפול
            </button>
          </div>
        )}
      </header>
      {error && <p className="adm-inline-error" role="alert">{error}</p>}

      <div className="adm-form-grid">
        <section className="adm-control">
          <h2 className="adm-section-title">פרטים</h2>
          {text('name', 'שם')}
          {text('description', 'תיאור', { area: true })}
          <div className="adm-form-2">
            {text('city', 'עיר')}
            {text('address', 'כתובת')}
          </div>
          <div className="adm-form-2">
            {text('phone', 'טלפון', { ltr: true })}
            {text('website', 'אתר', { ltr: true })}
          </div>
          {v && (v.navigation.waze || v.navigation.google) && (
            <p className="adm-row-actions">
              <a className="adm-link" href={v.navigation.waze} target="_blank" rel="noreferrer">Waze</a>
              <a className="adm-link" href={v.navigation.google} target="_blank" rel="noreferrer">Google Maps</a>
            </p>
          )}
        </section>

        <section className="adm-control">
          <h2 className="adm-section-title">סוגי אירועים וקיבולת</h2>
          <div className="adm-chips adm-mt" role="group" aria-label="סוגי אירועים">
            {EVENT_TYPES.map(([k, l]) => {
              const on = form.event_types.includes(k)
              return (
                <button key={k} type="button" aria-pressed={on} disabled={!canEdit} className={`adm-chip${on ? ' is-on' : ''}`}
                  onClick={() => set('event_types', on ? form.event_types.filter((t) => t !== k) : [...form.event_types, k])}>
                  {l}
                </button>
              )
            })}
          </div>
          <div className="adm-form-2">
            {num('capacity_min', 'קיבולת מינימלית')}
            {num('capacity_max', 'קיבולת מקסימלית')}
          </div>
          {form.event_types.length > 0 && (
            <details className="adm-advanced">
              <summary>קיבולת לפי סוג אירוע</summary>
              <div className="adm-advanced-body adm-form-2">
                {form.event_types.map((t) => (
                  <label key={t} className="adm-formfield">
                    <span className="adm-label">{EVENT_TYPES.find(([k]) => k === t)?.[1]}</span>
                    <input className="adm-input" type="number" min={0} disabled={!canEdit} value={form.capacity_by_type[t] ?? ''}
                      onChange={(e) => {
                        const next = { ...form.capacity_by_type }
                        if (e.target.value === '') delete next[t]
                        else next[t] = Number(e.target.value)
                        set('capacity_by_type', next)
                      }} />
                  </label>
                ))}
              </div>
            </details>
          )}
          <h2 className="adm-section-title adm-mt">מידע נוסף</h2>
          <label className="adm-formfield">
            <span className="adm-label">סוג מקום</span>
            <select className="adm-input" value={form.venue_kind} disabled={!canEdit} onChange={(e) => set('venue_kind', e.target.value)}>
              {KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          <div className="adm-form-2">
            {text('kashrut', 'כשרות')}
            {text('parking', 'חניה')}
          </div>
          {text('accessibility', 'נגישות')}
          <label className="adm-check">
            <input type="checkbox" checked={form.is_open} disabled={!canEdit} onChange={(e) => set('is_open', e.target.checked)} />
            <span>המקום פתוח ופועל</span>
          </label>
        </section>

        <section className="adm-control adm-internal">
          <h2 className="adm-section-title">מידע פנימי ל-VEYA</h2>
          <p className="adm-help">לא מוצג לבעלי אירועים.</p>
          <div className="adm-form-2">
            {text('contact_name', 'איש קשר')}
            {text('contact_phone', 'טלפון איש קשר', { ltr: true })}
          </div>
          <div className="adm-form-2">
            {text('source', 'מקור')}
            {text('partnership', 'שיתוף פעולה')}
          </div>
          {text('internal_notes', 'הערות', { area: true })}
          <div className="adm-form-2">
            <label className="adm-check">
              <input type="checkbox" checked={form.verified} disabled={!canEdit} onChange={(e) => set('verified', e.target.checked)} />
              <span>מאומת (הכתובת לא תידרס ע"י בעלי אירוע)</span>
            </label>
            {num('priority', 'עדיפות להצגה (0–100)')}
          </div>
        </section>

        {v && (
          <section className="adm-control">
            <h2 className="adm-section-title">תמונות</h2>
            {v.images.length === 0 ? (
              <p className="adm-quiet">אין תמונות.</p>
            ) : (
              <ol className="adm-gallery">
                {v.images.map((img, i) => (
                  <li key={img.id}>
                    <img src={mediaUrl(img.url)} alt={img.caption || v.name} loading="lazy" />
                    <div className="adm-gallery-bar">
                      {img.is_main ? <StatusPill tone="ok">ראשית</StatusPill> : canEdit && (
                        <button type="button" className="adm-link-btn" disabled={busy} onClick={() => run(() => sendJson<VenueDetail>(`/admin/venue-cms/${v.id}/images`, 'PUT', { order: v.images.map((x) => x.id), main_id: img.id }), 'נקבעה תמונה ראשית', (r) => data.setData(r))}>
                          ראשית
                        </button>
                      )}
                      {canEdit && (
                        <span className="adm-inline-group">
                          <button type="button" className="adm-btn adm-btn-sm" disabled={busy || i === 0} onClick={() => moveImage(i, -1)} aria-label="הקדמה">→</button>
                          <button type="button" className="adm-btn adm-btn-sm" disabled={busy || i === v.images.length - 1} onClick={() => moveImage(i, 1)} aria-label="איחור">←</button>
                          <button type="button" className="adm-link-btn adm-danger-text" disabled={busy} onClick={() => run(() => sendJson<VenueDetail>(`/admin/venue-cms/${v.id}/images/${img.id}`, 'DELETE'), 'התמונה נמחקה', (r) => data.setData(r))}>
                            מחיקה
                          </button>
                        </span>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
            {canEdit && (
              <label className="adm-btn adm-mt adm-file">
                הוספת תמונות
                <input type="file" accept="image/*" multiple onChange={(e) => { addImages(e.target.files); e.target.value = '' }} />
              </label>
            )}
          </section>
        )}
      </div>

      {v && can('venues.delete') && (
        <div className="adm-danger-zone">
          <div>
            <strong>מחיקת האולם</strong>
            <p className="adm-muted">אירועים שבחרו באולם שומרים את השם והכתובת אצלם ולא מושפעים. {v.events_using > 0 ? `${v.events_using} אירועים משתמשים בשם הזה.` : ''}</p>
          </div>
          <button type="button" className="adm-btn adm-danger-text" disabled={busy} onClick={() => setConfirm('delete')}>מחיקה</button>
        </div>
      )}

      {canEdit && (dirty || !venueId) && (
        <div className="adm-savebar" role="region" aria-label="שינויים שלא נשמרו">
          <span>{venueId ? 'יש שינויים שלא נשמרו' : 'אולם חדש נשמר כטיוטה'}</span>
          {venueId && <button type="button" className="adm-btn" onClick={() => setForm(original)} disabled={busy}>ביטול</button>}
          <button type="button" className="adm-btn adm-btn-primary" onClick={save} disabled={busy || !form.name.trim()}>
            {busy ? 'שומר…' : 'שמירה'}
          </button>
        </div>
      )}

      <ConfirmAction
        open={confirm === 'hide'}
        title="הסתרת אולם"
        body={<p>האולם לא יוצע יותר לבעלי אירועים. אפשר להחזיר בכל רגע.</p>}
        confirmLabel="הסתרה"
        requireReason
        busy={busy}
        error={error}
        onConfirm={(reason) => v && run(() => sendJson<VenueDetail>(`/admin/venue-cms/${v.id}/status`, 'POST', { status: 'hidden', reason }), 'האולם הוסתר', (r) => { data.setData(r); setConfirm(null) })}
        onCancel={() => setConfirm(null)}
      />
      <ConfirmAction
        open={confirm === 'delete'}
        title="מחיקת אולם לצמיתות"
        body={<p>האולם והתמונות שלו יימחקו מהמאגר. אם רק צריך שלא יוצע — עדיף להסתיר.</p>}
        confirmLabel="מחיקה"
        danger
        typeToConfirm={v?.name}
        requireReason
        busy={busy}
        error={error}
        onConfirm={(reason) => v && run(() => sendJson(`/admin/venue-cms/${v.id}/delete`, 'POST', { confirm_name: v.name, reason }), 'האולם נמחק', () => navigate('venues'))}
        onCancel={() => setConfirm(null)}
      />
    </div>
  )
}
