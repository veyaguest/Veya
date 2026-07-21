/**
 * עוזר הושבה חכם — מודול ליבה טהור (בלי UI, בלי קריאות רשת, בלי LLM).
 *
 * חשוב: הקובץ הזה **לא נוגע** ב-`app/seating.py` (המנוע הנעול בשרת) ולא
 * מייבא ממנו כלום. הוא שכבת ניתוח עצמאית שרצה על הנתונים שכבר קיימים
 * בצד הלקוח אחרי `GET /hall` (שולחנות, מוזמנים, זוגות אילוצים) ומחזירה
 * סטטיסטיקות/אזהרות/הצעות — כל הצעה היא רק טקסט + רשימת מהלכים מוצעים;
 * שום פונקציה כאן לא משנה state, לא קוראת ל-API ולא מפעילה שום דבר לבד.
 *
 * כל הפונקציות טהורות (קלט → פלט) וניתנות לבדיקה עצמאית.
 */
import { groupLabel, type HallGuest, type Side, type TableType } from './types'
import { sidePhrase } from './strings/eventTypes'

// מבנה שולחן מינימלי הדרוש לניתוח — תואם מבנית ל-TableView הפרטי
// שבתוך HallPage.tsx (בלי תלות ישירה בקובץ הזה, כדי למנוע import מעגלי
// ולשמור על המודול עצמאי/ניתן-לבדיקה בנפרד).
export interface SeatingTable {
  table_number: number
  guests: HallGuest[]
  table_type: TableType
  capacity: number
  name: string
  locked: boolean
}

export type PairList = [number, number][]

// ---- עזרי בסיס -------------------------------------------------------

function pairKey(a: number, b: number): string {
  return a < b ? `${a}_${b}` : `${b}_${a}`
}

function pairSetFrom(pairs: PairList | undefined): Set<string> {
  const s = new Set<string>()
  for (const [a, b] of pairs ?? []) s.add(pairKey(a, b))
  return s
}

// ---- שלב 1: סטטיסטיקות -------------------------------------------------

export interface SeatingStats {
  totalGuests: number // סה"כ מוזמנים (רשומות, לא כמות אנשים)
  totalPeople: number // סה"כ אנשים בפועל (effective seats)
  seatedPeople: number
  unseatedPeople: number
  unseatedGuests: number
  numTables: number
  totalCapacity: number
  freeSeats: number
  fullTables: number // תפוסה 100%+
  nearFullTables: number // תפוסה 90%-100%
  nearEmptyTables: number // יש מישהו אבל תפוסה מתחת ל-30%
  emptyTables: number // אין אף אחד
}

export function computeStats(
  tables: SeatingTable[],
  unassigned: HallGuest[],
  _seatsPerTable: number,
): SeatingStats {
  let seatedPeople = 0
  let totalCapacity = 0
  let fullTables = 0
  let nearFullTables = 0
  let nearEmptyTables = 0
  let emptyTables = 0

  for (const t of tables) {
    const used = t.guests.reduce((sum, g) => sum + g.seats, 0)
    seatedPeople += used
    totalCapacity += t.capacity
    const ratio = t.capacity > 0 ? used / t.capacity : 0
    if (used === 0) emptyTables++
    else if (ratio >= 1) fullTables++
    else if (ratio >= 0.9) nearFullTables++
    else if (ratio < 0.3) nearEmptyTables++
  }

  const unseatedPeople = unassigned.reduce((sum, g) => sum + g.seats, 0)
  const totalPeople = seatedPeople + unseatedPeople

  return {
    totalGuests: tables.reduce((n, t) => n + t.guests.length, 0) + unassigned.length,
    totalPeople,
    seatedPeople,
    unseatedPeople,
    unseatedGuests: unassigned.length,
    numTables: tables.length,
    totalCapacity,
    freeSeats: Math.max(0, totalCapacity - seatedPeople),
    fullTables,
    nearFullTables,
    nearEmptyTables,
    emptyTables,
  }
}

// ---- שלב 2: זיהוי משפחות (לפי מילת שם אחרונה בשם המלא) ------------------

