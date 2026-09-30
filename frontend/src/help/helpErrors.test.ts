/**
 * עזרה ליד שגיאה שקרתה עכשיו (HELP_CENTER_PLAN.md שלב 5).
 *
 * הרצה: `npm run test:help`.
 *
 *  1. שגיאה אמיתית (ההודעות שהשרת באמת מחזיר) → העץ הנכון, ותוצאה ספציפית.
 *  2. שגיאה לא מוזהה → אין הצעת עזרה (לא ממציאים פתרון).
 *  3. שגיאה ישנה (מעל 5 דקות) / הודעה אחרת על המסך → לא נחשבת "השגיאה של עכשיו".
 *  4. אין מידע אישי ב-error context: טלפונים, מספרים, מיילים, שמות אחרי נקודתיים,
 *     ומה שהוקלד בשדה הטלפון — מנוקים לפני שנשמרים.
 *  5. רשימת השגיאות המזוהות (errorHelp.ts, בחבילה הראשית) == מה שעצי התקלות
 *     בבסיס הידע באמת מזהים — לא יותר ולא פחות.
 */
import {
  onApiEvent, recentErrors, redactMessage, reportErrorMessage, reportNetworkFailure,
  reportResponse, resetErrorBusForTests,
} from './errorBus'
import { ERROR_HELP, ERROR_WINDOW_MS, currentKnownError, errorAt, knownErrorTree, latestKnownError } from './errorHelp'
import { TREES } from './kb/index'
import { runTree } from './engine/diagnose'
import { errorFactsFor } from './engine/topics'
import type { Condition } from './types'

function assert(cond: boolean, msg: string): void {
  if (!cond) throw new Error(`✗ ${msg}`)
}
function eq<T>(actual: T, expected: T, msg: string): void {
  const a = JSON.stringify(actual)
  const b = JSON.stringify(expected)
  if (a !== b) throw new Error(`✗ ${msg}\n  התקבל:  ${a}\n  ציפינו: ${b}`)
}

/** מדמה בדיוק מה ש-apiFetch + toError עושים בשגיאה אמיתית. */
function serverError(method: string, path: string, status: number, message: string): void {
  reportResponse(method, path, status)
  reportErrorMessage(path, status, message)
}

// ההודעות כפי שהשרת מחזיר אותן בפועל (נאכף ב-helpKb שהן קיימות בקוד השרת).
const REAL: [string, string, number, string, string][] = [
  ['POST', '/guests', 422, 'נראה שהמספר 05212 לא תקין. מספר נייד מתחיל ב-05 ויש בו 10 ספרות, למשל 050-1234567.', 'guest-save-failed'],
  ['POST', '/guests', 422, 'שם מלא הוא שדה חובה', 'guest-save-failed'],
  ['PATCH', '/guests/17', 422, 'כמות אנשים חייבת להיות לפחות 1', 'guest-save-failed'],
  ['POST', '/guests/import/preview', 400, "לא זוהו עמודות חובה. ודא שיש עמודות 'שם' ו'טלפון' בקובץ.", 'import-failed'],
  ['POST', '/guests/import/preview', 400, 'הקובץ גדול מדי (מעל 5MB) — פצלו אותו לקובץ קטן יותר.', 'import-failed'],
  ['POST', '/guests/import/preview', 400, 'הקובץ מכיל יותר מ-5000 שורות — פצלו אותו לכמה קבצים קטנים יותר.', 'import-failed'],
  ['POST', '/guests/import/preview', 400, 'פורמט קובץ לא נתמך. נא להעלות קובץ .xlsx או .csv', 'import-failed'],
  ['POST', '/guests/import/paste', 400, 'הרשימה ארוכה מדי. נא לפצל להדבקות קטנות יותר.', 'import-failed'],
  ['PATCH', '/event', 409, 'תאריך האירוע נעול לעריכה, כדי שאישורי ההגעה והתזכורות יישארו מסונכרנים.', 'event-save-failed'],
  ['PATCH', '/event', 400, 'בתאריך הזה הרשימה כבר הייתה סגורה. אפשר לבחור פחות ימים לפני האירוע.', 'event-save-failed'],
  ['PATCH', '/event', 400, 'שעת השליחה חייבת להיות בין 10:00 ל-19:00', 'event-save-failed'],
  ['POST', '/seating/generate', 400, 'אין מוזמנים שאישרו הגעה לשיבוץ', 'seating-failed'],
  ['POST', '/seating/generate', 400, 'חבורה גדולה ממספר הכיסאות לשולחן: משפחת לוי, דנה כהן', 'seating-failed'],
  ['POST', '/seating/generate', 400, 'הרזרבה גדולה מדי: אחרי השארת 20 מקומות פנויים נשארו 80 מקומות ל-95 אנשים.', 'seating-failed'],
]

