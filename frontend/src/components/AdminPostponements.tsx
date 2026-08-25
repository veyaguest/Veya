import { useCallback, useEffect, useState } from 'react'
import {
  adminApprovePostponement,
  adminListPostponements,
  adminRejectPostponement,
} from '../api'
import type { PostponementReviewRow } from '../types'
import { getEventTerms } from '../strings/eventTypes'
import './AdminPayoutReview.css'
import './AdminPostponements.css'

/**
 * מסך אישור "נוהל דחייה" — צד VEYA.
 *
 * **מי שמבקש לדחות את האירוע אינו מי שמאשר את הדחייה.** המסך הזה קיים רק
 * באזור האדמין, וכל הנתיבים שמאחוריו דורשים הרשאת אדמין בשרת. בעל אירוע
 * שינסה להגיע אליהם יקבל 403 — ההסתרה כאן היא נוחות, לא הגנה.
 *
 * **האישור לא קובע תאריך.** הוא פותח לבעלי האירוע את פרטי האירוע לעריכה
 * מלאה ואת קטגוריית ההודעות "אירוע נדחה". מכאן הם עובדים לבד: מעדכנים
 * תאריך, קובעים מועד סגירת רשימה חדש, ופותחים מחזור אישורי-הגעה חדש —
 * פעולה שנשארת שלהם.
 *
 * **הדחייה קיימת כדי שהתור לא ייתקע.** בקשה שנפתחה בטעות חוסמת את בעלי
 * האירוע מלפתוח בקשה חדשה, ולכן צריך להיות אפשר להוריד אותה מהתור — עם
 * סיבה שהם רואים.
 */

