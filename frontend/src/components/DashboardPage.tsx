import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { getEvent, getStats, mediaUrl, readAudit, updateEvent } from '../api'
import type { AuditLogRow, DashboardStats, EventDetails } from '../types'
import type { ReadinessPage } from '../readiness'
import { VenueAutocomplete } from './VenueAutocomplete'
import { getEventTerms } from '../strings/eventTypes'
import { strings } from '../strings/he'

interface Props {
  // ניווט למסך אחר (מוזמנים / מפת אולם) — עבור הבאנר וכרטיס ההושבה.
  onNavigate?: (page: ReadinessPage) => void
}

const t = strings.dashboard

/** מקטין את font-size של הרכיב עד שהטקסט (בשורה אחת) נכנס בדיוק ברוחב
 * הזמין לו — כדי שהשם המלא תמיד יוצג (אף פעם לא נחתך ב-"…"), גם באייפון
 * הקטן במובייל וגם בשמות ארוכים. רץ מחדש כשהטקסט או רוחב המסגרת משתנים. */
function useShrinkToFit(text: string, maxPx: number, minPx: number) {
  const ref = useRef<HTMLSpanElement>(null)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const fit = () => {
      let size = maxPx
      el.style.fontSize = `${size}px`
      while (el.scrollWidth > el.clientWidth && size > minPx) {
        size -= 0.5
        el.style.fontSize = `${size}px`
      }
    }
    fit()
    // מסך שמסתובב/משתנה גודל (טאבלט, שינוי חלון) עלול לשנות את הרוחב
    // הזמין בלי שהטקסט עצמו משתנה — צריך למדוד מחדש גם אז.
    window.addEventListener('resize', fit)
    return () => window.removeEventListener('resize', fit)
  }, [text, maxPx, minPx])
  return ref
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
  const nameRef = useShrinkToFit(contactName, 10, 6.5)
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
            <span ref={nameRef} className="invite-phone-name">{contactName}</span>
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

/** באנר "יש מוזמנים בלי הזמנה" — מופיע רק כשקיימים מוזמנים שטרם נשלחה
 * אליהם הזמנה. בולט אך אלגנטי (מבטא זהב עדין), לא אזהרה אדומה. */
function InviteBanner({ count, onSend }: { count: number; onSend: () => void }) {
  if (count <= 0) return null
  return (
    <div className="invite-banner">
      <div className="invite-banner-text">
        <p className="invite-banner-title">{t.inviteBannerTitle(count)}</p>
        <p className="invite-banner-desc">{t.inviteBannerDesc}</p>
      </div>
      <button type="button" className="invite-banner-btn" onClick={onSend}>
        {t.inviteBannerCta}
      </button>
    </div>
  )
}

/** מפענח שורת יומן ביקורת של אישור/ביטול/"אולי" מהקישור הציבורי (action
 * "confirm_submit", detail בפורמט "שם: תווית"), וגם שינוי סטטוס ידני
 * מעריכת מוזמן (action "guest_rsvp_manual_update") — לפריט Feed קריא.
 * מתעלם מכל שורה אחרת ביומן — ה-Feed הזה מוקדש לעדכוני RSVP בלבד. */
function parseRsvpEvent(row: AuditLogRow): { icon: string; text: string } | null {
  if (row.action === 'guest_rsvp_manual_update') {
    // ה-detail כבר משפט עברי שלם ("שם: אישור הגעה השתנה מ'X' ל'Y'") —
    // מוצג כמו שהוא, בלי לפרק אותו מחדש.
    return { icon: '✎', text: row.detail }
  }
  if (row.action !== 'confirm_submit') return null
  const sep = row.detail.indexOf(': ')
  if (sep < 0) return null
  const name = row.detail.slice(0, sep)
  const label = row.detail.slice(sep + 2)
  if (label.startsWith('אישר')) return { icon: '✅', text: t.feedConfirmed(name) }
  if (label.startsWith('ביטל')) return { icon: '❌', text: t.feedDeclined(name) }
  if (label.startsWith('סימן')) return { icon: '🟡', text: t.feedMaybe(name) }
  return null
}

