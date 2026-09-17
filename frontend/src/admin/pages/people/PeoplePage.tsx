import { useEffect, useState } from 'react'
import { AdminUserDialog } from '../../../components/AdminApp'
import { CreateAccountForm } from '../../../components/AdminPage'
import { people } from '../../peopleApi'
import { navigate, type AdminRoute } from '../../route'
import {
  Drawer,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  StatusPill,
  Tabs,
  fmtDate,
  fmtDateTime,
  useAsync,
  useCan,
} from '../../ui'
import { Pager } from '../AuditPage'
import { EventControlPage } from './EventControlPage'

const PAGE = 50
type Impersonate = (userId: number, eventId?: number) => Promise<void>

export function PeoplePage({ route, onImpersonate }: { route: AdminRoute; onImpersonate: Impersonate }) {
  const id = route.id ?? ''
  if (id.startsWith('e') && Number(id.slice(1))) {
    return <EventControlPage eventId={Number(id.slice(1))} onImpersonate={onImpersonate} />
  }
  const tab = route.params.get('tab') === 'events' ? 'events' : 'users'
  return (
    <div className="adm-page">
      <PageHeader title="משתמשים ואירועים" />
      <Tabs
        label="משתמשים ואירועים"
        tabs={[
          { key: 'users', label: 'משתמשים' },
          { key: 'events', label: 'אירועים' },
        ]}
        active={tab}
        onChange={(k) => navigate('people', null, k === 'events' ? { tab: 'events' } : {}, { replace: true })}
      />
      {tab === 'users' ? (
        <UsersTab route={route} onImpersonate={onImpersonate} />
      ) : (
        <EventsTab route={route} />
      )}
    </div>
  )
}

function useDebounced(value: string, ms = 250) {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms)
    return () => window.clearTimeout(t)
  }, [value, ms])
  return v
}

