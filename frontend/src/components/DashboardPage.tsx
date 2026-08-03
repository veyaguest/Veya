import { useCallback, useEffect, useState } from 'react'
import { getEvent, getStats, mediaUrl, updateEvent } from '../api'
import type { DashboardStats, EventDetails } from '../types'
import type { ReadinessPage } from '../readiness'
import { SeatingPrep } from './SeatingPrep'
import { VenueAutocomplete } from './VenueAutocomplete'
import { getEventTerms } from '../strings/eventTypes'
import { strings } from '../strings/he'

interface Props {
  // ניווט למסך אחר (מוזמנים / מפת אולם) — עבור סקשן "הכנה להושבה".
  onNavigate?: (page: ReadinessPage) => void
}

const t = strings.dashboard

function NextAction({
  stats,
  onNavigate,
}: {
  stats: DashboardStats
  onNavigate?: (page: ReadinessPage) => void
}) {
  let text: string
  let cta: string
  let target: ReadinessPage

  if (stats.invitations_sent === 0) {
    text = `${stats.total_guests} מוזמנים ברשימה — עדיין לא נשלחו הזמנות`
    cta = 'שליחת הזמנות'
    target = 'guests'
  } else if (stats.pending > stats.confirmed + stats.declined) {
    text = `${stats.pending} מוזמנים עדיין לא ענו`
    cta = 'מעקב תשובות'
    target = 'guests'
  } else if (stats.pending_clarifications > 0) {
    text = `${stats.pending_clarifications} הבהרות ממתינות לטיפול`
    cta = 'לטפל בהבהרות'
    target = 'hall'
  } else if (stats.seated_guests < stats.confirmed) {
    const unseated = stats.confirmed - stats.seated_guests
    text = `${unseated} אורחים מאושרים עדיין בלי מקום בשולחן`
    cta = 'סידור הושבה'
    target = 'hall'
  } else {
    return null
  }

  return (
    <div className="next-action">
      <p className="next-action-text">{text}</p>
      <button
        className="next-action-cta"
        onClick={() => onNavigate?.(target)}
      >
        {cta}
      </button>
    </div>
  )
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

  // מנוע המונחים לפי סוג האירוע — קובע תוויות שדות, כותרת ותווית ההזמנה.
  const terms = getEventTerms(event?.event_type)

  const couple =
    event && (event.groom_name || event.bride_name)
      ? [event.groom_name, event.bride_name].filter(Boolean).join(' ו')
      : null

  const when = event
    ? formatWhen(event.event_date, event.event_time)
    : ''

  const countdown = event?.event_date ? daysUntil(event.event_date) : null

  return (
    <div className="dash-page">
      {/* ---- Hero: שמות + סוג אירוע + תאריך + ספירה לאחור ---- */}
      <div className="dash-hero-section">
        {editing ? (
          <div className="event-edit">
            <div className="event-fields">
              <input
                placeholder={terms.hostAField}
                value={form.groom_name}
                onChange={(e) => setForm({ ...form, groom_name: e.target.value })}
              />
              {terms.hasTwoHosts && (
                <input
                  placeholder={terms.hostBField}
                  value={form.bride_name}
                  onChange={(e) => setForm({ ...form, bride_name: e.target.value })}
                />
              )}
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
                  <div className="invite-frame">
                    <div className="invite-frame-mat">
                      <img
                        className="event-image-thumb"
                        src={mediaUrl(form.invite_image)}
                        alt={t.imageAlt}
                      />
                    </div>
                    <span className="invite-frame-caption">{terms.inviteLabel}</span>
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
            <h2 className="event-couple">{couple ?? terms.defaultTitle}</h2>
            <p className="event-meta">
              {terms.icon} {terms.label}
              {event?.venue_name ? ` · ${event.venue_name}` : ''}
            </p>
            {when && <p className="event-when">{when}</p>}
            {countdown !== null && countdown >= 0 && (
              <p className="event-countdown">
                {countdown === 0 ? 'היום!' : `עוד ${countdown} ימים`}
              </p>
            )}
            <button className="btn-text dash-edit-link" onClick={() => setEditing(true)}>
              ✎ עריכה
            </button>
          </div>
        )}
      </div>

      {error && <p className="form-error">{error}</p>}

      {/* ---- RSVP Control Center — הדונאט + מקרא לצידו ---- */}
      <div className="rsvp-center">
        <div className="rsvp-center-donut">
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
        <ul className="rsvp-center-legend">
          <LegendRow color="var(--green)" label={t.segConfirmed} value={stats?.confirmed ?? 0} />
          <LegendRow color="var(--gold)" label={t.legendMaybe} value={stats?.maybe ?? 0} />
          <LegendRow color="var(--error)" label={t.segDeclined} value={stats?.declined ?? 0} />
          <LegendRow color="var(--faint)" label={t.segPending} value={stats?.pending ?? 0} />
        </ul>
      </div>

      {/* ---- Next Action — הדבר הכי חשוב לעשות עכשיו ---- */}
      {stats && stats.total_guests > 0 && (
        <NextAction stats={stats} onNavigate={onNavigate} />
      )}

      {/* ---- VEYA Assistant — מלווה אישי להושבה ---- */}
      {stats && stats.total_guests > 0 && (
        <SeatingPrep stats={stats} onNavigate={onNavigate} />
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

function daysUntil(dateStr: string): number {
  const target = new Date(dateStr + 'T00:00:00')
  if (isNaN(target.getTime())) return -1
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  return Math.round((target.getTime() - today.getTime()) / 86_400_000)
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


