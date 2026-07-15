import { useCallback, useEffect, useRef, useState } from 'react'
import { deleteGuest, listGuests } from '../api'
import type { Guest } from '../types'
import { groupLabel, RSVP_LABELS, SIDE_LABELS } from '../types'
import { AddGuestForm } from './AddGuestForm'
import { GroupNotesPanel } from './GroupNotesPanel'
import { GroupSuggestions } from './GroupSuggestions'
import { ImportDialog } from './ImportDialog'
import { OnboardingDialog } from './OnboardingDialog'
import { PasteImportDialog } from './PasteImportDialog'

// דגל localStorage — מסך הפתיחה מוצג פעם אחת בלבד.
const ONBOARDING_KEY = 'veya_guests_onboarding_seen'

const PAGE_SIZE = 50

export function GuestsPage() {
  const [guests, setGuests] = useState<Guest[]>([])
  const [total, setTotal] = useState(0)
  const [totalPeople, setTotalPeople] = useState(0)
  const [confirmedPeople, setConfirmedPeople] = useState(0)
  const [search, setSearch] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [importFile, setImportFile] = useState<File | null>(null)
  const [showPaste, setShowPaste] = useState(false)
  const [showNotes, setShowNotes] = useState(false)
  const [showOnboarding, setShowOnboarding] = useState(
    () => localStorage.getItem(ONBOARDING_KEY) !== '1',
  )
  const [toast, setToast] = useState('')
  // עולה בכל טעינה מוצלחת — מפעיל טעינה מחדש של הצעות הקבוצה החכמות.
  const [refreshTick, setRefreshTick] = useState(0)
  const fileInput = useRef<HTMLInputElement>(null)

  // טעינת העמוד הראשון (וגם רענון אחרי שינוי/חיפוש).
  const load = useCallback(async (q: string) => {
    setLoading(true)
    setError('')
    try {
      const page = await listGuests(q, PAGE_SIZE, 0)
      setGuests(page.items)
      setTotal(page.total)
      setTotalPeople(page.total_people)
      setConfirmedPeople(page.confirmed_people)
      setRefreshTick((t) => t + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לטעון את הרשימה, ננסה שוב')
    } finally {
      setLoading(false)
    }
  }, [])

  // טעינת עוד עמוד (מוסיף לרשימה הקיימת).
  async function loadMore() {
    setLoadingMore(true)
    try {
      const page = await listGuests(search, PAGE_SIZE, guests.length)
      setGuests((prev) => [...prev, ...page.items])
      setTotal(page.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לטעון את הרשימה, ננסה שוב')
    } finally {
      setLoadingMore(false)
    }
  }

  // טעינה ראשונית + חיפוש עם השהיה קלה (debounce)
  useEffect(() => {
    const t = setTimeout(() => load(search), 250)
    return () => clearTimeout(t)
  }, [search, load])

  async function onDelete(g: Guest) {
    if (!confirm(`להסיר את ${g.full_name} מהרשימה?`)) return
    try {
      await deleteGuest(g.id)
      load(search)
    } catch (err) {
      alert(err instanceof Error ? err.message : 'לא הצלחנו להסיר, נסו שוב')
    }
  }

  const hasMore = guests.length < total

  return (
    <div className="guests-page">
      <div className="toolbar">
        <input
          className="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="חיפוש לפי שם או טלפון…"
        />
        <button className="btn-ghost" onClick={() => setShowPaste(true)}>
          📋 הדבקת רשימה
        </button>
        <button className="btn-ghost" onClick={() => setShowNotes(true)}>
          ⭐ העדפות קבוצה
        </button>
        <button className="btn-ghost" onClick={() => fileInput.current?.click()}>
          ⬆ העלאת קובץ אקסל
        </button>
        <button className="btn-primary" onClick={() => setShowForm((s) => !s)}>
          {showForm ? 'סגירת הטופס' : '+ הוספת מוזמן'}
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
          onImported={(created, skippedDuplicates) => {
            setImportFile(null)
            const dup =
              skippedDuplicates > 0
                ? ` (${skippedDuplicates} כבר היו אצלכם)`
                : ''
            setToast(`הוספנו ${created} מוזמנים לרשימה ✓${dup}`)
            setTimeout(() => setToast(''), 4000)
            load(search)
          }}
        />
      )}

      {showPaste && (
        <PasteImportDialog
          onClose={() => setShowPaste(false)}
          onImported={(created, skippedDuplicates) => {
            setShowPaste(false)
            const dup =
              skippedDuplicates > 0
                ? ` (${skippedDuplicates} כבר היו אצלכם)`
                : ''
            setToast(`הוספנו ${created} מוזמנים לרשימה ✓${dup}`)
            setTimeout(() => setToast(''), 4000)
            load(search)
          }}
        />
      )}

      {showOnboarding && (
        <OnboardingDialog
          onClose={() => {
            localStorage.setItem(ONBOARDING_KEY, '1')
            setShowOnboarding(false)
          }}
        />
      )}

      {showNotes && <GroupNotesPanel onClose={() => setShowNotes(false)} />}

      {showForm && (
        <AddGuestForm
          onAdded={() => {
            setShowForm(false)
            load(search)
          }}
          onCancel={() => setShowForm(false)}
        />
      )}

      <GroupSuggestions
        refreshToken={refreshTick}
        onApplied={(message) => {
          setToast(message)
          setTimeout(() => setToast(''), 4000)
          load(search)
        }}
      />

      <div className="summary">
        {total} מוזמנים · {totalPeople} אנשים הוזמנו ·{' '}
        {confirmedPeople} אישרו הגעה
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
              <th>אישור הגעה</th>
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
                <td>{groupLabel(g.group_type)}</td>
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
                    מחיקה
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {!loading && guests.length === 0 && (
          <div className="empty">
            {search
              ? 'לא נמצאו מוזמנים שתואמים לחיפוש.'
              : 'הרשימה עדיין ריקה. הוסיפו מוזמן ראשון או ייבאו קובץ אקסל כדי להתחיל.'}
          </div>
        )}
        {loading && <div className="empty">טוען…</div>}
      </div>

      {!loading && hasMore && (
        <div className="load-more-wrap">
          <button
            className="btn-ghost"
            onClick={loadMore}
            disabled={loadingMore}
          >
            {loadingMore
              ? 'טוען…'
              : `טעינת עוד (${guests.length} מתוך ${total})`}
          </button>
        </div>
      )}
    </div>
  )
}
