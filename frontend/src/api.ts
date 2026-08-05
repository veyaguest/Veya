import type {
  AdminAccountCreateResult,
  AdminAuditRow,
  AdminDashboard,
  AdminEventRow,
  AdminImpersonateResult,
  AdminPasswordResetResult,
  AdminUserDetail,
  AdminMessageStats,
  AdminUserRow,
  AdminUserUpdate,
  AdminVenueMerge,
  AdminVenueRow,
  AdminVenueUpdate,
  AnalyzeResult,
  AuditLogRow,
  AutomationDashboard,
  Clarification,
  CommunicationDueQueue,
  CommunicationSendResult,
  ConfirmGuestPublic,
  ConfirmSubmit,
  DashboardStats,
  EventDetails,
  EventMemberRead,
  EventMessage,
  EventMessageInput,
  EventSummary,
  GroupNotes,
  GroupSuggestion,
  GuestTimeline,
  Guest,
  GuestCreate,
  GuestUpdate,
  HallElement,
  HallLayout,
  HallState,
  HallTableSave,
  ImportPreview,
  Message,
  MessageDefault,
  MessageDefaultInput,
  MessageDefaultsBackfillResult,
  MessageTemplate,
  RsvpSummary,
  ReserveSummary,
  RecommendSeatResponse,
  AssignSeatResult,
  SeatingRequest,
  SeatingResult,
  NoteSplitSuggestions,
  SeatingUndoResult,
  SeatingUndoState,
  SendInvitationsResult,
  RsvpTimelineView,
  RsvpTrackActivateResult,
  RsvpTrackAdvanceResult,
  RsvpTrackStatus,
  InvitationSendPreview,
  SendScope,
  TokenResponse,
  User,
  VenueSuggestion,
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

/**
 * מרכיב כתובת תצוגה תקינה לתמונה ששמורה בשרת (הזמנה/סקיצת אולם).
 *
 * למה זה קיים: השרת מחזיר נתיב תמונה כמו ``/media/<id>``. מקור האמת היחיד
 * לכתובת השרת הוא ``VITE_API_URL`` של הפרונטאנד (חייב להיות נכון, אחרת שום
 * קריאת API לא עובדת) — ולכן כאן מרכיבים את הכתובת המלאה מולו. כך תמונות
 * עובדות בכל סביבה בלי להסתמך על משתנה סביבה נפרד ושביר בצד השרת.
 *
 * - ``data:`` / ``blob:`` (תצוגה מקדימה מקומית לפני שמירה) → מוחזר כמו שהוא.
 * - כל ערך שמכיל ``/media/..`` או ``/uploads/..`` (גם אם הגיע עם host שגוי
 *   כמו localhost) → מחלצים את הנתיב ומרכיבים אותו מול ``API_URL`` הנכון.
 * - כתובת חיצונית אחרת (http/https) → מוחזרת כמו שהיא.
 */
export function mediaUrl(raw?: string | null): string {
  if (!raw) return ''
  if (/^(data:|blob:)/i.test(raw)) return raw
  const base = API_URL.replace(/\/$/, '')
  const m = raw.match(/\/(?:media|uploads)\/.+$/)
  if (m) return base + m[0]
  if (/^https?:\/\//i.test(raw)) return raw
  return base + (raw.startsWith('/') ? raw : '/' + raw)
}

/** מרכיב כותרות בקשה כולל טוקן ההתחברות והאירוע הפעיל. */
function authHeaders(extra?: HeadersInit): Record<string, string> {
  const h: Record<string, string> = { ...(extra as Record<string, string>) }
  const token = getToken()
  if (token) h['Authorization'] = `Bearer ${token}`
  const eventId = getEventId()
  if (eventId != null) h['X-Event-Id'] = String(eventId)
  return h
}

const NETWORK_ERROR_MESSAGE = 'החיבור לשרת נכשל. בדקו את החיבור ונסו שוב.'
const SERVER_ERROR_MESSAGE = 'משהו השתבש. נסו שוב בעוד רגע.'
const PERMISSION_ERROR_MESSAGE = 'אין לכם הרשאה לבצע פעולה זו.'
const AUTH_ERROR_MESSAGE = 'אתם צריכים להתחבר מחדש.'

/**
 * שכבת שגיאות אחידה: כל מסך במערכת מקבל הודעת שגיאה בעברית שאפשר להבין
 * ולפעול לפיה — לעולם לא "Failed to fetch", "Value error" גולמי, או stack
 * trace. שני מקומות אחראים לכך: apiFetch (תקלת רשת — אין בכלל תשובה
 * מהשרת) ו-toError (תשובה עם קוד שגיאה — מנקה/ממיין אותה).
 */

/** fetch עוטף שמזריק כותרות אימות, הופך תקלת רשת גולמית להודעה בעברית,
 * ומטפל ב-401 (טוקן פג/לא תקין). */
async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: authHeaders(init?.headers),
    })
  } catch {
    // fetch() עצמו נכשל (אין רשת/שרת לא זמין/CORS) — לא Response בכלל,
    // אלא TypeError גולמי מהדפדפן. זה המקום היחיד לתפוס את זה עבור כל
    // קריאות ה-API במערכת.
    throw new Error(NETWORK_ERROR_MESSAGE)
  }
  if (res.status === 401) {
    clearAuth()
    notifyUnauthorized()
  }
  return res
}

