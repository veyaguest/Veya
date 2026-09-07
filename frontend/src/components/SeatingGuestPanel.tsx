/**
 * סרגל המוזמנים של מרחב ההושבה — הצד שממנו מסדרים, לצד סקיצת האולם.
 *
 * הקומפוננטה **מציגה בלבד**: כל הנתונים והפעולות מגיעים ב-props מ-HallPage,
 * שהוא מקור האמת החי של מצב האולם (`tables` / `unassigned`). אין כאן קריאת
 * רשת, אין state של הושבה, ואין חישוב שיבוץ — הלוגיקה העסקית נשארת בשרת
 * ובמצב הקיים של המסך.
 *
 * שלוש דרכים להושיב מוזמן, וכולן מגיעות לאותה פונקציה ב-HallPage:
 *   1. גרירה אל שולחן במפה (עכבר).
 *   2. בחירת מוזמן → הקשה על שולחן במפה (מגע/עכבר).
 *   3. פעולות השורה → "הושבה לשולחן" → דיאלוג בחירת שולחן (מקלדת/מגע).
 * הגרירה היא **תוספת ולא תנאי** — כל פעולה אפשרית גם בלעדיה (§24).
 */
import {
  memo,
  useCallback,
  useDeferredValue,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { HallGuest } from '../types'
import { RSVP_LABELS } from '../types'
import {
  buildEntries,
  buildSections,
  EMPTY_FILTER,
  groupAriaLabel,
  groupsInUse,
  guestAriaLabel,
  isFilterActive,
  matchesFilter,
  matchesSearch,
  peopleOf,
  sectionAriaLabel,
  sortEntries,
} from '../seatingWorkspace'
import type {
  GuestEntry,
  WorkspaceFilter,
  WorkspaceSort,
  WorkspaceTable,
} from '../seatingWorkspace'
import { activeEventTerms } from '../strings/eventTypes'
import { strings } from '../strings/he'
import { SeatTablePickerDialog } from './SeatTablePickerDialog'
import './SeatingWorkspace.css'

const t = strings.hall.workspace

/** ה-MIME שבו נושאים את מזהה המוזמן בגרירה. */
export const GUEST_DRAG_TYPE = 'application/x-veya-guest'

export interface SeatingGuestPanelProps {
  tables: WorkspaceTable[]
  unassigned: HallGuest[]
  /** העדפות קבוצה (`getGroupNotes`) — מפתח = group_type. */
  groupNotes: Record<string, string>
  selectedGuestId: number | null
  onSelectGuest: (guestId: number | null) => void
  /** מושיב/מעביר מוזמן לשולחן — עובר דרך `requestSeatGuest` ב-HallPage. */
  onSeatGuest: (guestId: number, tableNumber: number) => void
  /** מסיר מהשולחן ומחזיר לרשימה. */
  onUnseatGuest: (guestId: number) => void
  /** ממקד את השולחן על המפה (בוחר אותו ומגלגל אליו). */
  onShowTable: (tableNumber: number) => void
  /** פותח את שכבת ניהול המוזמנים, אופציונלית עם חיפוש מוכן. */
  onManageGuests: (search?: string) => void
  /** מכריז לקורא מסך (aria-live) — מסופק ע"י HallPage. */
  onAnnounce: (message: string) => void
  /** מתחיל/מסיים גרירה — HallPage מדליק את יעדי השחרור על המפה. */
  onDragGuestChange: (guestId: number | null) => void
  /** סינון התחלתי — משמש את "הצגת מי שנשאר ללא שולחן" אחרי הושבה בקליק. */
  externalFilter?: WorkspaceFilter | null
  /** ה-CTA התחתון (הושבה בקליק והשלמה) — מרונדר ע"י HallPage. */
  footer?: React.ReactNode
}

// ---------------------------------------------------------------------------
// שורת מוזמן
// ---------------------------------------------------------------------------

interface GuestRowProps {
  entry: GuestEntry
  groupNote: string | undefined
  selected: boolean
  expanded: boolean
  onToggleActions: (guestId: number) => void
  onSelect: (guestId: number) => void
  onSeatRequest: (entry: GuestEntry) => void
  onUnseat: (guestId: number) => void
  onShowTable: (tableNumber: number) => void
  onEdit: (name: string) => void
  onDragStart: (guestId: number) => void
  onDragEnd: () => void
}

const GuestRow = memo(function GuestRow({
  entry,
  groupNote,
  selected,
  expanded,
  onToggleActions,
  onSelect,
  onSeatRequest,
  onUnseat,
  onShowTable,
  onEdit,
  onDragStart,
  onDragEnd,
}: GuestRowProps) {
  const g = entry.guest
  const seated = entry.tableNumber !== null
  const [notesOpen, setNotesOpen] = useState(false)
  const actionsRef = useRef<HTMLDivElement | null>(null)
  const rowRef = useRef<HTMLButtonElement | null>(null)
  const rowId = `ws-guest-${g.id}`
  const people = peopleOf(g)
  const hasNotes = !!(g.seating_notes || g.guest_note || groupNote)

  // כשאזור הפעולות נפתח — הפוקוס נכנס אליו, כדי שמשתמש מקלדת ימשיך
  // ברצף מהשורה אל הפעולה ולא יצטרך לחפש אותה.
  useEffect(() => {
    if (!expanded) return
    const first = actionsRef.current?.querySelector<HTMLButtonElement>('button')
    first?.focus()
  }, [expanded])

  function closeActions() {
    onToggleActions(g.id)
    rowRef.current?.focus()
  }

  return (
    <li
      className={`ws-guest${selected ? ' is-selected' : ''}${seated ? '' : ' is-unseated'}`}
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData(GUEST_DRAG_TYPE, String(g.id))
        e.dataTransfer.setData('text/plain', g.full_name)
        e.dataTransfer.effectAllowed = 'move'
        onDragStart(g.id)
      }}
      onDragEnd={onDragEnd}
    >
      <div className="ws-guest-main">
        <button
          type="button"
          ref={rowRef}
          id={rowId}
          className="ws-guest-btn"
          aria-expanded={expanded}
          aria-controls={`${rowId}-actions`}
          // הטקסט המלא לקורא מסך — שם, אישור הגעה, מצב הושבה, כמה אנשים.
          // הצבע והאייקון הם תוספת חזותית בלבד (§28).
          aria-label={guestAriaLabel(entry, t.notSeated, 'שולחן')}
          onClick={() => {
            onSelect(g.id)
            onToggleActions(g.id)
          }}
        >
          <span className="ws-guest-name">
            <span className="ws-guest-mark" aria-hidden="true">
              {seated ? '✓' : '○'}
            </span>
            {g.full_name}
          </span>
          <span className="ws-guest-meta">
            <span className={`ws-rsvp ws-rsvp-${g.rsvp_status}`}>
              {RSVP_LABELS[g.rsvp_status]}
            </span>
            {people > 1 && <span className="ws-guest-people">{t.peopleCount(people)}</span>}
            <span className={`ws-guest-seat${seated ? '' : ' is-empty'}`}>
              {seated ? t.seatedAt(entry.tableNumber as number) : t.notSeated}
            </span>
          </span>
        </button>

        {hasNotes && (
          <button
            type="button"
            className={`ws-note-btn${notesOpen ? ' is-open' : ''}`}
            aria-expanded={notesOpen}
            aria-controls={`${rowId}-notes`}
            aria-label={`${t.noteToggle} — ${g.full_name}`}
            onClick={() => setNotesOpen((v) => !v)}
          >
            <span aria-hidden="true">📝</span>
          </button>
        )}
      </div>

      {hasNotes && notesOpen && (
        <div className="ws-notes" id={`${rowId}-notes`}>
          {g.seating_notes && (
            <p className="ws-note">
              <span className="ws-note-title">{t.noteSeatingTitle}</span>
              {g.seating_notes}
            </p>
          )}
          {g.guest_note && (
            <p className="ws-note">
              <span className="ws-note-title">{t.noteGuestTitle}</span>
              {g.guest_note}
            </p>
          )}
          {groupNote && (
            <p className="ws-note">
              <span className="ws-note-title">{t.noteGroupTitle}</span>
              {groupNote}
            </p>
          )}
        </div>
      )}

      {/* אזור הפעולות — המסלול שאינו גרירה (§24, §25).
          Escape סוגר ומחזיר את הפוקוס לשורה עצמה. */}
      <div
        className="ws-actions"
        id={`${rowId}-actions`}
        ref={actionsRef}
        role="group"
        aria-label={t.actionsLabel(g.full_name)}
        hidden={!expanded}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            e.stopPropagation()
            closeActions()
          }
        }}
      >
        <button type="button" className="ws-action" onClick={() => onSeatRequest(entry)}>
          {seated ? t.actionMove : t.actionSeat}
        </button>
        {seated && (
          <>
            <button
              type="button"
              className="ws-action"
              onClick={() => onShowTable(entry.tableNumber as number)}
            >
              {t.actionShowOnMap}
            </button>
            <button type="button" className="ws-action" onClick={() => onUnseat(g.id)}>
              {t.actionUnseat}
            </button>
          </>
        )}
        <button type="button" className="ws-action" onClick={() => onEdit(g.full_name)}>
          {t.actionEdit}
        </button>
        <p className="ws-action-hint">{t.dragHint}</p>
      </div>
    </li>
  )
})

