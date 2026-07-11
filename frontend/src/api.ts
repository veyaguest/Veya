import type {
  AdminEventRow,
  AdminUserRow,
  AnalyzeResult,
  AuditLogRow,
  Clarification,
  ConfirmGuestPublic,
  ConfirmSubmit,
  DashboardStats,
  EventDetails,
  EventSummary,
  Guest,
  GuestCreate,
  HallElement,
  HallState,
  HallTableSave,
  ImportPreview,
  Message,
  MessageTemplate,
  RsvpSummary,
  SeatingRequest,
  SeatingResult,
  SendInvitationsResult,
  TokenResponse,
  User,
} from './types'
import {
  clearAuth,
  getEventId,
  getToken,
  notifyUnauthorized,
} from './authStore'

// כתובת ה-API ניתנת להגדרה בזמן build דרך משתנה סביבה של Vite (VITE_API_URL),
// כדי שבייצור אפשר להצביע על השרת האמיתי. ברירת מחדל: שרת הפיתוח המקומי.
const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

/** מרכיב כותרות בקשה כולל טוקן ההתחברות והאירוע הפעיל. */
function authHeaders(extra?: HeadersInit): Record<string, string> {
  const h: Record<string, string> = { ...(extra as Record<string, string>) }
  const token = getToken()
  if (token) h['Authorization'] = `Bearer ${token}`
  const eventId = getEventId()
  if (eventId != null) h['X-Event-Id'] = String(eventId)
  return h
}

/** fetch עוטף שמזריק כותרות אימות ומטפל ב-401 (טוקן פג/לא תקין). */
async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: authHeaders(init?.headers),
  })
  if (res.status === 401) {
    clearAuth()
    notifyUnauthorized()
  }
  return res
}

/** מחלץ הודעת שגיאה קריאה מתשובת FastAPI (כולל שגיאות ולידציה 422). */
async function toError(res: Response): Promise<Error> {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return new Error(body.detail)
    if (Array.isArray(body.detail)) {
      const msgs = body.detail.map((d: { msg: string }) => d.msg).join(', ')
      return new Error(msgs || `שגיאה ${res.status}`)
    }
  } catch {
    /* ignore */
  }
  return new Error(`שגיאה ${res.status}`)
}

export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch(`${API_URL}/health`)
    return res.ok
  } catch {
    return false
  }
}

// ---- התחברות + משתמשים (שלב 8) ----

