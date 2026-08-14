/**
 * בדיקות למתמטיקת "בניית אולם מסקיצה" (hallSketchGeometry.ts) — סקריפט
 * assert-פשוט, בלי framework, בדיוק כמו הבדיקות ב-backend/tests (עובד גם
 * בלי jest/vitest מותקן).
 *
 * הרצה: npm run test:hall-sketch-geometry (ראה package.json)
 */
import { clampCenterWithMargin, clampItemSize, clampNum, rectOverlapFraction, sketchBuildCanvasSize } from './hallSketchGeometry'

function assert(cond: boolean, msg: string): void {
  if (!cond) throw new Error(`✗ ${msg}`)
}

function approxEqual(a: number, b: number, eps = 0.01): boolean {
  return Math.abs(a - b) <= eps
}

function testClampNum(): void {
  assert(clampNum(5, 0, 10) === 5, 'clampNum: ערך בתוך הטווח לא משתנה')
  assert(clampNum(-5, 0, 10) === 0, 'clampNum: מוצמד למינימום')
  assert(clampNum(50, 0, 10) === 10, 'clampNum: מוצמד למקסימום')
  console.log('✓ clampNum')
}

function testAspectRatioPreserved(): void {
  // סקיצה לרוחב מובהק (1600x800, יחס 2:1) — הקנבס חייב לשמור על אותו יחס
  // בדיוק, אחרת אובייקטים על ציר אחד "נמתחים" יחסית לציר השני (עיוות).
  const wide = sketchBuildCanvasSize([0.08, 0.09, 0.07], 1600, 800, 122, 900, 3200)
  assert(approxEqual(wide.w / wide.h, 2, 0.001), `יחס-ממדים לרוחב לא נשמר: ${wide.w}x${wide.h}`)

  // סקיצה לאורך (800x1600, יחס 1:2).
  const tall = sketchBuildCanvasSize([0.08, 0.09, 0.07], 800, 1600, 122, 900, 3200)
  assert(approxEqual(tall.w / tall.h, 0.5, 0.001), `יחס-ממדים לאורך לא נשמר: ${tall.w}x${tall.h}`)

  // סקיצה ריבועית (1000x1000).
  const square = sketchBuildCanvasSize([0.08], 1000, 1000, 122, 900, 3200)
  assert(approxEqual(square.w / square.h, 1, 0.001), `יחס-ממדים ריבועי לא נשמר: ${square.w}x${square.h}`)

  console.log('✓ sketchBuildCanvasSize שומר על יחס-הממדים המקורי של הסקיצה (contain, לא stretch)')
}

function testCanvasCalibratedToTablePreset(): void {
  // חציון רוחב-bbox של שולחנות = 0.1 (10% מרוחב התמונה). אם roundTableTargetPx
  // הוא 122 (פרופיל "comfortable"), הקנבס חייב לצאת כזה ששולחן עם רוחב-bbox
  // 0.1 ימופה לכ-122 פיקסל, לא לגודל שרירותי.
  const canvas = sketchBuildCanvasSize([0.1, 0.1, 0.1], 1000, 1000, 122, 200, 5000)
  const mappedTableWidth = 0.1 * canvas.w
  assert(approxEqual(mappedTableWidth, 122, 0.5), `כיול לפי פרופיל הצפיפות שגוי: ${mappedTableWidth} במקום ~122`)
  console.log('✓ sketchBuildCanvasSize מכייל כך ששולחן טיפוסי יוצא בגודל פרופיל הצפיפות')
}

function testCanvasBoundsWhenNoTablesDetected(): void {
  // רק אזורים (בר/רחבה), בלי שולחנות — לא קורס, נופל לברירת מחדל סבירה
  // ונשאר בתוך minLongEdge/maxLongEdge.
  const canvas = sketchBuildCanvasSize([], 1200, 900, 122, 900, 3200)
  assert(canvas.w >= 900 && canvas.w <= 3200, `קנבס בלי שולחנות חורג מהטווח: ${canvas.w}`)
  assert(isFinite(canvas.h) && canvas.h > 0, 'קנבס בלי שולחנות לא תקין')
  console.log('✓ sketchBuildCanvasSize לא קורס כשאין שולחנות שזוהו (רק אזורים)')
}

function testClampItemSizeKeepsRelativeDifference(): void {
  const base = 122
  // שולחן "רגיל" קרוב ל-base — כמעט לא זז.
  const normal = clampItemSize(120, base, 0.45, 2.2)
  assert(approxEqual(normal, 120, 0.01), `שולחן בגודל סביר לא אמור להשתנות: ${normal}`)

  // שולחן ענק ביחס לפרופיל — מוגבל, לא נעלם, ונשאר גדול יותר מהרגיל.
  const huge = clampItemSize(2000, base, 0.45, 2.2)
  assert(approxEqual(huge, base * 2.2, 0.01), `שולחן ענק לא הוגבל נכון: ${huge}`)
  assert(huge > normal, 'שולחן ענק חייב להישאר גדול מהרגיל אחרי ההגבלה (לא לבטל את ההבדל היחסי)')

  // שולחן זעיר ביחס לפרופיל — מוגבל כלפי מעלה, לא נשאר מיקרוסקופי.
  const tiny = clampItemSize(2, base, 0.45, 2.2)
  assert(approxEqual(tiny, base * 0.45, 0.01), `שולחן זעיר לא הוגבל נכון: ${tiny}`)
  assert(tiny < normal, 'שולחן זעיר חייב להישאר קטן מהרגיל אחרי ההגבלה')

  console.log('✓ clampItemSize מגביל קיצוניות אבל שומר על סדר-גודל יחסי')
}

