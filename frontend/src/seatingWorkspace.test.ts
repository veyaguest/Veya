/**
 * בדיקות ללוגיקת רשימת המוזמנים במרחב העבודה של ההושבה.
 *
 * הרצה: `npm run test:seating-workspace` מתוך תיקיית frontend.
 * (מהדר את הקוד האמיתי ומריץ ב-node — בלי דפדפן, בלי runner. אותו דפוס
 * של `test:hall-sketch-geometry`.)
 *
 * חשוב: הבדיקות מייבאות את **הקוד שנשלח לייצור** (`seatingWorkspace.ts`),
 * לא העתק שלו — כך שינוי בלוגיקה נתפס כאן מיד.
 */
import {
  buildEntries,
  buildSections,
  EMPTY_FILTER,
  groupsInUse,
  guestAriaLabel,
  isFilterActive,
  matchesFilter,
  matchesSearch,
  peopleOf,
  RSVP_SECTION_ORDER,
  sectionAriaLabel,
  sortEntries,
  tableAriaLabel,
  tableOccupancy,
} from './seatingWorkspace'
import type { GuestEntry, WorkspaceFilter, WorkspaceTable } from './seatingWorkspace'
import type { HallGuest, RsvpStatus } from './types'

/* עוזרי assert מקומיים — לפרויקט אין @types/node, ובדיקת הגאומטריה
   הקיימת (hallSketchGeometry.test.ts) משתמשת באותו דפוס בדיוק. */
const assert = {
  equal(actual: unknown, expected: unknown, msg = ''): void {
    if (actual !== expected) {
      throw new Error(`✗ ${msg}\n  התקבל:  ${JSON.stringify(actual)}\n  ציפינו: ${JSON.stringify(expected)}`)
    }
  },
  deepEqual(actual: unknown, expected: unknown, msg = ''): void {
    const a = JSON.stringify(actual)
    const b = JSON.stringify(expected)
    if (a !== b) throw new Error(`✗ ${msg}\n  התקבל:  ${a}\n  ציפינו: ${b}`)
  },
  ok(cond: boolean, msg = ''): void {
    if (!cond) throw new Error(`✗ ${msg}`)
  },
  match(actual: string, re: RegExp, msg = ''): void {
    if (!re.test(actual)) throw new Error(`✗ ${msg}\n  התקבל: ${actual}\n  לא תואם: ${re}`)
  },
}

let id = 0
function guest(
  full_name: string,
  rsvp_status: RsvpStatus,
  extra: Partial<HallGuest> = {},
): HallGuest {
  id += 1
  return {
    id,
    full_name,
    party_size: 1,
    seats: rsvp_status === 'confirmed' ? 1 : 0,
    side: 'shared',
    group_type: 'other',
    rsvp_status,
    is_child: false,
    ...extra,
  } as HallGuest
}

function entry(g: HallGuest, tableNumber: number | null = null): GuestEntry {
  return { guest: g, tableNumber }
}

// ---------------------------------------------------------------------------
// §5 — סדר ברירת המחדל: אישרו → ממתינים → לא החליטו → לא מגיעים
// ---------------------------------------------------------------------------

function testDefaultOrder(): void {
  assert.deepEqual(RSVP_SECTION_ORDER, ['confirmed', 'pending', 'maybe', 'declined'])

  const entries = [
    entry(guest('דנה', 'declined')),
    entry(guest('גיל', 'maybe')),
    entry(guest('בני', 'pending')),
    entry(guest('אבי', 'confirmed')),
  ]
  const sorted = sortEntries(entries, 'confirmed_first')
  assert.deepEqual(
    sorted.map((e) => e.guest.rsvp_status),
    ['confirmed', 'pending', 'maybe', 'declined'],
    'ברירת המחדל חייבת להיות אישרו → ממתינים → לא החליטו → לא מגיעים',
  )
  console.log('✓ ברירת מחדל: אישרו הגעה ראשונים, לא מגיעים אחרונים')
}

function testAlphabeticalWithinStatus(): void {
  const entries = [
    entry(guest('בתיה', 'confirmed')),
    entry(guest('אבי', 'confirmed')),
    entry(guest('גיל', 'confirmed')),
  ]
  assert.deepEqual(
    sortEntries(entries, 'confirmed_first').map((e) => e.guest.full_name),
    ['אבי', 'בתיה', 'גיל'],
    'בתוך אותו סטטוס — א-ב',
  )
  console.log('✓ בתוך אותו סטטוס הסדר הוא א-ב')
}

