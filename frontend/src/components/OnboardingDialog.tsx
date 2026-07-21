import { strings } from '../strings/he'

const t = strings.guests

interface Props {
  onClose: () => void
}

// שלושת היתרונות המרכזיים שמוצגים במסך הפתיחה — קצר, ברור, מרגיע.
const POINTS = t.onboardingPoints

/**
 * מסך פתיחה בכניסה הראשונה לאזור המוזמנים. מטרה: להרגיע ולהראות שהחלק
 * המלחיץ ביותר לפני האירוע הופך לפשוט. מוצג פעם אחת (דגל localStorage).
 */
export function OnboardingDialog({ onClose }: Props) {
  return (
    <div className="overlay" onClick={onClose}>
      <div
        className="dialog onboarding-dialog"
        onClick={(e) => e.stopPropagation()}
      >
        <button className="x" onClick={onClose}>
          ✕
        </button>

        <div className="onboarding-head">
          <h2>{t.onboardingTitle}</h2>
          <p className="onboarding-sub">{t.onboardingSub}</p>
        </div>

        <div className="onboarding-points">
          {POINTS.map((p) => (
            <div key={p.title} className="onboarding-point">
              <span className="onboarding-icon">{p.icon}</span>
              <div>
                <div className="onboarding-point-title">{p.title}</div>
                <div className="onboarding-point-text">{p.text}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="add-actions onboarding-actions">
          <button className="btn-primary" onClick={onClose}>
            {t.onboardingCta}
          </button>
        </div>
      </div>
    </div>
  )
}
