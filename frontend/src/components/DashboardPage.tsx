import { useCallback, useEffect, useState } from 'react'
import { getEvent, getStats, mediaUrl, readAudit, updateEvent } from '../api'
import type { AuditLogRow, DashboardStats, EventDetails } from '../types'
import type { ReadinessPage } from '../readiness'
import { SeatingPrep } from './SeatingPrep'
import { VenueAutocomplete } from './VenueAutocomplete'
import { strings } from '../strings/he'

interface Props {
  // ניווט למסך אחר (מוזמנים / מפת אולם) — עבור סקשן "הכנה להושבה".
  onNavigate?: (page: ReadinessPage) => void
}

const t = strings.dashboard

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
      setError(err instanceof Error ? err.message : t.loadError)
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
      setError(err instanceof Error ? err.message : t.saveError)
    }
  }

  function onPickImage(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = '' // מאפשר לבחור שוב את אותו קובץ
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setError(t.imageTypeError)
      return
    }
    if (file.size > 3 * 1024 * 1024) {
      setError(t.imageSizeError)
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

  return (
    <div className="dash-page">
      {/* ---- כותרת האירוע ---- */}
      <div className="dash-event">
        {editing ? (
          <div className="event-edit">
            <div className="event-fields">
              <input
                placeholder={t.groomPlaceholder}
                value={form.groom_name}
                onChange={(e) => setForm({ ...form, groom_name: e.target.value })}
              />
              <input
                placeholder={t.bridePlaceholder}
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
                placeholder={t.venuePlaceholder}
              />
              <input
                placeholder={t.venueAddressPlaceholder}
                value={form.venue_address}
                onChange={(e) =>
                  setForm({ ...form, venue_address: e.target.value })
                }
              />
            </div>

            <div className="event-datetime">
              <label className="field-group">
                <span className="field-label">{t.dateLabel}</span>
                <input
                  type="date"
                  value={form.event_date}
                  onChange={(e) =>
                    setForm({ ...form, event_date: e.target.value })
                  }
                />
              </label>
              <label className="field-group">
                <span className="field-label">{t.timeLabel}</span>
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
              <span className="field-label">{t.commitLabel}</span>
              <p className="commit-explain">{t.commitExplain}</p>
              {commitLocked ? (
                <div className="commit-locked">
                  <span className="commit-locked-value">
                    {t.commitLockedValue(form.venue_commit_days_before)}
                  </span>
                  <span className="commit-locked-note">{t.commitLockedNote}</span>
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
                    <option value="">{t.commitSelectPlaceholder}</option>
                    {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => (
                      <option key={n} value={n}>
                        {t.commitOptionLabel(n)}
                      </option>
                    ))}
                  </select>
                  <span className="commit-warn">{t.commitWarn}</span>
                </>
              )}
            </div>

            <div className="event-image-edit">
              <span className="event-image-label">{t.imageLabel}</span>
              {form.invite_image ? (
                <div className="event-image-has">
                  <div className="phone-mock">
                    <div className="phone-mock-notch" />
                    <div className="phone-mock-bubble">
                      <img
                        className="event-image-thumb"
                        src={mediaUrl(form.invite_image)}
                        alt={t.imageAlt}
                      />
                      <div className="phone-mock-meta">
                        <span>{t.imageBubbleLabel}</span>
                        <span className="phone-mock-check">✓✓</span>
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn-text"
                    onClick={() => setForm({ ...form, invite_image: '' })}
                  >
                    {t.imageRemove}
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
                  <span>{t.imageUpload}</span>
                  <small>{t.imageUploadHint}</small>
                </label>
              )}
            </div>

            <div className="event-edit-actions">
              <button className="btn-primary" onClick={onSaveEvent}>
                {strings.common.save}
              </button>
              <button className="btn-text" onClick={() => setEditing(false)}>
                {strings.common.cancel}
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
                    src={mediaUrl(event.invite_image)}
                    alt={t.inviteImgAlt}
                  />
                  <div className="phone-mock-meta">
                    <span>{t.imageBubbleLabel}</span>
                    <span className="phone-mock-check">✓✓</span>
                  </div>
                </div>
              </div>
            )}
            <div className="event-view-text">
              <h2 className="event-couple">{couple ?? t.coupleFallback}</h2>
              <p className="event-venue">
                {event?.venue_name || t.venueFallback}
              </p>
              {when && <p className="event-when">{when}</p>}
            </div>
            <button className="btn-ghost" onClick={() => setEditing(true)}>
              {t.editButton}
            </button>
          </div>
        )}
      </div>

      {error && <p className="form-error">{error}</p>}

      {/* ---- תמונת מצב ראשית — אישורי הגעה (העוגה הגדולה, החלק החשוב) ---- */}
      <div className="dash-hero">
        <h3 className="dash-hero-title">{t.rsvpTitle}</h3>
        <p className="dash-hero-sub">
          {stats ? t.rsvpSub(stats.confirmed_people, stats.total_people) : t.loadingData}
        </p>
        <div className="dash-hero-chart">
          <Donut
            segments={[
              { label: t.segConfirmed, value: stats?.confirmed ?? 0, color: 'var(--green)' },
              { label: t.segMaybe, value: stats?.maybe ?? 0, color: 'var(--gold)' },
              { label: t.segDeclined, value: stats?.declined ?? 0, color: 'var(--error)' },
              { label: t.segPending, value: stats?.pending ?? 0, color: 'var(--faint)' },
            ]}
            centerNum={stats ? `${stats.confirmed_people}` : '—'}
            centerLabel={t.centerLabel}
          />
        </div>
        <ul className="donut-legend">
          <LegendRow color="var(--green)" label={t.segConfirmed} value={stats?.confirmed ?? 0} />
          <LegendRow color="var(--gold)" label={t.legendMaybe} value={stats?.maybe ?? 0} />
          <LegendRow color="var(--error)" label={t.segDeclined} value={stats?.declined ?? 0} />
          <LegendRow color="var(--faint)" label={t.segPending} value={stats?.pending ?? 0} />
        </ul>
      </div>

      {/* ---- הכנה להושבה (אחרי העוגה, לפני הפעילות האחרונה) ---- */}
      {stats && stats.total_guests > 0 && (
        <SeatingPrep stats={stats} onNavigate={onNavigate} />
      )}

      {/* ---- התראת הבהרות (פעולה נדרשת) ---- */}
      {stats && stats.pending_clarifications > 0 && (
        <p className="dash-alert">{t.clarificationsAlert(stats.pending_clarifications)}</p>
      )}

      {/* ---- פעילות אחרונה ---- */}
      {audit.length > 0 && (
        <div className="dash-panel audit-panel">
          <h3 className="clar-title">{t.auditTitle}</h3>
          <span className="clar-sub">{t.auditSub}</span>
          <ul className="audit-list">
            {audit.map((a) => (
              <li key={a.id} className="audit-row">
                <span className="audit-action">
                  {t.auditLabels[a.action] ?? a.action}
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

