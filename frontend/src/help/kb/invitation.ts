/**
 * ידע: שליחת ההזמנה (HELP_CENTER_PLAN.md — שלב 2, חלק 2).
 *
 * עובדות שמאחורי הניסוחים (אומתו ב-2026-09-29):
 * - ההזמנה נשלחת **רק** בלחיצה "שליחת הזמנות", מיד (strings.messages.when.invitation).
 *   היא לא מבקשת אישור הגעה — הכפתור שלה "צפייה בהזמנה" (CommunicationTab).
 *   בקשות אישור ההגעה נפרדות, לפי מועד סגירת הרשימה (inviteIsSeparate).
 * - כל מוזמן מקבל הזמנה פעם אחת; שליחה חוזרת למי שכבר קיבל — לאדמין בלבד
 *   (routers/automation.py::activate_track). מי שהשליחה אליו נכשלה — לא נחשב
 *   "קיבל", ולכן נכלל שוב ("ניסיון חוזר לנכשלים" / "שליחת הזמנות").
 * - בלי מספר תקין — מדלגים (invitations.classify_phone).
 * - עצירת חירום → כל שליחה נרשמת כנכשלת (messaging.StoppedProvider).
 * - נוסח ריק → מדלגים על כולם, והחלון מציג אותם כ"בלי טלפון" (באג ידוע,
 *   לא מתוקן במסגרת העזרה — העזרה בודקת נוסח ריק **לפני** טלפון).
 * - WhatsApp במצב mock → נרשם, לא נשלח (sendsMessages + MOCK_NOTICE).
 */
import type { DiagnosticTree, GuidedFlow, HelpTopic } from '../types'
import { MANAGER, MOCK_NOTICE, VERIFIED } from './shared'

const SOURCES = ['components/MessagesPage.tsx', 'components/CommunicationTab.tsx', 'strings/he.ts', 'App.tsx']
const SERVER = ['../../backend/app/routers/automation.py', '../../backend/app/invitations.py']

