import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  analyzeConstraints,
  analyzeHallSketch,
  assignSeat,
  generateSeating,
  getSeatingUndoState,
  undoSeating,
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
  DetectedHallElement,
  ElementShape,
  HallElement,
  HallElementType,
  HallGuest,
  HallLayout,
  HallSketchTransform,
  HallState,
  ReserveSummary,
  SeatRecommendation,
  SeatingExplanation,
  SeatingViolation,
  TableType,
} from '../types'
import { GROUP_LABELS, RSVP_LABELS } from '../types'
import { activeEventTerms, sideLabel } from '../strings/eventTypes'
import { strings } from '../strings/he'
import { getEventId } from '../authStore'
import { ConfirmDialog } from './ConfirmDialog'

// טקסטי מסך ההושבה — כולם ב-strings/he.ts, אף פעם לא קשיחים בקומפוננטה.
const hallT = strings.hall
import {
  computeSmartWarnings,
  computeStats,
  computeSuggestions,
  computeTableInsight,
  detectChildrenWithoutFamily,
  detectFamilyGroups,
  detectSplitGroups,
  smartSearch,
  type PairList,
  type SmartMove,
  type SmartSuggestion,
} from '../seatingAdvisor'
import {
  assignTableNumbers,
  orientedAspect,
  placeSketchItems,
  rectOverlapFraction,
  sketchWorldCanvas,
  spatialOrder,
  type AxisRect,
  type SketchItemInput,
} from '../hallSketchGeometry'

interface TableView {
  table_number: number
  x: number
  y: number
  guests: HallGuest[]
  table_type: TableType
  capacity: number
  rotation: number
  width?: number
  height?: number
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

// הגדרות ברירת-מחדל לכל סוג אלמנט מיוחד (תווית, גודל, צורה, צבע).
// הגדלים כאן קטנים יחסית לגודל המפה (WORLD_W/H) — כדי שגם ברמת זום 100%
// האלמנטים ייראו פרופורציונליים לחלל האולם, לא ענקיים.
// חלק מהסוגים (head_table/gift_table/restroom/stage) לא מוצעים כרגע בתפריט
// ההוספה — הקוד שלהם נשאר שלם כדי שאפשר יהיה להחזיר אותם בעתיד.
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
  // מגיעים רק מבניית אולם אוטומטית (AI Vision) — לא מוצעים ידנית בסרגל הכלים.
  pillar: { label: '🔘 עמוד', width: 40, height: 40, shape: 'circle', color: '#6b6355' },
  wall: { label: '▬ קיר', width: 160, height: 16, shape: 'rectangle', color: '#3f4756' },
  obstacle: { label: '⚠️ מכשול', width: 60, height: 60, shape: 'square', color: '#8c8375' },
  other_area: { label: '⬛ אזור', width: 140, height: 100, shape: 'rectangle', color: '#8a6bc9' },
}

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

// ---- שלב D: זום/פאן ידניים בנגיעה (Pinch/Pan) ----
// טווח זום ידני רחב יותר מ-FIT_MIN/MAX_SCALE: המשתמש מבקש בפירוש להתקרב/
// להתרחק, בניגוד ל-Auto-Fit שרק בוחר קנה-מידה "יפה" כברירת מחדל.
const MANUAL_ZOOM_MIN = FIT_MIN_SCALE
const MANUAL_ZOOM_MAX = 4
// כמה פיקסלים מתיבת-התוכן חייבים תמיד להישאר בתוך אזור-התצוגה בזמן פאן —
// כדי שאי אפשר "לאבד" את המפה לגמרי מחוץ למסך.
const PAN_CLAMP_MIN_VISIBLE = 80

function touchDist(t: React.TouchList): number {
  return Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY)
}
function touchMid(t: React.TouchList): { x: number; y: number } {
  return { x: (t[0].clientX + t[1].clientX) / 2, y: (t[0].clientY + t[1].clientY) / 2 }
}
function touchAngle(t: React.TouchList): number {
  return (Math.atan2(t[1].clientY - t[0].clientY, t[1].clientX - t[0].clientX) * 180) / Math.PI
}

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

// זווית מנורמלת ל-0..359 ומוצמדת לצעדים של 5°. atan2 מחזיר טווח שלילי
// חלקית, ובלי נרמול נשמרות זוויות כמו 90-; ההצמדה מונעת "רעד" של מעלה
// אחת בגרירה ומקלה על יישור מדויק לקיר האולם.
const ROTATION_SNAP_DEG = 5

export function normalizeRotation(deg: number): number {
  const snapped = Math.round(deg / ROTATION_SNAP_DEG) * ROTATION_SNAP_DEG
  return ((snapped % 360) + 360) % 360
}

/** תיבת הגבולות (bbox) של מלבן אחרי סיבוב סביב מרכזו.
 *
 * `transform: rotate()` ב-CSS הוא אפקט ציור בלבד — הוא לא משנה את הפריסה,
 * ולכן חישוב גבולות לפי `x + width` מפספס לגמרי אובייקט מסובב. שולחן
 * אבירים (252×58) שמסובב 90° בולט ~97px מעל ומתחת למה שהחישוב הנאיבי
 * מניח, ולכן הוא נחתך ב"התאמה למסך" — ובמסך הזה אין גלילה או זום, אז
 * למשתמש אין שום דרך להגיע אליו. משמש גם לשולחנות וגם לאלמנטים.
 */
export function rotatedBounds(
  x: number,
  y: number,
  w: number,
  h: number,
  deg: number,
): { minX: number; minY: number; maxX: number; maxY: number } {
  const rad = ((deg || 0) * Math.PI) / 180
  const cos = Math.abs(Math.cos(rad))
  const sin = Math.abs(Math.sin(rad))
  const bw = w * cos + h * sin
  const bh = w * sin + h * cos
  const cx = x + w / 2
  const cy = y + h / 2
  return {
    minX: cx - bw / 2,
    minY: cy - bh / 2,
    maxX: cx + bw / 2,
    maxY: cy + bh / 2,
  }
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

// גודל שולחן בפועל (לתצוגה/למדידת bbox): אם לשולחן יש width/height עצמאיים
// (יובא מסקיצת AI — ראה applySketchReview) הם קובעים; אחרת נופלים חזרה
// ל-tableSize הרגיל (שולחן שנוסף ידנית, ממשיך להשתנות עם פרופיל-הצפיפות).
function tableRenderSize(t: { table_type: TableType; width?: number; height?: number }, preset: DensityPreset): { w: number; h: number } {
  if (t.width && t.height) return { w: t.width, h: t.height }
  return tableSize(t.table_type, preset)
}

// קנה-מידה לקישוטי השולחן (כיסאות, מספר, "0/24", טבעת העיגול) יחסית לגודל
// הרגיל של הסוג הזה. שולחן שנוסף ידנית מקבל תמיד 1 — כלומר רינדור זהה
// לחלוטין להיום. שולחן שיובא מסקיצה וקטן מהרגיל מקבל פחות מ-1, כדי שכיסא
// בגודל קבוע (11×15px) לא ייצא גדול מהשולחן עצמו. לא מגדילים מעל 1.
function tableUiScale(w: number, h: number, base: { w: number; h: number }): number {
  const ref = Math.min(base.w, base.h)
  const cur = Math.min(w, h)
  return ref > 0 ? clamp(cur / ref, 0.35, 1) : 1
}

// גודל אלמנט מיוחד (רחבה/בר/DJ) לפי פרופיל הצפיפות. שאר הסוגים → null (גודל
// ברירת המחדל מ-ELEMENT_DEFS).
function elementSizeFor(type: HallElementType, preset: DensityPreset): { w: number; h: number } | null {
  if (type === 'dance_floor') return preset.dance
  if (type === 'bar') return preset.bar
  if (type === 'dj') return preset.dj
  // "כניסה" נגזרת מרוחב עמדת ה-DJ ובגובה נמוך יותר — פתח, לא רהיט. בלי
  // המקרה הזה היא נוספה תמיד בגודל קבוע ולא הצטמצמה יחד עם שאר האולם.
  if (type === 'entrance') return { w: preset.dj.w, h: Math.round(preset.dj.h * 0.8) }
  return null
}

// ---- בניית אולם מסקיצה (AI Vision): קנבס הסקיצה ----
// המתמטיקה הטהורה (יחס-ממדים, מיפוי, סדר מרחבי, חפיפות) יושבת ב-
// hallSketchGeometry.ts כדי שאפשר לבדוק אותה אוטומטית; הקבועים כאן הם
// מדיניות VEYA-ספציפית.
//
// חשוב: הצלע הארוכה היא **בחירת זום גלובלית בלבד** — כל ערך נותן בדיוק אותה
// נאמנות לסקיצה (מכפיל אחיד על שני הצירים). היא קבועה בכוונה ולא נגזרת ממספר
// השולחנות / מגודל חציוני / מפרופיל צפיפות, כדי שאותה סקיצה תמיד תיתן אותה
// תוצאה. 1900 נבחר כך ששולחן טיפוסי (6 בשורה) יוצא סביב הגודל המוכר של VEYA.
const SKETCH_WORLD_LONG_EDGE = 1900
// ריפוד אחיד (הזזה בלבד, לא שינוי גודל) כדי שהאולם לא ייצמד לפינה 0,0.
const SKETCH_WORLD_PAD = 60
// רצפת גודל לזיהוי מנוון בלבד — מוחלת אחיד על שני הצירים (יחס-הממדים נשמר).
const SKETCH_MIN_ITEM_PX = 10
// פער אנכי בין מרכזי שולחנות שעדיין נחשב "אותה שורה" למספור מרחבי.
const SKETCH_ROW_TOLERANCE = 40
// בנייה מסקיצה כשכבר יש אולם על הלוח: להחליף אותו, או להוסיף לצדו.
type SketchBuildMode = 'replace' | 'add'
// חפיפה (יחסית לשטח הקטן מבין השניים) שנחשבת "משמעותית" לצורך תגית אזהרה
// במסך ה-Review — לא מזיזים כלום אוטומטית, רק מסמנים לבדיקה.
const SKETCH_OVERLAP_WARN_THRESHOLD = 0.35

// ---- שלב C: שכבת הסקיצה כאובייקט עצמאי (הזזה/שינוי-גודל/סיבוב/שקיפות/נעילה/הצגה) ----
// גודל מינימלי (world units) לשינוי-גודל בגרירה — כדי שאי אפשר לכווץ את
// הסקיצה לנקודה בטעות ולאבד אותה.
const SKETCH_MIN_SIZE = 80

// ברירת המחדל כשמריחים/גוררים סקיצה שעדיין אין לה sketchTransform משלה
// (אירוע ישן, או סקיצה שהועלתה ידנית בלי בניית אולם מ-AI) — בדיוק ההתנהגות
// החזותית הקיימת עד כה (רקע מלא בגודל worldSize, שקיפות 0.42 מה-CSS), רק
// "אפויה" ל-state אמיתי כדי שאפשר יהיה לגרור/לסובב/לשנות גודל אותה בפועל.
function defaultSketchTransform(worldSize: { w: number; h: number }): HallSketchTransform {
  return { x: 0, y: 0, width: worldSize.w, height: worldSize.h, rotation: 0, opacity: 0.42, locked: false, hidden: false }
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
// gap מוקטן יחד עם השולחן (ראה tableUiScale) — אחרת בשולחן קטן שיובא מסקיצה
// הכיסאות "מתעופפים" רחוק מגוף השולחן.
function seatPositions(type: TableType, capacity: number, w: number, h: number, gap = 12): SeatPoint[] {
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
  | 'sketch'

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
    // תמונה/סקיצה — החליף את האימוג'י 🖼️ שהופיע בשלושה מקומות בעורך.
    case 'sketch':
      return (
        <svg {...common}>
          <rect x="3.5" y="5" width="17" height="14" rx="2" />
          <path d="M3.8 15.6 8.2 11.4l3.3 3.1 3.4-3.6 5.1 5" />
          <path d="M15.6 9v.2" />
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
            ⚠ בנייה מחדש תחליף את הסידור הנוכחי — {activeEventTerms().guestsLabel} המשובצים יחזרו ל"ללא שולחן".
          </p>
        )}

        <div className="hm-wizard-actions">
          <button className="hm-wizard-build" onClick={props.onBuild} disabled={total === 0}>
            בניית האולם
          </button>
          <button className="hm-wizard-cancel" onClick={props.onClose}>
            {props.hasContent ? 'ביטול' : 'התחלה ממסך ריק'}
          </button>
        </div>
      </div>
    </>
  )
}

/** מסך הבחירה שנפתח לפני בניית אולם — בחירה ברורה בין שתי דרכים:
 *  בנייה ידנית מאפס (HallWizard, בלי שינוי), או בנייה מסקיצה קיימת (Sketch
 *  Upload Flow — AI Vision + Review + Build, בלי שינוי). נפתח אוטומטית
 *  כשהאולם ריק, וגם מכפתור "בניית אולם מחדש". שתי הבחירות רק פותחות את
 *  המנגנון הקיים המתאים — אין כאן שום לוגיקת בנייה חדשה, ואם כבר יש אולם
 *  על הלוח, דיאלוג ההחלפה/הוספה/ביטול הקיים ב-Sketch Upload Flow ממשיך
 *  לפעול בדיוק כמו קודם, ללא תלות באיך המשתמש הגיע לכאן. */
function HallStartChoice(props: { hasContent: boolean; onBuildNew: () => void; onBuildFromSketch: () => void; onClose: () => void }) {
  return (
    <>
      <div className="hm-wizard-backdrop" onClick={props.onClose} />
      <div className="hm-start-choice" role="dialog" aria-label="בניית אולם">
        <h2 className="hm-wizard-title">איך בונים את האולם?</h2>
        <p className="hm-wizard-lead">בחרו את הדרך הנוחה לכם — אפשר תמיד לערוך הכול אחר כך.</p>

        <div className="hm-start-options">
          <button type="button" className="hm-start-card" onClick={props.onBuildNew}>
            <span className="hm-start-card-ic" aria-hidden="true">
              <HmIcon name="hall" size={26} />
            </span>
            <span className="hm-start-card-title">בניית אולם חדש</span>
            <span className="hm-start-card-sub">בנו את האולם שלכם מאפס והוסיפו שולחנות, רחבה ואובייקטים לפי הצורך.</span>
          </button>
          <button type="button" className="hm-start-card" onClick={props.onBuildFromSketch}>
            <span className="hm-start-card-ic" aria-hidden="true">
              <HmIcon name="sketch" size={26} />
            </span>
            <span className="hm-start-card-title">בניית אולם מסקיצה</span>
            <span className="hm-start-card-sub">
              יש לכם סקיצה מהאולם? העלו אותה ו-VEYA תזהה את השולחנות, המספרים והפריסה ותבנה עבורכם את האולם.
            </span>
          </button>
        </div>

        <div className="hm-wizard-actions">
          <button className="hm-wizard-cancel hm-start-choice-cancel" onClick={props.onClose}>
            {props.hasContent ? 'ביטול' : 'התחלה ממסך ריק'}
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
  orientation: HallOrientation
  onCancel: () => void
  onConfirm: (dataUrl: string, orientation: HallOrientation) => void
}) {
  const { src } = props
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

  // יחס מסגרת החיתוך: תמיד יחס-הממדים האמיתי של הסקיצה עצמה (לא של המסך/
  // החלון!) בהתחשב בסיבוב הנוכחי — כך שברירת המחדל מציגה את כל הסקיצה בלי
  // חיתוך (coverScale למטה הופך ל-contain מדויק כשהמסגרת תואמת לתמונה).
  // "לרוחב/לאורך" (orient) לא משפיע כאן יותר — הוא רק קובע hallOrientation
  // להמשך (פריסת שולחנות ידניים), לא את צורת מסגרת החיתוך.
  const aspect = imgRef.current
    ? orientedAspect(imgRef.current.naturalWidth || 4, imgRef.current.naturalHeight || 3, rotation)
    : 1.6

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

const hallSketchT = strings.hall.sketchReview

// שלב 1 של הזרימה (שלב E): פאנל העלאה עם כותרת/הסבר ברורים, Drag & Drop
// בדסקטופ, ותצוגת preview+שם+גודל-קובץ+אפשרות-החלפה לפני שממשיכים לעורך
// החיתוך הקיים (SketchEditor, ללא שינוי). לא נוגע בניתוח/במיפוי בשום צורה.
function SketchUploadDialog(props: {
  picked: { name: string; size: number; dataUrl: string } | null
  onPick: (file: File) => void
  onBrowse: () => void
  onConfirm: () => void
  onCancel: () => void
}) {
  const [dragOver, setDragOver] = useState(false)
  return (
    <>
      <div className="sk-editor-backdrop" onClick={props.onCancel} />
      <div className="sk-upload" role="dialog" aria-label={hallSketchT.uploadTitle}>
        <div className="sk-editor-head">
          <h2>{hallSketchT.uploadTitle}</h2>
          <p>{hallSketchT.uploadLead}</p>
        </div>

        {!props.picked ? (
          <div
            className={`sk-upload-drop ${dragOver ? 'drag-over' : ''}`}
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragOver(false)
              const file = e.dataTransfer.files?.[0]
              if (file) props.onPick(file)
            }}
            onClick={props.onBrowse}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') props.onBrowse()
            }}
          >
            <span className="sk-upload-drop-icon" aria-hidden="true">
              <HmIcon name="sketch" size={30} />
            </span>
            <p className="sk-upload-drop-hint">{hallSketchT.uploadDropHint}</p>
            <button type="button" className="hm-ghost-btn" onClick={(e) => { e.stopPropagation(); props.onBrowse() }}>
              {hallSketchT.uploadBrowse}
            </button>
          </div>
        ) : (
          <div className="sk-upload-preview">
            <img src={props.picked.dataUrl} alt="" className="sk-upload-preview-img" />
            <div className="sk-upload-file-meta">
              <span className="sk-upload-file-name">{props.picked.name}</span>
              <span className="sk-upload-file-size">{hallSketchT.fileSize(props.picked.size)}</span>
            </div>
            <button type="button" className="hm-ghost-btn" onClick={props.onBrowse}>
              {hallSketchT.uploadReplace}
            </button>
          </div>
        )}

        <div className="sk-editor-actions">
          <button className="sk-confirm" onClick={props.onConfirm} disabled={!props.picked}>
            {hallSketchT.uploadNext}
          </button>
          <button className="sk-cancel" onClick={props.onCancel}>
            {hallSketchT.uploadCancel}
          </button>
        </div>
      </div>
    </>
  )
}

