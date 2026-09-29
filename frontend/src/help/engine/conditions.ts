/**
 * הערכת תנאים — שלושה ערכים: ``true`` / ``false`` / ``'unknown'``.
 *
 * למה לא בוליאני: עובדה חסרה (השרת לא ענה, או שהיא עוד לא נאספה) היא לא
 * "לא". אם היינו הופכים אותה ל-false, ``not`` היה הופך אותה ל-true — והעזרה
 * הייתה אומרת "יש לכם מספר תקין" בלי שבדקה. לכן חסר = לא ידוע, וכל שכבה
 * מעל מחליטה מה לעשות עם זה (בד"כ: לא להציג; בעץ תקלות: ענף "אי אפשר לבדוק").
 *
 * פונקציה טהורה — נבדקת ב-node.
 */
import type { Condition, FactCondition } from '../types'
import type { Facts } from '../facts'

export type Tri = true | false | 'unknown'

function compare(c: FactCondition, facts: Facts): Tri {
  const actual = facts[c.fact]
  if (actual === undefined || actual === null) return 'unknown'
  const v = c.value
  switch (c.op) {
    case '==':
      return actual === v
    case '!=':
      return actual !== v
    case '>':
      return typeof actual === 'number' && typeof v === 'number' ? actual > v : 'unknown'
    case '>=':
      return typeof actual === 'number' && typeof v === 'number' ? actual >= v : 'unknown'
    case '<':
      return typeof actual === 'number' && typeof v === 'number' ? actual < v : 'unknown'
    case '<=':
      return typeof actual === 'number' && typeof v === 'number' ? actual <= v : 'unknown'
    case 'in':
      return Array.isArray(v) ? (v as readonly unknown[]).includes(actual) : 'unknown'
    case 'includes':
      return typeof actual === 'string' && typeof v === 'string' ? actual.includes(v) : 'unknown'
  }
}

export function evaluate(cond: Condition, facts: Facts): Tri {
  if ('all' in cond) {
    let sawUnknown = false
    for (const c of cond.all) {
      const r = evaluate(c, facts)
      if (r === false) return false
      if (r === 'unknown') sawUnknown = true
    }
    return sawUnknown ? 'unknown' : true
  }
  if ('any' in cond) {
    let sawUnknown = false
    for (const c of cond.any) {
      const r = evaluate(c, facts)
      if (r === true) return true
      if (r === 'unknown') sawUnknown = true
    }
    return sawUnknown ? 'unknown' : false
  }
  if ('not' in cond) {
    const r = evaluate(cond.not, facts)
    return r === 'unknown' ? 'unknown' : !r
  }
  return compare(cond, facts)
}

/** "מותר להציג?" — רק כשהתנאי **בוודאות** מתקיים (או כשאין תנאי). */
export function holds(cond: Condition | undefined, facts: Facts): boolean {
  return cond === undefined || evaluate(cond, facts) === true
}

/** כל העובדות שתנאי מתייחס אליהן (לבדיקות השלמות). */
export function factsOf(cond: Condition | undefined): string[] {
  if (!cond) return []
  if ('all' in cond) return cond.all.flatMap(factsOf)
  if ('any' in cond) return cond.any.flatMap(factsOf)
  if ('not' in cond) return factsOf(cond.not)
  return [cond.fact]
}
