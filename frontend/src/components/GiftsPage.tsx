import { useEffect, useState } from 'react'
import { getGifts } from '../api'
import type { GiftRow, GiftsSummary } from '../types'
import { strings } from '../strings/he'
import { PayoutDetails } from './PayoutDetails'
import './GiftsPage.css'

const t = strings.gifts

/**
 * מסך "מתנות באשראי" לבעלי האירוע — קריאה בלבד.
 *
 * באופיו הוא קרוב ל"יומן פעילות" ולא ללוח בקרה: כרטיס שקט אחד, שורות
 * מופרדות בקו שיער, טיפוגרפיה רגועה. הזוג בא לכאן לראות מי בירך ובכמה,
 * לא לנתח נתונים.
 *
 * **מה שבמפורש לא מוצג כאן: עמלת השירות.** היא עניין שבין VEYA לנותן
 * המתנה — הוא משלם אותה ורואה אותה במלואה במסך שלו לפני התשלום. לבעלי
 * האירוע מוצג רק מה שהם מקבלים.
 */

/** ₪1 = 100 אגורות. הצגה בלבד — כל חשבון הכסף כבר בוצע בשרת. */
function formatAgorot(agorot: number): string {
  const whole = Math.trunc(agorot / 100)
  const rest = agorot % 100
  const shown = whole.toLocaleString('he-IL')
  return rest ? `₪${shown}.${String(rest).padStart(2, '0')}` : `₪${shown}`
}

/** "24.08.26" — קצר ועדין, לא משפט שלם.
 *
 * ה-Backend מחזיר UTC נאיבי (בלי Z), ולכן מסמנים זאת במפורש — אחרת
 * הדפדפן קורא את המחרוזת כזמן מקומי והתאריך יכול לקפוץ ביום שלם.
 * אותו טיפול בדיוק כמו ב-ActivityLog.
 */
function formatDate(iso: string): string {
  const hasZone = /[Zz]|[+-]\d{2}:?\d{2}$/.test(iso)
  const d = new Date(hasZone ? iso : `${iso}Z`)
  if (isNaN(d.getTime())) return ''
  const dd = String(d.getDate()).padStart(2, '0')
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const yy = String(d.getFullYear()).slice(-2)
  return `${dd}.${mm}.${yy}`
}

/** תג סטטוס — ברור אך לא צעקני. */
function StatusBadge({ status }: { status: GiftRow['status'] }) {
  return (
    <span className={`gift-status gift-status-${status}`}>
      {t.statusLabels[status] ?? status}
    </span>
  )
}

function GiftListRow({ gift }: { gift: GiftRow }) {
  return (
    <li className="gift-row">
      <span className="gift-cell-name">{gift.sender_name || t.anonymousGiver}</span>
      <span className="gift-cell-amount">{formatAgorot(gift.gift_amount_agorot)}</span>
      <span className="gift-cell-blessing">
        {gift.message ? <q>{gift.message}</q> : <span aria-hidden="true">—</span>}
      </span>
      <span className="gift-cell-date">{formatDate(gift.created_at)}</span>
      <span className="gift-cell-status">
        <StatusBadge status={gift.status} />
      </span>
    </li>
  )
}

export function GiftsPage() {
  const [data, setData] = useState<GiftsSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError(null)
    getGifts()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : t.loadError))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  if (loading) return <div className="gifts-state">{strings.common.loading}</div>
  if (error) return <div className="gifts-state gifts-state-error">{error}</div>
  if (!data) return null

  return (
    <div className="gifts-page">
      {/* פרטי קבלת המתנות — לאן הכסף מועבר. מעל הרשימה, כי בלעדיו
          המתנות שהתקבלו לא יגיעו לשום מקום. */}
      <PayoutDetails />

      {/* סיכום — שתי עובדות בלבד, בלי עמלות ובלי פילוחים. */}
      <section className="gifts-summary" aria-label={t.totalReceivedLabel}>
        <span className="gifts-summary-label">{t.totalReceivedLabel}</span>
        <span className="gifts-summary-total">{data.total_received_display}</span>
        <span className="gifts-summary-count">
          {t.countLabel}: <strong>{data.paid_count}</strong>
        </span>
      </section>

      {data.gifts.length === 0 ? (
        <div className="gifts-empty">
          <p>{t.emptyTitle}</p>
          <p>{t.emptyBody}</p>
        </div>
      ) : (
        <div className="gifts-card">
          {/* כותרות עמודות — בדסקטופ בלבד. במובייל כל מתנה היא כרטיס
              שקורא את עצמו, ולכן שורת כותרות רק הייתה מוסיפה רעש. */}
          <div className="gift-head" aria-hidden="true">
            <span>{t.colGuest}</span>
            <span>{t.colAmount}</span>
            <span>{t.colBlessing}</span>
            <span>{t.colDate}</span>
            <span>{t.colStatus}</span>
          </div>
          <ul className="gift-list">
            {data.gifts.map((g) => (
              <GiftListRow key={g.id} gift={g} />
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
