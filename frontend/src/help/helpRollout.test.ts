/**
 * שחרור מדורג (HELP_CENTER_PLAN.md §19 שלב 9).
 *
 * הרצה: `npm run test:help`.
 *
 * כשהמייסד מכבה את העזרה באדמין ("כבוי" = מתג כיבוי, גובר גם על חריגות), מי
 * שכבר בתוך VEYA עדיין מחזיק ``help_enabled=true`` מהאירוע. ברגע שהשרת עונה
 * 404 באחד מנתיבי העזרה שבהם 404 אומר רק "העזרה סגורה" — הכפתור, החלונית
 * וההדרכה נעלמים, בלי רענון.
 *
 *  1. 404 על הקשר מסך / מדידה / פנייה לצוות → נסגר. החלונית נסגרת.
 *  2. 404 על בדיקת מוזמן (יכול להיות "המוזמן נמחק"), שגיאות אחרות, ו-404
 *     של מסכים שאינם עזרה → לא נסגר.
 *  3. כל מסכי העזרה ונתיבי api.ts שהעזרה משתמשת בהם מזוהים בתבנית.
 *  4. הכפתור והמארח באמת מורידים הכול כשהעזרה נסגרה.
 */
import { reportResponse } from './errorBus'
import { HELP_SCREENS } from './contexts'
import { isHelpOffSignal, isHelpSwitchedOff, openHelp, setHelpEnabled } from './helpStore'

function assert(cond: boolean, msg: string): void {
  if (!cond) throw new Error(`✗ ${msg}`)
}

interface Fs {
  readFileSync(p: string, enc: string): string
}
declare function require(name: 'fs'): Fs
declare const __dirname: string
const fs = require('fs')
const SRC = `${__dirname}/../../src`

function testSignals(): void {
  for (const screen of HELP_SCREENS) {
    assert(isHelpOffSignal({ path: `/help/context/${screen}`, status: 404 }), `מסך ${screen} לא מזוהה`)
  }
  for (const path of ['/help/events', '/help/requests', '/help/requests/mine']) {
    assert(isHelpOffSignal({ path, status: 404 }), `${path} לא מזוהה`)
  }
  const notOff: { path: string; status: number }[] = [
    { path: '/help/guest-check/{id}/{id}', status: 404 },
    { path: '/help/guest-options', status: 404 },
    { path: '/help/context/guests', status: 500 },
    { path: '/help/events', status: 429 },
    { path: '/help/requests', status: 403 },
    { path: '/guests/{id}', status: 404 },
    { path: '/gifts', status: 404 },
  ]
  for (const e of notOff) assert(!isHelpOffSignal(e), `${e.status} ${e.path} נחשב בטעות "העזרה נסגרה"`)
  console.log('✓ רק 404 על הקשר מסך / מדידה / פנייה נחשב "העזרה נסגרה"')
}

function testApiPathsCovered(): void {
  const api = fs.readFileSync(`${SRC}/api.ts`, 'utf8')
  for (const p of ['/help/requests', '/help/requests/mine', '/help/events']) {
    assert(api.includes(`'${p}'`), `api.ts לא קורא ל-${p} — התבנית ב-helpStore לא מעודכנת`)
  }
  assert(api.includes('`/help/context/${'), 'api.ts לא קורא ל-/help/context/{screen}')
  console.log('✓ כל נתיבי העזרה ב-api.ts מכוסים')
}

function testSwitchOff(): void {
  setHelpEnabled(true)
  openHelp()
  reportResponse('GET', 'http://api/help/guest-check/rsvp/12', 404)
  reportResponse('GET', 'http://api/help/context/guests', 200)
  assert(!isHelpSwitchedOff(), 'נסגר בלי סיבה')
  reportResponse('GET', 'http://api/help/context/guests?x=1', 404)
  assert(isHelpSwitchedOff(), 'השרת אמר שהעזרה סגורה — והיא לא נסגרה')
  console.log('✓ תשובת "סגור" מהשרת סוגרת את העזרה מיד')
}

function testUiHides(): void {
  const host = fs.readFileSync(`${SRC}/help/HelpHost.tsx`, 'utf8')
  assert(/const off = useHelpSwitchedOff\(\)[\s\S]*?if \(off\) return null/.test(host), 'הכפתור לא נעלם כשהעזרה נסגרה')
  assert(/if \(!mounted \|\| off\) return null/.test(host), 'החלונית/ההדרכה לא יורדות כשהעזרה נסגרה')
  const store = fs.readFileSync(`${SRC}/help/helpStore.ts`, 'utf8')
  assert(/enabled && !switchedOff/.test(store), '"צריכים עזרה עם זה?" ממשיך להופיע אחרי שהעזרה נסגרה')
  assert(/switchedOff = true\s+set\(false\)/.test(store), 'החלונית לא נסגרת כשהעזרה נסגרה')
  console.log('✓ הכפתור, החלונית, ההדרכה ו"צריכים עזרה עם זה?" יורדים יחד')
}

testSignals()
testApiPathsCovered()
testSwitchOff()
testUiHides()
console.log('OK — שחרור מדורג: כשהעזרה נסגרת באדמין, היא נעלמת גם למי שכבר בפנים.')
