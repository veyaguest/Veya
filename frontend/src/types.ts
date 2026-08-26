export type Side = 'groom' | 'bride' | 'shared'
// סוג האירוע — קובע את השפה הדינמית של המערכת (ראו strings/eventTypes.ts).
// חתונה היא ברירת המחדל ושומרת על תאימות אחורה.
export type EventType =
  | 'wedding'
  | 'bar_mitzvah'
  | 'bat_mitzvah'
  | 'henna'
  | 'brit'
  | 'brita'
  | 'business'
// קבוצה יכולה להיות אחת מהמוכרות, או קבוצה מותאמת אישית (טקסט חופשי בעברית).
// המפתחות תלויי-סוג-אירוע — ראו EventTerms.groupOptions ב-eventTypes.ts.
export type KnownGroupType =
  | 'close_family'
  | 'extended_family'
  | 'friends'
  | 'work'
  | 'army'
  | 'studies'
  | 'childhood'
  | 'neighbors'
  | 'family_father'
  | 'family_mother'
  | 'class'
  | 'staff_clubs'
  | 'family'
  | 'employees'
  | 'clients'
  | 'suppliers'
  | 'management'
  | 'partners'
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
  // הערה פנימית (מידע לזוג בלבד — לא משפיעה על ההושבה)
  notes_raw: string | null
  // הערות הושבה — המקור היחיד שמנוע ההושבה קורא מהבעלים
  seating_notes: string | null
  rsvp_status: RsvpStatus
  table_number: number | null
  guest_token: string | null
  confirmed_count: number | null
  guest_note: string | null
  is_child: boolean
  // סטטוס נגזר של ההזמנה (מהשרת): not_sent/sent/awaiting/confirmed/declined
  // ובעתיד delivered/read. אופציונלי — לא כל endpoint מחזיר אותו.
  invite_status?: InviteStatus
  created_at: string
}

export type InviteStatus =
  | 'not_sent'
  | 'sent'
  | 'delivered'
  | 'read'
  | 'awaiting'
  | 'confirmed'
  | 'declined'

