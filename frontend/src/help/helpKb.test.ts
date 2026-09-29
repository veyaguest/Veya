/**
 * בדיקות בסיס הידע והמנוע של העזרה (HELP_CENTER_PLAN.md — שלב 2).
 *
 * הרצה: `npm run test:help` מתוך תיקיית frontend.
 *
 * חלק א — **שלמות הידע ("אסור להמציא")**: כל נושא/הדרכה/עץ מצביע רק על
 * דברים שקיימים באמת — יעדי UI, עובדות, מסכים, טקסטי כפתורים מ-he.ts,
 * נתיבי API שהפרונט קורא להם, וקבצי מקור. וגם: נאמן ללקסיקון (בלי "חתן/כלה"
 * באירוע אחר), בלי מילים אסורות, תשובות קצרות, שאלות סגורות עד 3 כפתורים.
 * הודעות שגיאה שהעצים מזהים — חייבות להופיע בקוד השרת שמחזיר אותן.
 *
 * חלק ב — **המנוע**: תנאים עם "לא ידוע", טקסט, דירוג, חיפוש, עצי תקלות,
 * ומתי מציעים את צוות VEYA.
 */
import { FACTS, FACT_IDS } from './facts'
import type { Facts } from './facts'
import { SCOPES } from './scopes'
import type { ScopeId } from './scopes'
import { TARGETS } from './targets'
import { GUIDES } from './guides'
import type { Condition, DiagnosticTree, GuidedFlow, HelpAction, HelpTopic } from './types'
import { FLOWS, TOPICS, TREES } from './kb/index'
import { evaluate, factsOf, holds } from './engine/conditions'
import { hebrewDate, renderText, tokensOf } from './engine/text'
import type { TextContext, TextTerms } from './engine/text'
import {
  ERROR_RECENCY_MS,
  errorFactsFor,
  rankTopics,
  resolveTopic,
  treeForRecentError,
} from './engine/topics'
import type { RankContext, RecentError } from './engine/topics'
import { hasCycle, reachableNodes, runTree } from './engine/diagnose'
import { normalize, search } from './engine/search'
import { NO_ATTEMPTS, teamOption } from './engine/ladder'
import { strings } from '../strings/he'
import { EVENT_TYPE_OPTIONS, getEventTerms } from '../strings/eventTypes'

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
  existsSync(p: string): boolean
}
declare function require(name: 'fs'): Fs
declare const __dirname: string
const SRC = `${__dirname}/../../src`
const fs = require('fs')
const readSrc = (rel: string) => fs.readFileSync(`${SRC}/${rel}`, 'utf8')

/** טקסט כפתור מ-strings/he.ts לפי נתיב — רק מחרוזת (לא פונקציה). */
function uiText(path: string): string | undefined {
  let cur: unknown = strings
  for (const key of path.split('.')) {
    if (cur === null || typeof cur !== 'object') return undefined
    cur = (cur as Record<string, unknown>)[key]
  }
  return typeof cur === 'string' ? cur : undefined
}

function termsFor(type: string): TextTerms {
  const t = getEventTerms(type)
  return {
    guests: t.guestsLabel,
    guest: t.guestsLabel === 'משתתפים' ? 'משתתף' : 'מוזמן',
    hosts: t.hostsLabel,
    event: t.eventNoun,
  }
}

/** מצב "מלא" — כל העובדות ידועות — כדי שכל טקסט יוכל להירנדר בבדיקה. */
const FULL_FACTS: Facts = {
  'layout.guestCards': false,
  'layout.hallDesktop': true,
  'client.contactPicker': false,
  'client.online': true,
  'user.role': 'owner',
  'event.days_to_event': 40,
  'guests.total': 120,
  'guests.bad_phone': 3,
  'error.last.method': 'POST',
  'error.last.path': '/guests',
  'error.last.status': 422,
  'error.last.message': 'הודעה לדוגמה',
  'guests.confirmed': 80,
  'event.has_date': true,
  'event.commit_chosen': true,
  'event.edit_unlocked': false,
  'event.postpone': 'none',
  'event.can_request_postpone': true,
  'rsvp.phase': 'running',
  'rsvp.start_date': '2026-10-15',
  'rsvp.commit_date': '2026-10-29',
  'rsvp.next_date': '2026-10-20',
  'rsvp.next_label': 'תזכורת שנייה',
  'rsvp.today_is_weekend': false,
  'messaging.mode': 'live',
  'messaging.emergency_stop': false,
  'messaging.invitation_empty': false,
  'invites.sent': 40,
  'invites.not_yet': 5,
  'messages.wizardStep': 1,
  'feature.calls': true,
  'gifts.eligible': false,
  'seating.undo_available': true,
  'guest.phone': 'valid',
  'guest.invitation': 'sent',
  'guest.rsvp': 'pending',
  'guest.joined_after_last_round': false,
}

function ctxFor(type = 'wedding', facts: Facts = FULL_FACTS): TextContext {
  return { facts, terms: termsFor(type), ui: uiText }
}

const EVENT_TYPES = EVENT_TYPE_OPTIONS.map((o) => o.type as string)

// ─── איסוף כל מה שבבסיס הידע ──────────────────────────────────────────────

function conditionsOfTopic(t: HelpTopic): (Condition | undefined)[] {
  return [t.when, t.urgentWhen, ...(t.variants ?? []).map((v) => v.when)]
}
function conditionsOfFlow(f: GuidedFlow): (Condition | undefined)[] {
  return [f.when, ...f.steps.map((s) => s.when)]
}
function conditionsOfTree(t: DiagnosticTree): (Condition | undefined)[] {
  return [t.when, ...Object.values(t.nodes).map((n) => (n.kind === 'check' ? n.test : undefined))]
}

