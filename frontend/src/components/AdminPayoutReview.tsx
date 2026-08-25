import { useCallback, useEffect, useState } from 'react'
import {
  adminApprovePayout,
  adminFetchPayoutCertificate,
  adminListPayoutReviews,
  adminRejectPayout,
  adminReopenPayout,
  adminSetPayoutProviderStatus,
} from '../api'
import type { PayoutReviewRow } from '../types'
import './AdminPayoutReview.css'

/**
 * מסך בדיקת פרטי קבלת מתנות — צד VEYA.
 *
 * **מי שמזין את פרטי החשבון אינו מי שמאשר אותם.** המסך הזה קיים רק
 * באזור האדמין, וכל הנתיבים שמאחוריו דורשים הרשאת אדמין בשרת. בעל אירוע
 * או מפיק שינסה להגיע אליהם יקבל 403 — ההסתרה כאן היא נוחות, לא הגנה.
 *
 * שתי הבדיקות מוצגות בנפרד **כאן בלבד**, כי הן באמת נפרדות: אישור VEYA
 * אינו הופך את החשבון לכשיר, וגם אישור הספק לבדו לא. בעלי האירוע רואים
 * מצב אחד פשוט ולא את ההבחנה הזו — היא עניין תפעולי של VEYA.
 *
 * **אישור VEYA נועל את פרטי החשבון מיד.** מרגע האישור אין לבעלי האירוע
 * שום מסלול לשנות בנק, סניף, מספר חשבון או מסמך — לא ב-UI ולא ב-API.
 * "פתיחה מחדש" כאן היא הדרך היחידה לבטל את הנעילה.
 *
 * **כפתורי הספק אינם חלק מהתהליך.** הם כלי בדיקה עד שיחובר ספק אמיתי:
 * הם לא פונים לאף ספק ולא מדמים אישור אמיתי. לכן הם מקופלים בנפרד
 * ומסומנים ככאלה, ולא יושבים לצד פעולות הבדיקה האמיתיות.
 */

const REVIEW_LABELS: Record<PayoutReviewRow['veya_status'], string> = {
  pending: 'ממתין',
  approved: 'אושר',
  rejected: 'לא אושר',
}

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

function Track({ label, state }: { label: string; state: PayoutReviewRow['veya_status'] }) {
  return (
    <span className={`apr-track apr-track-${state}`}>
      {label}: <strong>{REVIEW_LABELS[state]}</strong>
    </span>
  )
}

