/**
 * עובדות — אוצר המילים הסגור של "מה נכון עכשיו", שהעזרה רשאית להסתמך עליו.
 *
 * כל תנאי בבסיס הידע מתייחס רק לעובדה שרשומה כאן (נבדק ב-helpKb.test.ts).
 * עובדה שלא ידועה ברגע ההצגה (למשל השרת לא ענה) → התנאי "לא ידוע", והעזרה
 * לא מציגה דבר שנשען עליה — עדיף לשתוק מאשר לנחש (HELP_CENTER_PLAN.md §8).
 *
 * מקורות:
 * - ``client`` — מה שהדפדפן יודע (גודל מסך, תמיכה באנשי קשר, חיבור).
 * - ``user``   — מהחשבון והאירוע שכבר נטענו (EventSummary.my_role).
 * - ``server`` — ``GET /help/facts`` (שלב 3). ספירות ודגלים בלבד — בלי שמות
 *                ובלי טלפונים. **עד שלב 3 הן חסרות**, ולכן כל מה שתלוי בהן
 *                פשוט לא מוצג.
 * - ``error``  — השגיאה האחרונה מ-help/errorBus.ts (בזיכרון בלבד).
 */

export interface FactDef {
  source: 'client' | 'user' | 'server' | 'error'
  type: 'boolean' | 'number' | 'string'
  /** ערכים אפשריים לעובדה מסוג string סגור. */
  values?: readonly string[]
  /** למפתחים: מאיפה זה מגיע. */
  note: string
}

export const FACTS = {
  // ── דפדפן ────────────────────────────────────────────────────────────
  // "טלפון" אינו דבר אחד ב-VEYA: כל מסך עובר לפריסה אחרת בנקודה משלו.
  // לכן כל עובדת פריסה משתמשת **באותה שאילתה בדיוק** של המסך עצמו.
  'layout.guestCards': {
    source: 'client', type: 'boolean',
    note: 'מסך המוזמנים בפריסת כרטיסים — GuestsPage CARD_LAYOUT_QUERY (max-width: 700px). הקשה על כרטיס פותחת עריכה',
  },
  'layout.hallDesktop': {
    source: 'client', type: 'boolean',
    note: 'מסך ההושבה בפריסת דסקטופ — lib/useMediaQuery HALL_DESKTOP_QUERY',
  },
  'client.contactPicker': {
    source: 'client', type: 'boolean',
    note: 'ContactsImportDialog.isContactPickerSupported() — false בספארי/אייפון',
  },
  'client.online': {
    source: 'client', type: 'boolean',
    note: 'בדיקת /health שכבר רצה ב-App.tsx',
  },

  // ── המשתמש באירוע ───────────────────────────────────────────────────
  'user.role': {
    source: 'user', type: 'string', values: ['owner', 'partner', 'member'],
    note: 'EventSummary.my_role (routers/events.py::_my_role)',
  },

  // ── האירוע (שלב 3: /help/facts) ─────────────────────────────────────
  'event.days_to_event': {
    source: 'server', type: 'number',
    note: 'כמה ימים עד האירוע (0 = היום, שלילי = עבר). משמש רק לקביעה אם להבליט את צוות VEYA (engine/ladder.ts)',
  },

  // ── מוזמנים (שלב 3: /help/facts) ────────────────────────────────────
  'guests.total': {
    source: 'server', type: 'number',
    note: 'כמה מוזמנים (שורות) ברשימה — DashboardStats.total_guests',
  },
  'guests.bad_phone': {
    source: 'server', type: 'number',
    note: 'מוזמנים בלי מספר תקין (חסר/לא תקין) — DashboardStats.bad_phone_guests',
  },

  // ── השגיאה האחרונה (help/errorBus.ts) ────────────────────────────────
  'error.last.method': { source: 'error', type: 'string', note: 'GET/POST/…' },
  'error.last.path': { source: 'error', type: 'string', note: 'תבנית נתיב, בלי מזהים' },
  'error.last.status': { source: 'error', type: 'number', note: '0 = אין רשת' },
  'error.last.message': { source: 'error', type: 'string', note: 'ההודעה שהמשתמש ראה' },
} as const satisfies Record<string, FactDef>

export type FactId = keyof typeof FACTS

export const FACT_IDS = Object.keys(FACTS) as FactId[]

/** ערכי העובדות ברגע נתון. עובדה שחסרה כאן = לא ידועה. */
export type Facts = Partial<Record<FactId, string | number | boolean>>
