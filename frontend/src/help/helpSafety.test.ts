/**
 * העזרה לעולם לא מבצעת פעולה בשם המשתמש (החלטת המייסד 2026-09-29).
 *
 * הרצה: `npm run test:help`.
 *
 * סורק את כל קוד העזרה (``src/help``, בלי הבדיקות) ונכשל אם מופיע בו משהו
 * שיכול ללחוץ, לשלוח טופס, לדמות הקלדה, או לקרוא לשרת בפעולה שאינה קריאה:
 *  - ``.click()`` / ``requestSubmit`` / ``.submit()`` / ``dispatchEvent`` של
 *    עכבר/מקלדת/טופס — ההדרכה רק מסמנת ומחכה.
 *  - ייבוא מ-api.ts של משהו שאינו ``getHelp…`` (או טיפוס) — העזרה קוראת רק
 *    לשלושת נתיבי ה-GET שלה.
 *  - ``method:`` בבקשה (POST/PUT/PATCH/DELETE) — אין לעזרה בקשות כתיבה.
 *  - ``fetch(`` / ``XMLHttpRequest`` / ``sendBeacon`` ישירים — הכול דרך api.ts.
 */

function assert(cond: boolean, msg: string): void {
  if (!cond) throw new Error(`✗ ${msg}`)
}

interface Fs {
  readFileSync(p: string, enc: string): string
  readdirSync(p: string): string[]
  statSync(p: string): { isDirectory(): boolean }
}
declare function require(name: 'fs'): Fs
declare const __dirname: string

const HELP = `${__dirname}/../../src/help`
const fs = require('fs')

function helpFiles(dir = ''): string[] {
  const out: string[] = []
  for (const name of fs.readdirSync(`${HELP}/${dir}`)) {
    const rel = dir ? `${dir}/${name}` : name
    if (fs.statSync(`${HELP}/${rel}`).isDirectory()) out.push(...helpFiles(rel))
    else if (/\.tsx?$/.test(name) && !/\.test\.ts$/.test(name)) out.push(rel)
  }
  return out
}

