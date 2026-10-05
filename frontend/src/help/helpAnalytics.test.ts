/**
 * מדידת שימוש בעזרה (HELP_CENTER_PLAN.md §12, שלב 8).
 *
 * הרצה: `npm run test:help`.
 *
 *  1. אוצר המילים בדפדפן == ``backend/app/help_events_spec.json`` (אותם 11 שמות,
 *     אותם שדות, אותם ערכים) — אין "אוצר מילים שני" שיכול לסטות.
 *  2. אין שדה טקסט חופשי בכלל; ל-``search_no_results`` אין שדות — טקסט החיפוש
 *     לא יכול לעבור.
 *  3. ``cleanEvent`` דוחה שם/שדה/ערך לא מוכר, טקסט, מספר גדול, אובייקט.
 *  4. כל מזהי בסיס הידע עומדים בתבנית kb_id (אחרת האירוע שלהם לא יישלח).
 *  5. בקוד העזרה: ``track`` לא מקבל את טקסט החיפוש, ונשלח רק דרך analytics.ts.
 *  6. אישור Cookies: אישור ישן (מלפני שהסטטיסטיקה הייתה בשימוש) לא מספיק —
 *     לא מודדים עד בחירה מחדש; "לא" נשאר "לא"; אחרי אישור חדש — מודדים.
 */
import { HELP_EVENT_SPEC, cleanEvent, newSessionId } from './analyticsSpec'
import { ANALYTICS_PURPOSE, analyticsAllowed, getCookieConsent, needsAnalyticsReconsent, setCookieConsent } from '../cookieConsent'
import { strings } from '../strings/he'
import { FLOWS, TOPICS, TREES } from './kb/index'

function assert(cond: boolean, msg: string): void {
  if (!cond) throw new Error(`✗ ${msg}`)
}
function eq<T>(actual: T, expected: T, msg: string): void {
  const a = JSON.stringify(actual)
  const b = JSON.stringify(expected)
  if (a !== b) throw new Error(`✗ ${msg}\n  בדפדפן: ${a}\n  בשרת:   ${b}`)
}

interface Fs {
  readFileSync(p: string, enc: string): string
  readdirSync(p: string): string[]
  statSync(p: string): { isDirectory(): boolean }
}
declare function require(name: 'fs'): Fs
declare const __dirname: string
const fs = require('fs')
const HELP = `${__dirname}/../../src/help`
const SPEC_PATH = `${__dirname}/../../../backend/app/help_events_spec.json`