export async function register(
  email: string,
  password: string,
  displayName: string,
): Promise<TokenResponse> {
  const res = await fetch(`${API_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, display_name: displayName }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function login(
  email: string,
  password: string,
): Promise<TokenResponse> {
  const res = await fetch(`${API_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function getMe(): Promise<User> {
  const res = await apiFetch('/auth/me')
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- ניהול אירועים של המשתמש (שלב 8) ----

export async function listMyEvents(): Promise<EventSummary[]> {
  const res = await apiFetch('/events')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function createMyEvent(data: {
  groom_name: string
  bride_name: string
  venue_name: string
}): Promise<EventSummary> {
  const res = await apiFetch('/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function deleteMyEvent(id: number): Promise<void> {
  const res = await apiFetch(`/events/${id}`, { method: 'DELETE' })
  if (!res.ok) throw await toError(res)
}

// ---- פאנל אדמין ----

export async function adminListUsers(): Promise<AdminUserRow[]> {
  const res = await apiFetch('/admin/users')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminListEvents(): Promise<AdminEventRow[]> {
  const res = await apiFetch('/admin/events')
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- מוזמנים ----

export async function listGuests(q?: string): Promise<Guest[]> {
  const path = q ? `/guests?q=${encodeURIComponent(q)}` : '/guests'
  const res = await apiFetch(path)
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function createGuest(data: GuestCreate): Promise<Guest> {
  const res = await apiFetch('/guests', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function deleteGuest(id: number): Promise<void> {
  const res = await apiFetch(`/guests/${id}`, { method: 'DELETE' })
  if (!res.ok) throw await toError(res)
}

export async function previewImport(file: File): Promise<ImportPreview> {
  const fd = new FormData()
  fd.append('file', file)
  const res = await apiFetch('/guests/import/preview', {
    method: 'POST',
    body: fd,
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function commitImport(
  rows: GuestCreate[],
): Promise<{ created: number }> {
  const res = await apiFetch('/guests/import/commit', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rows }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function generateSeating(
  req: SeatingRequest,
): Promise<SeatingResult> {
  const res = await apiFetch('/seating/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function analyzeConstraints(): Promise<AnalyzeResult> {
  const res = await apiFetch('/constraints/analyze', { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function listClarifications(): Promise<Clarification[]> {
  const res = await apiFetch('/constraints/clarifications')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function resolveClarification(
  id: number,
  chosenGuestId: number | null,
): Promise<AnalyzeResult> {
  const res = await apiFetch(`/constraints/clarifications/${id}/resolve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chosen_guest_id: chosenGuestId }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- WhatsApp / RSVP (שלב 5) ----

export async function rsvpSummary(): Promise<RsvpSummary> {
  const res = await apiFetch('/messaging/summary')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function sendInvitations(
  onlyPending: boolean,
): Promise<SendInvitationsResult> {
  const res = await apiFetch('/messaging/invitations/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ only_pending: onlyPending }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function sendReminders(): Promise<SendInvitationsResult> {
  const res = await apiFetch('/messaging/reminders/send', { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function simulateReply(
  guestId: number,
  coming: boolean,
): Promise<RsvpSummary> {
  const res = await apiFetch('/messaging/simulate-reply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ guest_id: guestId, coming }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function messageLog(limit = 50): Promise<Message[]> {
  const res = await apiFetch(`/messaging/log?limit=${limit}`)
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function getTemplate(): Promise<MessageTemplate> {
  const res = await apiFetch('/messaging/template')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function saveTemplate(template: string): Promise<MessageTemplate> {
  const res = await apiFetch('/messaging/template', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ template }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function previewTemplate(template: string): Promise<string> {
  const res = await apiFetch('/messaging/template/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ template }),
  })
  if (!res.ok) throw await toError(res)
  const data = await res.json()
  return data.preview as string
}

// ---- דשבורד + אירוע (שלב 6) ----

export async function getStats(): Promise<DashboardStats> {
  const res = await apiFetch('/stats')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function getEvent(): Promise<EventDetails> {
  const res = await apiFetch('/event')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function updateEvent(
  data: Partial<
    Pick<
      EventDetails,
      | 'groom_name'
      | 'bride_name'
      | 'venue_name'
      | 'event_date'
      | 'event_time'
      | 'invite_image'
    >
  >,
): Promise<EventDetails> {
  const res = await apiFetch('/event', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function readAudit(limit = 30): Promise<AuditLogRow[]> {
  const res = await apiFetch(`/event/audit?limit=${limit}`)
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- מפת אולם (שלב 7) ----

export async function getHall(): Promise<HallState> {
  const res = await apiFetch('/hall')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function saveHall(
  tables: HallTableSave[],
  seatsPerTable?: number,
  elements?: HallElement[],
  sketch?: string | null,
): Promise<HallState> {
  const res = await apiFetch('/hall', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tables,
      seats_per_table: seatsPerTable,
      elements,
      sketch,
    }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- דף אישור הגעה ציבורי (קישור אישי — ללא התחברות) ----

/** מביא את פרטי המוזמן והאירוע לפי הטוקן האישי (נתיב ציבורי, בלי טוקן אימות). */
export async function getConfirm(token: string): Promise<ConfirmGuestPublic> {
  const res = await fetch(`${API_URL}/confirm/${encodeURIComponent(token)}`)
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** שולח את תשובת המוזמן (מגיע/לא/אולי + כמות + הערה). */
export async function submitConfirm(
  token: string,
  payload: ConfirmSubmit,
): Promise<ConfirmGuestPublic> {
  const res = await fetch(`${API_URL}/confirm/${encodeURIComponent(token)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}
