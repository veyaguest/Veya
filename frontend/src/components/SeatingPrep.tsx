import type { DashboardStats } from '../types'
import type { ReadinessPage } from '../readiness'
import { strings } from '../strings/he'

const t = strings.dashboard.prep

interface Props {
  stats: DashboardStats | null
  onNavigate?: (page: ReadinessPage) => void
}

export function SeatingPrep({ onNavigate }: Props) {
  return (
    <div className="seating-hero">
      <h3 className="seating-hero-title">{t.title}</h3>
      <p className="seating-hero-subtitle">{t.subtitle}</p>

      <ul className="seating-hero-benefits">
        {t.benefits.map((b, i) => (
          <li key={i} className="seating-hero-benefit">
            <span className="seating-hero-benefit-icon">{b.icon}</span>
            <span className="seating-hero-benefit-text">{b.text}</span>
          </li>
        ))}
      </ul>

      <button
        type="button"
        className="seating-hero-cta"
        onClick={() => onNavigate?.('guests')}
      >
        {t.cta}
      </button>
    </div>
  )
}
