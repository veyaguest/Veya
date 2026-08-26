import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  getEvent,
  getPayoutAccount,
  getPostponement,
  getStats,
  mediaUrl,
  updateEvent,
} from '../api'
import type {
  DashboardStats,
  EventDetails,
  PayoutAccount,
  Postponement,
} from '../types'
import type { ReadinessPage } from '../readiness'
import {
  payoutDisplayStatus,
  payoutStage,
  type PayoutDisplayStatus,
} from '../payoutState'
import { ActivityLog } from './ActivityLog'
import { EventStateBanner } from './EventStateBanner'
import { PartnerCta } from './PartnerCta'
import { PostponeFinishDialog, PostponeRequestDialog } from './PostponeDialog'
import { VenueAutocomplete } from './VenueAutocomplete'
import { TimePicker } from './TimePicker'
import { getEventTerms } from '../strings/eventTypes'
import { strings } from '../strings/he'
import './CallFeed.css'
import './PostponeDialog.css'

interface Props {
  // ניווט למסך אחר (מוזמנים / מפת אולם) — עבור הבאנר וכרטיס ההושבה.
  onNavigate?: (page: ReadinessPage) => void
  /**
   * האם האירוע זכאי לשירות "מתנות באשראי".
   *
   * מגיע מהשרת דרך ``EventSummary.gift_service_eligible``. כשהתשובה
   * שלילית, תמונת המצב לא מזכירה את השירות בכלל — אין תזכורת ואין
   * הפניה למסך שממילא אינו קיים לאירוע הזה.
   */
  giftsEligible?: boolean
}

const t = strings.dashboard
const tp = strings.postpone

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

/**
 * תזכורת "פרטי קבלת מתנות" בתמונת המצב.
 *
 * **מוצגת רק כשיש מה לעשות או מה לדעת.** ברגע ששתי הבדיקות אושרו היא
 * נעלמת לגמרי: משימה שנגמרה לא צריכה להמשיך לתפוס מקום בדשבורד.
 *
 * הטון עדין ולא מלחיץ — זה סעיף פתוח ברשימה של הזוג, לא אזהרה. לכן יש
 * כפתור רק במצבים שבהם באמת נדרשת פעולה; כשהפרטים בבדיקה, התזכורת רק
 * מדווחת ומוסיפה קישור צפייה.
 *
 * הסיווג עצמו מגיע מ-``payoutDisplayStatus`` — אותה פונקציה שמזינה את
 * הסטטוס במסך המתנות, כדי ששני המסכים לא יאמרו לזוג שני דברים שונים,
 * ובלי אזכור של מי מבין שני הגורמים בודק.
 */
