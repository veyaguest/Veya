import type { DashboardStats } from '../types'
import type { ReadinessPage } from '../readiness'
import { activeEventTerms } from '../strings/eventTypes'
import { strings } from '../strings/he'

const t = strings.dashboard.prep

type StepState = 'not_started' | 'in_progress' | 'done'

interface PrepStep {
  key: string
  title: string
  desc: string
  state: StepState
  // מסך שאליו השלב מנווט; null = שלב סקירה שמתבצע בתוך העמוד (בלי ניווט).
  page: ReadinessPage | null
}

interface Props {
  stats: DashboardStats | null
  onNavigate?: (page: ReadinessPage) => void
}

/**
 * "הכנה להושבה" — מוביל את הזוג בארבעה שלבים קצרים (צד → קבוצות → העדפות →
 * סקירה) עד לכפתור "הושבה בקליק". כל שלב מציג סטטוס אמיתי הנגזר מנתוני
 * הדשבורד, נפתח רק אחרי השלמת הקודם, וניתן לחזור אליו בכל רגע. ממליץ ומזמין —
 * המסר: "אנחנו רק מספרים ל-VEYA כמה דברים, והמערכת עושה את רוב העבודה".
 */
export function SeatingPrep({ stats, onNavigate }: Props) {
  const total = stats?.total_guests ?? 0
  const groom = stats?.by_side?.groom ?? 0
  const bride = stats?.by_side?.bride ?? 0
  const sideAssigned = groom + bride
  const sideRatio = total > 0 ? sideAssigned / total : 0

  const other = (stats?.by_group?.['other'] as number | undefined) ?? 0
  const grouped = Math.max(0, total - other)
  const groupRatio = total > 0 ? grouped / total : 0
  const groupsCount = stats
    ? Object.entries(stats.by_group).filter(
        ([k, v]) => k !== 'other' && (v as number) > 0,
      ).length
    : 0

  const prefsCount =
    (stats?.guests_with_notes ?? 0) + (stats?.group_notes_count ?? 0)

  // שלב "בתהליך" כשחלק מהמוזמנים כבר טופלו; "הושלם" מ-80% ומעלה (מרווח נשימה
  // ל"משותף"/"אחר" בודדים שלא חייבים שיוך).
  const sideState: StepState =
    sideAssigned === 0
      ? 'not_started'
      : sideRatio >= 0.8
        ? 'done'
        : 'in_progress'
  const groupState: StepState =
    grouped === 0 ? 'not_started' : groupRatio >= 0.8 ? 'done' : 'in_progress'
  const prefState: StepState = prefsCount > 0 ? 'done' : 'not_started'
  const reviewState: StepState =
    sideState === 'done' && groupState === 'done' && prefState === 'done'
      ? 'done'
      : 'not_started'

  const steps: PrepStep[] = [
    { key: 'side', ...t.steps[0], state: sideState, page: 'guests' },
    { key: 'groups', ...t.steps[1], state: groupState, page: 'guests' },
    { key: 'prefs', ...t.steps[2], state: prefState, page: 'guests' },
    { key: 'review', ...t.steps[3], state: reviewState, page: null },
  ]

  const doneCount = steps.filter((s) => s.state === 'done').length
  const allDone = doneCount === steps.length
  // השלב הפעיל = הראשון שעדיין לא הושלם; כל מה שאחריו נעול עד שמשלימים אותו.
  const currentIndex = steps.findIndex((s) => s.state !== 'done')

  const stateLabel: Record<StepState, string> = {
    not_started: t.stateNotStarted,
    in_progress: t.stateInProgress,
    done: t.stateDone,
  }

  const showSummary = reviewState === 'done' || currentIndex === 3

  return (
    <div className="seatprep-card">
      <div className="seatprep-head">
        <h3 className="seatprep-title">{t.title}</h3>
        <span className="seatprep-progress">
          {t.progress(doneCount, steps.length)}
        </span>
      </div>
      <p className="seatprep-intro">{t.intro}</p>

      <ol className="seatprep-steps">
        {steps.map((s, i) => {
          const locked = currentIndex >= 0 && i > currentIndex
          const phase =
            s.state === 'done' ? 'done' : locked ? 'locked' : 'current'
          // שלב הסקירה (page=null) אינו מנווט — אין טעם ללחוץ עליו.
          const noAction = locked || s.page === null
          return (
            <li key={s.key} className={`seatprep-step ${phase}`}>
              <button
                type="button"
                className="seatprep-step-btn"
                disabled={noAction}
                onClick={() => s.page && onNavigate?.(s.page)}
              >
                <span className="seatprep-num">
                  {s.state === 'done' ? '✓' : locked ? '🔒' : i + 1}
                </span>
                <span className="seatprep-step-text">
                  <span className="seatprep-step-label">{s.title}</span>
                  <span className="seatprep-step-desc">{s.desc}</span>
                </span>
                <span className={`seatprep-badge ${s.state}`}>
                  {stateLabel[s.state]}
                </span>
              </button>
            </li>
          )
        })}
      </ol>

      {showSummary && (
        <p className="seatprep-summary">
          {t.reviewSummary({
            total,
            groom,
            bride,
            groups: groupsCount,
            prefs: prefsCount,
            sideALabel: activeEventTerms().sideLabels.groom,
            sideBLabel: activeEventTerms().sideLabels.bride,
          })}
        </p>
      )}

      <div className="seatprep-cta-wrap">
        <button
          type="button"
          className="seatprep-cta"
          disabled={!allDone}
          onClick={() => onNavigate?.('hall')}
        >
          {t.cta}
        </button>
        <p className="seatprep-cta-hint">
          {allDone ? t.ctaHint : t.ctaLockedHint}
        </p>
      </div>
    </div>
  )
}