// שם משפחה קצר מדי (אות אחת) לא מספיק ייחודי לזיהוי אמין — false positive
// גבוה (למשל "עם קידומת בודדת"). מסננים קבוצות שהעוגן שלהן קצר מדי.
const MIN_SURNAME_LEN = 2

export interface FamilyGroup {
  surname: string
  guestIds: number[]
}

/** מקבל את כל המוזמנים (משובצים + לא-משובצים) ומחזיר קבוצות משפחה בגודל ≥2. */
export function detectFamilyGroups(
  allGuests: { id: number; full_name: string }[],
): FamilyGroup[] {
  const bySurname = new Map<string, number[]>()
  for (const g of allGuests) {
    const parts = g.full_name.trim().split(/\s+/).filter(Boolean)
    if (parts.length < 2) continue // בלי שם משפחה — לא ניתן לשייך למשפחה
    const surname = parts[parts.length - 1]
    if (surname.length < MIN_SURNAME_LEN) continue
    const arr = bySurname.get(surname)
    if (arr) arr.push(g.id)
    else bySurname.set(surname, [g.id])
  }
  const groups: FamilyGroup[] = []
  for (const [surname, guestIds] of bySurname) {
    if (guestIds.length >= 2) groups.push({ surname, guestIds })
  }
  return groups
}

// ---- שלב 3: זיהוי קבוצות מפוצלות (לפי group_type) ----------------------

export interface SplitGroupInfo {
  groupType: string
  label: string
  tableNumbers: number[] // השולחנות שהקבוצה מפוצלת ביניהם (רק משובצים)
  guestIdsByTable: Map<number, number[]>
}

/** מזהה קבוצות (group_type) שמפוצלות בין ≥2 שולחנות שונים. 'other' מתעלמים
 * ממנה במפורש — כמעט כל אורח יכול להיות שם, כך שכמעט תמיד "מפוצלת" ואין
 * בכך תובנה שימושית. */
export function detectSplitGroups(tables: SeatingTable[]): SplitGroupInfo[] {
  const byGroup = new Map<string, Map<number, number[]>>()
  for (const t of tables) {
    for (const g of t.guests) {
      if (!g.group_type || g.group_type === 'other') continue
      let byTable = byGroup.get(g.group_type)
      if (!byTable) {
        byTable = new Map()
        byGroup.set(g.group_type, byTable)
      }
      const arr = byTable.get(t.table_number)
      if (arr) arr.push(g.id)
      else byTable.set(t.table_number, [g.id])
    }
  }
  const result: SplitGroupInfo[] = []
  for (const [groupType, byTable] of byGroup) {
    if (byTable.size >= 2) {
      result.push({
        groupType,
        label: groupLabel(groupType),
        tableNumbers: [...byTable.keys()].sort((a, b) => a - b),
        guestIdsByTable: byTable,
      })
    }
  }
  return result
}

// ---- שלב 4: ילדים ללא מבוגר מהמשפחה באותו שולחן ------------------------

export interface ChildWithoutFamilyWarning {
  childId: number
  childName: string
  tableNumber: number
}

/** לכל מוזמן עם is_child=true שכן משובץ לשולחן, בודק שיש לפחות מבוגר אחד
 * מאותה "משפחה" (detectFamilyGroups) יושב באותו שולחן. מבוסס על שדה
 * מפורש (is_child), לא ניחוש. ילדים לא-משובצים לא נבדקים כאן — הם כבר
 * מכוסים ע"י ספירת "לא שובצו" הכללית. */
export function detectChildrenWithoutFamily(
  tables: SeatingTable[],
  familyGroups: FamilyGroup[],
): ChildWithoutFamilyWarning[] {
  // מיפוי guestId -> קבוצת המשפחה שלו (אם יש)
  const familyOf = new Map<number, number[]>() // guestId -> כל שאר בני המשפחה
  for (const fam of familyGroups) {
    for (const id of fam.guestIds) {
      familyOf.set(
        id,
        fam.guestIds.filter((x) => x !== id),
      )
    }
  }

  const warnings: ChildWithoutFamilyWarning[] = []
  for (const t of tables) {
    const tableGuestIds = new Set(t.guests.map((g) => g.id))
    for (const g of t.guests) {
      if (!g.is_child) continue
      const relatives = familyOf.get(g.id)
      if (!relatives || relatives.length === 0) continue // אין מידע על משפחה — לא ניתן לבדוק
      const hasAdultRelativeHere = relatives.some((relId) => {
        if (!tableGuestIds.has(relId)) return false
        const relGuest = t.guests.find((x) => x.id === relId)
        return !!relGuest && !relGuest.is_child
      })
      if (!hasAdultRelativeHere) {
        warnings.push({ childId: g.id, childName: g.full_name, tableNumber: t.table_number })
      }
    }
  }
  return warnings
}