function testStatusChangeMovesGuest(): void {
  // §42: "שינוי RSVP מעדכן את הסדר" — אותו מוזמן, סטטוס אחר, מיקום אחר.
  const pendingAvi = guest('אבי', 'pending')
  const confirmedZohar = guest('זוהר', 'confirmed')
  let entries = [entry(pendingAvi), entry(confirmedZohar)]
  assert.equal(sortEntries(entries, 'confirmed_first')[0].guest.full_name, 'זוהר')

  const confirmedAvi = { ...pendingAvi, rsvp_status: 'confirmed' as RsvpStatus, seats: 1 }
  entries = [entry(confirmedAvi), entry(confirmedZohar)]
  assert.equal(
    sortEntries(entries, 'confirmed_first')[0].guest.full_name,
    'אבי',
    'אחרי אישור הגעה, אבי עולה לפני זוהר (א-ב בתוך אותו סטטוס)',
  )
  console.log('✓ שינוי סטטוס RSVP מזיז את המוזמן במיקום ברשימה')
}

// ---------------------------------------------------------------------------
// §10 — מיונים
// ---------------------------------------------------------------------------

function testAllSorts(): void {
  const a = entry(guest('אבי', 'confirmed', { party_size: 1, seats: 1 }), 3)
  const b = entry(guest('בני', 'confirmed', { party_size: 5, seats: 5 }), null)
  const c = entry(guest('גיל', 'pending', { party_size: 2 }), 1)

  assert.deepEqual(
    sortEntries([c, b, a], 'name_asc').map((e) => e.guest.full_name),
    ['אבי', 'בני', 'גיל'],
  )
  assert.deepEqual(
    sortEntries([a, b, c], 'name_desc').map((e) => e.guest.full_name),
    ['גיל', 'בני', 'אבי'],
  )
  assert.equal(sortEntries([a, b, c], 'party_size')[0].guest.full_name, 'בני')
  assert.equal(
    sortEntries([b, a, c], 'seated_first')[0].guest.full_name,
    'גיל',
    'מיון "הושבו" — לפי מספר שולחן עולה, וללא-שולחן בסוף',
  )
  const seatedOrder = sortEntries([a, c, b], 'seated_first')
  assert.equal(seatedOrder[seatedOrder.length - 1].guest.full_name, 'בני')
  assert.equal(sortEntries([a, c, b], 'unseated_first')[0].guest.full_name, 'בני')
  console.log('✓ כל המיונים: שם א-ת, ת-א, כמות אנשים, הושבו, לא הושבו')
}

// ---------------------------------------------------------------------------
// §9 — סינון
// ---------------------------------------------------------------------------

function testFilters(): void {
  const seatedConfirmed = entry(guest('אבי', 'confirmed', { group_type: 'friends' }), 5)
  const unseatedPending = entry(guest('בני', 'pending', { group_type: 'work' }), null)

  assert.equal(isFilterActive(EMPTY_FILTER), false)
  assert.equal(matchesFilter(seatedConfirmed, EMPTY_FILTER), true)
  assert.equal(matchesFilter(unseatedPending, EMPTY_FILTER), true)

  const f = (over: Partial<WorkspaceFilter>): WorkspaceFilter => ({ ...EMPTY_FILTER, ...over })

  assert.equal(matchesFilter(seatedConfirmed, f({ rsvp: 'confirmed' })), true)
  assert.equal(matchesFilter(unseatedPending, f({ rsvp: 'confirmed' })), false)
  assert.equal(matchesFilter(seatedConfirmed, f({ seating: 'seated' })), true)
  assert.equal(matchesFilter(seatedConfirmed, f({ seating: 'unseated' })), false)
  assert.equal(matchesFilter(unseatedPending, f({ seating: 'unseated' })), true)
  assert.equal(matchesFilter(seatedConfirmed, f({ group: 'friends' })), true)
  assert.equal(matchesFilter(seatedConfirmed, f({ group: 'work' })), false)
  assert.equal(isFilterActive(f({ group: 'work' })), true)
  console.log('✓ סינון: סטטוס RSVP, הושבו/לא הושבו, קבוצה')
}

// ---------------------------------------------------------------------------
// §8 — חיפוש, וגם חיפוש + סינון + מיון יחד
// ---------------------------------------------------------------------------

function testSearch(): void {
  const e = entry(
    guest('אבי כהן', 'confirmed', { group_type: 'friends', seating_notes: 'ליד הרחבה' }),
    12,
  )
  assert.equal(matchesSearch(e, ''), true, 'חיפוש ריק מחזיר הכול')
  assert.equal(matchesSearch(e, 'כהן'), true)
  assert.equal(matchesSearch(e, 'חברים'), true, 'חיפוש לפי שם קבוצה')
  assert.equal(matchesSearch(e, '12'), true, 'חיפוש לפי מספר שולחן')
  assert.equal(matchesSearch(e, 'רחבה'), true, 'חיפוש בתוך הערת ההושבה')
  assert.equal(matchesSearch(e, 'לוי'), false)
  console.log('✓ חיפוש: שם, קבוצה, מספר שולחן, הערה')
}