function testClampCenterWithMarginKeepsInteriorUnchanged(): void {
  // אובייקט שכבר בתוך התחום עם שוליים — לא זז בכלל (לא "מכווצים" סתם).
  const centered = clampCenterWithMargin(500, 50, 1000, 44)
  assert(centered === 500, `אובייקט פנימי לא אמור לזוז: ${centered}`)
  console.log('✓ clampCenterWithMargin לא מזיז אובייקטים שכבר בתוך התחום')
}

function testClampCenterWithMarginPushesOffEdge(): void {
  // אובייקט שממורכזו כמעט על x=0 נדחף פנימה כך שהוא (כולל חצי-גודלו) לא
  // חוצה את גבול השוליים — אבל לא "נזרק" למרכז.
  const nearEdge = clampCenterWithMargin(5, 50, 1000, 44)
  assert(nearEdge === 44 + 50, `אובייקט קרוב לקצה לא הוצמד לשוליים הנכונים: ${nearEdge}`)
  assert(nearEdge - 50 >= 44, 'אחרי ההצמדה האובייקט עדיין נוגע בשוליים הפנימיים')

  const nearOtherEdge = clampCenterWithMargin(995, 50, 1000, 44)
  assert(nearOtherEdge === 1000 - 44 - 50, `אובייקט קרוב לקצה השני לא הוצמד נכון: ${nearOtherEdge}`)
  console.log('✓ clampCenterWithMargin דוחף אובייקטים קרובים לקצה פנימה, לא מצמיד לקיר')
}

function testRectOverlapFractionBasics(): void {
  assert(rectOverlapFraction({ x: 0, y: 0, w: 10, h: 10 }, { x: 20, y: 20, w: 10, h: 10 }) === 0, 'מלבנים רחוקים: 0 חפיפה')

  const identical = rectOverlapFraction({ x: 0, y: 0, w: 10, h: 10 }, { x: 0, y: 0, w: 10, h: 10 })
  assert(identical === 1, `מלבנים זהים: חפיפה מלאה, קיבלנו ${identical}`)

  // מלבן קטן שכולו בתוך מלבן גדול — 100% מהקטן.
  const contained = rectOverlapFraction({ x: 0, y: 0, w: 100, h: 100 }, { x: 40, y: 40, w: 10, h: 10 })
  assert(contained === 1, `מלבן קטן בתוך גדול: אמור להיות 1, קיבלנו ${contained}`)

  // חפיפה חלקית: שני מלבנים 10x10 חופפים ב-5x10 → 50 מתוך 100 = 0.5.
  const partial = rectOverlapFraction({ x: 0, y: 0, w: 10, h: 10 }, { x: 5, y: 0, w: 10, h: 10 })
  assert(approxEqual(partial, 0.5, 0.001), `חפיפה חלקית שגויה: ${partial}`)

  console.log('✓ rectOverlapFraction')
}

function testRectOverlapFractionIsScaleInvariant(): void {
  // אותה תצורה יחסית, פעם בקואורדינטות מנורמלות [0,1] ופעם ב-world (סקאלה
  // עצמאית שונה לכל ציר) — התוצאה חייבת להיות זהה (ראה תיעוד הפונקציה).
  const aNorm: import('./hallSketchGeometry').AxisRect = { x: 0.1, y: 0.1, w: 0.1, h: 0.08 }
  const bNorm: import('./hallSketchGeometry').AxisRect = { x: 0.15, y: 0.12, w: 0.1, h: 0.08 }
  const normFraction = rectOverlapFraction(aNorm, bNorm)

  const sx = 1600
  const sy = 900
  const aWorld = { x: aNorm.x * sx, y: aNorm.y * sy, w: aNorm.w * sx, h: aNorm.h * sy }
  const bWorld = { x: bNorm.x * sx, y: bNorm.y * sy, w: bNorm.w * sx, h: bNorm.h * sy }
  const worldFraction = rectOverlapFraction(aWorld, bWorld)

  assert(approxEqual(normFraction, worldFraction, 0.0001), `לא scale-invariant: ${normFraction} != ${worldFraction}`)
  console.log('✓ rectOverlapFraction זהה גם על קואורדינטות מנורמלות וגם על world (scale-invariant)')
}

testClampNum()
testAspectRatioPreserved()
testCanvasCalibratedToTablePreset()
testCanvasBoundsWhenNoTablesDetected()
testClampItemSizeKeepsRelativeDifference()
testClampCenterWithMarginKeepsInteriorUnchanged()
testClampCenterWithMarginPushesOffEdge()
testRectOverlapFractionBasics()
testRectOverlapFractionIsScaleInvariant()
console.log('OK — מתמטיקת בניית אולם מסקיצה תקינה.')
