/**
 * בדיקות למתמטיקת "בניית אולם מסקיצה" (hallSketchGeometry.ts) — סקריפט
 * assert-פשוט, בלי framework, בדיוק כמו הבדיקות ב-backend/tests (עובד גם
 * בלי jest/vitest מותקן).
 *
 * הרצה: npm run test:hall-sketch-geometry (ראה package.json)
 *
 * הבדיקה המרכזית כאן היא testSketchImportRegressionLayout: פריסה מלאה
 * (6+6 שולחנות בשתי שורות עם מרווחים לא אחידים, אופקי/אנכי/מרובע/עגול/45°,
 * גדלים שונים) שמוכיחה שההמרה היא similarity transform טהור — כלומר שהסקיצה
 * נשארת מקור האמת: גודל, יחס-ממדים, סיבוב, מיקום והמרווחים בין האובייקטים.
 */
import {
  clampNum,
  orientedAspect,
  placeSketchItems,
  rectOverlapFraction,
  sketchWorldCanvas,
  spatialOrder,
  type SketchItemInput,
} from './hallSketchGeometry'

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

function testSketchWorldCanvasPreservesAspect(): void {
  // רחב מובהק (2:1), לאורך (1:2) וריבועי — הקנבס חייב לשמור על היחס בדיוק,
  // אחרת אובייקטים על ציר אחד "נמתחים" יחסית לציר השני.
  const wide = sketchWorldCanvas(1600, 800, 1900)
  assert(approxEqual(wide.w / wide.h, 2, 0.0001), `יחס לרוחב לא נשמר: ${wide.w}x${wide.h}`)
  assert(approxEqual(wide.w, 1900, 0.0001), 'הצלע הארוכה לרוחב = longEdge')

  const tall = sketchWorldCanvas(800, 1600, 1900)
  assert(approxEqual(tall.w / tall.h, 0.5, 0.0001), `יחס לאורך לא נשמר: ${tall.w}x${tall.h}`)
  assert(approxEqual(tall.h, 1900, 0.0001), 'הצלע הארוכה לאורך = longEdge')

  const square = sketchWorldCanvas(1000, 1000, 1900)
  assert(approxEqual(square.w / square.h, 1, 0.0001), `יחס ריבועי לא נשמר: ${square.w}x${square.h}`)

  // 16:9 ו-4:3 — היחסים המדויקים שהבעלים ביקש לבדוק.
  assert(approxEqual(sketchWorldCanvas(1920, 1080, 1900).w / sketchWorldCanvas(1920, 1080, 1900).h, 16 / 9, 0.0001), '16:9 לא נשמר')
  assert(approxEqual(sketchWorldCanvas(1200, 900, 1900).w / sketchWorldCanvas(1200, 900, 1900).h, 4 / 3, 0.0001), '4:3 לא נשמר')

  // הצלע הארוכה היא בחירת זום בלבד: הכפלתה מכפילה את שני הצירים באותה מידה.
  const a = sketchWorldCanvas(1600, 1000, 1000)
  const b = sketchWorldCanvas(1600, 1000, 2000)
  assert(approxEqual(b.w / a.w, 2, 0.0001) && approxEqual(b.h / a.h, 2, 0.0001), 'longEdge חייב להיות מכפיל אחיד על שני הצירים')

  console.log('✓ sketchWorldCanvas שומר על יחס-הממדים של הסקיצה, ו-longEdge הוא זום אחיד בלבד')
}

// ─── פריסת הרגרסיה: 6+6 שולחנות + כל סוגי הצורות והכיוונים ────────────────
// מרווחים לא אחידים בכוונה, כדי לוודא שאין "יישור" או פיזור אוטומטי.
const ROW_1_X = [0.10, 0.24, 0.36, 0.52, 0.66, 0.82]
const ROW_2_X = [0.12, 0.26, 0.40, 0.54, 0.68, 0.86]
const ROW_1_Y = 0.20
const ROW_2_Y = 0.55

