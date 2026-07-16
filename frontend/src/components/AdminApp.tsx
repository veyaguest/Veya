import { useEffect, useState } from 'react'
import {
  adminDashboard,
  adminListEvents,
  adminListUsers,
} from '../api'
import type {
  AdminDashboard,
  AdminEventRow,
  AdminUserRow,
  User,
} from '../types'
import { CreateAccountForm, VeyaDefaultsManager } from './AdminPage'

type AdminPage = 'dashboard' | 'users' | 'events' | 'messages'

const ADMIN_PAGE_TITLES: Record<AdminPage, string> = {
  dashboard: 'לוח בקרה',
  users: 'ניהול משתמשים',
  events: 'ניהול אירועים',
  messages: 'הודעות ומסלול אישורים',
}

const ADMIN_NAV: { key: AdminPage; label: string }[] = [
  { key: 'dashboard', label: 'לוח בקרה' },
  { key: 'users', label: 'משתמשים' },
  { key: 'events', label: 'אירועים' },
  { key: 'messages', label: 'הודעות ומסלול' },
]

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  couple: 'זוג',
  planner: 'מפיק',
  venue: 'אולם',
}

/** אייקון קווי לכל פריט בניווט האדמין. */
function AdminNavIcon({ page }: { page: AdminPage }) {
  const common = {
    className: 'nav-icon',
    width: 22,
    height: 22,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  }
  switch (page) {
    case 'dashboard':
      return (
        <svg {...common}>
          <rect x="3" y="3" width="7" height="9" rx="1.5" />
          <rect x="14" y="3" width="7" height="5" rx="1.5" />
          <rect x="14" y="12" width="7" height="9" rx="1.5" />
          <rect x="3" y="16" width="7" height="5" rx="1.5" />
        </svg>
      )
    case 'users':
      return (
        <svg {...common}>
          <circle cx="9" cy="8" r="3" />
          <path d="M3.5 20a5.5 5.5 0 0 1 11 0" />
          <path d="M16 6.5a3 3 0 0 1 0 5.8" />
          <path d="M17.5 20a5.5 5.5 0 0 0-2.5-4.6" />
        </svg>
      )
    case 'events':
      return (
        <svg {...common}>
          <rect x="3" y="4.5" width="18" height="16" rx="2" />
          <path d="M3 9h18M8 3v3M16 3v3" />
        </svg>
      )
    case 'messages':
      return (
        <svg {...common}>
          <path d="M4 5h16v11H8l-4 3z" />
          <path d="M8 10h8M8 13h5" />
        </svg>
      )
  }
}

