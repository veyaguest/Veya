/**
 * איזה context כל מסך צריך מהשרת — נגזר **מבסיס הידע עצמו**.
 *
 * החלטת המייסד (2026-09-29): לא API כללי של "כל פרטי האירוע", אלא context
 * מצומצם ומפורש לכל מסך ולכל בדיקה על מוזמן. הרשימות בשרת
 * (backend/app/help_contexts.json) חייבות להיות **זהות** למה שמחושב כאן —
 * לא יותר (שלא יצא מידע שאין בו צורך) ולא פחות (שלא תחסר עובדה ותוצג
 * תשובה חלקית). נאכף ב-helpContexts.test.ts.
 *
 * רק עובדות ``source: 'server'`` נכנסות. עובדות דפדפן/משתמש/שגיאה לא נשלחות
 * מהשרת בכלל.
 */
import { FACTS } from './facts'
import type { FactId } from './facts'
import type { ScopeId } from './scopes'
import { factsOf } from './engine/conditions'
import { tokensOf } from './engine/text'
import { FLOWS, TOPICS, TREES } from './kb/index'
import type { Condition, DiagnosticTree, GuidedFlow, HelpAction, HelpTopic } from './types'

export type HelpScreen = 'dashboard' | 'guests' | 'messages' | 'rsvp' | 'hall' | 'finance' | 'gifts'

export const HELP_SCREENS: readonly HelpScreen[] = ['dashboard', 'guests', 'messages', 'rsvp', 'hall', 'finance', 'gifts']

/** לאיזה מסך שייך scope. ``account`` הוא חלון מעל כל מסך — בלי context משלו. */
export function screenOfScope(scope: ScopeId): HelpScreen | null {
  const head = scope.split('.')[0]
  return (HELP_SCREENS as readonly string[]).includes(head) ? (head as HelpScreen) : null
}

/**
 * עובדות שהמנוע עצמו קורא, בלי שיופיעו בתנאי של פריט מסוים:
 * - ``messaging.mode`` — כל פריט ``sendsMessages`` (הודעת הדגמה כנה / הסתרה).
 * - ``event.days_to_event`` — engine/ladder.ts (מתי להבליט את צוות VEYA),
 *   בכל מסך שיש בו עזרה בכלל.
 */
const MODE_FACT = 'messaging.mode'
const LADDER_FACT = 'event.days_to_event'

const isServer = (f: string) => (FACTS as Record<string, { source: string }>)[f]?.source === 'server'

function textFacts(texts: readonly string[]): string[] {
  return texts.flatMap((t) =>
    tokensOf(t).filter((x) => ['n', 'date', 'text', 'count'].includes(x.kind) && x.arg).map((x) => x.arg!),
  )
}

function condFacts(conds: readonly (Condition | undefined)[]): string[] {
  return conds.flatMap(factsOf)
}

function flowFacts(flow: GuidedFlow): string[] {
  return [
    ...(flow.sendsMessages ? [MODE_FACT] : []),
    ...condFacts([flow.when, ...flow.steps.map((s) => s.when)]),
    ...textFacts([...flow.steps.map((s) => s.text), flow.doneText]),
  ]
}

function actionFacts(action: HelpAction | null | undefined): string[] {
  if (!action) return []
  if (action.kind === 'tour') return FLOWS[action.flow] ? flowFacts(FLOWS[action.flow]) : []
  // עץ שנפתח מתוך נושא — העובדות שלו נכנסות דרך ה-scopes של העץ עצמו.
  return []
}

function topicFacts(t: HelpTopic): string[] {
  return [
    ...(t.sendsMessages ? [MODE_FACT] : []),
    ...condFacts([t.when, t.urgentWhen, ...(t.variants ?? []).map((v) => v.when)]),
    ...textFacts([t.title, ...t.answer, ...(t.variants ?? []).flatMap((v) => v.answer)]),
    ...actionFacts(t.primary),
    ...(t.variants ?? []).flatMap((v) => actionFacts(v.primary)),
  ]
}

/** עובדות שהעץ עצמו בודק או מציג (בלי העובדות של הפעולות בתוצאות). */
function treeOwnFacts(t: DiagnosticTree): string[] {
  const out: string[] = [
    ...(t.sendsMessages ? [MODE_FACT] : []),
    ...condFacts([t.when]),
    ...textFacts([t.symptom]),
  ]
  for (const n of Object.values(t.nodes)) {
    if (n.kind === 'check') out.push(...factsOf(n.test))
    if (n.kind === 'outcome') out.push(...textFacts(n.text))
    if (n.kind === 'ask') out.push(...textFacts([n.question, ...n.options.map((o) => o.label)]))
  }
  return out
}

function treeActionFacts(t: DiagnosticTree): string[] {
  return Object.values(t.nodes).flatMap((n) => (n.kind === 'outcome' ? actionFacts(n.action) : []))
}

export interface ContextSpec {
  screens: Record<HelpScreen, FactId[]>
  guest_checks: Record<string, FactId[]>
}

/** ה-context המינימלי לכל מסך ולכל בדיקת מוזמן, כפי שבסיס הידע דורש. */
export function requiredContexts(): ContextSpec {
  const screens = Object.fromEntries(HELP_SCREENS.map((s) => [s, new Set<string>()])) as Record<HelpScreen, Set<string>>
  const add = (scopes: readonly { scope: ScopeId }[], facts: string[]) => {
    for (const { scope } of scopes) {
      const screen = screenOfScope(scope)
      if (!screen) continue
      // מסך שיש בו עזרה כלשהי — צריך גם את עובדת הסולם (מתי להבליט צוות).
      for (const f of [...facts, LADDER_FACT]) if (isServer(f) && !f.startsWith('guest.')) screens[screen].add(f)
    }
  }
  for (const t of TOPICS) add(t.scopes, topicFacts(t))
  const guestChecks: Record<string, FactId[]> = {}
  for (const t of TREES) {
    if (t.needsGuest) {
      // בדיקת מוזמן: השרת מחזיר רק את מה שהעץ בודק/מציג (כולל guest.*).
      guestChecks[t.id] = [...new Set(treeOwnFacts(t).filter(isServer))].sort() as FactId[]
      add(t.scopes, treeActionFacts(t))
    } else {
      add(t.scopes, [...treeOwnFacts(t), ...treeActionFacts(t)])
    }
  }
  return {
    screens: Object.fromEntries(
      HELP_SCREENS.map((s) => [s, [...screens[s]].sort()]),
    ) as Record<HelpScreen, FactId[]>,
    guest_checks: Object.fromEntries(Object.entries(guestChecks).sort(([a], [b]) => a.localeCompare(b))),
  }
}
