import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  analyzeConstraints,
  assignSeat,
  generateSeating,
  getHall,
  getReserveSummary,
  listClarifications,
  mediaUrl,
  recommendSeat,
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
  HallLayout,
  HallState,
  ReserveSummary,
  SeatRecommendation,
  SeatingExplanation,
  TableType,
} from '../types'
import { GROUP_LABELS, SIDE_LABELS } from '../types'
import { getEventId } from '../authStore'
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
  is_reserve: boolean
}

const REL_TEXT: Record<Clarification['relation_type'], string> = {
  avoid: 'לא לשבת עם',
  together: 'לשבת עם',
}

// אפשרויות מהירות לכמות מקומות הרזרבה המפוזרים (0 = ללא). מעבר לזה יש שדה חופשי.
const RESERVE_PRESETS = [0, 5, 10, 15] as const

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

// גודל בסיס ללוח האולם (עולם פנימי בקואורדינטות LTR, כמו Figma). הלוח "עוטף"
// את התוכן בפועל (ראה worldSize) עם שוליים נוחים, ואז שכבת ההתאמה-למסך
// (recomputeFit) קובעת קנה-מידה חד-פעמי שמכניס את כל העולם לאזור התצוגה בלי
// גלילה.
// שוליים (ביחידות-עולם) סביב התוכן — "מרחב נשימה" לגרירה, וגם מרווח יפה סביב
// האולם אחרי ההתאמה-למסך. מינימום לעולם כדי שאולם זעיר/ריק לא ייראה מוזר.
const WORLD_MARGIN = 140
const WORLD_MIN_W = 760
const WORLD_MIN_H = 560
// גבולות קנה-המידה של ההתאמה-למסך. תקרה מעל 1 = מרשים הגדלה מתונה כך שאולם
// קטן/בינוני "ימלא" את המסך והאלמנטים יֵראו נוחים (במקום להיתקע קטנים במרכז).
// רצפה נמוכה מאוד — לפי בקשת הבעלים "להכניס הכל בכל מחיר" גם באולם ענק.
const FIT_MAX_SCALE = 2.4
const FIT_MIN_SCALE = 0.08
// יעד-מילוי: האולם ממלא ~95% מהתצוגה, ומשאיר ~5% שוליים נוחים מסביב (כמו עורך
// תוכנית-רצפה מקצועי). זה גם מבטיח שאף פעם אין גלילה — תמיד יש מרווח.
const FIT_SAFETY = 0.95
// ריפוד (ביחידות-עולם) שנוסף סביב גבולות התוכן בחישוב ה-fit, כדי שכיסאות/תוויות
// שבולטים מעט מעבר לקופסת השולחן לא ייגעו בקצה המסך.
const FIT_CONTENT_PAD = 16

// ---- פרופיל צפיפות: גודל אלמנטים קבוע לפי מספר השולחנות המתוכנן ----
// במקום להקטין את כל המפה בכל שינוי, מחליטים מראש על גודל האלמנטים לפי כמות
// השולחנות. הפרופיל נבחר פעם אחת (בהגדרת האולם) ונשמר נעול — הוא לא משתנה
// לבד כשמוסיפים כיסאות או שולחנות. כל האלמנטים באולם חולקים את אותו קנה-מידה.
type DensityKey = 'spacious' | 'comfortable' | 'compact' | 'dense'

interface DensityPreset {
  round: number // קוטר לשולחן עגול/מרובע
  knightsW: number // אורך שולחן אבירים/מלבני
  knightsH: number
  dance: { w: number; h: number }
  bar: { w: number; h: number }
  dj: { w: number; h: number }
  ring: number // מרווח בין שולחנות בסקיצה האוטומטית
}

const DENSITY_PRESETS: Record<DensityKey, DensityPreset> = {
  spacious: { round: 150, knightsW: 300, knightsH: 66, dance: { w: 270, h: 156 }, bar: { w: 224, h: 66 }, dj: { w: 152, h: 60 }, ring: 210 },
  comfortable: { round: 122, knightsW: 252, knightsH: 58, dance: { w: 226, h: 132 }, bar: { w: 194, h: 58 }, dj: { w: 140, h: 56 }, ring: 176 },
  compact: { round: 98, knightsW: 204, knightsH: 52, dance: { w: 192, h: 112 }, bar: { w: 166, h: 52 }, dj: { w: 128, h: 50 }, ring: 146 },
  dense: { round: 80, knightsW: 168, knightsH: 46, dance: { w: 168, h: 98 }, bar: { w: 150, h: 46 }, dj: { w: 118, h: 44 }, ring: 122 },
}

function densityKeyForCount(n: number): DensityKey {
  if (n <= 10) return 'spacious'
  if (n <= 20) return 'comfortable'
  if (n <= 35) return 'compact'
  return 'dense'
}

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

// גודל חזותי של השולחן (בפיקסלים) — קבוע לפי פרופיל הצפיפות בלבד, לא לפי מספר
// הכיסאות. הוספת/הסרת כיסא לא משנה את גודל השולחן (הכיסאות פשוט מתפזרים סביב
// אותה מסגרת קבועה). כל השולחנות באולם באותו קנה-מידה.
function tableSize(type: TableType, preset: DensityPreset): { w: number; h: number } {
  if (type === 'round' || type === 'square') {
    return { w: preset.round, h: preset.round }
  }
  // מלבני / אבירים — שולחן ארוך בגודל קבוע לפי הפרופיל.
  return { w: preset.knightsW, h: preset.knightsH }
}

// גודל אלמנט מיוחד (רחבה/בר/DJ) לפי פרופיל הצפיפות. שאר הסוגים → null (גודל
// ברירת המחדל מ-ELEMENT_DEFS).
function elementSizeFor(type: HallElementType, preset: DensityPreset): { w: number; h: number } | null {
  if (type === 'dance_floor') return preset.dance
  if (type === 'bar') return preset.bar
  if (type === 'dj') return preset.dj
  return null
}

export type HallOrientation = 'landscape' | 'portrait'