/** גרף עמודות פשוט להרשמות לפי יום (14 ימים אחרונים). */
function SignupsChart({ points }: { points: AdminDashboard['signups'] }) {
  const max = Math.max(1, ...points.map((p) => p.count))
  const total = points.reduce((s, p) => s + p.count, 0)
  return (
    <div className="adm-chart">
      <div className="adm-chart-head">
        <span className="adm-chart-title">הרשמות ב-14 הימים האחרונים</span>
        <span className="adm-chart-total">{total} סה״כ</span>
      </div>
      <div className="adm-chart-bars">
        {points.map((p, i) => (
          <div className="adm-bar" key={i} title={`${p.label}: ${p.count}`}>
            <div className="adm-bar-track">
              <div
                className="adm-bar-fill"
                style={{ height: `${(p.count / max) * 100}%` }}
              />
            </div>
            <span className="adm-bar-label">{p.label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** לוח הבקרה של האדמין — מונים, גרף, אירועים אחרונים והתראות. */
function AdminDashboardView() {
  const [data, setData] = useState<AdminDashboard | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    adminDashboard()
      .then(setData)
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'שגיאה בטעינת לוח הבקרה'),
      )
  }, [])

  if (error) return <div className="admin-error">{error}</div>
  if (!data) return <div className="admin-loading">טוען…</div>

  const kpis = [
    { num: data.total_events, label: 'אירועים במערכת' },
    { num: data.upcoming_events, label: 'אירועים עתידיים' },
    { num: data.total_users, label: 'משתמשים' },
    { num: data.total_guests, label: 'מוזמנים בסה״כ' },
    { num: data.total_venues, label: 'אולמות במאגר' },
    { num: data.whatsapp_sent, label: 'הודעות WhatsApp' },
  ]

  return (
    <div className="adm-dash">
      <div className="adm-kpis">
        {kpis.map((k) => (
          <div className="adm-kpi" key={k.label}>
            <span className="adm-kpi-num">{k.num}</span>
            <span className="adm-kpi-label">{k.label}</span>
          </div>
        ))}
      </div>

      <div className="adm-dash-grid">
        <SignupsChart points={data.signups} />

        <div className="adm-alerts">
          <span className="adm-chart-title">התראות מערכת</span>
          <div className="adm-alerts-list">
            {data.alerts.map((a, i) => (
              <div className={`adm-alert ${a.level}`} key={i}>
                <span className="adm-alert-dot" aria-hidden="true" />
                {a.text}
              </div>
            ))}
          </div>
        </div>
      </div>

      <h2 className="admin-section-title">אירועים אחרונים</h2>
      <div className="table-wrap">
        <table className="guests-table">
          <thead>
            <tr>
              <th>#</th>
              <th>חתן / כלה</th>
              <th>אולם</th>
              <th>בעלים</th>
              <th>מוזמנים</th>
              <th>מתי</th>
            </tr>
          </thead>
          <tbody>
            {data.recent_events.map((e) => (
              <tr key={e.id}>
                <td>{e.id}</td>
                <td>{e.couple}</td>
                <td>{e.venue_name || '—'}</td>
                <td>{e.owner_email || '—'}</td>
                <td>{e.guests_count}</td>
                <td>
                  {e.days_until != null ? (
                    <span className="badge confirmed">
                      {e.days_until === 0 ? 'היום' : `בעוד ${e.days_until} ימים`}
                    </span>
                  ) : e.event_date ? (
                    <span className="badge">עבר</span>
                  ) : (
                    <span className="badge">ללא תאריך</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** ניהול משתמשים (שלב 1 — טבלה + יצירת חשבון; עריכה/השבתה בשלב הבא). */
function AdminUsersView() {
  const [users, setUsers] = useState<AdminUserRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  function reload() {
    adminListUsers()
      .then(setUsers)
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'שגיאה בטעינת המשתמשים'),
      )
  }

  useEffect(() => {
    reload()
  }, [])

  if (error) return <div className="admin-error">{error}</div>
  if (!users) return <div className="admin-loading">טוען…</div>

  return (
    <div className="admin-page">
      <CreateAccountForm onCreated={reload} />

      <h2 className="admin-section-title">כל המשתמשים ({users.length})</h2>
      <div className="table-wrap">
        <table className="guests-table">
          <thead>
            <tr>
              <th>#</th>
              <th>שם</th>
              <th>אימייל</th>
              <th>תפקיד</th>
              <th>אירועים</th>
              <th>מוזמנים</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.id}</td>
                <td>{u.display_name || '—'}</td>
                <td dir="ltr">{u.email}</td>
                <td>
                  {u.is_admin ? (
                    <span className="badge confirmed">בעלים</span>
                  ) : (
                    <span className="badge">
                      {ACCOUNT_TYPE_LABELS[u.account_type ?? 'couple'] ?? 'משתמש'}
                    </span>
                  )}
                </td>
                <td>{u.events_count}</td>
                <td>{u.guests_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** ניהול אירועים (שלב 1 — טבלה; כניסה לאירוע/התחזות בשלב הבא). */
function AdminEventsView() {
  const [events, setEvents] = useState<AdminEventRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    adminListEvents()
      .then(setEvents)
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'שגיאה בטעינת האירועים'),
      )
  }, [])

  if (error) return <div className="admin-error">{error}</div>
  if (!events) return <div className="admin-loading">טוען…</div>

  return (
    <div className="admin-page">
      <h2 className="admin-section-title">כל האירועים ({events.length})</h2>
      <div className="table-wrap">
        <table className="guests-table">
          <thead>
            <tr>
              <th>#</th>
              <th>חתן / כלה</th>
              <th>אולם</th>
              <th>בעלים</th>
              <th>מוזמנים</th>
            </tr>
          </thead>
          <tbody>
            {events.map((e) => (
              <tr key={e.id}>
                <td>{e.id}</td>
                <td>
                  {[e.groom_name, e.bride_name].filter(Boolean).join(' · ') || '—'}
                </td>
                <td>{e.venue_name || '—'}</td>
                <td dir="ltr">{e.owner_email || '—'}</td>
                <td>{e.guests_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** פאנל האדמין המלא — מסך נפרד לגמרי מממשק הזוג (App.tsx מנתב לפי is_admin). */
export function AdminApp({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [page, setPage] = useState<AdminPage>('dashboard')
  const userInitial = (user.display_name || user.email || '?').trim().charAt(0).toUpperCase()

  return (
    <div className="shell admin-shell">
      <aside className="sidebar">
        <div className="sidebar-logo" dir="ltr">
          <span className="auth-monogram">
            <span className="auth-monogram-diamond" />
            <span className="auth-monogram-v">V</span>
          </span>
          <span className="logo-text">VEYA</span>
          <span className="admin-badge-pill">ניהול</span>
        </div>

        <nav className="side-nav">
          {ADMIN_NAV.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`nav-item ${page === item.key ? 'active' : ''}`}
              onClick={() => setPage(item.key)}
            >
              <span className="nav-bullet" aria-hidden="true" />
              <AdminNavIcon page={item.key} />
              <span className="nav-label">{item.label}</span>
              <span className="nav-label-short">{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar-foot">
          <div className="user-chip" title="חשבון אדמין">
            <span className="user-avatar">{userInitial}</span>
            <span className="user-meta">
              <span className="user-name">{user.display_name || 'אדמין'}</span>
              <span className="user-event">מנהל מערכת</span>
            </span>
          </div>
          <div className="sidebar-foot-row">
            <span className="conn">
              <span className="dot ok" />
              <span className="conn-text">מחובר</span>
            </span>
            <button type="button" className="logout-btn" onClick={onLogout}>
              יציאה
            </button>
          </div>
        </div>
      </aside>

      <div className="main-area">
        <header className="page-header">
          <h1 className="page-title">{ADMIN_PAGE_TITLES[page]}</h1>
        </header>
        <main className="content" key={page}>
          {page === 'dashboard' && <AdminDashboardView />}
          {page === 'users' && <AdminUsersView />}
          {page === 'events' && <AdminEventsView />}
          {page === 'messages' && <VeyaDefaultsManager />}
        </main>
      </div>
    </div>
  )
}
