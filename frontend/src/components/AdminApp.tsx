/**
 * מסכי הניהול הוותיקים (משתמשים / אירועים / אולמות). המעטפת, הניווט והדשבורד
 * עברו ל-``src/admin/`` — כאן נשארים רק המסכים שעדיין בשימוש בתוכה.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  adminDeleteEvent,
  adminDeleteUser,
  adminDeleteVenue,
  adminDisableUser,
  adminEnableUser,
  adminGetUser,
  adminListEvents,
  adminListUsers,
  adminListVenues,
  adminMergeVenue,
  adminResetPassword,
  adminUpdateUser,
  adminUpdateVenue,
  type AdminDeleteUserMode,
} from '../api'
import type {
  AdminEventRow,
  AdminUserDetail,
  AdminUserRow,
  AdminVenueRow,
} from '../types'
import { CreateAccountForm } from './AdminPage'
import { EVENT_TYPE_OPTIONS, getEventTerms } from '../strings/eventTypes'
import { strings } from '../strings/he'

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  couple: 'בעל/ת אירוע',
  planner: 'מפיק',
  venue: 'אולם',
  phone_agent: 'טלפן',
}

/** סוגי החשבון שאדמין יכול להגדיר במסך המשתמש. */
const ACCOUNT_TYPE_OPTIONS: { value: 'couple' | 'planner' | 'venue' | 'phone_agent'; label: string }[] = [
  { value: 'couple', label: 'בעל/ת אירוע' },
  { value: 'planner', label: 'מפיק' },
  { value: 'venue', label: 'אולם' },
  { value: 'phone_agent', label: 'טלפן — שיחות אישורי הגעה בלבד' },
]

/** אייקון קווי לכל פריט בניווט האדמין. */
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

/** דיאלוג מחיקת משתמש — שתי אפשרויות: מחיקת החשבון בלבד (האירועים נשארים),
 * או מחיקת החשבון וכל האירועים בבעלותו (בלתי הפיך, דורש אישור מפורש). */
function DeleteUserDialog({
  userLabel,
  eventsCount,
  busy,
  onConfirm,
  onCancel,
}: {
  userLabel: string
  eventsCount: number
  busy?: boolean
  onConfirm: (mode: AdminDeleteUserMode) => void
  onCancel: () => void
}) {
  const [mode, setMode] = useState<AdminDeleteUserMode>('user_only')
  const [ack, setAck] = useState(false)
  const isDestructive = mode === 'user_and_events'
  const canConfirm = !isDestructive || ack

  return (
    <div className="overlay" onClick={onCancel}>
      <div className="dialog adm-confirm adm-delete-user" onClick={(e) => e.stopPropagation()}>
        <h3 className="adm-confirm-title">מחיקת {userLabel}</h3>
        <p className="adm-confirm-body">
          {eventsCount > 0
            ? `למשתמש הזה יש ${eventsCount} אירועים. בחרו מה קורה להם:`
            : 'למשתמש הזה אין אירועים משויכים.'}
        </p>

        <label className="adm-delete-option">
          <input
            type="radio"
            name="delete-mode"
            checked={mode === 'user_only'}
            onChange={() => {
              setMode('user_only')
              setAck(false)
            }}
          />
          <span>
            <strong>משתמש בלבד</strong>
            <small>מחיקת החשבון בלבד. כל האירועים והנתונים שלהם (מוזמנים, הודעות, סידור הושבה) נשארים בשלמותם.</small>
          </span>
        </label>

        <label className="adm-delete-option">
          <input
            type="radio"
            name="delete-mode"
            checked={mode === 'user_and_events'}
            onChange={() => setMode('user_and_events')}
          />
          <span>
            <strong>משתמש + כל האירועים</strong>
            <small>
              מחיקת המשתמש{eventsCount > 0 ? ` וכל ${eventsCount} האירועים בבעלותו` : ''} — כולל
              מוזמנים, RSVP, הודעות, סידורי הושבה וכל נתון תלוי אחר.
            </small>
          </span>
        </label>

        {isDestructive && (
          <div className="adm-delete-warning">
            <p>
              ⚠️ פעולה בלתי הפיכה. {eventsCount > 0 ? `${eventsCount} האירועים` : 'האירועים'} וכל
              הנתונים התלויים בהם יימחקו לצמיתות ולא ניתן יהיה לשחזר אותם.
            </p>
            <label className="adm-delete-ack">
              <input
                type="checkbox"
                checked={ack}
                onChange={(e) => setAck(e.target.checked)}
              />
              <span>אני מבין/ה שהפעולה בלתי הפיכה ומאשר/ת מחיקה מלאה</span>
            </label>
          </div>
        )}

        <div className="adm-confirm-actions">
          <button type="button" className="btn-ghost" onClick={onCancel} disabled={busy}>
            ביטול
          </button>
          <button
            type="button"
            className="btn-danger"
            onClick={() => onConfirm(mode)}
            disabled={busy || !canConfirm}
          >
            {busy ? 'רגע…' : 'מחיקה סופית'}
          </button>
        </div>
      </div>
    </div>
  )
}

