/**
 * ידע: אישורי הגעה (HELP_CENTER_PLAN.md — שלב 2, חלק 2).
 *
 * עובדות שמאחורי הניסוחים (אומתו ב-2026-09-29):
 * - המסלול פועל רק אחרי שנבחר מועד סגירת רשימה (rsvp_timeline.track_enabled).
 *   שליחת הזמנה לא מתחילה אותו.
 * - 14 ימים לפני מועד הסגירה: בקשה ראשונה + 3 תזכורות WhatsApp, ו-3 סבבי
 *   שיחות (rsvp_timeline.CYCLE). חלון קצר — נדחס, לא מתקצר. שישי/שבת — לא.
 * - תזכורות: רק למי שעדיין ממתינים לתשובה (communication.matches_audience,
 *   audience=pending). "לא החליטו" לא מקבלים עוד WhatsApp, אבל נשארים בתור
 *   השיחות (call_center.OPEN_STATUSES) — אם שיחות פעילות לאירוע.
 * - אין שליחה בדיעבד: סבב שהחלון שלו עבר לא יוצא (communication.send_window).
 * - מוזמן חדש מצטרף רק לסבבים שיוצאים אחרי שנוסף (communication._existed_by).
 * - המוזמנים יכולים לאשר רק מיום בקשת האישור הראשונה (guest_journey.rsvp_is_open);
 *   עד אז הקישור מציג את ההזמנה בלבד ("אישורי ההגעה עדיין לא נפתחו…", confirm.py).
 * - קישור שלא מוביל לאף מוזמן → "הקישור כבר לא פעיל" (confirm.py). טוקן לא
 *   מתחלף — קורה רק כשהמוזמן הוסר (או קישור שהועתק חלקית).
 * - יום האירוע: הודעה למי שאישרו; יום אחרי — תודה (communication, rsvp_timeline).
 * - השאלות הנפוצות במסך אישורי ההגעה: kb/rsvpFaq.ts — מקושרות לנושאים כאן.
 * - עדכון ידני: "סטטוס אישור הגעה" בעריכת מוזמן בלבד (AddGuestForm, editing).
 */
import type { DiagnosticTree, HelpTopic } from '../types'
import { MANAGER, MOCK_NOTICE, VERIFIED } from './shared'

const SOURCES = ['components/RsvpPage.tsx', 'components/RsvpTimeline.tsx', 'strings/he.ts']
const SERVER = ['../../backend/app/rsvp_timeline.py', '../../backend/app/communication.py']
const CALLS_ON = { fact: 'feature.calls', op: '==', value: true } as const
const CALLS_OFF = { fact: 'feature.calls', op: '==', value: false } as const

