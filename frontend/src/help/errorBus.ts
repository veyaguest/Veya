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
 * ומטוקנים, והודעת השגיאה נשארת בזיכרון של הלשונית בלבד.
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
  /** ההודעה שהמשתמש ראה (רק לשגיאות, ורק אם כבר חושבה). */
  message?: string
  at: number
}

const MAX_ERRORS = 5
const WRITE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

let errors: ApiEvent[] = []
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
    emit(e)
  }
}

/** נקרא מ-``apiFetch`` כשאין תשובה בכלל (רשת/שרת לא זמין). */
export function reportNetworkFailure(method: string | undefined, url: string): void {
  recordError({
    method: (method || 'GET').toUpperCase(),
    path: pathTemplate(url),
    status: 0,
    ok: false,
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
      errors = errors.map((x, j) => (j === i ? { ...x, message } : x))
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
  listeners.clear()
}
