/**
 * מרחב העבודה של ההושבה — לוגיקת הרשימה, בלי React ובלי רשת.
 *
 * מה יש כאן: חיפוש, סינון, מיון וקיבוץ של רשימת המוזמנים שבסרגל שלצד
 * סקיצת האולם, וכן בניית ה-Accessible Names לקורא מסך.
 *
 * מה **אין** כאן, בכוונה:
 * - אין חישוב הושבה. המנוע יושב בשרת (`backend/app/seating.py`), והחלטה
 *   נעולה אוסרת מנוע שיבוץ בצד הלקוח (ראו `seating-engine.md` — "מנוע אחד
 *   בלבד"). כאן רק *מציגים* מה שהשרת החזיר.
 * - אין הגדרה חדשה של "מי זכאי להושבה". הזכאות נאכפת ב-
 *   `routers/seating.py::generate` (רק `rsvp_status === 'confirmed'`),
 *   ונעולה ע"י `backend/tests/test_seating_rsvp_filter.py`.
 *
 * למה קובץ נפרד ולא בתוך הקומפוננטה: כדי שאפשר יהיה לבדוק את הסדר, המיון
 * והסינון ב-node בלי דפדפן (`npm run test:seating-workspace`).
 */
import type { HallGuest, RsvpStatus } from './types'
import { groupLabel, RSVP_LABELS } from './types'

/** מוזמן + השולחן שבו הוא יושב (null = עדיין ללא שולחן). */
export interface GuestEntry {
  guest: HallGuest
  tableNumber: number | null
}

/** המידע המינימלי על שולחן שהרשימה צריכה — לא כל ה-TableView של המפה. */
export interface WorkspaceTable {
  table_number: number
  capacity: number
  name?: string
  guests: HallGuest[]
}

/**
 * סדר סעיפי הרשימה — **החלטת מוצר, לא העתק של השרת.**
 *
 * ב-`GET /guests?sort=status` הסדר הוא confirmed → declined → maybe →
 * pending (`backend/app/routers/guests.py::_STATUS_SORT_RANK`), וזה הסדר
 * הנכון ל*ניהול רשימה*. כאן הסדר הוא סדר של **עבודת הושבה**: קודם מי
 * שצריך מקום עכשיו (אישרו), אחריו מי שעוד עשוי לצרוך מקום (ממתינים, לא
 * החליטו), ובסוף מי שלא תופס מקום (לא מגיעים).
 *
 * זו החלטת תצוגה בלבד — הסטטוס עצמו מגיע מהשרת ואינו משתנה כאן.
 */
export const RSVP_SECTION_ORDER: RsvpStatus[] = [
  'confirmed',
  'pending',
  'maybe',
  'declined',
]

const RSVP_RANK: Record<RsvpStatus, number> = {
  confirmed: 0,
  pending: 1,
  maybe: 2,
  declined: 3,
}

export type WorkspaceSort =
  | 'confirmed_first' // ברירת מחדל — אישרו הגעה ראשונים
  | 'name_asc'
  | 'name_desc'
  | 'party_size'
  | 'seated_first'
  | 'unseated_first'

export type RsvpFilter = 'all' | RsvpStatus
export type SeatingFilter = 'all' | 'seated' | 'unseated'

export interface WorkspaceFilter {
  rsvp: RsvpFilter
  seating: SeatingFilter
  /** `group_type` יחיד, או `all` לכל הקבוצות. */
  group: string
}

export const EMPTY_FILTER: WorkspaceFilter = {
  rsvp: 'all',
  seating: 'all',
  group: 'all',
}

export function isFilterActive(f: WorkspaceFilter): boolean {
  return f.rsvp !== 'all' || f.seating !== 'all' || f.group !== 'all'
}

/**
 * כמה אנשים מוזמן אחד תופס בתצוגה.
 *
 * `seats` הוא מה שהוא תופס **בפועל** אחרי RSVP — ולכן 0 למי שלא מגיע.
 * בסעיף "לא מגיעים" 0 היה מציג "0 אנשים" לכל הסעיף, שזה נכון-טכנית
 * וחסר-משמעות; שם מציגים את מספר ההזמנה המקורי (`party_size`).
 */
export function peopleOf(g: HallGuest): number {
  return g.rsvp_status === 'confirmed' ? g.seats : g.party_size
}

/**
 * בונה את רשימת העבודה מתוך מצב האולם החי (`tables` + `unassigned`).
 *
 * כל מוזמן מופיע **פעם אחת בלבד**, וההופעה הראשונה מנצחת (כלומר שיבוץ
 * לשולחן גובר על "ללא שולחן"). זו הגנה על התצוגה, לא ניקוי נתונים:
 * `tables` ו-`unassigned` הם שתי פיסות state נפרדות ב-HallPage, ויש
 * מסלולים שמעדכנים רק אחת מהן (למשל השמירה האוטומטית, שמקבלת מהשרת
 * `unassigned` מעודכן בזמן ש-`tables` המקומי עדיין מהרינדור הקודם).
 * ברגע כזה אותו מוזמן נמצא בשתיהן — וברשימה זה התבטא בשורה כפולה
 * ובאזהרת "duplicate key" של React.
 */
