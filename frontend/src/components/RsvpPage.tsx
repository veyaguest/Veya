import { useCallback, useEffect, useRef, useState } from 'react'
import {
  activateRsvpTrack,
  advanceRsvpTrack,
  getAutomationDashboard,
  getEvent,
  getRsvpTrack,
  getTemplate,
  listGuests,
  messageLog,
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
  Message,
  RsvpSummary,
  RsvpTrackStatus,
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

function CoupleRsvpView() {
  const [track, setTrack] = useState<RsvpTrackStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [activating, setActivating] = useState(false)
  const [note, setNote] = useState('')
  const [error, setError] = useState('')

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

  async function onActivate() {
    setActivating(true)
    setError('')
    setNote('')
    try {
      const res = await activateRsvpTrack()
      setTrack(res)
      setNote(
        `המסלול הופעל! נשלחו ${res.invitations_sent} הזמנות` +
          (res.mode === 'mock' ? ' (מצב תצוגה — עדיין לא שלחנו הודעות אמיתיות)' : ''),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : 'לא הצלחנו להפעיל כרגע, ננסה שוב')
    } finally {
      setActivating(false)
    }
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
        <ActivateCard onActivate={onActivate} busy={activating} />
      ) : (
        track && <TrackStatusCard track={track} />
      )}

      <MessageBuilder />
    </div>
  )
}

function ActivateCard({
  onActivate,
  busy,
}: {
  onActivate: () => void
  busy: boolean
}) {
  return (
    <div className="track-hero">
      <span className="track-hero-badge">מסלול אישורי הגעה</span>
      <h2 className="track-hero-title">הכנו עבורכם מסלול אישורי הגעה מלא</h2>
      <p className="track-hero-sub">
        ברגע שתפעילו, נשלח לכל המוזמנים הזמנה אישית — ואז אנחנו נמשיך לבד:
        תזכורות עדינות למי שעוד לא ענה, ורשימת מעקב טלפוני למי שצריך תשומת לב.
        אתם רק צריכים לאשר את הנוסח.
      </p>
      <ul className="track-flow">
        <li><span className="track-flow-num">1</span> הזמנה לכל המוזמנים</li>
        <li><span className="track-flow-num">2</span> תזכורת ראשונה אחרי 3 ימים</li>
        <li><span className="track-flow-num">3</span> תזכורת שנייה אחרי 6 ימים</li>
        <li><span className="track-flow-num">4</span> מעקב טלפוני למי שעדיין לא ענה</li>
      </ul>
      <button className="btn-primary track-activate-btn" onClick={onActivate} disabled={busy}>
        {busy ? 'מפעיל…' : 'הפעלת מסלול אישורי ההגעה'}
      </button>
      <span className="track-hero-note">
        אפשר לערוך את נוסח ההודעות למטה לפני ואחרי ההפעלה.
      </span>
    </div>
  )
}

function TrackStatusCard({ track }: { track: RsvpTrackStatus }) {
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
                src={event.invite_image}
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