function UsersTab({ route, onImpersonate }: { route: AdminRoute; onImpersonate: Impersonate }) {
  const can = useCan()
  const [q, setQ] = useState('')
  const dq = useDebounced(q)
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const [tick, setTick] = useState(0)
  const [creating, setCreating] = useState(false)
  const openId = route.id?.startsWith('u') ? Number(route.id.slice(1)) : null

  useEffect(() => setOffset(0), [dq, status])
  const data = useAsync(() => people.users({ q: dq, status, limit: PAGE, offset }), [dq, status, offset, tick])

  return (
    <>
      <div className="adm-toolbar">
        <input
          type="search"
          className="adm-input adm-toolbar-search"
          placeholder="שם, אימייל, טלפון או מזהה…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="חיפוש משתמש"
        />
        <select className="adm-input" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="סינון">
          <option value="">כל המשתמשים</option>
          <option value="active">פעילים</option>
          <option value="disabled">חסומים</option>
          <option value="admins">אדמינים</option>
          <option value="planners">מפיקים</option>
          <option value="venues">אולמות</option>
          <option value="callers">טלפנים</option>
        </select>
        {can('users.create') && (
          <button type="button" className="adm-btn" onClick={() => setCreating(true)}>
            + חשבון מפיק / אולם
          </button>
        )}
      </div>

      {data.loading && !data.data ? (
        <Loading />
      ) : data.error && !data.data ? (
        <ErrorState message={data.error} onRetry={data.reload} />
      ) : !data.data || data.data.items.length === 0 ? (
        <EmptyState title="לא נמצאו משתמשים" text={dq || status ? 'נסו חיפוש או סינון אחר.' : undefined} />
      ) : (
        <>
          <div className="adm-table-wrap">
            <table className="adm-table">
              <thead>
                <tr>
                  <th>משתמש</th>
                  <th>סוג</th>
                  <th className="adm-num">אירועים</th>
                  <th className="adm-hide-md">התחברות אחרונה</th>
                  <th className="adm-hide-md">נרשם</th>
                  <th>סטטוס</th>
                </tr>
              </thead>
              <tbody>
                {data.data.items.map((u) => (
                  <tr
                    key={u.id}
                    className="is-clickable"
                    tabIndex={0}
                    onClick={() => navigate('people', `u${u.id}`)}
                    onKeyDown={(e) => e.key === 'Enter' && navigate('people', `u${u.id}`)}
                  >
                    <td>
                      <div className="adm-cell-title">{u.display_name || u.email}</div>
                      <div className="adm-cell-sub">{u.email}</div>
                    </td>
                    <td>
                      {u.account_type_label}
                      {u.is_admin && <div className="adm-cell-sub">{u.admin_role_label}</div>}
                    </td>
                    <td className="adm-num">
                      {u.events_count ? (
                        <a
                          className="adm-link"
                          href={`#/admin/people?tab=events&owner=${u.id}`}
                          onClick={(e) => e.stopPropagation()}
                        >
                          {u.events_count}
                        </a>
                      ) : (
                        0
                      )}
                    </td>
                    <td className="adm-hide-md adm-muted">{u.last_login_at ? fmtDateTime(u.last_login_at) : '—'}</td>
                    <td className="adm-hide-md adm-muted">{fmtDateTime(u.created_at)}</td>
                    <td>
                      <StatusPill tone={u.disabled ? 'bad' : 'ok'}>{u.disabled ? 'חסום' : 'פעיל'}</StatusPill>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager total={data.data.total} offset={offset} limit={PAGE} onChange={setOffset} />
        </>
      )}

      {openId !== null && (
        <AdminUserDialog
          userId={openId}
          onClose={() => navigate('people', null, {}, { replace: true })}
          onChanged={() => setTick((n) => n + 1)}
          onImpersonate={(uid) => onImpersonate(uid)}
        />
      )}
      <Drawer open={creating} onClose={() => setCreating(false)} title="חשבון חדש" subtitle="מפיקים ואולמות לא נרשמים לבד — החשבון נוצר כאן">
        <div className="adm-legacy">
          <CreateAccountForm onCreated={() => setTick((n) => n + 1)} />
        </div>
      </Drawer>
    </>
  )
}

function EventsTab({ route }: { route: AdminRoute }) {
  const [q, setQ] = useState('')
  const dq = useDebounced(q)
  const [eventType, setEventType] = useState('')
  const [when, setWhen] = useState('upcoming')
  const [track, setTrack] = useState('')
  const [offset, setOffset] = useState(0)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const ownerId = route.params.get('owner') ? Number(route.params.get('owner')) : null

  useEffect(() => setOffset(0), [dq, eventType, when, track, ownerId])
  const data = useAsync(
    () => people.events({ q: dq, event_type: eventType, when: ownerId ? '' : when, track, owner_id: ownerId, limit: PAGE, offset }),
    [dq, eventType, when, track, ownerId, offset],
  )

  return (
    <>
      <div className="adm-toolbar">
        <input
          type="search"
          className="adm-input adm-toolbar-search"
          placeholder="שמות, אולם, אימייל בעלים או מזהה…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="חיפוש אירוע"
        />
        <button type="button" className="adm-btn adm-filters-toggle" aria-expanded={filtersOpen} onClick={() => setFiltersOpen((v) => !v)}>
          סינון
        </button>
        <div className={`adm-filters${filtersOpen ? ' is-open' : ''}`}>
          {!ownerId && (
            <select className="adm-input" value={when} onChange={(e) => setWhen(e.target.value)} aria-label="מועד">
              <option value="upcoming">קרובים</option>
              <option value="this_month">החודש</option>
              <option value="past">עברו</option>
              <option value="no_date">בלי תאריך</option>
              <option value="">הכול</option>
            </select>
          )}
          <select className="adm-input" value={eventType} onChange={(e) => setEventType(e.target.value)} aria-label="סוג">
            <option value="">כל הסוגים</option>
            <option value="wedding">חתונה</option>
            <option value="henna">חינה</option>
            <option value="bar_mitzvah">בר מצווה</option>
            <option value="bat_mitzvah">בת מצווה</option>
            <option value="brit">ברית</option>
            <option value="brita">בריתה</option>
            <option value="business">עסקי</option>
          </select>
          <select className="adm-input" value={track} onChange={(e) => setTrack(e.target.value)} aria-label="אישורי הגעה">
            <option value="">אישורי הגעה: הכול</option>
            <option value="active">מסלול פעיל</option>
            <option value="inactive">לא הופעל</option>
          </select>
          {ownerId && (
            <button type="button" className="adm-link-btn" onClick={() => navigate('people', null, { tab: 'events' }, { replace: true })}>
              ביטול סינון לפי בעלים
            </button>
          )}
        </div>
      </div>

      {data.loading && !data.data ? (
        <Loading />
      ) : data.error && !data.data ? (
        <ErrorState message={data.error} onRetry={data.reload} />
      ) : !data.data || data.data.items.length === 0 ? (
        <EmptyState title="לא נמצאו אירועים" />
      ) : (
        <>
          <div className="adm-table-wrap">
            <table className="adm-table">
              <thead>
                <tr>
                  <th>אירוע</th>
                  <th>תאריך</th>
                  <th className="adm-hide-md">בעלים</th>
                  <th className="adm-num">מוזמנים</th>
                  <th>אישורי הגעה</th>
                  <th className="adm-num adm-hide-md">הושבה</th>
                  <th className="adm-num adm-hide-md">שיחות פתוחות</th>
                </tr>
              </thead>
              <tbody>
                {data.data.items.map((e) => (
                  <tr
                    key={e.id}
                    className="is-clickable"
                    tabIndex={0}
                    onClick={() => navigate('people', `e${e.id}`)}
                    onKeyDown={(ev) => ev.key === 'Enter' && navigate('people', `e${e.id}`)}
                  >
                    <td>
                      <div className="adm-cell-title">{e.label}</div>
                      <div className="adm-cell-sub">{e.event_type_label}{e.venue_name ? ` · ${e.venue_name}` : ''}</div>
                    </td>
                    <td>{fmtDate(e.event_date)}</td>
                    <td className="adm-hide-md adm-muted">{e.owner_email || '—'}</td>
                    <td className="adm-num">{e.guests}</td>
                    <td>
                      <div>{e.confirmed} אישרו · {e.pending} ממתינים</div>
                      <div className="adm-cell-sub">{e.rsvp_track_active ? 'מסלול פעיל' : 'מסלול לא הופעל'}</div>
                    </td>
                    <td className="adm-num adm-hide-md">{e.confirmed ? `${e.seated}/${e.confirmed}` : '—'}</td>
                    <td className="adm-num adm-hide-md">{e.open_calls || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager total={data.data.total} offset={offset} limit={PAGE} onChange={setOffset} />
        </>
      )}
    </>
  )
}