/** כל הטקסטים שהמשתמש רואה, עם מאיפה הם באו (להודעות שגיאה ברורות). */
function userTexts(): { where: string; text: string }[] {
  const out: { where: string; text: string }[] = []
  const actionLabel = (where: string, a?: HelpAction | null) => {
    if (a?.label) out.push({ where: `${where} (תווית פעולה)`, text: a.label })
  }
  for (const t of TOPICS) {
    out.push({ where: t.id, text: t.title })
    t.answer.forEach((a) => out.push({ where: t.id, text: a }))
    for (const v of t.variants ?? []) {
      v.answer.forEach((a) => out.push({ where: `${t.id} (וריאנט)`, text: a }))
      actionLabel(t.id, v.primary)
    }
    actionLabel(t.id, t.primary)
  }
  for (const f of Object.values(FLOWS)) {
    f.steps.forEach((s) => out.push({ where: `הדרכה ${f.id}`, text: s.text }))
    out.push({ where: `הדרכה ${f.id}`, text: f.doneText })
  }
  for (const tr of TREES) {
    out.push({ where: `עץ ${tr.id}`, text: tr.symptom })
    for (const [id, n] of Object.entries(tr.nodes)) {
      if (n.kind === 'ask') {
        out.push({ where: `עץ ${tr.id}/${id}`, text: n.question })
        n.options.forEach((o) => out.push({ where: `עץ ${tr.id}/${id}`, text: o.label }))
      }
      if (n.kind === 'outcome') {
        n.text.forEach((x) => out.push({ where: `עץ ${tr.id}/${id}`, text: x }))
        actionLabel(`עץ ${tr.id}/${id}`, n.action)
      }
    }
  }
  return out
}

function actionsAll(): { where: string; action: HelpAction }[] {
  const out: { where: string; action: HelpAction }[] = []
  for (const t of TOPICS) {
    if (t.primary) out.push({ where: t.id, action: t.primary })
    for (const v of t.variants ?? []) if (v.primary) out.push({ where: t.id, action: v.primary })
  }
  for (const tr of TREES) {
    for (const [id, n] of Object.entries(tr.nodes)) {
      if (n.kind === 'outcome' && n.action) out.push({ where: `${tr.id}/${id}`, action: n.action })
    }
  }
  return out
}

// ═══ חלק א — שלמות הידע ════════════════════════════════════════════════════

function testUniqueIds(): void {
  const ids = [...TOPICS.map((t) => t.id), ...Object.keys(FLOWS), ...TREES.map((t) => t.id)]
  eq(ids.length, new Set(ids).size, 'אין שני נושאים/הדרכות/עצים עם אותו מזהה')
  eq(Object.values(FLOWS).every((f) => FLOWS[f.id] === f), true, 'מזהה ההדרכה = המפתח שלה')
  console.log(`✓ ${TOPICS.length} נושאים, ${Object.keys(FLOWS).length} הדרכות, ${TREES.length} עצי תקלות — מזהים ייחודיים`)
}

function testFactsExist(): void {
  const used = new Set<string>()
  for (const t of TOPICS) conditionsOfTopic(t).forEach((c) => factsOf(c).forEach((f) => used.add(f)))
  for (const f of Object.values(FLOWS)) conditionsOfFlow(f).forEach((c) => factsOf(c).forEach((x) => used.add(x)))
  for (const tr of TREES) conditionsOfTree(tr).forEach((c) => factsOf(c).forEach((x) => used.add(x)))
  for (const { text } of userTexts()) {
    for (const tok of tokensOf(text)) if (['n', 'date', 'text', 'count'].includes(tok.kind) && tok.arg) used.add(tok.arg)
  }
  for (const f of used) {
    assert((FACT_IDS as string[]).includes(f), `העובדה "${f}" לא רשומה ב-help/facts.ts`)
  }
  // ערך השוואה לעובדה סגורה חייב להיות אחד הערכים שלה.
  const checkValues = (c: Condition | undefined) => {
    if (!c) return
    if ('all' in c) return c.all.forEach(checkValues)
    if ('any' in c) return c.any.forEach(checkValues)
    if ('not' in c) return checkValues(c.not)
    const def = FACTS[c.fact] as { values?: readonly string[] }
    if (!def.values) return
    const vals = Array.isArray(c.value) ? c.value : [c.value]
    for (const v of vals) assert(def.values.includes(String(v)), `ערך "${v}" לא קיים לעובדה ${c.fact}`)
  }
  TOPICS.forEach((t) => conditionsOfTopic(t).forEach(checkValues))
  Object.values(FLOWS).forEach((f) => conditionsOfFlow(f).forEach(checkValues))
  TREES.forEach((t) => conditionsOfTree(t).forEach(checkValues))
  console.log(`✓ כל ${used.size} העובדות שבשימוש רשומות, עם ערכים חוקיים`)
}

function testUiTokensResolve(): void {
  let n = 0
  for (const { where, text } of userTexts()) {
    for (const tok of tokensOf(text)) {
      assert(
        ['guests', 'guest', 'hosts', 'event', 'ui', 'n', 'date', 'text', 'count'].includes(tok.kind),
        `${where}: טוקן לא מוכר {${tok.kind}}`,
      )
      if (tok.kind === 'ui') {
        n++
        assert(!!tok.arg && uiText(tok.arg) !== undefined, `${where}: {ui:${tok.arg}} לא קיים כטקסט ב-strings/he.ts`)
      }
    }
    const stripped = text.replace(/\{[^{}]*\}/g, '')
    assert(!/[{}]/.test(stripped), `${where}: סוגריים מסולסלים שבורים — "${text}"`)
  }
  console.log(`✓ כל ${n} ציטוטי הכפתורים ({ui:…}) קיימים ב-strings/he.ts`)
}

