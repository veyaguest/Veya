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
