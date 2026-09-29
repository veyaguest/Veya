/**
 * בחירת הנושאים שמוצגים — "3–4 אפשרויות נכונות, לא 30" (HELP_CENTER_PLAN.md §7.4).
 *
 * דטרמיניסטי לגמרי: אותו הקשר → אותה רשימה, באותו סדר. אין אקראיות ואין
 * "למידה". נבדק ב-helpKb.test.ts.
 *
 * נושא מוצג רק אם:
 *  1. התנאי שלו מתקיים **בוודאות** (עובדה חסרה = לא מציגים);
 *  2. כל שורות התשובה שלו נרנדרות (אין טוקן שאי אפשר למלא);
 *  3. הוא קשור למקום שבו המשתמש נמצא, לשגיאה שקרתה עכשיו, או למשהו דחוף.
 */
import type { DiagnosticTree, ErrorMatch, GuidedFlow, HelpAction, HelpTopic } from '../types'
import type { Facts } from '../facts'
import type { ScopeId } from '../scopes'
import { holds } from './conditions'
import { renderText } from './text'
import type { TextContext } from './text'

/** שגיאה אחרונה, כפי שהיא נשמרת ב-help/errorBus.ts. */
export interface RecentError {
  method: string
  path: string
  status: number
  message?: string
  at: number
}

export interface RankContext {
  /** ה-scopes הפעילים, מהספציפי לכללי (help/scopes.ts::activeScopes). */
  scopes: readonly ScopeId[]
  facts: Facts
  text: TextContext
  recentErrors: readonly RecentError[]
  now: number
  /** נושאים שהמשתמש כבר סימן עליהם "עדיין לא" בפתיחה הזו. */
  notHelped: ReadonlySet<string>
  /** לבדיקה שהדרכה עדיין מותרת (flow.when). */
  flows: Readonly<Record<string, GuidedFlow>>
}

export interface ResolvedAction {
  action: HelpAction
  /** התווית המרונדרת, אם יש (אחרת ה-UI משתמש בברירת מחדל לסוג הפעולה). */
  label: string | null
}

export interface ResolvedTopic {
  topic: HelpTopic
  title: string
  answer: string[]
  primary: ResolvedAction | null
  /**
   * להציג לידו את הודעת "WhatsApp במצב הדגמה" (kb/shared.ts). נקבע רק
   * מהעובדה ``messaging.mode`` — אף פעם לא מניחים.
   */
  mockNotice: boolean
  score: number
  urgent: boolean
  errorHit: boolean
}

/** שגיאה נחשבת "עכשיו" עד 5 דקות אחרי שקרתה. */
export const ERROR_RECENCY_MS = 5 * 60 * 1000

export const MAX_TOPICS = 4

export function errorMatches(match: ErrorMatch, e: RecentError): boolean {
  if (match.path !== e.path) return false
  if (match.method && match.method.toUpperCase() !== e.method) return false
  if (match.status !== undefined && match.status !== e.status) return false
  if (match.textIncludes && !(e.message ?? '').includes(match.textIncludes)) return false
  return true
}

/** האם אחת השגיאות מה-5 דקות האחרונות מתאימה. */
export function hitsRecentError(
  matches: readonly ErrorMatch[] | undefined,
  errors: readonly RecentError[],
  now: number,
): boolean {
  if (!matches?.length) return false
  return errors.some((e) => now - e.at <= ERROR_RECENCY_MS && matches.some((m) => errorMatches(m, e)))
}

/** משקל ה-scope הגבוה ביותר של הנושא מבין ה-scopes הפעילים. */
export function scopeScore(
  topicScopes: readonly { scope: ScopeId; weight: number }[],
  active: readonly ScopeId[],
): number {
  let best = 0
  for (const s of topicScopes) if (active.includes(s.scope)) best = Math.max(best, s.weight)
  return best
}

function resolveAction(
  action: HelpAction | undefined | null,
  ctx: Pick<RankContext, 'facts' | 'text' | 'flows'>,
): ResolvedAction | null {
  if (!action) return null
  if (action.kind === 'tour') {
    const flow = ctx.flows[action.flow]
    if (!flow || !holds(flow.when, ctx.facts)) return null
    if (flow.sendsMessages && messagingMode(ctx.facts) === null) return null
  }
  if (action.label === undefined) return { action, label: null }
  const label = renderText(action.label, ctx.text)
  return label === null ? null : { action, label }
}

/**
 * מרנדר נושא אחד מול ההקשר. ``null`` = לא מציגים אותו עכשיו (התנאי לא
 * מתקיים בוודאות, או ששורה בתשובה לא ניתנת למילוי).
 */
