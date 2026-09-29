/**
 * ידע: סידור ההושבה (HELP_CENTER_PLAN.md — שלב 2, חלק 2).
 *
 * במסך ההושבה כבר יש מדריך — "איך זה עובד?" (help/guides.ts). העזרה מפנה
 * אליו ולא מסבירה במקביל (החלטת המייסד 2026-09-29: חוויית עזרה אחת).
 *
 * עובדות שמאחורי הניסוחים (אומתו ב-2026-09-29):
 * - "הושבה בקליק" מושיבה רק מי שאישרו הגעה, ומסדרת מחדש את כולם
 *   (routers/seating.py::generate). "השלמת מי שללא שולחן" — רק מי שאין לו
 *   שולחן (strings.hall.fillEmptyHint).
 * - "החזרת הסידור הקודם" — רק אחרי הושבה בקליק, לסידור האחרון בלבד
 *   (Event.seating_snapshot; מתאפס אחרי שחזור).
 * - רק "אישרו הגעה" תופסים מקום; מי ששינה סטטוס נשאר על השולחן ונספר 0
 *   (models.Guest.effective_seats).
 * - שגיאות "הושבה בקליק" — הניסוחים ב-routers/seating.py.
 */
import type { DiagnosticTree, GuidedFlow, HelpTopic } from '../types'
import { MANAGER, VERIFIED } from './shared'

const SOURCES = ['components/HallPage.tsx', 'components/SeatingGuestPanel.tsx', 'strings/he.ts']
const SERVER = ['../../backend/app/routers/seating.py', '../../backend/app/models.py']
const GUIDE = { kind: 'guide', guide: 'hall', label: 'למדריך "איך זה עובד?"' } as const

export const SEATING_TOPICS: readonly HelpTopic[] = [
  {
    id: 'seating.how',
    area: 'seating',
    title: 'איך מושיבים {guest} לשולחן?',
    aliases: ['להושיב', 'שולחן', 'גרירה', 'לשבץ', 'להעביר שולחן'],
    scopes: [{ scope: 'hall', weight: 90 }],
    when: MANAGER,
    answer: [],
    variants: [
      {
        when: { fact: 'layout.hallDesktop', op: '==', value: true },
        answer: ['גוררים {guest} מהרשימה שבצד אל שולחן במפה — או בוחרים {guest} ומקישים על השולחן.'],
      },
      {
        when: { fact: 'layout.hallDesktop', op: '==', value: false },
        answer: ['לוחצים "{guests}" בפס התחתון, בוחרים {guest} ומקישים על שולחן במפה.'],
      },
    ],
    primary: GUIDE,
    related: ['seating.one-click'],
    sources: SOURCES,
    verifiedAt: VERIFIED,
    priority: 5,
  },
  {
    id: 'seating.one-click',
    area: 'seating',
    title: 'מה עושה "הושבה בקליק"?',
    aliases: ['הושבה אוטומטית', 'סידור אוטומטי', 'בקליק', 'אלגוריתם'],
    scopes: [{ scope: 'hall', weight: 85 }],
    when: MANAGER,
    answer: [
      'סידור אוטומטי לפי הקבוצות, הערות ההושבה, האילוצים ומבנה האולם.',
      'היא מושיבה רק את מי שאישרו הגעה, ומסדרת מחדש את כולם. אחרי ההרצה אפשר להזיז כל {guest}.',
    ],
    primary: { kind: 'tour', flow: 'one-click-seating' },
    related: ['seating.fill-empty', 'seating.undo'],
    sources: [...SOURCES, ...SERVER],
    verifiedAt: VERIFIED,
    priority: 4,
  },
  {
    id: 'seating.fill-empty',
    area: 'seating',
    title: 'מה ההבדל בין שני כפתורי ההושבה?',
    aliases: ['השלמה', 'מי שללא שולחן', 'בלי לשנות את כולם'],
    scopes: [{ scope: 'hall', weight: 55 }],
    when: MANAGER,
    answer: [
      '"{ui:hall.oneClickButton}" מסדרת מחדש את כל מי שאישרו הגעה.',
      '"{ui:hall.fillEmptyButton}" משבצת רק את מי שעדיין אין לו שולחן — אף אחד מהמשובצים לא זז.',
    ],
    sources: SOURCES,
    verifiedAt: VERIFIED,
  },
  {
    id: 'seating.undo',
    area: 'seating',
    title: 'איך מחזירים את הסידור הקודם?',
    aliases: ['ביטול', 'לבטל הושבה', 'חזרה אחורה', 'undo'],
    scopes: [{ scope: 'hall', weight: 60 }],
    when: MANAGER,
    answer: [],
    variants: [
      {
        when: { fact: 'seating.undo_available', op: '==', value: true },
        answer: ['בלוח ההושבה: "החזרת הסידור הקודם" — כל ה{guests} חוזרים למקומות שהיו לפני ההושבה בקליק.'],
      },
      {
        when: { fact: 'seating.undo_available', op: '==', value: false },
        answer: ['הכפתור "החזרת הסידור הקודם" מופיע רק אחרי "{ui:hall.oneClickButton}", ומחזיר רק את הסידור שלפני ההרצה האחרונה.'],
      },
    ],
    sources: [...SOURCES, ...SERVER],
    verifiedAt: VERIFIED,
  },
  {
    id: 'seating.not-counted',
    area: 'seating',
    title: 'למה יש מי שיושבים בשולחן ולא נספרים?',
    aliases: ['לא נספר', 'מקום פנוי', 'ספירה בשולחן', 'ביטל הגעה'],
    scopes: [{ scope: 'hall', weight: 45 }],
    answer: [
      'רק מי שאישרו הגעה תופסים מקום. מי שעוד לא ענו, לא החליטו או לא מגיעים — נשארים על השולחן, אבל נספרים כ-0.',
      'כשמגיע אישור הגעה, המקום נספר שוב מעצמו.',
    ],
    sources: SERVER,
    verifiedAt: VERIFIED,
  },
  {
    id: 'seating.guide',
    area: 'seating',
    title: 'איך עובד סידור ההושבה?',
    aliases: ['מדריך', 'הסבר', 'איך זה עובד', 'מפת האולם'],
    scopes: [{ scope: 'hall', weight: 70 }],
    when: MANAGER,
    answer: ['יש מדריך קצר בתוך המסך — סימן השאלה "איך זה עובד?" בפס העליון.'],
    primary: GUIDE,
    sources: ['components/HallPage.tsx'],
    verifiedAt: VERIFIED,
    priority: 2,
  },
]

