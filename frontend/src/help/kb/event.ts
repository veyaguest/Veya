/**
 * ידע: פרטי האירוע, מועד סגירת הרשימה ושינוי מועד (HELP_CENTER_PLAN.md — שלב 2, חלק 2).
 *
 * עובדות שמאחורי הניסוחים (אומתו ב-2026-09-29):
 * - נעולים אחרי שמולאו: סוג האירוע, השמות, שמות ההורים, תאריך ושעה
 *   (routers/event.py::_core_fields). פתוחים תמיד: שם המקום, כתובת, תמונת
 *   הזמנה, שעות שליחה (ALWAYS_EDITABLE). שדה ריק — מותר למלא.
 * - הנעילה נפתחת רק בבקשה לשינוי מועד שאושרה (postponement_service.edit_unlocked).
 *   הבקשה: "האירוע נדחה?" → "בקשה לשינוי מועד", רק כשאפשר (can_request).
 * - מועד סגירת רשימה: 1–10 ימים לפני האירוע, בחירה חד-פעמית, לא בעבר.
 *   נופל בשישי/שבת → חמישי שלפניו (strings.dashboard.commitConfirmBody).
 * - שעת שליחה: בין 10:00 ל-19:00 (communication.validate_send_time).
 */
import type { DiagnosticTree, GuidedFlow, HelpTopic } from '../types'
import { MANAGER, VERIFIED } from './shared'

const SOURCES = ['components/DashboardPage.tsx', 'strings/he.ts']
const SERVER = ['../../backend/app/routers/event.py']

