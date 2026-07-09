import { useCallback, useEffect, useState } from 'react'
import {
  analyzeConstraints,
  generateSeating,
  listClarifications,
  resolveClarification,
} from '../api'
import type { AnalyzeResult, Clarification, SeatingResult } from '../types'
import { GROUP_LABELS, SIDE_LABELS } from '../types'

const REL_TEXT: Record<Clarification['relation_type'], string> = {
  avoid: 'לא לשבת עם',
  together: 'לשבת עם',
}

export function SeatingPage() {
  const [seats, setSeats] = useState(12)
  const [result, setResult] = useState<SeatingResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const [clarifications, setClarifications] = useState<Clarification[]>([])
  const [summary, setSummary] = useState<AnalyzeResult | null>(null)
  const [analyzing, setAnalyzing] = useState(false)

  const loadClarifications = useCallback(async () => {
    try {
      setClarifications(await listClarifications())
    } catch {
      /* שקט — לא חוסם את מסך השיבוץ */
    }
  }, [])

  useEffect(() => {
    loadClarifications()
  }, [loadClarifications])

  async function onAnalyze() {
    setAnalyzing(true)
    setError('')
    try {
      setSummary(await analyzeConstraints())
      await loadClarifications()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בניתוח ההערות')
    } finally {
      setAnalyzing(false)
    }
  }

  async function onResolve(id: number, chosenGuestId: number | null) {
    try {
      const res = await resolveClarification(id, chosenGuestId)
      setSummary(res)
      await loadClarifications()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בפתרון ההבהרה')
    }
  }

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
      {/* ---- אילוצים מההערות ---- */}
      <div className="clar-panel">
        <div className="clar-head">
          <div>
            <h3 className="clar-title">אילוצים מההערות</h3>
            <p className="clar-sub">
              המערכת קוראת את ההערות החופשיות והופכת אותן לכללי הושבה ("לא
              לשבת עם", "לשבת ליד").
            </p>
          </div>
          <button className="btn-ghost" onClick={onAnalyze} disabled={analyzing}>
            {analyzing ? 'מנתח…' : '↻ נתח הערות'}
          </button>
        </div>

        {summary && (
          <p className="clar-summary">
            נותחו {summary.guests_analyzed} מוזמנים · {summary.resolved} אילוצים
            זוהו · {summary.pending_clarifications} ממתינים להבהרה
          </p>
        )}

        {clarifications.length > 0 ? (
          <div className="clar-list">
            {clarifications.map((c) => (
              <div className="clar-card" key={c.id}>
                <div className="clar-q">
                  <strong>{c.source_guest_name}</strong> ביקש/ה{' '}
                  {REL_TEXT[c.relation_type]} "<strong>{c.target_text}</strong>" —
                  למי הכוונה?
                </div>
                <div className="clar-actions">
                  {c.candidates.map((cand) => (
                    <button
                      key={cand.id}
                      className="btn-ghost clar-choice"
                      onClick={() => onResolve(c.id, cand.id)}
                    >
                      {cand.full_name}
                    </button>
                  ))}
                  <button
                    className="btn-text"
                    onClick={() => onResolve(c.id, null)}
                  >
                    אף אחד מהם
                  </button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          summary && <p className="clar-ok">אין הבהרות ממתינות ✓</p>
        )}
      </div>

      {/* ---- יצירת שיבוץ ---- */}
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
