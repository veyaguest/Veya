/** ניהול מצב ההתחברות בצד הלקוח: טוקן + האירוע הפעיל, נשמרים ב-localStorage. */

const TOKEN_KEY = 'veya_token'
const EVENT_KEY = 'veya_event_id'

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

/** מנקה את כל מצב ההתחברות (התנתקות). */
export function clearAuth(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(EVENT_KEY)
}

/** אירוע גלובלי שנורה כשמתקבל 401 — האפליקציה מגיבה בהצגת מסך התחברות. */
export function notifyUnauthorized(): void {
  window.dispatchEvent(new Event('veya-unauthorized'))
}
