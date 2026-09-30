/**
 * ערוץ התוצאות של קריאות ה-API — כדי שהעזרה תדע "מה נכשל עכשיו" ו"מה הצליח".
 *
 * היום ``api.ts::toError`` הופך כל כשל להודעה בעברית, והסטטוס עצמו הולך
 * לאיבוד בדרך למסך. כאן נשמר, **בזיכרון בלבד**, תקציר קטן של כל תוצאה:
 * שיטה, נתיב כתבנית (בלי מזהים), סטטוס, והודעת השגיאה שהמשתמש ראה.
 *
 * - שגיאות: 5 האחרונות (לזיהוי "צריכים עזרה עם זה?" — HELP_CENTER_PLAN.md §8.3).
 * - הצלחות של כתיבה (POST/PUT/PATCH/DELETE): רק מועברות למאזינים — כך הדרכה
 *   יודעת ש"המוזמן נוסף" לפי מה שהשרת אישר, ולא לפי לחיצה (§9.4).
 *
 * פרטיות: שום דבר כאן לא נשלח לשרת ולא נשמר בדפדפן. הנתיב מנוקה ממספרים
 * ומטוקנים, וההודעה נשמרת **אחרי ניקוי** (``redactMessage``): בלי טלפונים,
 * בלי מספרים, בלי כתובות מייל, ובלי מה שאחרי נקודתיים (שם השרת מצרף לפעמים
 * שמות של מוזמנים — למשל "חבורה גדולה…: משפחת לוי"). נשאר רק הניסוח הכללי.
 *
 * הקובץ טהור (בלי React/DOM) — נבדק ב-node.
 */

export interface ApiEvent {
  method: string
  /** תבנית נתיב: ``/guests/{id}`` — בלי origin, בלי query, בלי מזהים. */
  path: string
  /** 0 = אין תשובה בכלל (רשת); -1 = קריסת מסך (ErrorBoundary). */
  status: number
  ok: boolean
  /** ההודעה שהמשתמש ראה, אחרי ``redactMessage`` (רק לשגיאות). */
  message?: string
  at: number
}

const MAX_ERRORS = 5
const WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

let errors: ApiEvent[] = []
/**
 * סדר האירועים (מונה עולה, לא שעון — שני אירועים באותה אלפית שנייה עדיין מסודרים):
 * לכל שגיאה — מתי קרתה; לכל "שיטה נתיב" — מתי הצליחה בו כתיבה לאחרונה.
 * כך שגיאה שתוקנה (הצליחה אחריה כתיבה לאותו נתיב) לא נחשבת "עכשיו".
 */
let seq = 0
let errorSeq = new WeakMap<ApiEvent, number>()
let lastWriteOk = new Map<string, number>()
const listeners = new Set<(e: ApiEvent) => void>()

/**
 * ממיר כתובת/נתיב לתבנית יציבה: מסיר origin ו-query, ומחליף מקטע מספרי
 * ב-``{id}`` ומקטע ארוך דמוי-טוקן ב-``{token}``. כך אין בזיכרון מזהי
 * מוזמנים/טוקנים, וקל להתאים לחוקים (``POST /guests/import/preview``).
 */
export function pathTemplate(urlOrPath: string): string {
  let path = urlOrPath
  const schemeAt = path.indexOf('://')
  if (schemeAt >= 0) {
    const slash = path.indexOf('/', schemeAt + 3)
    path = slash >= 0 ? path.slice(slash) : '/'
  }
  path = path.split('#')[0].split('?')[0]
  if (!path.startsWith('/')) path = `/${path}`
  const segments = path.split('/').map((seg) => {
    if (/^\d+$/.test(seg)) return '{id}'
    if (seg.length >= 20 && /^[A-Za-z0-9_-]+$/.test(seg) && /\d/.test(seg)) return '{token}'
    return seg
  })
  const out = segments.join('/').replace(/\/+$/, '')
  return out || '/'
}

function emit(e: ApiEvent): void {
  for (const fn of listeners) {
    try {
      fn(e)
    } catch {
      /* מאזין שנכשל לא מפיל את הקריאה ל-API */
    }
  }
}

function recordError(e: ApiEvent): void {
  errorSeq.set(e, ++seq)
  errors = [...errors, e].slice(-MAX_ERRORS)
  emit(e)
}

