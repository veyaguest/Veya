import { useCallback, useEffect, useState } from 'react'
import {
  listGuests,
  messageLog,
  rsvpSummary,
  sendInvitations,
  simulateReply,
} from '../api'
import type { Guest, Message, RsvpSummary } from '../types'
import { RSVP_LABELS } from '../types'

export function RsvpPage() {
  const [summary, setSummary] = useState<RsvpSummary | null>(null)
  const [guests, setGuests] = useState<Guest[]>([])
  const [log, setLog] = useState<Message[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [note, setNote] = useState('')

  const refresh = useCallback(async () => {
    try {
      const [s, g, l] = await Promise.all([
        rsvpSummary(),
        listGuests(),
        messageLog(20),
      ])
      setSummary(s)
      setGuests(g)
      setLog(l)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'שגיאה בטעינת נתוני RSVP')
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

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

      {/* ---- שליחת הזמנות ---- */}
      <div className="rsvp-actions">
        <button
          className="btn-primary"
          onClick={() => onSend(true)}
          disabled={busy}
        >
          {busy ? 'שולח…' : 'שלח הזמנות לממתינים'}
        </button>
        <button className="btn-ghost" onClick={() => onSend(false)} disabled={busy}>
          שלח לכולם מחדש
        </button>
        {summary && (
          <span className={`mode-badge ${summary.mode}`}>
            {summary.mode === 'mock'
              ? 'מצב בדיקה — לא נשלח וואטסאפ אמיתי'
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
