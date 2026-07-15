import { useState } from 'react'
import { changePassword, logoutAll, updateProfile } from '../api'
import { setToken } from '../authStore'
import type { User } from '../types'

/**
 * מודל "החשבון שלי": עריכת שם תצוגה, שינוי סיסמה, ויציאה מכל המכשירים.
 * שינוי סיסמה או יציאה-מכל-המכשירים פוסלים את הטוקנים הישנים בשרת.
 */
export function ProfileDialog({
  user,
  onClose,
  onUpdated,
  onLogout,
  onManageAccess,
}: {
  user: User
  onClose: () => void
  onUpdated: (user: User) => void
  onLogout: () => void
  onManageAccess?: () => void
}) {
  const [displayName, setDisplayName] = useState(user.display_name || '')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function saveName(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setNote(null)
    setBusy(true)
    try {
      const updated = await updateProfile(displayName)
      onUpdated(updated)
      setNote('השם עודכן בהצלחה')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לשמור את השינוי, נסו שוב')
    } finally {
      setBusy(false)
    }
  }

  async function savePassword(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setNote(null)
    setBusy(true)
    try {
      const res = await changePassword(currentPassword, newPassword)
      // הטוקן החדש שומר על החיבור במכשיר הנוכחי; שאר המכשירים נותקו.
      setToken(res.access_token)
      setCurrentPassword('')
      setNewPassword('')
      setNote('הסיסמה עודכנה. מכשירים אחרים נותקו.')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לעדכן את הסיסמה, נסו שוב')
    } finally {
      setBusy(false)
    }
  }

  async function doLogoutAll() {
    if (
      !window.confirm(
        'לצאת מכל המכשירים? תצטרכו להתחבר מחדש בכל מקום, כולל כאן.',
      )
    )
      return
    setBusy(true)
    try {
      await logoutAll()
      onLogout()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו להוציא אתכם מכל המכשירים, נסו שוב')
      setBusy(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div
        className="dialog"
        style={{ maxWidth: 460 }}
        onClick={(e) => e.stopPropagation()}
        dir="rtl"
      >
        <div className="dialog-head">
          <h2>החשבון שלי</h2>
          <button type="button" className="x" onClick={onClose}>
            ✕
          </button>
        </div>

        <p className="file-name" dir="ltr" style={{ textAlign: 'right' }}>
          {user.email}
        </p>

        {error && <div className="auth-error">{error}</div>}
        {note && <div className="auth-note">{note}</div>}

        {/* עריכת שם תצוגה */}
        <form className="auth-form" onSubmit={saveName} style={{ marginTop: 12 }}>
          <div className="auth-field">
            <label htmlFor="profile-name">שם תצוגה</label>
            <input
              id="profile-name"
              type="text"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              autoComplete="name"
            />
          </div>
          <button type="submit" className="auth-submit" disabled={busy}>
            שמירת שם
          </button>
        </form>

        <div className="auth-divider">
          <span className="auth-divider-line" />
          <span className="auth-divider-word">סיסמה</span>
          <span className="auth-divider-line" />
        </div>

        {/* שינוי סיסמה */}
        <form className="auth-form" onSubmit={savePassword}>
          <div className="auth-field">
            <label htmlFor="profile-cur">סיסמה נוכחית</label>
            <input
              id="profile-cur"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          <div className="auth-field">
            <label htmlFor="profile-new">סיסמה חדשה</label>
            <input
              id="profile-new"
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="לפחות 8 תווים, אות וספרה"
              autoComplete="new-password"
              required
            />
          </div>
          <button type="submit" className="auth-submit" disabled={busy}>
            עדכון סיסמה
          </button>
        </form>

        {onManageAccess && (
          <>
            <div className="auth-divider">
              <span className="auth-divider-line" />
              <span className="auth-divider-word">גישה לאירוע</span>
              <span className="auth-divider-line" />
            </div>

            <button
              type="button"
              className="auth-secondary"
              onClick={onManageAccess}
              disabled={busy}
            >
              ניהול גישה לאירוע
            </button>
          </>
        )}

        <div className="auth-divider">
          <span className="auth-divider-line" />
          <span className="auth-divider-word">אבטחה</span>
          <span className="auth-divider-line" />
        </div>

        <button
          type="button"
          className="auth-secondary"
          onClick={doLogoutAll}
          disabled={busy}
        >
          יציאה מכל המכשירים
        </button>
      </div>
    </div>
  )
}
