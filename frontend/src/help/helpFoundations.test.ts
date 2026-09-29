/**
 * בדיקות יסודות מערכת העזרה (HELP_CENTER_PLAN.md, שלב 1).
 *
 * הרצה: `npm run test:help` מתוך תיקיית frontend. (מהדר את הקוד האמיתי
 * ומריץ ב-node — בלי דפדפן, בלי runner. אותו דפוס של `test:seating-workspace`.)
 *
 * שלושה חלקים:
 *  1. **"אסור להמציא"** — כל יעד ב-`targets.ts` קיים כ-`data-help` בדיוק
 *     בקובץ שלו, אין `data-help` יתום, ואין id כפול בין קבצים. כל scope
 *     רשום בשימוש בפועל. כל מסך ב-`HelpPage` קיים ב-`PAGE_PATHS`.
 *     שינוי עתידי שמסיר/משנה כפתור שההדרכה תלויה בו — ייכשל כאן.
 *  2. `scopes.ts` — סדר "איפה המשתמש נמצא" (חלון > קטע > מסך, ואז אחרון).
 *  3. `errorBus.ts` — נתיבים בלי מזהים, 5 שגיאות אחרונות, הצלחות כתיבה בלבד.
 */
import {
  SCOPES,
  SCOPE_IDS,
  activeScopes,
  pushScope,
  resetScopesForTests,
  subscribeScopes,
} from './scopes'
import type { ScopeId } from './scopes'
import { TARGETS, TARGET_IDS } from './targets'
import type { HelpPage } from './targets'
import {
  onApiEvent,
  pathTemplate,
  recentErrors,
  reportCrash,
  reportErrorMessage,
  reportNetworkFailure,
  reportResponse,
  resetErrorBusForTests,
} from './errorBus'
import type { ApiEvent } from './errorBus'

// ─── כלי עזר ───────────────────────────────────────────────────────────────

function assert(cond: boolean, msg: string): void {
  if (!cond) throw new Error(`✗ ${msg}`)
}

function eq<T>(actual: T, expected: T, msg: string): void {
  const a = JSON.stringify(actual)
  const b = JSON.stringify(expected)
  if (a !== b) throw new Error(`✗ ${msg}\n  התקבל:  ${a}\n  ציפינו: ${b}`)
}

interface Fs {
  readFileSync(p: string, enc: string): string
  readdirSync(p: string): string[]
  statSync(p: string): { isDirectory(): boolean }
}
declare function require(name: 'fs'): Fs
declare const __dirname: string

// ה-JS המהודר יושב ב-frontend/.tmp-test-help/help/ (rootDir = src), ולכן
// המקור נמצא שני צעדים למעלה, ב-src/.
const SRC = `${__dirname}/../../src`
const fs = require('fs')

function readSrc(rel: string): string {
  return fs.readFileSync(`${SRC}/${rel}`, 'utf8')
}

/** כל קבצי ה-ts/tsx תחת src/ (יחסי), בלי תיקיית help/ עצמה ובלי בדיקות. */
function sourceFiles(dir = ''): string[] {
  const out: string[] = []
  for (const name of fs.readdirSync(`${SRC}/${dir}`)) {
    const rel = dir ? `${dir}/${name}` : name
    if (fs.statSync(`${SRC}/${rel}`).isDirectory()) {
      if (rel === 'help') continue
      out.push(...sourceFiles(rel))
    } else if (/\.(tsx?|mts)$/.test(name) && !/\.test\./.test(name)) {
      out.push(rel)
    }
  }
  return out
}

/** צורת id של יעד: ``אזור.שם`` (למשל ``guests.addButton``). */
const TARGET_ID_SHAPE = /^[a-zA-Z]+\.[a-zA-Z][\w.]*$/

/**
 * כל ה-id-ים של ``data-help`` בקובץ: ``data-help="x"`` וגם ``data-help={cond
 * ? 'x' : undefined}``. בתוך ביטוי נספרות רק מחרוזות בצורת id (עם נקודה),
 * כדי שערך ההשוואה בתנאי (``tab.key === 'smart'``) לא ייחשב ליעד.
 */
function dataHelpIds(source: string): string[] {
  const ids: string[] = []
  for (const m of source.matchAll(/data-help="([^"]+)"/g)) ids.push(m[1])
  for (const m of source.matchAll(/data-help=\{([^}]*)\}/g)) {
    for (const lit of m[1].matchAll(/['"]([^'"]+)['"]/g)) {
      if (TARGET_ID_SHAPE.test(lit[1])) ids.push(lit[1])
    }
  }
  return ids
}

// ─── 1. "אסור להמציא" ──────────────────────────────────────────────────────

