import { useState } from 'react'
import { changePassword, deleteMyAccount, exportMyData, logoutAll, updateProfile } from '../api'
import { setToken } from '../authStore'
import type { User } from '../types'
import { strings } from '../strings/he'

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
  const [phone, setPhone] = useState(user.phone || '')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [deleteStage, setDeleteStage] = useState<'idle' | 'confirming'>('idle')
  const [deleteConfirmText, setDeleteConfirmText] = useState('')
  const [deleting, setDeleting] = useState(false)

  async function saveName(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setNote(null)
    setBusy(true)
    try {
      const updated = await updateProfile(displayName, phone)
      onUpdated(updated)
      setNote(strings.toasts.profileUpdated)
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.profileSaveFailed)
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
      setNote(strings.toasts.passwordUpdated)
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.profilePasswordFailed)
    } finally {
      setBusy(false)
    }
  }

  async function doExport() {
    setError(null)
    setExporting(true)
    try {
      const data = await exportMyData()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `veya-export-${new Date().toISOString().slice(0, 10)}.json`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.profileExportFailed)
    } finally {
      setExporting(false)
    }
  }

  async function doDeleteAccount() {
    setError(null)
    setDeleting(true)
    try {
      await deleteMyAccount()
      onLogout()
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.profileDeleteFailed)
      setDeleting(false)
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
      setError(err instanceof Error ? err.message : strings.errors.profileLogoutAllFailed)
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

        {/* עריכת שם תצוגה + טלפון */}
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
          <div className="auth-field">
            <label htmlFor="profile-phone">טלפון</label>
            <input
              id="profile-phone"
              type="tel"
              dir="ltr"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="050-123-4567"
              autoComplete="tel"
            />
          </div>
          <button type="submit" className="auth-submit" disabled={busy}>
            שמירת פרטים
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

        <div className="auth-divider">
          <span className="auth-divider-line" />
          <span className="auth-divider-word">המידע שלי</span>
          <span className="auth-divider-line" />
        </div>

        <button
          type="button"
          className="auth-secondary"
          onClick={doExport}
          disabled={exporting}
        >
          {exporting ? 'מייצא…' : 'ייצוא המידע שלי (JSON)'}
        </button>

        <div className="auth-divider">
          <span className="auth-divider-line" />
          <span className="auth-divider-word">אזור מסוכן</span>
          <span className="auth-divider-line" />
        </div>

        {deleteStage === 'idle' ? (
          <button
            type="button"
            className="auth-danger"
            onClick={() => setDeleteStage('confirming')}
          >
            מחיקת החשבון שלי
          </button>
        ) : (
          <div className="danger-zone-confirm">
            <p className="danger-zone-warning">
              פעולה זו בלתי הפיכה: כל האירועים, המוזמנים, ההודעות והקבצים
              שלך יימחקו לצמיתות. כדי לאשר, הקלידו <strong>מחק</strong> בשדה
              למטה.
            </p>
            <input
              type="text"
              value={deleteConfirmText}
              onChange={(e) => setDeleteConfirmText(e.target.value)}
              placeholder="הקלידו מחק לאישור"
              dir="rtl"
            />
            <div className="danger-zone-actions">
              <button
                type="button"
                className="auth-danger"
                onClick={doDeleteAccount}
                disabled={deleteConfirmText !== 'מחק' || deleting}
              >
                {deleting ? 'מוחק…' : 'מחיקה סופית של החשבון'}
              </button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => {
                  setDeleteStage('idle')
                  setDeleteConfirmText('')
                }}
                disabled={deleting}
              >
                ביטול
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