function testActionsPointToRealThings(): void {
  const appPages = ['dashboard', 'guests', 'messages', 'rsvp', 'hall', 'gifts', 'finance']
  for (const { where, action } of actionsAll()) {
    if (action.kind === 'tour') assert(!!FLOWS[action.flow], `${where}: הדרכה לא קיימת "${action.flow}"`)
    if (action.kind === 'diagnose') assert(TREES.some((t) => t.id === action.tree), `${where}: עץ לא קיים "${action.tree}"`)
    if (action.kind === 'navigate') assert(appPages.includes(action.page), `${where}: מסך לא קיים "${action.page}"`)
    if (action.kind === 'guide') {
      const g = GUIDES[action.guide]
      assert(!!g, `${where}: מדריך לא קיים "${action.guide}"`)
      // ה-opener חייב להיות על הכפתור עצמו — בתוך תגית הפתיחה של האלמנט עם ה-data-help שלו.
      const src = readSrc(g.file)
      const at = src.indexOf(`data-help="${g.target}"`)
      assert(at >= 0, `${where}: הכפתור של המדריך (${g.target}) לא נמצא ב-${g.file}`)
      // תגית הפתיחה: מ-"<" שלפני ה-data-help ועד 200 תווים אחריו (ה-onClick צמוד אליו).
      const openTag = src.slice(src.lastIndexOf('<', at), at + 200)
      assert(openTag.includes(g.opener), `${where}: הכפתור ${g.target} כבר לא פותח את המדריך (${g.opener})`)
      assert(src.includes(g.listener), `${where}: המסך לא מאזין לבקשת "למדריך" מהעזרה (${g.listener})`)
    }
  }
  for (const t of TOPICS) {
    for (const r of t.related ?? []) assert(TOPICS.some((x) => x.id === r), `${t.id}: נושא קשור לא קיים "${r}"`)
    assert((t.related ?? []).length <= 2, `${t.id}: יותר מ-2 נושאים קשורים`)
  }
  // כל הדרכה בשימוש — אין הדרכה "יתומה" שאף אחד לא מגיע אליה.
  const used = new Set(actionsAll().filter((a) => a.action.kind === 'tour').map((a) => (a.action as { flow: string }).flow))
  for (const id of Object.keys(FLOWS)) assert(used.has(id), `ההדרכה "${id}" לא מופעלת מאף נושא או עץ`)
  console.log('✓ כל פעולה מובילה להדרכה/עץ/מסך קיים, ואין הדרכה יתומה')
}

function testFlowsUseRealTargetsAndApis(): void {
  const api = readSrc('api.ts')
  const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const apiCalled = (method: string, path: string) => {
    // "/guests/{id}" ⇔ `/guests/${id}` ב-api.ts; השיטה — בתוך אותה קריאה.
    const pathRe = escapeRe(path).replace(/\\\{id\\\}/g, '\\$\\{[^}]+\\}')
    const call = new RegExp(`apiFetch\\([\`'"]${pathRe}[\`'"][^)]*?method: '${method}'`, 's')
    return call.test(api)
  }
  for (const f of Object.values(FLOWS)) {
    assert(f.steps.length > 0, `הדרכה ${f.id}: אין צעדים`)
    for (const s of f.steps) {
      assert(s.target in TARGETS, `הדרכה ${f.id}: היעד "${s.target}" לא רשום ב-help/targets.ts`)
      if (s.advanceOn.kind === 'visible') assert(s.advanceOn.target in TARGETS, `הדרכה ${f.id}: יעד לא רשום ${s.advanceOn.target}`)
      if (s.advanceOn.kind === 'scope') assert(s.advanceOn.scope in SCOPES, `הדרכה ${f.id}: scope לא רשום ${s.advanceOn.scope}`)
      if (s.advanceOn.kind === 'api') {
        assert(apiCalled(s.advanceOn.method, s.advanceOn.path), `הדרכה ${f.id}: ${s.advanceOn.method} ${s.advanceOn.path} לא נקרא ב-api.ts`)
      }
      // היעד של הצעד חייב להיות במסך שההדרכה מתחילה בו (אין הדרכה שקופצת בין מסכים באמצע).
      eq(TARGETS[s.target].page, f.start.page, `הדרכה ${f.id}: היעד ${s.target} לא במסך ${f.start.page}`)
    }
    assert(apiCalled(f.success.method, f.success.path), `הדרכה ${f.id}: סימן ההצלחה לא נקרא ב-api.ts`)
    // הצעד האחרון הוא זה שהשרת מאשר — ההדרכה לא "מסתיימת" בלי שהפעולה באמת קרתה.
    const last = f.steps[f.steps.length - 1]
    eq(last.advanceOn, f.success, `הדרכה ${f.id}: הצעד האחרון צריך להסתיים באישור השרת`)
    for (const e of f.onError ?? []) assert(TREES.some((t) => t.id === e.tree), `הדרכה ${f.id}: עץ לא קיים ${e.tree}`)
  }
  console.log('✓ ההדרכות משתמשות רק ביעדים רשומים, ומסתיימות רק כשהשרת מאשר קריאה שקיימת ב-api.ts')
}

function testTreesAreSound(): void {
  for (const t of TREES) {
    assert(t.root in t.nodes, `עץ ${t.id}: שורש חסר`)
    for (const [id, n] of Object.entries(t.nodes)) {
      const refs =
        n.kind === 'check' ? [n.yes, n.no, ...(n.unknown ? [n.unknown] : [])] :
        n.kind === 'ask' ? n.options.map((o) => o.next) : []
      for (const r of refs) assert(r in t.nodes, `עץ ${t.id}/${id}: מפנה לצומת חסר "${r}"`)
      if (n.kind === 'ask') assert(n.options.length >= 2 && n.options.length <= 3, `עץ ${t.id}/${id}: שאלה סגורה = 2–3 כפתורים`)
      if (n.kind === 'outcome') assert(n.text.length >= 1 && n.text.length <= 3, `עץ ${t.id}/${id}: 1–3 שורות`)
    }
    assert(!hasCycle(t), `עץ ${t.id}: יש מעגל`)
    const reach = reachableNodes(t)
    for (const id of Object.keys(t.nodes)) assert(reach.has(id), `עץ ${t.id}: הצומת "${id}" לא נגיש מהשורש`)
    assert(Object.values(t.nodes).some((n) => n.kind === 'outcome'), `עץ ${t.id}: אין תוצאה`)
  }
  console.log('✓ עצי התקלות תקינים: בלי מעגלים, בלי צמתים מתים, שאלות סגורות עד 3 כפתורים')
}

/** כל הודעת שגיאה שעץ מזהה — חייבת להופיע בקוד שמחזיר אותה (ב-sources של העץ). */
function testTreeErrorTextsExistInServer(): void {
  let n = 0
  for (const t of TREES) {
    const sources = t.sources.map(readSrc).join('\n')
    for (const [id, node] of Object.entries(t.nodes)) {
      if (node.kind !== 'check') continue
      const c = node.test
      if (!('fact' in c) || c.fact !== 'error.last.message' || c.op !== 'includes') continue
      n++
      assert(
        sources.includes(String(c.value)),
        `עץ ${t.id}/${id}: "${c.value}" לא מופיע בהודעות השרת (${t.sources.join(', ')}) — ההודעה השתנתה?`,
      )
    }
  }
  for (const t of TOPICS) {
    for (const m of t.errorMatch ?? []) {
      if (!m.textIncludes) continue
      n++
      const sources = t.sources.map(readSrc).join('\n')
      assert(sources.includes(m.textIncludes), `${t.id}: "${m.textIncludes}" לא מופיע ב-sources`)
    }
  }
  console.log(`✓ כל ${n} ההודעות שהעזרה מזהה קיימות בקוד השרת שמחזיר אותן`)
}

