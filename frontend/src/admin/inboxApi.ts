/**
 * תיבת WhatsApp — API (``backend/app/routers/admin_inbox.py``).
 * משמש גם את מרכז השליטה וגם את מסך הטלפן. ההרשאות נאכפות בשרת.
 */
import { adminHttp, qs } from './adminApi'

export type InboxStatus = 'open' | 'answered' | 'closed'
export type InboxFilter = InboxStatus | 'all'
/** account = יש לו חשבון ב-VEYA · unknown = מספר לא מוכר · guest = מוזמן שלא זוהה בוודאות */
export type InboxSenderKind = 'account' | 'unknown' | 'guest'
/** יוצאת: pending · sent · delivered · read · failed · blocked · mock. נכנסת: received. */
export type InboxMessageStatus =
  | 'received' | 'pending' | 'sent' | 'delivered' | 'read' | 'failed' | 'blocked' | 'mock'

export interface InboxPerson {
  id: number
  name: string
}

export interface InboxThreadRow {
  id: number
  phone: string
  name: string
  sender_kind: InboxSenderKind
  status: InboxStatus
  assigned_to: InboxPerson | null
  last_message_at: string | null
  last_inbound_at: string | null
  preview: string
  preview_direction: 'inbound' | 'outbound' | ''
  window_open: boolean
  window_closes_at: string | null
  /** נשלחה הודעת חזרה (אחרי שהחלון נסגר) והפונה עוד לא ענה. */
  followup_waiting?: boolean
}

export interface InboxMessage {
  id: number
  direction: 'inbound' | 'outbound'
  /** נכנסת: text / image / … · יוצאת: reply / auto_reply / followup */
  kind: string
  body: string
  status: InboxMessageStatus
  failure_reason: string
  created_at: string | null
  sent_by: InboxPerson | null
}

export interface InboxThreadDetail extends InboxThreadRow {
  profile_name: string
  account: { id: number; name: string; email: string; events: { id: number; title: string }[] } | null
  messages: InboxMessage[]
  agents: InboxPerson[]
}

export interface InboxSummary {
  open: number
  mine: number
}

const BASE = '/admin/inbox'

export const fetchInboxSummary = () => adminHttp.getJson<InboxSummary>(`${BASE}/summary`)

export const fetchInboxThreads = (status: InboxFilter, mine: boolean) =>
  adminHttp.getJson<InboxThreadRow[]>(`${BASE}/threads${qs({ status, mine })}`)

export const fetchInboxThread = (id: number) => adminHttp.getJson<InboxThreadDetail>(`${BASE}/threads/${id}`)

/** הנמען נקבע בשרת מהשיחה. ``clientToken`` אחד לכל טיוטה: אותו מזהה = אותה תשובה. */
export const sendInboxReply = (id: number, body: string, clientToken: string) =>
  adminHttp.sendJson<InboxThreadDetail>(`${BASE}/threads/${id}/reply`, 'POST', { body, client_token: clientToken })

/** הודעת חזרה בתבנית מאושרת — רק אחרי שחלון 24 השעות נסגר. */
export const sendInboxFollowup = (id: number) =>
  adminHttp.sendJson<InboxThreadDetail>(`${BASE}/threads/${id}/followup`, 'POST', {})

export const setInboxStatus = (id: number, status: InboxStatus) =>
  adminHttp.sendJson<InboxThreadDetail>(`${BASE}/threads/${id}/status`, 'POST', { status })

export const assignInboxThread = (id: number, assigneeId: number | null) =>
  adminHttp.sendJson<InboxThreadDetail>(`${BASE}/threads/${id}/assign`, 'POST', { assignee_id: assigneeId })
