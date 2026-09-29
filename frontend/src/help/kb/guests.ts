/**
 * ידע: ניהול המוזמנים (HELP_CENTER_PLAN.md — שלב 2, חלק 1).
 *
 * כל משפט כאן אומת מול הקוד ב-2026-09-29. עובדות שמאחורי הניסוחים:
 * - הוספה ידנית, הדבקה וייבוא — **כולם** דורשים מספר ישראלי תקין
 *   (schemas.GuestCreate → validators.normalize_israeli_phone). מספר מחו"ל
 *   לא עובר. לכן "בלי מספר תקין" מגיע רק מנתונים ישנים או מדיווח של צוות
 *   השיחות ("המספר לא הוביל אליו") — העזרה לא מסבירה *איך* זה קרה, רק מה עושים.
 * - ייבוא קובץ: ‎.csv / ‎.xlsx / ‎.xlsm בלבד (importer.parse_file), עד 5MB
 *   ו-5,000 שורות (routers/import_guests.py), חובה עמודת שם ועמודת טלפון.
 * - כפילות = אותו מספר טלפון שכבר ברשימה (import_guests._phone_key).
 * - אנשי קשר: רק כשהדפדפן תומך (ContactsImportDialog — Chrome באנדרואיד).
 * - מחיקה: מסירה גם מסידור ההושבה ומההודעות שעוד לא יצאו, בלי ביטול
 *   (strings.guests.deleteConfirm).
 * - "מוזמנים" = שורות; "אנשים" = סכום הכמויות (strings.guests.summary).
 *
 * כפתורים מצוטטים דרך ``{ui:…}`` — הטקסט המדויק מ-strings/he.ts.
 */
import type { DiagnosticTree, GuidedFlow, HelpTopic } from '../types'
import { MANAGER, VERIFIED } from './shared'

const GUEST_SOURCES = [
  'components/GuestsPage.tsx',
  'components/AddGuestForm.tsx',
  'strings/he.ts',
]

// ─── נושאים ────────────────────────────────────────────────────────────────

