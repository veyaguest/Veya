import { useEffect, useState } from 'react'
import { readAudit } from '../api'
import type { AuditLogRow } from '../types'
import './ActivityLog.css'

/**
 * "יומן פעילות" — מי עשה מה ומתי באירוע.
 *
 * הערך האמיתי שלו מתחיל כשמנהלים את האירוע בשניים: "אביב שינה את כמות
 * המוזמנים של משפחת כהן מ-2 ל-4", "דנה שיבצה את משפחת לוי לשולחן 12".
 * שני המנהלים רואים בדיוק את אותו יומן — הוא תלוי אירוע, לא משתמש.
 *
 * מציג רק פעולות שיש להן משמעות לזוג. רשומות תשתית (גישה לקישור, אישורי
 * הסכמה וכו') נשארות ביומן בשרת אבל לא מוצגות כאן, כדי שהיומן יישאר קריא.
 */

// action → נתיב SVG + תיאור קצר. מה שלא ברשימה פשוט לא מוצג.
//
// קודם היו כאן אימוג'י (👥 ✅ 🪑 📝 📤 💌 💍 ✖️ 🔑). ביומן שכולו שורות
// קצרות זה יצר עמודה של סמלים צבעוניים בגדלים ובסגנונות שונים, שמושכת
// את העין חזק יותר מהתוכן עצמו. אותם אייקונים קוויים בצבע אחד נקראים
// כסימון סוג, לא כקישוט.
const ICONS: Record<string, string> = {
  people: 'M8.6 11a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4ZM3 19.4c0-3 2.5-5.2 5.6-5.2s5.6 2.2 5.6 5.2M16 6.2a2.7 2.7 0 1 1 0 5.4M17 14.3c2.5.4 4 2.4 4 5.1',
  check: 'M4.5 12.5l5 5 10-10',
  chair: 'M7 4.5h10v7H7zM6 12.5h12M8 12.5v6M16 12.5v6',
  pencil: 'M4.5 19.5h4l10-10a2.1 2.1 0 0 0-3-3l-10 10v3ZM14.5 7.5l3 3',
  send: 'M20.5 4.5 3.5 11l7 2.5 2.5 7 7.5-16ZM10.5 13.5l4-4',
  mail: 'M3.5 6.5h17v12h-17zM4 7.2 12 13l8-5.8',
  rings: 'M9.4 19a5 5 0 1 0 0-10 5 5 0 0 0 0 10ZM14.6 19a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z',
  close: 'M6.5 6.5l11 11M17.5 6.5l-11 11',
  key: 'M15.5 3.5a5 5 0 1 0-4.2 7.7L4.5 18v2.5H7l1-1v-2h2v-2h2l1.3-1.3a5 5 0 0 0 2.2-10.7ZM16.6 7.4v.2',
}

const SHOWN: Record<string, { icon: keyof typeof ICONS; label: string }> = {
  guest_party_size_update: { icon: 'people', label: 'עדכון כמות מוזמנים' },
  guest_rsvp_manual_update: { icon: 'check', label: 'עדכון אישור הגעה' },
  seating_assign: { icon: 'chair', label: 'שיבוץ להושבה' },
  update_event: { icon: 'pencil', label: 'עדכון פרטי האירוע' },
  send_invitations: { icon: 'send', label: 'שליחת הזמנות' },
  partner_invited: { icon: 'mail', label: 'הזמנה לניהול משותף' },
  partner_joined: { icon: 'rings', label: 'הצטרפות לניהול האירוע' },
  partner_invite_cancelled: { icon: 'close', label: 'ביטול הזמנה' },
  event_ownership_transferred: { icon: 'key', label: 'העברת ניהול האירוע' },
}

/** "לפני 5 דקות" / "אתמול" — זמן יחסי קצר, בעברית. */
function timeAgo(iso: string): string {
  // ה-Backend מחזיר UTC נאיבי (בלי Z) — מסמנים זאת במפורש, אחרת הדפדפן
  // מפרש את המחרוזת כזמן מקומי והזמנים "קופצים" בכמה שעות.
  const hasZone = /[Zz]|[+-]\d{2}:?\d{2}$/.test(iso)
  const then = new Date(hasZone ? iso : `${iso}Z`).getTime()
  if (isNaN(then)) return ''
  const mins = Math.floor((Date.now() - then) / 60000)
  if (mins < 1) return 'עכשיו'
  if (mins < 60) return `לפני ${mins} דק׳`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `לפני ${hours} שע׳`
  const days = Math.floor(hours / 24)
  if (days === 1) return 'אתמול'
  if (days < 30) return `לפני ${days} ימים`
  return new Date(then).toLocaleDateString('he-IL', { day: 'numeric', month: 'numeric' })
}

export function ActivityLog() {
  const [rows, setRows] = useState<AuditLogRow[] | null>(null)

  useEffect(() => {
    let alive = true
    readAudit(50)
      .then((data) => alive && setRows(data))
      .catch(() => alive && setRows([]))
    return () => {
      alive = false
    }
  }, [])

  if (rows === null) return null

  const items = rows.filter((r) => SHOWN[r.action]).slice(0, 12)
  if (items.length === 0) return null

  return (
    <div className="alog-card">
      <h3 className="alog-title">יומן פעילות</h3>
      <ul className="alog-list">
        {items.map((row) => {
          const meta = SHOWN[row.action]
          return (
            <li key={row.id} className="alog-item">
              <span className="alog-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                  <path d={ICONS[meta.icon]} />
                </svg>
              </span>
              <span className="alog-body">
                <span className="alog-text">
                  {row.actor_name && <strong>{row.actor_name}: </strong>}
                  {row.detail || meta.label}
                </span>
              </span>
              <span className="alog-time">{timeAgo(row.created_at)}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