interface FixtureItem extends SketchItemInput {
  label: string
}

function gridFixture(): FixtureItem[] {
  const items: FixtureItem[] = []
  // שורה 1: שולחנות מלבניים אופקיים, בגדלים מעט שונים זה מזה.
  ROW_1_X.forEach((x, i) => {
    items.push({ label: `r1-${i}`, x, y: ROW_1_Y, width: 0.055 + i * 0.004, height: 0.028, rotation: 0 })
  })
  // שורה 2: גדלים אחרים לגמרי — כדי לוודא שההבדל היחסי נשמר.
  ROW_2_X.forEach((x, i) => {
    items.push({ label: `r2-${i}`, x, y: ROW_2_Y, width: 0.048, height: 0.034 + i * 0.002, rotation: 0 })
  })
  return items
}

function fullFixture(): FixtureItem[] {
  return [
    ...gridFixture(),
    { label: 'vertical', x: 0.93, y: 0.35, width: 0.022, height: 0.105, rotation: 0 },
    { label: 'horizontal-long', x: 0.45, y: 0.80, width: 0.150, height: 0.030, rotation: 0 },
    { label: 'rotated-45', x: 0.70, y: 0.80, width: 0.120, height: 0.030, rotation: 45 },
    { label: 'rotated-90', x: 0.84, y: 0.80, width: 0.100, height: 0.026, rotation: 90 },
    // bbox לא-ריבועי בכוונה: squareLock חייב להוציא ריבוע אמת (לא אליפסה).
    { label: 'round', x: 0.10, y: 0.90, width: 0.055, height: 0.048, rotation: 0, squareLock: true },
    { label: 'square', x: 0.22, y: 0.90, width: 0.050, height: 0.050, rotation: 0, squareLock: true },
    // נוגע בקצה השמאלי — נבדוק שההזזה המשותפת מונעת קואורדינטה שלילית.
    { label: 'edge-left', x: 0.012, y: 0.45, width: 0.060, height: 0.030, rotation: 0 },
  ]
}

const CANVAS = sketchWorldCanvas(1600, 1000, 1900)
const PAD = 60
const MIN_PX = 10

function testExactScaleAndAspect(): void {
  const items = fullFixture()
  const { placed } = placeSketchItems(items, CANVAS, PAD, MIN_PX)

  items.forEach((it, i) => {
    const r = placed[i]
    if (it.squareLock) {
      // הכלל היחיד על צורה: עיגול/מרובע יוצאים ריבוע אמת.
      assert(approxEqual(r.w, r.h, 0.0001), `${it.label}: עיגול/מרובע חייב w===h, קיבלנו ${r.w}x${r.h}`)
      return
    }
    // 1. scale מדויק — בלי clamp, בלי preset, בלי גודל ברירת מחדל.
    assert(
      approxEqual(r.w, it.width * CANVAS.w, 0.0001),
      `${it.label}: רוחב לא שווה ל-width*canvasW (${r.w} vs ${it.width * CANVAS.w})`,
    )
    assert(
      approxEqual(r.h, it.height * CANVAS.h, 0.0001),
      `${it.label}: גובה לא שווה ל-height*canvasH (${r.h} vs ${it.height * CANVAS.h})`,
    )
    // 2. יחס-הממדים: אותו יחס כמו ב-bbox, אחרי המרה לפיקסלים.
    const expectedAspect = (it.width * CANVAS.w) / (it.height * CANVAS.h)
    assert(
      approxEqual(r.w / r.h, expectedAspect, 0.0001),
      `${it.label}: יחס-ממדים לא נשמר (${r.w / r.h} vs ${expectedAspect})`,
    )
  })

  // כיוון: אנכי נשאר אנכי, אופקי נשאר אופקי.
  const vertical = placed[items.findIndex((it) => it.label === 'vertical')]
  assert(vertical.h > vertical.w, `שולחן אנכי חייב h>w, קיבלנו ${vertical.w}x${vertical.h}`)
  const horizontal = placed[items.findIndex((it) => it.label === 'horizontal-long')]
  assert(horizontal.w > horizontal.h, `שולחן אופקי חייב w>h, קיבלנו ${horizontal.w}x${horizontal.h}`)

  // גדלים שונים נשארים שונים (אין "האחדה" לגודל אחד).
  const r1First = placed[items.findIndex((it) => it.label === 'r1-0')]
  const r1Last = placed[items.findIndex((it) => it.label === 'r1-5')]
  assert(r1Last.w > r1First.w, 'הבדלי גודל בין שולחנות באותה שורה חייבים להישמר')

  console.log('✓ מיפוי bbox→world: scale מדויק, יחס-ממדים, כיוון והבדלי גודל נשמרים')
}

