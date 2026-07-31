import { useState } from 'react'
import { acceptConsent } from '../api'
import { strings } from '../strings/he'

/**
 * מודל חוסם: מוצג כש-user.needs_reconsent=true (גרסת תנאים/פרטיות שהמשתמש
 * אישר ישנה מהעדכנית — ראו backend/app/legal.py::needs_reconsent). חוסם
 * גישה למסכי האפליקציה עד לאישור מחדש, לפי הדרישה ב-
 * legal/11-dev-compliance-tasklist.md (Frontend #6).
 */
export function ReconsentModal({ onAccepted }: { onAccepted: () => void }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function accept() {
    setBusy(true)
    setError(null)
    try {
      await acceptConsent(['terms', 'privacy'])
      onAccepted()
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.consentSaveFailed)
      setBusy(false)
    }
  }

  return (
    <div className="overlay" dir="rtl">
      <div className="dialog" style={{ maxWidth: 440 }} onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h2>{strings.legal.reconsentTitle}</h2>
        </div>
        <p>{strings.legal.reconsentBody}</p>
        <p>
          <a href="/legal/terms.html" target="_blank" rel="noopener noreferrer">
            {strings.legal.reconsentTermsLink}
          </a>{' '}
          ·{' '}
          <a href="/legal/privacy.html" target="_blank" rel="noopener noreferrer">
            {strings.legal.reconsentPrivacyLink}
          </a>
        </p>
        {error && <div className="auth-error">{error}</div>}
        <button type="button" className="auth-submit" onClick={accept} disabled={busy}>
          {busy ? strings.common.working : strings.legal.reconsentSubmit}
        </button>
      </div>
    </div>
  )
}
