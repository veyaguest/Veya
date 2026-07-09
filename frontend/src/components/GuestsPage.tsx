import { useCallback, useEffect, useRef, useState } from 'react'
import { deleteGuest, listGuests } from '../api'
import type { Guest } from '../types'
import { GROUP_LABELS, RSVP_LABELS, SIDE_LABELS } from '../types'
import { AddGuestForm } from './AddGuestForm'
import { ImportDialog } from './ImportDialog'

export function GuestsPage() {
  const [guests, setGuests] = useState<Guest[]>([])
  const [search, setSearch] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [importFile, setImportFile] = useState<File | null>(null)
  const [toast, setToast] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)

  const load = useCallback(async (q: string) => {
    setLoading(true)
    setError('')
    try {
      setGuests(await listGuests(q))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בטעינה')
    } finally {
      setLoading(false)
    }
  }, [])

  // טעינה ראשונית + חיפוש עם השהיה קלה (debounce)
  useEffect(() => {
    const t = setTimeout(() => load(search), 250)
    return () => clearTimeout(t)
  }, [search, load])

  async function onDelete(g: Guest) {
    if (!confirm(`למחוק את "${g.full_name}"?`)) return
    try {
      await deleteGuest(g.id)
      load(search)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'שגיאה במחיקה')
    }
  }

  const totalPeople = guests.reduce((sum, g) => sum + g.party_size, 0)

  return (
    <div className="guests-page">
      <div className="toolbar">
        <input
          className="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="חיפוש לפי שם או טלפון…"
        />
        <button className="btn-ghost" onClick={() => fileInput.current?.click()}>
          ⬆ ייבוא Excel/CSV
        </button>
        <button className="btn-primary" onClick={() => setShowForm((s) => !s)}>
          {showForm ? 'סגור טופס' : '+ הוסף מוזמן'}
        </button>
        <input
          ref={fileInput}
          type="file"
          accept=".xlsx,.xlsm,.csv"
          style={{ display: 'none' }}
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) setImportFile(f)
            e.target.value = '' // מאפשר לבחור שוב את אותו קובץ
          }}
        />
      </div>

      {toast && <div className="toast">{toast}</div>}

      {importFile && (
        <ImportDialog
          file={importFile}
          onClose={() => setImportFile(null)}
          onImported={(created) => {
            setImportFile(null)
            setToast(`יובאו ${created} מוזמנים בהצלחה ✓`)
            setTimeout(() => setToast(''), 4000)
            load(search)
          }}
        />
      )}

      {showForm && (
        <AddGuestForm
          onAdded={() => {
            setShowForm(false)
            load(search)
          }}
          onCancel={() => setShowForm(false)}
        />
      )}

      <div className="summary">
        {guests.length} מוזמנים · {totalPeople} אנשים בסך הכל
      </div>

      {error && <p className="form-error">{error}</p>}

      <div className="table-wrap">
        <table className="guests-table">
          <thead>
            <tr>
              <th>שם מלא</th>
              <th>טלפון</th>
              <th>צד</th>
              <th>קבוצה</th>
              <th>כמות</th>
              <th>סטטוס</th>
              <th>שולחן</th>
              <th>הערות</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {guests.map((g) => (
              <tr key={g.id}>
                <td>{g.full_name}</td>
                <td dir="ltr" className="phone">
                  {g.phone}
                </td>
                <td>{SIDE_LABELS[g.side]}</td>
                <td>{GROUP_LABELS[g.group_type]}</td>
                <td className="center">{g.party_size}</td>
                <td>
                  <span className={`badge ${g.rsvp_status}`}>
                    {RSVP_LABELS[g.rsvp_status]}
                  </span>
                </td>
                <td className="center">{g.table_number ?? '—'}</td>
                <td className="notes">{g.notes_raw ?? ''}</td>
                <td>
                  <button className="btn-delete" onClick={() => onDelete(g)}>
                    מחק
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {!loading && guests.length === 0 && (
          <div className="empty">
            {search
              ? 'לא נמצאו מוזמנים התואמים לחיפוש.'
              : 'עדיין אין מוזמנים. לחץ "הוסף מוזמן" כדי להתחיל.'}
          </div>
        )}
        {loading && <div className="empty">טוען…</div>}
      </div>
    </div>
  )
}