// ---- שלב 5: אזהרות חכמות מאוחדות ---------------------------------------

export interface SmartWarning {
  severity: 'red' | 'yellow'
  tableNumbers: number[]
  text: string
}

export function computeSmartWarnings(
  tables: SeatingTable[],
  familyGroups: FamilyGroup[],
  splitGroups: SplitGroupInfo[],
  childWarnings: ChildWithoutFamilyWarning[],
  togetherPairs?: PairList,
): SmartWarning[] {
  const warnings: SmartWarning[] = []

  // משפחות מפוצלות: לפי FamilyGroup, בודקים אם בני המשפחה (המשובצים) יושבים
  // ביותר משולחן אחד.
  const tableByGuestId = new Map<number, number>()
  for (const t of tables) {
    for (const g of t.guests) tableByGuestId.set(g.id, t.table_number)
  }
  for (const fam of familyGroups) {
    const tableNums = new Set<number>()
    for (const id of fam.guestIds) {
      const tn = tableByGuestId.get(id)
      if (tn != null) tableNums.add(tn)
    }
    if (tableNums.size >= 2) {
      warnings.push({
        severity: 'yellow',
        tableNumbers: [...tableNums].sort((a, b) => a - b),
        text: `משפחת ${fam.surname} מפוצלת בין ${tableNums.size} שולחנות (${[...tableNums]
          .sort((a, b) => a - b)
          .join(', ')})`,
      })
    }
  }

  // קבוצות מפוצלות (group_type)
  for (const sg of splitGroups) {
    warnings.push({
      severity: 'yellow',
      tableNumbers: sg.tableNumbers,
      text: `קבוצת "${sg.label}" מפוצלת בין ${sg.tableNumbers.length} שולחנות (${sg.tableNumbers.join(', ')})`,
    })
  }

  // ילדים ללא מבוגר מהמשפחה
  for (const cw of childWarnings) {
    warnings.push({
      severity: 'red',
      tableNumbers: [cw.tableNumber],
      text: `${cw.childName} (ילד/ה) יושב/ת בשולחן ${cw.tableNumber} בלי אף מבוגר מהמשפחה`,
    })
  }

  // זוגות "לשבת יחד" שבפועל יושבים בשולחנות שונים (שניהם כבר משובצים)
  for (const [a, b] of togetherPairs ?? []) {
    const ta = tableByGuestId.get(a)
    const tb = tableByGuestId.get(b)
    if (ta != null && tb != null && ta !== tb) {
      const nameA = tables.flatMap((t) => t.guests).find((g) => g.id === a)?.full_name ?? `#${a}`
      const nameB = tables.flatMap((t) => t.guests).find((g) => g.id === b)?.full_name ?? `#${b}`
      warnings.push({
        severity: 'yellow',
        tableNumbers: [ta, tb].sort((x, y) => x - y),
        text: `${nameA} ו${nameB} סומנו כ"לשבת יחד" אבל יושבים בשולחנות נפרדים (${ta}, ${tb})`,
      })
    }
  }

  // ערבוב צד חתן וצד כלה באותו שולחן — אזהרה רכה בלבד, ורק כשהערבוב בולט
  // (לפחות 3 מכל צד), כדי לא להציק על שולחנות "משותפים" תקינים. מוזמני
  // "משותף" לא נספרים כאן — הם ניטרליים ומשתלבים בכל צד.
  const SIDE_MIX_THRESHOLD = 3
  for (const t of tables) {
    let groom = 0
    let bride = 0
    for (const g of t.guests) {
      if (g.side === 'groom') groom += 1
      else if (g.side === 'bride') bride += 1
    }
    if (groom >= SIDE_MIX_THRESHOLD && bride >= SIDE_MIX_THRESHOLD) {
      warnings.push({
        severity: 'yellow',
        tableNumbers: [t.table_number],
        text: `בשולחן ${t.table_number} מעורבבים ${groom} מ${sidePhrase('groom')} ו-${bride} מ${sidePhrase('bride')} — כדאי לוודא שזה מכוון`,
      })
    }
  }

  // שולחן כמעט-ריק לצד שולחן כמעט-מלא — הזדמנות ניצול מקום (לפנות שולחן
  // שלם ולחסוך). "כמעט ריק" = תפוסה מתחת ל-30% (יש לפחות מוזמן אחד),
  // "כמעט מלא" = תפוסה 90%-100% אבל לא מלא לגמרי (עדיין יש מקום לספוג).
  const nearEmptyForOpportunity = tables.filter((t) => {
    const used = t.guests.reduce((sum, g) => sum + g.seats, 0)
    const ratio = t.capacity > 0 ? used / t.capacity : 0
    return used > 0 && ratio < 0.3
  })
  const nearFullForOpportunity = tables.filter((t) => {
    const used = t.guests.reduce((sum, g) => sum + g.seats, 0)
    const ratio = t.capacity > 0 ? used / t.capacity : 0
    return ratio >= 0.9 && ratio < 1
  })
  for (const empty of nearEmptyForOpportunity) {
    const emptyUsed = empty.guests.reduce((sum, g) => sum + g.seats, 0)
    // מחפשים שולחן כמעט-מלא שיכול לספוג את כל האורחים משולחן כמעט-הריק
    const target = nearFullForOpportunity.find((t) => {
      const used = t.guests.reduce((sum, g) => sum + g.seats, 0)
      return t.capacity - used >= emptyUsed
    })
    if (target) {
      warnings.push({
        severity: 'yellow',
        tableNumbers: [empty.table_number, target.table_number].sort((a, b) => a - b),
        text: `שולחן ${empty.table_number} כמעט ריק (${emptyUsed}/${empty.capacity}) ושולחן ${target.table_number} כמעט מלא — אפשר לאחד ולפנות שולחן שלם`,
      })
    }
  }

  return warnings
}

