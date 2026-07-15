import type { Readiness, ReadinessPage } from '../readiness'

interface Props {
  readiness: Readiness
  onNavigate?: (page: ReadinessPage) => void
}

/**
 * אשף ההכנה — חמישה שלבים שמובילים את הזוג מרשימת מוזמנים ועד הושבה מוכנה:
 * ייבוא → קבוצות → העדפות → מפת אולם → סידור הושבה. כל שלב מקשר למסך קיים,
 * ומודגש השלב הבא שכדאי להשלים. ממליץ בלבד — אפשר לגשת לכל שלב בכל רגע.
 */
export function PrepWizard({ readiness, onNavigate }: Props) {
  const { steps, nextIndex } = readiness
  const next = nextIndex >= 0 ? steps[nextIndex] : null

  return (
    <div className="wizard-card">
      <div className="wizard-head">
        <h3 className="wizard-title">אשף ההכנה להושבה</h3>
        {next && (
          <button
            className="btn-primary btn-sm"
            onClick={() => onNavigate?.(next.page)}
          >
            {next.cta} →
          </button>
        )}
      </div>

      <ol className="wizard-steps">
        {steps.map((s, i) => {
          const state = s.done ? 'done' : i === nextIndex ? 'current' : 'todo'
          return (
            <li key={s.key} className={`wizard-step ${state}`}>
              <button
                type="button"
                className="wizard-step-btn"
                onClick={() => onNavigate?.(s.page)}
                title={s.desc}
              >
                <span className="wizard-num">{s.done ? '✓' : i + 1}</span>
                <span className="wizard-step-text">
                  <span className="wizard-step-label">{s.label}</span>
                  <span className="wizard-step-desc">{s.desc}</span>
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
