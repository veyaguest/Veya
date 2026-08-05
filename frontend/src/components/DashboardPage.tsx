import { useCallback, useEffect, useMemo, useState } from 'react'
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

/** כרטיס "הצעד הבא" — משבצת קבועה ב-Grid ליד הדונאט, תמיד מציגה משהו. */
function QuickActionsCard({
  stats,
  onNavigate,
}: {
  stats: DashboardStats
  onNavigate?: (page: ReadinessPage) => void
}) {
  if (stats.invitations_sent === 0) {
    return (
      <div className="cta-card dash-grid-card">
        <h3 className="cta-card-title">{t.ctaTitle}</h3>
        <p className="cta-card-desc">{t.ctaDesc}</p>
        <button
          className="cta-card-btn"
          onClick={() => onNavigate?.('guests')}
        >
          {t.ctaButton}
        </button>
      </div>
    )
  }

  let text: string
  let cta: string
  let target: ReadinessPage

  if (stats.pending > stats.confirmed + stats.declined) {
    text = `${stats.pending} מוזמנים עדיין לא ענו`
    cta = 'מעקב תשובות'
    target = 'guests'
  } else if (stats.pending_clarifications > 0) {
    text = `${stats.pending_clarifications} הבהרות ממתינות לטיפול`
    cta = 'לטפל בהבהרות'
    target = 'hall'
  } else if (stats.seated_guests < stats.confirmed) {
    const unseated = stats.confirmed - stats.seated_guests
    text = `${unseated} מוזמנים מאושרים עדיין בלי מקום בשולחן`
    cta = 'סידור הושבה'
    target = 'hall'
  } else {
    return (
      <div className="quick-actions-card dash-grid-card">
        <span className="quick-actions-icon">✓</span>
        <h3 className="quick-actions-title">{t.allDoneTitle}</h3>
        <p className="quick-actions-desc">{t.allDoneDesc}</p>
      </div>
    )
  }

  return (
    <div className="quick-actions-card dash-grid-card">
      <span className="quick-actions-icon">✦</span>
      <h3 className="quick-actions-title">{t.nextStepTitle}</h3>
      <p className="quick-actions-desc">{text}</p>
      <button
        className="quick-actions-btn"
        onClick={() => onNavigate?.(target)}
      >
        {cta}
      </button>
    </div>
  )
}

/** מוקאפ תמונת ההזמנה כפי שהיא נראית ב-WhatsApp — אייפון צף בתוך משבצת ה-Hero,
 * באותו גודל קבוע כמו קודם (dash-hero-image, 4:3). */
function InvitePhoneMock({
  imageSrc,
  imageAlt,
  contactName,
  captionText,
}: {
  imageSrc: string
  imageAlt: string
  contactName: string
  captionText: string
}) {
  return (
    <div className="invite-phone-stage">
      <div className="invite-phone">
        <span className="invite-phone-btn invite-phone-btn--mute" aria-hidden="true" />
        <span className="invite-phone-btn invite-phone-btn--vol-up" aria-hidden="true" />
        <span className="invite-phone-btn invite-phone-btn--vol-down" aria-hidden="true" />
        <span className="invite-phone-btn invite-phone-btn--power" aria-hidden="true" />
        <span className="invite-phone-notch" aria-hidden="true" />
        <div className="invite-phone-screen">
          <div className="invite-phone-header">
            <span className="invite-phone-avatar" aria-hidden="true">💍</span>
            <span className="invite-phone-name">{contactName}</span>
          </div>
          <div className="invite-phone-chat">
            <div className="invite-phone-bubble">
              <img className="invite-phone-bubble-img" src={imageSrc} alt={imageAlt} />
              <p className="invite-phone-bubble-caption">{captionText}</p>
              <span className="invite-phone-bubble-time" aria-hidden="true">
                12:00 ✓✓
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

/** אחוז בין 0–100 עבור פס ההתקדמות הזעיר בכרטיסי ה-KPI, בטוח מחלוקה באפס. */
function kpiPct(value: number, total: number): number {
  if (total <= 0) return 0
  return Math.max(0, Math.min(100, Math.round((value / total) * 100)))
}

/** שניות עד לתאריך/שעת האירוע (יכול להיות שלילי אם האירוע כבר עבר). */
function useCountdown(targetMs: number | null) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (targetMs === null) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [targetMs])

  if (targetMs === null) return null
  const diff = targetMs - now
  if (diff <= 0) return { days: 0, hours: 0, minutes: 0, seconds: 0, isPast: true }
  return {
    days: Math.floor(diff / 86_400_000),
    hours: Math.floor((diff % 86_400_000) / 3_600_000),
    minutes: Math.floor((diff % 3_600_000) / 60_000),
    seconds: Math.floor((diff % 60_000) / 1000),
    isPast: false,
  }
}