function testRelativeDistancesPreserved(): void {
  // הלב של הדרישה: אם שני שולחנות רחוקים X בסקיצה, הם רחוקים X*scale בקנבס.
  // נבדק על **כל** הזוגות, בשני הצירים.
  const items = fullFixture()
  const { placed } = placeSketchItems(items, CANVAS, PAD, MIN_PX)
  const centers = placed.map((r) => ({ cx: r.x + r.w / 2, cy: r.y + r.h / 2 }))

  for (let i = 0; i < items.length; i++) {
    for (let j = i + 1; j < items.length; j++) {
      const expectedDx = (items[i].x - items[j].x) * CANVAS.w
      const expectedDy = (items[i].y - items[j].y) * CANVAS.h
      const actualDx = centers[i].cx - centers[j].cx
      const actualDy = centers[i].cy - centers[j].cy
      assert(
        approxEqual(actualDx, expectedDx, 0.0001),
        `מרווח אופקי ${items[i].label}↔${items[j].label} השתנה: ${actualDx} vs ${expectedDx}`,
      )
      assert(
        approxEqual(actualDy, expectedDy, 0.0001),
        `מרווח אנכי ${items[i].label}↔${items[j].label} השתנה: ${actualDy} vs ${expectedDy}`,
      )
    }
  }

  // ובמיוחד: המרווחים הלא-אחידים בשורה 1 נשארים לא-אחידים באותם יחסים.
  const gapsNorm: number[] = []
  const gapsWorld: number[] = []
  for (let i = 1; i < ROW_1_X.length; i++) {
    gapsNorm.push(ROW_1_X[i] - ROW_1_X[i - 1])
    const a = centers[i - 1].cx
    const b = centers[i].cx
    gapsWorld.push(b - a)
  }
  gapsNorm.forEach((g, i) => {
    assert(
      approxEqual(gapsWorld[i] / g, CANVAS.w, 0.001),
      `מרווח לא-אחיד #${i} לא עבר scale אחיד (${gapsWorld[i] / g} vs ${CANVAS.w})`,
    )
  })

  console.log('✓ מרווחים: כל המרחקים בין האובייקטים עברו את אותו scale בדיוק (אין יישור/פיזור אוטומטי)')
}

function testRotationPassedThrough(): void {
  const items = fullFixture()
  const { placed } = placeSketchItems(items, CANVAS, PAD, MIN_PX)
  items.forEach((it, i) => {
    assert(
      placed[i].rotation === (it.rotation ?? 0),
      `${it.label}: סיבוב השתנה (${placed[i].rotation} vs ${it.rotation})`,
    )
  })
  const rotated = placed[items.findIndex((it) => it.label === 'rotated-45')]
  assert(rotated.rotation === 45, 'שולחן ב-45° חייב לשמור על 45')
  const r90 = placed[items.findIndex((it) => it.label === 'rotated-90')]
  assert(r90.rotation === 90, 'שולחן ב-90° חייב לשמור על 90')
  console.log('✓ סיבוב עובר as-is לכל אובייקט (כולל 45° ו-90°), כיוונים שונים לא מאוחדים')
}