// מסך "טוענים" בזמן ניתוח ה-AI לסקיצה — מוצג אוטומטית אחרי אישור עריכת הסקיצה.
// שלוש שורות (שלב E, דרישה 2) — לא ספינר גנרי בלי הקשר: מה קורה, מה בודקים,
// וכמה זמן לצפות. לא מציגים שום דבר טכני כאן (אין סטטוס/שגיאה אפשרית).
function SketchAnalyzingOverlay() {
  return (
    <div className="sk-editor-backdrop">
      <div className="sk-analyzing" role="status" aria-live="polite">
        <div className="sk-analyzing-spinner" aria-hidden="true" />
        <h2>{hallSketchT.analyzingTitle}</h2>
        <p>{hallSketchT.analyzingStep}</p>
        <p className="sk-analyzing-sub">{hallSketchT.analyzingHint}</p>
      </div>
    </div>
  )
}

const DETECTED_TYPE_LABELS: Record<DetectedHallElement['type'], string> = {
  round_table: TABLE_TYPE_LABELS.round,
  square_table: TABLE_TYPE_LABELS.square,
  rectangle_table: TABLE_TYPE_LABELS.rectangle,
  knights_table: TABLE_TYPE_LABELS.knights,
  bar: ELEMENT_DEFS.bar.label,
  dance_floor: ELEMENT_DEFS.dance_floor.label,
  stage: ELEMENT_DEFS.stage.label,
  entrance: ELEMENT_DEFS.entrance.label,
  pillar: ELEMENT_DEFS.pillar.label,
  wall: ELEMENT_DEFS.wall.label,
  obstacle: ELEMENT_DEFS.obstacle.label,
  other_area: ELEMENT_DEFS.other_area.label,
}

const DETECTED_TYPE_OPTIONS = Object.keys(DETECTED_TYPE_LABELS) as DetectedHallElement['type'][]

// שלוש רמות ודאות (שלב E, דרישה 4) — 🟢 בטוח, 🟡 כדאי לבדוק, 🔴 לא בטוח.
const LOW_CONFIDENCE_THRESHOLD = 0.85
const VERY_LOW_CONFIDENCE_THRESHOLD = 0.5

type ConfidenceTier = 'high' | 'mid' | 'low'
function confidenceTier(confidence: number): ConfidenceTier {
  if (confidence < VERY_LOW_CONFIDENCE_THRESHOLD) return 'low'
  if (confidence < LOW_CONFIDENCE_THRESHOLD) return 'mid'
  return 'high'
}
const CONFIDENCE_EMOJI: Record<ConfidenceTier, string> = { high: '🟢', mid: '🟡', low: '🔴' }

// ממיר item (מרכז+גודל, מנורמל) למלבן פינה-שמאלית-עליונה — הפורמט ש-
// rectOverlapFraction מצפה לו. עובד ישירות על קואורדינטות מנורמלות [0,1]
// (בלי לדעת עדיין את קנבס-הבנייה) כי הפונקציה scale-invariant.
function itemAsAxisRect(it: DetectedHallElement): AxisRect {
  return { x: it.x - it.width / 2, y: it.y - it.height / 2, w: it.width, h: it.height }
}

