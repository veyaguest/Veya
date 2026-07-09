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