function CountdownCell({ value, label }: { value: number; label: string }) {
  return (
    <div className="countdown-cell">
      <span className="countdown-cell-num">{String(value).padStart(2, '0')}</span>
      <span className="countdown-cell-label">{label}</span>
    </div>
  )
}

/** Live Countdown Timer — ימים/שעות/דקות/שניות עד האירוע, בקוביות זכוכית. */
function CountdownTimer({ date, time }: { date?: string; time?: string }) {
  const targetMs = useMemo(() => {
    if (!date) return null
    const iso = `${date}T${time || '00:00'}:00`
    const ms = new Date(iso).getTime()
    return isNaN(ms) ? null : ms
  }, [date, time])

  const cd = useCountdown(targetMs)
  if (!cd) return null

  if (cd.isPast) {
    return <div className="countdown-timer-today">{t.countdownToday}</div>
  }

  return (
    <div className="countdown-timer" role="timer" aria-label={t.countdownAriaLabel(cd.days, cd.hours, cd.minutes)}>
      <CountdownCell value={cd.days} label={t.countdownDays} />
      <span className="countdown-sep" aria-hidden="true">:</span>
      <CountdownCell value={cd.hours} label={t.countdownHours} />
      <span className="countdown-sep" aria-hidden="true">:</span>
      <CountdownCell value={cd.minutes} label={t.countdownMinutes} />
      <span className="countdown-sep" aria-hidden="true">:</span>
      <CountdownCell value={cd.seconds} label={t.countdownSeconds} />
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
    if (file.size > 50 * 1024 * 1024) {
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
          <div className="dash-hero-bento">
            {/* מימין (RTL): כרטיסיית תמונת הזוג */}
            <div className="dash-hero-image">
              {event?.invite_image ? (
                <>
                  <InvitePhoneMock
                    imageSrc={mediaUrl(event.invite_image)}
                    imageAlt={terms.inviteLabel}
                    contactName={couple ?? terms.defaultTitle}
                    captionText={
                      couple
                        ? t.inviteCaptionNamed(terms.celebration, couple)
                        : t.inviteCaptionGeneric(terms.celebration)
                    }
                  />
                  <button
                    type="button"
                    className="dash-hero-image-edit"
                    onClick={() => setEditing(true)}
                  >
                    ✎ {strings.common.edit}
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  className="dash-hero-image-placeholder"
                  onClick={() => setEditing(true)}
                >
                  <span className="dash-hero-image-placeholder-icon">🖼</span>
                  <span className="dash-hero-image-placeholder-text">{t.invitePlaceholder}</span>
                </button>
              )}
            </div>

            {/* משמאל: שמות, מיקום ותאריך, וטיימר ספירה לאחור חי */}
            <div className="dash-hero-info">
              <h2 className="event-couple">{couple ?? terms.defaultTitle}</h2>
              <p className="event-info-line">
                {terms.icon} {terms.label}
                {event?.venue_name ? ` · ${event.venue_name}` : ''}
                {when ? ` · ${when}` : ''}
              </p>
              <CountdownTimer date={event?.event_date} time={event?.event_time} />
              <button className="btn-text dash-edit-link" onClick={() => setEditing(true)}>
                ✎ עריכת פרטים
              </button>
            </div>
          </div>
        )}
      </div>

      {error && <p className="form-error">{error}</p>}

      {!stats && <p className="dash-loading">{t.loadingData}</p>}

      {stats && stats.total_guests === 0 && (
        <div className="dash-empty-state">
          <span className="dash-empty-icon">📋</span>
          <h3 className="dash-empty-title">{t.emptyTitle}</h3>
          <p className="dash-empty-desc">{t.emptyDesc}</p>
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => onNavigate?.('guests')}
          >
            {t.emptyCta}
          </button>
        </div>
      )}

      {stats && stats.total_guests > 0 && (() => {
        const rsvpSegments = [
          { key: 'confirmed', label: t.kpiConfirmed, value: stats.confirmed, color: 'var(--gauge-confirmed)' },
          { key: 'maybe', label: t.gaugeStatusMaybe, value: stats.maybe, color: 'var(--gauge-maybe)' },
          { key: 'declined', label: t.gaugeStatusDeclined, value: stats.declined, color: 'var(--gauge-declined)' },
          { key: 'pending', label: t.kpiPending, value: stats.pending, color: 'var(--gauge-pending)' },
        ]
        return (
          <>
            {/* ---- סקשן המד — מוקד ויזואלי במלוא הרוחב, מיד מתחת להירו.
                 לא כרטיס קטן בתוך Grid — "חלון ראווה" עצמאי למד ולסטטיסטיקות
                 שלו בלבד, בלי כרטיסים אחרים לצידו. ---- */}
            <section className="gauge-section">
              <div className="gauge-section-head">
                <h3 className="gauge-section-title">{t.donutCardTitle}</h3>
                <span className="gauge-section-badge">
                  {t.donutResponseBadge(Math.round(stats.response_rate))}
                </span>
              </div>
              <RsvpGauge
                segments={rsvpSegments}
                centerValue={stats.confirmed}
                centerLabel={t.gaugeLabel}
              />
              <ul className="gauge-status-grid">
                {rsvpSegments.map((seg) => (
                  <li key={seg.key} className="gauge-status-card">
                    <span className="gauge-status-dot" style={{ background: seg.color }} />
                    <span className="gauge-status-num">{seg.value}</span>
                    <span className="gauge-status-label">{seg.label}</span>
                  </li>
                ))}
              </ul>
            </section>

            {/* ---- "הצעד הבא" — עומד עכשיו לבדו, לא ליד המד ---- */}
            <div className="dash-next-row">
              <QuickActionsCard stats={stats} onNavigate={onNavigate} />
            </div>

            {/* ---- KPI Cards — 4 מדדים מרכזיים ---- */}
            <div className="kpi-grid">
              <div className="kpi-card">
                <span className="kpi-dot" style={{ background: 'var(--green)' }} />
                <span className="kpi-num">{stats.confirmed}</span>
                <span className="kpi-label">{t.kpiConfirmed}</span>
                <span className="kpi-progress-track">
                  <span
                    className="kpi-progress-fill"
                    style={{
                      width: `${kpiPct(stats.confirmed, stats.total_guests)}%`,
                      background: 'var(--green)',
                    }}
                  />
                </span>
              </div>
              <div className="kpi-card">
                <span className="kpi-dot" style={{ background: 'var(--faint)' }} />
                <span className="kpi-num">{stats.pending}</span>
                <span className="kpi-label">{t.kpiPending}</span>
                <span className="kpi-progress-track">
                  <span
                    className="kpi-progress-fill"
                    style={{
                      width: `${kpiPct(stats.pending, stats.total_guests)}%`,
                      background: 'var(--faint)',
                    }}
                  />
                </span>
              </div>
              <div className="kpi-card">
                <span className="kpi-dot" style={{ background: 'var(--error)' }} />
                <span className="kpi-num">{stats.declined}</span>
                <span className="kpi-label">{t.kpiDeclined}</span>
                <span className="kpi-progress-track">
                  <span
                    className="kpi-progress-fill"
                    style={{
                      width: `${kpiPct(stats.declined, stats.total_guests)}%`,
                      background: 'var(--error)',
                    }}
                  />
                </span>
              </div>
              <div className="kpi-card">
                <span className="kpi-dot" style={{ background: 'var(--gold-light)' }} />
                <span className="kpi-num">{stats.total_guests - stats.invitations_sent}</span>
                <span className="kpi-label">{t.kpiNotSent}</span>
                <span className="kpi-progress-track">
                  <span
                    className="kpi-progress-fill"
                    style={{
                      width: `${kpiPct(stats.total_guests - stats.invitations_sent, stats.total_guests)}%`,
                      background: 'var(--gold-light)',
                    }}
                  />
                </span>
              </div>
            </div>
          </>
        )
      })()}

      {/* ---- Event Progress — מד מוכנות ---- */}
      {stats && stats.total_guests > 0 && (() => {
        const d1 = 1
        const d2 = (stats.by_side.groom + stats.by_side.bride) / stats.total_guests
        const d3 = 1 - ((stats.by_group as Record<string, number>).other ?? 0) / stats.total_guests
        const d4 = stats.invitations_sent / stats.total_guests
        const d5 = stats.response_rate / 100
        const pct = Math.min(100, Math.round((d1 + d2 + d3 + d4 + d5) * 20))
        return (
          <div className="event-progress">
            <span className="event-progress-label">{t.progressLabel(pct)}</span>
            <div className="event-progress-track">
              <div className="event-progress-fill" style={{ width: `${pct}%` }} />
            </div>
          </div>
        )
      })()}

      {/* ---- סידור הושבה חכם — פיצ'ר דגל ---- */}
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