function testSourcesAndDates(): void {
  const all = [...TOPICS, ...Object.values(FLOWS), ...TREES]
  for (const x of all) {
    assert(x.sources.length > 0, `${x.id}: חסרים sources`)
    for (const s of x.sources) assert(fs.existsSync(`${SRC}/${s}`), `${x.id}: קובץ מקור לא קיים ${s}`)
    assert(/^\d{4}-\d{2}-\d{2}$/.test(x.verifiedAt), `${x.id}: verifiedAt לא בפורמט תאריך`)
  }
  console.log('✓ לכל פריט יש קבצי מקור קיימים ותאריך אימות')
}

function testShortAnswers(): void {
  for (const t of TOPICS) {
    assert(t.answer.length <= 3, `${t.id}: יותר מ-3 שורות`)
    for (const v of t.variants ?? []) assert(v.answer.length >= 1 && v.answer.length <= 3, `${t.id}: וריאנט עם 1–3 שורות`)
    assert(t.answer.length > 0 || (t.variants ?? []).length > 0, `${t.id}: אין תשובה`)
    assert(t.title.length <= 50, `${t.id}: כותרת ארוכה מדי`)
    assert(t.title.endsWith('?'), `${t.id}: כותרת נושא היא שאלה`)
  }
  for (const f of Object.values(FLOWS)) {
    for (const s of f.steps) assert(s.text.length <= 70, `הדרכה ${f.id}: צעד ארוך מדי — "${s.text}"`)
  }
  console.log('✓ תשובות עד 3 שורות, כותרות קצרות, צעדי הדרכה בשורה אחת')
}

/** veya-copy: lexicon.md §2 + brand-voice.md + hebrew-writing-rules.md §1. */
const FORBIDDEN: readonly (string | RegExp)[] = [
  'מערכת', 'פלטפורמה', 'ממשק', 'דאשבורד', 'פיצ\'ר', 'באג', 'שרת', 'סנכרון', 'ולידציה', 'רשומה', 'יוזר',
  'אנא', 'יש למלא', 'לחץ כאן', 'אירעה שגיאה', 'שגוי', 'לא חוקי', 'אינו תקין', 'נכשל', 'חובה', 'אסור',
  'שימו לב', 'אזהרה', 'לצערנו', /(^|\s)אנו(\s|$)/, 'אל דאגה', 'בקלות', 'בכמה קליקים', 'RSVP', 'אורחים', 'שיבוץ',
  /(^|\s)אולי(\s|$)/, /(^|\s)(לחץ|הקש|בחר|הזן|שמור|ערוך|הוסף)(\s|$)/,
  '!!',
]

function testCopyRules(): void {
  for (const { where, text } of userTexts()) {
    for (const f of FORBIDDEN) {
      const hit = typeof f === 'string' ? text.includes(f) : f.test(text)
      assert(!hit, `${where}: מילה/ביטוי שאסור לפי veya-copy (${f}) — "${text}"`)
    }
    assert((text.match(/!/g) ?? []).length <= 1, `${where}: יותר מסימן קריאה אחד`)
  }
  console.log('✓ אין מילים אסורות, אין פנייה בלשון זכר יחיד, אין ז\'רגון')
}

/** Event-first: כל טקסט מתרנדר בכל סוג אירוע, ובלי "חתן/כלה/חתונה" באירוע אחר. */
function testEveryEventType(): void {
  let rendered = 0
  for (const type of EVENT_TYPES) {
    const ctx = ctxFor(type)
    for (const { where, text } of userTexts()) {
      const r = renderText(text, ctx)
      assert(r !== null, `${where}: לא מתרנדר באירוע ${type} — "${text}"`)
      if (type !== 'wedding' && type !== 'henna') {
        assert(!/חתן|כלה|חתונה/.test(r!), `${where}: "חתן/כלה/חתונה" באירוע ${type} — "${r}"`)
      }
      rendered++
    }
  }
  const business = renderText('איך מוסיפים {guest}?', ctxFor('business'))
  eq(business, 'איך מוסיפים משתתף?', 'אירוע עסקי: "משתתף"')
  console.log(`✓ ${rendered} טקסטים מתרנדרים נכון בכל ${EVENT_TYPES.length} סוגי האירוע`)
}

function testGiftsAreGated(): void {
  for (const t of TOPICS.filter((x) => x.area === 'gifts')) {
    assert(factsOf(t.when).includes('gifts.eligible'), `${t.id}: נושא מתנות חייב תנאי זכאות`)
  }
  console.log('✓ נושאי מתנות מוצגים רק לאירוע זכאי')
}

function testOnlyManagers(): void {
  // החלטת המייסד: מפיק/אולם לא מקבלים flows. כל נושא שמציע פעולה — רק למנהלי האירוע.
  const member: Facts = { ...FULL_FACTS, 'user.role': 'member' }
  for (const t of TOPICS) {
    const r = resolveTopic(t, { facts: member, text: ctxFor('wedding', member), flows: FLOWS })
    if (r) assert(r.primary === null, `${t.id}: מציע פעולה לחבר-אירוע (מפיק/אולם)`)
  }
  for (const f of Object.values(FLOWS)) assert(!holds(f.when, member), `הדרכה ${f.id} זמינה לחבר-אירוע`)
  console.log('✓ פעולות והדרכות — רק למנהלי האירוע (בעלים / בן-בת זוג)')
}


/**
 * כל מה שמצוטט במירכאות בתשובה ("…") בלי טוקן — חייב להופיע מילה במילה
 * באחד מקבצי המקור של הפריט. כך אי אפשר לצטט כפתור שלא קיים (או שהשם שלו
 * השתנה) גם כשהוא כתוב ישירות בקומפוננטה ולא ב-he.ts.
 */
