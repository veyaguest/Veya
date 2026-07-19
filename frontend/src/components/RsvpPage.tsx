import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  activateRsvpTrack,
  advanceRsvpTrack,
  getAutomationDashboard,
  getAutomationPlaceholders,
  getEvent,
  getRsvpTrack,
  getTemplate,
  listAutomationTemplates,
  listGuests,
  mediaUrl,
  messageLog,
  previewSend,
  previewTemplate,
  rsvpSummary,
  saveTemplate,
  sendInvitations,
  sendReminders,
  simulateReply,
} from '../api'
import type {
  AutomationDashboard,
  EventDetails,
  Guest,
  InvitationSendPreview,
  Message,
  RsvpSummary,
  RsvpTrackActivateResult,
  RsvpTrackStatus,
  SendScope,
  TemplatePlaceholder,
} from '../types'
import { RSVP_LABELS } from '../types'
import { AutomationRulesTab } from './AutomationRulesTab'
import { AutomationTemplatesTab } from './AutomationTemplatesTab'
import { AutomationQueueTab } from './AutomationQueueTab'
import { GuestTimelineModal } from './GuestTimelineModal'
import { MessageBuilder } from './MessageBuilder'
import { RsvpTimeline } from './RsvpTimeline'

type Tab = 'dashboard' | 'automations' | 'templates' | 'queue' | 'manual'

const TABS: { key: Tab; label: string }[] = [
  { key: 'dashboard', label: 'מצב ומעקב' },
  { key: 'automations', label: 'אוטומציות' },
  { key: 'templates', label: 'תבניות הודעה' },
  { key: 'queue', label: 'תור לשליחה' },
  { key: 'manual', label: 'שליחה ידנית' },
]

/**
 * מסך אישורי ההגעה. הזוג רואה חוויה פשוטה (מסלול פעיל + עורך הודעות),
 * ואילו אדמין רואה את הלשוניות הטכניות המלאות (אוטומציות/תור/ידני).
 */
export function RsvpPage({ isAdmin }: { isAdmin: boolean }) {
  if (!isAdmin) return <CoupleRsvpView />
  return <AdminRsvpShell />
}

/**
 * מעטפת לאדמין: כברירת מחדל מציגה את חוויית הזוג (מסלול אישורי ההגעה),
 * כי זה הלב של המוצר. מתג קטן מאפשר לעבור לפאנל הניהול הטכני בעת הצורך.
 * זוג רגיל לא רואה את המתג הזה כלל.
 */
function AdminRsvpShell() {
  const [view, setView] = useState<'couple' | 'admin'>('couple')
  return (
    <>
      <div className="rsvp-view-toggle" role="tablist">
        <button
          role="tab"
          className={`rsvp-view-btn ${view === 'couple' ? 'active' : ''}`}
          onClick={() => setView('couple')}
        >
          תצוגת הזוג
        </button>
        <button
          role="tab"
          className={`rsvp-view-btn ${view === 'admin' ? 'active' : ''}`}
          onClick={() => setView('admin')}
        >
          ניהול טכני
        </button>
      </div>
      {view === 'couple' ? <CoupleRsvpView /> : <AdminRsvpView />}
    </>
  )
}