export const SEATING_FLOWS: readonly GuidedFlow[] = [
  {
    id: 'one-click-seating',
    when: { all: [MANAGER, { fact: 'guests.confirmed', op: '>', value: 0 }] },
    start: { page: 'hall' },
    steps: [
      { target: 'hall.seatingTab', text: 'לחצו "{ui:hall.workspace.tabSeating}"', advanceOn: { kind: 'visible', target: 'hall.oneClick' } },
      { target: 'hall.oneClick', text: 'לחצו "{ui:hall.oneClickButton}"', advanceOn: { kind: 'api', method: 'POST', path: '/seating/generate' } },
    ],
    success: { kind: 'api', method: 'POST', path: '/seating/generate' },
    doneText: 'הסידור מוכן. אפשר להזיז כל {guest}, ואם צריך — "החזרת הסידור הקודם".',
    onError: [{ match: { method: 'POST', path: '/seating/generate' }, tree: 'seating-failed' }],
    sources: [...SOURCES, ...SERVER],
    verifiedAt: VERIFIED,
  },
]

export const SEATING_TREES: readonly DiagnosticTree[] = [
  {
    id: 'seating-failed',
    area: 'seating',
    symptom: '"הושבה בקליק" לא עבדה',
    scopes: [{ scope: 'hall', weight: 80 }],
    when: MANAGER,
    errorMatch: [{ method: 'POST', path: '/seating/generate' }],
    root: 'offline',
    nodes: {
      offline: { kind: 'check', test: { fact: 'error.last.status', op: '==', value: 0 }, yes: 'out-offline', no: 'no-guests', unknown: 'out-no-error' },
      'no-guests': { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'אין מוזמנים לשיבוץ' }, yes: 'out-no-guests', no: 'no-confirmed', unknown: 'out-unknown' },
      'no-confirmed': { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'אין מוזמנים שאישרו הגעה' }, yes: 'out-no-confirmed', no: 'big-party' },
      'big-party': { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'חבורה גדולה' }, yes: 'out-big-party', no: 'reserve' },
      reserve: { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'הרזרבה גדולה מדי' }, yes: 'out-reserve', no: 'out-unknown' },
      'out-offline': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['נראה שאין חיבור לאינטרנט כרגע. כשהחיבור יחזור — אפשר לנסות שוב.'],
      },
      'out-no-guests': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['עוד אין {guests} ברשימה.'],
        action: { kind: 'navigate', page: 'guests', label: 'לניהול ה{guests}' },
      },
      'out-no-confirmed': {
        kind: 'outcome', resolution: 'explained',
        text: [
          '"{ui:hall.oneClickButton}" מושיבה רק את מי שאישרו הגעה — ועוד אין כאלה.',
          'אפשר להושיב ידנית גם מי שעוד לא ענו: תופיע שאלה, והמקום ייספר רק כשיאשרו.',
        ],
        action: GUIDE,
      },
      'out-big-party': {
        kind: 'outcome', resolution: 'user_fix',
        text: [
          'באחת ההזמנות יש יותר אנשים ממספר המקומות בשולחן.',
          'אפשר להגדיל את "מקומות ברירת מחדל לשולחן" בכלים של מפת האולם, או לפצל את ההזמנה לשתי שורות ברשימה.',
        ],
      },
      'out-reserve': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['הרזרבה גדולה מדי למספר השולחנות. אפשר להקטין אותה, או להוסיף שולחנות.'],
      },
      'out-no-error': {
        kind: 'outcome', resolution: 'unknown', offerTeam: true,
        text: ['לא ראינו שגיאה בהרצה האחרונה.', 'אם הופיע "הסידור לא נשמר" — מתחתיו כתוב בדיוק מה לא הצלחנו לפתור.'],
      },
      'out-unknown': {
        kind: 'outcome', resolution: 'unknown', offerTeam: true,
        text: ['לא זיהינו מה עצר את ההושבה.'],
      },
    },
    sources: [...SERVER, 'components/HallPage.tsx', 'strings/he.ts'],
    verifiedAt: VERIFIED,
  },
]
