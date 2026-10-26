/**
 * סוג האירוע שנבחר בדף הבית ("ממשיכים עם בר מצווה") — עובר להרשמה ולאשף
 * הפתיחה, כדי שהמבקר לא יצטרך לבחור אותו שוב.
 *
 * דף הבית מקשר ל-/app?auth=register&event_type=<type>. בטעינת האפליקציה
 * (main.tsx) קולטים את הערך ושומרים אותו ב-sessionStorage, כי האפליקציה
 * מנקה את ה-URL בדרך (replaceState) לפני שהאשף מוצג. אשף הפתיחה קורא אותו
 * כבחירה ראשונית, ומוחק אותו מיד אחרי שהאירוע הראשון נוצר — כך הבחירה חיה
 * רק בתהליך ההרשמה הזה ולא "נדבקת" לאירועים הבאים.
 *
 * רק ערך מתוך EventType מתקבל; כל דבר אחר נזרק בשקט. אין כאן מידע אישי.
 */
import type { EventType } from '../types'

const KEY = 'veya.signupEventType'

// Record על כל EventType — אם יתווסף סוג אירוע ב-types.ts, הקומפיילר
// יחייב להוסיף אותו גם כאן.
const VALID: Record<EventType, true> = {
  wedding: true,
  bar_mitzvah: true,
  bat_mitzvah: true,
  henna: true,
  brit: true,
  brita: true,
  business: true,
}

type Store = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

function defaultStore(): Store | null {
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

/** מחזיר את הערך אם הוא סוג אירוע אמיתי, אחרת null. */
export function parseEventType(raw: string | null | undefined): EventType | null {
  if (!raw || !Object.prototype.hasOwnProperty.call(VALID, raw)) return null
  return raw as EventType
}

/** קולט event_type מה-query string ושומר אותו להמשך ההרשמה. ערך לא תקין — מתעלמים. */
export function captureSignupEventType(search: string, store: Store | null = defaultStore()): void {
  const type = parseEventType(new URLSearchParams(search).get('event_type'))
  if (!type || !store) return
  try {
    store.setItem(KEY, type)
  } catch {
    // אחסון חסום (גלישה פרטית וכו') — פשוט לא נבחר מראש.
  }
}

/** הסוג שנשמר מדף הבית, אם יש. */
export function readSignupEventType(store: Store | null = defaultStore()): EventType | null {
  try {
    return parseEventType(store?.getItem(KEY))
  } catch {
    return null
  }
}

/** נקרא אחרי שהאירוע הראשון נוצר. */
export function clearSignupEventType(store: Store | null = defaultStore()): void {
  try {
    store?.removeItem(KEY)
  } catch {
    // אין מה לנקות
  }
}