export const INVITE_STATUS_LABELS: Record<InviteStatus, string> = {
  not_sent: 'לא נשלחה הזמנה',
  sent: 'נשלחה הזמנה',
  delivered: 'נמסרה',
  read: 'נקראה',
  awaiting: 'ממתין למענה',
  confirmed: 'אישר הגעה',
  declined: 'סירב להגיע',
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

/** שלוש הדרכים להוסיף את האירוע ליומן. ריקות כשאין תאריך לאירוע. */
export interface ConfirmCalendarLinks {
  google: string
  outlook: string
  /** נתיב יחסי ל-API (``/confirm/{token}/calendar.ics``) — ראו confirmIcsUrl. */
  ics: string
}

/**
 * אילו פעולות זמינות למוזמן. **השרת מחליט, לא העמוד** — כך פעולה חדשה
 * (מתנה באשראי) תידלק בעתיד בלי לגעת כאן, ופעולה שאין לה נתונים (אירוע בלי
 * כתובת) פשוט לא מוצגת במקום כפתור שלא עושה כלום.
 */
export interface ConfirmActions {
  invitation: boolean
  calendar: boolean
  navigation: boolean
  rsvp: boolean
  gift: boolean
}

export interface ConfirmEventInfo {
  event_type: EventType
  groom_name: string
  bride_name: string
  venue_name: string
  venue_address: string
  maps_link: string
  waze_link: string
  apple_maps_link: string
  event_date: string
  event_time: string
  invite_image: string | null
  /** "החתונה של אביב ודנה" / "בר המצווה של יונתן" — לפי סוג האירוע. */
  title: string
  calendar: ConfirmCalendarLinks
}

export interface ConfirmGuestPublic {
  full_name: string
  party_size: number
  rsvp_status: string
  confirmed_count: number | null
  guest_note: string | null
  event: ConfirmEventInfo
  actions: ConfirmActions
}

/** פירוט התשלום כפי שהשרת חישב אותו. כל הסכומים ב**אגורות** (₪1 = 100). */
export interface GiftQuote {
  /** מה שבעלי האירוע יקבלו — במלואו, בלי ניכוי עמלה. */
  gift_amount_agorot: number
  /** עמלת השירות, שמשולמת ע"י נותן המתנה ומתווספת מעל. */
  fee_agorot: number
  /** מה שנותן המתנה מחויב בפועל. */
  total_agorot: number
  /** 4 — מגיע מהשרת כדי שהטקסט במסך לא יקבע מספר משלו. */
  fee_percent: number
}

export interface GiftCheckoutResult {
  status: 'success' | 'failure'
  quote: GiftQuote
  /** מזהה העסקה אצל ספק הסליקה (מדומה בשלב הזה). */
  reference: string
  /** מזהה העסקה במערכת. */
  gift_id: number
  /** pending / paid / failed / cancelled / refunded — נקבע ע"י הספק. */
  gift_status: string
  /** תמיד true בשלב הזה — אין סליקה אמיתית. */
  mock: boolean
  message: string
}

/**
 * שורת מתנה כפי שבעלי האירוע רואים אותה — קריאה בלבד.
 *
 * מכיל בדיוק את מה שהשרת מחזיר ל-``GET /gifts`` (``schemas.OwnerGiftRead``).
 * עמלת השירות והסכום ששילם המוזמן **אינם חלק מהתשובה** — הם עניין שבין
 * VEYA לנותן המתנה, ומוצגים לו במסך שלו לפני התשלום.
 */
export interface GiftRow {
  id: number
  sender_name: string
  message: string | null
  /**
   * מה שהאירוע מקבל (אגורות) — במלואו, בלי ניכוי.
   *
   * ``null`` כל עוד חשבון קבלת המתנות לא עבר את **שתי** הבדיקות (VEYA
   * וספק הסליקה). זו החלטה של השרת: הסכום כלל לא נשלח, ולא משהו שהמסך
   * בוחר להסתיר. ראו ``GiftsSummary.amounts_visible``.
   */
  gift_amount_agorot: number | null
  status: 'pending' | 'paid' | 'failed' | 'cancelled' | 'refunded'
  created_at: string
}

/** מסך "מתנות באשראי" — סיכום + רשימה. הסיכום נספר רק מ-paid, בשרת. */
export interface GiftsSummary {
  /** האם השרת החזיר סכומים. ``false`` ⇒ כל שדות הסכום כאן הם ``null``. */
  amounts_visible: boolean
  total_received_agorot: number | null
  total_received_display: string | null
  paid_count: number
  /** כמה עסקאות קיימות בסך הכול (כולל שנכשלו). */
  total_count: number
  gifts: GiftRow[]
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
  seating_notes?: string
  is_child?: boolean
}

// עדכון חלקי של מוזמן קיים (עריכה) — כל השדות אופציונליים.
export interface GuestUpdate {
  full_name?: string
  phone?: string
  side?: Side
  group_type?: GroupType
  party_size?: number
  notes_raw?: string | null
  seating_notes?: string | null
  rsvp_status?: RsvpStatus
  table_number?: number | null
  is_child?: boolean
}

// מקור אמת יחיד לתוויות תצוגה של כל מפתחות הקבוצה הידועים — על כל סוגי
// האירוע (חתונה + כל השאר). "אפשרויות הבחירה" בטופס תלויות-סוג ונשאבות מ-
// activeEventTerms().groupOptions ב-eventTypes.ts; המילון כאן רק מתרגם מפתח
// לתווית לתצוגה, כדי שמוזמן שיובא/הוזן תחת סוג אירוע אחד יוצג נכון גם אם
// המסך הפעיל שונה (למשל דרך ה-API/דוחות).
export const GROUP_LABELS: Record<string, string> = {
  // חתונה / חינה
  close_family: 'משפחה קרובה',
  extended_family: 'משפחה רחוקה',
  friends: 'חברים',
  work: 'עבודה',
  army: 'צבא',
  studies: 'מהלימודים',
  childhood: 'חברי ילדות',
  neighbors: 'שכנים',
  // בר/בת מצווה
  family_father: 'משפחת האב',
  family_mother: 'משפחת האם',
  class: 'כיתה',
  staff_clubs: 'צוות/חוגים',
  // ברית / אירוע משפחתי / חינה
  family: 'משפחה',
  // אירוע עסקי
  employees: 'עובדים',
  clients: 'לקוחות',
  suppliers: 'ספקים',
  management: 'הנהלה',
  partners: 'שותפים',
  other: 'אחר',
}

// תווית לתצוגה: קבוצה מוכרת → שם בעברית; קבוצה מותאמת → הטקסט עצמו.
export function groupLabel(group: string): string {
  return (GROUP_LABELS as Record<string, string>)[group] ?? group
}

export const RSVP_LABELS: Record<RsvpStatus, string> = {
  pending: 'טרם השיב',
  confirmed: 'מגיע',
  declined: 'לא מגיע',
  maybe: 'מתלבט',
}

// ---- תבנית הודעת הזמנה (שלב RSVP 2) ----

export interface TemplatePlaceholder {
  key: string
  // כינוי ידידותי בעברית ([שם אורח]) שהזוג רואה ומכניס במקום {{...}}.
  token: string
  desc: string
  // קטגוריה לקיבוץ בעורך ההודעות (guest / event / when_where / links / extra).
  // ריק בתשובה משרת ותיק — הקומפוננטה נופלת אז לקבוצה אחת.
  cat?: string
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
  // party_size: 0 = טרם זוהתה כמות בטקסט (לא כמות אפס בפועל — יש להשלים
  // לפני ייבוא). מגיע רק מייבוא הדבקת טקסט חופשי; בייבוא Excel/CSV תמיד ≥1.
  party_size: number
  // guest_count_text: בדיוק מה שהמשתמש כתב לגבי כמות ("זוג", "שני ילדים"),
  // או null אם לא זוהתה כמות בשורה. מגיע רק מייבוא הדבקת טקסט חופשי.
  guest_count_text?: string | null
  notes_raw: string | null
  seating_notes: string | null
  valid: boolean
  errors: string[]
  // אזהרות רכות (לא חוסמות) — מגיע רק מייבוא הדבקת טקסט חופשי: "חסר טלפון",
  // "טלפון לא תקין", "כפילות", "חסרה כמות" (חוסמת ייבוא, ראו rowIssues).
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

export interface SeatingExplanation {
  guest_id: number
  full_name: string
  table_number: number
  reasons: string[]
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
  explanations?: SeatingExplanation[]
  // דוח בדיקת התקינות שרץ אחרי השיבוץ. ריק = ההושבה תקינה.
  violations?: SeatingViolation[]
  // האם יש סידור קודם לשחזור ("החזרת הסידור הקודם").
  can_undo?: boolean
}

// הפרה בודדת מדוח התקינות שאחרי ההושבה.
export interface SeatingViolation {
  kind: 'capacity' | 'forbidden_pair' | 'unseated'
  table_number: number | null
  guest_ids: number[]
  names: string[]
  text: string
}

export interface SeatingRequest {
  seats_per_table: number
  num_tables?: number
  only_confirmed?: boolean
  persist?: boolean
  // כמה מקומות להשאיר פנויים (רזרבה מפוזרת אחיד). null/undefined => הערך השמור.
  reserve_seats?: number | null
  // משבץ רק את מי שאין לו שולחן; מי שכבר משובץ נשאר בדיוק במקומו.
  only_unassigned?: boolean
}

// ---- ניהול רזרבה חכם (מצב יום האירוע) ----

// סיכום הרזרבה — לכרטיס הדשבורד ולפאנל "מצב יום האירוע".
export interface ReserveSummary {
  reserve_seats: number // יעד המקומות הפנויים המפוזרים שנבחר
  reserve_tables: number // מספר שולחנות רזרבה שלמים
  reserve_tables_capacity: number // סה"כ מקומות בשולחנות הרזרבה
  free_seats_active: number // מקומות פנויים בשולחנות הפעילים
  seated_people: number // כמה אנשים משובצים בפועל
  unseated_guests: number // כמה מוזמנים (רשומות) עדיין ללא שולחן
}

// המלצת שיבוץ בודדת (דטרמיניסטית) לשולחן אחד.
export interface SeatRecommendation {
  table_number: number
  table_name: string
  is_reserve: boolean
  free_seats: number
  score: number
  reasons: string[]
}

export interface RecommendSeatRequest {
  guest_id: number
  include_reserve?: boolean
}

export interface RecommendSeatResponse {
  guest_id: number
  guest_name: string
  seats_needed: number
  recommendations: SeatRecommendation[]
}

export interface AssignSeatRequest {
  guest_id: number
  table_number: number | null
}

export interface AssignSeatResult {
  guest_id: number
  table_number: number | null
  warnings: string[]
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
  declined_people: number
  maybe_people: number
  pending_people: number
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
  event_type: EventType
  groom_name: string
  bride_name: string
  // שורות ההורים כמזמינים — משמשות את נוסחי ההזמנה הדתי/חב"ד/חרדי.
  groom_parents_line?: string
  bride_parents_line?: string
  venue_name: string
  venue_address: string
  event_date: string
  event_time: string
  invite_image: string | null
  // כמה ימים לפני האירוע צריך למסור לאולם מספר סופי (1–10). null = טרם נבחר.
  venue_commit_days_before: number | null
  // האם הבחירה כבר ננעלה (בלתי-הפיכה מרגע שנקבעה).
  venue_commit_locked: boolean
  // שעת שליחה — "HH:MM", שעון ישראל בלבד, בטווח 10:00–19:00.
  // חלה על כל הודעות מסלול אישורי ההגעה (תזכורות/יום האירוע).
  rsvp_send_time: string
  // שעת שליחה נפרדת להודעת התודה — אותו טווח, עצמאית מהמסלול.
  thank_you_send_time: string
  // ---- נוהל דחייה ----
  // מחזור האירוע. 1 = האירוע המקורי; 2 ומעלה = אחרי דחייה.
  cycle_number: number
  // באיזה שלב האירוע נמצא. מחושב בשרת (app/postponement_service.py) —
  // המסך מציג את מה שהשרת אומר ואינו מסיק מצב בעצמו.
  event_stage: EventStage
  // האם פרטי הליבה נעולים כרגע לעריכה.
  edit_locked: boolean
  // אילו שדות נעולים — המסך מציג בדיוק אותם כקריאה-בלבד ולא מנחש.
  locked_fields: string[]
}

// חמשת מצבי האירוע (מקור: app/postponement_service.py, STAGE_*).
export type EventStage =
  | 'normal'          // אירוע פעיל, פרטי הליבה נעולים
  | 'requested'       // בקשת דחייה ממתינה לאישור
  | 'open'            // נוהל דחייה פעיל, עדיין בלי תאריך חדש
  | 'new_date_set'    // נוהל דחייה פעיל, התאריך החדש כבר עודכן
  | 'rsvp_reopened'   // מחזור חדש נפתח, טרם נשלחה הזמנה חדשה

export type PostponementStatus = 'pending' | 'approved' | 'completed' | 'rejected'

/** מצב נוהל הדחייה של האירוע. אין כאן תאריך חדש — הבקשה אינה מבקשת אותו. */
export interface Postponement {
  status: PostponementStatus | null
  cycle_number: number
  requested_at: string | null
  reviewed_at: string | null
  completed_at: string | null
  rejection_reason: string | null
  previous_event_date: string
  previous_event_time: string
  can_request: boolean
  can_complete: boolean
}

/** בקשת דחייה אחת בתור של האדמין. */
export interface PostponementReviewRow {
  request_id: number
  event_id: number
  event_title: string
  event_type: EventType
  cycle_number: number
  owner_name: string
  owner_email: string
  requested_by_name: string
  event_date: string
  event_time: string
  venue_name: string
  guests_total: number
  guests_confirmed: number
  status: PostponementStatus
  requested_at: string | null
  reviewed_by: string | null
  reviewed_at: string | null
  rejection_reason: string | null
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
  // שם מי שביצע את הפעולה. ריק בפעולות מערכת/אנונימיות (למשל אישור הגעה
  // שהגיע ממוזמן דרך הקישור האישי, בלי משתמש מחובר).
  actor_name?: string
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
  // גודל עצמאי (פיקסלים) — undefined = ללא override, גודל נגזר מ-table_type+density
  // כרגיל (התנהגות היסטורית). מוגדר רק לשולחנות שיובאו מסקיצת AI, כדי לשמר את
  // הגודל/הפרופורציה שזוהו בסקיצה במקום גודל אחיד לכל השולחנות מאותו סוג.
  width?: number
  height?: number
  name: string
  color: string
  notes: string
  locked: boolean
  // שולחן רזרבה שלם — מוצא מהשיבוץ האוטומטי, שמור לשיבוץ ידני ביום האירוע.
  is_reserve: boolean
}

// רק האלמנטים הגלויים בסרגל הכלים כרגע. שאר הסוגים (head_table, gift_table,
// restroom, stage) עדיין נתמכים בקוד לתאימות לאחור — רק הוסתרו מהממשק.
// pillar/wall/obstacle/other_area: לא מוצעים ידנית בסרגל — מגיעים רק מבניית
// אולם אוטומטית מ-AI Vision (עמוד/קיר/מכשול/אזור שזוהה בסקיצה).
export type HallElementType =
  | 'head_table'
  | 'dance_floor'
  | 'bar'
  | 'stage'
  | 'entrance'
  | 'dj'
  | 'gift_table'
  | 'restroom'
  | 'pillar'
  | 'wall'
  | 'obstacle'
  | 'other_area'

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

// פרופיל הפריסה של האולם — נקבע בהגדרה הראשונית ונשמר נעול. density קובע את
// גודל האלמנטים הקבוע; planned_tables לזיהוי "נוספו הרבה מעבר לתכנון".
export type HallDensity = 'spacious' | 'comfortable' | 'compact' | 'dense'

export interface HallLayout {
  density: HallDensity
  planned_tables: number
}

// מיקום/גודל/סיבוב/שקיפות/נעילה של שכבת הסקיצה על הלוח (world coordinates).
// null בכל המקומות = תאימות אחורה: הסקיצה מוצגת כרקע מלא, כמו שהייתה תמיד.
export interface HallSketchTransform {
  x: number
  y: number
  width: number
  height: number
  rotation: number
  opacity: number
  locked: boolean
  hidden: boolean
}

export interface HallState {
  seats_per_table: number
  reserve_seats: number
  tables: HallTable[]
  unassigned: HallGuest[]
  elements: HallElement[]
  warnings: string[]
  sketch: string | null
  hall_layout: HallLayout | null
  sketch_transform: HallSketchTransform | null
  // זוגות אילוצים שכבר מחושבים היום מהערות חופשיות — לשימוש עוזר ההושבה
  // החכם בצד הלקוח (בדיקות מיידיות כולל בזמן גרירה, בלי קריאת רשת נוספת).
  forbidden_pairs: [number, number][]
  together_pairs: [number, number][]
}

// אלמנט אחד שזוהה ע"י ניתוח AI Vision לסקיצה — לפני שהמשתמש אישר. קואורדינטות
// מנורמלות [0,1] יחסית לתמונת הסקיצה, לא לפיקסלים של הלוח (ראה HallPage.tsx).
export type DetectedHallElementType =
  | 'round_table' | 'square_table' | 'rectangle_table' | 'knights_table'
  | 'bar' | 'dance_floor' | 'stage' | 'entrance' | 'pillar' | 'wall' | 'obstacle' | 'other_area'

export interface DetectedHallElement {
  type: DetectedHallElementType
  x: number
  y: number
  width: number
  height: number
  rotation: number
  capacity: number | null
  // מספר השולחן כפי שהוא כתוב בסקיצה עצמה. null = לא זוהה מספר (ואז ממספרים
  // מרחבית — ראה assignTableNumbers). רלוונטי לשולחנות בלבד.
  table_number?: number | null
  confidence: number
  label: string
}

export interface SketchAnalyzeResponse {
  elements: DetectedHallElement[]
}

export interface HallTableSave {
  table_number: number
  x: number
  y: number
  guest_ids: number[]
  table_type: TableType
  capacity: number
  rotation: number
  width?: number
  height?: number
  name: string
  color: string
  notes: string
  locked: boolean
  is_reserve: boolean
}

// ---- משתמשים והתחברות (שלב 8) ----

export interface User {
  id: number
  email: string
  display_name: string
  phone: string
  avatar_url?: string
  is_admin: boolean
  // couple (זוג) / planner (מפיק) / venue (אולם) — ציר נפרד מ-is_admin.
  account_type: string
  // True אם המשתמש אישר גרסה ישנה של תנאי השימוש/מדיניות הפרטיות —
  // ראו legal.py::needs_reconsent (backend) ו-ReconsentModal (frontend).
  needs_reconsent?: boolean
  // האם כתובת המייל אומתה. false ⇒ מציגים את מסך "אימות כתובת המייל"
  // ואי אפשר ליצור אירוע.
  email_verified?: boolean
  // האם יש למשתמש שם מלא + טלפון תקין. false ⇒ מציגים השלמת פרטים לפני
  // יצירת אירוע (משתמשים ותיקים שנרשמו לפני שהשדות היו חובה).
  profile_complete?: boolean
}

// ---- ניהול משותף של האירוע (בן/בת זוג) ----

/** מנהל/ת אירוע כפי שמוצג במסך "ניהול משותף". */
export interface EventManager {
  user_id: number
  display_name: string
  email: string
  role_label: string
  is_me: boolean
}

/** האירוע היחיד של המשתמש. */
export interface MyEvent {
  id: number
  title: string
  event_type: EventType
  event_date: string
  venue_name: string
}

/** הזמנה ממתינה לניהול משותף (ללא הטוקן — הוא קיים רק במייל). */
export interface PartnerInvite {
  id: number
  invited_email: string
  status: string
  created_at: string
  expires_at?: string | null
  email_sent: boolean
}

/** כל מה שמסך "החשבון שלי" צריך, בקריאה אחת. */
export interface AccountOverview {
  user: User
  event?: MyEvent | null
  managers: EventManager[]
  pending_invite?: PartnerInvite | null
  can_invite_partner: boolean
}

/** מצב ההזמנה בדף ההצטרפות — כל ערך מקבל מסך משלו. */
export type InvitationState =
  | 'ready'
  | 'needs_login'
  | 'wrong_account'
  | 'expired'
  | 'used'
  | 'cancelled'
  | 'invalid'
  | 'already_member'
  | 'joined'

export interface InvitationPreview {
  state: InvitationState
  event_title: string
  inviter_name: string
  invited_email: string
  message: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export interface EventSummary {
  id: number
  event_type: EventType
  groom_name: string
  bride_name: string
  venue_name: string
  /**
   * האם האירוע זכאי לשירות "מתנות באשראי".
   *
   * **נקבע בשרת** (``gift_eligibility.is_eligible``) — הפרונט לא מחשב
   * זכאות ולא מחזיק תנאי משלו. ההסתרה כאן היא נוחות; האכיפה היא ב-API,
   * שמחזיר 404 על ``/gifts`` לאירוע שאינו זכאי.
   *
   * זכאות **אינה** "השירות פעיל" — לשם כך נדרש גם חשבון קבלת מתנות
   * מאומת, וזה סטטוס נפרד לגמרי.
   */
  gift_service_eligible: boolean
}

// ---- פאנל אדמין ----

export interface AdminUserRow {
  id: number
  email: string
  display_name: string
  is_admin: boolean
  account_type: string
  disabled: boolean
  events_count: number
  guests_count: number
  created_at: string
}

export interface AdminUserUpdate {
  display_name?: string
  phone?: string
  account_type?: 'couple' | 'planner' | 'venue' | 'phone_agent'
  is_admin?: boolean
}

export interface AdminLoginRow {
  id: number
  ip: string | null
  user_agent: string | null
  created_at: string
}

export interface AdminEventRow {
  id: number
  event_type: string
  hosts: string
  groom_name: string
  bride_name: string
  venue_name: string
  owner_id: number | null
  owner_email: string | null
  guests_count: number
}

export interface AdminUserDetail {
  id: number
  email: string
  display_name: string
  phone: string
  is_admin: boolean
  account_type: string
  disabled: boolean
  created_at: string
  events: AdminEventRow[]
  recent_logins: AdminLoginRow[]
  login_count: number
}

export interface AdminAccountCreateResult {
  user_id: number
  email: string
  account_type: string
  temporary_password: string
}

// ---- ניהול טלפנים (phone_agent) בפאנל האדמין ----
// אין כאן מודל נתונים חדש: המשתמש הוא שורת users רגילה, ההקצאה היא
// call_assignments הקיימת, והמונים נגזרים מ-call_logs ומתור השיחות.

export interface AdminCallerRow {
  id: number
  email: string
  display_name: string
  phone: string
  disabled: boolean
  /** כמה שיחות תיעד בפועל (מתוך יומן השיחות הקיים). */
  calls_made: number
  /** כמה שיחות ממתינות לו עכשיו, לפי אותו חישוב שמזין את מסך השיחות שלו. */
  waiting_tasks: number
  assigned_event_ids: number[]
  created_at: string
}

export interface AdminCallerEventOption {
  event_id: number
  event_type: string
  hosts: string
  venue_name: string
  event_date: string
  waiting: number
}

export interface AdminCallersPage {
  callers: AdminCallerRow[]
  events: AdminCallerEventOption[]
}

export interface AdminPasswordResetResult {
  user_id: number
  email: string
  temporary_password: string
}

export interface AdminImpersonateResult {
  token: string
  user_id: number
  email: string
  display_name: string
}

export interface AdminVenueRow {
  id: number
  name: string
  address: string
  city: string
  usage_count: number
  maps_link: string
  waze_link: string
  created_at: string
}

export interface AdminVenueUpdate {
  name?: string
  address?: string
  city?: string
}

export interface AdminVenueMerge {
  target_id: number
}

// ---- לוח הבקרה של האדמין ----

export interface AdminDashboardEvent {
  id: number
  event_type: string
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

export interface AdminEventTypeCount {
  event_type: string
  label: string
  count: number
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
  events_by_type: AdminEventTypeCount[]
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

// ---- תקשורת עם אורחים — רצף ההודעות הקבוע של האירוע ----

export type MessageType =
  | 'invitation'
  | 'reminder_1'
  | 'reminder_2'
  | 'final_reminder'
  | 'event_day'
  | 'thank_you'
  // מותנה: מופיע רק בזמן נוהל דחייה פעיל, ולכן **אינו** ב-MESSAGE_TYPES
  // למטה (שהוא הרצף הקבוע). ראו backend/app/communication.py.
  | 'postponement'

// הסדר הקבוע להצגה (תואם ל-backend/app/communication.py: MESSAGE_TYPES).
export const MESSAGE_TYPES: MessageType[] = [
  'invitation', 'reminder_1', 'reminder_2',
  'final_reminder', 'event_day', 'thank_you',
]

export type TargetAudience = 'all' | 'pending' | 'confirmed' | 'declined'

export const TARGET_AUDIENCE_LABELS: Record<TargetAudience, string> = {
  all: 'כל המוזמנים',
  pending: 'ממתינים לתשובה',
  confirmed: 'מאשרים הגעה',
  declined: 'מסרבים',
}

// 12 המשתנים הנתמכים בתוכן הודעה — {{key}} — עם תווית עברית להוספה בעורך.
export const COMMUNICATION_VARIABLES: { key: string; label: string }[] = [
  { key: 'guest_name', label: 'שם האורח' },
  { key: 'guest_names', label: 'שמות האורחים' },
  { key: 'host_names', label: 'שמות בעלי האירוע' },
  { key: 'event_type', label: 'סוג האירוע' },
  { key: 'event_type_definite', label: 'סוג האירוע (מיודע)' },
  { key: 'event_date', label: 'תאריך האירוע' },
  { key: 'event_time', label: 'שעת האירוע' },
  { key: 'venue_name', label: 'שם האולם' },
  { key: 'address', label: 'כתובת' },
  { key: 'navigation_link', label: 'קישור ניווט' },
  { key: 'rsvp_link', label: 'קישור אישור הגעה' },
  { key: 'table_number', label: 'מספר שולחן' },
  { key: 'gift_link', label: 'קישור מתנה' },
]

export interface EventMessage {
  id: number
  message_type: MessageType
  title: string
  content: string
  variables_supported: string[]
  is_active: boolean
  trigger_offset_days: number
  target_audience: TargetAudience
  updated_at: string
}

export interface EventMessageInput {
  title?: string
  content?: string
  is_active?: boolean
  trigger_offset_days?: number
  target_audience?: TargetAudience
}

export interface CommunicationDue {
  event_message_id: number
  message_type: MessageType
  guest_id: number
  guest_name: string
  phone: string
  preview: string
}

export interface CommunicationDueQueue {
  actions: CommunicationDue[]
  mode: string
}

/** תוצאת שליחה ידנית — כולל מי דולג ולמה, כדי שהזוג יידע מה קרה בפועל. */
export interface ManualSendResult {
  mode: string
  sent: number
  failed: number
  /** מוזמנים ללא מספר טלפון תקין — לא נשלחה אליהם הודעה. */
  skipped_no_phone: number
  detail: string | null
}

export interface CommunicationSendResult {
  mode: string
  sent: number
  failed: number
  detail: string | null
}

export interface MessageDefault {
  id: number
  event_type: string
  message_type: MessageType
  title: string
  content: string
  variables_supported: string[]
  is_active: boolean
  updated_at: string
}

export interface MessageDefaultInput {
  title?: string
  content?: string
  is_active?: boolean
}

export interface MessageDefaultsBackfillResult {
  events_processed: number
  messages_created: number
}

// ספריית נוסחים לבחירה (עד 12 לכל event_type×message_type) — הזוג בוחר
// מתוכן במקום נוסח קבוע יחיד. ראו MessageDefault (הנוסח שמוקצה אוטומטית).
export interface MessageDefaultOption {
  id: number
  event_type: string
  message_type: MessageType
  option_number: number
  tone: string
  title: string
  content: string
  variables_supported: string[]
  is_active: boolean
  updated_at: string
}

export interface MessageDefaultOptionCreate {
  event_type: string
  message_type: MessageType
  tone?: string
  title?: string
  content?: string
  variables_supported?: string[]
}

export interface MessageDefaultOptionInput {
  tone?: string
  title?: string
  content?: string
  is_active?: boolean
  variables_supported?: string[]
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

export interface AdminMessageStat {
  kind: string
  count: number
}

export interface AdminMessageStats {
  total_outbound: number
  total_inbound: number
  by_kind: AdminMessageStat[]
}

export interface AdminAuditRow {
  id: number
  action: string
  detail: string
  ip: string | null
  event_id: number | null
  user_id: number | null
  actor_email: string | null
  actor_name: string | null
  created_at: string
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
  skipped_missing: number
  skipped_invalid: number
  failed: number
  failed_ids: number[]
  newly_activated: boolean
}

// סיכום מצב ההודעות שנשלחו למוזמנים (נמסרו/נקראו/נכשלו/...) — כרטיס
// "מעקב אחרי המוזמנים" במסך ניהול ההודעות. נפרד מ-RsvpTrackStatus: זה סטטוס
// ההודעה עצמה, לא תשובת ה-RSVP.
// חשוב: no_valid_number הוא ידע מקומי בלבד (טלפון חסר/פורמט לא תקין) —
// לא אישור מ-WhatsApp שהמספר לא קיים שם (ראו backend/app/message_status.py).
export interface MessageStatusSummary {
  mode: string
  total_guests: number
  sent: number
  delivered: number
  read: number
  failed: number
  no_valid_number: number
  blocked: number
  queued: number
}

// שורת מוזמן ברשימת "מי קיבל את ההודעה" (סינון לפי סוג הודעה נבחר).
export interface MessageTypeGuestRow {
  guest_id: number
  guest_name: string
  phone: string
  status: string
  updated_at: string | null
}

// סטטוס ההודעות לפי סוג הודעה נבחר — הכרטיס "מעקב אחרי המוזמנים" מציג
// הודעה אחת בכל פעם (invitation/reminder_1/.../thank_you), לא סיכום מצטבר.
// not_sent_yet=true → אף הודעה מהסוג הזה עוד לא נשלחה לאף מוזמן.
export interface MessageTypeStatus {
  message_type: MessageType
  not_sent_yet: boolean
  total: number
  sent: number
  delivered: number
  read: number
  failed: number
  no_valid_number: number
  blocked: number
  queued: number
  guests: MessageTypeGuestRow[]
}

// האייקון של כל סוג הודעה חי ב-``components/MessageTypeIcon.tsx`` (SVG
// קווי, אחד לכל הסוגים). קודם הייתה כאן מפת אימוג'י — היא הוסרה כדי
// שכל המערכת תדבר בשפת אייקונים אחת ולא באוסף סמלים של מערכת ההפעלה.

/** סוגי הודעה שהזוג שולח ידנית (ולא לפי לוח זמנים). */
export const MANUAL_SEND_TYPES: MessageType[] = ['postponement']

// ספירה מקדימה לדיאלוג האישור לפני שליחת הזמנות ידנית.
export interface InvitationSendPreview {
  total_guests: number
  can_receive: number
  not_yet_sent: number
  already_sent: number
  missing_phone: number
  invalid_phone: number
  already_activated: boolean
}

// היקף שליחה: רק חדשים / שליחה מחדש לכולם.
export type SendScope = 'new' | 'all'

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

// ---- הפרדת ההערות: הצעה להעביר הערה פנימית לשדה "הערות הושבה" ----
export interface NoteSplitCandidate {
  guest_id: number
  full_name: string
  notes_raw: string
}

export interface NoteSplitSuggestions {
  candidates: NoteSplitCandidate[]
}

// ---- "החזרת הסידור הקודם" ----
export interface SeatingUndoResult {
  restored_guests: number
  can_undo: boolean
}

export interface SeatingUndoState {
  can_undo: boolean
  at: string | null
}

// ---- Call Center (אדמין) — תור השיחות, נגזר מ-Workflow אישורי ההגעה ----
// אין כאן תאריכים או סטטוסים חדשים: המועדים מגיעים ממסלול אישורי ההגעה
// והסטטוסים הם אותם סטטוסי RSVP של המערכת (ראו backend/app/call_center.py).

export type CallOutcome =
  | 'confirmed'
  | 'declined'
  | 'no_answer'
  | 'busy'
  | 'wrong_number'
  | 'callback'

/** טווח התצוגה במסך השיחות — היום (ברירת המחדל) / מחר / בהמשך / לא טופל
 * (שיחה מתאריך שעבר, באירוע פעיל, שעדיין לא בוצעה). אירוע שתאריכו כבר עבר
 * לא מופיע באף אחד מהטווחים, כולל 'לא טופל' — ראו backend/app/call_center.py. */
export type CallCenterScope = 'today' | 'tomorrow' | 'later' | 'not_handled'

export interface CallCenterEventRow {
  event_id: number
  event_type: string
  hosts: string
  venue_name: string
  event_date: string
  event_time: string
  days_until: number | null
  round_number: number
  round_label: string
  round_date: string
  waiting: number
  done: number
}

export interface CallCenterOverview {
  scope: CallCenterScope
  total: number
  done: number
  waiting: number
  events_needing_attention: number
  events: CallCenterEventRow[]
}

export interface CallCenterGuestRow {
  guest_id: number
  event_id: number
  event_type: string
  event_hosts: string
  event_date: string
  full_name: string
  phone: string
  party_size: number
  side: string
  guest_note: string | null
  rsvp_status: string
  round_number: number
  round_date: string
  last_outcome: CallOutcome | null
  last_outcome_label: string | null
  callback_at: string | null
  /** חזר לתור כי הגיע מועד ה"חזרו אליי" שהוא ביקש — ולא כי נפתח סבב חדש. */
  is_followup: boolean
  followup_count: number
}

export interface CallCenterQueue {
  scope: CallCenterScope
  items: CallCenterGuestRow[]
  total: number
  limit: number
  offset: number
}

export interface CallCenterTimelineItem {
  kind: string
  channel: string
  label: string
  text: string
  status: string
  round_number: number | null
  actor: string | null
  created_at: string
}

export interface CallCenterGuestDetail {
  guest_id: number
  full_name: string
  phone: string
  side: string
  party_size: number
  rsvp_status: string
  confirmed_count: number | null
  guest_note: string | null
  notes_raw: string | null
  event_id: number
  event_type: string
  hosts: string
  event_date: string
  event_time: string
  venue_name: string
  venue_address: string
  round_number: number | null
  round_date: string | null
  timeline: CallCenterTimelineItem[]
}

export interface CallOutcomeRequest {
  outcome: CallOutcome
  count?: number | null
  guest_note?: string | null
  note?: string
  callback_at?: string | null
}

export interface CallOutcomeResult {
  guest_id: number
  outcome: CallOutcome
  outcome_label: string
  rsvp_status: string
  confirmed_count: number | null
  callback_at: string | null
}

// ---- התראות איכות-דאטה על מוזמנים ----
// נפרד לחלוטין מסטטוס אישור ההגעה: זו בעיה בפרטי הקשר, לא תשובה של המוזמן.

export interface GuestDataAlert {
  kind: 'phone_fix'
  guest_id: number
  full_name: string
  phone: string
  rsvp_status: string
  attempts: number
  reported_at: string
}

export interface GuestDataAlerts {
  phone_fix: GuestDataAlert[]
  total: number
}

// ── פרטי קבלת מתנות (חשבון הבנק של בעלי האירוע) ──────────────────────────

/** תיאור אישור ניהול החשבון שהועלה — בלי הקובץ עצמו. */
export type PayoutCertificate = {
  filename: string | null
  content_type: string | null
  size: number | null
  uploaded_at: string | null
}

/**
 * פרטי החשבון כפי שהם חוזרים מהשרת.
 *
 * ``account_number_masked`` בלבד — מספר החשבון המלא לעולם לא חוזר לדפדפן
 * (ראו backend/app/routers/payout.py). מי שרוצה לשנות מקליד מחדש.
 */
/** missing → submitted → under_review → verified / rejected. */
export type PayoutStatus = 'missing' | 'submitted' | 'under_review' | 'verified' | 'rejected'

/** תשובת בדיקה — אותן שלוש מילים לשני המסלולים. */
export type ReviewStatus = 'pending' | 'approved' | 'rejected'

export type PayoutAccount = {
  configured: boolean
  /** מסלול הבדיקה של VEYA, בפירוט מלא. */
  status: PayoutStatus
  /** אותו מסלול, מקוצר: pending / approved / rejected. */
  veya_status: ReviewStatus
  /** בדיקת ספק הסליקה — **מסלול נפרד**. אישור VEYA אינו מזיז אותו. */
  provider_status: ReviewStatus
  /**
   * שתי הבדיקות אושרו. **נגזר בשרת בלבד** ולא נשלח בשום קלט — המסך רק
   * מציג אותו. רק כשהוא ``true`` השרת מחזיר סכומי מתנות.
   */
  fully_verified: boolean
  /**
   * הפרטים אושרו ולכן **נעולים לשינוי**.
   *
   * מגיע מהשרת ואינו נגזר בדפדפן: השרת הוא שחוסם את הכתיבה בפועל
   * (``payout_service.assert_unlocked``), והמסך רק מציית. חישוב מקביל
   * כאן היה רק הזדמנות לשתי האמיתות לסטות זו מזו.
   */
  locked: boolean
  /** האם אפשר להגיש לבדיקה עכשיו — נקבע בשרת, לא מחושב כאן. */
  can_submit: boolean
  /** סיבת הדחייה של VEYA. */
  rejection_reason: string | null
  /** סיבת הדחייה של ספק הסליקה, אם סיפק אותה. */
  provider_rejection_reason: string | null
  submitted_at: string | null
  bank_code: number | null
  bank_name: string | null
  branch_number: string | null
  account_number_masked: string | null
  certificate: PayoutCertificate | null
  updated_at: string | null
}

/** קלט הטופס. ``certificate`` הוא data URL; null = לא נגעו בקובץ הקיים. */
export type PayoutAccountInput = {
  bank_code: number
  branch_number: string
  account_number: string
  certificate: string | null
}

/**
 * שורה בתור הבדיקה של האדמין — חשבון אחד שממתין להכרעת VEYA.
 *
 * **אין כאן מספר חשבון מלא.** מי שבודק פותח את אישור ניהול החשבון
 * ומשווה מולו; ארבע הספרות האחרונות מספיקות כדי להצליב.
 */
export type PayoutReviewRow = {
  event_id: number
  event_title: string
  owner_name: string
  owner_email: string

  bank_code: number | null
  bank_name: string | null
  branch_number: string | null
  account_number_masked: string | null
  certificate: PayoutCertificate | null

  status: PayoutStatus
  veya_status: ReviewStatus
  provider_status: ReviewStatus
  fully_verified: boolean
  rejection_reason: string | null
  provider_rejection_reason: string | null
  submitted_at: string | null
  /** מי ב-VEYA הכריע בבדיקה האחרונה, ומתי. */
  reviewed_by: string | null
  reviewed_at: string | null
}
