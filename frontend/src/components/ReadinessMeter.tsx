import type { Readiness } from '../readiness'

interface Props {
  readiness: Readiness
}

/**
 * מדד המוכנות להושבה — "מוכנים ל-X%". מציג טבעת התקדמות, מסר מעודד
 * וסיכום השלבים שהושלמו. ממליץ בלבד — לא חוסם שום פעולה.
 */
export function ReadinessMeter({ readiness }: Props) {
  const { percent, steps, message } = readiness
  const doneCount = steps.filter((s) => s.done).length

  const R = 34
  const C = 2 * Math.PI * R
  const filled = (percent / 100) * C

  return (
    <div className="readiness-card">
      <div className="readiness-ring">
        <svg viewBox="0 0 80 80" className="ring-svg" role="img"
          aria-label={`מוכנים ל-${percent} אחוז`}>
          <circle className="ring-bg" cx="40" cy="40" r={R} fill="none"
            strokeWidth="8" />
          <circle
            className="ring-fill"
            cx="40"
            cy="40"
            r={R}
            fill="none"
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={`${filled} ${C - filled}`}
            transform="rotate(-90 40 40)"
          />
        </svg>
        <div className="ring-center">
          <span className="ring-num">{percent}%</span>
        </div>
      </div>

      <div className="readiness-body">
        <h3 className="readiness-title">מוכנים ל-{percent}% להושבה</h3>
        <p className="readiness-msg">{message}</p>
        <div className="readiness-dots" aria-hidden="true">
          {steps.map((s) => (
            <span
              key={s.key}
              className={`readiness-dot ${s.done ? 'done' : ''}`}
              title={s.label}
            />
          ))}
          <span className="readiness-count">
            {doneCount} מתוך {steps.length} שלבים
          </span>
        </div>
      </div>
    </div>
  )
}