/** נמצא בבדיקה בדפדפן (StrictMode בונה רכיבים פעמיים): בלי ספירה כפולה. */
function testNoDoubleCounting(): void {
  const tour = fs.readFileSync(`${HELP}/ui/TourRunner.tsx`, 'utf8')
  assert(!/return \(\) => report\(/.test(tour), 'הדרכה: "נעצרה" נרשם בפירוק הרכיב — זה סופר כפול ומחמיץ יציאה אמיתית')
  assert(/startedRef\.current\) return/.test(tour), 'הדרכה: "התחילה" לא מוגן מספירה כפולה')
  assert(/onClick=\{exitAbandoned\}/.test(tour) && /else exitAbandoned\(\)/.test(tour), 'הדרכה: יציאה (כפתור / Escape) לא נרשמת כ"נעצרה"')
  const app = fs.readFileSync(`${HELP}/ui/HelpApp.tsx`, 'utf8')
  assert(/onceKey=\{`article:/.test(app) && /onceKey=\{`outcome:/.test(app), 'נושא/תוצאה לא נרשמים פעם אחת בסשן')
  assert(/if \(wasOpenRef\.current\) return/.test(app), 'פתיחת העזרה לא מוגנת מסשן כפול')
  console.log('✓ בלי ספירה כפולה: פתיחה, נושא, תוצאה והדרכה נרשמים פעם אחת; "נעצרה" רק ביציאה אמיתית')
}

function testSameVocabularyAsServer(): void {
  const server = JSON.parse(fs.readFileSync(SPEC_PATH, 'utf8')) as { names: Record<string, Record<string, unknown>> }
  const sortKeys = (o: Record<string, unknown>) => Object.fromEntries(Object.keys(o).sort().map((k) => [k, o[k]]))
  eq(Object.keys(HELP_EVENT_SPEC).sort(), Object.keys(server.names).sort(), 'אותם שמות אירועים')
  for (const name of Object.keys(server.names)) {
    eq(
      sortKeys((HELP_EVENT_SPEC as Record<string, Record<string, unknown>>)[name]),
      sortKeys(server.names[name]),
      `${name}: אותם שדות וערכים`,
    )
  }
  assert(Object.keys(HELP_EVENT_SPEC).length === 11, '11 שמות בדיוק (החלטת המייסד)')
  console.log('✓ 11 האירועים בדפדפן זהים בדיוק לאוצר המילים של השרת')
}

function testNoFreeText(): void {
  for (const [name, fields] of Object.entries(HELP_EVENT_SPEC)) {
    for (const [field, kind] of Object.entries(fields as Record<string, unknown>)) {
      assert(Array.isArray(kind) || ['kb_id', 'kb_id?', 'bool', 'int'].includes(String(kind)), `${name}.${field}: סוג פתוח "${kind}"`)
      assert(!/query|text|search|message|name|email|phone/i.test(field) || field === 'name', `${name}.${field}: שם שדה חשוד`)
    }
  }
  eq(HELP_EVENT_SPEC.search_no_results, {}, 'search_no_results — בלי שדות בכלל')
  console.log('✓ אין אף שדה של טקסט חופשי; לחיפוש בלי תוצאות אין שדות')
}

function testCleanEvent(): void {
  assert(cleanEvent('topic_selected', { topic_id: 'guests.add-one', source: 'home' }) !== null, 'אירוע תקין עובר')
  eq(cleanEvent('escalation_started', { from: 'home', topic_id: undefined, tree_id: undefined }), { from: 'home' }, 'שדה לא-חובה ריק מושמט')
  const bad: [string, Record<string, unknown>][] = [
    ['search', {}],
    ['search_no_results', { q: 'זהבית' }],
    ['topic_selected', { topic_id: 'guests.add-one', source: 'home', query: 'דנה' }],
    ['topic_selected', { topic_id: 'דנה כהן', source: 'home' }],
    ['topic_selected', { topic_id: 'guests.add-one', source: 'twitter' }],
    ['guided_help_completed', { flow_id: 'add-guest', result: 'completed', step: 51 }],
    ['guided_help_completed', { flow_id: 'add-guest', result: 'completed', step: 1.5 }],
    ['help_opened', { entry: 'launcher', had_error: 'no', had_urgent: false }],
    ['help_feedback', { target: 'topic', id: 'x', value: 'maybe' }],
    ['help_feedback', { target: 'topic', value: 'helped' }],
  ]
  for (const [name, props] of bad) {
    eq(cleanEvent(name, props as Record<string, string>), null, `נדחה: ${name} ${JSON.stringify(props)}`)
  }
  const sid = newSessionId((n) => new Uint8Array(n).map((_, i) => i * 17))
  assert(/^[0-9a-f]{32}$/.test(sid), 'מזהה סשן: 32 תווי hex')
  console.log('✓ אירוע לא תקין (שם/שדה/ערך/טקסט) פשוט לא נשלח')
}

function testKbIdsFitThePattern(): void {
  const re = /^[a-z0-9][a-z0-9.-]{0,59}$/
  const ids = [
    ...TOPICS.map((t) => t.id), ...TREES.map((t) => t.id), ...Object.keys(FLOWS),
    ...TREES.flatMap((t) => Object.keys(t.nodes)),
  ]
  for (const id of ids) assert(re.test(id), `מזהה "${id}" לא עומד בתבנית — האירועים שלו לא יישלחו`)
  console.log(`✓ כל ${ids.length} המזהים (נושאים, בדיקות, תוצאות, הדרכות) עוברים את התבנית`)
}

function helpFiles(dir = ''): string[] {
  const out: string[] = []
  for (const n of fs.readdirSync(`${HELP}/${dir}`)) {
    const rel = dir ? `${dir}/${n}` : n
    if (fs.statSync(`${HELP}/${rel}`).isDirectory()) out.push(...helpFiles(rel))
    else if (/\.tsx?$/.test(n) && !/\.test\.ts$/.test(n)) out.push(rel)
  }
  return out
}

function testSearchTextNeverTracked(): void {
  let calls = 0
  for (const f of helpFiles()) {
    const src = fs.readFileSync(`${HELP}/${f}`, 'utf8')
    for (const m of src.matchAll(/\btrack\(([^)]*)\)/g)) {
      calls++
      assert(!/query|\bq\b|search(?!_no_results)|needle|value\b(?!:)/.test(m[1]), `help/${f}: track(${m[1]}) — נראה שמעביר טקסט`)
    }
    if (f !== 'analytics.ts') assert(!/postHelpEvents/.test(src), `help/${f}: שולח מדידה ישירות — רק דרך analytics.ts`)
  }
  const app = fs.readFileSync(`${HELP}/ui/HelpApp.tsx`, 'utf8')
  assert(/track\('search_no_results'\)/.test(app), 'חיפוש בלי תוצאות נרשם בלי שום שדה')
  assert(calls >= 10, `נמצאו רק ${calls} קריאות track`)
  const analytics = fs.readFileSync(`${HELP}/analytics.ts`, 'utf8')
  assert(/!analyticsAllowed\(\)\) return/.test(analytics), 'המדידה לא בודקת את אישור ה-Cookies')
  assert(!/getCookieConsent/.test(analytics), 'המדידה בודקת את האישור הישן במקום analyticsAllowed')
  assert(/cleanEvent\(name, props\)/.test(analytics), 'המדידה לא מנקה כל אירוע לפני שליחה')
  console.log(`✓ ${calls} קריאות track — אף אחת לא מעבירה את טקסט החיפוש; נשלח רק באישור ורק דרך analytics.ts`)
}

