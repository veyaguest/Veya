/** API של מרכז השליטה בטלפנים (``/admin/call-ops``). */
import { callCenterRecordOutcome } from '../api'
import type { CallOutcomeRequest } from '../types'
import { adminHttp, qs } from './adminApi'

const { getJson, sendJson } = adminHttp

export type TaskGroup =
  | 'all'
  | 'pending'
  | 'handled'
  | 'not_handled'
  | 'unreachable'
  | 'followup'
  | 'overdue'
  | 'cancelled'

export type Tone = 'ok' | 'warn' | 'bad' | 'neutral' | 'info'

export interface TaskRow {
  task_id: number | null
  guest_id: number
  guest_name: string
  phone: string
  rsvp_status: string
  event_id: number
  event_label: string
  event_type: string
  event_date: string
  round_number: number
  total_rounds: number
  round_label: string
  reason: string
  reason_label: string
  planned_date: string
  due_date: string
  assignee_id: number | null
  assignee_name: string
  status: string
  status_label: string
  status_tone: Tone
  attempts: number
  last_attempt_at: string | null
  last_outcome: string
  handled_by_name: string
  closed_reason_label: string
  needs_attention: boolean
  round_state: string
}

export interface TaskPage {
  date: string
  mode: 'tasks' | 'preview'
  group: TaskGroup
  total: number
  limit: number
  offset: number
  items: TaskRow[]
}

export interface RoundSummary {
  event_id: number
  event_label: string
  event_date: string
  round_number: number
  total_rounds: number
  round_label: string
  state: string
  total: number
  handled: number
  pending: number
  no_answer: number
  callback: number
  complete: boolean
}

export interface CallerLoad {
  id: number
  name: string
  availability: string
  available: boolean
  tasks: number
  handled: number
  pending: number
  next_day: number
  capacity: number | null
  overloaded: boolean
}

export interface ExceptionItem {
  key: string
  severity: 'critical' | 'warning' | 'info'
  title: string
  detail: string
  count: number
  group: TaskGroup | ''
  assignee: string
  event_ids: number[]
}

export interface DaySummary {
  date: string
  today: string
  relation: 'past' | 'today' | 'tomorrow' | 'future'
  mode: 'tasks' | 'preview'
  counts: Record<
    | 'planned' | 'handled' | 'pending' | 'not_handled' | 'overdue' | 'unreachable'
    | 'followup' | 'cancelled' | 'assigned' | 'unassigned',
    number
  >
  rounds: RoundSummary[]
  callers: CallerLoad[]
  exceptions: ExceptionItem[]
}

export interface TimelineDay {
  date: string
  mode: 'tasks' | 'preview'
  planned: number
  handled: number
  pending: number
  unassigned: number
}

export interface HistoryItem {
  at: string | null
  channel: 'whatsapp' | 'phone' | 'task'
  title: string
  detail: string
  actor: string
  tone: Tone
}

export interface GuestCard {
  guest_id: number
  guest_name: string
  phone: string
  rsvp_status: string
  party_size: number
  confirmed_count: number | null
  event_id: number
  event_label: string
  event_date: string
  event_type: string
  current: TaskRow | null
  tasks: TaskRow[]
  history: HistoryItem[]
  next_action: string
}

export interface GuestHit {
  guest_id: number
  guest_name: string
  phone: string
  event_id: number
  event_label: string
  rsvp_status: string
  round_label: string
  status_label: string
  status_tone: Tone
  assignee_name: string
  last_attempt_at: string | null
}

export interface BulkResult {
  updated: number
  skipped: number
  message: string
}

export interface ProposalRow {
  task_id: number
  guest_name: string
  event_label: string
  assignee_id: number
  assignee_name: string
  why: string
}

export interface AutoAssignPreview {
  date: string
  proposals: ProposalRow[]
  by_caller: { id: number; name: string; count: number }[]
  unassignable: number
  note: string
}