// ---- שלב 6: הצעות קונקרטיות (moves) ------------------------------------

export interface SmartMove {
  guestId: number
  toTable: number
}

export interface SmartSuggestion {
  text: string
  moves: SmartMove[]
}

function tableFreeCapacity(t: SeatingTable): number {
  const used = t.guests.reduce((sum, g) => sum + g.seats, 0)
  return Math.max(0, t.capacity - used)
}

/** בוחר את השולחן עם הכי הרבה נציגים מתוך קבוצת האנשים הנתונה, ושיש בו
 * מקום פנוי — יעד טבעי לאיחוד. מחזיר null אם אין שולחן פנוי מתאים. */
function pickReunionTarget(
  tables: SeatingTable[],
  memberIds: Set<number>,
  neededSeats: number,
): SeatingTable | null {
  let best: SeatingTable | null = null
  let bestCount = -1
  for (const t of tables) {
    const count = t.guests.filter((g) => memberIds.has(g.id)).length
    if (count === 0) continue
    if (tableFreeCapacity(t) < neededSeats) continue
    if (count > bestCount) {
      best = t
      bestCount = count
    }
  }
  return best
}

export function computeSuggestions(
  tables: SeatingTable[],
  familyGroups: FamilyGroup[],
  splitGroups: SplitGroupInfo[],
  childWarnings: ChildWithoutFamilyWarning[],
  togetherPairs?: PairList,
): SmartSuggestion[] {
  const suggestions: SmartSuggestion[] = []
  const guestById = new Map<number, HallGuest>()
  const tableByGuestId = new Map<number, number>()
  for (const t of tables) {
    for (const g of t.guests) {
      guestById.set(g.id, g)
      tableByGuestId.set(g.id, t.table_number)
    }
  }
  const tableByNum = new Map(tables.map((t) => [t.table_number, t]))

  // (א) איחוד משפחות מפוצלות
  for (const fam of familyGroups) {
    const seated = fam.guestIds.filter((id) => tableByGuestId.has(id))
    const tableNums = new Set(seated.map((id) => tableByGuestId.get(id)!))
    if (tableNums.size < 2) continue
    const memberSet = new Set(fam.guestIds)
    // מזיזים את מי שאינם בשולחן הרוב אליו
    const target = pickReunionTarget(tables, memberSet, 0)
    if (!target) continue
    const toMove = seated.filter((id) => tableByGuestId.get(id) !== target.table_number)
    const neededSeats = toMove.reduce((sum, id) => sum + (guestById.get(id)?.seats ?? 1), 0)
    if (tableFreeCapacity(target) < neededSeats) continue
    if (toMove.length === 0) continue
    suggestions.push({
      text: `לאחד את משפחת ${fam.surname} — להעביר ${toMove.length} מוזמנים לשולחן ${target.table_number}`,
      moves: toMove.map((id) => ({ guestId: id, toTable: target.table_number })),
    })
  }

  // (ב) איחוד קבוצות מפוצלות (group_type)
  for (const sg of splitGroups) {
    const allIds = [...sg.guestIdsByTable.values()].flat()
    const memberSet = new Set(allIds)
    const target = pickReunionTarget(tables, memberSet, 0)
    if (!target) continue
    const toMove = allIds.filter((id) => tableByGuestId.get(id) !== target.table_number)
    const neededSeats = toMove.reduce((sum, id) => sum + (guestById.get(id)?.seats ?? 1), 0)
    if (toMove.length === 0 || tableFreeCapacity(target) < neededSeats) continue
    suggestions.push({
      text: `לאחד את קבוצת "${sg.label}" — להעביר ${toMove.length} מוזמנים לשולחן ${target.table_number}`,
      moves: toMove.map((id) => ({ guestId: id, toTable: target.table_number })),
    })
  }

  // (ג) איחוד זוגות "לשבת יחד" שיושבים בנפרד
  for (const [a, b] of togetherPairs ?? []) {
    const ta = tableByGuestId.get(a)
    const tb = tableByGuestId.get(b)
    if (ta == null || tb == null || ta === tb) continue
    const guestA = guestById.get(a)
    const guestB = guestById.get(b)
    if (!guestA || !guestB) continue
    const tableA = tableByNum.get(ta)!
    const tableB = tableByNum.get(tb)!
    // מעדיפים להזיז את מי שדורש פחות מקומות אל השולחן של השני
    let mover: HallGuest, moverFrom: SeatingTable, target: SeatingTable
    if (tableFreeCapacity(tableA) >= guestB.seats) {
      mover = guestB
      moverFrom = tableB
      target = tableA
    } else if (tableFreeCapacity(tableB) >= guestA.seats) {
      mover = guestA
      moverFrom = tableA
      target = tableB
    } else {
      continue
    }
    suggestions.push({
      text: `להעביר את ${mover.full_name} משולחן ${moverFrom.table_number} לשולחן ${target.table_number} כדי לשבת עם ${
        mover.id === a ? guestB.full_name : guestA.full_name
      }`,
      moves: [{ guestId: mover.id, toTable: target.table_number }],
    })
  }

  // (ד) ילד ללא מבוגר מהמשפחה — להעביר לשולחן שבו יש בן משפחה מבוגר ומקום
  const familyOf = new Map<number, number[]>()
  for (const fam of familyGroups) {
    for (const id of fam.guestIds) {
      familyOf.set(
        id,
        fam.guestIds.filter((x) => x !== id),
      )
    }
  }
  for (const cw of childWarnings) {
    const relatives = familyOf.get(cw.childId) ?? []
    const child = guestById.get(cw.childId)
    if (!child) continue
    let target: SeatingTable | null = null
    for (const relId of relatives) {
      const relTableNum = tableByGuestId.get(relId)
      if (relTableNum == null) continue
      const relGuest = guestById.get(relId)
      if (!relGuest || relGuest.is_child) continue
      const relTable = tableByNum.get(relTableNum)
      if (relTable && tableFreeCapacity(relTable) >= child.seats) {
        target = relTable
        break
      }
    }
    if (!target) continue
    suggestions.push({
      text: `להעביר את ${cw.childName} לשולחן ${target.table_number}, לצד מבוגר מהמשפחה`,
      moves: [{ guestId: cw.childId, toTable: target.table_number }],
    })
  }

  return suggestions
}

