/**
 * מעבר על עץ תקלות (HELP_CENTER_PLAN.md §8) — פונקציה טהורה.
 *
 * כל צעד נקבע רק מהעובדות ומהתשובות שהמשתמש כבר נתן בכפתורים. אין ניחוש:
 * בדיקה שהעובדה שלה חסרה הולכת לענף ``unknown`` של הצומת, ואם אין כזה —
 * לתוצאה ``cant-check`` ("לא הצלחנו לבדוק את זה מכאן"), שמאפשרת לפנות לצוות.
 */
import type { DiagNode, DiagnosticTree } from '../types'
import type { Facts } from '../facts'
import { evaluate } from './conditions'

export type TraceEntry =
  | { node: string; kind: 'check'; result: 'yes' | 'no' | 'unknown' }
  | { node: string; kind: 'ask'; option: number }

export type DiagStep =
  | { kind: 'ask'; node: string; def: Extract<DiagNode, { kind: 'ask' }> }
  | { kind: 'outcome'; node: string; def: Extract<DiagNode, { kind: 'outcome' }> }
  /** בדיקה בלי עובדה ובלי ענף חלופי — לא יודעים, ולא מנחשים. */
  | { kind: 'cant-check'; node: string }

export interface DiagResult {
  step: DiagStep
  /** המסלול שנעשה — עובר להסלמה ולאנליטיקס (בלי ערכים, רק צמתים ותוצאות). */
  trace: TraceEntry[]
}

/** מגן מלולאה בעץ פגום. עץ תקין קצר בהרבה (נבדק ב-helpKb.test.ts). */
const MAX_STEPS = 40

/**
 * @param answers לכל צומת ``ask`` שכבר נענה — אינדקס הכפתור שנבחר.
 */
export function runTree(
  tree: DiagnosticTree,
  facts: Facts,
  answers: Readonly<Record<string, number>> = {},
): DiagResult {
  const trace: TraceEntry[] = []
  let id = tree.root
  for (let i = 0; i < MAX_STEPS; i++) {
    const node = tree.nodes[id]
    if (!node) throw new Error(`help: צומת חסר "${id}" בעץ ${tree.id}`)
    if (node.kind === 'outcome') return { step: { kind: 'outcome', node: id, def: node }, trace }
    if (node.kind === 'ask') {
      const chosen = answers[id]
      if (chosen === undefined || !node.options[chosen]) {
        return { step: { kind: 'ask', node: id, def: node }, trace }
      }
      trace.push({ node: id, kind: 'ask', option: chosen })
      id = node.options[chosen].next
      continue
    }
    const r = evaluate(node.test, facts)
    if (r === 'unknown') {
      trace.push({ node: id, kind: 'check', result: 'unknown' })
      if (!node.unknown) return { step: { kind: 'cant-check', node: id }, trace }
      id = node.unknown
      continue
    }
    trace.push({ node: id, kind: 'check', result: r ? 'yes' : 'no' })
    id = r ? node.yes : node.no
  }
  throw new Error(`help: העץ ${tree.id} ארוך מדי או מכיל לולאה`)
}

/** כל הצמתים שאפשר להגיע אליהם מהשורש (לבדיקות השלמות). */
export function reachableNodes(tree: DiagnosticTree): Set<string> {
  const seen = new Set<string>()
  const stack = [tree.root]
  while (stack.length) {
    const id = stack.pop()!
    if (seen.has(id)) continue
    seen.add(id)
    const n = tree.nodes[id]
    if (!n) continue
    if (n.kind === 'check') stack.push(n.yes, n.no, ...(n.unknown ? [n.unknown] : []))
    if (n.kind === 'ask') stack.push(...n.options.map((o) => o.next))
  }
  return seen
}

/** האם יש מעגל בעץ (מסלול שחוזר לצומת שכבר עבר בו). */
export function hasCycle(tree: DiagnosticTree): boolean {
  const state = new Map<string, 'visiting' | 'done'>()
  const visit = (id: string): boolean => {
    const s = state.get(id)
    if (s === 'visiting') return true
    if (s === 'done') return false
    state.set(id, 'visiting')
    const n = tree.nodes[id]
    const next =
      !n ? [] :
      n.kind === 'check' ? [n.yes, n.no, ...(n.unknown ? [n.unknown] : [])] :
      n.kind === 'ask' ? n.options.map((o) => o.next) : []
    for (const x of next) if (visit(x)) return true
    state.set(id, 'done')
    return false
  }
  return visit(tree.root)
}