function testSearchFilterSortTogether(): void {
  // התרחיש מהאפיון: חיפוש "כהן" + סינון "אישרו הגעה" + מיון "שם א׳–ת׳".
  const entries = [
    entry(guest('אבי כהן', 'confirmed'), 1),
    entry(guest('דנה כהן', 'confirmed'), null),
    entry(guest('בני כהן', 'pending'), null),
    entry(guest('גיל לוי', 'confirmed'), null),
  ]
  const result = sortEntries(
    entries
      .filter((e) => matchesSearch(e, 'כהן'))
      .filter((e) => matchesFilter(e, { ...EMPTY_FILTER, rsvp: 'confirmed' })),
    'name_asc',
  )
  assert.deepEqual(
    result.map((e) => e.guest.full_name),
    ['אבי כהן', 'דנה כהן'],
    'חיפוש + סינון + מיון חייבים לעבוד יחד',
  )
  console.log('✓ חיפוש + סינון + מיון פועלים יחד')
}

function testNoResults(): void {
  const entries = [entry(guest('אבי', 'confirmed'))]
  assert.equal(entries.filter((e) => matchesSearch(e, 'לוי')).length, 0)
  console.log('✓ חיפוש בלי תוצאות מחזיר רשימה ריקה')
}

// ---------------------------------------------------------------------------
// §7 — קבוצות בתוך סעיפי RSVP
// ---------------------------------------------------------------------------

function testSections(): void {
  const entries = [
    entry(guest('אבי כהן', 'confirmed', { group_type: 'close_family', party_size: 2, seats: 2 }), 1),
    entry(guest('דנה כהן', 'confirmed', { group_type: 'close_family', party_size: 1, seats: 1 }), null),
    entry(guest('רון לוי', 'confirmed', { group_type: 'army', party_size: 4, seats: 4 }), 2),
    entry(guest('נועה', 'pending', { group_type: 'friends', party_size: 2 })),
    entry(guest('שרון', 'declined', { group_type: 'work', party_size: 3 })),
  ]
  const sections = buildSections(entries)
  assert.deepEqual(
    sections.map((s) => s.key),
    ['confirmed', 'pending', 'maybe', 'declined'],
    'הסעיפים תמיד באותו סדר, גם כשסעיף ריק',
  )

  const confirmed = sections[0]
  assert.equal(confirmed.people, 7, '2+1+4 אנשים אישרו')
  assert.equal(confirmed.seated, 2, 'שניים מהם משובצים')
  assert.deepEqual(
    confirmed.groups.map((g) => g.key),
    ['army', 'close_family'],
    'הקבוצה הגדולה קודם (4 מול 3)',
  )
  assert.equal(confirmed.groups[1].label, 'משפחה קרובה')
  assert.equal(confirmed.groups[1].seated, 1)

  // §5 — "לא מגיעים" נספרים לפי מספר ההזמנה המקורי, לא לפי 0 מקומות.
  const declined = sections[3]
  assert.equal(declined.people, 3, 'לא מגיעים נספרים לפי party_size')
  assert.equal(peopleOf(entries[4].guest), 3)

  const maybe = sections[2]
  assert.equal(maybe.entries.length, 0)
  assert.equal(maybe.groups.length, 0)
  console.log('✓ קיבוץ לסעיפי RSVP ולקבוצות, כולל ספירות')
}

function testGroupsInUse(): void {
  const entries = [
    entry(guest('א', 'confirmed', { group_type: 'work' })),
    entry(guest('ב', 'pending', { group_type: 'work' })),
    entry(guest('ג', 'confirmed', { group_type: 'army' })),
  ]
  // ממוין לפי **התווית בעברית**, לא לפי המפתח באנגלית:
  // "עבודה" (work) לפני "צבא" (army).
  assert.deepEqual(
    groupsInUse(entries).map((g) => g.label),
    ['עבודה', 'צבא'],
    'רק קבוצות שבשימוש, ממוינות לפי התווית בעברית',
  )
  console.log('✓ רשימת הקבוצות שבשימוש נגזרת מהמוזמנים בפועל')
}

// ---------------------------------------------------------------------------
// buildEntries — הגזירה ממצב האולם החי
// ---------------------------------------------------------------------------