function testSketchAndObjectsShareOneFrame(): void {
  // הוכחת ה-overlay: הרקע מוצב על {origin, canvas}, והאובייקטים מופו מאותו
  // origin ואותו canvas. לכן כל אובייקט יושב בתוך מלבן הסקיצה, ואפשר להמיר
  // אותו חזרה לקואורדינטות מנורמלות ולקבל בדיוק את ה-bbox המקורי.
  const items = fullFixture()
  const { placed, origin } = placeSketchItems(items, CANVAS, PAD, MIN_PX)

  const sketchRect = { x: origin.x, y: origin.y, w: CANVAS.w, h: CANVAS.h }
  let maxDeviation = 0
  items.forEach((it, i) => {
    const r = placed[i]
    // המרה חזרה למרחב הסקיצה — בדיוק החישוב שנעשה גם בבדיקת הדפדפן.
    const backX = (r.x + r.w / 2 - sketchRect.x) / sketchRect.w
    const backY = (r.y + r.h / 2 - sketchRect.y) / sketchRect.h
    maxDeviation = Math.max(maxDeviation, Math.abs(backX - it.x), Math.abs(backY - it.y))
  })
  assert(maxDeviation < 1e-9, `המרכזים לא חוזרים בדיוק ל-bbox המקורי: סטייה מקסימלית ${maxDeviation}`)

  // אובייקט שה-bbox שלו כולו בתוך התמונה חייב לצאת כולו בתוך מלבן הסקיצה.
  // (bbox יכול לחרוג מהתמונה — למשל 'edge-left' כאן, שמרכזו 0.012 ורוחבו
  // 0.060 ולכן קצהו ב-0.018- — ואז נאמנות לסקיצה דורשת לשמר גם את החריגה.
  // ההוכחה שהמיפוי נכון גם שם היא המרת-חזרה של המרכז, שנבדקה למעלה.)
  let checkedInside = 0
  items.forEach((it, i) => {
    const r = placed[i]
    const insideImage =
      it.x - it.width / 2 >= 0 && it.y - it.height / 2 >= 0 &&
      it.x + it.width / 2 <= 1 && it.y + it.height / 2 <= 1
    if (!insideImage) return
    checkedInside += 1
    assert(
      r.x >= sketchRect.x - 1 && r.y >= sketchRect.y - 1 &&
        r.x + r.w <= sketchRect.x + sketchRect.w + 1 &&
        r.y + r.h <= sketchRect.y + sketchRect.h + 1,
      `${it.label} יוצא מגבולות מלבן הסקיצה`,
    )
  })
  assert(checkedInside === items.length - 1, `ציפינו שכל האובייקטים חוץ מ-edge-left יהיו בתוך התמונה, נבדקו ${checkedInside}`)

  console.log('✓ overlay: הרקע והאובייקטים חולקים origin+scale אחד — המרה חזרה מחזירה את ה-bbox המקורי בדיוק')
}

function testNoNegativeCoordinates(): void {
  // אובייקט שנוגע בקצה השמאלי גורם ל-origin לזוז — כל הסצנה (כולל הרקע) זזה
  // באותה הזזה, כי worldSize ב-HallPage סופר רק מקסימומים ואובייקט בקואורדינטה
  // שלילית היה יוצא מהתיבה ונעלם.
  const items = fullFixture()
  const { placed, origin } = placeSketchItems(items, CANVAS, PAD, MIN_PX)
  placed.forEach((r, i) => {
    assert(r.x >= 0 && r.y >= 0, `${items[i].label} בקואורדינטה שלילית: ${r.x},${r.y}`)
  })
  assert(origin.x >= PAD && origin.y >= PAD, `origin קטן מהריפוד: ${origin.x},${origin.y}`)

  // וההזזה לא שינתה מרחקים (נבדק כבר בכל-הזוגות, כאן רק שההזזה אמיתית).
  const edge = placed[items.findIndex((it) => it.label === 'edge-left')]
  assert(edge.x >= 0, 'האובייקט שנוגע בקצה הוזז פנימה ולא נחתך')

  console.log('✓ אין קואורדינטות שליליות — ההזזה אחידה ומשותפת לרקע ולאובייקטים')
}

