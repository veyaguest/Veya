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
    <div className="reconsent-overlay" dir="rtl">
      <div className="reconsent-card" onClick={(e) => e.stopPropagation()}>
        <h2 className="reconsent-title">{strings.legal.reconsentTitle}</h2>
        <p className="reconsent-body">{strings.legal.reconsentBody}</p>
        <p className="reconsent-hint">{strings.legal.reconsentHint}</p>
        <p className="reconsent-links">
          <a href="/legal/terms.html" target="_blank" rel="noopener noreferrer">
            {strings.legal.reconsentTermsLink}
          </a>{' '}
          ·{' '}
          <a href="/legal/privacy.html" target="_blank" rel="noopener noreferrer">
            {strings.legal.reconsentPrivacyLink}
          </a>
        </p>
        {error && <div className="reconsent-error">{error}</div>}
        <button type="button" className="reconsent-submit" onClick={accept} disabled={busy}>
          {busy ? strings.common.working : strings.legal.reconsentSubmit}
        </button>
      </div>
    </div>
  )
}
