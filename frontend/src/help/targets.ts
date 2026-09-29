/**
 * יעדי UI שהעזרה רשאית להצביע עליהם ("לחצו כאן") — רישום מרכזי אחד.
 *
 * כל יעד = מאפיין ``data-help="<id>"`` על אלמנט אמיתי, בקובץ שרשום כאן.
 * ההדרכות (שלב 6) יפנו **רק** ל-id מהרשימה הזו, והעזרה לעולם לא לוחצת,
 * ממלאת או שולחת בעצמה — היא רק מסמנת (HELP_CENTER_PLAN.md §9.2).
 *
 * ## "אסור להמציא" — נאכף בבדיקה
 * ``helpFoundations.test.ts`` נכשלת אם:
 *   - יעד רשום כאן **לא** מופיע כ-``data-help`` בקובץ שלו (ה-UI השתנה
 *     והעזרה הייתה מצביעה על כלום);
 *   - ``data-help`` מופיע בקוד בלי רישום כאן (יעד "יתום");
 *   - אותו id מופיע ביותר מקובץ אחד (ההדרכה לא תדע לאן להצביע).
 * כך שינוי עתידי שמסיר או משנה כפתור שובר את הבדיקה, ולא משאיר הדרכה שבורה.
 *
 * הרשימה מכסה רק את 7 ההדרכות שאושרו ל-MVP: הוספת מוזמן · הדבקת רשימה ·
 * ייבוא אקסל · תיקון מספרים · שליחת הזמנות · בחירת מועד סגירה · הושבה בקליק.
 * יעד נוסף נכנס רק יחד עם הדרכה שבאמת משתמשת בו.
 */

/** המסכים של האפליקציה — חייבים להתאים ל-``PAGE_PATHS`` ב-``App.tsx`` (נבדק). */
export type HelpPage = 'dashboard' | 'guests' | 'messages' | 'rsvp' | 'hall' | 'gifts' | 'finance'

export interface HelpTarget {
  /** שם הקובץ תחת ``src/`` שבו נמצא ``data-help`` של היעד. */
  file: string
  /** המסך שבו היעד מוצג. */
  page: HelpPage
  /** יעד שקיים רק בגודל מסך אחד. בלי ערך = בשניהם. */
  platforms?: readonly ('mobile' | 'desktop')[]
  /** למפתחים: מה זה ומתי הוא מופיע (לא מוצג למשתמש). */
  note: string
}

