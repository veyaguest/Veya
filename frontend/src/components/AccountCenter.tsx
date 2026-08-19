import { useEffect, useState } from 'react'
import {
  cancelPartnerInvite,
  changePassword,
  deleteMyAccount,
  getAccountOverview,
  invitePartner,
  logoutAll,
  updateProfile,
} from '../api'
import { setToken } from '../authStore'
import type { AccountOverview, User } from '../types'
import { strings } from '../strings/he'
import { ConfirmDialog } from './ConfirmDialog'
import './AccountCenter.css'

/**
 * "החשבון שלי" — מסך החשבון של VEYA.
 *
 * חמישה חלקים, בסדר הזה: הפרטים שלי → האירוע שלי → ניהול משותף → אבטחה →
 * מחיקת החשבון (בתחתית בלבד). הגישה: מסך של מוצר, לא פאנל ניהול — שדות
 * בהירים, מסגרות עדינות, הרבה אוויר, ושפה אנושית ("מנהלים את האירוע יחד")
 * במקום שפה טכנית של הרשאות וחברויות.
 */
export function AccountCenter({
  user,
  onClose,
  onUpdated,
  onLogout,
}: {
  user: User
  onClose: () => void
  onUpdated: (user: User) => void
  onLogout: () => void
}) {
  const [overview, setOverview] = useState<AccountOverview | null>(null)
  const [loading, setLoading] = useState(true)

  const [displayName, setDisplayName] = useState(user.display_name || '')
  const [phone, setPhone] = useState(user.phone || '')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [partnerEmail, setPartnerEmail] = useState('')

  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [inviting, setInviting] = useState(false)
  const [confirmingLogoutAll, setConfirmingLogoutAll] = useState(false)
  const [deleteStage, setDeleteStage] = useState<'idle' | 'confirming'>('idle')
  const [deleteConfirmText, setDeleteConfirmText] = useState('')
  const [deleting, setDeleting] = useState(false)

  async function refresh() {
    try {
      const data = await getAccountOverview()
      setOverview(data)
      setDisplayName(data.user.display_name || '')
      setPhone(data.user.phone || '')
    } catch {
      /* המסך עדיין שמיש בלי הסקירה — הפרטים האישיים מגיעים מ-user. */
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /** מנקה הודעות קודמות לפני פעולה חדשה — כדי שלא יישאר "נשמר" ליד שגיאה. */
  function reset() {
    setError(null)
    setNote(null)
  }

  async function saveDetails(e: React.FormEvent) {
    e.preventDefault()
    reset()
    setBusy(true)
    try {
      const updated = await updateProfile(displayName, phone)
      onUpdated(updated)
      setNote('הפרטים נשמרו')
      void refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.profileSaveFailed)
    } finally {
      setBusy(false)
    }
  }

  async function savePassword(e: React.FormEvent) {
    e.preventDefault()
    reset()
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

  async function sendInvite(e: React.FormEvent) {
    e.preventDefault()
    reset()
    setInviting(true)
    try {
      const invite = await invitePartner(partnerEmail)
      setPartnerEmail('')
      setNote(
        invite.email_sent
          ? `שלחנו הזמנה ל-${invite.invited_email}`
          : `ההזמנה נשמרה, אבל המייל ל-${invite.invited_email} לא יצא. אפשר לשלוח שוב`,
      )
      void refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לשלוח את ההזמנה')
    } finally {
      setInviting(false)
    }
  }

  async function resendInvite(email: string) {
    reset()
    setInviting(true)
    try {
      const invite = await invitePartner(email)
      setNote(`שלחנו שוב הזמנה ל-${invite.invited_email}`)
      void refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לשלוח את ההזמנה')
    } finally {
      setInviting(false)
    }
  }

  async function dropInvite() {
    reset()
    setInviting(true)
    try {
      await cancelPartnerInvite()
      setNote('ההזמנה בוטלה')
      void refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לבטל את ההזמנה')
    } finally {
      setInviting(false)
    }
  }

  async function doLogoutAll() {
    setConfirmingLogoutAll(false)
    setBusy(true)
    try {
      await logoutAll()
      onLogout()
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.profileLogoutAllFailed)
      setBusy(false)
    }
  }

  async function doDeleteAccount() {
    reset()
    setDeleting(true)
    try {
      await deleteMyAccount()
      onLogout()
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.profileDeleteFailed)
      setDeleting(false)
    }
  }

  const verified = overview?.user.email_verified ?? user.email_verified ?? true
  const managers = overview?.managers ?? []
  const pending = overview?.pending_invite
  const hasPartner = managers.length > 1

  return (
    <div className="acc-overlay" onClick={onClose}>
      <div
        className="acc-sheet"
        onClick={(e) => e.stopPropagation()}
        dir="rtl"
        role="dialog"
        aria-label="החשבון שלי"
      >
        <header className="acc-head">
          <h2>החשבון שלי</h2>
          <button type="button" className="acc-close" onClick={onClose} aria-label="סגירה">
            ✕
          </button>
        </header>

        <div className="acc-body">
          {error && <div className="acc-alert acc-alert-error">{error}</div>}
          {note && <div className="acc-alert acc-alert-ok">{note}</div>}

          {/* ===== הפרטים שלי ===== */}
          <section className="acc-card">
            <h3 className="acc-card-title">הפרטים שלי</h3>
            <form className="acc-form" onSubmit={saveDetails}>
              <div className="acc-field">
                <label htmlFor="acc-name">שם מלא</label>
                <input
                  id="acc-name"
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  autoComplete="name"
                  placeholder="דנה כהן"
                />
              </div>

              <div className="acc-field">
                <label htmlFor="acc-email">אימייל</label>
                <div className="acc-readonly">
                  <span dir="ltr">{overview?.user.email ?? user.email}</span>
                  {verified ? (
                    <span className="acc-badge acc-badge-ok">✓ מאומת</span>
                  ) : (
                    <span className="acc-badge acc-badge-wait">ממתין לאימות</span>
                  )}
                </div>
              </div>

              <div className="acc-field">
                <label htmlFor="acc-phone">טלפון</label>
                <input
                  id="acc-phone"
                  type="tel"
                  dir="ltr"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="050-123-4567"
                  autoComplete="tel"
                />
              </div>

              <button type="submit" className="acc-btn acc-btn-primary" disabled={busy}>
                שמירת שינויים
              </button>
            </form>
          </section>

          {/* ===== האירוע שלי ===== */}
          {overview?.event && (
            <section className="acc-card">
              <h3 className="acc-card-title">האירוע שלי</h3>
              <p className="acc-event-title">{overview.event.title}</p>
              {(overview.event.event_date || overview.event.venue_name) && (
                <p className="acc-event-meta">
                  {[overview.event.event_date, overview.event.venue_name]
                    .filter(Boolean)
                    .join(' · ')}
                </p>
              )}
            </section>
          )}

          {/* ===== ניהול משותף ===== */}
          {overview?.event && (
            <section className="acc-card">
              <h3 className="acc-card-title">ניהול משותף</h3>

              {managers.length > 0 && (
                <ul className="acc-people">
                  {managers.map((m) => (
                    <li key={m.user_id} className="acc-person">
                      <span className="acc-avatar" aria-hidden="true">
                        {(m.display_name || m.email).trim().charAt(0)}
                      </span>
                      <span className="acc-person-text">
                        <span className="acc-person-name">
                          {m.display_name}
                          {m.is_me && <span className="acc-you">זה אתם</span>}
                        </span>
                        <span className="acc-person-role">{m.role_label}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              {/* הזמנה שנשלחה וממתינה */}
              {!hasPartner && pending && (
                <div className="acc-pending">
                  <p className="acc-pending-text">
                    שלחנו הזמנה ל-<span dir="ltr">{pending.invited_email}</span> והיא
                    ממתינה לאישור.
                  </p>
                  <div className="acc-pending-actions">
                    <button
                      type="button"
                      className="acc-btn acc-btn-ghost"
                      onClick={() => resendInvite(pending.invited_email)}
                      disabled={inviting}
                    >
                      שליחה מחדש
                    </button>
                    <button
                      type="button"
                      className="acc-btn acc-btn-ghost"
                      onClick={dropInvite}
                      disabled={inviting}
                    >
                      ביטול ההזמנה
                    </button>
                  </div>
                </div>
              )}

              {/* אין שותף/ה ואין הזמנה פתוחה — ההזמנה עצמה */}
              {!hasPartner && !pending && (
                <div className="acc-invite">
                  <p className="acc-invite-lead">מנהלים את האירוע יחד?</p>
                  <p className="acc-invite-sub">
                    הזמינו את בן/בת הזוג כדי שתוכלו לנהל יחד את אותו אירוע.
                  </p>
                  <form className="acc-invite-form" onSubmit={sendInvite}>
                    <div className="acc-field">
                      <label htmlFor="acc-partner">האימייל של בן/בת הזוג</label>
                      <input
                        id="acc-partner"
                        type="email"
                        dir="ltr"
                        value={partnerEmail}
                        onChange={(e) => setPartnerEmail(e.target.value)}
                        placeholder="partner@example.com"
                        required
                      />
                    </div>
                    <button
                      type="submit"
                      className="acc-btn acc-btn-primary"
                      disabled={inviting}
                    >
                      {inviting ? 'שולח…' : 'הזמנת בן/בת זוג'}
                    </button>
                  </form>
                </div>
              )}
            </section>
          )}

          {/* ===== אבטחה ===== */}
          <section className="acc-card">
            <h3 className="acc-card-title">אבטחה</h3>
            <form className="acc-form" onSubmit={savePassword}>
              <div className="acc-field">
                <label htmlFor="acc-cur">סיסמה נוכחית</label>
                <input
                  id="acc-cur"
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                />
              </div>
              <div className="acc-field">
                <label htmlFor="acc-new">סיסמה חדשה</label>
                <input
                  id="acc-new"
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="לפחות 8 תווים, אות וספרה"
                  autoComplete="new-password"
                  required
                />
              </div>
              <button type="submit" className="acc-btn acc-btn-primary" disabled={busy}>
                שינוי סיסמה
              </button>
            </form>

            <div className="acc-divider" />

            <button
              type="button"
              className="acc-btn acc-btn-ghost acc-btn-block"
              onClick={() => setConfirmingLogoutAll(true)}
              disabled={busy}
            >
              יציאה מכל המכשירים
            </button>
          </section>

          {/* ===== מחיקת החשבון — בתחתית בלבד ===== */}
          <section className="acc-card acc-card-danger">
            <h3 className="acc-card-title">מחיקת החשבון</h3>
            <p className="acc-danger-text">
              מחיקת החשבון היא פעולה בלתי הפיכה. כל הפרטים שלכם יימחקו לצמיתות
              ולא נוכל לשחזר אותם.
              {hasPartner && ' האירוע עצמו יישאר אצל מי שמנהל אותו איתכם.'}
            </p>

            {deleteStage === 'idle' ? (
              <button
                type="button"
                className="acc-btn acc-btn-danger"
                onClick={() => setDeleteStage('confirming')}
              >
                מחיקת החשבון שלי
              </button>
            ) : (
              <div className="acc-danger-confirm">
                <label htmlFor="acc-del">
                  כדי לאשר, הקלידו <strong>מחק</strong>
                </label>
                <input
                  id="acc-del"
                  type="text"
                  value={deleteConfirmText}
                  onChange={(e) => setDeleteConfirmText(e.target.value)}
                  placeholder="מחק"
                />
                <div className="acc-danger-actions">
                  <button
                    type="button"
                    className="acc-btn acc-btn-danger"
                    onClick={doDeleteAccount}
                    disabled={deleteConfirmText.trim() !== 'מחק' || deleting}
                  >
                    {deleting ? 'מוחק…' : 'מחיקה סופית'}
                  </button>
                  <button
                    type="button"
                    className="acc-btn acc-btn-ghost"
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
          </section>

          {loading && <p className="acc-loading">טוען…</p>}
        </div>

        {confirmingLogoutAll && (
          <ConfirmDialog
            title="יציאה מכל המכשירים"
            message="לצאת מכל המכשירים? תצטרכו להתחבר מחדש בכל מקום, כולל כאן."
            confirmLabel="כן, לצאת מהכול"
            danger
            busy={busy}
            onConfirm={doLogoutAll}
            onCancel={() => setConfirmingLogoutAll(false)}
          />
        )}
      </div>
    </div>
  )
}
