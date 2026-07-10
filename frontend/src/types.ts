export type Side = 'groom' | 'bride' | 'shared'
export type GroupType =
  | 'close_family'
  | 'extended_family'
  | 'friends'
  | 'work'
  | 'other'
export type RsvpStatus = 'pending' | 'confirmed' | 'declined'

export interface Guest {
  id: number
  full_name: string
  phone: string
  side: Side
  group_type: GroupType
  party_size: number
  notes_raw: string | null
  rsvp_status: RsvpStatus
  table_number: number | null
  created_at: string
}

export interface GuestCreate {
  full_name: string
  phone: string
  side: Side
  group_type: GroupType
  party_size: number
  notes_raw?: string
}

// תוויות בעברית לתצוגה
export const SIDE_LABELS: Record<Side, string> = {
  groom: 'חתן',
  bride: 'כלה',
  shared: 'משותף',
}

export const GROUP_LABELS: Record<GroupType, string> = {
  close_family: 'משפחה קרובה',
  extended_family: 'משפחה רחוקה',
  friends: 'חברים',
  work: 'עבודה',
  other: 'אחר',
}

export const RSVP_LABELS: Record<RsvpStatus, string> = {
  pending: 'ממתין',
  confirmed: 'מגיע',
  declined: 'לא מגיע',
}

export interface ImportPreviewRow {
  row_number: number
  full_name: string
  phone: string
  side: Side
  group_type: GroupType
  party_size: number
  notes_raw: string | null
  valid: boolean
  errors: string[]
}

export interface ImportPreview {
  detected_columns: Record<string, string | null>
  rows: ImportPreviewRow[]
  total: number
  valid_count: number
  invalid_count: number
}

// ---- שיבוץ הושבה (שלב 3) ----

export interface SeatingParty {
  id: number
  full_name: string
  party_size: number
  side: Side
  group_type: GroupType
}

export interface SeatingTable {
  table_number: number
  seats_used: number
  capacity: number
  parties: SeatingParty[]
}

export interface SeatingResult {
  tables: SeatingTable[]
  total_people: number
  num_tables: number
  seats_per_table: number
  score: number
  hard_ok: boolean
  unseated: number[]
  persisted: boolean
}

export interface SeatingRequest {
  seats_per_table: number
  num_tables?: number
  only_confirmed?: boolean
  persist?: boolean
}

// ---- פרסור הערות + הבהרות (שלב 4) ----

export interface ClarificationCandidate {
  id: number
  full_name: string
}

export interface Clarification {
  id: number
  source_guest_id: number
  source_guest_name: string
  relation_type: 'avoid' | 'together'
  target_text: string
  candidates: ClarificationCandidate[]
}

export interface AnalyzeResult {
  guests_analyzed: number
  relations_found: number
  resolved: number
  ambiguous: number
  unresolved: number
  pending_clarifications: number
}

// ---- WhatsApp / RSVP (שלב 5) ----

export interface RsvpSummary {
  total_guests: number
  confirmed: number
  declined: number
  pending: number
  invitations_sent: number
  mode: string
}

export interface SendInvitationsResult {
  mode: string
  sent: number
  failed: number
  skipped: number
  detail: string | null
}

export interface Message {
  id: number
  guest_id: number | null
  direction: 'outbound' | 'inbound'
  kind: string
  body: string
  status: string
  provider: string
  created_at: string
}

// ---- דשבורד + אירוע (שלב 6) ----

export interface DashboardStats {
  total_guests: number
  total_people: number
  confirmed_people: number
  confirmed: number
  declined: number
  pending: number
  response_rate: number
  invitations_sent: number
  by_side: Record<Side, number>
  by_group: Record<GroupType, number>
  tables_assigned: number
  seated_guests: number
  pending_clarifications: number
  groom_name: string
  bride_name: string
  venue_name: string
}

export interface EventDetails {
  id: number
  groom_name: string
  bride_name: string
  venue_name: string
}

// ---- מפת אולם (שלב 7) ----

export interface HallGuest {
  id: number
  full_name: string
  party_size: number
  side: Side
  group_type: GroupType
  rsvp_status: RsvpStatus
}

export interface HallTable {
  table_number: number
  x: number
  y: number
  seats_used: number
  guests: HallGuest[]
}

export type HallElementType =
  | 'head_table'
  | 'dance_floor'
  | 'bar'
  | 'stage'
  | 'entrance'
  | 'dj'

export interface HallElement {
  id: string
  type: HallElementType
  x: number
  y: number
  width: number
  height: number
  rotation: number
  locked: boolean
  label: string
}

export interface HallState {
  seats_per_table: number
  tables: HallTable[]
  unassigned: HallGuest[]
  elements: HallElement[]
  warnings: string[]
}

export interface HallTableSave {
  table_number: number
  x: number
  y: number
  guest_ids: number[]
}

// ---- משתמשים והתחברות (שלב 8) ----

export interface User {
  id: number
  email: string
  display_name: string
  is_admin: boolean
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export interface EventSummary {
  id: number
  groom_name: string
  bride_name: string
  venue_name: string
}

// ---- פאנל אדמין ----

export interface AdminUserRow {
  id: number
  email: string
  display_name: string
  is_admin: boolean
  events_count: number
  guests_count: number
  created_at: string
}

export interface AdminEventRow {
  id: number
  groom_name: string
  bride_name: string
  venue_name: string
  owner_id: number | null
  owner_email: string | null
  guests_count: number
}
