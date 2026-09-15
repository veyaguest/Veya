/**
 * שרת דמו בזיכרון — עבור ההדגמה של ספירת המעטפות בדף הנחיתה.
 *
 * ## מה זה כן, ומה זה לא
 *
 * זה **לא** עותק של מסך הספירה ולא מוקאפ של הדוח. המסך והדוח שמוצגים
 * בהדגמה הם ``FinancePage`` ו-``EnvelopeCounter`` האמיתיים של המוצר,
 * בלי שורת קוד שונה. מה שהקובץ הזה מחליף הוא **השרת בלבד**: במקום
 * ``fetch`` שיוצא ל-API, יושבת כאן תשובה מחושבת על נתוני דוגמה.
 *
 * כך ההתנהגות שהגולש רואה היא ההתנהגות האמיתית — אותה שמירה, אותו
 * רענון, אותו יומן מתנות — ורק המקור של הנתונים הוא מקומי.
 *
 * ## למה בכלל שרת ולא "נתונים קבועים"
 *
 * כי ``EnvelopeCounter`` באמת שומר: הוא קורא ל-``POST /finance/envelopes``
 * ומחכה למספר המעטפה הבא מהשרת. כדי שהרכיב האמיתי יעבוד כמו שהוא, צריך
 * מישהו שיענה לו — ושהיומן שמתחתיו יראה מיד את מה שנשמר.
 *
 * המרה לכסף זהה ל-``backend/app/gift.py::format_agorot`` — אותו פורמט,
 * כדי שהמספרים בהדגמה ייראו בדיוק כמו במוצר.
 */
import type {
  ExpenseCategory,
  FinanceSummary,
  GiftCounting,
  GiftEntry,
  Guest,
  GuestGiftRow,
} from '../types'

/** המעטפות של ההדגמה — שם וסכום, בסדר שבו הן "נפתחות". */
export const DEMO_ENVELOPES: { name: string; amount: number }[] = [
  { name: 'דני ורותם', amount: 1000 },
  { name: 'משפחת כהן', amount: 1800 },
  { name: 'יוסי לוי', amount: 600 },
  { name: 'מאיה ואיתי', amount: 1200 },
  { name: 'משפחת ישראלי', amount: 2000 },
  { name: 'נועה ושחר', amount: 750 },
  { name: 'דוד ורונית', amount: 1500 },
  { name: 'עומר וגל', amount: 900 },
  { name: 'משפחת אברהם', amount: 2500 },
  { name: 'תומר ונועה', amount: 1100 },
]

/** ``52000 → "₪520"`` — אותו כלל כמו ``gift.format_agorot`` בשרת. */
export function formatAgorot(agorot: number): string {
  const sign = agorot < 0 ? '-' : ''
  const abs = Math.abs(agorot)
  const whole = Math.floor(abs / 100)
  const rest = abs % 100
  const withCommas = whole.toLocaleString('en-US')
  return rest ? `${sign}₪${withCommas}.${String(rest).padStart(2, '0')}` : `${sign}₪${withCommas}`
}

const PARTY: Record<string, number> = { 'משפחת כהן': 4, 'משפחת ישראלי': 5, 'משפחת אברהם': 4 }

/** רשימת המוזמנים של אירוע הדוגמה. השמות הם אלה שעל המעטפות. */
const GUESTS: Guest[] = DEMO_ENVELOPES.map((e, i) => ({
  id: i + 1,
  full_name: e.name,
  phone: '',
  side: (i % 2 === 0 ? 'groom' : 'bride') as Guest['side'],
  group_type: (i % 3 === 0 ? 'family' : 'friends') as Guest['group_type'],
  party_size: PARTY[e.name] ?? 2,
  notes_raw: null,
  seating_notes: null,
  rsvp_status: 'confirmed' as Guest['rsvp_status'],
  table_number: null,
  guest_token: null,
  confirmed_count: PARTY[e.name] ?? 2,
  guest_note: null,
  is_child: false,
  created_at: new Date().toISOString(),
}))

const TOTAL_PEOPLE = GUESTS.reduce((n, g) => n + g.party_size, 0)