// ---- שלב 7: תובנות שולחן בודד (לשימוש בפאנל מאפייני שולחן) --------------

export interface TableInsight {
  tableNumber: number
  capacity: number
  occupied: number
  free: number
  families: string[]
  groups: string[]
  hasProblem: boolean
}

export function computeTableInsight(
  table: SeatingTable,
  familyGroups: FamilyGroup[],
  forbiddenPairs?: PairList,
  childWarnings?: ChildWithoutFamilyWarning[],
): TableInsight {
  const occupied = table.guests.reduce((sum, g) => sum + g.seats, 0)
  const idsHere = new Set(table.guests.map((g) => g.id))

  const families = familyGroups
    .filter((fam) => fam.guestIds.some((id) => idsHere.has(id)))
    .map((fam) => fam.surname)

  const groups = [
    ...new Set(
      table.guests.map((g) => groupLabel(g.group_type)).filter((label) => !!label),
    ),
  ]

  const forbiddenSet = pairSetFrom(forbiddenPairs)
  const ids = [...idsHere]
  let hasForbiddenHere = false
  for (let i = 0; i < ids.length && !hasForbiddenHere; i++) {
    for (let j = i + 1; j < ids.length; j++) {
      if (forbiddenSet.has(pairKey(ids[i], ids[j]))) {
        hasForbiddenHere = true
        break
      }
    }
  }

  const hasChildProblemHere = (childWarnings ?? []).some(
    (cw) => cw.tableNumber === table.table_number,
  )

  return {
    tableNumber: table.table_number,
    capacity: table.capacity,
    occupied,
    free: Math.max(0, table.capacity - occupied),
    families,
    groups,
    hasProblem: occupied > table.capacity || hasForbiddenHere || hasChildProblemHere,
  }
}

