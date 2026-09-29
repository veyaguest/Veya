/**
 * בסיס הידע של העזרה — נקודת כניסה אחת (HELP_CENTER_PLAN.md §5–6).
 *
 * כל תחום בקובץ משלו. תחום חדש = קובץ + שורה כאן. בדיקת השלמות
 * (helpKb.test.ts) רצה על כל מה שמיוצא מכאן.
 */
import type { DiagnosticTree, GuidedFlow, HelpTopic } from '../types'
import { GUEST_FLOWS, GUEST_TOPICS, GUEST_TREES } from './guests'

/** גרסת התוכן — עולה בכל שינוי תוכן; נשמרת באנליטיקס (שלב 8). */
export const KB_VERSION = '2026-09-29.1'

export const TOPICS: readonly HelpTopic[] = [...GUEST_TOPICS]

export const FLOWS: Readonly<Record<string, GuidedFlow>> = Object.fromEntries(
  [...GUEST_FLOWS].map((f) => [f.id, f]),
)

export const TREES: readonly DiagnosticTree[] = [...GUEST_TREES]
