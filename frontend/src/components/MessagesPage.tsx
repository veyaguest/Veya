import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  activateRsvpTrack,
  advanceRsvpTrack,
  getEvent,
  getRsvpTrack,
  listGuests,
  mediaUrl,
  previewCommunicationMessage,
  previewSend,
} from '../api'
import type {
  EventDetails,
  Guest,
  InvitationSendPreview,
  RsvpTrackActivateResult,
  RsvpTrackStatus,
  SendScope,
} from '../types'
import { activeEventTerms } from '../strings/eventTypes'
import { strings } from '../strings/he'
import { AddGuestForm } from './AddGuestForm'
import { CommunicationTab } from './CommunicationTab'
import { ImportDialog } from './ImportDialog'
import { MessageLibrary } from './MessageLibrary'
import { PasteImportDialog } from './PasteImportDialog'

type Tab = 'communication' | 'library'

const TABS: { key: Tab; label: string }[] = [
  { key: 'communication', label: 'תקשורת עם אורחים' },
  { key: 'library', label: 'ספריית הודעות מוכנות' },
]

/**
 * מסך ניהול ההודעות: בחירת סוג הודעה, נוסח, תצוגה מקדימה, ושליחה בפועל —
 * כל מה שקשור ל"מה אני שולח, למי ומתי". אישורי הגעה (מצב, מעקב WhatsApp,
 * לוח הזמנים) נמצאים במסך נפרד. הזוג רואה חוויה פשוטה (אשף/כרטיס הודעות),
 * ואילו אדמין רואה גם את הלשוניות הטכניות (תקשורת/ספרייה).
 */
export function MessagesPage({
  isAdmin,
  onNavigate,
}: {
  isAdmin: boolean
  onNavigate?: (page: 'guests') => void
}) {
  if (!isAdmin) return <CoupleMessagesView onNavigate={onNavigate} />
  return <AdminMessagesShell onNavigate={onNavigate} />
}

/**
 * מעטפת לאדמין: כברירת מחדל מציגה את חוויית הזוג, ומתג קטן מאפשר לעבור
 * לפאנל הניהול הטכני (תקשורת עם אורחים / ספריית הודעות מוכנות).
 */
function AdminMessagesShell({ onNavigate }: { onNavigate?: (page: 'guests') => void }) {
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
      {view === 'couple' ? (
        <CoupleMessagesView onNavigate={onNavigate} />
      ) : (
        <AdminMessagesView />
      )}
    </>
  )
}

function AdminMessagesView() {
  const [tab, setTab] = useState<Tab>('communication')

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

      {tab === 'communication' && <CommunicationTab />}
      {tab === 'library' && <MessageLibrary />}
    </div>
  )
}

// ============ מסך הזוג — ניהול הודעות ============

// שלבי דיאלוג השליחה: סגור / אישור / שולח (התקדמות) / סיכום.
type SendPhase = 'idle' | 'confirm' | 'sending' | 'summary'

