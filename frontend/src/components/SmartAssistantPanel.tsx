import { SIDE_LABELS } from '../types'
import type {
  SeatingStats,
  SmartMove,
  SmartSearchResult,
  SmartSuggestion,
  SmartWarning,
} from '../seatingAdvisor'

interface PendingProposal {
  text: string
  moves: SmartMove[]
  diff: { guestId: number; guestName: string; fromTable: number | null; toTable: number }[]
}

/**
 * פאנל "עוזר הושבה חכם" — פאנל צד קבוע (Dock), לא חלון צף.
 *
 * חשוב: הפאנל הזה עצמו לא מזיז אף מוזמן ולא שומר כלום — הוא רק מציג
 * נתונים שכבר חושבו ב-HallPage (מ-seatingAdvisor.ts, שכבה טהורה ונפרדת
 * מהמנוע הנעול app/seating.py) ומפעיל callbacks. כל הצעה עוברת קודם
 * דרך "תצוגה מקדימה" (pendingProposal) שדורשת אישור מפורש — "אשר" בלבד
 * מזיז אורחים (מקומית, בדיוק כמו גרירה ידנית), ועדיין צריך "שמירת המפה".
 */
export function SmartAssistantPanel({
  stats,
  warnings,
  suggestions,
  searchQuery,
  onSearchQueryChange,
  searchResults,
  pendingProposal,
  onProposeSuggestion,
  onConfirmProposal,
  onCancelProposal,
  onClose,
}: {
  stats: SeatingStats
  warnings: SmartWarning[]
  suggestions: SmartSuggestion[]
  searchQuery: string
  onSearchQueryChange: (q: string) => void
  searchResults: SmartSearchResult[]
  pendingProposal: PendingProposal | null
  onProposeSuggestion: (s: SmartSuggestion) => void
  onConfirmProposal: () => void
  onCancelProposal: () => void
  onClose: () => void
}) {
  return (
    <div className="hall-assistant-panel">
      <div className="assistant-head">
        <h3>✨ עוזר הושבה חכם</h3>
        <button className="x" onClick={onClose} title="סגירה">
          ✕
        </button>
      </div>
      <p className="assistant-sub">
        ניתוח, אזהרות והצעות — כל הצעה מוצגת לאישור לפני שמשהו זז בפועל.
      </p>

      {/* ---- ניתוח כללי ---- */}
      <div className="assistant-section">
        <h4>ניתוח</h4>
        <div className="assistant-stats-grid">
          <div className="assistant-stat">
            <span className="assistant-stat-num">{stats.seatedPeople}</span>
            <span className="assistant-stat-label">משובצים</span>
          </div>
          <div className="assistant-stat">
            <span className="assistant-stat-num">{stats.unseatedPeople}</span>
            <span className="assistant-stat-label">ללא שולחן</span>
          </div>
          <div className="assistant-stat">
            <span className="assistant-stat-num">{stats.numTables}</span>
            <span className="assistant-stat-label">שולחנות</span>
          </div>
          <div className="assistant-stat">
            <span className="assistant-stat-num">{stats.freeSeats}</span>
            <span className="assistant-stat-label">מקומות פנויים</span>
          </div>
          <div className="assistant-stat">
            <span className="assistant-stat-num">{stats.fullTables}</span>
            <span className="assistant-stat-label">שולחנות מלאים</span>
          </div>
          <div className="assistant-stat">
            <span className="assistant-stat-num">{stats.nearEmptyTables}</span>
            <span className="assistant-stat-label">כמעט ריקים</span>
          </div>
        </div>
      </div>

      {/* ---- חיפוש חכם ---- */}
      <div className="assistant-section">
        <h4>חיפוש חכם</h4>
        <input
          type="text"
          className="assistant-search"
          placeholder="שם מוזמן…"
          value={searchQuery}
          onChange={(e) => onSearchQueryChange(e.target.value)}
        />
        {searchQuery.trim() && (
          <div className="assistant-search-results">
            {searchResults.length === 0 && <p className="assistant-empty">לא נמצאו התאמות</p>}
            {searchResults.map((r) => (
              <div key={r.guestId} className="assistant-search-result">
                <div className="assistant-search-name">
                  {r.fullName} <span className="assistant-search-side">{SIDE_LABELS[r.side]}</span>
                </div>
                {r.tableNumber != null ? (
                  <div className="assistant-search-meta">
                    שולחן {r.tableNumber}
                    {r.companions.length > 0 && ` · יחד עם: ${r.companions.join(', ')}`}
                    {r.freeSeatsAtTable != null && ` · ${r.freeSeatsAtTable} מקומות פנויים`}
                  </div>
                ) : (
                  <div className="assistant-search-meta">ללא שולחן</div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ---- אזהרות חכמות ---- */}
      <div className="assistant-section">
        <h4>אזהרות חכמות</h4>
        {warnings.length === 0 && <p className="assistant-empty">אין אזהרות כרגע ✓</p>}
        <div className="assistant-warning-list">
          {warnings.map((w, i) => (
            <div key={i} className={`assistant-warning ${w.severity}`}>
              {w.text}
            </div>
          ))}
        </div>
      </div>

      {/* ---- הצעות ---- */}
      <div className="assistant-section">
        <h4>הצעות</h4>
        {suggestions.length === 0 && <p className="assistant-empty">אין הצעות כרגע</p>}
        <div className="assistant-suggestion-list">
          {suggestions.map((s, i) => (
            <div key={i} className="assistant-suggestion">
              <span>{s.text}</span>
              <button className="btn-ghost" onClick={() => onProposeSuggestion(s)}>
                הצג תצוגה מקדימה
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* ---- תצוגה מקדימה של הצעה שנבחרה — ממתינה לאישור מפורש ---- */}
      {pendingProposal && (
        <div className="assistant-proposal">
          <h4>תצוגה מקדימה</h4>
          <p>{pendingProposal.text}</p>
          <ul className="assistant-proposal-diff">
            {pendingProposal.diff.map((d, i) => (
              <li key={i}>
                {d.guestName}: {d.fromTable != null ? `שולחן ${d.fromTable}` : 'ללא שולחן'} ←{' '}
                שולחן {d.toTable}
              </li>
            ))}
          </ul>
          <div className="assistant-proposal-actions">
            <button className="btn-primary" onClick={onConfirmProposal}>
              ✓ אשר
            </button>
            <button className="btn-ghost" onClick={onCancelProposal}>
              ✕ בטל
            </button>
          </div>
          <p className="assistant-proposal-note">
            האישור מזיז את המוזמנים על המפה בלבד — עדיין צריך ללחוץ "שמירת המפה" כדי לשמור.
          </p>
        </div>
      )}
    </div>
  )
}
