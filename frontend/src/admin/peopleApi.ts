import { adminHttp, qs } from './adminApi'

const { getJson } = adminHttp

export interface UserRow {
  id: number
  email: string
  display_name: string
  phone: string
  account_type: string
  account_type_label: string
  is_admin: boolean
  admin_role_label: string
  disabled: boolean
  events_count: number
  last_login_at: string | null
  created_at: string | null
}

export interface EventRow {
  id: number
  label: string
  event_type: string
  event_type_label: string
  event_date: string
  venue_name: string
  owner_id: number | null
  owner_email: string
  guests: number
  confirmed: number
  pending: number
  declined: number
  seated: number
  rsvp_track_active: boolean
  open_calls: number
  created_at: string | null
}

export interface Page<T> {
  total: number
  limit: number
  offset: number
  items: T[]
}

export interface ControlSection {
  key: string
  title: string
  status: 'ok' | 'warn' | 'bad' | 'neutral' | 'info'
  status_label: string
  facts: { label: string; value: string; tone: 'ok' | 'warn' | 'bad' | 'neutral' | 'info' }[]
  link: string
}

export interface EventControl {
  id: number
  label: string
  event_type: string
  event_type_label: string
  event_date: string
  event_time: string
  venue_name: string
  venue_address: string
  cycle_number: number
  created_at: string | null
  owner: { id: number; email: string; name: string; disabled: boolean } | null
  members: { id: number; email: string; name: string; role: string; status: string }[]
  sections: ControlSection[]
}

export interface ActivityRow {
  id: number
  action: string
  detail: string
  actor: string
  created_at: string | null
}

export const people = {
  users: (p: { q?: string; status?: string; limit?: number; offset?: number }) =>
    getJson<Page<UserRow>>(`/admin/people/users${qs(p)}`),
  events: (p: {
    q?: string
    event_type?: string
    when?: string
    track?: string
    owner_id?: number | null
    limit?: number
    offset?: number
  }) => getJson<Page<EventRow>>(`/admin/people/events${qs(p)}`),
  event: (id: number) => getJson<EventControl>(`/admin/people/events/${id}`),
  activity: (id: number) => getJson<ActivityRow[]>(`/admin/people/events/${id}/activity`),
}

/** שמות פעולות ביומן האירוע (מערכת ההודעות/האוטומציה הקיימת). */
export const EVENT_ACTIVITY_LABELS: Record<string, string> = {
  update_event: 'עדכון פרטי האירוע',
  send_invitations: 'שליחת הזמנות',
  send_reminders: 'שליחת תזכורות',
  automation_run_due: 'הרצת אוטומציה',
  confirm_submit: 'אישור הגעה של מוזמן',
  rsvp_track_activate: 'הפעלת מסלול אישורי הגעה',
  rsvp_track_advance: 'התקדמות במסלול',
  guest_call_confirmed: 'שיחה: אישר/ה הגעה',
  guest_call_declined: 'שיחה: לא מגיע/ה',
  guest_call_no_answer: 'שיחה: לא ענה/תה',
  guest_call_busy: 'שיחה: לא ניתן להשיג',
  guest_call_wrong_number: 'שיחה: מספר שגוי',
  guest_call_callback: 'שיחה: נקבעה שיחה חוזרת',
  guest_call_followup: 'שיחת המשך',
  payout_details_saved: 'פרטי קבלת מתנות נשמרו',
  payout_details_updated: 'פרטי קבלת מתנות עודכנו',
  payout_status_changed: 'בדיקת פרטי חשבון',
  event_ownership_transferred: 'העברת בעלות',
  data_export: 'ייצוא נתונים',
}
