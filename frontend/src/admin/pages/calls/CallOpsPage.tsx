import { useEffect, useMemo, useState } from 'react'
import {
  addDays,
  callOps,
  israelToday,
  weekday,
  type AutoAssignPreview,
  type CallerRow,
  type DaySummary,
  type TaskGroup,
  type TaskRow,
} from '../../callOpsApi'
import { navigate, type AdminRoute } from '../../route'
import {
  Advanced,
  ConfirmAction,
  Drawer,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  StatusPill,
  Tabs,
  fmtDate,
  fmtDateTime,
  fmtNumber,
  useAsync,
  useCan,
  useToast,
} from '../../ui'
import { Pager } from '../AuditPage'
import { CallersPanel } from './CallersPanel'
import { GuestCallDrawer } from './GuestCallDrawer'

const PAGE = 50

type View = 'control' | 'callers'

export function CallOpsPage({ route }: { route: AdminRoute }) {
  const view: View = route.params.get('view') === 'callers' ? 'callers' : 'control'
  const guestParam = route.params.get('guest')
  const [guestId, setGuestId] = useState<number | null>(guestParam ? Number(guestParam) : null)
  const callers = useAsync(callOps.callers, [])

  useEffect(() => {
    if (guestParam) setGuestId(Number(guestParam))
  }, [guestParam])

  return (
    <div className="adm-page">
      <PageHeader title="מרכז שליטה בטלפנים" />
      <Tabs
        label="טלפנים"
        tabs={[
          { key: 'control', label: 'שיחות' },
          { key: 'callers', label: 'טלפנים', count: callers.data?.filter((c) => !c.disabled).length ?? null },
        ]}
        active={view}
        onChange={(k) => navigate('calls', null, k === 'callers' ? { view: 'callers' } : {}, { replace: true })}
      />
      {view === 'control' ? (
        <ControlView route={route} callers={callers.data ?? []} onOpenGuest={setGuestId} />
      ) : (
        <CallersPanel callers={callers} />
      )}
      <GuestCallDrawer
        guestId={guestId}
        callers={callers.data ?? []}
        onClose={() => {
          setGuestId(null)
          if (guestParam) {
            const p: Record<string, string> = {}
            route.params.forEach((v, k) => {
              if (k !== 'guest') p[k] = v
            })
            navigate('calls', null, p, { replace: true })
          }
        }}
        onChanged={() => window.dispatchEvent(new Event('adm-calls-changed'))}
      />
    </div>
  )
}

const GROUP_TABS: Record<DaySummary['relation'], TaskGroup[]> = {
  today: ['pending', 'handled', 'unreachable', 'followup', 'overdue', 'all'],
  tomorrow: ['pending', 'all'],
  past: ['not_handled', 'handled', 'unreachable', 'followup', 'all'],
  future: ['all'],
}

const GROUP_LABELS: Record<TaskGroup, string> = {
  pending: 'ממתינות',
  handled: 'טופלו',
  not_handled: 'לא טופלו',
  unreachable: 'לא ניתן להשיג',
  followup: 'דורשות טיפול',
  overdue: 'באיחור',
  cancelled: 'בוטלו',
  all: 'הכול',
}

