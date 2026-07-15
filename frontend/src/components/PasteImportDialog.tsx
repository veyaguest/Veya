import { useState } from 'react'
import { commitImport, pasteImportPreview } from '../api'
import type { GroupType, GuestCreate, Side } from '../types'
import { GROUP_LABELS, SIDE_LABELS } from '../types'

interface Props {
  onClose: () => void
  onImported: (created: number, skippedDuplicates: number) => void
}

// שורה בתצוגה המקדימה הניתנת לעריכה — עותק עבודה מקומי שהמשתמש יכול לשנות.
interface EditRow {
  key: number
  full_name: string
  phone: string
  side: Side
  group_type: GroupType
  party_size: number
  duplicate: boolean
  include: boolean
}

/** נרמול טלפון ישראלי בצד הלקוח — תואם ללוגיקת השרת. מחזיר null אם לא תקין. */
function normalizePhone(raw: string): string | null {
  let d = (raw || '').replace(/\D/g, '')
  if (d.startsWith('972')) d = '0' + d.slice(3)
  if (!d.startsWith('0')) return null
  if (d.length !== 9 && d.length !== 10) return null
  return d
}

// תגי אזהרה מחושבים חי לפי הערכים הנוכחיים (כדי שיתעדכנו תוך כדי עריכה).
function rowIssues(r: EditRow): { canImport: boolean; badges: string[] } {
  const badges: string[] = []
  const hasName = r.full_name.trim().length > 0
  const phoneOk = normalizePhone(r.phone) !== null
  if (!hasName) badges.push('חסר שם')
  if (!r.phone.trim()) badges.push('חסר טלפון')
  else if (!phoneOk) badges.push('טלפון לא תקין')
  if (r.duplicate) badges.push('כפילות')
  return { canImport: hasName && phoneOk, badges }
}

