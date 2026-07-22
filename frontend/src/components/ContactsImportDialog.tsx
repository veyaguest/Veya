import { useState } from 'react'
import { commitImport, pasteImportPreview } from '../api'
import type { GroupType, GuestCreate, Side } from '../types'
import { GROUP_LABELS } from '../types'
import { activeEventTerms } from '../strings/eventTypes'
import { strings } from '../strings/he'
import { type EditRow, normalizePhone, rowIssues } from '../lib/importRows'

const t = strings.guests
const tc = strings.common

interface Props {
  onClose: () => void
  onImported: (created: number, skippedDuplicates: number) => void
}

// טיפוס מינימלי ל-Contact Picker API — לא חלק מ-lib.dom.d.ts הסטנדרטי.
interface WebContact {
  name?: string[]
  tel?: string[]
}
interface ContactsManager {
  select(properties: string[], options?: { multiple?: boolean }): Promise<WebContact[]>
}

function getContactsApi(): ContactsManager | null {
  const nav = navigator as Navigator & { contacts?: ContactsManager }
  return nav.contacts ?? null
}

/** זיהוי תמיכת דפדפן — כרגע רק Chrome אנדרואיד. מוסתר לגמרי אצל אחרים (כמו Safari/iPhone). */
export function isContactPickerSupported(): boolean {
  return typeof navigator !== 'undefined' && 'contacts' in navigator && 'ContactsManager' in window
}

type Stage = 'intro' | 'picking' | 'reviewing'