export const INVITATION_TOPICS: readonly HelpTopic[] = [
  {
    id: 'invitation.how-to-send',
    area: 'invitation',
    title: 'איך שולחים את ההזמנה?',
    aliases: ['שליחה', 'לשלוח הזמנה', 'הזמנה בוואטסאפ', 'לשלוח למוזמנים'],
    scopes: [
      { scope: 'messages', weight: 80 },
      { scope: 'messages.wizard.review', weight: 100 },
      { scope: 'dashboard', weight: 25 },
    ],
    when: MANAGER,
    sendsMessages: true,
    answer: [],
    variants: [
      {
        when: { fact: 'invites.sent', op: '==', value: 0 },
        answer: [
          'במסך "ניהול הודעות": בוחרים נוסח, בודקים את ה{guests}, ולוחצים "שליחת הזמנות".',
          'לפני השליחה רואים בדיוק את ההודעה ולמי היא תצא.',
        ],
      },
      {
        when: { fact: 'invites.sent', op: '>', value: 0 },
        answer: ['במסך "ניהול הודעות" לוחצים "שליחת הזמנות" — היא יוצאת רק למי שעוד לא קיבל.'],
      },
    ],
    primary: { kind: 'tour', flow: 'send-invitations' },
    related: ['invitation.vs-rsvp', 'invitation.who-wont-get'],
    sources: SOURCES,
    verifiedAt: VERIFIED,
    priority: 5,
  },
  {
    id: 'invitation.vs-rsvp',
    area: 'invitation',
    title: 'מה ההבדל בין ההזמנה לאישור ההגעה?',
    aliases: ['הזמנה ואישור', 'למה אין כפתור אישור', 'אישור הגעה בהזמנה'],
    scopes: [
      { scope: 'messages', weight: 70 },
      { scope: 'rsvp', weight: 60 },
      { scope: 'dashboard', weight: 25 },
    ],
    sendsMessages: true,
    answer: [
      'ההזמנה יוצאת כשלוחצים "שליחת הזמנות", והיא לא מבקשת לאשר הגעה — יש בה רק "צפייה בהזמנה".',
      'בקשות אישור ההגעה יוצאות בנפרד, לפי לוח הזמנים שנבנה ממועד סגירת הרשימה.',
    ],
    related: ['rsvp.when-requests'],
    sources: [...SOURCES, '../../backend/app/communication.py'],
    verifiedAt: VERIFIED,
    priority: 4,
  },
  {
    id: 'invitation.resend',
    area: 'invitation',
    title: 'אפשר לשלוח הזמנה שוב למי שכבר קיבל?',
    aliases: ['שליחה חוזרת', 'לשלוח שוב', 'שוב הזמנה', 'כבר קיבלו הזמנה'],
    scopes: [
      { scope: 'messages.sendDialog', weight: 70 },
      { scope: 'messages', weight: 40 },
    ],
    when: MANAGER,
    sendsMessages: true,
    answer: [
      'לא — כל {guest} מקבל הזמנה פעם אחת, כדי שאף אחד לא יקבל אותה פעמיים בטעות. בחלון השליחה הם מסומנים "כבר קיבלו הזמנה".',
      'מי שהשליחה אליו לא הצליחה — כן נכלל שוב ב"שליחת הזמנות".',
    ],
    sources: [...SOURCES, ...SERVER],
    verifiedAt: VERIFIED,
  },
  {
    id: 'invitation.who-wont-get',
    area: 'invitation',
    title: 'מי לא יקבל את ההזמנה?',
    aliases: ['לא יקבלו', 'בלי טלפון', 'חסרים', 'דולגו'],
    scopes: [
      { scope: 'messages.wizard.recipients', weight: 100 },
      { scope: 'messages.sendDialog', weight: 80 },
      { scope: 'messages', weight: 45 },
    ],
    when: MANAGER,
    urgentWhen: { all: [{ fact: 'guests.bad_phone', op: '>', value: 0 }, { fact: 'invites.not_yet', op: '>', value: 0 }] },
    sendsMessages: true,
    answer: [
      '{guests} בלי מספר טלפון תקין — עד שהמספר מתוקן.',
      'ומי שכבר קיבל — ההזמנה לא יוצאת פעמיים.',
    ],
    variants: [
      {
        when: { fact: 'guests.bad_phone', op: '>', value: 0 },
        answer: [
          '{count:guests.bad_phone|guest:ל} אין מספר טלפון תקין — ההזמנה לא תצא עד שהמספר יתוקן.',
          'ומי שכבר קיבל — ההזמנה לא יוצאת פעמיים.',
        ],
      },
    ],
    primary: { kind: 'tour', flow: 'fix-phone' },
    related: ['guests.fix-phones'],
    sources: [...SOURCES, ...SERVER],
    verifiedAt: VERIFIED,
  },
  {
    id: 'invitation.new-guests',
    area: 'invitation',
    title: 'הוספנו {guests} חדשים — איך הם יקבלו הזמנה?',
    aliases: ['מוזמנים חדשים', 'הוספתי מוזמן', 'אחרי השליחה', 'מוזמן חדש'],
    scopes: [
      { scope: 'messages', weight: 50 },
      { scope: 'guests', weight: 30 },
      { scope: 'rsvp', weight: 30 },
    ],
    when: { all: [MANAGER, { fact: 'invites.sent', op: '>', value: 0 }] },
    sendsMessages: true,
    answer: [
      'ההזמנה לא נשלחת לבד: לוחצים "שליחת הזמנות", והיא יוצאת רק למי שעוד לא קיבל.',
      'בקשות אישור ההגעה יגיעו אליהם בסבבים שיוצאים אחרי שנוספו.',
    ],
    primary: { kind: 'tour', flow: 'send-invitations' },
    sources: [...SOURCES, '../../backend/app/communication.py'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'invitation.wording',
    area: 'invitation',
    title: 'איך בוחרים נוסח להזמנה?',
    aliases: ['נוסח', 'טקסט ההזמנה', 'לשנות את ההודעה', 'לערוך הזמנה', 'נוסחים מוכנים'],
    scopes: [
      { scope: 'messages.wizard.design', weight: 100 },
      { scope: 'messages', weight: 55 },
    ],
    when: MANAGER,
    answer: [
      'בכרטיס ההזמנה: "בחירת הודעה" — עוברים בין הנוסחים ולוחצים "בחירת ההודעה הזו".',
      'אפשר גם "עריכה" ולכתוב בעצמכם.',
    ],
    sources: ['components/CommunicationTab.tsx'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'invitation.missing-details',
    area: 'invitation',
    title: 'למה כתוב שבהזמנה חסרים פרטים?',
    aliases: ['חסרים פרטים', 'אין שעה', 'אין כתובת', 'אין מקום'],
    scopes: [{ scope: 'messages.wizard.review', weight: 90 }],
    when: MANAGER,
    sendsMessages: true,
    answer: [
      'שעת האירוע, שם המקום או הכתובת עוד לא מולאו — וההזמנה תצא בלעדיהם.',
      'משלימים ב"{ui:dashboard.editDetailsButton}" בתמונת המצב.',
    ],
    primary: { kind: 'navigate', page: 'dashboard', label: 'לתמונת המצב' },
    sources: ['components/MessagesPage.tsx', 'strings/he.ts'],
    verifiedAt: VERIFIED,
  },
]

export const INVITATION_FLOWS: readonly GuidedFlow[] = [
  {
    id: 'send-invitations',
    when: { all: [MANAGER, { fact: 'invites.not_yet', op: '>', value: 0 }] },
    sendsMessages: true,
    start: { page: 'messages' },
    steps: [
      // לפני הזמנה ראשונה — האשף (3 שלבים). מדלגים על שלב שכבר עברו.
      {
        target: 'messages.wizardToGuests',
        text: 'לחצו "המשך למוזמנים"',
        advanceOn: { kind: 'scope', scope: 'messages.wizard.recipients' },
        when: { all: [{ fact: 'invites.sent', op: '==', value: 0 }, { fact: 'messages.wizardStep', op: '==', value: 1 }] },
      },
      {
        target: 'messages.wizardToReview',
        text: 'בדקו את הרשימה ולחצו "המשך לתצוגה"',
        advanceOn: { kind: 'scope', scope: 'messages.wizard.review' },
        when: { all: [{ fact: 'invites.sent', op: '==', value: 0 }, { fact: 'messages.wizardStep', op: '<=', value: 2 }] },
      },
      {
        target: 'messages.wizardSend',
        text: 'לחצו "שליחת הזמנות"',
        advanceOn: { kind: 'scope', scope: 'messages.sendDialog' },
        when: { fact: 'invites.sent', op: '==', value: 0 },
      },
      // אחרי שכבר יצאו הזמנות — הכפתור שמתחת לכרטיסי ההודעות.
      {
        target: 'messages.sendMore',
        text: 'לחצו "שליחת הזמנות"',
        advanceOn: { kind: 'scope', scope: 'messages.sendDialog' },
        when: { fact: 'invites.sent', op: '>', value: 0 },
      },
      {
        target: 'messages.sendConfirm',
        text: 'בדקו את ההודעה ואת הנמענים, ולחצו כאן כדי לשלוח',
        advanceOn: { kind: 'api', method: 'POST', path: '/automation/track/activate' },
      },
    ],
    success: { kind: 'api', method: 'POST', path: '/automation/track/activate' },
    doneText: 'זהו. החלון מראה בדיוק מה קרה, ומי שהשליחה אליו לא הצליחה מופיע שם.',
    sources: [...SOURCES, ...SERVER],
    verifiedAt: VERIFIED,
  },
]

export const INVITATION_TREES: readonly DiagnosticTree[] = [
  {
    id: 'invite-not-sent',
    area: 'invitation',
    symptom: 'לא מצליחים לשלוח את ההזמנה',
    scopes: [
      { scope: 'messages', weight: 70 },
      { scope: 'messages.sendDialog', weight: 90 },
    ],
    when: MANAGER,
    sendsMessages: true,
    errorMatch: [{ method: 'POST', path: '/automation/track/activate' }],
    root: 'offline',
    nodes: {
      offline: { kind: 'check', test: { fact: 'client.online', op: '==', value: false }, yes: 'out-offline', no: 'stopped', unknown: 'stopped' },
      stopped: { kind: 'check', test: { fact: 'messaging.emergency_stop', op: '==', value: true }, yes: 'out-stopped', no: 'no-guests' },
      'no-guests': { kind: 'check', test: { fact: 'guests.total', op: '==', value: 0 }, yes: 'out-no-guests', no: 'empty' },
      // נוסח ריק נבדק לפני הטלפונים: במקרה הזה החלון מציג את כולם כ"בלי טלפון".
      empty: { kind: 'check', test: { fact: 'messaging.invitation_empty', op: '==', value: true }, yes: 'out-empty', no: 'nothing-left' },
      'nothing-left': { kind: 'check', test: { fact: 'invites.not_yet', op: '==', value: 0 }, yes: 'bad-left', no: 'out-unknown' },
      'bad-left': { kind: 'check', test: { fact: 'guests.bad_phone', op: '>', value: 0 }, yes: 'out-only-bad', no: 'out-all-sent' },
      'out-offline': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['נראה שאין חיבור לאינטרנט כרגע. כשהחיבור יחזור — אפשר לנסות שוב.'],
      },
      'out-stopped': {
        kind: 'outcome', resolution: 'veya_side', offerTeam: true,
        text: ['השליחה עצורה זמנית מצד VEYA. זה לא משהו שצריך לתקן אצלכם.'],
      },
      'out-no-guests': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['עוד אין {guests} ברשימה — מוסיפים אותם, ואז שולחים.'],
        action: { kind: 'tour', flow: 'add-guest', label: 'תראו לי איך מוסיפים' },
      },
      'out-empty': {
        kind: 'outcome', resolution: 'user_fix',
        text: [
          'להזמנה עוד אין נוסח. בוחרים נוסח בכרטיס ההזמנה, ואז שולחים.',
          'אם חלון השליחה אמר שחסר מספר טלפון — הסיבה האמיתית היא הנוסח החסר.',
        ],
      },
      'out-only-bad': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['כל מי שעוד לא קיבל הזמנה — בלי מספר טלפון תקין. אחרי שהמספר יתוקן, אפשר לשלוח אליו.'],
        action: { kind: 'tour', flow: 'fix-phone', label: 'תראו לי איך מתקנים' },
      },
      'out-all-sent': {
        kind: 'outcome', resolution: 'explained',
        text: ['כל ה{guests} כבר מסומנים "כבר קיבלו הזמנה" — ההזמנה לא יוצאת פעמיים.'],
      },
      'out-unknown': {
        kind: 'outcome', resolution: 'unknown', offerTeam: true,
        text: ['יש למי לשלוח, ולא זיהינו מה עצר את השליחה.'],
      },
    },
    sources: [...SOURCES, ...SERVER, '../../backend/app/messaging.py'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'invite-not-received',
    area: 'invitation',
    symptom: 'ההזמנה לא הגיעה ל{guest}',
    scopes: [
      { scope: 'messages', weight: 60 },
      { scope: 'rsvp', weight: 50 },
      { scope: 'guests', weight: 30 },
    ],
    when: MANAGER,
    needsGuest: true,
    root: 'mock',
    nodes: {
      // קודם כול: האם הודעות בכלל יוצאות. במצב הדגמה — לא, ולכן אין מה לבדוק מעבר.
      mock: { kind: 'check', test: { fact: 'messaging.mode', op: '==', value: 'mock' }, yes: 'out-mock', no: 'stopped' },
      stopped: { kind: 'check', test: { fact: 'messaging.emergency_stop', op: '==', value: true }, yes: 'out-stopped', no: 'phone' },
      phone: { kind: 'check', test: { fact: 'guest.phone', op: '==', value: 'valid' }, yes: 'status', no: 'out-bad-phone' },
      status: { kind: 'check', test: { fact: 'guest.invitation', op: '==', value: 'none' }, yes: 'out-not-sent', no: 'failed' },
      failed: { kind: 'check', test: { fact: 'guest.invitation', op: '==', value: 'failed' }, yes: 'out-failed', no: 'blocked' },
      blocked: { kind: 'check', test: { fact: 'guest.invitation', op: '==', value: 'blocked' }, yes: 'out-blocked', no: 'arrived' },
      arrived: { kind: 'check', test: { fact: 'guest.invitation', op: 'in', value: ['delivered', 'read'] }, yes: 'out-delivered', no: 'out-sent' },
      'out-mock': { kind: 'outcome', resolution: 'explained', text: [MOCK_NOTICE] },
      'out-stopped': {
        kind: 'outcome', resolution: 'veya_side', offerTeam: true,
        text: ['השליחה עצורה זמנית מצד VEYA. זה לא משהו שצריך לתקן אצלכם.'],
      },
      'out-bad-phone': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['ל{guest} הזה אין מספר טלפון תקין, ולכן ההזמנה לא נשלחה. אחרי שהמספר יתוקן — שולחים.'],
        action: { kind: 'tour', flow: 'fix-phone', label: 'תראו לי איך מתקנים' },
      },
      'out-not-sent': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['ההזמנה עוד לא נשלחה ל{guest} הזה. "שליחת הזמנות" תשלח אותה — רק למי שעוד לא קיבל.'],
        action: { kind: 'tour', flow: 'send-invitations' },
      },
      'out-failed': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['השליחה ל{guest} הזה לא הצליחה. "שליחת הזמנות" תנסה שוב — מי שהשליחה אליו לא הצליחה נכלל בה.'],
        action: { kind: 'tour', flow: 'send-invitations' },
      },
      'out-blocked': {
        kind: 'outcome', resolution: 'explained',
        text: ['נראה שהמספר של VEYA חסום אצל ה{guest} ב-WhatsApp, ולכן ההודעות לא מגיעות. כדאי ליצור קשר ישירות.'],
      },
      'out-delivered': {
        kind: 'outcome', resolution: 'explained',
        text: [
          'WhatsApp אישרה שההזמנה הגיעה לטלפון של ה{guest}. כדאי לבדוק ב-WhatsApp, גם בצ\'אטים שבארכיון.',
        ],
      },
      'out-sent': {
        kind: 'outcome', resolution: 'explained', offerTeam: true,
        text: [
          'ההזמנה יצאה, ועדיין לא קיבלנו מ-WhatsApp אישור שהיא הגיעה לטלפון.',
          'כדאי לוודא שהמספר ברשימה נכון.',
        ],
      },
    },
    sources: [...SOURCES, ...SERVER, '../../backend/app/message_status.py', '../../backend/app/messaging.py'],
    verifiedAt: VERIFIED,
  },
]
