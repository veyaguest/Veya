import type { DashboardStats } from '../types'
import type { ReadinessPage } from '../readiness'
import { strings } from '../strings/he'

const t = strings.dashboard.prep

type StepState = 'not_started' | 'in_progress' | 'done'

interface PrepStep {
  key: string
  title: string
  state: StepState
  page: ReadinessPage | null
}

interface Props {
  stats: DashboardStats | null
  onNavigate?: (page: ReadinessPage) => void
}

export function SeatingPrep({ stats, onNavigate }: Props) {
  const total = stats?.total_guests ?? 0
  const groom = stats?.by_side?.groom ?? 0
  const bride = stats?.by_side?.bride ?? 0
  const sideAssigned = groom + bride
  const sideRatio = total > 0 ? sideAssigned / total : 0

  const other = (stats?.by_group?.['other'] as number | undefined) ?? 0
  const grouped = Math.max(0, total - other)
  const groupRatio = total > 0 ? grouped / total : 0

  const prefsCount =
    (stats?.guests_with_notes ?? 0) + (stats?.group_notes_count ?? 0)

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
    { key: 'side', title: t.steps[0].title, state: sideState, page: 'guests' },
    { key: 'groups', title: t.steps[1].title, state: groupState, page: 'guests' },
    { key: 'prefs', title: t.steps[2].title, state: prefState, page: 'guests' },
    { key: 'review', title: t.steps[3].title, state: reviewState, page: null },
  ]

  const doneCount = steps.filter((s) => s.state === 'done').length
  const allDone = doneCount === steps.length
  const currentIndex = steps.findIndex((s) => s.state !== 'done')
  const nextStep = currentIndex >= 0 ? steps[currentIndex] : null

  return (
    <div className="seatprep-card">
      <div className="seatprep-head">
        <h3 className="seatprep-title">{t.title}</h3>
        <span className="seatprep-progress">
          {t.progress(doneCount, steps.length)}
        </span>
      </div>

      <ol className="seatprep-steps">
        {steps.map((s, i) => {
          const locked = currentIndex >= 0 && i > currentIndex
          return (
            <li
              key={s.key}
              className={`seatprep-step ${s.state === 'done' ? 'done' : locked ? 'locked' : 'current'}`}
            >
              <span className="seatprep-check">
                {s.state === 'done' ? '✓' : '○'}
              </span>
              <span className="seatprep-step-label">{s.title}</span>
            </li>
          )
        })}
      </ol>

      <button
        type="button"
        className="seatprep-continue"
        disabled={allDone ? false : !nextStep?.page}
        onClick={() => {
          if (allDone) {
            onNavigate?.('hall')
          } else if (nextStep?.page) {
            onNavigate?.(nextStep.page)
          }
        }}
      >
        {allDone ? t.cta : 'המשך'}
      </button>
    </div>
  )
}
