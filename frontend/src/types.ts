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
