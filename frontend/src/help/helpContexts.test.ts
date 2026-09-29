/**
 * ה-context שהשרת נותן לעזרה == מה שבסיס הידע באמת צריך. לא יותר, לא פחות.
 *
 * הרצה: `npm run test:help`.
 *
 * backend/app/help_contexts.json היא הרשימה שהשרת מחזיר לכל מסך ולכל בדיקת
 * מוזמן (app/help_context.py). כאן היא מושווית ל-requiredContexts() — מה
 * שנגזר מהנושאים, ההדרכות ועצי התקלות:
 *  - עובדה עודפת בשרת = מידע שיוצא בלי צורך → נכשל.
 *  - עובדה חסרה בשרת = תשובה שלא תוכל להיות מלאה → נכשל.
 * וגם: אין עובדות מוזמן (guest.*) ב-context של מסך, ואין עובדות שמקורן
 * בדפדפן/משתמש/שגיאה ברשימות של השרת.
 */
import { FACTS } from './facts'
import { HELP_SCREENS, requiredContexts } from './contexts'
import { TREES } from './kb/index'

function assert(cond: boolean, msg: string): void {
  if (!cond) throw new Error(`✗ ${msg}`)
}
function eq<T>(actual: T, expected: T, msg: string): void {
  const a = JSON.stringify(actual)
  const b = JSON.stringify(expected)
  if (a !== b) throw new Error(`✗ ${msg}\n  בשרת:   ${a}\n  נדרש:   ${b}`)
}

interface Fs {
  readFileSync(p: string, enc: string): string
}
declare function require(name: 'fs'): Fs
declare const __dirname: string

// ה-JS המהודר ב-frontend/.tmp-test-help/help/ → השורש שלושה צעדים למעלה.
const SPEC_PATH = `${__dirname}/../../../backend/app/help_contexts.json`
const server = JSON.parse(require('fs').readFileSync(SPEC_PATH, 'utf8')) as {
  screens: Record<string, string[]>
  guest_checks: Record<string, string[]>
}
const needed = requiredContexts()

function testScreensMatchExactly(): void {
  eq(Object.keys(server.screens).sort(), [...HELP_SCREENS].sort(), 'אותם מסכים בשרת ובעזרה')
  for (const screen of HELP_SCREENS) {
    eq([...server.screens[screen]].sort(), [...needed.screens[screen]].sort(), `המסך "${screen}"`)
  }
  console.log(`✓ לכל אחד מ-${HELP_SCREENS.length} המסכים השרת מחזיר בדיוק את העובדות שהעזרה צריכה`)
}

function testGuestChecksMatchExactly(): void {
  eq(Object.keys(server.guest_checks).sort(), Object.keys(needed.guest_checks).sort(), 'אותן בדיקות מוזמן')
  for (const check of Object.keys(needed.guest_checks)) {
    eq([...server.guest_checks[check]].sort(), [...needed.guest_checks[check]].sort(), `בדיקת המוזמן "${check}"`)
  }
  // כל עץ שבודק מוזמן — יש לו בדיקה בשרת; ואין בדיקה בשרת בלי עץ.
  const guestTrees = TREES.filter((t) => t.needsGuest).map((t) => t.id).sort()
  eq(Object.keys(server.guest_checks).sort(), guestTrees, 'בדיקות המוזמן = העצים שבודקים מוזמן')
  console.log(`✓ כל ${guestTrees.length} בדיקות המוזמן מקבלות בדיוק את העובדות שהן בודקות`)
}

function testOnlyServerFactsAndNoGuestFactsOnScreens(): void {
  const defs = FACTS as Record<string, { source: string }>
  for (const [screen, names] of Object.entries(server.screens)) {
    for (const n of names) {
      assert(defs[n]?.source === 'server', `המסך "${screen}": "${n}" אינה עובדה של השרת`)
      assert(!n.startsWith('guest.'), `המסך "${screen}": עובדת מוזמן "${n}" לא שייכת ל-context של מסך`)
    }
  }
  for (const [check, names] of Object.entries(server.guest_checks)) {
    for (const n of names) assert(defs[n]?.source === 'server', `הבדיקה "${check}": "${n}" אינה עובדה של השרת`)
  }
  console.log('✓ השרת מחזיר רק עובדות שרת; עובדות מוזמן רק בבדיקת מוזמן')
}

testScreensMatchExactly()
testGuestChecksMatchExactly()
testOnlyServerFactsAndNoGuestFactsOnScreens()
console.log('OK — ה-context של השרת תואם בדיוק למה שהעזרה צריכה.')
