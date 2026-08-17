/**
 * מתמטיקה טהורה (בלי תלות ב-React/DOM) להמרת האלמנטים שה-AI Vision זיהה
 * בסקיצת אולם — קואורדינטות מנורמלות [0,1] יחסית לתמונה — לקואורדינטות
 * world של מפת האולם ב-HallPage.
 *
 * הופרד מ-HallPage.tsx כדי לאפשר בדיקה אוטומטית (hallSketchGeometry.test.ts)
 * בלי סביבת דפדפן, בדיוק כמו seatingAdvisor.ts.
 *
 * זרימת הקואורדינטות: image (פיקסלים) → normalized [0,1] (מה שה-AI מחזיר,
 * ראה hall_vision.py) → world (מה שהמפה מציגה). "קנבס הבנייה" (ראה
 * sketchBuildCanvasSize) הוא הגשר: תיבה ביחידות-world ששומרת בדיוק על יחס-
 * הממדים של תמונת הסקיצה, כדי שמכפלה פשוטה של הקואורדינטות המנורמלות בגודל
 * הקנבס לא תעוות אותן (contain, לא stretch).
 */

export function clampNum(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v))
}

/**
 * גודל "קנבס בנייה" ששומר על יחס-הממדים המקורי של הסקיצה (imgW×imgH), מכויל
 * כך ששולחן טיפוסי (רוחב-bbox חציוני מתוך tableBboxWidths, כל אחד ב-[0,1])
 * ייצא בערך בגודל roundTableTargetPx — אותו קנה-מידה שמשמש שולחנות שנוספו
 * ידנית (ראה DENSITY_PRESETS ב-HallPage) — כדי שהתוצאה תיראה עקבית עם שאר
 * המערכת, לא ריבוע שרירותי. minLongEdge/maxLongEdge מונעים קנבס זעיר (סקיצה
 * עם שולחנות "גדולים" יחסית לתמונה) או ענק (שולחנות "קטנטנים").
 */
export function sketchBuildCanvasSize(
  tableBboxWidths: number[],
  imgW: number,
  imgH: number,
  roundTableTargetPx: number,
  minLongEdge: number,
  maxLongEdge: number,
): { w: number; h: number } {
  const aspect = imgW > 0 && imgH > 0 ? imgW / imgH : 4 / 3
  const sorted = tableBboxWidths.filter((w) => w > 0.001).sort((a, b) => a - b)
  const medianW = sorted.length ? sorted[Math.floor(sorted.length / 2)] : 0.06
  const longEdge = clampNum(roundTableTargetPx / medianW, minLongEdge, maxLongEdge)
  return aspect >= 1 ? { w: longEdge, h: longEdge / aspect } : { w: longEdge * aspect, h: longEdge }
}

/**
 * מגביל גודל אלמנט שחושב מה-bbox לטווח סביר סביב הגודל הרגיל של VEYA לסוג
 * הזה (basePx) — כדי שזיהוי רועש לא ייצר אובייקט זעיר או ענק, בלי לבטל
 * לגמרי את ההבדל היחסי שה-AI זיהה בין אובייקטים.
 */
export function clampItemSize(rawPx: number, basePx: number, minRatio: number, maxRatio: number): number {
  return clampNum(rawPx, basePx * minRatio, basePx * maxRatio)
}

/**
 * מצמיד את מרכז האובייקט כך שהאובייקט (כולל גודלו) יישאר בתוך הקנבס עם
 * שוליים פנימיים קבועים (margin) — בלי להזיז אובייקטים שכבר בתוך התחום,
 * ובלי להצמיד אף פעם לקצה ממש.
 */
export function clampCenterWithMargin(center: number, halfSize: number, canvasLen: number, margin: number): number {
  const lo = margin + halfSize
  const hi = Math.max(lo, canvasLen - margin - halfSize)
  return clampNum(center, lo, hi)
}

/**
 * גודל שולחן (world units) שנשמר נאמן לצורה שזוהתה בסקיצה — לא לגודל אחיד
 * לכל השולחנות מאותו table_type (ראה tableSize ב-HallPage). עגול/מרובע
 * תמיד יוצאים width===height (אף פעם לא אליפסה, אף פעם לא מלבן) — הממוצע בין
 * ה-bbox הרוחב/גובה שזוהו נלקח כסקלר יחיד ומוגבל לטווח סביר. מלבני/אבירים
 * שומרים על הרוחב והגובה שזוהו בנפרד (יחס-ממדים נשמר), כל אחד מוגבל בנפרד.
 */
export function tableWorldSize(
  shape: 'round' | 'square' | 'rectangle' | 'knights',
  detectedWNorm: number,
  detectedHNorm: number,
  canvasW: number,
  canvasH: number,
  base: { w: number; h: number },
  minRatio: number,
  maxRatio: number,
): { w: number; h: number } {
  const rawW = detectedWNorm * canvasW
  const rawH = detectedHNorm * canvasH
  if (shape === 'round' || shape === 'square') {
    const size = clampItemSize((rawW + rawH) / 2, base.w, minRatio, maxRatio)
    return { w: size, h: size }
  }
  return {
    w: clampItemSize(rawW, base.w, minRatio, maxRatio),
    h: clampItemSize(rawH, base.h, minRatio, maxRatio),
  }
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
