import { useEffect, useState } from 'react'
import { addEventMember, listEventMembers, removeEventMember, updateEventMember } from '../api'
import type { EventMemberRead } from '../types'
import { PERMISSION_LABELS, PLANNER_PERMISSIONS, VENUE_PERMISSIONS } from '../types'
import { strings } from '../strings/he'
import { ConfirmDialog } from './ConfirmDialog'

const ROLE_LABELS: Record<string, string> = { planner: 'מפיק', venue: 'אולם' }

function permissionsForRole(role: string): readonly string[] {
  return role === 'venue' ? VENUE_PERMISSIONS : PLANNER_PERMISSIONS
}

/** שורת חבר-אירוע קיים — עריכת הרשאות + הסרה. */
function MemberRow({
  member,
  onChanged,
  eventId,
}: {
  member: EventMemberRead
  eventId: number
  onChanged: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const options = permissionsForRole(member.role)

  async function togglePermission(perm: string) {
    setError(null)
    setBusy(true)
    const next = member.permissions.includes(perm)
      ? member.permissions.filter((p) => p !== perm)
      : [...member.permissions, perm]
    try {
      await updateEventMember(eventId, member.id, next)
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.membersUpdateFailed)
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    setConfirming(false)
    setBusy(true)
    setError(null)
    try {
      await removeEventMember(eventId, member.id)
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.membersRemoveFailed)
      setBusy(false)
    }
  }

  return (
    <div className="member-row">
      {confirming && (
        <ConfirmDialog
          title="הסרת גישה"
          message={`להסיר את הגישה של ${member.display_name || member.email}?`}
          confirmLabel="כן, להסיר"
          danger
          busy={busy}
          onConfirm={remove}
          onCancel={() => setConfirming(false)}
        />
      )}
      <div className="member-row-head">
        <div>
          <strong>{member.display_name || member.email}</strong>{' '}
          <span className="badge">{ROLE_LABELS[member.role] ?? member.role}</span>
        </div>
        <button type="button" className="btn-ghost" onClick={() => setConfirming(true)} disabled={busy}>
          הסרה
        </button>
      </div>
      <div className="file-name" dir="ltr" style={{ textAlign: 'right' }}>
        {member.email}
      </div>
      <div className="member-perms">
        {options.map((perm) => (
          <label key={perm} className="member-perm-chip">
            <input
              type="checkbox"
              checked={member.permissions.includes(perm)}
              onChange={() => togglePermission(perm)}
              disabled={busy}
            />
            {PERMISSION_LABELS[perm] ?? perm}
          </label>
        ))}
      </div>
      {error && <div className="auth-error">{error}</div>}
    </div>
  )
}

/** מודל "ניהול גישה" — בעל האירוע מוסיף/מסיר מפיקים ואולמות ומגדיר הרשאות. */
export function EventMembersDialog({
  eventId,
  onClose,
}: {
  eventId: number
  onClose: () => void
}) {
  const [members, setMembers] = useState<EventMemberRead[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [email, setEmail] = useState('')
  const [busy, setBusy] = useState(false)

  function reload() {
    listEventMembers(eventId)
      .then(setMembers)
      .catch((err) =>
        setError(err instanceof Error ? err.message : strings.errors.membersLoadFailed),
      )
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventId])

  async function submitAdd(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await addEventMember(eventId, email, [])
      setEmail('')
      reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.membersAddFailed)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" style={{ maxWidth: 520 }} onClick={(e) => e.stopPropagation()} dir="rtl">
        <div className="dialog-head">
          <h2>ניהול גישה לאירוע</h2>
          <button type="button" className="x" onClick={onClose}>
            ✕
          </button>
        </div>

        <p className="file-name" style={{ textAlign: 'right' }}>
          הוסיפו מפיק/אולם לפי אימייל מדויק (חייב להיות חשבון קיים מסוג מפיק/אולם —
          נוצר ע"י האדמין). לאחר ההוספה אפשר לבחור לו הרשאות ספציפיות.
        </p>

        <form className="auth-form" onSubmit={submitAdd}>
          <div className="auth-field">
            <label htmlFor="member-email">אימייל</label>
            <input
              id="member-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              dir="ltr"
              required
            />
          </div>
          <button type="submit" className="auth-submit" disabled={busy}>
            הוספת גישה
          </button>
        </form>

        {error && <div className="auth-error">{error}</div>}

        <div className="auth-divider">
          <span className="auth-divider-line" />
          <span className="auth-divider-word">מי כבר בפנים</span>
          <span className="auth-divider-line" />
        </div>

        {members === null && <div className="empty">טוען…</div>}
        {members !== null && members.length === 0 && (
          <div className="empty">עוד אין מפיקים/אולמות עם גישה לאירוע הזה</div>
        )}
        {members !== null &&
          members.map((m) => (
            <MemberRow key={m.id} member={m} eventId={eventId} onChanged={reload} />
          ))}
      </div>
    </div>
  )
}