/** כמו apiFetch, אבל בלי כותרות אימות — למסכים הציבוריים (הרשמה/התחברות/
 * דף אישור הגעה) שעדיין אין להם טוקן, או שלא צריכים אחד. אותה הגנה מפני
 * תקלת רשת גולמית — קריטי דווקא כאן כי אלה המסכים הראשונים שכל משתמש/ת
 * (או מוזמן/ת אנונימי/ת בדף האישור) פוגשים. */
async function publicFetch(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${API_URL}${path}`, init)
  } catch {
    throw new Error(NETWORK_ERROR_MESSAGE)
  }
}

/** מנקה קידומות טכניות שפיידנטיק (Pydantic) מוסיף לשגיאות ולידציה
 * מותאמות-אישית (למשל "Value error, הסיסמה חייבת..." → "הסיסמה חייבת..."). */
function cleanDetailMessage(msg: string): string {
  return msg.replace(/^(value error|assertion error)\s*,\s*/i, '').trim()
}

/** מחלץ הודעת שגיאה קריאה מתשובת FastAPI (כולל שגיאות ולידציה 422). */
async function toError(res: Response): Promise<Error> {
  // שגיאת שרת (5xx): לעולם לא מציגים למשתמש את התוכן הגולמי (יכול להיות
  // traceback/HTML) — רק את ההודעה הידידותית, בלי קשר למה שהשרת החזיר.
  if (res.status >= 500) {
    return new Error(SERVER_ERROR_MESSAGE)
  }
  try {
    const body = await res.json()
    if (typeof body.detail === 'string' && body.detail.trim()) {
      return new Error(cleanDetailMessage(body.detail))
    }
    if (Array.isArray(body.detail) && body.detail.length) {
      const msgs = body.detail
        .map((d: { msg: string }) => cleanDetailMessage(d.msg))
        .filter(Boolean)
        .join(', ')
      if (msgs) return new Error(msgs)
    }
  } catch {
    /* התשובה לא הייתה JSON תקין — נופלים לברירות המחדל לפי קוד הסטטוס. */
  }
  if (res.status === 401) return new Error(AUTH_ERROR_MESSAGE)
  if (res.status === 403) return new Error(PERMISSION_ERROR_MESSAGE)
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
  acceptedTerms: boolean,
  acceptedMarketing = false,
): Promise<TokenResponse> {
  const res = await publicFetch('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email,
      password,
      display_name: displayName,
      phone,
      accepted_terms: acceptedTerms,
      accepted_marketing: acceptedMarketing,
    }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** אישור/אישור-מחדש מפורש של תנאי שימוש/מדיניות פרטיות (למשל אחרי עדכון גרסה). */
export async function acceptConsent(
  types: Array<'terms' | 'privacy' | 'marketing'> = ['terms', 'privacy'],
): Promise<void> {
  const res = await apiFetch('/auth/consent', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ types }),
  })
  if (!res.ok) throw await toError(res)
}

/** מוחק לצמיתות את החשבון המחובר (כולל כל האירועים שלו). בלתי הפיך. */
export async function deleteMyAccount(): Promise<void> {
  const res = await apiFetch('/auth/me', { method: 'DELETE' })
  if (!res.ok) throw await toError(res)
}

/** מייצא את כל המידע האישי של המשתמש המחובר כאובייקט JSON. */
export async function exportMyData(): Promise<Record<string, unknown>> {
  const res = await apiFetch('/auth/me/export')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function login(
  email: string,
  password: string,
): Promise<TokenResponse> {
  const res = await publicFetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** ממיר טוקן Supabase (אחרי OAuth של גוגל) לטוקן פנימי של VEYA.
 * המשך זהה ל-login רגיל: שומרים את access_token ב-authStore ונכנסים לאפליקציה. */
export async function googleExchange(
  supabaseAccessToken: string,
): Promise<TokenResponse> {
  const res = await publicFetch('/auth/google/exchange', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ supabase_access_token: supabaseAccessToken }),
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
  event_type?: string
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

/** עדכון פרטי מוזמן קיים (עריכה ע"י בעל האירוע). */
export async function updateGuest(id: number, data: GuestUpdate): Promise<Guest> {
  const res = await apiFetch(`/guests/${id}`, {
    method: 'PATCH',
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

// ---- הפרדת ההערות: הצעה להעביר הערות קיימות לשדה "הערות הושבה" ----
export async function getNoteSplitSuggestions(): Promise<NoteSplitSuggestions> {
  const res = await apiFetch('/constraints/note-split/suggestions')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function applyNoteSplit(guestIds: number[]): Promise<{ moved: number }> {
  const res = await apiFetch('/constraints/note-split/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ guest_ids: guestIds }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- "החזרת הסידור הקודם" (Undo ייעודי להושבה בקליק) ----
export async function undoSeating(): Promise<SeatingUndoResult> {
  const res = await apiFetch('/seating/undo', { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function getSeatingUndoState(): Promise<SeatingUndoState> {
  const res = await apiFetch('/seating/undo-state')
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
      | 'event_type'
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
  hallLayout?: HallLayout | null,
  reserveSeats?: number | null,
): Promise<HallState> {
  const res = await apiFetch('/hall', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      tables,
      seats_per_table: seatsPerTable,
      elements,
      sketch,
      hall_layout: hallLayout,
      reserve_seats: reserveSeats,
    }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- ניהול רזרבה חכם (מצב יום האירוע) ----

/** סיכום הרזרבה — מקומות פנויים, שולחנות רזרבה, משובצים וללא שולחן. */
export async function getReserveSummary(): Promise<ReserveSummary> {
  const res = await apiFetch('/seating/reserve')
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** המלצה דטרמיניסטית על השולחן/ות המתאים/ים ביותר לשיבוץ מוזמן בודד. */
export async function recommendSeat(
  guestId: number,
  includeReserve = true,
): Promise<RecommendSeatResponse> {
  const res = await apiFetch('/seating/recommend-seat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ guest_id: guestId, include_reserve: includeReserve }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** שיבוץ מהיר של מוזמן לשולחן (או שחרור אם table_number=null). מחזיר אזהרות רכות. */
export async function assignSeat(
  guestId: number,
  tableNumber: number | null,
): Promise<AssignSeatResult> {
  const res = await apiFetch('/seating/assign', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ guest_id: guestId, table_number: tableNumber }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- דף אישור הגעה ציבורי (קישור אישי — ללא התחברות) ----

/** מביא את פרטי המוזמן והאירוע לפי הטוקן האישי (נתיב ציבורי, בלי טוקן אימות). */
export async function getConfirm(token: string): Promise<ConfirmGuestPublic> {
  const res = await publicFetch(`/confirm/${encodeURIComponent(token)}`)
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** שולח את תשובת המוזמן (מגיע/לא/אולי + כמות + הערה). */
export async function submitConfirm(
  token: string,
  payload: ConfirmSubmit,
): Promise<ConfirmGuestPublic> {
  const res = await publicFetch(`/confirm/${encodeURIComponent(token)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
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

/** ספירה מקדימה לפני שליחה — כמה יקבלו, כמה לא (וסיבה), האם כבר נשלח. */
export async function previewSend(): Promise<InvitationSendPreview> {
  const res = await apiFetch('/automation/track/preview')
  if (!res.ok) throw await toError(res)
  return res.json()
}

/**
 * שולח הזמנות ומפעיל את המסלול (mock). היקף השליחה:
 * - ללא אפשרויות / scope='new' → רק מי שעדיין לא קיבל.
 * - scope='all' → שליחה מחדש לכולם.
 * - retryIds → ניסיון חוזר רק למוזמנים אלה.
 */
export async function activateRsvpTrack(opts?: {
  scope?: SendScope
  retryIds?: number[]
  guestIds?: number[]
}): Promise<RsvpTrackActivateResult> {
  const body: { scope?: SendScope; retry_ids?: number[]; guest_ids?: number[] } = {}
  if (opts?.scope) body.scope = opts.scope
  if (opts?.retryIds) body.retry_ids = opts.retryIds
  if (opts?.guestIds) body.guest_ids = opts.guestIds
  const res = await apiFetch('/automation/track/activate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** מקדם את המסלול אוטומטית (idempotent) — נקרא בטעינת מסך ה-RSVP. */
export async function advanceRsvpTrack(): Promise<RsvpTrackAdvanceResult> {
  const res = await apiFetch('/automation/track/advance', { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- תקשורת עם אורחים — רצף ההודעות הקבוע של האירוע ----

export async function getCommunicationSequence(): Promise<EventMessage[]> {
  const res = await apiFetch('/communication/sequence')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function updateCommunicationMessage(
  messageType: string,
  data: Partial<EventMessageInput>,
): Promise<EventMessage> {
  const res = await apiFetch(`/communication/sequence/${messageType}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function previewCommunicationMessage(messageType: string): Promise<string> {
  const res = await apiFetch(`/communication/sequence/${messageType}/preview`, {
    method: 'POST',
  })
  if (!res.ok) throw await toError(res)
  return (await res.json()).preview
}

export async function testSendCommunicationMessage(
  messageType: string,
): Promise<CommunicationSendResult> {
  const res = await apiFetch(`/communication/sequence/${messageType}/test-send`, {
    method: 'POST',
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function getMessageLibrary(): Promise<MessageDefault[]> {
  const res = await apiFetch('/communication/library')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function getCommunicationDue(): Promise<CommunicationDueQueue> {
  const res = await apiFetch('/communication/due')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function sendCommunicationDue(): Promise<CommunicationSendResult> {
  const res = await apiFetch('/communication/due/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- ניהול ברירות המחדל הגלובליות של רצף ההודעות (אדמין בלבד) ----

export async function adminListMessageDefaults(): Promise<MessageDefault[]> {
  const res = await apiFetch('/admin/message-defaults')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminUpdateMessageDefault(
  defaultId: number,
  data: Partial<MessageDefaultInput>,
): Promise<MessageDefault> {
  const res = await apiFetch(`/admin/message-defaults/${defaultId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminBackfillMessageDefaults(): Promise<MessageDefaultsBackfillResult> {
  const res = await apiFetch('/admin/message-defaults/backfill', { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminMessageStats(): Promise<AdminMessageStats> {
  const res = await apiFetch('/admin/veya/message-stats')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminAuditLog(action?: string): Promise<AdminAuditRow[]> {
  const qs = action ? `?action=${encodeURIComponent(action)}` : ''
  const res = await apiFetch(`/admin/audit-log${qs}`)
  if (!res.ok) throw await toError(res)
  return res.json()
}
