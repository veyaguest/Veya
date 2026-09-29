/**
 * סכמת הידע של מערכת העזרה (HELP_CENTER_PLAN.md §6).
 *
 * שלושה סוגי תוכן, כולם **נתונים** (בלי פונקציות) — כדי שאפשר יהיה לבדוק
 * אותם אוטומטית, ובעתיד גם להציג/לערוך ניסוח מהאדמין בלי לגעת בקוד:
 *
 * - ``HelpTopic``     — שאלה אחת במילים של המשתמש → תשובה קצרה → פעולה אחת.
 * - ``GuidedFlow``    — "תראו לי": צעדים על יעדי UI אמיתיים (help/targets.ts).
 * - ``DiagnosticTree``— "משהו לא עובד": בדיקות על עובדות אמיתיות → פתרון.
 *
 * כללי ברזל שנאכפים בבדיקות (helpKb.test.ts):
 * - כל יעד/עובדה/מסך/טקסט-כפתור שהתוכן מזכיר — קיים באמת בקוד.
 * - תשובה עד 3 שורות; שאלה סגורה עד 3 כפתורים.
 * - העזרה לא לוחצת, לא ממלאת ולא שולחת — רק מסמנת ומסבירה.
 */
import type { ScopeId } from './scopes'
import type { HelpPage, TargetId } from './targets'
import type { FactId } from './facts'

/** תחומי הידע. */
export type Area = 'event' | 'guests' | 'invitation' | 'rsvp' | 'seating' | 'finance' | 'gifts' | 'account'

// ─── תנאים ─────────────────────────────────────────────────────────────────

/** השוואה על עובדה. עובדה שחסרה → "לא ידוע" (לא true ולא false). */
export interface FactCondition {
  fact: FactId
  op: '==' | '!=' | '>' | '>=' | '<' | '<=' | 'in' | 'includes'
  value: string | number | boolean | readonly (string | number | boolean)[]
}

export type Condition =
  | FactCondition
  | { all: readonly Condition[] }
  | { any: readonly Condition[] }
  | { not: Condition }

// ─── טקסט ──────────────────────────────────────────────────────────────────

/**
 * מחרוזת עם טוקנים (engine/text.ts):
 * - ``{guests}`` / ``{guest}`` — "מוזמנים"/"מוזמן" או "משתתפים"/"משתתף" לפי סוג האירוע.
 * - ``{hosts}`` — כינוי בעלי האירוע ("בני הזוג" / "המשפחה"…).
 * - ``{ui:guests.addGuestButton}`` — הטקסט **המדויק** של כפתור מ-strings/he.ts.
 *   כך שינוי שם כפתור מתעדכן בעזרה מעצמו, וכפתור שנמחק שובר בדיקה.
 * - ``{n:fact}`` מספר · ``{date:fact}`` תאריך בעברית · ``{text:fact}`` מחרוזת.
 * - ``{count:fact|יחיד|רבים עם #}`` — "מוזמן אחד" / "3 מוזמנים".
 *   ``{count:fact|guest}`` — אותו דבר לפי הלקסיקון; ``{count:fact|guest:ל}`` —
 *   "למוזמן אחד" / "ל-3 מוזמנים".
 * טוקן שאי אפשר למלא → כל השורה לא מוצגת (לא מציגים חצי-משפט).
 */
export type HelpText = string

// ─── פעולות ────────────────────────────────────────────────────────────────

export type GuestFilter = 'all' | 'confirmed' | 'declined' | 'maybe' | 'pending' | 'no_table' | 'bad_phone'

export type HelpAction =
  /** "תראו לי" — הדרכה על המסך. */
  | { kind: 'tour'; flow: string; label?: HelpText }
  /** מעבר למסך (אפשר עם סינון מוכן במסך המוזמנים). */
  | { kind: 'navigate'; page: HelpPage; guestFilter?: GuestFilter; label: HelpText }
  /** "בואו נבדוק" — עץ תקלות. */
  | { kind: 'diagnose'; tree: string; label?: HelpText }

// ─── נושא ──────────────────────────────────────────────────────────────────

/** התאמה לשגיאה אחרונה מ-help/errorBus.ts. */
export interface ErrorMatch {
  method?: string
  /** תבנית נתיב כמו ב-errorBus: ``/guests/import/preview``. */
  path: string
  status?: number
  /** קטע מהודעת השגיאה שהמשתמש ראה (מהשרת, בעברית). */
  textIncludes?: string
}

