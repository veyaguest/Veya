/**
 * פניות מדף הבית — הטופס "רוצים שנדבר קודם?" (2026-10-29).
 *
 * רשימה לקריאה בלבד, מהחדשה לישנה: שם, טלפון, סוג אירוע, תאריך האירוע וכמה
 * ימים נשארו, ומתי הפנייה נכנסה. מכל שורה אפשר להתקשר או לפתוח WhatsApp.
 * אין כאן סטטוס "חזרתי אליו" — הטבלה בשרת יודעת רק להוסיף שורות.
 */
import { fetchLandingLeads, type LandingLead } from '../../adminApi'
import { EmptyState, ErrorState, Loading, PageHeader, StatusPill, fmtDate, fmtDateTime, useAsync } from '../../ui'

/** פנייה מהיממיים האחרונים מסומנת "חדשה" — לעין, לא כסטטוס שנשמר. */
const FRESH_MS = 48 * 60 * 60 * 1000

/** זמן מהשרת (UTC נאיבי) → מילישניות, כמו ב־fmtDateTime. */
function serverMs(iso: string | null): number {
  if (!iso) return NaN
  return Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`)
}

export function LeadsPage() {
  const { data, error, loading, reload } = useAsync(() => fetchLandingLeads(), [])
  const weekAgo = Date.now() - 7 * 24 * 60 * 60 * 1000
  const lastWeek = (data ?? []).filter((l) => serverMs(l.created_at) >= weekAgo).length
  return (
    <div className="adm-page">
      <PageHeader
        title="פניות מדף הבית"
        subtitle={data ? `${lastWeek} פניות ב־7 הימים האחרונים · מהטופס "רוצים שנדבר קודם?"` : 'מהטופס "רוצים שנדבר קודם?"'}
      />
      {loading && !data ? (
        <Loading />
      ) : error && !data ? (
        <ErrorState message={error} onRetry={reload} />
      ) : !data || data.length === 0 ? (
        <EmptyState title="עוד אין פניות" text="פניות מהטופס בדף הבית יופיעו כאן, ותקבלו עליהן גם מייל." />
      ) : (
        <ul className="adm-list">
          {data.map((l) => (
            <li key={l.id}>
              <LeadRow lead={l} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function LeadRow({ lead }: { lead: LandingLead }) {
  const fresh = Date.now() - serverMs(lead.created_at) < FRESH_MS
  return (
    <div className="adm-list-row adm-lead-row">
      {fresh ? <StatusPill tone="warn">חדשה</StatusPill> : <span aria-hidden="true" />}
      <span className="adm-list-main">
        <span className="adm-list-title">
          {lead.name} · <span dir="ltr">{formatPhone(lead.phone)}</span>
        </span>
        <span className="adm-list-sub">
          {lead.event_type_label}
          {lead.event_date ? ` · ${fmtDate(lead.event_date)}` : ''}
          {lead.days_to_event != null ? ` · ${daysLabel(lead.days_to_event)}` : ''}
          {' · נכנסה '}
          {fmtDateTime(lead.created_at)}
        </span>
      </span>
      <span className="adm-lead-actions">
        <a className="adm-btn" href={`tel:${lead.phone}`}>התקשרו</a>
        <a className="adm-btn" href={whatsappHref(lead.phone)} target="_blank" rel="noopener noreferrer">WhatsApp</a>
      </span>
    </div>
  )
}

function daysLabel(days: number): string {
  if (days < 0) return 'האירוע עבר'
  if (days === 0) return 'האירוע היום'
  if (days === 1) return 'מחר האירוע'
  return `עוד ${days} ימים לאירוע`
}

/** 0501234567 → 050-123-4567 (רק לתצוגה). */
function formatPhone(phone: string): string {
  const d = phone.replace(/\D/g, '')
  return d.length === 10 ? `${d.slice(0, 3)}-${d.slice(3, 6)}-${d.slice(6)}` : phone
}

/** wa.me דורש קידומת בינלאומית בלי אפס מוביל: 0501234567 → 972501234567. */
function whatsappHref(phone: string): string {
  const d = phone.replace(/\D/g, '')
  return `https://wa.me/${d.startsWith('0') ? `972${d.slice(1)}` : d}`
}