export function resolveTopic(
  topic: HelpTopic,
  ctx: Pick<RankContext, 'facts' | 'text' | 'flows'>,
): Omit<ResolvedTopic, 'score' | 'urgent' | 'errorHit'> | null {
  if (!holds(topic.when, ctx.facts)) return null
  // נושא על הודעות — רק כשידוע באמת אם הן יוצאות (לא מרמזים שיצאו כשלא).
  const mode = topic.sendsMessages ? messagingMode(ctx.facts) : null
  if (topic.sendsMessages && mode === null) return null
  const variant = topic.variants?.find((v) => holds(v.when, ctx.facts))
  if (topic.variants?.length && !variant && topic.answer.length === 0) return null
  const lines = variant ? variant.answer : topic.answer
  const answer: string[] = []
  for (const line of lines) {
    const r = renderText(line, ctx.text)
    if (r === null) return null
    answer.push(r)
  }
  const title = renderText(topic.title, ctx.text)
  if (title === null || answer.length === 0) return null
  const primaryDef = variant && variant.primary !== undefined ? variant.primary : topic.primary
  return { topic, title, answer, primary: resolveAction(primaryDef, ctx), mockNotice: mode === 'mock' }
}

/** מצב השליחה של WhatsApp, רק אם ידוע בוודאות. */
export function messagingMode(facts: Facts): 'mock' | 'live' | null {
  const m = facts['messaging.mode']
  return m === 'mock' || m === 'live' ? m : null
}

/**
 * הבית של העזרה: נושא דחוף אחד (אם יש) + עד 4 נושאים.
 * נושא שאינו קשור למקום/לשגיאה/לדחיפות — לא מוצג בכלל בבית (רק בחיפוש).
 */
export function rankTopics(
  topics: readonly HelpTopic[],
  ctx: RankContext,
): { urgent: ResolvedTopic | null; topics: ResolvedTopic[] } {
  const ranked: ResolvedTopic[] = []
  for (const topic of topics) {
    const resolved = resolveTopic(topic, ctx)
    if (!resolved) continue
    const scope = scopeScore(topic.scopes, ctx.scopes)
    const errorHit = hitsRecentError(topic.errorMatch, ctx.recentErrors, ctx.now)
    const urgent = topic.urgentWhen !== undefined && holds(topic.urgentWhen, ctx.facts)
    if (scope === 0 && !errorHit && !urgent) continue
    const score =
      scope +
      (errorHit ? 80 : 0) +
      (urgent ? 40 : 0) +
      (topic.priority ?? 0) -
      (ctx.notHelped.has(topic.id) ? 15 : 0)
    ranked.push({ ...resolved, score, urgent, errorHit })
  }
  ranked.sort((a, b) => b.score - a.score || a.topic.id.localeCompare(b.topic.id))
  const urgent = ranked.find((t) => t.urgent) ?? null
  const rest = ranked.filter((t) => t !== urgent).slice(0, MAX_TOPICS)
  return { urgent, topics: rest }
}

/**
 * עובדות ``error.last.*`` לעץ תקלות — **רק** מהשגיאה האחרונה שמתאימה לעץ
 * (ומ-5 הדקות האחרונות). שגיאה לא קשורה (למשל טעינה שנכשלה במסך אחר) לא
 * נכנסת, כדי שהעץ לא יסיק מסקנה משגיאה שאינה שלו. אין התאמה → אין עובדות
 * שגיאה, והעץ הולך לענף "לא ידוע".
 */
export function errorFactsFor(
  matches: readonly ErrorMatch[] | undefined,
  errors: readonly RecentError[],
  now: number,
): Facts {
  if (!matches?.length) return {}
  for (let i = errors.length - 1; i >= 0; i--) {
    const e = errors[i]
    if (now - e.at > ERROR_RECENCY_MS) continue
    if (!matches.some((m) => errorMatches(m, e))) continue
    const facts: Facts = {
      'error.last.method': e.method,
      'error.last.path': e.path,
      'error.last.status': e.status,
    }
    if (e.message) facts['error.last.message'] = e.message
    return facts
  }
  return {}
}

/** עץ התקלות שמתאים לשגיאה שקרתה עכשיו (לכניסה מ"צריכים עזרה עם זה?"). */
export function treeForRecentError(
  trees: readonly DiagnosticTree[],
  ctx: Pick<RankContext, 'facts' | 'recentErrors' | 'now'>,
): DiagnosticTree | null {
  // השגיאה האחרונה קודם — היא זו שהמשתמש רואה עכשיו.
  const errors = [...ctx.recentErrors].reverse()
  for (const e of errors) {
    if (ctx.now - e.at > ERROR_RECENCY_MS) continue
    const hit = trees.find(
      (t) => holds(t.when, ctx.facts) && (t.errorMatch ?? []).some((m) => errorMatches(m, e)),
    )
    if (hit) return hit
  }
  return null
}
