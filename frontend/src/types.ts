export type Side = 'groom' | 'bride' | 'shared'
// קבוצה יכולה להיות אחת מהמוכרות, או קבוצה מותאמת אישית (טקסט חופשי בעברית)
export type KnownGroupType =
  | 'close_family'
  | 'extended_family'
  | 'friends'
  | 'work'
  | 'army'
  | 'studies'
  | 'childhood'
  | 'neighbors'
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
  is_child: boolean
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
  venue_address: string
  maps_link: string
  waze_link: string
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
  is_child?: boolean
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
  army: 'צבא',
  studies: 'מהלימודים',
  childhood: 'חברי ילדות',
  neighbors: 'שכנים',
  other: 'אחר',
}

// תווית לתצוגה: קבוצה מוכרת → שם בעברית; קבוצה מותאמת → הטקסט עצמו.
export function groupLabel(group: string): string {
  return (GROUP_LABELS as Record<string, string>)[group] ?? group
}

export const RSVP_LABELS: Record<RsvpStatus, string> = {
  pending: 'ממתין לתשובה',
  confirmed: 'מגיע',
  declined: 'לא מגיע',
  maybe: 'אולי',
}

// ---- תבנית הודעת הזמנה (שלב RSVP 2) ----

export interface TemplatePlaceholder {
  key: string
  // כינוי ידידותי בעברית ([שם אורח]) שהזוג רואה ומכניס במקום {{...}}.
  token: string
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
  // אזהרות רכות (לא חוסמות) — מגיע רק מייבוא הדבקת טקסט חופשי: "חסר טלפון",
  // "טלפון לא תקין", "כפילות". ריק/חסר בייבוא Excel/CSV הרגיל.
  warnings?: string[]
  // האם זוהתה כפילות (מול הרשימה המודבקת עצמה או מול מוזמני האירוע).
  duplicate?: boolean
}

export interface ImportPreview {
  detected_columns: Record<string, string | null>
  rows: ImportPreviewRow[]
  total: number
  valid_count: number
  invalid_count: number
}

// הצעת קבוצה חכמה: מקבץ מוזמנים בעלי אותו שם משפחה שאפשר לאחד לקבוצה.
export interface GroupSuggestion {
  surname: string
  group_name: string // "משפחת <שם>"
  count: number
  guest_ids: number[]
  sample_names: string[]
}

// קבוצה שבשימוש באירוע (עם מספר המוזמנים בה) — לתצוגת העדפות הקבוצה.
export interface GroupInUse {
  group_type: string
  count: number
}

// הערות/העדפות ברמת קבוצה + רשימת הקבוצות הפעילות.
export interface GroupNotes {
  notes: Record<string, string>
  groups: GroupInUse[]
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
  guests_with_notes: number
  group_notes_count: number
  groom_name: string
  bride_name: string
  venue_name: string
}

export interface EventDetails {
  id: number
  groom_name: string
  bride_name: string
  venue_name: string
  venue_address: string
  event_date: string
  event_time: string
  invite_image: string | null
  // כמה ימים לפני האירוע צריך למסור לאולם מספר סופי (1–10). null = טרם נבחר.
  venue_commit_days_before: number | null
  // האם הבחירה כבר ננעלה (בלתי-הפיכה מרגע שנקבעה).
  venue_commit_locked: boolean
}