// מסך "בדיקה ואישור" — מוצג אחרי שה-AI סיים לנתח את הסקיצה. ברירת המחדל היא
// שהמפה כבר בנויה (שלב 16, Zero Manual Setup); המשתמש רק מתקן/מוחק/מוסיף.
// שלב E: שני חלקים — תצוגה מקדימה של הסקיצה עם Bounding Boxes תמיד גלויים
// (לא מאחורי toggle "דיבאג" כמו קודם) + רשימה עריכה, זה לצד זה בדסקטופ
// ומוערמים במובייל (ראה CSS: .sk-review-body).
function SketchReviewPanel(props: {
  items: DetectedHallElement[]
  sketchSrc: string | null
  onCancel: () => void
  onConfirm: (items: DetectedHallElement[]) => void
}) {
  const [items, setItems] = useState<DetectedHallElement[]>(props.items)

  const tableCount = items.filter((it) => it.type.endsWith('_table')).length
  const otherCount = items.length - tableCount
  const needsCheckCount = items.filter((it) => confidenceTier(it.confidence) !== 'high').length

  // חפיפה משמעותית בין פריטים (req 6) — מחושב על הקואורדינטות המנורמלות
  // הגולמיות (scale-invariant, ראה rectOverlapFraction), רק לתגית אזהרה;
  // לא מזיז שום דבר אוטומטית.
  const overlapFlags = useMemo(() => {
    const flags = new Array(items.length).fill(false)
    for (let a = 0; a < items.length; a++) {
      for (let b = a + 1; b < items.length; b++) {
        if (rectOverlapFraction(itemAsAxisRect(items[a]), itemAsAxisRect(items[b])) > SKETCH_OVERLAP_WARN_THRESHOLD) {
          flags[a] = true
          flags[b] = true
        }
      }
    }
    return flags
  }, [items])

  function updateItem(i: number, patch: Partial<DetectedHallElement>) {
    setItems((prev) => prev.map((it, idx) => (idx === i ? { ...it, ...patch } : it)))
  }
  function removeItem(i: number) {
    setItems((prev) => prev.filter((_, idx) => idx !== i))
  }
  // מוסיף אובייקט חדש (ברירת מחדל: שולחן עגול) שה-AI פספס — אפשר לשנות את
  // הסוג מיד מהתפריט הנפתח באותה שורה, בדיוק כמו כל פריט שזוהה (req 6).
  function addMissingItem() {
    setItems((prev) => [
      ...prev,
      { type: 'round_table', x: 0.5, y: 0.5, width: 0.08, height: 0.08, rotation: 0, capacity: 12, confidence: 1, label: '' },
    ])
  }

  return (
    <>
      <div className="sk-editor-backdrop" onClick={props.onCancel} />
      <div className="sk-review" role="dialog" aria-label={hallSketchT.reviewTitle}>
        <div className="sk-editor-head">
          <h2>{hallSketchT.reviewTitle}</h2>
          <p>
            {hallSketchT.summary(tableCount, otherCount)}
            {needsCheckCount > 0 ? ` ${hallSketchT.needsCheck(needsCheckCount)}` : ''}
          </p>
        </div>

        <div className="sk-review-body">
          {props.sketchSrc && (
            <div className="sk-review-preview-wrap">
              {/* אותן קואורדינטות מנורמלות [0,1] שחזרו מ-AI Vision, מוצגות ישירות
                  על גבי הסקיצה המקורית — תמיד גלוי (לא toggle נסתר), כדי
                  שאפשר יהיה לבדוק כל זיהוי מול המקור בלי לנחש (req 3). */}
              <img src={props.sketchSrc} alt="" className="sk-review-preview-img" />
              {items.map((it, i) => {
                const tier = confidenceTier(it.confidence)
                return (
                  <div
                    key={i}
                    className={`sk-review-box sk-review-box-${tier} ${overlapFlags[i] ? 'sk-review-box-overlap' : ''}`}
                    style={{
                      left: `${(it.x - it.width / 2) * 100}%`,
                      top: `${(it.y - it.height / 2) * 100}%`,
                      width: `${it.width * 100}%`,
                      height: `${it.height * 100}%`,
                    }}
                    title={`${DETECTED_TYPE_LABELS[it.type]} · ${
                      tier === 'high' ? hallSketchT.confidenceHigh : tier === 'mid' ? hallSketchT.confidenceMid : hallSketchT.confidenceLow
                    }`}
                  >
                    {/* מספר שנקרא מהסקיצה מוצג כמו שהוא — זה בדיוק המספר
                        שהשולחן יקבל במפה (ראה assignTableNumbers). */}
                    <span className="sk-review-box-num">{it.table_number ?? (it.label || i + 1)}</span>
                  </div>
                )
              })}
            </div>
          )}

          <div className="sk-review-list">
            {items.map((it, i) => {
              const tier = confidenceTier(it.confidence)
              const isTable = it.type.endsWith('_table')
              return (
                <div key={i} className="sk-review-row-wrap">
                  <div className="sk-review-row">
                    <span className={`sk-review-badge sk-review-badge-${tier}`}>
                      {CONFIDENCE_EMOJI[tier]}{' '}
                      {tier === 'high' ? hallSketchT.confidenceHigh : tier === 'mid' ? hallSketchT.confidenceMid : hallSketchT.confidenceLow}
                    </span>
                    {isTable && it.table_number != null && (
                      <span className="sk-review-badge sk-review-badge-num" title={hallSketchT.numberFromSketchHint}>
                        #{' '}
                        {hallSketchT.numberFromSketch(it.table_number)}
                      </span>
                    )}
                    {overlapFlags[i] && (
                      <span className="sk-review-badge sk-review-badge-overlap" title={hallSketchT.overlapWarningHint}>
                        ⚠️ {hallSketchT.overlapWarning}
                      </span>
                    )}
                    <select
                      value={it.type}
                      onChange={(e) => updateItem(i, { type: e.target.value as DetectedHallElement['type'] })}
                    >
                      {DETECTED_TYPE_OPTIONS.map((t) => (
                        <option key={t} value={t}>
                          {DETECTED_TYPE_LABELS[t]}
                        </option>
                      ))}
                    </select>
                    {isTable && (
                      <span className="sk-review-capacity">
                        <button type="button" onClick={() => updateItem(i, { capacity: Math.max(2, (it.capacity ?? 12) - 2) })}>
                          −
                        </button>
                        {it.capacity ?? 12}
                        <button type="button" onClick={() => updateItem(i, { capacity: Math.min(24, (it.capacity ?? 12) + 2) })}>
                          +
                        </button>
                      </span>
                    )}
                    <button
                      type="button"
                      className="sk-review-icon-btn"
                      title={hallSketchT.rotateItem}
                      onClick={() => updateItem(i, { rotation: ((it.rotation ?? 0) + 90) % 360 })}
                    >
                      ↻
                    </button>
                    <button
                      type="button"
                      className="sk-review-icon-btn"
                      title={hallSketchT.removeItem}
                      onClick={() => removeItem(i)}
                    >
                      ✕
                    </button>
                  </div>
                  {/* שפה פשוטה במקום מספר/אחוז — רק לפריטים שכדאי לבדוק (req 4). */}
                  {tier !== 'high' && (
                    <p className="sk-review-row-hint">
                      {tier === 'mid' ? hallSketchT.confidenceHintMid(DETECTED_TYPE_LABELS[it.type]) : hallSketchT.confidenceHintLow}
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        <div className="sk-review-add-wrap">
          <button type="button" className="hm-ghost-btn sk-review-add" onClick={addMissingItem}>
            {hallSketchT.addMissingTable}
          </button>
          <p className="sk-review-add-hint">{hallSketchT.addMissingHint}</p>
        </div>

        <div className="sk-editor-actions">
          <button className="sk-confirm" onClick={() => props.onConfirm(items)} disabled={items.length === 0}>
            {hallSketchT.confirm}
          </button>
          <button className="sk-cancel" onClick={props.onCancel}>
            {hallSketchT.cancel}
          </button>
        </div>
        <p className="sk-review-confirm-hint">{hallSketchT.confirmHint}</p>
      </div>
    </>
  )
}

// שלב 4 (שלב E, דרישה 8): אישור קצר אחרי שהאולם נבנה בפועל — עובדתי, בלי
// חגיגה, עם מספרים (כמו כל הודעת הצלחה ב-VEYA). האולם כבר בנוי ב-state
// ברגע שזה מוצג; "פתיחת האולם" רק סוגר את המסך הזה ומגלה אותו.
function SketchBuildSuccess(props: { items: DetectedHallElement[]; onOpen: () => void }) {
  const tableCount = props.items.filter((it) => it.type.endsWith('_table')).length
  const elementTypes = Array.from(new Set(props.items.filter((it) => !it.type.endsWith('_table')).map((it) => it.type)))
  const parts: string[] = []
  if (tableCount > 0) parts.push(tableCount === 1 ? 'שולחן אחד' : `${tableCount} שולחנות`)
  for (const t of elementTypes) parts.push(DETECTED_TYPE_LABELS[t])
  return (
    <div className="sk-editor-backdrop">
      <div className="sk-analyzing sk-build-success" role="status" aria-live="polite">
        <span className="sk-build-success-icon" aria-hidden="true">
          ✓
        </span>
        <h2>{hallSketchT.builtTitle}</h2>
        {parts.length > 0 && <p className="sk-build-success-summary">{parts.join(' · ')}</p>}
        <button type="button" className="sk-confirm" onClick={props.onOpen}>
          {hallSketchT.builtOpen}
        </button>
      </div>
    </div>
  )
}

export function HallPage({ onNavigate }: { onNavigate?: (page: 'dashboard') => void } = {}) {
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
  const [dirty, setDirty] = useState(false)
  const [loading, setLoading] = useState(false)
  // שמירה אוטומטית (בלי כפתור): saving = בקשת שמירה פעילה כרגע.
  const [saving, setSaving] = useState(false)
  const [savedTick, setSavedTick] = useState(false) // הבהוב "נשמר ✓" קצר
  const [error, setError] = useState('')
  // הסברי "למה שובץ כאן" מהסידור האוטומטי האחרון — מוצגים בפאנל סיכום שאפשר לסגור.
  const [seatExplain, setSeatExplain] = useState<SeatingExplanation[]>([])
  // דוח ההרצה האחרונה של "הושבה בקליק": כמה שובצו, והאם נמצאו הפרות.
  const [seatingReport, setSeatingReport] = useState<{
    ok: boolean
    people: number
    tables: number
    violations: SeatingViolation[]
  } | null>(null)
  // "החזרת הסידור הקודם" — נטען מהשרת כדי שישרוד רענון דף.
  const [canUndo, setCanUndo] = useState(false)
  const [undoing, setUndoing] = useState(false)
  const [undoNote, setUndoNote] = useState('')

  // ---- חוויית הושבה אחידה בטלפון ובמחשב (Auto-Fit, Bottom Sheet, ניווט תחתון) ----
  // אותה מפה נוחה בכל מכשיר: הלוח נכנס במלואו למסך, הקשה על שולחן פותחת
  // Bottom Sheet, וניווט תחתון עם 5 מדורים. במחשב הלוח ממלא את אזור התוכן
  // שלצד סרגל הצד (המיקום נקבע ב-CSS לפי רוחב המסך).
  const [mobileTab, setMobileTab] = useState<'hall' | 'tables' | 'guests' | 'smart' | 'tools'>('hall')
  // מיון רשימת "מוזמנים": ברירת מחדל לפי סטטוס שיבוץ (ללא שולחן קודם), או
  // א'-ב'/מספר שולחן — לבחירת המשתמש, נשמר רק בזיכרון המסך הנוכחי.
  const [guestSortMode, setGuestSortMode] = useState<'status' | 'name' | 'table'>('status')
  const [sheetTable, setSheetTable] = useState<number | null>(null)
  const [sheetEdit, setSheetEdit] = useState(false)
  // השולחן שנבחר **על המפה** — נפרד מ-sheetTable בכוונה.
  //
  // הבחירה והגיליון התחתון היו אותו state, ולכן ידית הסיבוב (z-index 8)
  // הופיעה בדיוק כשהגיליון (z-index 71) והרקע שלו (70) כיסו אותה — היא
  // הייתה גלויה אבל `elementFromPoint` החזיר את הגיליון, כלומר בלתי
  // ניתנת ללחיצה לחלוטין. זה מה שגרם ל"אי אפשר לסובב שולחן אבירים":
  // בשולחן עגול הסיבוב לא נראה לעין, אז הבאג התגלה רק במלבניים/אבירים.
  //
  // עכשיו זה עובד כמו אלמנט הבר: הבחירה חיה על המפה בזכות עצמה, והגיליון
  // הוא שכבה נפרדת שאפשר לסגור בלי לאבד את הבחירה.
  const [selectedTable, setSelectedTable] = useState<number | null>(null)
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
  // מסך הבחירה שקודם לאשף: "בניית אולם חדש" (ידני) מול "בניית אולם מסקיצה"
  // (Sketch Upload Flow). נפתח אוטומטית כשהאולם ריק, וגם מכפתור "בניית אולם
  // מחדש" — שתי הבחירות רק פותחות מנגנון קיים (wizardOpen / sketchUploadOpen),
  // בלי שום שינוי בהם.
  const [startChoiceOpen, setStartChoiceOpen] = useState(false)
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
  // שלב D: true אחרי שהמשתמש זימם/הזיז ידנית בנגיעה (Pinch/Pan) — עוצר את
  // ה-Auto-Fit האוטומטי-על-שינוי-תוכן (למטה) כדי שגרירת שולחן לא "תבטל" זום
  // ידני שהמשתמש בחר. "התאם למסך" מאפס את הדגל וחוזר להתנהגות האוטומטית.
  const manualViewRef = useRef(false)

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
  // שלב E: פאנל ההעלאה (כותרת/הסבר/dropzone/preview) שנפתח *לפני* עורך
  // הסקיצה — pickedSketchFile הוא הקובץ שנבחר וממתין לאישור ("ניתוח ובניית
  // האולם"), לפני שהוא הופך ל-sketchEditSrc (עורך החיתוך, ללא שינוי).
  const [sketchUploadOpen, setSketchUploadOpen] = useState(false)
  const [pickedSketchFile, setPickedSketchFile] = useState<{ name: string; size: number; dataUrl: string } | null>(null)
  // עורך הסקיצה: התמונה הגולמית שממתינה לעריכה (לפני שמירה), והתמונה
  // המקורית שנשמרת בזיכרון-הפעלה כדי שעריכה חוזרת תהיה איכותית (חיתוך-מחדש
  // מהמקור ולא מהתמונה שכבר נחתכה). לא נשמר בשרת — רק לנוחות הסשן.
  const [sketchEditSrc, setSketchEditSrc] = useState<string | null>(null)
  const sketchOriginalRef = useRef<string | null>(null)
  // מיקום/גודל/סיבוב/שקיפות/נעילה/הצגה של שכבת הסקיצה (שלב C — עצמאית
  // לגמרי מהשולחנות/אלמנטים: הזזה שלה לא נוגעת בהם, והזזתם לא נוגעת בה).
  // null = תאימות אחורה — הסקיצה מוצגת כרקע מלא בדיוק כמו תמיד (ראה
  // defaultSketchTransform, שממלא ערך אמיתי רק ברגע שנוגעים בה בפועל).
  const [sketchTransform, setSketchTransform] = useState<HallSketchTransform | null>(null)
  // בחירה על הלוח (מציגה ידיות סיבוב/שינוי-גודל + סרגל צף) — נפרדת מ-
  // selectedTable/selectedEl, בדיוק כמו שהם נפרדים זה מזה.
  const [sketchSelected, setSketchSelected] = useState(false)

  // ---- בניית אולם אוטומטית מסקיצה (AI Vision) ----
  const [sketchAnalyzing, setSketchAnalyzing] = useState(false)
  // מגן סינכרוני נגד ניתוח כפול (ראה runSketchAnalysis) — ref, לא state,
  // כי צריך לבדוק/לעדכן מיידית לפני שרינדור הבא "רואה" את זה.
  const sketchAnalyzingRef = useRef(false)
  const [sketchAnalyzeError, setSketchAnalyzeError] = useState('')
  // true = "לא זיהינו כלום" (לא כשל אמיתי — כותרת/כפתורים שונים מהשגיאה).
  const [sketchAnalyzeEmpty, setSketchAnalyzeEmpty] = useState(false)
  const [sketchReview, setSketchReview] = useState<DetectedHallElement[] | null>(null)
  // אישור "האולם נבנה בהצלחה" (שלב E) — null = לא מוצג; אחרת מחזיק את
  // הפריטים שאושרו כדי לחשב את שורת הסיכום (X שולחנות · רחבה · בר...).
  const [sketchBuildResult, setSketchBuildResult] = useState<DetectedHallElement[] | null>(null)
  // ממתין להכרעה "להחליף או להוסיף?" כשכבר יש אולם על הלוח בזמן בנייה מסקיצה.
  const [sketchBuildPending, setSketchBuildPending] = useState<DetectedHallElement[] | null>(null)
  // כמה מוזמנים משובצים כרגע — מוצג באזהרת ההחלפה (בהחלפה הם חוזרים ל"ללא שולחן").
  const seatedGuestCount = useMemo(
    () => tables.reduce((sum, t) => sum + t.guests.length, 0),
    [tables],
  )
  // מידות התמונה המקורית (פיקסלים) — נטענות פעם אחת יחד עם ניתוח ה-AI,
  // כדי ש-applySketchReview יוכל לשמר את יחס-הממדים שלה (ראה sketchBuildCanvasSize).
  const sketchImgSizeRef = useRef<{ w: number; h: number } | null>(null)

  // ---- עוזר הושבה חכם (Dock) ----
  // זוגות אילוצים שכבר מחושבים בשרת מהערות חופשיות — נשמרים כאן כדי
  // שהעוזר יוכל לבדוק אותם מיידית בצד לקוח בלי קריאת רשת נוספת.
  const [forbiddenPairs, setForbiddenPairs] = useState<PairList>([])
  const [togetherPairs, setTogetherPairs] = useState<PairList>([])
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

  // אזהרת "הושבה ידנית של מי שלא אישר הגעה" (Audit RSVP↔הושבה, 2026-08-19)
  // — בהמתנה לאישור, בדיוק כמו pendingProposal. ``onConfirm`` מבצע רק את
  // ההושבה עצמה (table_number) ולעולם לא נוגע ב-RSVP.
  const [seatWarning, setSeatWarning] = useState<{
    guestIds: number[]
    onConfirm: () => void
  } | null>(null)

  // ---- אילוצים מההערות (לולאת הבהרות) ----
  const [clarifications, setClarifications] = useState<Clarification[]>([])
  const [analyzeSummary, setAnalyzeSummary] = useState<AnalyzeResult | null>(null)
  const [analyzing, setAnalyzing] = useState(false)

  type DragState =
    | { kind: 'table-group'; items: { id: number; startX: number; startY: number }[]; startWorldX: number; startWorldY: number }
    | { kind: 'table-rotate'; id: number; cx: number; cy: number }
    | { kind: 'element'; id: string; dx: number; dy: number }
    | {
        kind: 'resize'
        id: string
        startX: number
        startY: number
        startW: number
        startH: number
        lockSquare: boolean
        rotation: number
      }
    | { kind: 'rotate'; id: string; cx: number; cy: number }
    | { kind: 'sketch-move'; dx: number; dy: number }
    | { kind: 'sketch-resize'; startX: number; startY: number; startW: number; startH: number; aspect: number; rotation: number }
    | { kind: 'sketch-rotate'; cx: number; cy: number }
  const dragRef = useRef<DragState | null>(null)
  // שלב D: מצב מחווה דו-אצבעית פעילה (Pinch/Pan ללוח, או צביטה/twist לסקיצה
  // הנבחרת) — ראה onCanvasTouchStart/Move/End.
  type TwoFingerGesture =
    | { kind: 'canvas-pan-zoom'; startDist: number; startMid: { x: number; y: number }; startScale: number; startOffset: { x: number; y: number } }
    | { kind: 'sketch-pinch'; startDist: number; startAngle: number; startW: number; startH: number; startRotation: number; aspect: number }
  const twoFingerRef = useRef<TwoFingerGesture | null>(null)
  // ערך "בהמתנה" בזמן צביטת-הסקיצה — נכתב ל-DOM ישירות בכל touchmove (ביצועים),
  // ונשמר ל-state האמיתי (sketchTransform) פעם אחת בלבד ב-touchend.
  const sketchPinchPendingRef = useRef<{ width: number; height: number; rotation: number } | null>(null)
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
    // מודע-סיבוב: אחרת שולחן/אלמנט מסובב חורג מקופסת העולם ונחתך.
    for (const t of tables) {
      const { w, h } = tableRenderSize(t, preset)
      const b = rotatedBounds(t.x, t.y, w, h, t.rotation)
      maxX = Math.max(maxX, b.maxX)
      maxY = Math.max(maxY, b.maxY)
    }
    for (const el of elements) {
      const b = rotatedBounds(el.x, el.y, el.width, el.height, el.rotation)
      maxX = Math.max(maxX, b.maxX)
      maxY = Math.max(maxY, b.maxY)
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
        width: t.width ?? undefined,
        height: t.height ?? undefined,
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
    setSketchTransform(h.sketch_transform ?? null)
    setSketchSelected(false)
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
        setStartChoiceOpen(true)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.hallLoadFailed)
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
    // האם יש סידור קודם לשחזור. נטען מהשרת (ולא מהזיכרון של הדפדפן) כדי
    // שכפתור "החזרת הסידור הקודם" ישרוד רענון דף ומעבר מכשיר.
    getSeatingUndoState()
      .then((s) => setCanUndo(s.can_undo))
      .catch(() => {
        /* שקט — היעדר הכפתור עדיף על הודעת שגיאה בטעינה */
      })
  }, [load, loadClarifications])

  // ---- התאמה-למסך חד-פעמית (Auto-Fit) ----
  // מחשבים קנה-מידה אחד שמכניס את כל העולם (התוכן + שוליים) לאזור התצוגה, וממרכז
  // אותו. זה רץ *פעם אחת* בכניסה, אחרי בניית אולם, ובשינוי גודל מסך/סיבוב — אבל
  // *לא* בהוספת שולחן/כיסא או בגרירה, כדי שלא יהיו קפיצות-גודל תוך כדי עבודה.
  // הידיות והתוויות נשארות בגודל-מסך דרך המשתנה --hm-s (counter-scale ב-CSS).
  // גבולות התוכן האמיתיים (bbox של כל השולחנות/אלמנטים, כולל סיבוב) — הבסיס
  // המשותף ל-recomputeFit, centerContent, ולהצמדת-פאן (clampPanOffset) בשלב D.
  // מופרד מ-recomputeFit כדי שאפשר יהיה להשתמש בו גם ב"מרכז" בלי לשכפל לוגיקה.
  const computeContentBounds = useCallback((): { minX: number; minY: number; maxX: number; maxY: number } | null => {
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    for (const t of tablesRef.current) {
      const { w, h } = tableRenderSize(t, presetRef.current)
      const b = rotatedBounds(t.x, t.y, w, h, t.rotation)
      minX = Math.min(minX, b.minX)
      minY = Math.min(minY, b.minY)
      maxX = Math.max(maxX, b.maxX)
      maxY = Math.max(maxY, b.maxY)
    }
    for (const el of elementsRef.current) {
      const b = rotatedBounds(el.x, el.y, el.width, el.height, el.rotation)
      minX = Math.min(minX, b.minX)
      minY = Math.min(minY, b.minY)
      maxX = Math.max(maxX, b.maxX)
      maxY = Math.max(maxY, b.maxY)
    }
    return isFinite(minX) ? { minX, minY, maxX, maxY } : null
  }, [])

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
    const bounds = computeContentBounds()
    // אין תוכן עדיין — לא משנים כלום (נחכה שהתוכן ייטען ואז נריץ שוב).
    if (!bounds) return
    const { minX, minY, maxX, maxY } = bounds
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
    // "התאם למסך" הוא איפוס מלא לתצוגה האוטומטית — מבטל כל זום/פאן ידני
    // שהמשתמש עשה (שלב D), כדי ש-Auto-Fit יחזור לפעול על שינויי תוכן עתידיים.
    manualViewRef.current = false
    setViewScale(s)
    setViewTransform(`translate(${offX}px, ${offY}px) scale(${s})`)
  }, [computeContentBounds])

  // "מרכז את האולם" (שלב D): ממרכז את התוכן הנוכחי בלי לגעת בקנה-המידה —
  // שימושי אחרי פאן שאיבד את הלוח מהתצוגה, בלי "לקפוץ" גם בזום כמו Fit.
  const centerContent = useCallback(() => {
    const vp = viewportRef.current
    if (!vp) return
    const vpW = vp.clientWidth
    const vpH = vp.clientHeight
    if (!vpW || !vpH) return
    const bounds = computeContentBounds()
    if (!bounds) return
    const s = scaleRef.current || 1
    const centerX = (bounds.minX + bounds.maxX) / 2
    const centerY = (bounds.minY + bounds.maxY) / 2
    const offX = vpW / 2 - centerX * s
    const offY = vpH / 2 - centerY * s
    scaleRef.current = s
    offsetRef.current = { x: offX, y: offY }
    setViewTransform(`translate(${offX}px, ${offY}px) scale(${s})`)
  }, [computeContentBounds])

  // Auto-Fit: מתאימים מחדש בכל פעם שגודל התוכן (worldSize) משתנה — טעינה, הוספת
  // שולחן/אלמנט, בנייה מחדש — כך תמיד רואים את *כל* האולם ואף פעם לא נחתך חצי.
  // חשוב: התלות ב-worldSize פותרת את הבאג המקורי — קודם ההתאמה רצה פעם אחת מוקדם
  // מדי (לפני שהשולחנות נטענו) וחישבה "אולם ריק", ואז לא רצה שוב. עכשיו היא רצה
  // כשהתוכן האמיתי מוכן. מדלגים רק בזמן גרירה פעילה כדי לא להילחם באצבע.
  useEffect(() => {
    if (loading) return
    if (dragRef.current) return
    // שלב D: אחרי זום/פאן ידני בנגיעה, שינוי תוכן (גרירת שולחן) לא אמור
    // "לבטל" את הבחירה של המשתמש — רק "התאם למסך" עושה זאת במפורש.
    if (manualViewRef.current) return
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

  // ---- קיצורי מקלדת (במחשב): Delete למחיקה, Esc לסגירה, Ctrl/Cmd+D לשכפול ----
  // הבחירה הפעילה היא מה שפתוח כרגע: אלמנט נבחר במפה, או השולחן שה-Bottom
  // Sheet שלו פתוח. אין יותר בחירה מרובה (היא הייתה קיימת רק בשכבת הדסקטופ
  // הישנה שנמחקה, ולא הייתה דרך להפעיל אותה במסך שהמשתמש רואה בפועל).
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const tag = (document.activeElement?.tagName || '').toLowerCase()
      if (tag === 'input' || tag === 'textarea') return
      if (e.key === 'Escape') {
        setSheetTable(null)
        setSelectedEl(null)
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        if (sheetTable != null) deleteTable(sheetTable)
        else if (selectedEl) removeElement(selectedEl)
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'd') {
        if (selectedEl || sheetTable != null) {
          e.preventDefault()
          if (selectedEl) duplicateElement(selectedEl)
          else if (sheetTable != null) duplicateTable(sheetTable)
        }
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sheetTable, selectedEl, tables, elements])

  async function onAnalyze() {
    setAnalyzing(true)
    setError('')
    try {
      setAnalyzeSummary(await analyzeConstraints())
      await loadClarifications()
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.hallNotesLoadFailed)
    } finally {
      setAnalyzing(false)
    }
  }

  async function onResolve(id: number, chosenGuestId: number | null) {
    try {
      setAnalyzeSummary(await resolveClarification(id, chosenGuestId))
      await loadClarifications()
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.hallChoiceSaveFailed)
    }
  }

  // אין יותר הצמדה לרשת — מיקום חופשי (מעוגל לפיקסל שלם).
  function snapVal(v: number) {
    return Math.round(v)
  }

  // ---- גרירת שולחן ----
  function onTablePointerDown(e: React.PointerEvent, tnum: number) {
    e.stopPropagation()
    const t = tables.find((x) => x.table_number === tnum)
    if (!t) return
    // מתחילים אינטראקציה חדשה: מאפסים את דגל ה"נגרר" כאן (בתחילת הלחיצה) ולא
    // ב-pointerup — כדי שה-click שרץ *אחרי* הגרירה עדיין יראה שהיתה גרירה
    // ולא יפתח את חלון העריכה. (ראה onCanvasPointerUp — שם כבר לא מאפסים.)
    movedRef.current = false
    dragStartRef.current = { x: e.clientX, y: e.clientY }
    const movable = tables.filter((x) => x.table_number === tnum && !x.locked)
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
    setSelectedTable(null)
    setSheetTable(null)
  }

  function onResizePointerDown(e: React.PointerEvent, id: string) {
    e.stopPropagation()
    movedRef.current = false
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
      rotation: el.rotation || 0,
    }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  // סיבוב שולחן — זהה לחלוטין לסיבוב אלמנט (הבר), לכל סוגי השולחנות.
  // מרכז הסיבוב נלקח מה-rect האמיתי על המסך, ולכן זה נכון גם כשהלוח מוקטן.
  function onTableRotatePointerDown(e: React.PointerEvent, tnum: number) {
    e.stopPropagation()
    // אינטראקציה חדשה — מאפסים כמו בכל pointerdown אחר. בלי זה הדגל נשאר
    // "נגרר" אחרי הסיבוב, וההקשה הבאה על רקע המפה (ביטול בחירה) נבלעת.
    movedRef.current = false
    const graphic = (e.currentTarget as HTMLElement).parentElement
    if (!graphic) return
    const r = graphic.getBoundingClientRect()
    dragRef.current = {
      kind: 'table-rotate',
      id: tnum,
      cx: r.left + r.width / 2,
      cy: r.top + r.height / 2,
    }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  function onRotatePointerDown(e: React.PointerEvent, id: string) {
    e.stopPropagation()
    movedRef.current = false
    // מרכז הסיבוב נלקח מה-rect האמיתי של האלמנט על המסך (getBoundingClientRect),
    // ולא מחישוב לפי el.x/scroll — כך זה נכון גם במובייל שבו הלוח מוקטן (scale<1).
    const elNode = (e.currentTarget as HTMLElement).parentElement
    if (!elNode) return
    const r = elNode.getBoundingClientRect()
    dragRef.current = { kind: 'rotate', id, cx: r.left + r.width / 2, cy: r.top + r.height / 2 }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  // ---- שכבת הסקיצה: הזזה/שינוי-גודל/סיבוב/שקיפות/נעילה/הצגה (שלב C) ----
  // כל הפעולות עצמאיות לגמרי משולחנות/אלמנטים — פועלות רק על sketchTransform.
  function patchSketchTransform(
    patch: Partial<HallSketchTransform> | ((cur: HallSketchTransform) => Partial<HallSketchTransform>),
  ) {
    setSketchTransform((cur) => {
      const base = cur ?? defaultSketchTransform(worldSize)
      const p = typeof patch === 'function' ? patch(base) : patch
      return { ...base, ...p }
    })
    setDirty(true)
  }

  function toggleSketchLock() {
    patchSketchTransform((cur) => ({ locked: !cur.locked }))
  }

  function toggleSketchHidden() {
    patchSketchTransform((cur) => ({ hidden: !cur.hidden }))
  }

  function resetSketchTransform() {
    setSketchTransform(defaultSketchTransform(worldSize))
    setDirty(true)
  }

  // גרירה להזזה — זהה לחלוטין לתבנית onElementPointerDown, רק שמפעילה על
  // sketchTransform. אם עדיין אין transform משלה (סקיצה ישנה/ידנית) — "אופים"
  // אותו עכשיו לערך שמזהה בדיוק את מה שכבר מוצג (ראה defaultSketchTransform),
  // כדי שהגרירה תתחיל מהמיקום הנכון ותישמר בפועל.
  function onSketchPointerDown(e: React.PointerEvent) {
    e.stopPropagation()
    movedRef.current = false
    dragStartRef.current = { x: e.clientX, y: e.clientY }
    const st = sketchTransform ?? defaultSketchTransform(worldSize)
    if (sketchTransform === null) setSketchTransform(st)
    if (st.locked) return
    const w = toWorld(e.clientX, e.clientY)
    dragRef.current = { kind: 'sketch-move', dx: w.x - st.x, dy: w.y - st.y }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  // הקשה (בלי גרירה) → בחירה. אותה הגנה כמו onElementClick.
  function onSketchClick(e: React.MouseEvent) {
    e.stopPropagation()
    if (movedRef.current) return
    setSketchSelected(true)
    setSelectedTable(null)
    setSelectedEl(null)
    setSheetTable(null)
  }

  function onSketchResizePointerDown(e: React.PointerEvent) {
    e.stopPropagation()
    movedRef.current = false
    const st = sketchTransform
    if (!st || st.locked) return
    dragRef.current = {
      kind: 'sketch-resize',
      startX: e.clientX,
      startY: e.clientY,
      startW: st.width,
      startH: st.height,
      // יחס-הממדים נלכד ברגע ההתחלה ונשמר תמיד — שינוי גודל אף פעם לא מותח
      // את הסקיצה (דרישה מפורשת של שלב C).
      aspect: st.height > 0 ? st.width / st.height : 1,
      rotation: st.rotation || 0,
    }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  function onSketchRotatePointerDown(e: React.PointerEvent) {
    e.stopPropagation()
    movedRef.current = false
    const node = (e.currentTarget as HTMLElement).parentElement
    if (!node) return
    const r = node.getBoundingClientRect()
    dragRef.current = { kind: 'sketch-rotate', cx: r.left + r.width / 2, cy: r.top + r.height / 2 }
    ;(e.target as HTMLElement).setPointerCapture?.(e.pointerId)
  }

  function onCanvasPointerMove(e: React.PointerEvent) {
    const drag = dragRef.current
    if (!drag) return
    // סף-תזוזה: רק להזזת אלמנט/שולחן. עד שהאצבע לא זזה ~6px זו עדיין הקשה
    // (בחירה) ולא גרירה — כדי שרעד קטן לא יזיז ולא יבטל את הבחירה. ידיות
    // סיבוב/שינוי-גודל לא מוגבלות בסף (שם כל תזוזה קטנה חשובה).
    if (!movedRef.current && (drag.kind === 'element' || drag.kind === 'table-group' || drag.kind === 'sketch-move')) {
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
            const ox = snapVal(item.startX + p.dx) - item.startX
            const oy = snapVal(item.startY + p.dy) - item.startY
            node.style.transform = `translate(${ox}px, ${oy}px)`
          }
        })
      }
      return // בלי setState / setDirty בזמן הגרירה — זה קורה פעם אחת ב-pointerup
    } else if (drag.kind === 'table-rotate') {
      const deg = (Math.atan2(e.clientY - drag.cy, e.clientX - drag.cx) * 180) / Math.PI + 90
      const next = normalizeRotation(deg)
      setTables((prev) =>
        prev.map((t) => (t.table_number === drag.id ? { ...t, rotation: next } : t)),
      )
    } else if (drag.kind === 'element') {
      const w = toWorld(e.clientX, e.clientY)
      const x = snapVal(w.x - drag.dx)
      const y = snapVal(w.y - drag.dy)
      setElements((prev) => prev.map((el) => (el.id === drag.id ? { ...el, x, y } : el)))
    } else if (drag.kind === 'resize') {
      // תזוזת-מסך → תזוזת-לוח: בדסקטופ 1:1, במובייל מחולק בקנה-המידה.
      const s = scaleRef.current || 1
      const rawX = (e.clientX - drag.startX) / s
      const rawY = (e.clientY - drag.startY) / s
      // באלמנט מסובב, צירי המסך אינם צירי האלמנט: גרירת הפינה של בר
      // שסובב 90° הייתה מגדילה את הצד הלא נכון. מסובבים את הדלתא
      // ב-‎−rotation כדי לעבוד תמיד בצירים המקומיים של האלמנט.
      const rad = ((drag.rotation || 0) * Math.PI) / 180
      const cos = Math.cos(-rad)
      const sin = Math.sin(-rad)
      const dx = rawX * cos - rawY * sin
      const dy = rawX * sin + rawY * cos
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
      const next = normalizeRotation(deg)
      setElements((prev) => prev.map((el) => (el.id === drag.id ? { ...el, rotation: next } : el)))
    } else if (drag.kind === 'sketch-move') {
      const w = toWorld(e.clientX, e.clientY)
      const x = snapVal(w.x - drag.dx)
      const y = snapVal(w.y - drag.dy)
      setSketchTransform((cur) => (cur ? { ...cur, x, y } : cur))
    } else if (drag.kind === 'sketch-resize') {
      // אותה תבנית בדיוק כמו שינוי-גודל לאלמנט (מסובב את הדלתא לצירים
      // המקומיים), אבל כאן הגובה תמיד נגזר מהרוחב לפי היחס שנלכד בתחילת
      // הגרירה — לעולם לא מותחים את הסקיצה (דרישה מפורשת).
      const s = scaleRef.current || 1
      const rawX = (e.clientX - drag.startX) / s
      const rawY = (e.clientY - drag.startY) / s
      const rad = ((drag.rotation || 0) * Math.PI) / 180
      const cos = Math.cos(-rad)
      const sin = Math.sin(-rad)
      const dx = rawX * cos - rawY * sin
      const dy = rawX * sin + rawY * cos
      // ממוצע X/Y: גרירה לכל כיוון (לא רק אלכסון מדויק) משנה גודל בצורה חלקה.
      const w = Math.max(SKETCH_MIN_SIZE, drag.startW + (dx + dy * drag.aspect) / 2)
      const h = w / drag.aspect
      setSketchTransform((cur) => (cur ? { ...cur, width: w, height: h } : cur))
    } else if (drag.kind === 'sketch-rotate') {
      const deg = (Math.atan2(e.clientY - drag.cy, e.clientX - drag.cx) * 180) / Math.PI + 90
      const next = normalizeRotation(deg)
      setSketchTransform((cur) => (cur ? { ...cur, rotation: next } : cur))
    }
    setDirty(true)
  }

  // חסימת ה-click ה"רפאים" שהדפדפן יורה מיד אחרי סיום גרירה. גם אם movedRef
  // התאפס או שה-click מכוון לאלמנט אחר — כאן אנחנו בולעים את ה-click הבא בשלב
  // ה-capture (לפני שהוא מגיע ל-onTableClick/onElementClick), וכך גרירה לעולם
  // לא פותחת את חלון העריכה. הגנת timeout מסירה את המאזין אם משום מה אין click.
  //
  // חשוב: בולעים רק click שהיעד שלו בתוך .hall-world (שולחן/אלמנט על המפה
  // עצמה) — לא כל click בעמוד. בלי ההגבלה הזו, גרירת שולחן ואז הקשה מיידית
  // על כפתור מחוץ למפה (כמו ה-FAB "+" להוספת שולחן) הייתה נבלעת גם היא,
  // כי המאזין רשום על window ותופס את ה-click הבא בכל מקום — בדיוק הבאג
  // שדווח כ"כפתור הפלוס לפעמים לא מגיב".
  function suppressNextClick() {
    const handler = (ev: MouseEvent) => {
      if (worldRef.current?.contains(ev.target as Node)) {
        ev.stopPropagation()
        ev.preventDefault()
      }
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
              x: snapVal(item.startX + p.dx),
              y: snapVal(item.startY + p.dy),
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

  // ---- שלב D: מחוות מגע דו-אצבעיות (Pinch-Zoom / Pan / סיבוב-סקיצה) ----
  // עצמאי לגמרי מ-Vision/coordinate-mapping/HallSketchGeometry — UI/מחוות בלבד,
  // פועל מעל אותם scaleRef/offsetRef/sketchTransform שכבר קיימים.
  //
  // ביצועים (דרישה מפורשת): לא קוראים ל-setState בכל touchmove — מזיזים ישירות
  // את ה-DOM (transform על .hall-world או .hall-sketch-bg), בדיוק כמו שגרירת
  // קבוצת-שולחנות כבר עושה, ומתחייבים ל-state (setViewScale/patchSketchTransform)
  // פעם אחת בלבד ב-touchend. כך אין רינדור-מלא של HallPage באמצע המחווה.
  function clampPanOffset(offX: number, offY: number, s: number, vpW: number, vpH: number): { x: number; y: number } {
    const bounds = computeContentBounds()
    if (!bounds) return { x: offX, y: offY }
    // לפחות PAN_CLAMP_MIN_VISIBLE פיקסלים מתיבת-התוכן חייבים להישאר באזור-
    // התצוגה בכל ציר — כדי שאי אפשר "לאבד" את המפה לגמרי מחוץ למסך (דרישה 4).
    const contentLeft = bounds.minX * s + offX
    const contentRight = bounds.maxX * s + offX
    const contentTop = bounds.minY * s + offY
    const contentBottom = bounds.maxY * s + offY
    let x = offX
    let y = offY
    if (contentRight < PAN_CLAMP_MIN_VISIBLE) x += PAN_CLAMP_MIN_VISIBLE - contentRight
    if (contentLeft > vpW - PAN_CLAMP_MIN_VISIBLE) x -= contentLeft - (vpW - PAN_CLAMP_MIN_VISIBLE)
    if (contentBottom < PAN_CLAMP_MIN_VISIBLE) y += PAN_CLAMP_MIN_VISIBLE - contentBottom
    if (contentTop > vpH - PAN_CLAMP_MIN_VISIBLE) y -= contentTop - (vpH - PAN_CLAMP_MIN_VISIBLE)
    return { x, y }
  }

  // שתי אצבעות יורדות: אם הסקיצה נבחרה, פתוחה (לא נעולה), ושתי הנגיעות בתוך
  // התיבה שלה — המחווה שולטת בה (צביטה=גודל, twist=סיבוב). אחרת — פאן/זום
  // ללוח כולו. אם אצבע ראשונה כבר התחילה גרירת אובייקט (Pointer Events), היא
  // מבוטלת נקייה כאן כדי שלא "תילחם" עם המחווה הדו-אצבעית על אותו state.
  function onCanvasTouchStart(e: React.TouchEvent) {
    if (e.touches.length < 2) return
    if (dragRafRef.current != null) {
      cancelAnimationFrame(dragRafRef.current)
      dragRafRef.current = null
    }
    for (const node of dragNodesRef.current.values()) node.style.transform = ''
    dragNodesRef.current.clear()
    dragPendingRef.current = null
    dragRef.current = null
    movedRef.current = false

    const touches = e.touches
    const dist = touchDist(touches)

    const sk = sketchTransform
    if (sketchSelected && sk && !sk.locked) {
      const skEl = worldRef.current?.querySelector<HTMLElement>('.hall-sketch-bg')
      if (skEl) {
        const r = skEl.getBoundingClientRect()
        const within = (t: React.Touch) =>
          t.clientX >= r.left && t.clientX <= r.right && t.clientY >= r.top && t.clientY <= r.bottom
        if (within(touches[0]) && within(touches[1])) {
          twoFingerRef.current = {
            kind: 'sketch-pinch',
            startDist: dist,
            startAngle: touchAngle(touches),
            startW: sk.width,
            startH: sk.height,
            startRotation: sk.rotation || 0,
            aspect: sk.height > 0 ? sk.width / sk.height : 1,
          }
          return
        }
      }
    }

    twoFingerRef.current = {
      kind: 'canvas-pan-zoom',
      startDist: dist,
      startMid: touchMid(touches),
      startScale: scaleRef.current || 1,
      startOffset: { ...offsetRef.current },
    }
  }

  function onCanvasTouchMove(e: React.TouchEvent) {
    const g = twoFingerRef.current
    if (!g || e.touches.length < 2) return
    const touches = e.touches
    if (g.kind === 'canvas-pan-zoom') {
      const vp = viewportRef.current
      const world = worldRef.current
      if (!vp || !world) return
      const rect = vp.getBoundingClientRect()
      const dist = touchDist(touches)
      const mid = touchMid(touches)
      const scaleFactor = g.startDist > 0 ? dist / g.startDist : 1
      const s = clamp(g.startScale * scaleFactor, MANUAL_ZOOM_MIN, MANUAL_ZOOM_MAX)
      // נקודת-העולם שהייתה מתחת למרכז-שתי-האצבעות **בתחילת** המחווה נשארת
      // "תפוסה" מתחת לאצבעות לאורך כל הגרירה (בדיוק כמו pinch-zoom של מפות) —
      // כך גם זום וגם פאן קורים בטבעיות במחווה אחת.
      const worldX = (g.startMid.x - rect.left - g.startOffset.x) / g.startScale
      const worldY = (g.startMid.y - rect.top - g.startOffset.y) / g.startScale
      let offX = mid.x - rect.left - worldX * s
      let offY = mid.y - rect.top - worldY * s
      ;({ x: offX, y: offY } = clampPanOffset(offX, offY, s, vp.clientWidth, vp.clientHeight))
      scaleRef.current = s
      offsetRef.current = { x: offX, y: offY }
      manualViewRef.current = true
      world.style.transform = `translate(${offX}px, ${offY}px) scale(${s})`
      world.style.setProperty('--hm-s', String(s))
    } else if (g.kind === 'sketch-pinch') {
      const dist = touchDist(touches)
      const angle = touchAngle(touches)
      const scaleFactor = g.startDist > 0 ? dist / g.startDist : 1
      const w = Math.max(SKETCH_MIN_SIZE, g.startW * scaleFactor)
      const h = w / g.aspect
      const rotation = normalizeRotation(g.startRotation + (angle - g.startAngle))
      sketchPinchPendingRef.current = { width: w, height: h, rotation }
      const skEl = worldRef.current?.querySelector<HTMLElement>('.hall-sketch-bg')
      if (skEl) {
        skEl.style.width = `${w}px`
        skEl.style.height = `${h}px`
        skEl.style.transform = rotation ? `rotate(${rotation}deg)` : ''
      }
    }
  }

  function onCanvasTouchEnd(e: React.TouchEvent) {
    if (e.touches.length >= 2) return // עדיין שתי אצבעות (או יותר) — ממשיכים
    const g = twoFingerRef.current
    twoFingerRef.current = null
    if (!g) return
    if (g.kind === 'canvas-pan-zoom') {
      // מסנכרנים ל-state פעם אחת בסיום (לא בכל touchmove) — ראה הערת ביצועים למעלה.
      setViewScale(scaleRef.current)
      setViewTransform(`translate(${offsetRef.current.x}px, ${offsetRef.current.y}px) scale(${scaleRef.current})`)
    } else if (g.kind === 'sketch-pinch') {
      const pending = sketchPinchPendingRef.current
      sketchPinchPendingRef.current = null
      if (pending) patchSketchTransform(pending)
    }
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
    setSheetTable(null)
    setSelectedTable(null)
    setSelectedEl(null)
    setSketchSelected(false)
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
      x: Math.round(center.x - w / 2 + off),
      y: Math.round(center.y - h / 2 + off),
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
    setDirty(true)
  }

  function deleteTable(tnum: number) {
    const src = tables.find((t) => t.table_number === tnum)
    setTables((prev) => prev.filter((t) => t.table_number !== tnum))
    if (src && src.guests.length) setUnassigned((prev) => [...prev, ...src.guests])
    setSheetTable((cur) => (cur === tnum ? null : cur))
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
    // אם המספר החדש כבר תפוס ע"י שולחן אחר — מחליפים רק את התווית (המספר) בין
    // שני השולחנות. כל שאר הנתונים (מיקום, זווית, מוזמנים, קיבולת וכו') נשארים
    // צמודים לשולחן הפיזי כפי שהוא — השולחן לא "קופץ" למקום של השולחן האחר.
    const target = tables.find((t) => t.table_number === newNum)
    setTables((prev) =>
      prev.map((t) => {
        if (t.table_number === oldNum) return { ...t, table_number: newNum }
        if (target && t.table_number === newNum) return { ...t, table_number: oldNum }
        return t
      }),
    )
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
      x: Math.round(center.x - width / 2 + off),
      y: Math.round(center.y - height / 2 + off),
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
    setSelectedTable(null)
    setSheetTable(null)
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
          x: Math.round(center.x - w / 2 + off),
          y: Math.round(center.y - h / 2 + off),
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

  function onTableClick(e: React.MouseEvent, tnum: number) {
    e.stopPropagation()
    if (movedRef.current) return // זו הייתה גרירה, לא קליק לבחירה
    // מוזמן "נבחר להעברה" (הקשה עליו ברשימה) — הקשה על שולחן משבצת אותו לשם.
    if (selected !== null) {
      requestSeatGuest(selected, tnum)
      return
    }
    // אחרת: הקשה **בוחרת** את השולחן על המפה בלבד — בדיוק כמו אלמנט הבר.
    // הבחירה מציגה מיד ידית סיבוב + סרגל פעולות קטן צמוד לשולחן (מסובבים,
    // שוכפלים, מוחקים בלי שום חלון). "פרטים מלאים" (שם/סוג/צבע/רזרבה) הוא
    // כפתור מפורש בסרגל — לא עוד לחיצה על השולחן, כדי לא לשבור את ההרגל.
    // עד עכשיו הקשה פתחה ישר את הגיליון התחתון (עד 82% מהמסך), שקבר את
    // ידית הסיבוב מתחתיו — בדיוק הבעיה שביקשת לתקן.
    if (selectedTable === tnum) {
      setSelectedTable(null) // הקשה שנייה על שולחן נבחר מבטלת בחירה
      return
    }
    setSelectedEl(null)
    setSelectedTable(tnum)
  }

  function openTableSheet(tnum: number) {
    setSheetTable(tnum)
    setSheetEdit(false)
  }

  // ---- סקיצת האולם ----
  // בדיקת קובץ משותפת לבחירה מהדפדפן ול-Drag & Drop (שלב E) — אותה ולידציה
  // בדיוק כמו קודם, רק מופרדת כדי לשרת את שני הנתיבים בלי כפילות.
  function validateSketchFile(file: File): string | null {
    if (!file.type.startsWith('image/')) return strings.errors.hallImageTypeError
    if (file.size > 4 * 1024 * 1024) return strings.errors.hallImage4MB
    return null
  }

  // קורא קובץ שנבחר/נגרר ל-pickedSketchFile (פאנל ההעלאה) — עדיין *לא*
  // פותח את עורך החיתוך; זה קורה רק ב-confirmSketchUpload, אחרי שהמשתמש
  // ראה preview + שם/גודל קובץ ולחץ "ניתוח ובניית האולם" (req 1).
  function pickSketchFile(file: File) {
    const err = validateSketchFile(file)
    if (err) {
      setError(err)
      return
    }
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        setPickedSketchFile({ name: file.name, size: file.size, dataUrl: reader.result })
      }
    }
    reader.readAsDataURL(file)
  }

  function onPickSketch(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    pickSketchFile(file)
  }

  // "ניתוח ובניית האולם" בפאנל ההעלאה — סוגר אותו ופותח את עורך החיתוך
  // הקיים (ללא שינוי) עם הקובץ שנבחר. משם הזרימה ממשיכה בדיוק כמו קודם:
  // חיתוך/יישור → אישור → ניתוח AI אוטומטי.
  function confirmSketchUpload() {
    if (!pickedSketchFile) return
    sketchOriginalRef.current = pickedSketchFile.dataUrl
    setSketchEditSrc(pickedSketchFile.dataUrl)
    setSketchUploadOpen(false)
    setPickedSketchFile(null)
  }

  function closeSketchUpload() {
    setSketchUploadOpen(false)
    setPickedSketchFile(null)
  }

  // פתיחת עורך הסקיצה לעריכה חוזרת: מעדיפים את המקור ששמור בזיכרון (איכותי);
  // אם אין (למשל אחרי רענון) — עורכים את הסקיצה השמורה עצמה.
  function editSketch() {
    setSketchEditSrc(sketchOriginalRef.current ?? sketch)
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
    // העלאת סקיצה מפעילה ניתוח AI אוטומטי — "Zero Manual Setup": המשתמש לא
    // אמור להתחיל להוסיף שולחנות ידנית אחרי שהעלה סקיצה.
    void runSketchAnalysis(dataUrl)
  }

  function removeSketch() {
    setSketch(null)
    setSketchTransform(null)
    setSketchSelected(false)
    sketchOriginalRef.current = null
    setDirty(true)
  }

  // טוען תמונה כדי לקרוא את מידותיה המקוריות (פיקסלים) — נחוץ כדי לשמר את
  // יחס-הממדים של הסקיצה בבניית האולם (ראה sketchBuildCanvasSize). כישלון
  // (תמונה פגומה וכו') נופל לברירת מחדל 4:3 סבירה, לא חוסם את הזרימה.
  function loadImageSize(dataUrl: string): Promise<{ w: number; h: number }> {
    return new Promise((resolve) => {
      const img = new Image()
      img.onload = () => resolve({ w: img.naturalWidth || 4, h: img.naturalHeight || 3 })
      img.onerror = () => resolve({ w: 4, h: 3 })
      img.src = dataUrl
    })
  }

  // שולח את הסקיצה ל-AI Vision (שרת) ומקבל רשימת אלמנטים מוצעים לבדיקה.
  // כשל לא חוסם כלום — הכלים הידניים הרגילים תמיד זמינים (Fallback ידני, שלב 17).
  async function runSketchAnalysis(dataUrl: string) {
    // מגן סינכרוני מפני שליחה כפולה (req 2 בשלב E) — בדיקת ה-state
    // (sketchAnalyzing) לבדה לא מספיקה נגד שתי קריאות באותו tick (לפני
    // שהרינדור הבא מעדכן אותה); ref נבדק ומעודכן מיידית.
    if (sketchAnalyzingRef.current) return
    sketchAnalyzingRef.current = true
    setSketchAnalyzing(true)
    setSketchAnalyzeError('')
    setSketchAnalyzeEmpty(false)
    setSketchReview(null)
    try {
      const [els, imgSize] = await Promise.all([analyzeHallSketch(dataUrl), loadImageSize(dataUrl)])
      sketchImgSizeRef.current = imgSize
      if (els.length === 0) {
        setSketchAnalyzeEmpty(true)
        setSketchAnalyzeError(hallT.sketchReview.emptyHint)
      } else {
        setSketchReview(els)
      }
    } catch (err) {
      setSketchAnalyzeError(err instanceof Error ? err.message : hallT.sketchReview.failedTitle)
    } finally {
      sketchAnalyzingRef.current = false
      setSketchAnalyzing(false)
    }
  }

  // ממיר סוג שזוהה ע"י ה-AI לסוג שולחן, אם רלוונטי.
  const DETECTED_TABLE_TYPES: Partial<Record<DetectedHallElement['type'], TableType>> = {
    round_table: 'round',
    square_table: 'square',
    rectangle_table: 'rectangle',
    knights_table: 'knights',
  }

  // "בניית האולם" — ממיר את מה שה-AI זיהה לאובייקטים חיים על הקנבס.
  //
  // ── הסקיצה היא מקור האמת לפריסה ────────────────────────────────────────
  // ההמרה היא similarity transform טהור: קנה-מידה אחיד אחד (canvas) + הזזה
  // אחת (origin), זהים לכל האובייקטים **וגם לרקע הסקיצה עצמו**. לכן המיקום,
  // הגודל, יחס-הממדים, הסיבוב והמרווחים בין האובייקטים נשמרים בדיוק כפי
  // שזוהו — וה-overlay בין הרקע לאובייקטים מדויק מעצם הבנייה.
  //
  // במפורש אין כאן: density preset, גודל ברירת-מחדל לפי סוג שולחן, ממוצע,
  // clamp פר-ציר, auto-layout, grid, מרווח אוטומטי או פתרון-התנגשויות. אלה
  // בדיוק הדברים שקודם החזירו את הגיאומטריה של VEYA במקום זו של הסקיצה
  // (שולחן אנכי היה מתנפח לרוחב ומתקצר לגובה, ולכן שורות "נדחסו").
  //
  // הממופה לא ל-worldSize (זה מעגלי — worldSize נגזר מהאובייקטים הקיימים,
  // שלפני הבנייה כמעט תמיד ריקים); worldSize גדל אחר-כך סביב התוצאה.
  function applySketchReview(items: DetectedHallElement[], mode: SketchBuildMode = 'add') {
    const imgSize = sketchImgSizeRef.current ?? { w: 4, h: 3 }
    // קנבס הסקיצה: יחס-הממדים של התמונה, בזום גלובלי קבוע.
    const canvas = sketchWorldCanvas(imgSize.w, imgSize.h, SKETCH_WORLD_LONG_EDGE)
    // הכלל היחיד על צורה: **שולחן** עגול/מרובע יוצא ריבוע אמת, כי הוא מצויר עם
    // border-radius:50% על קופסה w×h — קופסה לא-ריבועית הייתה נראית אליפסה.
    // הגודל עדיין נגזר רק מה-bbox שזוהה (ממוצע שני הצירים), בלי שום preset.
    //
    // אלמנטים (רחבת ריקודים/בר/במה) **לא** נעולים לריבוע — הם שומרים על הגודל
    // שזוהה במדויק, וסוג הצורה שלהם מותאם אליו (רחבה רחבה שזוהתה כמלבן תיווצר
    // אליפסה, לא עיגול מכווץ — VEYA תומכת ב-ellipse ומציירת אותה באותו
    // border-radius:50%).
    const inputs: SketchItemInput[] = items.map((it) => {
      const tableType = DETECTED_TABLE_TYPES[it.type]
      return {
        x: it.x,
        y: it.y,
        width: it.width,
        height: it.height,
        rotation: it.rotation ?? 0,
        squareLock: tableType === 'round' || tableType === 'square',
      }
    })
    const { placed, origin } = placeSketchItems(inputs, canvas, SKETCH_WORLD_PAD, SKETCH_MIN_ITEM_PX)

    // מספור: מספר שכתוב בסקיצה עצמה מנצח (it.table_number מ-AI Vision). רק
    // שולחן שאין לו מספר כתוב מקבל מספור מרחבי — שורות מלמעלה למטה, ובכל
    // שורה משמאל לימין — ולא לפי סדר ה-JSON שה-AI החזיר. שולחנות קיימים
    // שומרים על מספרם (isTaken), כי table_number הוא המזהה שלפיו מוזמנים
    // משובצים. כל ההיגיון ב-assignTableNumbers, כדי שיהיה ניתן לבדיקה.
    const tableIdx = items.map((it, i) => (DETECTED_TABLE_TYPES[it.type] ? i : -1)).filter((i) => i >= 0)
    const order = spatialOrder(tableIdx.map((i) => placed[i]), SKETCH_ROW_TOLERANCE)
    const startNum = mode === 'replace' ? 1 : nextTableNumRef.current
    const takenNums = new Set<number>(mode === 'replace' ? [] : tables.map((t) => t.table_number))
    const assigned = assignTableNumbers(
      tableIdx.map((i) => items[i].table_number ?? null),
      order,
      startNum,
      (n) => takenNums.has(n),
    )
    const numberByItemIdx = new Map<number, number>()
    tableIdx.forEach((itemIdx, k) => numberByItemIdx.set(itemIdx, assigned[k]))

    const newTables: TableView[] = []
    const newElements: HallElement[] = []
    items.forEach((it, i) => {
      const r = placed[i]
      const tableType = DETECTED_TABLE_TYPES[it.type]
      if (tableType) {
        newTables.push({
          table_number: numberByItemIdx.get(i) ?? startNum + newTables.length,
          // (הערך אחרי ?? הוא רשת ביטחון בלבד — כל שולחן נמצא ב-numberByItemIdx)
          x: Math.round(r.x),
          y: Math.round(r.y),
          guests: [],
          table_type: tableType,
          capacity: snapCapacity(it.capacity ?? defaultCapacityForType(tableType)),
          rotation: r.rotation,
          width: Math.round(r.w),
          height: Math.round(r.h),
          name: '',
          color: '',
          notes: '',
          locked: false,
          is_reserve: false,
        })
      } else {
        const elType = it.type as HallElementType
        const def = ELEMENT_DEFS[elType]
        // צורה עגולה כברירת מחדל (רחבת ריקודים) נשארת עגולה רק אם ה-bbox שזוהה
        // אכן ~ריבועי; אחרת אליפסה, כדי לא לעוות את הגודל שזוהה.
        const baseShape = def?.shape ?? 'rectangle'
        const isRounded = baseShape === 'circle' || baseShape === 'ellipse'
        const nearSquare = Math.abs(r.w - r.h) <= Math.max(r.w, r.h) * 0.12
        newElements.push({
          id: `${elType}-ai-${Date.now()}-${i}`,
          type: elType,
          x: Math.round(r.x),
          y: Math.round(r.y),
          width: Math.round(r.w),
          height: Math.round(r.h),
          rotation: r.rotation,
          locked: false,
          label: it.label || def?.label || '',
          shape: isRounded ? (nearSquare ? 'circle' : 'ellipse') : baseShape,
          color: '',
        })
      }
    })

    newTables.sort((a, b) => a.table_number - b.table_number)
    // המספר הפנוי הבא לשולחן שיתווסף ידנית — מעל הגבוה שבשימוש בפועל, כי
    // מספרים שנקראו מהסקיצה יכולים "לקפוץ" (למשל 27) ואינם רצף מ-startNum.
    const highest = Math.max(
      startNum - 1,
      ...newTables.map((t) => t.table_number),
      ...(mode === 'replace' ? [] : tables.map((t) => t.table_number)),
    )
    if (mode === 'replace') {
      setTables(newTables)
      setElements(newElements)
    } else {
      setTables((prev) => [...prev, ...newTables])
      setElements((prev) => [...prev, ...newElements])
    }
    nextTableNumRef.current = highest + 1
    // פרופיל הצפיפות ממשיך לשלוט על שולחנות שיתווספו **ידנית** בהמשך. הוא לא
    // נוגע יותר בשולחנות שיובאו מהסקיצה — להם יש width/height משלהם
    // (ראה tableRenderSize).
    const totalTables = (mode === 'replace' ? 0 : tables.length) + newTables.length
    setHallLayout({ density: densityKeyForCount(totalTables), planned_tables: totalTables })
    // הרקע מוצב על אותו origin ואותו canvas שמהם מופו האובייקטים — זה מה
    // שהופך את ה-overlay למדויק. נכתב תמיד (לא ??), אחרת בנייה חוזרת הייתה
    // משאירה את הרקע בקנבס הקודם והתמונה הייתה מוסטת מהאובייקטים.
    setSketchTransform((cur) => ({
      x: origin.x,
      y: origin.y,
      width: canvas.w,
      height: canvas.h,
      rotation: 0,
      opacity: cur?.opacity ?? 0.5,
      locked: false,
      hidden: cur?.hidden ?? false,
    }))
    setSketchReview(null)
    setSelectedTable(null)
    setSelectedEl(null)
    setSketchSelected(false)
    setDirty(true)
    // אישור קצר (שלב E, דרישה 8) — האולם כבר בנוי ב-state למעלה; זה רק
    // מציג "נבנה בהצלחה" עד שלוחצים "פתיחת האולם".
    setSketchBuildResult(items)
  }

  // "בניית האולם" מתוך מסך ה-Review. אם הלוח כבר לא ריק — שואלים קודם אם
  // להחליף את הקיים או להוסיף אליו, כדי שבנייה חוזרת לא תערים שולחנות חדשים
  // על הקודמים בשקט (זה מה שיצר מספור מבולגן וכפילויות).
  function requestSketchBuild(items: DetectedHallElement[]) {
    if (tables.length > 0 || elements.length > 0) {
      setSketchBuildPending(items)
      return
    }
    applySketchReview(items, 'add')
  }

  function resolveSketchBuild(mode: SketchBuildMode) {
    const items = sketchBuildPending
    setSketchBuildPending(null)
    if (items) applySketchReview(items, mode)
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
          width: t.width,
          height: t.height,
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
        const res = await saveHall(payload, seats, elements, sketch ?? '', layoutToSave, reserveSeats, sketchTransform)
        setWarnings(res.warnings)
        setUnassigned(res.unassigned)
        // מנקים dirty רק אם לא נעשה שינוי נוסף בזמן השמירה; אחרת שומרים שוב.
        if (editVersionRef.current === version) {
          setDirty(false)
          setSavedTick(true)
          window.setTimeout(() => setSavedTick(false), 1600)
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : strings.errors.hallAutoSaveFailed)
        // ניסיון חוזר אמיתי גם בלי עריכה נוספת — אחרת "נמשיך לנסות" בהודעה
        // לא היה קורה בפועל (ה-effect מסתמך על saveRetry/dirty כדי לרוץ שוב).
        window.setTimeout(() => setSaveRetry((r) => r + 1), 4000)
      } finally {
        savingRef.current = false
        setSaving(false)
        // אם התווספו שינויים בזמן השמירה (או שדילגנו על גרירה) — מפעילים סבב נוסף.
        if (editVersionRef.current !== version) setSaveRetry((r) => r + 1)
      }
    }, 900)
    return () => window.clearTimeout(timer)
    // saveRetry בכוונה בתלויות — מאלץ בדיקת-שמירה חוזרת אחרי סבב שהסתיים עם שינויים.
  }, [dirty, tables, elements, sketch, seats, hallLayout, reserveSeats, sketchTransform, saveRetry])

  // "הושבה בקליק" — הפעולה המרכזית של המסך. onlyUnassigned=true משבץ רק את
  // מי שאין לו שולחן (אף אחד מהמשובצים לא זז). שני המצבים רצים על **אותו**
  // מנוע בשרת — לא על שני אלגוריתמים שונים שנותנים תשובות שונות.
  async function onOneClickSeating(onlyUnassigned = false) {
    setLoading(true)
    setError('')
    setSeatingReport(null)
    try {
      const res = await generateSeating({
        seats_per_table: seats,
        persist: true,
        reserve_seats: reserveSeats,
        only_unassigned: onlyUnassigned,
      })
      // דוח הבדיקה שרץ בשרת אחרי השיבוץ. אם יש הפרה — לא מציגים את
      // ההושבה כתקינה, ומפרטים בדיוק מה לא הסתדר (דרישה 5).
      setSeatingReport({
        ok: res.hard_ok,
        people: res.total_people,
        tables: res.num_tables,
        violations: res.violations ?? [],
      })
      setCanUndo(res.can_undo ?? false)
      // הסברי "למה שובץ כאן" — מציגים למי שהמערכת זיהתה לו העדפה מההערות.
      setSeatExplain(res.explanations ?? [])
      applyState(await getHall())
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.hallSeatingFailed)
    } finally {
      setLoading(false)
    }
  }

  // "החזרת הסידור הקודם" — Undo ייעודי (דרישה 6). התצלום נשמר בשרת, ולכן
  // הכפתור זמין גם אחרי רענון דף.
  async function onUndoSeating() {
    setUndoing(true)
    setError('')
    try {
      const res = await undoSeating()
      setCanUndo(false)
      setSeatingReport(null)
      setSeatExplain([])
      applyState(await getHall())
      setUndoNote(hallT.undoDone(res.restored_guests))
      window.setTimeout(() => setUndoNote(''), 4000)
    } catch (err) {
      setError(err instanceof Error ? err.message : hallT.undoError)
    } finally {
      setUndoing(false)
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
      setAssignNote(err instanceof Error ? err.message : strings.errors.hallRecommendFailed)
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
      setAssignNote(err instanceof Error ? err.message : strings.errors.hallAssignFailed)
    } finally {
      setAssignBusy(false)
    }
  }

  // מספרי שולחנות המוזכרים באזהרות (למשל זוג "לא לשבת יחד") — לסימון חזותי
  // ישירות על השולחן, לא רק ברשימת האזהרות הכללית.
  const warnTables = useMemo(
    () =>
      new Set(
        warnings
          .map((w) => w.match(/^שולחן (\d+):/)?.[1])
          .filter((n): n is string => !!n)
          .map(Number),
      ),
    [warnings],
  )

  // רשימת "ללא שולחן" ממוינת לפי שם — קל יותר לסרוק ברשימות ארוכות.
  const visibleUnassigned = [...unassigned].sort((a, b) =>
    a.full_name.localeCompare(b.full_name, 'he'),
  )

  // כל המוזמנים באירוע ללשונית "מוזמנים", לפי מצב המיון שנבחר (guestSortMode):
  // - 'status' (ברירת מחדל): קודם כל מי שללא שולחן, אחר כך המשובצים — בכל
  //   קבוצה מיון א'-ב'.
  // - 'name': כולם יחד, מיון א'-ב' בלבד (בלי הפרדה לפי שיבוץ).
  // - 'table': מיון לפי מספר שולחן עולה; מי שללא שולחן בסוף הרשימה, כי אין
  //   להם מיקום טבעי בסדר מספרי.
  // נגזר מ-tables/unassigned בכל רינדור, כך שהרשימה מתעדכנת מיד עם כל
  // שיבוץ/הסרת שיבוץ בלי לוגיקה נוספת.
  const allGuestsSorted = useMemo(() => {
    const assignedEntries = tables.flatMap((t) =>
      t.guests.map((g) => ({ guest: g, tableNumber: t.table_number as number | null })),
    )
    const unassignedEntries = unassigned.map((g) => ({ guest: g, tableNumber: null as number | null }))
    const byName = (a: { guest: HallGuest }, b: { guest: HallGuest }) =>
      a.guest.full_name.localeCompare(b.guest.full_name, 'he')

    if (guestSortMode === 'name') {
      return [...unassignedEntries, ...assignedEntries].sort(byName)
    }
    if (guestSortMode === 'table') {
      return [...unassignedEntries, ...assignedEntries].sort((a, b) => {
        if ((a.tableNumber === null) !== (b.tableNumber === null)) {
          return a.tableNumber === null ? 1 : -1
        }
        if (a.tableNumber !== null && b.tableNumber !== null && a.tableNumber !== b.tableNumber) {
          return a.tableNumber - b.tableNumber
        }
        return byName(a, b)
      })
    }
    // 'status' — ברירת המחדל
    return [...unassignedEntries, ...assignedEntries].sort((a, b) => {
      if ((a.tableNumber === null) !== (b.tableNumber === null)) {
        return a.tableNumber === null ? -1 : 1
      }
      return byName(a, b)
    })
  }, [tables, unassigned, guestSortMode])

  // ---- עוזר הושבה חכם: חישובים נגזרים (טהורים, בלי קריאת רשת) ----
  // כל הפונקציות מ-seatingAdvisor.ts הן O(n) — מחושבות מחדש רק כשמשהו
  // רלוונטי משתנה (useMemo), לא בכל רינדור/כל פיקסל גרירה.
  const allGuestsForFamily = useMemo(
    () => [...tables.flatMap((t) => t.guests), ...unassigned],
    [tables, unassigned],
  )

  // מוזמן לפי id — לבדיקת rsvp_status לפני הושבה ידנית (למטה) ולעוד שימושים
  // שצריכים חיפוש מהיר בלי לסרוק tables/unassigned בכל פעם.
  const guestById = useMemo(
    () => new Map(allGuestsForFamily.map((g) => [g.id, g] as const)),
    [allGuestsForFamily],
  )

  // ---- אזהרה לפני הושבה ידנית של מי שלא "מגיע" (Audit RSVP↔הושבה, 2026-08-19) ----
  // לא חוסמת — רק שואלת, ורק כשהאורח אינו "מגיע". מכסה את כל המסלולים שבהם
  // אפשר להושיב מוזמן ידנית: הקשה על שולחן אחרי בחירת מוזמן (onTableClick),
  // הקשה על מוזמן ברשימה אחרי בחירת שולחן (assignTarget), "שיבוץ מהיר" של
  // מצב יום האירוע (doAssign), ואישור הצעה חכמה (applyMoves). הסרה משולחן
  // (targetTable === null) לעולם לא מוזהרת.
  function needsSeatWarning(guestId: number): boolean {
    return guestById.get(guestId)?.rsvp_status !== 'confirmed'
  }

  function requestSeatGuest(guestId: number, targetTable: number | null) {
    if (targetTable === null || !needsSeatWarning(guestId)) {
      moveGuestToTable(guestId, targetTable)
      return
    }
    setSeatWarning({ guestIds: [guestId], onConfirm: () => moveGuestToTable(guestId, targetTable) })
  }

  function requestDoAssign(guestId: number, tableNumber: number) {
    if (!needsSeatWarning(guestId)) {
      void doAssign(guestId, tableNumber)
      return
    }
    setSeatWarning({ guestIds: [guestId], onConfirm: () => void doAssign(guestId, tableNumber) })
  }

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
    () =>
      computeSuggestions(
        tables,
        familyGroups,
        splitGroups,
        childWarnings,
        togetherPairs,
        forbiddenPairs,
      ),
    [tables, familyGroups, splitGroups, childWarnings, togetherPairs, forbiddenPairs],
  )
  // תובנות לשולחן שה-Bottom Sheet שלו פתוח — משפחות, קבוצות, ובעיות פתוחות.
  const sheetInsight = useMemo(() => {
    const t = sheetTable != null ? tables.find((x) => x.table_number === sheetTable) : null
    return t ? computeTableInsight(t, familyGroups, forbiddenPairs, childWarnings) : null
  }, [sheetTable, tables, familyGroups, forbiddenPairs, childWarnings])

  // נקודת-סטטוס צבעונית לכל שולחן (ירוק/צהוב/אדום) — מידע בלבד, לא חוסמת
  // כלום. אדום = בעיה קשה (חריגת קיבולת/זוג אסור/ילד בלי מבוגר מהמשפחה),
  // צהוב = יש המלצה/אזהרה רכה (משפחה או קבוצה מפוצלת וכו'), ירוק = תקין.
  // ממוזער (useMemo): בלי זה זה נבנה מחדש בכל רינדור — כולל כל 20 שניות
  // מבדיקת "מחובר לשרת" ב-App.tsx — למרות שהחישובים הסמוכים (smartWarnings
  // וכו') כבר ממוזערים.
  const tableStatus = useMemo(() => {
    const redFromSmart = new Set(
      smartWarnings.filter((w) => w.severity === 'red').flatMap((w) => w.tableNumbers),
    )
    const yellowFromSmart = new Set(
      smartWarnings.filter((w) => w.severity === 'yellow').flatMap((w) => w.tableNumbers),
    )
    const status = new Map<number, 'red' | 'yellow' | 'green'>()
    for (const t of tables) {
      const used = t.guests.reduce((s, g) => s + g.seats, 0)
      const isRed = used > t.capacity || warnTables.has(t.table_number) || redFromSmart.has(t.table_number)
      const isYellow = !isRed && yellowFromSmart.has(t.table_number)
      status.set(t.table_number, isRed ? 'red' : isYellow ? 'yellow' : 'green')
    }
    return status
  }, [tables, smartWarnings, warnTables])

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

  // הערה על מה שהיה כאן: עד 2026-08 היה כאן `onSmartFill` — מנוע מילוי
  // עצמאי בצד הלקוח (Best-Fit Decreasing ב-seatingAdvisor.ts). הוא לא הכיר
  // העדפות אזור, לא ידע איפה השולחנות מונחים באולם, ולא ראה שולחנות
  // נעולים — ולכן נתן תשובה **שונה** מהמנוע האמיתי לאותה שאלה. שני כפתורי
  // "אוטומטי" עם שתי תוצאות שונות הם בדיוק מה שיוצר חוסר אמון. היום שני
  // המצבים ("הושבה בקליק" ו"השלמת מי שללא שולחן") רצים על אותו מנוע בשרת
  // דרך `onOneClickSeating`, עם הדגל only_unassigned.

  function onConfirmProposal() {
    if (!pendingProposal) return
    const proposal = pendingProposal
    // אם ההצעה מזיזה מוזמן שלא "מגיע" — אותה אזהרה כמו בכל מסלול הושבה
    // ידנית אחר (Audit RSVP↔הושבה, 2026-08-19), לפני שמפעילים את המהלכים.
    const unconfirmedIds = [...new Set(proposal.moves.map((m) => m.guestId))].filter(
      needsSeatWarning,
    )
    if (unconfirmedIds.length > 0) {
      setSeatWarning({
        guestIds: unconfirmedIds,
        onConfirm: () => {
          applyMoves(proposal.moves, proposal.newTables)
          setPendingProposal(null)
        },
      })
      return
    }
    applyMoves(proposal.moves, proposal.newTables)
    setPendingProposal(null)
  }
  function onCancelProposal() {
    setPendingProposal(null)
  }

  // ============================================================
  // ============  חוויית ההושבה (מסך אחד לכל מכשיר)  ===========
  // ============================================================
  // עד 2026-07 היו כאן שתי שכבות: "מובייל" ו"דסקטופ". בפועל השכבה הזו רצה
  // תמיד (הדגל שגידר אותה היה קבוע `true`), והשכבה השנייה הייתה קוד מת
  // שאיש לא ראה — ולכן פיצ'רים שישבו רק בה (סיבוב שולחן, פאנל ההבהרות,
  // הוספת אלמנט "כניסה") היו בלתי נגישים למשתמש. הדסקטופ הישן נמחק, וזו
  // עכשיו השכבה היחידה — היא נראית טוב בטלפון ובמחשב (המיקום ב-CSS).
  // עקרונות: האולם תמיד "נכנס" במלואו למסך (Auto-Fit, בלי גלילה ובלי זום),
  // הקשה על שולחן פותחת Bottom Sheet, והעברת מוזמן נעשית בהקשה (לא בגרירה).
  {
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
          {onNavigate && (
            <button
              className="hm-home-btn"
              onClick={() => onNavigate('dashboard')}
              aria-label="חזרה לתמונת המצב"
              title="תמונת מצב"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M3 10.5 12 3l9 7.5" />
                <path d="M5 9.5V21h14V9.5" />
              </svg>
            </button>
          )}
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
            onClick={centerContent}
            aria-label="מרכז את האולם"
            title="מרכז את האולם"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
              <path d="M12 3v3.5M12 17.5V21M3 12h3.5M17.5 12H21" />
            </svg>
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
          {/* סטטוס שמירה — גלוי כאן רק בזמן פעילות (שומר/שינויים ממתינים/נשמר עכשיו),
              כדי לא להוסיף רעש קבוע כשהכול כבר שמור. הפירוט המלא נשאר בלשונית "כלים". */}
          {(saving || dirty || savedTick) && (
            <span className={`hm-topbar-save ${saving ? 'saving' : ''}`} role="status">
              <HmIcon name="save" size={14} />
              {saving ? 'שומר…' : dirty ? 'שינויים ממתינים' : 'נשמר ✓'}
            </span>
          )}
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
                <p className="hm-search-empty">לא נמצא מוזמן או שולחן כאלה.</p>
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
          {/* שגיאות: עד היום הן נשמרו ל-state אבל לא הוצגו בשום מקום (הן הוצגו
              רק בשכבת הדסקטופ שנמחקה) — כך תקלות שמירה/טעינה נבלעו בשקט. */}
          {error && (
            <div className="hm-error-banner" role="alert">
              <span>{error}</span>
              <button onClick={() => setError('')} aria-label="סגירת ההודעה">
                ×
              </button>
            </div>
          )}
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
              onTouchStart={onCanvasTouchStart}
              onTouchMove={onCanvasTouchMove}
              onTouchEnd={onCanvasTouchEnd}
              onTouchCancel={onCanvasTouchEnd}
            >
              <div
                className="hall-world"
                ref={worldRef}
                onClick={(e) => {
                  // הקשה על רקע המפה מבטלת בחירה — אחרת ידית הסיבוב וסרגל
                  // הפעולות נשארים תלויים על שולחן שהמשתמש כבר לא עוסק בו.
                  // ה-listener יושב כאן (לא על .hm-canvas) כי .hall-world
                  // הוא השכבה שממלאת בפועל את כל שטח התצוגה — לחיצה בכל
                  // מקום נוגעת בה תחילה, ורק שולחן/אלמנט ספציפי עוצר את
                  // הבועה (stopPropagation) לפני שהיא מגיעה לכאן.
                  if (e.target !== e.currentTarget) return
                  if (movedRef.current) return
                  setSelectedTable(null)
                  setSelectedEl(null)
                  setSketchSelected(false)
                }}
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
                {/* שכבת הסקיצה (שלב C): עצמאית לגמרי משולחנות/אלמנטים — הזזה/שינוי-
                    גודל/סיבוב שלה לא נוגעים בהם, ולהפך. hidden מדלג על הרינדור
                    כליל (הצגה/הסתרה תמיד זמינה דרך "רקע האולם" בהגדרות ההושבה,
                    גם כשהשכבה מוסתרת ואי אפשר ללחוץ עליה כאן). */}
                {sketch && !sketchTransform?.hidden && (
                  <div
                    className={`hall-sketch-bg ${sketchSelected ? 'selected' : ''} ${
                      sketchTransform?.locked ? 'locked' : ''
                    }`}
                    style={{
                      backgroundImage: `url(${mediaUrl(sketch)})`,
                      // ללא sketchTransform (אירועים ישנים) — בדיוק ההתנהגות הקודמת:
                      // רקע מלא בגודל worldSize, פינה 0,0, שקיפות מה-CSS (0.42).
                      // עם sketchTransform (בנייה אוטומטית מ-AI, או אחרי גרירה
                      // ידנית) — אותה תיבה בדיוק ששימשה למיפוי האובייקטים (ראה
                      // applySketchReview), כדי שהתמונה תמיד תתיישר עם מה שנבנה
                      // ממנה (שלב 8).
                      left: sketchTransform?.x ?? 0,
                      top: sketchTransform?.y ?? 0,
                      width: sketchTransform?.width ?? worldSize.w,
                      height: sketchTransform?.height ?? worldSize.h,
                      ...(sketchTransform ? { opacity: sketchTransform.opacity } : {}),
                      ...(sketchTransform?.rotation ? { transform: `rotate(${sketchTransform.rotation}deg)` } : {}),
                    }}
                    onPointerDown={onSketchPointerDown}
                    onClick={onSketchClick}
                  >
                    {sketchTransform?.locked && (
                      <span className="element-lock-badge" title="נעולה">
                        🔒
                      </span>
                    )}
                    {sketchSelected && !sketchTransform?.locked && (
                      <>
                        <span
                          className="handle handle-rotate"
                          title="סובב"
                          onPointerDown={onSketchRotatePointerDown}
                        />
                        <span
                          className="handle handle-resize"
                          title="שנה גודל (שומר על יחס-הממדים)"
                          onPointerDown={onSketchResizePointerDown}
                        />
                      </>
                    )}
                  </div>
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
                  const { w, h } = tableRenderSize(t, preset)
                  // קישוטי השולחן (כיסאות/מספר/טבעת) מוקטנים יחד איתו — 1 בדיוק
                  // לשולחן שנוסף ידנית, ולכן אין שינוי במפות קיימות.
                  const tScale = tableUiScale(w, h, tableSize(t.table_type, preset))
                  const color = t.color || TABLE_TYPE_DEFAULT_COLOR[t.table_type]
                  const seatCount = Math.max(t.capacity, used, 1)
                  const pts = seatPositions(t.table_type, seatCount, w, h, 12 * tScale)
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
                      className={`hall-table ${over ? 'over' : ''} ${
                        selected !== null ? 'droppable' : ''
                      } ${selectedTable === t.table_number ? 'selected' : ''}`}
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
                          '--t-s': tScale,
                        } as React.CSSProperties}
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
                          {/* מספר התפוסה הוא הדבר היחיד על השולחן שאומר
                              "יש כאן בעיה". קודם הוא הוצג באפור 11px גם
                              כשהיו 18 אנשים ב-12 מקומות, והחריגה סומנה רק
                              בנקודה בת 10px בפינה. עכשיו הוא עצמו משנה
                              צבע ומשקל. */}
                          <span
                            className={`table-occ${over ? ' table-occ-over' : ''}${
                              !over && used === t.capacity ? ' table-occ-full' : ''
                            }`}
                          >
                            {used}/{t.capacity}
                          </span>
                        </span>
                        {/* ידית סיבוב — זהה לזו של אלמנט הבר, לכל סוגי
                            השולחנות. הכיסאות יושבים בתוך אותו אלמנט מסובב
                            ולכן מסתובבים איתו, בלי חישוב נפרד. מופיעה מיד
                            עם הבחירה — אין יותר גיליון שמכסה אותה. */}
                        {selectedTable === t.table_number && !t.locked && (
                          <span
                            className="handle handle-rotate table-rot"
                            title={hallT.rotationLabel}
                            onPointerDown={(e) =>
                              onTableRotatePointerDown(e, t.table_number)
                            }
                          />
                        )}
                      </div>

                      {/* סרגל פעולות צף — מופיע עם הבחירה, בלי לפתוח חלון.
                          "פרטים" הוא הדרך המפורשת לגיליון המלא (שם/סוג/צבע/
                          רזרבה); סיבוב זמין ישירות דרך הידית שמעל השולחן. */}
                      {selectedTable === t.table_number && (
                        <div
                          className="table-toolbar"
                          onPointerDown={(e) => e.stopPropagation()}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            className="tt-btn"
                            onClick={() => openTableSheet(t.table_number)}
                            title={hallT.tableDetails}
                          >
                            <HmIcon name="edit" size={15} />
                          </button>
                          {!t.locked && (
                            <button
                              className="tt-btn"
                              onClick={() => {
                                duplicateTable(t.table_number)
                              }}
                              title={hallT.duplicateTable}
                            >
                              <HmIcon name="plus" size={15} />
                            </button>
                          )}
                          {!t.locked && (
                            <button
                              className="tt-btn danger"
                              onClick={() => {
                                deleteTable(t.table_number)
                                setSelectedTable(null)
                              }}
                              title={hallT.deleteTable}
                            >
                              🗑
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>

              {/* סרגל הכלים הצף של הסקיצה — כ-sibling של .hall-world (לא בתוכו),
                  כדי שיישאר קריא במקום קבוע במסך גם כשהשכבה מסובבת/מוקטנת/
                  ממוקמת בקצה (ראה הערה ב-CSS: .sketch-toolbar). */}
              {sketch && !sketchTransform?.hidden && sketchSelected && (
                <div className="element-toolbar sketch-toolbar" onPointerDown={(e) => e.stopPropagation()}>
                  <span className="sketch-opacity-row" title="שקיפות">
                    🔅
                    <input
                      type="range"
                      min={0.1}
                      max={1}
                      step={0.05}
                      value={sketchTransform?.opacity ?? 0.42}
                      onChange={(e) => patchSketchTransform({ opacity: Number(e.target.value) })}
                    />
                  </span>
                  <button type="button" title={sketchTransform?.locked ? 'שחרר נעילה' : 'נעל'} onClick={toggleSketchLock}>
                    {sketchTransform?.locked ? '🔓' : '🔒'}
                  </button>
                  <button type="button" title="הסתרה" onClick={toggleSketchHidden}>
                    🙈
                  </button>
                  <button type="button" title="איפוס מיקום/גודל/סיבוב" onClick={resetSketchTransform}>
                    ↺
                  </button>
                  <button
                    type="button"
                    title="הסרת הסקיצה"
                    onClick={() => {
                      removeSketch()
                    }}
                  >
                    🗑
                  </button>
                  <button type="button" title="סגירה" onClick={() => setSketchSelected(false)}>
                    ×
                  </button>
                </div>
              )}

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
                    {/* כניסה — האלמנט היה מוגדר בקוד ומזין את אזור "הכניסה"
                        במנוע ההושבה, אבל לא היה שום כפתור להוסיף אותו. */}
                    <button onClick={() => addElement('entrance')}>
                      <HmIcon name="hall" size={18} /> כניסה
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

          {/* ===== לשונית: מוזמנים (כולם — משובצים וללא שולחן) ===== */}
          {mobileTab === 'guests' && (
            <div className="hm-panel">
              <p className="hm-panel-head">
                {allGuestsSorted.length} {activeEventTerms().guestsLabel} · ללא שולחן: {visibleUnassigned.length}
                {assignTarget !== null
                  ? ` · הקישו על מוזמן ללא שולחן לשיבוץ לשולחן ${assignTarget}`
                  : ''}
              </p>
              <div className="hm-sort-row" role="group" aria-label="מיון רשימת המוזמנים">
                <button
                  type="button"
                  className={`hm-sort-btn ${guestSortMode === 'status' ? 'active' : ''}`}
                  onClick={() => setGuestSortMode('status')}
                >
                  לפי שיבוץ
                </button>
                <button
                  type="button"
                  className={`hm-sort-btn ${guestSortMode === 'name' ? 'active' : ''}`}
                  onClick={() => setGuestSortMode('name')}
                >
                  שם (א-ב)
                </button>
                <button
                  type="button"
                  className={`hm-sort-btn ${guestSortMode === 'table' ? 'active' : ''}`}
                  onClick={() => setGuestSortMode('table')}
                >
                  מספר שולחן
                </button>
              </div>
              {allGuestsSorted.length === 0 ? (
                <p className="hm-empty">עדיין אין {activeEventTerms().guestsLabel} באירוע.</p>
              ) : (
                allGuestsSorted.map(({ guest: g, tableNumber }) => (
                  <button
                    key={g.id}
                    className={`hm-guest-row ${selected === g.id ? 'sel' : ''}`}
                    onClick={() => {
                      if (tableNumber === null && assignTarget !== null) {
                        requestSeatGuest(g.id, assignTarget)
                        setAssignTarget(null)
                        setMobileTab('hall')
                      } else {
                        setSelected(g.id)
                        setMobileTab('hall')
                      }
                    }}
                  >
                    <span className="hm-gr-main">
                      <span className="hm-gr-name">
                        {g.full_name}
                        <span className={`badge ${g.rsvp_status}`}>{RSVP_LABELS[g.rsvp_status]}</span>
                      </span>
                      <span className="hm-gr-sub">
                        {GROUP_LABELS[g.group_type]} · {sideLabel(g.side)}
                        {g.seats > 1 ? ` · ${g.seats} מקומות` : ''}
                      </span>
                    </span>
                    <span className={`hm-gr-cta ${tableNumber === null ? 'hm-gr-cta-empty' : ''}`}>
                      {tableNumber === null ? 'ללא שולחן' : `שולחן ${tableNumber}`}
                    </span>
                  </button>
                ))
              )}
            </div>
          )}

          {/* ===== לשונית: הושבה חכמה ===== */}
          {mobileTab === 'smart' && (
            <div className="hm-panel">
              <p className="assistant-ai-disclosure">
                המלצות המערכת מבוססות AI ונועדו לסיוע בלבד. האחריות לקבלת
                החלטות נשארת בידי המשתמש.
              </p>
              <div className="hm-progress">
                <span className="hm-progress-num">
                  {smartStats.seatedPeople} / {smartStats.totalPeople}
                </span>
                <span className="hm-progress-lbl">
                  {activeEventTerms().guestsLabel} שובצו
                </span>
              </div>
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

              {/* ---- הושבה בקליק: הפעולה המרכזית של המסך (דרישות 1, 5, 6) ---- */}
              <div className="hm-oneclick">
                <button
                  className="hm-primary-btn hm-oneclick-btn"
                  onClick={() => onOneClickSeating(false)}
                  disabled={loading}
                >
                  <HmIcon name="smart" size={18} />{' '}
                  {loading ? hallT.oneClickRunning : hallT.oneClickButton}
                </button>
                <p className="hm-oneclick-hint">{hallT.oneClickHint}</p>

                <button
                  className="hm-ghost-btn"
                  onClick={() => onOneClickSeating(true)}
                  disabled={loading || unassigned.length === 0}
                >
                  {hallT.fillEmptyButton}
                </button>
                <p className="hm-oneclick-hint">{hallT.fillEmptyHint}</p>

                {canUndo && (
                  <>
                    <button
                      className="hm-ghost-btn hm-undo-btn"
                      onClick={onUndoSeating}
                      disabled={undoing}
                    >
                      {undoing ? hallT.undoRunning : hallT.undoButton}
                    </button>
                    <p className="hm-oneclick-hint">{hallT.undoHint}</p>
                  </>
                )}
                {undoNote && <p className="hm-oneclick-done">{undoNote}</p>}
              </div>

              {/* דוח ההרצה האחרונה — הצלחה או התנגשות, אף פעם לא "בוצע" סתמי */}
              {seatingReport && (
                <div className={`hm-seating-report ${seatingReport.ok ? 'ok' : 'conflict'}`}>
                  {seatingReport.ok ? (
                    <>
                      <p className="hm-report-title">{hallT.doneTitle}</p>
                      <p className="hm-report-sub">
                        {hallT.doneSummary(seatingReport.people, seatingReport.tables)}
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="hm-report-title">{hallT.conflictTitle}</p>
                      <p className="hm-report-sub">{hallT.conflictHint}</p>
                      {/* מגבילים את הרשימה: 30 שורות זהות הן רעש, לא מידע.
                          המשתמש צריך להבין *מה* הבעיה, לא לקרוא אותה 30 פעם. */}
                      <ul className="hm-report-list">
                        {seatingReport.violations.slice(0, 6).map((v, i) => (
                          <li key={i}>{v.text}</li>
                        ))}
                      </ul>
                      {seatingReport.violations.length > 6 && (
                        <p className="hm-report-sub">
                          {hallT.conflictMore(seatingReport.violations.length - 6)}
                        </p>
                      )}
                    </>
                  )}
                </div>
              )}

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

              {(warnings.length > 0 || smartWarnings.length > 0) && (
                <div className="hm-warnings">
                  <p className="hm-panel-head">שווה לשים לב</p>
                  {/* אזהרות מהשרת (חריגת קיבולת, זוג "לא לשבת יחד" באותו שולחן) —
                      עד היום הן נטענו אבל לא הוצגו בשום מסך שהמשתמש רואה. */}
                  {warnings.map((w, i) => (
                    <div key={`srv-${i}`} className="hm-warn sev-red">
                      {w}
                    </div>
                  ))}
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
                  למוזמנים של הרגע האחרון.
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
              {/* ---- אילוצים והעדפות מההערות (לולאת ההבהרות) ----
                  הפאנל הזה היה קיים רק בשכבת הדסקטופ שנמחקה, כלומר המשתמש
                  מעולם לא יכול היה לראות אילו אילוצים המערכת זיהתה, ולא לפתור
                  הערה עמומה ("דני" כשיש כמה דנים). כאן הוא חוזר למסך החי. */}
              <div className="hm-tools-group">
                <p className="hm-panel-head">{hallT.constraintsTitle}</p>
                <p className="hm-reserve-desc">{hallT.constraintsHint}</p>
                {analyzeSummary && (
                  <p className="hm-clar-summary">
                    {hallT.constraintsSummary(
                      analyzeSummary.guests_analyzed,
                      analyzeSummary.resolved,
                      analyzeSummary.pending_clarifications,
                    )}
                  </p>
                )}
                <button className="hm-ghost-btn" onClick={onAnalyze} disabled={analyzing}>
                  <HmIcon name="refresh" size={18} />{' '}
                  {analyzing ? hallT.constraintsChecking : hallT.constraintsRecheck}
                </button>

                {clarifications.length > 0
                  ? clarifications.map((c) => (
                      <div className="hm-clar-card" key={c.id}>
                        <p className="hm-clar-q">
                          {hallT.clarificationQuestion(
                            c.source_guest_name,
                            REL_TEXT[c.relation_type],
                            c.target_text,
                          )}
                        </p>
                        <div className="hm-clar-actions">
                          {c.candidates.map((cand) => (
                            <button
                              key={cand.id}
                              className="hm-ghost-btn"
                              onClick={() => onResolve(c.id, cand.id)}
                            >
                              {cand.full_name}
                            </button>
                          ))}
                          <button className="hm-clar-none" onClick={() => onResolve(c.id, null)}>
                            {hallT.clarificationNone}
                          </button>
                        </div>
                      </div>
                    ))
                  : analyzeSummary && (
                      <p className="hm-clar-ok">{hallT.constraintsNonePending}</p>
                    )}
              </div>

              <button
                className="hm-ghost-btn hm-daymode-btn"
                onClick={() => setDayMode(true)}
              >
                <HmIcon name="check" size={18} /> מצב יום האירוע
              </button>
              <button className="hm-ghost-btn" onClick={() => setStartChoiceOpen(true)}>
                <HmIcon name="hall" size={18} /> בניית אולם מחדש
              </button>

              <div className="hm-tools-group">
                <p className="hm-panel-head">רקע האולם (סקיצה)</p>
                {sketch ? (
                  <>
                    <button className="hm-ghost-btn" onClick={editSketch}>
                      עריכת הסקיצה
                    </button>
                    <button className="hm-ghost-btn" onClick={() => setSketchUploadOpen(true)}>
                      החלפת תמונה
                    </button>
                    {/* הצגה/הסתרה תמיד זמינה כאן (בניגוד לנעילה/שקיפות, שנשלטות
                        מהסרגל הצף על הלוח) — כי כשהשכבה מוסתרת אין דרך אחרת
                        להגיע אליה כדי להחזיר אותה. */}
                    <button className="hm-ghost-btn" onClick={toggleSketchHidden}>
                      {sketchTransform?.hidden ? '👁️ הצגת הסקיצה' : '🙈 הסתרת הסקיצה'}
                    </button>
                    <button className="hm-ghost-btn" onClick={removeSketch}>
                      הסרת הסקיצה
                    </button>
                  </>
                ) : (
                  <button className="hm-ghost-btn" onClick={() => setSketchUploadOpen(true)}>
                    העלאת סקיצת אולם
                  </button>
                )}
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
              { key: 'guests', icon: 'guests', label: activeEventTerms().guestsLabel },
              { key: 'smart', icon: 'smart', label: 'הושבה' },
              { key: 'tools', icon: 'tools', label: hallT.settingsTab },
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
                      <p className="hm-empty">אין עדיין {activeEventTerms().guestsLabel} בשולחן הזה.</p>
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

                  {/* תובנות על השולחן — משפחות/קבוצות שיושבות בו, וסימון אם יש
                      בעיה פתוחה (חריגת קיבולת / זוג "לא לשבת יחד" / ילד בלי
                      מבוגר מהמשפחה). היה קיים רק בשכבת הדסקטופ שנמחקה. */}
                  {sheetInsight && (sheetInsight.families.length > 0 || sheetInsight.groups.length > 0 || sheetInsight.hasProblem) && (
                    <div className={`hm-sheet-insight ${sheetInsight.hasProblem ? 'problem' : ''}`}>
                      {sheetInsight.families.length > 0 && (
                        <span>משפחות: {sheetInsight.families.join(' · ')}</span>
                      )}
                      {sheetInsight.groups.length > 0 && (
                        <span>קבוצות: {sheetInsight.groups.join(' · ')}</span>
                      )}
                      {sheetInsight.hasProblem && (
                        <span className="hm-sheet-insight-flag">
                          ⚠ יש בעיה פתוחה בשולחן הזה — ראו "שווה לשים לב" בלשונית ההושבה.
                        </span>
                      )}
                    </div>
                  )}

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
                    {/* גשר חזרה למפה: כשהגיליון נפתח מלשונית "שולחנות" (לא
                        מהקשה על המפה עצמה), עדיין אין שולחן נבחר על המפה.
                        הכפתור סוגר את הגיליון ובוחר את השולחן, כדי שסרגל
                        הפעולות + ידית הסיבוב יופיעו מיד בלי הקשה נוספת. */}
                    {!sheetT.locked && (
                      <button
                        className="hm-ghost-btn"
                        onClick={() => {
                          setSelectedTable(sheetT.table_number)
                          setSheetTable(null)
                          setSheetEdit(false)
                        }}
                      >
                        <HmIcon name="refresh" size={18} /> {hallT.selectOnMap}
                      </button>
                    )}
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
                      placeholder="למשל: שולחן המשפחה"
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
                            // משנים סוג → מנקים override גודל שהגיע מ-AI (אם היה), כדי
                            // שהשולחן יחזור לגודל הרגיל של הסוג החדש (לא ישאר בגודל/צורה
                            // של הסוג הקודם).
                            updateTable(sheetT.table_number, {
                              table_type: tt,
                              capacity: defaultCapacityForType(tt),
                              width: undefined,
                              height: undefined,
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
                      לא ישובץ אוטומטית — שמור למוזמנים של הרגע האחרון.
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
                  ועוד {seatExplain.length - 6} {activeEventTerms().guestsLabel} סודרו לפי ההעדפות שלהם
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
                <h2 className="hm-guide-title">ברוכים הבאים לסידור ההושבה</h2>
                <p className="hm-guide-lead">
                  גוררים שולחנות ואלמנטים בדיוק לאן שרוצים — והכול נשמר לבד.
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
                      מזיזים שולחן לכיוון הצדדים? המפה תתכווץ בעדינות כדי שכל
                      האולם יישאר מולכם.
                    </li>
                    <li>
                      מחזירים שולחנות לכיוון המרכז? המפה תגדל שוב כדי שתוכלו לראות הכול
                      בצורה ברורה ונוחה.
                    </li>
                  </ul>
                  <p className="hm-guide-hint">
                    💡 <b>טיפ קטן:</b> פשוט גררו את השולחנות למקום הרצוי — אנחנו כבר
                    נדאג לגודל המתאים בשבילכם.
                  </p>
                  <p className="hm-guide-reassure">
                    אין צורך בזום, אין גלילות — רק לסדר את האולם כמו שאתם רוצים 😊
                  </p>
                </div>

                <div className="hm-guide-divider">
                  <span>עוד דברים שכדאי לדעת</span>
                </div>

                <div className="hm-guide-step">
                  <span className="hm-guide-emoji" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                      <path d='M12 5.5v13M5.5 12h13' />
                    </svg>
                  </span>
                  <div>
                    <h3>מוסיפים שולחנות ואלמנטים</h3>
                    <p>
                      לוחצים על כפתור ה־➕ בפינה, ובוחרים מה להוסיף: שולחן עגול, שולחן אבירים,
                      בר, רחבת ריקודים או עמדת דיג׳יי.
                    </p>
                  </div>
                </div>

                <div className="hm-guide-step">
                  <span className="hm-guide-emoji" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                      <path d='M8.5 11V5.8a1.6 1.6 0 0 1 3.2 0V11M11.7 10.6V4.9a1.6 1.6 0 0 1 3.2 0v5.7M14.9 10.9V6.6a1.6 1.6 0 0 1 3.1 0v7.6a6 6 0 0 1-6 6h-.9a5.4 5.4 0 0 1-4-1.8l-3-3.4a1.6 1.6 0 0 1 2.3-2.2l2 1.9' />
                    </svg>
                  </span>
                  <div>
                    <h3>מזיזים, מסובבים ומשנים גודל</h3>
                    <p>
                      גוררים כל שולחן או אלמנט למקום שלו. הקשה קצרה בוחרת אותו — ואז מופיעות
                      שתי ידיות: העליונה לסיבוב, והפינתית לשינוי גודל.
                    </p>
                  </div>
                </div>

                <div className="hm-guide-step">
                  <span className="hm-guide-emoji" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                      <path d='M7 4.5h10v7H7zM6 12.5h12M8 12.5v6M16 12.5v6' />
                    </svg>
                  </span>
                  <div>
                    <h3>הושבה בקליק</h3>
                    <p>
                      בלשונית "{activeEventTerms().guestsLabel}" בוחרים מוזמן, ואז מקישים על השולחן שאליו הוא ישב. זהו —
                      הוא משובץ. כך אפשר להעביר כל מוזמן בכמה שניות.
                    </p>
                  </div>
                </div>

                <div className="hm-guide-step">
                  <span className="hm-guide-emoji" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                      <path d='M8.4 4.5 9.7 8l3.5 1.3L9.7 10.6 8.4 14.1 7.1 10.6 3.6 9.3 7.1 8l1.3-3.5ZM16.6 12.4 17.5 15l2.6.9-2.6.9-.9 2.6-.9-2.6-2.6-.9 2.6-.9.9-2.6Z' />
                    </svg>
                  </span>
                  <div>
                    <h3>מילוי אוטומטי חכם</h3>
                    <p>
                      אין כוח לשבץ ידנית? בלשונית "הושבה" יש "מילוי שולחנות אוטומטי" שמסדר את
                      כולם בשבילכם — לפי הקבוצות והבקשות. תמיד אפשר לגרור ולתקן אחר כך.
                    </p>
                  </div>
                </div>

                <div className="hm-guide-step">
                  <span className="hm-guide-emoji" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                      <path d='M3.5 5.5h17v13h-17zM3.8 15.4l4.4-4.2 3.3 3.1 3.4-3.6 5.1 5M15.6 8.9v.2' />
                    </svg>
                  </span>
                  <div>
                    <h3>סקיצת האולם כרקע</h3>
                    <p>
                      יש לכם תמונה או סקיצה של האולם? בלשונית "כלים" אפשר להעלות אותה, ו-VEYA
                      תבנה לבד את סידור השולחנות לפי המבנה האמיתי — פירוט מלא למטה.
                    </p>
                  </div>
                </div>

                <div className="hm-guide-divider">
                  <span>בניית אולם מסקיצה</span>
                </div>

                <div className="hm-guide-sketch">
                  <p className="hm-guide-lead">
                    קיבלתם סקיצה מהאולם? נהדר — פשוט מעלים אותה ו-VEYA כבר תבנה לכם את סידור
                    השולחנות.
                  </p>
                  <p className="hm-guide-sketch-intro">
                    במקום לבנות את האולם ידנית שולחן־שולחן, אפשר להעלות את הסקיצה שקיבלתם
                    מהאולם ולתת ל-VEYA להפוך אותה לאולם דיגיטלי.
                  </p>

                  <div className="hm-guide-sketch-shots">
                    <div className="hm-guide-sketch-shot">
                      <img src="/product/hall-sketch-before.jpg" alt="הסקיצה שהתקבלה מהאולם" loading="lazy" />
                      <span>הסקיצה מהאולם</span>
                    </div>
                    <span className="hm-guide-sketch-arrow" aria-hidden="true">←</span>
                    <div className="hm-guide-sketch-shot">
                      <img src="/product/hall-sketch-after.jpg" alt="אותו אולם אחרי הבנייה ב-VEYA" loading="lazy" />
                      <span>האולם ב-VEYA</span>
                    </div>
                  </div>

                  <h3>איך זה עובד?</h3>
                  <ol className="hm-guide-sketch-steps">
                    <li>
                      <span className="hm-guide-sketch-num">1</span>
                      <div>
                        <h4>מעלים את הסקיצה</h4>
                        <p>העלו צילום, תמונה או קובץ של הסקיצה שקיבלתם מהאולם.</p>
                      </div>
                    </li>
                    <li>
                      <span className="hm-guide-sketch-num">2</span>
                      <div>
                        <h4>VEYA מנתחת את הסקיצה</h4>
                        <p>
                          ה-AI מזהה את השולחנות ואת הפריסה שלהם, ומזהה — כשניתן — גם את מספרי
                          השולחנות שמופיעים בסקיצה.
                        </p>
                      </div>
                    </li>
                    <li>
                      <span className="hm-guide-sketch-num">3</span>
                      <div>
                        <h4>מתקבלת תצוגת בדיקה</h4>
                        <p>לפני שהאולם נבנה, תוכלו לראות מה VEYA זיהתה ולוודא שהפריסה תואמת לסקיצה.</p>
                      </div>
                    </li>
                    <li>
                      <span className="hm-guide-sketch-num">4</span>
                      <div>
                        <h4>האולם נבנה אוטומטית</h4>
                        <p>
                          לאחר האישור, השולחנות והאובייקטים עוברים למפת האולם תוך שמירה על
                          המיקום, הגודל והכיוון שלהם בהתאם לסקיצה.
                        </p>
                      </div>
                    </li>
                    <li>
                      <span className="hm-guide-sketch-num">5</span>
                      <div>
                        <h4>ממשיכים לערוך כרגיל</h4>
                        <p>
                          אחרי שהאולם נבנה אפשר להזיז שולחנות, לשנות פרטים, לבצע סידור הושבה
                          ולנהל אותו כמו כל אולם שנבנה ידנית.
                        </p>
                      </div>
                    </li>
                  </ol>

                  <div className="hm-guide-smart">
                    <h3>מה VEYA יכולה לזהות?</h3>
                    <ul>
                      <li>שולחנות</li>
                      <li>מספרי שולחנות שמופיעים בסקיצה</li>
                      <li>מיקום השולחנות</li>
                      <li>גודל וצורה</li>
                      <li>כיוון השולחן</li>
                      <li>פריסת השולחנות והמרווחים ביניהם</li>
                      <li>אובייקטים נוספים שמופיעים בסקיצה כאשר הם מזוהים</li>
                    </ul>
                  </div>

                  <div className="hm-guide-note">
                    <p>
                      <b>חשוב לדעת:</b> ככל שהסקיצה ברורה ואיכותית יותר, כך קל יותר ל-VEYA
                      לזהות את הפרטים שבה. מומלץ להעלות סקיצה שבה:
                    </p>
                    <ul>
                      <li>השולחנות ברורים</li>
                      <li>מספרי השולחנות קריאים</li>
                      <li>רוב האולם מופיע בתמונה</li>
                      <li>אין חיתוך של אזורים משמעותיים</li>
                    </ul>
                    <p>אם מספר שולחן אינו ברור, VEYA לא תנחש אותו.</p>
                  </div>

                  <div className="hm-guide-note">
                    <p>
                      <b>אם כבר בניתם אולם:</b> אם כבר קיים אולם על הלוח ואתם מעלים סקיצה
                      חדשה, VEYA תציג לכם אפשרויות לפני הבנייה:
                    </p>
                    <ul>
                      <li><b>{hallSketchT.existingReplace}</b> — מחליפה את פריסת האולם הקיימת בתוצאה מהסקיצה.</li>
                      <li><b>{hallSketchT.existingAdd}</b> — מוסיפה את התוצאה לאולם הקיים.</li>
                      <li><b>ביטול</b> — חוזרים לאולם בלי לבצע שינוי.</li>
                    </ul>
                  </div>

                  <p className="hm-guide-hint">
                    💡 <b>טיפ:</b> אם קיבלתם מהאולם סקיצה מוכנה — אין צורך לבנות הכול מחדש
                    ידנית. פשוט מעלים אותה ונותנים ל-VEYA להתחיל משם.
                  </p>

                  <button
                    type="button"
                    className="hm-guide-sketch-cta"
                    onClick={() => {
                      setGuideOpen(false)
                      setSketchUploadOpen(true)
                    }}
                  >
                    יש לכם סקיצה? נסו לבנות ממנה את האולם
                  </button>
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
                      <b>{activeEventTerms().guestsLabel}</b> — מי עוד מחכה למקום.
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
                מתחילים
              </button>
            </div>
          </>
        )}

        {startChoiceOpen && (
          <HallStartChoice
            hasContent={tables.length > 0 || elements.length > 0}
            onBuildNew={() => {
              setStartChoiceOpen(false)
              setWizardOpen(true)
            }}
            onBuildFromSketch={() => {
              setStartChoiceOpen(false)
              setSketchUploadOpen(true)
            }}
            onClose={() => setStartChoiceOpen(false)}
          />
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

        {sketchUploadOpen && (
          <SketchUploadDialog
            picked={pickedSketchFile}
            onPick={pickSketchFile}
            onBrowse={() => sketchInputRef.current?.click()}
            onConfirm={confirmSketchUpload}
            onCancel={closeSketchUpload}
          />
        )}
        <input ref={sketchInputRef} type="file" accept="image/*" hidden onChange={onPickSketch} />

        {sketchEditSrc && (
          <SketchEditor
            src={sketchEditSrc}
            orientation={hallOrientation}
            onCancel={() => setSketchEditSrc(null)}
            onConfirm={onSketchConfirm}
          />
        )}

        {sketchAnalyzing && <SketchAnalyzingOverlay />}

        {!sketchAnalyzing && sketchAnalyzeError && (
          <div className="sk-editor-backdrop" onClick={() => setSketchAnalyzeError('')}>
            <div className="sk-analyzing" role="alertdialog" onClick={(e) => e.stopPropagation()}>
              <h2>{sketchAnalyzeEmpty ? hallSketchT.emptyTitle : hallSketchT.failedTitle}</h2>
              <p>{sketchAnalyzeEmpty ? sketchAnalyzeError : hallSketchT.failedHint}</p>
              {!sketchAnalyzeEmpty && <p className="sk-analyzing-sub">{sketchAnalyzeError}</p>}
              <div className="sk-editor-actions">
                {sketch && /^data:/i.test(sketch) && (
                  <button className="sk-confirm" onClick={() => { setSketchAnalyzeError(''); void runSketchAnalysis(sketch) }}>
                    {hallSketchT.retry}
                  </button>
                )}
                <button className="sk-cancel" onClick={() => setSketchAnalyzeError('')}>
                  {hallSketchT.continueManually}
                </button>
              </div>
            </div>
          </div>
        )}

        {sketchReview && (
          <SketchReviewPanel
            items={sketchReview}
            sketchSrc={sketch}
            onCancel={() => setSketchReview(null)}
            onConfirm={requestSketchBuild}
          />
        )}

        {sketchBuildPending && (
          <>
            <div className="sk-editor-backdrop" onClick={() => setSketchBuildPending(null)} />
            <div className="sk-upload" role="dialog" aria-label={hallSketchT.existingTitle}>
              <div className="sk-editor-head">
                <h2>{hallSketchT.existingTitle}</h2>
                <p>{hallSketchT.existingBody(tables.length)}</p>
                {seatedGuestCount > 0 && (
                  <p className="sk-analyzing-sub">{hallSketchT.existingSeated(seatedGuestCount)}</p>
                )}
              </div>
              <div className="sk-editor-actions">
                <button className="sk-confirm" onClick={() => resolveSketchBuild('replace')}>
                  {hallSketchT.existingReplace}
                </button>
                <button className="sk-confirm sk-secondary" onClick={() => resolveSketchBuild('add')}>
                  {hallSketchT.existingAdd}
                </button>
                <button className="sk-cancel" onClick={() => setSketchBuildPending(null)}>
                  {hallSketchT.uploadCancel}
                </button>
              </div>
            </div>
          </>
        )}

        {sketchBuildResult && (
          <SketchBuildSuccess items={sketchBuildResult} onOpen={() => setSketchBuildResult(null)} />
        )}

        {/* ---- מצב יום האירוע: שיבוץ אורחים של הרגע האחרון, עם המלצה חכמה ---- */}
        {dayMode && (
          <div className="day-mode" role="dialog" aria-label="מצב יום האירוע">
            <div className="day-mode-head">
              <div>
                <h3>מצב יום האירוע</h3>
                <p>שיבוץ מוזמנים של הרגע האחרון — בקליק, עם המלצה חכמה.</p>
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
                <p className="day-mode-empty">כל ה{activeEventTerms().guestsLabel} משובצים.</p>
              ) : (
                [...unassigned]
                  .sort((a, b) => a.full_name.localeCompare(b.full_name, 'he'))
                  .map((g) => (
                    <div key={g.id} className={`dm-guest ${assignGuestId === g.id ? 'open' : ''}`}>
                      <button className="dm-guest-head" onClick={() => openAssign(g.id)}>
                        <span className="dm-guest-name">
                          {g.full_name}
                          {g.seats > 1 && <span className="chip-size">×{g.seats}</span>}
                        </span>
                        <span className="dm-guest-cta">
                          {assignGuestId === g.id ? 'סגירה' : 'שבץ מוזמן'}
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
                                onClick={() => requestDoAssign(g.id, r.table_number)}
                              >
                                <span className="dm-rec-top">
                                  <span className="dm-rec-table">
                                    שולחן {r.table_number}
                                    {r.table_name && ` · ${r.table_name}`}
                                    {r.is_reserve && <span className="dm-rec-reserve">רזרבה</span>}
                                  </span>
                                  <span className="dm-rec-free">{r.free_seats} פנויים</span>
                                </span>
                                {r.reasons.length > 0 && (
                                  <span className="dm-rec-reasons">{r.reasons.join(' · ')}</span>
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

        {/* ---- אזהרת הושבה ידנית של מי שלא "מגיע" (Audit RSVP↔הושבה) ---- */}
        {seatWarning && (() => {
          const names = seatWarning.guestIds
            .map((id) => guestById.get(id)?.full_name)
            .filter((n): n is string => !!n)
          if (names.length === 0) return null
          const isDeclined = seatWarning.guestIds.some(
            (id) => guestById.get(id)?.rsvp_status === 'declined',
          )
          return (
            <ConfirmDialog
              title={hallT.seatWarningTitle(isDeclined)}
              message={
                names.length === 1
                  ? hallT.seatWarningMessageSingle(names[0], isDeclined)
                  : hallT.seatWarningMessageMulti(names)
              }
              confirmLabel={hallT.seatWarningConfirm}
              danger={isDeclined}
              onConfirm={() => {
                seatWarning.onConfirm()
                setSeatWarning(null)
              }}
              onCancel={() => setSeatWarning(null)}
            />
          )
        })()}
      </div>
    )
  }
}