/** נקודה על מעגל לפי זווית (מעלות, 0=ימין, 90=למעלה) — לבניית קשתות SVG. */
function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = (angleDeg * Math.PI) / 180
  return { x: cx + r * Math.cos(rad), y: cy - r * Math.sin(rad) }
}

/** מחרוזת path של קשת SVG בין שתי זוויות (עד 180°, ולכן large-arc-flag תמיד 0). */
function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number) {
  const start = polarToCartesian(cx, cy, r, startAngle)
  const end = polarToCartesian(cx, cy, r, endAngle)
  return `M ${start.x} ${start.y} A ${r} ${r} 0 0 1 ${end.x} ${end.y}`
}

/** סופר מ-0 עד היעד בעקומת ease-out, פעם אחת ברכיבה (לא מגיב לרינדורים חוזרים). */
function useCountUp(target: number, duration = 900) {
  const [value, setValue] = useState(0)
  useEffect(() => {
    const reduceMotion =
      typeof window !== 'undefined' &&
      window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reduceMotion) {
      setValue(target)
      return
    }
    let raf = 0
    const startTime = performance.now()
    function tick(now: number) {
      const elapsed = now - startTime
      const progress = Math.min(1, elapsed / duration)
      const eased = 1 - Math.pow(1 - progress, 3)
      setValue(Math.round(target * eased))
      if (progress < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target])
  return value
}

/** מד חצי-עגול (Gauge) — פרימיום, בהשראת לוח מחוונים של רכב יוקרה. מציג את
 * כמות המאושרים (לא אחוז — VEYA מדברת בכמות) כמוקד הראשי, עם ציור-קשתות
 * ומספר עולה באנימציה. */
function RsvpGauge({
  segments,
  centerValue,
  centerLabel,
}: {
  segments: { key: string; label: string; value: number; color: string }[]
  centerValue: number
  centerLabel: string
}) {
  const animatedValue = useCountUp(centerValue, 900)
  const total = segments.reduce((s, x) => s + x.value, 0)

  const CX = 120
  const CY = 122
  const R = 96
  const STROKE = 24
  // מרווח זעיר (במעלות) בין הפלחים — קצוות מעוגלים בלי לגעת בפלח הבא.
  const GAP_DEG = 3

  let cursor = 180
  const arcs = segments.map((seg) => {
    const span = total > 0 ? (seg.value / total) * 180 : 0
    const start = cursor
    const end = cursor - span
    cursor = end
    return { ...seg, start, end, span }
  })

  return (
    <div className="gauge-wrap">
      <span className="gauge-glow" aria-hidden="true" />
      <svg viewBox="0 0 240 140" className="gauge-svg" role="img" aria-label={`${centerValue} ${centerLabel}`}>
        <path
          d={describeArc(CX, CY, R, 180, 0)}
          className="gauge-track"
          fill="none"
          strokeWidth={STROKE}
          strokeLinecap="round"
        />
        {arcs.map((a, i) => {
          if (a.span <= 0.4) return null
          const inset = Math.min(GAP_DEG / 2, a.span / 2 - 0.2)
          const s = a.start - inset
          const e = a.end + inset
          if (s <= e) return null
          return (
            <path
              key={a.key}
              d={describeArc(CX, CY, R, s, e)}
              className="gauge-segment"
              style={{ stroke: a.color, animationDelay: `${i * 110}ms` }}
              fill="none"
              strokeWidth={STROKE}
              strokeLinecap="round"
              pathLength={100}
            />
          )
        })}
      </svg>
      {/* מרכז המד כ-HTML (ולא SVG) — כדי שהעברית תוצג נכון בכל דפדפן */}
      <div className="gauge-center" aria-hidden="true">
        <span className="gauge-num">{animatedValue}</span>
        <span className="gauge-lbl">{centerLabel}</span>
      </div>
    </div>
  )
}



