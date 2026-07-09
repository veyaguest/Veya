import { useState } from 'react'
import { generateSeating } from '../api'
import type { SeatingResult } from '../types'
import { GROUP_LABELS, SIDE_LABELS } from '../types'

export function SeatingPage() {
  const [seats, setSeats] = useState(12)
  const [result, setResult] = useState<SeatingResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function onGenerate() {
    setLoading(true)
    setError('')
    try {
      setResult(await generateSeating({ seats_per_table: seats }))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בשיבוץ')
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="seating-page">
      <div className="toolbar">
        <label className="seats-field">
          כיסאות לשולחן
          <input
            type="number"
            min={1}
            value={seats}
            onChange={(e) => setSeats(Math.max(1, Number(e.target.value) || 1))}
          />
        </label>
        <button className="btn-primary" onClick={onGenerate} disabled={loading}>
          {loading ? 'משבץ…' : 'צור שיבוץ'}
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}

      {result && (
        <>
          <div className="seating-summary">
            <span>
              {result.total_people} אנשים · {result.num_tables} שולחנות ·{' '}
              {result.seats_per_table} כיסאות לשולחן
            </span>
            {result.hard_ok ? (
              <span className="ok-badge">כל החוקים הקשיחים נשמרו ✓</span>
            ) : (
              <span className="err-badge">נמצאו הפרות חוקים ✕</span>
            )}
          </div>

          <div className="tables-grid">
            {result.tables.map((t) => (
              <div className="table-card" key={t.table_number}>
                <div className="table-head">
                  <span className="table-name">שולחן {t.table_number}</span>
                  <span className="table-occupancy">
                    {t.seats_used}/{t.capacity}
                  </span>
                </div>
                <ul className="party-list">
                  {t.parties.map((p) => (
                    <li key={p.id}>
                      <span className="party-name">{p.full_name}</span>
                      {p.party_size > 1 && (
                        <span className="party-size">×{p.party_size}</span>
                      )}
                      <span className="party-tags">
                        {SIDE_LABELS[p.side]} · {GROUP_LABELS[p.group_type]}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </>
      )}

      {!result && !error && !loading && (
        <div className="empty">
          בחר כמות כיסאות לשולחן ולחץ "צור שיבוץ" כדי לחלק את המוזמנים לשולחנות.
        </div>
      )}
    </div>
  )
}
