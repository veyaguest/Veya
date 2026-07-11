import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getEvent,
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
  EventDetails,
  Guest,
  Message,
  RsvpSummary,
  TemplatePlaceholder,
} from '../types'
import { RSVP_LABELS } from '../types'

export function RsvpPage() {
  const [summary, setSummary] = useState<RsvpSummary | null>(null)
  const [event, setEvent] = useState<EventDetails | null>(null)
  const [guests, setGuests] = useState<Guest[]>([])
  const [log, setLog] = useState<Message[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')

  // ---- תבנית הודעה ----
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
        listGuests(),
        messageLog(20),
        getTemplate(),
        getEvent(),
      ])
      setSummary(s)
      setEvent(ev)
      setGuests(g)
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

  // תצוגה מקדימה חיה (עם השהיה קלה כדי לא להציף את השרת)
  useEffect(() => {
    if (!template) return
    const id = setTimeout(() => {
      previewTemplate(template)
        .then(setPreview)
        .catch(() => setPreview(''))
    }, 350)
    return () => clearTimeout(id)
  }, [template])

  /** מוסיף משתנה במיקום הסמן בתוך תיבת התבנית. */
  function insertPlaceholder(key: string) {
    const ta = tplRef.current
    if (!ta) {
      setTemplate((t) => t + key)
      return
    }
    const start = ta.selectionStart
    const end = ta.selectionEnd
    setTemplate((t) => t.slice(0, start) + key + t.slice(end))
    requestAnimationFrame(() => {
      ta.focus()
      ta.selectionStart = ta.selectionEnd = start + key.length
    })
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
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בעדכון התשובה')
    }
  }

  return (
    <div className="rsvp-page">
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
        <button
          className="btn-primary"
          onClick={() => onSend(true)}
          disabled={busy}
        >
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