export const TARGETS = {
  // ── ניהול המוזמנים ────────────────────────────────────────────────────
  'guests.addButton': {
    file: 'components/GuestsPage.tsx', page: 'guests',
    note: 'כפתור "הוספת מוזמן" בסרגל — פותח/סוגר את הטופס',
  },
  'guests.importMenu': {
    file: 'components/ImportMenu.tsx', page: 'guests',
    note: 'כפתור "ייבוא מוזמנים" — פותח תפריט של דרכי ייבוא',
  },
  'guests.importExcel': {
    file: 'components/ImportMenu.tsx', page: 'guests',
    note: 'פריט "ייבוא מקובץ Excel / CSV" — מופיע רק כשהתפריט פתוח; פותח בחירת קובץ',
  },
  'guests.importPaste': {
    file: 'components/ImportMenu.tsx', page: 'guests',
    note: 'פריט "הדבקה מרשימה קיימת" — מופיע רק כשהתפריט פתוח',
  },
  'guests.editButton': {
    file: 'components/GuestsPage.tsx', page: 'guests', platforms: ['desktop'],
    note: 'כפתור "עריכה" בשורת מוזמן (בטלפון מוסתר — מקישים על הכרטיס עצמו)',
  },
  'guests.row': {
    file: 'components/GuestsPage.tsx', page: 'guests', platforms: ['mobile'],
    note: 'שורת/כרטיס מוזמן — בטלפון הקשה עליו פותחת עריכה',
  },
  'guestForm.name': {
    file: 'components/AddGuestForm.tsx', page: 'guests',
    note: 'שדה השם המלא בטופס הוספה/עריכה של מוזמן',
  },
  'guestForm.phone': {
    file: 'components/AddGuestForm.tsx', page: 'guests',
    note: 'שדה הטלפון בטופס הוספה/עריכה של מוזמן',
  },
  'guestForm.submit': {
    file: 'components/AddGuestForm.tsx', page: 'guests',
    note: 'כפתור השמירה: "הוספת מוזמן" (הוספה) / "שמירת שינויים" (עריכה)',
  },
  'paste.textarea': {
    file: 'components/PasteImportDialog.tsx', page: 'guests',
    note: 'תיבת ההדבקה בחלון "הדבקה מרשימה קיימת"',
  },
  'paste.parse': {
    file: 'components/PasteImportDialog.tsx', page: 'guests',
    note: 'הכפתור שמנתח את הרשימה המודבקת ומציג תצוגה מקדימה',
  },
  'paste.import': {
    file: 'components/PasteImportDialog.tsx', page: 'guests',
    note: 'כפתור "ייבוא N מוזמנים" בתצוגה המקדימה של ההדבקה',
  },
  'excel.import': {
    file: 'components/ImportDialog.tsx', page: 'guests',
    note: 'כפתור "ייבוא N מוזמנים" בחלון ייבוא הקובץ',
  },

  // ── ניהול הודעות — שליחת הזמנות ─────────────────────────────────────
  'messages.wizardToGuests': {
    file: 'components/MessagesPage.tsx', page: 'messages',
    note: 'אשף ההזמנה הראשונה, שלב 1 — "המשך למוזמנים"',
  },
  'messages.wizardToReview': {
    file: 'components/MessagesPage.tsx', page: 'messages',
    note: 'אשף ההזמנה הראשונה, שלב 2 — "המשך לתצוגה"',
  },
  'messages.wizardSend': {
    file: 'components/MessagesPage.tsx', page: 'messages',
    note: 'אשף ההזמנה הראשונה, שלב 3 — "שליחת הזמנות" (פותח את חלון האישור)',
  },
  'messages.sendMore': {
    file: 'components/MessagesPage.tsx', page: 'messages',
    note: 'אחרי שכבר יצאו הזמנות — "שליחת הזמנות" (למי שעוד לא קיבל)',
  },
  'messages.sendNewGuests': {
    file: 'components/MessagesPage.tsx', page: 'messages',
    note: 'באנר "נוספו מוזמנים חדשים" — "שליחת הזמנות למוזמנים החדשים"',
  },
  'messages.sendConfirm': {
    file: 'components/MessagesPage.tsx', page: 'messages',
    note: 'בחלון האישור — "שליחת ההזמנות (N)". השליחה עצמה: רק בלחיצה של המשתמש',
  },

  // ── תמונת מצב — מועד סגירת הרשימה ─────────────────────────────────────
  'dashboard.editDetails': {
    file: 'components/DashboardPage.tsx', page: 'dashboard',
    note: 'כפתור "עריכת פרטי האירוע"',
  },
  'dashboard.commitField': {
    file: 'components/DashboardPage.tsx', page: 'dashboard',
    note: 'אזור "מועד סגירת הרשימה" במצב עריכה (בחירה, או ערך נעול)',
  },
  'dashboard.saveDetails': {
    file: 'components/DashboardPage.tsx', page: 'dashboard',
    note: 'כפתור "שמירה" של פרטי האירוע',
  },

  // ── סידור הושבה ──────────────────────────────────────────────────────
  'hall.seatingTab': {
    file: 'components/HallPage.tsx', page: 'hall',
    note: 'לשונית "הושבה" בכלי מרחב ההושבה (דסקטופ ברכבת, טלפון בפס התחתון)',
  },
  'hall.oneClick': {
    file: 'components/HallPage.tsx', page: 'hall',
    note: 'כפתור "הושבה בקליק" בלוח ההושבה',
  },
  'hall.undo': {
    file: 'components/HallPage.tsx', page: 'hall',
    note: '"החזרת הסידור הקודם" — מופיע רק אחרי הושבה בקליק',
  },
} as const satisfies Record<string, HelpTarget>

export type TargetId = keyof typeof TARGETS

export const TARGET_IDS = Object.keys(TARGETS) as TargetId[]
