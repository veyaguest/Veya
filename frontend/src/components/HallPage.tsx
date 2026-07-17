import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  analyzeConstraints,
  generateSeating,
  getHall,
  listClarifications,
  resolveClarification,
  saveHall,
} from '../api'
import type {
  AnalyzeResult,
  Clarification,
  ElementShape,
  HallElement,
  HallElementType,
  HallGuest,
  HallState,
  TableType,
} from '../types'
import { GROUP_LABELS, SIDE_LABELS } from '../types'
import {
  computeSmartFill,
  computeSmartWarnings,
  computeStats,
  computeSuggestions,
  computeTableInsight,
  detectChildrenWithoutFamily,
  detectFamilyGroups,
  detectSplitGroups,
  liveDragValidation,
  smartSearch,
  type PairList,
  type SmartMove,
  type SmartSuggestion,
} from '../seatingAdvisor'
import { SmartAssistantPanel } from './SmartAssistantPanel'

interface TableView {
  table_number: number
  x: number
  y: number
  guests: HallGuest[]
  table_type: TableType
  capacity: number
  rotation: number
  name: string
  color: string
  notes: string
  locked: boolean
}

const REL_TEXT: Record<Clarification['relation_type'], string> = {
  avoid: 'לא לשבת עם',
  together: 'לשבת עם',
}

const TABLE_TYPE_LABELS: Record<TableType, string> = {
  round: '⬤ עגול',
  square: '◼ מרובע',
  rectangle: '▭ מלבני',
  knights: '▬ אבירים',
}

const TABLE_TYPE_DEFAULT_COLOR: Record<TableType, string> = {
  round: '#c9a227',
  square: '#4a7fc9',
  rectangle: '#5fa66c',
  knights: '#8a6bc9',
}

const TABLE_COLORS = ['#c9a227', '#4a7fc9', '#5fa66c', '#c96b6b', '#8a6bc9', '#3f4756']
const ELEMENT_COLORS = ['#7fb3e0', '#e4c96b', '#8fd0a8', '#e08f8f', '#b79ae0', '#9a7b2e']

// הגדרות ברירת-מחדל לכל סוג אלמנט מיוחד (תווית, גודל, צורה, צבע).
// הגדלים כאן קטנים יחסית לגודל המפה (WORLD_W/H) — כדי שגם ברמת זום 100%
// האלמנטים ייראו פרופורציונליים לחלל האולם, לא ענקיים.
// חלק מהסוגים (head_table/gift_table/restroom/stage) מוסתרים כרגע מהסרגל
// (VISIBLE_ELEMENTS) — הקוד שלהם נשאר שלם כדי שאפשר יהיה להחזיר אותם בעתיד.
const ELEMENT_DEFS: Record<
  HallElementType,
  { label: string; width: number; height: number; shape: ElementShape; color: string }
> = {
  head_table: { label: '💍 שולחן מחותנים', width: 160, height: 42, shape: 'rectangle', color: '#c9a227' },
  dance_floor: { label: '💃 רחבת ריקודים', width: 210, height: 120, shape: 'circle', color: '#c9a227' },
  bar: { label: '🥂 בר', width: 190, height: 58, shape: 'rectangle', color: '#c9a227' },
  stage: { label: '🎤 במה', width: 148, height: 54, shape: 'rectangle', color: '#b79ae0' },
  dj: { label: '🎧 עמדת DJ', width: 150, height: 58, shape: 'rectangle', color: '#6b6355' },
  entrance: { label: '🚪 כניסה', width: 150, height: 46, shape: 'rectangle', color: '#9a7b2e' },
  gift_table: { label: '🎁 שולחן מתנות', width: 90, height: 34, shape: 'rectangle', color: '#c9a227' },
  restroom: { label: '🚻 שירותים', width: 68, height: 34, shape: 'rectangle', color: '#8c8375' },
}

// רק אלה מוצגים בסרגל ה"הוספה למפה" (לפי בקשת הבעלים — רוב המידע הזה
// כבר מופיע בסקיצת האולם שמעלים כרקע).
const VISIBLE_ELEMENTS: HallElementType[] = ['dance_floor', 'bar', 'dj', 'entrance']
const ELEMENT_SHAPES: { key: ElementShape; label: string }[] = [
  { key: 'rectangle', label: '▭' },
  { key: 'square', label: '◼' },
  { key: 'circle', label: '⬤' },
  { key: 'ellipse', label: '⬭' },
]

// גודל לוח האולם (עולם פנימי בקואורדינטות LTR, כמו Figma). אין זום/מצלמה —
// הלוח מוצג תמיד בגודל אמיתי (100%), והמאגר (viewport) נגלל סביבו באופן
// טבעי (overflow: auto) כשהאולם גדול מהמסך. כך התצוגה תמיד ברורה וקריאה.
const WORLD_W = 2000
const WORLD_H = 1400

// מספרי מקומות אפשריים לשולחן — סט סגור בלבד (לא כל מספר), לפי בקשת הבעלים.
// שולחן אבירים (מלבני ארוך) מיועד לחבורה גדולה ולכן ברירת המחדל שלו גבוהה
// יותר (24) מכל שאר סוגי השולחנות (12).
const SEAT_OPTIONS = [10, 12, 14, 16, 18, 20, 22, 24]
function defaultCapacityForType(t: TableType): number {
  return t === 'knights' ? 24 : 12
}
// נתונים ישנים (שנשמרו לפני שהוגבל מספר המקומות לסט קבוע) עלולים להכיל ערך
// שלא ברשימה — מעגלים לערך הקרוב ביותר מהסט, כדי שהתפריט הנפתח תמיד יציג
// ערך תקין.
function snapCapacity(n: number): number {
  return SEAT_OPTIONS.reduce((best, v) => (Math.abs(v - n) < Math.abs(best - n) ? v : best), SEAT_OPTIONS[0])
}

function clamp(v: number, min: number, max: number) {
  return Math.min(max, Math.max(min, v))
}

// גודל חזותי של השולחן (בפיקסלים) — נגזר ממספר המקומות, כך ש"שינוי גודל"
// קורה אוטומטית עם שינוי כמות הכיסאות (בהתאם לדרישה: "כשמספר המקומות
// משתנה, הכיסאות מתעדכנים אוטומטית להתאמת צורת השולחן").
function tableSize(type: TableType, capacity: number): { w: number; h: number } {
  if (type === 'round' || type === 'square') {
    const d = Math.round(clamp(46 + capacity * 6, 68, 190))
    return { w: d, h: d }
  }
  const hasEnds = type === 'knights'
  const rowSeats = hasEnds && capacity >= 6 ? capacity - 2 : capacity
  const topCount = Math.max(1, Math.ceil(rowSeats / 2))
  // רוחב שולחן האבירים מוגבל לטווח קרוב לשולחנות העגולים/מרובעים (68–190),
  // כך שגם בקיבולת המרבית (24) הוא לא "בולע" את הלוח — בלי לגעת במספר
  // המקומות עצמו.
  const w = Math.round(clamp(topCount * 17, 76, 200))
  return { w, h: 52 }
}

interface SeatPoint {
  left: number
  top: number
}

// מיקום כל כיסא סביב גוף השולחן, יחסית לקופסת השולחן (0,0 עד w,h).
function seatPositions(type: TableType, capacity: number, w: number, h: number): SeatPoint[] {
  const gap = 12
  if (type === 'round' || type === 'square') {
    const radius = Math.max(w, h) / 2 + gap
    const cx = w / 2
    const cy = h / 2
    return Array.from({ length: capacity }, (_, i) => {
      const angle = (i / capacity) * Math.PI * 2 - Math.PI / 2
      return { left: cx + radius * Math.cos(angle), top: cy + radius * Math.sin(angle) }
    })
  }
  // מלבני / אבירים: שתי שורות; אבירים גם עם כיסא בכל קצה.
  const hasEnds = type === 'knights'
  const ends = hasEnds && capacity >= 6 ? 2 : 0
  const rowSeats = capacity - ends
  const topCount = Math.ceil(rowSeats / 2)
  const bottomCount = rowSeats - topCount
  const pts: SeatPoint[] = []
  for (let i = 0; i < topCount; i++) {
    pts.push({ left: topCount === 1 ? w / 2 : (w * (i + 0.5)) / topCount, top: -gap })
  }
  for (let i = 0; i < bottomCount; i++) {
    pts.push({ left: bottomCount === 1 ? w / 2 : (w * (i + 0.5)) / bottomCount, top: h + gap })
  }
  if (ends >= 1) pts.push({ left: -gap, top: h / 2 })
  if (ends >= 2) pts.push({ left: w + gap, top: h / 2 })
  return pts
}

/** אייקונים קוויים נקיים למסך המובייל — במקום אימוג'ים, באותו סגנון של סרגל הצד. */
type HmIconName =
  | 'hall'
  | 'tables'
  | 'guests'
  | 'smart'
  | 'tools'
  | 'search'
  | 'plus'
  | 'round'
  | 'knights'
  | 'bar'
  | 'dance'
  | 'chuppah'
  | 'dj'
  | 'move'
  | 'edit'
  | 'save'
  | 'refresh'
  | 'copy'
  | 'trash'

function HmIcon({ name, size = 22 }: { name: HmIconName; size?: number }) {
  const common = {
    className: 'hm-icon',
    width: size,
    height: size,
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.7,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
  }
  switch (name) {
    case 'hall':
      return (
        <svg {...common}>
          <path d="M3 10.5 12 3l9 7.5" />
          <path d="M5 9.5V21h14V9.5" />
          <path d="M9.5 21v-6h5v6" />
        </svg>
      )
    case 'tables':
      return (
        <svg {...common}>
          <path d="M7 4v7m10-7v7" />
          <path d="M6 11h12l-1 5H7z" />
          <path d="M8 16v4m8-4v4" />
        </svg>
      )
    case 'guests':
      return (
        <svg {...common}>
          <circle cx="9" cy="8" r="3" />
          <path d="M3.5 20a5.5 5.5 0 0 1 11 0" />
          <path d="M16 6.5a3 3 0 0 1 0 5.8" />
          <path d="M17.5 20a5.5 5.5 0 0 0-2.5-4.6" />
        </svg>
      )
    case 'smart':
      return (
        <svg {...common}>
          <path d="M12 3.5 13.4 8l4.6 1.4-4.6 1.4L12 15.4 10.6 10.8 6 9.4 10.6 8z" />
          <path d="M18 15l.7 2.3L21 18l-2.3.7L18 21l-.7-2.3L15 18l2.3-.7z" />
        </svg>
      )
    case 'tools':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="3" />
          <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1" />
        </svg>
      )
    case 'search':
      return (
        <svg {...common}>
          <circle cx="11" cy="11" r="7" />
          <path d="m20 20-3.5-3.5" />
        </svg>
      )
    case 'plus':
      return (
        <svg {...common}>
          <path d="M12 5v14M5 12h14" />
        </svg>
      )
    case 'round':
      return (
        <svg {...common}>
          <circle cx="12" cy="12" r="7.5" />
        </svg>
      )
    case 'knights':
      return (
        <svg {...common}>
          <rect x="3.5" y="8.5" width="17" height="7" rx="2" />
        </svg>
      )
    case 'bar':
      return (
        <svg {...common}>
          <path d="M5 4h14l-7 8z" />
          <path d="M12 12v6M8 21h8" />
        </svg>
      )
    case 'dance':
      return (
        <svg {...common}>
          <path d="M9 18V6l10-2v12" />
          <circle cx="6.5" cy="18" r="2.5" />
          <circle cx="16.5" cy="16" r="2.5" />
        </svg>
      )
    case 'chuppah':
      return (
        <svg {...common}>
          <path d="M4 21V8a8 8 0 0 1 16 0v13" />
          <path d="M4 8h16M12 8v13" />
        </svg>
      )
    case 'dj':
      return (
        <svg {...common}>
          <path d="M4 13v-1a8 8 0 0 1 16 0v1" />
          <rect x="3" y="13" width="4" height="7" rx="1.5" />
          <rect x="17" y="13" width="4" height="7" rx="1.5" />
        </svg>
      )
    case 'move':
      return (
        <svg {...common}>
          <path d="M7 8H4l3-3M4 8l3 3" />
          <path d="M17 16h3l-3-3m3 3-3 3" />
          <path d="M4 8h13M20 16H7" />
        </svg>
      )
    case 'edit':
      return (
        <svg {...common}>
          <path d="M4 20h4L19 9l-4-4L4 16z" />
          <path d="m13.5 6.5 4 4" />
        </svg>
      )
    case 'save':
      return (
        <svg {...common}>
          <path d="M5 5h11l3 3v11H5z" />
          <path d="M8 5v5h7V5M8 19v-5h8v5" />
        </svg>
      )
    case 'refresh':
      return (
        <svg {...common}>
          <path d="M20 12a8 8 0 1 1-2.3-5.6" />
          <path d="M20 4v4h-4" />
        </svg>
      )
    case 'copy':
      return (
        <svg {...common}>
          <rect x="9" y="9" width="11" height="11" rx="2" />
          <path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1" />
        </svg>
      )
    case 'trash':
      return (
        <svg {...common}>
          <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" />
        </svg>
      )
  }
}