function ControlView({
  route,
  callers,
  onOpenGuest,
}: {
  route: AdminRoute
  callers: CallerRow[]
  onOpenGuest: (id: number) => void
}) {
  const can = useCan()
  const toast = useToast()
  const today = israelToday()
  const date = route.params.get('date') || today
  const relation: DaySummary['relation'] =
    date < today ? 'past' : date === today ? 'today' : date === addDays(today, 1) ? 'tomorrow' : 'future'
  const defaultGroup = GROUP_TABS[relation][0]
  const groupParam = route.params.get('group') as TaskGroup | null
  const group: TaskGroup = groupParam && GROUP_TABS[relation].includes(groupParam) ? groupParam : defaultGroup
  const [q, setQ] = useState(route.params.get('q') ?? '')
  const [debouncedQ, setDebouncedQ] = useState(q)
  const eventId = route.params.get('event') ? Number(route.params.get('event')) : null
  const assignee = route.params.get('assignee') ?? ''
  const eventType = route.params.get('type') ?? ''
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQ(q), 250)
    return () => window.clearTimeout(t)
  }, [q])
  useEffect(() => {
    const onChange = () => setTick((n) => n + 1)
    window.addEventListener('adm-calls-changed', onChange)
    return () => window.removeEventListener('adm-calls-changed', onChange)
  }, [])
  useEffect(() => {
    setOffset(0)
    setSelected(new Set())
  }, [date, group, debouncedQ, eventId, assignee, eventType])

  function setParams(next: Record<string, string | number | null>) {
    const p: Record<string, string> = {}
    route.params.forEach((v, k) => (p[k] = v))
    for (const [k, v] of Object.entries(next)) {
      if (v === null || v === '') delete p[k]
      else p[k] = String(v)
    }
    navigate('calls', null, p, { replace: true })
  }

  const summary = useAsync(() => callOps.day(date), [date, tick])
  const tasks = useAsync(
    () =>
      callOps.tasks({
        date, group, q: debouncedQ, event_id: eventId, assignee, event_type: eventType, limit: PAGE, offset,
      }),
    [date, group, debouncedQ, eventId, assignee, eventType, offset, tick],
  )
  const reload = () => setTick((n) => n + 1)
  const s = summary.data
  const page = tasks.data
  const isPreview = page?.mode === 'preview' || relation === 'future'

  const eventOptions = useMemo(() => {
    const m = new Map<number, string>()
    s?.rounds.forEach((r) => m.set(r.event_id, r.event_label))
    return [...m.entries()]
  }, [s])

  const selectable = (page?.items ?? []).filter((r) => r.task_id !== null && r.status === 'open')
  const allSelected = selectable.length > 0 && selectable.every((r) => selected.has(r.task_id as number))

  return (
    <>
      <DateBar date={date} today={today} onChange={(d) => setParams({ date: d === today ? null : d, group: null })} />

      {summary.loading && !s ? (
        <Loading />
      ) : summary.error && !s ? (
        <ErrorState message={summary.error} onRetry={summary.reload} />
      ) : s ? (
        <DayStats summary={s} onGroup={(g) => setParams({ group: g })} />
      ) : null}

      {s && s.exceptions.length > 0 && (
        <section className="adm-section" aria-labelledby="calls-exceptions">
          <div className="adm-section-head">
            <h2 className="adm-section-title" id="calls-exceptions">דורש בדיקה</h2>
          </div>
          <ul className="adm-list">
            {s.exceptions.map((x) => (
              <li key={x.key}>
                <button
                  type="button"
                  className="adm-list-row adm-list-btn"
                  onClick={() =>
                    x.group
                      ? setParams({ group: x.group, assignee: x.assignee || null, date: null })
                      : undefined
                  }
                >
                  <span className={`adm-sev adm-sev-${x.severity}`}>
                    {x.severity === 'critical' ? 'דחוף' : x.severity === 'warning' ? 'לטיפול' : 'לידיעה'}
                  </span>
                  <span className="adm-list-main">
                    <span className="adm-list-title">{x.title}</span>
                    <span className="adm-list-sub">{x.detail}</span>
                  </span>
                  <span className="adm-list-count">{fmtNumber(x.count)}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="adm-section">
        <Tabs
          label="קבוצות משימות"
          tabs={GROUP_TABS[relation].map((g) => ({
            key: g,
            label: relation === 'future' ? 'מתוכננות' : GROUP_LABELS[g],
            count: s && g !== 'all' ? (s.counts as Record<string, number>)[g] ?? null : null,
          }))}
          active={group}
          onChange={(g) => setParams({ group: g === defaultGroup ? null : g })}
        />

        <div className="adm-toolbar">
          <input
            type="search"
            className="adm-input adm-toolbar-search"
            placeholder="שם אורח, טלפון או אירוע…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="חיפוש"
          />
          <button
            type="button"
            className="adm-btn adm-filters-toggle"
            aria-expanded={filtersOpen}
            onClick={() => setFiltersOpen((v) => !v)}
          >
            סינון{[eventId, assignee, eventType].filter(Boolean).length ? ` (${[eventId, assignee, eventType].filter(Boolean).length})` : ''}
          </button>
          <div className={`adm-filters${filtersOpen ? ' is-open' : ''}`}>
            <select
              className="adm-input"
              value={eventId ?? ''}
              onChange={(e) => setParams({ event: e.target.value || null })}
              aria-label="אירוע"
            >
              <option value="">כל האירועים</option>
              {eventOptions.map(([id, label]) => (
                <option key={id} value={id}>{label}</option>
              ))}
            </select>
            <select
              className="adm-input"
              value={assignee}
              onChange={(e) => setParams({ assignee: e.target.value || null })}
              aria-label="טלפן"
            >
              <option value="">כל הטלפנים</option>
              <option value="none">רק ללא הקצאה</option>
              {callers.filter((c) => !c.disabled).map((c) => (
                <option key={c.id} value={c.id}>{c.display_name || c.email}</option>
              ))}
            </select>
            <select
              className="adm-input"
              value={eventType}
              onChange={(e) => setParams({ type: e.target.value || null })}
              aria-label="סוג אירוע"
            >
              <option value="">כל סוגי האירוע</option>
              <option value="wedding">חתונה</option>
              <option value="henna">חינה</option>
              <option value="bar_mitzvah">בר מצווה</option>
              <option value="bat_mitzvah">בת מצווה</option>
              <option value="brit">ברית</option>
              <option value="brita">בריתה</option>
              <option value="business">עסקי</option>
            </select>
          </div>
          {!isPreview && relation !== 'past' && can('calls.operate') && (
            <AutoAssignButton date={date} disabled={!s || s.counts.unassigned === 0} onDone={reload} />
          )}
        </div>

        {selected.size > 0 && (
          <BulkBar
            ids={[...selected]}
            callers={callers}
            date={date}
            onDone={(msg) => {
              toast(msg)
              setSelected(new Set())
              reload()
            }}
          />
        )}

        {tasks.loading && !page ? (
          <Loading />
        ) : tasks.error && !page ? (
          <ErrorState message={tasks.error} onRetry={tasks.reload} />
        ) : !page || page.items.length === 0 ? (
          <EmptyState
            title={emptyTitle(relation, group)}
            text={debouncedQ || eventId || assignee || eventType ? 'נסו לנקות את החיפוש או הסינון.' : undefined}
          />
        ) : (
          <>
            {isPreview && (
              <p className="adm-quiet">
                תצוגה מקדימה לפי לוח הזמנים הנוכחי. המשימות ייווצרו יום לפני — אם מועד סגירת הרשימה ישתנה, הרשימה תתעדכן.
              </p>
            )}
            <div className="adm-table-wrap adm-tasks">
              <table className="adm-table">
                <thead>
                  <tr>
                    {!isPreview && (
                      <th className="adm-col-check">
                        <input
                          type="checkbox"
                          aria-label="בחירת כל המשימות הפתוחות בעמוד"
                          checked={allSelected}
                          disabled={selectable.length === 0}
                          onChange={() =>
                            setSelected(
                              allSelected ? new Set() : new Set(selectable.map((r) => r.task_id as number)),
                            )
                          }
                        />
                      </th>
                    )}
                    <th>אורח</th>
                    <th>אירוע</th>
                    <th>סבב</th>
                    <th className="adm-hide-md">סיבה</th>
                    <th>טלפן</th>
                    <th>סטטוס</th>
                    <th className="adm-hide-md">ניסיון אחרון</th>
                  </tr>
                </thead>
                <tbody>
                  {page.items.map((row) => (
                    <TaskTableRow
                      key={`${row.task_id ?? 'p'}-${row.guest_id}-${row.round_number}`}
                      row={row}
                      preview={isPreview}
                      checked={row.task_id !== null && selected.has(row.task_id)}
                      onToggle={() => {
                        if (row.task_id === null) return
                        setSelected((prev) => {
                          const next = new Set(prev)
                          if (next.has(row.task_id as number)) next.delete(row.task_id as number)
                          else next.add(row.task_id as number)
                          return next
                        })
                      }}
                      onOpen={() => onOpenGuest(row.guest_id)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
            <Pager total={page.total} offset={offset} limit={PAGE} onChange={setOffset} />
          </>
        )}
      </section>

      {s && s.rounds.length > 0 && (
        <Advanced title={`סיכום סבבים (${s.rounds.length})`}>
          <RoundsTable rounds={s.rounds} canManage={can('calls.manage') && relation !== 'past'} onChanged={reload} />
        </Advanced>
      )}

      <Advanced title="עומס לאורך זמן">
        <TimelineStrip start={addDays(today, -3)} selected={date} onPick={(d) => setParams({ date: d === today ? null : d, group: null })} tick={tick} />
      </Advanced>
    </>
  )
}

function emptyTitle(relation: DaySummary['relation'], group: TaskGroup) {
  if (relation === 'future') return 'אין שיחות מתוכננות ליום הזה'
  if (group === 'pending') return relation === 'today' ? 'אין שיחות שממתינות להיום' : 'אין שיחות מתוכננות'
  if (group === 'not_handled') return 'כל השיחות של היום הזה טופלו'
  if (group === 'overdue') return 'אין שיחות באיחור'
  return 'אין משימות להצגה'
}

function DateBar({ date, today, onChange }: { date: string; today: string; onChange: (d: string) => void }) {
  const tomorrow = addDays(today, 1)
  const yesterday = addDays(today, -1)
  const label =
    date === today ? 'היום' : date === tomorrow ? 'מחר' : date === yesterday ? 'אתמול' : `יום ${weekday(date)}`
  return (
    <div className="adm-datebar" role="group" aria-label="בחירת יום">
      <div className="adm-datebar-current">
        <span className="adm-datebar-label">{label}</span>
        <span className="adm-datebar-date">{fmtDate(date)}</span>
      </div>
      <div className="adm-datebar-nav">
        <button type="button" className="adm-btn adm-btn-sm" onClick={() => onChange(addDays(date, -1))} aria-label="יום קודם">
          <span aria-hidden="true">→</span>
        </button>
        {[
          [yesterday, 'אתמול'],
          [today, 'היום'],
          [tomorrow, 'מחר'],
        ].map(([d, l]) => (
          <button
            key={d}
            type="button"
            className={`adm-seg${date === d ? ' is-on' : ''}`}
            aria-pressed={date === d}
            onClick={() => onChange(d)}
          >
            {l}
          </button>
        ))}
        <button type="button" className="adm-btn adm-btn-sm" onClick={() => onChange(addDays(date, 1))} aria-label="יום הבא">
          <span aria-hidden="true">←</span>
        </button>
        <input
          type="date"
          className="adm-input adm-input-sm"
          value={date}
          onChange={(e) => e.target.value && onChange(e.target.value)}
          aria-label="בחירת תאריך"
        />
      </div>
    </div>
  )
}

function DayStats({ summary, onGroup }: { summary: DaySummary; onGroup: (g: TaskGroup) => void }) {
  const c = summary.counts
  type Stat = { label: string; value: number; group?: TaskGroup; tone?: 'warn' | 'bad' }
  let stats: Stat[]
  if (summary.relation === 'past') {
    stats = [
      { label: 'תוכננו', value: c.planned, group: 'all' },
      { label: 'טופלו', value: c.handled, group: 'handled' },
      { label: 'לא טופלו', value: c.not_handled, group: 'not_handled', tone: c.not_handled ? 'bad' : undefined },
      { label: 'לא ניתן להשיג', value: c.unreachable, group: 'unreachable' },
      { label: 'דורשות טיפול נוסף', value: c.followup, group: 'followup', tone: c.followup ? 'warn' : undefined },
    ]
  } else if (summary.relation === 'today') {
    stats = [
      { label: 'שיחות להיום', value: c.planned, group: 'all' },
      { label: 'טופלו', value: c.handled, group: 'handled' },
      { label: 'ממתינות', value: c.pending, group: 'pending' },
      { label: 'לא ניתן להשיג', value: c.unreachable, group: 'unreachable' },
      { label: 'דורשות טיפול נוסף', value: c.followup, group: 'followup', tone: c.followup ? 'warn' : undefined },
      { label: 'באיחור מימים קודמים', value: c.overdue, group: 'overdue', tone: c.overdue ? 'bad' : undefined },
    ]
  } else {
    stats = [
      { label: 'שיחות מתוכננות', value: c.planned, group: 'all' },
      { label: 'כבר מוקצות', value: c.assigned },
      { label: 'עדיין ללא טלפן', value: c.unassigned, tone: c.unassigned ? 'warn' : undefined },
    ]
  }
  return (
    <section aria-label="מצב היום" className={`adm-stats adm-stats-${stats.length}`}>
      {stats.map((st) => {
        const inner = (
          <>
            <span className="adm-stat-value">{fmtNumber(st.value)}</span>
            <span className="adm-stat-label">{st.label}</span>
          </>
        )
        const cls = `adm-stat${st.tone === 'warn' ? ' is-warn' : st.tone === 'bad' ? ' is-bad' : ''}`
        return st.group ? (
          <button key={st.label} type="button" className={`${cls} adm-stat-btn`} onClick={() => onGroup(st.group as TaskGroup)}>
            {inner}
          </button>
        ) : (
          <div key={st.label} className={cls}>{inner}</div>
        )
      })}
    </section>
  )
}

function TaskTableRow({
  row,
  preview,
  checked,
  onToggle,
  onOpen,
}: {
  row: TaskRow
  preview: boolean
  checked: boolean
  onToggle: () => void
  onOpen: () => void
}) {
  return (
    <tr
      className={`is-clickable${checked ? ' is-selected' : ''}`}
      onClick={onOpen}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter') onOpen()
        if (e.key === ' ' && !preview) {
          e.preventDefault()
          onToggle()
        }
      }}
    >
      {!preview && (
        <td className="adm-col-check" onClick={(e) => e.stopPropagation()}>
          {row.task_id !== null && row.status === 'open' && (
            <input type="checkbox" checked={checked} onChange={onToggle} aria-label={`בחירת ${row.guest_name}`} />
          )}
        </td>
      )}
      <td data-label="אורח">
        <div className="adm-cell-title">
          {row.guest_name}
          {row.needs_attention && <span className="adm-flag" title="דורש טיפול">!</span>}
        </div>
        <div className="adm-cell-sub adm-mono">{row.phone}</div>
      </td>
      <td data-label="אירוע">
        <div className="adm-cell-title">{row.event_label}</div>
        <div className="adm-cell-sub">{fmtDate(row.event_date)}</div>
      </td>
      <td data-label="סבב">
        {row.round_label}
        {row.round_state === 'paused' && <div className="adm-cell-sub">מושהה</div>}
      </td>
      <td data-label="סיבה" className="adm-hide-md">{row.reason_label}</td>
      <td data-label="טלפן">{row.assignee_name || null}</td>
      <td data-label="סטטוס">
        <StatusPill tone={row.status_tone}>{row.status_label}</StatusPill>
        {row.reason === 'callback' && row.status === 'open' && (
          <div className="adm-cell-sub">{fmtDate(row.due_date)}</div>
        )}
      </td>
      <td data-label="ניסיון אחרון" className="adm-hide-md">
        {row.last_attempt_at ? (
          <>
            <div>{fmtDateTime(row.last_attempt_at)}</div>
            <div className="adm-cell-sub">
              {row.attempts} ניסיונות{row.handled_by_name ? ` · ${row.handled_by_name}` : ''}
            </div>
          </>
        ) : (
          <span className="adm-muted">—</span>
        )}
      </td>
    </tr>
  )
}

function BulkBar({
  ids,
  callers,
  date,
  onDone,
}: {
  ids: number[]
  callers: CallerRow[]
  date: string
  onDone: (msg: string) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dueDate, setDueDate] = useState(date < israelToday() ? israelToday() : date)
  const [confirmCancel, setConfirmCancel] = useState(false)
  const available = callers.filter((c) => c.available_today)

  async function run(action: () => Promise<{ message: string }>) {
    setBusy(true)
    setError(null)
    try {
      const r = await action()
      setConfirmCancel(false)
      onDone(r.message)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'הפעולה נכשלה')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="adm-bulkbar" role="region" aria-label="פעולות על משימות שנבחרו">
      <strong>{ids.length} נבחרו</strong>
      <select
        className="adm-input adm-input-sm"
        defaultValue=""
        disabled={busy}
        aria-label="הקצאה לטלפן"
        onChange={(e) => {
          const v = e.target.value
          if (!v) return
          run(() => callOps.assign(ids, v === 'none' ? null : Number(v)))
          e.target.value = ''
        }}
      >
        <option value="">הקצאה לטלפן…</option>
        {available.map((c) => (
          <option key={c.id} value={c.id}>{c.display_name || c.email} ({c.today.pending})</option>
        ))}
        <option value="none">הסרת הקצאה</option>
      </select>
      <span className="adm-inline-group">
        <input
          type="date"
          className="adm-input adm-input-sm"
          value={dueDate}
          min={israelToday()}
          onChange={(e) => setDueDate(e.target.value)}
          aria-label="תאריך חדש"
        />
        <button type="button" className="adm-btn adm-btn-sm" disabled={busy} onClick={() => run(() => callOps.reschedule(ids, dueDate))}>
          העברת תאריך
        </button>
      </span>
      <button type="button" className="adm-btn adm-btn-sm adm-danger-text" disabled={busy} onClick={() => setConfirmCancel(true)}>
        ביטול משימות
      </button>
      {error && <span className="adm-inline-error" role="alert">{error}</span>}
      <ConfirmAction
        open={confirmCancel}
        title={`ביטול ${ids.length} משימות שיחה`}
        body={<p>האורחים לא יקבלו שיחה במשימות האלה. אפשר לפתוח אותן מחדש מאוחר יותר.</p>}
        confirmLabel="ביטול המשימות"
        danger
        requireReason
        busy={busy}
        error={error}
        onConfirm={(reason) => run(() => callOps.cancel(ids, reason))}
        onCancel={() => setConfirmCancel(false)}
      />
    </div>
  )
}

function AutoAssignButton({ date, disabled, onDone }: { date: string; disabled: boolean; onDone: () => void }) {
  const toast = useToast()
  const [preview, setPreview] = useState<AutoAssignPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setBusy(true)
    setError(null)
    try {
      setPreview(await callOps.autoPreview(date))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'לא הצלחנו להכין חלוקה')
      setPreview({ date, proposals: [], by_caller: [], unassignable: 0, note: '' })
    } finally {
      setBusy(false)
    }
  }

  async function apply() {
    if (!preview) return
    setBusy(true)
    setError(null)
    try {
      const r = await callOps.autoApply(
        preview.date,
        preview.proposals.map((p) => ({ task_id: p.task_id, assignee_id: p.assignee_id })),
      )
      toast(r.message)
      setPreview(null)
      onDone()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'החלוקה נכשלה')
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button type="button" className="adm-btn" disabled={disabled || busy} onClick={load}>
        חלוקה אוטומטית
      </button>
      <Drawer
        open={preview !== null}
        onClose={() => setPreview(null)}
        title="חלוקת משימות לטלפנים"
        subtitle="רק משימות בלי טלפן. שום דבר לא משתנה עד שמאשרים."
        footer={
          <>
            <button type="button" className="adm-btn" onClick={() => setPreview(null)} disabled={busy}>ביטול</button>
            <button
              type="button"
              className="adm-btn adm-btn-primary"
              onClick={apply}
              disabled={busy || !preview || preview.proposals.length === 0}
            >
              {busy ? 'מחלק…' : `אישור חלוקה (${preview?.proposals.length ?? 0})`}
            </button>
          </>
        }
      >
        {error && <p className="adm-inline-error" role="alert">{error}</p>}
        {preview && preview.proposals.length === 0 ? (
          <EmptyState title="אין מה לחלק" text={preview.note || 'כל המשימות כבר מוקצות.'} />
        ) : preview ? (
          <>
            <table className="adm-table adm-table-plain">
              <thead>
                <tr><th>טלפן</th><th>משימות חדשות</th></tr>
              </thead>
              <tbody>
                {preview.by_caller.map((c) => (
                  <tr key={c.id}><td>{c.name}</td><td className="adm-num">{c.count}</td></tr>
                ))}
              </tbody>
            </table>
            {preview.unassignable > 0 && (
              <p className="adm-inline-error">{preview.unassignable} משימות יישארו בלי טלפן. {preview.note}</p>
            )}
            <Advanced title="פירוט לפי אורח">
              <ul className="adm-plain-list">
                {preview.proposals.map((p) => (
                  <li key={p.task_id}>
                    {p.guest_name} <span className="adm-muted">· {p.event_label} → </span>
                    <strong>{p.assignee_name}</strong> <span className="adm-muted">({p.why})</span>
                  </li>
                ))}
              </ul>
            </Advanced>
          </>
        ) : null}
      </Drawer>
    </>
  )
}

function RoundsTable({
  rounds,
  canManage,
  onChanged,
}: {
  rounds: DaySummary['rounds']
  canManage: boolean
  onChanged: () => void
}) {
  const toast = useToast()
  const [pending, setPending] = useState<{ event: number; round: number; action: 'pause' | 'resume' | 'stop'; label: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const stateLabel: Record<string, string> = { paused: 'מושהה', stopped: 'עצור', started: 'הופעל ידנית' }

  return (
    <>
      <div className="adm-table-wrap">
        <table className="adm-table">
          <thead>
            <tr>
              <th>אירוע</th>
              <th>סבב</th>
              <th className="adm-num">אורחים</th>
              <th className="adm-num">טופלו</th>
              <th className="adm-num">ממתינים</th>
              <th className="adm-num adm-hide-md">לא ענו</th>
              <th className="adm-num adm-hide-md">שיחה חוזרת</th>
              <th>הושלם?</th>
              {canManage && <th />}
            </tr>
          </thead>
          <tbody>
            {rounds.map((r) => (
              <tr key={`${r.event_id}-${r.round_number}`}>
                <td>
                  <div className="adm-cell-title">{r.event_label}</div>
                  <div className="adm-cell-sub">{fmtDate(r.event_date)}</div>
                </td>
                <td>
                  {r.round_label}
                  {r.state && <div className="adm-cell-sub">{stateLabel[r.state] ?? r.state}</div>}
                </td>
                <td className="adm-num">{r.total}</td>
                <td className="adm-num">{r.handled}</td>
                <td className="adm-num">{r.pending}</td>
                <td className="adm-num adm-hide-md">{r.no_answer}</td>
                <td className="adm-num adm-hide-md">{r.callback}</td>
                <td>
                  <StatusPill tone={r.complete ? 'ok' : 'warn'}>{r.complete ? 'כן' : `לא · נשארו ${r.pending}`}</StatusPill>
                </td>
                {canManage && (
                  <td className="adm-col-action">
                    {r.state === 'paused' || r.state === 'stopped' ? (
                      <button type="button" className="adm-link-btn" onClick={() => setPending({ event: r.event_id, round: r.round_number, action: 'resume', label: 'חידוש הסבב' })}>
                        חידוש
                      </button>
                    ) : (
                      <span className="adm-inline-group">
                        <button type="button" className="adm-link-btn" onClick={() => setPending({ event: r.event_id, round: r.round_number, action: 'pause', label: 'השהיית הסבב' })}>
                          השהיה
                        </button>
                        <button type="button" className="adm-link-btn adm-danger-text" onClick={() => setPending({ event: r.event_id, round: r.round_number, action: 'stop', label: 'עצירת הסבב' })}>
                          עצירה
                        </button>
                      </span>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ConfirmAction
        open={pending !== null}
        title={pending?.label ?? ''}
        body={
          <p>
            {pending?.action === 'stop'
              ? 'כל המשימות הפתוחות בסבב יבוטלו ולא ייווצרו חדשות. חידוש מחזיר אותן.'
              : pending?.action === 'pause'
                ? 'לא ייווצרו משימות חדשות לסבב עד שיחודש. משימות קיימות נשארות.'
                : 'הסבב יחזור לפעול לפי לוח הזמנים.'}
          </p>
        }
        confirmLabel={pending?.label ?? ''}
        danger={pending?.action === 'stop'}
        requireReason={pending?.action !== 'resume'}
        busy={busy}
        error={error}
        onCancel={() => {
          setPending(null)
          setError(null)
        }}
        onConfirm={async (reason) => {
          if (!pending) return
          setBusy(true)
          setError(null)
          try {
            await callOps.round(pending.event, pending.round, pending.action, reason)
            toast('הסבב עודכן')
            setPending(null)
            onChanged()
          } catch (e) {
            setError(e instanceof Error ? e.message : 'הפעולה נכשלה')
          } finally {
            setBusy(false)
          }
        }}
      />
    </>
  )
}

function TimelineStrip({
  start,
  selected,
  onPick,
  tick,
}: {
  start: string
  selected: string
  onPick: (d: string) => void
  tick: number
}) {
  const data = useAsync(() => callOps.timeline(start, 17), [start, tick])
  if (data.loading && !data.data) return <Loading />
  if (data.error && !data.data) return <ErrorState message={data.error} onRetry={data.reload} />
  const days = data.data ?? []
  const max = Math.max(1, ...days.map((d) => d.planned))
  return (
    <ol className="adm-timeline">
      {days.map((d) => (
        <li key={d.date}>
          <button
            type="button"
            className={`adm-timeline-day${d.date === selected ? ' is-on' : ''}`}
            onClick={() => onPick(d.date)}
            aria-pressed={d.date === selected}
          >
            <span className="adm-timeline-date">
              {fmtDate(d.date).slice(0, 5)} <span className="adm-muted">{weekday(d.date)}</span>
            </span>
            <span className="adm-timeline-bar" aria-hidden="true">
              <span style={{ width: `${(d.planned / max) * 100}%` }} />
            </span>
            <span className="adm-num">{fmtNumber(d.planned)}</span>
            <span className="adm-muted adm-timeline-extra">
              {d.mode === 'preview'
                ? 'צפי'
                : d.unassigned
                  ? `${d.unassigned} ללא טלפן`
                  : d.planned
                    ? `${d.handled} טופלו`
                    : ''}
            </span>
          </button>
        </li>
      ))}
    </ol>
  )
}