/** מסיר הערות, כדי שהסבר בעברית ("העזרה לא לוחצת .click()") לא ייחשב קוד. */
function code(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

const FORBIDDEN: [RegExp, string][] = [
  [/\.click\(\s*\)/, 'לחיצה בשם המשתמש (.click())'],
  [/requestSubmit\s*\(/, 'שליחת טופס (requestSubmit)'],
  [/\.submit\(\s*\)/, 'שליחת טופס (.submit())'],
  [/dispatchEvent\s*\(\s*new\s+(Mouse|Pointer|Keyboard|Submit|Input)Event/, 'דימוי פעולת משתמש (dispatchEvent)'],
  [/method\s*:\s*['"](POST|PUT|PATCH|DELETE)['"]/, 'בקשת כתיבה לשרת'],
  [/\bfetch\s*\(/, 'fetch ישיר (הכול דרך api.ts)'],
  [/XMLHttpRequest|sendBeacon/, 'קריאת רשת ישירה'],
  [/\.value\s*=(?!=)/, 'מילוי שדה בשם המשתמש (.value =)'],
]

function testNoActionOnBehalfOfUser(): void {
  const files = helpFiles()
  assert(files.length > 10, 'לא נמצאו קבצי עזרה לסריקה')
  for (const f of files) {
    const src = code(fs.readFileSync(`${HELP}/${f}`, 'utf8'))
    for (const [re, what] of FORBIDDEN) {
      // בקבצי הידע ``method: 'PATCH'`` הוא "לחכות לאישור השרת על השמירה"
      // (Signal), לא בקשה. שם אין קוד שקורא לשרת בכלל — רק נתונים.
      if (what === 'בקשת כתיבה לשרת' && (f.startsWith('kb/') || f === 'types.ts')) continue
      assert(!re.test(src), `help/${f}: ${what}`)
    }
  }
  // ובקבצי הידע — רק נתונים: אין בהם ייבוא של api.ts בכלל.
  for (const f of files.filter((x) => x.startsWith('kb/'))) {
    assert(!/from\s+['"][./]*\/api['"]/.test(fs.readFileSync(`${HELP}/${f}`, 'utf8')), `help/${f}: קובץ ידע לא מייבא את api.ts`)
  }
  console.log(`✓ ${files.length} קבצי העזרה לא לוחצים, לא ממלאים, לא שולחים ולא כותבים לשרת`)
}

function testOnlyReadOnlyApiImports(): void {
  for (const f of helpFiles()) {
    const src = fs.readFileSync(`${HELP}/${f}`, 'utf8')
    for (const m of src.matchAll(/import\s+(type\s+)?\{([^}]*)\}\s+from\s+['"][./]*\/api['"]/g)) {
      if (m[1]) continue // ייבוא טיפוסים בלבד
      const names = m[2].split(',').map((s) => s.trim().replace(/^type\s+/, '')).filter(Boolean)
      for (const n of names) {
        // שלב 7: הכתיבה היחידה — פנייה לצוות — ורק מקובץ הטופס (נבדק למטה).
        if (n === 'sendHelpSupportRequest' && f === 'ui/TeamRequest.tsx') continue
        // שלב 8: מדידה בלי זהות — רק מהתור ב-analytics.ts (נבדק ב-helpAnalytics.test.ts).
        if (n === 'postHelpEvents' && f === 'analytics.ts') continue
        assert(/^getHelp/.test(n) || /^type\s/.test(n) || /^[A-Z]/.test(n), `help/${f}: מייבא "${n}" מ-api.ts — לעזרה מותר רק getHelp…`)
      }
    }
  }
  console.log('✓ העזרה קוראת לשרת רק דרך נתיבי ה-GET שלה, וכותבת רק פנייה לצוות')
}

/** שלב 7: הפנייה נשלחת רק כשהמשתמש לוחץ "שליחה" בטופס — אף פעם לבד. */
function testSupportRequestOnlyOnUserSubmit(): void {
  const src = code(fs.readFileSync(`${HELP}/ui/TeamRequest.tsx`, 'utf8'))
  const calls = src.match(/sendHelpSupportRequest\(/g) ?? []
  assert(calls.length === 1, `sendHelpSupportRequest נקרא ${calls.length} פעמים — מותר פעם אחת, בתוך submit`)
  const submitAt = src.indexOf('const submit = async (e: FormEvent)')
  const callAt = src.indexOf('sendHelpSupportRequest(')
  const bodyEnd = src.indexOf('\n  }\n', submitAt)
  assert(submitAt > 0 && callAt > submitAt && callAt < bodyEnd, 'השליחה לא נמצאת בתוך submit')
  assert(/<form[^>]*onSubmit=\{submit\}/.test(src), 'submit לא מחובר ל-onSubmit של הטופס')
  assert(/<button type="submit"/.test(src), 'אין כפתור שליחה שהמשתמש לוחץ עליו')
  assert(!/useEffect\([^)]*submit/.test(src), 'submit לא נקרא מתוך useEffect')
  // שום קובץ עזרה אחר לא נוגע בשליחה.
  for (const f of helpFiles()) {
    if (f === 'ui/TeamRequest.tsx') continue
    assert(!/sendHelpSupportRequest/.test(code(fs.readFileSync(`${HELP}/${f}`, 'utf8'))), `help/${f}: נוגע בשליחת פנייה`)
  }
  console.log('✓ פנייה לצוות נשלחת רק מכפתור "שליחה" בטופס — לא אוטומטית ולא מקובץ אחר')
}

testNoActionOnBehalfOfUser()
testOnlyReadOnlyApiImports()
testSupportRequestOnlyOnUserSubmit()
console.log('OK — העזרה לא מבצעת שום פעולה בשם המשתמש.')