export interface CallerRow {
  id: number
  email: string
  display_name: string
  phone: string
  disabled: boolean
  availability: 'active' | 'inactive' | 'vacation'
  availability_label: string
  available_today: boolean
  unavailable_from: string
  unavailable_until: string
  group_name: string
  daily_capacity: number | null
  note: string
  today: { tasks: number; handled: number; pending: number }
  tomorrow_tasks: number
  last_activity_at: string | null
  calls_total: number
  event_ids: number[]
}

export interface TaskQuery {
  date?: string
  group?: TaskGroup
  event_id?: number | null
  assignee?: string
  round?: number | null
  event_type?: string
  q?: string
  limit?: number
  offset?: number
}

export const callOps = {
  day: (date?: string) => getJson<DaySummary>(`/admin/call-ops/day${qs({ date })}`),
  tasks: (query: TaskQuery) => getJson<TaskPage>(`/admin/call-ops/tasks${qs({ ...query })}`),
  timeline: (start: string, days = 14) =>
    getJson<TimelineDay[]>(`/admin/call-ops/timeline${qs({ start, days })}`),
  guest: (guestId: number) => getJson<GuestCard>(`/admin/call-ops/guests/${guestId}`),
  search: (q: string) => getJson<GuestHit[]>(`/admin/call-ops/search${qs({ q })}`),
  assign: (taskIds: number[], assigneeId: number | null, reason = '') =>
    sendJson<BulkResult>('/admin/call-ops/tasks/assign', 'POST', {
      task_ids: taskIds, assignee_id: assigneeId, reason,
    }),
  autoPreview: (date: string, taskIds?: number[]) =>
    sendJson<AutoAssignPreview>('/admin/call-ops/tasks/auto-assign/preview', 'POST', {
      date, task_ids: taskIds && taskIds.length ? taskIds : null,
    }),
  autoApply: (date: string, assignments: { task_id: number; assignee_id: number }[]) =>
    sendJson<BulkResult>('/admin/call-ops/tasks/auto-assign/apply', 'POST', { date, assignments }),
  reschedule: (taskIds: number[], dueDate: string, reason = '') =>
    sendJson<BulkResult>('/admin/call-ops/tasks/reschedule', 'POST', {
      task_ids: taskIds, due_date: dueDate, reason,
    }),
  cancel: (taskIds: number[], reason: string) =>
    sendJson<BulkResult>('/admin/call-ops/tasks/cancel', 'POST', { task_ids: taskIds, reason }),
  reopen: (taskIds: number[], reason = '') =>
    sendJson<BulkResult>('/admin/call-ops/tasks/reopen', 'POST', { task_ids: taskIds, reason }),
  manual: (guestId: number, dueDate: string, note: string, assigneeId: number | null) =>
    sendJson<TaskRow>('/admin/call-ops/tasks/manual', 'POST', {
      guest_id: guestId, due_date: dueDate, note, assignee_id: assigneeId,
    }),
  round: (eventId: number, round: number, action: 'pause' | 'resume' | 'stop' | 'start', reason = '') =>
    sendJson<{ ok: boolean; state: string }>(
      `/admin/call-ops/rounds/${eventId}/${round}/${action}`, 'POST', { reason },
    ),
  callers: () => getJson<CallerRow[]>('/admin/call-ops/callers'),
  createCaller: (data: {
    display_name: string
    email: string
    phone: string
    group_name: string
    daily_capacity: number | null
  }) => sendJson<{ caller: CallerRow; temporary_password: string }>('/admin/call-ops/callers', 'POST', data),
  updateCaller: (id: number, data: Partial<Omit<CallerRow, 'id'>>) =>
    sendJson<CallerRow>(`/admin/call-ops/callers/${id}`, 'PATCH', data),
  recordOutcome: (guestId: number, data: CallOutcomeRequest) => callCenterRecordOutcome(guestId, data),
}

// ── תאריכים (שעון ישראל) ──────────────────────────────────────────────
export function israelToday(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Jerusalem' }).format(new Date())
}

export function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.split('-').map(Number)
  const dt = new Date(Date.UTC(y, m - 1, d + days))
  return dt.toISOString().slice(0, 10)
}

const WEEKDAYS = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת']

export function weekday(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number)
  return WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]
}