export interface HelpTopic {
  id: string
  area: Area
  /** השאלה, במילים של המשתמש. */
  title: HelpText
  /** ניסוחים נוספים לחיפוש. */
  aliases: readonly string[]
  /** איפה הנושא הכי רלוונטי: 100 = תת-מסך מדויק, 60 = המסך, 20 = קשור. */
  scopes: readonly { scope: ScopeId; weight: number }[]
  /** מתי מותר להציג בכלל. בלי תנאי = תמיד. */
  when?: Condition
  /** מתי הנושא נכנס ל"חשוב עכשיו". */
  urgentWhen?: Condition
  /** 1–3 שורות. אם יש ``variants`` — הראשון שהתנאי שלו מתקיים גובר. */
  answer: readonly HelpText[]
  variants?: readonly { when: Condition; answer: readonly HelpText[]; primary?: HelpAction | null }[]
  primary?: HelpAction
  /** עד 2 נושאים קשורים. */
  related?: readonly string[]
  errorMatch?: readonly ErrorMatch[]
  /** הקבצים שמהם נגזרה התשובה (נבדק שהם קיימים). */
  sources: readonly string[]
  /** מתי אומת מול הקוד. */
  verifiedAt: string
  /** 0–10, שובר שוויון בדירוג. */
  priority?: number
}

// ─── הדרכה ("תראו לי") ─────────────────────────────────────────────────────

/**
 * מה מקדם את ההדרכה לצעד הבא. אף אחד מהם לא מבצע פעולה בשם המשתמש.
 *
 * כלל: צעד שהאות שלו **כבר** מתקיים כשמגיעים אליו (``scope`` פעיל / יעד
 * ``visible`` כבר מוצג) — מדלגים עליו. למשל טופס הוספת מוזמן שכבר פתוח: לא
 * מבקשים ללחוץ שוב על "הוספת מוזמן" (זה היה סוגר את הטופס).
 * ``filled`` = השדה לא ריק כשהמשתמש יוצא ממנו; בשדה שכבר מלא (עריכה)
 * משתמשים ב-``manual``.
 */
export type Signal =
  | { kind: 'click' }                          // המשתמש לחץ על היעד
  | { kind: 'scope'; scope: ScopeId }          // נפתח תת-מסך/חלון
  | { kind: 'filled' }                         // שדה הקלט לא ריק
  | { kind: 'visible'; target: TargetId }      // יעד אחר הופיע (תפריט נפתח, תצוגה מקדימה מוכנה)
  | { kind: 'api'; method: 'POST' | 'PUT' | 'PATCH' | 'DELETE'; path: string }  // השרת אישר
  | { kind: 'manual' }                         // כפתור "הבא" בכרטיס ההדרכה

export interface FlowStep {
  target: TargetId
  /** שורה אחת. */
  text: HelpText
  advanceOn: Signal
  /**
   * צעד שקיים רק בפריסה מסוימת — למשל "עריכה" בשורה (``layout.guestCards``
   * false) מול הקשה על הכרטיס (true). צעד שהתנאי שלו לא מתקיים מדולג.
   */
  when?: Condition
}

export interface GuidedFlow {
  id: string
  /** מתי מותר להתחיל. */
  when?: Condition
  /** לאן לנווט לפני הצעד הראשון (אם המשתמש לא שם). */
  start: { page: HelpPage; guestFilter?: GuestFilter }
  steps: readonly FlowStep[]
  /** מה נחשב "בוצע". */
  success: Extract<Signal, { kind: 'api' }>
  /** הודעת הסיום. */
  doneText: HelpText
  /** שגיאה בזמן ההדרכה → עץ התקלות המתאים. */
  onError?: readonly { match: ErrorMatch; tree: string }[]
  sources: readonly string[]
  verifiedAt: string
}

// ─── עץ תקלות ──────────────────────────────────────────────────────────────

export type Resolution =
  | 'user_fix'   // המשתמש יכול לתקן (ואנחנו מראים איך)
  | 'explained'  // זו ההתנהגות הנכונה — הסבר
  | 'veya_side'  // משהו אצלנו — אין מה לתקן אצלכם
  | 'unknown'    // לא הצלחנו לזהות

export type DiagNode =
  /** בדיקה על עובדות. ``unknown`` = כשאין עובדה לבדוק (בלי ענף — מגיעים ל-``cant-check``). */
  | { kind: 'check'; test: Condition; yes: string; no: string; unknown?: string }
  /** שאלה סגורה — עד 3 כפתורים. */
  | { kind: 'ask'; question: HelpText; options: readonly { label: HelpText; next: string }[] }
  | {
      kind: 'outcome'
      text: readonly HelpText[]
      action?: HelpAction
      resolution: Resolution
      /** האם להציע את צוות VEYA אחרי התוצאה הזו. */
      offerTeam?: boolean
    }

export interface DiagnosticTree {
  id: string
  area: Area
  /** הסימפטום, במילים של המשתמש. */
  symptom: HelpText
  scopes: readonly { scope: ScopeId; weight: number }[]
  when?: Condition
  errorMatch?: readonly ErrorMatch[]
  root: string
  nodes: Readonly<Record<string, DiagNode>>
  sources: readonly string[]
  verifiedAt: string
}