export const EVENT_TOPICS: readonly HelpTopic[] = [
  {
    id: 'event.edit-details',
    area: 'event',
    title: 'איך משנים את פרטי האירוע?',
    aliases: ['פרטי האירוע', 'שם המקום', 'כתובת', 'תמונת הזמנה', 'אולם'],
    scopes: [
      { scope: 'dashboard', weight: 60 },
      { scope: 'dashboard.editEvent', weight: 80 },
    ],
    when: MANAGER,
    answer: [
      'בתמונת המצב: "{ui:dashboard.editDetailsButton}".',
      'שם המקום, הכתובת ותמונת ההזמנה — אפשר לשנות תמיד.',
      'סוג האירוע, השמות, התאריך והשעה נעולים אחרי שנקבעו, כדי שאישורי ההגעה והתזכורות יישארו מסונכרנים.',
    ],
    related: ['event.change-date'],
    sources: [...SOURCES, ...SERVER],
    verifiedAt: VERIFIED,
    priority: 3,
  },
  {
    id: 'event.change-date',
    area: 'event',
    title: 'איך משנים את תאריך האירוע?',
    aliases: ['שינוי תאריך', 'לשנות תאריך', 'להזיז את התאריך', 'האירוע נדחה', 'דחייה', 'שינוי מועד', 'תאריך נעול'],
    scopes: [
      { scope: 'dashboard', weight: 50 },
      { scope: 'dashboard.editEvent', weight: 85 },
    ],
    when: MANAGER,
    errorMatch: [{ method: 'PATCH', path: '/event', status: 409 }],
    answer: [],
    variants: [
      {
        when: { fact: 'event.has_date', op: '==', value: false },
        answer: ['עוד אין תאריך — מוסיפים אותו ב"{ui:dashboard.editDetailsButton}".'],
      },
      {
        when: { fact: 'event.edit_unlocked', op: '==', value: true },
        answer: ['האירוע פתוח עכשיו לעדכון: משנים את התאריך ב"{ui:dashboard.editDetailsButton}".'],
      },
      {
        when: { fact: 'event.postpone', op: '==', value: 'pending' },
        answer: ['הבקשה לשינוי מועד ממתינה לאישור. אחרי האישור אפשר יהיה לעדכן את התאריך.'],
      },
      {
        when: { fact: 'event.can_request_postpone', op: '==', value: true },
        answer: [
          'התאריך נעול אחרי שנקבע, כדי שאישורי ההגעה והתזכורות יישארו מסונכרנים.',
          'אם האירוע זז: ב"{ui:dashboard.editDetailsButton}" ← "{ui:postpone.entryCta}". אחרי אישור קצר של צוות VEYA אפשר לעדכן תאריך, שעה ומקום.',
        ],
      },
    ],
    sources: [...SOURCES, ...SERVER, '../../backend/app/postponement_service.py'],
    verifiedAt: VERIFIED,
    priority: 3,
  },
  {
    id: 'event.commit-date',
    area: 'event',
    title: 'מה זה מועד סגירת הרשימה?',
    aliases: ['סגירת רשימה', 'מספר סופי לאולם', 'כמה ימים לפני', 'התחייבות לאולם'],
    scopes: [
      { scope: 'dashboard.editEvent', weight: 90 },
      { scope: 'dashboard', weight: 55 },
      { scope: 'rsvp', weight: 60 },
    ],
    when: MANAGER,
    urgentWhen: { all: [{ fact: 'event.has_date', op: '==', value: true }, { fact: 'event.commit_chosen', op: '==', value: false }] },
    answer: [
      'היום שבו מוסרים לאולם מספר סופי. ביום הזה אישורי ההגעה נסגרים, והלוח שלהם נבנה לאחור ממנו.',
      'בוחרים פעם אחת — אחרי השמירה אי אפשר לשנות.',
    ],
    variants: [
      {
        when: { all: [{ fact: 'event.has_date', op: '==', value: true }, { fact: 'event.commit_chosen', op: '==', value: false }] },
        answer: [
          'היום שבו מוסרים לאולם מספר סופי. ביום הזה אישורי ההגעה נסגרים, והלוח שלהם נבנה לאחור ממנו.',
          'עוד לא בחרתם — ובלי הבחירה לא יוצאות בקשות אישור הגעה. בוחרים פעם אחת, ואחרי השמירה אי אפשר לשנות.',
        ],
        primary: { kind: 'tour', flow: 'choose-commit-date' },
      },
    ],
    related: ['event.commit-change', 'rsvp.when-requests'],
    sources: [...SOURCES, ...SERVER, '../../backend/app/rsvp_timeline.py'],
    verifiedAt: VERIFIED,
    priority: 4,
  },
  {
    id: 'event.commit-change',
    area: 'event',
    title: 'אפשר לשנות את מועד סגירת הרשימה?',
    aliases: ['לשנות סגירה', 'טעיתי במועד', 'מועד נעול'],
    scopes: [
      { scope: 'dashboard.editEvent', weight: 60 },
      { scope: 'rsvp', weight: 30 },
    ],
    when: { all: [MANAGER, { fact: 'event.commit_chosen', op: '==', value: true }] },
    answer: [
      'לא — הבחירה נעולה, כי כל לוח אישורי ההגעה נבנה סביבה.',
      'אם האירוע נדחה, בקשה לשינוי מועד פותחת גם אותה מחדש.',
    ],
    sources: [...SOURCES, ...SERVER],
    verifiedAt: VERIFIED,
  },
  {
    id: 'event.commit-weekend',
    area: 'event',
    title: 'למה הרשימה נסגרת בחמישי ולא ביום שבחרנו?',
    aliases: ['חמישי', 'שישי', 'שבת', 'סוף שבוע'],
    scopes: [
      { scope: 'dashboard.editEvent', weight: 40 },
      { scope: 'rsvp', weight: 30 },
    ],
    answer: ['היום שנבחר נופל בשישי או בשבת — ובימים האלה לא פונים ל{guests}, ולכן הרשימה נסגרת בחמישי שלפניו.'],
    sources: ['strings/he.ts', '../../backend/app/rsvp_timeline.py'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'event.send-time',
    area: 'event',
    title: 'איך בוחרים באיזו שעה יוצאות ההודעות?',
    aliases: ['שעת שליחה', 'שעה', 'מתי ביום'],
    scopes: [
      { scope: 'messages', weight: 45 },
      { scope: 'rsvp', weight: 30 },
    ],
    when: MANAGER,
    sendsMessages: true,
    answer: [],
    variants: [
      {
        when: { fact: 'invites.sent', op: '>', value: 0 },
        answer: [
          'במסך "ניהול הודעות", בכרטיס של כל הודעה שיוצאת לפי הלוח: "{ui:messages.roundTime.label}", בין 10:00 ל-19:00.',
          'היום עצמו נקבע לפי לוח אישורי ההגעה — בוחרים רק את השעה.',
        ],
      },
      {
        // לפני הזמנה ראשונה האשף מציג רק את כרטיס ההזמנה (CommunicationTab only=['invitation']).
        when: { fact: 'invites.sent', op: '==', value: 0 },
        answer: [
          'אחרי ששולחים את ההזמנה, במסך "ניהול הודעות" מופיעים כל כרטיסי ההודעות — ובכל אחד "{ui:messages.roundTime.label}", בין 10:00 ל-19:00.',
          'ההזמנה עצמה יוצאת ברגע שלוחצים "שליחת הזמנות".',
        ],
      },
    ],
    sources: ['components/CommunicationTab.tsx', 'components/MessagesPage.tsx', 'strings/he.ts', 'App.tsx', '../../backend/app/communication.py'],
    verifiedAt: VERIFIED,
  },
]

export const EVENT_FLOWS: readonly GuidedFlow[] = [
  {
    id: 'choose-commit-date',
    when: {
      all: [
        MANAGER,
        { fact: 'event.has_date', op: '==', value: true },
        { fact: 'event.commit_chosen', op: '==', value: false },
      ],
    },
    start: { page: 'dashboard' },
    steps: [
      { target: 'dashboard.editDetails', text: 'לחצו "{ui:dashboard.editDetailsButton}"', advanceOn: { kind: 'scope', scope: 'dashboard.editEvent' } },
      { target: 'dashboard.commitField', text: 'בחרו כמה ימים לפני האירוע, ואז "{ui:help.tourNext}"', advanceOn: { kind: 'manual' } },
      {
        target: 'dashboard.saveDetails',
        text: 'לחצו "{ui:common.save}", ואז "{ui:dashboard.commitConfirmCta}"',
        advanceOn: { kind: 'api', method: 'PATCH', path: '/event' },
        // מילה במילה מחלון האישור (strings.dashboard.commitConfirmBody).
        warning: { text: 'אחרי השמירה אי אפשר לשנות את הבחירה.' },
      },
    ],
    success: { kind: 'api', method: 'PATCH', path: '/event' },
    doneText: 'נשמר. עכשיו יש לוח אישורי הגעה — אפשר לראות אותו במסך "אישורי הגעה".',
    onError: [{ match: { method: 'PATCH', path: '/event' }, tree: 'event-save-failed' }],
    sources: [...SOURCES, ...SERVER],
    verifiedAt: VERIFIED,
  },
]

export const EVENT_TREES: readonly DiagnosticTree[] = [
  {
    id: 'event-save-failed',
    area: 'event',
    symptom: 'לא מצליחים לשמור את פרטי האירוע',
    scopes: [
      { scope: 'dashboard.editEvent', weight: 90 },
      { scope: 'dashboard', weight: 40 },
    ],
    when: MANAGER,
    errorMatch: [{ method: 'PATCH', path: '/event' }],
    root: 'offline',
    nodes: {
      offline: { kind: 'check', test: { fact: 'error.last.status', op: '==', value: 0 }, yes: 'out-offline', no: 'locked', unknown: 'out-no-error' },
      // הניסוחים שהשרת מחזיר — routers/event.py + communication.validate_send_time.
      locked: { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'נעול לעריכה' }, yes: 'pending', no: 'commit-set', unknown: 'out-unknown' },
      pending: { kind: 'check', test: { fact: 'event.postpone', op: '==', value: 'pending' }, yes: 'out-pending', no: 'out-locked' },
      'commit-set': { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'מועד סגירת הרשימה כבר נקבע' }, yes: 'out-commit-set', no: 'commit-past' },
      'commit-past': { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'כבר הייתה סגורה' }, yes: 'out-commit-past', no: 'send-time' },
      'send-time': { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'שעת השליחה חייבת' }, yes: 'out-send-time', no: 'out-unknown' },
      'out-offline': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['נראה שאין חיבור לאינטרנט כרגע. כשהחיבור יחזור — אפשר לשמור שוב.'],
      },
      'out-pending': {
        kind: 'outcome', resolution: 'explained',
        text: ['הפרט הזה נעול, והבקשה לשינוי מועד עוד ממתינה לאישור. אחרי האישור אפשר יהיה לעדכן.'],
      },
      'out-locked': {
        kind: 'outcome', resolution: 'explained',
        text: [
          'סוג האירוע, השמות, התאריך והשעה נעולים אחרי שנקבעו.',
          'אם האירוע זז — "{ui:postpone.entryCta}" בתוך "{ui:dashboard.editDetailsButton}".',
        ],
      },
      'out-commit-set': {
        kind: 'outcome', resolution: 'explained',
        text: ['מועד סגירת הרשימה כבר נקבע, וכל לוח אישורי ההגעה נבנה סביבו. אם האירוע נדחה — בקשה לשינוי מועד פותחת אותו מחדש.'],
      },
      'out-commit-past': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['בתאריך הזה הרשימה כבר הייתה סגורה. בוחרים פחות ימים לפני האירוע.'],
      },
      'out-send-time': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['שעת השליחה צריכה להיות בין 10:00 ל-19:00.'],
      },
      'out-no-error': {
        kind: 'outcome', resolution: 'unknown', offerTeam: true,
        text: [
          'לא ראינו שגיאה בשמירה האחרונה.',
          'סוג האירוע, השמות, התאריך והשעה נעולים אחרי שנקבעו; שם המקום, הכתובת ותמונת ההזמנה פתוחים תמיד.',
        ],
      },
      'out-unknown': {
        kind: 'outcome', resolution: 'unknown', offerTeam: true,
        text: ['לא זיהינו מה עצר את השמירה.'],
      },
    },
    sources: [...SERVER, '../../backend/app/communication.py', 'strings/he.ts'],
    verifiedAt: VERIFIED,
  },
]
