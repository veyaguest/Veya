import { useCallback, useEffect, useRef, useState } from 'react'
import {
  applyNoteSplit,
  deleteGuest,
  getNoteSplitSuggestions,
  guestDataAlerts,
  listGuests,
} from '../api'
import type { GuestFilter, GuestSort } from '../api'
import type { Guest, GuestDataAlert, NoteSplitCandidate } from '../types'
import { groupLabel, INVITE_STATUS_LABELS, RSVP_LABELS } from '../types'
import { activeEventTerms, sideLabel } from '../strings/eventTypes'
import { strings } from '../strings/he'
import { AddGuestForm } from './AddGuestForm'
import { ConfirmDialog } from './ConfirmDialog'
import { ContactsImportDialog, isContactPickerSupported } from './ContactsImportDialog'
import { CreateGroupDialog } from './CreateGroupDialog'
import { GroupNotesPanel } from './GroupNotesPanel'
import { GroupSuggestions } from './GroupSuggestions'
import { ImportDialog } from './ImportDialog'
import { ImportMenu } from './ImportMenu'
import { OnboardingDialog } from './OnboardingDialog'
import { PasteImportDialog } from './PasteImportDialog'
import './GuestDataAlert.css'

// נבדק פעם אחת בטעינת המודול — תמיכת הדפדפן בבחירת אנשי קשר לא משתנה תוך כדי שימוש.
const contactsSupported = isContactPickerSupported()

const t = strings.guests

// דגל localStorage — מסך הפתיחה מוצג פעם אחת בלבד.
const ONBOARDING_KEY = 'veya_guests_onboarding_seen'

const PAGE_SIZE = 50

const FILTER_LABELS: Record<GuestFilter, string> = {
  all: t.filterLabelAll,
  confirmed: t.filterLabelConfirmed,
  declined: t.filterLabelDeclined,
  maybe: t.filterLabelMaybe,
  pending: t.filterLabelPending,
  no_table: t.filterLabelNoTable,
}