function CoupleMessagesView({ onNavigate }: { onNavigate?: (page: 'guests') => void }) {
  const [track, setTrack] = useState<RsvpTrackStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  // כמה מוזמנים חדשים (עם טלפון תקין) עדיין לא קיבלו הזמנה — מזין את הבאנר.
  const [newCount, setNewCount] = useState(0)

  // מצב דיאלוג השליחה הידנית.
  const [phase, setPhase] = useState<SendPhase>('idle')
  const [preview, setPreview] = useState<InvitationSendPreview | null>(null)
  const [result, setResult] = useState<RsvpTrackActivateResult | null>(null)
  const [dialogError, setDialogError] = useState('')

  // בטעינה: טוענים סטטוס, ואם המסלול פעיל — מקדמים אותו אוטומטית (idempotent,
  // אותו קריאה שגם מסך "אישורי הגעה" מבצע — כך התזכורות ממשיכות לצאת גם
  // כשמבקרים רק כאן).
  const load = useCallback(async () => {
    setError('')
    try {
      const status = await getRsvpTrack()
      if (status.active) {
        const [, p] = await Promise.all([advanceRsvpTrack(), previewSend()])
        setTrack(status)
        setNewCount(p.not_yet_sent)
      } else {
        // לפני שליחה ראשונה: טוענים ספירה מקדימה כדי להזין את שלבי הוויזארד.
        const p = await previewSend()
        setTrack(status)
        setPreview(p)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.loadGenericRetry)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // רענון הספירה המקדימה בלבד (למשל אחרי הוספת מוזמנים באשף) — בלי לטעון מחדש
  // את כל המסך, כדי שסיכום המוכנות באשף יתעדכן מיד.
  const refreshPreview = useCallback(async () => {
    try {
      const p = await previewSend()
      setPreview(p)
      setNewCount(p.not_yet_sent)
    } catch {
      /* שקט — לא מפילים את המסך בגלל רענון ספירה */
    }
  }, [])

  // לחיצה על "שליחת הזמנות" — טוענים ספירה מקדימה ופותחים דיאלוג אישור.
  async function openSendDialog() {
    setDialogError('')
    setResult(null)
    try {
      const p = await previewSend()
      setPreview(p)
      setPhase('confirm')
    } catch (err) {
      setError(err instanceof Error ? err.message : strings.errors.loadGenericRetry)
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
        err instanceof Error ? err.message : strings.errors.rsvpSendGenericRetry,
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
        <p className="mb-empty">רגע, מכינים לכם את ניהול ההודעות…</p>
      </div>
    )
  }

  const active = track?.active

  return (
    <div className="rsvp-page couple-rsvp">
      <p className="page-intro">
        כאן תוכלו לבחור הודעות לאורחים, לתזמן ולשלוח אותן, ולוודא שכל מי
        שצריך לקבל הזמנה אכן קיבל אותה.
      </p>

      {error && <p className="form-error">{error}</p>}

      {!active ? (
        /* לפני שליחה ראשונה — אשף מודרך: עיצוב → מוזמנים → שליחה. */
        <FirstInviteWizard
          preview={preview}
          onSend={openSendDialog}
          onAddGuests={onNavigate ? () => onNavigate('guests') : undefined}
          onGuestsChanged={refreshPreview}
        />
      ) : (
        /* אחרי השליחה — כרטיס ההודעות הרגיל, עם אפשרות תמיד פתוחה לשלוח
           הזמנה למי שעוד לא קיבל. */
        <>
          {newCount > 0 && (
            <NewGuestsBanner count={newCount} onSend={openSendDialog} />
          )}
          <div id="mb-anchor">
            <CommunicationTab />
          </div>
          <div className="track-resend">
            <button className="btn-ghost" onClick={openSendDialog}>
              שליחת הזמנות
            </button>
            <span className="clar-sub">
              הוספתם מוזמנים חדשים? אפשר לשלוח להם הזמנה בלי לשלוח שוב למי
              שכבר קיבל.
            </span>
          </div>
        </>
      )}

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
              {result.failed > 0 ? strings.errors.rsvpSendPartialFail : strings.toasts.invitationsSent}
            </h3>
            <p className="send-summary-main">
              נשלחו <strong>{result.invitations_sent}</strong> הזמנות
              {mode === 'mock' && ' (עדיין לא נשלחות הודעות אמיתיות)'}
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
  const [previewText, setPreviewText] = useState('')
  const [event, setEvent] = useState<EventDetails | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<Set<number>>(new Set())

  // מוזמן יכול לקבל הזמנה רק אם יש לו מספר טלפון כלשהו (מספר לא-תקין יסונן בשרת).
  const canReceive = useCallback((g: Guest) => (g.phone || '').trim() !== '', [])

  // מי שאפשר לשלוח אליו הזמנה עכשיו: יש טלפון ועדיין לא קיבל הזמנה.
  // כל אורח מקבל הזמנה פעם אחת בלבד — שליחה חוזרת שמורה לאדמין (בפאנל הניהול).
  const canSend = useCallback(
    (g: Guest) => (g.phone || '').trim() !== '' && g.invite_status === 'not_sent',
    [],
  )

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [g, text, ev] = await Promise.all([
          listGuests('', 500, 0),
          previewCommunicationMessage('invitation'),
          getEvent(),
        ])
        if (!alive) return
        setGuests(g.items)
        setPreviewText(text)
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
            err instanceof Error ? err.message : strings.errors.rsvpGuestsLoadFailed,
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

  function toggle(id: number) {
    const g = guests.find((x) => x.id === id)
    if (g && !canSend(g)) return // מי שכבר קיבל / בלי טלפון — לא ניתן לבחירה
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function selectNotSent() {
    setSelected(new Set(guests.filter(canSend).map((g) => g.id)))
  }

  const selectedCount = selected.size
  const missingPhone = preview.missing_phone

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
              בחר את כל מי שעדיין לא קיבל
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
            const sendable = canSend(g)
            const alreadySent = !!g.invite_status && g.invite_status !== 'not_sent'
            return (
              <li key={g.id} className={`send-recipient-row ${sendable ? '' : 'disabled'}`}>
                <label>
                  <input
                    type="checkbox"
                    checked={selected.has(g.id)}
                    disabled={!sendable}
                    onChange={() => toggle(g.id)}
                  />
                  <span className="rsvp-name">{g.full_name}</span>
                  {alreadySent && (
                    <span className="send-recipient-tag">כבר קיבל/ה — פעם אחת בלבד</span>
                  )}
                  {!canReceive(g) && (
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
      {preview.already_sent > 0 && (
        <p className="clar-sub">
          {preview.already_sent} מוזמנים כבר קיבלו הזמנה — כל מוזמן מקבל הזמנה פעם
          אחת בלבד, ולכן לא תישלח אליהם שוב.
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

// שלבי האשף לשליחה הראשונית — מוצגים כפס התקדמות בראש המסך.
// פונקציה (לא קבוע) כי guestsLabel תלוי בסוג האירוע הפעיל.
function wizardSteps(guestsLabel: string) {
  return [
    { n: 1, label: 'עיצוב ההזמנה' },
    { n: 2, label: guestsLabel },
    { n: 3, label: 'תצוגה ושליחה' },
  ]
}

/**
 * אשף שליחת ההזמנה הראשונה — מוביל את הזוג שלב אחר שלב עם פס התקדמות:
 * (1) עיצוב ההזמנה, (2) בדיקת רשימת המוזמנים, (3) סקירה ושליחה.
 * המעבר בין השלבים אינו מאבד מידע (כל השלבים נשארים טעונים ורק מוסתרים),
 * כך שאפשר לחזור אחורה בלי לאבד עריכות. השליחה בפועל נעשית בדיאלוג האישור.
 */
function FirstInviteWizard({
  preview,
  onSend,
  onAddGuests,
  onGuestsChanged,
}: {
  preview: InvitationSendPreview | null
  onSend: () => void
  onAddGuests?: () => void
  onGuestsChanged?: () => void
}) {
  const [step, setStep] = useState(1)

  // הוספת מוזמנים ישירות מתוך האשף — שימוש חוזר בדיאלוגים הקיימים.
  const [importFile, setImportFile] = useState<File | null>(null)
  const [showPaste, setShowPaste] = useState(false)
  const [showAdd, setShowAdd] = useState(false)
  const [addNote, setAddNote] = useState('')
  const fileInput = useRef<HTMLInputElement | null>(null)

  function afterGuestsChanged(msg: string) {
    setImportFile(null)
    setShowPaste(false)
    setShowAdd(false)
    setAddNote(msg)
    onGuestsChanged?.()
    setTimeout(() => setAddNote(''), 4000)
  }

  const total = preview?.total_guests ?? 0
  const sendable = preview?.not_yet_sent ?? 0
  const missing = preview?.missing_phone ?? 0
  const invalid = preview?.invalid_phone ?? 0
  const badPhone = missing + invalid
  const steps = wizardSteps(activeEventTerms().guestsLabel)
  const pct = ((step - 1) / (steps.length - 1)) * 100

  return (
    <div className="invite-wizard">
      {/* פס התקדמות */}
      <div className="wiz-header">
        <ol className="wiz-steps">
          {steps.map((s) => (
            <li
              key={s.n}
              className={`wiz-step ${step === s.n ? 'active' : ''} ${
                step > s.n ? 'done' : ''
              }`}
            >
              <button
                type="button"
                className="wiz-step-btn"
                onClick={() => setStep(s.n)}
                disabled={s.n > step && !(s.n === step + 1)}
              >
                <span className="wiz-step-num">{step > s.n ? '✓' : s.n}</span>
                <span className="wiz-step-label">{s.label}</span>
              </button>
            </li>
          ))}
        </ol>
        <div className="wiz-progress">
          <span className="wiz-progress-fill" style={{ width: `${pct}%` }} />
        </div>
      </div>

      {/* ---- שלב 1: עיצוב ההזמנה ---- */}
      <section className="wiz-panel" hidden={step !== 1}>
        <div className="wiz-panel-head">
          <span className="wiz-panel-badge">שלב 1 מתוך 3</span>
          <h2 className="wiz-title">עיצוב ההזמנה</h2>
          <p className="wiz-sub">
            ערכו את נוסח ההזמנה בכרטיס הראשון למטה. תראו תצוגה מקדימה חיה
            בדיוק כפי שהמוזמנים יראו ב-WhatsApp.
          </p>
        </div>
        <div id="mb-anchor">
          <CommunicationTab />
        </div>
        <div className="wiz-nav">
          <span />
          <button className="btn-primary" onClick={() => setStep(2)}>
            המשך למוזמנים →
          </button>
        </div>
      </section>

      {/* ---- שלב 2: מוזמנים ---- */}
      <section className="wiz-panel" hidden={step !== 2}>
        <div className="wiz-panel-head">
          <span className="wiz-panel-badge">שלב 2 מתוך 3</span>
          <h2 className="wiz-title">מי מקבל את ההזמנה?</h2>
          <p className="wiz-sub">
            בדקו שהרשימה מוכנה. אפשר להוסיף מוזמנים או לתקן מספרי טלפון במסך ניהול
            המוזמנים, ולחזור לכאן להמשך.
          </p>
        </div>

        <div className="auto-stat-grid wiz-guests-grid">
          <StatCard num={total} label="סה״כ מוזמנים" />
          <StatCard num={sendable} label="מוכנים לשליחה" tone="ok" />
          <StatCard num={missing} label="ללא טלפון" tone={missing ? 'wait' : undefined} />
          <StatCard num={invalid} label="טלפון לא תקין" tone={invalid ? 'err' : undefined} />
        </div>

        {sendable === 0 ? (
          <p className="wiz-warn">
            אין עדיין מוזמנים עם מספר טלפון תקין. הוסיפו מוזמנים כדי שנוכל לשלוח את
            ההזמנה.
          </p>
        ) : (
          <p className="clar-sub wiz-guests-note">
            <strong>{sendable}</strong> מוזמנים יקבלו את ההזמנה כעת.
            {badPhone > 0 &&
              ` ${badPhone} ללא טלפון תקין לא ייכללו — אפשר לתקן במסך המוזמנים.`}
          </p>
        )}

        {/* הוספת מוזמנים מבלי לצאת מהאשף */}
        <div className="wiz-add">
          <span className="wiz-add-label">הוספת מוזמנים:</span>
          <div className="wiz-add-actions">
            <button
              className="btn-ghost"
              onClick={() => fileInput.current?.click()}
            >
              📄 העלאת Excel
            </button>
            <button className="btn-ghost" onClick={() => setShowPaste(true)}>
              📋 הדבקת רשימה
            </button>
            <button className="btn-ghost" onClick={() => setShowAdd(true)}>
              ➕ הוספה ידנית
            </button>
          </div>
          <input
            ref={fileInput}
            type="file"
            accept=".xlsx,.xlsm,.csv"
            style={{ display: 'none' }}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) setImportFile(f)
              e.target.value = ''
            }}
          />
        </div>

        {addNote && <p className="rsvp-note wiz-add-note">{addNote}</p>}

        {onAddGuests && (
          <button className="btn-text wiz-guests-link" onClick={onAddGuests}>
            לניהול מלא של המוזמנים — עברו למסך המוזמנים →
          </button>
        )}

        <div className="wiz-nav">
          <button className="btn-ghost" onClick={() => setStep(1)}>
            ← חזרה
          </button>
          <button
            className="btn-primary"
            disabled={sendable === 0}
            onClick={() => setStep(3)}
          >
            המשך לתצוגה →
          </button>
        </div>
      </section>

      {/* ---- שלב 3: תצוגה ושליחה ---- */}
      <section className="wiz-panel" hidden={step !== 3}>
        <div className="wiz-panel-head">
          <span className="wiz-panel-badge">שלב 3 מתוך 3</span>
          <h2 className="wiz-title">כמעט שם — סקירה ושליחה</h2>
          <p className="wiz-sub">
            זו הסקירה האחרונה. בלחיצה על "שליחת הזמנות" נציג לכם בדיוק את ההודעה
            ואת רשימת הנמענים לאישור סופי לפני השליחה.
          </p>
        </div>

        <ul className="wiz-review-list">
          <li>
            <span>ההזמנה מוכנה לשליחה</span>
            <span className="wiz-review-ok">✓</span>
          </li>
          <li>
            <span>מוזמנים שיקבלו את ההזמנה</span>
            <strong>{sendable}</strong>
          </li>
          {badPhone > 0 && (
            <li>
              <span>ללא טלפון תקין (לא ייכללו)</span>
              <strong>{badPhone}</strong>
            </li>
          )}
        </ul>

        <p className="clar-sub">
          מיד לאחר השליחה יתחיל טיימר אישורי ההגעה וייפתח מסך המעקב המלא — תזכורות
          ומעקב טלפוני יתנהלו אוטומטית.
        </p>

        <div className="wiz-nav">
          <button className="btn-ghost" onClick={() => setStep(2)}>
            ← חזרה
          </button>
          <button
            className="btn-primary track-activate-btn"
            disabled={sendable === 0}
            onClick={onSend}
          >
            שליחת הזמנות
          </button>
        </div>
      </section>

      {/* דיאלוגי הוספת מוזמנים (שימוש חוזר ברכיבים הקיימים) */}
      {importFile && (
        <ImportDialog
          file={importFile}
          onClose={() => setImportFile(null)}
          onImported={(created, skipped) =>
            afterGuestsChanged(
              `נוספו ${created} מוזמנים${skipped ? ` · ${skipped} כפילויות דולגו` : ''}`,
            )
          }
        />
      )}

      {showPaste && (
        <PasteImportDialog
          onClose={() => setShowPaste(false)}
          onImported={(created, skipped) =>
            afterGuestsChanged(
              `נוספו ${created} מוזמנים${skipped ? ` · ${skipped} כפילויות דולגו` : ''}`,
            )
          }
        />
      )}

      {showAdd && (
        <div className="overlay" onClick={() => setShowAdd(false)}>
          <div
            className="dialog edit-guest-dialog"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="dialog-head">
              <h2>הוספת מוזמן</h2>
              <button className="x" onClick={() => setShowAdd(false)}>
                ✕
              </button>
            </div>
            <AddGuestForm
              onAdded={() => afterGuestsChanged('המוזמן נוסף')}
              onCancel={() => setShowAdd(false)}
            />
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * באנר "נוספו מוזמנים חדשים" — מופיע רק אחרי שההזמנה הראשונה נשלחה וכשיש
 * מוזמנים חדשים (עם טלפון תקין) שעדיין לא קיבלו הזמנה. השליחה מכאן תגיע רק
 * אליהם — בלי לשלוח שוב למי שכבר קיבל, ובלי לפגוע במעקב אישורי ההגעה הקיים.
 */
function NewGuestsBanner({ count, onSend }: { count: number; onSend: () => void }) {
  return (
    <div className="new-guests-banner" role="status">
      <div className="new-guests-banner-text">
        <span className="new-guests-banner-icon" aria-hidden>
          👋
        </span>
        <span>
          נוספו <strong>{count}</strong>{' '}
          {count === 1 ? 'מוזמן/ת חדש/ה שעדיין לא קיבל/ה' : 'מוזמנים חדשים שעדיין לא קיבלו'}{' '}
          הזמנה.
        </span>
      </div>
      <button className="btn-primary new-guests-banner-btn" onClick={onSend}>
        שליחת הזמנות למוזמנים החדשים
      </button>
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