function testQuotedLiteralsExist(): void {
  let n = 0
  const check = (where: string, text: string, sources: readonly string[]) => {
    const src = sources.map(readSrc).join('\n')
    for (const m of text.matchAll(/"([^"]+)"/g)) {
      const quoted = m[1]
      if (/\{[^}]*\}/.test(quoted)) continue // כפתור שמגיע מטוקן — נבדק ב-testUiTokensResolve
      n++
      assert(src.includes(quoted), `${where}: "${quoted}" לא מופיע בקבצי המקור (${sources.join(', ')})`)
    }
  }
  for (const t of TOPICS) {
    const texts = [t.title, ...t.answer, ...(t.variants ?? []).flatMap((v) => v.answer)]
    texts.forEach((x) => check(t.id, x, t.sources))
  }
  for (const f of Object.values(FLOWS)) [...f.steps.map((s) => s.text), f.doneText].forEach((x) => check(`הדרכה ${f.id}`, x, f.sources))
  for (const tr of TREES) {
    for (const [id, nd] of Object.entries(tr.nodes)) {
      if (nd.kind === 'outcome') nd.text.forEach((x) => check(`עץ ${tr.id}/${id}`, x, tr.sources))
      if (nd.kind === 'ask') nd.options.forEach((o) => check(`עץ ${tr.id}/${id}`, o.label, tr.sources))
      if (nd.kind === 'outcome' && nd.action?.label) check(`עץ ${tr.id}/${id}`, nd.action.label, tr.sources)
    }
  }
  console.log(`✓ כל ${n} הכפתורים/ההודעות שמצוטטים במירכאות קיימים מילה במילה בקוד`)
}

/**
 * כנות (החלטת המייסד 2026-09-29): טקסט שמתאר הודעה ש*יוצאת/נשלחת/מתקבלת* —
 * חייב להיות מסומן sendsMessages (ואז במצב הדגמה מוצגת הודעה כנה), או בעץ
 * שבודק את מצב השליחה לפני שמגיע לתוצאה. חריגים — רק משפטי שלילה, עם נימוק.
 */
const SENDING = /(יוצא|יוצאת|יוצאות|יצאה|יצא\b|נשלח|נשלחת|נשלחות|תצא|ייצאו|מקבלים|יקבלו|קיבל|שולחים)/
const HONEST_EXCEPTIONS: Record<string, string> = {
  'guests.fix-phones': 'רק שלילה: "לא נשלחות" — נכון גם במצב הדגמה',
  'rsvp.maybe': 'רק שלילה: "לא מקבלים עוד תזכורות"',
  'event.commit-date': 'רק שלילה: "לא יוצאות בקשות"',
}
function testSendingTextsAreHonest(): void {
  // חריג מיותר = חור בכלל. כל חריג חייב לתפוס באמת טקסט על שליחה.
  for (const id of Object.keys(HONEST_EXCEPTIONS)) {
    const t = TOPICS.find((x) => x.id === id)
    assert(!!t, `חריג לנושא שלא קיים: ${id}`)
    const texts = [t!.title, ...t!.answer, ...(t!.variants ?? []).flatMap((v) => v.answer)]
    assert(texts.some((x) => SENDING.test(x)), `החריג "${id}" מיותר — אין בו טקסט על שליחה. מוחקים אותו`)
  }
  let n = 0
  for (const t of TOPICS) {
    if (t.sendsMessages || HONEST_EXCEPTIONS[t.id]) continue
    const texts = [t.title, ...t.answer, ...(t.variants ?? []).flatMap((v) => v.answer)]
    for (const x of texts) {
      assert(!SENDING.test(x), `${t.id}: מדבר על שליחה בלי sendsMessages — "${x}"`)
    }
    n++
  }
  for (const f of Object.values(FLOWS)) {
    if (f.sendsMessages) continue
    for (const x of [...f.steps.map((s) => s.text), f.doneText]) {
      assert(!SENDING.test(x), `הדרכה ${f.id}: מדברת על שליחה בלי sendsMessages — "${x}"`)
    }
  }
  for (const tr of TREES) {
    if (tr.sendsMessages) continue
    const checksMode = (id: string): boolean => {
      const nd = tr.nodes[id]
      return nd?.kind === 'check' && 'fact' in nd.test && nd.test.fact === 'messaging.mode'
    }
    for (const [id, nd] of Object.entries(tr.nodes)) {
      if (nd.kind !== 'outcome') continue
      if (!nd.text.some((x) => SENDING.test(x))) continue
      // מותר רק אם העץ מתחיל בבדיקת מצב השליחה (ואז התוצאה הזו מגיעה רק במצב אמיתי).
      assert(checksMode(tr.root), `עץ ${tr.id}/${id}: מדבר על שליחה, והעץ לא בודק קודם את מצב WhatsApp`)
    }
  }
  console.log(`✓ כל טקסט שמתאר שליחה מסומן — במצב הדגמה תוצג הודעה כנה (${n} נושאים בלי שליחה)`)
}

function testSendingTopicsNeedKnownMode(): void {
  const base: Facts = { ...FULL_FACTS }
  delete base['messaging.mode']
  for (const t of TOPICS.filter((x) => x.sendsMessages)) {
    eq(resolveTopic(t, { facts: base, text: ctxFor('wedding', base), flows: FLOWS }), null, `${t.id}: מצב שליחה לא ידוע → לא מוצג`)
    const mock = resolveTopic(t, { facts: { ...FULL_FACTS, 'messaging.mode': 'mock' }, text: ctxFor(), flows: FLOWS })
    if (mock) eq(mock.mockNotice, true, `${t.id}: במצב הדגמה → הודעה כנה`)
    const live = resolveTopic(t, { facts: FULL_FACTS, text: ctxFor(), flows: FLOWS })
    if (live) eq(live.mockNotice, false, `${t.id}: במצב אמיתי → בלי הודעת הדגמה`)
  }
  console.log('✓ נושאים על שליחה: לא מוצגים כשהמצב לא ידוע, ובמצב הדגמה — תמיד עם הודעה כנה')
}

// ═══ חלק ב — המנוע ═════════════════════════════════════════════════════════