function formatDateTime(iso: string | null): string {
  if (!iso) return ''
  const hasZone = /[Zz]|[+-]\d{2}:?\d{2}$/.test(iso)
  const d = new Date(hasZone ? iso : `${iso}Z`)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleString('he-IL', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

function formatDate(value: string): string {
  if (!value) return 'טרם נקבע'
  const d = new Date(value)
  if (isNaN(d.getTime())) return value
  return d.toLocaleDateString('he-IL', {
    day: '2-digit', month: '2-digit', year: 'numeric',
  })
}

function RequestCard({
  row,
  onDone,
}: {
  row: PostponementReviewRow
  onDone: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  const terms = getEventTerms(row.event_type)

  async function run(action: () => Promise<PostponementReviewRow>) {
    setError(null)
    setBusy(true)
    try {
      await action()
      onDone()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'הפעולה נכשלה, נסו שוב')
    } finally {
      setBusy(false)
    }
  }

  return (
    <article className="apr-card apo-card">
      <header className="apo-head">
        <div className="apo-title-wrap">
          <h3 className="apo-title">
            {terms.icon} {row.event_title || `אירוע #${row.event_id}`}
          </h3>
          <span className="apo-sub">
            {terms.label}
            {row.cycle_number > 1 ? ` · דחייה מספר ${row.cycle_number}` : ''}
          </span>
        </div>
        <span className={`apo-badge apo-badge-${row.status}`}>
          {row.status === 'pending' ? 'ממתין לאישור' : 'נוהל פעיל'}
        </span>
      </header>

      <dl className="apo-facts">
        <div>
          <dt>תאריך נוכחי</dt>
          <dd>
            {formatDate(row.event_date)}
            {row.event_time ? ` · ${row.event_time}` : ''}
          </dd>
        </div>
        <div>
          <dt>מקום</dt>
          <dd>{row.venue_name || '—'}</dd>
        </div>
        <div>
          <dt>מוזמנים</dt>
          <dd>
            {row.guests_total} · מהם {row.guests_confirmed} אישרו הגעה
          </dd>
        </div>
        <div>
          <dt>בעלי האירוע</dt>
          <dd>
            {row.owner_name || '—'}
            {row.owner_email ? ` · ${row.owner_email}` : ''}
          </dd>
        </div>
        <div>
          <dt>הבקשה הוגשה</dt>
          <dd>
            {formatDateTime(row.requested_at)}
            {row.requested_by_name ? ` · ${row.requested_by_name}` : ''}
          </dd>
        </div>
        {row.reviewed_at && (
          <div>
            <dt>אושר</dt>
            <dd>
              {formatDateTime(row.reviewed_at)}
              {row.reviewed_by ? ` · ${row.reviewed_by}` : ''}
            </dd>
          </div>
        )}
      </dl>

      {error && <p className="apr-state-error apo-error">{error}</p>}

      {row.status === 'pending' && (
        <>
          <p className="apo-note">
            אישור פותח לזוג עריכה מלאה של פרטי האירוע ואת נוסחי הודעת הדחייה.
            התאריך החדש נקבע על ידם, לא כאן.
          </p>
          <div className="apo-actions">
            <button
              type="button"
              className="apr-btn apr-btn-approve"
              disabled={busy}
              onClick={() => run(() => adminApprovePostponement(row.event_id))}
            >
              אישור נוהל דחייה
            </button>
            <button
              type="button"
              className="apr-btn"
              disabled={busy}
              onClick={() => setRejecting((v) => !v)}
            >
              {rejecting ? 'ביטול' : 'דחיית הבקשה'}
            </button>
          </div>
        </>
      )}

      {rejecting && (
        <div className="apo-reject">
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="למשל: הבקשה נפתחה בטעות — האירוע מתקיים כמתוכנן"
          />
          <button
            type="button"
            className="apr-btn apr-btn-reject"
            disabled={busy || !reason.trim()}
            onClick={() =>
              run(() => adminRejectPostponement(row.event_id, reason.trim()))
            }
          >
            שליחת הדחייה
          </button>
        </div>
      )}
    </article>
  )
}

type Scope = 'pending' | 'approved'

const SCOPES: { key: Scope; label: string; intro: string; empty: string }[] = [
  {
    key: 'pending',
    label: 'ממתינים לאישור',
    intro:
      'בקשות לפתיחת נוהל דחייה. הוותיקה ביותר ראשונה. אישור פותח לבעלי ' +
      'האירוע עריכה מלאה של פרטי האירוע — הוא אינו קובע תאריך חדש, וגם לא ' +
      'מאפס אישורי הגעה. שני אלה נעשים על ידם, בקצב שלהם.',
    empty: 'אין כרגע בקשות שממתינות לאישור.',
  },
  {
    key: 'approved',
    label: 'נהלים פעילים',
    intro:
      'נהלים שאושרו ובעלי האירוע עדיין עובדים עליהם. הנוהל נסגר כשהם ' +
      'פותחים מחזור אישורי-הגעה חדש, ואז פרטי האירוע ננעלים שוב.',
    empty: 'אין כרגע נהלי דחייה פעילים.',
  },
]

export function AdminPostponements() {
  const [scope, setScope] = useState<Scope>('pending')
  const [rows, setRows] = useState<PostponementReviewRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    adminListPostponements(scope)
      .then(setRows)
      .catch((e) =>
        setError(e instanceof Error ? e.message : 'לא הצלחנו לטעון את הרשימה'),
      )
      .finally(() => setLoading(false))
  }, [scope])

  useEffect(load, [load])

  const current = SCOPES.find((s) => s.key === scope) as (typeof SCOPES)[number]

  return (
    <div className="apr-page">
      {/* שתי רשימות ולא אחת: בקשה שאושרה יוצאת מהתור, ובלי הלשונית השנייה
          לא הייתה שום דרך לראות אילו נהלים פתוחים כרגע במערכת. */}
      <div className="apr-scopes" role="tablist">
        {SCOPES.map((s) => (
          <button
            key={s.key}
            type="button"
            role="tab"
            aria-selected={scope === s.key}
            className={`apr-scope ${scope === s.key ? 'active' : ''}`}
            onClick={() => setScope(s.key)}
          >
            {s.label}
          </button>
        ))}
      </div>

      <p className="apo-intro">{current.intro}</p>

      {loading && <p className="apr-state">טוענים…</p>}
      {error && <p className="apr-state apr-state-error">{error}</p>}
      {!loading && !error && rows.length === 0 && (
        <p className="apr-state">{current.empty}</p>
      )}

      {!loading &&
        !error &&
        rows.map((row) => (
          <RequestCard key={row.request_id} row={row} onDone={load} />
        ))}
    </div>
  )
}