export interface VenueSuggestion {
  name: string
  address: string
  maps_link: string
  waze_link: string
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
  is_child: boolean
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
  // זוגות אילוצים שכבר מחושבים היום מהערות חופשיות — לשימוש עוזר ההושבה
  // החכם בצד הלקוח (בדיקות מיידיות כולל בזמן גרירה, בלי קריאת רשת נוספת).
  forbidden_pairs: [number, number][]
  together_pairs: [number, number][]
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
  phone: string
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

// ---- לוח הבקרה של האדמין ----

export interface AdminDashboardEvent {
  id: number
  couple: string
  venue_name: string
  owner_email: string | null
  event_date: string
  guests_count: number
  days_until: number | null
}

export interface AdminDashboardPoint {
  label: string
  count: number
}

export interface AdminDashboardAlert {
  level: string
  text: string
}

export interface AdminDashboard {
  total_events: number
  upcoming_events: number
  total_users: number
  total_venues: number
  total_guests: number
  whatsapp_sent: number
  recent_events: AdminDashboardEvent[]
  signups: AdminDashboardPoint[]
  alerts: AdminDashboardAlert[]
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

// ---- מנוע אוטומציות אישורי הגעה (RSVP Automation) ----

export type TriggerType =
  | 'event_created'
  | 'invitation_sent'
  | 'no_response'
  | 'before_event_date'
  | 'guest_confirmed'

export type TargetGroup =
  | 'all'
  | 'pending'
  | 'confirmed'
  | 'declined'
  | 'maybe'
  | 'side_groom'
  | 'side_bride'
  | 'group'

export type TemplateKind =
  | 'invitation'
  | 'reminder'
  | 'pre_event'
  | 'thank_you'
  | 'custom'

// תוויות בעברית לתצוגה בממשק.
export const TRIGGER_LABELS: Record<TriggerType, string> = {
  event_created: 'לאחר יצירת האירוע',
  invitation_sent: 'לאחר שליחת ההזמנה',
  no_response: 'אם אין תגובה',
  before_event_date: 'לפני תאריך האירוע',
  guest_confirmed: 'לאחר אישור המוזמן',
}

export const TARGET_GROUP_LABELS: Record<TargetGroup, string> = {
  all: 'כל המוזמנים',
  pending: 'ממתינים לתשובה',
  confirmed: 'מאשרים',
  declined: 'מסרבים',
  maybe: "מסמנים 'אולי'",
  side_groom: 'צד החתן',
  side_bride: 'צד הכלה',
  group: 'קבוצה מסוימת',
}

export const TEMPLATE_KIND_LABELS: Record<TemplateKind, string> = {
  invitation: 'הזמנה',
  reminder: 'תזכורת',
  pre_event: 'לפני האירוע',
  thank_you: 'תודה',
  custom: 'כללי',
}

export interface AutomationTemplate {
  id: number
  name: string
  kind: string
  body: string
  created_at: string
}

export interface AutomationTemplateInput {
  name: string
  kind?: TemplateKind
  body?: string
}

export interface AutomationRule {
  id: number
  rule_name: string
  trigger_type: string
  delay_days: number
  target_group: string
  target_group_value: string
  template_id: number | null
  action_kind: string
  active: boolean
  created_at: string
}

export interface AutomationRuleInput {
  rule_name: string
  trigger_type?: TriggerType
  delay_days?: number
  target_group?: TargetGroup
  target_group_value?: string
  template_id?: number | null
  active?: boolean
}

export interface DueAction {
  rule_id: number
  rule_name: string
  trigger_type: string
  guest_id: number
  guest_name: string
  phone: string
  channel: string
  preview: string
}

export interface DueQueue {
  actions: DueAction[]
  mode: string
}

export interface RunDueResult {
  mode: string
  sent: number
  failed: number
  skipped: number
  detail: string | null
}

export interface TimelineEvent {
  kind: string
  direction: 'outbound' | 'inbound'
  channel: string
  text: string
  status: string
  created_at: string
}

export interface GuestTimeline {
  guest_id: number
  guest_name: string
  rsvp_status: RsvpStatus
  events: TimelineEvent[]
}

export interface SmartFollowUp {
  severity: 'info' | 'warn'
  text: string
}

export interface AutomationDashboard {
  total_guests: number
  invited: number
  confirmed: number
  declined: number
  maybe: number
  pending: number
  in_reminder_process: number
  days_to_event: number | null
  active_rules: number
  due_now: number
  recommendations: SmartFollowUp[]
}

// ---- ברירות המחדל הגלובליות של VEYA (ספריית תבניות + מסלול קבוע) ----

export type VeyaStage =
  | 'invitation'
  | 'first_reminder'
  | 'second_reminder'
  | 'thank_you'
  | 'before_event'

export interface VeyaTemplate {
  id: number
  stage: VeyaStage
  name: string
  body: string
  is_default: boolean
  active: boolean
  sort_order: number
  created_at: string
}

export interface VeyaTemplateInput {
  stage?: VeyaStage
  name?: string
  body?: string
  is_default?: boolean
  active?: boolean
  sort_order?: number
}

export interface VeyaWorkflowStep {
  id: number
  step_order: number
  name: string
  offset_days: number
  action_kind: 'send' | 'phone_followup'
  template_stage: string
  active: boolean
  created_at: string
}

export interface VeyaWorkflowStepInput {
  name?: string
  offset_days?: number
  action_kind?: 'send' | 'phone_followup'
  template_stage?: string
  active?: boolean
}

// ---- מסלול אישורי-ההגעה של האירוע (מסך הזוג) ----

export interface RsvpTrackPhoneRow {
  guest_id: number
  guest_name: string
  phone: string
  side: string
}

export interface RsvpTrackStepRow {
  rule_id: number
  name: string
  offset_days: number
  action_kind: 'send' | 'phone_followup'
  active: boolean
  done: number
}

export interface RsvpTrackStatus {
  active: boolean
  started_at: string | null
  mode: string
  total_guests: number
  invited: number
  confirmed: number
  declined: number
  maybe: number
  pending: number
  in_phone_followup: number
  phone_list: RsvpTrackPhoneRow[]
  steps: RsvpTrackStepRow[]
  due_now: number
}

export interface RsvpTrackActivateResult extends RsvpTrackStatus {
  templates_created: number
  rules_created: number
  invitations_sent: number
}

export interface RsvpTrackAdvanceResult extends RsvpTrackStatus {
  sent: number
  phoned: number
  failed: number
}

// ---- יומן המשימות של אישורי-ההגעה (Timeline לפי תאריכים) ----

// פעולה בודדת ביום מסוים (בקשת אישור / תזכורת / סבב שיחות / ציון-דרך).
export interface TimelineAction {
  type: string
  icon: string
  label: string
  audience: string // תווית קהל היעד ("כל המוזמנים" / "מי שעדיין לא אישר")
  audience_count: number
  moved_from_weekend: boolean // הוזז מסוף שבוע ליום פעיל
}

// יום אחד בלוח הזמנים, עם כל הפעולות שמתוכננות בו.
export interface TimelineDay {
  date: string // dd/mm/yyyy
  iso: string
  weekday: string // שם היום בעברית
  is_today: boolean
  is_tomorrow: boolean
  is_past: boolean
  is_commitment: boolean
  actions: TimelineAction[]
}

// התצוגה המלאה של יומן המשימות לזוג.
export interface RsvpTimelineView {
  configured: boolean
  event_date: string
  commit_days_before: number | null
  commitment_date: string | null
  rsvp_start_date: string | null
  days_to_commitment: number | null
  compressed: boolean
  total_guests: number
  pending_count: number
  confirmed_count: number
  today: string
  today_summary: string
  tomorrow_summary: string
  current_stage: string | null
  next_action_date: string | null
  next_action_label: string | null
  days: TimelineDay[]
}
