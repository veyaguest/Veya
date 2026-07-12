import { useEffect, useState } from 'react'
import { adminCreateAccount, adminListEvents, adminListUsers } from '../api'
import type { AdminEventRow, AdminUserRow } from '../types'

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  couple: 'זוג',
  planner: 'מפיק',
  venue: 'אולם',
}

/** טופס יצירת חשבון מפיק/אולם — לתפקידים אלו אין הרשמה עצמאית. */
function CreateAccountForm({ onCreated }: { onCreated: () => void }) {
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

/** פאנל האדמין (הבעלים) — סקירה של כל המשתמשים וכל האירועים במערכת. */
export function AdminPage() {
  const [users, setUsers] = useState<AdminUserRow[] | null>(null)
  const [events, setEvents] = useState<AdminEventRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  function reload() {
    Promise.all([adminListUsers(), adminListEvents()])
      .then(([u, e]) => {
        setUsers(u)
        setEvents(e)
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'שגיאה בטעינת הנתונים'),
      )
  }

  useEffect(() => {
    reload()
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

      <CreateAccountForm onCreated={reload} />

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