/** כרטיס משתמש מלא — פרופיל, עריכה, אירועים, היסטוריית התחברות, ופעולות אדמין. */
export function AdminUserDialog({
  userId,
  onClose,
  onChanged,
  onImpersonate,
}: {
  userId: number
  onClose: () => void
  onChanged: () => void
  onImpersonate: (userId: number) => Promise<void>
}) {
  const [detail, setDetail] = useState<AdminUserDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  // עריכת פרופיל
  const [editing, setEditing] = useState(false)
  const [displayName, setDisplayName] = useState('')
  const [phone, setPhone] = useState('')
  const [accountType, setAccountType] =
    useState<'couple' | 'planner' | 'venue' | 'phone_agent'>('couple')

  // תוצאת איפוס סיסמה + דיאלוגי אישור
  const [tempPassword, setTempPassword] = useState<string | null>(null)
  const [confirm, setConfirm] = useState<null | 'disable' | 'delete'>(null)
  const [eventToDelete, setEventToDelete] = useState<AdminEventRow | null>(null)
  const [eventDeleteBusy, setEventDeleteBusy] = useState(false)

  function load() {
    adminGetUser(userId)
      .then((d) => {
        setDetail(d)
        setDisplayName(d.display_name)
        setPhone(d.phone)
        setAccountType((d.account_type as typeof accountType) ?? 'couple')
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : strings.errors.adminUserLoadFailed),
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
        // סוג חשבון של אדמין לא נשלח כלל — השרת דוחה שילוב אדמין+טלפן.
        ...(detail.is_admin ? {} : { account_type: accountType }),
      })
      setEditing(false)
      setNotice(strings.toasts.adminUserDetailsSaved)
      load()
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.adminUserSaveFailed)
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
      setError(err instanceof Error ? err.message : strings.errors.adminPasswordResetFailed)
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
      setError(err instanceof Error ? err.message : strings.errors.adminActionFailed)
      setConfirm(null)
    } finally {
      setBusy(false)
    }
  }

  async function deleteUser(mode: AdminDeleteUserMode) {
    if (!detail) return
    setBusy(true)
    setError(null)
    try {
      await adminDeleteUser(detail.id, mode)
      onChanged()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.adminDeleteFailed)
      setConfirm(null)
    } finally {
      setBusy(false)
    }
  }

  async function deleteEvent() {
    if (!eventToDelete) return
    setEventDeleteBusy(true)
    setError(null)
    try {
      await adminDeleteEvent(eventToDelete.id)
      setNotice(`האירוע ${eventToDelete.hosts || `#${eventToDelete.id}`} נמחק`)
      setEventToDelete(null)
      load()
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.adminDeleteFailed)
      setEventToDelete(null)
    } finally {
      setEventDeleteBusy(false)
    }
  }

  async function impersonate() {
    if (!detail) return
    setBusy(true)
    setError(null)
    try {
      await onImpersonate(detail.id)
      // ההתחזות מחליפה את כל המסך — הדיאלוג ירד עם רענון האפליקציה.
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.adminImpersonateFailed)
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
                  <label className="adm-field">
                    <span className="adm-field-label">סוג חשבון</span>
                    <select
                      className="adm-field-input"
                      value={accountType}
                      onChange={(e) =>
                        setAccountType(e.target.value as typeof accountType)
                      }
                      disabled={detail.is_admin}
                    >
                      {ACCOUNT_TYPE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  {accountType === 'phone_agent' && (
                    <p className="adm-field-hint">
                      טלפן רואה אך ורק את מסך "שיחות להיום". אין לו גישה לניהול
                      מוזמנים, להושבה, להודעות או להגדרות — גם לא דרך קישור ישיר.
                    </p>
                  )}
                  {detail.is_admin && (
                    <p className="adm-field-hint">
                      אי אפשר לשנות סוג חשבון של אדמין. יש להסיר קודם את הרשאת האדמין.
                    </p>
                  )}
                  <div className="adm-user-edit-actions">
                    <button
                      type="button"
                      className="btn-ghost"
                      onClick={() => {
                        setEditing(false)
                        setDisplayName(detail.display_name)
                        setPhone(detail.phone)
                        setAccountType(
                          (detail.account_type as typeof accountType) ?? 'couple',
                        )
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
                        {e.hosts || `אירוע #${e.id}`}
                      </span>
                      <span className="adm-user-event-meta">
                        {getEventTerms(e.event_type).label} · {e.venue_name || 'ללא אולם'} · {e.guests_count} מוזמנים
                      </span>
                      <button
                        type="button"
                        className="btn-danger btn-sm"
                        onClick={() => setEventToDelete(e)}
                        disabled={busy}
                      >
                        מחיקת אירוע
                      </button>
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
              {!detail.is_admin && (
                <button
                  type="button"
                  className="btn-primary"
                  onClick={impersonate}
                  disabled={busy || detail.disabled}
                  title={
                    detail.disabled
                      ? 'צריך להפעיל את החשבון לפני התחברות כמשתמש'
                      : undefined
                  }
                >
                  התחבר כמשתמש
                </button>
              )}
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

        {eventToDelete && (
          <ConfirmDialog
            title="למחוק את האירוע?"
            body={`${eventToDelete.hosts || `אירוע #${eventToDelete.id}`} (${eventToDelete.guests_count} מוזמנים) יימחק לצמיתות — כולל כל המוזמנים, ההודעות, יומן השיחות וסידור ההושבה. אי אפשר לשחזר.`}
            confirmLabel="מחיקת אירוע"
            danger
            busy={eventDeleteBusy}
            onConfirm={deleteEvent}
            onCancel={() => setEventToDelete(null)}
          />
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
          <DeleteUserDialog
            userLabel={detail.display_name || detail.email}
            eventsCount={detail.events.length}
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
export function AdminUsersView({
  onImpersonate,
}: {
  onImpersonate: (userId: number) => Promise<void>
}) {
  const [users, setUsers] = useState<AdminUserRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [openUserId, setOpenUserId] = useState<number | null>(null)

  function reload() {
    adminListUsers()
      .then(setUsers)
      .catch((err) =>
        setError(err instanceof Error ? err.message : strings.errors.adminUsersLoadFailed),
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
          onImpersonate={onImpersonate}
        />
      )}
    </div>
  )
}

/** ניהול אירועים — טבלת כל האירועים + כניסה לאירוע כבעלים (התחזות). */
export function AdminEventsView({
  onImpersonate,
}: {
  onImpersonate: (userId: number) => Promise<void>
}) {
  const [events, setEvents] = useState<AdminEventRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [busyOwner, setBusyOwner] = useState<number | null>(null)
  const [eventToDelete, setEventToDelete] = useState<AdminEventRow | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)

  useEffect(() => {
    adminListEvents()
      .then(setEvents)
      .catch((err) =>
        setError(err instanceof Error ? err.message : strings.errors.adminEventsLoadFailed),
      )
  }, [])

  const filtered = useMemo(() => {
    if (!events) return []
    const q = query.trim().toLowerCase()
    return events.filter((e) => {
      if (typeFilter && e.event_type !== typeFilter) return false
      if (!q) return true
      return (
        e.hosts.toLowerCase().includes(q) ||
        e.groom_name.toLowerCase().includes(q) ||
        e.bride_name.toLowerCase().includes(q) ||
        (e.venue_name || '').toLowerCase().includes(q) ||
        (e.owner_email || '').toLowerCase().includes(q) ||
        getEventTerms(e.event_type).label.toLowerCase().includes(q) ||
        String(e.id) === q
      )
    })
  }, [events, query, typeFilter])

  async function enterEvent(ownerId: number) {
    setBusyOwner(ownerId)
    setError(null)
    try {
      await onImpersonate(ownerId)
      // מצליח → כל המסך מתחלף לממשק הזוג; אין צורך לאפס busy.
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.adminEventEnterFailed)
      setBusyOwner(null)
    }
  }

  async function deleteEvent() {
    if (!eventToDelete) return
    setDeleteBusy(true)
    setError(null)
    try {
      await adminDeleteEvent(eventToDelete.id)
      setEvents((prev) => (prev ? prev.filter((e) => e.id !== eventToDelete.id) : prev))
      setNotice(`האירוע ${eventToDelete.hosts || `#${eventToDelete.id}`} נמחק בהצלחה`)
      setEventToDelete(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.adminDeleteFailed)
      setEventToDelete(null)
    } finally {
      setDeleteBusy(false)
    }
  }

  if (error && !events) return <div className="admin-error">{error}</div>
  if (!events) return <div className="admin-loading">טוען…</div>

  return (
    <div className="admin-page">
      <div className="adm-users-head">
        <h2 className="admin-section-title">
          כל האירועים ({filtered.length}
          {filtered.length !== events.length ? ` מתוך ${events.length}` : ''})
        </h2>
        <select
          className="adm-search"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
        >
          <option value="">כל סוגי האירוע</option>
          {EVENT_TYPE_OPTIONS.map((opt) => (
            <option key={opt.type} value={opt.type}>
              {opt.label}
            </option>
          ))}
        </select>
        <input
          type="search"
          className="adm-search"
          placeholder="חיפוש לפי בעלי אירוע, אולם, בעלים או מזהה…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {error && <div className="admin-error">{error}</div>}
      {notice && <div className="adm-user-notice">{notice}</div>}

      <div className="table-wrap">
        <table className="guests-table">
          <thead>
            <tr>
              <th>#</th>
              <th>סוג אירוע</th>
              <th>בעלי האירוע</th>
              <th>אולם</th>
              <th>בעלים</th>
              <th>מוזמנים</th>
              <th>פעולות</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((e) => (
              <tr key={e.id}>
                <td>{e.id}</td>
                <td>{getEventTerms(e.event_type).label}</td>
                <td>{e.hosts || '—'}</td>
                <td>{e.venue_name || '—'}</td>
                <td dir="ltr">{e.owner_email || '—'}</td>
                <td>{e.guests_count}</td>
                <td>
                  <div className="adm-row-actions">
                    {e.owner_id ? (
                      <button
                        type="button"
                        className="btn-ghost btn-sm"
                        onClick={() => enterEvent(e.owner_id as number)}
                        disabled={busyOwner != null}
                      >
                        {busyOwner === e.owner_id ? 'רגע…' : 'כניסה כבעלים'}
                      </button>
                    ) : (
                      <span className="adm-event-noowner">ללא בעלים</span>
                    )}
                    <button
                      type="button"
                      className="btn-danger btn-sm"
                      onClick={() => setEventToDelete(e)}
                      disabled={busyOwner != null || deleteBusy}
                    >
                      מחיקת אירוע
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="adm-empty-row">
                  לא נמצאו אירועים שתואמים לחיפוש.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {eventToDelete && (
        <ConfirmDialog
          title="מחיקת האירוע לצמיתות?"
          body={`${eventToDelete.hosts || `אירוע #${eventToDelete.id}`} (${eventToDelete.guests_count} מוזמנים) — כל המידע המשויך לאירוע (מוזמנים, הודעות, יומן שיחות, סידור הושבה) יימחק לצמיתות. לא ניתן לשחזר.`}
          confirmLabel="מחיקת אירוע"
          danger
          busy={deleteBusy}
          onConfirm={deleteEvent}
          onCancel={() => setEventToDelete(null)}
        />
      )}
    </div>
  )
}

/** ניהול מאגר האולמות — צפייה, עריכה, מחיקה ומיזוג כפילויות. */
export function AdminVenuesView() {
  const [venues, setVenues] = useState<AdminVenueRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [editing, setEditing] = useState<AdminVenueRow | null>(null)
  const [merging, setMerging] = useState<AdminVenueRow | null>(null)

  function reload() {
    adminListVenues()
      .then(setVenues)
      .catch((err) =>
        setError(err instanceof Error ? err.message : strings.errors.adminVenuesLoadFailed),
      )
  }

  useEffect(() => {
    reload()
  }, [])

  const filtered = useMemo(() => {
    if (!venues) return []
    const q = query.trim().toLowerCase()
    if (!q) return venues
    return venues.filter(
      (v) =>
        v.name.toLowerCase().includes(q) ||
        (v.address || '').toLowerCase().includes(q) ||
        (v.city || '').toLowerCase().includes(q),
    )
  }, [venues, query])

  async function handleDelete(v: AdminVenueRow) {
    if (
      !window.confirm(
        `למחוק את "${v.name}" מהמאגר? האירועים הקיימים לא יושפעו — רק ההצעה האוטומטית למשתמשים חדשים.`,
      )
    )
      return
    try {
      await adminDeleteVenue(v.id)
      setVenues((prev) => (prev ? prev.filter((x) => x.id !== v.id) : prev))
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.adminVenueDeleteFailed)
    }
  }

  if (error && !venues) return <div className="admin-error">{error}</div>
  if (!venues) return <div className="admin-loading">טוען…</div>

  return (
    <div className="admin-page">
      <div className="adm-users-head">
        <h2 className="admin-section-title">
          מאגר האולמות ({filtered.length}
          {filtered.length !== venues.length ? ` מתוך ${venues.length}` : ''})
        </h2>
        <input
          type="search"
          className="adm-search"
          placeholder="חיפוש לפי שם, כתובת או עיר…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {error && <div className="admin-error">{error}</div>}

      <div className="table-wrap">
        <table className="guests-table">
          <thead>
            <tr>
              <th>שם האולם</th>
              <th>כתובת</th>
              <th>עיר</th>
              <th>שימושים</th>
              <th>ניווט</th>
              <th>פעולות</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((v) => (
              <tr key={v.id}>
                <td>{v.name}</td>
                <td>{v.address || '—'}</td>
                <td>{v.city || '—'}</td>
                <td>{v.usage_count}</td>
                <td>
                  {v.address ? (
                    <span className="adm-venue-nav">
                      <a href={v.maps_link} target="_blank" rel="noreferrer">
                        Maps
                      </a>
                      <a href={v.waze_link} target="_blank" rel="noreferrer">
                        Waze
                      </a>
                    </span>
                  ) : (
                    '—'
                  )}
                </td>
                <td>
                  <div className="adm-row-actions">
                    <button
                      type="button"
                      className="btn-ghost btn-sm"
                      onClick={() => setEditing(v)}
                    >
                      עריכה
                    </button>
                    <button
                      type="button"
                      className="btn-ghost btn-sm"
                      onClick={() => setMerging(v)}
                    >
                      מיזוג
                    </button>
                    <button
                      type="button"
                      className="btn-ghost btn-sm danger"
                      onClick={() => handleDelete(v)}
                    >
                      מחיקה
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={6} className="adm-empty-row">
                  לא נמצאו אולמות שתואמים לחיפוש.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {editing && (
        <AdminVenueEditDialog
          venue={editing}
          onClose={() => setEditing(null)}
          onSaved={(updated) => {
            setVenues((prev) =>
              prev ? prev.map((x) => (x.id === updated.id ? updated : x)) : prev,
            )
            setEditing(null)
          }}
        />
      )}

      {merging && (
        <AdminVenueMergeDialog
          source={merging}
          venues={venues}
          onClose={() => setMerging(null)}
          onMerged={() => {
            setMerging(null)
            reload()
          }}
        />
      )}
    </div>
  )
}

/** חלונית עריכת אולם — שם, כתובת, עיר. */
function AdminVenueEditDialog({
  venue,
  onClose,
  onSaved,
}: {
  venue: AdminVenueRow
  onClose: () => void
  onSaved: (updated: AdminVenueRow) => void
}) {
  const [name, setName] = useState(venue.name)
  const [address, setAddress] = useState(venue.address)
  const [city, setCity] = useState(venue.city)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save() {
    if (!name.trim()) {
      setError(strings.errors.adminVenueNameRequired)
      return
    }
    setBusy(true)
    setError(null)
    try {
      const updated = await adminUpdateVenue(venue.id, {
        name: name.trim(),
        address: address.trim(),
        city: city.trim(),
      })
      onSaved(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.adminVenueSaveFailed)
      setBusy(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h3>עריכת אולם</h3>
          <button type="button" className="x" onClick={onClose} aria-label="סגירה">
            ×
          </button>
        </div>
        <div className="dialog-body adm-venue-form">
          <label className="adm-field">
            <span className="adm-field-label">שם האולם</span>
            <input
              className="adm-field-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="adm-field">
            <span className="adm-field-label">כתובת</span>
            <input
              className="adm-field-input"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
            />
          </label>
          <label className="adm-field">
            <span className="adm-field-label">עיר</span>
            <input
              className="adm-field-input"
              value={city}
              onChange={(e) => setCity(e.target.value)}
            />
          </label>
          {error && <div className="admin-error">{error}</div>}
        </div>
        <div className="dialog-foot">
          <button type="button" className="btn-ghost" onClick={onClose} disabled={busy}>
            ביטול
          </button>
          <button type="button" className="btn-primary" onClick={save} disabled={busy}>
            {busy ? 'רגע…' : 'שמירה'}
          </button>
        </div>
      </div>
    </div>
  )
}

/** חלונית מיזוג אולם כפול לתוך אולם יעד. */
function AdminVenueMergeDialog({
  source,
  venues,
  onClose,
  onMerged,
}: {
  source: AdminVenueRow
  venues: AdminVenueRow[]
  onClose: () => void
  onMerged: () => void
}) {
  const [targetId, setTargetId] = useState<number | ''>('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const options = venues.filter((v) => v.id !== source.id)

  async function merge() {
    if (targetId === '') {
      setError(strings.errors.adminVenueMergeTargetRequired)
      return
    }
    const target = options.find((v) => v.id === targetId)
    if (
      !window.confirm(
        `למזג את "${source.name}" לתוך "${target?.name}"? האולם "${source.name}" יימחק והשימושים שלו יתווספו ליעד. לא ניתן לבטל.`,
      )
    )
      return
    setBusy(true)
    setError(null)
    try {
      await adminMergeVenue(source.id, { target_id: targetId })
      onMerged()
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.adminVenueMergeFailed)
      setBusy(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h3>מיזוג אולם כפול</h3>
          <button type="button" className="x" onClick={onClose} aria-label="סגירה">
            ×
          </button>
        </div>
        <div className="dialog-body adm-venue-form">
          <p className="dialog-note">
            ממזגים את <strong>{source.name}</strong> לתוך אולם אחר. השימושים
            ({source.usage_count}) יתווספו ליעד, והרשומה הכפולה תימחק.
          </p>
          <label className="adm-field">
            <span className="adm-field-label">אולם יעד</span>
            <select
              className="adm-field-input"
              value={targetId}
              onChange={(e) =>
                setTargetId(e.target.value ? Number(e.target.value) : '')
              }
            >
              <option value="">בחרו אולם…</option>
              {options.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                  {v.city ? ` — ${v.city}` : ''} ({v.usage_count})
                </option>
              ))}
            </select>
          </label>
          {error && <div className="admin-error">{error}</div>}
        </div>
        <div className="dialog-foot">
          <button type="button" className="btn-ghost" onClick={onClose} disabled={busy}>
            ביטול
          </button>
          <button type="button" className="btn-primary" onClick={merge} disabled={busy}>
            {busy ? 'רגע…' : 'מיזוג'}
          </button>
        </div>
      </div>
    </div>
  )
}

/** יומן פעולות האדמין — מי עשה מה ומתי, החדשות קודם. */