// ---------------------------------------------------------------------------
// חלונית הסינון
// ---------------------------------------------------------------------------

function FilterPopover({
  value,
  groups,
  guestsWord,
  onApply,
  onClose,
}: {
  value: WorkspaceFilter
  groups: { key: string; label: string }[]
  guestsWord: string
  onApply: (next: WorkspaceFilter) => void
  onClose: () => void
}) {
  const [draft, setDraft] = useState<WorkspaceFilter>(value)
  const ref = useRef<HTMLDivElement | null>(null)
  const titleId = useId()

  // מלכודת פוקוס פשוטה: Tab מסתובב בתוך החלונית, Escape סוגר (§26, §30).
  useEffect(() => {
    const first = ref.current?.querySelector<HTMLElement>(
      'input, select, button, [tabindex]:not([tabindex="-1"])',
    )
    first?.focus()
  }, [])

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onClose()
      return
    }
    if (e.key !== 'Tab') return
    const focusables = ref.current?.querySelectorAll<HTMLElement>(
      'input:not([disabled]), select, button:not([disabled])',
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

  const rsvpOptions: { key: WorkspaceFilter['rsvp']; label: string }[] = [
    { key: 'all', label: t.filterAll(guestsWord) },
    { key: 'confirmed', label: RSVP_LABELS.confirmed },
    { key: 'pending', label: RSVP_LABELS.pending },
    { key: 'maybe', label: RSVP_LABELS.maybe },
    { key: 'declined', label: RSVP_LABELS.declined },
  ]
  const seatingOptions: { key: WorkspaceFilter['seating']; label: string }[] = [
    { key: 'all', label: t.filterSeatedAll },
    { key: 'seated', label: t.filterSeated },
    { key: 'unseated', label: t.filterUnseated },
  ]

  return (
    <>
      <div className="ws-popover-backdrop" onClick={onClose} />
      <div
        className="ws-popover"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        ref={ref}
        onKeyDown={onKeyDown}
      >
        <h2 className="ws-popover-title" id={titleId}>
          {t.filterTitle(guestsWord)}
        </h2>

        <fieldset className="ws-fieldset">
          <legend>{t.filterRsvpTitle}</legend>
          {rsvpOptions.map((o) => (
            <label key={o.key} className="ws-radio">
              <input
                type="radio"
                name="ws-filter-rsvp"
                checked={draft.rsvp === o.key}
                onChange={() => setDraft({ ...draft, rsvp: o.key })}
              />
              <span>{o.label}</span>
            </label>
          ))}
        </fieldset>

        <fieldset className="ws-fieldset">
          <legend>{t.filterSeatingTitle}</legend>
          {seatingOptions.map((o) => (
            <label key={o.key} className="ws-radio">
              <input
                type="radio"
                name="ws-filter-seating"
                checked={draft.seating === o.key}
                onChange={() => setDraft({ ...draft, seating: o.key })}
              />
              <span>{o.label}</span>
            </label>
          ))}
        </fieldset>

        {groups.length > 0 && (
          <div className="ws-field">
            <label className="ws-field-label" htmlFor={`${titleId}-group`}>
              {t.filterGroupTitle}
            </label>
            <select
              id={`${titleId}-group`}
              className="ws-select"
              value={draft.group}
              onChange={(e) => setDraft({ ...draft, group: e.target.value })}
            >
              <option value="all">{t.filterAllGroups}</option>
              {groups.map((g) => (
                <option key={g.key} value={g.key}>
                  {g.label}
                </option>
              ))}
            </select>
          </div>
        )}

        <div className="ws-popover-actions">
          <button type="button" className="ws-btn-primary" onClick={() => onApply(draft)}>
            {t.filterApply}
          </button>
          <button
            type="button"
            className="ws-btn-ghost"
            onClick={() => onApply({ ...EMPTY_FILTER })}
          >
            {t.filterReset}
          </button>
        </div>
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// הסרגל עצמו
// ---------------------------------------------------------------------------

export const SeatingGuestPanel = memo(function SeatingGuestPanel({
  tables,
  unassigned,
  groupNotes,
  selectedGuestId,
  onSelectGuest,
  onSeatGuest,
  onUnseatGuest,
  onShowTable,
  onManageGuests,
  onAnnounce,
  onDragGuestChange,
  externalFilter,
  footer,
}: SeatingGuestPanelProps) {
  const terms = activeEventTerms()
  const guestsWord = terms.guestsLabel

  const [search, setSearch] = useState('')
  // הקלדה לא חוסמת רינדור — הרשימה מתעדכנת ברקע (React 19).
  const deferredSearch = useDeferredValue(search)
  const [sort, setSort] = useState<WorkspaceSort>('confirmed_first')
  const [filter, setFilter] = useState<WorkspaceFilter>(EMPTY_FILTER)
  const [filterOpen, setFilterOpen] = useState(false)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})
  const [expandedGuest, setExpandedGuest] = useState<number | null>(null)
  const [picker, setPicker] = useState<GuestEntry | null>(null)
  const filterBtnRef = useRef<HTMLButtonElement | null>(null)
  const listId = useId()

  // סינון שנכפה מבחוץ ("הצגת מי שנשאר ללא שולחן" אחרי הושבה בקליק).
  useEffect(() => {
    if (externalFilter) setFilter(externalFilter)
  }, [externalFilter])

  const allEntries = useMemo(
    () => buildEntries(tables, unassigned),
    [tables, unassigned],
  )
  const groups = useMemo(() => groupsInUse(allEntries), [allEntries])

  const visible = useMemo(() => {
    const filtered = allEntries.filter(
      (e) => matchesSearch(e, deferredSearch) && matchesFilter(e, filter),
    )
    return sortEntries(filtered, sort)
  }, [allEntries, deferredSearch, filter, sort])

  const sections = useMemo(() => buildSections(visible), [visible])

  // הכרזה על מספר התוצאות אחרי חיפוש/סינון — לא רק שינוי ויזואלי (§31).
  const lastAnnounced = useRef<number | null>(null)
  useEffect(() => {
    if (!deferredSearch && !isFilterActive(filter)) {
      lastAnnounced.current = null
      return
    }
    if (lastAnnounced.current === visible.length) return
    lastAnnounced.current = visible.length
    onAnnounce(t.filterAnnounce(visible.length, guestsWord))
  }, [visible.length, deferredSearch, filter, onAnnounce, guestsWord])

  const toggleActions = useCallback((guestId: number) => {
    setExpandedGuest((cur) => (cur === guestId ? null : guestId))
  }, [])

  const handleSelect = useCallback(
    (guestId: number) => {
      onSelectGuest(guestId)
    },
    [onSelectGuest],
  )

  const handleDragStart = useCallback(
    (guestId: number) => {
      onSelectGuest(guestId)
      onDragGuestChange(guestId)
    },
    [onDragGuestChange, onSelectGuest],
  )
  const handleDragEnd = useCallback(() => onDragGuestChange(null), [onDragGuestChange])

  const handleEdit = useCallback(
    (name: string) => onManageGuests(name),
    [onManageGuests],
  )

  const handleSeatRequest = useCallback((entry: GuestEntry) => setPicker(entry), [])

  const emptyBecauseOfQuery = allEntries.length > 0 && visible.length === 0

  return (
    <div className="ws-panel" role="region" aria-label={t.panelLabel(guestsWord)}>
      {/* ---- כלי הרשימה ---- */}
      <div className="ws-toolbar">
        <div className="ws-search">
          <span className="ws-search-icon" aria-hidden="true">
            🔍
          </span>
          <input
            type="search"
            className="ws-search-input"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t.searchPlaceholder}
            aria-label={t.searchPlaceholder}
            aria-controls={listId}
          />
          {search && (
            <button
              type="button"
              className="ws-search-clear"
              onClick={() => setSearch('')}
              aria-label={t.searchClear}
            >
              ×
            </button>
          )}
        </div>

        <div className="ws-controls">
          <label className="ws-sr-only" htmlFor={`${listId}-sort`}>
            {t.sortLabel}
          </label>
          <select
            id={`${listId}-sort`}
            className="ws-select ws-sort"
            value={sort}
            onChange={(e) => setSort(e.target.value as WorkspaceSort)}
          >
            <option value="confirmed_first">
              {t.sortLabel}: {t.sortConfirmedFirst}
            </option>
            <option value="name_asc">
              {t.sortLabel}: {t.sortNameAsc}
            </option>
            <option value="name_desc">
              {t.sortLabel}: {t.sortNameDesc}
            </option>
            <option value="party_size">
              {t.sortLabel}: {t.sortPartySize}
            </option>
            <option value="seated_first">
              {t.sortLabel}: {t.sortSeated}
            </option>
            <option value="unseated_first">
              {t.sortLabel}: {t.sortUnseated}
            </option>
          </select>

          <button
            type="button"
            ref={filterBtnRef}
            className={`ws-filter-btn${isFilterActive(filter) ? ' is-active' : ''}`}
            aria-haspopup="dialog"
            aria-expanded={filterOpen}
            onClick={() => setFilterOpen(true)}
          >
            {t.filterLabel}
            {isFilterActive(filter) && (
              <span className="ws-filter-dot" aria-hidden="true" />
            )}
          </button>
        </div>

        <p className="ws-count">
          {t.countSummary(visible.length, allEntries.length, guestsWord)}
        </p>
      </div>

      {filterOpen && (
        <FilterPopover
          value={filter}
          groups={groups}
          guestsWord={guestsWord}
          onApply={(next) => {
            setFilter(next)
            setFilterOpen(false)
            filterBtnRef.current?.focus()
          }}
          onClose={() => {
            setFilterOpen(false)
            filterBtnRef.current?.focus()
          }}
        />
      )}

      {/* ---- הרשימה ---- */}
      <div className="ws-list" id={listId}>
        {allEntries.length === 0 && (
          <div className="ws-empty">
            <strong className="ws-empty-title">{t.emptyListTitle(guestsWord)}</strong>
            <span className="ws-empty-desc">{t.emptyListDesc}</span>
            <button
              type="button"
              className="ws-btn-primary"
              onClick={() => onManageGuests()}
            >
              {t.manageButton(guestsWord)}
            </button>
          </div>
        )}

        {emptyBecauseOfQuery && (
          <div className="ws-empty">
            <strong className="ws-empty-title">{t.emptySearchTitle}</strong>
            <span className="ws-empty-desc">{t.emptySearchDesc}</span>
            <button
              type="button"
              className="ws-btn-ghost"
              onClick={() => {
                setSearch('')
                setFilter(EMPTY_FILTER)
              }}
            >
              {t.filterReset}
            </button>
          </div>
        )}

        {sections.map((section) => {
          if (section.entries.length === 0) return null
          const isCollapsed = collapsed[section.key] === true
          const bodyId = `${listId}-sec-${section.key}`
          return (
            <section className={`ws-section ws-section-${section.key}`} key={section.key}>
              <h3 className="ws-section-head">
                <button
                  type="button"
                  className="ws-section-btn"
                  aria-expanded={!isCollapsed}
                  aria-controls={bodyId}
                  aria-label={sectionAriaLabel(section)}
                  onClick={() =>
                    setCollapsed((c) => ({ ...c, [section.key]: !isCollapsed }))
                  }
                >
                  <span className="ws-section-caret" aria-hidden="true">
                    {isCollapsed ? '▸' : '▾'}
                  </span>
                  <span className="ws-section-label">{section.label}</span>
                  <span className="ws-section-count">
                    {section.people}
                    <span className="ws-sr-only"> {t.sectionPeople(section.people)}</span>
                  </span>
                </button>
              </h3>

              <div id={bodyId} hidden={isCollapsed}>
                {section.groups.map((group) => {
                  const groupKey = `${section.key}:${group.key}`
                  const groupCollapsed = collapsed[groupKey] === true
                  const groupBodyId = `${listId}-grp-${groupKey}`
                  return (
                    <div className="ws-group" key={groupKey}>
                      <h4 className="ws-group-head">
                        <button
                          type="button"
                          className="ws-group-btn"
                          aria-expanded={!groupCollapsed}
                          aria-controls={groupBodyId}
                          aria-label={groupAriaLabel(group, guestsWord)}
                          onClick={() =>
                            setCollapsed((c) => ({ ...c, [groupKey]: !groupCollapsed }))
                          }
                        >
                          <span className="ws-group-caret" aria-hidden="true">
                            {groupCollapsed ? '▸' : '▾'}
                          </span>
                          <span className="ws-group-label">{group.label}</span>
                          <span className="ws-group-count">{group.people}</span>
                        </button>
                        {groupNotes[group.key] && (
                          <span className="ws-group-note" title={groupNotes[group.key]}>
                            <span aria-hidden="true">📝</span>
                            <span className="ws-sr-only">
                              {t.noteGroupTitle}: {groupNotes[group.key]}
                            </span>
                          </span>
                        )}
                      </h4>
                      <ul className="ws-guests" id={groupBodyId} hidden={groupCollapsed}>
                        {group.entries.map((entry) => (
                          <GuestRow
                            key={entry.guest.id}
                            entry={entry}
                            groupNote={groupNotes[entry.guest.group_type]}
                            selected={selectedGuestId === entry.guest.id}
                            expanded={expandedGuest === entry.guest.id}
                            onToggleActions={toggleActions}
                            onSelect={handleSelect}
                            onSeatRequest={handleSeatRequest}
                            onUnseat={onUnseatGuest}
                            onShowTable={onShowTable}
                            onEdit={handleEdit}
                            onDragStart={handleDragStart}
                            onDragEnd={handleDragEnd}
                          />
                        ))}
                      </ul>
                    </div>
                  )
                })}
              </div>
            </section>
          )
        })}
      </div>

      {/* ---- תחתית קבועה: הפעולה המרכזית + ניהול המוזמנים ---- */}
      <div className="ws-footer">
        {footer}
        <button
          type="button"
          className="ws-btn-ghost ws-manage-btn"
          onClick={() => onManageGuests()}
        >
          {t.manageButton(guestsWord)}
        </button>
      </div>

      {picker && (
        <SeatTablePickerDialog
          guestName={picker.guest.full_name}
          guestSeats={Math.max(1, peopleOf(picker.guest))}
          currentTable={picker.tableNumber}
          tables={tables}
          onPick={(tableNumber) => {
            onSeatGuest(picker.guest.id, tableNumber)
            setPicker(null)
          }}
          onClose={() => setPicker(null)}
        />
      )}
    </div>
  )
})