function testEveryTargetExistsInItsFile(): void {
  for (const id of TARGET_IDS) {
    const t = TARGETS[id]
    let source: string
    try {
      source = readSrc(t.file)
    } catch {
      throw new Error(`✗ היעד "${id}" רשום בקובץ ${t.file}, והקובץ לא קיים`)
    }
    assert(
      dataHelpIds(source).includes(id),
      `היעד "${id}" לא נמצא כ-data-help ב-${t.file} — ה-UI השתנה? עדכנו את help/targets.ts ואת ההדרכות שמשתמשות בו`,
    )
  }
  console.log(`✓ כל ${TARGET_IDS.length} היעדים קיימים בקוד, בקובץ שלהם`)
}

function testNoOrphanOrDuplicateDataHelp(): void {
  const seenIn = new Map<string, string>()
  for (const file of sourceFiles()) {
    const ids = new Set(dataHelpIds(readSrc(file)))
    for (const id of ids) {
      assert(
        (TARGET_IDS as string[]).includes(id),
        `data-help="${id}" ב-${file} לא רשום ב-help/targets.ts (יעד יתום)`,
      )
      const prev = seenIn.get(id)
      assert(
        prev === undefined,
        `data-help="${id}" מופיע גם ב-${prev} וגם ב-${file} — ההדרכה לא תדע לאן להצביע`,
      )
      seenIn.set(id, file)
      assert(
        TARGETS[id as keyof typeof TARGETS].file === file,
        `data-help="${id}" נמצא ב-${file}, אבל רשום ב-targets.ts תחת ${TARGETS[id as keyof typeof TARGETS].file}`,
      )
    }
  }
  console.log('✓ אין data-help יתום, ואין id שמופיע ביותר מקובץ אחד')
}

function testEveryScopeIsUsed(): void {
  const users = sourceFiles()
    .map((f) => ({ f, s: readSrc(f) }))
    .filter(({ s }) => s.includes("from '../help/useHelpScope'") || s.includes("from './help/useHelpScope'"))
  assert(users.length > 0, 'אף רכיב לא משתמש ב-useHelpScope')
  for (const id of SCOPE_IDS) {
    const hit = users.find(({ s }) => s.includes(`'${id}'`))
    assert(!!hit, `ה-scope "${id}" רשום ב-help/scopes.ts, אבל אף רכיב לא מכריז עליו (useHelpScope)`)
  }
  console.log(`✓ כל ${SCOPE_IDS.length} ה-scopes מוכרזים ברכיבים אמיתיים`)
}

function testHelpPagesMatchAppRoutes(): void {
  const app = readSrc('App.tsx')
  const block = /const PAGE_PATHS: Record<Page, string> = \{([\s\S]*?)\n\}/.exec(app)
  assert(!!block, 'לא נמצא PAGE_PATHS ב-App.tsx — מבנה הניווט השתנה')
  const appPages = [...block![1].matchAll(/^\s*(\w+):/gm)].map((m) => m[1]).sort()
  const expected: HelpPage[] = ['dashboard', 'guests', 'messages', 'rsvp', 'hall', 'gifts', 'finance']
  eq(appPages, [...expected].sort(), 'המסכים ב-HelpPage חייבים להתאים ל-PAGE_PATHS')
  for (const id of TARGET_IDS) {
    assert(appPages.includes(TARGETS[id].page), `ליעד "${id}" מסך לא קיים: ${TARGETS[id].page}`)
  }
  console.log('✓ המסכים של העזרה תואמים לניווט האמיתי של האפליקציה')
}

// ─── 2. scopes ─────────────────────────────────────────────────────────────

function testScopeOrder(): void {
  resetScopesForTests()
  // React מריץ effects של ילד לפני ההורה: השלב באשף נרשם לפני המסך.
  const offStep = pushScope('messages.wizard.design')
  const offPage = pushScope('messages')
  eq(activeScopes(), ['messages.wizard.design', 'messages'], 'קטע גובר על מסך גם כשנרשם קודם')

  const offForm = pushScope('guests.addForm')
  eq(
    activeScopes(),
    ['guests.addForm', 'messages.wizard.design', 'messages'],
    'חלון (טופס הוספת מוזמן באשף) גובר על הכול',
  )
  offForm()
  offStep()
  const offStep2 = pushScope('messages.wizard.recipients')
  eq(activeScopes(), ['messages.wizard.recipients', 'messages'], 'מעבר שלב מחליף את הקטע')
  offStep2()
  offPage()
  eq(activeScopes(), [], 'אחרי סגירה לא נשאר כלום')
  console.log('✓ סדר ה-scopes: חלון > קטע > מסך, ובתוך שכבה — האחרון שנפתח')
}

function testScopeDuplicatesAndCleanup(): void {
  resetScopesForTests()
  let calls = 0
  const unsub = subscribeScopes(() => {
    calls++
  })
  const a = pushScope('guests.addForm')
  const b = pushScope('guests.addForm')
  eq(activeScopes(), ['guests.addForm'], 'אותו scope פעמיים — מוצג פעם אחת')
  a()
  eq(activeScopes(), ['guests.addForm'], 'סגירת רישום אחד לא מוחקת את השני')
  b()
  b() // סגירה כפולה — בלי שגיאה ובלי התראה נוספת
  eq(activeScopes(), [], 'שני הרישומים נסגרו')
  eq(calls, 4, 'התראה על כל שינוי אמיתי בלבד')
  unsub()
  for (const id of SCOPE_IDS) {
    assert(['page', 'section', 'dialog'].includes(SCOPES[id as ScopeId]), `שכבה לא מוכרת ל-${id}`)
  }
  console.log('✓ רישומים כפולים וסגירה כפולה מטופלים נכון')
}