/** המעטפות שנשמרו עד כה בהדגמה — בדיוק כמו טבלה בשרת. */
let saved: GiftEntry[] = []
let nextNumber = 1
let nextId = 1

export function resetDemoServer(): void {
  saved = []
  nextNumber = 1
  nextId = 1
}

function envelopesAgorot(): number {
  return saved.reduce((sum, e) => sum + (e.amount_agorot ?? 0), 0)
}

function income(): GiftCounting['income'] {
  const agorot = envelopesAgorot()
  const unidentified = saved.filter((e) => e.guest_id === null)
  const unidentifiedAgorot = unidentified.reduce((s, e) => s + (e.amount_agorot ?? 0), 0)
  return {
    envelopes_agorot: agorot,
    envelopes_display: formatAgorot(agorot),
    envelopes_count: saved.length,
    credit_agorot: 0,
    credit_display: formatAgorot(0),
    credit_count: 0,
    total_agorot: agorot,
    total_display: formatAgorot(agorot),
    unidentified_count: unidentified.length,
    external_agorot: 0,
    external_display: formatAgorot(0),
    external_count: 0,
    unidentified_agorot: unidentifiedAgorot,
    unidentified_display: formatAgorot(unidentifiedAgorot),
  }
}

function counting(): GiftCounting {
  return {
    counting_open: true,
    days_until_open: null,
    credit_service_active: false,
    credit_amounts_visible: false,
    next_envelope_number: nextNumber,
    income: income(),
    entries: [...saved].reverse(),
  }
}

function countedGuestIds(): Set<number> {
  return new Set(saved.map((e) => e.guest_id).filter((id): id is number => id !== null))
}

function summary(): FinanceSummary {
  const counted = countedGuestIds().size
  const agorot = envelopesAgorot()
  const zero = formatAgorot(0)
  return {
    rsvp: {
      total_guests: GUESTS.length,
      invited_people: TOTAL_PEOPLE,
      confirmed_guests: GUESTS.length,
      confirmed_people: TOTAL_PEOPLE,
      declined_guests: 0,
      pending_guests: 0,
      maybe_guests: 0,
    },
    attendance: {
      confirmed_people: TOTAL_PEOPLE,
      actual: TOTAL_PEOPLE,
      is_final: true,
      no_show: 0,
      extra: 0,
      event_passed: true,
    },
    cost: {
      total_agorot: 0,
      total_display: zero,
      fixed_agorot: 0,
      fixed_display: zero,
      variable_agorot: 0,
      variable_display: zero,
      attendees: TOTAL_PEOPLE,
      invited: TOTAL_PEOPLE,
      cost_per_attendee_agorot: null,
      cost_per_attendee_display: zero,
      next_attendee_agorot: 0,
      next_attendee_display: zero,
      paid_agorot: 0,
      paid_display: zero,
      unpaid_agorot: 0,
      unpaid_display: zero,
      estimated_agorot: 0,
      estimated_display: zero,
    } as FinanceSummary['cost'],
    income: income(),
    breakdown: {
      from_attendees_agorot: agorot,
      from_attendees_display: formatAgorot(agorot),
      from_non_attendees_agorot: 0,
      from_non_attendees_display: zero,
      unattributed_agorot: 0,
      from_external_agorot: 0,
      from_external_display: zero,
      unattributed_display: zero,
      guests_counted: counted,
      guests_not_counted: GUESTS.length - counted,
    } as FinanceSummary['breakdown'],
    counting_open: true,
    bottom_line_agorot: agorot,
    bottom_line_display: formatAgorot(agorot),
    expenses: [],
  } as FinanceSummary
}

function byGuest(): GuestGiftRow[] {
  return GUESTS.map((g) => {
    const mine = saved.filter((e) => e.guest_id === g.id)
    const agorot = mine.reduce((s, e) => s + (e.amount_agorot ?? 0), 0)
    const has = mine.length > 0
    return {
      guest_id: g.id,
      full_name: g.full_name,
      phone: '',
      rsvp_status: g.rsvp_status,
      party_size: g.party_size,
      attended_count: g.party_size,
      status: has ? 'counted' : 'not_counted',
      total_agorot: has ? agorot : null,
      total_display: has ? formatAgorot(agorot) : '',
      envelope_agorot: agorot,
      envelope_display: formatAgorot(agorot),
      credit_agorot: 0,
      credit_display: formatAgorot(0),
      envelope_count: mine.length,
      credit_count: 0,
      gift_count: mine.length,
      envelope_numbers: mine.map((e) => e.envelope_number ?? 0),
      note: '',
    } as GuestGiftRow
  })
}