function PayoutReminder({
  account,
  onNavigate,
}: {
  account: PayoutAccount | null
  onNavigate?: (page: ReadinessPage) => void
}) {
  const display = payoutDisplayStatus(payoutStage(account))
  if (display === 'approved') return null

  const r = t.payoutReminder
  const copy: Record<Exclude<PayoutDisplayStatus, 'approved'>, {
    title: string
    desc: string
    cta: string
  }> = {
    missing: { title: r.missingTitle, desc: r.missingDesc, cta: r.missingCta },
    review: { title: r.reviewTitle, desc: r.reviewDesc, cta: r.viewCta },
    fix: { title: r.fixTitle, desc: r.fixDesc, cta: r.fixCta },
  }
  const { title, desc, cta } = copy[display]
  const urgent = display === 'fix'

  return (
    <div className={`payout-reminder${urgent ? ' payout-reminder--action' : ''}`}>
      <div className="payout-reminder-text">
        <p className="payout-reminder-title">{title}</p>
        <p className="payout-reminder-desc">{desc}</p>
      </div>
      <button
        type="button"
        className="payout-reminder-btn"
        onClick={() => onNavigate?.('gifts')}
      >
        {cta}
      </button>
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

/**
 * שדה שנעול או פתוח לפי מצב האירוע.
 *
 * כשהוא נעול הוא מוצג כערך ולא כתיבה — לא input מושבת. שדה אפור שאי אפשר
 * להקליד בו נראה כמו תקלה; ערך עם מנעול לצידו נראה כמו החלטה.
 */
function LockableInput({
  locked,
  placeholder,
  value,
  onChange,
}: {
  locked: boolean
  placeholder: string
  value: string
  onChange: (v: string) => void
}) {
  if (locked) return <LockedValue text={value} />
  return (
    <input
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  )
}

function LockedValue({ text }: { text: string }) {
  return (
    <span className="locked-value" title={strings.postpone.lockedFieldHint}>
      <span className="locked-value-icon" aria-hidden="true">🔒</span>
      <span className="locked-value-text">{text || '—'}</span>
    </span>
  )
}

export function DashboardPage({ onNavigate, giftsEligible = false }: Props) {
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
  // פרטי קבלת המתנות — עבור התזכורת בלבד. ``null`` כשאין הרשאה (הנתיב
  // פתוח לבעלים בלבד) או כשהקריאה נכשלה, ואז פשוט אין תזכורת.
  const [payout, setPayout] = useState<PayoutAccount | null>(null)
  // ---- נוהל דחייה ----
  // ``postpone`` נטען לצד האירוע ומשמש רק להצגת סיבת דחייה ולכפתור "פתיחת
  // מחזור חדש". **מצב האירוע עצמו מגיע מ-``event.event_stage``** — מקור
  // אמת אחד בשרת, לא הרכבה מחדש כאן.
  const [postpone, setPostpone] = useState<Postponement | null>(null)
  const [postponeDialog, setPostponeDialog] = useState<'request' | 'finish' | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [s, e, p] = await Promise.all([
        getStats(),
        getEvent(),
        // נכשל בשקט למי שאינו בעלים (הנתיב owner-only) — ואז פשוט אין
        // אזור נוהל דחייה, בלי לשבור את הדשבורד.
        getPostponement().catch(() => null),
      ])
      setStats(s)
      setEvent(e)
      setPostpone(p)
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

  // בקריאה נפרדת ולא בתוך ``refresh``: הנתיב פתוח לבעלים בלבד, ולכן מפיק
  // שצופה בדשבורד יקבל כאן 403 — וזה תקין. כישלון שקט משמעו "בלי תזכורת",
  // ולא דשבורד שנשבר בגלל אזור משני.
  useEffect(() => {
    // לאירוע שאינו זכאי אין מה לשלוף: אין תזכורת, ואין מסך להפנות אליו.
    if (!giftsEligible) return
    let alive = true
    getPayoutAccount()
      .then((a) => alive && setPayout(a))
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [giftsEligible])

  async function onSaveEvent() {
    setError('')
    try {
      const payload: Parameters<typeof updateEvent>[0] = {
        venue_name: form.venue_name,
        venue_address: form.venue_address,
        invite_image: form.invite_image,
      }
      // שדות הליבה נשלחים רק כשמותר לגעת בהם: כשהאירוע פתוח לעריכה, או
      // כשהשדה עדיין ריק (כתיבה ראשונה). השרת אוכף את אותו כלל בעצמו —
      // כאן זה רק כדי לא לשלוח בקשה שידוע מראש שתיכשל.
      const canEdit = (key: string, current: string) =>
        !locked || !current.trim() || !lockedFields.has(key)
      if (canEdit('groom_name', event?.groom_name ?? '')) {
        payload.groom_name = form.groom_name
      }
      if (canEdit('bride_name', event?.bride_name ?? '')) {
        payload.bride_name = form.bride_name
      }
      if (canEdit('event_date', event?.event_date ?? '')) {
        payload.event_date = form.event_date
      }
      if (canEdit('event_time', event?.event_time ?? '')) {
        payload.event_time = form.event_time
      }
      // את מועד סגירת הרשימה שולחים רק כשנבחר וטרם ננעל — הבחירה חד-פעמית.
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

  // ---- נעילת פרטי האירוע ----
  // שתי השורות האלה הן כל מה שהמסך יודע על הנעילה. הן מגיעות מהשרת
  // (``GET /event``) ולא מחושבות כאן — האכיפה האמיתית ממילא ב-``PATCH /event``,
  // וזה רק מה שמוצג.
  const locked = event?.edit_locked !== false
  const lockedFields = useMemo(
    () => new Set(event?.locked_fields ?? []),
    [event?.locked_fields],
  )
  /** האם השדה הזה נעול *עכשיו* — שדה ריק תמיד ניתן למילוי ראשון. */
  const isLocked = (key: string, current: string | undefined) =>
    locked && lockedFields.has(key) && !!(current || '').trim()

  const stage = event?.event_stage ?? 'normal'

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
            {locked && <p className="locked-note">{tp.lockedNote}</p>}

            <div className="event-fields">
              <LockableInput
                locked={isLocked('groom_name', event?.groom_name)}
                placeholder={terms.hostAField}
                value={form.groom_name}
                onChange={(v) => setForm({ ...form, groom_name: v })}
              />
              {terms.hasTwoHosts && (
                <LockableInput
                  locked={isLocked('bride_name', event?.bride_name)}
                  placeholder={terms.hostBField}
                  value={form.bride_name}
                  onChange={(v) => setForm({ ...form, bride_name: v })}
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
                {isLocked('event_date', event?.event_date) ? (
                  <LockedValue text={form.event_date} />
                ) : (
                  <input
                    type="date"
                    value={form.event_date}
                    onChange={(e) =>
                      setForm({ ...form, event_date: e.target.value })
                    }
                    onClick={(e) => e.currentTarget.showPicker?.()}
                  />
                )}
              </label>
              <div className="field-group">
                <span className="field-label">{t.timeLabel}</span>
                {isLocked('event_time', event?.event_time) ? (
                  <LockedValue text={form.event_time} />
                ) : (
                  <TimePicker
                    value={form.event_time}
                    onChange={(time) => setForm({ ...form, event_time: time })}
                    ariaLabel={t.timeLabel}
                  />
                )}
              </div>
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

            {/* "האירוע נדחה?" — הדרך היחידה לפתוח את פרטי הליבה. מוצג רק
                כשהאירוע באמת נעול וכשאין כבר בקשה פתוחה, כדי שלא יציע
                לזוג לעשות משהו שהוא כבר עשה. */}
            {locked && postpone?.can_request && (
              <div className="postpone-entry">
                <strong className="postpone-entry-title">{tp.entryTitle}</strong>
                <p className="postpone-entry-body">{tp.entryBody}</p>
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => setPostponeDialog('request')}
                >
                  {tp.entryCta}
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="dash-hero-bento">
            {/* מימין (RTL): כרטיסיית תמונת הזוג. יש תמונה → המוקאפ הקיים,
                בלי שום שינוי. אין תמונה → empty state מעוצב באותו תא בדיוק
                (לא כרטיס נפרד/גדול יותר), שלוחץ פותח את "פרטי האירוע"
                (event-image-edit למעלה) — אותה לוגיקת העלאה קיימת. */}
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
                  className="invite-empty"
                  onClick={() => setEditing(true)}
                >
                  <span className="invite-empty-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
                      <rect x="3" y="5" width="18" height="14" rx="2.5" />
                      <path d="M3.5 7l8.5 6 8.5-6" />
                    </svg>
                  </span>
                  <span className="invite-empty-title">{t.inviteEmptyTitle}</span>
                  <span className="invite-empty-desc">{t.inviteEmptyDesc}</span>
                  <span className="invite-empty-cta">{t.inviteEmptyCta}</span>
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

      {/* מצב האירוע — מוצג רק כשיש מה לומר (אירוע רגיל לא מקבל באנר).
          הפעולה הבאה נשלחת פנימה, כדי שהמשתמש תמיד יראה "מה עכשיו". */}
      <EventStateBanner
        stage={stage}
        postponement={postpone}
        action={
          postpone?.can_complete ? (
            <button
              type="button"
              className="btn-primary"
              onClick={() => setPostponeDialog('finish')}
            >
              {tp.finishCta}
            </button>
          ) : stage === 'open' ? (
            <span className="ev-state-hint">{tp.finishNeedsDate}</span>
          ) : null
        }
      />

      {postponeDialog === 'request' && (
        <PostponeRequestDialog
          onDone={(p) => setPostpone(p)}
          onClose={() => {
            setPostponeDialog(null)
            refresh()
          }}
        />
      )}
      {postponeDialog === 'finish' && (
        <PostponeFinishDialog
          onDone={(p) => setPostpone(p)}
          onClose={() => {
            setPostponeDialog(null)
            refresh()
          }}
        />
      )}

      {/* "מנהלים את האירוע יחד?" — מוצג רק כשאין עדיין בן/בת זוג ואין הזמנה
          פתוחה. הרכיב מחליט על עצמו ונעלם לבד ברגע שיש שותף/ה. */}
      <PartnerCta />

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

            {/* ---- יומן פעילות: מי שינה מה ומתי. מקבל משמעות אמיתית
                 כשמנהלים את האירוע בשניים — שני המנהלים רואים אותו יומן. ---- */}
            <section className="rsvp-feed-section">
              <ActivityLog />
            </section>

            <div className="dash-stack">
              <InviteBanner
                count={stats.total_guests - stats.invitations_sent}
                onSend={() => onNavigate?.('messages')}
              />
              {giftsEligible && (
                <PayoutReminder account={payout} onNavigate={onNavigate} />
              )}
              <SeatingHelperCard stats={stats} onNavigate={onNavigate} />
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