function testConditions(): void {
  const f: Facts = { 'guests.total': 5, 'user.role': 'owner' }
  eq(evaluate({ fact: 'guests.total', op: '>', value: 0 }, f), true, '> על מספר')
  eq(evaluate({ fact: 'guests.bad_phone', op: '>', value: 0 }, f), 'unknown', 'עובדה חסרה = לא ידוע')
  eq(evaluate({ not: { fact: 'guests.bad_phone', op: '>', value: 0 } }, f), 'unknown', 'not של לא-ידוע נשאר לא-ידוע')
  eq(evaluate({ all: [{ fact: 'guests.total', op: '>', value: 0 }, { fact: 'guests.bad_phone', op: '>', value: 0 }] }, f), 'unknown', 'all עם לא-ידוע')
  eq(evaluate({ all: [{ fact: 'guests.total', op: '>', value: 9 }, { fact: 'guests.bad_phone', op: '>', value: 0 }] }, f), false, 'all עם false גובר')
  eq(evaluate({ any: [{ fact: 'guests.bad_phone', op: '>', value: 0 }, { fact: 'user.role', op: 'in', value: ['owner'] }] }, f), true, 'any עם true גובר')
  eq(evaluate({ fact: 'guests.total', op: '>', value: 'x' }, f), 'unknown', 'השוואה בין סוגים שונים = לא ידוע')
  eq(holds(undefined, f), true, 'בלי תנאי = מותר')
  eq(holds({ fact: 'guests.bad_phone', op: '==', value: 0 }, f), false, 'holds דורש ודאות')
  console.log('✓ תנאים: לא-ידוע לעולם לא הופך ל"כן" או "לא" בטעות')
}

function testText(): void {
  const c = ctxFor('wedding', { 'guests.bad_phone': 1, 'guests.total': 3 })
  eq(renderText('{count:guests.bad_phone|guest:ל} אין מספר', c), 'למוזמן אחד אין מספר', 'יחיד עם ל')
  eq(renderText('{count:guests.total|guest:ל} אין', c), 'ל-3 מוזמנים אין', 'רבים עם ל-')
  eq(renderText('{count:guests.total|guest}', ctxFor('business', { 'guests.total': 1 })), 'משתתף אחד', 'עסקי יחיד')
  eq(renderText('{count:guests.total|שורה אחת|# שורות}', c), '3 שורות', 'צורות חופשיות')
  eq(renderText('לחצו "{ui:guests.addGuestButton}"', c), 'לחצו "הוספת מוזמן"', 'טקסט כפתור מ-he.ts')
  eq(renderText('{ui:guests.noSuchButton}', c), null, 'כפתור שלא קיים → לא מציגים')
  eq(renderText('{n:guests.bad_phone} ו-{n:guests.missing}', c), null, 'עובדה חסרה → כל השורה לא מוצגת')
  eq(renderText('{ui:guests.summary}', c), null, 'טקסט שהוא פונקציה (לא מחרוזת) → לא מוצג')
  eq(hebrewDate('2026-10-29'), 'יום חמישי, 29 באוקטובר', 'תאריך בעברית')
  eq(hebrewDate('29/10/2026'), null, 'תאריך בפורמט לא צפוי → null')
  console.log('✓ טקסט: לקסיקון, כפתורים, יחיד/רבים, תאריכים — ושורה שלא נשלמת לא מוצגת')
}

function rankCtx(scopes: ScopeId[], facts: Facts, extra: Partial<RankContext> = {}): RankContext {
  return {
    scopes,
    facts,
    text: ctxFor('wedding', facts),
    recentErrors: [],
    now: 1_000_000,
    notHelped: new Set(),
    flows: FLOWS,
    ...extra,
  }
}

const OWNER_DESKTOP: Facts = { 'user.role': 'owner', 'layout.guestCards': false, 'client.contactPicker': false }

function testRankAddForm(): void {
  // הדוגמה של המייסד: מוזמנים → הוספת מוזמן → פותחים עזרה.
  const r = rankTopics(TOPICS, rankCtx(['guests.addForm', 'guests'], OWNER_DESKTOP))
  eq(r.urgent, null, 'אין "חשוב עכשיו" בלי עובדה דחופה')
  eq(
    r.topics.map((t) => t.topic.id),
    ['guests.add-one', 'guests.add-many', 'guests.phone-format', 'guests.import-excel'],
    'בטופס הוספת מוזמן: 4 הנושאים הנכונים, בסדר הנכון',
  )
  eq(r.topics[0].title, 'איך מוסיפים מוזמן?', 'כותרת מרונדרת')
  eq(r.topics[0].primary?.action.kind, 'tour', '"תראו לי" זמין')
  console.log('✓ דירוג: בטופס הוספת מוזמן — 4 הנושאים מהדוגמה של המייסד')
}

function testRankUrgentAndUnknown(): void {
  const withBad = rankTopics(TOPICS, rankCtx(['guests'], { ...OWNER_DESKTOP, 'guests.bad_phone': 3 }))
  eq(withBad.urgent?.topic.id, 'guests.fix-phones', 'מספרים לא תקינים → "חשוב עכשיו"')
  eq(withBad.urgent?.answer[0], 'ל-3 מוזמנים אין מספר טלפון תקין. בלי מספר תקין לא נשלחות הזמנה ובקשות לאישור הגעה ב-WhatsApp.', 'המספר האמיתי בתשובה')
  eq(withBad.urgent?.primary?.action.kind, 'tour', 'יש מה לתקן → הדרכה זמינה')
  assert(withBad.topics.length <= 4 && !withBad.topics.some((t) => t.topic.id === 'guests.fix-phones'), 'הדחוף לא מופיע פעמיים')

  // לפני שלב 3 אין עובדות שרת: לא ממציאים "יש לכם 0 מספרים לא תקינים".
  const unknown = rankTopics(TOPICS, rankCtx(['guests'], OWNER_DESKTOP))
  eq(unknown.urgent, null, 'עובדה לא ידועה → אין דחוף')
  const fix = resolveTopic(TOPICS.find((t) => t.id === 'guests.fix-phones')!, rankCtx(['guests'], OWNER_DESKTOP))
  eq(fix?.primary, null, 'עובדה לא ידועה → לא מציעים הדרכה שאולי תוביל לרשימה ריקה')
  eq(fix?.answer.length, 1, 'עובדה לא ידועה → התשובה הכללית, בלי מספר מומצא')

  const zero = resolveTopic(TOPICS.find((t) => t.id === 'guests.fix-phones')!, rankCtx(['guests'], { ...OWNER_DESKTOP, 'guests.bad_phone': 0 }))
  eq(zero?.primary, null, 'אין מספרים לתקן → אין הדרכה')

  const member = rankTopics(TOPICS, rankCtx(['guests.addForm', 'guests'], { ...OWNER_DESKTOP, 'user.role': 'member' }))
  eq(member.topics.map((t) => t.topic.id), ['guests.people-count'], 'חבר-אירוע: רק הסבר כללי, בלי פעולות')
  console.log('✓ דירוג: דחוף רק כשבאמת ידוע, ועובדה חסרה לא מייצרת תשובה מומצאת')
}