function createEnvelope(body: {
  amount_agorot: number
  guest_id: number | null
  shared_guest_ids?: number[]
  external_name?: string
  note?: string | null
}) {
  const guest = GUESTS.find((g) => g.id === body.guest_id) ?? null
  const entry: GiftEntry = {
    source: 'envelope',
    id: nextId++,
    amount_agorot: body.amount_agorot,
    amount_display: formatAgorot(body.amount_agorot),
    guest_id: guest?.id ?? null,
    guest_name: guest?.full_name ?? body.external_name ?? '',
    envelope_number: nextNumber,
    note: body.note ?? null,
    created_at: new Date().toISOString(),
    shared_names: (body.shared_guest_ids ?? [])
      .map((id) => GUESTS.find((g) => g.id === id)?.full_name ?? '')
      .filter(Boolean),
    is_external: Boolean(body.external_name),
    external_phone: '',
    status: null,
  }
  saved = [...saved, entry]
  nextNumber += 1
  return { envelope: entry, next_envelope_number: nextNumber }
}

/** משלים בשקט את המעטפות שעוד לא נספרו — כדי שההדגמה תקליד רק כמה
 *  מעטפות לאט, והדוח בסוף עדיין יציג את כל הערימה. */
export function seedRemainingEnvelopes(): void {
  const from = saved.length
  DEMO_ENVELOPES.slice(from).forEach((e, k) => {
    createEnvelope({ amount_agorot: e.amount * 100, guest_id: from + k + 1, shared_guest_ids: [] })
  })
}

/** ממלא מראש את כל המעטפות — למצב "תנועה מופחתת", שבו אין הקלדה. */
export function seedAllEnvelopes(): void {
  if (saved.length) return
  DEMO_ENVELOPES.forEach((e, i) => {
    createEnvelope({ amount_agorot: e.amount * 100, guest_id: i + 1, shared_guest_ids: [] })
  })
}

/** הדוח המלא — אותו מבנה שהשרת מחזיר ל-``GET /finance/report``. */
function fullReport() {
  return {
    event_title: 'החתונה של דניאל ושרון',
    event_type_label: 'חתונה',
    event_date: '2026-09-30',
    venue_name: 'אולם הדר',
    generated_at: new Date().toISOString(),
    ...summary(),
    guests: byGuest(),
    unidentified: saved.filter((e) => e.guest_id === null),
    external: saved.filter((e) => e.is_external),
  }
}

const CATEGORIES: ExpenseCategory[] = []

function json(data: unknown): Response {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

let installed = false

/**
 * מחליף את ``fetch`` בתשובות מקומיות — רק לנתיבים שההדגמה צריכה.
 * כל בקשה אחרת ממשיכה כרגיל, כדי שלא נשבור שום דבר אחר בעמוד.
 */
export function installDemoServer(): void {
  if (installed) return
  installed = true
  const real = window.fetch.bind(window)

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
    const path = url.replace(/^https?:\/\/[^/]+/, '').split('?')[0]
    const method = (init?.method ?? 'GET').toUpperCase()

    if (path === '/finance' && method === 'GET') return json(summary())
    if (path === '/finance/categories') return json(CATEGORIES)
    if (path === '/finance/gifts' && method === 'GET') return json(counting())
    if (path === '/finance/gifts/by-guest') return json(byGuest())
    if (path === '/finance/report') return json(fullReport())
    if (path === '/guests' && method === 'GET') {
      return json({ items: GUESTS, total: GUESTS.length })
    }
    if (path === '/finance/envelopes' && method === 'POST') {
      const body = init?.body ? JSON.parse(String(init.body)) : {}
      return json(createEnvelope(body))
    }
    return real(input as RequestInfo, init)
  }
}