// ---- שלב 8: חיפוש חכם ---------------------------------------------------

export interface SmartSearchResult {
  guestId: number
  fullName: string
  side: Side
  tableNumber: number | null
  seatIndex: number | null // אינדקס המקום סביב השולחן (אם משובץ)
  companions: string[] // שאר היושבים באותו שולחן
  freeSeatsAtTable: number | null
}

/** אותו דפוס חיפוש (includes + localeCompare('he')) כמו traySearch הקיים
 * ב-HallPage.tsx. seatIndex מחושב באותו סדר מצטבר (לפי g.seats) שכבר
 * משמש שם ל-GuestSeatChip, כדי שהתוצאה תואמת למה שרואים על המסך. */
export function smartSearch(
  query: string,
  tables: SeatingTable[],
  unassigned: HallGuest[],
): SmartSearchResult[] {
  const norm = query.trim()
  if (!norm) return []

  const results: SmartSearchResult[] = []

  for (const t of tables) {
    let idx = 0
    for (const g of t.guests) {
      if (g.full_name.includes(norm)) {
        results.push({
          guestId: g.id,
          fullName: g.full_name,
          side: g.side,
          tableNumber: t.table_number,
          seatIndex: idx,
          companions: t.guests.filter((x) => x.id !== g.id).map((x) => x.full_name),
          freeSeatsAtTable: tableFreeCapacity(t),
        })
      }
      idx += g.seats
    }
  }

  for (const g of unassigned) {
    if (g.full_name.includes(norm)) {
      results.push({
        guestId: g.id,
        fullName: g.full_name,
        side: g.side,
        tableNumber: null,
        seatIndex: null,
        companions: [],
        freeSeatsAtTable: null,
      })
    }
  }

  return results.sort((a, b) => a.fullName.localeCompare(b.fullName, 'he'))
}

// ---- שלב 9: מילוי שולחנות (Smart Fill) ----------------------------------
//
// היוריסטיקה **עצמאית וקטנה** (Best-Fit Decreasing), לא קשורה בשום צורה
// למנוע הנעול app/seating.py ולא מייבאת ממנו — רק ממומשת מחדש בהשראת
// עקרונות דומים (זוגות אסורים = חוק קשיח, אותו צד/קבוצה/together = בונוס
// רך). לא מזיזה אף מוזמן שכבר משובץ — רק ממקמת מי שברשימת "ללא שולחן".
// פותחת שולחן חדש רק אם אין מקום בשום שולחן קיים.

