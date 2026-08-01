/**
 * בדיקות ליבה לחישובי מפת האולם ולעוזר ההושבה — בלי דפדפן, בלי React.
 *
 * הרצה: `node src/seatingAdvisor.test.mjs` מתוך תיקיית frontend.
 * (סקריפט עצמאי עם assert, כמו בדיקות הבקאנד — אין runner בפרויקט.)
 *
 * הבדיקות משכפלות במכוון את הנוסחה של `rotatedBounds` מ-HallPage.tsx: אי
 * אפשר לייבא TSX ל-node בלי שלב בנייה, והנוסחה קצרה ויציבה. אם היא תשתנה
 * שם ולא כאן — הבדיקה תיכשל מול הערכים הצפויים, וזה בדיוק מה שרצינו.
 */
import assert from 'node:assert/strict'

const ROTATION_SNAP_DEG = 5

function normalizeRotation(deg) {
  const snapped = Math.round(deg / ROTATION_SNAP_DEG) * ROTATION_SNAP_DEG
  return ((snapped % 360) + 360) % 360
}

function rotatedBounds(x, y, w, h, deg) {
  const rad = ((deg || 0) * Math.PI) / 180
  const cos = Math.abs(Math.cos(rad))
  const sin = Math.abs(Math.sin(rad))
  const bw = w * cos + h * sin
  const bh = w * sin + h * cos
  const cx = x + w / 2
  const cy = y + h / 2
  return { minX: cx - bw / 2, minY: cy - bh / 2, maxX: cx + bw / 2, maxY: cy + bh / 2 }
}

// ---- normalizeRotation ----------------------------------------------------

// atan2 מחזיר טווח שלילי חלקית; בלי נרמול נשמרו זוויות כמו 90-.
assert.equal(normalizeRotation(-90), 270, 'זווית שלילית חייבת להיות מנורמלת')
assert.equal(normalizeRotation(0), 0)
assert.equal(normalizeRotation(360), 0, '360 שקול ל-0')
assert.equal(normalizeRotation(451), 90, 'מעל סיבוב שלם')
// הצמדה ל-5° — מונעת רעד של מעלה בודדת בגרירה.
assert.equal(normalizeRotation(43), 45)
assert.equal(normalizeRotation(42), 40)
assert.ok(normalizeRotation(-1234) >= 0 && normalizeRotation(-1234) < 360)
console.log('✓ normalizeRotation: נרמול ל-0..359 והצמדה ל-5°')

// ---- rotatedBounds --------------------------------------------------------

// בלי סיבוב — בדיוק תיבת המקור.
{
  const b = rotatedBounds(100, 200, 300, 60, 0)
  assert.equal(b.minX, 100)
  assert.equal(b.minY, 200)
  assert.equal(b.maxX, 400)
  assert.equal(b.maxY, 260)
}

// 90° — הרוחב והגובה מתחלפים, סביב אותו מרכז.
{
  const b = rotatedBounds(100, 200, 300, 60, 90)
  const cx = 100 + 150
  const cy = 200 + 30
  assert.ok(Math.abs(b.maxX - b.minX - 60) < 1e-6, 'רוחב אחרי 90° = גובה המקור')
  assert.ok(Math.abs(b.maxY - b.minY - 300) < 1e-6, 'גובה אחרי 90° = רוחב המקור')
  assert.ok(Math.abs((b.minX + b.maxX) / 2 - cx) < 1e-6, 'המרכז לא זז')
  assert.ok(Math.abs((b.minY + b.maxY) / 2 - cy) < 1e-6, 'המרכז לא זז')
}

// התרחיש שגרם לבאג: שולחן אבירים בפרופיל comfortable (252×58) מסובב 90°.
// החישוב הנאיבי הניח y ∈ [300, 358]; בפועל הוא חורג ~97px לכל כיוון,
// ולכן נחתך ב"התאמה למסך" — ובמסך הזה אין גלילה או זום כדי להגיע אליו.
{
  const naiveMaxY = 300 + 58
  const b = rotatedBounds(400, 300, 252, 58, 90)
  assert.ok(b.minY < 300, 'השולחן המסובב חורג מעל תיבת המקור')
  assert.ok(b.maxY > naiveMaxY, 'השולחן המסובב חורג מתחת לתיבת המקור')
  const overflow = Math.round(300 - b.minY)
  assert.ok(overflow > 90 && overflow < 105, `חריגה צפויה ~97px, התקבל ${overflow}`)
}

// 45° — הריבוע גדל באלכסון (הבדיקה הכי רגישה לשגיאת נוסחה).
{
  const b = rotatedBounds(0, 0, 100, 100, 45)
  const side = b.maxX - b.minX
  assert.ok(Math.abs(side - 100 * Math.SQRT2) < 1e-6, 'ריבוע ב-45° = צלע × √2')
}

// 180° — חוזרים בדיוק לתיבת המקור.
{
  const b = rotatedBounds(10, 20, 80, 40, 180)
  assert.ok(Math.abs(b.minX - 10) < 1e-6)
  assert.ok(Math.abs(b.minY - 20) < 1e-6)
  assert.ok(Math.abs(b.maxX - 90) < 1e-6)
  assert.ok(Math.abs(b.maxY - 60) < 1e-6)
}
console.log('✓ rotatedBounds: תיבת גבולות נכונה בכל זווית, כולל מקרה האבירים')

console.log('OK — חישובי הסיבוב במפת האולם תקינים.')
