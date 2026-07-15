interface Props {
  onClose: () => void
}

// שלושת היתרונות המרכזיים שמוצגים במסך הפתיחה — קצר, ברור, מרגיע.
const POINTS = [
  {
    icon: '📋',
    title: 'מדביקים רשימה — וזהו',
    text: 'רשימה מ-WhatsApp, מאקסל או מכל מקום. VEYA מזהה לבד שם, טלפון וכמות.',
  },
  {
    icon: '✨',
    title: 'קבוצות מסתדרות מעצמן',
    text: 'אנחנו מציעים לכם לאחד משפחות וחברים לקבוצות — אתם רק מאשרים.',
  },
  {
    icon: '🎉',
    title: 'הושבה בקליק',
    text: 'כשהכול מוכן, VEYA מסדרת את השולחנות לפי הקשרים וההעדפות שלכם.',
  },
]

/**
 * מסך פתיחה בכניסה הראשונה לאזור המוזמנים. מטרה: להרגיע ולהראות שהחלק
 * המלחיץ ביותר לפני החתונה הופך לפשוט. מוצג פעם אחת (דגל localStorage).
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
          <h2>חסכו לעצמכם שעות של כאב ראש לפני החתונה</h2>
          <p className="onboarding-sub">
            ניהול המוזמנים והושבה הם החלק הכי מלחיץ. VEYA כאן כדי לעשות אותו
            פשוט — צעד אחר צעד, בלי גיליונות מסובכים.
          </p>
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
            בואו נתחיל
          </button>
        </div>
      </div>
    </div>
  )
}
