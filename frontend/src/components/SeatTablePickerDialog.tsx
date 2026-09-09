/**
 * בחירת שולחן למוזמן — המסלול שאינו גרירה.
 *
 * דרישת נגישות מפורשת (§24): גרירה לא יכולה להיות הדרך היחידה להושיב.
 * הדיאלוג הזה הוא החלופה המלאה — עובד במקלדת, במגע ובעכבר, ומגיע בסוף
 * לאותה פונקציית הושבה של המפה (`requestSeatGuest` ב-HallPage), כולל
 * אותה אזהרה למי שלא אישר הגעה.
 *
 * שולחן מלא **אינו חסום** — זו ההתנהגות הקיימת והמוצהרת של המערכת
 * ("מתריעה, לא חוסמת" — ראו `backend/app/routers/hall.py`). הוא מסומן
 * בטקסט מפורש, לא רק בצבע.
 */
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { tableOccupancy } from '../seatingWorkspace'
import type { WorkspaceTable } from '../seatingWorkspace'
import { strings } from '../strings/he'
import './SeatingWorkspace.css'

const t = strings.hall.workspace

interface Props {
  guestName: string
  /** כמה מקומות המוזמן תופס — כדי להראות אם הוא "נכנס" בשולחן. */
  guestSeats: number
  currentTable: number | null
  tables: WorkspaceTable[]
  onPick: (tableNumber: number) => void
  onClose: () => void
}

export function SeatTablePickerDialog({
  guestName,
  guestSeats,
  currentTable,
  tables,
  onPick,
  onClose,
}: Props) {
  const [query, setQuery] = useState('')
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const listRef = useRef<HTMLDivElement | null>(null)
  // האלמנט שפתח את הדיאלוג — הפוקוס חוזר אליו בסגירה (§26).
  const openerRef = useRef<Element | null>(null)
  const titleId = useId()

  useEffect(() => {
    openerRef.current = document.activeElement
    // החיפוש קודם לכפתור הסגירה: מי שנכנס לכאן רוצה למצוא שולחן, לא
    // לצאת. ``querySelector('input, button')`` היה מחזיר את ה-✕ כי הוא
    // קודם ב-DOM.
    const first =
      dialogRef.current?.querySelector<HTMLElement>('input') ??
      dialogRef.current?.querySelector<HTMLElement>('button')
    first?.focus()
    return () => {
      const opener = openerRef.current
      if (opener instanceof HTMLElement && document.contains(opener)) opener.focus()
    }
  }, [])

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase()
    return [...tables]
      .sort((a, b) => a.table_number - b.table_number)
      .filter((table) => {
        if (!q) return true
        if (String(table.table_number).includes(q)) return true
        return (table.name ?? '').toLowerCase().includes(q)
      })
  }, [tables, query])

  /** ניווט בחצים בין השולחנות — מהיר יותר מ-Tab ברשימה ארוכה (§23). */
  function onListKeyDown(e: React.KeyboardEvent) {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    const buttons = Array.from(
      listRef.current?.querySelectorAll<HTMLButtonElement>('button.ws-pick-row') ?? [],
    )
    if (buttons.length === 0) return
    const idx = buttons.indexOf(document.activeElement as HTMLButtonElement)
    e.preventDefault()
    const next =
      e.key === 'ArrowDown'
        ? buttons[Math.min(buttons.length - 1, idx + 1)] ?? buttons[0]
        : buttons[Math.max(0, idx - 1)] ?? buttons[0]
    next.focus()
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onClose()
      return
    }
    if (e.key !== 'Tab') return
    const focusables = dialogRef.current?.querySelectorAll<HTMLElement>(
      'input, button:not([disabled])',
    )
    if (!focusables || focusables.length === 0) return
    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }

  return (
    <>
      <div className="ws-dialog-backdrop" onClick={onClose} />
      <div
        className="ws-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={dialogRef}
        onKeyDown={onKeyDown}
      >
        <div className="ws-dialog-head">
          <h2 className="ws-dialog-title" id={titleId}>
            {t.pickerTitle(guestName)}
          </h2>
          <button
            type="button"
            className="ws-dialog-x"
            onClick={onClose}
            aria-label={t.pickerCancel}
          >
            ×
          </button>
        </div>

        {tables.length === 0 ? (
          <p className="ws-dialog-empty">{t.pickerNoTables}</p>
        ) : (
          <>
            <input
              type="search"
              className="ws-search-input ws-dialog-search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t.pickerSearch}
              aria-label={t.pickerSearch}
            />

            <div className="ws-pick-list" ref={listRef} onKeyDown={onListKeyDown}>
              {rows.length === 0 && <p className="ws-dialog-empty">{t.pickerEmpty}</p>}
              {rows.map((table) => {
                const { used, free, full } = tableOccupancy(table)
                const isCurrent = table.table_number === currentTable
                const wontFit = free < guestSeats
                return (
                  <button
                    key={table.table_number}
                    type="button"
                    className={`ws-pick-row${full ? ' is-full' : ''}${
                      isCurrent ? ' is-current' : ''
                    }`}
                    // הכול בטקסט — קורא מסך מקבל את אותו מידע כמו העין (§28).
                    aria-label={`${t.seatedAt(table.table_number)}${
                      table.name ? `, ${table.name}` : ''
                    }, ${t.pickerOccupancy(used, table.capacity)}, ${
                      full ? t.pickerFull : t.pickerFree(free)
                    }${isCurrent ? `, ${t.pickerCurrent}` : ''}`}
                    onClick={() => onPick(table.table_number)}
                  >
                    <span className="ws-pick-main">
                      <span className="ws-pick-title">
                        {t.seatedAt(table.table_number)}
                        {table.name ? ` · ${table.name}` : ''}
                      </span>
                      <span className="ws-pick-sub">
                        {t.pickerOccupancy(used, table.capacity)}
                      </span>
                    </span>
                    <span className="ws-pick-side">
                      <span className={`ws-pick-free${full || wontFit ? ' is-full' : ''}`}>
                        {full ? t.pickerFull : t.pickerFree(free)}
                      </span>
                      {isCurrent && <span className="ws-pick-current">{t.pickerCurrent}</span>}
                    </span>
                  </button>
                )
              })}
            </div>
            <p className="ws-dialog-foot">{t.pickerFullHint}</p>
          </>
        )}
      </div>
    </>
  )
}
