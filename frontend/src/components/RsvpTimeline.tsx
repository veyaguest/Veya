import { useCallback, useEffect, useState } from 'react'
import { getRsvpTimeline } from '../api'
import type { RsvpTimelineView, TimelineAction, TimelineDay } from '../types'
import { strings } from '../strings/he'

/**
 * יומן המשימות של אישורי-ההגעה — לוח זמנים יומי לזוג, שנבנה *לאחור*
 * ממועד סגירת הרשימה. מרגיש כמו יומן משימות אישי: היום וכל מה שמתוכנן עד
 * שהרשימה סופית.
 *
 * שלבי ה-WhatsApp שבלוח (בקשת אישור ראשונה + שלוש התזכורות) מחוברים למנגנון
 * השליחה בפועל — נשלחים אוטומטית בתאריך שמוצג. סבבי השיחות הם פעולת מוקד.
 */
export function RsvpTimeline() {
  const [view, setView] = useState<RsvpTimelineView | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      setView(await getRsvpTimeline())
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.timelineLoadFailed)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return <p className="load-text">מכינים את לוח אישורי ההגעה…</p>
  }

  if (error) {
    return <p className="form-error" role="alert">{error}</p>
  }

  // עדיין לא בחרו מועד סגירת רשימה — מזמינים אותם להגדיר במסך הפרטים.
  if (!view || !view.configured) {
    return (
      <div className="tl-empty">
        <span className="tl-empty-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3.5" y="5.5" width="17" height="15" rx="2.5" />
            <path d="M3.5 10h17M8.5 3.5v4M15.5 3.5v4" />
            <path d="M8.8 14.6l2 2 4-4" />
          </svg>
        </span>
        <h3 className="tl-empty-title">לוח אישורי ההגעה עוד לא נקבע</h3>
        <p className="tl-empty-sub">
          עדכנו ב<strong>תמונת מצב</strong> את תאריך האירוע, ובחרו כמה ימים
          לפני האירוע צריך למסור לאולם את המספר הסופי.
        </p>
        <p className="tl-empty-sub">
          משם נבנה את לוח אישורי ההגעה לאחור — תזכורות ושיחות טלפון — כדי
          שתגיעו לאירוע עם מספר מדויק.
        </p>
      </div>
    )
  }

  return (
    <div className="tl-wrap">
      <TimelineHeader view={view} />
      {/* כרטיס "מה קורה היום" — רק כשבאמת יש פעילות היום. אין פעילות → אין
          מה להציג (הודעה "אין פעילות מתוכננת" היא רעש טכני לבעל האירוע). */}
      {view.today_summary && <TodayCard view={view} />}
      <DayScale view={view} />
    </div>
  )
}

/** כותרת עליונה — ספירה למועד סגירת הרשימה + מצב מסלול מקוצר. */
function TimelineHeader({ view }: { view: RsvpTimelineView }) {
  const days = view.days_to_commitment
  return (
    <div className="tl-header">
      <span className="track-hero-badge">יומן אישורי ההגעה</span>
      <h2 className="tl-header-title">עד שנדע כמה מגיעים</h2>
      <p className="tl-header-sub">
        כאן תוכלו לראות את השלבים הקרובים עד סגירת רשימת המוזמנים.
      </p>

      <div className="tl-header-stats">
        <TlStat
          num={days != null && days >= 0 ? days : '—'}
          label="ימים למועד סגירת הרשימה"
        />
        <TlStat num={view.confirmed_count} label="אישרו הגעה" tone="ok" />
        <TlStat num={view.pending_count} label="ממתינים לתשובה" tone="wait" />
        <TlStat num={view.total_guests} label="סה״כ מוזמנים" />
      </div>

      {view.compressed && (
        <div className="tl-compressed">
          <strong className="tl-compressed-title">נשאר מעט זמן עד סגירת הרשימה</strong>
          <p className="tl-compressed-text">
            נמשיך מכאן עם הצעדים החשובים כדי להגיע לכמה שיותר תשובות בזמן.
          </p>
        </div>
      )}
    </div>
  )
}

/** כרטיס בולט אחד: מה קורה היום. אין כרטיס 'מחר' — ב-VEYA אין הודעת
 *  "מחר מתראים", רק הודעת יום האירוע. */
function TodayCard({ view }: { view: RsvpTimelineView }) {
  return (
    <div className="tl-now">
      <div className="tl-now-card today">
        <span className="tl-now-tag">היום · {view.today}</span>
        <p className="tl-now-text">{view.today_summary}</p>
      </div>
    </div>
  )
}