function ReviewCard({
  row,
  onUpdated,
}: {
  row: PayoutReviewRow
  onUpdated: (next: PayoutReviewRow) => void
}) {
  const [busy, setBusy] = useState(false)
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function run(action: () => Promise<PayoutReviewRow>) {
    setError(null)
    setBusy(true)
    try {
      onUpdated(await action())
      setRejecting(false)
      setReason('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'הפעולה נכשלה, נסו שוב')
    } finally {
      setBusy(false)
    }
  }

  async function openCertificate() {
    // הלשונית נפתחת בתוך אירוע הלחיצה עצמו — אחרת הדפדפן חוסם אותה
    // כחלון קופץ. אותו טיפול כמו במסך של בעלי האירוע.
    const tab = window.open('', '_blank')
    try {
      const blob = await adminFetchPayoutCertificate(row.event_id)
      const url = URL.createObjectURL(blob)
      if (tab) tab.location.href = url
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch {
      tab?.close()
      setError('לא הצלחנו לפתוח את אישור ניהול החשבון')
    }
  }

  return (
    <article className="apr-card">
      <header className="apr-head">
        <div className="apr-who">
          <h3 className="apr-title">{row.event_title || `אירוע ${row.event_id}`}</h3>
          <p className="apr-owner">
            {row.owner_name}
            {row.owner_email ? ` · ${row.owner_email}` : ''}
          </p>
        </div>
        <div className="apr-tracks">
          <Track label="VEYA" state={row.veya_status} />
          <Track label="ספק סליקה" state={row.provider_status} />
        </div>
      </header>

      {/* פרטי החשבון — בדיוק מה שצריך כדי להצליב מול המסמך.
          מספר החשבון המלא אינו מגיע מהשרת גם לכאן. */}
      <dl className="apr-details">
        <div>
          <dt>בנק</dt>
          <dd>{row.bank_name} <span className="apr-code">({row.bank_code})</span></dd>
        </div>
        <div>
          <dt>סניף</dt>
          <dd className="apr-num">{row.branch_number}</dd>
        </div>
        <div>
          <dt>חשבון</dt>
          <dd className="apr-num">{row.account_number_masked}</dd>
        </div>
        <div>
          <dt>הוגש</dt>
          <dd>{formatDateTime(row.submitted_at) || '—'}</dd>
        </div>
      </dl>

      {row.rejection_reason && (
        <p className="apr-reason">סיבת דחייה קודמת של VEYA: {row.rejection_reason}</p>
      )}
      {row.provider_rejection_reason && (
        <p className="apr-reason">סיבת דחייה של הספק: {row.provider_rejection_reason}</p>
      )}
      {row.reviewed_by && (
        <p className="apr-trail">
          נבדק על ידי {row.reviewed_by} · {formatDateTime(row.reviewed_at)}
        </p>
      )}

      {error && <p className="apr-error" role="alert">{error}</p>}

      <div className="apr-actions">
        <button type="button" className="apr-btn apr-btn-ghost" onClick={openCertificate}
                disabled={!row.certificate}>
          {row.certificate ? 'צפייה באישור ניהול חשבון' : 'לא צורף אישור'}
        </button>
        <span className="apr-actions-spacer" />
        {/* חשבון מאושר נעול לבעלי האירוע, ולכן הפעולה היחידה עליו היא
            לפתוח אותו מחדש — לא לאשר שוב ולא לדחות. */}
        {row.veya_status === 'approved' ? (
          <button type="button" className="apr-btn apr-btn-reject" disabled={busy}
                  onClick={() => run(() => adminReopenPayout(row.event_id))}>
            פתיחה מחדש לעריכה
          </button>
        ) : (
          <>
            <button type="button" className="apr-btn apr-btn-approve" disabled={busy}
                    onClick={() => run(() => adminApprovePayout(row.event_id))}>
              אישור פרטי החשבון
            </button>
            <button type="button" className="apr-btn apr-btn-reject" disabled={busy}
                    onClick={() => setRejecting((v) => !v)}>
              דחייה
            </button>
          </>
        )}
      </div>

      {row.veya_status === 'approved' && (
        <p className="apr-trail">
          הפרטים אושרו ונעולים לשינוי אצל בעלי האירוע. פתיחה מחדש תבטל את
          האישור ותאפשר להם לתקן ולשלוח שוב.
        </p>
      )}

      {rejecting && (
        <div className="apr-reject-box">
          {/* סיבת הדחייה חובה — גם בשרת. בלעדיה בעלי האירוע מקבלים "נדחה"
              ולא יודעים מה לתקן, וזו דחייה שתחזור. */}
          <label className="apr-label" htmlFor={`apr-reason-${row.event_id}`}>
            סיבת הדחייה (תוצג לבעלי האירוע)
          </label>
          <textarea
            id={`apr-reason-${row.event_id}`}
            className="apr-textarea"
            rows={2}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="למשל: אישור ניהול החשבון אינו קריא"
          />
          <button
            type="button"
            className="apr-btn apr-btn-reject"
            disabled={busy || !reason.trim()}
            onClick={() => run(() => adminRejectPayout(row.event_id, reason.trim()))}
          >
            שליחת הדחייה
          </button>
        </div>
      )}

      {/* ── כלי בדיקה, לא חלק מהתהליך ──────────────────────────────────
          אין ספק סליקה מחובר, ולכן אין "תשובת ספק" אמיתית לרשום. הכפתורים
          כאן קיימים **רק** כדי שאפשר יהיה לבדוק את המסלול מקצה לקצה עד
          שיחובר ספק אמיתי — ואז הוא יכתוב את השדה בעצמו והם ייעלמו.

          מקופלים בכוונה: פעולה שאינה חלק מהעבודה השוטפת לא צריכה לשבת
          פתוחה לצד פעולות שכן. */}
      <details className="apr-tools">
        <summary className="apr-tools-summary">כלי בדיקה — אינו ספק סליקה אמיתי</summary>
        <p className="apr-tools-note">
          אין ספק סליקה מחובר. הכפתורים כאן מסמנים ידנית את תוצאת בדיקת
          הספק לצורכי בדיקה בלבד, ואינם פונים לאף גורם חיצוני.
        </p>
        <div className="apr-tools-row">
          <button type="button" className="apr-chip" disabled={busy}
                  onClick={() => run(() => adminSetPayoutProviderStatus(row.event_id, 'approved'))}>
            סימון כ"אושר"
          </button>
          <button type="button" className="apr-chip" disabled={busy}
                  onClick={() => run(() => adminSetPayoutProviderStatus(row.event_id, 'rejected', reason.trim()))}>
            סימון כ"לא אושר"
          </button>
          <button type="button" className="apr-chip" disabled={busy}
                  onClick={() => run(() => adminSetPayoutProviderStatus(row.event_id, 'pending'))}>
            איפוס להמתנה
          </button>
        </div>
      </details>
    </article>
  )
}

type Scope = 'pending' | 'approved'

const SCOPES: { key: Scope; label: string; intro: string; empty: string }[] = [
  {
    key: 'pending',
    label: 'ממתינים לבדיקה',
    intro:
      'חשבונות שהוגשו וממתינים לבדיקה. הוותיק ביותר ראשון. אישור נועל את ' +
      'פרטי החשבון אצל בעלי האירוע מיד, והוא אחת משתי בדיקות — הסכומים ' +
      'נפתחים להם רק אחרי שגם ספק הסליקה אישר.',
    empty: 'אין כרגע חשבונות שממתינים לבדיקה.',
  },
  {
    key: 'approved',
    label: 'מאושרים ונעולים',
    intro:
      'חשבונות שאושרו. בעלי האירוע אינם יכולים לשנות בהם בנק, סניף, מספר ' +
      'חשבון או מסמך. אם נדרש שינוי — פתיחה מחדש כאן היא הדרך היחידה, והיא ' +
      'מבטלת את האישור ומחזירה אותם לתחילת התהליך.',
    empty: 'אין כרגע חשבונות מאושרים.',
  },
]

export function AdminPayoutReview() {
  const [scope, setScope] = useState<Scope>('pending')
  const [rows, setRows] = useState<PayoutReviewRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    adminListPayoutReviews(scope)
      .then(setRows)
      .catch((e) => setError(e instanceof Error ? e.message : 'לא הצלחנו לטעון את הרשימה'))
      .finally(() => setLoading(false))
  }, [scope])

  useEffect(load, [load])

  const current = SCOPES.find((s) => s.key === scope) as (typeof SCOPES)[number]

  return (
    <div className="apr-page">
      {/* שתי רשימות ולא אחת: חשבון מאושר יוצא מתור הבדיקה, ובלי הלשונית
          השנייה לא הייתה שום דרך להגיע אליו כדי לפתוח אותו מחדש. */}
      <div className="apr-scopes" role="tablist">
        {SCOPES.map((s) => (
          <button
            key={s.key}
            type="button"
            role="tab"
            aria-selected={s.key === scope}
            className={`apr-scope${s.key === scope ? ' apr-scope--on' : ''}`}
            onClick={() => setScope(s.key)}
          >
            {s.label}
          </button>
        ))}
      </div>

      <p className="apr-intro">{current.intro}</p>

      {loading ? (
        <p className="apr-state">טוען…</p>
      ) : error ? (
        <p className="apr-state apr-state-error">{error}</p>
      ) : rows.length === 0 ? (
        <p className="apr-empty">{current.empty}</p>
      ) : (
        rows.map((row) => (
          <ReviewCard
            key={row.event_id}
            row={row}
            // הכרעה מוציאה את החשבון מהתור — טוענים אותו מחדש מהשרת
            // במקום לנחש מקומית מה עדיין ממתין.
            onUpdated={load}
          />
        ))
      )}
    </div>
  )
}