function testRankErrorBoostAndPenalty(): void {
  const err: RecentError = { method: 'POST', path: '/guests', status: 422, message: 'נראה שהמספר 123 לא תקין. מספר נייד מתחיל ב-05', at: 1_000_000 - 1000 }
  const r = rankTopics(TOPICS, rankCtx(['guests.addForm', 'guests'], OWNER_DESKTOP, { recentErrors: [err] }))
  eq(r.topics[0].topic.id, 'guests.phone-format', 'שגיאה של עכשיו מקפיצה את הנושא שלה לראש')
  eq(r.topics[0].errorHit, true, 'מסומן כקשור לשגיאה')
  const old = { ...err, at: 1_000_000 - ERROR_RECENCY_MS - 1 }
  const r2 = rankTopics(TOPICS, rankCtx(['guests.addForm', 'guests'], OWNER_DESKTOP, { recentErrors: [old] }))
  eq(r2.topics[0].topic.id, 'guests.add-one', 'שגיאה ישנה (מעל 5 דקות) לא משפיעה')
  const r3 = rankTopics(TOPICS, rankCtx(['guests.addForm', 'guests'], OWNER_DESKTOP, { notHelped: new Set(['guests.add-one']) }))
  eq(r3.topics[0].topic.id, 'guests.add-many', '"עדיין לא" מוריד את הנושא')
  const again = rankTopics(TOPICS, rankCtx(['guests.addForm', 'guests'], OWNER_DESKTOP))
  eq(again.topics.map((t) => t.topic.id), rankTopics(TOPICS, rankCtx(['guests.addForm', 'guests'], OWNER_DESKTOP)).topics.map((t) => t.topic.id), 'אותו הקשר → אותה תוצאה')
  console.log('✓ דירוג: שגיאה עדכנית מקפיצה, "עדיין לא" מוריד, ותמיד דטרמיניסטי')
}

function testLayoutVariants(): void {
  const t = TOPICS.find((x) => x.id === 'guests.delete')!
  const desk = resolveTopic(t, rankCtx(['guests'], OWNER_DESKTOP))
  const phone = resolveTopic(t, rankCtx(['guests'], { ...OWNER_DESKTOP, 'layout.guestCards': true }))
  assert(!!desk && desk.answer[0].includes('"מחיקה"'), 'דסקטופ: כפתור "מחיקה" בשורה')
  assert(!!phone && phone.answer[0].includes('הסרת המוזמן מהרשימה'), 'טלפון: בתוך חלון העריכה')
  const contacts = TOPICS.find((x) => x.id === 'guests.contacts')!
  const iphone = resolveTopic(contacts, rankCtx(['guests'], OWNER_DESKTOP))
  assert(!!iphone && iphone.answer[0].includes('Chrome באנדרואיד'), 'אייפון: אומרים בכנות שאנשי קשר לא זמינים')
  eq(iphone?.primary?.action, { kind: 'tour', flow: 'paste-list', label: 'תראו לי איך מדביקים' }, 'ומציעים את הדרך שכן עובדת')
  const many = resolveTopic(TOPICS.find((x) => x.id === 'guests.add-many')!, rankCtx(['guests'], OWNER_DESKTOP))
  assert(!!many && !many.answer[0].includes('אנשי קשר'), 'אייפון: "ייבוא מאנשי קשר" לא מוצג כאפשרות')
  console.log('✓ תשובות לפי הפריסה האמיתית (שורה/כרטיס) ולפי מה שהדפדפן תומך בו')
}

function testDiagnose(): void {
  const tree = TREES.find((t) => t.id === 'guest-save-failed')!
  const run = (facts: Facts) => runTree(tree, facts).step
  const outcomeOf = (facts: Facts) => {
    const s = run(facts)
    return s.kind === 'outcome' ? s.node : s.kind
  }
  eq(outcomeOf({}), 'out-no-error', 'בלי שגיאה → לא מנחשים')
  eq(outcomeOf({ 'error.last.status': 0 }), 'out-offline', 'אין רשת')
  eq(outcomeOf({ 'error.last.status': 422, 'error.last.message': 'נראה שהמספר 12 לא תקין. מספר נייד מתחיל ב-05' }), 'out-phone', 'טלפון')
  eq(outcomeOf({ 'error.last.status': 422, 'error.last.message': 'שם מלא הוא שדה חובה' }), 'out-name', 'שם')
  eq(outcomeOf({ 'error.last.status': 422, 'error.last.message': 'כמות אנשים חייבת להיות לפחות 1' }), 'out-count', 'כמות')
  eq(outcomeOf({ 'error.last.status': 422, 'error.last.message': 'משהו אחר' }), 'out-unknown', 'לא מזוהה → אומרים שלא זיהינו')
  eq(outcomeOf({ 'error.last.status': 422 }), 'out-unknown', 'יש שגיאה בלי הודעה → לא מזוהה')

  const imp = TREES.find((t) => t.id === 'import-failed')!
  const serverMessages: [string, string][] = [
    ["לא זוהו עמודות חובה. ודא שיש עמודות 'שם' ו'טלפון' בקובץ.", 'out-columns'],
    ['הקובץ גדול מדי (מעל 5MB) — פצלו אותו לקובץ קטן יותר.', 'out-size'],
    ['הרשימה ארוכה מדי. נא לפצל להדבקות קטנות יותר.', 'out-long'],
    ['הקובץ מכיל יותר מ-5000 שורות — פצלו אותו לכמה קבצים קטנים יותר.', 'out-rows'],
    ['פורמט קובץ לא נתמך. נא להעלות קובץ .xlsx או .csv', 'out-format'],
    ['הקובץ ריק או ללא כותרות', 'out-empty'],
    ['לא הצלחנו לקרוא את הקובץ. בדקו שהקובץ תקין ונסו שוב.', 'out-unreadable'],
  ]
  for (const [msg, expected] of serverMessages) {
    const s = runTree(imp, { 'error.last.status': 400, 'error.last.message': msg }).step
    eq(s.kind === 'outcome' ? s.node : s.kind, expected, `ייבוא: "${msg.slice(0, 25)}…"`)
  }
  const trace = runTree(tree, { 'error.last.status': 422, 'error.last.message': 'שם מלא הוא שדה חובה' }).trace
  eq(trace.map((t) => t.node), ['offline', 'phone', 'name'], 'המסלול נשמר (בלי ערכים — רק צמתים)')
  console.log('✓ עצי תקלות: כל הודעת שרת אמיתית מגיעה לפתרון הנכון, ובלי שגיאה — לא מנחשים')
}

