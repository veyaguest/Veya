/**
 * מתמטיקה טהורה (בלי תלות ב-React/DOM) להמרת האלמנטים שה-AI Vision זיהה
 * בסקיצת אולם — קואורדינטות מנורמלות [0,1] יחסית לתמונה — לקואורדינטות
 * world של מפת האולם ב-HallPage.
 *
 * הופרד מ-HallPage.tsx כדי לאפשר בדיקה אוטומטית (hallSketchGeometry.test.ts)
 * בלי סביבת דפדפן, בדיוק כמו seatingAdvisor.ts.
 *
 * ── עקרון-על: הסקיצה היא מקור האמת לפריסה ──────────────────────────────
 * ההמרה כאן היא **similarity transform טהור**: קנה-מידה אחיד אחד + הזזה אחת,
 * זהה לכל האובייקטים. אין שום נרמול-מחדש פר-אובייקט, אין density preset, אין
 * "גודל ברירת מחדל" לפי סוג שולחן, אין ממוצע, ואין auto-layout מכל סוג
 * (grid/spacing/collision/centering). כל מה שה-AI זיהה — מרכז, רוחב, גובה,
 * סיבוב — נשמר ביחסים מדויקים, ולכן גם המרווחים בין האובייקטים נשמרים.
 *
 * זו בדיוק אותה נוסחה שמסך ה-Review מצייר בה את ה-Bounding Boxes על התמונה
 * (ראה SketchReviewPanel ב-HallPage: left=(x-w/2)*100%, width=w*100%) — ולכן
 * מה שנראה נכון ב-Review יוצא נכון גם על הקנבס.
 *
 * זרימת הקואורדינטות: image (פיקסלים) → normalized [0,1] (מה שה-AI מחזיר,
 * ראה hall_vision.py) → world (מה שהמפה מציגה). "קנבס הסקיצה" (ראה
 * sketchWorldCanvas) הוא הגשר: תיבה ביחידות-world ששומרת בדיוק על יחס-הממדים
 * של תמונת הסקיצה, כך שמכפלה פשוטה של הקואורדינטות המנורמלות בגודל הקנבס לא
 * מעוותת אותן (contain, לא stretch).
 */

export function clampNum(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v))
}

/**
 * תיבת "קנבס הסקיצה" ביחידות world — שומרת בדיוק על יחס-הממדים של התמונה
 * (imgW×imgH), עם longEdge כצלע הארוכה.
 *
 * longEdge הוא **בחירת זום גלובלית בלבד**: כל ערך נותן בדיוק אותה נאמנות
 * גיאומטרית (כי הוא מכפיל אחיד על שני הצירים), הוא רק קובע כמה גדול האולם
 * ביחידות world. במפורש: הוא לא נגזר ממספר השולחנות, מגודל חציוני/ממוצע או
 * מפרופיל צפיפות — כדי שאותה סקיצה תמיד תיתן אותה תוצאה.
 */
export function sketchWorldCanvas(imgW: number, imgH: number, longEdge: number): { w: number; h: number } {
  const aspect = imgW > 0 && imgH > 0 ? imgW / imgH : 4 / 3
  return aspect >= 1 ? { w: longEdge, h: longEdge / aspect } : { w: longEdge * aspect, h: longEdge }
}

/** אובייקט שזוהה, בקואורדינטות מנורמלות [0,1] (מרכז + גודל) — הקלט להמרה. */
export interface SketchItemInput {
  /** מרכז האובייקט, 0-1, יחסית לרוחב התמונה */
  x: number
  /** מרכז האובייקט, 0-1, יחסית לגובה התמונה */
  y: number
  width: number
  height: number
  rotation?: number
  /**
   * צורה שחייבת להישאר ריבועית (עיגול/מרובע) — width===height תמיד, כדי
   * שעיגול לא ייצא אליפסה. הגודל עדיין נגזר **רק** מה-bbox שזוהה (ממוצע שני
   * הצירים), בלי שום preset.
   */
  squareLock?: boolean
}

/** מלבן ממוקם ביחידות world. x,y = פינה שמאלית-עליונה (כמו ב-DOM). */
export interface PlacedRect {
  x: number
  y: number
  w: number
  h: number
  rotation: number
}

export interface PlacedSketch {
  placed: PlacedRect[]
  /** נקודת המקור המשותפת לאובייקטים **ולרקע הסקיצה** — ראה applySketchReview. */
  origin: { x: number; y: number }
}