export const GUEST_TOPICS: readonly HelpTopic[] = [
  {
    id: 'guests.add-one',
    area: 'guests',
    title: 'איך מוסיפים {guest}?',
    aliases: ['מוזמן חדש', 'להכניס מוזמן', 'הוספה ידנית', 'להוסיף אורח'],
    scopes: [
      { scope: 'guests.addForm', weight: 100 },
      { scope: 'guests', weight: 70 },
    ],
    when: MANAGER,
    answer: [
      'לוחצים "{ui:guests.addGuestButton}", ממלאים שם מלא ומספר נייד, ולוחצים שוב "{ui:guests.submitAdd}".',
      'צד, קבוצה וכמה אנשים בהזמנה — אפשר להשלים גם אחר כך.',
    ],
    primary: { kind: 'tour', flow: 'add-guest' },
    related: ['guests.add-many', 'guests.phone-format'],
    sources: GUEST_SOURCES,
    verifiedAt: VERIFIED,
    priority: 5,
  },
  {
    id: 'guests.add-many',
    area: 'guests',
    title: 'איך מוסיפים רשימה שלמה?',
    aliases: ['ייבוא', 'הרבה מוזמנים', 'העלאת רשימה', 'להדביק רשימה', 'רשימה מוואטסאפ'],
    scopes: [
      { scope: 'guests', weight: 65 },
      { scope: 'guests.addForm', weight: 90 },
    ],
    when: MANAGER,
    answer: [],
    variants: [
      {
        when: { fact: 'client.contactPicker', op: '==', value: true },
        answer: [
          'בכפתור "{ui:guests.importMenuButton}" יש שלוש דרכים: {ui:guests.pasteButton}, {ui:guests.uploadButton}, או {ui:guests.contactsButton}.',
          'הכי מהיר: מעתיקים רשימה מ-WhatsApp או מאקסל ומדביקים — נזהה לבד שם, טלפון וכמות.',
        ],
      },
      {
        when: { fact: 'client.contactPicker', op: '==', value: false },
        answer: [
          'בכפתור "{ui:guests.importMenuButton}" יש שתי דרכים: {ui:guests.pasteButton}, או {ui:guests.uploadButton}.',
          'הכי מהיר: מעתיקים רשימה מ-WhatsApp או מאקסל ומדביקים — נזהה לבד שם, טלפון וכמות.',
        ],
      },
    ],
    primary: { kind: 'tour', flow: 'paste-list', label: 'תראו לי איך מדביקים' },
    related: ['guests.import-excel', 'guests.import-skipped'],
    sources: [...GUEST_SOURCES, 'components/ImportMenu.tsx', 'components/PasteImportDialog.tsx'],
    verifiedAt: VERIFIED,
    priority: 4,
  },
  {
    id: 'guests.import-excel',
    area: 'guests',
    title: 'איך מייבאים קובץ Excel?',
    aliases: ['אקסל', 'קובץ', 'csv', 'העלאת קובץ', 'גוגל שיטס'],
    scopes: [
      { scope: 'guests.import.excel', weight: 100 },
      { scope: 'guests', weight: 55 },
      { scope: 'guests.addForm', weight: 60 },
    ],
    when: MANAGER,
    answer: [
      'בשורה הראשונה צריכות להיות כותרות, עם עמודת שם ועמודת טלפון.',
      'אפשר קובץ ‎.xlsx, ‎.xlsm או ‎.csv — עד 5MB ועד 5,000 שורות.',
      'לפני ההוספה רואים תצוגה מקדימה, ושורות עם בעיה לא נכנסות.',
    ],
    primary: { kind: 'tour', flow: 'excel-import' },
    related: ['guests.import-skipped', 'guests.add-many'],
    sources: ['components/ImportDialog.tsx', 'components/ImportMenu.tsx', 'strings/he.ts'],
    verifiedAt: VERIFIED,
    priority: 3,
  },
  {
    id: 'guests.fix-phones',
    area: 'guests',
    title: 'איך מתקנים מספר טלפון?',
    aliases: ['מספר לא תקין', 'בלי מספר', 'טלפון שגוי', 'לא מקבלים הודעות'],
    scopes: [
      { scope: 'guests.edit', weight: 90 },
      { scope: 'guests', weight: 50 },
      { scope: 'dashboard', weight: 20 },
    ],
    when: MANAGER,
    urgentWhen: { fact: 'guests.bad_phone', op: '>', value: 0 },
    answer: [
      'בסינון "{ui:guests.filterLabelBadPhone}" רואים את מי שצריך לתקן. פותחים את ה{guest} ומעדכנים מספר נייד.',
    ],
    variants: [
      {
        when: { fact: 'guests.bad_phone', op: '>', value: 0 },
        answer: [
          '{count:guests.bad_phone|guest:ל} אין מספר טלפון תקין. בלי מספר תקין לא נשלחות הזמנה ובקשות לאישור הגעה ב-WhatsApp.',
          'בסינון "{ui:guests.filterLabelBadPhone}" רואים את מי שצריך לתקן. פותחים את ה{guest} ומעדכנים מספר נייד.',
        ],
      },
    ],
    primary: { kind: 'tour', flow: 'fix-phone' },
    related: ['guests.phone-format'],
    sources: [...GUEST_SOURCES, 'strings/he.ts', 'components/DashboardPage.tsx'],
    verifiedAt: VERIFIED,
    priority: 3,
  },
  {
    id: 'guests.phone-format',
    area: 'guests',
    title: 'איזה מספר טלפון אפשר להזין?',
    aliases: ['מספר מחו"ל', 'חו"ל', 'קידומת', '972', 'פורמט טלפון'],
    scopes: [
      { scope: 'guests.addForm', weight: 80 },
      { scope: 'guests.edit', weight: 80 },
      { scope: 'guests', weight: 30 },
    ],
    when: MANAGER,
    answer: [
      'מספר ישראלי: נייד מתחיל ב-05 ויש בו 10 ספרות. אפשר לכתוב עם מקפים, עם רווחים או עם ‎+972.',
      'מספר מחו"ל עדיין לא נתמך.',
    ],
    errorMatch: [
      { method: 'POST', path: '/guests', status: 422, textIncludes: 'לא תקין' },
      { method: 'PATCH', path: '/guests/{id}', status: 422, textIncludes: 'לא תקין' },
    ],
    related: ['guests.fix-phones'],
    sources: ['../../backend/app/validators.py', 'components/AddGuestForm.tsx'],
    verifiedAt: VERIFIED,
    priority: 2,
  },
  {
    id: 'guests.edit',
    area: 'guests',
    title: 'איך משנים פרטים של {guest}?',
    aliases: ['עריכה', 'לשנות שם', 'לשנות כמות', 'לתקן פרטים'],
    scopes: [{ scope: 'guests', weight: 45 }],
    when: MANAGER,
    answer: [],
    variants: [
      {
        when: { fact: 'layout.guestCards', op: '==', value: false },
        answer: ['לוחצים "{ui:guests.editRow}" בשורה של ה{guest}, משנים, ולוחצים "{ui:guests.submitEdit}".'],
      },
      {
        when: { fact: 'layout.guestCards', op: '==', value: true },
        answer: ['מקישים על הכרטיס של ה{guest}, משנים, ולוחצים "{ui:guests.submitEdit}".'],
      },
    ],
    sources: GUEST_SOURCES,
    verifiedAt: VERIFIED,
  },
  {
    id: 'guests.delete',
    area: 'guests',
    title: 'איך מסירים {guest} מהרשימה?',
    aliases: ['מחיקה', 'מחיקת מוזמן', 'למחוק מוזמן', 'להוריד מהרשימה'],
    scopes: [
      { scope: 'guests', weight: 40 },
      { scope: 'guests.edit', weight: 60 },
    ],
    when: MANAGER,
    answer: [],
    variants: [
      {
        when: { fact: 'layout.guestCards', op: '==', value: false },
        answer: [
          'לוחצים "{ui:guests.deleteRow}" בשורה של ה{guest}.',
          'ה{guest} יוסר גם מסידור ההושבה ומההודעות שעוד לא יצאו, ואי אפשר לבטל את זה.',
        ],
      },
      {
        when: { fact: 'layout.guestCards', op: '==', value: true },
        answer: [
          'מקישים על הכרטיס, ובתחתית החלון: "{ui:guests.deleteGuestInDialog}".',
          'ה{guest} יוסר גם מסידור ההושבה ומההודעות שעוד לא יצאו, ואי אפשר לבטל את זה.',
        ],
      },
    ],
    sources: GUEST_SOURCES,
    verifiedAt: VERIFIED,
  },
  {
    id: 'guests.people-count',
    area: 'guests',
    title: 'למה מספר ה{guests} שונה ממספר האנשים?',
    aliases: ['כמה אנשים', 'ספירה', 'המספרים לא מסתדרים', 'סך הכול'],
    scopes: [
      { scope: 'guests', weight: 35 },
      { scope: 'dashboard', weight: 25 },
    ],
    answer: [
      '"{guests}" הם שורות ברשימה — משפחה אחת היא שורה אחת. "אנשים" הם סכום הכמויות.',
      'למשל: משפחה של 4 היא {guest} אחד ו-4 אנשים.',
    ],
    sources: ['strings/he.ts', 'components/GuestsPage.tsx'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'guests.groups',
    area: 'guests',
    title: 'איך יוצרים קבוצה?',
    aliases: ['קבוצות', 'שיוך לקבוצה', 'משפחה', 'חברים מהצבא'],
    scopes: [{ scope: 'guests', weight: 35 }],
    when: MANAGER,
    answer: [
      'בכפתור "{ui:guests.groupsMenuButton}" ← "{ui:guests.groupButton}": נותנים שם ומסמנים מי שייך אליה.',
      'אפשר גם לבחור קבוצה כשמוסיפים או עורכים {guest}.',
    ],
    sources: ['components/GuestsPage.tsx', 'components/CreateGroupDialog.tsx', 'components/AddGuestForm.tsx'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'guests.export',
    area: 'guests',
    title: 'אפשר להוציא את הרשימה לקובץ?',
    aliases: ['ייצוא', 'אקסל', 'להוריד רשימה', 'iPlan', 'אייפלן', 'קובץ לאולם'],
    scopes: [{ scope: 'guests', weight: 30 }],
    when: MANAGER,
    answer: [
      'כן — "{ui:guests.iplanButton}": קובץ עם כל ה{guests}, אישורי ההגעה ומספרי השולחנות, מוכן להעלאה ל-iPlan.',
      'זה הייצוא היחיד שיש כרגע.',
    ],
    sources: ['components/IPlanExportDialog.tsx', 'strings/he.ts', '../../backend/app/iplan_export.py'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'guests.import-skipped',
    area: 'guests',
    title: 'למה חלק מה{guests} לא נוספו בייבוא?',
    aliases: ['לא נוספו', 'כפולים', 'חסרים', 'שורות עם בעיה'],
    scopes: [
      { scope: 'guests.import.excel', weight: 70 },
      { scope: 'guests.import.paste', weight: 70 },
      { scope: 'guests', weight: 25 },
    ],
    when: MANAGER,
    answer: [
      '{guest} שכבר ברשימה עם אותו מספר טלפון לא נוסף פעמיים.',
      'שורה בלי שם או בלי מספר נייד תקין לא נכנסת — רואים את זה בתצוגה המקדימה, לפני ההוספה.',
    ],
    sources: ['../../backend/app/routers/import_guests.py', '../../backend/app/importer.py', 'lib/importRows.ts'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'guests.contacts',
    area: 'guests',
    title: 'אפשר לייבא מאנשי הקשר בטלפון?',
    aliases: ['אנשי קשר', 'מהטלפון', 'contacts'],
    scopes: [{ scope: 'guests', weight: 20 }],
    when: MANAGER,
    answer: [],
    variants: [
      {
        when: { fact: 'client.contactPicker', op: '==', value: true },
        answer: ['כן — "{ui:guests.importMenuButton}" ← "{ui:guests.contactsButton}". בוחרים, בודקים ומוסיפים.'],
      },
      {
        when: { fact: 'client.contactPicker', op: '==', value: false },
        answer: [
          'בדפדפן הזה אי אפשר לבחור אנשי קשר — זה עובד כרגע רק ב-Chrome באנדרואיד.',
          'במקום זה: מעתיקים את השמות והמספרים ומשתמשים ב"{ui:guests.pasteButton}".',
        ],
        primary: { kind: 'tour', flow: 'paste-list', label: 'תראו לי איך מדביקים' },
      },
    ],
    sources: ['components/ContactsImportDialog.tsx', 'strings/he.ts'],
    verifiedAt: VERIFIED,
  },
]

// ─── הדרכות ("תראו לי") ────────────────────────────────────────────────────

export const GUEST_FLOWS: readonly GuidedFlow[] = [
  {
    id: 'add-guest',
    when: MANAGER,
    start: { page: 'guests' },
    steps: [
      { target: 'guests.addButton', text: 'לחצו על "{ui:guests.addGuestButton}"', advanceOn: { kind: 'scope', scope: 'guests.addForm' } },
      { target: 'guestForm.name', text: 'כתבו שם מלא', advanceOn: { kind: 'filled' } },
      { target: 'guestForm.phone', text: 'ומספר נייד — 10 ספרות שמתחילות ב-05', advanceOn: { kind: 'filled' } },
      { target: 'guestForm.submit', text: 'ולסיום — "{ui:guests.submitAdd}"', advanceOn: { kind: 'api', method: 'POST', path: '/guests' } },
    ],
    success: { kind: 'api', method: 'POST', path: '/guests' },
    doneText: 'מצוין — ה{guest} ברשימה.',
    onError: [{ match: { method: 'POST', path: '/guests', status: 422 }, tree: 'guest-save-failed' }],
    sources: GUEST_SOURCES,
    verifiedAt: VERIFIED,
  },
  {
    id: 'paste-list',
    when: MANAGER,
    start: { page: 'guests' },
    steps: [
      { target: 'guests.importMenu', text: 'לחצו על "{ui:guests.importMenuButton}"', advanceOn: { kind: 'visible', target: 'guests.importPaste' } },
      { target: 'guests.importPaste', text: 'ובחרו "{ui:guests.pasteButton}"', advanceOn: { kind: 'scope', scope: 'guests.import.paste' } },
      { target: 'paste.textarea', text: 'הדביקו כאן את הרשימה — שורה לכל {guest}', advanceOn: { kind: 'filled' } },
      { target: 'paste.parse', text: 'לחצו "{ui:guests.parseButton}"', advanceOn: { kind: 'visible', target: 'paste.import' } },
      { target: 'paste.import', text: 'בדקו את השורות, ולחצו כאן כדי להוסיף אותן', advanceOn: { kind: 'api', method: 'POST', path: '/guests/import/commit' } },
    ],
    success: { kind: 'api', method: 'POST', path: '/guests/import/commit' },
    doneText: 'הרשימה נוספה.',
    onError: [
      { match: { method: 'POST', path: '/guests/import/paste', status: 400 }, tree: 'import-failed' },
    ],
    sources: ['components/ImportMenu.tsx', 'components/PasteImportDialog.tsx', 'strings/he.ts'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'excel-import',
    when: MANAGER,
    start: { page: 'guests' },
    steps: [
      { target: 'guests.importMenu', text: 'לחצו על "{ui:guests.importMenuButton}"', advanceOn: { kind: 'visible', target: 'guests.importExcel' } },
      { target: 'guests.importExcel', text: 'בחרו "{ui:guests.uploadButton}", ואז את הקובץ', advanceOn: { kind: 'scope', scope: 'guests.import.excel' } },
      { target: 'excel.import', text: 'בדקו את התצוגה המקדימה, ולחצו כאן כדי להוסיף', advanceOn: { kind: 'api', method: 'POST', path: '/guests/import/commit' } },
    ],
    success: { kind: 'api', method: 'POST', path: '/guests/import/commit' },
    doneText: 'הרשימה נוספה.',
    onError: [
      { match: { method: 'POST', path: '/guests/import/preview', status: 400 }, tree: 'import-failed' },
    ],
    sources: ['components/ImportMenu.tsx', 'components/ImportDialog.tsx', 'strings/he.ts'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'fix-phone',
    // רק כשבאמת יש מה לתקן — אחרת הרשימה המסוננת ריקה וההדרכה תיתקע.
    when: { all: [MANAGER, { fact: 'guests.bad_phone', op: '>', value: 0 }] },
    start: { page: 'guests', guestFilter: 'bad_phone' },
    steps: [
      {
        target: 'guests.editButton',
        text: 'לחצו "{ui:guests.editRow}" ליד ה{guest}',
        advanceOn: { kind: 'scope', scope: 'guests.edit' },
        when: { fact: 'layout.guestCards', op: '==', value: false },
      },
      {
        target: 'guests.row',
        text: 'הקישו על הכרטיס של ה{guest}',
        advanceOn: { kind: 'scope', scope: 'guests.edit' },
        when: { fact: 'layout.guestCards', op: '==', value: true },
      },
      // השדה כבר מלא במספר הישן — לכן "הבא" ידני ולא "filled".
      { target: 'guestForm.phone', text: 'עדכנו כאן מספר נייד', advanceOn: { kind: 'manual' } },
      { target: 'guestForm.submit', text: 'ולסיום — "{ui:guests.submitEdit}"', advanceOn: { kind: 'api', method: 'PATCH', path: '/guests/{id}' } },
    ],
    success: { kind: 'api', method: 'PATCH', path: '/guests/{id}' },
    doneText: 'המספר עודכן.',
    onError: [{ match: { method: 'PATCH', path: '/guests/{id}', status: 422 }, tree: 'guest-save-failed' }],
    sources: GUEST_SOURCES,
    verifiedAt: VERIFIED,
  },
]

// ─── בדיקת תקלות ───────────────────────────────────────────────────────────

export const GUEST_TREES: readonly DiagnosticTree[] = [
  {
    id: 'guest-save-failed',
    area: 'guests',
    symptom: 'לא מצליחים לשמור {guest}',
    scopes: [
      { scope: 'guests.addForm', weight: 90 },
      { scope: 'guests.edit', weight: 90 },
      { scope: 'guests', weight: 30 },
    ],
    when: MANAGER,
    errorMatch: [
      { method: 'POST', path: '/guests' },
      { method: 'PATCH', path: '/guests/{id}' },
    ],
    root: 'offline',
    nodes: {
      // כל הבדיקות כאן נשענות על השגיאה שהשרת החזיר בשמירה האחרונה.
      // אין שגיאה כזו (נכנסו ישירות, בלי ניסיון שמירה) → "no-error".
      offline: { kind: 'check', test: { fact: 'error.last.status', op: '==', value: 0 }, yes: 'out-offline', no: 'phone', unknown: 'out-no-error' },
      phone: { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'לא תקין' }, yes: 'out-phone', no: 'name', unknown: 'out-unknown' },
      name: { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'שם מלא' }, yes: 'out-name', no: 'count' },
      count: { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'כמות אנשים' }, yes: 'out-count', no: 'out-unknown' },
      'out-offline': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['נראה שאין חיבור לאינטרנט כרגע. כשהחיבור יחזור — אפשר לשמור שוב.'],
      },
      'out-phone': {
        kind: 'outcome', resolution: 'user_fix',
        text: [
          'המספר שהוזן לא נראה כמו מספר ישראלי תקין.',
          'נייד מתחיל ב-05 ויש בו 10 ספרות, למשל 050-1234567. מספר מחו"ל עדיין לא נתמך.',
        ],
      },
      'out-name': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['צריך למלא שם מלא — בלי שם אי אפשר לשמור.'],
      },
      'out-count': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['בשדה "{ui:guests.partySizeLabel}" צריך להיות לפחות 1.'],
      },
      'out-no-error': {
        kind: 'outcome', resolution: 'unknown', offerTeam: true,
        text: [
          'לא ראינו שגיאה בשמירה האחרונה.',
          'אם מופיעה הודעה מתחת לטופס — היא אומרת בדיוק מה לתקן.',
        ],
      },
      'out-unknown': {
        kind: 'outcome', resolution: 'unknown', offerTeam: true,
        text: ['לא זיהינו מה עצר את השמירה.'],
      },
    },
    sources: ['../../backend/app/schemas.py', '../../backend/app/validators.py', 'api.ts'],
    verifiedAt: VERIFIED,
  },
  {
    id: 'import-failed',
    area: 'guests',
    symptom: 'הייבוא לא עובד',
    scopes: [
      { scope: 'guests.import.excel', weight: 90 },
      { scope: 'guests.import.paste', weight: 90 },
      { scope: 'guests', weight: 30 },
    ],
    when: MANAGER,
    errorMatch: [
      { method: 'POST', path: '/guests/import/preview' },
      { method: 'POST', path: '/guests/import/paste' },
      { method: 'POST', path: '/guests/import/commit' },
    ],
    root: 'offline',
    nodes: {
      offline: { kind: 'check', test: { fact: 'error.last.status', op: '==', value: 0 }, yes: 'out-offline', no: 'columns', unknown: 'out-no-error' },
      // הניסוחים שהשרת מחזיר — routers/import_guests.py + importer.parse_file.
      columns: { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'לא זוהו עמודות' }, yes: 'out-columns', no: 'size', unknown: 'out-unknown' },
      size: { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'גדול מדי' }, yes: 'out-size', no: 'long' },
      long: { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'ארוכה מדי' }, yes: 'out-long', no: 'rows' },
      rows: { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'שורות' }, yes: 'out-rows', no: 'format' },
      format: { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'פורמט' }, yes: 'out-format', no: 'empty' },
      empty: { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'ריק' }, yes: 'out-empty', no: 'unreadable' },
      unreadable: { kind: 'check', test: { fact: 'error.last.message', op: 'includes', value: 'לא הצלחנו לקרוא' }, yes: 'out-unreadable', no: 'out-unknown' },
      'out-offline': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['נראה שאין חיבור לאינטרנט כרגע. כשהחיבור יחזור — אפשר לנסות שוב.'],
      },
      'out-columns': {
        kind: 'outcome', resolution: 'user_fix',
        text: [
          'לא מצאנו בשורה הראשונה עמודת שם ועמודת טלפון.',
          'אפשר להוסיף כותרות "שם" ו"טלפון" בשורה הראשונה, או להדביק את הרשימה — שם לא צריך כותרות.',
        ],
        action: { kind: 'tour', flow: 'paste-list', label: 'תראו לי איך מדביקים' },
      },
      'out-size': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['הקובץ גדול מ-5MB. אפשר לפצל אותו לכמה קבצים קטנים.'],
      },
      'out-long': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['הרשימה ארוכה מדי להדבקה אחת. אפשר להדביק אותה בכמה חלקים.'],
      },
      'out-rows': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['יש יותר מ-5,000 שורות. אפשר לפצל לכמה חלקים.'],
      },
      'out-format': {
        kind: 'outcome', resolution: 'user_fix',
        text: [
          'אפשר להעלות קובץ ‎.xlsx, ‎.xlsm או ‎.csv.',
          'קובץ אחר אפשר לפתוח באקסל ולשמור מחדש כ-‎.xlsx.',
        ],
      },
      'out-empty': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['הקובץ נראה ריק, או שאין בו שורת כותרות.'],
      },
      'out-unreadable': {
        kind: 'outcome', resolution: 'user_fix',
        text: ['לא הצלחנו לקרוא את הקובץ. אפשר לפתוח אותו באקסל, לשמור מחדש ולנסות שוב.'],
      },
      'out-no-error': {
        kind: 'outcome', resolution: 'unknown', offerTeam: true,
        text: [
          'לא ראינו שגיאה בייבוא האחרון.',
          'שורה לא נכנסת כשהיא כבר ברשימה, או כשחסר בה שם, מספר נייד תקין או כמות.',
        ],
      },
      'out-unknown': {
        kind: 'outcome', resolution: 'unknown', offerTeam: true,
        text: ['לא זיהינו מה עצר את הייבוא.'],
      },
    },
    sources: ['../../backend/app/routers/import_guests.py', '../../backend/app/importer.py'],
    verifiedAt: VERIFIED,
  },
]
