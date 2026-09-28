import { useEffect, useState } from 'react'
import {
  fetchIPlanExportFile,
  fetchIPlanExportSummary,
  type IPlanExportIssue,
  type IPlanExportSummary,
} from '../api'
import { useBackToClose } from '../lib/backToClose'
import { strings } from '../strings/he'

const t = strings.guests

// כמה שמות מציגים בכל רשימת אזהרה לפני "ועוד N" — שהחלון לא יהפוך לרשימה.
const MAX_NAMES = 5

interface Props {
  onClose: () => void
  onDownloaded: () => void
}

/** "ייצוא לאייפלן": סיכום מה ייכנס לקובץ ומה חסר — ואז הורדה.
 *  הנתונים נבדקים בשרת בכל פתיחה, כך שהסיכום תמיד תואם לקובץ שיורד. */
export function IPlanExportDialog({ onClose, onDownloaded }: Props) {
  useBackToClose(true, onClose)
  const [summary, setSummary] = useState<IPlanExportSummary | null>(null)
  const [loadError, setLoadError] = useState('')
  const [busy, setBusy] = useState(false)
  const [downloadError, setDownloadError] = useState('')

  useEffect(() => {
    let alive = true
    fetchIPlanExportSummary()
      .then((s) => alive && setSummary(s))
      .catch(() => alive && setLoadError(t.iplanLoadError))
    return () => {
      alive = false
    }
  }, [])

  async function download() {
    if (!summary) return
    setBusy(true)
    setDownloadError('')
    try {
      const blob = await fetchIPlanExportFile()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = summary.filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      onDownloaded()
    } catch {
      setDownloadError(t.iplanDownloadError)
    } finally {
      setBusy(false)
    }
  }

  const byKind = (kind: IPlanExportIssue['kind']) =>
    (summary?.issues ?? []).filter((i) => i.kind === kind)
  const badPhone = byKind('bad_phone')
  const missingName = byKind('missing_name')
  const hasIssues = badPhone.length + missingName.length > 0
  const canDownload = !!summary && summary.invitations > 0

  return (
    <div className="overlay" onClick={onClose}>
      <div
        className="dialog iplan-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="iplan-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="dialog-head">
          <h2 id="iplan-title">{t.iplanTitle}</h2>
          <button className="x" onClick={onClose} aria-label={strings.common.close}>
            ✕
          </button>
        </div>
        <p className="dialog-note">{t.iplanIntro}</p>

        {!summary && !loadError && <p className="iplan-status">{t.iplanLoading}</p>}
        {loadError && <p className="form-error">{loadError}</p>}

        {summary && (
          <div className="iplan-body" aria-live="polite">
            {summary.invitations > 0 ? (
              <div className="iplan-summary">
                <strong>{t.iplanSummary(summary.invitations, summary.invited_people)}</strong>
                <ul className="iplan-breakdown">
                  <li>{t.iplanConfirmed(summary.confirmed, summary.confirmed_people)}</li>
                  {summary.seated > 0 && <li>{t.iplanSeated(summary.seated)}</li>}
                  {summary.pending > 0 && <li>{t.iplanPending(summary.pending)}</li>}
                  {summary.maybe > 0 && <li>{t.iplanMaybe(summary.maybe)}</li>}
                  {summary.declined > 0 && <li>{t.iplanDeclined(summary.declined)}</li>}
                </ul>
              </div>
            ) : (
              <p className="iplan-status">{t.iplanEmpty}</p>
            )}

            {summary.invitations > 0 && <p className="iplan-hint">{t.iplanRefreshHint}</p>}

            {hasIssues && (
              <section className="iplan-issues">
                <h3>{t.iplanIssuesTitle}</h3>
                {badPhone.length > 0 && <IssueList label={t.iplanBadPhone} items={badPhone} />}
                {missingName.length > 0 && <p>{t.iplanMissingName(missingName.length)}</p>}
              </section>
            )}
          </div>
        )}

        {downloadError && <p className="form-error">{downloadError}</p>}

        <div className="add-actions">
          {canDownload && (
            <button className="btn-primary" onClick={download} disabled={busy}>
              {busy ? t.iplanDownloading : t.iplanDownload}
            </button>
          )}
          <button className="btn-ghost" onClick={onClose} disabled={busy}>
            {strings.common.close}
          </button>
        </div>
      </div>
    </div>
  )
}

function IssueList({ label, items }: { label: string; items: IPlanExportIssue[] }) {
  const shown = items.slice(0, MAX_NAMES).map((i) => i.full_name)
  const rest = items.length - shown.length
  return (
    <p>
      {label} {shown.join(', ')}
      {rest > 0 && ` ${t.iplanMoreNames(rest)}`}
    </p>
  )
}
