/**
 * אוצר המילים הסגור של מדידת השימוש בעזרה (HELP_CENTER_PLAN.md §12, שלב 8).
 *
 * זהה בדיוק ל-``backend/app/help_events_spec.json`` (נאכף ב-helpAnalytics.test.ts).
 * 11 שמות בלבד (החלטות המייסד 2026-09-29 / 2026-09-30). אין אף שדה של טקסט
 * חופשי — ערכים סגורים, מזהי בסיס ידע, bool או int. **טקסט החיפוש לא נשלח
 * לעולם**: ל-``search_no_results`` אין שדות בכלל.
 *
 * הקובץ טהור (בלי DOM/רשת) — נבדק ב-node.
 */

export const KB_VERSION = '2026-09-30'

type Kind = readonly string[] | 'kb_id' | 'kb_id?' | 'bool' | 'int'

export const HELP_EVENT_SPEC = {
  help_opened: { entry: ['launcher', 'error_hint', 'tour_back'], had_error: 'bool', had_urgent: 'bool' },
  topic_selected: { topic_id: 'kb_id', source: ['home', 'search', 'related', 'urgent'] },
  article_opened: { topic_id: 'kb_id', has_action: 'bool' },
  guided_help_started: { flow_id: 'kb_id' },
  guided_help_completed: {
    flow_id: 'kb_id',
    result: ['completed', 'abandoned', 'target_missing', 'error'],
    step: 'int',
  },
  troubleshooting_started: { tree_id: 'kb_id', source: ['trouble', 'search', 'error', 'topic_action', 'tour_error'] },
  troubleshooting_completed: {
    tree_id: 'kb_id',
    outcome_id: 'kb_id',
    resolution: ['user_fix', 'explained', 'veya_side', 'unknown'],
  },
  help_feedback: { target: ['topic', 'tree'], id: 'kb_id', value: ['helped', 'not_helped'] },
  search_no_results: {},
  escalation_started: { from: ['home', 'topic', 'tree'], topic_id: 'kb_id?', tree_id: 'kb_id?' },
  escalation_submitted: { from: ['home', 'topic', 'tree'], topic_id: 'kb_id?', tree_id: 'kb_id?' },
} as const satisfies Record<string, Record<string, Kind>>

export type HelpEventName = keyof typeof HELP_EVENT_SPEC
export type HelpEventProps = Record<string, string | number | boolean | null | undefined>

const KB_ID = /^[a-z0-9][a-z0-9.-]{0,59}$/
const MAX_INT = 50

function validValue(kind: Kind, value: unknown): boolean {
  if (Array.isArray(kind)) return typeof value === 'string' && kind.includes(value)
  const k = String(kind).replace(/\?$/, '')
  if (k === 'kb_id') return typeof value === 'string' && KB_ID.test(value)
  if (k === 'bool') return typeof value === 'boolean'
  if (k === 'int') return typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= MAX_INT
  return false
}

/**
 * ה-props אחרי ניקוי, או ``null`` אם האירוע לא תקין (ואז הוא פשוט לא נשלח).
 * שדה לא-חובה בלי ערך — מושמט.
 */
export function cleanEvent(name: string, props: HelpEventProps): Record<string, string | number | boolean> | null {
  const spec = (HELP_EVENT_SPEC as Record<string, Record<string, Kind>>)[name]
  if (!spec) return null
  const out: Record<string, string | number | boolean> = {}
  for (const key of Object.keys(props)) if (!(key in spec) && props[key] !== undefined) return null
  for (const [field, kind] of Object.entries(spec)) {
    const optional = typeof kind === 'string' && kind.endsWith('?')
    const v = props[field]
    if (v === undefined || v === null) {
      if (optional) continue
      return null
    }
    if (!validValue(kind, v)) return null
    out[field] = v as string | number | boolean
  }
  return out
}

/** מזהה סשן אקראי (32 תווי hex) — חדש בכל פתיחה של העזרה, לא קשור למשתמש. */
export function newSessionId(random: (n: number) => Uint8Array): string {
  return Array.from(random(16), (b) => b.toString(16).padStart(2, '0')).join('')
}
