import { useCallback, useEffect, useState } from 'react'
import { getEvent, getStats, readAudit, updateEvent } from '../api'
import type { AuditLogRow, DashboardStats, EventDetails } from '../types'
import { GROUP_LABELS, SIDE_LABELS } from '../types'
import type { KnownGroupType, Side } from '../types'
import { computeReadiness, type ReadinessPage } from '../readiness'
import { ReadinessMeter } from './ReadinessMeter'
import { PrepWizard } from './PrepWizard'
import { VenueAutocomplete } from './VenueAutocomplete'

interface Props {
  // ניווט למסך אחר (מוזמנים / מפת אולם) — עבור אשף ההכנה ומדד המוכנות.
  onNavigate?: (page: ReadinessPage) => void
}

const AUDIT_LABELS: Record<string, string> = {
  send_invitations: 'שליחת הזמנות',
  send_reminders: 'שליחת תזכורות',
  update_event: 'עדכון פרטי אירוע',
  confirm_submit: 'אישור הגעה מהקישור',
  confirm_invalid_token: '⚠ ניסיון גישה לקישור לא תקין',
}

export function DashboardPage({ onNavigate }: Props) {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [event, setEvent] = useState<EventDetails | null>(null)
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({
    groom_name: '',
    bride_name: '',
    venue_name: '',
    venue_address: '',
    event_date: '',
    event_time: '',
    invite_image: '' as string | null,
    // יום ההתחייבות לאולם — כמה ימים לפני האירוע (1–10). '' = טרם נבחר.
    venue_commit_days_before: '' as number | '',
  })
  // האם הבחירה כבר ננעלה (בלתי-הפיכה) — נטען מהשרת.
  const [commitLocked, setCommitLocked] = useState(false)
  const [audit, setAudit] = useState<AuditLogRow[]>([])
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [s, e, a] = await Promise.all([getStats(), getEvent(), readAudit(15)])
      setStats(s)
      setEvent(e)
      setAudit(a)
      setForm({
        groom_name: e.groom_name,
        bride_name: e.bride_name,
        venue_name: e.venue_name,
        venue_address: e.venue_address ?? '',
        event_date: e.event_date,
        event_time: e.event_time,
        invite_image: e.invite_image ?? '',
        venue_commit_days_before: e.venue_commit_days_before ?? '',
      })
      setCommitLocked(e.venue_commit_locked)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לטעון כרגע, ננסה שוב')
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  async function onSaveEvent() {
    setError('')
    try {
      const payload: Parameters<typeof updateEvent>[0] = {
        groom_name: form.groom_name,
        bride_name: form.bride_name,
        venue_name: form.venue_name,
        venue_address: form.venue_address,
        event_date: form.event_date,
        event_time: form.event_time,
        invite_image: form.invite_image,
      }
      // את יום ההתחייבות שולחים רק כשנבחר וטרם ננעל — הבחירה חד-פעמית ובלתי-הפיכה.
      if (!commitLocked && form.venue_commit_days_before !== '') {
        payload.venue_commit_days_before = form.venue_commit_days_before
      }
      const e = await updateEvent(payload)
      setEvent(e)
      setEditing(false)
      await refresh()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לשמור את הפרטים, נסו שוב')
    }
  }

  function onPickImage(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // מאפשר לבחור שוב את אותו קובץ
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setError('אפשר להעלות קובץ תמונה בלבד')
      return
    }
    if (file.size > 3 * 1024 * 1024) {
      setError('התמונה גדולה מדי — עד 3MB')
      return
    }
    setError('')
    const reader = new FileReader()
    reader.onload = () =>
      setForm((f) => ({ ...f, invite_image: String(reader.result) }))
    reader.readAsDataURL(file)
  }

  const couple =
    event && (event.groom_name || event.bride_name)
      ? [event.groom_name, event.bride_name].filter(Boolean).join(' ו')
      : null

  const when = event
    ? formatWhen(event.event_date, event.event_time)
    : ''

  const readiness = computeReadiness(stats)

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
              <VenueAutocomplete
                value={form.venue_name}
                onChange={(name) => setForm({ ...form, venue_name: name })}
                onPick={(name, address) =>
                  setForm((f) => ({
                    ...f,
                    venue_name: name,
                    // כתובת מהמאגר ממלאת אוטומטית אם השדה עדיין ריק; לא דורסים כתובת שהזוג הקליד.
                    venue_address: f.venue_address.trim() ? f.venue_address : address,
                  }))
                }
                placeholder="שם האולם"
              />
              <input
                placeholder="כתובת האולם (לניווט בהודעות)"
                value={form.venue_address}
                onChange={(e) =>
                  setForm({ ...form, venue_address: e.target.value })
                }
              />
            </div>

            <div className="event-datetime">
              <label className="field-group">
                <span className="field-label">תאריך האירוע</span>
                <input
                  type="date"
                  value={form.event_date}
                  onChange={(e) =>
                    setForm({ ...form, event_date: e.target.value })
                  }
                />
              </label>
              <label className="field-group">
                <span className="field-label">שעת האירוע</span>
                <input
                  type="time"
                  value={form.event_time}
                  onChange={(e) =>
                    setForm({ ...form, event_time: e.target.value })
                  }
                />
              </label>
            </div>

            {/* ---- יום ההתחייבות לאולם — בחירה חד-פעמית ובלתי-הפיכה ---- */}
            <div className="commit-field">
              <span className="field-label">יום ההתחייבות לאולם</span>
              <p className="commit-explain">
                כמה ימים לפני החתונה אתם צריכים למסור לאולם מספר סופי? זה היום
                שבו כל אישורי ההגעה נסגרים — תדעו בדיוק מי מגיע ומי לא. כל לוח
                הזמנים של אישורי ההגעה נבנה לאחור סביב היום הזה.
              </p>
              {commitLocked ? (
                <div className="commit-locked">
                  <span className="commit-locked-value">
                    {form.venue_commit_days_before} ימים לפני האירוע
                  </span>
                  <span className="commit-locked-note">
                    🔒 כבר בחרתם — הבחירה נעולה כי לוח הזמנים כבר בנוי סביבה.
                  </span>
                </div>
              ) : (
                <>
                  <select
                    className="commit-select"
                    value={form.venue_commit_days_before}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        venue_commit_days_before:
                          e.target.value === '' ? '' : Number(e.target.value),
                      })
                    }
                  >
                    <option value="">בחרו מספר ימים…</option>
                    {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                      <option key={n} value={n}>
                        {n} ימים לפני האירוע
                      </option>
                    ))}
                  </select>
                  <span className="commit-warn">
                    שימו לב: אחרי השמירה לא ניתן לשנות את הבחירה הזו.
                  </span>
                </>
              )}
            </div>

            <div className="event-image-edit">
              <span className="event-image-label">תמונת ההזמנה</span>
              {form.invite_image ? (
                <div className="event-image-has">
                  <div className="phone-mock">
                    <div className="phone-mock-notch" />
                    <div className="phone-mock-bubble">
                      <img
                        className="event-image-thumb"
                        src={form.invite_image}
                        alt="תצוגה מקדימה של ההזמנה"
                      />
                      <div className="phone-mock-meta">
                        <span>הזמנה לחתונה</span>
                        <span className="phone-mock-check">✓✓</span>
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn-text"
                    onClick={() => setForm({ ...form, invite_image: '' })}
                  >
                    הסרת התמונה
                  </button>
                </div>
              ) : (
                <label className="event-image-drop">
                  <input
                    type="file"
                    accept="image/*"
                    onChange={onPickImage}
                    style={{ display: 'none' }}
                  />
                  <span>⬆ העלאת תמונת הזמנה</span>
                  <small>זו התמונה שתישלח למוזמנים בהזמנה</small>
                </label>
              )}
            </div>

            <div className="event-edit-actions">
              <button className="btn-primary" onClick={onSaveEvent}>
                שמירה
              </button>
              <button className="btn-text" onClick={() => setEditing(false)}>
                ביטול
              </button>
            </div>
          </div>
        ) : (
          <div className="event-view">
            {event?.invite_image && (
              <div className="phone-mock">
                <div className="phone-mock-notch" />
                <div className="phone-mock-bubble">
                  <img
                    className="event-invite-img"
                    src={event.invite_image}
                    alt="הזמנה לחתונה"
                  />
                  <div className="phone-mock-meta">
                    <span>הזמנה לחתונה</span>
                    <span className="phone-mock-check">✓✓</span>
                  </div>
                </div>
              </div>
            )}
            <div className="event-view-text">
              <h2 className="event-couple">{couple ?? 'החתונה שלנו'}</h2>
              <p className="event-venue">
                {event?.venue_name ||
                  'עוד לא הזנתם את פרטי האירוע — בואו נשלים את שמות בני הזוג, האולם והתאריך'}
              </p>
              {when && <p className="event-when">{when}</p>}
            </div>
            <button className="btn-ghost" onClick={() => setEditing(true)}>
              ✎ עריכת פרטים
            </button>
          </div>
        )}
      </div>

      {error && <p className="form-error">{error}</p>}

      {/* ---- מדד מוכנות + אשף ההכנה (מובילים את הזוג צעד אחר צעד) ---- */}
      {stats && stats.total_guests > 0 && readiness.percent < 100 && (
        <div className="prep-block">
          <ReadinessMeter readiness={readiness} />
          <PrepWizard readiness={readiness} onNavigate={onNavigate} />
        </div>
      )}

      {/* ---- תמונת מצב ראשית — אישורי הגעה (העוגה הגדולה, החלק החשוב) ---- */}
      <div className="dash-hero">
        <h3 className="dash-hero-title">תמונת מצב — אישורי הגעה</h3>
        <p className="dash-hero-sub">
          {stats
            ? `${stats.confirmed_people} אורחים אישרו הגעה מתוך ${stats.total_people}`
            : 'טוען נתונים…'}
        </p>
        <div className="dash-hero-chart">
          <Donut
            segments={[
              { label: 'אישרו הגעה', value: stats?.confirmed ?? 0, color: 'var(--green)' },
              { label: 'לא החליטו', value: stats?.maybe ?? 0, color: 'var(--gold)' },
              { label: 'לא מגיעים', value: stats?.declined ?? 0, color: 'var(--error)' },
              { label: 'טרם הגיבו', value: stats?.pending ?? 0, color: 'var(--faint)' },
            ]}
            centerNum={stats ? `${stats.confirmed_people}` : '—'}
            centerLabel="אורחים אישרו"
          />
        </div>
        <ul className="donut-legend">
          <LegendRow color="var(--green)" label="אישרו הגעה" value={stats?.confirmed ?? 0} />
          <LegendRow color="var(--gold)" label="לא החליטו (אולי)" value={stats?.maybe ?? 0} />
          <LegendRow color="var(--error)" label="לא מגיעים" value={stats?.declined ?? 0} />
          <LegendRow color="var(--faint)" label="טרם הגיבו" value={stats?.pending ?? 0} />
        </ul>
      </div>

      {/* ---- מדדים ראשיים ---- */}
      <div className="dash-grid">
        <div className="stat-card">
          <span className="stat-num">{stats?.total_guests ?? '—'}</span>
          <span className="stat-label">מוזמנים ברשימה</span>
        </div>
        <div className="stat-card">
          <span className="stat-num">{stats?.total_people ?? '—'}</span>
          <span className="stat-label">סך האורחים</span>
        </div>
        <div className="stat-card ok">
          <span className="stat-num">{stats?.confirmed_people ?? '—'}</span>
          <span className="stat-label">אישרו הגעה</span>
        </div>
        <div className="stat-card wait">
          <span className="stat-num">
            {stats ? `${stats.response_rate}%` : '—'}
          </span>
          <span className="stat-label">שיעור מענה</span>
        </div>
      </div>

      {/* ---- התראת הבהרות ---- */}
      {stats && stats.pending_clarifications > 0 && (
        <p className="dash-alert">
          ⚠ יש {stats.pending_clarifications} הבהרות שממתינות לכם — במסך "מפת
          אולם והושבה" נשלים אותן יחד.
        </p>
      )}

      {/* ---- פילוחים ---- */}
      <div className="dash-panels">
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
            {(Object.keys(GROUP_LABELS) as KnownGroupType[]).map((g) => (
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

      {/* ---- יומן אבטחה ---- */}
      {audit.length > 0 && (
        <div className="dash-panel audit-panel">
          <h3 className="clar-title">יומן פעילות ואבטחה</h3>
          <span className="clar-sub">
            תיעוד הפעולות הרגישות האחרונות (שליחות, עדכונים, גישה לקישורים).
          </span>
          <ul className="audit-list">
            {audit.map((a) => (
              <li key={a.id} className="audit-row">
                <span className="audit-action">
                  {AUDIT_LABELS[a.action] ?? a.action}
                </span>
                <span className="audit-detail">{a.detail}</span>
                <span className="audit-time">{formatTime(a.created_at)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** מרכיב מחרוזת "תאריך · שעה" קריאה בעברית, או ריק אם אין נתונים. */
function formatWhen(date: string, time: string): string {
  const parts: string[] = []
  if (date) {
    const d = new Date(date)
    parts.push(
      isNaN(d.getTime())
        ? date
        : d.toLocaleDateString('he-IL', {
            weekday: 'long',
            day: 'numeric',
            month: 'long',
            year: 'numeric',
          }),
    )
  }
  if (time) parts.push(`בשעה ${time}`)
  return parts.join(', ')
}

/** תאריך+שעה קצרים לשורת יומן. */
function formatTime(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString('he-IL', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** תרשים עוגה (donut) טהור ב-SVG — בלי ספריות חיצוניות, קל ומהיר. */
function Donut({
  segments,
  centerNum,
  centerLabel,
}: {
  segments: { label: string; value: number; color: string }[]
  centerNum: string
  centerLabel: string
}) {
  const total = segments.reduce((s, x) => s + x.value, 0)
  const R = 52
  const C = 2 * Math.PI * R
  let acc = 0
  return (
    <div className="donut-wrap">
      <svg viewBox="0 0 140 140" className="donut" role="img" aria-label={centerLabel}>
        <circle className="donut-bg" cx="70" cy="70" r={R} fill="none" strokeWidth="18" />
        {total > 0 &&
          segments.map((seg, i) => {
            const len = (seg.value / total) * C
            const dash = (
              <circle
                key={i}
                cx="70"
                cy="70"
                r={R}
                fill="none"
                stroke={seg.color}
                strokeWidth="18"
                strokeDasharray={`${len} ${C - len}`}
                strokeDashoffset={-acc}
                transform="rotate(-90 70 70)"
              />
            )
            acc += len
            return dash
          })}
      </svg>
      {/* מרכז העוגה כ-HTML (ולא SVG) — כדי שהעברית תוצג נכון בכל דפדפן */}
      <div className="donut-center" aria-hidden="true">
        <span className="donut-num">{centerNum}</span>
        <span className="donut-lbl">{centerLabel}</span>
      </div>
    </div>
  )
}

/** שורת מקרא לצד תרשים העוגה. */
function LegendRow({
  color,
  label,
  value,
}: {
  color: string
  label: string
  value: number
}) {
  return (
    <li className="legend-row">
      <span className="legend-dot" style={{ background: color }} />
      <span className="legend-label">{label}</span>
      <b className="legend-val">{value}</b>
    </li>
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