// ─── 5. הרשימה בחבילה הראשית == מה שהעצים מזהים ─────────────────────────

function factsIn(c: Condition): { fact: string; op: string; value: unknown }[] {
  if ('all' in c) return c.all.flatMap(factsIn)
  if ('any' in c) return c.any.flatMap(factsIn)
  if ('not' in c) return factsIn(c.not)
  return [c]
}

function testRegistryMatchesTrees(): void {
  const derived = TREES.flatMap((t) => {
    const checks = Object.values(t.nodes).flatMap((n) => (n.kind === 'check' ? factsIn(n.test) : []))
    const known = checks.filter((c) => c.fact === 'error.last.message' && c.op === 'includes').map((c) => String(c.value))
    const offline = checks.some((c) => c.fact === 'error.last.status' && c.op === '==' && c.value === 0)
    if (!t.errorMatch?.length || (!known.length && !offline)) return []
    const routes = t.errorMatch.map((m) => `${m.method} ${m.path}`)
    return [{ tree: t.id, routes, known, offline }]
  })
  const norm = (x: readonly { tree: string; routes: readonly string[]; known: readonly string[]; offline: boolean }[]) =>
    [...x].map((d) => ({ ...d, routes: [...d.routes].sort(), known: [...d.known].sort() }))
      .sort((a, b) => a.tree.localeCompare(b.tree))
  eq(norm(ERROR_HELP), norm(derived), 'errorHelp.ts == מה שעצי התקלות מזהים')
  // העץ "לא מצליחים לשלוח" בודק עובדות ולא הודעות שגיאה — ולכן לא מוצע ליד שגיאה.
  assert(!ERROR_HELP.some((d) => d.tree === 'invite-not-sent'), 'עץ בלי זיהוי הודעה לא מוצע ליד שגיאה')
  console.log(`✓ ${ERROR_HELP.length} סוגי השגיאות המזוהות זהים בדיוק למה שעצי התקלות יודעים לזהות`)
}

function testKnownFragmentsSurviveRedaction(): void {
  for (const d of ERROR_HELP) {
    for (const k of d.known) eq(redactMessage(k), k, `הניסוח "${k}" לא נפגע מהניקוי`)
  }
  console.log('✓ הניקוי לא פוגע באף ניסוח שהעזרה מזהה')
}

// ─── 1. שגיאה אמיתית → העזרה הנכונה, עם תוצאה ספציפית ─────────────────

function testRealErrorsGetTheRightHelp(): void {
  for (const [method, path, status, message, tree] of REAL) {
    resetErrorBusForTests()
    serverError(method, path, status, message)
    const e = recentErrors()[0]
    eq(knownErrorTree(e), tree, `"${message.slice(0, 30)}…" → ${tree}`)
    // מה שהמסך מציג (ההודעה המקורית) מוביל לאותה שגיאה בדיוק.
    const hit = currentKnownError(message)
    eq(hit?.tree, tree, 'ההודעה שעל המסך מזוהה')
    // והעץ, מול העובדות של השגיאה הזו (אחרי ניקוי), מגיע לתוצאה ספציפית — לא "לא זיהינו".
    const t = TREES.find((x) => x.id === tree)!
    // + עובדת שרת אחת שהמסך מקבל תמיד מ-/help/context (האם יש בקשה לשינוי מועד).
    const step = runTree(t, { 'event.postpone': 'none', ...errorFactsFor(t.errorMatch, [e], Date.now()) }).step
    assert(step.kind === 'outcome' && step.def.resolution !== 'unknown', `${tree}: תוצאה ספציפית ל-"${message.slice(0, 30)}…" (קיבלנו ${step.kind === 'outcome' ? step.node : step.kind})`)
  }
  // אין אינטרנט — מזוהה בכל אחד מהנתיבים שיש להם טיפול בזה.
  resetErrorBusForTests()
  reportNetworkFailure('POST', '/guests', 'החיבור לשרת נכשל. בדקו את החיבור ונסו שוב.')
  eq(currentKnownError('החיבור לשרת נכשל. בדקו את החיבור ונסו שוב.')?.tree, 'guest-save-failed', 'אין חיבור → בדיקת החיבור')
  console.log(`✓ ${REAL.length} הודעות שרת אמיתיות + "אין חיבור" → העזרה הנכונה, עם תוצאה ספציפית`)
}