export function GuestsPage() {
  const [guests, setGuests] = useState<Guest[]>([])
  const [total, setTotal] = useState(0)
  const [totalPeople, setTotalPeople] = useState(0)
  const [confirmedPeople, setConfirmedPeople] = useState(0)
  const [search, setSearch] = useState('')
  // מיון/סינון תצוגתיים בלבד — לא נשמרים ל-localStorage, כך שרענון דף
  // מחזיר אוטומטית לברירת המחדל (א-ב, כל המוזמנים).
  const [sort, setSort] = useState<GuestSort>('name')
  const [filterStatus, setFilterStatus] = useState<GuestFilter>('all')
  const [showForm, setShowForm] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [importFile, setImportFile] = useState<File | null>(null)
  const [showPaste, setShowPaste] = useState(false)
  const [showContacts, setShowContacts] = useState(false)
  // הערות פנימיות שנראות כמו העדפות ישיבה, אצל מוזמנים ששדה ההושבה שלהם ריק.
  // המערכת לא מעבירה אותן בעצמה — רק מציעה, וההחלטה של המשתמש.
  const [noteSplit, setNoteSplit] = useState<NoteSplitCandidate[]>([])
  const [noteSplitOpen, setNoteSplitOpen] = useState(false)
  const [noteSplitBusy, setNoteSplitBusy] = useState(false)
  const [noteSplitHidden, setNoteSplitHidden] = useState(false)
  const [showNotes, setShowNotes] = useState(false)
  const [showCreateGroup, setShowCreateGroup] = useState(false)
  const [editGuest, setEditGuest] = useState<Guest | null>(null)
  // מוזמנים שמספר הטלפון שלהם נמצא שגוי בשיחה — דורש תיקון של בעל/ת האירוע.
  const [phoneAlerts, setPhoneAlerts] = useState<GuestDataAlert[]>([])
  const [showOnboarding, setShowOnboarding] = useState(
    () => localStorage.getItem(ONBOARDING_KEY) !== '1',
  )
  const [toast, setToast] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<Guest | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)
  // עולה בכל טעינה מוצלחת — מפעיל טעינה מחדש של הצעות הקבוצה החכמות.
  const [refreshTick, setRefreshTick] = useState(0)
  // אזור "הצעות לאיחוד" נפתח רק לפי דרישה — לא אוטומטית בכניסה לעמוד.
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [suggestionsCount, setSuggestionsCount] = useState(0)
  const fileInput = useRef<HTMLInputElement>(null)

  // טעינת העמוד הראשון (וגם רענון אחרי שינוי/חיפוש).
  const load = useCallback(async (q: string) => {
    setLoading(true)
    setError('')
    try {
      const page = await listGuests(q, PAGE_SIZE, 0, sort, filterStatus)
      setGuests(page.items)
      setTotal(page.total)
      setTotalPeople(page.total_people)
      setConfirmedPeople(page.confirmed_people)
      setRefreshTick((t) => t + 1)
    } catch (err) {
      setError(err instanceof Error ? err.message : t.loadError)
    } finally {
      setLoading(false)
    }
  }, [sort, filterStatus])

  // טעינת עוד עמוד (מוסיף לרשימה הקיימת), באותו מיון/סינון פעיל.
  async function loadMore() {
    setLoadingMore(true)
    try {
      const page = await listGuests(search, PAGE_SIZE, guests.length, sort, filterStatus)
      setGuests((prev) => [...prev, ...page.items])
      setTotal(page.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : t.loadError)
    } finally {
      setLoadingMore(false)
    }
  }

  // טעינה ראשונית + חיפוש עם השהיה קלה (debounce) — גם על שינוי מיון/סינון.
  useEffect(() => {
    const t = setTimeout(() => load(search), 250)
    return () => clearTimeout(t)
  }, [search, load])

  // התראות איכות-דאטה (מספר טלפון שדווח כשגוי בשיחת טלפון של VEYA).
  // נטענות מחדש אחרי כל עריכת מוזמן, כך שההתראה נסגרת ברגע שהמספר תוקן.
  const loadDataAlerts = useCallback(async () => {
    try {
      const res = await guestDataAlerts()
      setPhoneAlerts(res.phone_fix)
    } catch {
      /* שקט — התראה, לא פעולה קריטית */
    }
  }, [])

  useEffect(() => {
    loadDataAlerts()
  }, [loadDataAlerts])

  // בדיקת "הערות שנראות כמו העדפות ישיבה" — פעם אחת בטעינה ואחרי כל העברה.
  const loadNoteSplit = useCallback(async () => {
    try {
      const res = await getNoteSplitSuggestions()
      setNoteSplit(res.candidates)
    } catch {
      /* שקט — זו הצעה, לא פעולה קריטית */
    }
  }, [])

  useEffect(() => {
    loadNoteSplit()
  }, [loadNoteSplit])

  async function onApplyNoteSplit() {
    setNoteSplitBusy(true)
    try {
      const res = await applyNoteSplit(noteSplit.map((c) => c.guest_id))
      setToast(t.noteSplitDone(res.moved))
      setTimeout(() => setToast(''), 4000)
      setNoteSplitOpen(false)
      await loadNoteSplit()
      await load(search)
    } catch {
      setToast(t.noteSplitError)
      setTimeout(() => setToast(''), 4000)
    } finally {
      setNoteSplitBusy(false)
    }
  }

  function onDelete(g: Guest) {
    setDeleteTarget(g)
  }

  async function confirmDelete() {
    if (!deleteTarget) return
    setDeleteBusy(true)
    try {
      await deleteGuest(deleteTarget.id)
      setDeleteTarget(null)
      load(search)
    } catch (err) {
      setToast(err instanceof Error ? err.message : t.deleteError)
      setTimeout(() => setToast(''), 4000)
    } finally {
      setDeleteBusy(false)
    }
  }

  const hasMore = guests.length < total

  /** פותח את עריכת המוזמן ישירות מתוך ההתראה, כדי לתקן את המספר במקום. */
  function openPhoneFix(alert: GuestDataAlert) {
    const inList = guests.find((g) => g.id === alert.guest_id)
    // המוזמן לא בהכרח בעמוד הנוכחי (חיפוש/סינון/דפדוף) — בונים ממנו רשומה
    // מינימלית כדי שהטופס ייפתח תמיד, גם כשהוא מחוץ לתצוגה.
    setEditGuest(
      inList ?? ({
        id: alert.guest_id,
        full_name: alert.full_name,
        phone: alert.phone,
        rsvp_status: alert.rsvp_status,
        side: 'shared',
        group_type: 'other',
        party_size: 1,
        notes_raw: null,
        seating_notes: null,
        table_number: null,
        is_child: false,
        invite_status: 'not_sent',
        created_at: alert.reported_at,
      } as Guest),
    )
  }

  return (
    <div className="guests-page">
      {phoneAlerts.length > 0 && (
        <section className="data-alert" role="status">
          <div className="data-alert-head">
            <span aria-hidden>⚠️</span>
            <strong>נדרש תיקון מספר טלפון</strong>
          </div>
          <ul className="data-alert-list">
            {phoneAlerts.map((a) => (
              <li key={a.guest_id}>
                <div className="data-alert-text">
                  ל{a.full_name} יש מספר טלפון שגוי (<span dir="ltr">{a.phone}</span>).
                  לא הצלחנו ליצור איתו קשר — יש לעדכן את המספר.
                </div>
                <button
                  type="button"
                  className="btn-primary data-alert-btn"
                  onClick={() => openPhoneFix(a)}
                >
                  תיקון מספר
                </button>
              </li>
            ))}
          </ul>
          <p className="data-alert-foot">
            אישור ההגעה של המוזמנים האלה לא השתנה — זו בעיה בפרטי הקשר בלבד.
          </p>
        </section>
      )}

      <div className="toolbar">
        <input
          className="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t.searchPlaceholder}
        />
        <select
          className="toolbar-select"
          aria-label={t.sortButton}
          value={sort}
          onChange={(e) => setSort(e.target.value as GuestSort)}
        >
          <option value="name">{t.sortButton}: {t.sortLabelName}</option>
          <option value="status">{t.sortButton}: {t.sortLabelStatus}</option>
          <option value="table">{t.sortButton}: {t.sortLabelTable}</option>
          <option value="party_size">{t.sortButton}: {t.sortLabelPartySize}</option>
          <option value="recent">{t.sortButton}: {t.sortLabelRecent}</option>
        </select>
        <select
          className="toolbar-select"
          aria-label={t.filterButton}
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value as GuestFilter)}
        >
          <option value="all">{t.filterButton}: {t.filterLabelAll}</option>
          <option value="confirmed">{t.filterButton}: {t.filterLabelConfirmed}</option>
          <option value="declined">{t.filterButton}: {t.filterLabelDeclined}</option>
          <option value="maybe">{t.filterButton}: {t.filterLabelMaybe}</option>
          <option value="pending">{t.filterButton}: {t.filterLabelPending}</option>
          <option value="no_table">{t.filterButton}: {t.filterLabelNoTable}</option>
        </select>
        <ImportMenu
          onExcel={() => fileInput.current?.click()}
          onPaste={() => setShowPaste(true)}
          onContacts={contactsSupported ? () => setShowContacts(true) : undefined}
        />
        <button className="btn-ghost" onClick={() => setShowCreateGroup(true)}>
          {t.groupButton}
        </button>
        <button className="btn-ghost" onClick={() => setShowNotes(true)}>
          {t.notesButton}
        </button>
        <button className="btn-ghost" onClick={() => setShowSuggestions(true)}>
          {t.suggestionsButton(suggestionsCount)}
        </button>
        <button className="btn-primary" onClick={() => setShowForm((s) => !s)}>
          {showForm ? t.closeForm : t.addGuestButton}
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

      {filterStatus !== 'all' && (
        <div className="filter-notice">
          <span>{t.filteredNotice(FILTER_LABELS[filterStatus])}</span>
          <button className="btn-text" onClick={() => setFilterStatus('all')}>
            {t.clearFilter}
          </button>
        </div>
      )}

      {toast && (
        <div className="toast">
          <span className="toast-brand" aria-hidden="true">
            <span className="auth-monogram">
              <span className="auth-monogram-diamond" />
              <span className="auth-monogram-v">V</span>
            </span>
          </span>
          <span className="toast-text">{toast}</span>
        </div>
      )}

      {/* הפרדת ההערות: שדה "הערות הושבה" מתחיל ריק בכוונה, כדי שהערה
          תפעולית לא תהפוך פתאום לאילוץ. כאן מציעים למשתמש להעביר את מה
          שכן נראה כמו העדפת ישיבה — בהחלטה מפורשת שלו. */}
      {noteSplit.length > 0 && !noteSplitHidden && (
        <div className="note-split-banner">
          <div className="note-split-head">
            <div>
              <p className="note-split-title">{t.noteSplitTitle(noteSplit.length)}</p>
              <p className="note-split-body">{t.noteSplitBody}</p>
            </div>
            <button
              className="btn-text"
              onClick={() => setNoteSplitOpen((v) => !v)}
            >
              {noteSplitOpen ? t.noteSplitHide : t.noteSplitPreview}
            </button>
          </div>
          {noteSplitOpen && (
            <ul className="note-split-list">
              {noteSplit.map((c) => (
                <li key={c.guest_id}>
                  <strong>{c.full_name}</strong> — {c.notes_raw}
                </li>
              ))}
            </ul>
          )}
          <div className="note-split-actions">
            <button
              className="btn-primary"
              disabled={noteSplitBusy}
              onClick={onApplyNoteSplit}
            >
              {t.noteSplitApply}
            </button>
            <button className="btn-text" onClick={() => setNoteSplitHidden(true)}>
              {t.noteSplitDismiss}
            </button>
          </div>
        </div>
      )}

      {deleteTarget && (
        <ConfirmDialog
          title={t.deleteTitle}
          message={t.deleteConfirm(deleteTarget.full_name)}
          confirmLabel={t.deleteConfirmButton}
          danger
          busy={deleteBusy}
          onConfirm={confirmDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}

      {importFile && (
        <ImportDialog
          file={importFile}
          onClose={() => setImportFile(null)}
          onImported={(created, skippedDuplicates) => {
            setImportFile(null)
            const dup = skippedDuplicates > 0 ? t.dupSuffix(skippedDuplicates) : ''
            setToast(t.importedToast(created, dup))
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
            const dup = skippedDuplicates > 0 ? t.dupSuffix(skippedDuplicates) : ''
            setToast(t.importedToast(created, dup))
            setTimeout(() => setToast(''), 4000)
            load(search)
          }}
        />
      )}

      {showContacts && (
        <ContactsImportDialog
          onClose={() => setShowContacts(false)}
          onImported={(created, skippedDuplicates) => {
            setShowContacts(false)
            const dup = skippedDuplicates > 0 ? t.dupSuffix(skippedDuplicates) : ''
            setToast(t.importedToast(created, dup))
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
          onPaste={() => setShowPaste(true)}
          onExcel={() => fileInput.current?.click()}
          onContacts={contactsSupported ? () => setShowContacts(true) : undefined}
          onManual={() => setShowForm(true)}
        />
      )}

      {showNotes && <GroupNotesPanel onClose={() => setShowNotes(false)} />}

      {showCreateGroup && (
        <CreateGroupDialog
          onClose={() => setShowCreateGroup(false)}
          onCreated={(message) => {
            setShowCreateGroup(false)
            setToast(message)
            setTimeout(() => setToast(''), 4000)
            load(search)
          }}
        />
      )}

      {editGuest && (
        <div className="overlay" onClick={() => setEditGuest(null)}>
          <div
            className="dialog edit-guest-dialog"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="dialog-head">
              <h2>{t.editRow}</h2>
              <button className="x" onClick={() => setEditGuest(null)}>
                ✕
              </button>
            </div>
            <AddGuestForm
              guest={editGuest}
              onAdded={() => {
                setEditGuest(null)
                load(search)
                // אם המספר תוקן — ההתראה נסגרת מעצמה בטעינה הזו.
                loadDataAlerts()
              }}
              onCancel={() => setEditGuest(null)}
            />
          </div>
        </div>
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

      <GroupSuggestions
        refreshToken={refreshTick}
        open={showSuggestions}
        onClose={() => setShowSuggestions(false)}
        onCountChange={setSuggestionsCount}
        onApplied={(message) => {
          setToast(message)
          setTimeout(() => setToast(''), 4000)
          load(search)
        }}
      />

      <div className="summary">
        {t.summary(total, totalPeople, confirmedPeople, activeEventTerms().guestsLabel)}
      </div>

      {error && <p className="form-error">{error}</p>}

      <div className="table-wrap">
        <table className="guests-table">
          <thead>
            <tr>
              <th>{t.colFullName}</th>
              <th>{t.colPhone}</th>
              <th>{t.colSide}</th>
              <th>{t.colGroup}</th>
              <th>{t.colCount}</th>
              <th>{t.colRsvp}</th>
              <th>{t.colInviteStatus}</th>
              <th>{t.colTable}</th>
              <th>{t.colSeatingNotes}</th>
              <th>{t.colNotes}</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {loading && guests.length === 0 &&
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={`sk-${i}`} className="skeleton-row" aria-hidden="true">
                  {Array.from({ length: 11 }).map((__, j) => (
                    <td key={j}><span className="skeleton-bar" /></td>
                  ))}
                </tr>
              ))}
            {guests.map((g) => (
              <tr key={g.id}>
                <td>{g.full_name}</td>
                <td dir="ltr" className="phone">
                  {g.phone}
                </td>
                <td>{sideLabel(g.side)}</td>
                <td>{groupLabel(g.group_type)}</td>
                <td className="center">{g.party_size}</td>
                <td>
                  <span className={`badge ${g.rsvp_status}`}>
                    {RSVP_LABELS[g.rsvp_status]}
                  </span>
                </td>
                <td>
                  <span className={`badge invite-${g.invite_status ?? 'not_sent'}`}>
                    {INVITE_STATUS_LABELS[g.invite_status ?? 'not_sent']}
                  </span>
                </td>
                <td className="center">{g.table_number ?? '—'}</td>
                <td className="notes seating">{g.seating_notes ?? ''}</td>
                <td className="notes">{g.notes_raw ?? ''}</td>
                <td className="row-actions">
                  <button className="btn-edit" onClick={() => setEditGuest(g)}>
                    {t.editRow}
                  </button>
                  <button className="btn-delete" onClick={() => onDelete(g)}>
                    {t.deleteRow}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {!loading && guests.length === 0 && (
          <div className="empty">
            {search ? t.emptySearch : t.emptyList}
          </div>
        )}
        {loading && <div className="empty">{t.loadingRows}</div>}
      </div>

      {!loading && hasMore && (
        <div className="load-more-wrap">
          <button
            className="btn-ghost"
            onClick={loadMore}
            disabled={loadingMore}
          >
            {loadingMore ? t.loadingRows : t.loadMore(guests.length, total)}
          </button>
        </div>
      )}
    </div>
  )
}
