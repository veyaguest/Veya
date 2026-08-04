import type { DashboardStats } from '../types'
import type { ReadinessPage } from '../readiness'
import { strings } from '../strings/he'

const t = strings.dashboard.prep

interface Props {
  stats: DashboardStats
  onNavigate?: (page: ReadinessPage) => void
}

export function SeatingPrep({ stats, onNavigate }: Props) {
  return (
    <div className="seating-widget">
      <div className="seating-widget-text">
        <h3 className="seating-widget-title">{t.title}</h3>
        <p className="seating-widget-progress">
          {t.seatedProgress(stats.seated_guests, stats.total_guests)}
        </p>
      </div>
      <button
        type="button"
        className="seating-widget-btn"
        onClick={() => onNavigate?.('hall')}
      >
        {t.openDesigner}
      </button>
    </div>
  )
}