// ─── 2. שגיאה לא מזוהה → לא ממציאים ──────────────────────────────────────

function testUnknownErrorsGetNoHelp(): void {
  resetErrorBusForTests()
  serverError('POST', '/guests', 500, 'משהו השתבש. נסו שוב בעוד רגע.')
  eq(currentKnownError('משהו השתבש. נסו שוב בעוד רגע.'), null, 'שגיאת שרת כללית → אין הצעה')
  resetErrorBusForTests()
  serverError('POST', '/guests', 422, 'הודעה שאף עץ לא מכיר')
  eq(currentKnownError('הודעה שאף עץ לא מכיר'), null, 'הודעה לא מוכרת בנתיב מוכר → אין הצעה')
  resetErrorBusForTests()
  serverError('POST', '/finance/expenses', 400, 'שם מלא הוא שדה חובה')
  eq(currentKnownError('שם מלא הוא שדה חובה'), null, 'ניסוח מוכר בנתיב שאין לו עץ → אין הצעה')
  resetErrorBusForTests()
  reportNetworkFailure('POST', '/automation/track/activate', 'החיבור לשרת נכשל. בדקו את החיבור ונסו שוב.')
  eq(currentKnownError('החיבור לשרת נכשל. בדקו את החיבור ונסו שוב.'), null, 'אין חיבור בנתיב שאין לו טיפול בשגיאה → אין הצעה')
  eq(currentKnownError('טקסט שמעולם לא הגיע מהשרת'), null, 'הודעה שלא נרשמה (למשל טקסט קבוע של המסך) → אין הצעה')
  console.log('✓ שגיאה לא מזוהה לא מקבלת "פתרון" מומצא')
}

// ─── 3. שגיאה ישנה / אחרת לא נחשבת "עכשיו" ──────────────────────────────

