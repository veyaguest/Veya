/**
 * בסיס הידע של העזרה — נקודת כניסה אחת (HELP_CENTER_PLAN.md §5–6).
 *
 * כל תחום בקובץ משלו. תחום חדש = קובץ + שורה כאן. בדיקת השלמות
 * (helpKb.test.ts) רצה על כל מה שמיוצא מכאן.
 */
import type { DiagnosticTree, GuidedFlow, HelpTopic } from '../types'
import { EVENT_FLOWS, EVENT_TOPICS, EVENT_TREES } from './event'
import { FINANCE_TOPICS } from './finance'
import { GUEST_FLOWS, GUEST_TOPICS, GUEST_TREES } from './guests'
import { INVITATION_FLOWS, INVITATION_TOPICS, INVITATION_TREES } from './invitation'
import { RSVP_TOPICS, RSVP_TREES } from './rsvp'
import { SEATING_FLOWS, SEATING_TOPICS, SEATING_TREES } from './seating'

/** גרסת התוכן — עולה בכל שינוי תוכן; נשמרת באנליטיקס (שלב 8). */
export const KB_VERSION = '2026-09-29.2'

export const TOPICS: readonly HelpTopic[] = [
  ...GUEST_TOPICS,
  ...INVITATION_TOPICS,
  ...RSVP_TOPICS,
  ...EVENT_TOPICS,
  ...SEATING_TOPICS,
  ...FINANCE_TOPICS,
]

export const FLOWS: Readonly<Record<string, GuidedFlow>> = Object.fromEntries(
  [...GUEST_FLOWS, ...INVITATION_FLOWS, ...EVENT_FLOWS, ...SEATING_FLOWS].map((f) => [f.id, f]),
)

export const TREES: readonly DiagnosticTree[] = [
  ...GUEST_TREES,
  ...INVITATION_TREES,
  ...RSVP_TREES,
  ...EVENT_TREES,
  ...SEATING_TREES,
]