function testBuildEntries(): void {
  const seated = guest('אבי', 'confirmed')
  const waiting = guest('בני', 'pending')
  const tables: WorkspaceTable[] = [
    { table_number: 7, capacity: 10, guests: [seated] },
    { table_number: 8, capacity: 10, guests: [] },
  ]
  const entries = buildEntries(tables, [waiting])
  assert.equal(entries.length, 2)
  assert.equal(entries.find((e) => e.guest.id === seated.id)!.tableNumber, 7)
  assert.equal(entries.find((e) => e.guest.id === waiting.id)!.tableNumber, null)
  console.log('✓ הרשימה נגזרת ממצב האולם החי (tables + unassigned)')
}

// ---------------------------------------------------------------------------
// §27 / §33 — Accessible Names
// ---------------------------------------------------------------------------

function testAriaLabels(): void {
  const seated = entry(guest('אבי כהן', 'confirmed', { party_size: 2, seats: 2 }), 12)
  assert.equal(
    guestAriaLabel(seated, 'לא הושבה', 'שולחן'),
    'אבי כהן, אישרו הגעה, שולחן 12, 2 אנשים',
  )
  const alone = entry(guest('דנה כהן', 'confirmed'), null)
  assert.equal(guestAriaLabel(alone, 'לא הושבה', 'שולחן'), 'דנה כהן, אישרו הגעה, לא הושבה')

  const table: WorkspaceTable = {
    table_number: 12,
    capacity: 10,
    guests: [guest('x', 'confirmed', { seats: 8 })],
  }
  assert.equal(
    tableAriaLabel(table, 'שולחן'),
    'שולחן 12, 8 מתוך 10 מקומות תפוסים, 2 מקומות פנויים',
  )
  const over: WorkspaceTable = {
    table_number: 3,
    capacity: 6,
    guests: [guest('y', 'confirmed', { seats: 8 })],
  }
  assert.match(tableAriaLabel(over, 'שולחן'), /חריגה של 2 מקומות$/)

  const sections = buildSections([seated, alone])
  assert.equal(sectionAriaLabel(sections[0]), 'אישרו הגעה, 3 אנשים, 1 הושבו')
  console.log('✓ Accessible Names למוזמן, לשולחן ולסעיף')
}

function testOccupancy(): void {
  const t: WorkspaceTable = {
    table_number: 1,
    capacity: 10,
    guests: [guest('a', 'confirmed', { seats: 8 })],
  }
  assert.deepEqual(tableOccupancy(t), { used: 8, free: 2, full: false })
  const fullTable: WorkspaceTable = {
    table_number: 2,
    capacity: 4,
    guests: [guest('b', 'confirmed', { seats: 4 })],
  }
  assert.deepEqual(tableOccupancy(fullTable), { used: 4, free: 0, full: true })
  console.log('✓ תפוסת שולחן: תפוסים / פנויים / מלא')
}

// ---------------------------------------------------------------------------
// ביצועים — מאות מוזמנים (§41)
// ---------------------------------------------------------------------------

function testLargeDataset(): void {
  const statuses: RsvpStatus[] = ['confirmed', 'pending', 'maybe', 'declined']
  const groups = ['close_family', 'friends', 'work', 'army', 'neighbors']
  const tables: WorkspaceTable[] = []
  const unassigned: HallGuest[] = []
  for (let i = 0; i < 600; i++) {
    const g = guest(`מוזמן ${i}`, statuses[i % 4], { group_type: groups[i % 5] })
    if (i % 3 === 0) {
      const tnum = Math.floor(i / 12) + 1
      const t = tables.find((x) => x.table_number === tnum)
      if (t) t.guests.push(g)
      else tables.push({ table_number: tnum, capacity: 12, guests: [g] })
    } else {
      unassigned.push(g)
    }
  }

  const started = Date.now()
  const entries = buildEntries(tables, unassigned)
  const sections = buildSections(sortEntries(entries, 'confirmed_first'))
  const elapsed = Date.now() - started

  assert.equal(entries.length, 600)
  assert.equal(
    sections.reduce((s, x) => s + x.entries.length, 0),
    600,
    'אף מוזמן לא נעלם בקיבוץ',
  )
  assert.ok(elapsed < 250, `בניית הרשימה ל-600 מוזמנים ארכה ${elapsed}ms — איטי מדי`)
  console.log(`✓ 600 מוזמנים: מיון + קיבוץ ב-${elapsed}ms`)
}

testDefaultOrder()
testAlphabeticalWithinStatus()
testStatusChangeMovesGuest()
testAllSorts()
testFilters()
testSearch()
testSearchFilterSortTogether()
testNoResults()
testSections()
testGroupsInUse()
testBuildEntries()
testAriaLabels()
testOccupancy()
testLargeDataset()
console.log('OK — לוגיקת רשימת המוזמנים במרחב ההושבה עובדת כמפרט.')
