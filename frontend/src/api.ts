import type {
  AdminAccountCreateResult,
  AdminDashboard,
  AdminEventRow,
  AdminImpersonateResult,
  AdminPasswordResetResult,
  AdminUserDetail,
  AdminUserRow,
  AdminUserUpdate,
  AdminVenueMerge,
  AdminVenueRow,
  AdminVenueUpdate,
  AnalyzeResult,
  AuditLogRow,
  AutomationDashboard,
  AutomationRule,
  AutomationRuleInput,
  AutomationTemplate,
  AutomationTemplateInput,
  Clarification,
  ConfirmGuestPublic,
  ConfirmSubmit,
  DashboardStats,
  DueQueue,
  EventDetails,
  EventMemberRead,
  EventSummary,
  GroupNotes,
  GroupSuggestion,
  GuestTimeline,
  Guest,
  GuestCreate,
  HallElement,
  HallState,
  HallTableSave,
  ImportPreview,
  Message,
  MessageTemplate,
  RsvpSummary,
  RunDueResult,
  SeatingRequest,
  SeatingResult,
  SendInvitationsResult,
  TemplatePlaceholder,
  RsvpTimelineView,
  RsvpTrackActivateResult,
  RsvpTrackAdvanceResult,
  RsvpTrackStatus,
  TokenResponse,
  User,
  VenueSuggestion,
  VeyaTemplate,
  VeyaTemplateInput,
  VeyaWorkflowStep,
  VeyaWorkflowStepInput,
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
  phone: string,
): Promise<TokenResponse> {
  const res = await fetch(`${API_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, display_name: displayName, phone }),
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

/** עדכון שם התצוגה (וברירת מחדל גם הטלפון) של המשתמש המחובר. */
export async function updateProfile(displayName: string, phone?: string): Promise<User> {
  const body: Record<string, string> = { display_name: displayName }
  if (phone !== undefined) body.phone = phone
  const res = await apiFetch('/auth/me', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** שינוי סיסמה: מחזיר טוקן חדש (המכשיר הנוכחי נשאר מחובר). */
export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<TokenResponse> {
  const res = await apiFetch('/auth/change-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** יציאה מכל המכשירים: פוסל את כל הטוקנים הקיימים בשרת. */
export async function logoutAll(): Promise<void> {
  const res = await apiFetch('/auth/logout-all', { method: 'POST' })
  if (!res.ok) throw await toError(res)
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

export async function adminDashboard(): Promise<AdminDashboard> {
  const res = await apiFetch('/admin/dashboard')
  if (!res.ok) throw await toError(res)
  return res.json()
}

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

/** כרטיס משתמש מלא: פרופיל + אירועים + היסטוריית התחברות. */
export async function adminGetUser(userId: number): Promise<AdminUserDetail> {
  const res = await apiFetch(`/admin/users/${userId}`)
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** עריכת פרטי משתמש ע"י אדמין (עדכון חלקי). */
export async function adminUpdateUser(
  userId: number,
  data: AdminUserUpdate,
): Promise<AdminUserRow> {
  const res = await apiFetch(`/admin/users/${userId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** איפוס סיסמה: מחזיר סיסמה זמנית שהאדמין ימסור למשתמש. */
export async function adminResetPassword(
  userId: number,
  newPassword?: string,
): Promise<AdminPasswordResetResult> {
  const res = await apiFetch(`/admin/users/${userId}/reset-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ new_password: newPassword ?? null }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminDisableUser(userId: number): Promise<void> {
  const res = await apiFetch(`/admin/users/${userId}/disable`, { method: 'POST' })
  if (!res.ok) throw await toError(res)
}

export async function adminEnableUser(userId: number): Promise<void> {
  const res = await apiFetch(`/admin/users/${userId}/enable`, { method: 'POST' })
  if (!res.ok) throw await toError(res)
}

export async function adminDeleteUser(userId: number): Promise<void> {
  const res = await apiFetch(`/admin/users/${userId}`, { method: 'DELETE' })
  if (!res.ok) throw await toError(res)
}

/** "התחבר כמשתמש" — מנפיק טוקן זמני שמאפשר לראות את המערכת בעיני המשתמש. */
export async function adminImpersonate(userId: number): Promise<AdminImpersonateResult> {
  const res = await apiFetch(`/admin/users/${userId}/impersonate`, { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** יצירת חשבון מפיק/אולם ע"י אדמין (אין הרשמה עצמאית לתפקידים אלו). */
export async function adminCreateAccount(data: {
  email: string
  display_name: string
  account_type: 'planner' | 'venue'
}): Promise<AdminAccountCreateResult> {
  const res = await apiFetch('/admin/accounts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- ניהול מאגר האולמות (אדמין) ----

export async function adminListVenues(): Promise<AdminVenueRow[]> {
  const res = await apiFetch('/admin/venues')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminUpdateVenue(
  venueId: number,
  data: AdminVenueUpdate,
): Promise<AdminVenueRow> {
  const res = await apiFetch(`/admin/venues/${venueId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminDeleteVenue(venueId: number): Promise<void> {
  const res = await apiFetch(`/admin/venues/${venueId}`, { method: 'DELETE' })
  if (!res.ok) throw await toError(res)
}

export async function adminMergeVenue(
  venueId: number,
  data: AdminVenueMerge,
): Promise<AdminVenueRow> {
  const res = await apiFetch(`/admin/venues/${venueId}/merge`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- שיתוף גישה לאירוע (מפיק/אולם) ----

export async function listEventMembers(eventId: number): Promise<EventMemberRead[]> {
  const res = await apiFetch(`/events/${eventId}/members`)
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function addEventMember(
  eventId: number,
  email: string,
  permissions: string[],
): Promise<EventMemberRead> {
  const res = await apiFetch(`/events/${eventId}/members`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, permissions }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function updateEventMember(
  eventId: number,
  memberId: number,
  permissions: string[],
): Promise<EventMemberRead> {
  const res = await apiFetch(`/events/${eventId}/members/${memberId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ permissions }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function removeEventMember(eventId: number, memberId: number): Promise<void> {
  const res = await apiFetch(`/events/${eventId}/members/${memberId}`, { method: 'DELETE' })
  if (!res.ok) throw await toError(res)
}

// ---- מוזמנים ----

export interface GuestListPage {
  items: Guest[]
  total: number
  total_people: number
  confirmed_people: number
  limit: number
  offset: number
}

export async function listGuests(
  q?: string,
  limit = 50,
  offset = 0,
): Promise<GuestListPage> {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  const res = await apiFetch(`/guests?${params.toString()}`)
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

/** הצעות קבוצה חכמות — מקבצי שם-משפחה זהה ברשימת המוזמנים. */
export async function groupSuggestions(): Promise<GroupSuggestion[]> {
  const res = await apiFetch('/guests/group-suggestions')
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** שיוך קבוצתי: מעדכן את הקבוצה לרשימת מוזמנים בבת אחת. */
export async function bulkGroup(
  guestIds: number[],
  groupType: string,
): Promise<{ updated: number }> {
  const res = await apiFetch('/guests/bulk-group', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ guest_ids: guestIds, group_type: groupType }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** הערות/העדפות ברמת קבוצה + הקבוצות הפעילות באירוע. */
export async function getGroupNotes(): Promise<GroupNotes> {
  const res = await apiFetch('/guests/group-notes')
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** שמירת הערה לקבוצה אחת (הערה ריקה מוחקת). */
export async function setGroupNote(
  groupType: string,
  note: string,
): Promise<GroupNotes> {
  const res = await apiFetch('/guests/group-notes', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ group_type: groupType, note }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
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

/** ייבוא חכם: שולח רשימת טקסט חופשי (הדבקה) ומקבל תצוגה מקדימה מפוענחת. */
export async function pasteImportPreview(text: string): Promise<ImportPreview> {
  const res = await apiFetch('/guests/import/paste', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function commitImport(
  rows: GuestCreate[],
): Promise<{ created: number; skipped_duplicates: number }> {
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
      | 'venue_address'
      | 'event_date'
      | 'event_time'
      | 'invite_image'
      | 'venue_commit_days_before'
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

export async function searchVenues(q: string): Promise<VenueSuggestion[]> {
  const query = q.trim()
  if (!query) return []
  const res = await apiFetch(`/venues/search?q=${encodeURIComponent(query)}`)
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

// ---- מנוע אוטומציות אישורי הגעה (RSVP Automation) ----

/** רשימת המשתנים הדינמיים ({{...}}) הזמינים לתבניות האוטומציה. */
export async function getAutomationPlaceholders(): Promise<TemplatePlaceholder[]> {
  const res = await apiFetch('/automation/placeholders')
  if (!res.ok) throw await toError(res)
  return res.json()
}

// -- תבניות הודעה בעלות שם --

export async function listAutomationTemplates(): Promise<AutomationTemplate[]> {
  const res = await apiFetch('/automation/templates')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function createAutomationTemplate(
  data: AutomationTemplateInput,
): Promise<AutomationTemplate> {
  const res = await apiFetch('/automation/templates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function updateAutomationTemplate(
  templateId: number,
  data: Partial<AutomationTemplateInput>,
): Promise<AutomationTemplate> {
  const res = await apiFetch(`/automation/templates/${templateId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function deleteAutomationTemplate(templateId: number): Promise<void> {
  const res = await apiFetch(`/automation/templates/${templateId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw await toError(res)
}

// -- חוקי אוטומציה --

export async function listAutomationRules(): Promise<AutomationRule[]> {
  const res = await apiFetch('/automation/rules')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function createAutomationRule(
  data: AutomationRuleInput,
): Promise<AutomationRule> {
  const res = await apiFetch('/automation/rules', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function updateAutomationRule(
  ruleId: number,
  data: Partial<AutomationRuleInput>,
): Promise<AutomationRule> {
  const res = await apiFetch(`/automation/rules/${ruleId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function deleteAutomationRule(ruleId: number): Promise<void> {
  const res = await apiFetch(`/automation/rules/${ruleId}`, { method: 'DELETE' })
  if (!res.ok) throw await toError(res)
}

// -- התור לאישור + שליחה --

/** התור לאישור — מי אמור לקבל הודעה עכשיו (מחושב חי, לא נשלח כלום). */
export async function getDueQueue(): Promise<DueQueue> {
  const res = await apiFetch('/automation/due')
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** שליחה בפועל של התור לאחר אישור. ריק => כל התור; אחרת רק החוקים שסומנו. */
export async function runDueQueue(ruleIds?: number[]): Promise<RunDueResult> {
  const res = await apiFetch('/automation/run-due', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rule_ids: ruleIds ?? null }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

// -- Timeline של מוזמן + דשבורד --

export async function getGuestTimeline(guestId: number): Promise<GuestTimeline> {
  const res = await apiFetch(`/automation/timeline/${guestId}`)
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function getAutomationDashboard(): Promise<AutomationDashboard> {
  const res = await apiFetch('/automation/dashboard')
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** יומן המשימות של אישורי-ההגעה — לוח הזמנים היומי שנבנה לאחור מיום ההתחייבות. */
export async function getRsvpTimeline(): Promise<RsvpTimelineView> {
  const res = await apiFetch('/automation/timeline')
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- מסלול אישורי-ההגעה הקבוע (VEYA RSVP Track) ----

/** סטטוס המסלול למסך הזוג — פעיל/לא, ספירות, רשימת מעקב טלפוני, שלבים. */
export async function getRsvpTrack(): Promise<RsvpTrackStatus> {
  const res = await apiFetch('/automation/track')
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** מפעיל את המסלול: מקצה תבניות+חוקים ושולח הזמנות לכל המוזמנים (mock). */
export async function activateRsvpTrack(): Promise<RsvpTrackActivateResult> {
  const res = await apiFetch('/automation/track/activate', { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** מקדם את המסלול אוטומטית (idempotent) — נקרא בטעינת מסך ה-RSVP. */
export async function advanceRsvpTrack(): Promise<RsvpTrackAdvanceResult> {
  const res = await apiFetch('/automation/track/advance', { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- ניהול ברירות המחדל הגלובליות של VEYA (אדמין בלבד) ----

export async function adminListVeyaTemplates(): Promise<VeyaTemplate[]> {
  const res = await apiFetch('/admin/veya/templates')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminCreateVeyaTemplate(
  data: VeyaTemplateInput,
): Promise<VeyaTemplate> {
  const res = await apiFetch('/admin/veya/templates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminUpdateVeyaTemplate(
  templateId: number,
  data: Partial<VeyaTemplateInput>,
): Promise<VeyaTemplate> {
  const res = await apiFetch(`/admin/veya/templates/${templateId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminDeleteVeyaTemplate(templateId: number): Promise<void> {
  const res = await apiFetch(`/admin/veya/templates/${templateId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw await toError(res)
}

export async function adminListVeyaWorkflow(): Promise<VeyaWorkflowStep[]> {
  const res = await apiFetch('/admin/veya/workflow')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminUpdateVeyaWorkflowStep(
  stepId: number,
  data: VeyaWorkflowStepInput,
): Promise<VeyaWorkflowStep> {
  const res = await apiFetch(`/admin/veya/workflow/${stepId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}
