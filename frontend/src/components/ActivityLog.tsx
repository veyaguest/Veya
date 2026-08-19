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

// action → אייקון + תיאור קצר. מה שלא ברשימה פשוט לא מוצג.
const SHOWN: Record<string, { icon: string; label: string }> = {
  guest_party_size_update: { icon: '👥', label: 'עדכון כמות מוזמנים' },
  guest_rsvp_manual_update: { icon: '✅', label: 'עדכון אישור הגעה' },
  seating_assign: { icon: '🪑', label: 'שיבוץ להושבה' },
  update_event: { icon: '📝', label: 'עדכון פרטי האירוע' },
  send_invitations: { icon: '📤', label: 'שליחת הזמנות' },
  partner_invited: { icon: '💌', label: 'הזמנה לניהול משותף' },
  partner_joined: { icon: '💍', label: 'הצטרפות לניהול האירוע' },
  partner_invite_cancelled: { icon: '✖️', label: 'ביטול הזמנה' },
  event_ownership_transferred: { icon: '🔑', label: 'העברת ניהול האירוע' },
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
              <span className="alog-icon" aria-hidden="true">{meta.icon}</span>
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