export function ContactsImportDialog({ onClose, onImported }: Props) {
  const [stage, setStage] = useState<Stage>('intro')
  const [rows, setRows] = useState<EditRow[]>([])
  // מספר אנשי הקשר שהוסתרו כי הם כבר קיימים ברשימת המוזמנים.
  const [hiddenDuplicates, setHiddenDuplicates] = useState(0)
  const [error, setError] = useState('')
  const [committing, setCommitting] = useState(false)

  async function pickContacts() {
    const api = getContactsApi()
    if (!api) {
      setError(t.contactsUnsupported)
      return
    }
    setError('')
    setStage('picking')
    try {
      const picked = await api.select(['name', 'tel'], { multiple: true })
      if (!picked || picked.length === 0) {
        setStage('intro')
        return
      }
      const text = picked
        .map((c) => `${(c.name?.[0] ?? '').trim()} ${(c.tel?.[0] ?? '').trim()}`.trim())
        .filter((line) => line.length > 0)
        .join('\n')
      const preview = await pasteImportPreview(text)
      let hidden = 0
      const edit: EditRow[] = []
      preview.rows.forEach((r, i) => {
        const dup = r.duplicate ?? false
        // כפילויות מוסתרות לגמרי מהתצוגה — לא מציגים אנשי קשר שכבר קיימים במערכת.
        if (dup) {
          hidden += 1
          return
        }
        edit.push({
          key: i,
          full_name: r.full_name,
          phone: r.phone,
          side: r.side,
          group_type: r.group_type,
          party_size: r.party_size,
          duplicate: false,
          include: r.valid && normalizePhone(r.phone) !== null,
        })
      })
      setHiddenDuplicates(hidden)
      setRows(edit)
      setStage('reviewing')
    } catch (err) {
      // ביטול ע"י המשתמש (AbortError) — פשוט חוזרים למסך הפתיחה, לא שגיאה.
      if (err instanceof DOMException && err.name === 'AbortError') {
        setStage('intro')
        return
      }
      setError(err instanceof Error ? err.message : t.contactsPickError)
      setStage('intro')
    }
  }

  function updateRow(key: number, patch: Partial<EditRow>) {
    setRows((prev) =>
      prev.map((r) => {
        if (r.key !== key) return r
        const next = { ...r, ...patch }
        if (!rowIssues(r).canImport && rowIssues(next).canImport) {
          next.include = true
        }
        return next
      }),
    )
  }

  const includedReady = rows.filter((r) => r.include && rowIssues(r).canImport)
  const selectableCount = rows.filter((r) => rowIssues(r).canImport).length

  function selectAll() {
    setRows((prev) => prev.map((r) => (rowIssues(r).canImport ? { ...r, include: true } : r)))
  }
  function clearAll() {
    setRows((prev) => prev.map((r) => ({ ...r, include: false })))
  }

  function removeRow(key: number) {
    setRows((prev) => prev.filter((r) => r.key !== key))
  }

  async function doImport() {
    if (includedReady.length === 0) return
    setCommitting(true)
    setError('')
    try {
      const payload: GuestCreate[] = includedReady.map((r) => ({
        full_name: r.full_name.trim(),
        phone: r.phone,
        side: r.side,
        group_type: r.group_type,
        party_size: r.party_size,
      }))
      const res = await commitImport(payload)
      onImported(res.created, res.skipped_duplicates)
    } catch (err) {
      setError(err instanceof Error ? err.message : t.pasteImportError)
      setCommitting(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog paste-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h2>{t.contactsTitle}</h2>
          <button className="x" onClick={onClose}>
            ✕
          </button>
        </div>

        {(stage === 'intro' || stage === 'picking') && (
          <>
            <p className="paste-hint">{t.contactsHint}</p>
            {error && <p className="form-error">{error}</p>}
            <div className="add-actions">
              <button
                className="btn-primary"
                onClick={pickContacts}
                disabled={stage === 'picking'}
              >
                {stage === 'picking' ? t.contactsPicking : t.contactsPickButton}
              </button>
              <button className="btn-ghost" onClick={onClose}>
                {tc.cancel}
              </button>
            </div>
          </>
        )}

        {stage === 'reviewing' && (
          <>
            <p className="paste-hint">
              {t.contactsReviewHint}
              {hiddenDuplicates > 0 ? ' ' + t.contactsHiddenDuplicates(hiddenDuplicates) : ''}
            </p>

            {rows.length === 0 && (
              <div className="empty">{t.contactsEmptyAfterDedup}</div>
            )}

            {rows.length > 0 && (
              <>
                <div className="import-summary">
                  <span>{t.pasteSelectedSummary(includedReady.length, rows.length)}</span>
                  <span className="select-actions">
                    <button
                      type="button"
                      className="btn-link"
                      onClick={selectAll}
                      disabled={selectableCount === 0}
                    >
                      {t.selectAll}
                    </button>
                    <button
                      type="button"
                      className="btn-link"
                      onClick={clearAll}
                      disabled={includedReady.length === 0}
                    >
                      {t.clearAll}
                    </button>
                  </span>
                </div>

                <div className="preview-wrap">
                  <table className="guests-table paste-table">
                    <thead>
                      <tr>
                        <th className="center">{t.colImport}</th>
                        <th>{t.colFullName}</th>
                        <th>{t.colPhone}</th>
                        <th>{t.colSide}</th>
                        <th>{t.colGroup}</th>
                        <th className="center">{t.colCount}</th>
                        <th>{t.colNotes}</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r) => {
                        const { canImport, badges } = rowIssues(r)
                        return (
                          <tr key={r.key} className={r.include ? '' : 'row-excluded'}>
                            <td className="center">
                              <input
                                type="checkbox"
                                checked={r.include}
                                disabled={!canImport}
                                onChange={(e) => updateRow(r.key, { include: e.target.checked })}
                              />
                            </td>
                            <td>
                              <input
                                className="cell-input"
                                value={r.full_name}
                                onChange={(e) => updateRow(r.key, { full_name: e.target.value })}
                              />
                            </td>
                            <td>
                              <input
                                className="cell-input phone"
                                dir="ltr"
                                value={r.phone}
                                onChange={(e) => updateRow(r.key, { phone: e.target.value })}
                              />
                            </td>
                            <td>
                              <select
                                className="cell-input"
                                value={r.side}
                                onChange={(e) => updateRow(r.key, { side: e.target.value as Side })}
                              >
                                {Object.entries(activeEventTerms().sideLabels).map(([v, l]) => (
                                  <option key={v} value={v}>
                                    {l}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td>
                              <select
                                className="cell-input"
                                value={r.group_type in GROUP_LABELS ? r.group_type : 'other'}
                                onChange={(e) =>
                                  updateRow(r.key, { group_type: e.target.value as GroupType })
                                }
                              >
                                {activeEventTerms().groupOptions.map(({ key, label }) => (
                                  <option key={key} value={key}>
                                    {label}
                                  </option>
                                ))}
                              </select>
                            </td>
                            <td className="center">
                              <input
                                className="cell-input count-input"
                                type="number"
                                min={1}
                                value={r.party_size}
                                onChange={(e) =>
                                  updateRow(r.key, { party_size: Math.max(1, Number(e.target.value)) })
                                }
                              />
                            </td>
                            <td>
                              {badges.map((b) => (
                                <span
                                  key={b}
                                  className={`warn-badge ${b === t.rowIssueNoName ? 'warn-block' : ''}`}
                                >
                                  {b}
                                </span>
                              ))}
                            </td>
                            <td>
                              <button
                                type="button"
                                className="btn-link"
                                onClick={() => removeRow(r.key)}
                              >
                                {t.deleteRow}
                              </button>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            {error && <p className="form-error">{error}</p>}

            <div className="add-actions">
              <button
                className="btn-primary"
                onClick={doImport}
                disabled={committing || includedReady.length === 0}
              >
                {committing ? t.importing : t.importCount(includedReady.length)}
              </button>
              <button
                className="btn-ghost"
                onClick={() => {
                  setRows([])
                  setError('')
                  setStage('intro')
                }}
              >
                {t.backToPick}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
