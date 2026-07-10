import { useEffect, useState } from 'react'
import { adminListEvents, adminListUsers } from '../api'
import type { AdminEventRow, AdminUserRow } from '../types'

/** פאנל האדמין (הבעלים) — סקירה של כל המשתמשים וכל האירועים במערכת. */
export function AdminPage() {
  const [users, setUsers] = useState<AdminUserRow[] | null>(null)
  const [events, setEvents] = useState<AdminEventRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    Promise.all([adminListUsers(), adminListEvents()])
      .then(([u, e]) => {
        setUsers(u)
        setEvents(e)
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'שגיאה בטעינת הנתונים'),
      )
  }, [])

  if (error) return <div className="admin-error">{error}</div>
  if (!users || !events) return <div className="admin-loading">טוען…</div>

  const totalGuests = events.reduce((s, e) => s + e.guests_count, 0)

  return (
    <div className="admin-page">
      <div className="admin-cards">
        <div className="admin-stat">
          <span className="admin-stat-num">{users.length}</span>
          <span className="admin-stat-label">משתמשים</span>
        </div>
        <div className="admin-stat">
          <span className="admin-stat-num">{events.length}</span>
          <span className="admin-stat-label">אירועים</span>
        </div>
        <div className="admin-stat">
          <span className="admin-stat-num">{totalGuests}</span>
          <span className="admin-stat-label">מוזמנים בסה״כ</span>
        </div>
      </div>

      <h2 className="admin-section-title">משתמשים</h2>
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
                <td>{u.email}</td>
                <td>
                  {u.is_admin ? (
                    <span className="badge confirmed">בעלים</span>
                  ) : (
                    <span className="badge">משתמש</span>
                  )}
                </td>
                <td>{u.events_count}</td>
                <td>{u.guests_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 className="admin-section-title">אירועים</h2>
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
                  {[e.groom_name, e.bride_name].filter(Boolean).join(' · ') ||
                    '—'}
                </td>
                <td>{e.venue_name || '—'}</td>
                <td>{e.owner_email || '—'}</td>
                <td>{e.guests_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