/** נקרא מ-``apiFetch`` אחרי כל תשובה מהשרת. */
export function reportResponse(method: string | undefined, url: string, status: number): void {
  const m = (method || 'GET').toUpperCase()
  const e: ApiEvent = { method: m, path: pathTemplate(url), status, ok: status < 400, at: Date.now() }
  if (!e.ok) {
    recordError(e)
  } else if (WRITE_METHODS.has(m)) {
    lastWriteOk.set(`${e.method} ${e.path}`, ++seq)
    emit(e)
  }
}

/**
 * מנקה הודעת שגיאה מכל מה שעלול להיות מידע אישי, ומשאיר את הניסוח הכללי:
 * - מה שאחרי נקודתיים — נחתך (שם מופיעים שמות: "…לשולחן: משפחת לוי");
 * - מה שהוקלד בשדה הטלפון ("נראה שהמספר X לא תקין") — מוחלף;
 * - כתובות מייל, ורצפים של 2 ספרות ומעלה (טלפונים, מספרים) — מוחלפים;
 * - אורך מקסימלי 160 תווים.
 * העזרה מזהה שגיאה לפי קטעי ניסוח קבועים ("לא זוהו עמודות"), שלא נפגעים מזה.
 */
export function redactMessage(message: string): string {
  let m = message
  const colon = m.indexOf(':')
  if (colon >= 0) m = m.slice(0, colon)
  m = m.replace(/המספר\s+.*?\s+לא תקין/g, 'המספר # לא תקין')
  m = m.replace(/\S+@\S+/g, '@')
  m = m.replace(/\+?\d[\d\s\-()]*\d/g, '#')
  return m.trim().slice(0, 160)
}

/** נקרא מ-``apiFetch`` כשאין תשובה בכלל (רשת/שרת לא זמין). */
export function reportNetworkFailure(method: string | undefined, url: string, message?: string): void {
  recordError({
    method: (method || 'GET').toUpperCase(),
    path: pathTemplate(url),
    status: 0,
    ok: false,
    ...(message ? { message: redactMessage(message) } : {}),
    at: Date.now(),
  })
}

/**
 * נקרא מ-``toError`` אחרי שנקבעה ההודעה בעברית. מעשיר את השגיאה האחרונה
 * שתואמת (נתיב + סטטוס) ועדיין בלי הודעה. אין התאמה — מתעלמים (למשל
 * שגיאה ממסך ציבורי שלא עבר דרך ``apiFetch``).
 */
export function reportErrorMessage(url: string, status: number, message: string): void {
  const path = pathTemplate(url)
  for (let i = errors.length - 1; i >= 0; i--) {
    const e = errors[i]
    if (e.path === path && e.status === status && e.message === undefined) {
      const clean = redactMessage(message)
      const withMessage = { ...e, message: clean }
      errorSeq.set(withMessage, errorSeq.get(e) ?? ++seq)
      errors = errors.map((x, j) => (j === i ? withMessage : x))
      return
    }
  }
}

/** קריסת מסך שנתפסה ב-``ErrorBoundary``. */
export function reportCrash(): void {
  recordError({ method: '', path: 'ui:crash', status: -1, ok: false, at: Date.now() })
}

/** השגיאות האחרונות, מהישנה לחדשה (עד 5). */
export function recentErrors(): ApiEvent[] {
  return errors
}

/** האם אחרי השגיאה הזו כבר הצליחה כתיבה לאותו נתיב (כלומר — היא כבר לא "עכשיו"). */
export function succeededSince(e: ApiEvent): boolean {
  const ok = lastWriteOk.get(`${e.method} ${e.path}`)
  const at = errorSeq.get(e)
  return ok !== undefined && at !== undefined && ok > at
}

/** מאזין לכל שגיאה ולכל הצלחה של כתיבה. מחזיר פונקציית ביטול. */
export function onApiEvent(fn: (e: ApiEvent) => void): () => void {
  listeners.add(fn)
  return () => {
    listeners.delete(fn)
  }
}

/** לבדיקות בלבד. */
export function resetErrorBusForTests(): void {
  errors = []
  lastWriteOk = new Map()
  errorSeq = new WeakMap()
  listeners.clear()
}
