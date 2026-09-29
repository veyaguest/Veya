/**
 * הדרכות ("תראו לי") — החלק הטהור: מתי מותר להתחיל, ואילו צעדים רלוונטיים.
 *
 * ההרצה עצמה (סימון, המתנה ללחיצה, מעבר מסך) נבנית בשלב 6 ומשתמשת בזה.
 * כאן: צעד שהתנאי שלו לא מתקיים **בוודאות** — מדולג (למשל "המשך למוזמנים"
 * כשהאשף כבר בשלב 3, או "עריכה" בשורה כשהמסך בפריסת כרטיסים).
 */
import type { FlowStep, GuidedFlow } from '../types'
import type { Facts } from '../facts'
import { holds } from './conditions'
import { messagingMode } from './topics'

/** האם אפשר להתחיל את ההדרכה עכשיו. */
export function canStartFlow(flow: GuidedFlow, facts: Facts): boolean {
  if (!holds(flow.when, facts)) return false
  // הדרכה על שליחה — רק כשידוע אם ההודעות יוצאות באמת (בשביל ההודעה הכנה בסיום).
  if (flow.sendsMessages && messagingMode(facts) === null) return false
  return true
}

/** הצעדים שרלוונטיים למצב הנוכחי, בסדר. */
export function activeSteps(flow: GuidedFlow, facts: Facts): FlowStep[] {
  return flow.steps.filter((s) => holds(s.when, facts))
}