export interface SmartFillNewTable {
  table_number: number
  capacity: number
}

export interface SmartFillResult {
  moves: SmartMove[]
  newTables: SmartFillNewTable[]
  placedCount: number
  unplacedCount: number
}

/** שולחן-עבודה פנימי לאלגוריתם — רק המידע הדרוש לניקוד/קיבולת. */
interface FillWorkingTable {
  table_number: number
  capacity: number
  freeCapacity: number
  guestIds: Set<number>
  sides: Map<Side, number>
  groups: Map<string, number>
  isNew: boolean
}

// ניקוד "צד" (חתן/כלה): מנחה את המילוי לשמור אנשים מאותו צד יחד, ולהימנע
// מלערבב צד חתן עם צד כלה באותו שולחן — בלי לחסום. מוזמן "משותף" ניטרלי
// ומשתלב בכל שולחן בלי בונוס או קנס. הקנס רך: הוא רק משנה סדר עדיפויות,
// לעולם לא מונע הושבה (שולחן עם מקום פנוי תמיד נשאר מועמד חוקי).
const SAME_SIDE_BONUS = 2
const OPPOSITE_SIDE_PENALTY = 3

/** ניקוד התאמת הצד של מוזמן לתמהיל הצדדים שכבר יושב בשולחן. */
function sideScore(guestSide: Side, tableSides: Map<Side, number>): number {
  if (guestSide === 'shared') return 0 // משותף — משתלב בכל מקום, בלי העדפה
  const oppositeSide: Side = guestSide === 'groom' ? 'bride' : 'groom'
  const same = tableSides.get(guestSide) ?? 0
  const opposite = tableSides.get(oppositeSide) ?? 0
  return same * SAME_SIDE_BONUS - opposite * OPPOSITE_SIDE_PENALTY
}

export function computeSmartFill(
  tables: SeatingTable[],
  unassigned: HallGuest[],
  forbiddenPairs: PairList | undefined,
  togetherPairs: PairList | undefined,
  defaultCapacity: number,
  nextTableNumber: number,
): SmartFillResult {
  const forbiddenSet = pairSetFrom(forbiddenPairs)
  const togetherSet = pairSetFrom(togetherPairs)

  const working: FillWorkingTable[] = tables.map((t) => {
    const sides = new Map<Side, number>()
    const groups = new Map<string, number>()
    for (const g of t.guests) {
      sides.set(g.side, (sides.get(g.side) ?? 0) + 1)
      if (g.group_type && g.group_type !== 'other') {
        groups.set(g.group_type, (groups.get(g.group_type) ?? 0) + 1)
      }
    }
    return {
      table_number: t.table_number,
      capacity: t.capacity,
      freeCapacity: tableFreeCapacity(t),
      guestIds: new Set(t.guests.map((g) => g.id)),
      sides,
      groups,
      isNew: false,
    }
  })

  // חבורות גדולות קודם (Best-Fit Decreasing) — קל יותר למקם חבורה גדולה
  // מוקדם, לפני שהמקום הפנוי מתפזר לפירורים בין שולחנות.
  const ordered = [...unassigned].sort((a, b) => b.seats - a.seats)

  const moves: SmartMove[] = []
  const newTables: SmartFillNewTable[] = []
  let nextNum = nextTableNumber
  let placedCount = 0

  for (const g of ordered) {
    // חוק קשיח: לא לשבץ לצד מישהו שברשימת "לא לשבת יחד" איתו.
    const fitsHard = (t: FillWorkingTable) => {
      if (t.freeCapacity < g.seats) return false
      for (const otherId of t.guestIds) {
        if (forbiddenSet.has(pairKey(g.id, otherId))) return false
      }
      return true
    }

    let best: FillWorkingTable | null = null
    let bestScore = -Infinity
    for (const t of working) {
      if (!fitsHard(t)) continue
      let score = 0
      for (const otherId of t.guestIds) {
        if (togetherSet.has(pairKey(g.id, otherId))) score += 10
      }
      if (g.group_type && g.group_type !== 'other') {
        score += (t.groups.get(g.group_type) ?? 0) * 3
      }
      // צד חתן/כלה: בונוס לאותו צד, קנס רך לערבוב עם הצד הנגדי.
      score += sideScore(g.side, t.sides)
      // Best-Fit: בין שולחנות עם אותו ניקוי, מעדיפים את זה עם פחות מקום
      // פנוי שנשאר אחרי ההושבה (ממלאים שולחנות עד הסוף, לא מפזרים).
      const leftoverAfter = t.freeCapacity - g.seats
      const tieBreak = -leftoverAfter * 0.01
      const total = score + tieBreak
      if (total > bestScore) {
        bestScore = total
        best = t
      }
    }

    if (!best) {
      // חבורה גדולה מקיבולת שולחן בודד (ברירת המחדל) — לא ניתן למקם
      // אוטומטית בלי לחרוג מקיבולת; משאירים "ללא שולחן" במקום להפר חוק קשיח.
      if (g.seats > defaultCapacity) continue
      // אין מקום בשום שולחן קיים — פותחים שולחן חדש בקיבולת ברירת המחדל.
      best = {
        table_number: nextNum,
        capacity: defaultCapacity,
        freeCapacity: defaultCapacity,
        guestIds: new Set(),
        sides: new Map(),
        groups: new Map(),
        isNew: true,
      }
      working.push(best)
      newTables.push({ table_number: nextNum, capacity: defaultCapacity })
      nextNum += 1
    }

    best.freeCapacity -= g.seats
    best.guestIds.add(g.id)
    best.sides.set(g.side, (best.sides.get(g.side) ?? 0) + 1)
    if (g.group_type && g.group_type !== 'other') {
      best.groups.set(g.group_type, (best.groups.get(g.group_type) ?? 0) + 1)
    }
    moves.push({ guestId: g.id, toTable: best.table_number })
    placedCount++
  }

  return {
    moves,
    newTables,
    placedCount,
    unplacedCount: unassigned.length - placedCount,
  }
}

