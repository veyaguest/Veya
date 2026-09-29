/**
 * העובדות שהעזרה רואה ברגע נתון — צירוף של שלושה מקורות, בלי לנחש:
 * - דפדפן: פריסה (אותן שאילתות של המסכים), תמיכה באנשי קשר, חיבור.
 * - משתמש/אירוע: התפקיד והזכאות למתנות (EventSummary, כבר טעון).
 * - שרת: ``GET /help/context/{screen}`` — רק העובדות של המסך הזה.
 *   ``null`` מהשרת = לא ידוע → לא נכנס בכלל (והמנוע מתייחס לזה כ"לא ידוע").
 */
import { CARD_LAYOUT_QUERY } from '../../components/GuestsPage'
import { isContactPickerSupported } from '../../components/ContactsImportDialog'
import { plainStepLabel } from '../../components/RsvpTimeline'
import { HALL_DESKTOP_QUERY } from '../../lib/useMediaQuery'
import type { HelpFactValue } from '../../api'
import type { EventSummary } from '../../types'
import { FACTS } from '../facts'
import type { Facts } from '../facts'
import { activeScopes } from '../scopes'

const WIZARD_STEP: Record<string, number> = {
  'messages.wizard.design': 1,
  'messages.wizard.recipients': 2,
  'messages.wizard.review': 3,
}

function matches(query: string): boolean {
  return typeof window !== 'undefined' && window.matchMedia(query).matches
}

/** עובדות הדפדפן והמשתמש — מחושבות מחדש בכל קריאה (משתנות תוך כדי הדרכה). */
export function clientFacts(event: EventSummary, online: boolean | null): Facts {
  const f: Facts = {
    'layout.guestCards': matches(CARD_LAYOUT_QUERY),
    'layout.hallDesktop': matches(HALL_DESKTOP_QUERY),
    'client.contactPicker': isContactPickerSupported(),
    'gifts.eligible': event.gift_service_eligible,
  }
  if (online !== null) f['client.online'] = online
  if (event.my_role) f['user.role'] = event.my_role
  const step = activeScopes().map((s) => WIZARD_STEP[s]).find((n) => n !== undefined)
  if (step !== undefined) f['messages.wizardStep'] = step
  return f
}

/**
 * עובדות השרת כפי שהגיעו, מסוננות: רק מפתחות שרשומים כעובדות שרת, ובלי
 * ``null``. שם הצעד הבא עובר לניסוח של בעלי האירוע — כמו במסך אישורי ההגעה.
 */
export function serverFacts(raw: Record<string, HelpFactValue>): Facts {
  const defs = FACTS as Record<string, { source: string }>
  const out: Facts = {}
  for (const [k, v] of Object.entries(raw)) {
    if (v === null || defs[k]?.source !== 'server') continue
    const value = k === 'rsvp.next_label' && typeof v === 'string' ? plainStepLabel(v) : v
    ;(out as Record<string, string | number | boolean>)[k] = value
  }
  return out
}