function testStaleOrDifferentErrorsAreIgnored(): void {
  resetErrorBusForTests()
  serverError('POST', '/seating/generate', 400, 'אין מוזמנים שאישרו הגעה לשיבוץ')
  const at = recentErrors()[0].at
  eq(currentKnownError('אין מוזמנים שאישרו הגעה לשיבוץ', at + ERROR_WINDOW_MS + 1), null, 'אחרי 5 דקות — לא "עכשיו"')
  eq(latestKnownError(at + ERROR_WINDOW_MS + 1), null, 'גם בבית העזרה — לא מוצגת שגיאה ישנה')
  eq(errorAt(at, at + ERROR_WINDOW_MS + 1), null, 'עץ שנפתח משגיאה ישנה לא מקבל את העובדות שלה')
  eq(currentKnownError('הודעה אחרת לגמרי', at), null, 'הודעה אחרת על המסך → לא קשורה לשגיאה שנרשמה')
  // שגיאה חדשה ושונה אחריה — היא "העכשווית" בבית העזרה.
  serverError('PATCH', '/event', 409, 'תאריך האירוע נעול לעריכה, כדי שאישורי ההגעה והתזכורות יישארו מסונכרנים.')
  eq(latestKnownError()?.tree, 'event-save-failed', 'השגיאה המזוהה האחרונה היא זו שמוצגת')
  // והשגיאה הקודמת עדיין נגישה רק דרך הרגע שלה — לא מתחלפת בחדשה.
  eq(errorAt(at)?.path, '/seating/generate', 'עץ שנפתח משגיאה מסוימת נבדק מולה בלבד')
  // השגיאה תוקנה: כתיבה מוצלחת לאותו נתיב אחריה → כבר לא "עכשיו" (לא בשורה ולא בבית העזרה).
  resetErrorBusForTests()
  serverError('POST', '/guests', 422, 'שם מלא הוא שדה חובה')
  eq(latestKnownError()?.tree, 'guest-save-failed', 'לפני התיקון — מוצגת')
  reportResponse('PATCH', '/guests/9', 200)
  eq(latestKnownError()?.tree, 'guest-save-failed', 'הצלחה בנתיב אחר לא "מתקנת" אותה')
  reportResponse('POST', '/guests', 201)
  eq(latestKnownError(), null, 'אחרי שמירה מוצלחת — לא מוצגת בבית העזרה')
  eq(currentKnownError('שם מלא הוא שדה חובה'), null, 'ולא ליד ההודעה')
  // …ושגיאה חדשה אחרי ההצלחה — שוב "עכשיו".
  serverError('POST', '/guests', 422, 'שם מלא הוא שדה חובה')
  eq(latestKnownError()?.tree, 'guest-save-failed', 'שגיאה חדשה אחרי ההצלחה — מוצגת')
  console.log('✓ שגיאה ישנה, אחרת, או כזו שכבר תוקנה — לא מוצגת כאילו היא השגיאה של עכשיו')
}

// ─── 4. בלי מידע אישי ─────────────────────────────────────────────────────

function testNoPersonalDataInErrorContext(): void {
  const cases: [string, string[]][] = [
    ['נראה שהמספר 052-777-0011 לא תקין. מספר נייד מתחיל ב-05 ויש בו 10 ספרות, למשל 050-1234567.', ['0527770011', '777', '050', '1234567']],
    ['נראה שהמספר דנה כהן לא תקין. מספר נייד מתחיל ב-05', ['דנה כהן']],
    ['חבורה גדולה ממספר הכיסאות לשולחן: משפחת לוי, זהבית סודית', ['לוי', 'זהבית', 'סודית']],
    ['ההזמנה נשלחה לכתובת dana@example.com, ואתם מחוברים עם avi@example.com', ['dana', 'avi', 'example.com']],
    ['הקישור +972 52 777 0011 לא תקין', ['972', '777']],
  ]
  for (const [raw, secrets] of cases) {
    resetErrorBusForTests()
    serverError('POST', '/guests', 422, raw)
    const stored = recentErrors()[0].message ?? ''
    for (const s of secrets) assert(!stored.includes(s), `"${s}" נשאר אחרי הניקוי: "${stored}"`)
    assert(!/\d{2,}/.test(stored), `נשארו ספרות: "${stored}"`)
    assert(stored.length <= 160, 'הודעה מקוצרת')
  }
  // הנתיב עצמו בלי מזהים, והאירועים שמאזינים מקבלים — בלי ההודעה הגולמית.
  resetErrorBusForTests()
  const seen: string[] = []
  const off = onApiEvent((e) => seen.push(JSON.stringify(e)))
  serverError('PATCH', '/guests/555', 422, 'נראה שהמספר 0527770011 לא תקין')
  off()
  const all = JSON.stringify(recentErrors()) + seen.join('')
  assert(!all.includes('555') && !all.includes('0527770011'), `מזהה/טלפון דלף: ${all}`)
  console.log('✓ ב-error context אין טלפונים, מספרים, מיילים, שמות, או מה שהוקלד בשדה')
}

testRegistryMatchesTrees()
testKnownFragmentsSurviveRedaction()
testRealErrorsGetTheRightHelp()
testUnknownErrorsGetNoHelp()
testStaleOrDifferentErrorsAreIgnored()
testNoPersonalDataInErrorContext()
console.log('OK — עזרה ליד שגיאה: מזהה רק מה שבאמת קרה, ולא שומרת מידע אישי.')
