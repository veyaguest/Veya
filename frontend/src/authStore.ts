/** ניהול מצב ההתחברות בצד הלקוח: טוקן + האירוע הפעיל, נשמרים ב-localStorage. */

const TOKEN_KEY = 'veya_token'
const EVENT_KEY = 'veya_event_id'
// סוג האירוע הפעיל — נשמר כדי שמסכים יוכלו לגזור מונחים דינמיים (צדדים,
// בעלי אירוע) בלי להעביר event_type בכל prop. חתונה היא ברירת המחדל.
const EVENT_TYPE_KEY = 'veya_event_type'
// כשאדמין "מתחבר כמשתמש" (התחזות) — טוקן האדמין נשמר כאן בצד, וטוקן המשתמש
// נכנס במקומו ב-TOKEN_KEY. קיום ערך כאן פירושו שאנחנו במצב התחזות פעיל.
const ADMIN_TOKEN_KEY = 'veya_admin_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function getEventId(): number | null {
  const raw = localStorage.getItem(EVENT_KEY)
  return raw ? Number(raw) : null
}

export function setEventId(id: number | null): void {
  if (id == null) localStorage.removeItem(EVENT_KEY)
  else localStorage.setItem(EVENT_KEY, String(id))
}

/** סוג האירוע הפעיל (wedding אם לא נקבע). */
export function getActiveEventType(): string {
  return localStorage.getItem(EVENT_TYPE_KEY) || 'wedding'
}

/** קובע את סוג האירוע הפעיל — נקרא כשמתחלף האירוע הפעיל או נטענים פרטיו. */
export function setActiveEventType(type: string | null): void {
  if (!type) localStorage.removeItem(EVENT_TYPE_KEY)
  else localStorage.setItem(EVENT_TYPE_KEY, type)
}

/** טוקן האדמין השמור בזמן התחזות (או null אם לא מתחזים כרגע). */
export function getAdminToken(): string | null {
  return localStorage.getItem(ADMIN_TOKEN_KEY)
}

/** שומר את טוקן האדמין בצד ומסמן כניסה למצב התחזות. */
export function setAdminToken(token: string): void {
  localStorage.setItem(ADMIN_TOKEN_KEY, token)
}

/** מסיר את טוקן האדמין השמור (יציאה ממצב התחזות). */
export function clearAdminToken(): void {
  localStorage.removeItem(ADMIN_TOKEN_KEY)
}

/** האם אנחנו כרגע במצב התחזות (אדמין שמחובר כמשתמש). */
export function isImpersonating(): boolean {
  return localStorage.getItem(ADMIN_TOKEN_KEY) != null
}

/** מנקה את כל מצב ההתחברות (התנתקות), כולל טוקן התחזות אם קיים. */
export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(EVENT_KEY)
  localStorage.removeItem(EVENT_TYPE_KEY)
  localStorage.removeItem(ADMIN_TOKEN_KEY)
}

/** אירוע גלובלי שנורה כשמתקבל 401 — האפליקציה מגיבה בהצגת מסך התחברות. */
export function notifyUnauthorized(): void {
  window.dispatchEvent(new Event('veya-unauthorized'))
}