export const RSVP_TOPICS: readonly HelpTopic[] = [
  {
    id: 'rsvp.when-requests',
    area: 'rsvp',
    title: 'מתי יוצאות בקשות אישור ההגעה?',
    aliases: ['תזכורות', 'מתי שולחים', 'לא יצאו תזכורות', 'לוח זמנים', 'סבבים'],
    scopes: [
      { scope: 'rsvp', weight: 100 },
      { scope: 'messages', weight: 55 },
      { scope: 'dashboard', weight: 40 },
    ],
    when: MANAGER,
    sendsMessages: true,
    answer: [],
    variants: [
      {
        when: { fact: 'event.has_date', op: '==', value: false },
        answer: ['קודם מוסיפים תאריך לאירוע, ואז בוחרים מועד סגירת רשימה. בלי שניהם לא יוצאת אף בקשה.'],
        primary: { kind: 'navigate', page: 'dashboard', label: 'לתמונת המצב' },
      },
      {
        when: { fact: 'rsvp.phase', op: 'in', value: ['unscheduled', 'waiting'] },
        answer: ['הן יוצאות רק אחרי שתבחרו מועד סגירת רשימה, ב"{ui:dashboard.editDetailsButton}".'],
        primary: { kind: 'tour', flow: 'choose-commit-date' },
      },
      {
        when: { fact: 'rsvp.phase', op: '==', value: 'before' },
        answer: ['הבקשה הראשונה תצא ב{date:rsvp.start_date}. עד אז לא יוצאת אף בקשה.'],
        primary: null,
      },
      {
        when: { fact: 'rsvp.phase', op: '==', value: 'running' },
        answer: [
          'הצעד הבא: {text:rsvp.next_label}, ב{date:rsvp.next_date}.',
          'בשישי ובשבת לא יוצאות הודעות.',
        ],
        primary: null,
      },
      {
        when: { fact: 'rsvp.phase', op: '==', value: 'ended' },
        answer: ['הרשימה נסגרה ב{date:rsvp.commit_date}, והמספרים עכשיו סופיים.'],
        primary: null,
      },
    ],
    related: ['rsvp.how-it-works', 'invitation.vs-rsvp'],
    sources: [...SOURCES, ...SERVER],
    verifiedAt: VERIFIED,
    priority: 5,
  },
  {
    id: 'rsvp.how-it-works',
    area: 'rsvp',
    title: 'איך עובדים אישורי ההגעה?',
    aliases: ['מסלול', 'תהליך', 'שיחות טלפון', 'כמה תזכורות'],
    scopes: [
      { scope: 'rsvp', weight: 80 },
      { scope: 'dashboard', weight: 20 },
    ],
    sendsMessages: true,
    answer: [],
    variants: [
      {
        when: CALLS_ON,
        answer: [
          '14 ימים לפני מועד סגירת הרשימה יוצאת בקשה ראשונה, ואחריה עוד 3 תזכורות ב-WhatsApp למי שעוד לא ענו.',
          'מי שלא עונים מקבלים גם שיחת טלפון, עד 3 פעמים.',
          'בשישי ובשבת לא פונים ל{guests}. כשנשאר פחות זמן — הלוח צפוף יותר.',
        ],
      },
      {
        when: CALLS_OFF,
        answer: [
          '14 ימים לפני מועד סגירת הרשימה יוצאת בקשה ראשונה, ואחריה עוד 3 תזכורות ב-WhatsApp למי שעוד לא ענו.',
          'בשישי ובשבת לא פונים ל{guests}. כשנשאר פחות זמן — הלוח צפוף יותר.',
        ],
      },
    ],
    related: ['rsvp.when-requests'],
    sources: [...SOURCES, ...SERVER, '../../backend/app/features.py'],
    verifiedAt: VERIFIED,
    priority: 3,
  },
  {
    id: 'rsvp.maybe',
    area: 'rsvp',
    title: 'מה קורה עם מי שענו "לא החליטו"?',
    aliases: ['אולי', 'מתלבטים', 'לא בטוח', 'לא החליטו'],
    scopes: [{ scope: 'rsvp', weight: 70 }],
    when: MANAGER,
    answer: [],
    variants: [
      {
        when: CALLS_ON,
        answer: [
          'הם לא מקבלים עוד תזכורות ב-WhatsApp, אבל כן נשארים ברשימת השיחות.',
          'אחרי סגירת הרשימה הם מופיעים ב"צריכים אתכם" — כדאי לסגור איתם תשובה לפני ההושבה.',
        ],
      },
      {
        when: CALLS_OFF,
        answer: [
          'הם לא מקבלים עוד תזכורות ב-WhatsApp.',
          'אחרי סגירת הרשימה הם מופיעים ב"צריכים אתכם" — כדאי לסגור איתם תשובה לפני ההושבה.',
        ],
      },
    ],
    primary: { kind: 'navigate', page: 'guests', guestFilter: 'maybe', label: 'למי שלא החליטו' },
    sources: [...SOURCES, '../../backend/app/communication.py', '../../backend/app/call_center.py'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'rsvp.no-answer',
    area: 'rsvp',
    title: 'מה קורה עם מי שלא עונים?',
    aliases: ['לא ענו', 'ממתינים', 'אין תשובה'],
    scopes: [{ scope: 'rsvp', weight: 65 }],
    when: MANAGER,
    sendsMessages: true,
    answer: [],
    variants: [
      {
        when: CALLS_ON,
        answer: [
          'הם ממשיכים לקבל תזכורות ב-WhatsApp ושיחות טלפון, עד סגירת הרשימה.',
          'אחרי הסגירה הם מופיעים ב"צריכים אתכם" — אפשר לבדוק איתם ישירות ולעדכן ברשימה.',
        ],
      },
      {
        when: CALLS_OFF,
        answer: [
          'הם ממשיכים לקבל תזכורות ב-WhatsApp, עד סגירת הרשימה.',
          'אחרי הסגירה הם מופיעים ב"צריכים אתכם" — אפשר לבדוק איתם ישירות ולעדכן ברשימה.',
        ],
      },
    ],
    primary: { kind: 'navigate', page: 'guests', guestFilter: 'pending', label: 'למי שעוד לא ענו' },
    sources: [...SOURCES, ...SERVER],
    verifiedAt: VERIFIED,
  },
  {
    id: 'rsvp.guests-can-confirm',
    area: 'rsvp',
    title: 'ממתי ה{guests} יכולים לאשר הגעה?',
    aliases: ['הקישור', 'לא יכולים לאשר', 'כפתור אישור', 'לינק'],
    scopes: [
      { scope: 'rsvp', weight: 60 },
      { scope: 'messages', weight: 40 },
    ],
    when: MANAGER,
    sendsMessages: true,
    answer: [],
    variants: [
      {
        when: { fact: 'rsvp.phase', op: '==', value: 'before' },
        answer: ['מ{date:rsvp.start_date} — היום שבו יוצאת בקשת האישור הראשונה. עד אז הקישור מציג את ההזמנה בלבד.'],
      },
      {
        when: { fact: 'rsvp.phase', op: 'in', value: ['unscheduled', 'waiting'] },
        answer: [
          'מהיום שבו יוצאת בקשת האישור הראשונה — וזה קורה רק אחרי שתבחרו מועד סגירת רשימה.',
          'עד אז הקישור מציג את ההזמנה בלבד.',
        ],
        primary: { kind: 'tour', flow: 'choose-commit-date' },
      },
      {
        when: { fact: 'rsvp.phase', op: 'in', value: ['running', 'ended'] },
        answer: ['אישורי ההגעה כבר פתוחים — כל {guest} מאשר דרך הקישור האישי שלו.'],
      },
    ],
    sources: ['../../backend/app/guest_journey.py', '../../backend/app/routers/confirm.py'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'rsvp.update-manually',
    area: 'rsvp',
    title: 'איך מעדכנים ידנית שמישהו אישר?',
    aliases: ['עדכון ידני', 'אישר בטלפון', 'לסמן שמגיע', 'לשנות סטטוס'],
    scopes: [
      { scope: 'rsvp', weight: 55 },
      { scope: 'guests', weight: 40 },
      { scope: 'guests.edit', weight: 70 },
    ],
    when: MANAGER,
    answer: ['פותחים את ה{guest} ב"ניהול {guests}", ובוחרים ב"{ui:guests.rsvpStatusLabel}".'],
    sources: ['components/AddGuestForm.tsx', 'strings/he.ts', 'App.tsx'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'rsvp.event-day',
    area: 'rsvp',
    title: 'מה ה{guests} מקבלים ביום האירוע?',
    aliases: ['יום האירוע', 'מספר שולחן', 'הודעת תודה', 'ניווט'],
    scopes: [{ scope: 'rsvp', weight: 45 }],
    sendsMessages: true,
    answer: [
      'מי שאישרו הגעה מקבלים ביום האירוע הודעה עם מספר השולחן וניווט למקום.',
      'יום אחרי האירוע יוצאת הודעת תודה.',
    ],
    sources: ['components/RsvpPage.tsx', '../../backend/app/rsvp_timeline.py'],
    verifiedAt: VERIFIED,
  },
]

export const RSVP_TREES: readonly DiagnosticTree[] = [
  {
    id: 'reminders-not-sent',
    area: 'rsvp',
    symptom: 'בקשות אישור ההגעה לא יוצאות',
    scopes: [
      { scope: 'rsvp', weight: 80 },
      { scope: 'messages', weight: 50 },
    ],
    sendsMessages: true,
    root: 'date',
    nodes: {
      date: { kind: 'check', test: { fact: 'event.has_date', op: '==', value: true }, yes: 'commit', no: 'out-no-date' },
      commit: { kind: 'check', test: { fact: 'rsvp.phase', op: 'in', value: ['unscheduled', 'waiting'] }, yes: 'out-no-commit', no: 'postponed' },
      postponed: { kind: 'check', test: { fact: 'event.postpone', op: 'in', value: ['pending', 'approved'] }, yes: 'out-postponed', no: 'stopped' },
      stopped: { kind: 'check', test: { fact: 'messaging.emergency_stop', op: '==', value: true }, yes: 'out-stopped', no: 'before' },
      before: { kind: 'check', test: { fact: 'rsvp.phase', op: '==', value: 'before' }, yes: 'out-before', no: 'ended' },
      ended: { kind: 'check', test: { fact: 'rsvp.phase', op: '==', value: 'ended' }, yes: 'out-ended', no: 'weekend' },
      weekend: { kind: 'check', test: { fact: 'rsvp.today_is_weekend', op: '==', value: true }, yes: 'out-weekend', no: 'out-running' },
      'out-no-date': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['לאירוע עוד אין תאריך. בלי תאריך ומועד סגירת רשימה אי אפשר לבנות את הלוח.'],
        action: { kind: 'navigate', page: 'dashboard', label: 'לתמונת המצב' },
      },
      'out-no-commit': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['עוד לא נבחר מועד סגירת רשימה. רק אחרי הבחירה בקשות אישור ההגעה מתחילות לצאת.'],
        action: { kind: 'tour', flow: 'choose-commit-date' },
      },
      'out-postponed': {
        kind: 'outcome', resolution: 'explained',
        text: ['יש בקשה פתוחה לשינוי מועד. עד שהמועד החדש ייקבע, לא שולחים בקשות אישור הגעה.'],
      },
      'out-stopped': {
        kind: 'outcome', resolution: 'veya_side', offerTeam: true,
        text: ['השליחה עצורה זמנית מצד VEYA. זה לא משהו שצריך לתקן אצלכם.'],
      },
      'out-before': {
        kind: 'outcome', resolution: 'explained',
        text: ['הכול מוכן. הבקשה הראשונה תצא ב{date:rsvp.start_date}.'],
      },
      'out-ended': {
        kind: 'outcome', resolution: 'explained',
        text: ['הרשימה נסגרה ב{date:rsvp.commit_date}. אחרי מועד הסגירה לא יוצאות בקשות.'],
      },
      'out-weekend': {
        kind: 'outcome', resolution: 'explained',
        text: ['בשישי ובשבת לא יוצאות בקשות אישור הגעה. הצעד הבא: {text:rsvp.next_label}, ב{date:rsvp.next_date}.'],
      },
      'out-running': {
        kind: 'outcome', resolution: 'explained', offerTeam: true,
        text: [
          'הלוח פועל. הצעד הבא: {text:rsvp.next_label}, ב{date:rsvp.next_date}.',
          'בקשות יוצאות רק למי שעוד לא ענו, ובשעה שבחרתם — ולא בדיעבד: סבב שהיום שלו עבר לא נשלח מאוחר יותר.',
        ],
      },
    },
    sources: [...SERVER, '../../backend/app/rsvp_scheduler.py', '../../backend/app/messaging.py'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'reminder-not-received',
    area: 'rsvp',
    symptom: 'בקשת אישור הגעה לא הגיעה ל{guest}',
    scopes: [{ scope: 'rsvp', weight: 55 }],
    needsGuest: true,
    root: 'mock',
    nodes: {
      mock: { kind: 'check', test: { fact: 'messaging.mode', op: '==', value: 'mock' }, yes: 'out-mock', no: 'phase' },
      phase: { kind: 'check', test: { fact: 'rsvp.phase', op: 'in', value: ['running', 'ended'] }, yes: 'answered', no: 'out-not-started' },
      answered: { kind: 'check', test: { fact: 'guest.rsvp', op: '==', value: 'pending' }, yes: 'phone', no: 'out-answered' },
      phone: { kind: 'check', test: { fact: 'guest.phone', op: '==', value: 'valid' }, yes: 'joined', no: 'out-bad-phone' },
      joined: { kind: 'check', test: { fact: 'guest.joined_after_last_round', op: '==', value: true }, yes: 'out-joined-late', no: 'out-unknown' },
      'out-mock': {
        kind: 'outcome', resolution: 'explained',
        text: [MOCK_NOTICE],
      },
      'out-not-started': {
        kind: 'outcome', resolution: 'explained',
        text: ['בקשות אישור ההגעה עוד לא התחילו לצאת.'],
        action: { kind: 'diagnose', tree: 'reminders-not-sent', label: 'למה עוד לא?' },
      },
      'out-answered': {
        kind: 'outcome', resolution: 'explained',
        text: ['ה{guest} הזה כבר ענה — בקשות יוצאות רק למי שעוד ממתינים לתשובה.'],
      },
      'out-bad-phone': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['ל{guest} הזה אין מספר טלפון תקין, ולכן לא נשלחות בקשות.'],
        action: { kind: 'tour', flow: 'fix-phone', label: 'תראו לי איך מתקנים' },
      },
      'out-joined-late': {
        kind: 'outcome', resolution: 'explained',
        text: ['ה{guest} נוסף אחרי שהסבב האחרון יצא, ויצטרף לסבב הבא — לא שולחים בדיעבד.'],
      },
      'out-unknown': {
        kind: 'outcome', resolution: 'unknown', offerTeam: true,
        text: ['לא מצאנו סיבה שהבקשה לא הגיעה.'],
      },
    },
    sources: [...SERVER, '../../backend/app/invitations.py'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'guest-cant-confirm',
    area: 'rsvp',
    symptom: 'אי אפשר לאשר הגעה בקישור',
    scopes: [
      { scope: 'rsvp', weight: 60 },
      { scope: 'messages', weight: 40 },
    ],
    sendsMessages: true,
    root: 'what',
    nodes: {
      what: {
        kind: 'ask',
        question: 'מה כתוב כשפותחים את הקישור?',
        options: [
          { label: '"אישורי ההגעה עדיין לא נפתחו"', next: 'phase' },
          { label: '"הקישור כבר לא פעיל"', next: 'out-dead-link' },
          { label: 'משהו אחר', next: 'out-other' },
        ],
      },
      phase: { kind: 'check', test: { fact: 'rsvp.phase', op: 'in', value: ['unscheduled', 'waiting'] }, yes: 'out-no-commit', no: 'before' },
      before: { kind: 'check', test: { fact: 'rsvp.phase', op: '==', value: 'before' }, yes: 'out-before', no: 'out-other' },
      'out-no-commit': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['אישורי ההגעה נפתחים ביום שבו יוצאת בקשת האישור הראשונה — וזה קורה רק אחרי שתבחרו מועד סגירת רשימה.'],
        action: { kind: 'tour', flow: 'choose-commit-date' },
      },
      'out-before': {
        kind: 'outcome', resolution: 'explained',
        text: ['זה תקין: אפשר לאשר מ{date:rsvp.start_date}. עד אז הקישור מציג את ההזמנה בלבד, ומתעדכן מעצמו.'],
      },
      'out-dead-link': {
        kind: 'outcome', resolution: 'explained',
        text: [
          'הקישור לא מוביל לאף {guest} ברשימה — למשל אם ה{guest} הוסר מהרשימה, או שהקישור הועתק חלקית.',
          'אם ה{guest} נוסף מחדש, יש לו קישור חדש — והוא יוצא עם "שליחת הזמנות".',
        ],
      },
      'out-other': {
        kind: 'outcome', resolution: 'unknown', offerTeam: true,
        text: ['לא זיהינו את הבעיה מכאן.'],
      },
    },
    sources: ['../../backend/app/routers/confirm.py', '../../backend/app/guest_journey.py', 'components/MessagesPage.tsx'],
    verifiedAt: VERIFIED,
  },
]