function AdminRsvpView() {
  const [tab, setTab] = useState<Tab>('dashboard')
  const [timelineGuest, setTimelineGuest] = useState<number | null>(null)
  // מפתח רענון — כשאוטומציה/שליחה משנה נתונים, מכריח את לשונית המצב לטעון מחדש.
  const [refreshKey, setRefreshKey] = useState(0)
  const bump = useCallback(() => setRefreshKey((k) => k + 1), [])

  return (
    <div className="rsvp-page">
      <nav className="auto-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.key}
            role="tab"
            className={`auto-tab ${tab === t.key ? 'active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {tab === 'dashboard' && (
        <DashboardTab
          refreshKey={refreshKey}
          onOpenTimeline={setTimelineGuest}
          onGoTo={setTab}
        />
      )}
      {tab === 'automations' && <AutomationRulesTab onChanged={bump} />}
      {tab === 'templates' && <AutomationTemplatesTab onChanged={bump} />}
      {tab === 'queue' && <AutomationQueueTab onSent={bump} />}
      {tab === 'manual' && <ManualTab onChanged={bump} />}

      {timelineGuest != null && (
        <GuestTimelineModal
          guestId={timelineGuest}
          onClose={() => setTimelineGuest(null)}
        />
      )}
    </div>
  )
}

// ============ מסך הזוג — מסלול אישורי הגעה פשוט ============

// שלבי דיאלוג השליחה: סגור / אישור / שולח (התקדמות) / סיכום.
type SendPhase = 'idle' | 'confirm' | 'sending' | 'summary'

function CoupleRsvpView() {
  const [track, setTrack] = useState<RsvpTrackStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')

  // מצב דיאלוג השליחה הידנית.
  const [phase, setPhase] = useState<SendPhase>('idle')
  const [preview, setPreview] = useState<InvitationSendPreview | null>(null)
  const [result, setResult] = useState<RsvpTrackActivateResult | null>(null)
  const [dialogError, setDialogError] = useState('')

  // בטעינה: טוענים סטטוס, ואם המסלול פעיל — מקדמים אותו אוטומטית (idempotent).
  const load = useCallback(async () => {
    setError('')
    try {
      const status = await getRsvpTrack()
      if (status.active) {
        const advanced = await advanceRsvpTrack()
        setTrack(advanced)
        const moved = advanced.sent + advanced.phoned
        if (moved > 0) {
          setNote(
            `המסלול התקדם: ${advanced.sent} הודעות חדשות נשלחו` +
              (advanced.phoned
                ? ` · ${advanced.phoned} נוספו לרשימת המעקב הטלפוני`
                : ''),
          )
        }
      } else {
        setTrack(status)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לטעון כרגע, ננסה שוב')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // לחיצה על "שליחת הזמנות" — טוענים ספירה מקדימה ופותחים דיאלוג אישור.
  async function openSendDialog() {
    setDialogError('')
    setResult(null)
    setNote('')
    try {
      const p = await previewSend()
      setPreview(p)
      setPhase('confirm')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו לטעון כרגע, ננסה שוב')
    }
  }

  // ביצוע השליחה בפועל (אחרי אישור), עם היקף נבחר או ניסיון חוזר לנכשלים.
  async function runSend(opts?: {
    scope?: SendScope
    retryIds?: number[]
    guestIds?: number[]
  }) {
    setPhase('sending')
    setDialogError('')
    try {
      const res = await activateRsvpTrack(opts)
      setResult(res)
      setTrack(res)
      setPhase('summary')
    } catch (err) {
      setDialogError(
        err instanceof Error ? err.message : 'לא הצלחנו לשלוח כרגע, ננסה שוב',
      )
      setPhase('confirm')
    }
  }

  function closeDialog() {
    setPhase('idle')
    setPreview(null)
    setResult(null)
    setDialogError('')
    // מרעננים סטטוס אחרי סגירה כדי שהכרטיס יציג את המצב המעודכן.
    load()
  }

  // "לעריכת ההודעה" מתוך הדיאלוג — סוגרים וגוללים לעורך ההודעות שמתחת.
  function editMessage() {
    setPhase('idle')
    setPreview(null)
    setDialogError('')
    setTimeout(() => {
      document
        .getElementById('mb-anchor')
        ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }, 50)
  }

  if (loading) {
    return (
      <div className="rsvp-page couple-rsvp">
        <p className="mb-empty">רגע, מכינים לכם את אישורי ההגעה…</p>
      </div>
    )
  }

  const active = track?.active

  return (
    <div className="rsvp-page couple-rsvp">
      {error && <p className="form-error">{error}</p>}
      {note && <p className="rsvp-note">{note}</p>}

      {/* יומן המשימות היומי — לוח הזמנים שנבנה לאחור מיום ההתחייבות לאולם. */}
      <RsvpTimeline />

      {!active ? (
        <ActivateCard onSend={openSendDialog} />
      ) : (
        track && <TrackStatusCard track={track} onResend={openSendDialog} />
      )}

      <div id="mb-anchor">
        <MessageBuilder />
      </div>

      {phase !== 'idle' && preview && (
        <SendInvitationsDialog
          phase={phase}
          preview={preview}
          result={result}
          error={dialogError}
          mode={track?.mode ?? 'mock'}
          onConfirm={runSend}
          onRetry={(ids) => runSend({ retryIds: ids })}
          onEditMessage={editMessage}
          onClose={closeDialog}
        />
      )}
    </div>
  )
}

/**
 * דיאלוג שליחת ההזמנות — עובר בין 3 מצבים:
 * אישור (תצוגת הודעה + בחירת נמענים) → התקדמות → סיכום (ניסיון חוזר לנכשלים).
 */
function SendInvitationsDialog({
  phase,
  preview,
  result,
  error,
  mode,
  onConfirm,
  onRetry,
  onEditMessage,
  onClose,
}: {
  phase: SendPhase
  preview: InvitationSendPreview
  result: RsvpTrackActivateResult | null
  error: string
  mode: string
  onConfirm: (opts?: { scope?: SendScope; guestIds?: number[] }) => void
  onRetry: (ids: number[]) => void
  onEditMessage: () => void
  onClose: () => void
}) {
  return (
    <div className="send-dialog-overlay" role="dialog" aria-modal="true">
      <div className="send-dialog">
        {/* ---- מצב: התקדמות ---- */}
        {phase === 'sending' && (
          <div className="send-progress">
            <div className="send-spinner" aria-hidden="true" />
            <h3 className="send-dialog-title">שולחים את ההזמנות…</h3>
            <p className="clar-sub">רגע, מעבירים את ההזמנות למוזמנים שלכם.</p>
            <div className="send-progress-bar">
              <span className="send-progress-fill indeterminate" />
            </div>
          </div>
        )}

        {/* ---- מצב: סיכום ---- */}
        {phase === 'summary' && result && (
          <div className="send-summary">
            <h3 className="send-dialog-title">
              {result.failed > 0 ? 'השליחה הסתיימה — חלק נכשלו' : 'ההזמנות נשלחו! 🎉'}
            </h3>
            <p className="send-summary-main">
              נשלחו <strong>{result.invitations_sent}</strong> הזמנות בהצלחה
              {mode === 'mock' && ' (מצב תצוגה — עדיין לא שלחנו הודעות אמיתיות)'}
            </p>
            {(result.skipped_missing + result.skipped_invalid) > 0 && (
              <p className="send-summary-warn">
                {result.skipped_missing + result.skipped_invalid} מוזמנים לא קיבלו
                הזמנה עקב מספר טלפון חסר או לא תקין.
              </p>
            )}
            {result.failed > 0 && (
              <p className="send-summary-err">
                {result.failed} שליחות נכשלו. אפשר לנסות שוב רק עבורן.
              </p>
            )}
            {result.newly_activated && (
              <p className="send-summary-ok">מערכת אישורי ההגעה הופעלה ✓</p>
            )}
            <div className="send-dialog-actions">
              {result.failed > 0 && result.failed_ids.length > 0 && (
                <button
                  className="btn-primary"
                  onClick={() => onRetry(result.failed_ids)}
                >
                  ניסיון חוזר לנכשלים ({result.failed})
                </button>
              )}
              <button className="btn-ghost" onClick={onClose}>
                סגירה
              </button>
            </div>
          </div>
        )}

        {/* ---- מצב: אישור לפני שליחה ---- */}
        {phase === 'confirm' && (
          <SendConfirmStep
            preview={preview}
            error={error}
            onConfirm={onConfirm}
            onEditMessage={onEditMessage}
            onClose={onClose}
          />
        )}
      </div>
    </div>
  )
}

/**
 * שלב האישור: מציג תצוגה מקדימה של הודעת ההזמנה (עם קישור לעריכה) ורשימת
 * נמענים לבחירה (חיפוש + סימון). הזוג רואה בדיוק מה יישלח ולמי.
 */
function SendConfirmStep({
  preview,
  error,
  onConfirm,
  onEditMessage,
  onClose,
}: {
  preview: InvitationSendPreview
  error: string
  onConfirm: (opts?: { guestIds?: number[] }) => void
  onEditMessage: () => void
  onClose: () => void
}) {
  const [guests, setGuests] = useState<Guest[]>([])
  const [inviteBody, setInviteBody] = useState('')
  const [placeholders, setPlaceholders] = useState<TemplatePlaceholder[]>([])
  const [event, setEvent] = useState<EventDetails | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())

  // מוזמן יכול לקבל הזמנה רק אם יש לו מספר טלפון כלשהו (מספר לא-תקין יסונן בשרת).
  const canReceive = useCallback((g: Guest) => (g.phone || '').trim() !== '', [])

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [g, tpls, phs, ev] = await Promise.all([
          listGuests('', 500, 0),
          listAutomationTemplates(),
          getAutomationPlaceholders(),
          getEvent(),
        ])
        if (!alive) return
        setGuests(g.items)
        const invite = tpls.find((t) => t.kind === 'invitation') ?? tpls[0]
        setInviteBody(invite?.body ?? '')
        setPlaceholders(phs)
        setEvent(ev)
        // ברירת מחדל: מי שעדיין לא קיבל הזמנה ויש לו טלפון.
        setSelected(
          new Set(
            g.items
              .filter((x) => canReceive(x) && x.invite_status === 'not_sent')
              .map((x) => x.id),
          ),
        )
      } catch (err) {
        if (alive)
          setLoadError(
            err instanceof Error ? err.message : 'לא הצלחנו לטעון את רשימת המוזמנים',
          )
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [canReceive])

  const filtered = useMemo(() => {
    const q = search.trim()
    if (!q) return guests
    return guests.filter((g) => g.full_name.includes(q) || (g.phone || '').includes(q))
  }, [guests, search])

  // תצוגת ההודעה — מחליף כינויים בערכי דוגמה (כמו בעורך ההודעות).
  const previewText = useMemo(() => {
    const first = guests.find((g) => selected.has(g.id)) ?? guests[0]
    const couple =
      event && (event.groom_name || event.bride_name)
        ? `${event.groom_name} ו${event.bride_name}`
        : 'בני הזוג'
    const sample: Record<string, string> = {
      '{{guest_name}}': first?.full_name || 'דנה כהן',
      '{{couple_names}}': couple,
      '{{event_date}}': event?.event_date || 'תאריך האירוע',
      '{{event_time}}': event?.event_time || 'שעה',
      '{{venue_name}}': event?.venue_name || 'שם האולם',
      '{{venue_address}}': event?.venue_address || 'כתובת האולם',
      '{{maps_link}}': 'ניווט באמצעות Waze / Google Maps',
      '{{rsvp_link}}': 'קישור אישי לאישור הגעה',
    }
    let text = inviteBody
    for (const p of placeholders) {
      const val = sample[p.key] ?? ''
      if (p.token) text = text.split(p.token).join(val)
      text = text.split(p.key).join(val)
    }
    return text
  }, [inviteBody, placeholders, event, guests, selected])

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function selectNotSent() {
    setSelected(
      new Set(
        guests
          .filter((g) => canReceive(g) && g.invite_status === 'not_sent')
          .map((g) => g.id),
      ),
    )
  }

  function selectAll() {
    setSelected(new Set(guests.filter(canReceive).map((g) => g.id)))
  }

  const selectedCount = selected.size
  const missingPhone = preview.missing_phone
  const alreadySelected = guests.filter(
    (g) => selected.has(g.id) && g.invite_status !== 'not_sent',
  ).length

  if (loading) {
    return (
      <div className="send-confirm">
        <h3 className="send-dialog-title">שליחת הזמנות</h3>
        <p className="clar-sub">רגע, מכינים את רשימת המוזמנים…</p>
      </div>
    )
  }

  return (
    <div className="send-confirm">
      <h3 className="send-dialog-title">שליחת הזמנות</h3>

      {loadError && <p className="form-error">{loadError}</p>}

      {/* תצוגת ההודעה שתישלח + קישור לעריכה */}
      <div className="send-msg-preview">
        <div className="send-msg-head">
          <span className="mb-preview-label">ההודעה שתישלח</span>
          <button className="btn-text" onClick={onEditMessage}>
            לעריכת ההודעה
          </button>
        </div>
        <div className="wa-screen" dir="rtl">
          <div className="wa-bubble">
            {event?.invite_image && (
              <img
                className="wa-image"
                src={mediaUrl(event.invite_image)}
                alt="הזמנה"
              />
            )}
            <div className="wa-text">
              {previewText.trim() ? (
                previewText.split('\n').map((line, i) => (
                  <div key={i} className="wa-line">
                    {line || ' '}
                  </div>
                ))
              ) : (
                <span className="wa-empty">אין עדיין נוסח להודעה</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* בחירת נמענים */}
      <div className="send-recipients">
        <div className="send-recipients-head">
          <span className="mb-preview-label">למי לשלוח</span>
          <div className="send-recipients-quick">
            <button className="btn-text" onClick={selectNotSent}>
              מי שעדיין לא קיבל
            </button>
            <button className="btn-text" onClick={selectAll}>
              בחר הכל
            </button>
            <button className="btn-text" onClick={() => setSelected(new Set())}>
              נקה
            </button>
          </div>
        </div>

        <input
          className="send-recipients-search"
          type="search"
          dir="rtl"
          placeholder="חיפוש לפי שם או טלפון…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        <ul className="send-recipients-list">
          {filtered.map((g) => {
            const receivable = canReceive(g)
            return (
              <li key={g.id} className={`send-recipient-row ${receivable ? '' : 'disabled'}`}>
                <label>
                  <input
                    type="checkbox"
                    checked={selected.has(g.id)}
                    disabled={!receivable}
                    onChange={() => toggle(g.id)}
                  />
                  <span className="rsvp-name">{g.full_name}</span>
                  {g.invite_status && g.invite_status !== 'not_sent' && (
                    <span className="send-recipient-tag">כבר נשלח</span>
                  )}
                  {!receivable && (
                    <span className="send-recipient-tag warn">חסר טלפון</span>
                  )}
                </label>
              </li>
            )
          })}
          {filtered.length === 0 && (
            <li className="send-recipient-empty">לא נמצאו מוזמנים תואמים.</li>
          )}
        </ul>
      </div>

      <p className="send-confirm-line">
        יישלח ל־<strong>{selectedCount}</strong> מוזמנים.
      </p>
      {alreadySelected > 0 && (
        <p className="send-confirm-warn-line">
          {alreadySelected} מהנבחרים כבר קיבלו הזמנה — הם יקבלו אותה שוב.
        </p>
      )}
      {missingPhone > 0 && (
        <p className="clar-sub">
          {missingPhone} מוזמנים ללא מספר טלפון אינם ניתנים לבחירה.
        </p>
      )}
      <p className="clar-sub">
        לאחר השליחה יתחיל טיימר אישורי ההגעה, וכל התזכורות יחושבו מרגע זה.
      </p>

      {error && <p className="form-error">{error}</p>}

      <div className="send-dialog-actions">
        <button
          className="btn-primary"
          disabled={selectedCount === 0}
          onClick={() => onConfirm({ guestIds: [...selected] })}
        >
          שליחת ההזמנות ({selectedCount})
        </button>
        <button className="btn-ghost" onClick={onClose}>
          ביטול
        </button>
      </div>
    </div>
  )
}

function ActivateCard({ onSend }: { onSend: () => void }) {
  return (
    <div className="track-hero">
      <span className="track-hero-badge">מסלול אישורי הגעה</span>
      <h2 className="track-hero-title">הכנו עבורכם מסלול אישורי הגעה מלא</h2>
      <p className="track-hero-sub">
        כשתלחצו "שליחת הזמנות" נראה לכם בדיוק לכמה מוזמנים תישלח ההזמנה לפני
        שנשלח. אחרי אישורכם נשלח לכולם — ואז נמשיך לבד: תזכורות עדינות למי שעוד
        לא ענה, ורשימת מעקב טלפוני למי שצריך תשומת לב.
      </p>
      <ul className="track-flow">
        <li><span className="track-flow-num">1</span> הזמנה לכל המוזמנים</li>
        <li><span className="track-flow-num">2</span> תזכורת ראשונה אחרי 3 ימים</li>
        <li><span className="track-flow-num">3</span> תזכורת שנייה אחרי 6 ימים</li>
        <li><span className="track-flow-num">4</span> מעקב טלפוני למי שעדיין לא ענה</li>
      </ul>
      <button className="btn-primary track-activate-btn" onClick={onSend}>
        שליחת הזמנות
      </button>
      <span className="track-hero-note">
        אפשר לערוך את נוסח ההודעות למטה לפני השליחה.
      </span>
    </div>
  )
}

function TrackStatusCard({
  track,
  onResend,
}: {
  track: RsvpTrackStatus
  onResend: () => void
}) {
  const answered = track.confirmed + track.declined
  const total = track.total_guests || 1
  const pct = Math.round((answered / total) * 100)
  return (
    <div className="track-status">
      <div className="track-status-head">
        <div>
          <span className="track-hero-badge ok">המסלול פעיל</span>
          <h2 className="track-hero-title">מסלול אישורי ההגעה רץ עבורכם</h2>
        </div>
        <span className={`mode-badge ${track.mode}`}>
          {track.mode === 'mock'
            ? 'מצב תצוגה — עדיין לא שלחנו הודעות אמיתיות'
            : 'מצב חי — WhatsApp מחובר'}
        </span>
      </div>

      <div className="track-progress">
        <div className="track-progress-bar">
          <span className="track-progress-fill" style={{ width: `${pct}%` }} />
        </div>
        <span className="track-progress-label">
          {answered} מתוך {track.total_guests} מוזמנים כבר ענו ({pct}%)
        </span>
      </div>

      <div className="auto-stat-grid">
        <StatCard num={track.total_guests} label="סה״כ מוזמנים" />
        <StatCard num={track.invited} label="קיבלו הזמנה" />
        <StatCard num={track.confirmed} label="אישרו הגעה" tone="ok" />
        <StatCard num={track.pending} label="ממתינים לתשובה" tone="wait" />
        <StatCard num={track.declined} label="לא מגיעים" tone="err" />
        <StatCard num={track.in_phone_followup} label="במעקב טלפוני" />
      </div>

      <div className="track-resend">
        <button className="btn-ghost" onClick={onResend}>
          שליחת הזמנות
        </button>
        <span className="clar-sub">
          הוספתם מוזמנים חדשים? אפשר לשלוח להם הזמנה בלי לשלוח שוב למי שכבר קיבל.
        </span>
      </div>

      {track.phone_list.length > 0 && (
        <div className="track-phone">
          <h3 className="clar-title">רשימת מעקב טלפוני</h3>
          <span className="clar-sub">
            מוזמנים שעדיין לא ענו אחרי כל התזכורות — כדאי טלפון אישי.
          </span>
          <ul className="track-phone-list">
            {track.phone_list.map((row) => (
              <li key={row.guest_id} className="track-phone-row">
                <span className="rsvp-name">{row.guest_name}</span>
                <a className="track-phone-num" href={`tel:${row.phone}`}>
                  {row.phone || '—'}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

// ============ לשונית "מצב ומעקב" ============

function DashboardTab({
  refreshKey,
  onOpenTimeline,
  onGoTo,
}: {
  refreshKey: number
  onOpenTimeline: (guestId: number) => void
  onGoTo: (tab: Tab) => void
}) {
  const [dash, setDash] = useState<AutomationDashboard | null>(null)
  const [guests, setGuests] = useState<Guest[]>([])
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [d, g] = await Promise.all([
        getAutomationDashboard(),
        listGuests('', 300, 0),
      ])
      setDash(d)
      setGuests(g.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בטעינת המצב')
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh, refreshKey])

  return (
    <div className="auto-dashboard">
      {error && <p className="form-error">{error}</p>}

      {/* כרטיסי מצב */}
      <div className="auto-stat-grid">
        <StatCard num={dash?.total_guests} label="סה״כ מוזמנים" />
        <StatCard num={dash?.invited} label="קיבלו הזמנה" />
        <StatCard num={dash?.confirmed} label="אישרו הגעה" tone="ok" />
        <StatCard num={dash?.pending} label="ממתינים לתשובה" tone="wait" />
        <StatCard num={dash?.declined} label="לא מגיעים" tone="err" />
        <StatCard num={dash?.in_reminder_process} label="בתהליך תזכורות" />
      </div>

      {/* שורת סיכום מהירה */}
      <div className="auto-summary-row">
        {dash?.days_to_event != null && (
          <span className="auto-chip">
            {dash.days_to_event >= 0
              ? `${dash.days_to_event} ימים לאירוע`
              : 'האירוע כבר עבר'}
          </span>
        )}
        <span className="auto-chip">{dash?.active_rules ?? 0} חוקים פעילים</span>
        <button
          className="auto-chip auto-chip-btn"
          onClick={() => onGoTo('queue')}
          title="מעבר לתור לשליחה"
        >
          {dash?.due_now ?? 0} הודעות ממתינות בתור →
        </button>
      </div>

      {/* המלצות מעקב חכם */}
      {dash && dash.recommendations.length > 0 && (
        <div className="auto-recs">
          <h3 className="clar-title">מעקב חכם</h3>
          <ul className="auto-rec-list">
            {dash.recommendations.map((r, i) => (
              <li key={i} className={`auto-rec ${r.severity}`}>
                <span className="auto-rec-icon" aria-hidden>
                  {r.severity === 'warn' ? '⚠' : 'ℹ'}
                </span>
                <span>{r.text}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* רשימת מוזמנים עם גישה לציר זמן */}
      <div className="rsvp-guests">
        <div className="rsvp-guests-head">
          <h3 className="clar-title">מוזמנים</h3>
          <span className="clar-sub">לחצו "ציר זמן" כדי לראות את היסטוריית ההודעות של מוזמן.</span>
        </div>
        <ul className="rsvp-list">
          {guests.map((g) => (
            <li key={g.id} className="rsvp-row">
              <span className="rsvp-name">{g.full_name}</span>
              <span className={`rsvp-badge ${g.rsvp_status}`}>
                {RSVP_LABELS[g.rsvp_status]}
              </span>
              <button
                className="btn-text auto-timeline-btn"
                onClick={() => onOpenTimeline(g.id)}
              >
                ציר זמן
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

function StatCard({
  num,
  label,
  tone,
}: {
  num: number | undefined | null
  label: string
  tone?: 'ok' | 'err' | 'wait'
}) {
  return (
    <div className={`stat-card ${tone ?? ''}`}>
      <span className="stat-num">{num ?? '—'}</span>
      <span className="stat-label">{label}</span>
    </div>
  )
}

// ============ לשונית "שליחה ידנית" (הזרימה הקיימת) ============

function ManualTab({ onChanged }: { onChanged: () => void }) {
  const [summary, setSummary] = useState<RsvpSummary | null>(null)
  const [event, setEvent] = useState<EventDetails | null>(null)
  const [guests, setGuests] = useState<Guest[]>([])
  const [log, setLog] = useState<Message[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')

  const [template, setTemplate] = useState('')
  const [defaultTemplate, setDefaultTemplate] = useState('')
  const [placeholders, setPlaceholders] = useState<TemplatePlaceholder[]>([])
  const [preview, setPreview] = useState('')
  const [tplNote, setTplNote] = useState('')
  const [savingTpl, setSavingTpl] = useState(false)
  const tplRef = useRef<HTMLTextAreaElement | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [s, g, l, t, ev] = await Promise.all([
        rsvpSummary(),
        listGuests('', 200, 0),
        messageLog(20),
        getTemplate(),
        getEvent(),
      ])
      setSummary(s)
      setEvent(ev)
      setGuests(g.items)
      setLog(l)
      setTemplate(t.template)
      setDefaultTemplate(t.default_template)
      setPlaceholders(t.placeholders)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בטעינת נתוני RSVP')
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    if (!template) return
    const id = setTimeout(() => {
      previewTemplate(template)
        .then(setPreview)
        .catch(() => setPreview(''))
    }, 350)
    return () => clearTimeout(id)
  }, [template])

  function insertPlaceholder(key: string) {
    const ta = tplRef.current
    if (!ta) {
      setTemplate((t) => t + key)
      return
    }
    const start = ta.selectionStart
    const end = ta.selectionEnd
    setTemplate((t) => t.slice(0, start) + key + t.slice(end))
    setTimeout(() => {
      ta.focus()
      ta.selectionStart = ta.selectionEnd = start + key.length
    }, 0)
  }

  async function onSaveTemplate() {
    setSavingTpl(true)
    setTplNote('')
    setError('')
    try {
      const t = await saveTemplate(template)
      setTemplate(t.template)
      setTplNote('התבנית נשמרה ✓')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בשמירת התבנית')
    } finally {
      setSavingTpl(false)
    }
  }

  async function onSend(onlyPending: boolean) {
    setBusy(true)
    setError('')
    setNote('')
    try {
      const res = await sendInvitations(onlyPending)
      setNote(
        `נשלחו ${res.sent} הזמנות` +
          (res.failed ? ` · ${res.failed} נכשלו` : '') +
          (res.skipped ? ` · ${res.skipped} דולגו (ללא טלפון)` : '') +
          (res.mode === 'mock' ? ' · מצב בדיקה (לא נשלח בפועל)' : ''),
      )
      await refresh()
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בשליחת ההזמנות')
    } finally {
      setBusy(false)
    }
  }

  async function onReminders() {
    setBusy(true)
    setError('')
    setNote('')
    try {
      const res = await sendReminders()
      setNote(
        `נשלחו ${res.sent} תזכורות לממתינים` +
          (res.failed ? ` · ${res.failed} נכשלו` : '') +
          (res.skipped ? ` · ${res.skipped} דולגו (ללא טלפון)` : '') +
          (res.mode === 'mock' ? ' · מצב בדיקה (לא נשלח בפועל)' : ''),
      )
      await refresh()
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בשליחת התזכורות')
    } finally {
      setBusy(false)
    }
  }

  async function onReply(guestId: number, coming: boolean) {
    setError('')
    try {
      setSummary(await simulateReply(guestId, coming))
      await refresh()
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בעדכון התשובה')
    }
  }

  return (
    <div className="manual-tab">
      {/* ---- סיכום RSVP ---- */}
      <div className="rsvp-stats">
        <div className="stat-card ok">
          <span className="stat-num">{summary?.confirmed ?? '—'}</span>
          <span className="stat-label">אישרו הגעה</span>
        </div>
        <div className="stat-card err">
          <span className="stat-num">{summary?.declined ?? '—'}</span>
          <span className="stat-label">לא מגיעים</span>
        </div>
        <div className="stat-card wait">
          <span className="stat-num">{summary?.pending ?? '—'}</span>
          <span className="stat-label">ממתינים לתשובה</span>
        </div>
        <div className="stat-card">
          <span className="stat-num">{summary?.invitations_sent ?? '—'}</span>
          <span className="stat-label">הזמנות שנשלחו</span>
        </div>
      </div>

      {/* ---- תבנית הודעת הזמנה ---- */}
      <div className="tpl-editor">
        <div className="tpl-head">
          <h3 className="clar-title">תבנית הודעת ההזמנה</h3>
          <span className="clar-sub">
            כתבו את נוסח ההודעה. הוסיפו משתנים והם יוחלפו אוטומטית לכל מוזמן.
          </span>
        </div>

        <div className="tpl-placeholders">
          {placeholders.map((p) => (
            <button
              key={p.key}
              type="button"
              className="tpl-chip"
              title={p.desc}
              onClick={() => insertPlaceholder(p.key)}
            >
              {p.key}
            </button>
          ))}
        </div>

        <div className="tpl-grid">
          <textarea
            ref={tplRef}
            className="tpl-textarea"
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
            rows={6}
            dir="rtl"
          />
          <div className="tpl-preview">
            <span className="tpl-preview-label">תצוגה מקדימה</span>
            {event?.invite_image && (
              <img
                className="tpl-preview-img"
                src={mediaUrl(event.invite_image)}
                alt="הזמנה לחתונה"
              />
            )}
            <div className="tpl-preview-body">{preview || '—'}</div>
          </div>
        </div>

        <div className="tpl-actions">
          <button
            className="btn-primary"
            onClick={onSaveTemplate}
            disabled={savingTpl}
          >
            {savingTpl ? 'שומר…' : 'שמירת תבנית'}
          </button>
          <button
            className="btn-text"
            onClick={() => setTemplate(defaultTemplate)}
            disabled={savingTpl}
          >
            איפוס לברירת מחדל
          </button>
          {tplNote && <span className="tpl-saved">{tplNote}</span>}
        </div>
      </div>

      {/* ---- שליחת הזמנות ---- */}
      <div className="rsvp-actions">
        <button className="btn-primary" onClick={() => onSend(true)} disabled={busy}>
          {busy ? 'שולח…' : 'שליחת הזמנות לממתינים'}
        </button>
        <button className="btn-ghost" onClick={() => onSend(false)} disabled={busy}>
          שליחה לכולם מחדש
        </button>
        <button className="btn-ghost" onClick={onReminders} disabled={busy}>
          {busy ? 'שולח…' : 'שליחת תזכורת לממתינים'}
        </button>
        {summary && (
          <span className={`mode-badge ${summary.mode}`}>
            {summary.mode === 'mock'
              ? 'מצב בדיקה — לא נשלח WhatsApp אמיתי'
              : 'מצב חי — WhatsApp מחובר'}
          </span>
        )}
      </div>

      {note && <p className="rsvp-note">{note}</p>}
      {error && <p className="form-error">{error}</p>}

      {/* ---- רשימת מוזמנים + סימולציית תשובה ---- */}
      <div className="rsvp-guests">
        <div className="rsvp-guests-head">
          <h3 className="clar-title">תשובות מוזמנים</h3>
          {summary?.mode === 'mock' && (
            <span className="clar-sub">
              במצב בדיקה אפשר ללחוץ "מגיע/ה" או "לא" כדי לדמות תשובה של מוזמן.
            </span>
          )}
        </div>
        <ul className="rsvp-list">
          {guests.map((g) => (
            <li key={g.id} className="rsvp-row">
              <span className="rsvp-name">{g.full_name}</span>
              <span className={`rsvp-badge ${g.rsvp_status}`}>
                {RSVP_LABELS[g.rsvp_status]}
              </span>
              {summary?.mode === 'mock' && (
                <span className="rsvp-sim">
                  <button
                    className="btn-ghost clar-choice"
                    onClick={() => onReply(g.id, true)}
                  >
                    מגיע/ה
                  </button>
                  <button className="btn-text" onClick={() => onReply(g.id, false)}>
                    לא מגיע/ה
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      </div>

      {/* ---- יומן הודעות ---- */}
      {log.length > 0 && (
        <div className="rsvp-log">
          <h3 className="clar-title">יומן הודעות אחרון</h3>
          <ul className="log-list">
            {log.map((m) => (
              <li key={m.id} className={`log-row ${m.direction}`}>
                <span className="log-dir">
                  {m.direction === 'outbound' ? '↗ יוצאת' : '↘ נכנסת'}
                </span>
                <span className="log-body">{m.body.split('\n')[0]}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