/**
 * ממפה את כל האובייקטים שזוהו לקואורדינטות world בטרנספורם אחיד אחד.
 *
 * ``origin`` מוחזר כדי שהקורא יציב את **רקע הסקיצה** בדיוק על
 * ``{x: origin.x, y: origin.y, width: canvas.w, height: canvas.h}``. מכיוון
 * שהאובייקטים והרקע חולקים אותו origin ואותו canvas, החפיפה ביניהם מדויקת
 * *מעצם הבנייה* — לא צריך לכייל אותה.
 *
 * ``pad`` הוא ריפוד אחיד (הזזה בלבד, לא שינוי גודל) כדי שהאולם לא ייצמד לפינה
 * 0,0. אם אובייקט חורג לקואורדינטה שלילית (bbox שנוגע בקצה התמונה), כל
 * הסצנה — כולל הרקע — מוזזת באותה הזזה בדיוק, כי ``worldSize`` ב-HallPage
 * סופר רק מקסימומים ואובייקט בקואורדינטה שלילית היה יוצא מחוץ לתיבת העולם.
 *
 * ``minSizePx`` הוא רשת ביטחון לזיהוי מנוון בלבד, ומוחל **אחיד על שני הצירים**
 * (מכפיל אחד) כדי שיחס-הממדים לא ישתנה גם במקרה הזה.
 */
export function placeSketchItems(
  items: SketchItemInput[],
  canvas: { w: number; h: number },
  pad: number,
  minSizePx: number,
): PlacedSketch {
  // שלב 1: גודל + מרכז ביחידות world, בלי הזזה — scale טהור.
  const raw = items.map((it) => {
    let w = it.width * canvas.w
    let h = it.height * canvas.h
    if (it.squareLock) {
      const size = (w + h) / 2
      w = size
      h = size
    }
    // רצפת גודל אחידה: מכפילים את שני הצירים באותו מכפיל, כך שהיחס נשמר.
    const smallest = Math.min(w, h)
    if (smallest > 0 && smallest < minSizePx) {
      const k = minSizePx / smallest
      w *= k
      h *= k
    }
    return { cx: it.x * canvas.w, cy: it.y * canvas.h, w, h, rotation: it.rotation ?? 0 }
  })

  // שלב 2: הזזה אחת ומשותפת לכולם (כולל הרקע) — מבטיחה שאין קואורדינטה שלילית.
  let minX = 0
  let minY = 0
  for (const r of raw) {
    minX = Math.min(minX, r.cx - r.w / 2)
    minY = Math.min(minY, r.cy - r.h / 2)
  }
  const origin = { x: pad + Math.max(0, -minX), y: pad + Math.max(0, -minY) }

  return {
    origin,
    placed: raw.map((r) => ({
      x: origin.x + r.cx - r.w / 2,
      y: origin.y + r.cy - r.h / 2,
      w: r.w,
      h: r.h,
      rotation: r.rotation,
    })),
  }
}

/**
 * סדר מרחבי למספור שולחנות: שורות מלמעלה למטה, ובתוך כל שורה משמאל לימין.
 * מחזיר את האינדקסים בסדר הזה (לא ממספר בעצמו).
 *
 * ``rowTolerance`` — פער אנכי בין מרכזים שעדיין נחשב "אותה שורה", כדי ששולחנות
 * שלא מיושרים פרפקט בסקיצה לא יתפצלו לשורות מדומות.
 *
 * הכיוון (משמאל לימין) תואם לפריסה האוטומטית הקיימת (buildBandLayout, row-major)
 * ולעובדה שהקנבס עצמו מוגדר LTR בקוד — לא ל-RTL של הממשק.
 */
export function spatialOrder(rects: { x: number; y: number; w: number; h: number }[], rowTolerance: number): number[] {
  const withCenters = rects.map((r, i) => ({ i, cx: r.x + r.w / 2, cy: r.y + r.h / 2 }))
  // מקבצים לשורות לפי מרכז אנכי: עוברים מלמעלה למטה ופותחים שורה חדשה רק
  // כשהפער מהשורה הנוכחית גדול מהסבילות.
  const byY = [...withCenters].sort((a, b) => a.cy - b.cy)
  const rows: (typeof byY)[] = []
  let current: typeof byY = []
  let rowAnchor = Number.NaN
  for (const item of byY) {
    if (current.length === 0 || Math.abs(item.cy - rowAnchor) <= rowTolerance) {
      if (current.length === 0) rowAnchor = item.cy
      current.push(item)
    } else {
      rows.push(current)
      current = [item]
      rowAnchor = item.cy
    }
  }
  if (current.length > 0) rows.push(current)
  return rows.flatMap((row) => row.sort((a, b) => a.cx - b.cx).map((item) => item.i))
}