// ─── פריסת רצועות משותפת ─────────────────────────────────────────────────
// מחשב מיקומים (פינה שמאלית-עליונה, בקואורדינטות חיוביות) לפריסה מסודרת:
// DJ + רחבת ריקודים למעלה, רצועת אבירים, הבר במרכז, ורצועת עגולים למטה.
// האוריינטציה קובעת את *צורת* הרצועות: 'landscape' → שורות רחבות (מעט שורות,
// הרבה עמודות); 'portrait' → צר וגבוה (מעט עמודות, הרבה שורות). אותה פונקציה
// משמשת גם ל"בניית אולם" מאפס וגם ל"סידור מחדש" של שולחנות קיימים לפי
// אוריינטציה — כך שתמיד מקבלים בדיוק את אותה פוזה.
function buildBandLayout(args: {
  regular: number
  knights: number
  dance: boolean
  dj: boolean
  bar: boolean
  orientation: HallOrientation
  p: DensityPreset
}): {
  round: { x: number; y: number; w: number; h: number }[]
  knights: { x: number; y: number; w: number; h: number }[]
  elements: { type: HallElementType; x: number; y: number; w: number; h: number }[]
} {
  const { p, orientation } = args
  const regular = Math.max(0, args.regular)
  const knights = Math.max(0, args.knights)
  const total = regular + knights

  // מספר העמודות ברצועה, לפי האוריינטציה:
  // לרוחב — מעט שורות (2 כברירת מחדל, 3 כשהרבה) ולכן הרבה עמודות.
  // לאורך — מעט עמודות (2, או 3 כשהרבה) ולכן הרבה שורות → צר וגבוה.
  const colsFor = (n: number) => {
    if (n <= 0) return 0
    if (orientation === 'portrait') return n <= 2 ? n : n <= 12 ? 2 : 3
    const rows = n <= 2 ? 1 : n <= 16 ? 2 : 3
    return Math.ceil(n / rows)
  }

  const gapFactor = clamp(0.42 - total * 0.004, 0.2, 0.42)
  const roundCell = p.round + Math.round(p.round * gapFactor) + 18
  const knightCellW = p.knightsW + Math.round(p.knightsW * gapFactor) + 18
  const knightCellH = p.knightsH + Math.round(p.knightsH * gapFactor) + 18
  const vGap = Math.round(roundCell * 0.22) + 28

  type CP = { cx: number; cy: number; w: number; h: number }
  const elDefs: { type: HallElementType; place: CP }[] = []
  const roundPlaces: CP[] = []
  const knightPlaces: CP[] = []

  const placeBand = (count: number, cols: number, cellW: number, cellH: number, topY: number, tW: number, tH: number, out: CP[]) => {
    const rows = Math.max(1, Math.ceil(count / cols))
    for (let i = 0; i < count; i++) {
      const row = Math.floor(i / cols)
      const col = i % cols
      const inThisRow = Math.min(cols, count - row * cols)
      const rowW = inThisRow * cellW
      const cx = col * cellW + cellW / 2 - rowW / 2
      const cy = topY + row * cellH + cellH / 2
      out.push({ cx, cy, w: tW, h: tH })
    }
    return rows * cellH
  }

  let topY = 0
  if (args.dj) {
    elDefs.push({ type: 'dj', place: { cx: 0, cy: topY + p.dj.h / 2, w: p.dj.w, h: p.dj.h } })
    topY += p.dj.h + vGap
  }
  if (args.dance) {
    elDefs.push({ type: 'dance_floor', place: { cx: 0, cy: topY + p.dance.h / 2, w: p.dance.w, h: p.dance.h } })
    topY += p.dance.h + vGap
  }
  if (knights > 0) {
    topY += placeBand(knights, colsFor(knights), knightCellW, knightCellH, topY, p.knightsW, p.knightsH, knightPlaces) + vGap
  }
  if (args.bar) {
    elDefs.push({ type: 'bar', place: { cx: 0, cy: topY + p.bar.h / 2, w: p.bar.w, h: p.bar.h } })
    topY += p.bar.h + vGap
  }
  if (regular > 0) {
    topY += placeBand(regular, colsFor(regular), roundCell, roundCell, topY, p.round, p.round, roundPlaces)
  }

  // נרמול לקואורדינטות חיוביות (פינה שמאלית-עליונה בריפוד 50).
  const all: CP[] = [...elDefs.map((e) => e.place), ...roundPlaces, ...knightPlaces]
  let minX = Infinity
  let minY = Infinity
  for (const pl of all) {
    minX = Math.min(minX, pl.cx - pl.w / 2)
    minY = Math.min(minY, pl.cy - pl.h / 2)
  }
  if (!isFinite(minX)) {
    minX = 0
    minY = 0
  }
  const offX = 50 - minX
  const offY = 50 - minY
  const toXY = (pl: CP) => ({
    x: Math.round(pl.cx - pl.w / 2 + offX),
    y: Math.round(pl.cy - pl.h / 2 + offY),
    w: pl.w,
    h: pl.h,
  })

  return {
    round: roundPlaces.map(toXY),
    knights: knightPlaces.map(toXY),
    elements: elDefs.map((e) => ({ type: e.type, ...toXY(e.place) })),
  }
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
  | 'square'
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
  | 'check'

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
    case 'square':
      return (
        <svg {...common}>
          <rect x="5" y="5" width="14" height="14" rx="2" />
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
    case 'check':
      return (
        <svg {...common}>
          <path d="M5 12.5 10 17.5 19.5 7" />
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

/** אשף בניית האולם — נפתח כשהאולם ריק (או מכפתור "בניית אולם מחדש"). שואל כמה
 *  שולחנות רגילים/אבירים ואילו אלמנטים מרכזיים לכלול, ומייצר סקיצה התחלתית. */
function HallWizard(props: {
  regular: number
  knights: number
  dance: boolean
  dj: boolean
  bar: boolean
  hasContent: boolean
  onRegular: (n: number) => void
  onKnights: (n: number) => void
  onDance: (b: boolean) => void
  onDj: (b: boolean) => void
  onBar: (b: boolean) => void
  onBuild: () => void
  onClose: () => void
}) {
  const total = Math.max(0, props.regular) + Math.max(0, props.knights)
  const clampNum = (v: number) => Math.max(0, Math.round(v || 0))
  return (
    <>
      <div className="hm-wizard-backdrop" onClick={props.onClose} />
      <div className="hm-wizard" role="dialog" aria-label="בניית אולם">
        <h2 className="hm-wizard-title">בואו נבנה את האולם 🏛️</h2>
        <p className="hm-wizard-lead">
          כמה שולחנות יהיו, ומה עוד להוסיף? נכין לכם סקיצה מסודרת להתחיל ממנה —
          תוכלו לגרור, לסובב ולשנות הכול אחר כך.
        </p>

        <div className="hm-wizard-row">
          <label>שולחנות רגילים (12 מקומות)</label>
          <div className="hm-wizard-stepper">
            <button type="button" onClick={() => props.onRegular(Math.max(0, props.regular - 1))}>
              −
            </button>
            <input
              type="number"
              min={0}
              value={props.regular}
              onChange={(e) => props.onRegular(clampNum(Number(e.target.value)))}
            />
            <button type="button" onClick={() => props.onRegular(props.regular + 1)}>
              +
            </button>
          </div>
        </div>

        <div className="hm-wizard-row">
          <label>שולחנות אבירים (ארוכים, 24)</label>
          <div className="hm-wizard-stepper">
            <button type="button" onClick={() => props.onKnights(Math.max(0, props.knights - 1))}>
              −
            </button>
            <input
              type="number"
              min={0}
              value={props.knights}
              onChange={(e) => props.onKnights(clampNum(Number(e.target.value)))}
            />
            <button type="button" onClick={() => props.onKnights(props.knights + 1)}>
              +
            </button>
          </div>
        </div>

        <p className="hm-wizard-sub">מה עוד להוסיף למרכז האולם?</p>
        <div className="hm-wizard-toggles">
          <label className={`hm-wizard-toggle ${props.dance ? 'on' : ''}`}>
            <input type="checkbox" checked={props.dance} onChange={(e) => props.onDance(e.target.checked)} />
            <span>💃 רחבת ריקודים</span>
          </label>
          <label className={`hm-wizard-toggle ${props.dj ? 'on' : ''}`}>
            <input type="checkbox" checked={props.dj} onChange={(e) => props.onDj(e.target.checked)} />
            <span>🎧 עמדת DJ</span>
          </label>
          <label className={`hm-wizard-toggle ${props.bar ? 'on' : ''}`}>
            <input type="checkbox" checked={props.bar} onChange={(e) => props.onBar(e.target.checked)} />
            <span>🥂 בר</span>
          </label>
        </div>

        <p className="hm-wizard-total">סה"כ {total} שולחנות</p>

        {props.hasContent && (
          <p className="hm-wizard-warn">
            ⚠ בנייה מחדש תחליף את הסידור הנוכחי — המוזמנים המשובצים יחזרו ל"ללא שולחן".
          </p>
        )}

        <div className="hm-wizard-actions">
          <button className="hm-wizard-build" onClick={props.onBuild} disabled={total === 0}>
            בניית האולם
          </button>
          <button className="hm-wizard-cancel" onClick={props.onClose}>
            {props.hasContent ? 'ביטול' : 'אתחיל ממסך ריק'}
          </button>
        </div>
      </div>
    </>
  )
}

// ─── עורך הסקיצה ─────────────────────────────────────────────────────────
// חלון עריכה שנפתח מיד אחרי בחירת קובץ, לפני שמירה. הזוג יכול להזיז, לזום,
// לסובב ולחתוך את התמונה בתוך מסגרת חיתוך ביחס-ממדים של הקנבס — ורק ב"אישור"
// אנחנו "אופים" את מה שבתוך המסגרת לתמונה נקייה אחת שנשמרת ומוצגת כרקע.
// הכל רץ על קנבס יחיד: אותו חישוב מצייר גם את התצוגה החיה וגם את הפלט הסופי,
// כך שמה שרואים במסגרת הוא בדיוק מה שנשמר. בלי ספריות חיצוניות.
function SketchEditor(props: {
  src: string
  baseAspect: number // יחס הבסיס לרוחב (>1) — לאורך זהו ההפוך שלו
  orientation: HallOrientation
  onCancel: () => void
  onConfirm: (dataUrl: string, orientation: HallOrientation) => void
}) {
  const { src, baseAspect } = props
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const stageRef = useRef<HTMLDivElement | null>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)
  const [ready, setReady] = useState(false)
  const [failed, setFailed] = useState(false)
  const [orient, setOrient] = useState<HallOrientation>(props.orientation)
  const [scale, setScale] = useState(1) // 1 = "cover" (ממלא את המסגרת)
  const [rotation, setRotation] = useState(0) // מעלות, בקפיצות של 90°
  const [offset, setOffset] = useState({ x: 0, y: 0 }) // הזזה בפיקסלים של הבמה
  const [tick, setTick] = useState(0) // מאלץ ציור-מחדש בשינוי גודל הבמה
  const dragRef = useRef<{ px: number; py: number; ox: number; oy: number } | null>(null)

  // יחס מסגרת החיתוך: לרוחב = baseAspect (>1, רחב); לאורך = ההופכי (<1, גבוה).
  const aspect = orient === 'portrait' ? 1 / baseAspect : baseAspect

  // טעינת התמונה. לתמונה שמורה (media URL, אולי ממקור אחר) מבקשים crossOrigin
  // כדי שה-canvas לא "יזדהם" ונוכל לייצא ממנו; ל-data URL זה לא רלוונטי.
  useEffect(() => {
    const image = new Image()
    if (!/^data:/i.test(src)) image.crossOrigin = 'anonymous'
    image.onload = () => {
      imgRef.current = image
      setReady(true)
    }
    image.onerror = () => setFailed(true)
    image.src = src
    return () => {
      image.onload = null
      image.onerror = null
    }
  }, [src])

  // מלבן מסגרת החיתוך בתוך הבמה — ממורכז, עם שוליים, לפי היחס aspect.
  function frameRect(sw: number, sh: number) {
    const pad = 20
    let fw = sw - pad * 2
    let fh = fw / aspect
    if (fh > sh - pad * 2) {
      fh = sh - pad * 2
      fw = fh * aspect
    }
    return { x: (sw - fw) / 2, y: (sh - fh) / 2, w: fw, h: fh }
  }

  // מידות התמונה אחרי סיבוב (90/270 מחליפים רוחב/גובה).
  function rotatedImgDims() {
    const img = imgRef.current!
    const rot = ((rotation % 360) + 360) % 360
    const swap = rot === 90 || rot === 270
    return { ew: swap ? img.height : img.width, eh: swap ? img.width : img.height }
  }

  // סקייל-בסיס שממלא (cover) את המסגרת כשזום=1.
  function coverScale(fw: number, fh: number) {
    const { ew, eh } = rotatedImgDims()
    return Math.max(fw / ew, fh / eh)
  }

  // ציור הסצנה על קשר נתון, בקואורדינטות של הבמה. forExport => רקע לבן בתוך
  // המסגרת (כדי שאזורי "לטרבוקס" בזום-אאוט לא ייצאו שחורים).
  function paint(ctx: CanvasRenderingContext2D, sw: number, sh: number, fr: { x: number; y: number; w: number; h: number }, forExport: boolean) {
    const img = imgRef.current!
    if (forExport) {
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(fr.x, fr.y, fr.w, fr.h)
    }
    const s = coverScale(fr.w, fr.h) * scale
    ctx.save()
    ctx.translate(sw / 2 + offset.x, sh / 2 + offset.y)
    ctx.rotate((rotation * Math.PI) / 180)
    ctx.drawImage(img, (-img.width * s) / 2, (-img.height * s) / 2, img.width * s, img.height * s)
    ctx.restore()
  }

  // תצוגה חיה: מציירים את התמונה, מחשיכים מחוץ למסגרת, ומוסיפים מסגרת + קווי שליש.
  useEffect(() => {
    if (!ready) return
    const canvas = canvasRef.current
    const stage = stageRef.current
    if (!canvas || !stage) return
    const sw = Math.max(1, stage.clientWidth)
    const sh = Math.max(1, stage.clientHeight)
    canvas.width = sw
    canvas.height = sh
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const fr = frameRect(sw, sh)
    ctx.clearRect(0, 0, sw, sh)
    paint(ctx, sw, sh, fr, false)
    // החשכה מחוץ למסגרת (חור באמצעות evenodd)
    ctx.save()
    ctx.fillStyle = 'rgba(24, 22, 18, 0.55)'
    ctx.beginPath()
    ctx.rect(0, 0, sw, sh)
    ctx.rect(fr.x, fr.y, fr.w, fr.h)
    ctx.fill('evenodd')
    ctx.restore()
    // מסגרת + קווי שליש עדינים
    ctx.strokeStyle = 'rgba(255,255,255,0.95)'
    ctx.lineWidth = 2
    ctx.strokeRect(fr.x + 1, fr.y + 1, fr.w - 2, fr.h - 2)
    ctx.strokeStyle = 'rgba(255,255,255,0.28)'
    ctx.lineWidth = 1
    for (let i = 1; i < 3; i++) {
      ctx.beginPath()
      ctx.moveTo(fr.x + (fr.w * i) / 3, fr.y)
      ctx.lineTo(fr.x + (fr.w * i) / 3, fr.y + fr.h)
      ctx.moveTo(fr.x, fr.y + (fr.h * i) / 3)
      ctx.lineTo(fr.x + fr.w, fr.y + (fr.h * i) / 3)
      ctx.stroke()
    }
  }, [ready, scale, rotation, offset, tick, aspect])

  // מעקב אחרי שינוי גודל הבמה (סיבוב מסך/שינוי חלון) — ציור מחדש.
  useEffect(() => {
    const stage = stageRef.current
    if (!stage || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => setTick((t) => t + 1))
    ro.observe(stage)
    return () => ro.disconnect()
  }, [])

  // גרירה = הזזת התמונה.
  function onPointerDown(e: React.PointerEvent) {
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
    dragRef.current = { px: e.clientX, py: e.clientY, ox: offset.x, oy: offset.y }
  }
  function onPointerMove(e: React.PointerEvent) {
    const d = dragRef.current
    if (!d) return
    setOffset({ x: d.ox + (e.clientX - d.px), y: d.oy + (e.clientY - d.py) })
  }
  function onPointerUp() {
    dragRef.current = null
  }
  function onWheel(e: React.WheelEvent) {
    setScale((s) => clamp(s * (e.deltaY < 0 ? 1.08 : 1 / 1.08), 0.2, 5))
  }

  function reset() {
    setScale(1)
    setRotation(0)
    setOffset({ x: 0, y: 0 })
  }

  // "אפייה": מציירים את אזור המסגרת בלבד לקנבס פלט ברזולוציה טובה ומייצאים.
  function confirm() {
    const stage = stageRef.current
    if (!stage || !imgRef.current) return
    const sw = Math.max(1, stage.clientWidth)
    const sh = Math.max(1, stage.clientHeight)
    const fr = frameRect(sw, sh)
    const outW = 1600
    const outH = Math.round(outW / aspect)
    const k = outW / fr.w // מיפוי פיקסלֵי-במה ← פיקסלֵי-פלט
    const out = document.createElement('canvas')
    out.width = outW
    out.height = outH
    const ctx = out.getContext('2d')
    if (!ctx) return
    // ממפים כך שפינת המסגרת (fr.x,fr.y) תיפול על (0,0) של הפלט, בקנה-מידה k.
    ctx.setTransform(k, 0, 0, k, -fr.x * k, -fr.y * k)
    paint(ctx, sw, sh, fr, true)
    try {
      props.onConfirm(out.toDataURL('image/jpeg', 0.85), orient)
    } catch {
      setFailed(true)
    }
  }

  return (
    <>
      <div className="sk-editor-backdrop" onClick={props.onCancel} />
      <div className="sk-editor" role="dialog" aria-label="עריכת סקיצת האולם">
        <div className="sk-editor-head">
          <h2>עריכת סקיצת האולם ✂️</h2>
          <p>גררו להזזה · השתמשו בזום כדי להתקרב · סובבו אם צריך. מה שבתוך המסגרת יהפוך לרקע.</p>
        </div>

        {failed ? (
          <div className="sk-editor-stage sk-editor-error">
            <p>לא הצלחנו לטעון את התמונה לעריכה. נסו להעלות תמונה אחרת.</p>
          </div>
        ) : (
          <div
            className="sk-editor-stage"
            ref={stageRef}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={onPointerUp}
            onWheel={onWheel}
          >
            <canvas ref={canvasRef} className="sk-editor-canvas" />
            {!ready && <div className="sk-editor-loading">טוען תמונה…</div>}
          </div>
        )}

        <div className="sk-editor-controls">
          <div className="sk-orient" role="group" aria-label="כיוון האולם">
            <button
              type="button"
              className={orient === 'landscape' ? 'sk-orient-on' : ''}
              onClick={() => setOrient('landscape')}
              title="אולם לרוחב"
            >
              ▭ לרוחב
            </button>
            <button
              type="button"
              className={orient === 'portrait' ? 'sk-orient-on' : ''}
              onClick={() => setOrient('portrait')}
              title="אולם לאורך"
            >
              ▯ לאורך
            </button>
          </div>
          <div className="sk-zoom">
            <button type="button" onClick={() => setScale((s) => clamp(s / 1.15, 0.2, 5))} aria-label="הקטנה">
              −
            </button>
            <input
              type="range"
              min={0.2}
              max={5}
              step={0.01}
              value={scale}
              onChange={(e) => setScale(Number(e.target.value))}
              aria-label="זום"
            />
            <button type="button" onClick={() => setScale((s) => clamp(s * 1.15, 0.2, 5))} aria-label="הגדלה">
              +
            </button>
          </div>
          <div className="sk-rotate">
            <button type="button" onClick={() => setRotation((r) => r - 90)} title="סיבוב שמאלה">
              ↺
            </button>
            <button type="button" onClick={() => setRotation((r) => r + 90)} title="סיבוב ימינה">
              ↻
            </button>
            <button type="button" className="sk-reset" onClick={reset}>
              איפוס
            </button>
          </div>
        </div>

        <div className="sk-editor-actions">
          <button className="sk-confirm" onClick={confirm} disabled={!ready || failed}>
            אישור והוספה לקנבס
          </button>
          <button className="sk-cancel" onClick={props.onCancel}>
            ביטול
          </button>
        </div>
      </div>
    </>
  )
}

export function HallPage() {
  const [tables, setTables] = useState<TableView[]>([])
  const [unassigned, setUnassigned] = useState<HallGuest[]>([])
  const [elements, setElements] = useState<HallElement[]>([])
  const [seats, setSeats] = useState(12)
  // יעד מקומות רזרבה מפוזרים שנבחר לאירוע (נשמר, מוצג בפאנל יום האירוע).
  const [reserveSeats, setReserveSeats] = useState(0)
  // ---- מצב יום האירוע (ניהול בזמן אמת) ----
  const [dayMode, setDayMode] = useState(false)
  const [reserveSummary, setReserveSummary] = useState<ReserveSummary | null>(null)
  // המוזמן שנבחר לשיבוץ מהיר + ההמלצות שחזרו עבורו (null = טרם נטען/סגור).
  const [assignGuestId, setAssignGuestId] = useState<number | null>(null)
  const [recs, setRecs] = useState<SeatRecommendation[] | null>(null)
  const [recLoading, setRecLoading] = useState(false)
  const [assignBusy, setAssignBusy] = useState(false)
  const [assignNote, setAssignNote] = useState('')
  // פרופיל הפריסה של האולם (density + planned). null = טרם הוגדר (אולם ישן/ריק).
  const [hallLayout, setHallLayout] = useState<HallLayout | null>(null)
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
  // שמירה אוטומטית (בלי כפתור): saving = בקשת שמירה פעילה כרגע.
  const [saving, setSaving] = useState(false)
  const [savedTick, setSavedTick] = useState(false) // הבהוב "נשמר ✓" קצר
  const [error, setError] = useState('')
  // הסברי "למה שובץ כאן" מהסידור האוטומטי האחרון — מוצגים בפאנל סיכום שאפשר לסגור.
  const [seatExplain, setSeatExplain] = useState<SeatingExplanation[]>([])

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
  // טיוטת "מספר שולחן" בעריכה — שדה מבוקר, כדי שכל הקלדה תישמר מיד ולא נסמוך
  // על קריאה עמומה ב-onBlur (שבנייד לפעמים מחזירה ערך ריק/ישן).
  const [numDraft, setNumDraft] = useState('')
  // כשמוסיפים מוזמן לשולחן מסוים דרך ה-Bottom Sheet: מעבר ללשונית "מוזמנים"
  // במצב "שיוך" — כל הקשה על מוזמן משבצת אותו ישירות לשולחן הזה.
  const [assignTarget, setAssignTarget] = useState<number | null>(null)
  const [fabOpen, setFabOpen] = useState(false)
  const [mobileSearch, setMobileSearch] = useState('')
  // מדריך פתיחה קצר למשתמש. נפתח אוטומטית בביקור הראשון (נשמר ב-localStorage),
  // וניתן לפתוח שוב בכל רגע מכפתור "?" בפס העליון.
  const [guideOpen, setGuideOpen] = useState(false)
  // אשף בניית האולם (שלב 2). נפתח אוטומטית כשהאולם ריק, וניתן לפתוח שוב
  // בכל רגע מכפתור "בניית אולם מחדש". שואל כמה שולחנות רגילים (12) ואבירים,
  // ואילו אלמנטים לכלול (רחבה/DJ/בר), ואז מייצר סקיצה התחלתית מסודרת.
  const [wizardOpen, setWizardOpen] = useState(false)
  const [wzRegular, setWzRegular] = useState(0)
  const [wzKnights, setWzKnights] = useState(0)
  const [wzDance, setWzDance] = useState(true)
  const [wzDj, setWzDj] = useState(true)
  const [wzBar, setWzBar] = useState(true)
  // כיוון האולם (לרוחב/לאורך). נקבע בעורך הסקיצה ומכתיב את סידור רצועות
  // ההושבה. שינוי כיוון מסדר-מחדש מיד גם שולחנות קיימים (תוך שמירת השיבוצים).
  const [hallOrientation, setHallOrientation] = useState<HallOrientation>('landscape')
  const [viewTransform, setViewTransform] = useState<string | undefined>(undefined)
  // קנה-המידה הנוכחי של הלוח במובייל (1 בדסקטופ). נחשף כמשתנה CSS כדי
  // שידיות הסיבוב/שינוי-הגודל יישארו בגודל-מסך קבוע ונוח למגע גם כשהלוח מוקטן.
  const [viewScale, setViewScale] = useState(1)

  // ---- לוח האולם: בלי זום — תמיד בגודל אמיתי (100%), נגלל באופן טבעי ----
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const worldRef = useRef<HTMLDivElement | null>(null)

  // ---- מובייל: התאמת האולם אוטומטית למסך (Fit-to-Screen) ----
  // בדסקטופ scale=1 והיסט=0, כך שכל החישובים למטה מתנהגים בדיוק כמו קודם.
  // במובייל הלוח מוקטן וממורכז דרך transform על .hall-world, ולכן צריך
  // לתרגם נקודת-מגע חזרה לקואורדינטת-לוח לפי קנה-המידה וההיסט.
  const scaleRef = useRef(1)
  const offsetRef = useRef({ x: 0, y: 0 })

  // מראה עדכנית של השולחנות/האלמנטים ל-recomputeFit — כדי שההתאמה-למסך תוכל
  // לקרוא את המיקומים הנוכחיים בלי לתלות את עצמה ב-tables/elements. כך גרירה
  // (ששִנתה מיקום בלבד) לא מפעילה refit ולא מכווצת את המפה בכל תזוזה.
  const tablesRef = useRef(tables)
  const elementsRef = useRef(elements)
  useEffect(() => {
    tablesRef.current = tables
  }, [tables])
  useEffect(() => {
    elementsRef.current = elements
  }, [elements])

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
  // עורך הסקיצה: התמונה הגולמית שממתינה לעריכה (לפני שמירה), והתמונה
  // המקורית שנשמרת בזיכרון-הפעלה כדי שעריכה חוזרת תהיה איכותית (חיתוך-מחדש
  // מהמקור ולא מהתמונה שכבר נחתכה). לא נשמר בשרת — רק לנוחות הסשן.
  const [sketchEditSrc, setSketchEditSrc] = useState<string | null>(null)
  const sketchOriginalRef = useRef<string | null>(null)

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
  // נקודת-המסך שבה התחילה הגרירה — לחישוב סף-תזוזה שמבדיל בין הקשה (בחירה)
  // לבין גרירה אמיתית (הזזה). כך נגיעה קטנה עם רעד-אצבע לא נחשבת גרירה.
  const dragStartRef = useRef<{ x: number; y: number } | null>(null)
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

  // פרופיל הצפיפות בפועל: אם נשמר פרופיל נעול — משתמשים בו; אחרת (אולם ישן
  // ללא הגדרה) נגזר מכמות השולחנות הנוכחית, כדי שנתונים קיימים ייראו תקין.
  const densityKey: DensityKey = hallLayout?.density ?? densityKeyForCount(tables.length)
  const preset = DENSITY_PRESETS[densityKey]
  // מראה עדכנית של הפרופיל ל-recomputeFit — כדי שההתאמה-למסך תקרא את הגדלים
  // הנוכחיים בלי לתלות את עצמה ב-preset (ולהיבנות מחדש בכל שינוי).
  const presetRef = useRef(preset)
  useEffect(() => {
    presetRef.current = preset
  }, [preset])

  // גודל הלוח גדל דינמית כדי להכיל את כל התוכן (שולחנות + אלמנטים) עם שוליים,
  // כך שאפשר לגלול לכל פינה בלי לחתוך — ובלי להקטין שום דבר. מינימום = גודל
  // בסיס (WORLD_W/H) כשהאולם קטן.
  const worldSize = useMemo(() => {
    let maxX = 0
    let maxY = 0
    for (const t of tables) {
      const { w, h } = tableSize(t.table_type, preset)
      maxX = Math.max(maxX, t.x + w)
      maxY = Math.max(maxY, t.y + h)
    }
    for (const el of elements) {
      maxX = Math.max(maxX, el.x + el.width)
      maxY = Math.max(maxY, el.y + el.height)
    }
    return {
      w: Math.max(WORLD_MIN_W, Math.ceil(maxX) + WORLD_MARGIN),
      h: Math.max(WORLD_MIN_H, Math.ceil(maxY) + WORLD_MARGIN),
    }
  }, [tables, elements, preset])

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
        is_reserve: t.is_reserve ?? false,
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
    setReserveSeats(h.reserve_seats ?? 0)
    setHallLayout(h.hall_layout ?? null)
    setWarnings(h.warnings)
    setSketch(h.sketch ?? null)
    setForbiddenPairs(h.forbidden_pairs ?? [])
    setTogetherPairs(h.together_pairs ?? [])
    setDirty(false)
  }, [])

  const load = useCallback(async () => {
    setError('')
    try {
      const h = await getHall()
      applyState(h)
      // אולם ריק לגמרי (בלי שולחנות ובלי אלמנטים) => פותחים את אשף הבנייה
      // אוטומטית, כדי שהזוג יתחיל מסקיצה מסודרת ולא ממסך ריק.
      if (h.tables.length === 0 && (h.elements?.length ?? 0) === 0) {
        setWizardOpen(true)
      }
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

  // ---- התאמה-למסך חד-פעמית (Auto-Fit) ----
  // מחשבים קנה-מידה אחד שמכניס את כל העולם (התוכן + שוליים) לאזור התצוגה, וממרכז
  // אותו. זה רץ *פעם אחת* בכניסה, אחרי בניית אולם, ובשינוי גודל מסך/סיבוב — אבל
  // *לא* בהוספת שולחן/כיסא או בגרירה, כדי שלא יהיו קפיצות-גודל תוך כדי עבודה.
  // הידיות והתוויות נשארות בגודל-מסך דרך המשתנה --hm-s (counter-scale ב-CSS).
  const recomputeFit = useCallback(() => {
    const vp = viewportRef.current
    if (!vp) return
    const vpW = vp.clientWidth
    const vpH = vp.clientHeight
    if (!vpW || !vpH) return
    // ---- Fit Bounds אמיתי (כמו Figma / Google Maps) ----
    // מחשבים את *גבולות התוכן האמיתיים* (bbox של כל השולחנות והאלמנטים), מתאימים
    // קנה-מידה שממלא את היעד (~85%), וממרכזים את מרכז-התוכן בדיוק במרכז המסך.
    // זה מתעלם לחלוטין מגודל "קופסת העולם"/מינימום/ריפוד — כך התוכן תמיד ממורכז
    // ומלא, בין אם יש 2 שולחנות ובין אם 80.
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    for (const t of tablesRef.current) {
      const { w, h } = tableSize(t.table_type, presetRef.current)
      minX = Math.min(minX, t.x)
      minY = Math.min(minY, t.y)
      maxX = Math.max(maxX, t.x + w)
      maxY = Math.max(maxY, t.y + h)
    }
    for (const el of elementsRef.current) {
      minX = Math.min(minX, el.x)
      minY = Math.min(minY, el.y)
      maxX = Math.max(maxX, el.x + el.width)
      maxY = Math.max(maxY, el.y + el.height)
    }
    // אין תוכן עדיין — לא משנים כלום (נחכה שהתוכן ייטען ואז נריץ שוב).
    if (!isFinite(minX)) return
    // ריפוד קטן (ביחידות-עולם) סביב התוכן כדי שכיסאות/תוויות שבולטים לא ייגעו
    // בקצה. זה חלק מחישוב ה-fit בלבד.
    const pad = FIT_CONTENT_PAD
    const contentW = maxX - minX + pad * 2
    const contentH = maxY - minY + pad * 2
    const s = clamp(
      Math.min(vpW / contentW, vpH / contentH) * FIT_SAFETY,
      FIT_MIN_SCALE,
      FIT_MAX_SCALE,
    )
    // מרכז התוכן → מרכז אזור-התצוגה. (transformOrigin של .hall-world הוא 0 0,
    // ולכן offset = מרכז-מסך פחות מרכז-התוכן בקנה-מידה.)
    const centerX = (minX + maxX) / 2
    const centerY = (minY + maxY) / 2
    const offX = vpW / 2 - centerX * s
    const offY = vpH / 2 - centerY * s
    scaleRef.current = s
    offsetRef.current = { x: offX, y: offY }
    setViewScale(s)
    setViewTransform(`translate(${offX}px, ${offY}px) scale(${s})`)
  }, [])

  // Auto-Fit: מתאימים מחדש בכל פעם שגודל התוכן (worldSize) משתנה — טעינה, הוספת
  // שולחן/אלמנט, בנייה מחדש — כך תמיד רואים את *כל* האולם ואף פעם לא נחתך חצי.
  // חשוב: התלות ב-worldSize פותרת את הבאג המקורי — קודם ההתאמה רצה פעם אחת מוקדם
  // מדי (לפני שהשולחנות נטענו) וחישבה "אולם ריק", ואז לא רצה שוב. עכשיו היא רצה
  // כשהתוכן האמיתי מוכן. מדלגים רק בזמן גרירה פעילה כדי לא להילחם באצבע.
  useEffect(() => {
    if (loading) return
    if (dragRef.current) return
    const id = requestAnimationFrame(() => recomputeFit())
    return () => cancelAnimationFrame(id)
  }, [worldSize, loading, recomputeFit])

  // שינוי גודל מסך/סיבוב מכשיר — הסביבה השתנתה, אז מתאימים מחדש (לא "זום תוך
  // כדי עבודה"). מדלגים בזמן גרירה כדי לא לקטוע אותה. ResizeObserver יורה גם
  // מיד עם ההרשמה — משמש גם כרשת-ביטחון ל-Fit הראשוני.
  useEffect(() => {
    const vp = viewportRef.current
    if (!vp) return
    let timer = 0
    const ro = new ResizeObserver(() => {
      if (dragRef.current) return
      window.clearTimeout(timer)
      timer = window.setTimeout(() => recomputeFit(), 150)
    })
    ro.observe(vp)
    return () => {
      ro.disconnect()
      window.clearTimeout(timer)
    }
  }, [recomputeFit])

  // פתיחה אוטומטית של מדריך ההדרכה בביקור הראשון במסך האולם — פעם אחת לכל
  // אירוע (ולא פעם אחת לדפדפן), כדי שכל זוג/אירוע חדש יראה אותו גם באותו מכשיר.
  useEffect(() => {
    try {
      const eid = getEventId()
      const key = eid != null ? `veya_hall_guide_v1_${eid}` : 'veya_hall_guide_v1'
      if (!localStorage.getItem(key)) {
        setGuideOpen(true)
        localStorage.setItem(key, '1')
      }
    } catch {
      /* localStorage לא זמין (מצב פרטי וכו') — פשוט לא פותחים אוטומטית */
    }
  }, [])

  // ברגע שהמשתמש גורר שולחן בפעם הראשונה — הוא כבר "בפנים". סוגרים את המדריך
  // אם פתוח, ומסמנים שראה אותו, כדי שלא ייפתח שוב אוטומטית. הכפתור "?" למעלה
  // תמיד זמין לפתיחה חוזרת ידנית.
  function markUserMovedTable() {
    setGuideOpen(false)
    try {
      const eid = getEventId()
      const key = eid != null ? `veya_hall_guide_v1_${eid}` : 'veya_hall_guide_v1'
      localStorage.setItem(key, '1')
    } catch {
      /* localStorage לא זמין — לא נורא, פשוט לא נזכור בין רענונים */
    }
  }

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
    // מתחילים אינטראקציה חדשה: מאפסים את דגל ה"נגרר" כאן (בתחילת הלחיצה) ולא
    // ב-pointerup — כדי שה-click שרץ *אחרי* הגרירה עדיין יראה שהיתה גרירה
    // ולא יפתח את חלון העריכה. (ראה onCanvasPointerUp — שם כבר לא מאפסים.)
    movedRef.current = false
    dragStartRef.current = { x: e.clientX, y: e.clientY }
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
    // הבחירה (והצגת תפריט העריכה/הידיות) מתבצעת ב-onElementClick, כלומר רק
    // בהקשה בלי גרירה. כך גרירה להזזת אלמנט לא "מקפיצה" את תפריט העריכה.
    movedRef.current = false // ראה הערה ב-onTablePointerDown — איפוס בתחילת הגרירה
    dragStartRef.current = { x: e.clientX, y: e.clientY }
    if (el.locked) return
    const w = toWorld(e.clientX, e.clientY)
    dragRef.current = { kind: 'element', id, dx: w.x - el.x, dy: w.y - el.y }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  // הקשה (בלי גרירה) על אלמנט → בחירה. הדפדפן לא מפעיל click אחרי גרירה, ולכן
  // גרירה להזזה לא בוחרת/פותחת תפריט. movedRef הוא הגנה נוספת.
  function onElementClick(e: React.MouseEvent, id: string) {
    e.stopPropagation()
    if (movedRef.current) return
    setSelectedEl(id)
    setSelectedTables(new Set())
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
    // מרכז הסיבוב נלקח מה-rect האמיתי של האלמנט על המסך (getBoundingClientRect),
    // ולא מחישוב לפי el.x/scroll — כך זה נכון גם במובייל שבו הלוח מוקטן (scale<1).
    const elNode = (e.currentTarget as HTMLElement).parentElement
    if (!elNode) return
    const r = elNode.getBoundingClientRect()
    dragRef.current = { kind: 'rotate', id, cx: r.left + r.width / 2, cy: r.top + r.height / 2 }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  function onCanvasPointerMove(e: React.PointerEvent) {
    const drag = dragRef.current
    if (!drag) return
    // סף-תזוזה: רק להזזת אלמנט/שולחן. עד שהאצבע לא זזה ~6px זו עדיין הקשה
    // (בחירה) ולא גרירה — כדי שרעד קטן לא יזיז ולא יבטל את הבחירה. ידיות
    // סיבוב/שינוי-גודל לא מוגבלות בסף (שם כל תזוזה קטנה חשובה).
    if (!movedRef.current && (drag.kind === 'element' || drag.kind === 'table-group')) {
      const st = dragStartRef.current
      if (st && Math.hypot(e.clientX - st.x, e.clientY - st.y) < 6) return
    }
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

  // חסימת ה-click ה"רפאים" שהדפדפן יורה מיד אחרי סיום גרירה. גם אם movedRef
  // התאפס או שה-click מכוון לאלמנט אחר — כאן אנחנו בולעים את ה-click הבא בשלב
  // ה-capture (לפני שהוא מגיע ל-onTableClick/onElementClick), וכך גרירה לעולם
  // לא פותחת את חלון העריכה. הגנת timeout מסירה את המאזין אם משום מה אין click.
  function suppressNextClick() {
    const handler = (ev: MouseEvent) => {
      ev.stopPropagation()
      ev.preventDefault()
      window.removeEventListener('click', handler, true)
      clearTimeout(timer)
    }
    const timer = setTimeout(() => {
      window.removeEventListener('click', handler, true)
    }, 400)
    window.addEventListener('click', handler, true)
  }

  function onCanvasPointerUp() {
    const drag = dragRef.current
    const wasDrag = movedRef.current // האם באמת הייתה תזוזה (גרירה) ולא הקשה?
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
        markUserMovedTable()
      }
      for (const node of dragNodesRef.current.values()) node.style.transform = ''
      dragNodesRef.current.clear()
      dragPendingRef.current = null
    }
    dragRef.current = null
    dragStartRef.current = null
    // אם הייתה גרירה אמיתית — בולעים את ה-click שיבוא מיד אחריה, כדי שלא
    // ייפתח חלון עריכה/פרטים. זו שכבת הגנה ראשית; movedRef ב-onTableClick הוא
    // שכבה שנייה (הוא מתאפס רק בתחילת האינטראקציה הבאה, לא כאן).
    if (wasDrag) suppressNextClick()
  }

  // ---- שולחנות: הוספה / שכפול / מחיקה / עדכון שדה ----
  // ---- אשף בניית אולם: יצירת סקיצה התחלתית מסודרת ----
  // מייצר שולחנות + אלמנטים (רחבה/DJ/בר) מסודרים: הרחבה במרכז, ה-DJ צמוד
  // מעליה, הבר בצד, והשולחנות בטבעות מאוזנות סביב הרחבה. זו רק *נקודת התחלה*
  // טובה — הזוג יכול לגרור/לסובב/למחוק הכול אחר כך. הגדלים קבועים לפי פרופיל
  // הצפיפות שנגזר מכמות השולחנות הכוללת (ונשמר נעול).
  function generateHall(opts: {
    regular: number
    knights: number
    dance: boolean
    dj: boolean
    bar: boolean
  }) {
    const total = Math.max(0, opts.regular) + Math.max(0, opts.knights)
    const key = densityKeyForCount(total || 1)
    const p = DENSITY_PRESETS[key]
    // פריסת רצועות מסודרת (ראה buildBandLayout): DJ + רחבה למעלה, אבירים,
    // בר במרכז, עגולים למטה — בצורה שמתאימה לאוריינטציה הנוכחית של האולם.
    const layout = buildBandLayout({
      regular: Math.max(0, opts.regular),
      knights: Math.max(0, opts.knights),
      dance: opts.dance,
      dj: opts.dj,
      bar: opts.bar,
      orientation: hallOrientation,
      p,
    })

    const newElements: HallElement[] = layout.elements.map((e, i) => {
      const def = ELEMENT_DEFS[e.type]
      return {
        id: `${e.type}-${Date.now()}-${i}`,
        type: e.type,
        x: e.x,
        y: e.y,
        width: e.w,
        height: e.h,
        rotation: 0,
        locked: false,
        label: def.label,
        shape: def.shape,
        color: '',
      }
    })

    // מספור: עגולים 1..N ואז אבירים (רוב השולחנות עגולים — נעים לזוג).
    const orderedTables = [
      ...layout.round.map((pl) => ({ pl, type: 'round' as TableType })),
      ...layout.knights.map((pl) => ({ pl, type: 'knights' as TableType })),
    ]
    const newTables: TableView[] = orderedTables.map((t, i) => ({
      table_number: i + 1,
      x: t.pl.x,
      y: t.pl.y,
      guests: [],
      table_type: t.type,
      capacity: defaultCapacityForType(t.type),
      rotation: 0,
      name: '',
      color: '',
      notes: '',
      locked: false,
      is_reserve: false,
    }))

    // בנייה מחדש כשכבר יש אורחים משובצים — מחזירים אותם ל"ללא שולחן".
    const seated = tables.flatMap((t) => t.guests)
    if (seated.length) setUnassigned((prev) => [...prev, ...seated])

    setElements(newElements)
    setTables(newTables)
    setHallLayout({ density: key, planned_tables: total })
    nextTableNumRef.current = newTables.length + 1
    setSelectedTables(new Set())
    setSelectedEl(null)
    setWizardOpen(false)
    setDirty(true)
    setMobileTab('hall')
    // אחרי שהלוח התרנדר (worldSize התעדכן) — מבצעים התאמה-למסך חד-פעמית כך
    // שכל האולם החדש ייכנס לתצוגה, ממורכז, בלי גלילה.
    window.setTimeout(() => recomputeFit(), 80)
  }

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
    const { w, h } = tableSize(type, preset)
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
      is_reserve: false,
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

  // כמות הרזרבה המפוזרת שנשמרת לאירוע (מוגבל 0..60, נשמר אוטומטית כמו כל שינוי).
  function setReserveAmount(n: number) {
    setReserveSeats(Math.max(0, Math.min(60, Math.round(n || 0))))
    setDirty(true)
  }

  function renumberTable(oldNum: number, raw: string) {
    const newNum = Math.max(1, Math.round(Number(raw)) || oldNum)
    if (newNum === oldNum) return
    setError('')
    // אם המספר החדש כבר תפוס ע"י שולחן אחר — מבצעים החלפה מלאה: שני השולחנות
    // מתחלפים גם במספר וגם במיקום על המפה. כך המוזמנים "נוסעים" יחד עם השולחן
    // שלהם: מי שישב בשולחן הישן יושב עכשיו בשולחן החדש (במקומו של החדש).
    const target = tables.find((t) => t.table_number === newNum)
    const source = tables.find((t) => t.table_number === oldNum)
    setTables((prev) =>
      prev.map((t) => {
        if (t.table_number === oldNum) {
          return target
            ? { ...t, table_number: newNum, x: target.x, y: target.y }
            : { ...t, table_number: newNum }
        }
        if (target && source && t.table_number === newNum) {
          return { ...t, table_number: oldNum, x: source.x, y: source.y }
        }
        return t
      }),
    )
    setSelectedTables(new Set([newNum]))
    // חשוב: אם חלון עריכת השולחן (הגיליון התחתון) פתוח על השולחן הזה — צריך
    // להצביע על המספר החדש, אחרת החלון "מאבד" את השולחן ונסגר בלי לשמור.
    setSheetTable((cur) => (cur === oldNum ? newNum : cur))
    nextTableNumRef.current = Math.max(nextTableNumRef.current, newNum + 1)
    setDirty(true)
  }

  // מסנכרן את שדה "מספר שולחן" (הטיוטה) עם השולחן שנמצא כעת בעריכה. רץ בכל פעם
  // שנפתח שולחן אחר או שהמספר משתנה בהצלחה — כך השדה תמיד מציג את המספר הנכון.
  useEffect(() => {
    if (sheetTable != null && sheetEdit) setNumDraft(String(sheetTable))
  }, [sheetTable, sheetEdit])

  // מאשר את מספר השולחן שהוקלד בשדה המבוקר. בודק רק תקינות בסיסית (מספר חיובי
  // ושונה מהקיים). אם המספר תפוס ע"י שולחן אחר — renumberTable יחליף ביניהם.
  function commitNumber() {
    if (sheetTable == null) return
    const oldNum = sheetTable
    const parsed = Math.round(Number(numDraft.trim()))
    if (!Number.isFinite(parsed) || parsed < 1 || parsed === oldNum) {
      setNumDraft(String(oldNum))
      return
    }
    renumberTable(oldNum, String(parsed))
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
    // גודל רחבה/בר/DJ נקבע לפי פרופיל הצפיפות (קבוע לכל האולם); שאר הסוגים
    // נשארים בגודל ברירת המחדל שלהם.
    const sized = elementSizeFor(type, preset)
    const width = sized?.w ?? def.width
    const height = sized?.h ?? def.height
    const rect = viewportRef.current?.getBoundingClientRect()
    const center = toWorld(
      (rect?.left ?? 0) + (rect?.width ?? 400) / 2,
      (rect?.top ?? 0) + (rect?.height ?? 300) / 2,
    )
    const off = nextPlaceOffset()
    const el: HallElement = {
      id: `${type}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      type,
      x: Math.max(0, Math.round(center.x - width / 2 + off)),
      y: Math.max(0, Math.round(center.y - height / 2 + off)),
      width,
      height,
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
        const { w, h } = tableSize('round', preset)
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
          is_reserve: false,
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
      // לא שומרים מיד — פותחים את עורך הסקיצה עם התמונה הגולמית.
      if (typeof reader.result === 'string') {
        sketchOriginalRef.current = reader.result
        setSketchEditSrc(reader.result)
      }
    }
    reader.readAsDataURL(file)
  }

  // פתיחת עורך הסקיצה לעריכה חוזרת: מעדיפים את המקור ששמור בזיכרון (איכותי);
  // אם אין (למשל אחרי רענון) — עורכים את הסקיצה השמורה עצמה.
  function editSketch() {
    setSketchEditSrc(sketchOriginalRef.current ?? sketch)
  }

  // יחס-הבסיס לרוחב (>1) עבור עורך הסקיצה. הכיוון (לרוחב/לאורך) נבחר בעורך
  // עצמו ומהפך את היחס בעת הצורך, לכן כאן מחזירים תמיד את ה"גודל הרחב":
  // גוזרים מיחס-הממדים של אזור העבודה, אך מבטיחים ערך גדול מ-1.
  function canvasAspect() {
    const vp = viewportRef.current
    if (vp && vp.clientWidth > 0 && vp.clientHeight > 0) {
      const r = vp.clientWidth / vp.clientHeight
      return clamp(r >= 1 ? r : 1 / r, 1.2, 2.4)
    }
    return 1.6
  }

  // סידור-מחדש של שולחנות + אלמנטים קיימים לפי כיוון חדש (לרוחב/לאורך), תוך
  // שמירה מלאה על השיבוצים, המספור והקיבולות — רק המיקומים משתנים. שולחנות
  // עגולים ואבירים מקבלים את המיקומים מפריסת-הרצועות החדשה לפי סדרם, ואלמנטים
  // (רחבה/DJ/בר) מקבלים את מיקומם החדש לפי הסוג. שולחנות מסוג אחר לא זזים.
  function rearrangeForOrientation(orientation: HallOrientation) {
    const roundCount = tables.filter((t) => t.table_type === 'round').length
    const knightCount = tables.filter((t) => t.table_type === 'knights').length
    if (roundCount === 0 && knightCount === 0) return
    const key = hallLayout?.density ?? densityKeyForCount(tables.length || 1)
    const p = DENSITY_PRESETS[key]
    const layout = buildBandLayout({
      regular: roundCount,
      knights: knightCount,
      dance: elements.some((e) => e.type === 'dance_floor'),
      dj: elements.some((e) => e.type === 'dj'),
      bar: elements.some((e) => e.type === 'bar'),
      orientation,
      p,
    })
    setTables((prev) => {
      let ri = 0
      let ki = 0
      return prev.map((t) => {
        if (t.table_type === 'round' && ri < layout.round.length) {
          const pl = layout.round[ri++]
          return { ...t, x: pl.x, y: pl.y }
        }
        if (t.table_type === 'knights' && ki < layout.knights.length) {
          const pl = layout.knights[ki++]
          return { ...t, x: pl.x, y: pl.y }
        }
        return t
      })
    })
    setElements((prev) =>
      prev.map((el) => {
        const np = layout.elements.find((le) => le.type === el.type)
        return np ? { ...el, x: np.x, y: np.y } : el
      }),
    )
    window.setTimeout(() => recomputeFit(), 80)
  }

  // אישור העריכה: התמונה ה"אפויה" נשמרת ומוצגת. אם הכיוון השתנה (לרוחב/לאורך)
  // מסדרים-מחדש מיד את השולחנות הקיימים כדי שיתאימו לכיוון — בלי לאבד שיבוצים.
  function onSketchConfirm(dataUrl: string, orientation: HallOrientation) {
    setSketch(dataUrl)
    setSketchEditSrc(null)
    setDirty(true)
    if (orientation !== hallOrientation) {
      setHallOrientation(orientation)
      rearrangeForOrientation(orientation)
    }
  }

  function removeSketch() {
    setSketch(null)
    sketchOriginalRef.current = null
    setDirty(true)
  }

  // ---- שמירה אוטומטית (בלי כפתור "שמירה") ----
  // כל שינוי מסומן ב-dirty; אחרי השהיה קצרה (debounce) נשמר לשרת ברקע. לא
  // מפריע בזמן גרירה (מדלגים אם יש drag פעיל — סיום הגרירה יזמן שמירה חדשה),
  // ולא "קופץ" (לא מחליפים מיקומי שולחנות מתשובת השרת — רק אזהרות ו"ללא שולחן").
  const savingRef = useRef(false)
  const editVersionRef = useRef(0)
  const [saveRetry, setSaveRetry] = useState(0)

  useEffect(() => {
    if (!dirty) return
    editVersionRef.current += 1
    const version = editVersionRef.current
    const timer = window.setTimeout(async () => {
      // באמצע גרירה או בזמן שמירה קודמת — לא שומרים כרגע; ננסה שוב בהמשך.
      if (dragRef.current || savingRef.current) return
      savingRef.current = true
      setSaving(true)
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
          is_reserve: t.is_reserve,
        }))
        // נועלים פרופיל צפיפות: אם כבר נבחר — שומרים אותו; אחרת (אולם ישן)
        // גוזרים מכמות השולחנות הנוכחית, כדי שהגדלים יישארו יציבים.
        const layoutToSave: HallLayout = hallLayout ?? {
          density: densityKeyForCount(tables.length),
          planned_tables: tables.length,
        }
        const res = await saveHall(payload, seats, elements, sketch ?? '', layoutToSave, reserveSeats)
        setWarnings(res.warnings)
        setUnassigned(res.unassigned)
        // מנקים dirty רק אם לא נעשה שינוי נוסף בזמן השמירה; אחרת שומרים שוב.
        if (editVersionRef.current === version) {
          setDirty(false)
          setSavedTick(true)
          window.setTimeout(() => setSavedTick(false), 1600)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'לא הצלחנו לשמור אוטומטית — נמשיך לנסות')
      } finally {
        savingRef.current = false
        setSaving(false)
        // אם התווספו שינויים בזמן השמירה (או שדילגנו על גרירה) — מפעילים סבב נוסף.
        if (editVersionRef.current !== version) setSaveRetry((r) => r + 1)
      }
    }, 900)
    return () => window.clearTimeout(timer)
    // saveRetry בכוונה בתלויות — מאלץ בדיקת-שמירה חוזרת אחרי סבב שהסתיים עם שינויים.
  }, [dirty, tables, elements, sketch, seats, hallLayout, reserveSeats, saveRetry])

  async function onRegenerate() {
    setLoading(true)
    setError('')
    try {
      const res = await generateSeating({
        seats_per_table: seats,
        persist: true,
        reserve_seats: reserveSeats,
      })
      if (!res.hard_ok) {
        setError('לא הצלחנו לסדר את כולם בלי להתנגש בהעדפות — כדאי להוסיף מקומות לשולחן.')
      }
      // הסברי "למה שובץ כאן" — מציגים למי שהמערכת זיהתה לו העדפה מההערות.
      setSeatExplain(res.explanations ?? [])
      applyState(await getHall())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לסדר כרגע, ננסה שוב')
    } finally {
      setLoading(false)
    }
  }

  // ---- מצב יום האירוע: סיכום רזרבה + שיבוץ מהיר עם המלצה ----
  const refreshReserve = useCallback(async () => {
    try {
      setReserveSummary(await getReserveSummary())
    } catch {
      /* שקט — לא חוסם את המפה */
    }
  }, [])

  // כשנכנסים למצב יום האירוע — טוענים סיכום עדכני. גם אחרי כל שיבוץ מרעננים.
  useEffect(() => {
    if (dayMode) refreshReserve()
  }, [dayMode, refreshReserve])

  async function openAssign(guestId: number) {
    if (assignGuestId === guestId) {
      // לחיצה שנייה על אותו מוזמן סוגרת את כרטיס ההמלצה.
      setAssignGuestId(null)
      setRecs(null)
      return
    }
    setAssignGuestId(guestId)
    setRecs(null)
    setAssignNote('')
    setRecLoading(true)
    try {
      const res = await recommendSeat(guestId, true)
      setRecs(res.recommendations)
    } catch (err) {
      setAssignNote(err instanceof Error ? err.message : 'לא הצלחנו להמליץ כרגע')
    } finally {
      setRecLoading(false)
    }
  }

  async function doAssign(guestId: number, tableNumber: number) {
    setAssignBusy(true)
    setAssignNote('')
    try {
      const res = await assignSeat(guestId, tableNumber)
      // רענון המפה מהשרת — האורח עובר משם ל"ללא שולחן" לשולחן, בזמן אמת.
      applyState(await getHall())
      await refreshReserve()
      setAssignGuestId(null)
      setRecs(null)
      if (res.warnings.length) setAssignNote(res.warnings.join(' · '))
    } catch (err) {
      setAssignNote(err instanceof Error ? err.message : 'לא הצלחנו לשבץ כרגע')
    } finally {
      setAssignBusy(false)
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
          <button
            className="hm-help-btn"
            onClick={() => setGuideOpen(true)}
            aria-label="איך זה עובד? פתיחת המדריך"
            title="איך זה עובד?"
          >
            ?
          </button>
          <button
            className="hm-fit-btn"
            onClick={() => recomputeFit()}
            aria-label="התאמת האולם למסך"
            title="התאם למסך"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M4 9V5a1 1 0 0 1 1-1h4" />
              <path d="M20 9V5a1 1 0 0 0-1-1h-4" />
              <path d="M4 15v4a1 1 0 0 0 1 1h4" />
              <path d="M20 15v4a1 1 0 0 1-1 1h-4" />
            </svg>
          </button>
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
                style={
                  {
                    width: worldSize.w,
                    height: worldSize.h,
                    transform: viewTransform,
                    transformOrigin: '0 0',
                    '--hm-s': viewScale,
                  } as React.CSSProperties
                }
              >
                {sketch && (
                  <div
                    className="hall-sketch-bg"
                    style={{ backgroundImage: `url(${mediaUrl(sketch)})`, width: worldSize.w, height: worldSize.h }}
                    aria-hidden="true"
                  />
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
                      onClick={(e) => onElementClick(e, el.id)}
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
                          {!el.locked &&
                            ELEMENT_SHAPES.map((s) => (
                              <button
                                key={s.key}
                                type="button"
                                className={el.shape === s.key ? 'active' : ''}
                                title={s.key}
                                onClick={(e) => {
                                  e.stopPropagation()
                                  // בצורה עגולה/ריבועית משווים רוחב=גובה כדי שתֵצא
                                  // עיגול/ריבוע אמיתי ולא אליפסה/מלבן מעוגל.
                                  if (s.key === 'circle' || s.key === 'square') {
                                    const side = Math.round((el.width + el.height) / 2)
                                    updateElement(el.id, { shape: s.key, width: side, height: side })
                                  } else {
                                    updateElement(el.id, { shape: s.key })
                                  }
                                }}
                              >
                                {s.label}
                              </button>
                            ))}
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
                    </div>
                  )
                })}

                {/* שולחנות — הקשה פותחת Bottom Sheet, לחיצה ארוכה/גרירה מזיזה */}
                {tables.map((t) => {
                  const used = t.guests.reduce((s, g) => s + g.seats, 0)
                  const over = used > t.capacity
                  const { w, h } = tableSize(t.table_type, preset)
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
                    <button onClick={() => addTable('square')}>
                      <HmIcon name="square" size={18} /> שולחן מרובע
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
              <div className={`hm-autosave ${saving || dirty ? 'saving' : ''}`}>
                <HmIcon name="save" size={16} />
                {saving ? 'שומר…' : dirty ? 'שינויים יישמרו אוטומטית' : savedTick ? 'נשמר ✓' : 'הכול שמור אוטומטית'}
              </div>
              <div className="hm-reserve-picker">
                <p className="hm-panel-head">מקומות רזרבה</p>
                <p className="hm-reserve-desc">
                  כמה מקומות פנויים להשאיר בשיבוץ האוטומטי (מפוזר אחיד בין השולחנות),
                  לאורחים של הרגע האחרון.
                </p>
                <div className="hm-reserve-chips">
                  {RESERVE_PRESETS.map((n) => (
                    <button
                      key={n}
                      className={reserveSeats === n ? 'active' : ''}
                      onClick={() => setReserveAmount(n)}
                    >
                      {n === 0 ? 'ללא' : n}
                    </button>
                  ))}
                  <input
                    type="number"
                    min={0}
                    max={60}
                    value={reserveSeats}
                    onChange={(e) => setReserveAmount(Number(e.target.value))}
                    aria-label="כמות רזרבה מותאמת"
                  />
                </div>
              </div>
              <button
                className="hm-ghost-btn hm-daymode-btn"
                onClick={() => setDayMode(true)}
              >
                <HmIcon name="check" size={18} /> מצב יום האירוע
              </button>
              <button className="hm-ghost-btn" onClick={onRegenerate} disabled={loading}>
                <HmIcon name="refresh" size={18} /> סידור מחדש מההתחלה
              </button>
              <button className="hm-ghost-btn" onClick={() => setWizardOpen(true)}>
                <HmIcon name="hall" size={18} /> בניית אולם מחדש
              </button>

              <div className="hm-tools-group">
                <p className="hm-panel-head">רקע האולם (סקיצה)</p>
                {sketch ? (
                  <>
                    <button className="hm-ghost-btn" onClick={editSketch}>
                      עריכת הסקיצה
                    </button>
                    <button className="hm-ghost-btn" onClick={() => sketchInputRef.current?.click()}>
                      החלפת תמונה
                    </button>
                    <button className="hm-ghost-btn" onClick={removeSketch}>
                      הסרת הסקיצה
                    </button>
                  </>
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
                    <div className="hm-num-row">
                      <input
                        type="number"
                        inputMode="numeric"
                        value={numDraft}
                        onChange={(e) => setNumDraft(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') e.currentTarget.blur()
                        }}
                        onBlur={commitNumber}
                      />
                      <button
                        type="button"
                        className="hm-num-ok"
                        onClick={commitNumber}
                        disabled={
                          numDraft.trim() === '' ||
                          Math.round(Number(numDraft)) === sheetT.table_number
                        }
                        aria-label="אישור מספר שולחן"
                      >
                        <HmIcon name="check" size={18} />
                      </button>
                    </div>
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

                  <div className="hm-edit-field">
                    <label className="hm-reserve-toggle">
                      <input
                        type="checkbox"
                        checked={sheetT.is_reserve}
                        onChange={(e) =>
                          updateTable(sheetT.table_number, { is_reserve: e.target.checked })
                        }
                      />
                      שולחן רזרבה
                    </label>
                    <p className="hm-reserve-hint">
                      לא ישובץ אוטומטית — שמור לאורחים של הרגע האחרון.
                    </p>
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

        {/* ---- סיכום "מה VEYA הבינה מההערות" אחרי סידור אוטומטי ---- */}
        {seatExplain.length > 0 && (
          <>
            <div className="hm-explain-backdrop" onClick={() => setSeatExplain([])} />
            <div className="hm-explain" role="dialog" aria-label="הסבר השיבוץ האוטומטי">
              <button
                className="hm-explain-close"
                onClick={() => setSeatExplain([])}
                aria-label="סגירה"
              >
                ×
              </button>
              <div className="hm-explain-head">
                <span className="hm-explain-spark">✨</span>
                <div>
                  <h3 className="hm-explain-title">סידרנו לפי ההערות שלכם</h3>
                  <p className="hm-explain-sub">
                    VEYA הביאה בחשבון בקשות מיקום ונגישות — הנה כמה דוגמאות:
                  </p>
                </div>
              </div>
              <ul className="hm-explain-list">
                {seatExplain.slice(0, 6).map((ex) => (
                  <li key={ex.guest_id} className="hm-explain-item">
                    <div className="hm-explain-row">
                      <b>{ex.full_name}</b>
                      <span className="hm-explain-table">שולחן {ex.table_number}</span>
                    </div>
                    <ul className="hm-explain-reasons">
                      {ex.reasons.map((r, i) => (
                        <li key={i}>{r}</li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
              {seatExplain.length > 6 && (
                <p className="hm-explain-more">
                  ועוד {seatExplain.length - 6} מוזמנים סודרו לפי ההעדפות שלהם
                </p>
              )}
            </div>
          </>
        )}

        {/* ---- מדריך פתיחה: איך עובד מסך האולם ---- */}
        {guideOpen && (
          <>
            <div className="hm-guide-backdrop" onClick={() => setGuideOpen(false)} />
            <div className="hm-guide" role="dialog" aria-label="מדריך מסך האולם">
              <button
                className="hm-guide-close"
                onClick={() => setGuideOpen(false)}
                aria-label="סגירה"
              >
                ×
              </button>
              <div className="hm-guide-scroll">
                <h2 className="hm-guide-title">ברוכים הבאים לסידור ההושבה ✨</h2>
                <p className="hm-guide-lead">
                  כאן תוכלו לסדר את השולחנות באולם בקלות ובנוחות.
                </p>

                {/* אנימציית הסבר: יד גוררת שולחן לצד, המפה מתכווצת כדי להשאיר הכל גלוי,
                    ואז חוזרת למרכז והמפה גדלה שוב. CSS טהור, בלולאה. */}
                <div className="hm-demo" aria-hidden="true">
                  <div className="hm-demo-frame">
                    <div className="hm-demo-world">
                      <span className="hm-demo-table t1" />
                      <span className="hm-demo-table t2" />
                      <span className="hm-demo-table t3" />
                      <span className="hm-demo-table t4" />
                      <span className="hm-demo-table mover" />
                      <span className="hm-demo-hand">👆</span>
                    </div>
                    <span className="hm-demo-badge">הכל נשאר גלוי ✓</span>
                  </div>
                </div>

                <div className="hm-guide-smart">
                  <h3>איך זה עובד?</h3>
                  <ul>
                    <li>אין צורך לגלול או לחפש את השולחנות — המפה מתאימה את עצמה לבד.</li>
                    <li>
                      מזיזים שולחן לכיוון הצדדים? המערכת תקטין בעדינות את המפה כדי שכל
                      האולם יישאר מולכם.
                    </li>
                    <li>
                      מחזירים שולחנות לכיוון המרכז? המפה תגדל שוב כדי שתוכלו לראות הכול
                      בצורה ברורה ונוחה.
                    </li>
                  </ul>
                  <p className="hm-guide-hint">
                    💡 <b>טיפ קטן:</b> פשוט גררו את השולחנות למקום הרצוי — המערכת כבר
                    תדאג לגודל המתאים בשבילכם.
                  </p>
                  <p className="hm-guide-reassure">
                    אין צורך בזום, אין גלילות — רק לסדר את האולם כמו שאתם רוצים 😊
                  </p>
                </div>

                <div className="hm-guide-divider">
                  <span>עוד דברים שכדאי לדעת</span>
                </div>

                <div className="hm-guide-step">
                  <span className="hm-guide-emoji">➕</span>
                  <div>
                    <h3>מוסיפים שולחנות ואלמנטים</h3>
                    <p>
                      לוחצים על כפתור ה־➕ בפינה, ובוחרים מה להוסיף: שולחן עגול, שולחן אבירים,
                      בר, רחבת ריקודים או עמדת דיג׳יי.
                    </p>
                  </div>
                </div>

                <div className="hm-guide-step">
                  <span className="hm-guide-emoji">✋</span>
                  <div>
                    <h3>מזיזים, מסובבים ומשנים גודל</h3>
                    <p>
                      גוררים כל שולחן או אלמנט למקום שלו. הקשה קצרה בוחרת אותו — ואז מופיעות
                      שתי ידיות: העליונה לסיבוב, והפינתית לשינוי גודל.
                    </p>
                  </div>
                </div>

                <div className="hm-guide-step">
                  <span className="hm-guide-emoji">🪑</span>
                  <div>
                    <h3>הושבה בקליק</h3>
                    <p>
                      בלשונית "מוזמנים" בוחרים אורח, ואז מקישים על השולחן שאליו הוא ישב. זהו —
                      הוא משובץ. כך אפשר להעביר כל אורח בכמה שניות.
                    </p>
                  </div>
                </div>

                <div className="hm-guide-step">
                  <span className="hm-guide-emoji">✨</span>
                  <div>
                    <h3>מילוי אוטומטי חכם</h3>
                    <p>
                      אין כוח לשבץ ידנית? בלשונית "הושבה" יש "מילוי שולחנות אוטומטי" שמסדר את
                      כולם בשבילכם — לפי הקבוצות והבקשות. תמיד אפשר לגרור ולתקן אחר כך.
                    </p>
                  </div>
                </div>

                <div className="hm-guide-step">
                  <span className="hm-guide-emoji">🖼️</span>
                  <div>
                    <h3>סקיצת האולם כרקע</h3>
                    <p>
                      יש לכם תמונה או סקיצה של האולם? בלשונית "כלים" אפשר להעלות אותה כרקע,
                      ולסדר את השולחנות בדיוק לפי המבנה האמיתי.
                    </p>
                  </div>
                </div>

                <div className="hm-guide-tabs">
                  <h3>חמש הלשוניות למטה</h3>
                  <ul>
                    <li>
                      <b>אולם</b> — המפה עצמה, כאן בונים ומסדרים.
                    </li>
                    <li>
                      <b>שולחנות</b> — רשימת כל השולחנות ומי יושב בכל אחד.
                    </li>
                    <li>
                      <b>מוזמנים</b> — מי עוד מחכה למקום.
                    </li>
                    <li>
                      <b>הושבה</b> — מילוי אוטומטי, סטטיסטיקה והצעות לשיפור.
                    </li>
                    <li>
                      <b>כלים</b> — שמירה, העלאת סקיצה והגדרות.
                    </li>
                  </ul>
                </div>

                <p className="hm-guide-tip">
                  אפשר לפתוח את המדריך הזה שוב בכל רגע — מכפתור ה־"?" למעלה.
                </p>
              </div>
              <button className="hm-guide-cta" onClick={() => setGuideOpen(false)}>
                יאללה, מתחילים
              </button>
            </div>
          </>
        )}

        {wizardOpen && (
          <HallWizard
            regular={wzRegular}
            knights={wzKnights}
            dance={wzDance}
            dj={wzDj}
            bar={wzBar}
            hasContent={tables.length > 0 || elements.length > 0}
            onRegular={setWzRegular}
            onKnights={setWzKnights}
            onDance={setWzDance}
            onDj={setWzDj}
            onBar={setWzBar}
            onBuild={() =>
              generateHall({ regular: wzRegular, knights: wzKnights, dance: wzDance, dj: wzDj, bar: wzBar })
            }
            onClose={() => setWizardOpen(false)}
          />
        )}

        {sketchEditSrc && (
          <SketchEditor
            src={sketchEditSrc}
            baseAspect={canvasAspect()}
            orientation={hallOrientation}
            onCancel={() => setSketchEditSrc(null)}
            onConfirm={onSketchConfirm}
          />
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
        <span className={`hall-autosave ${saving || dirty ? 'saving' : ''}`}>
          {saving ? '💾 שומר…' : dirty ? '💾 יישמר אוטומטית' : savedTick ? '✓ נשמר' : '✓ שמור אוטומטית'}
        </span>
        <input ref={sketchInputRef} type="file" accept="image/*" hidden onChange={onPickSketch} />
        {sketch && (
          <button className="btn-ghost" onClick={editSketch}>
            ✂️ עריכת סקיצה
          </button>
        )}
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
              style={{ width: worldSize.w, height: worldSize.h }}
              onPointerDown={onWorldPointerDown}
            >
              {sketch && (
                <div
                  className="hall-sketch-bg"
                  style={{ backgroundImage: `url(${mediaUrl(sketch)})`, width: worldSize.w, height: worldSize.h }}
                  aria-hidden="true"
                />
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
                const { w, h } = tableSize(t.table_type, preset)
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
                    } ${t.is_reserve ? 'reserve' : ''} ${
                      dragOver === t.table_number ? 'drag-over' : ''
                    } ${fillClass}`}
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
                        {t.is_reserve && <span className="table-reserve-tag">רזרבה</span>}
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

              <label className="props-field reserve-toggle">
                <span className="reserve-toggle-head">
                  <input
                    type="checkbox"
                    checked={soleSelected.is_reserve}
                    onChange={(e) =>
                      updateTable(soleSelected.table_number, { is_reserve: e.target.checked })
                    }
                  />
                  שולחן רזרבה
                </span>
                <span className="reserve-toggle-hint">
                  לא ישובץ אוטומטית — שמור לאורחים של הרגע האחרון ביום האירוע.
                </span>
              </label>

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
      {sketchEditSrc && (
        <SketchEditor
          src={sketchEditSrc}
          baseAspect={canvasAspect()}
          orientation={hallOrientation}
          onCancel={() => setSketchEditSrc(null)}
          onConfirm={onSketchConfirm}
        />
      )}

      {dayMode && (
        <div className="day-mode" role="dialog" aria-label="מצב יום האירוע">
          <div className="day-mode-head">
            <div>
              <h3>מצב יום האירוע</h3>
              <p>שיבוץ אורחים של הרגע האחרון — בקליק, עם המלצה חכמה.</p>
            </div>
            <button
              className="day-mode-close"
              onClick={() => {
                setDayMode(false)
                setAssignGuestId(null)
                setRecs(null)
              }}
              aria-label="סגירה"
            >
              ✕
            </button>
          </div>

          {reserveSummary && (
            <div className="day-mode-stats">
              <div className="dm-stat">
                <span className="dm-num">{reserveSummary.free_seats_active}</span>
                <span className="dm-label">מקומות פנויים</span>
              </div>
              <div className="dm-stat">
                <span className="dm-num">{reserveSummary.reserve_tables}</span>
                <span className="dm-label">שולחנות רזרבה</span>
              </div>
              <div className="dm-stat">
                <span className="dm-num">{reserveSummary.seated_people}</span>
                <span className="dm-label">משובצים</span>
              </div>
              <div className="dm-stat">
                <span className="dm-num">{reserveSummary.unseated_guests}</span>
                <span className="dm-label">ללא שולחן</span>
              </div>
            </div>
          )}

          {assignNote && <p className="day-mode-note">{assignNote}</p>}

          <div className="day-mode-list">
            {unassigned.length === 0 ? (
              <p className="day-mode-empty">כל המוזמנים משובצים 🎉</p>
            ) : (
              [...unassigned]
                .sort((a, b) => a.full_name.localeCompare(b.full_name, 'he'))
                .map((g) => (
                  <div
                    key={g.id}
                    className={`dm-guest ${assignGuestId === g.id ? 'open' : ''}`}
                  >
                    <button className="dm-guest-head" onClick={() => openAssign(g.id)}>
                      <span className="dm-guest-name">
                        {g.full_name}
                        {g.seats > 1 && <span className="chip-size">×{g.seats}</span>}
                      </span>
                      <span className="dm-guest-cta">
                        {assignGuestId === g.id ? 'סגירה' : 'שבץ אורח'}
                      </span>
                    </button>

                    {assignGuestId === g.id && (
                      <div className="dm-recs">
                        {recLoading && <p className="dm-recs-loading">מחשב המלצה…</p>}
                        {!recLoading && recs && recs.length === 0 && (
                          <p className="dm-recs-empty">
                            אין שולחן פנוי מתאים — פנו מקום או הוסיפו שולחן רזרבה.
                          </p>
                        )}
                        {!recLoading &&
                          recs &&
                          recs.map((r, i) => (
                            <button
                              key={r.table_number}
                              className={`dm-rec ${i === 0 ? 'best' : ''}`}
                              disabled={assignBusy}
                              onClick={() => doAssign(g.id, r.table_number)}
                            >
                              <span className="dm-rec-top">
                                <span className="dm-rec-table">
                                  שולחן {r.table_number}
                                  {r.table_name && ` · ${r.table_name}`}
                                  {r.is_reserve && (
                                    <span className="dm-rec-reserve">רזרבה</span>
                                  )}
                                </span>
                                <span className="dm-rec-free">{r.free_seats} פנויים</span>
                              </span>
                              {r.reasons.length > 0 && (
                                <span className="dm-rec-reasons">
                                  {r.reasons.join(' · ')}
                                </span>
                              )}
                              {i === 0 && <span className="dm-rec-badge">מומלץ</span>}
                            </button>
                          ))}
                      </div>
                    )}
                  </div>
                ))
            )}
          </div>
        </div>
      )}
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