function testErrorFactsAreScoped(): void {
  const now = 1_000_000
  const tree = TREES.find((t) => t.id === 'import-failed')!
  const unrelated: RecentError = { method: 'GET', path: '/stats', status: 500, at: now - 10 }
  const related: RecentError = { method: 'POST', path: '/guests/import/preview', status: 400, message: 'הקובץ ריק או ללא כותרות', at: now - 60_000 }
  eq(errorFactsFor(tree.errorMatch, [related, unrelated], now)['error.last.path'], '/guests/import/preview', 'רק השגיאה ששייכת לעץ')
  eq(errorFactsFor(tree.errorMatch, [unrelated], now), {}, 'שגיאה לא קשורה לא נכנסת לעץ')
  eq(errorFactsFor(tree.errorMatch, [{ ...related, at: now - ERROR_RECENCY_MS - 1 }], now), {}, 'שגיאה ישנה לא נכנסת')
  const facts = { 'user.role': 'owner' as const }
  eq(treeForRecentError(TREES, { facts, recentErrors: [related], now })?.id, 'import-failed', '"צריכים עזרה עם זה?" פותח את העץ הנכון')
  eq(treeForRecentError(TREES, { facts, recentErrors: [unrelated], now }), null, 'שגיאה בלי עץ מתאים → אין עץ')
  console.log('✓ עצי תקלות רואים רק את השגיאה שלהם, מ-5 הדקות האחרונות')
}

function testSearch(): void {
  const items = TOPICS.map((t) => ({ id: t.id, texts: [t.title.replace(/\{[^}]*\}/g, ''), ...t.aliases] }))
  eq(normalize('מוזמן חדש!'), 'מוזמנ חדש', 'נרמול: סופיות ופיסוק')
  eq(search('איך מוסיפים אורח', items)[0], 'guests.add-one', '"אורח" (מילה שלא אומרים בממשק) עדיין נמצא')
  eq(search('מספר מחו"ל', items)[0], 'guests.phone-format', 'מספר מחו"ל')
  eq(search('מחיקת מוזמן', items)[0], 'guests.delete', 'מחיקה')
  eq(search('אקסל', items)[0], 'guests.import-excel', 'אקסל → ייבוא קודם')
  eq(search('איך מה למה', items), [], 'רק מילים ריקות → אין תוצאות')
  eq(search('מזג אוויר בפריז', items), [], 'בלי התאמה אמיתית → אין תוצאה מומצאת')
  console.log('✓ חיפוש: מוצא לפי מילים אמיתיות, ולא מחזיר תוצאות סרק')
}

function testLadder(): void {
  const far: Facts = { 'event.days_to_event': 30 }
  const soon: Facts = { 'event.days_to_event': 2 }
  eq(teamOption(NO_ATTEMPTS, soon), 'hidden', 'לפני ניסיון — לא מציעים צוות, גם כשהאירוע קרוב')
  eq(teamOption({ ...NO_ATTEMPTS, notHelped: 1 }, far), 'available', 'אחרי "עדיין לא" — זמין בשקט')
  eq(teamOption({ ...NO_ATTEMPTS, tour: 'abandoned' }, far), 'available', 'אחרי הדרכה שננטשה — זמין')
  eq(teamOption({ ...NO_ATTEMPTS, tour: 'completed' }, far), 'hidden', 'הדרכה שהצליחה — אין סיבה לצוות')
  eq(teamOption({ ...NO_ATTEMPTS, notHelped: 1 }, soon), 'prominent', 'יומיים לאירוע — בולט יותר (אחרי ניסיון)')
  eq(teamOption({ ...NO_ATTEMPTS, diagnosis: 'veya_side' }, far), 'prominent', 'הבעיה אצלנו — בולט')
  eq(teamOption({ ...NO_ATTEMPTS, diagnosis: 'user_fix' }, {}), 'available', 'בלי תאריך ידוע — לא מבליטים')
  eq(teamOption({ ...NO_ATTEMPTS, notHelped: 1 }, { 'event.days_to_event': -1 }), 'available', 'אירוע שעבר — לא דחוף')
  console.log('✓ צוות VEYA: רק אחרי ניסיון; בולט רק כשדחוף באמת')
}

// ─── הרצה ──────────────────────────────────────────────────────────────────

testUniqueIds()
testFactsExist()
testUiTokensResolve()
testActionsPointToRealThings()
testFlowsUseRealTargetsAndApis()
testTreesAreSound()
testTreeErrorTextsExistInServer()
testSourcesAndDates()
testShortAnswers()
testCopyRules()
testEveryEventType()
testGiftsAreGated()
testOnlyManagers()
testQuotedLiteralsExist()
testSendingTextsAreHonest()
testSendingTopicsNeedKnownMode()
testConditions()
testText()
testRankAddForm()
testRankUrgentAndUnknown()
testRankErrorBoostAndPenalty()
testLayoutVariants()
testDiagnose()
testErrorFactsAreScoped()
testSearch()
testLadder()
console.log('OK — בסיס הידע והמנוע של העזרה תקינים.')
