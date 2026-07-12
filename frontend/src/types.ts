export type Side = 'groom' | 'bride' | 'shared'
// קבוצה יכולה להיות אחת מהמוכרות, או קבוצה מותאמת אישית (טקסט חופשי בעברית)
export type KnownGroupType =
  | 'close_family'
  | 'extended_family'
  | 'friends'
  | 'work'
  | 'other'
export type GroupType = KnownGroupType | (string & {})
export type RsvpStatus = 'pending' | 'confirmed' | 'declined' | 'maybe'

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
  guest_token: string | null
  confirmed_count: number | null
  guest_note: string | null
  created_at: string
}

/**
 * כמה מקומות המוזמן באמת תופס — הבסיס לספירת אנשים בכל המערכת.
 * ביטל → 0, אישר → הכמות שהזין, אחרת (ממתין/אולי) → כמה שהוזמנו.
 */
export function effectiveSeats(g: {
  rsvp_status: RsvpStatus
  party_size: number
  confirmed_count: number | null
}): number {
  if (g.rsvp_status === 'declined') return 0
  if (g.rsvp_status === 'confirmed' && g.confirmed_count != null)
    return g.confirmed_count
  return g.party_size
}

// ---- דף אישור הגעה ציבורי (קישור אישי) ----

export interface ConfirmEventInfo {
  groom_name: string
  bride_name: string
  venue_name: string
  event_date: string
  event_time: string
  invite_image: string | null
}

export interface ConfirmGuestPublic {
  full_name: string
  party_size: number
  rsvp_status: string
  confirmed_count: number | null
  guest_note: string | null
  event: ConfirmEventInfo
}

export interface ConfirmSubmit {
  coming: boolean
  maybe?: boolean
  count?: number | null
  note?: string | null
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

export const GROUP_LABELS: Record<KnownGroupType, string> = {
  close_family: 'משפחה קרובה',
  extended_family: 'משפחה רחוקה',
  friends: 'חברים',
  work: 'עבודה',
  other: 'אחר',
}

// תווית לתצוגה: קבוצה מוכרת → שם בעברית; קבוצה מותאמת → הטקסט עצמו.
export function groupLabel(group: string): string {
  return (GROUP_LABELS as Record<string, string>)[group] ?? group
}

export const RSVP_LABELS: Record<RsvpStatus, string> = {
  pending: 'ממתין',
  confirmed: 'מגיע',
  declined: 'לא מגיע',
  maybe: 'אולי',
}

// ---- תבנית הודעת הזמנה (שלב RSVP 2) ----

export interface TemplatePlaceholder {
  key: string
  desc: string
}

export interface MessageTemplate {
  template: string
  is_custom: boolean
  default_template: string
  placeholders: TemplatePlaceholder[]
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
  maybe: number
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
  event_date: string
  event_time: string
  invite_image: string | null
}

export interface AuditLogRow {
  id: number
  action: string
  detail: string
  ip: string | null
  created_at: string
}

// ---- מפת אולם (שלב 7) ----

export interface HallGuest {
  id: number
  full_name: string
  party_size: number // כמה הוזמנו
  seats: number // כמה תופסים בפועל אחרי אישור (0 אם ביטלו)
  side: Side
  group_type: GroupType
  rsvp_status: RsvpStatus
}

// סוג שולחן: עגול | מרובע | מלבני | "אבירים" (שולחן ארוך, 24 מקומות כולל קצוות)
export type TableType = 'round' | 'square' | 'rectangle' | 'knights'

export interface HallTable {
  table_number: number
  x: number
  y: number
  seats_used: number
  guests: HallGuest[]
  table_type: TableType
  capacity: number
  rotation: number
  name: string
  color: string
  notes: string
  locked: boolean
}

// רק האלמנטים הגלויים בסרגל הכלים כרגע. שאר הסוגים (head_table, gift_table,
// restroom, stage) עדיין נתמכים בקוד לתאימות לאחור — רק הוסתרו מהממשק.
export type HallElementType =
  | 'head_table'
  | 'dance_floor'
  | 'bar'
  | 'stage'
  | 'entrance'
  | 'dj'
  | 'gift_table'
  | 'restroom'

// צורה גאומטרית של אלמנט (רלוונטי לרחבת ריקודים / בר / DJ)
export type ElementShape = 'rectangle' | 'square' | 'circle' | 'ellipse'

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
  shape: ElementShape
  color: string
}

export interface HallState {
  seats_per_table: number
  tables: HallTable[]
  unassigned: HallGuest[]
  elements: HallElement[]
  warnings: string[]
  sketch: string | null
}

export interface HallTableSave {
  table_number: number
  x: number
  y: number
  guest_ids: number[]
  table_type: TableType
  capacity: number
  rotation: number
  name: string
  color: string
  notes: string
  locked: boolean
}

// ---- משתמשים והתחברות (שלב 8) ----

export interface User {
  id: number
  email: string
  display_name: string
  is_admin: boolean
  // couple (זוג) / planner (מפיק) / venue (אולם) — ציר נפרד מ-is_admin.
  account_type: string
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
  account_type: string
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

export interface AdminAccountCreateResult {
  user_id: number
  email: string
  account_type: string
  temporary_password: string
}

// ---- שיתוף גישה לאירוע (מפיק/אולם) ----

export const PLANNER_PERMISSIONS = [
  'view_guests',
  'edit_guests',
  'manage_seating',
  'send_messages',
  'view_reports',
] as const

export const VENUE_PERMISSIONS = [
  'view_event',
  'view_seating',
  'edit_seating',
  'manage_venue_data',
] as const

export const PERMISSION_LABELS: Record<string, string> = {
  view_guests: 'צפייה במוזמנים',
  edit_guests: 'עריכת מוזמנים',
  manage_seating: 'ניהול שיבוץ',
  send_messages: 'שליחת הודעות',
  view_reports: 'צפייה בדוחות',
  view_event: 'צפייה באירוע',
  view_seating: 'צפייה בשיבוץ',
  edit_seating: 'עריכת שיבוץ',
  manage_venue_data: 'ניהול נתוני אולם',
}

export interface EventMemberRead {
  id: number
  user_id: number
  email: string
  display_name: string
  role: string
  permissions: string[]
  status: string
}
