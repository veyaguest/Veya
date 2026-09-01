import type {
  AdminAccountCreateResult,
  AdminCallerRow,
  AdminCallersPage,
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
  CallCenterGuestDetail,
  CallCenterOverview,
  CallCenterQueue,
  CallCenterScope,
  CallOutcomeRequest,
  CallOutcomeResult,
  Clarification,
  CommunicationDueQueue,
  CommunicationSendResult,
  ManualSendResult,
  MessageType,
  Postponement,
  PostponementReviewRow,
  TargetAudience,
  ConfirmGuestPublic,
  ConfirmSubmit,
  GiftCheckoutResult,
  GiftQuote,
  GiftsSummary,
  DashboardStats,
  EnvelopeCreated,
  EnvelopeInput,
  Expense,
  ExpenseCategory,
  ExpenseInput,
  FinanceReport,
  FinanceSummary,
  GiftCounting,
  GiftEntry,
  GuestGiftRow,
  TemplateApplyResult,
  EventDetails,
  EventMemberRead,
  EventMessage,
  EventMessageInput,
  EventSummary,
  GroupNotes,
  GroupSuggestion,
  GuestDataAlerts,
  GuestTimeline,
  Guest,
  GuestCreate,
  GuestUpdate,
  DetectedHallElement,
  HallElement,
  HallLayout,
  HallSketchTransform,
  HallState,
  HallTableSave,
  ImportPreview,
  Message,
  MessageDefault,
  MessageDefaultInput,
  MessageDefaultsBackfillResult,
  MessageDefaultOption,
  MessageDefaultOptionCreate,
  MessageDefaultOptionInput,
  PayoutAccount,
  PayoutAccountInput,
  PayoutReviewRow,
  ReviewStatus,
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
  MessageStatusSummary,
  MessageTypeStatus,
  InvitationSendPreview,
  SendScope,
  TokenResponse,
  User,
  VenueSuggestion,
  AccountOverview,
  InvitationPreview,
  PartnerInvite,
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

/** מבקש קישור לאיפוס סיסמה. התגובה זהה תמיד, בלי קשר אם הכתובת קיימת. */
export async function forgotPassword(email: string): Promise<{ message: string }> {
  const res = await publicFetch('/auth/forgot-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** מממש קישור איפוס סיסמה: קובע סיסמה חדשה ומחזיר טוקן כניסה. */
export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<TokenResponse> {
  const res = await publicFetch('/auth/reset-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, new_password: newPassword }),
  })
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

/** מצב מחיקת משתמש: user_only = החשבון בלבד (האירועים נשארים) · user_and_events = החשבון + כל האירועים שלו. */
export type AdminDeleteUserMode = 'user_only' | 'user_and_events'

export async function adminDeleteUser(userId: number, mode: AdminDeleteUserMode): Promise<void> {
  const res = await apiFetch(`/admin/users/${userId}?mode=${mode}`, { method: 'DELETE' })
  if (!res.ok) throw await toError(res)
}

/** "התחבר כמשתמש" — מנפיק טוקן זמני שמאפשר לראות את המערכת בעיני המשתמש. */
/** מחיקת אירוע בודד ע"י אדמין — בלתי הפיכה, כולל כל המידע התלוי בו. */
export async function adminDeleteEvent(eventId: number): Promise<void> {
  const res = await apiFetch(`/admin/events/${eventId}`, { method: 'DELETE' })
  if (!res.ok) throw await toError(res)
}

export async function adminImpersonate(userId: number): Promise<AdminImpersonateResult> {
  const res = await apiFetch(`/admin/users/${userId}/impersonate`, { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** יצירת חשבון מפיק/אולם/טלפן ע"י אדמין (אין הרשמה עצמאית לתפקידים אלו). */
export async function adminCreateAccount(data: {
  email: string
  display_name: string
  account_type: 'planner' | 'venue' | 'phone_agent'
}): Promise<AdminAccountCreateResult> {
  const res = await apiFetch('/admin/accounts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- ניהול טלפנים (אדמין) ----

/** מסך ניהול הטלפנים: הטלפנים + האירועים להקצאה, בבקשה אחת. */
export async function adminListCallers(): Promise<AdminCallersPage> {
  const res = await apiFetch('/admin/callers')
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** מחליף את רשימת האירועים המוקצים לטלפן. רשימה ריקה = תור משותף. */
export async function adminSetCallerAssignments(
  userId: number,
  eventIds: number[],
): Promise<AdminCallerRow> {
  const res = await apiFetch(`/admin/callers/${userId}/assignments`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event_ids: eventIds }),
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

export type GuestSort = 'name' | 'status' | 'table' | 'party_size' | 'recent'
export type GuestFilter = 'all' | 'confirmed' | 'declined' | 'maybe' | 'pending' | 'no_table'

export async function listGuests(
  q?: string,
  limit = 50,
  offset = 0,
  sort?: GuestSort,
  filterStatus?: GuestFilter,
): Promise<GuestListPage> {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  params.set('limit', String(limit))
  params.set('offset', String(offset))
  if (sort) params.set('sort', sort)
  if (filterStatus && filterStatus !== 'all') params.set('filter_status', filterStatus)
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

/** ייבוא חכם: שולח רשימת טקסט חופשי (הדבקה) ומקבל תצוגה מקדימה מפוענחת.
 *
 * assumeSingleIfNoCount: true רק בזרימת ייבוא אנשי קשר (ContactsImportDialog)
 * — שם כל שורה היא כבר איש קשר בודד בוודאות, אז 1 היא עובדה ולא ניחוש.
 * בהדבקת רשימה חופשית רגילה (ברירת המחדל) כמות חסרה נשארת ריקה לבדיקה.
 */
export async function pasteImportPreview(
  text: string,
  opts?: { assumeSingleIfNoCount?: boolean },
): Promise<ImportPreview> {
  const res = await apiFetch('/guests/import/paste', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text,
      assume_single_if_no_count: opts?.assumeSingleIfNoCount ?? false,
    }),
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

/** מסך "מתנות באשראי" של בעלי האירוע — קריאה בלבד. */
export async function getGifts(): Promise<GiftsSummary> {
  const res = await apiFetch('/gifts')
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** פרטי קבלת מתנות — בעלי האירוע בלבד. */
export async function getPayoutAccount(): Promise<PayoutAccount> {
  const res = await apiFetch('/payout')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function savePayoutAccount(input: PayoutAccountInput): Promise<PayoutAccount> {
  const res = await apiFetch('/payout', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/**
 * מגיש את פרטי החשבון לבדיקה (missing/rejected → submitted).
 *
 * לא נשלח כאן מידע לאף גורם חיצוני — ההגשה רק מסמנת שהפרטים מוכנים.
 */
export async function submitPayoutAccount(): Promise<PayoutAccount> {
  const res = await apiFetch('/payout/submit', { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/**
 * מוריד את אישור ניהול החשבון כ-Blob.
 *
 * למה לא פשוט ``<a href>``: הנתיב מאומת ודורש כותרת Authorization, שקישור
 * רגיל אינו שולח. לכן מושכים את הקובץ דרך fetch ופותחים אותו מהזיכרון —
 * וכך גם אין לו כתובת ציבורית שאפשר לשתף בטעות.
 */
export async function fetchPayoutCertificate(): Promise<Blob> {
  const res = await apiFetch('/payout/certificate')
  if (!res.ok) throw await toError(res)
  return res.blob()
}

// ---- בדיקת פרטי קבלת מתנות בצד VEYA (אדמין בלבד) ----
//
// הנתיבים האלה מוגנים ב-``get_current_admin`` בשרת. בעל אירוע או מפיק
// שיקרא להם יקבל 403 — ההסתרה במסך היא נוחות, לא הגנה.

/**
 * רשימת חשבונות לאדמין.
 *
 * ``pending`` — תור הבדיקה. ``approved`` — חשבונות שכבר אושרו ונעולים,
 * והדרך היחידה להגיע אליהם כדי לפתוח אותם מחדש.
 */
export async function adminListPayoutReviews(
  scope: 'pending' | 'approved' = 'pending',
): Promise<PayoutReviewRow[]> {
  const res = await apiFetch(`/admin/payout?scope=${scope}`)
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** VEYA מאשרת. **אינו** משנה את בדיקת ספק הסליקה — היא מסלול נפרד. */
export async function adminApprovePayout(eventId: number): Promise<PayoutReviewRow> {
  const res = await apiFetch(`/admin/payout/${eventId}/approve`, { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** VEYA דוחה. הסיבה חובה ומוצגת לבעלי האירוע. */
export async function adminRejectPayout(
  eventId: number,
  reason: string,
): Promise<PayoutReviewRow> {
  const res = await apiFetch(`/admin/payout/${eventId}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/**
 * פותח מחדש חשבון מאושר, כדי שבעלי האירוע יוכלו לתקן ולהגיש שוב.
 *
 * **הדרך היחידה לבטל את נעילת החשבון.** מרגע האישור אין לבעלי האירוע
 * שום מסלול לשנות את הפרטים, לא ב-UI ולא ב-API.
 */
export async function adminReopenPayout(eventId: number): Promise<PayoutReviewRow> {
  const res = await apiFetch(`/admin/payout/${eventId}/reopen`, { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/**
 * מסמן ידנית את תוצאת בדיקת ספק הסליקה.
 *
 * **כלי בדיקה, לא חלק מהתהליך.** אין ספק מחובר, והפונקציה אינה פונה לאף
 * גורם חיצוני ואינה מדמה אישור של ספק אמיתי. כשיחובר ספק, ה-adapter שלו
 * יכתוב את השדה בעצמו והנתיב הזה ייסגר.
 */
export async function adminSetPayoutProviderStatus(
  eventId: number,
  status: ReviewStatus,
  reason = '',
): Promise<PayoutReviewRow> {
  const res = await apiFetch(`/admin/payout/${eventId}/provider`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, reason }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** אישור ניהול החשבון, לצורך הבדיקה. אותו נימוק כמו ב-``fetchPayoutCertificate``. */
export async function adminFetchPayoutCertificate(eventId: number): Promise<Blob> {
  const res = await apiFetch(`/admin/payout/${eventId}/certificate`)
  if (!res.ok) throw await toError(res)
  return res.blob()
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
      | 'rsvp_send_time'
      | 'thank_you_send_time'
      | 'groom_parents_line'
      | 'bride_parents_line'
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

// ---- נוהל דחייה ----
//
// הבקשה עצמה **אינה מקבלת גוף** — אין תאריך חדש ואין מועד סגירת רשימה.
// בשלב שבו זוג מבקש לדחות אירוע הוא לרוב עדיין לא יודע מתי הוא יתקיים.

export async function getPostponement(): Promise<Postponement> {
  const res = await apiFetch('/postpone')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function requestPostponement(): Promise<Postponement> {
  const res = await apiFetch('/postpone', { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** סוגר את הנוהל ופותח מחזור אישורי-הגעה חדש. התשובות הקודמות עוברות לארכיון. */
export async function completePostponement(): Promise<Postponement> {
  const res = await apiFetch('/postpone/complete', { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminListPostponements(
  scope: 'pending' | 'approved' = 'pending',
): Promise<PostponementReviewRow[]> {
  const res = await apiFetch(`/admin/postpone?scope=${scope}`)
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminApprovePostponement(
  eventId: number,
): Promise<PostponementReviewRow> {
  const res = await apiFetch(`/admin/postpone/${eventId}/approve`, { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminRejectPostponement(
  eventId: number,
  reason: string,
): Promise<PostponementReviewRow> {
  const res = await apiFetch(`/admin/postpone/${eventId}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/**
 * שליחה ידנית של הודעה לקהל נבחר (היום: "אירוע נדחה").
 *
 * ההזמנה **אינה** עוברת כאן — היא נשלחת דרך ``activateRsvpTrack``, שאוכף
 * "הזמנה אחת בלבד לכל אורח".
 */
export async function sendMessageToGuests(
  messageType: MessageType,
  opts: { audience?: TargetAudience; guestIds?: number[] } = {},
): Promise<ManualSendResult> {
  const res = await apiFetch(`/communication/sequence/${messageType}/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      audience: opts.audience ?? 'all',
      guest_ids: opts.guestIds ?? null,
    }),
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
  sketchTransform?: HallSketchTransform | null,
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
      sketch_transform: sketchTransform,
    }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

// שלב 1 של בניית אולם אוטומטית: שולח סקיצה (data URL) ל-AI Vision, מקבל
// רשימת אלמנטים מוצעים. תצוגה מקדימה בלבד — שום דבר לא נשמר בשרת כאן.
export async function analyzeHallSketch(imageDataUrl: string): Promise<DetectedHallElement[]> {
  const res = await apiFetch('/hall/sketch/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image: imageDataUrl }),
  })
  if (!res.ok) throw await toError(res)
  const data = await res.json()
  return data.elements as DetectedHallElement[]
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

/**
 * מבקש מהשרת את פירוט התשלום עבור סכום מתנה נתון.
 *
 * **כל חשבון הכסף נעשה בשרת.** העמוד לא מחשב עמלה ולא סכום כולל — הוא
 * שולח את הסכום שהאורח הקליד ומציג את מה שחזר. כך המספר שמוצג על המסך
 * הוא בדיוק המספר שהשרת יחייב בו, ואין דרך שהם ייפרדו.
 */
export async function fetchGiftQuote(
  token: string,
  giftAmountAgorot: number,
): Promise<GiftQuote> {
  const res = await publicFetch(`/confirm/${encodeURIComponent(token)}/gift/quote`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ gift_amount_agorot: giftAmountAgorot }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/**
 * תשלום **מדומה** — אין כאן סליקה, ספק תשלומים או תנועת כסף.
 *
 * שולח רק את הסכום, השם והברכה. עמלה וסכום כולל אינם נשלחים בכלל — השרת
 * מחשב אותם מחדש (ראו backend/app/routers/confirm.py::gift_checkout).
 */
export async function submitGiftCheckout(
  token: string,
  payload: {
    gift_amount_agorot: number
    giver_name: string
    blessing?: string | null
    simulate?: 'success' | 'failure'
    /** מונע חיוב כפול בלחיצה כפולה או בניסיון חוזר של הרשת. */
    idempotency_key?: string
  },
): Promise<GiftCheckoutResult> {
  const res = await publicFetch(`/confirm/${encodeURIComponent(token)}/gift/checkout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/**
 * הכתובת המלאה לקובץ היומן (ICS) של המוזמן.
 *
 * השרת מחזיר נתיב יחסי בלבד, כי הוא יושב בדומיין אחר מהאתר ורק כאן ידועה
 * כתובת ה-API (``VITE_API_URL``) — בדיוק כמו ב-``mediaUrl``. חשוב שזו תהיה
 * **כתובת אמיתית ולא blob**: כך אייפון פותח ישירות את מסך "הוספה ליומן"
 * של אפל, במקום להוריד קובץ שהמוזמן לא יודע מה לעשות איתו.
 */
export function confirmIcsUrl(path: string): string {
  if (!path) return ''
  return API_URL.replace(/\/$/, '') + (path.startsWith('/') ? path : '/' + path)
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

/** יומן המשימות של אישורי-ההגעה — לוח הזמנים היומי שנבנה לאחור ממועד סגירת הרשימה. */
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

/** סיכום מצב ההודעות שנשלחו למוזמנים (נמסרו/נקראו/נכשלו/...) — נפרד מ-RSVP. */
export async function getMessageStatus(): Promise<MessageStatusSummary> {
  const res = await apiFetch('/automation/message-status')
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** סטטוס ההודעות לפי סוג הודעה נבחר (הזמנה/תזכורת.../תודה) — לכרטיס
 * "מעקב אחרי המוזמנים" כשבוחרים "מעקב אחר: X". כולל רשימת מוזמנים מלאה. */
export async function getMessageStatusByType(messageType: string): Promise<MessageTypeStatus> {
  const res = await apiFetch(`/automation/message-status/${messageType}`)
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

export async function getMessageOptions(messageType: string): Promise<MessageDefaultOption[]> {
  const res = await apiFetch(`/communication/sequence/${messageType}/options`)
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

export async function adminListMessageDefaultOptions(
  eventType: string,
  messageType?: string,
): Promise<MessageDefaultOption[]> {
  const params = new URLSearchParams({ event_type: eventType })
  if (messageType) params.set('message_type', messageType)
  const res = await apiFetch(`/admin/message-default-options?${params.toString()}`)
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminCreateMessageDefaultOption(
  data: MessageDefaultOptionCreate,
): Promise<MessageDefaultOption> {
  const res = await apiFetch('/admin/message-default-options', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminUpdateMessageDefaultOption(
  optionId: number,
  data: Partial<MessageDefaultOptionInput>,
): Promise<MessageDefaultOption> {
  const res = await apiFetch(`/admin/message-default-options/${optionId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function adminDeleteMessageDefaultOption(optionId: number): Promise<void> {
  const res = await apiFetch(`/admin/message-default-options/${optionId}`, { method: 'DELETE' })
  if (!res.ok) throw await toError(res)
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

// ---- Call Center (אדמין) ----
// כל הנתונים כאן נגזרים ב-Backend מ-Workflow אישורי ההגעה הקיים — אין כאן
// לוח זמנים או סטטוסים נפרדים (ראו backend/app/call_center.py).

/** מסך ה-Call Center הראשי: מונים + האירועים שיש בהם שיחות בטווח הנבחר.
 * ברירת המחדל ``scope='today'`` — רק שיחות שצריך לבצע היום. */
export async function callCenterOverview(
  scope: CallCenterScope = 'today',
): Promise<CallCenterOverview> {
  const res = await apiFetch(`/admin/call-center?scope=${scope}`)
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** תור המוזמנים בטווח הנבחר, עם חיפוש/סינון/דפדוף. החיפוש פועל רק בתוך הטווח. */
export async function callCenterQueue(params: {
  scope?: CallCenterScope
  eventId?: number | null
  q?: string
  status?: string
  roundNumber?: number | null
  limit?: number
  offset?: number
} = {}): Promise<CallCenterQueue> {
  const qs = new URLSearchParams()
  qs.set('scope', params.scope ?? 'today')
  if (params.eventId != null) qs.set('event_id', String(params.eventId))
  if (params.q) qs.set('q', params.q)
  if (params.status) qs.set('status', params.status)
  if (params.roundNumber != null) qs.set('round_number', String(params.roundNumber))
  if (params.limit != null) qs.set('limit', String(params.limit))
  if (params.offset != null) qs.set('offset', String(params.offset))
  const res = await apiFetch(`/admin/call-center/queue?${qs.toString()}`)
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** כרטיס ביצוע שיחה: פרטי האירוע, פרטי המוזמן ויומן הפעילות המלא. */
export async function callCenterGuest(guestId: number): Promise<CallCenterGuestDetail> {
  const res = await apiFetch(`/admin/call-center/guests/${guestId}`)
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** תיעוד תוצאת שיחה (ועדכון אישור ההגעה כשצריך). */
export async function callCenterRecordOutcome(
  guestId: number,
  data: CallOutcomeRequest,
): Promise<CallOutcomeResult> {
  const res = await apiFetch(`/admin/call-center/guests/${guestId}/outcome`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** התראות איכות-דאטה על מוזמני האירוע (כרגע: מספר טלפון שדווח כשגוי). */
export async function guestDataAlerts(): Promise<GuestDataAlerts> {
  const res = await apiFetch('/guests/data-alerts')
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- אימות כתובת המייל ----------------------------------------------------

/** שולח מחדש את מייל האימות למשתמש המחובר. */
export async function resendVerificationEmail(): Promise<{ sent: boolean }> {
  const res = await apiFetch('/auth/verify-email/resend', { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** מתקן כתובת מייל שגויה **לפני** שאומתה, ושולח אליה אימות חדש. */
export async function changeUnverifiedEmail(email: string): Promise<User> {
  const res = await apiFetch('/auth/verify-email/change', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** מאמת את כתובת המייל לפי הטוקן מהקישור, ומחזיר טוקן התחברות.
 * ציבורי בכוונה: הקישור עשוי להיפתח בדפדפן/מכשיר שבו המשתמש לא מחובר. */
export async function confirmEmailVerification(token: string): Promise<TokenResponse> {
  const res = await publicFetch('/auth/verify-email/confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** מאמת את כתובת המייל לפי קוד 6 הספרות שהוקלד במסך האימות. המשתמש כבר
 * מחובר בשלב הזה (הטוקן מתקבל מיד בהרשמה) — לכן נשלח עם כותרות אימות. */
export async function verifyEmailCode(code: string): Promise<User> {
  const res = await apiFetch('/auth/verify-email/verify-code', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ---- ניהול משותף של האירוע ------------------------------------------------

/** כל מה שמסך "החשבון שלי" צריך, בקריאה אחת. */
export async function getAccountOverview(): Promise<AccountOverview> {
  const res = await apiFetch('/partner/overview')
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** שולח לבן/בת הזוג הזמנה לנהל יחד את האירוע. שליחה חוזרת מבטלת קישור קודם. */
export async function invitePartner(email: string): Promise<PartnerInvite> {
  const res = await apiFetch('/partner/invite', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** מבטל את ההזמנה הפתוחה — הקישור שנשלח מפסיק לעבוד. */
export async function cancelPartnerInvite(): Promise<void> {
  const res = await apiFetch('/partner/invite', { method: 'DELETE' })
  if (!res.ok) throw await toError(res)
}

/** מה מצב ההזמנה — עובד גם כשלא מחוברים (משמש את דף ההצטרפות). */
export async function previewInvitation(token: string): Promise<InvitationPreview> {
  // מחובר → נשלח טוקן ונקבל מצב מדויק (ready/wrong_account); לא מחובר →
  // publicFetch, והשרת יחזיר needs_login. אותו endpoint לשני המקרים.
  const path = `/partner/invitations/${encodeURIComponent(token)}`
  const res = getToken() ? await apiFetch(path) : await publicFetch(path)
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** מצרף את המשתמש המחובר לאירוע הקיים כמנהל/ת שווה. */
export async function acceptInvitation(token: string): Promise<InvitationPreview> {
  const res = await apiFetch(
    `/partner/invitations/${encodeURIComponent(token)}/accept`,
    { method: 'POST' },
  )
  if (!res.ok) throw await toError(res)
  return res.json()
}

// ════════════════════════════════════════════════════════════════════════
//  כספי האירוע
// ════════════════════════════════════════════════════════════════════════
//
// כל הנתיבים כאן פתוחים **לבעלי האירוע ולבן/בת הזוג בלבד** — לא למפיק
// ולא לאולם. זה נאכף בשרת (``EventAccess(owner_only=True)``) וב-Postgres
// (``rls/16_finance_rls.sql``); כאן זה רק מתועד.
//
// **אף פונקציה כאן לא שולחת סכום מחושב.** המסך שולח מה שהזוג הקליד
// ומקבל בחזרה מספרים מוכנים להצגה — אותו כלל שכבר נאכף במתנות.

/** התמונה הכספית המלאה — הוצאות, הכנסות והשורה התחתונה, בקריאה אחת. */
export async function getFinance(): Promise<FinanceSummary> {
  const res = await apiFetch('/finance')
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** קטלוג ההוצאות המותאם לסוג האירוע. מוגש מהשרת ולא משוכפל כאן. */
export async function getExpenseCategories(): Promise<ExpenseCategory[]> {
  const res = await apiFetch('/finance/categories')
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function createExpense(input: ExpenseInput): Promise<Expense> {
  const res = await apiFetch('/finance/expenses', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function updateExpense(id: number, input: ExpenseInput): Promise<Expense> {
  const res = await apiFetch(`/finance/expenses/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function deleteExpense(id: number): Promise<void> {
  const res = await apiFetch(`/finance/expenses/${id}`, { method: 'DELETE' })
  if (!res.ok) throw await toError(res)
}

/** מסך ספירת המתנות — מעטפות ואשראי יחד, כולל מצב השער והמספר הבא. */
export async function getGiftCounting(): Promise<GiftCounting> {
  const res = await apiFetch('/finance/gifts')
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** מצב המתנה לכל מוזמן — **כולל מי שעדיין לא נספר**. */
export async function getGiftsByGuest(): Promise<GuestGiftRow[]> {
  const res = await apiFetch('/finance/gifts/by-guest')
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** שמירת מעטפה. התשובה כוללת את מספר המעטפה הבאה — מהשרת, לא מהדפדפן. */
export async function createEnvelope(input: EnvelopeInput): Promise<EnvelopeCreated> {
  const res = await apiFetch('/finance/envelopes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** עריכת מעטפה — כולל שיוך מאוחר של מעטפה שלא זוהתה.
 *  ``envelope_number`` אינו משתנה: הוא העוגן שבו מזהים את המעטפה בערימה. */
export async function updateEnvelope(id: number, input: EnvelopeInput): Promise<GiftEntry> {
  const res = await apiFetch(`/finance/envelopes/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  if (!res.ok) throw await toError(res)
  return res.json()
}

export async function deleteEnvelope(id: number): Promise<void> {
  const res = await apiFetch(`/finance/envelopes/${id}`, { method: 'DELETE' })
  if (!res.ok) throw await toError(res)
}

/** הדוח הסופי — שורה לכל מוזמן + כל הסיכומים.
 *
 *  נתיב נפרד מ-``/finance`` בכוונה: הוא מכיל מאות שורות ונדרש פעם אחת,
 *  בסוף. גרירה שלו בכל טעינת מסך הייתה מאטה את המסך בשביל נתון שאיש
 *  לא מסתכל עליו רוב הזמן. */
export async function getFinanceReport(): Promise<FinanceReport> {
  const res = await apiFetch('/finance/report')
  if (!res.ok) throw await toError(res)
  return res.json()
}

/** יוצר את תקציב הפתיחה של סוג האירוע — רק שורות ``is_default``.
 *
 *  **לא דורס**: אירוע שכבר יש בו הוצאה מקבל ``applied: false`` ולא
 *  משתנה כלל. התבנית היא נקודת פתיחה, לא איפוס. */
export async function applyExpenseTemplate(): Promise<TemplateApplyResult> {
  const res = await apiFetch('/finance/template/apply', { method: 'POST' })
  if (!res.ok) throw await toError(res)
  return res.json()
}