/** אישור הסטטיסטיקה — כולל אישור מחדש למי שאישר כשהיא עוד לא הייתה בשימוש. */
function testConsent(): void {
  const store = new Map<string, string>()
  ;(globalThis as unknown as { localStorage: Pick<Storage, 'getItem' | 'setItem'> }).localStorage = {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
  }
  const KEY = 'veya_cookie_consent'
  const old = (analytics: boolean) => store.set(KEY, JSON.stringify({ analytics, decidedAt: '2026-05-01T10:00:00.000Z' }))

  store.clear()
  assert(!analyticsAllowed() && !needsAnalyticsReconsent(), 'בלי בחירה: לא מודדים, הבאנר הרגיל')

  old(true)
  assert(!analyticsAllowed(), 'אישור ישן ("אישור הכול" כשהסטטיסטיקה לא הייתה בשימוש) — לא מודדים')
  assert(needsAnalyticsReconsent(), 'אישור ישן — מבקשים בחירה מחדש')
  assert(getCookieConsent()?.decidedAt === '2026-05-01T10:00:00.000Z', 'הבחירה הישנה לא נמחקת עד הבחירה החדשה')

  setCookieConsent(false)
  assert(!analyticsAllowed() && !needsAnalyticsReconsent(), 'בחרו מחדש "בלי סטטיסטיקה" — לא מודדים ולא שואלים שוב')

  old(true)
  setCookieConsent(true)
  assert(analyticsAllowed() && !needsAnalyticsReconsent(), 'אישרו מחדש — מודדים, ולא שואלים שוב')
  assert(getCookieConsent()?.analyticsPurpose === ANALYTICS_PURPOSE, 'האישור החדש מסומן לשימוש הנוכחי')

  old(false)
  assert(!analyticsAllowed() && !needsAnalyticsReconsent(), '"לא" ישן נשאר "לא" — בלי לשאול שוב')

  store.set(KEY, '{bad json')
  assert(!analyticsAllowed() && !needsAnalyticsReconsent(), 'ערך פגום — לא מודדים')

  const banner = fs.readFileSync(`${HELP}/../components/CookieBanner.tsx`, 'utf8')
  assert(/needsAnalyticsReconsent\(\)/.test(banner) && /if \(reconsent\)/.test(banner), 'הבאנר לא מבקש בחירה מחדש')
  assert(/\\\/confirm\\\//.test(banner), 'בדף אישור ההגעה של המוזמנים לא שואלים מחדש (אין שם עזרה)')
  const L = strings.legal
  assert(!/אינן בשימוש/.test(L.cookieAnalyticsLabel), 'הבאנר עדיין אומר שהסטטיסטיקה לא בשימוש')
  for (const t of [L.cookieAnalyticsLabel, L.cookieReconsentBody, L.cookieBody]) {
    assert(/בעזרה/.test(t), `הבאנר לא אומר שהמדידה היא רק בעזרה: "${t}"`)
  }
  console.log('✓ אישור Cookies: אישור ישן לא נחשב עד בחירה מחדש; "לא" נשאר "לא"; אישור חדש — מודדים')
}

testConsent()
testSameVocabularyAsServer()
testNoDoubleCounting()
testNoFreeText()
testCleanEvent()
testKbIdsFitThePattern()
testSearchTextNeverTracked()
console.log('OK — מדידת השימוש בעזרה: אוצר מילים סגור, בלי טקסט ובלי זהות.')