function testMinSizeKeepsAspect(): void {
  // רשת ביטחון לזיהוי מנוון: מוחלת אחיד על שני הצירים, כך שהיחס לא משתנה.
  const tiny: SketchItemInput[] = [{ x: 0.5, y: 0.5, width: 0.0004, height: 0.0002 }]
  const { placed } = placeSketchItems(tiny, CANVAS, PAD, 10)
  const r = placed[0]
  assert(Math.min(r.w, r.h) >= 10 - 1e-9, `רצפת הגודל לא הוחלה: ${r.w}x${r.h}`)
  const expectedAspect = (0.0004 * CANVAS.w) / (0.0002 * CANVAS.h)
  assert(approxEqual(r.w / r.h, expectedAspect, 0.0001), `רצפת הגודל שינתה את היחס: ${r.w / r.h} vs ${expectedAspect}`)
  console.log('✓ רצפת גודל מינימלית מוחלת אחיד ולא מעוותת את יחס-הממדים')
}

function testSpatialOrderIsReadingOrder(): void {
  // ה-AI מחזיר את השולחנות בסדר שרירותי; המספור חייב לצאת לפי המיקום:
  // שורות מלמעלה למטה, ובכל שורה משמאל לימין.
  const grid = gridFixture()
  // מערבבים בכוונה (סדר "AI") — כולל שורה 2 לפני שורה 1.
  const scrambled = [grid[9], grid[2], grid[11], grid[0], grid[7], grid[5], grid[3], grid[10], grid[1], grid[8], grid[4], grid[6]]
  const { placed } = placeSketchItems(scrambled, CANVAS, PAD, MIN_PX)
  const order = spatialOrder(placed, 40)

  const labelsInOrder = order.map((i) => scrambled[i].label)
  const expected = [...ROW_1_X.map((_, i) => `r1-${i}`), ...ROW_2_X.map((_, i) => `r2-${i}`)]
  assert(
    labelsInOrder.join(',') === expected.join(','),
    `סדר מרחבי שגוי:\n  קיבלנו: ${labelsInOrder.join(',')}\n  ציפינו: ${expected.join(',')}`,
  )
  console.log('✓ spatialOrder ממספר לפי שורות מלמעלה ובכל שורה משמאל לימין, לא לפי סדר ה-JSON של ה-AI')
}

function testSpatialOrderRowTolerance(): void {
  // שולחנות שלא מיושרים פרפקט (סטייה קטנה בגובה) חייבים להיחשב אותה שורה.
  const rects = [
    { x: 300, y: 105, w: 60, h: 30 },
    { x: 100, y: 100, w: 60, h: 30 },
    { x: 200, y: 112, w: 60, h: 30 },
  ]
  const order = spatialOrder(rects, 40)
  assert(order.join(',') === '1,2,0', `סבילות שורה לא עבדה: ${order.join(',')}`)

  // ופער גדול באמת כן מפצל לשורות.
  const twoRows = [
    { x: 100, y: 400, w: 60, h: 30 },
    { x: 200, y: 100, w: 60, h: 30 },
    { x: 100, y: 100, w: 60, h: 30 },
  ]
  assert(spatialOrder(twoRows, 40).join(',') === '2,1,0', 'פער גדול היה אמור לפצל לשתי שורות')

  console.log('✓ spatialOrder סובל אי-יישור קטן באותה שורה, ומפצל שורות כשהפער אמיתי')
}

