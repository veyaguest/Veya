/**
 * "איפה המשתמש נמצא עכשיו" — מקור האמת של מערכת העזרה למסך ולתת-המסך.
 *
 * כל מסך/חלון/שלב שהעזרה צריכה להכיר מכריז על עצמו עם
 * ``useHelpScope('guests.addForm')`` (ראו ``useHelpScope.ts``). המסכים לא
 * מכירים שום דבר אחר ממערכת העזרה, והיא לא נוגעת בלוגיקה שלהם.
 *
 * הקובץ **טהור** (בלי React, בלי DOM) כדי שאפשר יהיה לבדוק אותו ב-node.
 * HELP_CENTER_PLAN.md §7.
 *
 * ## למה שכבה (layer) ולא רק "מי נפתח אחרון"
 * React מריץ effects של ילדים **לפני** ההורה. מסך שנטען יחד עם שלב פנימי
 * (למשל אשף ההזמנה בתוך ניהול ההודעות) היה נרשם בסדר הפוך — המסך "אחרון"
 * והשלב "ראשון". לכן הסדר נקבע קודם לפי שכבה מוצהרת (חלון > קטע > מסך),
 * ורק בתוך אותה שכבה לפי מי נפתח אחרון.
 */

/** שכבה: חלון/טופס ממוקד גובר על קטע במסך, שגובר על המסך עצמו. */
export type ScopeLayer = 'page' | 'section' | 'dialog'

/**
 * כל ה-scopes הקיימים. **הוספת scope = שורה כאן + ``useHelpScope`` ברכיב.**
 * בדיקה (``helpFoundations.test.ts``) נכשלת אם scope רשום כאן ואף רכיב לא
 * משתמש בו — כך לא נשארים scopes "מתים" שהעזרה מתייחסת אליהם.
 */
export const SCOPES = {
  // תמונת מצב
  dashboard: 'page',
  'dashboard.editEvent': 'section',
  // ניהול המוזמנים
  guests: 'page',
  'guests.addForm': 'dialog',
  'guests.edit': 'dialog',
  'guests.import.excel': 'dialog',
  'guests.import.paste': 'dialog',
  'guests.import.contacts': 'dialog',
  // ניהול הודעות (אשף ההזמנה הראשונה: עיצוב → מוזמנים → תצוגה ושליחה)
  messages: 'page',
  'messages.wizard.design': 'section',
  'messages.wizard.recipients': 'section',
  'messages.wizard.review': 'section',
  'messages.sendDialog': 'dialog',
  // אישורי הגעה
  rsvp: 'page',
  // סידור הושבה
  hall: 'page',
  // מאזן האירוע — שלוש לשוניות
  finance: 'page',
  'finance.cost': 'section',
  'finance.counting': 'section',
  'finance.summary': 'section',
  // מתנות באשראי (רק לאירוע זכאי — המסך עצמו מגודר ב-App.tsx)
  gifts: 'page',
  // "החשבון שלי"
  account: 'dialog',
} as const satisfies Record<string, ScopeLayer>

export type ScopeId = keyof typeof SCOPES

export const SCOPE_IDS = Object.keys(SCOPES) as ScopeId[]

const LAYER_RANK: Record<ScopeLayer, number> = { page: 0, section: 1, dialog: 2 }

interface Entry {
  scope: ScopeId
  seq: number
}

let entries: Entry[] = []
let nextSeq = 1
const listeners = new Set<() => void>()

function notify(): void {
  for (const fn of listeners) fn()
}

/**
 * רושם scope פעיל ומחזיר פונקציה שמסירה אותו. אותו scope יכול להירשם
 * פעמיים (למשל טופס הוספת מוזמן גם במסך המוזמנים וגם באשף) — כל רישום
 * נמחק בנפרד, כך שסגירת אחד לא מוחקת את השני.
 */
export function pushScope(scope: ScopeId): () => void {
  const entry: Entry = { scope, seq: nextSeq++ }
  entries = [...entries, entry]
  notify()
  return () => {
    const before = entries.length
    entries = entries.filter((e) => e !== entry)
    if (entries.length !== before) notify()
  }
}

/**
 * ה-scopes הפעילים, מהספציפי לכללי: שכבה גבוהה קודם, ובתוך אותה שכבה —
 * מה שנפתח אחרון. בלי כפילויות.
 */
export function activeScopes(): ScopeId[] {
  const sorted = [...entries].sort(
    (a, b) =>
      LAYER_RANK[SCOPES[b.scope]] - LAYER_RANK[SCOPES[a.scope]] || b.seq - a.seq,
  )
  const out: ScopeId[] = []
  for (const e of sorted) if (!out.includes(e.scope)) out.push(e.scope)
  return out
}

/** מאזין לשינויים. מחזיר פונקציית ביטול. */
export function subscribeScopes(fn: () => void): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}

/** לבדיקות בלבד — מאפס את המצב. */
export function resetScopesForTests(): void {
  entries = []
  nextSeq = 1
  listeners.clear()
}
