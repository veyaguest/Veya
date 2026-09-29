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

  'guests.confirmed': {
    source: 'server', type: 'number',
    note: 'כמה מוזמנים (שורות) אישרו הגעה — DashboardStats.confirmed. "הושבה בקליק" עובדת רק עליהם',
  },

  // ── האירוע: פרטים ונעילה (שלב 3) ────────────────────────────────────
  'event.has_date': { source: 'server', type: 'boolean', note: 'Event.event_date לא ריק' },
  'event.commit_chosen': {
    source: 'server', type: 'boolean',
    note: 'נבחר מועד סגירת רשימה (Event.venue_commit_days_before). בחירה חד-פעמית',
  },
  'event.edit_unlocked': {
    source: 'server', type: 'boolean',
    note: 'פרטי הליבה פתוחים לעריכה בגלל בקשה לשינוי מועד שאושרה (postponement_service.edit_unlocked)',
  },
  'event.postpone': {
    source: 'server', type: 'string', values: ['none', 'pending', 'approved', 'completed', 'rejected'],
    note: 'מצב הבקשה לשינוי מועד — PostponementRead.status (None → none)',
  },
  'event.can_request_postpone': {
    source: 'server', type: 'boolean',
    note: 'PostponementRead.can_request — אפשר לפתוח בקשה חדשה עכשיו',
  },

  // ── אישורי הגעה (שלב 3, מתוך rsvp_timeline) ─────────────────────────
  'rsvp.phase': {
    source: 'server', type: 'string', values: ['unscheduled', 'waiting', 'before', 'running', 'ended'],
    note: 'rsvp_timeline.track_phase — unscheduled: אין תאריך / אירוע רחוק בלי מועד סגירה; waiting: אירוע קרוב בלי מועד סגירה (לא יוצא כלום)',
  },
  'rsvp.start_date': { source: 'server', type: 'string', note: 'YYYY-MM-DD — יום בקשת האישור הראשונה (וגם היום שממנו המוזמנים יכולים לאשר)' },
  'rsvp.commit_date': { source: 'server', type: 'string', note: 'YYYY-MM-DD — מועד סגירת הרשימה בפועל (אחרי הזזה מסוף שבוע)' },
  'rsvp.next_date': { source: 'server', type: 'string', note: 'YYYY-MM-DD — הצעד הבא במסלול' },
  'rsvp.next_label': {
    source: 'server', type: 'string',
    note: 'שם הצעד הבא **בניסוח של בעלי האירוע** (plainStepLabel — "שיחות טלפון ראשונות", לא "סבב שיחות")',
  },
  'rsvp.today_is_weekend': { source: 'server', type: 'boolean', note: 'היום שישי/שבת בשעון ישראל — לא יוצאות הודעות מסלול' },

  // ── הודעות (שלב 3) ──────────────────────────────────────────────────
  'messaging.mode': {
    source: 'server', type: 'string', values: ['mock', 'live'],
    note: 'messaging.current_mode(). mock = ההודעות נרשמות אבל לא נשלחות בפועל',
  },
  'messaging.emergency_stop': { source: 'server', type: 'boolean', note: 'עצירת חירום מהאדמין — שום הודעה לא יוצאת' },
  'messaging.invitation_empty': {
    source: 'server', type: 'boolean',
    note: 'לנוסח ההזמנה אין תוכן — השליחה מדלגת על כולם (ומציגה אותם בטעות כ"בלי טלפון"; באג ידוע, לא מתוקן כאן)',
  },
  'invites.sent': { source: 'server', type: 'number', note: 'כמה מוזמנים כבר נרשמה אליהם הזמנה במחזור הנוכחי (invitations.invited_guest_ids)' },
  'invites.not_yet': { source: 'server', type: 'number', note: 'טלפון תקין ועדיין בלי הזמנה — InvitationSendPreview.not_yet_sent' },
  'messages.wizardStep': {
    source: 'client', type: 'number',
    note: 'השלב הפתוח באשף ההזמנה הראשונה (1–3), מתוך ה-scope הפעיל messages.wizard.*',
  },

  // ── פיצ'רים ─────────────────────────────────────────────────────────
  'feature.calls': { source: 'server', type: 'boolean', note: "features.enabled('calls', event) — שיחות טלפון מצוות VEYA" },
  'gifts.eligible': { source: 'user', type: 'boolean', note: 'EventSummary.gift_service_eligible' },

  // ── הושבה (שלב 3) ───────────────────────────────────────────────────
  'seating.undo_available': { source: 'server', type: 'boolean', note: 'GET /seating/undo-state — יש סידור קודם להחזיר' },

  // ── מוזמן אחד (שלב 3: /help/facts/guests/{id}) — רק בעץ עם needsGuest ──
  'guest.phone': {
    source: 'server', type: 'string', values: ['valid', 'missing', 'invalid'],
    note: 'invitations.classify_phone — בלי המספר עצמו',
  },
  'guest.invitation': {
    source: 'server', type: 'string', values: ['none', 'sent', 'delivered', 'read', 'failed', 'blocked'],
    note: 'ההזמנה האחרונה במחזור הנוכחי (Message.status). none = לא נשלחה',
  },
  'guest.rsvp': {
    source: 'server', type: 'string', values: ['pending', 'confirmed', 'declined', 'maybe'],
    note: 'Guest.rsvp_status',
  },
  'guest.joined_after_last_round': {
    source: 'server', type: 'boolean',
    note: 'המוזמן נוסף אחרי שסבב ה-WhatsApp האחרון יצא — יצטרף רק לסבבים הבאים (communication._existed_by)',
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