export function HallPage() {
  const [tables, setTables] = useState<TableView[]>([])
  const [unassigned, setUnassigned] = useState<HallGuest[]>([])
  const [elements, setElements] = useState<HallElement[]>([])
  const [seats, setSeats] = useState(12)
  const [warnings, setWarnings] = useState<string[]>([])
  const [selected, setSelected] = useState<number | null>(null) // מוזמן שנבחר להעברה
  const [selectedEl, setSelectedEl] = useState<string | null>(null)
  const [selectedTables, setSelectedTables] = useState<Set<number>>(new Set())
  const [dragOver, setDragOver] = useState<number | 'tray' | null>(null)
  // מוזמן שנמצא כרגע בגרירה בפועל (HTML5 DnD) — לשימוש בבדיקה חיה
  // (liveDragValidation) שמוצגת בזמן ריחוף מעל שולחן, לפני drop בפועל.
  const [draggingGuestId, setDraggingGuestId] = useState<number | null>(null)
  const [dirty, setDirty] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  // ---- מגש "ללא שולחן" (צד ימין): חיפוש כדי למצוא מוזמן ברשימה ארוכה ----
  const [traySearch, setTraySearch] = useState('')

  // ---- חוויית הושבה אחידה בטלפון ובמחשב (Auto-Fit, Bottom Sheet, ניווט תחתון) ----
  // אותה מפה נוחה בכל מכשיר: הלוח נכנס במלואו למסך, הקשה על שולחן פותחת
  // Bottom Sheet, וניווט תחתון עם 5 מדורים. במחשב הלוח ממלא את אזור התוכן
  // שלצד סרגל הצד (המיקום נקבע ב-CSS לפי רוחב המסך).
  const mobileMode = true as boolean
  const isMobileRef = useRef(true)
  const [mobileTab, setMobileTab] = useState<'hall' | 'tables' | 'guests' | 'smart' | 'tools'>('hall')
  const [sheetTable, setSheetTable] = useState<number | null>(null)
  const [sheetEdit, setSheetEdit] = useState(false)
  // כשמוסיפים מוזמן לשולחן מסוים דרך ה-Bottom Sheet: מעבר ללשונית "מוזמנים"
  // במצב "שיוך" — כל הקשה על מוזמן משבצת אותו ישירות לשולחן הזה.
  const [assignTarget, setAssignTarget] = useState<number | null>(null)
  const [fabOpen, setFabOpen] = useState(false)
  const [mobileSearch, setMobileSearch] = useState('')
  const [viewTransform, setViewTransform] = useState<string | undefined>(undefined)

  // ---- לוח האולם: בלי זום — תמיד בגודל אמיתי (100%), נגלל באופן טבעי ----
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const worldRef = useRef<HTMLDivElement | null>(null)

  // ---- מובייל: התאמת האולם אוטומטית למסך (Fit-to-Screen) ----
  // בדסקטופ scale=1 והיסט=0, כך שכל החישובים למטה מתנהגים בדיוק כמו קודם.
  // במובייל הלוח מוקטן וממורכז דרך transform על .hall-world, ולכן צריך
  // לתרגם נקודת-מגע חזרה לקואורדינטת-לוח לפי קנה-המידה וההיסט.
  const scaleRef = useRef(1)
  const offsetRef = useRef({ x: 0, y: 0 })

  const toWorld = useCallback((clientX: number, clientY: number) => {
    const vp = viewportRef.current
    if (!vp) return { x: 0, y: 0 }
    const rect = vp.getBoundingClientRect()
    const s = scaleRef.current || 1
    const off = offsetRef.current
    return {
      x: (clientX - rect.left + vp.scrollLeft - off.x) / s,
      y: (clientY - rect.top + vp.scrollTop - off.y) / s,
    }
  }, [])

  // סקיצת האולם (data URL) — רקע עדין מתחת לשולחנות.

  // סקיצת האולם (data URL) — רקע עדין מתחת לשולחנות.
  const [sketch, setSketch] = useState<string | null>(null)
  const sketchInputRef = useRef<HTMLInputElement | null>(null)

  // ---- עוזר הושבה חכם (Dock) ----
  // זוגות אילוצים שכבר מחושבים בשרת מהערות חופשיות — נשמרים כאן כדי
  // שהעוזר יוכל לבדוק אותם מיידית בצד לקוח בלי קריאת רשת נוספת.
  const [forbiddenPairs, setForbiddenPairs] = useState<PairList>([])
  const [togetherPairs, setTogetherPairs] = useState<PairList>([])
  const [smartPanelOpen, setSmartPanelOpen] = useState(false)
  const [smartSearchQuery, setSmartSearchQuery] = useState('')
  // הצעה/מהלכים "בהמתנה לאישור" — אף פעם לא מוחלת לבד. רק לחיצה מפורשת על
  // "אשר" מיישמת את כל המהלכים בבת אחת (בדיוק כמו גרירה ידנית, אותה
  // סמנטיקה: מקומי בלבד, dirty=true); המשתמש עדיין צריך ללחוץ "שמירת
  // המפה" כדי לשמור בשרת. diff הוא רק לתצוגה קריאה (שם + מאיפה לאיפה).
  const [pendingProposal, setPendingProposal] = useState<{
    text: string
    moves: SmartMove[]
    diff: { guestId: number; guestName: string; fromTable: number | null; toTable: number }[]
    // שולחנות חדשים שצריך ליצור לפני שמפעילים את ה-moves (רק "מלא שולחנות"
    // עשוי להשתמש בזה — הצעות רגילות אף פעם לא פותחות שולחן חדש).
    newTables?: { table_number: number; capacity: number }[]
  } | null>(null)

  // ---- אילוצים מההערות (לולאת הבהרות) ----
  const [clarifications, setClarifications] = useState<Clarification[]>([])
  const [analyzeSummary, setAnalyzeSummary] = useState<AnalyzeResult | null>(null)
  const [analyzing, setAnalyzing] = useState(false)

  type DragState =
    | { kind: 'table-group'; items: { id: number; startX: number; startY: number }[]; startWorldX: number; startWorldY: number }
    | { kind: 'table-rotate'; id: number; cx: number; cy: number }
    | { kind: 'element'; id: string; dx: number; dy: number }
    | { kind: 'resize'; id: string; startX: number; startY: number; startW: number; startH: number; lockSquare: boolean }
    | { kind: 'rotate'; id: string; cx: number; cy: number }
  const dragRef = useRef<DragState | null>(null)
  // ביצועים בגרירת שולחנות: במקום לעדכן state בכל תזוזה (שמרנדר מחדש את כל
  // השולחנות), מזיזים את צמתי ה-DOM ישירות דרך transform בתוך requestAnimationFrame,
  // ומעדכנים את ה-state פעם אחת בסיום הגרירה (pointerup). כך גרירה חלקה גם עם
  // 100+ שולחנות.
  const dragRafRef = useRef<number | null>(null)
  const dragPendingRef = useRef<{ dx: number; dy: number } | null>(null)
  const dragNodesRef = useRef<Map<number, HTMLElement>>(new Map())
  const movedRef = useRef(false)
  // מונה קטן להוספות רצופות (שולחן/אלמנט) — כדי שכשלוחצים "הוסף" כמה פעמים
  // ברצף הפריטים ייפלו במדרגה קלה זה מזה, ולא יתערמו זה על גבי זה במרכז.
  const placeSeqRef = useRef(0)
  function nextPlaceOffset() {
    const seq = placeSeqRef.current % 8
    placeSeqRef.current += 1
    return seq * 22
  }

  // מספר השולחן הבא — ref ולא חישוב מ-tables.map בזמן הלחיצה, כי לחיצות
  // כפולות/מהירות על "הוסף שולחן" יכולות לקרוא ל-addTable פעמיים לפני
  // שהרינדור התעדכן, ואז שני השולחנות "יחשבו" שאותו המספר פנוי.
  const nextTableNumRef = useRef(1)

  const applyState = useCallback((h: HallState) => {
    setTables(
      h.tables.map((t) => ({
        table_number: t.table_number,
        x: t.x,
        y: t.y,
        guests: t.guests,
        table_type: t.table_type ?? 'round',
        capacity: snapCapacity(t.capacity ?? h.seats_per_table),
        rotation: t.rotation ?? 0,
        name: t.name ?? '',
        color: t.color ?? '',
        notes: t.notes ?? '',
        locked: t.locked ?? false,
      })),
    )
    nextTableNumRef.current = h.tables.length
      ? Math.max(...h.tables.map((t) => t.table_number)) + 1
      : 1
    setUnassigned(h.unassigned)
    setElements(
      (h.elements ?? []).map((el) => ({
        ...el,
        shape: el.shape ?? ELEMENT_DEFS[el.type]?.shape ?? 'rectangle',
        color: el.color ?? '',
      })),
    )
    setSeats(snapCapacity(h.seats_per_table))
    setWarnings(h.warnings)
    setSketch(h.sketch ?? null)
    setForbiddenPairs(h.forbidden_pairs ?? [])
    setTogetherPairs(h.together_pairs ?? [])
    setDirty(false)
  }, [])

  const load = useCallback(async () => {
    setError('')
    try {
      applyState(await getHall())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לטעון את מפת האולם, ננסה שוב')
    }
  }, [applyState])

  const loadClarifications = useCallback(async () => {
    try {
      setClarifications(await listClarifications())
    } catch {
      /* שקט — לא חוסם את מפת האולם */
    }
  }, [])

  useEffect(() => {
    load()
    loadClarifications()
  }, [load, loadClarifications])

  // ---- מובייל: Fit-to-Screen — האולם כולו מוקטן וממורכז כדי להיראות במלואו ----
  // מחשב את תיבת-התוכן (כל השולחנות + האלמנטים) ומקטין/ממרכז אותה לגודל המסך,
  // בלי גלילה ובלי זום ידני. בדסקטופ הפונקציה יוצאת מיד (scale נשאר 1).
  const recomputeFit = useCallback(() => {
    const vp = viewportRef.current
    if (!isMobileRef.current || !vp) {
      scaleRef.current = 1
      offsetRef.current = { x: 0, y: 0 }
      return
    }
    const cw = vp.clientWidth
    const ch = vp.clientHeight
    if (cw === 0 || ch === 0) return
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    const pad = 30 // שוליים סביב שולחן (כיסאות/מספר) בקואורדינטות-לוח
    for (const t of tables) {
      const { w, h } = tableSize(t.table_type, t.capacity)
      minX = Math.min(minX, t.x - pad)
      minY = Math.min(minY, t.y - pad)
      maxX = Math.max(maxX, t.x + w + pad)
      maxY = Math.max(maxY, t.y + h + pad)
    }
    for (const el of elements) {
      minX = Math.min(minX, el.x)
      minY = Math.min(minY, el.y)
      maxX = Math.max(maxX, el.x + el.width)
      maxY = Math.max(maxY, el.y + el.height)
    }
    if (!isFinite(minX)) {
      // אין תוכן — פינת הלוח בפינה עליונה, בלי הקטנה.
      scaleRef.current = 1
      offsetRef.current = { x: 20, y: 20 }
      setViewTransform('translate(20px, 20px) scale(1)')
      return
    }
    const margin = 18 // רווח לבן בקצוות המסך (בפיקסלי-מסך)
    const contentW = Math.max(1, maxX - minX)
    const contentH = Math.max(1, maxY - minY)
    const s = clamp(
      Math.min((cw - margin * 2) / contentW, (ch - margin * 2) / contentH),
      0.2,
      1.4,
    )
    const ox = (cw - contentW * s) / 2 - minX * s
    const oy = (ch - contentH * s) / 2 - minY * s
    scaleRef.current = s
    offsetRef.current = { x: ox, y: oy }
    setViewTransform(`translate(${ox}px, ${oy}px) scale(${s})`)
  }, [tables, elements])

  useEffect(() => {
    if (!mobileMode) {
      setViewTransform(undefined)
      scaleRef.current = 1
      offsetRef.current = { x: 0, y: 0 }
      return
    }
    recomputeFit()
  }, [mobileMode, mobileTab, recomputeFit])

  useEffect(() => {
    if (!mobileMode) return
    const vp = viewportRef.current
    if (!vp || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => recomputeFit())
    ro.observe(vp)
    return () => ro.disconnect()
  }, [mobileMode, mobileTab, recomputeFit])

  // אין יותר זום בדסקטופ — הלוח נגלל באופן טבעי (גלגלת/מגע רגילים דרך
  // overflow: auto של המאגר), בלי מאזינים מותאמים-אישית.

  // ---- קיצורי מקלדת: Delete למחיקה, Esc לביטול בחירה, Ctrl/Cmd+D לשכפול ----
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const tag = (document.activeElement?.tagName || '').toLowerCase()
      if (tag === 'input' || tag === 'textarea') return
      if (e.key === 'Escape') {
        setSelectedTables(new Set())
        setSelectedEl(null)
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (selectedTables.size > 0) {
          selectedTables.forEach((n) => deleteTable(n))
        } else if (selectedEl) {
          removeElement(selectedEl)
        }
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'd') {
        if (selectedEl || selectedTables.size === 1) {
          e.preventDefault()
          if (selectedEl) duplicateElement(selectedEl)
          else duplicateTable([...selectedTables][0])
        }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTables, selectedEl, tables, elements])

  async function onAnalyze() {
    setAnalyzing(true)
    setError('')
    try {
      setAnalyzeSummary(await analyzeConstraints())
      await loadClarifications()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לקרוא את ההערות, ננסה שוב')
    } finally {
      setAnalyzing(false)
    }
  }

  async function onResolve(id: number, chosenGuestId: number | null) {
    try {
      setAnalyzeSummary(await resolveClarification(id, chosenGuestId))
      await loadClarifications()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לשמור את הבחירה, נסו שוב')
    }
  }

  // אין יותר הצמדה לרשת — מיקום חופשי (מעוגל לפיקסל שלם).
  function snapVal(v: number) {
    return Math.round(v)
  }

  // ---- לחיצה על רקע הלוח: ביטול בחירה בלבד (הגלילה טבעית של הדפדפן) ----
  function onWorldPointerDown(e: React.PointerEvent) {
    if (e.target !== e.currentTarget) return // קליק על ילד (שולחן/אלמנט) — מטופל בנפרד
    setSelectedTables(new Set())
    setSelectedEl(null)
  }

  // ---- גרירת שולחן (בודד או קבוצה נבחרת) ----
  function onTablePointerDown(e: React.PointerEvent, tnum: number) {
    e.stopPropagation()
    const t = tables.find((x) => x.table_number === tnum)
    if (!t) return
    const activeSet = selectedTables.has(tnum) && selectedTables.size > 1 ? selectedTables : new Set([tnum])
    const movable = tables.filter((x) => activeSet.has(x.table_number) && !x.locked)
    if (movable.length === 0) return
    const w = toWorld(e.clientX, e.clientY)
    dragRef.current = {
      kind: 'table-group',
      items: movable.map((x) => ({ id: x.table_number, startX: x.x, startY: x.y })),
      startWorldX: w.x,
      startWorldY: w.y,
    }
    // ממפים את צמתי ה-DOM של השולחנות הנגררים כדי להזיז אותם ישירות (בלי re-render).
    const nodes = new Map<number, HTMLElement>()
    const world = worldRef.current
    movable.forEach((x) => {
      const node = world?.querySelector(`[data-tnum="${x.table_number}"]`)
      if (node) nodes.set(x.table_number, node as HTMLElement)
    })
    dragNodesRef.current = nodes
    dragPendingRef.current = null
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  function onTableRotatePointerDown(e: React.PointerEvent, tnum: number) {
    e.stopPropagation()
    const graphic = (e.currentTarget as HTMLElement).parentElement
    if (!graphic) return
    const r = graphic.getBoundingClientRect()
    dragRef.current = { kind: 'table-rotate', id: tnum, cx: r.left + r.width / 2, cy: r.top + r.height / 2 }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  function onElementPointerDown(e: React.PointerEvent, id: string) {
    e.stopPropagation()
    const el = elements.find((x) => x.id === id)
    if (!el) return
    setSelectedEl(id)
    setSelectedTables(new Set())
    if (el.locked) return
    const w = toWorld(e.clientX, e.clientY)
    dragRef.current = { kind: 'element', id, dx: w.x - el.x, dy: w.y - el.y }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  function onResizePointerDown(e: React.PointerEvent, id: string) {
    e.stopPropagation()
    const el = elements.find((x) => x.id === id)
    if (!el) return
    dragRef.current = {
      kind: 'resize',
      id,
      startX: e.clientX,
      startY: e.clientY,
      startW: el.width,
      startH: el.height,
      lockSquare: el.shape === 'square' || el.shape === 'circle',
    }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  function onRotatePointerDown(e: React.PointerEvent, id: string) {
    e.stopPropagation()
    const el = elements.find((x) => x.id === id)
    if (!el) return
    const vp = viewportRef.current
    if (!vp) return
    const rect = vp.getBoundingClientRect()
    // מרכז האלמנט בקואורדינטות-מסך = מוצא-הלוח על המסך (בניכוי גלילה) + מיקום.
    dragRef.current = {
      kind: 'rotate',
      id,
      cx: rect.left - vp.scrollLeft + el.x + el.width / 2,
      cy: rect.top - vp.scrollTop + el.y + el.height / 2,
    }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  function onCanvasPointerMove(e: React.PointerEvent) {
    const drag = dragRef.current
    if (!drag) return
    movedRef.current = true

    if (drag.kind === 'table-group') {
      // גרירה מהירה: מזיזים את צמתי ה-DOM ישירות (transform) בתוך rAF, בלי
      // לגעת ב-state. המיקום הסופי נשמר ל-state רק ב-pointerup.
      const w = toWorld(e.clientX, e.clientY)
      dragPendingRef.current = { dx: w.x - drag.startWorldX, dy: w.y - drag.startWorldY }
      if (dragRafRef.current == null) {
        dragRafRef.current = requestAnimationFrame(() => {
          dragRafRef.current = null
          const p = dragPendingRef.current
          if (!p) return
          for (const item of drag.items) {
            const node = dragNodesRef.current.get(item.id)
            if (!node) continue
            const ox = snapVal(Math.max(0, item.startX + p.dx)) - item.startX
            const oy = snapVal(Math.max(0, item.startY + p.dy)) - item.startY
            node.style.transform = `translate(${ox}px, ${oy}px)`
          }
        })
      }
      return // בלי setState / setDirty בזמן הגרירה — זה קורה פעם אחת ב-pointerup
    } else if (drag.kind === 'table-rotate') {
      const deg = (Math.atan2(e.clientY - drag.cy, e.clientX - drag.cx) * 180) / Math.PI + 90
      setTables((prev) =>
        prev.map((t) => (t.table_number === drag.id ? { ...t, rotation: Math.round(deg) } : t)),
      )
    } else if (drag.kind === 'element') {
      const w = toWorld(e.clientX, e.clientY)
      const x = snapVal(Math.max(0, w.x - drag.dx))
      const y = snapVal(Math.max(0, w.y - drag.dy))
      setElements((prev) => prev.map((el) => (el.id === drag.id ? { ...el, x, y } : el)))
    } else if (drag.kind === 'resize') {
      // תזוזת-מסך → תזוזת-לוח: בדסקטופ 1:1, במובייל מחולק בקנה-המידה.
      const s = scaleRef.current || 1
      const dx = (e.clientX - drag.startX) / s
      const dy = (e.clientY - drag.startY) / s
      let w = Math.max(40, drag.startW + dx)
      let h = Math.max(30, drag.startH + dy)
      if (drag.lockSquare) {
        const s = Math.max(w, h)
        w = s
        h = s
      }
      setElements((prev) => prev.map((el) => (el.id === drag.id ? { ...el, width: w, height: h } : el)))
    } else if (drag.kind === 'rotate') {
      const deg = (Math.atan2(e.clientY - drag.cy, e.clientX - drag.cx) * 180) / Math.PI + 90
      setElements((prev) => prev.map((el) => (el.id === drag.id ? { ...el, rotation: Math.round(deg) } : el)))
    }
    setDirty(true)
  }

  function onCanvasPointerUp() {
    const drag = dragRef.current
    // סיום גרירת שולחנות: משקפים את המיקום הסופי ל-state (פעם אחת) ומנקים
    // את ה-transform הזמני. React מעדכן left/top באותו tick — בלי ריצוד.
    if (drag && drag.kind === 'table-group') {
      if (dragRafRef.current != null) {
        cancelAnimationFrame(dragRafRef.current)
        dragRafRef.current = null
      }
      const p = dragPendingRef.current
      if (p && (p.dx !== 0 || p.dy !== 0)) {
        setTables((prev) =>
          prev.map((t) => {
            const item = drag.items.find((i) => i.id === t.table_number)
            if (!item) return t
            return {
              ...t,
              x: snapVal(Math.max(0, item.startX + p.dx)),
              y: snapVal(Math.max(0, item.startY + p.dy)),
            }
          }),
        )
        setDirty(true)
      }
      for (const node of dragNodesRef.current.values()) node.style.transform = ''
      dragNodesRef.current.clear()
      dragPendingRef.current = null
    }
    dragRef.current = null
    movedRef.current = false
  }

  // ---- שולחנות: הוספה / שכפול / מחיקה / עדכון שדה ----
  function addTable(type: TableType = 'round') {
    const rect = viewportRef.current?.getBoundingClientRect()
    const center = toWorld(
      (rect?.left ?? 0) + (rect?.width ?? 400) / 2,
      (rect?.top ?? 0) + (rect?.height ?? 300) / 2,
    )
    const nextNum = nextTableNumRef.current
    nextTableNumRef.current += 1
    const off = nextPlaceOffset()
    const capacity = defaultCapacityForType(type)
    const { w, h } = tableSize(type, capacity)
    const t: TableView = {
      table_number: nextNum,
      x: Math.max(0, Math.round(center.x - w / 2 + off)),
      y: Math.max(0, Math.round(center.y - h / 2 + off)),
      guests: [],
      table_type: type,
      capacity,
      rotation: 0,
      name: '',
      color: '',
      notes: '',
      locked: false,
    }
    setTables((prev) => [...prev, t])
    setSelectedTables(new Set([nextNum]))
    setSelectedEl(null)
    setDirty(true)
  }

  function duplicateTable(tnum: number) {
    const src = tables.find((t) => t.table_number === tnum)
    if (!src) return
    const nextNum = nextTableNumRef.current
    nextTableNumRef.current += 1
    const copy: TableView = { ...src, table_number: nextNum, x: src.x + 30, y: src.y + 30, guests: [], locked: false }
    setTables((prev) => [...prev, copy])
    setUnassigned((prev) => [...prev, ...src.guests])
    setSelectedTables(new Set([nextNum]))
    setDirty(true)
  }

  function deleteTable(tnum: number) {
    const src = tables.find((t) => t.table_number === tnum)
    setTables((prev) => prev.filter((t) => t.table_number !== tnum))
    if (src && src.guests.length) setUnassigned((prev) => [...prev, ...src.guests])
    setSelectedTables((prev) => {
      const next = new Set(prev)
      next.delete(tnum)
      return next
    })
    setDirty(true)
  }

  function updateTable(tnum: number, patch: Partial<TableView>) {
    setTables((prev) => prev.map((t) => (t.table_number === tnum ? { ...t, ...patch } : t)))
    setDirty(true)
  }

  function renumberTable(oldNum: number, raw: string) {
    const newNum = Math.max(1, Math.round(Number(raw)) || oldNum)
    if (newNum === oldNum) return
    if (tables.some((t) => t.table_number === newNum)) {
      setError(`מספר שולחן ${newNum} כבר תפוס — בחרו מספר אחר`)
      return
    }
    setError('')
    setTables((prev) => prev.map((t) => (t.table_number === oldNum ? { ...t, table_number: newNum } : t)))
    setSelectedTables(new Set([newNum]))
    nextTableNumRef.current = Math.max(nextTableNumRef.current, newNum + 1)
    setDirty(true)
  }

  function bumpCapacity(tnum: number, delta: number) {
    const t = tables.find((x) => x.table_number === tnum)
    if (!t) return
    // דילוג בתוך סט המספרים הקבוע (10,12,...,24) ולא בכל מספר בודד.
    const curIdx = SEAT_OPTIONS.indexOf(t.capacity)
    const nextIdx = clamp((curIdx === -1 ? 0 : curIdx) + delta, 0, SEAT_OPTIONS.length - 1)
    updateTable(tnum, { capacity: SEAT_OPTIONS[nextIdx] })
  }

  // ---- אלמנטים (רחבת ריקודים / בר / DJ / כניסה / חופה) ----
  // labelOverride מאפשר להוסיף אלמנט עם תווית מותאמת (למשל "חופה") על בסיס
  // צורת/גודל אלמנט קיים, בלי להוסיף סוג חדש לסכימת השרת.
  function addElement(type: HallElementType, labelOverride?: string) {
    const def = ELEMENT_DEFS[type]
    const rect = viewportRef.current?.getBoundingClientRect()
    const center = toWorld(
      (rect?.left ?? 0) + (rect?.width ?? 400) / 2,
      (rect?.top ?? 0) + (rect?.height ?? 300) / 2,
    )
    const off = nextPlaceOffset()
    const el: HallElement = {
      id: `${type}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      type,
      x: Math.max(0, Math.round(center.x - def.width / 2 + off)),
      y: Math.max(0, Math.round(center.y - def.height / 2 + off)),
      width: def.width,
      height: def.height,
      rotation: 0,
      locked: false,
      label: labelOverride ?? def.label,
      shape: def.shape,
      // ללא צבע מותאם כברירת מחדל — כך האלמנט מקבל את המראה המעוצב מלוח
      // ההשראה (themed). הצבע נקבע רק כשהזוג בוחר גוון ידני בסרגל.
      color: '',
    }
    setElements((prev) => [...prev, el])
    setSelectedEl(el.id)
    setSelectedTables(new Set())
    setDirty(true)
  }

  function removeElement(id: string) {
    setElements((prev) => prev.filter((el) => el.id !== id))
    if (selectedEl === id) setSelectedEl(null)
    setDirty(true)
  }

  function toggleElementLock(id: string) {
    setElements((prev) => prev.map((el) => (el.id === id ? { ...el, locked: !el.locked } : el)))
    setDirty(true)
  }

  function duplicateElement(id: string) {
    setElements((prev) => {
      const src = prev.find((el) => el.id === id)
      if (!src) return prev
      const copy: HallElement = {
        ...src,
        id: `${src.type}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
        x: src.x + 24,
        y: src.y + 24,
        locked: false,
      }
      setSelectedEl(copy.id)
      return [...prev, copy]
    })
    setDirty(true)
  }

  function updateElement(id: string, patch: Partial<HallElement>) {
    setElements((prev) => prev.map((el) => (el.id === id ? { ...el, ...patch } : el)))
    setDirty(true)
  }

  // ---- העברת מוזמן ----
  function moveGuestToTable(guestId: number, targetTable: number | null) {
    let moving: HallGuest | undefined
    const nextTables = tables.map((t) => {
      const found = t.guests.find((g) => g.id === guestId)
      if (found) moving = found
      return { ...t, guests: t.guests.filter((g) => g.id !== guestId) }
    })
    let nextUnassigned = unassigned.filter((g) => g.id !== guestId)
    if (!moving) moving = unassigned.find((g) => g.id === guestId)
    if (!moving) return

    if (targetTable === null) {
      nextUnassigned = [...nextUnassigned, moving]
    } else {
      const idx = nextTables.findIndex((t) => t.table_number === targetTable)
      if (idx >= 0) nextTables[idx] = { ...nextTables[idx], guests: [...nextTables[idx].guests, moving] }
    }
    setTables(nextTables)
    setUnassigned(nextUnassigned)
    setSelected(null)
    setDirty(true)
  }

  // מיישם כמה מהלכי-הזזה בבת אחת (הצעה מהעוזר החכם, למשל "איחוד משפחת כהן"
  // או "מלא שולחנות"). בנוי בנפרד מ-moveGuestToTable ולא כלולאה שקוראת לו:
  // קריאה בלולאה הייתה קוראת בכל איטרציה את אותו tables/unassigned "מיושן"
  // מסגירת ה-render הנוכחית (React מקבץ עדכוני state), כך שרק המהלך האחרון
  // היה בפועל נשמר. כאן בונים את המצב הבא פעם אחת, על סמך כל המהלכים יחד —
  // עדיין ללא קריאת רשת, אותה סמנטיקה בדיוק (dirty=true, שמירה בפועל רק
  // ב"שמירת המפה"). newTables אופציונלי — נוצרים לפני שהמהלכים מיושמים,
  // כדי ש"מלא שולחנות" יוכל לפתוח שולחן חדש בתוך אותה תצוגה מקדימה/אישור.
  function applyMoves(moves: SmartMove[], newTables?: { table_number: number; capacity: number }[]) {
    if (moves.length === 0 && (!newTables || newTables.length === 0)) return
    let nextTables = tables.map((t) => ({ ...t, guests: [...t.guests] }))

    if (newTables && newTables.length > 0) {
      const rect = viewportRef.current?.getBoundingClientRect()
      const center = toWorld(
        (rect?.left ?? 0) + (rect?.width ?? 400) / 2,
        (rect?.top ?? 0) + (rect?.height ?? 300) / 2,
      )
      newTables.forEach((nt) => {
        const { w, h } = tableSize('round', nt.capacity)
        const off = nextPlaceOffset()
        nextTables.push({
          table_number: nt.table_number,
          x: Math.max(0, Math.round(center.x - w / 2 + off)),
          y: Math.max(0, Math.round(center.y - h / 2 + off)),
          guests: [],
          table_type: 'round',
          capacity: nt.capacity,
          rotation: 0,
          name: '',
          color: '',
          notes: '',
          locked: false,
        })
      })
      nextTableNumRef.current = Math.max(
        nextTableNumRef.current,
        ...newTables.map((nt) => nt.table_number + 1),
      )
    }

    let nextUnassigned = [...unassigned]
    for (const { guestId, toTable } of moves) {
      let moving: HallGuest | undefined
      nextUnassigned = nextUnassigned.filter((g) => {
        if (g.id === guestId) {
          moving = g
          return false
        }
        return true
      })
      nextTables = nextTables.map((t) => {
        const found = t.guests.find((g) => g.id === guestId)
        if (found) moving = found
        return { ...t, guests: t.guests.filter((g) => g.id !== guestId) }
      })
      if (!moving) continue
      const idx = nextTables.findIndex((t) => t.table_number === toTable)
      if (idx >= 0) nextTables[idx] = { ...nextTables[idx], guests: [...nextTables[idx].guests, moving] }
    }
    setTables(nextTables)
    setUnassigned(nextUnassigned)
    setDirty(true)
  }

  function onGuestClick(e: React.MouseEvent, guestId: number) {
    e.stopPropagation()
    setSelected((cur) => (cur === guestId ? null : guestId))
  }

  function onTableClick(e: React.MouseEvent, tnum: number) {
    e.stopPropagation()
    if (movedRef.current) return // זו הייתה גרירה, לא קליק לבחירה
    if (selected !== null) {
      moveGuestToTable(selected, tnum)
      return
    }
    // במובייל: הקשה על שולחן פותחת Bottom Sheet עם כל הפרטים והפעולות.
    if (isMobileRef.current) {
      setSheetTable(tnum)
      setSheetEdit(false)
      return
    }
    setSelectedEl(null)
    setSelectedTables((prev) => {
      if (e.shiftKey) {
        const next = new Set(prev)
        if (next.has(tnum)) next.delete(tnum)
        else next.add(tnum)
        return next
      }
      return prev.size === 1 && prev.has(tnum) ? new Set() : new Set([tnum])
    })
  }

  function onTrayClick() {
    if (selected !== null) moveGuestToTable(selected, null)
  }

  // ---- גרירת מוזמן אמיתית (HTML5 drag & drop) ----
  function onGuestDragStart(e: React.DragEvent, guestId: number) {
    e.dataTransfer.setData('text/plain', String(guestId))
    e.dataTransfer.effectAllowed = 'move'
    setSelected(null)
    setDraggingGuestId(guestId)
  }

  function onGuestDragEnd() {
    setDraggingGuestId(null)
  }

  function onDropTo(e: React.DragEvent, target: number | null) {
    e.preventDefault()
    const gid = Number(e.dataTransfer.getData('text/plain'))
    if (!Number.isNaN(gid)) moveGuestToTable(gid, target)
    setDragOver(null)
    setDraggingGuestId(null)
  }

  // ---- סקיצת האולם ----
  function onPickSketch(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setError('יש לבחור קובץ תמונה (JPG/PNG).')
      return
    }
    if (file.size > 4 * 1024 * 1024) {
      setError('התמונה גדולה מדי (עד 4MB). נסו תמונה קטנה יותר.')
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      setSketch(typeof reader.result === 'string' ? reader.result : null)
      setDirty(true)
    }
    reader.readAsDataURL(file)
  }

  function removeSketch() {
    setSketch(null)
    setDirty(true)
  }

  async function onSave() {
    setLoading(true)
    setError('')
    try {
      const payload = tables.map((t) => ({
        table_number: t.table_number,
        x: t.x,
        y: t.y,
        guest_ids: t.guests.map((g) => g.id),
        table_type: t.table_type,
        capacity: t.capacity,
        rotation: t.rotation,
        name: t.name,
        color: t.color,
        notes: t.notes,
        locked: t.locked,
      }))
      applyState(await saveHall(payload, seats, elements, sketch ?? ''))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לשמור את המפה, נסו שוב')
    } finally {
      setLoading(false)
    }
  }

  async function onRegenerate() {
    setLoading(true)
    setError('')
    try {
      const res = await generateSeating({ seats_per_table: seats, persist: true })
      if (!res.hard_ok) {
        setError('לא הצלחנו לסדר את כולם בלי להתנגש בהעדפות — כדאי להוסיף מקומות לשולחן.')
      }
      applyState(await getHall())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לסדר כרגע, ננסה שוב')
    } finally {
      setLoading(false)
    }
  }

  const soleSelectedNum = selectedTables.size === 1 ? [...selectedTables][0] : null
  const soleSelected = soleSelectedNum != null ? tables.find((t) => t.table_number === soleSelectedNum) ?? null : null
  const soleSelectedEl = selectedEl ? elements.find((el) => el.id === selectedEl) ?? null : null

  // מספרי שולחנות המוזכרים באזהרות (למשל זוג "לא לשבת יחד") — לסימון חזותי
  // ישירות על השולחן, לא רק ברשימת האזהרות הכללית.
  const warnTables = new Set(
    warnings
      .map((w) => w.match(/^שולחן (\d+):/)?.[1])
      .filter((n): n is string => !!n)
      .map(Number),
  )

  // רשימת "ללא שולחן" ממוינת לפי שם (קל יותר לסרוק) ומסוננת לפי חיפוש —
  // כדי שברשימות ארוכות (100+ מוזמנים) אפשר יהיה למצוא מישהו מיד.
  const traySearchNorm = traySearch.trim()
  const visibleUnassigned = [...unassigned]
    .filter((g) => !traySearchNorm || g.full_name.includes(traySearchNorm))
    .sort((a, b) => a.full_name.localeCompare(b.full_name, 'he'))

  // ---- עוזר הושבה חכם: חישובים נגזרים (טהורים, בלי קריאת רשת) ----
  // כל הפונקציות מ-seatingAdvisor.ts הן O(n) — מחושבות מחדש רק כשמשהו
  // רלוונטי משתנה (useMemo), לא בכל רינדור/כל פיקסל גרירה.
  const allGuestsForFamily = useMemo(
    () => [...tables.flatMap((t) => t.guests), ...unassigned],
    [tables, unassigned],
  )
  const familyGroups = useMemo(() => detectFamilyGroups(allGuestsForFamily), [allGuestsForFamily])
  const splitGroups = useMemo(() => detectSplitGroups(tables), [tables])
  const childWarnings = useMemo(
    () => detectChildrenWithoutFamily(tables, familyGroups),
    [tables, familyGroups],
  )
  const smartStats = useMemo(() => computeStats(tables, unassigned, seats), [tables, unassigned, seats])
  const smartWarnings = useMemo(
    () => computeSmartWarnings(tables, familyGroups, splitGroups, childWarnings, togetherPairs),
    [tables, familyGroups, splitGroups, childWarnings, togetherPairs],
  )
  const smartSuggestions = useMemo(
    () => computeSuggestions(tables, familyGroups, splitGroups, childWarnings, togetherPairs),
    [tables, familyGroups, splitGroups, childWarnings, togetherPairs],
  )
  const smartSearchResults = useMemo(
    () => (smartSearchQuery.trim() ? smartSearch(smartSearchQuery, tables, unassigned) : []),
    [smartSearchQuery, tables, unassigned],
  )
  const soleSelectedInsight = useMemo(
    () =>
      soleSelected ? computeTableInsight(soleSelected, familyGroups, forbiddenPairs, childWarnings) : null,
    [soleSelected, familyGroups, forbiddenPairs, childWarnings],
  )

  // נקודת-סטטוס צבעונית לכל שולחן (ירוק/צהוב/אדום) — מידע בלבד, לא חוסמת
  // כלום. אדום = בעיה קשה (חריגת קיבולת/זוג אסור/ילד בלי מבוגר מהמשפחה),
  // צהוב = יש המלצה/אזהרה רכה (משפחה או קבוצה מפוצלת וכו'), ירוק = תקין.
  const redFromSmart = new Set(
    smartWarnings.filter((w) => w.severity === 'red').flatMap((w) => w.tableNumbers),
  )
  const yellowFromSmart = new Set(
    smartWarnings.filter((w) => w.severity === 'yellow').flatMap((w) => w.tableNumbers),
  )
  const tableStatus = new Map<number, 'red' | 'yellow' | 'green'>()
  for (const t of tables) {
    const used = t.guests.reduce((s, g) => s + g.seats, 0)
    const isRed = used > t.capacity || warnTables.has(t.table_number) || redFromSmart.has(t.table_number)
    const isYellow = !isRed && yellowFromSmart.has(t.table_number)
    tableStatus.set(t.table_number, isRed ? 'red' : isYellow ? 'yellow' : 'green')
  }

  // האורח שבפועל נגרר כרגע (אם יש) — לשימוש בבדיקה החיה בזמן ריחוף מעל שולחן.
  const draggedGuestForLive = useMemo(() => {
    if (draggingGuestId == null) return undefined
    return (
      tables.flatMap((t) => t.guests).find((g) => g.id === draggingGuestId) ??
      unassigned.find((g) => g.id === draggingGuestId)
    )
  }, [draggingGuestId, tables, unassigned])

  // הצעה נכנסת ל"המתנה לאישור" בלבד — לא מזיזה אף אורח עד לחיצה מפורשת על
  // "אשר". "בטל" רק מנקה את ה-state, אפס שינוי בפועל.
  // בונה "diff" קריא (שם מוזמן + מאיפה לאיפה) לתצוגה מקדימה, משותף לכל
  // סוגי ההצעות (הצעה בודדת מ-computeSuggestions או "מלא שולחנות").
  function buildProposalDiff(
    moves: SmartMove[],
  ): { guestId: number; guestName: string; fromTable: number | null; toTable: number }[] {
    const guestName = new Map<number, string>()
    const guestFromTable = new Map<number, number | null>()
    for (const t of tables) {
      for (const g of t.guests) {
        guestName.set(g.id, g.full_name)
        guestFromTable.set(g.id, t.table_number)
      }
    }
    for (const g of unassigned) {
      guestName.set(g.id, g.full_name)
      guestFromTable.set(g.id, null)
    }
    return moves.map((m) => ({
      guestId: m.guestId,
      guestName: guestName.get(m.guestId) ?? `מוזמן #${m.guestId}`,
      fromTable: guestFromTable.get(m.guestId) ?? null,
      toTable: m.toTable,
    }))
  }

  function onProposeSuggestion(s: SmartSuggestion) {
    setPendingProposal({ text: s.text, moves: s.moves, diff: buildProposalDiff(s.moves) })
  }

  // "מלא שולחנות" — Best-Fit Decreasing עצמאי (seatingAdvisor.ts), רק על
  // מי שב"ללא שולחן"; לא מזיז אף מוזמן שכבר משובץ. גם זה רק ממלא
  // pendingProposal — שום הזזה בפועל עד "אשר" (אותו מנגנון preview).
  function onSmartFill() {
    if (unassigned.length === 0) return
    const result = computeSmartFill(
      tables,
      unassigned,
      forbiddenPairs,
      togetherPairs,
      seats,
      nextTableNumRef.current,
    )
    if (result.moves.length === 0) {
      setError('לא נמצא מקום להושבה אוטומטית — נסו קיבולת גדולה יותר לשולחן.')
      return
    }
    const tableWord = result.newTables.length === 1 ? 'שולחן חדש אחד' : `${result.newTables.length} שולחנות חדשים`
    const text =
      result.newTables.length > 0
        ? `מילוי שולחנות: הושבת ${result.placedCount} מוזמנים, כולל פתיחת ${tableWord}` +
          (result.unplacedCount > 0 ? ` (${result.unplacedCount} נשארו ללא שולחן — חבורה גדולה מדי)` : '')
        : `מילוי שולחנות: הושבת ${result.placedCount} מוזמנים בשולחנות הקיימים` +
          (result.unplacedCount > 0 ? ` (${result.unplacedCount} נשארו ללא שולחן — חבורה גדולה מדי)` : '')
    setPendingProposal({
      text,
      moves: result.moves,
      diff: buildProposalDiff(result.moves),
      newTables: result.newTables,
    })
  }

  function onConfirmProposal() {
    if (!pendingProposal) return
    applyMoves(pendingProposal.moves, pendingProposal.newTables)
    setPendingProposal(null)
  }
  function onCancelProposal() {
    setPendingProposal(null)
  }

  // ============================================================
  // ============  מובייל: חוויית הושבה ייעודית  ================
  // ============================================================
  // שכבה נפרדת לגמרי לטלפון (early-return) — הדסקטופ שמתחת נשאר ללא שינוי.
  // עקרונות: האולם תמיד "נכנס" במלואו למסך (Auto-Fit, בלי גלילה ובלי זום),
  // הקשה על שולחן פותחת Bottom Sheet, והעברת מוזמן נעשית בהקשה (לא בגרירה).
  if (mobileMode) {
    const sheetT = sheetTable != null ? tables.find((t) => t.table_number === sheetTable) ?? null : null
    const q = mobileSearch.trim()
    const searchResults = q ? smartSearch(q, tables, unassigned) : []
    const seatedInSheet = sheetT ? sheetT.guests.reduce((s, g) => s + g.seats, 0) : 0
    const freeInSheet = sheetT ? sheetT.capacity - seatedInSheet : 0

    const closeSheet = () => {
      setSheetTable(null)
      setSheetEdit(false)
    }
    const startMove = (guestId: number) => {
      setSelected(guestId)
      closeSheet()
      setMobileTab('hall')
    }

    return (
      <div className="hall-mobile">
        {/* ---- פס עליון: כותרת + חיפוש ---- */}
        <div className="hm-topbar">
          <div className="hm-search">
            <span className="hm-search-icon" aria-hidden="true">
              <HmIcon name="search" size={18} />
            </span>
            <input
              type="search"
              value={mobileSearch}
              onChange={(e) => setMobileSearch(e.target.value)}
              placeholder="חיפוש מוזמן או מספר שולחן"
              aria-label="חיפוש מוזמן או שולחן"
            />
            {q && (
              <button className="hm-search-clear" onClick={() => setMobileSearch('')} aria-label="ניקוי חיפוש">
                ×
              </button>
            )}
          </div>
          {q && (
            <div className="hm-search-results">
              {searchResults.length === 0 ? (
                <p className="hm-search-empty">לא נמצא מוזמן בשם הזה.</p>
              ) : (
                searchResults.slice(0, 8).map((r) => (
                  <button
                    key={r.guestId}
                    className="hm-search-row"
                    onClick={() => {
                      setMobileSearch('')
                      if (r.tableNumber != null) {
                        setSheetTable(r.tableNumber)
                        setSheetEdit(false)
                        setMobileTab('hall')
                      } else {
                        setSelected(r.guestId)
                        setMobileTab('hall')
                      }
                    }}
                  >
                    <span className="hm-search-name">{r.fullName}</span>
                    <span className="hm-search-loc">
                      {r.tableNumber != null ? `שולחן ${r.tableNumber}` : 'ללא שולחן'}
                    </span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {/* ---- אזור התוכן המתחלף לפי הלשונית ---- */}
        <div className="hm-body">
          {/* באנר "מצב העברה" — פעיל בכל הלשוניות כשנבחר מוזמן להעברה */}
          {selected !== null && (
            <div className="hm-move-banner">
              <span>נבחר מוזמן להעברה — הקישו על שולחן כדי לשבץ אותו.</span>
              <button onClick={() => setSelected(null)}>ביטול</button>
            </div>
          )}
          {assignTarget !== null && mobileTab === 'guests' && (
            <div className="hm-move-banner assign">
              <span>בחרו מוזמן לשיבוץ לשולחן {assignTarget}.</span>
              <button onClick={() => setAssignTarget(null)}>ביטול</button>
            </div>
          )}

          {/* ===== לשונית: אולם ===== */}
          {mobileTab === 'hall' && (
            <div
              className="hm-canvas"
              ref={viewportRef}
              onPointerMove={onCanvasPointerMove}
              onPointerUp={onCanvasPointerUp}
              onPointerLeave={onCanvasPointerUp}
            >
              <div
                className="hall-world"
                ref={worldRef}
                style={{ width: WORLD_W, height: WORLD_H, transform: viewTransform, transformOrigin: '0 0' }}
              >
                {sketch && (
                  <div className="hall-sketch-bg" style={{ backgroundImage: `url(${sketch})` }} aria-hidden="true" />
                )}
                {tables.length === 0 && elements.length === 0 && (
                  <p className="hall-empty">אין עדיין שולחנות. הקישו על ➕ כדי להוסיף שולחן.</p>
                )}

                {/* אלמנטים (רחבה/בר/DJ/חופה) — ניתנים לגרירה ובחירה גם במובייל */}
                {elements.map((el) => {
                  const isSel = selectedEl === el.id
                  const color = el.color || ELEMENT_DEFS[el.type]?.color || '#7fb3e0'
                  const radius =
                    el.shape === 'circle' || el.shape === 'ellipse' ? '50%' : el.shape === 'square' ? '16px' : '12px'
                  const hasCustom = !!el.color
                  return (
                    <div
                      key={el.id}
                      className={`hall-element el-${el.type} ${hasCustom ? '' : 'themed'} ${
                        isSel ? 'selected' : ''
                      } ${el.locked ? 'locked' : ''}`}
                      style={{
                        left: el.x,
                        top: el.y,
                        width: el.width,
                        height: el.height,
                        transform: `rotate(${el.rotation}deg)`,
                        borderRadius: radius,
                        ...(hasCustom ? { background: `${color}26`, borderColor: color } : {}),
                      }}
                      onPointerDown={(e) => onElementPointerDown(e, el.id)}
                    >
                      <span className="element-label" style={hasCustom ? { color } : undefined}>
                        {el.label}
                      </span>
                      {el.locked && (
                        <span className="element-lock-badge" title="נעול">
                          🔒
                        </span>
                      )}
                      {isSel && (
                        <div className="element-toolbar mobile" onPointerDown={(e) => e.stopPropagation()}>
                          <button
                            type="button"
                            title={el.locked ? 'שחרר נעילה' : 'נעל'}
                            onClick={(e) => {
                              e.stopPropagation()
                              toggleElementLock(el.id)
                            }}
                          >
                            {el.locked ? '🔓' : '🔒'}
                          </button>
                          <button
                            type="button"
                            title="מחק"
                            onClick={(e) => {
                              e.stopPropagation()
                              removeElement(el.id)
                            }}
                          >
                            ×
                          </button>
                        </div>
                      )}
                      {isSel && !el.locked && (
                        <span
                          className="handle handle-resize"
                          title="שנה גודל"
                          onPointerDown={(e) => onResizePointerDown(e, el.id)}
                        />
                      )}
                    </div>
                  )
                })}

                {/* שולחנות — הקשה פותחת Bottom Sheet, לחיצה ארוכה/גרירה מזיזה */}
                {tables.map((t) => {
                  const used = t.guests.reduce((s, g) => s + g.seats, 0)
                  const over = used > t.capacity
                  const { w, h } = tableSize(t.table_type, t.capacity)
                  const color = t.color || TABLE_TYPE_DEFAULT_COLOR[t.table_type]
                  const seatCount = Math.max(t.capacity, used, 1)
                  const pts = seatPositions(t.table_type, seatCount, w, h)
                  const occupiedPoints = new Set<number>()
                  {
                    let idx = 0
                    for (const g of t.guests) {
                      for (let k = 0; k < Math.max(1, g.seats); k++) occupiedPoints.add(idx + k)
                      idx += Math.max(1, g.seats)
                    }
                  }
                  const status = tableStatus.get(t.table_number) ?? 'green'
                  const hasCustomColor = !!t.color
                  let bodyBg = `${color}33`
                  let bodyBorder = color
                  if (!hasCustomColor && status === 'green' && !over) {
                    if (used >= t.capacity) {
                      bodyBg = 'linear-gradient(160deg,#E9DCB3,#C9A227)'
                      bodyBorder = '#FFFFFF'
                    } else if (t.capacity > 0 && used / t.capacity >= 0.8) {
                      bodyBg = 'linear-gradient(160deg,#F4EEE0,#D9CBA6)'
                      bodyBorder = '#FFFFFF'
                    } else {
                      bodyBg = '#FFFFFF'
                      bodyBorder = '#E5DEC9'
                    }
                  }
                  return (
                    <div
                      key={t.table_number}
                      data-tnum={t.table_number}
                      className={`hall-table ${over ? 'over' : ''} ${selected !== null ? 'droppable' : ''}`}
                      style={{ left: t.x, top: t.y, width: w }}
                      onClick={(e) => onTableClick(e, t.table_number)}
                    >
                      <span className={`table-status-dot status-${status}`} />
                      <div
                        className={`table-graphic type-${t.table_type}`}
                        style={{
                          width: w,
                          height: h,
                          transform: `rotate(${t.rotation}deg)`,
                          background: bodyBg,
                          borderColor: bodyBorder,
                        }}
                        onPointerDown={(e) => onTablePointerDown(e, t.table_number)}
                      >
                        <span className="seat-layer" aria-hidden="true">
                          {pts.map((p, i) => (
                            <span
                              key={i}
                              className={`seat-pip ${occupiedPoints.has(i) ? 'seat-taken' : ''} ${
                                i >= t.capacity ? 'seat-extra' : ''
                              }`}
                              style={{ left: p.left, top: p.top }}
                            />
                          ))}
                        </span>
                        <span className="table-center">
                          <span className="table-num">{t.table_number}</span>
                          {t.name && <span className="table-name">{t.name}</span>}
                          <span className="table-occ">
                            {used}/{t.capacity}
                          </span>
                        </span>
                      </div>
                    </div>
                  )
                })}
              </div>

              {/* FAB — הוספה מהירה */}
              <div className={`hm-fab-wrap ${fabOpen ? 'open' : ''}`}>
                {fabOpen && (
                  <div className="hm-fab-menu" onClick={() => setFabOpen(false)}>
                    <button onClick={() => addTable('round')}>
                      <HmIcon name="round" size={18} /> שולחן עגול
                    </button>
                    <button onClick={() => addTable('knights')}>
                      <HmIcon name="knights" size={18} /> שולחן אבירים
                    </button>
                    <button onClick={() => addElement('bar')}>
                      <HmIcon name="bar" size={18} /> בר
                    </button>
                    <button onClick={() => addElement('dance_floor')}>
                      <HmIcon name="dance" size={18} /> רחבת ריקודים
                    </button>
                    <button onClick={() => addElement('dj')}>
                      <HmIcon name="dj" size={18} /> עמדת דיג'יי
                    </button>
                  </div>
                )}
                <button
                  className="hm-fab"
                  onClick={() => setFabOpen((v) => !v)}
                  aria-label={fabOpen ? 'סגירת תפריט הוספה' : 'הוספה'}
                >
                  {fabOpen ? '×' : '＋'}
                </button>
              </div>
            </div>
          )}

          {/* ===== לשונית: שולחנות ===== */}
          {mobileTab === 'tables' && (
            <div className="hm-panel">
              {tables.length === 0 ? (
                <p className="hm-empty">עדיין אין שולחנות. הוסיפו שולחן מלשונית "אולם".</p>
              ) : (
                [...tables]
                  .sort((a, b) => a.table_number - b.table_number)
                  .map((t) => {
                    const used = t.guests.reduce((s, g) => s + g.seats, 0)
                    const status = tableStatus.get(t.table_number) ?? 'green'
                    return (
                      <button
                        key={t.table_number}
                        className="hm-table-card"
                        onClick={() => {
                          setSheetTable(t.table_number)
                          setSheetEdit(false)
                          setMobileTab('hall')
                        }}
                      >
                        <span className={`hm-dot status-${status}`} />
                        <span className="hm-tc-main">
                          <span className="hm-tc-title">
                            שולחן {t.table_number}
                            {t.name ? ` · ${t.name}` : ''}
                          </span>
                          <span className="hm-tc-sub">{TABLE_TYPE_LABELS[t.table_type]}</span>
                        </span>
                        <span className={`hm-tc-count ${used > t.capacity ? 'over' : ''}`}>
                          {used}/{t.capacity}
                        </span>
                      </button>
                    )
                  })
              )}
            </div>
          )}

          {/* ===== לשונית: מוזמנים (ללא שולחן) ===== */}
          {mobileTab === 'guests' && (
            <div className="hm-panel">
              <p className="hm-panel-head">
                ללא שולחן: {visibleUnassigned.length}
                {assignTarget !== null ? ` · הקישו לשיבוץ לשולחן ${assignTarget}` : ' · הקישו כדי לשבץ'}
              </p>
              {visibleUnassigned.length === 0 ? (
                <p className="hm-empty">כל המוזמנים כבר משובצים. יופי! 🎉</p>
              ) : (
                visibleUnassigned.map((g) => (
                  <button
                    key={g.id}
                    className={`hm-guest-row ${selected === g.id ? 'sel' : ''}`}
                    onClick={() => {
                      if (assignTarget !== null) {
                        moveGuestToTable(g.id, assignTarget)
                        setAssignTarget(null)
                        setMobileTab('hall')
                      } else {
                        setSelected(g.id)
                        setMobileTab('hall')
                      }
                    }}
                  >
                    <span className="hm-gr-main">
                      <span className="hm-gr-name">{g.full_name}</span>
                      <span className="hm-gr-sub">
                        {GROUP_LABELS[g.group_type]} · {SIDE_LABELS[g.side]}
                        {g.seats > 1 ? ` · ${g.seats} מקומות` : ''}
                      </span>
                    </span>
                    <span className="hm-gr-cta">שיבוץ ›</span>
                  </button>
                ))
              )}
            </div>
          )}

          {/* ===== לשונית: הושבה חכמה ===== */}
          {mobileTab === 'smart' && (
            <div className="hm-panel">
              <div className="hm-stats">
                <div className="hm-stat">
                  <span className="hm-stat-num">{smartStats.seatedPeople}</span>
                  <span className="hm-stat-lbl">משובצים</span>
                </div>
                <div className="hm-stat">
                  <span className="hm-stat-num">{smartStats.unseatedPeople}</span>
                  <span className="hm-stat-lbl">ללא שולחן</span>
                </div>
                <div className="hm-stat">
                  <span className="hm-stat-num">{smartStats.numTables}</span>
                  <span className="hm-stat-lbl">שולחנות</span>
                </div>
                <div className="hm-stat">
                  <span className="hm-stat-num">{smartStats.freeSeats}</span>
                  <span className="hm-stat-lbl">מקומות פנויים</span>
                </div>
              </div>

              <button
                className="hm-primary-btn"
                onClick={onSmartFill}
                disabled={unassigned.length === 0}
              >
                <HmIcon name="smart" size={18} /> מילוי שולחנות אוטומטי
              </button>

              {pendingProposal && (
                <div className="hm-proposal">
                  <p className="hm-proposal-text">{pendingProposal.text}</p>
                  <div className="hm-proposal-actions">
                    <button className="hm-primary-btn" onClick={onConfirmProposal}>
                      אישור
                    </button>
                    <button className="hm-ghost-btn" onClick={onCancelProposal}>
                      ביטול
                    </button>
                  </div>
                </div>
              )}

              {smartWarnings.length > 0 && (
                <div className="hm-warnings">
                  <p className="hm-panel-head">שווה לשים לב</p>
                  {smartWarnings.slice(0, 6).map((w, i) => (
                    <div key={i} className={`hm-warn sev-${w.severity}`}>
                      {w.text}
                    </div>
                  ))}
                </div>
              )}

              {smartSuggestions.length > 0 && (
                <div className="hm-suggestions">
                  <p className="hm-panel-head">הצעות לשיפור</p>
                  {smartSuggestions.slice(0, 5).map((s, i) => (
                    <button key={i} className="hm-suggestion" onClick={() => onProposeSuggestion(s)}>
                      {s.text}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ===== לשונית: כלים ===== */}
          {mobileTab === 'tools' && (
            <div className="hm-panel">
              <button className="hm-primary-btn" onClick={onSave} disabled={loading || !dirty}>
                {loading ? (
                  'שומרים…'
                ) : dirty ? (
                  <>
                    <HmIcon name="save" size={18} /> שמירת הסידור
                  </>
                ) : (
                  'הכול שמור'
                )}
              </button>
              <button className="hm-ghost-btn" onClick={onRegenerate} disabled={loading}>
                <HmIcon name="refresh" size={18} /> סידור מחדש מההתחלה
              </button>

              <div className="hm-tools-group">
                <p className="hm-panel-head">רקע האולם (סקיצה)</p>
                {sketch ? (
                  <button className="hm-ghost-btn" onClick={removeSketch}>
                    הסרת הסקיצה
                  </button>
                ) : (
                  <button className="hm-ghost-btn" onClick={() => sketchInputRef.current?.click()}>
                    העלאת סקיצת אולם
                  </button>
                )}
                <input
                  ref={sketchInputRef}
                  type="file"
                  accept="image/*"
                  hidden
                  onChange={onPickSketch}
                />
              </div>

              <div className="hm-tools-group">
                <p className="hm-panel-head">מקומות ברירת מחדל לשולחן</p>
                <select value={seats} onChange={(e) => setSeats(Number(e.target.value))}>
                  {SEAT_OPTIONS.map((n) => (
                    <option key={n} value={n}>
                      {n} מקומות
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </div>

        {/* ---- ניווט תחתון (5 מדורים) ---- */}
        <nav className="hm-tabs" aria-label="ניווט מסך הושבה">
          {(
            [
              { key: 'hall', icon: 'hall', label: 'אולם' },
              { key: 'tables', icon: 'tables', label: 'שולחנות' },
              { key: 'guests', icon: 'guests', label: 'מוזמנים' },
              { key: 'smart', icon: 'smart', label: 'הושבה' },
              { key: 'tools', icon: 'tools', label: 'כלים' },
            ] as const
          ).map((tab) => (
            <button
              key={tab.key}
              className={`hm-tab ${mobileTab === tab.key ? 'active' : ''}`}
              onClick={() => setMobileTab(tab.key)}
            >
              <span className="hm-tab-icon" aria-hidden="true">
                <HmIcon name={tab.icon} />
              </span>
              <span className="hm-tab-label">{tab.label}</span>
              {tab.key === 'guests' && visibleUnassigned.length > 0 && (
                <span className="hm-tab-badge">{visibleUnassigned.length}</span>
              )}
            </button>
          ))}
        </nav>

        {/* ---- Bottom Sheet: פרטי שולחן ---- */}
        {sheetT && (
          <>
            <div className="hm-sheet-backdrop" onClick={closeSheet} />
            <div className="hm-sheet" role="dialog" aria-label={`שולחן ${sheetT.table_number}`}>
              <div className="hm-sheet-handle" onClick={closeSheet} />

              {!sheetEdit ? (
                <>
                  <div className="hm-sheet-head">
                    <div>
                      <h3 className="hm-sheet-title">
                        שולחן {sheetT.table_number}
                        {sheetT.name ? ` · ${sheetT.name}` : ''}
                      </h3>
                      <p className="hm-sheet-sub">
                        {TABLE_TYPE_LABELS[sheetT.table_type]} · {freeInSheet > 0 ? `${freeInSheet} מקומות פנויים` : 'מלא'}
                      </p>
                    </div>
                    <span className={`hm-sheet-count ${seatedInSheet > sheetT.capacity ? 'over' : ''}`}>
                      {seatedInSheet}/{sheetT.capacity}
                    </span>
                  </div>

                  <div className="hm-sheet-guests">
                    {sheetT.guests.length === 0 ? (
                      <p className="hm-empty">אין עדיין מוזמנים בשולחן הזה.</p>
                    ) : (
                      sheetT.guests.map((g) => (
                        <div key={g.id} className="hm-seated-row">
                          <span className="hm-seated-name">
                            {g.full_name}
                            {g.seats > 1 ? ` (${g.seats})` : ''}
                          </span>
                          <span className="hm-seated-actions">
                            <button onClick={() => startMove(g.id)} title="העברה לשולחן אחר">
                              <HmIcon name="move" size={16} /> העברה
                            </button>
                            <button className="danger" onClick={() => moveGuestToTable(g.id, null)} title="הסרה מהשולחן">
                              הסרה
                            </button>
                          </span>
                        </div>
                      ))
                    )}
                  </div>

                  <div className="hm-sheet-actions">
                    <button
                      className="hm-primary-btn"
                      onClick={() => {
                        setAssignTarget(sheetT.table_number)
                        setMobileTab('guests')
                        closeSheet()
                      }}
                    >
                      <HmIcon name="plus" size={18} /> הוספת מוזמן
                    </button>
                    <button className="hm-ghost-btn" onClick={() => setSheetEdit(true)}>
                      <HmIcon name="edit" size={18} /> עריכת שולחן
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div className="hm-sheet-head">
                    <h3 className="hm-sheet-title">עריכת שולחן {sheetT.table_number}</h3>
                    <button className="hm-sheet-back" onClick={() => setSheetEdit(false)}>
                      › חזרה
                    </button>
                  </div>

                  <div className="hm-edit-field">
                    <label>מספר שולחן</label>
                    <input
                      type="number"
                      defaultValue={sheetT.table_number}
                      key={sheetT.table_number}
                      onBlur={(e) => renumberTable(sheetT.table_number, e.target.value)}
                    />
                  </div>

                  <div className="hm-edit-field">
                    <label>שם (אופציונלי)</label>
                    <input
                      type="text"
                      value={sheetT.name}
                      placeholder="למשל: משפחת הכלה"
                      onChange={(e) => updateTable(sheetT.table_number, { name: e.target.value })}
                    />
                  </div>

                  <div className="hm-edit-field">
                    <label>סוג שולחן</label>
                    <div className="hm-type-chips">
                      {(Object.keys(TABLE_TYPE_LABELS) as TableType[]).map((tt) => (
                        <button
                          key={tt}
                          className={sheetT.table_type === tt ? 'active' : ''}
                          onClick={() =>
                            updateTable(sheetT.table_number, {
                              table_type: tt,
                              capacity: defaultCapacityForType(tt),
                            })
                          }
                        >
                          {TABLE_TYPE_LABELS[tt]}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="hm-edit-field">
                    <label>מספר מקומות</label>
                    <div className="hm-stepper">
                      <button onClick={() => bumpCapacity(sheetT.table_number, -1)}>−</button>
                      <span>{sheetT.capacity}</span>
                      <button onClick={() => bumpCapacity(sheetT.table_number, 1)}>+</button>
                    </div>
                  </div>

                  <div className="hm-edit-field">
                    <label>צבע</label>
                    <div className="hm-colors">
                      {TABLE_COLORS.map((c) => (
                        <button
                          key={c}
                          className={`hm-color ${sheetT.color === c ? 'active' : ''}`}
                          style={{ background: c }}
                          onClick={() => updateTable(sheetT.table_number, { color: c })}
                          aria-label="בחירת צבע"
                        />
                      ))}
                      <button
                        className={`hm-color none ${sheetT.color === '' ? 'active' : ''}`}
                        onClick={() => updateTable(sheetT.table_number, { color: '' })}
                        aria-label="בלי צבע"
                      >
                        ✕
                      </button>
                    </div>
                  </div>

                  <div className="hm-sheet-actions">
                    <button
                      className="hm-ghost-btn"
                      onClick={() => {
                        duplicateTable(sheetT.table_number)
                        closeSheet()
                      }}
                    >
                      <HmIcon name="copy" size={18} /> שכפול
                    </button>
                    <button
                      className="hm-ghost-btn danger"
                      onClick={() => {
                        deleteTable(sheetT.table_number)
                        closeSheet()
                      }}
                    >
                      <HmIcon name="trash" size={18} /> מחיקה
                    </button>
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </div>
    )
  }

  return (
    <div className="hall-page">
      {/* ---- אילוצים מההערות (לפני השיבוץ) ---- */}
      <div className="clar-panel">
        <div className="clar-head">
          <div>
            <h3 className="clar-title">העדפות הישיבה שלכם</h3>
            <p className="clar-sub">
              אנחנו קוראים את ההערות וממירים אותן להעדפות ישיבה — מי לשבת עם
              מי, וממי להרחיק — לפני שנסדר את ההושבה.
            </p>
          </div>
          <button className="btn-ghost" onClick={onAnalyze} disabled={analyzing}>
            {analyzing ? 'בודקים…' : '↻ בדיקת ההערות'}
          </button>
        </div>

        {analyzeSummary && (
          <p className="clar-summary">
            נותחו {analyzeSummary.guests_analyzed} מוזמנים ·{' '}
            {analyzeSummary.resolved} העדפות זוהו ·{' '}
            {analyzeSummary.pending_clarifications} ממתינים להבהרה
          </p>
        )}

        {clarifications.length > 0 ? (
          <div className="clar-list">
            {clarifications.map((c) => (
              <div className="clar-card" key={c.id}>
                <div className="clar-q">
                  <strong>{c.source_guest_name}</strong> ביקש/ה{' '}
                  {REL_TEXT[c.relation_type]} "<strong>{c.target_text}</strong>" —
                  למי הכוונה?
                </div>
                <div className="clar-actions">
                  {c.candidates.map((cand) => (
                    <button
                      key={cand.id}
                      className="btn-ghost clar-choice"
                      onClick={() => onResolve(c.id, cand.id)}
                    >
                      {cand.full_name}
                    </button>
                  ))}
                  <button className="btn-text" onClick={() => onResolve(c.id, null)}>
                    אף אחד מהם
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          analyzeSummary && <p className="clar-ok">אין הבהרות ממתינות ✓</p>
        )}
      </div>

      <div className="hall-toolbar">
        <button className="btn-primary btn-add-table" onClick={() => addTable()}>
          ➕ הוסף שולחן
        </button>
        <label className="seats-field" title="מספר מקומות ברירת מחדל לשולחן חדש ולסידור ההושבה">
          מקומות ברירת מחדל
          <select value={seats} onChange={(e) => setSeats(Number(e.target.value))}>
            {SEAT_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <button className="btn-ghost" onClick={onRegenerate} disabled={loading}>
          ✨ סידור הושבה חכם
        </button>
        <button className="btn-primary" onClick={onSave} disabled={loading || !dirty}>
          {loading ? 'שומר…' : dirty ? 'שמירת המפה' : 'שמרנו ✓'}
        </button>
        <input ref={sketchInputRef} type="file" accept="image/*" hidden onChange={onPickSketch} />
        <button className="btn-ghost" onClick={() => sketchInputRef.current?.click()}>
          {sketch ? '🖼 החלפת סקיצה' : '🖼 העלאת סקיצת אולם'}
        </button>
        {sketch && (
          <button className="btn-text" onClick={removeSketch}>
            הסרת סקיצה
          </button>
        )}
        <button
          className={`btn-ghost ${smartPanelOpen ? 'active' : ''}`}
          onClick={() => setSmartPanelOpen((v) => !v)}
        >
          ✨ העוזר החכם להושבה
        </button>
      </div>

      <div className="hall-palette">
        <span className="palette-label">הוספה למפה:</span>
        {VISIBLE_ELEMENTS.map((type) => (
          <button key={type} type="button" className="palette-btn" onClick={() => addElement(type)}>
            + {ELEMENT_DEFS[type].label}
          </button>
        ))}
        <span className="hall-hint">
          גררו שולחן כדי להזיז אותו · גררו מוזמן לשולחן · Shift+קליק לבחירה מרובה
        </span>
      </div>

      {error && <p className="form-error">{error}</p>}

      {warnings.length > 0 && (
        <div className="hall-warnings">
          {warnings.map((w, i) => (
            <p key={i}>⚠ {w}</p>
          ))}
        </div>
      )}

      {/* מקרא צבעים — מסביר את מצב התפוסה של השולחנות במפה (לפי עיצוב VEYA Seating) */}
      <div className="hall-legend" aria-hidden="true">
        <span className="hall-legend-item">
          <span className="hall-legend-swatch open" />מקומות פנויים
        </span>
        <span className="hall-legend-item">
          <span className="hall-legend-swatch near" />כמעט מלא
        </span>
        <span className="hall-legend-item">
          <span className="hall-legend-swatch full" />שולחן מלא
        </span>
      </div>

      <div className="hall-layout">
        {/* מגש מוזמנים ללא שולחן */}
        <div
          className={`hall-tray ${selected !== null ? 'droppable' : ''} ${
            dragOver === 'tray' ? 'drag-over' : ''
          }`}
          onClick={onTrayClick}
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver('tray')
          }}
          onDragLeave={() => setDragOver((c) => (c === 'tray' ? null : c))}
          onDrop={(e) => onDropTo(e, null)}
        >
          <h4 className="tray-title">ללא שולחן ({unassigned.length})</h4>
          {unassigned.length > 5 && (
            <input
              type="text"
              className="tray-search"
              placeholder="חיפוש מוזמן…"
              value={traySearch}
              onClick={(e) => e.stopPropagation()}
              onChange={(e) => setTraySearch(e.target.value)}
            />
          )}
          {unassigned.length === 0 && <p className="tray-empty">כולם משובצים ✓</p>}
          {unassigned.length > 0 && visibleUnassigned.length === 0 && (
            <p className="tray-empty tray-no-match">לא נמצאה התאמה ל"{traySearch}"</p>
          )}
          <div className="tray-list">
            {visibleUnassigned.map((g) => (
              <GuestChip
                key={g.id}
                g={g}
                selected={selected === g.id}
                onClick={(e) => onGuestClick(e, g.id)}
                onDragStart={(e) => onGuestDragStart(e, g.id)}
                onDragEnd={onGuestDragEnd}
              />
            ))}
          </div>
        </div>

        {/* לוח מפת האולם: מאגר נגלל (Viewport) המכיל את הלוח בגודל אמיתי (World) */}
        <div className="hall-canvas-wrap">
          <div
            className="hall-viewport"
            ref={viewportRef}
            onPointerMove={onCanvasPointerMove}
            onPointerUp={onCanvasPointerUp}
            onPointerLeave={onCanvasPointerUp}
          >
            <div
              className="hall-world"
              ref={worldRef}
              style={{ width: WORLD_W, height: WORLD_H }}
              onPointerDown={onWorldPointerDown}
            >
              {sketch && (
                <div className="hall-sketch-bg" style={{ backgroundImage: `url(${sketch})` }} aria-hidden="true" />
              )}
              {tables.length === 0 && elements.length === 0 && (
                <p className="hall-empty">
                  אין עדיין שולחנות. לחצו "➕ הוסף שולחן" או "סידור הושבה חכם".
                </p>
              )}

              {elements.map((el) => {
                const isSel = selectedEl === el.id
                const color = el.color || ELEMENT_DEFS[el.type]?.color || '#7fb3e0'
                const radius =
                  el.shape === 'circle' || el.shape === 'ellipse' ? '50%' : el.shape === 'square' ? '16px' : '12px'
                // כשהזוג לא בחר צבע מותאם — האלמנטים (DJ/בר/כניסה/רחבה) מקבלים
                // מראה מעוצב קבוע לפי עיצוב VEYA Seating (דרך מחלקת CSS). אם נבחר
                // צבע ידני, חוזרים לגוון הכללי (שומר על ההתאמה האישית הקיימת).
                const hasCustom = !!el.color
                return (
                  <div
                    key={el.id}
                    className={`hall-element el-${el.type} ${hasCustom ? '' : 'themed'} ${
                      isSel ? 'selected' : ''
                    } ${el.locked ? 'locked' : ''}`}
                    style={{
                      left: el.x,
                      top: el.y,
                      width: el.width,
                      height: el.height,
                      transform: `rotate(${el.rotation}deg)`,
                      borderRadius: radius,
                      ...(hasCustom ? { background: `${color}26`, borderColor: color } : {}),
                    }}
                    onPointerDown={(e) => onElementPointerDown(e, el.id)}
                  >
                    <span className="element-label" style={hasCustom ? { color } : undefined}>
                      {el.label}
                    </span>
                    {el.locked && (
                      <span className="element-lock-badge" title="נעול">
                        🔒
                      </span>
                    )}

                    {isSel && (
                      <>
                        <div className="element-toolbar" onPointerDown={(e) => e.stopPropagation()}>
                          <div className="shape-row">
                            {ELEMENT_SHAPES.map((s) => (
                              <button
                                key={s.key}
                                type="button"
                                className={el.shape === s.key ? 'active' : ''}
                                title={s.key}
                                onClick={(e) => {
                                  e.stopPropagation()
                                  updateElement(el.id, { shape: s.key })
                                }}
                              >
                                {s.label}
                              </button>
                            ))}
                          </div>
                          <div className="color-row">
                            {ELEMENT_COLORS.map((c) => (
                              <button
                                key={c}
                                type="button"
                                className="color-swatch"
                                style={{ background: c }}
                                title="צבע"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  updateElement(el.id, { color: c })
                                }}
                              />
                            ))}
                          </div>
                          <button
                            type="button"
                            title={el.locked ? 'שחרר נעילה' : 'נעל'}
                            onClick={(e) => {
                              e.stopPropagation()
                              toggleElementLock(el.id)
                            }}
                          >
                            {el.locked ? '🔓' : '🔒'}
                          </button>
                          <button
                            type="button"
                            title="שכפל"
                            onClick={(e) => {
                              e.stopPropagation()
                              duplicateElement(el.id)
                            }}
                          >
                            ⧉
                          </button>
                          <button
                            type="button"
                            title="מחק"
                            onClick={(e) => {
                              e.stopPropagation()
                              removeElement(el.id)
                            }}
                          >
                            ×
                          </button>
                        </div>

                        {!el.locked && (
                          <>
                            <span
                              className="handle handle-rotate"
                              title="סובב"
                              onPointerDown={(e) => onRotatePointerDown(e, el.id)}
                            />
                            <span
                              className="handle handle-resize"
                              title="שנה גודל"
                              onPointerDown={(e) => onResizePointerDown(e, el.id)}
                            />
                          </>
                        )}
                      </>
                    )}
                  </div>
                )
              })}

              {tables.map((t) => {
                const used = t.guests.reduce((s, g) => s + g.seats, 0)
                const over = used > t.capacity
                const free = t.capacity - used
                const isSelT = selectedTables.has(t.table_number)
                const { w, h } = tableSize(t.table_type, t.capacity)
                const color = t.color || TABLE_TYPE_DEFAULT_COLOR[t.table_type]
                const occupied: string[] = []
                for (const g of t.guests) for (let i = 0; i < g.seats; i++) occupied.push(g.side)
                const seatCount = Math.max(t.capacity, occupied.length, 1)
                const pts = seatPositions(t.table_type, seatCount, w, h)
                // כל מוזמן "תופס" נקודת כיסא ראשית (שבה יוצג עיגול-המוזמן) ואולי
                // עוד נקודות-לוואי (מלווים/seats>1) שמסומנות כתפוסות בלי עיגול נפרד.
                const guestAtPoint = new Map<number, HallGuest>()
                const companionPoints = new Set<number>()
                {
                  let idx = 0
                  for (const g of t.guests) {
                    guestAtPoint.set(idx, g)
                    for (let k = 1; k < g.seats; k++) companionPoints.add(idx + k)
                    idx += Math.max(1, g.seats)
                  }
                }
                const status = tableStatus.get(t.table_number) ?? 'green'
                // מצב תפוסה חזותי (מקרא): שולחן מלא = זהב, כמעט מלא (≥80%) = ירוק,
                // אחרת = ניטרלי. מוצג רק כשאין בעיה/אזהרה (status='green'), כדי לא
                // להסתיר את טבעת האזהרה האדומה/צהובה. תואם עיצוב VEYA Seating.
                const fillClass =
                  status === 'green' && !over
                    ? used >= t.capacity
                      ? 'fill-full'
                      : t.capacity > 0 && used / t.capacity >= 0.8
                        ? 'fill-near'
                        : ''
                    : ''
                // גוף השולחן מתמלא בצבע לפי תפוסה (עיצוב VEYA Seating):
                // פנוי=לבן, כמעט מלא=שמנת-חול, מלא=זהב. אם הזוג בחר צבע ידני
                // לשולחן — מכבדים אותו (שומרים על תכונת הצבע המותאם).
                const hasCustomColor = !!t.color
                let bodyBg = `${color}33`
                let bodyBorder = color
                if (!hasCustomColor && status === 'green' && !over) {
                  if (used >= t.capacity) {
                    bodyBg = 'linear-gradient(160deg,#E9DCB3,#C9A227)'
                    bodyBorder = '#FFFFFF'
                  } else if (t.capacity > 0 && used / t.capacity >= 0.8) {
                    bodyBg = 'linear-gradient(160deg,#F4EEE0,#D9CBA6)'
                    bodyBorder = '#FFFFFF'
                  } else {
                    bodyBg = '#FFFFFF'
                    bodyBorder = '#E5DEC9'
                  }
                }
                const liveCheck =
                  dragOver === t.table_number && draggedGuestForLive
                    ? liveDragValidation(draggedGuestForLive, t, forbiddenPairs, familyGroups)
                    : null
                return (
                  <div
                    key={t.table_number}
                    data-tnum={t.table_number}
                    className={`hall-table ${over ? 'over' : ''} ${
                      !over && warnTables.has(t.table_number) ? 'warn' : ''
                    } ${selected !== null ? 'droppable' : ''} ${isSelT ? 'selected' : ''} ${
                      t.locked ? 'locked' : ''
                    } ${dragOver === t.table_number ? 'drag-over' : ''} ${fillClass}`}
                    style={{ left: t.x, top: t.y, width: w }}
                    onClick={(e) => onTableClick(e, t.table_number)}
                    onDragOver={(e) => {
                      e.preventDefault()
                      setDragOver(t.table_number)
                    }}
                    onDragLeave={() => setDragOver((c) => (c === t.table_number ? null : c))}
                    onDrop={(e) => onDropTo(e, t.table_number)}
                  >
                    <span
                      className={`table-status-dot status-${status}`}
                      title={
                        status === 'red'
                          ? 'בעיה בשולחן — ראו אזהרות'
                          : status === 'yellow'
                            ? 'יש המלצה/אזהרה קלה לשולחן הזה'
                            : 'תקין'
                      }
                    />
                    <div
                      className={`table-graphic type-${t.table_type}`}
                      style={{
                        width: w,
                        height: h,
                        transform: `rotate(${t.rotation}deg)`,
                        background: bodyBg,
                        borderColor: bodyBorder,
                      }}
                      onPointerDown={(e) => onTablePointerDown(e, t.table_number)}
                    >
                      {/* כיסאות נקיים סביב היקף השולחן — תפוס/פנוי, בלי שמות
                          (עיצוב VEYA Seating: השולחן נשאר נקי, המספר והסְפירה
                          מספרים כמה יושבים). ניהול המוזמנים נעשה בפאנל הצד. */}
                      <span className="seat-layer" aria-hidden="true">
                        {pts.map((p, i) => (
                          <span
                            key={i}
                            className={`seat-pip ${
                              guestAtPoint.has(i) || companionPoints.has(i) ? 'seat-taken' : ''
                            } ${i >= t.capacity ? 'seat-extra' : ''}`}
                            style={{ left: p.left, top: p.top }}
                          />
                        ))}
                      </span>
                      <span className="table-center">
                        <span className="table-num">{t.table_number}</span>
                        {t.name && <span className="table-name">{t.name}</span>}
                        <span className="table-occ">
                          {used}/{t.capacity}
                        </span>
                      </span>
                      {t.locked && (
                        <span className="element-lock-badge" title="נעול">
                          🔒
                        </span>
                      )}
                      {isSelT && !t.locked && soleSelectedNum === t.table_number && (
                        <span
                          className="handle handle-rotate table-rot"
                          title="סובב שולחן"
                          onPointerDown={(e) => onTableRotatePointerDown(e, t.table_number)}
                        />
                      )}
                    </div>

                    {dragOver === t.table_number && (
                      <span className={`free-badge ${free <= 0 ? 'full' : ''}`}>
                        {free > 0 ? `${free} כיסאות פנויים` : 'השולחן מלא'}
                        {liveCheck && liveCheck.lines.length > 0 && (
                          <span className={`free-badge-live ${liveCheck.level}`}>
                            {liveCheck.lines.map((line, i) => (
                              <span key={i}>{line}</span>
                            ))}
                          </span>
                        )}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* פאנל בחירה מרובה */}
          {selectedTables.size > 1 && (
            <div className="hall-props-panel multi" onPointerDown={(e) => e.stopPropagation()}>
              <div className="props-head">
                <h4>נבחרו {selectedTables.size} שולחנות</h4>
                <button className="x" onClick={() => setSelectedTables(new Set())}>
                  ✕
                </button>
              </div>
              <p className="file-name">גררו כל שולחן נבחר כדי להזיז את כולם יחד.</p>
              <div className="props-actions">
                <button
                  className="danger"
                  onClick={() => {
                    selectedTables.forEach((n) => deleteTable(n))
                  }}
                >
                  🗑 מחיקת הנבחרים
                </button>
              </div>
            </div>
          )}

          {/* פאנל עריכת שולחן בודד */}
          {soleSelected && (
            <div className="hall-props-panel" onPointerDown={(e) => e.stopPropagation()}>
              <div className="props-head">
                <h4>עריכת שולחן</h4>
                <button className="x" onClick={() => setSelectedTables(new Set())}>
                  ✕
                </button>
              </div>

              <label className="props-field">
                מספר שולחן
                <input
                  type="number"
                  min={1}
                  defaultValue={soleSelected.table_number}
                  key={soleSelected.table_number}
                  onBlur={(e) => renumberTable(soleSelected.table_number, e.target.value)}
                />
              </label>

              <label className="props-field">
                שם (אופציונלי)
                <input
                  type="text"
                  value={soleSelected.name}
                  maxLength={60}
                  placeholder='למשל "משפחת כהן"'
                  onChange={(e) => updateTable(soleSelected.table_number, { name: e.target.value })}
                />
              </label>

              <div className="props-field">
                סוג שולחן
                <div className="type-chip-row">
                  {(Object.keys(TABLE_TYPE_LABELS) as TableType[]).map((tt) => (
                    <button
                      key={tt}
                      type="button"
                      className={soleSelected.table_type === tt ? 'active' : ''}
                      onClick={() =>
                        updateTable(soleSelected.table_number, {
                          table_type: tt,
                          // שולחן אבירים תמיד מתחיל ב-24 מקומות, כל שאר הסוגים ב-12 —
                          // כי מעבר בין סוגים משנה גם את הגודל הטבעי של השולחן.
                          capacity: defaultCapacityForType(tt),
                        })
                      }
                    >
                      {TABLE_TYPE_LABELS[tt]}
                    </button>
                  ))}
                </div>
              </div>

              <div className="props-field">
                מספר מקומות
                <div className="stepper">
                  <button type="button" onClick={() => bumpCapacity(soleSelected.table_number, -1)}>
                    −
                  </button>
                  <select
                    value={soleSelected.capacity}
                    onChange={(e) =>
                      updateTable(soleSelected.table_number, { capacity: Number(e.target.value) })
                    }
                  >
                    {SEAT_OPTIONS.map((n) => (
                      <option key={n} value={n}>
                        {n}
                      </option>
                    ))}
                  </select>
                  <button type="button" onClick={() => bumpCapacity(soleSelected.table_number, 1)}>
                    +
                  </button>
                </div>
              </div>

              <div className="props-field">
                צבע
                <div className="color-row">
                  {TABLE_COLORS.map((c) => (
                    <button
                      key={c}
                      type="button"
                      className={`color-swatch ${soleSelected.color === c ? 'active' : ''}`}
                      style={{ background: c }}
                      onClick={() => updateTable(soleSelected.table_number, { color: c })}
                    />
                  ))}
                  <button
                    type="button"
                    className={`color-swatch none ${soleSelected.color === '' ? 'active' : ''}`}
                    title="ברירת מחדל"
                    onClick={() => updateTable(soleSelected.table_number, { color: '' })}
                  >
                    ×
                  </button>
                </div>
              </div>

              <div className="props-field">
                יושבים בשולחן ({soleSelected.guests.reduce((s, g) => s + g.seats, 0)}/
                {soleSelected.capacity})
                {soleSelected.guests.length === 0 ? (
                  <p className="seated-empty">גררו מוזמנים מהמגש אל השולחן כדי להושיב אותם כאן.</p>
                ) : (
                  <div className="seated-list">
                    {soleSelected.guests.map((g) => (
                      <span key={g.id} className={`seated-row side-${g.side}`}>
                        <span
                          className="seated-name"
                          draggable
                          onDragStart={(e) => onGuestDragStart(e, g.id)}
                          onDragEnd={onGuestDragEnd}
                          title={`${g.full_name} · ${SIDE_LABELS[g.side]} · גררו לשולחן אחר`}
                        >
                          {g.full_name}
                          {g.seats > 1 && <span className="chip-size">×{g.seats}</span>}
                        </span>
                        <button
                          type="button"
                          className="seated-remove"
                          title="הסרה מהשולחן (חזרה למגש)"
                          onClick={() => moveGuestToTable(g.id, null)}
                        >
                          ✕
                        </button>
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <label className="props-field">
                הערות
                <textarea
                  value={soleSelected.notes}
                  maxLength={400}
                  rows={2}
                  onChange={(e) => updateTable(soleSelected.table_number, { notes: e.target.value })}
                />
              </label>

              <div className="props-actions">
                <button onClick={() => duplicateTable(soleSelected.table_number)}>⧉ שכפול</button>
                <button
                  onClick={() => updateTable(soleSelected.table_number, { locked: !soleSelected.locked })}
                >
                  {soleSelected.locked ? '🔓 שחרור' : '🔒 נעילה'}
                </button>
                <button className="danger" onClick={() => deleteTable(soleSelected.table_number)}>
                  🗑 מחיקה
                </button>
              </div>

              {/* תובנת שולחן מהעוזר החכם — לא פאנל נפרד, כדי למנוע כפילות ממשק */}
              {soleSelectedInsight && (
                <div className={`table-insight ${soleSelectedInsight.hasProblem ? 'has-problem' : ''}`}>
                  <h5>תובנת שולחן</h5>
                  <p>
                    {soleSelectedInsight.occupied}/{soleSelectedInsight.capacity} תפוסים ·{' '}
                    {soleSelectedInsight.free} פנויים
                  </p>
                  {soleSelectedInsight.families.length > 0 && (
                    <p className="table-insight-line">
                      משפחות: {soleSelectedInsight.families.join(', ')}
                    </p>
                  )}
                  {soleSelectedInsight.groups.length > 0 && (
                    <p className="table-insight-line">קבוצות: {soleSelectedInsight.groups.join(', ')}</p>
                  )}
                  {soleSelectedInsight.hasProblem && (
                    <p className="table-insight-warn">⚠ יש בעיה בשולחן הזה — ראו אזהרות למעלה</p>
                  )}
                </div>
              )}
            </div>
          )}

          {/* פאנל עריכת אלמנט (תווית בלבד — צבע/צורה בסרגל הצף שעל האלמנט) */}
          {soleSelectedEl && (
            <div className="hall-props-panel" onPointerDown={(e) => e.stopPropagation()}>
              <div className="props-head">
                <h4>{soleSelectedEl.label}</h4>
                <button className="x" onClick={() => setSelectedEl(null)}>
                  ✕
                </button>
              </div>
              <label className="props-field">
                תווית
                <input
                  type="text"
                  value={soleSelectedEl.label}
                  maxLength={40}
                  onChange={(e) => updateElement(soleSelectedEl.id, { label: e.target.value })}
                />
              </label>

              <div className="props-field props-dim-row">
                <label>
                  רוחב
                  <input
                    type="number"
                    min={30}
                    max={1000}
                    value={Math.round(soleSelectedEl.width)}
                    onChange={(e) =>
                      updateElement(soleSelectedEl.id, { width: clamp(Number(e.target.value) || 30, 30, 1000) })
                    }
                  />
                </label>
                <label>
                  גובה
                  <input
                    type="number"
                    min={20}
                    max={1000}
                    value={Math.round(soleSelectedEl.height)}
                    onChange={(e) =>
                      updateElement(soleSelectedEl.id, { height: clamp(Number(e.target.value) || 20, 20, 1000) })
                    }
                  />
                </label>
                <label>
                  סיבוב°
                  <input
                    type="number"
                    min={-180}
                    max={180}
                    value={Math.round(soleSelectedEl.rotation)}
                    onChange={(e) =>
                      updateElement(soleSelectedEl.id, { rotation: clamp(Number(e.target.value) || 0, -180, 180) })
                    }
                  />
                </label>
              </div>

              <div className="props-actions">
                <button onClick={() => duplicateElement(soleSelectedEl.id)}>⧉ שכפול</button>
                <button onClick={() => toggleElementLock(soleSelectedEl.id)}>
                  {soleSelectedEl.locked ? '🔓 שחרור' : '🔒 נעילה'}
                </button>
                <button className="danger" onClick={() => removeElement(soleSelectedEl.id)}>
                  🗑 מחיקה
                </button>
              </div>

              <p className="file-name">גררו לתזוזה · גררו את הידיות לסיבוב/שינוי גודל, או הזינו ערכים מדויקים למעלה.</p>
            </div>
          )}
        </div>

        {/* עוזר הושבה חכם — פאנל צד קבוע (Dock), לא חלון צף שמכסה את המפה. */}
        {smartPanelOpen && (
          <SmartAssistantPanel
            stats={smartStats}
            warnings={smartWarnings}
            suggestions={smartSuggestions}
            searchQuery={smartSearchQuery}
            onSearchQueryChange={setSmartSearchQuery}
            searchResults={smartSearchResults}
            pendingProposal={pendingProposal}
            onProposeSuggestion={onProposeSuggestion}
            onConfirmProposal={onConfirmProposal}
            onCancelProposal={onCancelProposal}
            onSmartFill={onSmartFill}
            unassignedCount={unassigned.length}
            onClose={() => setSmartPanelOpen(false)}
          />
        )}
      </div>
    </div>
  )
}

function GuestChip({
  g,
  selected,
  onClick,
  onDragStart,
  onDragEnd,
}: {
  g: HallGuest
  selected: boolean
  onClick: (e: React.MouseEvent) => void
  onDragStart?: (e: React.DragEvent) => void
  onDragEnd?: () => void
}) {
  return (
    <span
      className={`guest-chip side-${g.side} ${selected ? 'selected' : ''}`}
      draggable={!!onDragStart}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
      onClick={onClick}
      title={`${SIDE_LABELS[g.side]} · גררו לשולחן או לחצו לבחירה`}
    >
      {g.full_name}
      {g.seats > 1 && <span className="chip-size">×{g.seats}</span>}
    </span>
  )
}