export function buildEntries(
  tables: WorkspaceTable[],
  unassigned: HallGuest[],
): GuestEntry[] {
  const entries: GuestEntry[] = []
  const seen = new Set<number>()
  for (const t of tables) {
    for (const g of t.guests) {
      if (seen.has(g.id)) continue
      seen.add(g.id)
      entries.push({ guest: g, tableNumber: t.table_number })
    }
  }
  for (const g of unassigned) {
    if (seen.has(g.id)) continue
    seen.add(g.id)
    entries.push({ guest: g, tableNumber: null })
  }
  return entries
}

/** נרמול קל לחיפוש: בלי רווחים מיותרים, בלי רגישות לאותיות (שמות באנגלית). */
function norm(s: string): string {
  return s.trim().toLowerCase()
}

/**
 * חיפוש: שם המוזמן, שם הקבוצה, מספר השולחן, או תוכן ההערות.
 * חיפוש ריק מחזיר תמיד true.
 */
export function matchesSearch(entry: GuestEntry, query: string): boolean {
  const q = norm(query)
  if (!q) return true
  const g = entry.guest
  if (norm(g.full_name).includes(q)) return true
  if (norm(groupLabel(g.group_type)).includes(q)) return true
  if (entry.tableNumber !== null && String(entry.tableNumber) === q) return true
  if (g.seating_notes && norm(g.seating_notes).includes(q)) return true
  if (g.guest_note && norm(g.guest_note).includes(q)) return true
  return false
}

export function matchesFilter(entry: GuestEntry, filter: WorkspaceFilter): boolean {
  if (filter.rsvp !== 'all' && entry.guest.rsvp_status !== filter.rsvp) return false
  if (filter.seating === 'seated' && entry.tableNumber === null) return false
  if (filter.seating === 'unseated' && entry.tableNumber !== null) return false
  if (filter.group !== 'all' && entry.guest.group_type !== filter.group) return false
  return true
}

function byName(a: GuestEntry, b: GuestEntry): number {
  return a.guest.full_name.localeCompare(b.guest.full_name, 'he')
}

/**
 * מיון הרשימה. כל מיון נגמר בשם א'-ב' כשובר-שוויון, כדי שהסדר יהיה יציב
 * ולא "יקפוץ" בין רינדורים.
 */
export function sortEntries(entries: GuestEntry[], sort: WorkspaceSort): GuestEntry[] {
  const out = [...entries]
  switch (sort) {
    case 'name_asc':
      return out.sort(byName)
    case 'name_desc':
      return out.sort((a, b) => byName(b, a))
    case 'party_size':
      return out.sort(
        (a, b) => peopleOf(b.guest) - peopleOf(a.guest) || byName(a, b),
      )
    case 'seated_first':
      return out.sort(
        (a, b) =>
          Number(a.tableNumber === null) - Number(b.tableNumber === null) ||
          (a.tableNumber ?? 0) - (b.tableNumber ?? 0) ||
          byName(a, b),
      )
    case 'unseated_first':
      return out.sort(
        (a, b) =>
          Number(b.tableNumber === null) - Number(a.tableNumber === null) ||
          byName(a, b),
      )
    case 'confirmed_first':
    default:
      return out.sort(
        (a, b) =>
          RSVP_RANK[a.guest.rsvp_status] - RSVP_RANK[b.guest.rsvp_status] ||
          byName(a, b),
      )
  }
}

/** תת-קבוצה בתוך סעיף RSVP — "משפחת האב", "חברים", "עובדים"… */
export interface WorkspaceGroup {
  key: string // group_type
  label: string // התווית בעברית לפי הלקסיקון
  entries: GuestEntry[]
  people: number
  seated: number // כמה מהם כבר משובצים
}

export interface WorkspaceSection {
  key: RsvpStatus
  label: string
  entries: GuestEntry[]
  groups: WorkspaceGroup[]
  people: number
  seated: number
}

/**
 * מקבץ את הרשימה לסעיפי RSVP ובתוכם לקבוצות.
 *
 * הסדר בתוך כל סעיף נשמר כפי שהתקבל (כלומר לפי המיון שנבחר), והקבוצות
 * מסודרות לפי גודל יורד — הקבוצה הגדולה קודם, כי היא זו שמכתיבה שולחנות.
 */
