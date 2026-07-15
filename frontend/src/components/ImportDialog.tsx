import { useEffect, useState } from 'react'
import { commitImport, previewImport } from '../api'
import type { GuestCreate, ImportPreview } from '../types'
import { groupLabel, SIDE_LABELS } from '../types'

interface Props {
  file: File
  onClose: () => void
  onImported: (created: number, skippedDuplicates: number) => void
}

export function ImportDialog({ file, onClose, onImported }: Props) {
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [committing, setCommitting] = useState(false)

  useEffect(() => {
    let cancelled = false
    previewImport(file)
      .then((p) => !cancelled && setPreview(p))
      .catch((err) => !cancelled && setError(err instanceof Error ? err.message : 'לא הצלחנו לקרוא את הקובץ. ודאו שזה קובץ אקסל תקין.'))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [file])

  async function doImport() {
    if (!preview) return
    const validRows: GuestCreate[] = preview.rows
      .filter((r) => r.valid)
      .map((r) => ({
        full_name: r.full_name,
        phone: r.phone,
        side: r.side,
        group_type: r.group_type,
        party_size: r.party_size,
        notes_raw: r.notes_raw || undefined,
      }))
    setCommitting(true)
    try {
      const res = await commitImport(validRows)
      onImported(res.created, res.skipped_duplicates)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו להוסיף את הרשימה, נסו שוב')
      setCommitting(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h2>העלאת קובץ אקסל</h2>
          <button className="x" onClick={onClose}>
            ✕
          </button>
        </div>

        <p className="file-name">📄 {file.name}</p>

        {loading && <div className="empty">רגע, קוראים את הקובץ…</div>}
        {error && <p className="form-error">{error}</p>}

        {preview && (
          <>
            <div className="import-summary">
              נמצאו {preview.total} שורות:{' '}
              <strong className="ok-text">{preview.valid_count} תקינות</strong>
              {preview.invalid_count > 0 && (
                <>
                  {' · '}
                  <strong className="err-text">
                    {preview.invalid_count} עם בעיה (לא נוסיף אותן)
                  </strong>
                </>
              )}
            </div>

            <div className="preview-wrap">
              <table className="guests-table">
                <thead>
                  <tr>
                    <th>שורה</th>
                    <th>שם מלא</th>
                    <th>טלפון</th>
                    <th>צד</th>
                    <th>קבוצה</th>
                    <th>כמות</th>
                    <th>מצב</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.rows.map((r) => (
                    <tr key={r.row_number} className={r.valid ? '' : 'row-invalid'}>
                      <td className="center">{r.row_number}</td>
                      <td>{r.full_name || '—'}</td>
                      <td dir="ltr" className="phone">
                        {r.phone}
                      </td>
                      <td>{SIDE_LABELS[r.side]}</td>
                      <td>{groupLabel(r.group_type)}</td>
                      <td className="center">{r.party_size}</td>
                      <td>
                        {r.valid ? (
                          <span className="badge confirmed">תקין</span>
                        ) : (
                          <span className="badge declined">{r.errors.join(', ')}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="add-actions">
              <button
                className="btn-primary"
                onClick={doImport}
                disabled={committing || preview.valid_count === 0}
              >
                {committing
                  ? 'מייבא…'
                  : `ייבוא ${preview.valid_count} מוזמנים`}
              </button>
              <button className="btn-ghost" onClick={onClose}>
                ביטול
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