function testOrientedAspectPreservesSourceRatios(): void {
  assert(approxEqual(orientedAspect(1920, 1080, 0), 16 / 9, 0.001), `16:9 לא נשמר: ${orientedAspect(1920, 1080, 0)}`)
  assert(approxEqual(orientedAspect(1200, 900, 0), 4 / 3, 0.001), `4:3 לא נשמר: ${orientedAspect(1200, 900, 0)}`)
  assert(approxEqual(orientedAspect(800, 1600, 0), 0.5, 0.001), `סקיצה אנכית לא נשמרה: ${orientedAspect(800, 1600, 0)}`)
  assert(approxEqual(orientedAspect(3500, 1000, 0), 3.5, 0.001), `פנורמה לא נשמרה: ${orientedAspect(3500, 1000, 0)}`)
  assert(approxEqual(orientedAspect(1000, 3500, 0), 1000 / 3500, 0.001), `פנורמה אנכית לא נשמרה: ${orientedAspect(1000, 3500, 0)}`)
  console.log('✓ orientedAspect שומר על יחס-הממדים האמיתי של הסקיצה בכל טווח (רחב/גבוה/פנורמי)')
}

function testOrientedAspectSwapsOnRotation(): void {
  assert(approxEqual(orientedAspect(1600, 900, 0), 1600 / 900, 0.001), 'סיבוב 0° לא אמור להחליף צירים')
  assert(approxEqual(orientedAspect(1600, 900, 180), 1600 / 900, 0.001), 'סיבוב 180° לא אמור להחליף צירים')
  assert(approxEqual(orientedAspect(1600, 900, 90), 900 / 1600, 0.001), `סיבוב 90° לא החליף צירים: ${orientedAspect(1600, 900, 90)}`)
  assert(approxEqual(orientedAspect(1600, 900, 270), 900 / 1600, 0.001), `סיבוב 270° לא החליף צירים: ${orientedAspect(1600, 900, 270)}`)
  assert(approxEqual(orientedAspect(1600, 900, -90), 900 / 1600, 0.001), 'סיבוב שלילי (-90°) לא טופל נכון')
  assert(approxEqual(orientedAspect(1600, 900, 450), 900 / 1600, 0.001), 'סיבוב מעל 360° (450°) לא טופל נכון')
  console.log('✓ orientedAspect מחליף רוחב/גובה נכון בסיבוב 90/270, לא ב-0/180')
}

function testRectOverlapFractionBasics(): void {
  assert(rectOverlapFraction({ x: 0, y: 0, w: 10, h: 10 }, { x: 20, y: 20, w: 10, h: 10 }) === 0, 'מלבנים רחוקים: 0 חפיפה')

  const identical = rectOverlapFraction({ x: 0, y: 0, w: 10, h: 10 }, { x: 0, y: 0, w: 10, h: 10 })
  assert(identical === 1, `מלבנים זהים: חפיפה מלאה, קיבלנו ${identical}`)

  const contained = rectOverlapFraction({ x: 0, y: 0, w: 100, h: 100 }, { x: 40, y: 40, w: 10, h: 10 })
  assert(contained === 1, `מלבן קטן בתוך גדול: אמור להיות 1, קיבלנו ${contained}`)

  const partial = rectOverlapFraction({ x: 0, y: 0, w: 10, h: 10 }, { x: 5, y: 0, w: 10, h: 10 })
  assert(approxEqual(partial, 0.5, 0.001), `חפיפה חלקית שגויה: ${partial}`)

  console.log('✓ rectOverlapFraction')
}

function testRectOverlapFractionIsScaleInvariant(): void {
  const aNorm = { x: 0.1, y: 0.1, w: 0.1, h: 0.08 }
  const bNorm = { x: 0.15, y: 0.12, w: 0.1, h: 0.08 }
  const normFraction = rectOverlapFraction(aNorm, bNorm)

  const sx = 1600
  const sy = 900
  const aWorld = { x: aNorm.x * sx, y: aNorm.y * sy, w: aNorm.w * sx, h: aNorm.h * sy }
  const bWorld = { x: bNorm.x * sx, y: bNorm.y * sy, w: bNorm.w * sx, h: bNorm.h * sy }
  const worldFraction = rectOverlapFraction(aWorld, bWorld)

  assert(approxEqual(normFraction, worldFraction, 0.0001), `לא scale-invariant: ${normFraction} != ${worldFraction}`)
  console.log('✓ rectOverlapFraction זהה גם על קואורדינטות מנורמלות וגם על world (scale-invariant)')
}