export function PasteImportDialog({ onClose, onImported }: Props) {
  const [text, setText] = useState('')
  const [rows, setRows] = useState<EditRow[] | null>(null)
  const [error, setError] = useState('')
  const [parsing, setParsing] = useState(false)
  const [committing, setCommitting] = useState(false)

  async function doParse() {
    setError('')
    setParsing(true)
    try {
      const preview = await pasteImportPreview(text)
      const edit: EditRow[] = preview.rows.map((r, i) => {
        const dup = r.duplicate ?? false
        return {
          key: i,
          full_name: r.full_name,
          phone: r.phone,
          side: r.side,
          group_type: r.group_type,
          party_size: r.party_size,
          duplicate: dup,
          // ברירת מחדל: מסמנים לייבוא רק שורות תקינות שאינן כפילות.
          include: r.valid && normalizePhone(r.phone) !== null && !dup,
        }
      })
      setRows(edit)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'לא הצלחנו לפענח את הרשימה. נסו שוב.',
      )
    } finally {
      setParsing(false)
    }
  }

  function updateRow(key: number, patch: Partial<EditRow>) {
    setRows((prev) =>
      prev
        ? prev.map((r) => {
            if (r.key !== key) return r
            const next = { ...r, ...patch }
            // בחירה אוטומטית: אם השורה נעשתה תקינה לייבוא (למשל אחרי הוספת
            // טלפון תקין) וזו אינה כפילות — מסמנים אותה אוטומטית, כדי שלא צריך
            // גם להקליד טלפון וגם לסמן את התיבה ידנית.
            if (
              !rowIssues(r).canImport &&
              rowIssues(next).canImport &&
              !next.duplicate
            ) {
              next.include = true
            }
            return next
          })
        : prev,
    )
  }

  const includedReady = rows
    ? rows.filter((r) => r.include && rowIssues(r).canImport)
    : []

  // מספר השורות שאפשר לסמן לייבוא (יש שם וטלפון תקין, ואינן כפילות).
  const selectableCount = rows
    ? rows.filter((r) => rowIssues(r).canImport && !r.duplicate).length
    : 0

  // סימון כל השורות התקינות בבת אחת — כדי לא לסמן אחת-אחת ברשימה ארוכה.
  function selectAll() {
    setRows((prev) =>
      prev
        ? prev.map((r) =>
            rowIssues(r).canImport && !r.duplicate ? { ...r, include: true } : r,
          )
        : prev,
    )
  }

  // ניקוי כל הבחירות.
  function clearAll() {
    setRows((prev) =>
      prev ? prev.map((r) => ({ ...r, include: false })) : prev,
    )
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
      setError(err instanceof Error ? err.message : 'לא הצלחנו להוסיף את הרשימה, נסו שוב')
      setCommitting(false)
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog paste-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="dialog-head">
          <h2>הדבקת רשימת מוזמנים</h2>
          <button className="x" onClick={onClose}>
            ✕
          </button>
        </div>

        {!rows && (
          <>
            <p className="paste-hint">
              הדביקו כאן רשימה מ-WhatsApp, מאקסל או מכל מקום — שורה לכל מוזמן.
              אנחנו נזהה לבד את השם, הטלפון וכמות האנשים.
            </p>
            <textarea
              className="paste-area"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={
                'לדוגמה:\nיוסי כהן 052-1234567\nמשפחת לוי 5 אנשים 050-123-4567\nדנה מזרחי 054 987 6543 (2)'
              }
              dir="rtl"
              autoFocus
            />
            {error && <p className="form-error">{error}</p>}
            <div className="add-actions">
              <button
                className="btn-primary"
                onClick={doParse}
                disabled={parsing || text.trim().length === 0}
              >
                {parsing ? 'מפענח…' : 'פענוח הרשימה'}
              </button>
              <button className="btn-ghost" onClick={onClose}>
                ביטול
              </button>
            </div>
          </>
        )}

        {rows && (
          <>
            <p className="paste-hint">
              הכנו עבורכם את הרשימה. מומלץ לעבור ולוודא שאין טעויות בשם, בטלפון
              או בכמות. סמנו אילו שורות לייבא.
            </p>
            <div className="import-summary">
              <span>
                נבחרו לייבוא{' '}
                <strong className="ok-text">{includedReady.length}</strong> מתוך{' '}
                {rows.length} שורות
              </span>
              <span className="select-actions">
                <button
                  type="button"
                  className="btn-link"
                  onClick={selectAll}
                  disabled={selectableCount === 0}
                >
                  סמן הכל
                </button>
                <button
                  type="button"
                  className="btn-link"
                  onClick={clearAll}
                  disabled={includedReady.length === 0}
                >
                  נקה בחירה
                </button>
              </span>
            </div>

            <div className="preview-wrap">
              <table className="guests-table paste-table">
                <thead>
                  <tr>
                    <th className="center">ייבוא</th>
                    <th>שם מלא</th>
                    <th>טלפון</th>
                    <th>צד</th>
                    <th>קבוצה</th>
                    <th className="center">כמות</th>
                    <th>הערות</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const { canImport, badges } = rowIssues(r)
                    return (
                      <tr
                        key={r.key}
                        className={r.include ? '' : 'row-excluded'}
                      >
                        <td className="center">
                          <input
                            type="checkbox"
                            checked={r.include}
                            disabled={!canImport}
                            onChange={(e) =>
                              updateRow(r.key, { include: e.target.checked })
                            }
                          />
                        </td>
                        <td>
                          <input
                            className="cell-input"
                            value={r.full_name}
                            onChange={(e) =>
                              updateRow(r.key, { full_name: e.target.value })
                            }
                          />
                        </td>
                        <td>
                          <input
                            className="cell-input phone"
                            dir="ltr"
                            value={r.phone}
                            onChange={(e) =>
                              updateRow(r.key, { phone: e.target.value })
                            }
                          />
                        </td>
                        <td>
                          <select
                            className="cell-input"
                            value={r.side}
                            onChange={(e) =>
                              updateRow(r.key, { side: e.target.value as Side })
                            }
                          >
                            {Object.entries(SIDE_LABELS).map(([v, l]) => (
                              <option key={v} value={v}>
                                {l}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td>
                          <select
                            className="cell-input"
                            value={
                              r.group_type in GROUP_LABELS
                                ? r.group_type
                                : 'other'
                            }
                            onChange={(e) =>
                              updateRow(r.key, {
                                group_type: e.target.value as GroupType,
                              })
                            }
                          >
                            {Object.entries(GROUP_LABELS).map(([v, l]) => (
                              <option key={v} value={v}>
                                {l}
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
                              updateRow(r.key, {
                                party_size: Math.max(1, Number(e.target.value)),
                              })
                            }
                          />
                        </td>
                        <td>
                          {badges.map((b) => (
                            <span
                              key={b}
                              className={`warn-badge ${
                                b === 'חסר שם' ? 'warn-block' : ''
                              }`}
                            >
                              {b}
                            </span>
                          ))}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            {error && <p className="form-error">{error}</p>}

            <div className="add-actions">
              <button
                className="btn-primary"
                onClick={doImport}
                disabled={committing || includedReady.length === 0}
              >
                {committing
                  ? 'מייבא…'
                  : `ייבוא ${includedReady.length} מוזמנים`}
              </button>
              <button
                className="btn-ghost"
                onClick={() => {
                  setRows(null)
                  setError('')
                }}
              >
                חזרה לעריכת הטקסט
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
