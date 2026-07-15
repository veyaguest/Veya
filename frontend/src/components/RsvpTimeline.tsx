import { useCallback, useEffect, useState } from 'react'
import { getRsvpTimeline } from '../api'
import type { RsvpTimelineView, TimelineAction, TimelineDay } from '../types'

/**
 * יומן המשימות של אישורי-ההגעה — לוח זמנים יומי לזוג, שנבנה *לאחור* מיום
 * ההתחייבות לאולם. מרגיש כמו יומן משימות אישי: היום, מחר, וכל מה שמתוכנן
 * עד שהרשימה סופית. תצוגה בלבד (Phase 1) — עדיין לא שולחים בפועל.
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
      setError(err instanceof Error ? err.message : 'לא הצלחנו לטעון את היומן, ננסה שוב')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return <p className="mb-empty">רגע, מכינים לכם את יומן המשימות…</p>
  }

  if (error) {
    return <p className="form-error">{error}</p>
  }

  // עדיין לא בחרו יום התחייבות — מזמינים אותם להגדיר במסך הפרטים.
  if (!view || !view.configured) {
    return (
      <div className="tl-empty">
        <span className="tl-empty-icon" aria-hidden>🗓️</span>
        <h3 className="tl-empty-title">כאן יופיע יומן המשימות שלכם</h3>
        <p className="tl-empty-sub">
          כדי שנבנה לכם לוח זמנים אישי לאישורי ההגעה, השלימו במסך "סקירה" את
          תאריך החתונה ובחרו כמה ימים לפני האירוע צריך למסור לאולם מספר סופי.
          אנחנו נתכנן לבד את כל השאר.
        </p>
      </div>
    )
  }

  return (
    <div className="tl-wrap">
      <TimelineHeader view={view} />
      <TodayTomorrow view={view} />
      <DayScale view={view} />
    </div>
  )
}

/** כותרת עליונה — ספירה ליום ההתחייבות + מצב מסלול מקוצר. */
function TimelineHeader({ view }: { view: RsvpTimelineView }) {
  const days = view.days_to_commitment
  return (
    <div className="tl-header">
      <span className="track-hero-badge">יומן אישורי ההגעה</span>
      <h2 className="tl-header-title">לוח הזמנים האישי שלכם</h2>
      <p className="tl-header-sub">
        בנינו לכם לוח זמנים שמסתיים ביום ההתחייבות לאולם ({view.commitment_date})
        — היום שבו נדע בדיוק מי מגיע ומי לא.
      </p>

      <div className="tl-header-stats">
        <TlStat
          num={days != null && days >= 0 ? days : '—'}
          label="ימים ליום ההתחייבות"
        />
        <TlStat num={view.confirmed_count} label="אישרו הגעה" tone="ok" />
        <TlStat num={view.pending_count} label="עדיין לא ענו" tone="wait" />
        <TlStat num={view.total_guests} label="סה״כ מוזמנים" />
      </div>

      {view.compressed && (
        <p className="tl-compressed">
          ⏳ נשאר מעט זמן עד יום ההתחייבות, אז בנינו עבורכם מסלול מקוצר וחכם
          שמספיק כמה שיותר אישורים בזמן שנותר.
        </p>
      )}
    </div>
  )
}

/** שני כרטיסים בולטים: מה קורה היום ומה מחר. */
function TodayTomorrow({ view }: { view: RsvpTimelineView }) {
  return (
    <div className="tl-now">
      <div className="tl-now-card today">
        <span className="tl-now-tag">היום · {view.today}</span>
        <p className="tl-now-text">{view.today_summary}</p>
      </div>
      <div className="tl-now-card tomorrow">
        <span className="tl-now-tag">מחר</span>
        <p className="tl-now-text">{view.tomorrow_summary}</p>
      </div>
    </div>
  )
}

/** ציר הזמן היומי — כרטיס לכל יום, מהיום ועד יום האירוע. */
function DayScale({ view }: { view: RsvpTimelineView }) {
  if (view.days.length === 0) return null
  return (
    <div className="tl-scale">
      <h3 className="clar-title">כל התחנות בדרך</h3>
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
    day.is_tomorrow ? 'is-tomorrow' : '',
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
          {day.is_tomorrow && <span className="tl-tag soon">מחר</span>}
          {day.is_commitment && (
            <span className="tl-tag commit">יום ההתחייבות</span>
          )}
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

function ActionRow({ action }: { action: TimelineAction }) {
  return (
    <li className="tl-action">
      <span className="tl-action-icon" aria-hidden>
        {action.icon}
      </span>
      <span className="tl-action-main">
        <span className="tl-action-label">{action.label}</span>
        <span className="tl-action-meta">
          {action.audience} · {action.audience_count} מוזמנים
          {action.moved_from_weekend && (
            <span className="tl-moved"> · הוזז ליום ראשון בגלל סוף השבוע</span>
          )}
        </span>
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