function testSketchImportRegressionLayout(): void {
  // בדיקת-על: מריצה את כל הפריסה בכמה יחסי-תמונה שונים ומוודאת שכל התכונות
  // נשמרות בכולם — כי הסקיצה, לא המסך ולא סוג השולחן, קובעת את הגיאומטריה.
  const aspects: [number, number, string][] = [
    [1920, 1080, '16:9'],
    [1600, 1000, '1.6'],
    [1200, 900, '4:3'],
    [2000, 1200, '5:3'],
    [900, 1600, 'אנכי'],
    [3200, 900, 'פנורמי'],
  ]
  const items = fullFixture()
  for (const [iw, ih, label] of aspects) {
    const canvas = sketchWorldCanvas(iw, ih, 1900)
    const { placed, origin } = placeSketchItems(items, canvas, PAD, MIN_PX)

    assert(approxEqual(canvas.w / canvas.h, iw / ih, 0.0001), `${label}: יחס הקנבס לא תואם לתמונה`)

    items.forEach((it, i) => {
      const r = placed[i]
      // המרה חזרה למרחב הסקיצה חייבת להחזיר את ה-bbox המקורי, בכל יחס תמונה.
      const backX = (r.x + r.w / 2 - origin.x) / canvas.w
      const backY = (r.y + r.h / 2 - origin.y) / canvas.h
      assert(approxEqual(backX, it.x, 1e-9), `${label}/${it.label}: מרכז X לא חוזר ל-bbox`)
      assert(approxEqual(backY, it.y, 1e-9), `${label}/${it.label}: מרכז Y לא חוזר ל-bbox`)
      if (it.squareLock) {
        assert(approxEqual(r.w, r.h, 0.0001), `${label}/${it.label}: עיגול/מרובע לא ריבועי`)
      } else {
        const backW = r.w / canvas.w
        const backH = r.h / canvas.h
        assert(approxEqual(backW, it.width, 1e-9), `${label}/${it.label}: רוחב לא חוזר ל-bbox`)
        assert(approxEqual(backH, it.height, 1e-9), `${label}/${it.label}: גובה לא חוזר ל-bbox`)
      }
      assert(r.rotation === (it.rotation ?? 0), `${label}/${it.label}: סיבוב השתנה`)
      assert(r.x >= 0 && r.y >= 0, `${label}/${it.label}: קואורדינטה שלילית`)
    })

    // המספור המרחבי חייב לצאת אותו דבר בכל יחס תמונה.
    const gridCount = ROW_1_X.length + ROW_2_X.length
    const gridPlaced = placed.slice(0, gridCount)
    const tolerance = canvas.h * 0.03
    const order = spatialOrder(gridPlaced, tolerance)
    const expected = [...ROW_1_X.map((_, i) => i), ...ROW_2_X.map((_, i) => ROW_1_X.length + i)]
    assert(order.join(',') === expected.join(','), `${label}: סדר מרחבי שגוי (${order.join(',')})`)
  }
  console.log(`✓ פריסת רגרסיה מלאה (6+6 שולחנות, אופקי/אנכי/45°/90°/מרובע/עגול, מרווחים לא אחידים) נאמנה בכל ${aspects.length} יחסי התמונה`)
}

testClampNum()
testSketchWorldCanvasPreservesAspect()
testExactScaleAndAspect()
testRelativeDistancesPreserved()
testRotationPassedThrough()
testSketchAndObjectsShareOneFrame()
testNoNegativeCoordinates()
testMinSizeKeepsAspect()
testSpatialOrderIsReadingOrder()
testSpatialOrderRowTolerance()
testOrientedAspectPreservesSourceRatios()
testOrientedAspectSwapsOnRotation()
testRectOverlapFractionBasics()
testRectOverlapFractionIsScaleInvariant()
testSketchImportRegressionLayout()
console.log('OK — מתמטיקת בניית אולם מסקיצה תקינה.')