/** זמן יחסי קריא בעברית ("לפני 5 דק'" וכו') — לתדפיס שעת עדכון ב-Feed. */
function timeAgo(iso: string): string {
  const then = new Date(iso).getTime()
  if (isNaN(then)) return ''
  const diffSec = Math.max(0, Math.floor((Date.now() - then) / 1000))
  if (diffSec < 60) return 'עכשיו'
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `לפני ${diffMin} דק׳`
  const diffHour = Math.floor(diffMin / 60)
  if (diffHour < 24) return `לפני ${diffHour} שע׳`
  const diffDay = Math.floor(diffHour / 24)
  if (diffDay === 1) return 'אתמול'
  if (diffDay < 7) return `לפני ${diffDay} ימים`
  return new Date(iso).toLocaleDateString('he-IL', { day: 'numeric', month: 'short' })
}

/** "עדכוני אישורי הגעה" — Feed חי של תגובות מוזמנים בלבד (בלי מידע כפול
 * עם המד למעלה: כאן זו זרימת אירועים בזמן, לא סך-הכול). */
function RsvpUpdatesFeed({ rows }: { rows: AuditLogRow[] }) {
  const items = rows
    .map((r) => {
      const parsed = parseRsvpEvent(r)
      return parsed ? { ...parsed, id: r.id, created_at: r.created_at } : null
    })
    .filter((x): x is { icon: string; text: string; id: number; created_at: string } => x !== null)
    .slice(0, 6)

  return (
    <div className="rsvp-feed-card">
      <h3 className="rsvp-feed-title">{t.feedTitle}</h3>
      {items.length === 0 ? (
        <p className="rsvp-feed-empty">{t.feedEmpty}</p>
      ) : (
        <ul className="rsvp-feed-list">
          {items.map((it) => (
            <li key={it.id} className="rsvp-feed-item">
              <span className="rsvp-feed-icon" aria-hidden="true">{it.icon}</span>
              <span className="rsvp-feed-text">{it.text}</span>
              <span className="rsvp-feed-time">{timeAgo(it.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** קובע איפה הזוג נמצא בתהליך ההכנה להושבה, לפי נתונים אמיתיים בלבד —
 * לא הנחה. שלב 4 (הושבה) פתוח רק אחרי שיש גם מוזמנים, גם קבוצות אמיתיות
 * (לא כולם "אחר") וגם הערה אחת לפחות (הושבה או קבוצה). */
function seatingReadinessStep(stats: DashboardStats): number {
  const hasGuests = stats.total_guests > 0
  if (!hasGuests) return 0
  const other = (stats.by_group as Record<string, number>).other ?? 0
  const hasGroups = stats.total_guests - other > 0
  if (!hasGroups) return 1
  const hasNotes = stats.guests_with_notes > 0 || stats.group_notes_count > 0
  if (!hasNotes) return 2
  return 3
}

/** "סידורי הושבה בלי כאב הראש" — הכרטיס המרכזי לפיצ'ר הדגל: מסביר את
 * הערך, ומוביל אשף מדורג (מוזמנים → קבוצות → הערות → הושבה חכמה) — לא
 * זורק את הזוג ישר לעורך אולם ריק. ה-CTA "חכם": כל עוד לא הושלמו שלבי
 * ההכנה הוא מוביל למסך המוזמנים (שם מוסיפים מוזמנים, קובעים קבוצות
 * ומזינים הערות הושבה); רק כשהכול מוכן הוא נפתח למפת האולם. */
function SeatingHelperCard({ stats, onNavigate }: { stats: DashboardStats; onNavigate?: (page: ReadinessPage) => void }) {
  const steps = t.seatingHelperSteps
  const currentStep = seatingReadinessStep(stats)
  const ready = currentStep >= steps.length - 1
  return (
    <div className="seating-helper-card">
      <h3 className="seating-helper-title">{t.seatingHelperTitle}</h3>
      <p className="seating-helper-desc">{t.seatingHelperDesc}</p>
      <ol className="seating-helper-steps">
        {steps.map((step, i) => {
          const isFinal = i === steps.length - 1
          const status = i < currentStep ? 'done' : i === currentStep ? 'current' : 'upcoming'
          return (
            <li
              key={step}
              className={`seating-helper-step seating-helper-step--${status}${isFinal ? ' seating-helper-step--final' : ''}`}
            >
              <span className="seating-helper-step-num">{status === 'done' ? '✓' : i + 1}</span>
              <span className="seating-helper-step-label">{step}</span>
              {!isFinal && (
                <span className="seating-helper-step-arrow" aria-hidden="true">↓</span>
              )}
            </li>
          )
        })}
      </ol>
      <button
        type="button"
        className="seating-helper-cta"
        onClick={() => onNavigate?.(ready ? 'hall' : 'guests')}
      >
        {ready ? t.seatingHelperCtaReady : t.seatingHelperCta}
      </button>
    </div>
  )
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
    // מועד סגירת הרשימה — כמה ימים לפני האירוע (1–10). '' = טרם נבחר.
    venue_commit_days_before: '' as number | '',
  })
  // האם הבחירה כבר ננעלה (בלתי-הפיכה) — נטען מהשרת.
  const [commitLocked, setCommitLocked] = useState(false)
  const [error, setError] = useState('')
  // יומן העדכונים — מקור ה-Feed "עדכוני אישורי הגעה" (מסונן ל-confirm_submit).
  const [auditRows, setAuditRows] = useState<AuditLogRow[]>([])

  const refresh = useCallback(async () => {
    try {
      const [s, e, audit] = await Promise.all([getStats(), getEvent(), readAudit(20)])
      setStats(s)
      setEvent(e)
      setAuditRows(audit)
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
      // את מועד סגירת הרשימה שולחים רק כשנבחר וטרם ננעל — הבחירה חד-פעמית ובלתי-הפיכה.
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

            {/* ---- מועד סגירת הרשימה — בחירה חד-פעמית ובלתי-הפיכה ---- */}
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
        // "תמונת מצב" סופרת אנשים (SUM party_size), לא רשומות מוזמן — מוזמן
        // אחד עם party_size=4 שאישר מייצג 4, לא 1. חל רק כאן (העוגה + הכרטיסים);
        // שאר המערכת (למשל סיכום "ניהול מוזמנים") ממשיכה לספור מוזמנים כרגיל.
        const rsvpSegments = [
          { key: 'confirmed', label: t.kpiConfirmed, value: stats.confirmed_people, color: 'var(--gauge-confirmed)' },
          { key: 'maybe', label: t.gaugeStatusMaybe, value: stats.maybe_people, color: 'var(--gauge-maybe)' },
          { key: 'declined', label: t.gaugeStatusDeclined, value: stats.declined_people, color: 'var(--gauge-declined)' },
          { key: 'pending', label: t.kpiPending, value: stats.pending_people, color: 'var(--gauge-pending)' },
        ]
        return (
          <>
            {/* ---- סקשן המד — מוקד ויזואלי במלוא הרוחב, מיד מתחת להירו.
                 לא כרטיס קטן בתוך Grid — "חלון ראווה" עצמאי למד ולסטטיסטיקות
                 שלו בלבד, בלי כרטיסים אחרים לצידו. ---- */}
            <section className="gauge-section">
              <div className="gauge-section-head">
                <h3 className="gauge-section-title">{t.donutCardTitle}</h3>
              </div>
              <RsvpGauge
                segments={rsvpSegments}
                centerValue={stats.confirmed_people}
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

            {/* ---- שתי עמודות: עדכוני אישורי הגעה (Feed) + סידורי הושבה
                 (הפיצ'ר הדגל). מחליפות את כרטיס "הצעד הבא" וכרטיסי הסטטיסטיקה
                 הכפולים — כל המידע שהיה בהם כבר מופיע במד שלמעלה. ---- */}
            <div className="dash-two-col">
              <div className="dash-col-left">
                <InviteBanner
                  count={stats.total_guests - stats.invitations_sent}
                  onSend={() => onNavigate?.('messages')}
                />
                <RsvpUpdatesFeed rows={auditRows} />
              </div>
              <div className="dash-col-right">
                <SeatingHelperCard stats={stats} onNavigate={onNavigate} />
              </div>
            </div>
          </>
        )
      })()}
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



