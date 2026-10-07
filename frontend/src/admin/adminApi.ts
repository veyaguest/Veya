/**
 * API של מרכז השליטה (Admin). כל נתיב מוגן בשרת לפי דרגת האדמין —
 * ההסתרה ב-UI היא נוחות בלבד, לא אבטחה.
 */
import { apiFetch, toError } from '../api'

async function getJson<T>(path: string): Promise<T> {
  const res = await apiFetch(path)
  if (!res.ok) throw await toError(res)
  return res.json()
}

async function sendJson<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await apiFetch(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) throw await toError(res)
  if (res.status === 204) return undefined as T
  return res.json()
}

export const adminHttp = { getJson, sendJson }

export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === '' || v === false) continue
    p.set(k, String(v))
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

// ── מי אני ─────────────────────────────────────────────────────────────
export type AdminRole = 'super_admin' | 'admin' | 'support'

export interface AdminMe {
  id: number
  email: string
  display_name: string
  role: AdminRole
  role_label: string
  permissions: string[]
}

export const fetchAdminMe = () => getJson<AdminMe>('/admin/me')

// ── דשבורד ─────────────────────────────────────────────────────────────
export type ModuleState = 'active' | 'beta' | 'off' | 'mock' | 'issue'

export interface AttentionItem {
  key: string
  severity: 'critical' | 'warning' | 'info'
  title: string
  detail: string
  count: number
  page: string
  event_ids: number[]
}

export interface ModuleStatus {
  key: string
  label: string
  status: ModuleState
  detail: string
  page: string
}

export interface AdminOverview {
  today: string
  pulse: {
    active_users: number
    active_users_days: number
    upcoming_events: number
    new_events: number
    new_events_days: number
    events_needing_attention: number
    pending_requests: number
    warnings: number
  }
  attention: AttentionItem[]
  modules: ModuleStatus[]
}

export const fetchAdminOverview = () => getJson<AdminOverview>('/admin/overview')

// ── חיפוש גלובלי ───────────────────────────────────────────────────────
export interface SearchItem {
  id: number
  event_id?: number
  title: string
  subtitle: string
}
export interface SearchGroup {
  type: 'user' | 'event' | 'guest' | 'venue' | 'audit' | 'feature' | 'plan'
  label: string
  items: SearchItem[]
}
export const adminSearch = (q: string) =>
  getJson<{ q: string; groups: SearchGroup[] }>(`/admin/search${qs({ q })}`)

// ── יומן פעילות ────────────────────────────────────────────────────────
export interface AuditChange {
  field: string
  label: string
  before: string
  after: string
}
export interface AuditEntry {
  id: number
  actor_id: number | null
  actor_label: string
  actor_role: string
  domain: string
  domain_label: string
  action: string
  target_type: string
  target_id: string
  target_label: string
  summary: string
  changes: AuditChange[]
  reason: string
  event_id: number | null
  created_at: string | null
}
export interface AuditPage {
  items: AuditEntry[]
  total: number
  limit: number
  offset: number
  domains: Record<string, string>
  actors: { id: number; label: string }[]
}
export interface AuditQuery {
  q?: string
  domain?: string
  actor_id?: number | null
  date_from?: string
  date_to?: string
  target_type?: string
  target_id?: string
  event_id?: number
  limit?: number
  offset?: number
}
export const fetchAudit = (query: AuditQuery) =>
  getJson<AuditPage>(`/admin/audit${qs({ ...query })}`)

// ── הגדרות Admin ───────────────────────────────────────────────────────
export interface AdminAccount {
  id: number
  email: string
  display_name: string
  role: AdminRole | ''
  role_label: string
  disabled: boolean
  is_self: boolean
  created_at: string | null
}
export const fetchAdmins = () => getJson<AdminAccount[]>('/admin/admins')
export const setAdminRole = (userId: number, role: AdminRole | null, reason: string) =>
  sendJson<AdminAccount>(`/admin/admins/${userId}/role`, 'PUT', { role, reason })

// ── פניות תמיכה (עזרה, שלב 7) ───────────────────────────────────────────
export type SupportStatus = 'new' | 'in_progress' | 'resolved'

export interface SupportPerson {
  id: number
  name: string
  email: string
}

export interface SupportRequestRow {
  id: number
  status: SupportStatus
  urgency: 'normal' | 'high'
  about: string
  created_at: string | null
  updated_at: string | null
  user: SupportPerson | null
  event: { id: number; title: string; event_date: string | null; days_to_event: number | null; owner_id: number | null } | null
}

export interface SupportRequestDetail extends SupportRequestRow {
  message: string
  context: {
    event_type?: string
    role?: string
    screen?: string | null
    topic_id?: string | null
    tree_id?: string | null
    outcome?: string | null
    tour_flow?: string | null
    days_to_event?: number | null
    platform?: string
    recent_errors?: { method: string; path: string; status: number; message?: string }[]
    facts?: Record<string, boolean | number | string | null>
  }
  handled_by: SupportPerson | null
  /** תשובות הצוות שנשלחו מתוך המסך. לא קשורות לסטטוס ("נענתה" ≠ "טופלה"). */
  replies: SupportReply[]
}

export interface SupportReply {
  id: number
  /** sent = יצא באמת · mock = נשמר, אין חיבור למייל בסביבה הזו · failed · sending */
  status: 'sent' | 'mock' | 'failed' | 'sending'
  body: string
  created_at: string | null
  sent_at: string | null
  admin: SupportPerson | null
}

export const fetchSupportRequests = (status: SupportStatus | 'open' | 'all' = 'open') =>
  getJson<SupportRequestRow[]>(`/admin/support/requests?status=${status}`)

export const fetchSupportRequest = (id: number) =>
  getJson<SupportRequestDetail>(`/admin/support/requests/${id}`)

export const setSupportStatus = (id: number, status: SupportStatus) =>
  sendJson<SupportRequestDetail>(`/admin/support/requests/${id}/status`, 'POST', { status })

/** "השב לפונה". הנמען נקבע בשרת מהפנייה — אין כאן שדה נמען. ``clientToken``
 *  אחד לכל פתיחה של חלון המענה: אותו מזהה = אותה תשובה (לחיצה כפולה לא שולחת פעמיים). */
export const sendSupportReply = (id: number, body: string, clientToken: string) =>
  sendJson<SupportRequestDetail>(`/admin/support/requests/${id}/replies`, 'POST', { body, client_token: clientToken })

// ── תובנות עזרה (שלב 8) — ספירות בלבד, בלי זהות ────────────────────────
export interface HelpInsights {
  days: 7 | 30
  sessions: number
  events: number
  opened_by_screen: { screen: string; count: number }[]
  entries: { entry: string; count: number }[]
  topics: ({ topic_id: string } & Record<string, number | string>)[]
  tours: ({ flow_id: string } & Record<string, number | string>)[]
  trees: ({ tree_id: string } & Record<string, number | string>)[]
  no_results: { screen: string; count: number }[]
  escalations: { started: number; submitted: number }
}

export const fetchHelpInsights = (days: 7 | 30) => getJson<HelpInsights>(`/admin/help/insights?days=${days}`)