// ─── 3. errorBus ───────────────────────────────────────────────────────────

function testPathTemplate(): void {
  eq(pathTemplate('/guests/123'), '/guests/{id}', 'מזהה מספרי מוחלף')
  eq(pathTemplate('https://api.veya.test/guests/9?q=דנה'), '/guests/{id}', 'origin ו-query מוסרים')
  eq(pathTemplate('/guests/import/preview'), '/guests/import/preview', 'נתיב בלי מזהים נשאר')
  eq(pathTemplate('/automation/timeline/42/'), '/automation/timeline/{id}', 'לוכסן בסוף מוסר')
  eq(
    pathTemplate('/partner/invitations/Ab3dEfGh1jKlMnOpQrSt9uVwXyZ'),
    '/partner/invitations/{token}',
    'טוקן ארוך מוחלף',
  )
  eq(pathTemplate('/communication/sequence/invitation'), '/communication/sequence/invitation', 'מילה רגילה נשארת')
  eq(pathTemplate('guests'), '/guests', 'נתיב בלי לוכסן מתחיל מקבל אחד')
  console.log('✓ נתיבים נשמרים כתבנית — בלי מזהים, בלי טוקנים, בלי חיפושים')
}

function testErrorsKeepOnlyLastFive(): void {
  resetErrorBusForTests()
  for (let i = 1; i <= 7; i++) reportResponse('GET', `/guests/${i}`, 404)
  eq(recentErrors().length, 5, 'נשמרות רק 5 שגיאות אחרונות')
  eq(recentErrors()[0].path, '/guests/{id}', 'הנתיב נשמר כתבנית')
  reportResponse('GET', '/stats', 200)
  eq(recentErrors().length, 5, 'הצלחה לא נרשמת כשגיאה')
  console.log('✓ רק 5 השגיאות האחרונות נשמרות, בזיכרון')
}

function testErrorMessageEnrichment(): void {
  resetErrorBusForTests()
  reportResponse('POST', '/guests/import/preview', 400)
  reportErrorMessage('/guests/import/preview', 400, "לא זוהו עמודות חובה. ודא שיש עמודות 'שם' ו'טלפון' בקובץ.")
  eq(recentErrors()[0].message?.startsWith('לא זוהו עמודות חובה'), true, 'ההודעה נצמדת לשגיאה')
  reportErrorMessage('/confirm/abc', 404, 'הקישור כבר לא פעיל')
  eq(recentErrors().length, 1, 'הודעה בלי שגיאה תואמת (מסך ציבורי) לא יוצרת שגיאה חדשה')
  reportErrorMessage('/guests/import/preview', 400, 'הודעה שנייה')
  eq(recentErrors()[0].message?.startsWith('לא זוהו'), true, 'הודעה קיימת לא נדרסת')
  console.log('✓ ההודעה שהמשתמש ראה נצמדת לשגיאה הנכונה')
}

function testListenersGetWritesAndErrorsOnly(): void {
  resetErrorBusForTests()
  const seen: ApiEvent[] = []
  const off = onApiEvent((e) => seen.push(e))
  reportResponse('GET', '/guests', 200)          // קריאה מוצלחת — לא מעניינת
  reportResponse('POST', '/guests', 201)         // "המוזמן נוסף"
  reportResponse('patch', '/event', 409)         // שגיאה
  reportNetworkFailure(undefined, '/stats')      // אין רשת
  reportCrash()
  eq(
    seen.map((e) => `${e.method} ${e.path} ${e.status} ${e.ok}`),
    ['POST /guests 201 true', 'PATCH /event 409 false', 'GET /stats 0 false', ' ui:crash -1 false'],
    'מאזינים מקבלים הצלחות כתיבה ושגיאות בלבד',
  )
  off()
  reportResponse('POST', '/guests', 201)
  eq(seen.length, 4, 'אחרי ביטול — אין עוד התראות')
  onApiEvent(() => {
    throw new Error('מאזין שבור')
  })
  reportResponse('DELETE', '/guests/5', 204) // לא זורק החוצה
  console.log('✓ מאזינים מקבלים רק כתיבות מוצלחות ושגיאות, ומאזין שבור לא מפיל קריאה')
}

testEveryTargetExistsInItsFile()
testNoOrphanOrDuplicateDataHelp()
testEveryScopeIsUsed()
testHelpPagesMatchAppRoutes()
testScopeOrder()
testScopeDuplicatesAndCleanup()
testPathTemplate()
testErrorsKeepOnlyLastFive()
testErrorMessageEnrichment()
testListenersGetWritesAndErrorsOnly()
console.log('OK — יסודות מערכת העזרה תקינים.')