export function buildSections(entries: GuestEntry[]): WorkspaceSection[] {
  const byStatus = new Map<RsvpStatus, GuestEntry[]>()
  for (const status of RSVP_SECTION_ORDER) byStatus.set(status, [])
  for (const e of entries) {
    const bucket = byStatus.get(e.guest.rsvp_status)
    if (bucket) bucket.push(e)
  }

  return RSVP_SECTION_ORDER.map((status) => {
    const list = byStatus.get(status) ?? []
    const groupMap = new Map<string, GuestEntry[]>()
    for (const e of list) {
      const key = e.guest.group_type
      const arr = groupMap.get(key)
      if (arr) arr.push(e)
      else groupMap.set(key, [e])
    }
    const groups: WorkspaceGroup[] = [...groupMap.entries()]
      .map(([key, groupEntries]) => ({
        key,
        label: groupLabel(key),
        entries: groupEntries,
        people: groupEntries.reduce((s, e) => s + peopleOf(e.guest), 0),
        seated: groupEntries.filter((e) => e.tableNumber !== null).length,
      }))
      .sort((a, b) => b.people - a.people || a.label.localeCompare(b.label, 'he'))

    return {
      key: status,
      label: RSVP_LABELS[status],
      entries: list,
      groups,
      people: list.reduce((s, e) => s + peopleOf(e.guest), 0),
      seated: list.filter((e) => e.tableNumber !== null).length,
    }
  })
}

/** כל הקבוצות שבשימוש באירוע — למסנן "קבוצה". */
export function groupsInUse(entries: GuestEntry[]): { key: string; label: string }[] {
  const keys = new Set(entries.map((e) => e.guest.group_type))
  return [...keys]
    .map((key) => ({ key, label: groupLabel(key) }))
    .sort((a, b) => a.label.localeCompare(b.label, 'he'))
}

// ---------------------------------------------------------------------------
// Accessible Names (§27) — טקסט מלא לקורא מסך, בלי הסתמכות על צבע/אייקון.
// כל הטקסטים כאן הם *הרכבה* של מונחים קיימים (RSVP_LABELS, groupLabel),
// לא מילון חדש.
// ---------------------------------------------------------------------------

/** "אבי כהן, אישרו הגעה, שולחן 12" / "דנה כהן, אישרו הגעה, ללא שולחן" */
export function guestAriaLabel(entry: GuestEntry, noTableText: string, tableWord: string): string {
  const parts = [entry.guest.full_name, RSVP_LABELS[entry.guest.rsvp_status]]
  parts.push(entry.tableNumber === null ? noTableText : `${tableWord} ${entry.tableNumber}`)
  const people = peopleOf(entry.guest)
  if (people > 1) parts.push(`${people} אנשים`)
  return parts.join(', ')
}

/** "שולחן 12, 8 מתוך 10 מקומות תפוסים, 2 מקומות פנויים" */
export function tableAriaLabel(table: WorkspaceTable, tableWord: string): string {
  const used = table.guests.reduce((s, g) => s + g.seats, 0)
  const free = Math.max(0, table.capacity - used)
  const head = table.name
    ? `${tableWord} ${table.table_number}, ${table.name}`
    : `${tableWord} ${table.table_number}`
  const over = used > table.capacity ? `, חריגה של ${used - table.capacity} מקומות` : ''
  return `${head}, ${used} מתוך ${table.capacity} מקומות תפוסים, ${free} מקומות פנויים${over}`
}

/** "משפחת האב, 18 מוזמנים, 14 הושבו" */
export function groupAriaLabel(group: WorkspaceGroup, guestsWord: string): string {
  return `${group.label}, ${group.people} ${guestsWord}, ${group.seated} הושבו`
}

/** "אישרו הגעה, 122 אנשים, 100 הושבו" */
export function sectionAriaLabel(section: WorkspaceSection): string {
  return `${section.label}, ${section.people} אנשים, ${section.seated} הושבו`
}

/**
 * כמה מקומות יהיו תפוסים בשולחן **אחרי** שמוזמן יושב בו.
 *
 * שני דברים שקל לטעות בהם, ושניהם התגלו בבדיקה:
 * 1. מוזמן שכבר יושב בשולחן הזה לא נספר פעמיים (העברה אל אותו שולחן).
 * 2. מי שאינו "מגיע" תופס `seats === 0`, ולכן "הושבה בכל זאת" שלו אינה
 *    משנה את התפוסה. עיגול ל-1 היה מדווח למשתמש מספר שלא יופיע על השולחן.
 */
export function occupancyAfterSeating(table: WorkspaceTable, guest: HallGuest): number {
  const current = table.guests.reduce((sum, g) => sum + g.seats, 0)
  const alreadyHere = table.guests.some((g) => g.id === guest.id)
  return current + (alreadyHere ? 0 : guest.seats)
}

/** תפוסת שולחן כטקסט קצר לתצוגה: "8/10". */
export function tableOccupancy(table: WorkspaceTable): { used: number; free: number; full: boolean } {
  const used = table.guests.reduce((s, g) => s + g.seats, 0)
  return { used, free: Math.max(0, table.capacity - used), full: used >= table.capacity }
}
