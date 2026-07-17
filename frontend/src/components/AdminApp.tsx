import { useEffect, useMemo, useState } from 'react'
import {
  adminDashboard,
  adminDeleteUser,
  adminDisableUser,
  adminEnableUser,
  adminGetUser,
  adminListEvents,
  adminListUsers,
  adminResetPassword,
  adminUpdateUser,
} from '../api'
import type {
  AdminDashboard,
  AdminEventRow,
  AdminUserDetail,
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

/** מעצב תאריך+שעה קצר בעברית (DD/MM/YYYY HH:MM). */
function formatDateTime(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** תג תפקיד/מצב אחיד למשתמש. */
function UserRoleBadge({ user }: { user: { is_admin: boolean; account_type: string } }) {
  if (user.is_admin) return <span className="badge confirmed">אדמין</span>
  return (
    <span className="badge">
      {ACCOUNT_TYPE_LABELS[user.account_type ?? 'couple'] ?? 'משתמש'}
    </span>
  )
}

/** דיאלוג אישור לפעולה מסוכנת (מחיקה/השבתה). */
function ConfirmDialog({
  title,
  body,
  confirmLabel,
  danger,
  busy,
  onConfirm,
  onCancel,
}: {
  title: string
  body: string
  confirmLabel: string
  danger?: boolean
  busy?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="overlay" onClick={onCancel}>
      <div className="dialog adm-confirm" onClick={(e) => e.stopPropagation()}>
        <h3 className="adm-confirm-title">{title}</h3>
        <p className="adm-confirm-body">{body}</p>
        <div className="adm-confirm-actions">
          <button type="button" className="btn-ghost" onClick={onCancel} disabled={busy}>
            ביטול
          </button>
          <button
            type="button"
            className={danger ? 'btn-danger' : 'btn-primary'}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? 'רגע…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

/** כרטיס משתמש מלא — פרופיל, עריכה, אירועים, היסטוריית התחברות, ופעולות אדמין. */
function AdminUserDialog({
  userId,
  onClose,
  onChanged,
}: {
  userId: number
  onClose: () => void
  onChanged: () => void
}) {
  const [detail, setDetail] = useState<AdminUserDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // עריכת פרופיל
  const [editing, setEditing] = useState(false)
  const [displayName, setDisplayName] = useState('')
  const [phone, setPhone] = useState('')

  // תוצאת איפוס סיסמה + דיאלוגי אישור
  const [tempPassword, setTempPassword] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<null | 'disable' | 'delete'>(null)

  function load() {
    adminGetUser(userId)
      .then((d) => {
        setDetail(d)
        setDisplayName(d.display_name)
        setPhone(d.phone)
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'שגיאה בטעינת המשתמש'),
      )
  }

  useEffect(() => {
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId])

  async function saveProfile() {
    if (!detail) return
    setBusy(true)
    setError(null)
    try {
      await adminUpdateUser(detail.id, {
        display_name: displayName.trim(),
        phone: phone.trim(),
      })
      setEditing(false)
      setNotice('הפרטים נשמרו')
      load()
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שמירת הפרטים נכשלה')
    } finally {
      setBusy(false)
    }
  }

  async function resetPassword() {
    if (!detail) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const res = await adminResetPassword(detail.id)
      setTempPassword(res.temporary_password)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'איפוס הסיסמה נכשל')
    } finally {
      setBusy(false)
    }
  }

  async function toggleDisabled() {
    if (!detail) return
    setBusy(true)
    setError(null)
    try {
      if (detail.disabled) {
        await adminEnableUser(detail.id)
        setNotice('החשבון הופעל מחדש')
      } else {
        await adminDisableUser(detail.id)
        setNotice('החשבון הושבת')
      }
      setConfirm(null)
      load()
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'הפעולה נכשלה')
      setConfirm(null)
    } finally {
      setBusy(false)
    }
  }

  async function deleteUser() {
    if (!detail) return
    setBusy(true)
    setError(null)
    try {
      await adminDeleteUser(detail.id)
      onChanged()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'המחיקה נכשלה')
      setConfirm(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog adm-user-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head adm-user-head">
          <h2>כרטיס משתמש</h2>
          <button type="button" className="x" onClick={onClose} aria-label="סגירה">
            ×
          </button>
        </div>

        {error && <div className="admin-error">{error}</div>}
        {notice && <div className="adm-user-notice">{notice}</div>}

        {!detail ? (
          <div className="admin-loading">טוען…</div>
        ) : (
          <div className="adm-user-body">
            {detail.disabled && (
              <div className="adm-user-disabled-banner">החשבון מושבת כרגע</div>
            )}

            {/* פרופיל */}
            <section className="adm-user-section">
              <div className="adm-user-section-head">
                <span className="adm-user-section-title">פרטים</span>
                {!editing && (
                  <button
                    type="button"
                    className="btn-ghost btn-sm"
                    onClick={() => setEditing(true)}
                  >
                    עריכה
                  </button>
                )}
              </div>

              {editing ? (
                <div className="adm-user-edit">
                  <label className="adm-field">
                    <span className="adm-field-label">שם תצוגה</span>
                    <input
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      className="adm-field-input"
                    />
                  </label>
                  <label className="adm-field">
                    <span className="adm-field-label">טלפון</span>
                    <input
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      className="adm-field-input"
                      dir="ltr"
                    />
                  </label>
                  <div className="adm-user-edit-actions">
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => {
                        setEditing(false)
                        setDisplayName(detail.display_name)
                        setPhone(detail.phone)
                      }}
                      disabled={busy}
                    >
                      ביטול
                    </button>
                    <button
                      type="button"
                      className="btn-primary"
                      onClick={saveProfile}
                      disabled={busy}
                    >
                      {busy ? 'רגע…' : 'שמירה'}
                    </button>
                  </div>
                </div>
              ) : (
                <dl className="adm-user-facts">
                  <div>
                    <dt>שם</dt>
                    <dd>{detail.display_name || '—'}</dd>
                  </div>
                  <div>
                    <dt>אימייל</dt>
                    <dd dir="ltr">{detail.email}</dd>
                  </div>
                  <div>
                    <dt>טלפון</dt>
                    <dd dir="ltr">{detail.phone || '—'}</dd>
                  </div>
                  <div>
                    <dt>תפקיד</dt>
                    <dd>
                      <UserRoleBadge user={detail} />
                    </dd>
                  </div>
                  <div>
                    <dt>נרשם</dt>
                    <dd>{formatDateTime(detail.created_at)}</dd>
                  </div>
                  <div>
                    <dt>התחברויות</dt>
                    <dd>{detail.login_count}</dd>
                  </div>
                </dl>
              )}
            </section>

            {/* אירועים */}
            <section className="adm-user-section">
              <span className="adm-user-section-title">
                אירועים ({detail.events.length})
              </span>
              {detail.events.length === 0 ? (
                <p className="adm-user-empty">אין אירועים משויכים למשתמש הזה.</p>
              ) : (
                <ul className="adm-user-events">
                  {detail.events.map((e) => (
                    <li key={e.id}>
                      <span className="adm-user-event-couple">
                        {[e.groom_name, e.bride_name].filter(Boolean).join(' · ') ||
                          `אירוע #${e.id}`}
                      </span>
                      <span className="adm-user-event-meta">
                        {e.venue_name || 'ללא אולם'} · {e.guests_count} מוזמנים
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* היסטוריית התחברות */}
            <section className="adm-user-section">
              <span className="adm-user-section-title">התחברויות אחרונות</span>
              {detail.recent_logins.length === 0 ? (
                <p className="adm-user-empty">אין עדיין רישומי התחברות.</p>
              ) : (
                <ul className="adm-user-logins">
                  {detail.recent_logins.map((lg) => (
                    <li key={lg.id}>
                      <span className="adm-user-login-time">
                        {formatDateTime(lg.created_at)}
                      </span>
                      <span className="adm-user-login-ip" dir="ltr">
                        {lg.ip || '—'}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* תוצאת איפוס סיסמה */}
            {tempPassword && (
              <div className="adm-user-temp-pass">
                <span>סיסמה זמנית — מסרו אותה למשתמש:</span>
                <code dir="ltr">{tempPassword}</code>
              </div>
            )}

            {/* פעולות */}
            <div className="adm-user-actions">
              <button
                type="button"
                className="btn-ghost"
                onClick={resetPassword}
                disabled={busy}
              >
                איפוס סיסמה
              </button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() =>
                  detail.disabled ? toggleDisabled() : setConfirm('disable')
                }
                disabled={busy}
              >
                {detail.disabled ? 'הפעלה מחדש' : 'השבתת חשבון'}
              </button>
              <button
                type="button"
                className="btn-danger"
                onClick={() => setConfirm('delete')}
                disabled={busy}
              >
                מחיקה
              </button>
            </div>
          </div>
        )}

        {confirm === 'disable' && detail && (
          <ConfirmDialog
            title="להשבית את החשבון?"
            body={`${detail.display_name || detail.email} לא יוכל להתחבר עד שתפעילו מחדש. כל המכשירים המחוברים יתנתקו.`}
            confirmLabel="השבתה"
            danger
            busy={busy}
            onConfirm={toggleDisabled}
            onCancel={() => setConfirm(null)}
          />
        )}
        {confirm === 'delete' && detail && (
          <ConfirmDialog
            title="למחוק את המשתמש?"
            body={`פעולה בלתי-הפיכה: ${detail.display_name || detail.email} יימחק לצמיתות. אם יש למשתמש אירועים, המחיקה תיחסם.`}
            confirmLabel="מחיקה סופית"
            danger
            busy={busy}
            onConfirm={deleteUser}
            onCancel={() => setConfirm(null)}
          />
        )}
      </div>
    </div>
  )
}

/** ניהול משתמשים — חיפוש, טבלה לחיצה, כרטיס משתמש מלא, ויצירת חשבון. */
function AdminUsersView() {
  const [users, setUsers] = useState<AdminUserRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [openUserId, setOpenUserId] = useState<number | null>(null)

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

  const filtered = useMemo(() => {
    if (!users) return []
    const q = query.trim().toLowerCase()
    if (!q) return users
    return users.filter(
      (u) =>
        u.display_name.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q) ||
        String(u.id) === q,
    )
  }, [users, query])

  if (error) return <div className="admin-error">{error}</div>
  if (!users) return <div className="admin-loading">טוען…</div>

  return (
    <div className="admin-page">
      <CreateAccountForm onCreated={reload} />

      <div className="adm-users-head">
        <h2 className="admin-section-title">
          משתמשים ({filtered.length}
          {filtered.length !== users.length ? ` מתוך ${users.length}` : ''})
        </h2>
        <input
          type="search"
          className="adm-search"
          placeholder="חיפוש לפי שם, אימייל או מזהה…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <div className="table-wrap">
        <table className="guests-table adm-clickable-table">
          <thead>
            <tr>
              <th>#</th>
              <th>שם</th>
              <th>אימייל</th>
              <th>תפקיד</th>
              <th>אירועים</th>
              <th>מוזמנים</th>
              <th>מצב</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((u) => (
              <tr
                key={u.id}
                className="adm-row-click"
                onClick={() => setOpenUserId(u.id)}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    setOpenUserId(u.id)
                  }
                }}
              >
                <td>{u.id}</td>
                <td>{u.display_name || '—'}</td>
                <td dir="ltr">{u.email}</td>
                <td>
                  <UserRoleBadge user={u} />
                </td>
                <td>{u.events_count}</td>
                <td>{u.guests_count}</td>
                <td>
                  {u.disabled ? (
                    <span className="badge declined">מושבת</span>
                  ) : (
                    <span className="badge confirmed">פעיל</span>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="adm-empty-row">
                  לא נמצאו משתמשים שתואמים לחיפוש.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {openUserId != null && (
        <AdminUserDialog
          userId={openUserId}
          onClose={() => setOpenUserId(null)}
          onChanged={reload}
        />
      )}
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