/**
 * קובע את ``table_number`` הסופי לכל שולחן שיובא מסקיצה.
 *
 * ── סדר העדיפויות ──────────────────────────────────────────────────────
 * 1. **מספר שכתוב בסקיצה עצמה מנצח.** אם ה-AI קרא "27" ליד שולחן מסוים, זה
 *    יהיה שולחן 27 במפה — גם אם לפי מיקומו הוא היה מקבל מספר אחר. זה המספר
 *    שהמשתמש כבר עובד לפיו מול האולם/הקייטרינג.
 * 2. **fallback מרחבי** רק לשולחנות שאין להם מספר כתוב: שורות מלמעלה למטה,
 *    ובכל שורה משמאל לימין (``order``), כל אחד מקבל את המספר הפנוי הקטן
 *    ביותר מ-``startNum`` ומעלה.
 *
 * אין כאן שום renumbering: מספר שזוהה לא "מתוקן" לפי מיקום, ומספרים קיימים
 * על הלוח (``isTaken``) לא נוגעים בהם — ``table_number`` הוא המזהה שלפיו
 * מוזמנים משובצים, ושינוי שלו היה מזיז אנשים בין שולחנות.
 *
 * התנגשות (אותו מספר זוהה פעמיים, או שהמספר כבר תפוס על הלוח) לא נפתרת
 * בניחוש: הראשון בסדר המרחבי שומר על המספר שזוהה, והשני נופל ל-fallback.
 * הפונקציה דטרמיניסטית לחלוטין — אותה סקיצה תמיד מניבה אותו מספור, ולכן
 * Rebuild/Replace/Refresh לא משנים מספרים.
 *
 * ``detected`` — מקביל למערך השולחנות; ``order`` — אינדקסים לתוכו בסדר מרחבי.
 */
export function assignTableNumbers(
  detected: (number | null | undefined)[],
  order: number[],
  startNum: number,
  isTaken: (n: number) => boolean,
): number[] {
  const isValid = (n: number | null | undefined): n is number =>
    typeof n === 'number' && Number.isInteger(n) && n >= 1 && n <= 999
  const claimed = new Set<number>()
  const out = new Array<number>(detected.length).fill(0)

  // מעבר 1 — מספרים שזוהו בסקיצה, לפי סדר מרחבי (קובע מי זוכה בהתנגשות).
  for (const i of order) {
    const n = detected[i]
    if (isValid(n) && !claimed.has(n) && !isTaken(n)) {
      claimed.add(n)
      out[i] = n
    }
  }

  // מעבר 2 — כל השאר: המספר הפנוי הבא, בסדר מרחבי.
  let next = Math.max(1, Math.floor(startNum))
  for (const i of order) {
    if (out[i] !== 0) continue
    while (claimed.has(next) || isTaken(next)) next++
    claimed.add(next)
    out[i] = next
  }
  return out
}

/**
 * יחס-הממדים (רוחב/גובה) של תמונה, בהתחשב בסיבוב נוכחי (90/270 מחליפים
 * רוחב וגובה) — קובע את צורת מסגרת החיתוך ב-SketchEditor כברירת מחדל, כדי
 * שהסקיצה כולה תוצג ללא חיתוך (contain, לא cover) בלי תלות ביחס-הממדים של
 * המסך/החלון. נופל בבטחה ל-1 אם הגובה 0 (קלט לא תקין).
 */
export function orientedAspect(naturalW: number, naturalH: number, rotationDeg: number): number {
  const rot = ((rotationDeg % 360) + 360) % 360
  const swap = rot === 90 || rot === 270
  const w = swap ? naturalH : naturalW
  const h = swap ? naturalW : naturalH
  return h > 0 ? w / h : 1
}

export interface AxisRect {
  x: number
  y: number
  w: number
  h: number
}

/**
 * חלק החפיפה (0..1) יחסית לשטח הקטן מבין שני המלבנים. פונקציה זו
 * scale-invariant תחת שינוי-קנה-מידה עצמאי בכל ציר (x/y) בנפרד — ולכן אפשר
 * להריץ אותה גם ישירות על קואורדינטות מנורמלות [0,1] (כמו שמסך ה-Review
 * עושה, לפני שידוע קנבס-הבנייה) וגם על קואורדינטות world, ולקבל אותה תוצאה.
 */
export function rectOverlapFraction(a: AxisRect, b: AxisRect): number {
  const ix = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x))
  const iy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y))
  const inter = ix * iy
  if (inter <= 0) return 0
  const smaller = Math.min(a.w * a.h, b.w * b.h)
  return smaller > 0 ? inter / smaller : 0
}