/** ציר הזמן היומי — כרטיס לכל יום, מהיום ועד יום האירוע. */
function DayScale({ view }: { view: RsvpTimelineView }) {
  if (view.days.length === 0) return null
  return (
    <div className="tl-scale">
      <h3 className="clar-title">מסלול אישורי הגעה</h3>
      <ol className="tl-days">
        {view.days.map((day) => (
          <DayRow key={day.iso} day={day} />
        ))}
      </ol>
    </div>
  )
}

function DayRow({ day }: { day: TimelineDay }) {
  const cls = [
    'tl-day',
    day.is_today ? 'is-today' : '',
    day.is_past ? 'is-past' : '',
    day.is_commitment ? 'is-commitment' : '',
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <li className={cls}>
      <div className="tl-day-marker" aria-hidden>
        <span className="tl-day-dot" />
      </div>
      <div className="tl-day-body">
        <div className="tl-day-head">
          <span className="tl-day-date">
            {day.weekday} · {day.date}
          </span>
          {day.is_today && <span className="tl-tag now">היום</span>}
          {/* אין תגית "מועד סגירת הרשימה" נפרדת — הכרטיס של סבב השיחות
              האחרון כבר אומר "וסגירת הרשימה". רק הדגשה ויזואלית (is-commitment). */}
        </div>

        {day.actions.length === 0 ? (
          <p className="tl-day-empty">אין פעילות מתוכננת</p>
        ) : (
          <ul className="tl-actions">
            {day.actions.map((a, i) => (
              <ActionRow key={i} action={a} />
            ))}
          </ul>
        )}
      </div>
    </li>
  )
}

/* אייקון לכל סוג פעולה בלוח הזמנים.
 *
 * השרת מחזיר גם שדה ``icon`` עם אימוג'י (✅ 📩 📞 🎉), אבל אנחנו נגזרים
 * מ-``type`` ומתעלמים ממנו: אימוג'י בעמודה אנכית של פעולות נראה שונה בכל
 * מערכת הפעלה ואי אפשר לצבוע אותו לפי מצב השלב (עבר/היום/עתידי).
 * ה-API לא השתנה — רק מה שמוצג ממנו. */
const ACTION_ICON: Record<string, string> = {
  whatsapp_first: 'M20.5 12.4c0 4-3.8 7.2-8.5 7.2a9.7 9.7 0 0 1-2.6-.35L4.5 20.5l1.3-3.5A6.9 6.9 0 0 1 3.5 12.4c0-4 3.8-7.2 8.5-7.2s8.5 3.2 8.5 7.2Z',
  reminder: 'M18 16.5V11a6 6 0 1 0-12 0v5.5L4.5 18.5h15L18 16.5ZM10 21h4',
  call_round: 'M8.6 4.8H6.4A1.9 1.9 0 0 0 4.5 6.9c0 6.9 5.7 12.6 12.6 12.6a1.9 1.9 0 0 0 1.9-1.9v-2.2l-3.8-1.3-1.6 1.9a13.9 13.9 0 0 1-5.4-5.4l1.9-1.6L8.6 4.8Z',
  day_of: 'M5 4h6l-1.2 6a1.8 1.8 0 0 1-3.6 0L5 4ZM8 12.2V20M6 20h4M14 6.5h6l-1.2 6a1.8 1.8 0 0 1-3.6 0l-1.2-6ZM17 14.7V20M15 20h4',
}

function ActionRow({ action }: { action: TimelineAction }) {
  return (
    <li className="tl-action">
      <span className="tl-action-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d={ACTION_ICON[action.type] ?? ACTION_ICON.reminder} />
        </svg>
      </span>
      <span className="tl-action-main">
        <span className="tl-action-label">{action.label}</span>
        <span className="tl-action-meta">
          {/* התאריך שבו ההודעה תישלח בפועל מוצג בכותרת היום. פרטים פנימיים
              של תזמון (הזזה מסוף שבוע וכו') לא רלוונטיים לבעל האירוע. */}
          {action.audience} · {action.audience_count} מוזמנים
        </span>
        {action.note && <span className="tl-action-note">{action.note}</span>}
      </span>
    </li>
  )
}

function TlStat({
  num,
  label,
  tone,
}: {
  num: number | string
  label: string
  tone?: 'ok' | 'wait'
}) {
  return (
    <div className={`tl-stat ${tone ?? ''}`}>
      <span className="tl-stat-num">{num}</span>
      <span className="tl-stat-label">{label}</span>
    </div>
  )
}
