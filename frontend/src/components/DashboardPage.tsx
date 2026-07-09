import { useCallback, useEffect, useState } from 'react'
import { getEvent, getStats, updateEvent } from '../api'
import type { DashboardStats, EventDetails } from '../types'
import { GROUP_LABELS, SIDE_LABELS } from '../types'
import type { GroupType, Side } from '../types'

export function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [event, setEvent] = useState<EventDetails | null>(null)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ groom_name: '', bride_name: '', venue_name: '' })
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [s, e] = await Promise.all([getStats(), getEvent()])
      setStats(s)
      setEvent(e)
      setForm({
        groom_name: e.groom_name,
        bride_name: e.bride_name,
        venue_name: e.venue_name,
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בטעינת הדשבורד')
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  async function onSaveEvent() {
    setError('')
    try {
      const e = await updateEvent(form)
      setEvent(e)
      setEditing(false)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בשמירת פרטי האירוע')
    }
  }

  const couple =
    event && (event.groom_name || event.bride_name)
      ? [event.groom_name, event.bride_name].filter(Boolean).join(' ו')
      : null

  return (
    <div className="dash-page">
      {/* ---- כותרת האירוע ---- */}
      <div className="dash-event">
        {editing ? (
          <div className="event-edit">
            <div className="event-fields">
              <input
                placeholder="שם החתן"
                value={form.groom_name}
                onChange={(e) => setForm({ ...form, groom_name: e.target.value })}
              />
              <input
                placeholder="שם הכלה"
                value={form.bride_name}
                onChange={(e) => setForm({ ...form, bride_name: e.target.value })}
              />
              <input
                placeholder="שם האולם"
                value={form.venue_name}
                onChange={(e) => setForm({ ...form, venue_name: e.target.value })}
              />
            </div>
            <div className="event-edit-actions">
              <button className="btn-primary" onClick={onSaveEvent}>
                שמור
              </button>
              <button className="btn-text" onClick={() => setEditing(false)}>
                ביטול
              </button>
            </div>
          </div>
        ) : (
          <div className="event-view">
            <div>
              <h2 className="event-couple">{couple ?? 'החתונה שלנו'}</h2>
              <p className="event-venue">
                {event?.venue_name || 'הוסיפו את שם האולם ופרטי בני הזוג'}
              </p>
            </div>
            <button className="btn-ghost" onClick={() => setEditing(true)}>
              ✎ ערוך פרטים
            </button>
          </div>
        )}
      </div>

      {error && <p className="form-error">{error}</p>}

      {/* ---- מדדים ראשיים ---- */}
      <div className="dash-grid">
        <div className="stat-card">
          <span className="stat-num">{stats?.total_guests ?? '—'}</span>
          <span className="stat-label">מוזמנים ברשימה</span>
        </div>
        <div className="stat-card">
          <span className="stat-num">{stats?.total_people ?? '—'}</span>
          <span className="stat-label">סה"כ אנשים</span>
        </div>
        <div className="stat-card ok">
          <span className="stat-num">{stats?.confirmed_people ?? '—'}</span>
          <span className="stat-label">אנשים שאישרו</span>
        </div>
        <div className="stat-card wait">
          <span className="stat-num">
            {stats ? `${stats.response_rate}%` : '—'}
          </span>
          <span className="stat-label">אחוז מענה</span>
        </div>
      </div>

      {/* ---- התראת הבהרות ---- */}
      {stats && stats.pending_clarifications > 0 && (
        <p className="dash-alert">
          ⚠ {stats.pending_clarifications} הבהרות ממתינות — עברו למסך "שיבוץ הושבה"
          כדי לפתור אותן.
        </p>
      )}

      {/* ---- פילוחים ---- */}
      <div className="dash-panels">
        <div className="dash-panel">
          <h3 className="clar-title">אישורי הגעה</h3>
          <div className="bar-rows">
            <BarRow label="אישרו" value={stats?.confirmed ?? 0} total={stats?.total_guests ?? 0} tone="ok" />
            <BarRow label="לא מגיעים" value={stats?.declined ?? 0} total={stats?.total_guests ?? 0} tone="err" />
            <BarRow label="ממתינים" value={stats?.pending ?? 0} total={stats?.total_guests ?? 0} tone="wait" />
          </div>
        </div>

        <div className="dash-panel">
          <h3 className="clar-title">לפי צד</h3>
          <div className="bar-rows">
            {(Object.keys(SIDE_LABELS) as Side[]).map((s) => (
              <BarRow
                key={s}
                label={SIDE_LABELS[s]}
                value={stats?.by_side[s] ?? 0}
                total={stats?.total_guests ?? 0}
              />
            ))}
          </div>
        </div>

        <div className="dash-panel">
          <h3 className="clar-title">לפי קבוצה</h3>
          <div className="bar-rows">
            {(Object.keys(GROUP_LABELS) as GroupType[]).map((g) => (
              <BarRow
                key={g}
                label={GROUP_LABELS[g]}
                value={stats?.by_group[g] ?? 0}
                total={stats?.total_guests ?? 0}
              />
            ))}
          </div>
        </div>

        <div className="dash-panel">
          <h3 className="clar-title">הושבה</h3>
          <div className="dash-mini">
            <div>
              <span className="mini-num">{stats?.tables_assigned ?? '—'}</span>
              <span className="mini-label">שולחנות שובצו</span>
            </div>
            <div>
              <span className="mini-num">{stats?.seated_guests ?? '—'}</span>
              <span className="mini-label">מוזמנים משובצים</span>
            </div>
            <div>
              <span className="mini-num">{stats?.invitations_sent ?? '—'}</span>
              <span className="mini-label">הזמנות שנשלחו</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function BarRow({
  label,
  value,
  total,
  tone,
}: {
  label: string
  value: number
  total: number
  tone?: 'ok' | 'err' | 'wait'
}) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0
  return (
    <div className="bar-row">
      <span className="bar-label">{label}</span>
      <span className="bar-track">
        <span className={`bar-fill ${tone ?? ''}`} style={{ width: `${pct}%` }} />
      </span>
      <span className="bar-value">{value}</span>
    </div>
  )
}