// ---- שלב 10: בדיקה חיה בזמן גרירה ---------------------------------------
//
// לא חוסמת את הגרירה או ה-Drop בשום צורה — רק מידע קצר (עד 2 שורות) שמוצג
// בזמן ריחוף מעל שולחן, לפני שהמוזמן בכלל שוחרר. אותה לוגיקה בדיוק (קיבולת,
// זוג אסור, ילד בלי מבוגר מהמשפחה) שכבר קיימת ב-computeTableInsight/
// computeSmartWarnings, רק ממוקדת למוזמן הספציפי שנגרר.

export interface LiveDragCheck {
  level: 'green' | 'yellow' | 'red'
  lines: string[] // עד 2 שורות קצרות
}

export function liveDragValidation(
  draggedGuest: HallGuest,
  targetTable: SeatingTable,
  forbiddenPairs: PairList | undefined,
  familyGroups: FamilyGroup[],
): LiveDragCheck {
  const lines: string[] = []
  let level: LiveDragCheck['level'] = 'green'

  const free = tableFreeCapacity(targetTable)
  if (draggedGuest.seats > free) {
    level = 'red'
    lines.push(`חריגה מקיבולת — חסרים ${draggedGuest.seats - free} מקומות`)
  }

  const forbiddenSet = pairSetFrom(forbiddenPairs)
  const forbiddenHit = targetTable.guests.find((g) => forbiddenSet.has(pairKey(draggedGuest.id, g.id)))
  if (forbiddenHit) {
    level = 'red'
    lines.push(`מסומן/ת "לא לשבת יחד" עם ${forbiddenHit.full_name}`)
  }

  if (level !== 'red' && draggedGuest.is_child) {
    const fam = familyGroups.find((f) => f.guestIds.includes(draggedGuest.id))
    if (fam) {
      const relatives = new Set(fam.guestIds.filter((id) => id !== draggedGuest.id))
      const hasAdultHere = targetTable.guests.some((g) => relatives.has(g.id) && !g.is_child)
      if (!hasAdultHere) {
        level = 'yellow'
        lines.push('אין כאן מבוגר מהמשפחה')
      }
    }
  }

  return { level, lines: lines.slice(0, 2) }
}
